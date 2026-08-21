# Native Linux execution foundation qualification

## Classification

`HARAKO_GPU_NATIVE_LINUX_EXECUTION_FOUNDATION_QUALIFIED`

The fixed non-scientific lifecycle fixture was executed on native Ubuntu
24.04.4 with kernel 6.14.0-37-generic and Nextflow 25.04.3. Attempt 0001 returned
1 and recorded `FAIL_ONCE` exit 42. Attempt 0002 used the same launch/work root
with `-resume`, returned 0, recorded `PREPARE_TOKEN` as `CACHED` and `FAIL_ONCE`
as `COMPLETED`, and produced exactly `fixed-lifecycle-token`. Both attempt
histories, traces, reports, logs, PID files, command/environment identities,
and native resource samples were retained. No `wsl.exe` command was detected.

The full Python regression suite, Docker GPU smoke, doctor JSON parsing, and
loopback GUI health regression are required by the same commit gate. The
machine-readable lifecycle result is
[`native-linux-execution-foundation.json`](native-linux-execution-foundation.json).

## Claim boundary

This qualification establishes the native Linux execution foundation using a
fixed non-scientific fail/resume Nextflow fixture. It does not qualify
Parabricks, nf-core/rnaseq, BAM generation, expression quantification,
biological accuracy, full-human scale, or production use.
