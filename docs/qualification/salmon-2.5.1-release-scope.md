# Salmon 2.5.1 release-scope audit

This audit fixes upstream context for the qualification-only Rust candidate. It
does not treat release notes as local qualification evidence.

- Salmon 2.2 introduced FASTQ `--deterministic` by mapping once to an
  intermediate RAD and requantifying with order-independent accumulation.
- Salmon 2.4.1 fixed a RAD-reader race that could silently leave
  `num_processed` short or produce an empty/partial `quant.sf`. The affected
  paths explicitly include `--deterministic`.
- Salmon 2.5.0 added adaptive thread scheduling and correctness hardening. Its
  release note says fixed-thread serial-decoder output is byte-identical to
  2.4.1, while cross-thread internal values may differ below output precision.
- The official 2.5.1 release page identifies tag `v2.5.1` and commit
  `c360459bbf16e649a5c10c097e59f3c72e6b2e3c`. That commit changes workspace
  version metadata only. The supplied assertion about a structurally bounded
  worker pool is therefore not promoted to a verified release-note fact.

Primary sources:

- <https://github.com/COMBINE-lab/salmon/releases/tag/v2.2.0>
- <https://github.com/COMBINE-lab/salmon/releases/tag/v2.4.1>
- <https://github.com/COMBINE-lab/salmon/releases/tag/v2.5.0>
- <https://github.com/COMBINE-lab/salmon/releases/tag/v2.5.1>
- <https://github.com/COMBINE-lab/salmon/commit/c360459bbf16e649a5c10c097e59f3c72e6b2e3c>

Local checks used the exact 2.5.1 binary, `--deterministic`, `--decoder
serial`, absolute input-fragment accounting, 50 fresh repeats, a cross-thread
matrix, and an independent truth fixture. Those checks—not the upstream
claims—determine the rejection recorded in the qualification report.
