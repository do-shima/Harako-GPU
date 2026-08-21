# Native Linux execution foundation

Harako-GPU supports two explicit, immutable execution identities:

- `wsl2:<distribution>` uses the established Windows controller and WSL2 transport.
- `native_linux` uses the native Ubuntu filesystem and direct child processes.

The CLI spelling is `--execution-context wsl2` (the compatibility default) or
`--execution-context native-linux`. `run prepare` freezes the resolved identity
in `run.json`. Start, resume, inspect, status, artifact, and support operations
reject a requested identity that differs from that frozen value. A WSL
distribution is required only by the WSL2 transport. There is no automatic
fallback between transports and unsupported hosts fail closed.

Native execution preserves safe absolute Linux paths and launches structured
argv directly without a shell. Preparation derives its concrete prerequisites
from the validated route: GPU alignment resolves exact Nextflow 25.04.3 and its
fixed pipeline/images, while `fastq_quantification_only` inspects only fastp
and the selected fixed Salmon profile image(s). Generic `doctor` remains a
whole-product inventory; `run prepare` records generic findings that do not
apply to the frozen route as `NOT_APPLICABLE` without weakening Docker, disk,
input, reference, index, or selected-image identity checks.

Docker identity validation distinguishes registry manifest digests from local
image/config IDs. Public fastp and Salmon 1.10.3 contracts require the exact
configured repository in Docker `RepoDigests` and execute as
`<reference>@<digest>`; tag-only presence or a digest on an unrelated
repository fails closed. The locally built Salmon 2.5.1 contract continues to
require and execute its exact image ID. Historical readers retain their prior
Parabricks identities. The high-memory host overlay separately preserves the
manifest-list digest, linux/amd64 platform descriptor, loaded config/image ID,
offline archive SHA, version probe, and provenance-receipt identity. Docker
`.Id` is compared only with the config/image ID; a manifest-list digest is
supply-chain evidence, not a local image ID.
The native child PID is recorded atomically and interpreted as a local PID.
Resource probes run directly against `nvidia-smi`, `/proc`, cgroup, `df`, and
`du`; failures remain best-effort telemetry warnings. Native BAM validation
builds direct fixed-image Docker argv with a read-only artifact-directory
mount. No image, pipeline, reference, index, or FASTQ is downloaded.

The GUI can expose native scientific prepare/start only for the exact
receipt-backed Ubuntu high-memory profile after parity, provenance, runtime
closure, asset, local-storage, disk, and controller-lock checks pass. It reuses
the public plan/run services and never builds a GUI-specific command. Ubuntu
GUI C1 launch qualification remains pending, so this foundation is not itself
an acceptance result.

## Ubuntu high-memory installed evidence

`ubuntu_native_rtx3090_ram128_v1` is not inferred from RAM or GPU probes. An
operator provisions verified JSON receipts beneath `<runtime-root>/host-profiles/`;
plan creation never creates or edits them. The fixed plugin is provisioned
explicitly, outside a frozen run:

```bash
NXF_VER=25.04.3 NXF_PLUGINS_DIR="$HOME/.nextflow/plugins" nextflow plugin install nf-schema@2.5.1
```

The operator then copies the separately generated offline cache receipt to
`<runtime-root>/host-profiles/nf-schema-2.5.1-offline-v1.json`. Frozen runs set
`NXF_OFFLINE=true`; there is no prepare-time install, online fallback, image
pull, or unversioned resolution. The exact full-human closure contains 18 task
images, including Subread, BedClip, Qualimap, and StringTie, and is checked
before a run directory is created.

The operator-issued host and image receipts are copied explicitly as
`<runtime-root>/host-profiles/ubuntu_native_rtx3090_ram128_v1.json` and
`<runtime-root>/host-profiles/parabricks-offline-linux-amd64-v1.json`. They
contain identities and verification status only—no credentials, FASTQ, or
environment dump. `plan create --host-profile ... --host-receipt ...
--parabricks-provenance-receipt ...` consumes them read-only.

Provision the fixed Ubuntu receipt set explicitly from the verified evidence,
the retained offline handoff, and the prior execution receipt. The command
validates the current host, plugin cache, all 18 local task images, the
Parabricks manifest/platform/config/archive chain, and both terminal archive
receipts before performing atomic writes. It never downloads or auto-qualifies:

```text
harako-gpu host-profile provision \
  --bundle-root /path/to/ubuntu-high-memory-host-capability-v1 \
  --runtime-root /path/to/native-runtime \
  --plugin-dir /path/to/.nextflow/plugins \
  --handoff-root /path/to/verified-handoff \
  --parabricks-execution-receipt /path/to/parabricks-offline-execution-receipt.json
```

## Terminal-results archive policy

`harako-gpu-terminal-results-archive-v1` keeps active work on local ext4 SSD.
A successful terminal result is retained as a verified PAX archive on WD Gold;
full successful Nextflow work is not retained after that explicit verified
archive operation. Failed or resumable work remains on SSD. This implementation
does not add background deletion or automatic cleanup.

## Salmon 1.10.3 native index decision

Native-built Salmon 1.10.3 indexes for the fixed small reference were not
byte-deterministic with either one or six index-building threads. Same-index,
one-thread quantification repeats were also not exact-repeat stable. No index
was promoted and no native CPU product route was qualified. Salmon 1.10.3
therefore remains a bounded-numerical compatibility profile, and existing
immutable analysis series are not migrated automatically. Reproducibility-first
new native series should evaluate the fixed Salmon 2.5.1 deterministic profile
under a separate prospective qualification; this cleanup does not qualify that
profile on native Ubuntu. See the immutable
[v1 negative result](qualification/native-small-salmon-1.10.3-index-result.md)
and [cause-isolation result](qualification/native-small-salmon-1.10.3-index-cause-isolation.md).

## Qualification boundary

The native foundation is qualified with the fixed non-scientific
`qualification/lifecycle-nextflow/main.nf` fail/resume fixture. This establishes
direct structured launch, PID/resource evidence, expected exit 42, resume,
cache reuse, and exact output-token behavior. It does not qualify Parabricks,
nf-core/rnaseq, BAM production, Salmon, reference/index integration,
biological accuracy, full-human scale, or production use. The later immutable
[one-pass](qualification/native-high-memory-full-human-one-pass.md) and
[two-pass](qualification/native-high-memory-full-human-two-pass.md) reports add
an exact Ubuntu host overlay; they do not establish arbitrary hardware,
cross-host BAM equality, production, diagnostic, or clinical use.
