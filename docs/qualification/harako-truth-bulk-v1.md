# harako_truth_bulk_v1

`harako_truth_bulk_v1` is an independent deterministic simulation fixture for
expression-backend qualification. Its generator uses the Python standard
library and never reads a Salmon index or Salmon output.

The design contains 48 transcripts, 30 genes, 12 zero-expression transcripts,
four genome-like decoys, two conditions, and three fixed-seed samples per
condition. Every sample has exactly 50,000 paired-end fragments (100 bp reads),
including 500 decoy-origin fragments. Fragment length is normally distributed
around 220 bp (SD 18, bounded by sequence/read length), and independent
substitution error is 0.1%. Read IDs are opaque. The library orientation is
ISR.

The predeclared strata are unique single-isoform transcripts, shared-core
multi-isoform genes, high-similarity paralog groups, and zero-expression
controls. Transcript accuracy gates include only the identifiable unique
stratum. Ambiguous isoforms and paralogs are assessed at their predeclared
aggregate. Fold-change features and exclusions are determined before Salmon is
run.

The generator writes runtime-only FASTQ, reference, GTF, gentrome, decoy list,
and fragment truth tables. Only generator code, schema, and sanitized summary
are tracked. Two independent invocations with the same seeds produced identical
manifest/file checksums. The scientific manifest SHA-256 is
`2302601bc962a5d9880e93fe3f56b813355bad56817b4141da2c510b195c42c6`.

This small synthetic design is not a full transcriptome, does not model all
sequencing errors or biological biases, and is not clinical or diagnostic
validation. Its long decoy/zero-transcript homologs deliberately test whether
decoy-origin fragments acquire transcript abundance. Leakage is conservatively
reported as the larger of zero-control estimated mass and total estimated mass
above true transcript-origin fragments, without double-counting the same event.

## Remediation reclassification

The fixture, generator, seeds, checksums, and original 19.4% result remain
unchanged. A later read-pair identifiability audit found 1,621 unique, 767
dominant, 30 ambiguous, and 582 exact-tie decoy fragments. The exact-tie count
equals the old aggregate numerator, so truth-v1 is now
`PARTIALLY_VALID_WITH_IDENTIFIABILITY_STRATIFICATION`: it remains an
adversarial homology stress fixture but its unstratified percentage is not a
primary decoy-rejection gate. Truth-v2 supplies separate class-pure controls
while retaining the original 1% ceiling.
