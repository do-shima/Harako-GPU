# External truth dataset selection

The selection was fixed from official metadata before any primary Salmon run.
No abundance result was consulted.

## SIRV

`SRR3497201` (`SRX1752558`, `SAMN04939713`, `PRJNA312485`) is paired
Illumina HiSeq 2500 data from the published SIRV study. The methods identify
TruSeq Stranded mRNA HT preparation, SIRV E0, and batch `216652830`. Lexogen's
batch download page independently links this run to the same batch. The batch
amendment removes fragmented SIRV502 from the corrected annotation.

The ENA split-pair files contain 1,297,881 paired fragments each. The run also
has 98,365 singleton spots, which are excluded from paired-input quantification
and must be reported rather than silently treated as pairs.

## ERCC/SEQC

`GSE47792` is the SEQC SuperSeries; the raw core-study samples are under
`GSE47774` and `PRJNA208369`. Pure Sample E is ERCC ExFold Mix 1 and Sample F
is Mix 2. Both have suitable paired 100-bp BGI HiSeq 2000 data.

The preregistered rule selected library 1, flowcell `AC0AYTACXX`, and the first
two lanes in accession order for each mix:

- Mix 1: `SRR896983` (L01), `SRR896985` (L02)
- Mix 2: `SRR897015` (L01), `SRR897017` (L02)

This satisfies same site, platform, preparation family, layout, length,
library ID, and flowcell. The A/B human-RNA fallback is therefore unnecessary.

## Pre-registration stop

The batch-specific E0 table assigns identical expected molarity to every
corrected-annotation isoform. The required transcript Pearson and Spearman
truth correlations consequently have a zero-variance expected vector and are
undefined. This was discovered before primary quantification. The frozen
preregistration was invalidated rather than changing a threshold, selecting a
different mix, or converting an undefined statistic into PASS.
