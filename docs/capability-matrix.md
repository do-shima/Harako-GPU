# Reference-aware capability matrix

Harako-GPU evaluates an exact combination of host profile, reference-pack identity,
alignment profile, BAM output mode, quantification mode, and execution context.
Species labels and FASTA size alone never establish availability.

On `windows_wsl2_rtx3090_ram64_v1`, qualified small-reference Parabricks BAM
remains available. The exact GRCh38.p14/GENCODE 49 pack is
`FULL_MAMMALIAN_HIGH_MEMORY`: both one-pass and two-pass GPU BAM routes are
`UNSUPPORTED_HOST_MEMORY` based on retained runtime evidence. They are not
silently replaced.

The explicit alternative is `fastq_quantification_only` with BAM mode `none`.
It runs fixed fastp preprocessing and CPU Salmon quantification, and generates no
BAM, BAI, junction, STAR GeneCounts, alignment QC, or alignment MultiQC section.

Capability status is evidence-versioned. A candidate becomes available only after
prospective runtime qualification for that exact host/reference/profile contract.

Matrix v2 adds `ubuntu_native_rtx3090_ram128_v1`. For the exact full-human
reference, one-pass and two-pass with Salmon 2.5.1 are
`AVAILABLE_QUALIFIED` only when the installed host receipt, the 18-image task
closure, `nf-schema@2.5.1` offline cache receipt, and Parabricks linux/amd64
offline provenance all validate. Missing or changed provenance is
`BLOCKED_PROVENANCE`; RAM, GPU identity, or the profile ID alone never promotes
a route. Compare-both remains unqualified. Historical v1 snapshots remain
readable.

The GUI consumes this service result verbatim. It does not infer capability
from species, RAM labels, widget state, or observed mapping results. Human BAM
is disabled on the Windows/WSL host with a high-memory handoff action; exact
small-reference BAM remains available. Native capability can be displayed, but
native GUI launch stays guarded pending the separate Ubuntu public-CLI smoke.
