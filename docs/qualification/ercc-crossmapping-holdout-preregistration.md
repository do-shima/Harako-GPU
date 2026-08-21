# ERCC cross-mapping holdout preregistration

This contract was frozen on 2026-08-17 before holdout FASTQ download,
quantification, or read classification. Existing L01/L02 training lanes remain
unchanged. Applying the fixed same-site/platform/library/layout/read-length and
same-flowcell preference selects unused L03/L04 runs in accession order:

- Mix 1: `SRR896987`, `SRR896989`
- Mix 2: `SRR897019`, `SRR897021`

The read-level oracle first evaluates exact and reverse-complement evidence,
then uses the pinned minimap2 2.28 `-x sr` profile. A pair is class-unique only
when its class score leads by at least 10; margins 1--9 are ambiguous and zero
is an exact score tie. Low-complexity and adapter rules are fixed in the
adjacent JSON. The historical aggregate 0.10% gate is not changed.
