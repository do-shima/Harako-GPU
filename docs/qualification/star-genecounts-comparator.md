# STAR GeneCounts comparator qualification

## Root cause and capability

The pinned nf-core module already declared `*.ReadsPerGene.out.tab` as an
optional output, but `align_star.config` requested only
`--quantMode TranscriptomeSAM`. Absence in historical runs was expected. Both
source git-blob IDs match the preregistered values. Local Parabricks 4.6.0-1
help explicitly supports variadic `--quantMode`, `TranscriptomeSAM`, and
`GeneCounts` output to `ReadsPerGene.out.tab`.

## Actual WT_REP1 run

The new isolated runtime run completed 46/46 tasks. It retained transcriptome
BAM and produced non-empty GeneCounts, genomic BAM/BAI, junction, STAR metrics,
MultiQC, report, trace, and timeline. ReadsPerGene contained exactly four
integer count columns, four metadata rows, and 124 unique genes matching all
124 GTF genes. The fixed ISR contract selected column 4.

## Alignment invariance

Old and GeneCounts-enabled BAMs each had 88,628 records and identical
`samtools checksum -a` components (combined `28352bb9`). Junction, flagstat,
idxstats, input-read count, and 88.04% uniquely mapped metric were identical;
both BAMs passed quickcheck. Parabricks realtime was 39.8 seconds before and
40.3 seconds with GeneCounts, with the same 15.3 GB peak RSS. This small
fixture is not a full-size performance claim.

At final inspection, the retained old/new result trees were 56,344,478 and
49,382,087 bytes; the retained work trees were 91,662,068 and 69,176,413
bytes. Because task caching and retained intermediates differ, these observed
tree differences are recorded but are not attributed causally to GeneCounts.
