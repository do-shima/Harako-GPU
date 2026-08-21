# Expression truth and decoy-accounting remediation

## Completion classification

`HARAKO_GPU_SALMON_2_5_1_TECHNICALLY_QUALIFIED_EXTERNAL_TRUTH_REQUIRED`

Salmon 2.5.1 remains a non-default candidate. The internal deterministic,
biological-truth, identifiable-decoy, nf-core integration, tximport, MultiQC,
and resume gates passed. No external or published truth dataset was run, so
default adoption remains forbidden.

## Original status and corrected interpretation

The original `HARAKO_GPU_SALMON_2_5_1_CANDIDATE_REJECTED` record is retained as
the pre-remediation decision. Its only scientific failure was the truth-v1
19.4% aggregate decoy proxy. That value was reproduced exactly, then shown to
contain 582 exact-tie observations among 3,000 decoy fragments. Truth-v1 is now
`PARTIALLY_VALID_WITH_IDENTIFIABILITY_STRATIFICATION`: it remains a useful
adversarial homology stress fixture, but its unstratified percentage is not a
primary rejection gate.

## Truth-v2 and index controls

Truth-v2 scientific identity is
`d59b98d2ee229b3318562e4bda1488c198701804af121abc566c592f7e8a5821`.
Two Salmon 2.5.1 PISCEM k=31 indices were built from identical transcript
sources:

- transcript-only ID `0c3a4edffe5bc6f4dedd2b486e6c112e9350f01af8cdb5cff712a1a356371480`,
  1,208,469 bytes
- decoy-aware ID `1955f03bf5f19f21efd90cb9a69dc85cdb7e5f321d23e43dfbcac962af13f054`,
  1,285,673 bytes, four decoys

Both use image ID
`sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f`.
Build wall/RSS were 0.57 s/25,800 KiB and 0.51 s/25,724 KiB respectively.

## Decoy gates

| Class | Transcript-only mass | Decoy-aware mass | Correct interpretation |
|---|---:|---:|---|
| unique | 5,108/20,000 (25.54%) | 0/20,000 (0%) | PASS: <=1%, 100% reduction |
| dominant | 44/20,000 (0.22%) | 0/20,000 (0%) | PASS: <=1%, 100% reduction |
| ambiguous | 20,000/20,000 | 0/20,000 | report only |
| exact tie | 20,000/20,000 | 19,998/20,000 | unidentifiable assignment mass |

The 1% ceiling was not changed. Ambiguous and exact-tie samples were neither
discarded nor counted as PASS. All input fragment counts were exact.

## RAD and metadata accounting

Diagnostic decoy-aware runs retained completed RAD files with checksums and
sizes. The binary format was not reverse-engineered. Salmon 2.5.1 `meta_info`
reported `num_decoy_targets=0` and `num_decoy_fragments=0` even though index
`info.json` records four decoys and nonempty decoy hashes. Therefore those
metadata counters are classified
`METADATA_COUNTERS_DO_NOT_EXPOSE_INDEX_DECOY_ACCOUNTING`; they are supporting
diagnostics, not truth. The causal transcript-only/decoy-aware controls and
independent origin oracle supply the primary accounting evidence.

## Reproducibility and biological truth

The truth-v2 matrix contained 62 successful runs: every diagnostic sample ten
times, every biological sample three times, plus 1/2/4/6-thread checks.
`quant.sf`, `quant.genes.sf`, mapped/processed counts, and scientific metadata
were exact within sample and across threads. Matrix digest:
`267ee915a286e682e497fa350eeb71434f8854bc0e42ae8f838abe86ffd22102`.

For the six biological samples, identifiable transcript and expressed-gene
Pearson/Spearman were 1.0; median and p95 APE were 0; ambiguous aggregate error
was 0; zero transitions were 0; identifiable zero-expression mass was 0; high
false positives were 0; fold-change direction was 100%, RMSE 0, Spearman 1.0.
Exact-tie assignment mass 750 was reported separately and excluded from the
identifiable zero-expression gate.

Salmon 1.10.3 and 1.12.1 were rerun on truth-v2 with their own decoy-aware
indices. Both passed this internal biological design and assigned essentially
all exact-tie observations (19,999 and 19,998), while unique/dominant/ambiguous
diagnostics had zero transcript mass with decoys present. Version agreement was
not used as ground truth; prior reproducibility rejections remain intact.

## Conditional nf-core integration

After all internal truth gates passed, nf-core/rnaseq 3.26.0 was run with
Nextflow 25.04.3, Parabricks 4.6.0-1, the existing STAR-metrics compatibility,
and only the fully-qualified FASTQ pseudo-alignment Salmon process overridden.
Explicit `reverse` strandedness avoided the unrelated 1.x inference process;
BAM Salmon remained absent. Two fail-closed setup attempts exposed a Nextflow
version drift and a local-image registry alias issue before the final run.
Neither changed scientific outputs. The final recovery run completed, followed
by a separate formal resume.

WT_REP1 processed 47,605 fragments and mapped 37,397 (78.556874%) in Salmon
2.5.1. Parabricks ran; native STAR alignment and BAM Salmon were absent. The
coordinate BAM passed `samtools quickcheck`; STAR unique mapping remained
88.04%; junction, tximport matrices, gene SummarizedExperiment, and one Salmon
2.5.1 MultiQC section were present. Alignment-record stream SHA-256 matched the
prior independent run:
`536c3c2fa1a6dcdeae55f70b5fd9638cecea308d94adff7a973f0dd00f28bae2`.

Formal resume had 43 cached tasks and only MultiQC regenerated. Parabricks,
FASTQ Salmon, BAM sort/index, tximport, and all major QC tasks were cached.
BAM, BAI, junction, quant.sf, transcript matrix, and gene matrix SHA/mtime were
unchanged. `quant.sf` retained the prior exact public-fixture SHA
`44020ba1bc41c8d395fb41be44796c9e0877a42153101845e6060a3a3fd5c31c`.

## Scope and decision

Qualified: local Salmon 2.5.1 deterministic candidate identity, truth-v2
internal accuracy, identifiable unique/dominant decoy control, exact
reproducibility, small public-fixture config-only integration, tximport,
MultiQC, and resume. Unqualified: external/published truth, full-size data,
default adoption, production, diagnostic, and clinical use. The next goal is
broader external truth validation; the 1.10.3 default is unchanged.

The first external follow-up resolved SIRV and ERCC metadata prospectively but
did not run primary quantification. The mandated SIRV accession is equal-molar
E0, which makes the specified transcript truth correlations undefined. The
internal qualification remains intact and external qualification remains
blocked rather than failed or passed.

The prospective v2 amendment retained v1 unchanged and replaced only the
invalid E0 correlation with equal-molar error gates. SIRV transcript/gene and
ERCC gates passed, but frozen SIRV equivalence-group and Mix 2 cross-mapping
gates failed. Internal truth qualification remains historical evidence; the
candidate did not achieve external qualification and remains non-default.
