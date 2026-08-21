# BAM-optional routing

`bam_output_mode` is one of `none`, `keep`, or `discard_after_validation`.

- `none` selects `fastq_quantification_only`; alignment is disabled and alignment artifacts are `NOT_APPLICABLE`.
- `keep` requires the qualified `gpu_bam_alignment` route and retains BAM/BAI.
- `discard_after_validation` still requires successful BAM generation and validation. Deletion remains unimplemented.

No mode is silently converted. In particular, a human BAM request on the current
64-GB host is blocked before execution and is never changed to quantification-only.
Likewise, one-pass and two-pass profiles are never substituted.

The GUI shows quantification-only and BAM generation as distinct cards.
`discard_after_validation` is visible but disabled because deletion is outside
the MVP; selecting or changing a reference never silently changes the current
request.
