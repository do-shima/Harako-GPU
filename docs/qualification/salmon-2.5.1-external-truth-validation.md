# Salmon 2.5.1 external truth validation

## Completion classification

`HARAKO_GPU_SALMON_2_5_1_EXTERNAL_TRUTH_VALIDATION_BLOCKED`

The repository start gate passed, but the preregistered SIRV transcript
correlation gate cannot be evaluated with the mandated E0 source. Primary
quantification stopped before index construction.

## Candidate identity

Salmon 2.5.1 remains the pinned, non-default Rust candidate using deterministic
FASTQ mapping, serial decoder, six threads, and local image ID
`sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f`.
The local image exactly matched the existing manifest.

## External preregistration

Dataset selection, preprocessing policy, primary subsets, thresholds,
exclusions, and cross-mapping limits were frozen before primary quantification.
The preregistration then invalidated itself when official E0 truth was found to
have zero variance. No result-driven accession, mix, subset, or threshold
change was made. Its file SHA-256 is
`5ba814f25ce1bb1ab872a3649761f87bcb593af7797458b378933d8015c22077`.

## SIRV source, mix, and index

`SRR3497201` is unambiguously SIRV E0 batch `216652830`; the publication and
Lexogen download page agree. The batch amendment and corrected annotation
exclude fragmented SIRV502. ENA split files were downloaded to WSL ext4 and
passed MD5, gzip, and paired-count checks. They contain 1,297,881 pairs plus
98,365 separately represented singleton spots.

The E0 truth vector is equal-molar. Pearson and Spearman correlations against
expected transcript concentration are therefore undefined. The SIRV index,
repeats, transcript accuracy, gene accuracy, and equivalence-group accuracy
were not run after that pre-result blocker.

## ERCC/SEQC selection and truth

Pure Samples E/F are unambiguous. Two BGI HiSeq 2000 lanes from the same
library and flowcell were selected per mix. The official Thermo Fisher table
has all 92 IDs and all four ratio groups. Because full qualification already
could not complete, ERCC FASTQ acquisition, index, repeats, concentration,
fold-change, lane repeatability, and cross-mapping were not run.

## Tests and scope

Tracked code adds deterministic metadata selection, exact official ERCC table
validation, upper-quartile isolation, fail-closed zero-variance correlation,
abundance/fold-change metrics, exact-repeat checks, cross-mapping boundaries,
and download allowlisting. Internal truth and WT_REP1 qualification remain
unchanged. External accuracy, full human transcriptome, default adoption,
production, and diagnostic use remain unqualified.

## Recommended next goal

Pre-register a SIRV E1/E2 public run whose mix and lot can be independently
proven, or explicitly authorize an E0-specific gate that uses detection and
scale-normalized abundance error without a correlation statistic. Only after
that contract is fixed should the selected ERCC lanes and external runtime
matrix be executed.

## Historical follow-up

This v1 result remains immutable. A separate prospective v2 preregistration
authorized E0 equal-molar metrics and completed runtime evaluation. It did not
rewrite this blocker: the v2 candidate failed its frozen SIRV
equivalence-group and Mix 2 cross-mapping gates. See
`salmon-2.5.1-external-truth-validation-v2.md`.
