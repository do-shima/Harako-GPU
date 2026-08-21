# Medium human capacity and resource envelope qualification

## Completion classification

`HARAKO_GPU_MEDIUM_HUMAN_CAPACITY_AND_RESOURCE_ENVELOPE_BLOCKED`

The previous storage blocker is preserved as historical evidence. Its observed
89.33 GB free-space condition was remediated manually by the user: WSL root was
502.90 GiB total and 322.41 GiB free at restart. No runtime artifact was
deleted. The new blocker is independent: C1 full-human Parabricks alignment
exceeded the frozen WSL RAM hard-stop and was SIGKILLed. C1 therefore did not
qualify, and C2-C4 were not started.

## Dataset preregistration

The runtime preregistration was frozen before acquisition at SHA-256
`593e95828b14b474a9a61c90ebf8bd95542ebd313d16a4bbfcef50b0ba395123`.
It fixes ERR188044, the first-N nested subset policy, all four levels, reference
release, modes, and disk/RAM/VRAM gates. It has not been modified.

ERR188044 is public paired-end Homo sapiens RNA-seq from PRJEB3366 / ERP001942,
sample SAMEA1573216, experiment ERX162864, Illumina HiSeq 2000, prepared with
TruSeq RNA Sample Prep Kit v2. ENA declares 36,349,964 pairs and 5,525,194,528
bases. Both official FASTQs passed MD5, SHA-256, gzip, four-line structure,
pair-count, QNAME, read-length (76 nt), and orphan (zero) checks.

The original orientation probe result is retained. Its per-run denominator was
not comparable and returned UNKNOWN. Before primary quantification, amendment
v2 used the common unstranded assigned-fragment universe and the unchanged
orientation-only thresholds. IU=922,634, ISF=475,072, and ISR=474,443 selected
product library type U / Salmon IU. No abundance, truth metric, or mapping-rate
optimization was used.

## Reference and indices

The fixed GENCODE 49 / GRCh38.p14 human-only pack passed source checksum,
inventory, contig compatibility, and tx2gene checks. The three index identities
and sizes are recorded in [the reference pack contract](../human-reference-pack.md).

Build measurements:

| index | wall time | peak WSL RAM | final size |
|---|---:|---:|---:|
| STAR 2.7.2a | 1,523.64 s | 40.93 GB | 30.16 GB |
| Salmon 1.10.3 | 1,282.96 s | 22.40 GB | 18.22 GB |
| Salmon 2.5.1 | 845.84 s | 19.27 GB | 10.03 GB |

## Capacity subsets

Deterministic gzip subsets contain exactly 1M, 5M, 10M, and 20M paired records
and form nested prefixes. They were generated and validated in WSL ext4. The
full source FASTQ was downloaded and structurally validated, but no full-source
workflow was run.

## C1 1M run

Four immutable attempts were retained in separate run/work directories:

1. The first exposed an nf-core prepare-genome selection defect: a supplied
   STAR index was ignored when FASTA was also present.
2. After exact-SHA patching, scheduler validation exposed the stock 72 GB
   Parabricks request on a 47 GiB-visible WSL host.
3. A bounded 42 GB scheduling request reached Parabricks and exposed the
   required `sjdbOverhang=74` index/runtime identity.
4. With all fixed identities aligned, Parabricks completed first-pass mapping
   and was SIGKILLed while inserting junctions into the genome indices.

The last run processed the intended fixed C1 input and is the resource result.
Its peak WSL RAM was 48,418,181,120 bytes of 50,514,726,912 bytes (95.85%);
minimum available RAM was 2,096,545,792 bytes (1.95 GiB), with no swap. Peak
GPU memory was 12,695 MiB of 24,576 MiB (51.66%). Its retained work high-water
was 37,009,951,881 bytes and result high-water was 301,745,348 bytes. Minimum
filesystem free space during this run was 182,672,023,552 bytes, so the disk
reserve remained intact. Sampled CPU utilization peaked at 61.98% (17.85%
mean), GPU utilization peaked at 67% (12.15% mean), and GPU temperature peaked
at 58 C. The process exited 255 after SIGKILL. Required BAM,
STAR GeneCounts, Salmon, matrices, report, and artifact verification were not
produced, so C1 is `RESOURCE_FAILED` rather than a partial pass.

An active `run status` query separately observed the run in RUNNING state with
current stage/task and resource data, without interrupting execution. The
first failed run produced a sanitized support bundle. Neither proves artifact
correctness for C1.

## Later levels and envelope

| level | mode | outcome |
|---|---|---|
| C1 1M | recommended-only | `RESOURCE_FAILED` |
| C2 5M | compare-both | `NOT_RUN_SAFETY_GATE` |
| C3 10M | recommended-only | `NOT_RUN_SAFETY_GATE` |
| C4 20M | conditional recommended-only | `NOT_RUN_SAFETY_GATE` |

There is no maximum tested successful scale, no maximum comfortable scale, no
recommended internal operating scale, no compare-both overhead measurement,
and no capacity estimator. Publishing any of those would invent evidence.

## Qualified scope

Qualified here: dataset/source identities, deterministic subset generation,
human reference pack provenance, version/index coupling, storage/RAM/VRAM
monitoring, disk and progression rules, public run/status integration, and
fail-closed resource classification.

Unqualified: any full-human analysis scale, BAM/STAR/Salmon artifacts at 1M or
larger, compare-both overhead, cold-run success timing, native Linux, multiple
samples, standard-memory mode, clinical/diagnostic use, and capacity
extrapolation.

No runtime artifact was deleted, no WSL/Docker/Windows storage setting was
changed by Codex, and all failed work remains available for the future
retention goal.

## Historical follow-up: separate one-pass profile

This report and its two-pass verdict remain unchanged. A later, separately
preregistered one-pass profile completed WT_REP1 but failed full-human C1 by
SIGKILL during mapping at 91.53% WSL RAM and 3.99 GiB minimum available. It did
not rescue or modify this two-pass record. See
`parabricks-one-pass-workstation-profile.md` for that independent result.
Follow-up: the historical BAM-capacity failure remains unchanged. A later goal
qualified CPU FASTQ quantification without BAM through the full ERR188044 source;
those measurements belong to a separate route and are not BAM-capacity evidence.
