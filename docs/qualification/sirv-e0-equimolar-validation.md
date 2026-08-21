# SIRV E0 equimolar validation

`SRR3497201` is the fixed paired-end E0 run for SIRV Set 1 batch
`216652830`. Official E0 truth assigns each of 69 transcripts mole fraction
`1/69`; each gene's expected fraction is its included isoform count divided by
69. Estimated fractions are SIRV transcript TPM divided by total TPM over the
same 69 targets. Correlation against the constant expected vector is
`NOT_APPLICABLE_ZERO_VARIANCE`.

The primary index was GENCODE 49 human transcripts plus all 69 SIRV targets and
GRCh38.p14 primary-assembly decoys. The 69-target SIRV-only index remained a
diagnostic. Preprocessing yielded 1,291,246 paired fragments. Salmon 2.5.1
mapped 1,290,551 and was byte-identical across three fresh six-thread runs and
the 1/2/4/6 thread matrix.

The 63 preregistered transcript-identifiable targets were all detected. Median
and p90 absolute log2 molar error were 0.420518 and 1.460540, respectively.
All seven genes were detected; gene median/p90 errors were
0.181883/0.535181. Those gates passed. The 67 frozen equivalence groups had
median/p90 relative errors of 28.9838%/78.6794%, above the fixed 25%/50%
limits, so the equivalence-group gate failed.

All 69 expected-positive transcripts, including the documented fragmented
SIRV502 control, remain in the report. No undetected feature or batch caveat
was used for post-result exclusion.
