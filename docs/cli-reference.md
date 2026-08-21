# CLI reference

The execution lifecycle adds only these foreground/read-only groups:

- `run prepare --plan PATH --runtime-root LINUX_PATH`
- `run start --run-dir RUN --approval-hash HASH`
- `run inspect RUN [--json]`
- `run status RUN [--json] [--watch]`
- `run resume --run-dir RUN --approval-hash HASH`
- `artifacts list RUN [--json]`
- `artifacts verify RUN [--deep] [--json]`
- `support-bundle create RUN`

Execution commands accept `--execution-context wsl2|native-linux`; WSL2 remains
the default and mismatched frozen identities fail closed. See
[native Linux execution](native-linux-execution.md) for transport details.

`prepare` does not execute analysis. `start` is attached foreground execution.
`status --watch` is polling only and Ctrl+C stops the watcher, not the run.
`resume` accepts only failed/interrupted immutable runs. There is intentionally
no cancel, delete, archive, detach, submit, queue, remote-executor, DESeq2, or
enrichment command.

`harako-gpu ui [--host HOST] [--port PORT] [--no-browser] [--output-root PATH]`
launches Streamlit 1.60.0. The default host is `127.0.0.1`; `0.0.0.0` emits an
explicit out-of-qualification warning. Start/resume within the GUI calls the
same CLI and frozen approval contract.
