# Salmon 1.10.3 versus 2.5.1 C1 comparison

Classification: `SALMON_1103_VS_251_C1_TIME_AND_CONCORDANCE_COMPLETED`.

The exact full-human Salmon 1.10.3 index was imported from the verified WD Gold handoff without reconstruction. The uncompressed PAX tar passed its checksum and member-safety audits, and the installed index matched the source inventory exactly: 15 files, 18,223,695,337 bytes, inventory SHA-256 `1843542aa3c2aaa113265404b39b2c571e54af261262477cccda5b8e4a46a68b`. The installed ProfileIndex is `salmon-1.10.3-52224ad2355cc52b`; its transcript, genome, GTF, and tx2gene identities were equal to those in the qualified `salmon-2.5.1-1c037278d376f40f` ProfileIndex. `validate_comparable_indices()` passed. Salmon 1.10.3 ran from the exact linux/amd64 image digest `sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e` and reported version 1.10.3.

Two fresh public product CLI runs exercised the complete plan/create, validate, prepare, inspect, start, status, artifacts, deep verification, and support-bundle lifecycle. Q1 ran Salmon 2.5.1 first and 1.10.3 second; Q2 reversed both execution order and explicitly selected downstream primary. Both used the same C1 ERR188044 input, fixed fastp contract, ISR library type, six threads per profile, full-human reference sources, and no BAM, Parabricks, STAR, legacy Salmon manifest, or manual Salmon arguments. Both completed all 12 controller stages, passed deep artifact verification, and produced sanitized support bundles with no biological data.

The processed inputs were identical across Q1 and Q2 after decompression: R1 SHA-256 `8d1ed751996d41502ed8cac359c99ca8642f868f9361f98c178f3dd8d379d680`, R2 SHA-256 `b461ba57015a63d069d6724f5d225a23c5c95f7cc7b575c9f8934cb27b536c3e`, 958,978 paired fragments. Compressed-file hashes also matched.

Runtime observations were:

| Run/order | Profile | Wall seconds | Fragments/second |
|---|---|---:|---:|
| Q1 first | Salmon 2.5.1 | 25.1767 | 38,089.94 |
| Q1 second | Salmon 1.10.3 | 28.2002 | 34,006.05 |
| Q2 first | Salmon 1.10.3 | 28.1996 | 34,006.84 |
| Q2 second | Salmon 2.5.1 | 20.1402 | 47,615.17 |

The two-observation median wall time was 22.6584 seconds for 2.5.1 and 28.1999 seconds for 1.10.3, a descriptive 1.10.3/2.5.1 ratio of 1.2446. Salmon 1.10.3 differed by only 0.00065 seconds between first and second position; Salmon 2.5.1 was 5.0365 seconds faster in second position, consistent with an order/filesystem-cache effect. These n=2 measurements are not a general benchmark.

Cross-version comparison was stable in both orientations and was classified `B_MODERATE_METHOD_SENSITIVITY`, an interpretation aid rather than a process failure. In Q1, transcript TPM Spearman/log-Pearson were 0.95374/0.95698 and gene TPM were 0.98749/0.99030. Transcript NumReads were 0.95443/0.96200 and gene NumReads were 0.98891/0.99469. Top-100 overlaps were 0.98, 0.98, 0.97, and 0.99 respectively. Q2 reproduced these values closely. The 2.5.1 index includes 194 features not present in the 1.10.3 universe; comparisons used the 517,038 common transcripts and 87,307 common gene-level rows.

Salmon 2.5.1 met its deterministic repeatability contract: transcript and gene numerical digests, quantification byte hashes, feature order, and all six matrix SHA-256 values were identical between Q1 and Q2. Salmon 1.10.3 did not produce byte-identical output, as expected for its bounded-numerical contract. Its Q1/Q2 transcript TPM Spearman was 0.99612 and gene TPM Spearman was 0.99993; top-50 and top-100 overlaps were 1.0. Median absolute TPM and NumReads differences were zero. The largest observed absolute differences were 119.126901 transcript TPM, 58.205 transcript NumReads, 37.664 gene TPM, and 7.144 gene NumReads.

Method-sensitive features were retained as descriptive evidence. Q1 identified 2,882 transcript-TPM and 733 gene-TPM features under the fixed method-sensitive rule. Leading transcript examples include `ENST00000406022.6`, `ENST00000390297.3`, `ENST00000894299.1`, `ENST00000628287.1`, and `ENST00000336458.13`; leading gene-level examples include `ENSG00000211651.3`, `ENST00000628287.1`, `ENSG00000227097.5`, `ENSG00000206634.1`, and `ENSG00000238405.1`. The adjacent JSON records the complete metric summary and source identities; large quantification outputs are not committed.

Salmon 2.5.1 remains the default recommendation. Salmon 1.10.3 remains a visible, executable bounded-numerical compatibility option. Q1 used 2.5.1 as downstream primary and Q2 used 1.10.3 only because it was explicitly requested for the mirrored experiment. Runtime or concordance observations do not change future defaults. This comparison does not establish biological truth, clinical suitability, benchmark generality, or cross-host equality. Native GUI scientific launch remains guarded.
