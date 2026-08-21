process PUBLISH_ALIGNMENT_CONTRACT {
    tag "$sample"
    container params.images.samtools
    publishDir "${params.outdir}/alignment/${sample}", mode: 'copy', overwrite: false

    input:
    tuple val(sample), path(bam), path(bai), path(star_log), path(junction), path(counts), path(transcriptome)

    output:
    tuple val(sample), path("${sample}.sorted.bam"), path("${sample}.sorted.bam.bai"),
        path("${sample}.Log.final.out"), path("${sample}.SJ.out.tab"),
        path("${sample}.ReadsPerGene.out.tab"), path("${sample}.Aligned.toTranscriptome.out.bam"),
        emit: published

    script:
    """
    samtools quickcheck -- ${bam}
    """
}
