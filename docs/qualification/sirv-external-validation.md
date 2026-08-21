# SIRV external validation

## Source identity

The source identity is unambiguous: `SRR3497201`, SIRV-Set 1 batch
`216652830`, Mix E0, paired Illumina HiSeq 2500, PolyA selection, and TruSeq
Stranded mRNA HT. The batch sequence ZIP, concentration/design XLSX, and
amendment were downloaded from Lexogen and retained only under the runtime
root. Their checksums are in the JSON report.

## Fail-closed statistical result

E0 is an equal-molar mix. The batch-specific table contains only the expected
value `1` for E0 isoforms, while the corrected annotation excludes fragmented
SIRV502. An expected vector with one unique value has zero variance, so both
the preregistered transcript-level Pearson and Spearman correlations are
undefined. Undefined correlation is not a failed Salmon estimate, but it also
cannot satisfy a numeric `>= 0.90` gate.

This was detected before index construction or primary quantification.
Detection, scaled-error, gene aggregate, deterministic-repeat, and
equivalence-group results are therefore `NOT_RUN`, not PASS. A valid follow-up
must either preregister a public E1/E2 run with independently proven mix/batch
identity or explicitly replace correlation for E0 with a scale-error-only gate.
