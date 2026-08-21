# Run, attempt, and task states

Run states are `PREPARED`, `RUNNING`, `FAILED`, `INTERRUPTED`, `BLOCKED`,
`COMPLETED`, `COMPLETED_WITH_LIMITATION`, and `RETENTION_PENDING`. Start permits
only `PREPARED -> RUNNING`. Resume alone permits `FAILED/INTERRUPTED -> RUNNING`.
Completed runs cannot resume; repeat analysis requires a new run. A stale lock
is archived rather than deleted silently and a formerly running run becomes
`INTERRUPTED` before resume.

Attempts are immutable numbered directories with `CREATED`, `RUNNING`, and one
of `SUCCEEDED`, `FAILED`, or `INTERRUPTED`. Tasks record stage, sample/profile,
input/command/image identity, attempt, logs, exit, expected outputs, validation,
cache status, resumability, and failure class. Result files alone never infer a
terminal state. Completion additionally requires expected process identities,
validated profile outputs/matrices/STAR/report/artifacts, a terminal exit
record, and no live lock.
