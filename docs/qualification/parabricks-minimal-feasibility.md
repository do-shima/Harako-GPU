# Parabricks minimal feasibility qualification

Current classification after compatibility follow-up:
`HARAKO_GPU_PARABRICKS_MINIMAL_FEASIBILITY_QUALIFIED`

Original classification at the end of the first run:
`HARAKO_GPU_PARABRICKS_MINIMAL_FEASIBILITY_QUALIFIED_WITH_DOWNSTREAM_LIMITATION`

This qualification covers one pinned, public, paired-end nf-core test fixture
only. It demonstrates real Parabricks GPU alignment, BAM production, downstream
quantification, reporting, and core resume caching. It does not qualify a
full-size dataset, scientific equivalence, production readiness, standard
memory mode, mark duplicates, or all RNA-seq workloads on an RTX 3090.

## Runtime and fixture

The run used Windows 11, WSL2 Ubuntu 22.04 on Linux kernel
`6.18.33.2-microsoft-standard-WSL2`, Docker Linux engine 29.7.2, Java 17.0.19,
Nextflow 25.04.3, and one RTX 3090 (UUID
`GPU-729a533c-e203-acc9-47b0-27ac387bc151`, driver 591.86). The fresh Harako
doctor result was `PREFLIGHT_READY_LOW_MEMORY_CANDIDATE`. Its 12-thread and
47.05-GiB WSL resource findings remain warnings; the tiny fixture does not
satisfy or waive the 24-thread/100-GiB recommendations.

Reference files came from `nf-core/test-datasets` commit
`626c8fab639062eade4b10747e919341cbf9b41a`; FASTQs came from commit
`e07c1b158d1c4c9ea7978959d31e651098bec581`. Both FASTQs passed gzip and
four-line record validation and contained 50,000 reads each. Exact sizes,
download timestamps, source paths, and local SHA-256 values are in the adjacent
JSON report. GitHub blob IDs were not treated as SHA-256 values.

## Pipeline, plan, and precheck

`nf-core/rnaseq` tag 3.26.0 resolved to commit
`e7ca46272c8f9d5ceee3f71759f4ba551d3217a4` with nf-schema 2.5.1. The module
fixed Parabricks to `nvcr.io/nvidia/clara/clara-parabricks:4.6.0-1`; its local
digest matched the required `sha256:d0761eb4...4650447`. The compatible STAR
index task used STAR 2.7.2a through the nf-core container with digest
`sha256:f60e2def...4efd08`.

Harako plan `bc138670...f24a46` was created and revalidated with WSL absolute
paths, `star_salmon`, `use_parabricks_star=true`, `low_memory_candidate`, fixed
debug mapping `--low-memory --x3`, `skip_markduplicates=true`, BAM retention
`keep`, explicit FASTA/GTF/transcript FASTA, and no arbitrary parameter or shell
field. The first stub exposed the pipeline's declared 72-GB index requirement;
the debug-only config then applied nf-core's bounded `test_gpu` scheduling
envelope (8 CPUs, 30 GB, 2 hours). The second isolated stub completed and
resolved Parabricks alignment, BAM/Samtools, Salmon, and MultiQC without
selecting native `STAR_ALIGN`.

## Actual execution evidence

The actual run completed with exit 0 in 4m38s and 25 successful tasks. The trace
contains `PARABRICKS_RNA_FQ2BAM` and no native STAR alignment process. The task
used the exact 4.6.0-1 container and `pbrun rna_fq2bam`; `.command.sh` contains
`--low-memory --x3` and `--no-markdups`. Parabricks logs record CUDA success,
GPU 0 processing, version 4.6.0-1, and a successful STAR phase.

During the 40.7-second Parabricks task, 39 one-second samples showed peak VRAM
9,619 MiB versus a 1,240-MiB baseline, median utilization 5%, maximum utilization
81%, peak power 209.62 W, and maximum temperature 54 C. The low median is
reported without embellishment; the VRAM increase, 81% maximum, CUDA logs, and
GPU-only task command together establish actual GPU execution. Peak observed
WSL RAM use was 19,854,188,544 bytes, trace peak RSS for the task was 15.3 GB,
and peak host CPU utilization was 98.971%.

## BAM, quantification, and reports

The published coordinate-sorted BAM is 3,347,850 bytes and its BAI is 1,488
bytes. Samtools 1.23.1 in the exact nf-core-resolved container passed
`quickcheck`, found `SO:coordinate`, `@SQ I:230218` matching the reference FAI,
and read group/sample `WT_REP1`. Flagstat reported 92,113 mapped records; stats,
flagstat, and idxstats were retained. The BAM and BAI SHA-256 values are in the
JSON report, and neither file was deleted.

Alignment logs, `SJ.out.tab`, transcriptome BAM, Salmon `quant.sf` and
`meta_info.json`, merged gene/transcript counts and TPM, MultiQC HTML/data,
Nextflow report/timeline/trace/DAG, and software versions all exist and are
non-empty. Alignment-mode Salmon processed and mapped 33,017 fragments and
produced 124 transcript rows.

## Downstream limitation

Parabricks writes runtime messages into the published `Log.final.out` role
instead of the standard STAR metrics table that MultiQC expects. MultiQC thus
records STAR uniquely mapped reads as 0% and nf-core ends with a 5%-mapped
sample warning. This conflicts with the independently validated BAM and
alignment-mode Salmon metrics. MultiQC itself completed and wrote its report,
but its STAR-specific mapping interpretation is not qualified. The alignment
success is therefore not presented as unqualified pipeline/reporting success.

This was the accurate verdict for the original run. The pinned follow-up in
`parabricks-star-metrics-compatibility.md` isolated the generic log, recovered
the genuine second-pass STAR summary, matched it exactly to a native STAR
2.7.2a oracle, and reran the same fixture. The corrected run reported 87.33%
unique mapping, produced no false 5% warning, completed all 47 tasks, and
preserved the BAM alignment-record checksum and count matrices. The historical
evidence above is retained while the current combined small-fixture status is
upgraded to qualified.

## Resume

The identical plan, params, inputs, reference, result root, and work root were
run with `-resume`. It completed in 30.6 seconds. Twenty-four of 25 tasks were
`CACHED`, including Parabricks index and alignment, BAM sort/index, Samtools QC,
Salmon, and tximport. BAM mtime/hash and all identity checksums remained
unchanged; resume GPU monitoring stayed at the 1,240-MiB baseline. The
run-specific MultiQC aggregation alone regenerated in 8.7 seconds, and this
exception is recorded rather than described as an all-task cache hit.

Runtime FASTQ, references, indices, BAMs, work directories, raw logs, and
absolute-path artifacts remain outside Git. The machine-readable sibling report
uses normalized artifact roles and checksums.

## Salmon reproducibility follow-up

The qualification above establishes execution, artifact production, and
resume behavior; it did not establish fresh-run numerical reproducibility.
The subsequent `salmon-reproducibility-contract.md` ran Salmon ten times on one
frozen transcriptome BAM, a 1/2/4/8-thread matrix, and five fresh
Parabricks-to-Salmon paths.

The fixed-BAM six-thread result was bounded within the provisional numerical
ceiling. The fresh path was not: identical transcriptome alignment-record
multisets appeared in different orders, creating different contiguous QNAME
group counts, different Salmon processed/mapped fragment counts, and up to
about 0.258% TPM variation. That exceeds the fixed 0.1% ceiling. Accordingly,
Parabricks GPU alignment/BAM/STAR-reporting evidence remains qualified for this
fixture, while fresh alignment-mode Salmon release reproducibility is blocked.
