# Salmon 1.12.1 qualification container

This definition is only for the small-fixture Salmon 1.12.1 candidate
qualification. It does not change Harako-GPU's default Salmon 1.10.3 backend
and must not be published.

The image inherits the exact qualified 1.10.3 runtime image, retains that
binary in the base prefix, verifies the official v1.12.1 x86_64 release asset,
and prepends `/opt/salmon-1.12.1/bin` to `PATH`. The build fails closed on asset
checksum or binary-version mismatch.

The official binary calls `setlocale(en_US.UTF-8)` during startup. The exact
Debian 12 locale payload matching the base image's glibc release is therefore
SHA-256 pinned and installed in the image. This is a runtime compatibility
requirement; it does not alter the Salmon command or algorithm.

The base entrypoint activates its original environment and would otherwise
restore the 1.10.3 path. The candidate entrypoint runs that activation first,
then re-prepends only the verified 1.12.1 prefix. The original 1.10.3 binary
remains present and directly inspectable.

Local tag: `harako-gpu/salmon:1.12.1-qualification`.

The resulting local image is an experiment artifact. Its identity is recorded
in `manifest.json`; it is not an approved nf-core override because the candidate
failed the fixed numerical gate.

The tarball, built image, reference index, FASTQ, and quantification output are
runtime-only artifacts and are not committed.
