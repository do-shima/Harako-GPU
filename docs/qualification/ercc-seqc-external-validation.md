# ERCC/SEQC external validation

The immutable selection uses pure ERCC Sample E/F data: Mix 1
`SRR896983`/`SRR896985` and Mix 2 `SRR897015`/`SRR897017`. All files came
from ENA public FASTQ endpoints and passed source MD5, gzip, paired-count, and
non-empty checks. The official 92-row truth table SHA-256 is
`5151b394332477301851404d37b907cb6f27c9aaa2569e288531a839d6ca2b3b`.

The Salmon 2.5.1 ERCC-only k=31 index contains exactly 92 targets. Its
inventory SHA-256 is
`dfe50d9027975ea649a21ae2d647c7411a0e35651b778babe39a2217d4cf4912`.
Each lane passed three fresh six-thread repeats and the 1/2/4/6 thread matrix
with exact `quant.sf`, `quant.genes.sf`, fragment accounting, and scientific
metadata.

All 69 preregistered upper-75% targets were detected in every lane. Pearson
ranged 0.995621--0.995877 and Spearman 0.993912--0.994688, passing every
concentration gate. Fold-change Spearman was 0.968286, RMSE 0.177762, and
median absolute log2 error 0.112329. The 4:1, 1:1, 2:3, and 1:2 fixed group
gates all passed.

The ERCC arm itself is externally validated for these lanes. Full candidate
qualification nevertheless fails because the independent SIRV
equivalence-group gate and Mix 2 ERCC-to-combined cross-mapping hard gate did
not pass.
