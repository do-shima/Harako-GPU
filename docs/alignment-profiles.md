# Alignment profiles

Harako-GPU records alignment as an immutable, versioned profile. Changing the
alignment profile creates a new analysis series; artifacts from different
profiles must not be mixed.

## Workstation one-pass

`parabricks_star_one_pass_workstation` fixes nf-core/rnaseq 3.26.0, Nextflow
25.04.3, Parabricks 4.6.0-1, one GPU, `--low-memory`, no mark duplicates,
`TranscriptomeSAM GeneCounts`, and the explicit value `--two-pass-mode None`.
The full-human reference remains GRCh38.p14 / GENCODE 49 with the existing
STAR 2.7.2a lineage index at `sjdbOverhang=74`.

The profile is rejected on the tested 64-GB Windows / 47.05-GiB WSL host. Its
1M-pair full-human C1 run reached 91.53% WSL RAM, fell below 4 GiB available,
and was SIGKILLed during mapping. The successful WT_REP1 small-fixture run
proves the one-pass command and artifact contract, but does not qualify a
full-human operating scale.

On `ubuntu_native_rtx3090_ram128_v1`, the exact full ERR188044 route completed
under the fixed one-pass contract: 42 GB and 12 CPUs applied only to the fully
qualified Parabricks process selector. This is a host qualification overlay;
the scientific profile itself is host-neutral.

This profile uses annotation-backed one-pass alignment. It is intended for BAM
generation, GeneCounts, and known-gene expression analysis. Sensitivity for
reads spanning novel or low-abundance splice junctions may be lower than with
the high-memory two-pass profile.

## High-memory two-pass

`parabricks_star_two_pass_high_memory` fixes `--two-pass-mode Basic`. It remains
`unsupported_host_memory` on the Windows/WSL host after the historical 1M run used
95.85% WSL RAM and was SIGKILLed during junction insertion. This is not an
algorithm rejection. The Ubuntu 128-GB host overlay fixes 96 GB and 12 CPUs for
the same fully qualified Parabricks process only; its retained full-size run
completed with a cgroup peak of 80,275,611,648 bytes and no cgroup or host OOM.

Harako-GPU never silently switches between these profiles and never falls back
to CPU STAR. Both are research-only, non-diagnostic, and non-clinical.
