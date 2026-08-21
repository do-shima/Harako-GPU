# Sanitized support bundle

`support-bundle create` writes a ZIP under the run's `support/` directory. It
contains run/status, frozen contracts and structured commands, hardware and
version evidence, pipeline/patch identities, attempt/controller/Nextflow logs,
trace, bounded failed-task evidence, artifact verification, and a manifest with
SHA-256 for every entry.

FASTQ, FASTA/GTF bodies, indices, BAM/BAI, quant.sf, large matrices, images,
tokens, credentials, Docker auth, and raw biological data are excluded.
Absolute home/run/work/reference/input paths and usernames are replaced with
role labels such as `<HOME>`, `<RUN_DIR>`, and `<INPUT_1_FASTQ_1>`; no reverse
mapping is included.

GUI bundle creation calls this same service. The browser receives only the
resulting role/path; it does not assemble archives, inspect credentials, or add
biological artifacts.
