# STAR GeneCounts comparator

Harako-GPU can request the pinned Parabricks STAR lineage to emit
`ReadsPerGene.out.tab` by using the fixed argument sequence
`--low-memory --quantMode TranscriptomeSAM GeneCounts` (plus fixed `--x3` only
for the qualification-debug profile). `TranscriptomeSAM` is retained.
Arbitrary quant modes, native-STAR fallback, and featureCounts substitution are
forbidden.

The four columns are gene ID, unstranded, first-read strand aligned with RNA,
and second-read strand aligned with RNA. Library contracts map U to column 2,
ISF/forward to column 3, and ISR/reverse to column 4. Unknown or automatic
strandedness cannot select a comparator column. The four `N_*` rows are stored
as metadata and never enter the gene matrix.

Artifacts live under `alignment/star_gene_counts/` with sample-qualified
source, selected-count, metadata-count, and column-manifest names. STAR counts
are converted to CPM and compared with Salmon estimated-count CPM. They are an
orthogonal robustness comparator, not a transcript quantifier or automatic
downstream input.
