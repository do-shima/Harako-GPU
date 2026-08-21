# Qualification history

This page preserves the historical qualification narrative that previously
dominated the project README. The immutable Markdown and JSON records under
`docs/qualification/` remain authoritative; later success never rewrites an
earlier preregistered failure.

## Foundation and Windows/WSL2

Harako-GPU began as an internal planning and preflight foundation for a fixed
Windows 11 + WSL2 + NVIDIA path. The execution adapter, atomic PID/lock/state
model, numbered attempts, resume behavior, artifact verification, and sanitized
support bundle were established before native Linux execution. The 64 GB WSL
host retained strict full-human BAM memory limits after both one-pass and
two-pass capacity failures; those failures are not reclassified as successful
Windows qualification.

See:

- [Execution adapter lifecycle](../qualification/execution-adapter-run-status-resume-artifacts.md)
- [Reference-aware BAM routing](../qualification/reference-aware-bam-optional-human-quantification.md)
- [One-pass workstation profile](../qualification/parabricks-one-pass-workstation-profile.md)

## Native Linux and high-memory host

Native Linux support preserved Linux paths directly, used shell-free structured
argv, and separated native PID/resource/BAM validation from WSL transport.
Fixed non-scientific fail/resume lifecycle qualification preceded full-human
work. On the Ubuntu RTX 3090 / 128 GB host, one-pass completed with the fixed
42.GB contract. A two-pass failure was isolated to the inherited 42.GB container
limit rather than host OOM; a prospectively fixed 96.GB / 12-CPU contract then
completed without cgroup or host OOM. Verified terminal-results archives were
created before explicit SSD cleanup.

See:

- [Native Linux foundation](../qualification/native-linux-execution-foundation.md)
- [Full-human one-pass](../qualification/native-high-memory-full-human-one-pass.md)
- [Full-human two-pass](../qualification/native-high-memory-full-human-two-pass.md)
- [Ubuntu product CLI smoke](../qualification/ubuntu-high-memory-product-cli-smoke.md)

## Salmon evidence

Salmon 1.12.1 was rejected and hidden after its preregistered qualification.
Salmon 2.5.1 became the reproducibility-first default after deterministic
qualification, while immutable external-truth failures remained failures.
The native-small Salmon 1.10.3 index experiment did not promote an index because
index payloads and exact-repeat outputs failed its strict preregistered gates.
That result did not reject the previously fixed full-human Salmon 1.10.3
compatibility profile.

The later C1 comparison used the exact full-human 1.10.3 and 2.5.1 indices,
same processed FASTQ, six threads, and opposite execution orders across two
runs. It established a deterministic 2.5.1 profile, bounded-numerical 1.10.3
repeatability, observed runtime differences, and cross-version method
sensitivity. It did not establish biological truth or general performance.

See:

- [Salmon 2.5.1 deterministic qualification](../qualification/salmon-2.5.1-deterministic-qualification.md)
- [Salmon 1.10.3 native-small negative result](../qualification/native-small-salmon-1.10.3-index-result.md)
- [Salmon 1.10.3 vs 2.5.1 C1 comparison](../qualification/salmon-1.10.3-vs-2.5.1-c1-comparison.md)

## Harako-native and GUI

The compact Harako-native Nextflow backend was added without silently
reinterpreting historical plans. C1 one-pass and two-pass runs demonstrated
strict scientific parity and exact BAM record-stream parity against the fixed
nf-core reference backend, while documenting representation and optional-QC
differences. Receipt-backed qualified Ubuntu plans then adopted Harako-native
as the new-plan default; Windows/WSL and historical defaults remained nf-core.

The native Ubuntu GUI subsequently exercised the public planning, prepare,
start, status, artifact verification, and support-bundle services for C1
one-pass and two-pass. AppTest and HTTP qualification passed. The inability to
run an actual browser on that host remains an explicit public-alpha limitation.

See:

- [Harako-native parity](../qualification/harako-native-vs-nfcore-c1-parity.md)
- [Ubuntu native GUI qualification](../qualification/ubuntu-native-gui-scientific-launch.md)
- [Harako-native architecture](../architecture/harako-native-workflow-v1.md)

## Claim discipline

None of these records qualifies arbitrary hardware, arbitrary human inputs,
custom references, matched CPU speedup, cross-host BAM equality, biological
accuracy, diagnostic use, or clinical use. CPU STAR remains unavailable. The
fixed terminal archive policy does not authorize automatic deletion.
