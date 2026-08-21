# Issue draft: Parabricks logfile masks genuine STAR Log.final.out

## Versions

- nf-core/rnaseq: 3.26.0, commit `e7ca46272c8f9d5ceee3f71759f4ba551d3217a4`
- module: `modules/nf-core/parabricks/rnafq2bam/main.nf`
- Parabricks: 4.6.0-1
- Nextflow: 25.04.3

## Problem

The module passes `--logfile ${prefix}.Log.final.out`. Parabricks writes its
general `[PB Info]` runtime stream to that path. It contains none of the
standard STAR summary fields, so `ALIGN_STAR.getStarPercentMapped` does not
match its regex and returns its initial value of zero. This creates a false
`min_mapped_reads` failure. MultiQC's STAR parser returns no STAR sample for
the same file; nf-core's custom failure table then displays the false zero.

## Reproduction and result

With the module command unchanged, the top-level final path contains only the
generic Parabricks log. Changing only the logfile argument to
`${prefix}.parabricks.log` causes Parabricks to retain that general stream and
independently emit a genuine second-pass `${prefix}.Log.final.out` through the
existing `--out-prefix`. On the public minimal fixture it reports 87.33%
unique mapping. A native STAR 2.7.2a run with the same index, reads, and
equivalent parameters matches all final-summary fields exactly.

## Proposed minimal fix

1. Change the hard-coded logfile to `${prefix}.parabricks.log`.
2. Add that path as a module output and publish it with the alignment logs.
3. Keep `${prefix}.Log.final.out` as the existing `log_final` output.

No alignment argument, output BAM path, container, or downstream parser needs
to change. A/B direct runs have identical all-record samtools checksums.

Suggested tests should assert that both files exist, the general log contains
Parabricks markers, the final log contains required STAR fields, the parsed
unique rate is nonzero, and a missing metric is not silently coerced to zero.
The additional output is backward-compatible for consumers of the existing
`log_final` channel; its content changes from mislabelled runtime text to the
summary the channel already promises.
