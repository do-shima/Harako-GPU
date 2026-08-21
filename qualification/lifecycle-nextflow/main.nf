nextflow.enable.dsl = 2

process PREPARE_TOKEN {
    output:
    path 'token.txt'

    script:
    """
    printf 'fixed-lifecycle-token\n' > token.txt
    """
}

process FAIL_ONCE {
    input:
    path token

    output:
    path 'completed.txt'

    script:
    """
    if [[ ! -f '${params.sentinel}' ]]; then
        touch '${params.sentinel}'
        exit 42
    fi
    cp token.txt completed.txt
    """
}

workflow {
    token = PREPARE_TOKEN()
    FAIL_ONCE(token)
}
