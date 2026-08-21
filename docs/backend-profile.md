# Pinned backend profile

## Execution-adapter projection

The backend profile is frozen into each run. nf-core performs fixed fastp and
Parabricks `rna_fq2bam` with `TranscriptomeSAM GeneCounts`; its BAM/FASTQ Salmon
branches and native STAR alignment are explicitly disabled and trace-verified.
Harako then runs the primary and optional secondary fixed Salmon profiles
sequentially. Runtime image/index/version fallback and arbitrary parameters are
forbidden. GPU is used for alignment; both Salmon profiles are CPU tasks.
Schema version: `1`.

Both initial profiles fix `nf-core/rnaseq` revision `3.26.0`, aligner
`star_salmon`, `use_parabricks_star=true`, and Docker. The official 3.26.0
parameter schema defines the Parabricks switch and explicit FASTA/GTF inputs;
the pipeline output contract uses `save_align_intermeds` for alignment BAM
publication.

Harako-GPU therefore emits only this allowlisted parameter set:

```text
input, outdir, fasta, gtf, transcript_fasta, aligner,
use_parabricks_star, save_align_intermeds, save_reference,
skip_pseudo_alignment, skip_markduplicates, extra_star_align_args,
pseudo_aligner, salmon_index, salmon_quant_libtype, trimmer, save_trimmed
```

`save_align_intermeds` remains true for both retention policies. Discard is a
post-validation state transition, not omission of alignment or a request to
hide the BAM before it can be verified. This foundation does not perform that
transition on disk.

Nextflow `25.04.3` is the minimum and the initial qualified version. Backend
profiles and run plans contain `minimum_nextflow_version`,
`qualified_nextflow_version`, `detected_nextflow_version`, and
`nextflow_version_status`. A plan also contains the structured environment
`{"NXF_VER": "25.04.3"}`; this is not embedded in a shell command.

`dev`, `latest`, other revisions, `--genome`, a disabled Parabricks switch,
arbitrary nf-core parameters, and arbitrary command strings are rejected.
Commands are stored as argv arrays and rendered only for preview.

GPU selection accepts `all` or a comma-separated grammar of numeric device IDs
and `GPU-...` UUIDs. It is rendered by trusted code as the nf-core
`gpu_container_options` value, so only `process_gpu` tasks receive the Docker
GPU option. Windows drive paths remain rejected for WSL/Linux targets. A
Windows control-plane may use a `\\wsl.localhost` or `\\wsl$` UNC path; trusted
code validates the distribution and records the corresponding Linux absolute
path in the plan.

`standard` and `low_memory_candidate` remain planning labels. The fixed
low-memory mapping is:

```text
extra_star_align_args = "--low-memory"
skip_markduplicates = true
use_parabricks_star = true
aligner = star_salmon
```

Qualification debug mode may select only the fixed
`"--low-memory --x3"` value. Arbitrary extra STAR arguments remain forbidden.
That debug-only mode also applies the bounded nf-core `test_gpu` scheduling
envelope (8 CPUs, 30 GB memory, 2 hours) through Nextflow `resourceLimits`.
This caps declared resources for the tiny fixture; it does not qualify a host
below the 24-thread/100-GiB recommendations.
The initial RTX 3090 feasibility profile is low-memory candidate; neither that
GPU nor the standard profile is automatically qualified.

## Parabricks STAR reporting compatibility

For nf-core/rnaseq 3.26.0 at resolved commit
`e7ca46272c8f9d5ceee3f71759f4ba551d3217a4`, the upstream Parabricks module's
`--logfile` path masks the genuine STAR final summary. Harako's qualified local
compatibility patch changes only that destination to
`${prefix}.parabricks.log`, preserves `${prefix}.Log.final.out` for the
second-pass STAR summary produced through `--out-prefix`, and publishes both.

