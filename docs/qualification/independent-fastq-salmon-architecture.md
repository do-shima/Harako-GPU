# Independent FASTQ Salmon architecture audit

Audit scope is nf-core/rnaseq `3.26.0`, resolved commit
`e7ca46272c8f9d5ceee3f71759f4ba551d3217a4`, with no upstream source change.

`workflows/rnaseq/main.nf` imports the same pseudo-alignment subworkflow twice.
For `star_salmon`, `QUANTIFY_BAM_SALMON` receives the Parabricks transcriptome
BAM and passes `alignment_mode=true`; its Salmon module therefore emits
`-t <transcript_fasta> -a <bam>`. Separately, when
`pseudo_aligner=salmon` and `skip_pseudo_alignment=false`,
`QUANTIFY_PSEUDO_ALIGNMENT` receives
`FASTQ_QC_TRIM_FILTER_SETSTRANDEDNESS.out.reads` and passes
`alignment_mode=false`; the module emits `--index`, `-1`, and `-2`.
Parabricks alignment consumes the same processed-read channel.

There is no global `skip_quantification` switch that safely disables only the
BAM route. `skip_pseudo_alignment` controls only the FASTQ route and
`skip_quantification_merge` controls aggregation. Candidate A therefore uses
the exact fully-qualified BAM Salmon process selector and its built-in
`task.ext.when` gate. Trace evidence must show zero BAM-route tasks and one
FASTQ-route task per sample. The strandedness subsample Salmon process is a
separate probe and is never classified as primary quantification.

The first config-only run proved branch separation but exposed an optional
transcript SummarizedExperiment failure for the public empty-tid GTF fixture.
The corrected config disables that exact RDS process only. Core tximport TSVs,
tx2gene, gene SummarizedExperiment, MultiQC, and all alignment artifacts remain
required. This is config-only integration; no SHA-pinned nf-core source patch
or separate Harako runner is selected.

Harako-RNAseq's fixed source builds transcriptome+genome gentrome, writes genome
contigs as decoys, and invokes `salmon index -k 31`. nf-core uses the same index
class. Harako 1.10.0 uses `-l A`, while this contract uses nf-core 1.10.3 with
`--geneMap`, ISR, and six threads. Those differences remain explicit.
