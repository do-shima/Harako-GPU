# harako_truth_bulk_v2_decoy_stratified

`harako_truth_bulk_v2_decoy_stratified` is a versioned extension of truth-v1.
It reuses the v1 biological transcript design without changing or regenerating
v1, and adds an independent `decoy_identifiability_v1` oracle plus four
class-pure diagnostic samples.

The oracle does not use Salmon, a Salmon index, RAD, or quantification output.
It uses the generator source interval, ISR paired-end orientation, exact
15-mer candidate evidence, and paired Hamming distance. Exact ties have equal
best decoy/transcript distance. Dominant evidence requires a distance margin
of at least 4. Unique evidence requires decoy support and a conservative
transcript-distance floor of 12. Seedless observations use only a conservative
lower bound; this oracle is an information-identifiability model, not a
reimplementation of Salmon scoring.

The fixture contains the original 48 transcripts and 30 genes, plus four
distinct decoy targets. The exact-tie transcript is embedded between
non-homologous flanks so the decoy remains a separate index target. It includes
six biological samples (two conditions, three replicates, 50,000 PE100
fragments each) and four diagnostic samples (20,000 fragments each): unique,
dominant, ambiguous, and exact tie. Seeds, 0.1% substitution error, ISR
orientation, approximately 220 bp fragment lengths, opaque IDs, and gzip
timestamps are fixed.

Two fresh generator invocations produced identical manifests and all file
checksums. Scientific manifest SHA-256:
`d59b98d2ee229b3318562e4bda1488c198701804af121abc566c592f7e8a5821`.
R1/R2 counts, truth rows, source intervals, class purity, no-orphan pairs, gzip
CRC, and exact-tie/unique/dominant/ambiguous construction were self-validated.

Generated FASTQ, full FASTA/GTF, indices, RAD, and quantification outputs stay
under the WSL runtime root. Only generator/oracle code and this compact summary
are tracked. This internal synthetic fixture is not an external truth dataset,
full-size transcriptome, production validation, or clinical validation.
