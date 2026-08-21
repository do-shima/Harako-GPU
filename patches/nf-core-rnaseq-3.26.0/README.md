# nf-core/rnaseq 3.26.0 Parabricks STAR log compatibility

This compatibility patch applies only to `nf-core/rnaseq` revision `3.26.0`
resolved at commit `e7ca46272c8f9d5ceee3f71759f4ba551d3217a4`.

Parabricks 4.6.0-1 writes its general runtime log to the path supplied through
`--logfile`. The unpatched module assigns that path a STAR `Log.final.out`
name, hiding the genuine second-pass STAR summary that Parabricks otherwise
emits from `--out-prefix`. The patch moves the general log to
`<sample>.parabricks.log`, publishes it, and leaves
`<sample>.Log.final.out` for the standard STAR summary.

Apply it only through `scripts/apply_star_metrics_compatibility.py`. The
helper verifies the base commit, patch SHA-256, and every target file before
calling `git apply` with structured arguments. An unknown or already modified
upstream source fails closed.

This patch changes reporting paths only. It does not change the Parabricks
image, alignment arguments, reference, reads, BAM processing, or Salmon.
