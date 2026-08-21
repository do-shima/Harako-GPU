# Parabricks one-pass workstation profile qualification

## Completion classification

`HARAKO_GPU_PARABRICKS_ONE_PASS_WORKSTATION_PROFILE_REJECTED`

The fixed one-pass implementation completed WT_REP1, but the full-human C1
run was SIGKILLed after crossing the preregistered unsafe host-RAM boundary.
No full-human read-pair scale is qualified on this workstation.

## Previous two-pass failure

The historical two-pass run, work, logs, support bundle, preregistration, and
verdict were preserved. It reached 95.85% of WSL RAM during junction insertion.
`parabricks_star_two_pass_high_memory` remains `unsupported_host_memory`; this
does not reject the algorithm on a separately qualified high-memory host.

## One-pass contract and small fixture

The only scientific command delta is explicit `--two-pass-mode None` instead
of `Basic`. Low-memory, GeneCounts/TranscriptomeSAM, no-markdups, multimap,
sjdb-overhang, SAM attributes, strand field, read group, reference, index, and
versions remain fixed. WT_REP1 completed 38 Nextflow processes and all 12
Harako tasks in 96 seconds. BAM, BAI, STAR log, junctions, GeneCounts,
transcriptome BAM, both Salmon profiles, matrices, MultiQC, concordance, and
the self-contained report validated.

The separate descriptive comparison records mapping, splice, BAM, GeneCounts,
Salmon, and resource differences. It makes no scientific-equivalence claim.

## C1 — 1M pairs

Run `20260817T082055Z-bfce8a8e` used the public execution CLI, a fresh run and
work directory, fixed GRCh38.p14/GENCODE49 assets, and the existing
`sjdbOverhang=74` index. fastp processed 958,978 of 1,000,000 pairs. The actual
Parabricks command contained `--two-pass-mode None` and no `Basic`.

Parabricks was SIGKILLed during mapping (exit 255). Peak WSL RAM was
46,235,611,136 of 50,514,726,912 bytes (91.53%), minimum available RAM was
4,279,115,776 bytes (3.99 GiB), and memory PSI `some avg10` peaked at 6.33.
These satisfy the preregistered UNSAFE thresholds. Peak VRAM was 12,686 MiB
(51.62%), so GPU memory was not limiting. The disk reserve remained valid with
144,797,442,048 bytes free at the observed minimum. Required BAM, GeneCounts,
Salmon, matrices, MultiQC, and report artifacts were not produced and were not
treated as PASS.

The failed-run support bundle excludes biological data and has SHA-256
`8b5890f78d63a5ca44025a8f058c18708bcb545561f2ff3e9b727a15264c3589`.

## Capacity decision

C1 is `C1_RESOURCE_FAILED`. C2, C3, and C4 are
`NOT_RUN_SAFETY_GATE`; the result-dependent ladder was not continued. There is
no maximum tested successful scale, maximum comfortable scale, or recommended
internal operating scale for full-human Parabricks on this host.

The one-pass profile is rejected on the current 64-GB host. There was no
fallback, parameter mutation, two-pass retry, WSL/swap change, index rebuild,
or artifact deletion. The full 36.35M-pair source was not run.

## Limitations

The successful small fixture qualifies implementation only. Annotation-backed
one-pass may have lower sensitivity for novel or low-abundance splice
junctions than high-memory two-pass. Use is research-only, non-diagnostic, and
non-clinical.
Follow-up: the failure remains immutable and full-human BAM remains unavailable.
The later reference-aware goal qualified a separate CPU FASTQ quantification-only
route; it is not a rescue or reclassification of this one-pass result.
