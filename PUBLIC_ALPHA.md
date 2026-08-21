# Harako-GPU v0.1.0-alpha.1 public research alpha scope

Status: **Public research alpha**. Harako-GPU is source-available software for
research use only. It is not production-ready and is not qualified for
diagnostic or clinical use.

## Supported host class

Scientific native launch is qualified only for the receipt-backed
`ubuntu_native_rtx3090_ram128_v1` host profile: Ubuntu 24.04, NVIDIA GeForce RTX
3090 with 24 GiB VRAM, 128 GB physical RAM, local ext4 SSD active storage,
Docker Engine plus NVIDIA Container Toolkit, Java 17+, and Nextflow 25.04.3.
Candidate hardware is not automatically qualified from RAM/GPU detection.

The Windows/WSL2 product path remains available for planning, inspection,
small/reference behavior, and the nf-core reference backend. Its fixed 64 GB
host profile is not qualified for full-human BAM generation.

## Qualified workflows and reference

- `harako_native_v1` one-pass Parabricks STAR with 42.GB and 12 CPUs.
- `harako_native_v1` two-pass Basic with 96.GB and 12 CPUs.
- The fixed full ERR188044 evidence and C1 strict parity evidence only.
- Reference pack `human_grch38p14_gencode49_harako_gpu_v1` (GRCh38.p14,
  GENCODE release 49), STAR index `star-2.7.2a-c15a9d6fe6df9716`, and
  version-specific Salmon indices.
- Salmon 2.5.1 deterministic default and Salmon 1.10.3 bounded-numerical
  compatibility profile.

The nf-core/rnaseq 3.26 backend remains an expert/reference option. Historical
plans that do not name a workflow backend retain that interpretation.

## Required images, indices, and receipts

The host qualification receipt, parity-report hashes, offline Parabricks
provenance, selected workflow image closure, reference/index manifests, and
local asset inventories must all validate before launch. Harako-GPU does not
bundle or redistribute Parabricks, container archives, plugin binaries,
references, indices, FASTQ, BAM, or other biological data. Users obtain and
license each third-party asset separately.

## Research-use and browser boundary

The GUI scientific lifecycle was qualified on Ubuntu through Streamlit AppTest,
HTTP loopback checks, and retained C1 one-pass/two-pass product runs. An actual
Ubuntu browser runtime was unavailable during that qualification. Windows Edge
browser regression is separate evidence and does not substitute for an Ubuntu
browser run.

## Unsupported or not qualified

- CPU STAR, arbitrary GPUs/hosts, 64 GB full-human BAM, and custom references.
- DESeq2 and biological interpretation.
- Matched CPU-versus-GPU speedup claims.
- Cross-host BAM equality, arbitrary FASTQ generality, and biological truth.
- Automatic archive/deletion, remote execution, a server/queue product, or WD
  Gold/network storage as an active work directory.
- Production, diagnostic, clinical, or regulated use.

## Installation and support expectations

Installation is operator-managed and requires Docker/NVIDIA, Java/Nextflow,
exact images, fixed assets, offline provenance, and an installed host receipt.
Harako-GPU never accepts NVIDIA terms or performs registry login for the user.
This alpha is provided without warranty. Support is best-effort through GitHub
Issues; never upload biological data, credentials, private paths, or complete
support bundles.

For details, see the [installation page](site/installation/index.html),
[product contract](docs/product-contract.md), and immutable
[qualification history](docs/history/qualification-history.md).
