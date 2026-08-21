# Salmon 1.12.1 upgrade qualification

## Completion classification

`HARAKO_GPU_SALMON_2X_QUALIFICATION_REQUIRED`

Salmon 1.12.1 did not pass the predeclared six-thread numerical or fragment
identity gates. Thresholds were not relaxed and outputs were not rounded. The
candidate remains non-default and no nf-core candidate run was authorized by
the experiment-A/B gate.

## Repository and commits

The audit started from `origin/main` at
`454e62e81fc4097c2d59b6c530efe1e66d75abd6`; required ancestor
`08ceaf5ccd64c0d9b7427c4451bc0a1d9c025b5e` and the 116-test baseline were
confirmed before work. Work was isolated on
`test/salmon-1.12.1-upgrade-qualification`.

## Salmon 1.12.1 identity

- Official tag: `v1.12.1`
- Source commit: `971a2ad6e86cc32315d919faed0be0e88d36c9e5`
- Asset: `salmon-linux-x86_64.tar.gz`, 5,319,100 bytes
- Asset SHA-256: `00900135ecca10b45e3d78a6ab64463f957d0b2b0069eaa078c10784f1e2f8d6`
- Runtime output: `salmon 1.12.1`
- Implementation: legacy C++ 1.x qualification candidate

The release API tag object was followed to the exact source commit and the
downloaded runtime asset independently matched its pinned SHA-256.

## Candidate container

The local-only image is based on the exact 1.10.3 digest
`sha256:f83ebb15...f08e`, retains `/usr/local/bin/salmon` 1.10.3, and installs
the candidate under `/opt/salmon-1.12.1`. The official binary requires
`en_US.UTF-8`; a SHA-pinned Debian 12 locale payload matching glibc 2.36 was
added after the first index attempt failed closed at locale initialization.
Partial failed indices were not reused.

- Local tag: `harako-gpu/salmon:1.12.1-qualification`
- Local image ID: `sha256:88b88863...d81dd`
- Config digest: `sha256:c57bb5eb...b749`
- Size: 136,369,022 bytes
- Dockerfile SHA-256: `bc7dd012...ef59e`
- Published: no

Full construction identity is in the candidate container manifest.

## Release-note scope

SSHash orientation, deterministic offline reduction/uniform initialization,
selective-alignment changes, decoy attribution, and newly enforced
`maxReadOcc` are directly relevant. `--seqBias`, `--posBias`, alignment-mode
mate pairing, mapping-output flush, and the `--writeMappings`+`--gcBias` fix
were not exercised because their options/mode are absent. See the separate
release-scope audit.

## Candidate capabilities

`salmon quant --help`, `--help-reads`, and `salmon index --help` were captured
from the candidate image. The fixed mapping argv and `--geneMap` remain
supported; `quant.sf` retains the five expected columns and `quant.genes.sf`,
`meta_info.json`, and `lib_format_counts.json` were produced. Neither a
`--deterministic` option nor a random-seed option is exposed. `--seqBias`,
`--gcBias`, and `--posBias` exist but remain disabled.

## Version-specific index

The existing 1.10.3 index was not reused. A fresh 1.12.1 decoy-aware gentrome
index was built with six threads and k=31 from the same reference sources.

- Candidate index ID: `7e64ba84894294a0c3a46d2fab44deefa657a27839cd5fb706c7d8c4f072cd55`
- Index inventory SHA-256: `7de7129ef6e61ef6142bcd4df22d74969c1cf2c81cae01e220c4331d7c56e16f`
- Inventory: 12 files, 301,444 bytes
- Transcript FASTA SHA-256: `4f6a6733...3ac3`
- Genome FASTA SHA-256: `df709738...58e1`
- Gentrome SHA-256: `8e0b5df1...802`
- Decoys SHA-256: `7fdca686...fed7`
- Build wall time: 0.47 s for the small fixture

The product contract rejects either version paired with the other version's
index; compatibility is not inferred from internal sequence hashes.

## Command identity

The candidate command exactly preserved the current option meaning:

```text
salmon quant --geneMap <gtf> --threads 6 --libType=ISR
--index <1.12.1-index> -1 <processed-R1> -2 <processed-R2> -o <output>
```

No bias option, validation option, deterministic option, seed, alignment input,
free-form argument, or shell evaluation was added.

## Salmon 1.10.3 baseline

Three additional runs used the same processed FASTQ and 1.10.3 index. All had
47,605 processed and 37,586 mapped fragments, exact NumReads, unchanged zero
state, and Spearman 1.0. The maximum TPM>=1 relative difference was 0.799% and
EffectiveLength maximum difference was 0.064. This reproduces the existing
classification of 1.10.3 as materially variable rather than contradicting it.

## Frozen FASTQ repeats

Ten 1.12.1 runs used identical input/index/container/argv and all exited zero.
Processed fragments stayed 47,605, but mapped fragments varied between 5,818
and 5,831. Relative to run 1:

- EffectiveLength maximum absolute difference: 0.194
- transcript TPM>=1 maximum relative difference: 3.7595%
- gene TPM>=1 maximum relative difference: 3.7592%
- NumReads maximum absolute difference: 10
- zero/non-zero transitions: 0
- transcript/gene Spearman: 1.0

