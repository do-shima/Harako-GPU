# Hardware and runtime preflight

## Prepare-time runtime gate

`run prepare` revalidates Docker Linux engine/GPU, WSL2 or native Linux, Java
17+, exact Nextflow 25.04.3, pinned images, references/indices, path safety, and
disk space using the actual small-fixture estimate. Generic recommended scratch
warnings do not replace the run-specific disk gate. Missing inputs are not
downloaded and WSL work/results must stay outside Windows mounts.
Native-host gating follows the authoritative
[native Linux execution contract](native-linux-execution.md).

For the full-human Ubuntu GPU route, ordinary hardware readiness is not enough.
Preparation also validates the installed host qualification receipt, exact
`nf-schema@2.5.1` offline cache receipt, all 18 fixed task images, and the
Parabricks linux/amd64 offline provenance chain before launch. These checks do
not pull images or install plugins.
`harako-gpu doctor` produces a concise user summary. `harako-gpu doctor --json`
produces hardware-report schema version `1` with raw command results retained in
`support_details`.

The probe checks Python, OS and execution context, logical CPU count, host RAM,
current-filesystem capacity, NVIDIA GPU names/UUIDs/VRAM/driver, `nvidia-smi`,
Docker daemon and NVIDIA runtime indication, Java, Nextflow, nf-core, and local
Parabricks/CUDA test images. On Windows it also checks WSL status, distributions,
default WSL version, and WSL-side NVIDIA, Docker, Java, Nextflow, and nf-core
commands.

Java output is parsed from stdout and stderr. Java below major 17 is a hard
blocker (`JAVA_VERSION_UNSUPPORTED`); absence is `JAVA_NOT_FOUND`.

Nextflow `25.04.3` is the minimum and initial qualified version. Older versions
are blocked. Exact 25.04.3 is `QUALIFIED_VERSION_MATCH`; newer versions are
`VERSION_SUPPORTED_BUT_NOT_YET_QUALIFIED` warnings and do not become qualified
merely by being newer.

On WSL, the doctor first resolves `nextflow` with the fixed
`command -v nextflow` probe. It then launches that validated absolute path with
the structured environment `NXF_VER=25.04.3`; this supports user-local
installations without using a shell command string. Machine-readable JSON is
written as UTF-8 so raw WSL stderr remains serializable on Windows consoles
whose legacy text encoding cannot represent every character.

Within WSL, NVIDIA probing is ordered as `command -v nvidia-smi`,
`nvidia-smi`, then `/usr/lib/wsl/lib/nvidia-smi`. A successful full-path probe
records `NVIDIA_SMI_PATH_NOT_EXPORTED`, recommends `/usr/lib/wsl/lib` for PATH,
and does not report GPU absence. Installing a Linux NVIDIA driver inside WSL is
never recommended.

Windows Docker daemon detection is separate from WSL integration. WSL must
successfully return `docker version`, `docker info`, a server section, a Docker
context, and a Linux container-engine OS. Windows-side Docker alone is not
sufficient.

WSL-visible resources are distinct from Windows-host values. Contract constants
set the initial candidate thresholds to 24 logical CPUs, 100 GiB recommended
RAM, and 100 GiB minimum work-root free space. CPU/RAM shortfalls are warnings;
insufficient or undetectable work-root scratch is a blocker.

It never installs a distribution, pulls an image or pipeline, downloads a
reference, logs into a service, or accepts terms.

Native preparation additionally requires a genuine Linux host (not Windows,
macOS, or a WSL kernel), an existing absolute Nextflow executable reporting
exactly 25.04.3 under `NXF_VER=25.04.3`, and every fixed Docker image already
present locally. Image inspection runs as direct `docker image inspect`; it
never pulls or logs in. A missing Parabricks image remains an execution blocker
but does not invalidate the non-scientific lifecycle transport qualification.

Statuses mean:

- `PREFLIGHT_READY`: required components were detected; science is not qualified.
- `PREFLIGHT_READY_LOW_MEMORY_CANDIDATE`: components were detected but at least one GPU has less than 32 GiB VRAM; real qualification is still required.
- `BLOCKED`: one or more required runtime components were not detected or failed.
- `NOT_TESTED`: the relevant action was not run or cannot apply in this context.

Hard blockers include unavailable WSL2/GPU/Docker integration, Java below 17,
missing or unsupported Nextflow, Docker daemon/GPU access failure, missing
Parabricks image, insufficient scratch, and backend inconsistency. The nf-core
CLI is optional. Absence of a CUDA sample image is recorded separately as
`GPU_CONTAINER_TEST_NOT_RUN`; it means the qualification probe has not run and
does not by itself block execution readiness.

No GPU model, including RTX 3090, is automatically called supported. Timeouts,
non-zero exits, malformed output, exceptions, and raw stderr remain visible.
CPU fallback is neither performed nor proposed.

For a full-human capacity run, ordinary preflight readiness is necessary but
not sufficient. The qualification gate additionally requires WSL root total at
least 500 GiB, free at least 300 GiB before reference preparation, backing
Windows capacity, and a per-stage reserve of max(30 GiB, 15% filesystem size).
Those storage checks passed after user remediation. Runtime monitoring then
correctly stopped scale progression when C1 RAM crossed the preregistered hard
limit. Preflight must not interpret local image/index presence as capacity.

The follow-up one-pass probe reinforces this boundary: every static preflight
and storage check passed and the small fixture completed, yet full-human C1
was SIGKILLed at 91.53% WSL RAM. Doctor must report both one-pass and two-pass
as host-memory-unqualified on this workstation and must not auto-select either.
## Reference-aware gate

Preflight combines measured host identity with exact reference qualification.
GRCh38.p14/GENCODE 49 BAM requests fail before execution on the current host.
BAM-none plans must explicitly disable alignment and STAR comparison.
