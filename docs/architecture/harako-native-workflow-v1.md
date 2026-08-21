# Harako-native workflow v1

`harako_native_v1` is a focused Nextflow DSL2 workflow for the alignment and QC
portion of Harako-GPU. Nextflow remains the process engine; Harako's existing
controller remains responsible for validation, quantification, matrices,
concordance, reporting, artifact verification, and support bundles.

## Fixed DAG

```text
FASTP
  -> PARABRICKS_RNA_FQ2BAM
  -> PUBLISH_ALIGNMENT_CONTRACT
  -> FEATURECOUNTS_BIOTYPE_QC
  -> MULTIQC
```

The pipeline consumes paired FASTQ with an explicit library type. Parabricks
uses the fixed one-pass or two-pass profile, `--low-memory`,
`--quantMode TranscriptomeSAM GeneCounts`, and the reference-specific
`sjdbOverhang`. For the qualified GRCh38.p14/GENCODE 49 pack,
FeatureCounts is fixed to `-t exon -g gene_type` and remains a biotype/QC
artifact distinct from STAR GeneCounts.

Salmon is deliberately absent from this DAG. The controller runs the selected
Salmon 2.5.1 or 1.10.3 profile once, from the same validated fastp output, with
six threads and explicit library type. Compare-both remains sequential and the
primary profile remains the downstream identity.

## Ownership and provenance

The Parabricks, publication, fastp, FeatureCounts, and MultiQC modules in
`pipelines/harako-native-v1` are Harako-owned wrappers around pinned container
commands. No nf-core module source is copied in v1, so there is no vendored
nf-core/modules commit. A future vendored module must record its exact upstream
commit, source path, and license notice and must never download at runtime.

## Canonical outputs

Backend-specific files are normalized before controller consumption. Alignment
files live under `results/alignment/<sample>/`, preprocessed reads under
`results/preprocessing/fastp/`, and QC under `results/qc/` and
`results/reports/multiqc/`. `results/backend-output-manifest.json` records each
role, sample, relative path, byte size, and SHA-256. The controller consumes
this explicit manifest and does not discover scientific outputs through broad
recursive filename searches.

## Runtime boundary

The native closure contains only selected roles: Parabricks, fastp, samtools,
Subread FeatureCounts, MultiQC, and the selected controller-side Salmon
profiles. FASTQC is optional and absent from the initial fixed DAG. There is no
image pull, module download, online plugin resolution, or CPU STAR fallback.

One-pass selects `ubuntu_native_rtx3090_ram128_one_pass_42gb_v1` (42 GB,
12 CPUs); two-pass selects
`ubuntu_native_rtx3090_ram128_two_pass_96gb_v1` (96 GB, 12 CPUs). The memory
directive applies only to the exact Parabricks process. Active work remains on
local ext4 SSD and the existing `harako-gpu-terminal-results-archive-v1`
policy governs explicit terminal-result archival; this foundation adds no
automatic deletion.

## Qualification boundary

Ubuntu C1 one-pass and two-pass parity passed for canonical outputs,
structural BAM validation, counts, and controller artifacts. New plans select
`harako_native_v1` by default only for the exact native Ubuntu high-memory host
profile when its installed receipt and the committed parity-report hashes both
validate. Historical plans without a backend, Windows/WSL plans, unqualified
hosts, and explicit reference selections remain
`nfcore_rnaseq_3_26_reference`. The GUI foundation may lift the launch guard
only after the same receipt, parity, provenance, asset, storage, and lock gates
pass; Ubuntu GUI C1 launch qualification remains pending. CPU STAR is a future
adapter and remains unavailable.
