process PARABRICKS_RNA_FQ2BAM {
    tag "$sample"
    label 'parabricks_alignment'
    container params.images.parabricks

    input:
    tuple val(sample), path(r1), path(r2)
    path fasta
    path star_index

    output:
    tuple val(sample), path("${sample}.sorted.bam"), path("${sample}.sorted.bam.bai"),
        path("${sample}.Log.final.out"), path("${sample}.SJ.out.tab"),
        path("${sample}.ReadsPerGene.out.tab"), path("${sample}.Aligned.toTranscriptome.out.bam"),
        emit: alignment

    script:
    """
    pbrun rna_fq2bam \\
      --ref ${fasta} --in-fq ${r1} ${r2} \\
      --output-dir . --genome-lib-dir ${star_index} \\
      --out-bam ${sample}.sorted.bam --logfile ${sample}.parabricks.log \\
      --out-prefix ${sample}. --num-gpus 1 \\
      --out-qc-metrics-dir ${sample}_qc_metrics --no-markdups \\
      --out-sam-attributes NH HI AS NM MD --read-files-command zcat \\
      --read-group-sm ${sample} --read-group-id-prefix ${sample} \\
      --max-out-filter-multimap 20 --min-align-sjdb-overhang 1 \\
      --out-sam-strand-field intronMotif \\
      ${params.parabricks_extra_args}
    """
}
