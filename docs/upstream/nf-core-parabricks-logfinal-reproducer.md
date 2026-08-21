# Minimal Parabricks STAR logfile reproducer

Use nf-core's small public paired-end test fixture, an index made by its pinned
STAR 2.7.2a container, and Parabricks 4.6.0-1. Substitute local paths; no user
or clinical data is needed.

Keep every `rna_fq2bam` argument identical between the two runs, including the
reference, paired FASTQs, index, read group, `--out-prefix sample.`,
`--no-markdups`, `--low-memory`, and GPU selection.

```text
# Current module behavior
pbrun rna_fq2bam ... --logfile sample.Log.final.out --out-prefix sample.

# Isolated logfile
pbrun rna_fq2bam ... --logfile sample.parabricks.log --out-prefix sample.
```

For each isolated output directory:

1. Record structured argv, exit code, file sizes, and SHA-256.
2. Search both log paths for `Number of input reads`, `Uniquely mapped reads
   number`, `Uniquely mapped reads %`, and multiple-loci fields.
3. Confirm the current path contains `[PB Info]` but no STAR fields.
4. Confirm the isolated run produces both the PB log and a standard second-pass
   `sample.Log.final.out`.
5. Compare the resulting BAMs using `samtools checksum -a`; byte SHA alone is
   path-sensitive because STAR records command paths in the BAM header.
6. Feed the genuine final summary to `getStarPercentMapped` and MultiQC's STAR
   parser; the public fixture yields 87.33%, not zero.

An optional third run omitting `--logfile` should still emit the standard final
summary while the general PB stream is captured from stderr. Separating the
named log is preferable because it preserves both provenance streams.