The patch is gated by the revision, resolved commit, patch SHA-256, and both
target-file source SHAs. It fails closed for an unknown or mixed upstream
state. It does not change the image, alignment parameters, BAM processing,
Salmon, or the 5% threshold. A local patched pipeline is launched as a local
source tree because Nextflow rejects `-r` for local scripts; the base revision
is enforced before patching rather than relaxed at launch.

Primary upstream references:

- https://github.com/nf-core/rnaseq/tree/3.26.0
- https://raw.githubusercontent.com/nf-core/rnaseq/3.26.0/nextflow_schema.json

## Salmon reproducibility boundary

The pinned alignment-mode quantifier is Salmon 1.10.3 in
`quay.io/biocontainers/salmon:1.10.3--h6dccd9a_2` at digest
`sha256:f83ebb15...f08e`. The profile fixes ISR, six threads, no sequence/GC
bias correction, the explicit transcript FASTA and gene map, and a structured
argv. Arbitrary Salmon arguments remain forbidden. The pinned binary exposes
neither `--deterministic` nor a random-seed option in alignment-mode help.

Six threads are part of plan identity. Ten fresh Salmon executions against one
frozen transcriptome BAM met tolerance schema 1 but were not byte-identical.
The 1/2/4/8-thread matrix is characterization only; eight-thread and
cross-thread comparisons exceeded the fixed ceiling.

Five fresh Parabricks runs had one transcriptome alignment-record multiset but
five record orders. Salmon processed the resulting contiguous QNAME groups,
whose counts varied from 33,011 to 33,030 despite 32,980 invariant unique
QNAMEs. Processed/mapped fragment exactness failed and transcript/gene TPM >=1
varied by about 0.258%, above the predeclared 0.1% ceiling. The selected backend
decision is `MATERIAL_VARIABILITY`, not a relaxed bounded contract.

Samtools collate 1.23.1 is pinned only as a grouping qualification candidate:
`--no-PG -@ 2 -n 64` with a fixed temporary-prefix policy and no fast mode.
It produced complete QNAME groups and stable fragment counts without changing
records, flags, tags, or reference dictionary. It did not pass tolerance
schema 1: fixed grouped-input Salmon reached approximately 0.801% TPM relative
difference and fresh grouped inputs were materially order-sensitive. No
grouping process is therefore inserted into the qualified nf-core profile.
Raw Parabricks transcriptome BAM input remains fail-closed.

## Independent FASTQ Salmon candidate

The config-only candidate uses exact process identities observed in the 3.26.0
trace. It sets `ext.when=false` only for
`NFCORE_RNASEQ:RNASEQ:QUANTIFY_BAM_SALMON:SALMON_QUANT`, fixes the independent
FASTQ process to six CPUs, and leaves native STAR and Parabricks alignment
selection unchanged. Parameters are fixed to `pseudo_aligner=salmon`,
`skip_pseudo_alignment=false`, `trimmer=fastp`, `save_trimmed=true`, an explicit
Salmon index, and `salmon_quant_libtype=ISR`.

The public empty-tid fixture cannot construct optional transcript-level
SummarizedExperiment row metadata. A second exact selector disables only that
RDS process; quant.sf, transcript/gene count, TPM and effective-length matrices,
tx2gene, gene SummarizedExperiment, and MultiQC remain mandatory. No nf-core
source patch is needed for Candidate A.

Candidate A completed the small fixture and resume, but Salmon 1.10.3 did not
pass the fixed numerical reproducibility gate. The profile therefore remains
fail-closed for release execution; its successful orchestration result must not
be described as expression-backend qualification.

## Salmon 1.12.1 candidate result

The qualification-only profile ID `fastq_salmon_1_12_1_candidate` is reserved
in the candidate contract but is not exposed by planning. The local image and
1.12.1-specific k=31 index passed identity/build checks. Identical six-thread
FASTQ runs failed fragment exactness and tolerance schema 1, and the
version-to-version non-regression gate failed. The precise override generator
therefore refuses status `qualification_candidate` and
`rejected_numerical_gate`; only an already-qualified status could emit the two
allowlisted selectors for `PREPARE_GENOME:SALMON_INDEX` and FASTQ
`QUANTIFY_PSEUDO_ALIGNMENT:SALMON_QUANT`. BAM Salmon remains disabled and the
default 1.10.3 contract is unchanged.

