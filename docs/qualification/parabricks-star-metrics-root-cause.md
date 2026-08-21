# Parabricks STAR metrics root cause

Scope: `nf-core/rnaseq` 3.26.0 at commit
`e7ca46272c8f9d5ceee3f71759f4ba551d3217a4`, Parabricks 4.6.0-1.

## Defect chain

The pinned module `modules/nf-core/parabricks/rnafq2bam/main.nf` had SHA-256
`231d896e...94321` and passed both of these arguments to `pbrun rna_fq2bam`:

```text
--logfile ${prefix}.Log.final.out
--out-prefix ${prefix}.
```

Parabricks uses `--logfile` for its general `[PB Info]` runtime stream. That
stream occupied the filename reserved for STAR's final summary. It contained
none of the standard fields required by either downstream consumer:

- `Number of input reads`
- `Uniquely mapped reads number` and `%`
- multiple-loci counts and percentages
- unmapped-category percentages

`ALIGN_STAR.getStarPercentMapped` initializes `percent_aligned` to numeric zero
and changes it only when its unique-mapping regex matches. Missing fields
therefore became `0`, not an unavailable state. The workflow compared that
false zero with `min_mapped_reads=5`, emitted a failing sample row, and printed
the false threshold warning.

MultiQC 1.33's `parse_star_report` correctly returned no STAR sample for the
generic log. The visible 0% in the original report came from nf-core's custom
`fail_mapped_samples_mqc.tsv` table, whose column is labelled `STAR uniquely
mapped reads (%)`; it was not a successfully parsed MultiQC STAR summary. This
distinction is retained in the machine-readable compatibility report.

## Existing successful-run inventory

The pre-change successful task contained the 6,730-byte generic
`WT_REP1.Log.final.out`, 30,558-byte `Log.out`, 329-byte progress log,
1,005-byte `SJ.out.tab`, and a 1,988-byte nested first-pass STAR summary. It
also contained the raw genomic BAM/BAI, transcriptome BAM, 15 Parabricks QC
metric files, and the exact `.command.sh/.out/.err` evidence. Published results
included the coordinate-sorted BAM/BAI, samtools stats/flagstat/idxstats,
Salmon quant/log and merged matrices, MultiQC HTML/data, and a 48-byte
`multiqc_fail_mapped_samples_table.txt` containing `WT_REP1 0`. Searches across
all text outputs found standard final-summary fields only in the nested
first-pass log; the mislabelled top-level log contained only Parabricks/CUDA
runtime text.

## Evidence and resolution

When `--logfile` was moved to `WT_REP1.parabricks.log`, Parabricks emitted a
separate, genuine second-pass `WT_REP1.Log.final.out` through `--out-prefix`.
It reported 49,747 input paired fragments, 43,442 uniquely mapped fragments
(87.33%), and 986 multimapped fragments (1.98%). An independent native STAR
2.7.2a oracle using the same reads, index, and equivalent STAR arguments
matched every scientific field exactly.

The fix is therefore logfile separation, not synthetic metrics, threshold
suppression, or BAM-derived substitution. The pinned patch leaves all
alignment arguments unchanged, publishes both logs, and fails closed unless
the pipeline commit, patch SHA, and target file SHAs match its manifest.
