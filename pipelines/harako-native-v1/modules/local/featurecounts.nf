process FEATURECOUNTS_BIOTYPE_QC {
    tag "$sample"
    container params.images.subread_featurecounts
    publishDir "${params.outdir}/qc/featurecounts", mode: 'copy', overwrite: false

    input:
    tuple val(sample), path(bam), path(bai), path(star_log), path(junction), path(counts), path(transcriptome)
    path gtf

    output:
    tuple val(sample), path("${sample}.featureCounts.txt"), path("${sample}.featureCounts.txt.summary"), emit: counts

    script:
    def strandedness = ['U': 0, 'ISF': 1, 'ISR': 2][params.library_type]
    """
    featureCounts -B -C -p -T 6 -s ${strandedness} \\
      -t ${params.featurecounts_feature_type} \\
      -g ${params.featurecounts_group_type} -a ${gtf} \\
      -o ${sample}.featureCounts.txt ${bam}
    """
}
