# Local reference-aware GUI

`harako-gpu ui` launches the Streamlit 1.60.0 MVP on `127.0.0.1:8501` by
default. It is a local, single-user presentation layer over the existing
capability, planning, run, status, artifact, support-bundle, and handoff
services. It does not construct scientific commands or mutate run state.

The GUI supports project selection, paired FASTQ discovery/editing, explicit
library type, fixed reference packs, capability-aware BAM selection, the two
visible Salmon profiles, immutable prepare/approval, attached child-controller
launch, polling, reconnection, results, artifact verification, resume, support
bundles, and high-memory handoff. It has no cancel, delete, archive, custom
reference, DESeq2, enrichment, daemon, queue, remote executor, or authentication.

On genuine native Linux, the GUI can prepare and launch a scientific run only
for the exact `ubuntu_native_rtx3090_ram128_v1` profile. The installed host
receipt, committed C1 parity reports, selected backend/profile, reference and
index identities, offline image/provenance closure, local active filesystem,
disk reserve, and persistent controller lock must all validate. Hardware probes
or a profile string alone never unlock the buttons. A blocker leaves safe plan
inspection available and provides no manual bypass.

Receipt-backed Ubuntu defaults to `harako_native_v1`; the pinned
`nfcore_rnaseq_3_26_reference` backend is an advanced comparison/reference
choice. One-pass displays its fixed 42 GB / 12 CPU contract and two-pass its
fixed 96 GB / 12 CPU contract. Quantification choices are Salmon 2.5.1
recommended-only, Salmon 1.10.3 bounded-numerical compatibility-only, and the
sequential compare-both route. Only indices selected by that mode are required.

The native lifecycle is deliberately explicit: validate eligibility, create an
immutable plan, review its approval hash, prepare, then separately start. Run
state is rediscovered from disk after a page refresh; resume, status, artifact
verification, deep verification, and sanitized support bundles reuse the same
public services as the CLI. The GUI does not construct Nextflow commands or
manage a second process supervisor.

Active output and work must remain below the configured runtime root on local
ext4, XFS, or Btrfs storage. Windows drive mounts, CIFS/NFS, and WD Gold are not
active work locations. Successful terminal results may later use the explicit
`harako-gpu-terminal-results-archive-v1` WD Gold PAX archive operation; this GUI
foundation performs no automatic archive or deletion.

Human GRCh38.p14/GENCODE 49 runs on the Windows/WSL host expose CPU-only FASTQ
quantification. Human BAM remains unavailable because of the retained host-RAM
qualification failures. The exact small fixture exposes qualified GPU BAM.
Research use only; non-diagnostic and non-clinical.

Windows/WSL continues to default to the nf-core reference backend and uses the
existing `wsl.exe --distribution ... --exec` controller path. Harako-native is
not executable there, an Ubuntu receipt cannot qualify it, and Windows paths
remain invalid as native Linux paths. Historical plans without a backend keep
their nf-core reference meaning. CPU STAR remains unavailable. Native GUI
scientific C1 acceptance on Ubuntu is still a separate pending qualification;
this Windows implementation does not claim it.

Acceptance-readiness hardening adds one purpose and completion condition per
page, progressive disclosure for hashes/digests, five color-independent message
levels, actionable error summaries, generated/not-generated Results summaries,
and user-controlled status refresh. The audit is WCAG 2.2 AA-informed rather
than a formal conformity claim. External-user acceptance is pending.
