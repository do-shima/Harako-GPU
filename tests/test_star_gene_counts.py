from __future__ import annotations

import pytest

from harako_gpu.services.star_gene_counts import (
    ALIGN_STAR_CONFIG_BLOB, GENECOUNTS_ARGS, METADATA_ROWS, RNABAM_MODULE_BLOB,
    column_manifest, gene_counts_args,
    parse_parabricks_help, parse_reads_per_gene, replace_quant_mode,
    resolve_reads_per_gene, validate_gene_universe,
)


TEXT = "\n".join([
    "N_unmapped\t1\t2\t3", "N_multimapping\t4\t5\t6",
    "N_noFeature\t7\t8\t9", "N_ambiguous\t10\t11\t12",
    "G1\t13\t14\t15", "G2\t16\t17\t18",
]) + "\n"


def test_capability_parser_requires_variadic_gene_counts_help() -> None:
    help_text = "--quantMode QUANTMODE [QUANTMODE ...] Types TranscriptomeSAM GeneCounts output ReadsPerGene.out.tab"
    assert parse_parabricks_help(help_text).supported
    assert not parse_parabricks_help("TranscriptomeSAM only").supported
    assert RNABAM_MODULE_BLOB == "ddaf70c77733e4d85a2a912e30d01e82652dba2b"
    assert ALIGN_STAR_CONFIG_BLOB == "3bdcb00cc8855b1604ea63279eaf1d3f8f051ce2"


def test_fixed_quant_mode_retains_transcriptome_and_adds_gene_counts() -> None:
    assert gene_counts_args() == GENECOUNTS_ARGS
    result = replace_quant_mode(("--quantMode TranscriptomeSAM", "--foo fixed"))
    assert result[0] == "--quantMode TranscriptomeSAM GeneCounts"
    with pytest.raises(ValueError):
        replace_quant_mode(("--quantMode GeneCounts",))


def test_reads_per_gene_parser_separates_metadata_and_selects_strands() -> None:
    table = parse_reads_per_gene(TEXT)
    assert tuple(table.metadata) == METADATA_ROWS
    assert table.selected("U") == (2, {"G1": 13, "G2": 16})
    assert table.selected("ISF") == (3, {"G1": 14, "G2": 17})
    assert table.selected("ISR") == (4, {"G1": 15, "G2": 18})
    with pytest.raises(ValueError, match="Unknown"):
        table.selected("auto")


@pytest.mark.parametrize("bad", [
    TEXT.replace("G1\t13\t14\t15", "G1\t13\t14"),
    TEXT + "G1\t1\t1\t1\n",
    TEXT.replace("G1\t13", "G1\t-1"),
    TEXT.replace("G1\t13", "G1\t1.5"),
])
def test_reads_per_gene_parser_rejects_structural_errors(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_reads_per_gene(bad)


def test_gene_universe_and_isr_manifest() -> None:
    table = parse_reads_per_gene(TEXT)
    result = validate_gene_universe(table, ("G1", "G3"))
    assert result == {"unexpected_gene_ids": ("G2",), "missing_gene_ids": ("G3",)}
    manifest = column_manifest(sample="WT_REP1", source_file="x", source_sha256="a" * 64,
        library_type="ISR", gtf_sha256="b" * 64, reference_pack_id="r", processed_fastq_sha256="c" * 64,
        run_identity="run")
    assert manifest["selected_column"] == 4


def test_optional_output_resolver_requires_one_nonempty_sample_file(tmp_path) -> None:
    path = tmp_path / "WT_REP1.ReadsPerGene.out.tab"
    path.write_text(TEXT, encoding="utf-8")
    assert resolve_reads_per_gene((path,), sample="WT_REP1") == path
    with pytest.raises(ValueError):
        resolve_reads_per_gene((), sample="WT_REP1")