Fragment-count exactness, the 0.1 EffectiveLength ceiling, and the 0.1% TPM
ceiling all failed. Repeated identical SHA values occurred for some runs, but
the set was not reproducible.

## Thread matrix

Three repeats each were run at 1, 2, 4, and 6 threads. Mapped fragments were
5,854, 5,853, 5,810, and 5,818 respectively for the compared runs. Four-thread
outputs happened to be exact in three repeats; one- and two-thread sets mixed
exact and material results; six-thread repeats remained material with maximum
EffectiveLength difference 0.252 and TPM>=1 relative difference 0.960%.
Across one representative run per thread, maximum TPM>=1 relative difference
was 11.31%, maximum EffectiveLength difference was 0.593, and maximum NumReads
difference was 38. Thread-dependent fragment accounting is therefore material.

## Fresh pipeline repeats

`NOT_RUN`. Experiment A and the six-thread part of experiment B failed their
fixed gates. Per the fail-closed decision order, candidate integration and five
fresh full pipelines were not started. Existing Parabricks work and biological
artifacts were not changed.

## Version-to-version comparison

The comparison used the same processed FASTQ and reference source but separate
version-built indices, so it is not called a version-only comparison.

- processed fragments: 47,605 for both
- mapped fragments: 37,586 (1.10.3) versus 5,818 (1.12.1)
- mapping-rate absolute difference: 66.7325 percentage points
- transcript/gene ID sets: identical
- transcript/gene Spearman: 0.619585
- transcript/gene zero/non-zero transitions: 33
- output schemas: compatible; no negative/non-finite values

The 2-point mapping-rate and 0.995 correlation gates failed by a wide margin.
This result does not prove either version scientifically superior; it requires
a broader truth-based/version-line qualification.

## Release-fix targeted checks

The 1.12.1 index reports the expected SSHash metadata and shares transcript
sequence/name hashes with the 1.10.3 reference identity. The mapping result
changed materially after exercising the corrected mapping line. Attribution to
one upstream fix is not claimed. Bias and alignment-mode fixes are recorded as
not exercised/not applicable, not as passing.

## nf-core candidate integration

`NOT_RUN`. The exact selectors were audited as
`NFCORE_RNASEQ:PREPARE_GENOME:SALMON_INDEX` and
`NFCORE_RNASEQ:RNASEQ:QUANTIFY_PSEUDO_ALIGNMENT:SALMON_QUANT`; the BAM route
remains disabled. The code will refuse to emit the override unless candidate
status is `qualified_small_fixture`. No default or planning profile was
changed.

## tximport and MultiQC

Direct outputs passed strict `quant.sf` parsing and produced geneMap-derived
gene quantification and metadata. Actual nf-core tximport and MultiQC candidate
integration are `NOT_RUN` because the numerical precondition failed. They are
not reported as PASS and existing 1.10.3 results are not relabelled.

## Resume

`NOT_RUN`. No candidate Nextflow run existed to resume.

## Performance and resources

Candidate index build was 0.47 s for this tiny reference. Direct candidate
quantification wall time ranged from 0.96 to 1.01 s. `/usr/bin/time` wrapped
the Docker client (approximately 25 MiB peak), so it is not asserted as Salmon
container peak RSS. Full-pipeline and resume timings are not available. No
full-size performance inference is made.

## Code changes

The repository adds a qualification-only container definition and manifest, a
version/index fail-closed service, a non-executing artifact summarizer,
candidate/non-regression tests, and this evidence. The default 1.10.3 service,
plan, and nf-core configuration remain unchanged.

## Tests

Final code qualification records Python compilation, the full pytest suite,
architecture gates, candidate manifest/index/argv/comparator tests, CLI smoke,
and `git diff --check`. Runtime PASS is limited to identity, image/index build,
baseline capture, candidate direct execution, and evidence parsing. nf-core,
tximport, MultiQC, fresh-pipeline, and resume candidate gates are explicitly
`NOT_RUN` after the numerical stop condition.

## Qualified scope

Official asset/container identity, a version-specific small-reference index,
structured command compatibility, strict output parsing, and the fact that the
candidate fails the fixed numerical/non-regression gates are qualified.

## Unqualified scope

Salmon 1.12.1 as an expression backend, nf-core override, tximport, MultiQC,
resume, full-size data, production/diagnostic use, performance claims, default
adoption, and Salmon 2.x remain unqualified.

## Adoption decision

Candidate qualification: rejected. Default adoption: no change; Salmon 1.10.3
remains the declared default while expression execution stays unqualified.

## Remaining risks

The tiny decoy fixture is especially sensitive to corrected mapping behavior,
and no truth set establishes which mapping rate is scientifically preferable.
Salmon 1.12.1 also retains documented FLD-feedback variability. A larger,
truth-based evaluation is required before any backend adoption.

## Recommended next goal

`HARAKO_GPU_SALMON_2X_QUALIFICATION`: separately pin the official 2.x binary,
build its required new-format index, define an equivalent fixed command, and
evaluate truth-based accuracy plus the unchanged numerical ceiling. It must not
silently replace either 1.10.3 or this rejected candidate.

Follow-up result: Rust Salmon 2.5.1 resolved exact reproducibility on the public
fixture but failed the separate independent-truth decoy-leakage gate. This does
not revise the 1.12.1 rejection or establish a replacement backend.
