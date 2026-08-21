# External truth preregistration v2

This amendment was frozen on 2026-08-16 before any external Salmon
quantification. It preserves preregistration v1 byte-for-byte and keeps the
same SIRV and ERCC accessions. Its only scientific correction is to replace
undefined constant-vector correlation for equimolar SIRV E0 with detection and
normalized TPM mole-fraction error gates.

SIRV E0 uses all 69 official commercial transcript sequences from batch
216652830. The known fragmented SIRV502 remains expected-positive and receives
infinite error if undetected. The primary index is GENCODE 49 GRCh38.p14 human
transcripts plus the 69 SIRV targets and primary-assembly genome decoys. A
SIRV-only index is diagnostic and cannot become the primary result.

ERCC retains the four v1 lanes, official 92-row truth, IU library contract, and
fixed ratio groups. The primary 69-ID subset is selected before results by the
lower expected concentration across the two mixes. All thresholds and exact
source hashes are in the adjacent JSON contract.

The frozen JSON raw-file SHA-256 is
`d65570ad5d47bb99ad185e792ef1e1c9616016262189b1e24e84e43c59124794`.
