# High-memory host handoff

`harako-gpu capabilities export-handoff` emits a machine-readable, data-free
handoff for prospective full-human GPU-BAM qualification on a separate NVIDIA
host with at least 100 GiB host memory. It freezes the reference, STAR and Salmon
index IDs, nf-core/Nextflow/Parabricks identities, profile contracts, and prior
failure evidence. It contains no biological data or credentials and does not
perform remote execution.

When human BAM is disabled, the GUI exposes this export as a separate action.
It is not run preparation and does not silently select quantification-only or
perform remote execution.
