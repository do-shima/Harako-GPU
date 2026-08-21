process MULTIQC {
    container params.images.multiqc
    publishDir "${params.outdir}/reports/multiqc", mode: 'copy', overwrite: false

    input:
    path inputs

    output:
    path 'multiqc_report.html', emit: report
    path 'multiqc_report_data', emit: data

    script:
    """
    multiqc --force --filename multiqc_report.html --outdir . ${inputs}
    """
}
