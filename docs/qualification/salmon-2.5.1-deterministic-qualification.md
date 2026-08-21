# Salmon 2.5.1 deterministic qualification

> Historical decision revised: this document preserves the original
> pre-remediation rejection. The subsequent truth-v2 audit reproduced 19.4%,
> identified exact-tie contamination, retained the 1% identifiable-decoy gate,
> and passed internal truth plus conditional nf-core integration. Current
> status is `HARAKO_GPU_SALMON_2_5_1_TECHNICALLY_QUALIFIED_EXTERNAL_TRUTH_REQUIRED`.
> See `expression-truth-decoy-accounting-remediation.md`.

## Completion classification

`HARAKO_GPU_SALMON_2_5_1_CANDIDATE_REJECTED`

The candidate passed supply-chain, exact reproducibility, cross-thread, and
absolute fragment-accounting gates. It failed the predeclared truth decoy
leakage ceiling: 19.4% observed versus at most 1%. Thresholds were not changed,
outputs were not rounded, and no failed run was excluded.

## Repository and commits

The work started from `60d3f8a5b393f2c5312f0512eae4674b26800840`, equal to
`origin/main`, on `test/salmon-2.5.1-deterministic-qualification`. Required
ancestor `d758fb43f466c9535db71643bad08225769cdf7a` was present and the baseline
suite passed 127 tests.

## Salmon 2.5.1 identity and candidate container

- tag/source: `v2.5.1` / `c360459bbf16e649a5c10c097e59f3c72e6b2e3c`
- official Linux asset SHA-256:
  `6ad2a01b2022092f88f4c95601d19751e594dd3aa7be77ee7c11c1abf4842cbe`
- official source archive SHA-256:
  `6adde21a2baa6d0c3b8725e3180f7228b2c8a913668a81130990e6fb4dbd6036`
- local image: `harako-gpu/salmon:2.5.1-qualification`
- image ID/config digest: `sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f`
- runtime output: `salmon 2.5.1`; implementation: Rust; license:
  BSD-3-Clause; image size: 34,162,544 bytes

The image uses a digest-pinned minimal Debian base, verifies the official asset
during build, retains `ps`, defines no ENTRYPOINT, and was not pushed.

## Release scope and capabilities

The release-scope findings are in `salmon-2.5.1-release-scope.md`.
`--deterministic`, `--decoder serial`, `--geneMap`, `--libType ISR`, paired
FASTQ input, and the tximport-compatible quant columns were present and worked
together. Bias, sketch, alignment-BAM, auto-library, free-form options, and
silent online fallback were not used.
The optional online diagnostic profile was not needed for the rejection and was
not run; no online result contributes to any gate.

## Version-specific index and command identity

The public-fixture PISCEM/cf1-rs k=31 index was built by the exact candidate
image from the same transcript/genome/gentrome/decoy sources. It contains 11
files, occupies 6,017,712 bytes, and has index ID
`60a4f66452d40b59c06125219a4a0f6894a9d6f5908d58af39731cd821152751`.
The contract rejects every 1.x/2.x version-index mismatch.

The fixed argv is `salmon quant --deterministic --decoder serial --geneMap
<gtf> --threads 6 --libType ISR --index <2.5.1-index> -1 <R1> -2 <R2> -o
<output>`. It is stored as structured argv and has no arbitrary extension.

## Public fixture and deterministic reproducibility

WT_REP1 processed exactly 47,605 fragments and mapped 37,397 (78.556874%).
All 50 fresh six-thread runs exited successfully. Every `quant.sf` had SHA-256
`44020ba1bc41c8d395fb41be44796c9e0877a42153101845e6060a3a3fd5c31c`;
every `quant.genes.sf` had SHA-256
`1afc1dec894c028120da4f47ebaf19e0b5d93e1a010e215a4d0dc8f72429f332`.
Scientific metadata and canonical numerical digests were exact, with no partial
RAD signature.

The 1/2/4/6-thread matrix ran five fresh executions per thread. All 20
transcript and gene outputs were byte-identical to the 50-run identity. This
exact result is local evidence; it is not generalized beyond this fixture.

