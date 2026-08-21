"""Build, validate, and inspect descriptive concordance reports."""

import csv
import io
import json
from pathlib import Path

import typer

from harako_gpu.adapters.filesystem import sha256_path, write_new_text
from harako_gpu.core.canonical import sha256_payload
from harako_gpu.services.concordance import (
    compare_abundance, compare_orthogonal_gene_counts, parse_gtf_annotations, parse_quant_sf,
    ORTHOGONAL_GENE_CONCORDANCE_ARTIFACT, render_summary_html, result_dict, stratified_concordance,
    stratified_orthogonal_concordance,
)
from harako_gpu.services.quantification_profiles import get_profile


concordance_app = typer.Typer(help="Build or inspect profile concordance artifacts.", add_completion=False)


def _quant(path: Path):
    return {row.feature_id: row for row in parse_quant_sf(path.read_text(encoding="utf-8"))}


def _counts(path: Path) -> dict[str, float]:
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")), delimiter="\t")
    if reader.fieldnames != ["gene_id", "count"]:
        raise ValueError("Selected gene counts must contain gene_id and count")
    return {row["gene_id"]: float(row["count"]) for row in reader}


@concordance_app.command("build")
def build(
    primary_transcript: Path = typer.Option(..., exists=True, dir_okay=False),
    secondary_transcript: Path = typer.Option(..., exists=True, dir_okay=False),
    primary_gene: Path = typer.Option(..., exists=True, dir_okay=False),
    secondary_gene: Path = typer.Option(..., exists=True, dir_okay=False),
    primary_profile_id: str = typer.Option(...), secondary_profile_id: str = typer.Option(...),
    output_dir: Path = typer.Option(...), project_id: str = typer.Option(...),
    analysis_series_id: str = typer.Option(...), reference_pack_id: str = typer.Option(...),
    library_type: str = typer.Option(...), processed_fastq_identity: str = typer.Option(...),
    star_counts: Path | None = typer.Option(None, exists=True, dir_okay=False),
    gtf: Path | None = typer.Option(None, exists=True, dir_okay=False),
) -> None:
    try:
        primary, secondary = get_profile(primary_profile_id), get_profile(secondary_profile_id)
        if primary.profile_id == secondary.profile_id:
            raise ValueError("Primary and secondary profiles must differ")
        pt, st, pg, sg = _quant(primary_transcript), _quant(secondary_transcript), _quant(primary_gene), _quant(secondary_gene)
        transcript = compare_abundance({key: row.tpm for key, row in pt.items()}, {key: row.tpm for key, row in st.items()})
        gene = compare_abundance({key: row.tpm for key, row in pg.items()}, {key: row.tpm for key, row in sg.items()})
        annotations = parse_gtf_annotations(gtf.read_text(encoding="utf-8")) if gtf else {}
        strata = stratified_concordance({key: row.tpm for key, row in pg.items()}, {key: row.tpm for key, row in sg.items()}, annotations)
        star_results = None
        star_strata = {}
        star_status = "UNAVAILABLE_NOT_GENERATED"
        if star_counts:
            star = _counts(star_counts)
            star_results = {
                primary_profile_id: compare_orthogonal_gene_counts(star, {key: row.num_reads for key, row in pg.items()}),
                secondary_profile_id: compare_orthogonal_gene_counts(star, {key: row.num_reads for key, row in sg.items()}),
            }
            star_strata = {
                primary_profile_id: stratified_orthogonal_concordance(
                    star, {key: row.num_reads for key, row in pg.items()}, annotations,
                ),
                secondary_profile_id: stratified_orthogonal_concordance(
                    star, {key: row.num_reads for key, row in sg.items()}, annotations,
                ),
            }
            star_status = "AVAILABLE_QUALIFIED"
    except (OSError, UnicodeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    destination = output_dir.resolve()
    if destination.exists():
        raise typer.BadParameter("Concordance output directory must be new")
    identity = {
        "analysis_series_id": analysis_series_id, "primary_profile_id": primary_profile_id,
        "secondary_profile_id": secondary_profile_id, "reference_pack_id": reference_pack_id,
        "library_type": library_type, "processed_fastq_identity": processed_fastq_identity,
        "profile_identities": {
            primary_profile_id: primary.as_dict(), secondary_profile_id: secondary.as_dict(),
        },
        "inputs": {str(path.resolve()): sha256_path(path) for path in (primary_transcript, secondary_transcript, primary_gene, secondary_gene)},
    }
    comparison_id = sha256_payload({"kind": "harako-concordance-v1", "payload": identity})
    payload = {
        "schema_version": 1, "comparison_id": comparison_id, **identity,
        "star_comparator_status": star_status, "transcript": result_dict(transcript),
        "gene": result_dict(gene), "star": {key: result_dict(value) for key, value in (star_results or {}).items()},
        "annotation_strata": strata, "star_annotation_strata": star_strata,
        "limitations": ["descriptive only", "profile difference is not an error verdict", "primary only is downstream-eligible"],
    }
    report = render_summary_html(
        analysis_series_id=analysis_series_id, project_id=project_id,
        primary_profile=primary.as_dict(), secondary_profile=secondary.as_dict(),
        reference_pack_id=reference_pack_id, library_type=library_type,
        processed_fastq_identity=processed_fastq_identity, transcript=transcript, gene=gene,
        star_status=star_status, star_results=star_results,
    )
    write_new_text(destination / "profile_comparison.json", json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    write_new_text(destination / "profile_comparison.tsv", "level\tcommon\tspearman\tpearson\ttop100_overlap\n" + f"transcript\t{transcript.common_features}\t{transcript.spearman}\t{transcript.log_pearson}\t{transcript.top100_overlap}\n" + f"gene\t{gene.common_features}\t{gene.spearman}\t{gene.log_pearson}\t{gene.top100_overlap}\n")
    sensitive = "feature_id\tprimary_tpm\tsecondary_tpm\tabs_log2_ratio\tcategory\n" + "".join(f"{row.feature_id}\t{row.left_tpm}\t{row.right_tpm}\t{row.log2_ratio}\t{row.category}\n" for row in gene.sensitive_features)
    write_new_text(destination / "gene_method_sensitive.tsv", sensitive)
    write_new_text(destination / "transcript_method_sensitive.tsv", sensitive.replace("\n", "\n", 1) if not transcript.sensitive_features else "feature_id\tprimary_tpm\tsecondary_tpm\tabs_log2_ratio\tcategory\n" + "".join(f"{row.feature_id}\t{row.left_tpm}\t{row.right_tpm}\t{row.log2_ratio}\t{row.category}\n" for row in transcript.sensitive_features))
    write_new_text(destination / "summary.html", report)
    star_tsv = "profile_id\tcommon_genes\tspearman\tpearson\ttop100_overlap\n" + "".join(
        f"{key}\t{value.common_genes}\t{value.spearman}\t{value.log_pearson}\t{value.top100_overlap}\n"
        for key, value in sorted((star_results or {}).items()))
    write_new_text(destination / ORTHOGONAL_GENE_CONCORDANCE_ARTIFACT, star_tsv)
    strata_tsv = "stratum\tfeatures\tprofile_spearman\tmedian_absolute_log2_difference\tmethod_sensitive_fraction\tzero_transition_fraction\n" + "".join(
        f"{row['stratum']}\t{row['features']}\t{row['profile_spearman']}\t{row['median_absolute_log2_difference']}\t{row['method_sensitive_fraction']}\t{row['zero_transition_fraction']}\n"
        for row in strata)
    for profile_id, rows in sorted(star_strata.items()):
        strata_tsv += "".join(
            f"STAR_vs_{profile_id}:{row['stratum']}\t{row['features']}\t{row['star_profile_spearman']}\t{row['median_absolute_log2_cpm_difference']}\tNA\t{row['detection_discordance_fraction']}\n"
            for row in rows
        )
    write_new_text(destination / "annotation_stratified_concordance.tsv", strata_tsv)
    payload["report_sha256"] = sha256_path(destination / "summary.html")
    write_new_text(destination / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    typer.echo(json.dumps({"schema_version": 1, "comparison_id": comparison_id, "output_dir": str(destination)}, indent=2))


@concordance_app.command("validate")
def validate(manifest: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or not data.get("comparison_id") or data.get("primary_profile_id") == data.get("secondary_profile_id"):
            raise ValueError("Invalid concordance manifest")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps({"schema_version": 1, "valid": True, "comparison_id": data["comparison_id"]}, indent=2))


@concordance_app.command("inspect")
def inspect(manifest: Path = typer.Argument(..., exists=True, dir_okay=False), json_output: bool = typer.Option(False, "--json")) -> None:
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_output:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(f"comparison_id: {data.get('comparison_id')}")
        typer.echo(f"primary: {data.get('primary_profile_id')}")
        typer.echo(f"secondary: {data.get('secondary_profile_id')}")
        typer.echo(f"STAR: {data.get('star_comparator_status')}")
