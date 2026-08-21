# ERCC mitochondrial off-target cause analysis

The original 0.130048% and 0.131561% Mix 2 aggregate failures remain unchanged.
The metadata-only holdout preregistration selected unused BGI L03/L04 lanes
before download or classification. Held-out Mix 2 lanes reproduced the signal
at 0.142422% and 0.133739%; held-out Mix 1 remained near 0.025%.

Read pairs contributing to Salmon mapping output were assessed independently
against official ERCC92 and GRCh38 mitochondrial sequences using exact/
reverse-complement evidence and pinned minimap2 2.28-r1209. For the named
`MT-RNR2`/`MT-CO2` targets, 432/434 training Mix 2 pairs and 441/442 held-out
Mix 2 pairs were `HUMAN_MT_UNIQUE`. Of the held-out pairs, 419 already carried
the evidence in raw reads and 22 were exposed after trimming; only one was
ERCC-unique. This is reproducible external-sample mitochondrial contamination,
not a Salmon misassignment or predominantly a fastp artifact.

The frozen preregistered oracle intentionally covered ERCC and mitochondrial
references but not the complete nuclear transcriptome. Consequently, most
aggregate off-target records whose Salmon targets are nuclear genes remain
`UNRESOLVED`: 12,697/14,456 training Mix 2 and 13,572/15,409 held-out Mix 2.
It would be post-result rule mutation to expand that reference universe and
claim a fully classified aggregate here. The exact-tie/ambiguous contribution
is negligible, and ERCC-unique misassignment is 55 and 57 pairs in the two
Mix 2 aggregates, far below the historical aggregate failure rate.

ERCC-only quantification recovers most reads, but this does not establish
origin and was not promoted to the primary validation index. The defensible
classification is mixed: `EXTERNAL_SAMPLE_HUMAN_CONTAMINATION` is confirmed
for the named mitochondrial component, while the overall aggregate remains
inconclusive under the frozen oracle scope. No threshold or original verdict
was changed, and no raw read sequence was committed.
