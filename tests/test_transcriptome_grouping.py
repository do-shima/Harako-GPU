from __future__ import annotations

from dataclasses import replace

import pytest

from harako_gpu.core.artifacts import ArtifactType
from harako_gpu.services.transcriptome_grouping import (
    SAMTOOLS_IMAGE_DIGEST,
    GroupingMethod,
    TranscriptomeBamRole,
    default_collate_provenance,
    build_grouping_manifest,
    inspect_sam_topology,
    require_salmon_ready,
    samtools_collate_argv,
    samtools_queryname_sort_control_argv,
    validate_grouping_contract,
    validate_fragment_accounting,
)


HEADER = (
    "@HD\tVN:1.6\tSO:unsorted\n"
    "@SQ\tSN:tx1\tLN:100\n"
    "@SQ\tSN:tx2\tLN:100\n"
)
Q1_A = "q1\t99\ttx2\t20\t255\t5M\t=\t25\t10\tAAAAA\tFFFFF\tNH:i:2\tHI:i:1\n"
Q1_B = "q1\t355\ttx1\t25\t255\t5M\t=\t20\t-10\tTTTTT\tFFFFF\tHI:i:2\tNH:i:2\n"
Q2_A = "q2\t99\ttx1\t10\t255\t5M\t=\t15\t10\tCCCCC\tFFFFF\tNH:i:1\tHI:i:1\n"
Q2_B = "q2\t147\ttx1\t15\t255\t5M\t=\t10\t-10\tGGGGG\tFFFFF\tHI:i:1\tNH:i:1\n"


def test_split_qname_and_contiguous_group_counts() -> None:
    split = inspect_sam_topology((HEADER + Q1_A + Q2_A + Q2_B + Q1_B).splitlines(True))
    assert split.record_count == 4
    assert split.unique_qname_count == 2
    assert split.contiguous_qname_group_count == 3
    assert split.split_qname_count == 1
    assert split.maximum_groups_per_qname == 2
    assert split.group_size_distribution == {1: 2, 2: 1}
    assert not split.all_records_for_qname_contiguous


def test_grouping_contract_preserves_records_flags_tags_and_header() -> None:
    source = inspect_sam_topology((HEADER + Q1_A + Q2_A + Q2_B + Q1_B).splitlines(True))
    grouped = inspect_sam_topology((HEADER + Q1_A + Q1_B + Q2_A + Q2_B).splitlines(True))
    report = validate_grouping_contract(source, grouped, provenance=default_collate_provenance())
    assert report.qualified
    assert report.violations == ()
    assert report.record_multiset_checksum_preserved
    assert report.primary_count_preserved
    assert report.secondary_count_preserved
    assert report.supplementary_count_preserved
    assert report.alignment_tags_preserved
    assert grouped.primary_count == 3
    assert grouped.secondary_count == 1
    assert grouped.paired_count == 4
    assert grouped.tag_counts == {"HI": 4, "NH": 4}

    collate_header = HEADER.replace(
        "@HD\tVN:1.6\tSO:unsorted", "@HD\tVN:1.6\tSO:unsorted\tGO:query"
    )
    grouped_with_order_declaration = inspect_sam_topology(
        (collate_header + Q1_A + Q1_B + Q2_A + Q2_B).splitlines(True)
    )
    assert validate_grouping_contract(
        source, grouped_with_order_declaration, provenance=default_collate_provenance()
    ).qualified

    changed = replace(grouped, tag_checksum="0" * 64)
    rejected = validate_grouping_contract(source, changed, provenance=default_collate_provenance())
    assert not rejected.qualified
    assert "ALIGNMENT_TAGS_CHANGED" in rejected.violations


def test_collate_command_is_fixed_structured_and_never_fast() -> None:
    argv = samtools_collate_argv(
        input_bam="/inputs/raw transcriptome.bam",
        output_bam="/outputs/salmon-ready.bam",
        temporary_prefix="/scratch/collate/WT_REP1",
    )
    assert argv == (
        "samtools", "collate", "--no-PG", "-@", "2", "-n", "64", "-T",
        "/scratch/collate/WT_REP1", "-o", "/outputs/salmon-ready.bam",
        "/inputs/raw transcriptome.bam",
    )
    assert "-f" not in argv
    assert "eval" not in argv
    with pytest.raises(ValueError, match="overwrite"):
        samtools_collate_argv(input_bam="x", output_bam="x", temporary_prefix="tmp/x")


