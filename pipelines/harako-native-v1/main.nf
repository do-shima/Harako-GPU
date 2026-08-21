nextflow.enable.dsl = 2

include { PREPROCESS } from './subworkflows/preprocess'
include { ALIGN_PARABRICKS } from './subworkflows/align_parabricks'
include { QC_REPORT } from './subworkflows/qc_report'

workflow {
    def required = [params.input, params.outdir, params.fasta, params.gtf,
                    params.star_index, params.library_type,
                    params.featurecounts_group_type,
                    params.parabricks_two_pass_mode,
                    params.parabricks_extra_args,
                    params.images.fastp, params.images.parabricks,
                    params.images.samtools, params.images.subread_featurecounts,
                    params.images.multiqc]
    if (required.any { it == null }) {
        error 'Harako-native requires its complete frozen parameter contract'
    }
    if (!(params.library_type in ['U', 'ISF', 'ISR'])) {
        error 'Harako-native requires explicit U, ISF, or ISR library type'
    }
    if (params.featurecounts_feature_type != 'exon') {
        error 'Harako-native FeatureCounts feature type must be exon'
    }
    def expectedArgs = "--low-memory --quantMode TranscriptomeSAM GeneCounts --sjdb-overhang 74 --two-pass-mode ${params.parabricks_two_pass_mode}"
    if (!(params.parabricks_two_pass_mode in ['None', 'Basic']) || params.parabricks_extra_args != expectedArgs) {
        error 'Harako-native Parabricks arguments are outside the fixed profile contract'
    }
    if (params.images.values().any { !(it.startsWith('sha256:') || it.contains('@sha256:')) }) {
        error 'Harako-native images must use immutable execution references'
    }

    reads = Channel.fromPath(params.input, checkIfExists: true)
        .splitCsv(header: true)
        .map { row -> tuple(row.sample, file(row.fastq_1), file(row.fastq_2)) }

    preprocessed = PREPROCESS(reads)
    aligned = ALIGN_PARABRICKS(
        preprocessed.reads,
        file(params.fasta, checkIfExists: true),
        file(params.star_index, checkIfExists: true),
    )
    QC_REPORT(aligned.outputs, preprocessed.reports, file(params.gtf, checkIfExists: true))
}
