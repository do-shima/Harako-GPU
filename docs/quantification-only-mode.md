# FASTQ quantification-only mode

This fixed route is:

1. preflight and input validation
2. pinned fastp 1.0.1 paired-end preprocessing
3. processed-FASTQ validation
4. CPU Salmon primary and optional secondary profile, sequentially
5. profile-specific matrices and optional profile concordance
6. bilingual self-contained report and artifact verification

The fastp image is `community.wave.seqera.io/library/fastp:1.0.1--c8b87fe62dcc103c`
with identity `sha256:d228dace961ab50d04471e02e7fd2c8f2b8cd5b1b37be2d4039e2db64fcfae45`.
Its fixed paired command is derived from the qualified nf-core/rnaseq 3.26.0
runtime evidence: six threads, paired adapter detection, paired/unpaired failure
outputs, JSON, HTML, and deterministic artifact names. There are no arbitrary
fastp or Salmon arguments and no raw-read fallback.

This is CPU expression quantification. It is not GPU accelerated. It is for
internal research use only and is non-diagnostic and non-clinical.

The GUI report repeats that BAM, junction, and STAR GeneCounts were not
generated and that GPU was not used. Alignment roles are displayed as
`NOT_APPLICABLE`, not as failures or placeholders.
