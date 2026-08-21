"""Salmon-ready transcriptome BAM grouping contract.

This service defines scientific validation and structured command construction.
Process execution remains in the process adapter.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


GROUPING_PARAMETER_CONTRACT_VERSION = 1
SAMTOOLS_VERSION = "1.23.1"
SAMTOOLS_IMAGE = "community.wave.seqera.io/library/htslib_samtools:1.23.1--5b6bb4ede7e612e5"
SAMTOOLS_IMAGE_DIGEST = "sha256:6df2a43541963ac73551a79c48bf2dbd743b37ab8dd1bdec364de1d6bc8cd7f0"
SAMTOOLS_COLLATE_THREADS = 2
SAMTOOLS_COLLATE_BUCKETS = 64


class TranscriptomeBamRole(str, Enum):
    RAW_TRANSCRIPTOME_BAM = "raw_transcriptome_bam"
    SALMON_READY_TRANSCRIPTOME_BAM = "salmon_ready_transcriptome_bam"


class GroupingMethod(str, Enum):
    SAMTOOLS_COLLATE = "samtools_collate"
    QUERYNAME_SORT_CONTROL = "samtools_sort_n_control"


@dataclass(frozen=True)
class BamTopology:
    record_count: int
    unique_qname_count: int
    contiguous_qname_group_count: int
    split_qname_count: int
    maximum_groups_per_qname: int
    group_size_distribution: Mapping[int, int]
    record_multiset_checksum: str
    record_order_checksum: str
    primary_count: int
    secondary_count: int
    supplementary_count: int
    unmapped_count: int
    paired_count: int
    flag_checksum: str
    tag_checksum: str
    tag_counts: Mapping[str, int]
    header_normalized_checksum: str
    non_order_header_checksum: str
    reference_dictionary_checksum: str
    header_sort_order: str | None
    header_group_order: str | None
    header_sub_sort: str | None
    target_sorted: bool
    coordinate_sorted: bool

    @property
    def all_records_for_qname_contiguous(self) -> bool:
        return self.split_qname_count == 0 and (
            self.contiguous_qname_group_count == self.unique_qname_count
        )


@dataclass(frozen=True)
class GroupingProvenance:
    grouping_method: GroupingMethod
    grouping_tool: str
    grouping_tool_version: str
    grouping_container_digest: str
    grouping_parameter_contract_version: int


@dataclass(frozen=True)
class GroupingContractReport:
    schema_version: int
    source_role: TranscriptomeBamRole
    output_role: TranscriptomeBamRole
    qualified: bool
    violations: tuple[str, ...]
    unique_qname_count: int
    contiguous_qname_group_count: int
    split_qname_count: int
    record_count_preserved: bool
    record_multiset_checksum_preserved: bool
    primary_count_preserved: bool
    secondary_count_preserved: bool
    supplementary_count_preserved: bool
    unmapped_count_preserved: bool
    paired_flags_preserved: bool
    alignment_tags_preserved: bool
    header_reference_dictionary_preserved: bool
    group_order_not_target_sorted: bool
    group_order_not_coordinate_sorted: bool
    provenance: GroupingProvenance


@dataclass(frozen=True)
class FragmentAccountingReport:
    qualified: bool
    processed_fragments: int
    mapped_fragments: int
    unique_qname_count: int
    contiguous_qname_group_count: int
    processed_matches_unique_qnames: bool
    processed_matches_contiguous_groups: bool
    violations: tuple[str, ...]


@dataclass(frozen=True)
class TranscriptomeGroupingManifest:
    schema_version: int
    raw_transcriptome_bam_scientific_checksum: str
    grouped_transcriptome_bam_scientific_checksum: str
    unique_qname_count: int
    grouping_method: GroupingMethod
    split_qname_count: int
    salmon_input_contract_status: str


def _validate_path(value: str, field: str) -> None:
    if not value or "\x00" in value:
        raise ValueError(f"{field} must be non-empty and contain no NUL")


def samtools_collate_argv(
    *, input_bam: str, output_bam: str, temporary_prefix: str
) -> tuple[str, ...]:
    """Build the fixed production-candidate grouping command."""

    for field, value in (
        ("input_bam", input_bam),
        ("output_bam", output_bam),
        ("temporary_prefix", temporary_prefix),
    ):
        _validate_path(value, field)
    if input_bam == output_bam:
        raise ValueError("samtools collate must not overwrite its input BAM")
    return (
        "samtools",
        "collate",
        "--no-PG",
        "-@",
        str(SAMTOOLS_COLLATE_THREADS),
        "-n",
        str(SAMTOOLS_COLLATE_BUCKETS),
        "-T",
        temporary_prefix,
        "-o",
        output_bam,
        input_bam,
    )


def samtools_queryname_sort_control_argv(
    *, input_bam: str, output_bam: str, temporary_prefix: str, diagnostic_control: bool
) -> tuple[str, ...]:
    """Build queryname sort only when explicitly marked as a diagnostic control."""

    if not diagnostic_control:
        raise ValueError("samtools sort -n is rejected as a production grouping strategy")
    for field, value in (
        ("input_bam", input_bam),
        ("output_bam", output_bam),
        ("temporary_prefix", temporary_prefix),
    ):
        _validate_path(value, field)
    if input_bam == output_bam:
        raise ValueError("samtools sort -n must not overwrite its input BAM")
    return (
        "samtools",
        "sort",
        "--no-PG",
        "-n",
        "-@",
        str(SAMTOOLS_COLLATE_THREADS),
        "-T",
        temporary_prefix,
        "-o",
        output_bam,
        input_bam,
    )


def default_collate_provenance() -> GroupingProvenance:
    return GroupingProvenance(
        grouping_method=GroupingMethod.SAMTOOLS_COLLATE,
        grouping_tool="samtools collate",
        grouping_tool_version=SAMTOOLS_VERSION,
        grouping_container_digest=SAMTOOLS_IMAGE_DIGEST,
        grouping_parameter_contract_version=GROUPING_PARAMETER_CONTRACT_VERSION,
    )


def inspect_sam_topology(lines: Iterable[str]) -> BamTopology:
    """Inspect SAM header and records without changing record semantics."""

    header_lines: list[str] = []
    reference_lines: list[str] = []
    header_fields: dict[str, str] = {}
    records: list[str] = []
    order_hasher = hashlib.sha256()
    tag_counts: Counter[str] = Counter()
    flag_counts: Counter[int] = Counter()
    qname_group_counts: Counter[str] = Counter()
    group_sizes: Counter[int] = Counter()
    seen_qnames: set[str] = set()
    closed_qnames: set[str] = set()
    split_qnames: set[str] = set()
    reference_order: dict[str, int] = {}
    previous_qname: str | None = None
    current_group_size = 0
    primary = secondary = supplementary = unmapped = paired = 0
    target_sorted = True
    coordinate_sorted = True
    previous_target_index = -1
    previous_position = -1

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\r\n")
        if not line:
            continue
        if line.startswith("@"):
            header_lines.append(line)
            fields = line.split("\t")
            if fields[0] == "@HD":
                header_fields.update(
                    field.split(":", 1) for field in fields[1:] if ":" in field
                )
            elif fields[0] == "@SQ":
                reference_lines.append(line)
                values = dict(field.split(":", 1) for field in fields[1:] if ":" in field)
                if "SN" in values:
                    reference_order.setdefault(values["SN"], len(reference_order))
            continue
        fields = line.split("\t")
        if len(fields) < 11:
            raise ValueError(f"Malformed SAM record at line {line_number}")
        try:
            flag = int(fields[1])
            position = int(fields[3])
        except ValueError as exc:
            raise ValueError(f"Malformed SAM flag or position at line {line_number}") from exc
        qname = fields[0]
        if qname != previous_qname:
            if previous_qname is not None:
                closed_qnames.add(previous_qname)
                group_sizes[current_group_size] += 1
            qname_group_counts[qname] += 1
            current_group_size = 0
        if qname in closed_qnames and qname != previous_qname:
            split_qnames.add(qname)
        previous_qname = qname
        current_group_size += 1
        seen_qnames.add(qname)

        secondary += bool(flag & 0x100)
        supplementary += bool(flag & 0x800)
        primary += not bool(flag & (0x100 | 0x800))
        unmapped += bool(flag & 0x4)
        paired += bool(flag & 0x1)
        flag_counts[flag] += 1
        tags = sorted(fields[11:])
        for tag in tags:
            if len(tag) >= 3 and tag[2] == ":":
                tag_counts[tag[:2]] += 1
        normalized = "\t".join([*fields[:11], *tags])
        records.append(normalized)
        order_hasher.update(normalized.encode("utf-8") + b"\n")

        if not flag & 0x4:
            target_index = reference_order.get(fields[2], len(reference_order))
            if target_index < previous_target_index:
                target_sorted = False
                coordinate_sorted = False
            elif target_index == previous_target_index and position < previous_position:
                coordinate_sorted = False
            previous_target_index = target_index
            previous_position = position

    if not records:
        raise ValueError("SAM input has no alignment records")
    group_sizes[current_group_size] += 1

    def digest_lines(items: Iterable[str]) -> str:
        hasher = hashlib.sha256()
        for item in items:
            hasher.update(item.encode("utf-8") + b"\n")
        return hasher.hexdigest()

    normalized_header = [
        "\t".join(field for field in line.split("\t") if not field.startswith("CL:"))
        for line in header_lines
        if not line.startswith("@CO")
    ]
    non_order_header = [line for line in normalized_header if not line.startswith("@HD")]
    flag_payload = json.dumps(sorted(flag_counts.items()), separators=(",", ":"))
    tag_payload = json.dumps(sorted(tag_counts.items()), separators=(",", ":"))
    return BamTopology(
        record_count=len(records),
        unique_qname_count=len(seen_qnames),
        contiguous_qname_group_count=sum(qname_group_counts.values()),
        split_qname_count=len(split_qnames),
        maximum_groups_per_qname=max(qname_group_counts.values()),
        group_size_distribution=dict(sorted(group_sizes.items())),
        record_multiset_checksum=digest_lines(sorted(records)),
        record_order_checksum=order_hasher.hexdigest(),
        primary_count=primary,
        secondary_count=secondary,
        supplementary_count=supplementary,
        unmapped_count=unmapped,
        paired_count=paired,
        flag_checksum=hashlib.sha256(flag_payload.encode("ascii")).hexdigest(),
        tag_checksum=hashlib.sha256(tag_payload.encode("ascii")).hexdigest(),
        tag_counts=dict(sorted(tag_counts.items())),
        header_normalized_checksum=digest_lines(normalized_header),
        non_order_header_checksum=digest_lines(non_order_header),
        reference_dictionary_checksum=digest_lines(reference_lines),
        header_sort_order=header_fields.get("SO"),
        header_group_order=header_fields.get("GO"),
        header_sub_sort=header_fields.get("SS"),
        target_sorted=target_sorted,
        coordinate_sorted=coordinate_sorted,
    )


def validate_grouping_contract(
    source: BamTopology,
    candidate: BamTopology,
    *,
    provenance: GroupingProvenance,
) -> GroupingContractReport:
    checks = {
        "QNAME_NOT_CONTIGUOUS": candidate.all_records_for_qname_contiguous,
        "RECORD_COUNT_CHANGED": source.record_count == candidate.record_count,
        "RECORD_MULTISET_CHANGED": (
            source.record_multiset_checksum == candidate.record_multiset_checksum
        ),
        "PRIMARY_COUNT_CHANGED": source.primary_count == candidate.primary_count,
        "SECONDARY_COUNT_CHANGED": source.secondary_count == candidate.secondary_count,
        "SUPPLEMENTARY_COUNT_CHANGED": (
            source.supplementary_count == candidate.supplementary_count
        ),
        "UNMAPPED_COUNT_CHANGED": source.unmapped_count == candidate.unmapped_count,
        "PAIRED_FLAGS_CHANGED": (
            source.paired_count == candidate.paired_count
            and source.flag_checksum == candidate.flag_checksum
        ),
        "ALIGNMENT_TAGS_CHANGED": source.tag_checksum == candidate.tag_checksum,
        "HEADER_OR_REFERENCE_CHANGED": (
            source.non_order_header_checksum == candidate.non_order_header_checksum
            and source.reference_dictionary_checksum == candidate.reference_dictionary_checksum
        ),
        "GROUP_ORDER_TARGET_SORTED": not candidate.target_sorted,
        "GROUP_ORDER_COORDINATE_SORTED": not candidate.coordinate_sorted,
    }
    violations = tuple(name for name, passed in checks.items() if not passed)
    return GroupingContractReport(
        schema_version=1,
        source_role=TranscriptomeBamRole.RAW_TRANSCRIPTOME_BAM,
        output_role=TranscriptomeBamRole.SALMON_READY_TRANSCRIPTOME_BAM,
        qualified=not violations,
        violations=violations,
        unique_qname_count=candidate.unique_qname_count,
        contiguous_qname_group_count=candidate.contiguous_qname_group_count,
        split_qname_count=candidate.split_qname_count,
        record_count_preserved=checks["RECORD_COUNT_CHANGED"],
        record_multiset_checksum_preserved=checks["RECORD_MULTISET_CHANGED"],
        primary_count_preserved=checks["PRIMARY_COUNT_CHANGED"],
        secondary_count_preserved=checks["SECONDARY_COUNT_CHANGED"],
        supplementary_count_preserved=checks["SUPPLEMENTARY_COUNT_CHANGED"],
        unmapped_count_preserved=checks["UNMAPPED_COUNT_CHANGED"],
        paired_flags_preserved=checks["PAIRED_FLAGS_CHANGED"],
        alignment_tags_preserved=checks["ALIGNMENT_TAGS_CHANGED"],
        header_reference_dictionary_preserved=checks["HEADER_OR_REFERENCE_CHANGED"],
        group_order_not_target_sorted=checks["GROUP_ORDER_TARGET_SORTED"],
        group_order_not_coordinate_sorted=checks["GROUP_ORDER_COORDINATE_SORTED"],
        provenance=provenance,
    )


def require_salmon_ready(
    role: TranscriptomeBamRole, report: GroupingContractReport | None
) -> None:
    if role is not TranscriptomeBamRole.SALMON_READY_TRANSCRIPTOME_BAM:
        raise ValueError("Raw transcriptome BAM is not a permitted Salmon alignment input")
    if report is None or not report.qualified:
        raise ValueError("Transcriptome BAM has not passed the grouping contract")


def validate_fragment_accounting(
    topology: BamTopology, *, processed_fragments: int, mapped_fragments: int
) -> FragmentAccountingReport:
    if processed_fragments < 0 or mapped_fragments < 0:
        raise ValueError("Salmon fragment counts cannot be negative")
    checks = {
        "BAM_QNAME_GROUPING_INVALID": topology.all_records_for_qname_contiguous,
        "PROCESSED_FRAGMENT_COUNT_MISMATCH": (
            processed_fragments == topology.unique_qname_count
        ),
        "MAPPED_EXCEEDS_PROCESSED": mapped_fragments <= processed_fragments,
    }
    return FragmentAccountingReport(
        qualified=all(checks.values()),
        processed_fragments=processed_fragments,
        mapped_fragments=mapped_fragments,
        unique_qname_count=topology.unique_qname_count,
        contiguous_qname_group_count=topology.contiguous_qname_group_count,
        processed_matches_unique_qnames=(processed_fragments == topology.unique_qname_count),
        processed_matches_contiguous_groups=(
            processed_fragments == topology.contiguous_qname_group_count
        ),
        violations=tuple(name for name, passed in checks.items() if not passed),
    )


def topology_scientific_checksum(topology: BamTopology) -> str:
    payload = {
        "record_count": topology.record_count,
        "record_multiset_checksum": topology.record_multiset_checksum,
        "record_order_checksum": topology.record_order_checksum,
        "reference_dictionary_checksum": topology.reference_dictionary_checksum,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def build_grouping_manifest(
    source: BamTopology,
    candidate: BamTopology,
    report: GroupingContractReport,
) -> TranscriptomeGroupingManifest:
    return TranscriptomeGroupingManifest(
        schema_version=1,
        raw_transcriptome_bam_scientific_checksum=topology_scientific_checksum(source),
        grouped_transcriptome_bam_scientific_checksum=topology_scientific_checksum(candidate),
        unique_qname_count=candidate.unique_qname_count,
        grouping_method=report.provenance.grouping_method,
        split_qname_count=candidate.split_qname_count,
        salmon_input_contract_status=(
            "GROUPING_CONTRACT_PASS" if report.qualified else "GROUPING_CONTRACT_FAIL"
        ),
    )
