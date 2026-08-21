# Source provenance

## Execution adapter implementation

The run lifecycle, JSON exec runner, atomic state/lock contract, fixed-stage
orchestration, artifact verifier, failed-task evidence collector, and sanitized
support bundle are Harako-GPU-local implementations. The pipeline snapshot is
nf-core/rnaseq 3.26.0 commit `e7ca46272c8f9d5ceee3f71759f4ba551d3217a4`;
the existing repository patch manifest remains the source of patch identity.
No Harako-RNAseq runtime code, submodule, arbitrary downloader, or external
workflow framework was introduced.
Source repository: `do-shima/harako-rnaseq`

Immutable source commit: `9d8628f48226c330e159ac79c14595f2cf65a551`

Handoff: `docs/refactor/gpu-handoff.md` at that commit.

The source was inspected read-only. Harako-GPU has no runtime dependency,
submodule, subtree, or editable install referring to it.

| Source path | Imported symbol(s) | Local target | Modified | Reason |
|---|---|---|---:|---|
| `app/core/fastq.py` | `FASTQ_EXTS`, `relative_path`, `normalize_input_path`, `split_fastq_name`, `split_read_suffix`, `read_side`, `is_r1`, `sample_base`, `infer_pair_candidates`, `read_counts` | `src/harako_gpu/core/fastq.py` | No behavioral change | Namespace/docstring only; pure naming and pairing rules retained. |
| `app/core/analysis.py` | `POLICY_VERSION`, `PLAN_SCHEMA_VERSION`, `AnalysisPlanError`, `AnalysisEligibility`, `evaluate_analysis_eligibility`, `analysis_plan_from_rows`, `assert_analysis_plan_consistent`, `resolve_analysis_plan` | `src/harako_gpu/core/analysis.py` | No behavioral change | Formatting condensed; policy version and scientific eligibility behavior retained. |
| `app/core/canonical.py` | `canonical_json`, `sha256_payload` | `src/harako_gpu/core/canonical.py` | No | Exact serialization and digest behavior. |
| `app/agent_contracts.py` | response envelope fields | `src/harako_gpu/core/provenance.py` | Namespace value only | Uses Harako-GPU version while retaining schema version and versioned response shape. |
| `app/agent_contracts.py` | plan/approval hash domain separation | `src/harako_gpu/core/provenance.py` | Yes | GPU execution payload is defined by `services/run_contract.py`; digest algorithm and `kind` strings remain compatible. |
| `app/services/agent_inputs.py` | sample columns and structural validation concepts | `src/harako_gpu/core/samples.py` | Yes | Fields renamed to the required v1 GPU sample schema and filesystem checks kept outside core. |
| `app/services/run_inspection.py` | `_artifact` response fields | `src/harako_gpu/core/artifacts.py::artifact_response` | Public name only | Output discovery was not ported; the pure response fields and existence behavior were retained. |

Equivalence fixtures live in `tests/fixtures/source_agent_plan_v1_legacy.json`
and `tests/test_source_port_equivalence.py`. They cover FASTQ parsing/read side,
pair candidates, analysis eligibility/plan, canonical JSON, plan ID, approval
hash, adapted sample structure, and artifact response fields.

Not ported: reference registry/cache resolver, run implementation, report shell,
Streamlit/editor/state/presentation, validation presentation, Snakefile,
Snakemake adapter, direct-Salmon rules, the old CLI tree, old Dockerfile,
release compatibility code, workflow runner, Nextflow execution, resume, output
discovery, or BAM deletion.

The transcriptome grouping contract, topology inspector, structured samtools
argv, and artifact-role distinction are new Harako-GPU implementations; no
additional Harako-RNAseq symbol was ported. Runtime tool behavior is attributed
to pinned samtools 1.23.1 and Salmon 1.10.3 images. The unexecuted mudskipper
reference is pinned to upstream tag v0.1.0 / commit
`59ba072bb5b4aff192557e1503fd82376562a2e2` and is not a runtime dependency.

The independent FASTQ Salmon contract is newly implemented. Harako-RNAseq
commit `9d8628f48226c330e159ac79c14595f2cf65a551` was re-inspected read-only at
`workflow/Snakefile` and `workflow/scripts/build_gentrome.py`: its Salmon 1.10.0
path uses fastp output, auto library detection, and a decoy-aware gentrome k=31
index. No source symbol was copied. The nf-core 3.26.0 implementation instead
fixes Salmon 1.10.3, ISR, geneMap, and the stock decoy-aware k=31 index, so
runtime parity is measured rather than inferred.

