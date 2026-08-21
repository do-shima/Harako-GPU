process FASTP {
    tag "$sample"
    container params.images.fastp
    publishDir "${params.outdir}/preprocessing/fastp", mode: 'copy', overwrite: false

    input:
    tuple val(sample), path(r1), path(r2)

    output:
    tuple val(sample), path("${sample}_R1.fastp.fastq.gz"), path("${sample}_R2.fastp.fastq.gz"), emit: reads
    tuple val(sample), path("${sample}.fastp.json"), path("${sample}.fastp.html"), path("${sample}.command.json"), emit: reports

    script:
    """
    fastp \\
      --in1 ${r1} --in2 ${r2} \\
      --out1 ${sample}_R1.fastp.fastq.gz \\
      --out2 ${sample}_R2.fastp.fastq.gz \\
      --json ${sample}.fastp.json --html ${sample}.fastp.html \\
      --thread 6 --detect_adapter_for_pe
    printf '%s\n' '{"schema_version":1,"contract_id":"harako-fastp-1.0.1-fixed-v1","threads":6,"structured":true}' > ${sample}.command.json
    """
}
