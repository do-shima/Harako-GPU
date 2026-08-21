# Salmon 2.5.1 qualification container

This local-only image packages the official Salmon `v2.5.1` Rust x86_64
binary for deterministic qualification. It is not a product default and must
not be pushed.

The final stage uses digest-pinned Debian 12.11 slim. A digest-pinned existing
runtime image is used only as a download/extraction stage; the final image
copies the verified Salmon directory and `ps`, which Nextflow uses for task
metrics. It defines no entrypoint, so Nextflow can run its generated shell
command normally.

The build fails closed unless the asset SHA-256 and `salmon 2.5.1` version
output match. The source archive is independently downloaded and verified by
the qualification harness; neither archive is committed. The official 2.5.1
source archive identifies this Rust line as BSD-3-Clause, which is also the OCI
license label in the final image.

Local tag: `harako-gpu/salmon:2.5.1-qualification`.

Runtime binary, index, FASTQ, RAD, BAM, and quantification outputs remain under
the WSL runtime root and are not repository artifacts.