def test_queryname_sort_is_diagnostic_only_and_rejected_for_production() -> None:
    with pytest.raises(ValueError, match="production"):
        samtools_queryname_sort_control_argv(
            input_bam="raw.bam", output_bam="sorted.bam", temporary_prefix="tmp/x",
            diagnostic_control=False,
        )
    argv = samtools_queryname_sort_control_argv(
        input_bam="raw.bam", output_bam="sorted.bam", temporary_prefix="tmp/x",
        diagnostic_control=True,
    )
    assert argv[0:4] == ("samtools", "sort", "--no-PG", "-n")


def test_raw_and_salmon_ready_artifacts_are_distinct_and_fail_closed() -> None:
    assert ArtifactType.RAW_TRANSCRIPTOME_BAM.value == "raw_transcriptome_bam"
    assert ArtifactType.SALMON_READY_TRANSCRIPTOME_BAM.value == "salmon_ready_transcriptome_bam"
    grouped = inspect_sam_topology((HEADER + Q1_A + Q1_B + Q2_A + Q2_B).splitlines(True))
    report = validate_grouping_contract(grouped, grouped, provenance=default_collate_provenance())
    with pytest.raises(ValueError, match="Raw"):
        require_salmon_ready(TranscriptomeBamRole.RAW_TRANSCRIPTOME_BAM, report)
    require_salmon_ready(TranscriptomeBamRole.SALMON_READY_TRANSCRIPTOME_BAM, report)
    with pytest.raises(ValueError, match="not passed"):
        require_salmon_ready(TranscriptomeBamRole.SALMON_READY_TRANSCRIPTOME_BAM, None)


def test_grouping_provenance_is_fully_pinned() -> None:
    provenance = default_collate_provenance()
    assert provenance.grouping_method is GroupingMethod.SAMTOOLS_COLLATE
    assert provenance.grouping_tool_version == "1.23.1"
    assert provenance.grouping_container_digest == SAMTOOLS_IMAGE_DIGEST
    assert provenance.grouping_parameter_contract_version == 1


def test_fragment_accounting_rejects_accidental_contiguous_group_count() -> None:
    raw = inspect_sam_topology((HEADER + Q1_A + Q2_A + Q2_B + Q1_B).splitlines(True))
    raw_accounting = validate_fragment_accounting(
        raw, processed_fragments=raw.contiguous_qname_group_count, mapped_fragments=3
    )
    assert raw_accounting.processed_matches_contiguous_groups
    assert not raw_accounting.processed_matches_unique_qnames
    assert not raw_accounting.qualified

    grouped = inspect_sam_topology((HEADER + Q1_A + Q1_B + Q2_A + Q2_B).splitlines(True))
    grouped_accounting = validate_fragment_accounting(
        grouped, processed_fragments=grouped.unique_qname_count, mapped_fragments=2
    )
    assert grouped_accounting.qualified


def test_grouping_manifest_distinguishes_raw_and_grouped_scientific_identity() -> None:
    raw = inspect_sam_topology((HEADER + Q1_A + Q2_A + Q2_B + Q1_B).splitlines(True))
    grouped = inspect_sam_topology((HEADER + Q1_A + Q1_B + Q2_A + Q2_B).splitlines(True))
    report = validate_grouping_contract(raw, grouped, provenance=default_collate_provenance())
    manifest = build_grouping_manifest(raw, grouped, report)
    assert manifest.schema_version == 1
    assert manifest.raw_transcriptome_bam_scientific_checksum != (
        manifest.grouped_transcriptome_bam_scientific_checksum
    )
    assert manifest.unique_qname_count == 2
    assert manifest.split_qname_count == 0
    assert manifest.salmon_input_contract_status == "GROUPING_CONTRACT_PASS"
