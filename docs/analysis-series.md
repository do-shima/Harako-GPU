# Immutable analysis series

Execution freezes the analysis-series payload under `frozen/analysis-series.json`
and binds its ID into `run.json`, tasks, artifacts, and concordance. Resume uses
that exact series. A completed run or profile/reference/library change creates
a new run/series; existing matrices are never overwritten or mixed.
An analysis series freezes project, primary/secondary profiles, mode, FASTA,
GTF, tx2gene, processed FASTQ, preprocessing, library type, image, index, and
structured-command identities. Its ID is a canonical digest of that contract,
not a digest of favorable output values.

Samples with different primary profiles, references, library types, or
preprocessing identities cannot be mixed. A profile change creates a new
series with `parent_series_id`; it never overwrites the original series or its
matrices. Only `downstream_primary_profile_id` is eligible for future
downstream analysis. Secondary and STAR artifacts cannot be promoted after
viewing results.

`alignment_profile_id`, two-pass state, annotation-backed state, limitations,
and qualification report are also canonical series/run/artifact provenance.
One-pass and two-pass outputs cannot share a series. Both full-human profiles
are currently host-memory-unqualified on the tested workstation.
Execution route and BAM output mode are immutable series identity. Changing from
GPU BAM alignment to FASTQ quantification-only, or the reverse, requires a new
analysis series; results are never mixed or overwritten.

GUI draft state is never series identity. Preparation delegates canonical
series creation to the existing service; editing a prepared draft requires a
new prepare and cannot modify or overwrite the frozen series.
