include { FEATURECOUNTS_BIOTYPE_QC } from '../modules/local/featurecounts'
include { MULTIQC } from '../modules/local/multiqc'

workflow QC_REPORT {
    take:
    alignments
    fastp_reports
    gtf
    main:
    FEATURECOUNTS_BIOTYPE_QC(alignments, gtf)
    alignment_reports = alignments.map { sample, bam, bai, log, junction, counts, transcriptome -> tuple(sample, log, junction, counts) }
    report_inputs = fastp_reports.mix(alignment_reports).mix(FEATURECOUNTS_BIOTYPE_QC.out.counts)
        .map { row -> row.drop(1) }.flatten().collect()
    MULTIQC(report_inputs)
    emit:
    report = MULTIQC.out.report
}
