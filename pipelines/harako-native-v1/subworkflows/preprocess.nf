include { FASTP } from '../modules/local/fastp'

workflow PREPROCESS {
    take:
    raw_reads
    main:
    FASTP(raw_reads)
    emit:
    reads = FASTP.out.reads
    reports = FASTP.out.reports
}
