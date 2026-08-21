# Product contract

## Local execution lifecycle

The initial execution product is local, foreground, single-user, and one live
controller per immutable run directory. Preparation and approval do not pull
missing inputs. Resume cannot change samples, references, profiles, images,
indices, library type, pipeline/patch identity, work/output roots, or retention.
Status/watch is read-only. Artifact and support services are application
services reusable by a future GUI, but no GUI/daemon/server exists.

Success requires fixed process identity, Parabricks alignment, no native STAR
or nf-core Salmon branches, validated primary/optional secondary outputs,
matrices, STAR counts, reports, artifacts, terminal exit, and no live lock.
Schema version: `1`.

Harako-GPU is an internal, local, single-user workstation prototype for bulk
short-read RNA-seq. The MVP accepts single-end or paired-end FASTQ for human,
mouse, rat, or a custom reference. It targets NVIDIA GPUs on native Linux or
Windows 11 with WSL2. It is intended to wrap nf-core/rnaseq with Parabricks;
it is not a new algorithm, a diagnostic product, or a currently executing
analysis application.

## MVP profiles

`gpu_alignment_bam_keep` performs Parabricks STAR alignment, retains genomic
BAM/BAI and verification results, and independently runs CPU Salmon mapping
against the same nf-core-processed FASTQ to produce counts and TPM. Alignment
QC and MultiQC cover both branches without claiming that quantification is GPU
accelerated.

`gpu_alignment_bam_discard` performs the same alignment-aware workflow. It does
not mean quant-only or pseudoalignment. BAM/BAI may reach
`discarded_after_validation` only after terminal success and all validation
gates. Deletion is not implemented in this foundation.

`gpu_quant_only` and possible GPU-kallisto work are future candidates and are
not implemented.

## Fixed scientific/backend boundary

- Pipeline: `nf-core/rnaseq`
- Revision: `3.26.0`
- Aligner: `star_salmon`
- GPU switch: `use_parabricks_star = true`
- Container profile: Docker
- Qualified-candidate Parabricks version: the pipeline's standard `4.6.0-1`
- Reference input: explicit FASTA and GTF with SHA-256; `--genome` is forbidden
- No silent CPU STAR fallback

Parabricks `4.7.1-1` is recorded only as a future candidate channel. This
repository does not override the nf-core module container and does not adopt
that version before a separate qualification goal.

Counts, TPM, QC, and future DESeq2 integration are product outputs. DESeq2
execution is not implemented here.

Alignment-mode Salmon quantification identity is not the `quant.sf` byte SHA
alone. A versioned run manifest must retain the pinned Salmon version and image
digest, structured argv, thread count, transcript FASTA checksum, input BAM
scientific checksum, output byte SHA, canonical numerical digest,
reproducibility class, and tolerance schema version. The BAM scientific
checksum includes normalized header, record count, record multiset, and record
order because the pinned Salmon path is demonstrably order-sensitive.

Tolerance schema 1 requires exact feature identity/order, processed and mapped
fragment counts, library type, total NumReads, zero status, and all plan/input/
reference/container identity. Its small-fixture numerical ceilings are 0.1
absolute EffectiveLength, 0.1% relative TPM for transcript/gene TPM >=1, 0.001
absolute TPM for 0.1<=TPM<1, and 0.999999 minimum Spearman. A single 0.001
NumReads output-serialization quantum is distinguishable from count-matrix
identity and never permits a total-count or zero-status change.

The frozen-BAM six-thread experiment satisfies bounded numerical
reproducibility. The fresh Parabricks transcriptome-BAM path does not: record
order changes contiguous QNAME grouping, processed/mapped fragments are not
exact, and TPM exceeds the fixed ceiling. Its current decision is
`MATERIAL_VARIABILITY`; execution-adapter qualification cannot rely on this
path. Samtools collate 1.23.1 preserves records and restores exact fragment
accounting, but did not restore the numerical gate. The raw transcriptome BAM
role is provenance-only and must fail closed as Salmon input; no
`salmon_ready_transcriptome_bam` production strategy is currently selected.
The next candidate product path is independently qualified FASTQ-based Salmon.

The independent contract fixes `quantification_backend=fastq_salmon`,
`quantification_mode=mapping`, `quantification_input=processed_fastq`, Salmon
1.10.3 at its exact image digest, ISR, six threads, a decoy-aware k=31 index
identity, and `alignment_mode_salmon=disabled_unqualified`. The processed FASTQ
pair and index manifest are mandatory execution identities. Transcriptome BAM,
unqualified image/index versions, missing identities, and free-form Salmon
arguments fail closed.

The small-fixture Salmon 1.10.3 mapping experiment preserves fragments and
counts but exceeds the fixed TPM numerical ceiling. Consequently this backend
identity remains implemented but execution-unqualified until a separately
pinned Salmon version candidate passes without relaxing the tolerance.

The official Salmon 1.12.1 legacy C++ candidate was evaluated with its own
decoy-aware k=31 index and the same processed FASTQ/ISR/six-thread command.
Mapped fragments varied within identical six-thread repeats, TPM differences
exceeded tolerance schema 1, and the mapping rate differed materially from the
1.10.3/version-specific-index baseline. Candidate status is
`rejected_numerical_gate`; it is not a profile, default, or permissible nf-core
override. Salmon 2.x remains outside this contract until a separate pinned
binary, new-format index, truth-based comparison, and numerical qualification
are complete.

