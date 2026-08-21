# Third-party notices

Harako-GPU is source-available under the PolyForm Noncommercial License 1.0.0.
That license applies to Harako-GPU source; it does not relicense third-party
software, containers, references, indices, or biological data. This repository
does not bundle container layers, plugin binaries, references, indices, FASTQ,
BAM, or other scientific runtime assets.

The repository includes a minimal compatibility patch against
`nf-core/rnaseq` 3.26.0, commit
`e7ca46272c8f9d5ceee3f71759f4ba551d3217a4`. The patched upstream files are
copyright the nf-core/rnaseq team and provided under the MIT License. The patch
contains only the context required to move the Parabricks generic logfile and
publish it separately; it does not redistribute the pipeline or containers.
The upstream MIT license and notices continue to apply.

## Python dependencies

- Typer and Streamlit are runtime Python dependencies under their own licenses.
- pytest, Playwright, and Hatchling are development/build dependencies under
  their own licenses.

## External tools and content

- The selected vendored nf-core/modules snapshots retain their upstream source
  path, revision, and notices in `pipelines/harako-native-v1/README.md`.
- nf-core/rnaseq 3.26.0 and its transitive tools/containers retain their own licenses and notices.
- Nextflow retains its own license and notices.
- NVIDIA Parabricks and NGC content are governed by NVIDIA's applicable terms.
- Docker/Docker Desktop and the NVIDIA container runtime retain their own terms.
- STAR, Salmon, samtools, MultiQC, reference FASTA/GTF, and any input data retain their own licenses, attribution, and data-use requirements.

## Salmon 1.12.1 qualification definition

`containers/salmon-1.12.1-qualification/Dockerfile` downloads but does not
redistribute the official COMBINE-lab Salmon `v1.12.1` x86_64 release asset,
verifies its SHA-256, and records the upstream GPL-3.0-only notice. It also
verifies and extracts Debian's `locales-all` package for the `en_US.UTF-8`
runtime data required by that binary; Debian/glibc copyright and license terms
continue to apply. Neither asset, the built image, nor an index is committed or
published. This definition is qualification-only and the candidate was not
adopted.

## Salmon 2.5.1 qualification definition

`containers/salmon-2.5.1-qualification/Dockerfile` downloads but does not
redistribute the official COMBINE-lab Salmon `v2.5.1` x86_64 release asset. The
asset and source archive checksums are pinned in the adjacent manifest. The
official 2.5.1 source archive identifies this Rust line as BSD-3-Clause. The
local candidate image and downloaded archives are runtime-only and are not
published by this repository.

## External truth qualification data

SIRV sequences, annotations, concentration/design tables, and amendments remain
Lexogen assets. ERCC sequences and concentration tables remain Thermo Fisher
assets. SRA/ENA FASTQ files retain their submitter/archive terms. Qualification
stores these assets only under the untracked runtime root and records checksums
and citations; this repository does not redistribute them.

## NVIDIA Parabricks

Harako-GPU does not redistribute NVIDIA Parabricks. Users obtain Parabricks
4.6.0-1 from official NVIDIA NGC and must review and satisfy NVIDIA's terms
independently. Harako-GPU does not accept those terms, perform NGC login, or
grant any NVIDIA or other third-party rights. Image identities and offline
archive receipts in product contracts are verification metadata, not the image
itself and not permission to redistribute it.

Reference packs, genome annotations, indices, SRA/ENA data, and other public or
private inputs retain their separate licenses and data-use conditions. Nothing
in the Harako-GPU license grants rights to those assets.
