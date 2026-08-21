include { PARABRICKS_RNA_FQ2BAM } from '../modules/local/parabricks_rna_fq2bam'
include { PUBLISH_ALIGNMENT_CONTRACT } from '../modules/local/publish_alignment_contract'

workflow ALIGN_PARABRICKS {
    take:
    reads
    fasta
    star_index
    main:
    PARABRICKS_RNA_FQ2BAM(reads, fasta, star_index)
    PUBLISH_ALIGNMENT_CONTRACT(PARABRICKS_RNA_FQ2BAM.out.alignment)
    emit:
    outputs = PUBLISH_ALIGNMENT_CONTRACT.out.published
}
