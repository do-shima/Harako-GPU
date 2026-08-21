# Artifact discovery and verification

Discovery uses mode-, sample-, stage-, and profile-specific exact paths; it
does not register the first recursive-glob match. Ambiguous/missing paths fail.
The manifest records role, profile, sample, relative path, size, source stage,
required/state, structural/scientific validation, checksum status, retention,
user visibility, and limitations.

Default verification parses Salmon transcript/gene tables and metadata,
checks finite values, fragment counts, explicit library type, version,
image/index/command/input identity, validates four-column STAR counts and
selected-column provenance, checks matrix order/values, self-contained HTML,
and validates BAM/BAI with pinned-container samtools quickcheck, header,
checksum, flagstat, and idxstats. `--deep` additionally hashes every selected
artifact, including BAM, with interruptible progress; a partial digest is never
complete. BAM deletion is not implemented. A discard-after-validation plan
would remain `RETENTION_PENDING`.

Capacity qualification retains source/subset FASTQs, references, indices,
failed Nextflow work, and partial results because deletion semantics are a
separate goal. A C1 failure before BAM/quantification does not create
placeholders and does not mark expected BAM, STAR GeneCounts, Salmon matrices,
or reports valid. Reference/index manifests are preparation evidence, not
scientific run artifacts.
In `fastq_quantification_only`, BAM, BAI, STAR logs, junctions, GeneCounts, and
alignment MultiQC are `NOT_APPLICABLE`, never `MISSING`. Processed FASTQ, fastp
JSON/HTML/command provenance, quantification outputs, matrices, and the report
are required.

The GUI lists the manifest and previews only bounded matrix rows/columns. It
serves only registered small text/report roles inside the run root, rejects
symlink escape and size overflow, and never loads BAM, index, or FASTQ into the
browser.