The Salmon 1.12.1 candidate contract, version/index coupling, release-scope
classification, and non-regression comparator are new Harako-GPU code. No
Harako-RNAseq symbol was copied and that repository was not changed. Runtime
identity comes from the official COMBINE-lab `v1.12.1` release at commit
`971a2ad6e86cc32315d919faed0be0e88d36c9e5`; the candidate container preserves
the pinned nf-core 1.10.3 base while installing the verified upstream asset.

The Salmon 2.5.1 candidate identity and release-scope statements come from the
official COMBINE-lab `v2.5.1` release at commit
`c360459bbf16e649a5c10c097e59f3c72e6b2e3c` and official 2.2.0, 2.4.1, and
2.5.0 notes. No Salmon source code was copied. `harako_truth_bulk_v1` is new
Harako-GPU standard-library generator code, not a Harako-RNAseq port.

`harako_truth_bulk_v2_decoy_stratified`, the identifiability oracle, leakage
audit, and truth comparison harness are also original Harako-GPU code. They
reuse only the tracked v1 sequence-design functions, do not use Salmon source
or scoring code, and never read Salmon output while assigning identifiability
classes. Harako-RNAseq was neither copied nor changed.

The external-truth selection and metrics are new Harako-GPU code. Dataset
identity comes from NCBI SRA/GEO and ENA metadata, the batch-specific SIRV
sequence/design assets and amendment come from Lexogen, and ERCC sequences and
concentrations come from Thermo Fisher. None of those vendor/data assets is
tracked or redistributed. No code was copied from SIRVsuite or Harako-RNAseq.

External validation v2 adds original standard-library reference preparation
and equimolar/ERCC evaluation scripts. GENCODE 49 transcript and GRCh38.p14
primary-assembly sources were downloaded from the official EBI GENCODE
release. Only checksums, identities, and summarized results are tracked; no
GENCODE, Lexogen, ENA FASTQ, index, or quantification artifact is redistributed.

Failure-cause isolation is original Harako-GPU qualification code. Held-out
run metadata and FASTQ checksums came from ENA; sequence classification used
minimap2 2.28-r1209 from pinned image digest
`sha256:0c397895db3b494baa4f78de7110d516a1a57707d9c7df456634220bffd965ba`.
No external read sequence or third-party implementation is included in Git.

The versioned profile catalog, immutable analysis-series model, GeneCounts
parser, concordance metrics, report renderer, and symmetric execution adapter
are original Harako-GPU code. No Harako-RNAseq code was copied or changed. The
STAR column semantics and output contract follow the pinned STAR lineage
exposed by nf-core/rnaseq 3.26.0 and local Parabricks 4.6.0-1 help. The audited
nf-core module/config git-blob identities are recorded in the STAR comparator
qualification report; no nf-core source is redistributed or modified.

The medium-human capacity source is official ENA run ERR188044 (PRJEB3366 /
ERX162864 / SAMEA1573216). Reference inputs are official GENCODE release 49
GRCh38.p14 primary-assembly genome, transcript FASTA, and GTF. Only identities,
checksums, inventories, and summarized qualification evidence are tracked;
FASTQ/reference/index/work artifacts are not redistributed. The deterministic
subsetter, capacity gates, estimator contract, monitoring extensions, and
qualification scripts are original Harako-GPU code. The one-line prebuilt STAR
index selection patch targets nf-core/rnaseq 3.26.0 commit
`e7ca46272c8f9d5ceee3f71759f4ba551d3217a4` and is accepted only against its
recorded source/patched SHA-256 values. Harako-RNAseq was not modified.

The alignment-profile catalog, one-pass resource gates, plan/run provenance,
and descriptive one-pass/two-pass comparator are original Harako-GPU code.
They reuse the pinned nf-core/rnaseq 3.26.0 and Parabricks 4.6.0-1 contracts;
no third-party source or biological runtime artifact is included. The
full-human one-pass run reused the existing ERR188044 subsets and GENCODE 49 /
GRCh38.p14 indices without modification. Harako-RNAseq was not changed.
The fixed Harako-managed fastp command is derived from this repository's retained
nf-core/rnaseq 3.26.0 WT/ERR188044 runtime task evidence, using fastp 1.0.1 image
identity `sha256:d228dace961ab50d04471e02e7fd2c8f2b8cd5b1b37be2d4039e2db64fcfae45`.
No code or command was copied from a newer Harako-RNAseq revision.
# Reference-aware GUI source audit

The GUI selectively adapts interaction concepts from read-only
`do-shima/harako-rnaseq` commit
`9d8628f48226c330e159ac79c14595f2cf65a551`. Exact source paths, concepts,
targets, and modifications are recorded in [GUI source provenance](gui-source-provenance.md).
No source directory, Snakemake runtime, scientific workflow, or runtime
dependency was imported.