The pinned Salmon 2.5.1 Rust candidate is now internally qualified only. Its
deterministic profile was byte-identical across 50 public-fixture repeats and a
62-run truth-v2 matrix. The earlier `harako_truth_bulk_v1` 19.4% rejection is
retained as a historical aggregate proxy result; remediation showed that its
582-count numerator was exact-tie assignment mass. The replacement truth-v2
gate kept the absolute 1% and relative 90% thresholds and passed identifiable
unique/dominant decoy controls. The guarded nf-core override may be used only
for explicit candidate qualification. External truth, default adoption,
full-size, production, and diagnostic use remain unqualified, and the 1.10.3
default record is unchanged. Exactness and truth accuracy remain separate
release gates.

The first external-truth preregistration did not authorize primary execution.
The fixed SIRV source is equal-molar E0, so transcript truth Pearson and
Spearman are undefined by zero variance. Undefined metrics never satisfy a
numeric gate. External qualification requires a new, prospectively registered
SIRV source/gate decision; ERCC selection alone cannot qualify the candidate.

External preregistration v2 made that prospective decision without modifying
v1: E0 uses TPM-derived equal-molar transcript/gene error and records
correlation as `NOT_APPLICABLE_ZERO_VARIANCE`. Candidate runs passed exact
repeat/thread identity, SIRV identifiable transcript/gene gates, and ERCC
concentration/fold-change gates. The fixed SIRV equivalence-group and Mix 2
cross-mapping hard gates failed. Candidate status remains non-default and
externally unqualified; no product execution profile may select it.

Alignment execution and reporting qualification are separate gates. A file may
be treated as STAR `Log.final.out` only when it contains the required standard
STAR summary fields. A generic Parabricks runtime log is provenance, not a
numeric alignment metric. Missing unique-mapping data must remain
`QC_NOT_EVALUABLE`; it must never become a synthetic value or an implicit zero.
For the pinned qualified compatibility path, the generic log and genuine STAR
summary are retained under distinct names and the existing 5% nf-core gate
uses the genuine final two-pass STAR value.

External-truth cause isolation does not alter the v2 FAIL. The SIRV
equivalence contract is an incomparable, mostly-singleton metric shared across
Salmon versions. Held-out ERCC evidence confirms genuine mitochondrial sample
contamination for MT-RNR2/MT-CO2, but the full nuclear aggregate was not
reclassified outside the frozen oracle. No new adoption gate or default
authorization follows.

## Versioned quantification profiles

For newly created internal-research series, the explicit recommended profile
is `salmon_2_5_1_deterministic`; `salmon_1_10_3_compatibility` remains an
explicit continuity option. Salmon 1.12.1 is hidden. This catalog is a product
availability decision, not a rewrite of historical qualification results.
Existing series never migrate automatically. Every series freezes primary and
secondary profile, images, version-specific indices, reference, structured
commands, library type, and processed FASTQ identities. Only the primary may
feed future downstream analysis.

The optional STAR GeneCounts comparator is generated by the pinned Parabricks
lineage with both `TranscriptomeSAM` and `GeneCounts`. Its column is selected
from explicit U/ISF/ISR semantics. STAR and the secondary Salmon profile are
descriptive robustness evidence, not alternative primary inputs.

## Full-human capacity status

The fixed ERR188044 / GENCODE 49 capacity exercise did not qualify a supported
human input size. At C1 (1M paired reads), Parabricks 4.6.0-1 completed first
pass but was SIGKILLed while inserting junctions after WSL RAM reached 95.85%
and available memory fell below 2 GiB. C2-C4 were safety-gated. The reference
pack and version-specific indices are provenance-qualified inputs, not evidence
that the workstation can complete a full-human workflow. The product must not
advertise a human capacity estimate or automatically change WSL memory/swap.

The separate `parabricks_star_one_pass_workstation` contract changes only
`--two-pass-mode` from `Basic` to explicit `None`; it is never a silent fallback
from `parabricks_star_two_pass_high_memory`. WT_REP1 established the one-pass
command and artifact implementation, but full-human C1 reached 91.53% WSL RAM,
fell below 4 GiB available, and was SIGKILLed during mapping. It is rejected on
the current host. Two-pass remains `unsupported_host_memory`, not an algorithm
failure. Neither profile authorizes a full-human operating scale on that
Windows/WSL host.

Capability matrix v2 separates host-neutral alignment definitions from fixed
host qualification overlays. `ubuntu_native_rtx3090_ram128_v1` permits the
exact full-human Salmon 2.5.1 one-pass/two-pass routes only with valid installed
host, plugin, task-image, and Parabricks provenance receipts. The one-pass
overlay fixes 42 GB/12 CPUs; the two-pass overlay fixes 96 GB/12 CPUs. Both are
scoped solely to the fully qualified Parabricks process. This does not alter the
Windows/WSL limit or qualify compare-both.

For the exact GRCh38.p14/GENCODE 49 pack, FeatureCounts is frozen to
`-t exon -g gene_type`; the GTF is not modified and STAR GeneCounts remains an
independent artifact. Active high-memory work uses local ext4 SSD, while a
successful terminal result may be moved only by the explicit verified PAX
archive contract; automatic deletion is outside this implementation.
## Reference-aware execution boundary

Capability is keyed by exact host, reference pack, alignment profile, BAM output
mode, quantification mode, profiles, and execution context. Human BAM is not
available on the current 64-GB host. CPU FASTQ quantification without BAM is
qualified; it never claims GPU acceleration and never supplies STAR artifacts.

The local Streamlit GUI presents this exact matrix and immutable run lifecycle.
Disabled BAM choices remain visible with evidence; no GUI interaction changes a
requested route, profile, reference, or existing analysis series implicitly.

GUI acceptance readiness means automated functional/browser checks and a
developer-mediated walkthrough have no unresolved CRITICAL or MAJOR issue. It
does not mean external researchers accepted the product or that the interface
formally conforms to WCAG. No telemetry or participant tracking is permitted.