## Salmon 2.5.1 deterministic candidate result

The fixed Rust candidate used `--deterministic --decoder serial`, six CPU
threads, ISR, and a version-specific PISCEM k=31 index. It passed 50-run and
cross-thread byte identity. Truth-v2 remediation preserved the old 19.4%
truth-v1 result but separated exact ties from identifiable leakage. Unique and
dominant controls each had zero transcript mass with a decoy-aware index and
100% reduction from transcript-only controls. The 62-run truth-v2 matrix,
biological gates, conditional nf-core integration, tximport, MultiQC, and
resume passed. Profile ID `fastq_salmon_2_5_1_deterministic_candidate` remains
qualification-only and non-default. External truth, full-size, production, and
diagnostic use remain unqualified.

External-truth dataset metadata was resolved prospectively, but primary runs
remain blocked. `SRR3497201` is E0 batch `216652830`, whose expected transcript
concentrations are constant. The required correlation gate is therefore
undefined and may not be treated as PASS. No 2.5.1 default/profile change was
made.

The separate v2 preregistration subsequently ran E0 with equal-molar metrics
and ERCC with concentration/fold-change metrics. Exact repeat/thread identity,
SIRV transcript/gene, and ERCC gates passed; SIRV equivalence aggregation and
Mix 2 cross-mapping failed their unchanged limits. This is an external-truth
failure, not authorization to expose the qualification-only profile.

Subsequent cause isolation found no Salmon 2.5.1-specific SIRV failure and
confirmed the named mitochondrial ERCC signal in unused held-out lanes. It did
not fully classify nuclear off-target reads outside the frozen oracle. This is
diagnostic evidence, not a revised threshold or qualified/default profile.

## Product profile catalog

The historical candidate IDs above remain unchanged. The product-facing
catalog separately exposes `salmon_2_5_1_deterministic` as the recommendation
for new internal-research series and `salmon_1_10_3_compatibility` for
continuity. Both use six CPU threads, explicit library type, fixed images, and
their own decoy-aware index format. Salmon 1.12.1 remains hidden and cannot be
selected. Profile changes create a new immutable analysis series.

Parabricks alignment may additionally emit STAR GeneCounts with the fixed
`--quantMode TranscriptomeSAM GeneCounts` parameter. This does not change the
Salmon backend and does not authorize native STAR fallback.

## Capacity finding

The RTX 3090 `low_memory_candidate` remains a candidate, not a full-human
qualified profile. A 1M-pair run against GENCODE 49 / GRCh38.p14 reached only
51.66% VRAM but 95.85% of the 47.05-GiB WSL memory and ended by SIGKILL during
junction insertion. This evidence identifies host RAM—not GPU VRAM—as the C1
ceiling on the tested configuration. It does not authorize CPU STAR fallback,
standard-memory mode, swap creation, or a lower-memory parameter chosen after
the result.

## Alignment-profile finding

The explicit workstation candidate retained low-memory, no-markdups,
`TranscriptomeSAM GeneCounts`, multimap/sjdb/SAM-attribute settings, reference,
and index identities, changing only `--two-pass-mode Basic` to
`--two-pass-mode None`. It succeeded on WT_REP1, but the full-human C1 mapping
was SIGKILLed at 91.53% WSL RAM with under 4 GiB available. Consequently
`parabricks_star_one_pass_workstation` is rejected on this host and
`parabricks_star_two_pass_high_memory` remains unavailable. CPU STAR fallback
and automatic profile substitution remain forbidden.
## CPU FASTQ quantification profile

`cpu_fastq_quantification_only_v1` fixes `aligner=none`,
`use_parabricks_star=false`, `gpu_selection=none`, and BAM mode `none`. This is
an explicit route, not a fallback from an alignment request.
