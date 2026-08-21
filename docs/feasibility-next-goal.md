# Feasibility progression

The run/status/resume/artifact lifecycle is qualified on WT_REP1 and truth-v2
small fixtures. The next goal should retain these immutable services while
adding a GUI/application presentation layer or a separately preregistered
larger-data resource envelope. It must not add DESeq2/enrichment, automatic BAM
deletion, background scheduling, or full-size claims implicitly.
Completed goals: `HARAKO_GPU_PARABRICKS_MINIMAL_FEASIBILITY` and
`HARAKO_GPU_PARABRICKS_STAR_METRICS_COMPATIBILITY`.

The compatibility follow-up separated the generic Parabricks log from the
genuine second-pass STAR summary. Native STAR 2.7.2a matched the recovered
metrics exactly, nf-core's mapping gate passed at 87.33%, MultiQC reported the
same value, and fresh-run/resume validation passed without changing the genomic
BAM record set or count matrices.

`HARAKO_GPU_SALMON_REPRODUCIBILITY_CONTRACT` is complete. It found bounded
six-thread Salmon variation for one frozen transcriptome BAM, but five fresh
Parabricks runs emitted one alignment-record multiset in five different orders.
The resulting contiguous QNAME group count changed, Salmon processed/mapped
fragment counts changed with it, and transcript/gene TPM exceeded the fixed
0.1% ceiling.

The recommended next goal is
`HARAKO_GPU_TRANSCRIPTOME_BAM_GROUPING_COMPATIBILITY`. It should determine an
upstream-supported, scientifically justified grouping contract before any
execution adapter or larger-fixture qualification. It must not silently sort
or shuffle the BAM, relax the existing ceiling, or change pinned backend
versions without a separate qualification decision.

## Retained prerequisites

1. Qualify native Linux and WSL2 separately; do not transfer readiness between them.
2. Confirm Java 17 or newer and initial-qualified Nextflow 25.04.3 from `doctor --json`; nf-core CLI availability is optional.
3. On WSL, make `/usr/lib/wsl/lib` visible in PATH if doctor reports `NVIDIA_SMI_PATH_NOT_EXPORTED`; do not install a Linux NVIDIA driver in WSL.
4. Confirm WSL-side Docker version/info/context, Linux server, and GPU visibility.
5. Start RTX 3090 feasibility with `low_memory_candidate`, fixed `--low-memory`, and `skip_markduplicates=true`; do not call the standard profile qualified.
6. Review and manually accept NVIDIA/NGC and all reference/data terms where applicable.
7. Authenticate manually if the selected registry requires it.
8. Make the nf-core/rnaseq 3.26.0 standard Parabricks 4.6.0-1 image locally available without changing the module container.
9. Supply a deliberately small, permitted FASTQ fixture plus matching explicit FASTA/GTF and record their SHA-256 values.
10. Record both Windows-host and WSL-visible CPU/RAM/scratch; meet the work-root scratch gate before execution.

## Completed experiment

1. Freeze the generated plan and hardware report.
2. Verify that the resolved workflow contains Parabricks STAR and no CPU STAR fallback.
3. Run the pinned pipeline once with `gpu_alignment_bam_keep`.
4. Verify BAM/BAI, `samtools quickcheck`, coordinate sort, reference contigs,
   Salmon counts/TPM, required alignment QC, MultiQC, versions, and Nextflow reports.
5. Compare a separately authorized CPU profile only in a distinct goal; never use it as fallback.
6. Measure peak VRAM, host RAM, disk, exit status, and task/container versions.
7. Repeat the exact input to assess resume behavior without changing this goal's foundation contract.
8. Exercise the discard state machine in dry-run/audit form first; actual deletion requires a separately reviewed implementation.

## Decision record

Record success/failure independently for runtime feasibility, performance,
artifact completeness, and scientific equivalence. A successful preflight or a
single successful GPU run does not establish broad GPU support.

Parabricks 4.7.1-1 may be evaluated only in a later independent qualification
channel; it must not silently replace 4.6.0-1.

## Versioned expression foundation completed

The small-fixture foundation now has two fixed Salmon profiles, immutable
analysis series, same-FASTQ concordance, and a qualified Parabricks
ReadsPerGene comparator. A future goal may add a general execution/status/
resume adapter or downstream DE contract, but must retain the primary-profile
boundary, avoid automatic series migration, and not infer full-size
performance from these fixture measurements.

## Medium-human capacity outcome

The storage-remediated capacity goal fixed the real human source, full GENCODE
49 reference, and three version-specific indices, but did not complete C1. The
tested WSL instance exposed 50,514,726,912 bytes RAM and no swap; Parabricks
reached 48,418,181,120 bytes used and was SIGKILLed during junction insertion.
The next goal should be a prospectively reviewed resource-strategy decision
(for example, a user-controlled larger WSL memory allocation on appropriate
hardware or a separately qualified reference/backend strategy). It must not
delete retained data, loosen gates, enable fallback, or call 1M supported.
