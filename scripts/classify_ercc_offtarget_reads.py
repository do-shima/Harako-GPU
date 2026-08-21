"""Classify Salmon ERCC-to-human mappings with a fixed independent oracle."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from harako_gpu.services.external_truth_cause_isolation import (
    OffTargetClass,
    OffTargetRates,
    classify_offtarget_pair,
    classify_preprocessing_effect,
    exact_reference_support,
)


MINIMAP_IMAGE = "quay.io/biocontainers/minimap2@sha256:0c397895db3b494baa4f78de7110d516a1a57707d9c7df456634220bffd965ba"
TRAINING = ("SRR896983", "SRR896985", "SRR897015", "SRR897017")
HOLDOUT = ("SRR896987", "SRR896989", "SRR897019", "SRR897021")


def normalized_name(value: str) -> str:
    return value.split()[0].removesuffix("/1").removesuffix("/2")


def fasta_records(path: Path):
    handle = gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open("r", encoding="utf-8")
    with handle:
        name = None
        sequence: list[str] = []
        for line in handle:
            if line.startswith(">"):
                if name is not None:
                    yield name, "".join(sequence)
                name, sequence = line[1:].strip(), []
            else:
                sequence.append(line.strip().upper())
        if name is not None:
            yield name, "".join(sequence)


def prepare_reference(root: Path) -> tuple[Path, dict[str, str]]:
    output_root = root / "references/cause-isolation"
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root / "ercc-mitochondrial-diagnostic.fa"
    class_sequences: dict[str, list[str]] = {"human_mt": [], "ercc": []}
    rows: list[tuple[str, str]] = []
    for name, sequence in fasta_records(root / "references/ercc92/ERCC92.fa"):
        rows.append((f"ERCC|{name.split()[0]}", sequence))
        class_sequences["ercc"].append(sequence)
    for name, sequence in fasta_records(root / "references/gencode-v49/gencode.v49.transcripts.fa.gz"):
        if "|MT-" in name:
            rows.append((f"HUMAN_MT|{name.split()[0]}", sequence))
            class_sequences["human_mt"].append(sequence)
    for name, sequence in fasta_records(root / "references/gencode-v49/GRCh38.primary_assembly.genome.fa.gz"):
        if name.split()[0] in {"chrM", "MT"}:
            rows.append((f"HUMAN_MT|{name.split()[0]}", sequence))
            class_sequences["human_mt"].append(sequence)
    if len(class_sequences["ercc"]) != 92 or not class_sequences["human_mt"]:
        raise ValueError("Diagnostic reference identity is incomplete")
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for name, sequence in rows:
            handle.write(f">{name}\n{sequence}\n")
    return output, {name: ("N" * 120).join(values) for name, values in class_sequences.items()}


def salmon_mappings(path: Path) -> tuple[set[str], dict[str, Counter[str]]]:
    names: set[str] = set()
    targets: dict[str, Counter[str]] = defaultdict(Counter)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("@"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 11 or fields[2] == "*":
                continue
            name = normalized_name(fields[0])
            names.add(name)
            target = fields[2].split("|")[5] if fields[2].startswith("ENST") and len(fields[2].split("|")) > 5 else fields[2]
            targets[name][target] += 1
    return names, targets


def load_selected_pairs(r1: Path, r2: Path, selected: set[str]) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    with gzip.open(r1, "rt", encoding="ascii") as left, gzip.open(r2, "rt", encoding="ascii") as right:
        while True:
            l = [left.readline() for _ in range(4)]
            r = [right.readline() for _ in range(4)]
            if not l[0] and not r[0]:
                break
            if not all(l) or not all(r):
                raise ValueError("Truncated paired FASTQ")
            left_name, right_name = normalized_name(l[0][1:]), normalized_name(r[0][1:])
            if left_name != right_name:
                raise ValueError("Orphan or reordered paired FASTQ")
            if left_name in selected:
                result[left_name] = (l[1].strip().upper(), r[1].strip().upper())
    missing = selected - set(result)
    if missing:
        raise ValueError(f"Selected read IDs missing from FASTQ: {len(missing)}")
    return result


def write_pairs(root: Path, sample: str, kind: str, pairs: dict[str, tuple[str, str]]) -> tuple[Path, Path]:
    output = root / "runs/cause-isolation" / sample / "oracle-input"
    output.mkdir(parents=True, exist_ok=True)
    paths = output / f"{kind}_R1.fastq", output / f"{kind}_R2.fastq"
    with paths[0].open("w", encoding="ascii", newline="\n") as left, paths[1].open("w", encoding="ascii", newline="\n") as right:
        for name in sorted(pairs):
            r1, r2 = pairs[name]
            left.write(f"@{name}/1\n{r1}\n+\n{'I' * len(r1)}\n")
            right.write(f"@{name}/2\n{r2}\n+\n{'I' * len(r2)}\n")
    return paths


def run_minimap(root: Path, reference: Path, reads: tuple[Path, Path], output: Path) -> None:
    relative_reference = reference.relative_to(root).as_posix()
    r1, r2 = (path.relative_to(root).as_posix() for path in reads)
    argv = [
        "docker", "run", "--rm", "-v", f"{root}:/runtime:ro", MINIMAP_IMAGE,
        "minimap2", "-x", "sr", "-a", "--secondary=yes", "-t", "2",
        f"/runtime/{relative_reference}", f"/runtime/{r1}", f"/runtime/{r2}",
    ]
    with output.open("wb") as stdout, output.with_suffix(".stderr.txt").open("wb") as stderr:
        completed = subprocess.run(argv, stdout=stdout, stderr=stderr, check=False)
    if completed.returncode:
        raise RuntimeError(f"minimap2 failed for {output}")


def minimap_scores(path: Path) -> dict[str, dict[str, int]]:
    per_read: dict[tuple[str, str, int], int] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("@"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 12 or fields[2] == "*":
                continue
            flag = int(fields[1])
            mate = 1 if flag & 64 else 2 if flag & 128 else 0
            reference_class = "human_mt" if fields[2].startswith("HUMAN_MT|") else "ercc"
            score_tags = [int(tag[5:]) for tag in fields[11:] if tag.startswith("AS:i:")]
            if not score_tags:
                continue
            key = (normalized_name(fields[0]), reference_class, mate)
            per_read[key] = max(per_read.get(key, -10**9), score_tags[0])
    scores: dict[str, dict[str, int]] = defaultdict(dict)
    names = {key[0] for key in per_read}
    for name in names:
        for reference_class in ("human_mt", "ercc"):
            values = [per_read[(name, reference_class, mate)] for mate in (1, 2) if (name, reference_class, mate) in per_read]
            if values:
                scores[name][reference_class] = sum(values)
    return scores


def quant_mass(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        return str(sum((float(row["NumReads"]) for row in csv.DictReader(handle, delimiter="\t")), 0.0))


def raw_paths(root: Path, sample: str) -> tuple[Path, Path]:
    base = root / "ercc/raw" if sample in TRAINING else root / "ercc/holdout/raw"
    return base / f"{sample}_1.fastq.gz", base / f"{sample}_2.fastq.gz"


def processed_paths(root: Path, sample: str) -> tuple[Path, Path]:
    base = root / "runs/preprocessing" / sample / "repeat-1" if sample in TRAINING else root / "ercc/holdout/processed" / sample
    return base / f"{sample}_R1.fastq.gz", base / f"{sample}_R2.fastq.gz"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.runtime_root.resolve()
    reference, reference_classes = prepare_reference(root)
    report = {
        "schema_version": 1,
        "minimap_image": MINIMAP_IMAGE,
        "diagnostic_reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "lanes": {},
    }
    for sample in (*TRAINING, *HOLDOUT):
        sample_root = root / "runs/cause-isolation" / sample
        names, salmon_targets = salmon_mappings(sample_root / "combined-mappings/mappings.sam")
        processed = load_selected_pairs(*processed_paths(root, sample), names)
        raw = load_selected_pairs(*raw_paths(root, sample), names)
        processed_subset = write_pairs(root, sample, "processed", processed)
        raw_subset = write_pairs(root, sample, "raw", raw)
        processed_sam, raw_sam = sample_root / "oracle-processed.sam", sample_root / "oracle-raw.sam"
        run_minimap(root, reference, processed_subset, processed_sam)
        run_minimap(root, reference, raw_subset, raw_sam)
        processed_scores, raw_scores = minimap_scores(processed_sam), minimap_scores(raw_sam)
        sequence_duplicates = Counter(processed.values())
        classes: Counter[str] = Counter()
        preprocessing: Counter[str] = Counter()
        top_targets: Counter[str] = Counter()
        details = []
        for name in sorted(names):
            reads = processed[name]
            exact = exact_reference_support(reads, reference_classes)
            scores = processed_scores.get(name, {})
            classification = classify_offtarget_pair(
                reads, human_score=scores.get("human_mt"), ercc_score=scores.get("ercc"), exact_support=exact,
            )
            raw_exact = exact_reference_support(raw[name], reference_classes)
            raw_class = classify_offtarget_pair(
                raw[name], human_score=raw_scores.get(name, {}).get("human_mt"),
                ercc_score=raw_scores.get(name, {}).get("ercc"), exact_support=raw_exact,
            )
            effect = classify_preprocessing_effect(
                raw[name], reads, raw_supported=raw_class is OffTargetClass.HUMAN_MT_UNIQUE,
                processed_supported=classification is OffTargetClass.HUMAN_MT_UNIQUE,
            )
            classes[classification.value] += 1
            preprocessing[effect.value] += 1
            top_targets.update(salmon_targets[name])
            details.append({
                "opaque_read_id": hashlib.sha256(name.encode()).hexdigest()[:20],
                "classification": classification.value,
                "raw_classification": raw_class.value,
                "preprocessing": effect.value,
                "human_score": scores.get("human_mt"),
                "ercc_score": scores.get("ercc"),
                "exact_support": sorted(exact),
                "duplicate_count": sequence_duplicates[reads],
                "salmon_targets": [target for target, _ in salmon_targets[name].most_common(5)],
            })
        metadata = json.loads((sample_root / "combined-mappings/aux_info/meta_info.json").read_text())
        if len(names) != int(metadata["num_mapped"]):
            raise ValueError(f"SAM/metadata mapped-fragment mismatch for {sample}")
        ercc_meta_path = (
            root / "runs/salmon-2.5.1" / sample / "threads-6-run-1/aux_info/meta_info.json"
            if sample in TRAINING else sample_root / "ercc-only/aux_info/meta_info.json"
        )
        ercc_quant_path = ercc_meta_path.parents[1] / "quant.sf"
        ercc_meta = json.loads(ercc_meta_path.read_text())
        rates = OffTargetRates(
            int(metadata["num_processed"]), len(names), classes[OffTargetClass.HUMAN_MT_UNIQUE.value],
            classes[OffTargetClass.ERCC_UNIQUE_MISASSIGNED.value], int(ercc_meta["num_mapped"]),
            classes[OffTargetClass.EXACT_TIE.value], classes[OffTargetClass.AMBIGUOUS.value],
        )
        rates.validate()
        report["lanes"][sample] = {
            "role": "training" if sample in TRAINING else "holdout",
            "mix": "Mix1" if sample.startswith("SRR896") else "Mix2",
            "processed_fragments": rates.processed_fragments,
            "salmon_combined_mapped": len(names),
            "salmon_combined_fraction": len(names) / rates.processed_fragments,
            "ercc_only_mapped": int(ercc_meta["num_mapped"]),
            "ercc_only_estimated_mass": quant_mass(ercc_quant_path),
            "classes": dict(classes),
            "preprocessing": dict(preprocessing),
            "sample_purity_rate": rates.sample_purity_rate,
            "algorithmic_misassignment_rate": rates.algorithmic_misassignment_rate,
            "ambiguous_rate": rates.ambiguous_rate,
            "top_salmon_targets": top_targets.most_common(10),
            "details": details,
        }
    args.output.resolve().write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {sample: {key: value for key, value in row.items() if key != "details"} for sample, row in report["lanes"].items()}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
