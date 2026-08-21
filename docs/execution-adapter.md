# Local execution adapter

Harako-GPU executes one immutable run directory at a time. `run start` is an
attached foreground command; there is no daemon, queue, detach mode, remote
executor, or background service. A second terminal may use `run status` or
`run status --watch`, which is read-only polling and never controls the run.

The fixed sequence is preflight, nf-core preprocessing/Parabricks alignment,
alignment validation, primary Salmon, optional secondary Salmon, matrices,
STAR GeneCounts selection, optional concordance, self-contained reporting,
artifact verification, and terminal classification. This is deliberately not
a generic DAG/plugin engine. Alignment uses the GPU; Salmon quantification uses
the CPU.

Windows uses the fixed shell-free WSL runner; native Linux uses the same command
contract directly. Runtime paths remain Linux absolute paths outside Windows
mounts; see [native Linux execution](native-linux-execution.md).

Commands:

```text
harako-gpu run prepare --plan PLAN --runtime-root /home/.../harako-gpu-runtime
harako-gpu run start --run-dir RUN --approval-hash HASH
harako-gpu run inspect RUN [--json]
harako-gpu run status RUN [--json] [--watch]
harako-gpu run resume --run-dir RUN --approval-hash HASH
harako-gpu artifacts list RUN [--json]
harako-gpu artifacts verify RUN [--deep] [--json]
harako-gpu support-bundle create RUN
```

Every command accepts `--execution-context wsl2|native-linux`; WSL2 remains the
compatibility default and frozen-context mismatches are rejected.

This remains research-use-only, non-diagnostic, and non-clinical. It does not
delete/archive BAMs, run DESeq2/enrichment, or qualify full-size data.

The medium-human exercise also regression-tested read-only status during an
active GPU alignment. Status reported RUNNING, current stage/task, RAM/VRAM,
and disk information without controlling the run. The scientific run later
failed its RAM gate, demonstrating that lifecycle observability is distinct
from workflow success. No capacity harness bypassed the public prepare/start/
status path.

The one-pass follow-up again used public prepare/start/status/artifacts and a
fresh run/work directory. Status observed the active GPU stage; the failed run
preserved command, trace, resource log, failed-task evidence, and a sanitized
support bundle. Missing BAM/GeneCounts/Salmon/report artifacts remained
explicitly missing rather than being inferred from partial outputs.
## Quantification-only fixed route

The execution adapter also supports a fixed foreground CPU route: input
validation, pinned fastp, processed-FASTQ validation, sequential Salmon profiles,
matrices, optional profile concordance, report, and artifact verification. It
does not materialize or run an nf-core pipeline snapshot.

The GUI launches the exact CLI start/resume controller as a per-run child using
structured argv and `shell=False`. Status polling is read-only and bounded;
browser closure or page rerun does not cancel the controller. There is still no
daemon, queue, scheduler, cancel command, or global detached service.
