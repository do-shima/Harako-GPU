# Reference-aware BAM-optional human quantification qualification

`HARAKO_GPU_REFERENCE_AWARE_BAM_OPTIONAL_AND_HUMAN_QUANTIFICATION_QUALIFIED`

The product now makes availability decisions from the exact host, reference pack,
alignment profile, BAM mode, quantification profiles, and execution context.
Small-reference GPU BAM capability remains qualified. On the current 64-GB
Windows/WSL2/RTX 3090 host, exact GRCh38.p14/GENCODE 49 one-pass, two-pass, and
discard-after-validation requests remain blocked as `UNSUPPORTED_HOST_MEMORY`.
No request is silently converted.

The explicit BAM `none` route uses pinned fastp and CPU Salmon. Q1-Q3 required
levels passed, as did conditional Q4 and optional full-source Q5. Recommended
2.5.1 is `AVAILABLE_QUALIFIED`; compare-both is
`AVAILABLE_WITH_LIMITATION` because it adds CPU time/storage, emits no BAM/STAR
evidence, and the 1.10.3 compatibility profile has bounded numerical
reproducibility.

The self-contained reports disclose in Japanese and English that GPU was not
used and BAM, splice-junction, and STAR artifacts were not generated. A data-free
high-memory-host handoff freezes the future prospective BAM qualification inputs.
