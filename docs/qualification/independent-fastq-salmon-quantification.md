# Independent FASTQ Salmon quantification

Classification: `HARAKO_GPU_SALMON_VERSION_UPGRADE_QUALIFICATION_REQUIRED`

This qualification used only the public WT_REP1 paired-end fixture and the
pinned small reference. It does not qualify full-size data, production use, or
diagnostic use. Salmon remained at 1.10.3; no threshold was relaxed.

## Backend architecture and workflow audit

The selected Candidate A is config-only. nf-core/rnaseq 3.26.0 (resolved commit
`e7ca46272c8f9d5ceee3f71759f4ba551d3217a4`) feeds the same
`FASTQ_QC_TRIM_FILTER_SETSTRANDEDNESS.out.reads` channel to Parabricks and the
FASTQ pseudo-alignment subworkflow. An exact `withName` selector disables only
`NFCORE_RNASEQ:RNASEQ:QUANTIFY_BAM_SALMON:SALMON_QUANT`; trace evidence shows
zero alignment-mode tasks and one FASTQ-mapping task per sample. No nf-core
source patch or separate runner was required.

The empty-tid test GTF cannot populate the optional transcript
SummarizedExperiment row metadata. A second exact selector disables only that
RDS process. quant.sf, transcript/gene TSV matrices, tx2gene, gene
SummarizedExperiment, MultiQC, and all alignment outputs remain mandatory.

## Input, index, and command identity

- fastp 1.0.1 image digest:
  `sha256:d228dace961ab50d04471e02e7fd2c8f2b8cd5b1b37be2d4039e2db64fcfae45`
- processed R1 SHA-256:
  `a39a425c9c0e652bc0df0a5a59d172a073ebc78f9d741cb65bad7f4cedcad625`
- processed R2 SHA-256:
  `75fcc5e66900610fbf3777840f991c27611a0210b21565279cb44ec604e91143`
- R1/R2 count: 47,605 each; gzip integrity passed
- fastp argv profile: paired `--in1/--in2`, separate `--out1/--out2`, JSON and
  HTML reports, failed/unpaired outputs, `--thread 6`, and
  `--detect_adapter_for_pe`; no duplicate preprocessing occurred
- Salmon 1.10.3 image digest:
  `sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e`
- index ID:
  `364ab1bb39830756ae301b96839e986b47bd93af2ef2d321bbf80be05b615713`
- index: decoy-aware gentrome, k=31, 125 transcripts plus one decoy
- quantification command: structured argv with `--geneMap`, `--threads 6`,
  `--libType=ISR`, `--index`, `-1`, `-2`, and `-o`; no `-a`, shell eval, or
  free-form argument is accepted

Parabricks uses the GPU only for alignment. Salmon mapping and tximport are CPU
work. Raw Parabricks transcriptome BAM remains provenance-only and is rejected
as a quantification input.

## Minimal run and resume

The corrected Candidate A run completed 46 tasks in 1m45s. The identical
`-resume` completed in 39s. fastp, Parabricks, genomic BAM sort/index, FASTQ
Salmon, tximport, and gene SummarizedExperiment were cached; MultiQC was the
expected regenerated report. The trace classifier found zero BAM-based Salmon
tasks, one FASTQ-mapping Salmon task, and one separate strandedness probe.

Parabricks GPU evidence reached 9,467 MiB peak VRAM, 83% peak utilization, and
188.1 W peak power. The coordinate-sorted genomic BAM passed samtools
quickcheck. Its alignment-record checksum was
`70b490c1dccaacbbc88a1f07be34a737b5ee0abc95da36e7ee95356ee609aea7`
in all five fresh runs. STAR reported 47,605 input reads, 88.04% uniquely
mapped, and 1.91% multi-locus in every run. The earlier 87.33% value used a
different trimming path; the required fastp branch is consistently 88.04% and
is not represented as byte-identical to that earlier input contract.

MultiQC produced one Salmon section in mapping mode, the corrected STAR
section, no false mapping warning, and no alignment-mode Salmon section. The
result includes quant.sf, meta_info, lib-format counts, transcript and gene
count/TPM/effective-length matrices, tx2gene, gene SummarizedExperiment, HTML,
data directory, execution report, timeline, trace, DAG, and versions.

