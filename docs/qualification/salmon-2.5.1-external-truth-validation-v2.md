# Salmon 2.5.1 external truth validation v2

## Completion classification

`HARAKO_GPU_SALMON_2_5_1_EXTERNAL_TRUTH_FAILED`

The preregistered SIRV transcript and gene gates and all ERCC accuracy gates
passed. The fixed SIRV equivalence-group gate and the cross-mapping hard gate
did not pass. Thresholds, accessions, feature subsets, and failed lanes were not
changed after results were observed. Salmon 2.5.1 therefore remains a
qualification-only, non-default candidate.

## Preregistration

The v1 record remains byte-for-byte unchanged at SHA-256
`5ba814f25ce1bb1ab872a3649761f87bcb593af7797458b378933d8015c22077`.
The prospective v2 amendment replaces only the invalid zero-variance SIRV E0
correlation gate. Its raw-file SHA-256 is
`d65570ad5d47bb99ad185e792ef1e1c9616016262189b1e24e84e43c59124794`.
Pearson and Spearman against the constant E0 truth vector are recorded as
`NOT_APPLICABLE_ZERO_VARIANCE`, never as zero or one.

## Fixed sources and candidate

- Candidate: Salmon 2.5.1 Rust, `--deterministic --decoder serial`, explicit
  library type, six threads, pinned local image ID
  `sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f`.
- SIRV: `SRR3497201`, E0, batch `216652830`, 69 expected-positive equimolar
  transcript designs and seven genes from the verified Lexogen asset.
- ERCC: Mix 1 `SRR896983`/`SRR896985`; Mix 2
  `SRR897015`/`SRR897017`; official 92-row concentration table.
- Human background: GENCODE 49, GRCh38.p14 primary assembly.

Lexogen documents E0 as equimolar and separately documents the fragmented
SIRV502 batch issue. Because v2 preregistered all 69 transcripts as expected
positive, SIRV502 was reported and was not excluded post hoc.

## Index identities

The primary combined human+SIRV decoy-aware index contains 533,809 input
targets and 194 genome decoys; the Salmon build retained 517,301 indexed
references after its standard duplicate removal. Its inventory SHA-256 is
`21f6c9e368f1b213d283c87c066403ed193654a1953fa7f2f02f351c151a55f3`.
All 69 SIRV targets were verified in the built index. The diagnostic SIRV-only
index has 69 targets and inventory SHA-256
`8a5fe678a946acdc0d8928043ef3312f9a68027c5789252441f5d932520345ce`;
it was not promoted to the primary gate. The ERCC index has 92 targets and
inventory SHA-256
`dfe50d9027975ea649a21ae2d647c7411a0e35651b778babe39a2217d4cf4912`.

## Deterministic reproducibility

Each of five external samples passed three fresh six-thread runs and one run at
each of one, two, and four threads. Within each sample, `quant.sf`,
`quant.genes.sf`, row order, feature IDs, processed/mapped counts, and
zero/non-zero state were exact across all six runs. SIRV processed 1,291,246
fragments and mapped 1,290,551. The four ERCC lanes processed 6,604,093,
6,817,379, 5,577,941, and 5,474,248 fragments respectively.

## SIRV E0 results

The sequence-only preregistered classification contained 63
transcript-identifiable transcripts and 67 equivalence groups.

- Identifiable detection: 63/63 (100%), PASS.
- Transcript median absolute log2 molar error: 0.420518, PASS.
- Transcript p90 absolute log2 molar error: 1.460540, PASS.
- All-transcript detection: 69/69 (100%), secondary metric.
- Gene detection: 7/7, PASS.
- Gene median/p90 absolute log2 molar error: 0.181883/0.535181, PASS.
- Equivalence-group median relative error: 28.9838%, FAIL (limit 25%).
- Equivalence-group p90 relative error: 78.6794%, FAIL (limit 50%).

TPM was normalized over the 69 SIRV targets because E0 truth is molar and
transcript lengths differ. Undetected expected-positive features would have
received infinite error; none were silently removed.

## ERCC results

All 69 preregistered upper-75% targets were detected in every lane. Pearson was
0.995621--0.995877 and Spearman was 0.993912--0.994688; all concentration
gates passed. The matched-lane fold-change comparison passed with Spearman
0.968286, RMSE 0.177762, and median absolute log2 error 0.112329. All fixed
ratio-group gates passed.

## Cross-mapping

SIRV to ERCC mapped 0/1,291,246. Mix 1 ERCC lanes mapped 0.024697% and
0.024951% to the combined human+SIRV index, below the warning threshold. Mix 2
lanes mapped 0.130048% and 0.131561%, exceeding the fixed 0.10% hard limit;
their largest false targets were mitochondrial human transcripts (`MT-RNR2`
or `MT-CO2`). Both lanes were retained and the hard gate is FAIL.

## Version comparison

Version-specific indices were built for Salmon 1.10.3, 1.12.1, and 2.5.1.
Salmon 1.10.3 and 2.5.1 passed the SIRV identifiable transcript/gene gates;
1.12.1 failed the transcript p90 gate (1.848004). Every version failed the
same frozen SIRV equivalence-group gate. All three passed the ERCC
concentration and fold-change gates. These results do not reverse the existing
1.x reproducibility rejections and do not treat version agreement as truth.

## Optional E1/E2 discovery

Metadata-only review did not identify an official-source-linked public E1/E2
run whose accession, mix, and batch were all unambiguous. No run was adopted,
downloaded, quantified, or substituted for the preregistered E0 source. This
optional result did not affect either E0 or ERCC gates.

## Integration, performance, and scope

The conditional representative nf-core regression was `NOT_RUN` because full
external truth did not pass. Existing Parabricks, STAR-metrics, BAM, tximport,
and MultiQC contracts were not changed. Reference preparation took 51.66 s
with 1.18 GiB peak RSS. Candidate index builds took 16:42.55 for the 9.4 GiB
combined index and under one second each for the 772 KiB SIRV-only and 2.0 MiB
ERCC indices. The runtime tree occupied 51 GiB. These small-control figures are
not full-human production performance claims.

## Decision

External reproducibility, SIRV transcript/gene accuracy, and ERCC accuracy are
qualified for these fixed controls. Full external truth qualification is not:
the preregistered SIRV equivalence aggregation and Mix 2 cross-mapping gates
failed. Default adoption, production/diagnostic use, and full-size human
transcriptome use remain unauthorized.

## Subsequent cause-isolation note

The later cause-isolation study does not rewrite this FAIL. It found the SIRV
group metric unsuitable for attributing a Salmon 2.5.1-specific defect and
confirmed genuine human-mitochondrial evidence for the named Mix 2 targets in
held-out lanes. Most nuclear off-target records remained unresolved under the
prospectively frozen oracle. See
`external-truth-failure-cause-isolation.{md,json}`.