## Truth fixture, fragment accounting, and accuracy

`harako_truth_bulk_v1` is described separately. All six 2.5.1 runs processed
exactly 50,000 fragments; mapped fragments ranged from 49,593 to 49,604, and
estimated mass matched `num_mapped` within serialization precision.

- identifiable transcript feature/sample pairs: 72; Pearson/Spearman 1.0;
  median/p95 APE 0%
- expressed non-paralog gene feature/sample pairs: 120; Pearson/Spearman 1.0;
  median/p95 APE 0%
- ambiguous group maximum relative error: 0%
- true count >=50 zero transitions: 0
- zero-expression mass: 0.195576% of total estimated mass
- high-expression false positives: 0
- fold-change direction: 100%; log2FC RMSE 0; Spearman 1.0
- decoy-origin leakage: **19.4%**, exceeding the fixed **1%** ceiling

Exact reproducibility cannot override this scientific failure.

## Version comparison

Each version used its own index over the same truth sources. Salmon 1.10.3 had
29.9333% decoy leakage; Salmon 1.12.1 and 2.5.1 each had 19.4%. All three had
exact fragment accounting and passed the other truth metrics in this deliberately
simple fixture. Version agreement was not used as ground truth and does not
rescue the 2.5.1 failure.

## nf-core, tximport, MultiQC, and resume

Not run. The contract forbids emitting the exact nf-core override until direct
deterministic, thread, and truth gates all pass. Because truth failed, no
nf-core candidate run, tximport, MultiQC, five fresh pipelines, or resume was
attempted. This is a fail-closed result, not missing success evidence.

## Performance and resources

For the final BSD-labeled image, the 70 public repeat/thread tasks reported
0.00486–0.02885 s internal time (median 0.02492 s) and 58,660–114,712 KiB peak
RSS. The six final truth tasks reported 0.02365–0.02678 s (median 0.02477 s) and
112,312–122,628 KiB peak RSS. The truth 2.5.1 index was 1,293,662 bytes and all
generated fixture files totaled 16,998,253 bytes. Container-launch overhead is
excluded and no full-size performance inference is made.

## Code, tests, and qualified scope

Tracked code adds pinned 2.5.1 supply-chain/index/argv contracts, exact-run and
truth gate models, a standard-library truth generator, non-executing summary
tooling, container recipe/manifest, and focused tests. Runtime biological and
quantification artifacts remain outside Git.

Qualified: official/local identity, public-fixture 50-run exactness,
cross-thread byte identity, absolute processed-fragment accounting, and the
truth generator's deterministic identity. Unqualified: scientific adoption,
nf-core integration, tximport, MultiQC, resume, default status, full-size,
production, diagnostic, and clinical use.

## Adoption decision and recommended next goal

The 2.5.1 profile remains `qualification_only`; it is not added to the product
plan and the default Salmon version is unchanged. Before testing another
backend, independently confirm the intended decoy-best accounting semantics
with an external truth dataset and an upstream-informed decoy fixture. A next
goal should be `HARAKO_GPU_EXPRESSION_TRUTH_AND_DECOY_ACCOUNTING_REMEDIATION`.

Subsequent truth-v2 remediation qualified the internal candidate, but the first
external-truth preregistration stopped before primary quantification. Its fixed
SIRV E0 truth vector is constant, so the mandated transcript Pearson/Spearman
gates are undefined. See `salmon-2.5.1-external-truth-validation.md`; this does
not alter the historical result recorded above.

External preregistration v2 then used prospective E0 equal-molar gates while
preserving v1. Exact external reproducibility, SIRV transcript/gene, and ERCC
accuracy passed, but SIRV equivalence-group and Mix 2 cross-mapping gates
failed. See `salmon-2.5.1-external-truth-validation-v2.md`. The candidate is
not externally qualified or default-adoptable.

Subsequent cause isolation retained that FAIL but found no 2.5.1-specific
algorithm defect. A later, explicitly versioned product decision therefore
made this exact deterministic backend the recommendation for *new internal
research analysis series*. Historical external evidence remains visible;
production, diagnostic, clinical, and full-size-human claims remain
unqualified, and existing series are never upgraded automatically.