## Reproducibility results

The frozen processed FASTQ experiment ran Salmon 1.10.3 ten times at six
threads. All runs had exactly 47,605 processed fragments, 37,586 mapped
fragments, identical IDs/order/count estimates/zero status, and transcript and
gene Spearman 1.0. EffectiveLength max absolute difference was at most 0.037.
Two of nine baseline comparisons nevertheless exceeded the fixed 0.1% TPM
ceiling: 0.19726% and 0.20137% at transcript level (0.19718% and 0.20139% at
gene level). This is `MATERIAL_VARIABILITY`, not bounded reproducibility.

The 1/2/4/6-thread matrix ran three fresh quantifications per thread. Every
thread count preserved fragment and count identities, but every thread count
had at least one within-thread comparison above the ceiling. The largest
cross-thread TPM relative difference for TPM >= 1 was 1.06037%. Six threads
remain the product contract, but fixing that value does not make 1.10.3 pass.

Five fresh full branches all completed. Processed FASTQ hashes, genomic and
transcriptome alignment record multisets, fragment counts, STAR metrics, and
feature/count identities were stable. Raw transcriptome BAM record-order
checksums differed in all runs, while FASTQ Salmon never consumed that BAM.
Three of four fresh comparisons exceeded the TPM ceiling (0.19875%, 0.20012%,
and 0.12334%), confirming that the remaining variation is independent of the
Parabricks transcriptome-BAM ordering defect.

## Harako-RNAseq continuity

Immutable Harako-RNAseq source commit
`9d8628f48226c330e159ac79c14595f2cf65a551` uses Salmon 1.10.0, a decoy-aware
gentrome k=31 index, and `-l A`. Its already-local image ran successfully on the
same processed FASTQ and same index. It detected `IU` and mapped 37,848
fragments, versus the Harako-GPU 1.10.3 fixed `ISR` contract's 37,586.
Transcript Spearman was 0.83370 and eleven zero/non-zero states differed. This
is a library-type/command-contract difference as well as a version difference;
runtime parity is not claimed.

## Performance and qualified boundary

On this fixture, fastp used 1.8s/47 MB, Parabricks 39.8s/15.3 GB host RSS, and
tximport 3s/420 MB in the Nextflow trace. Salmon completed below the trace's
one-second resolution. Results occupied about 56 MB, work about 91 MB, and the
small Salmon index 0.86 MB. These figures must not be extrapolated to full-size
data.

The branch-separation architecture, fail-closed plan, artifact semantics,
fragment accounting, genomic alignment, STAR reporting, tximport, MultiQC, and
resume behavior are technically demonstrated for the small fixture. The
primary expression backend is not release-qualified because Salmon 1.10.3
violates the predeclared numerical ceiling. The next goal must qualify a pinned
newer Salmon candidate (starting with 1.12.1, with 2.x kept separate) without
changing this result or relaxing the tolerance.

Follow-up result: official legacy C++ Salmon 1.12.1 was tested with a dedicated
index and also failed the unchanged gate. Six-thread repeats varied in mapped
fragment count and exceeded the TPM ceiling; the version-specific index
comparison produced a material mapping-rate and expression shift. No nf-core
candidate run or default adoption followed. See
`salmon-1.12.1-upgrade-qualification.md`; the next version line must be a
separate Salmon 2.x qualification.

Follow-up result: Salmon 2.5.1 produced exact output across 50 runs and all
tested thread counts, but failed the independent truth decoy-leakage ceiling
(19.4% versus 1%). It was not integrated and did not change this document's
default record. See `salmon-2.5.1-deterministic-qualification.md`.

Later truth remediation and cause isolation preserved this historical result
while finding no confirmed 2.5.1-specific algorithm defect. The versioned
product catalog now recommends deterministic 2.5.1 for newly created internal
research series and retains 1.10.3 as a bounded-numerical compatibility
profile. That later product position does not retroactively change this
qualification verdict or make Harako-RNAseq Salmon 1.10.0 identical.
