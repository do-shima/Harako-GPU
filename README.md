# Harako-GPU

Harako-GPU is a local, single-user, GPU-assisted RNA-seq workflow for producing
versioned BAM, junction, STAR GeneCounts, FeatureCounts QC, Salmon abundance,
matrices, MultiQC, and verification records through one GUI and CLI contract.
Nextflow remains the execution engine; Harako freezes planning, execution,
artifact, and provenance identities before a run starts.

## Public alpha warning

This repository is preparing **v0.1.0-alpha.1**, a public research alpha. It is
source-available for permitted noncommercial use, has a narrow qualification
boundary, and is not for diagnostic or clinical use. Do not treat qualification
on one fixed host, reference, and public input as general hardware, biological,
or production validation. See [PUBLIC_ALPHA.md](PUBLIC_ALPHA.md).

## Current supported environment

The qualified native route is Ubuntu 24.04 on the fixed
`ubuntu_native_rtx3090_ram128_v1` class: NVIDIA GeForce RTX 3090 (24 GiB
VRAM), 128 GB physical RAM, Docker Engine with NVIDIA Container Toolkit, Java
17+, Nextflow 25.04.3, and local ext4 SSD active storage. Availability also
requires the exact installed host receipt, offline image provenance, reference
pack, STAR index, and selected Salmon index. RAM or GPU detection alone never
qualifies a host.

Windows with WSL2 remains a supported planning and reference-backend path, but
the 64 GB WSL host profile is not qualified for full-human BAM generation.
Native Windows paths are never interpreted as native Linux paths.

## Harako-native workflow

The default for a receipt-backed qualified Ubuntu host is
`harako_native_v1`:

```text
FASTQ -> fastp -> Parabricks STAR -> BAM / junction / GeneCounts
                                     + FeatureCounts QC / MultiQC
                                     + versioned Salmon -> matrices / concordance
```

One-pass uses the fixed 42.GB / 12-CPU contract. Two-pass uses the fixed 96.GB
/ 12-CPU contract. CPU STAR is unavailable, and there is no silent fallback.
The full nf-core/rnaseq 3.26 reference backend remains available as an expert
comparison path.

## CPU Harako-RNAseq vs Harako-GPU

[Harako-RNAseq](https://do-shima.github.io/harako-rnaseq/) is the general
Salmon/tximport/DESeq2 workflow for broader Windows and Linux access.
Harako-GPU is the GPU-assisted BAM, junction, and GeneCounts workflow for a
narrow qualified Ubuntu/NVIDIA host class. Harako-GPU does not supersede the
CPU version, and no matched CPU/GPU speedup ratio is claimed because the two
products perform different workflows.

## Installation overview

Clone the source, create a Python 3.11+ virtual environment, and install the
package. Runtime assets are provisioned separately and are never bundled:

```bash
git clone https://github.com/do-shima/Harako-GPU.git
cd Harako-GPU
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
harako-gpu doctor --json
```

Users must obtain NVIDIA Parabricks 4.6.0-1 from official NVIDIA NGC under
NVIDIA's terms. Harako-GPU neither redistributes it nor accepts terms, logs in,
pulls images, or builds reference/index assets during planning. Follow the
[alpha installation guide](site/installation/index.html) for the exact tested,
candidate, and unsupported boundaries.

## Quick start

Inspect the public CLI before creating a non-executing immutable plan:

```bash
harako-gpu --version
harako-gpu doctor --json
harako-gpu profiles list --json
harako-gpu plan create --help
harako-gpu ui --no-browser
```

The lifecycle is explicit: validate inputs and assets, create and review a
plan, prepare, start, observe status, resume only when eligible, verify
artifacts, and create a sanitized support bundle. Plan review and approval are
required; preparation never automatically starts scientific work.

## Reproducibility and version pinning

Each Run freezes the workflow backend, alignment profile, resource contract,
reference/index identities, runtime images, Salmon profile, processed-FASTQ
contract, output contract, execution context, and approval hash. Historical
plans without `workflow_backend` remain the nf-core reference backend.
Cross-version analysis series must not be merged silently.

## Salmon profiles

- Salmon 2.5.1 is the deterministic default for new series.
- Salmon 1.10.3 remains visible and executable as a bounded-numerical
  compatibility profile.
- Compare-both runs the two profiles sequentially against the same processed
  FASTQ and reports timing and concordance without calling either version
  universally correct.

The C1 comparison had `n=2`; it describes method/version sensitivity, not
biological truth. The selected version, image, index, options, library type,
and six-thread contract are frozen per Run.

## Outputs

Fixed outputs include processed FASTQ, BAM/BAI, junction tables, STAR
GeneCounts, FeatureCounts biotype QC, Salmon `quant.sf` and `quant.genes.sf`,
transcript/gene matrices, concordance, MultiQC, Nextflow reports, a
backend-neutral output manifest, deep verification evidence, and a sanitized
support bundle. Successful terminal results may be archived under
`harako-gpu-terminal-results-archive-v1`; automatic archive or deletion is not
implemented.

## Limitations

- Public research alpha; research use only, non-diagnostic, and non-clinical.
- Qualified only for the exact Ubuntu RTX 3090 / 128 GB host receipt and fixed
  GRCh38.p14 / GENCODE 49 assets.
- No CPU STAR, DESeq2, arbitrary custom-reference qualification, or matched CPU
  speed benchmark.
- Cross-host BAM equality and biological truth were not evaluated.
- Ubuntu scientific GUI execution passed AppTest and HTTP qualification; an
  actual Ubuntu browser runtime was unavailable during qualification.
- Active work must remain on local ext4 SSD, not WD Gold, SMB/CIFS, NFS, NTFS,
  `/mnt/c`, or `/mnt/d`.

## Licensing and third-party terms

Harako-GPU source is available under the
[PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use requires
separate permission; see [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md).
Parabricks, Nextflow, nf-core, containers, reference/index assets, and public
biological data retain their own licenses and terms. No third-party rights are
granted by Harako-GPU. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Citation

Use [CITATION.cff](CITATION.cff) for the software citation and cite the
underlying tools and reference resources separately. A formal archived release
identifier does not exist until the maintainer publishes the release.

## Development and tests

```bash
python -m pip install -e ".[test]"
python -m pytest -ra -rs
python -m pip check
python -m compileall -q src tests scripts
```

Contributions must preserve the fail-closed path, identity, no-fallback, and
scientific safety contracts in [AGENTS.md](AGENTS.md). Do not attach FASTQ,
BAM, indices, references, credentials, or unredacted support bundles to issues.

## Detailed qualification links

- [Ubuntu high-memory one-pass](docs/qualification/native-high-memory-full-human-one-pass.md)
- [Ubuntu high-memory two-pass](docs/qualification/native-high-memory-full-human-two-pass.md)
- [Harako-native vs nf-core C1 parity](docs/qualification/harako-native-vs-nfcore-c1-parity.md)
- [Salmon 1.10.3 vs 2.5.1 C1 comparison](docs/qualification/salmon-1.10.3-vs-2.5.1-c1-comparison.md)
- [Ubuntu native GUI qualification](docs/qualification/ubuntu-native-gui-scientific-launch.md)
- [Qualification history](docs/history/qualification-history.md)
