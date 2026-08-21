"""Apply the SHA-pinned nf-core/rnaseq 3.26.0 log compatibility patch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harako_gpu.adapters.nfcore_patch import apply_verified_patch
from harako_gpu.adapters.process import ProcessRunner


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pipeline_root", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("patch", type=Path)
    args = parser.parse_args()

    runner = ProcessRunner()
    commit_result = runner.run(("git", "-C", str(args.pipeline_root), "rev-parse", "HEAD"), timeout=30)
    if not commit_result.ok:
        raise SystemExit(commit_result.stderr.strip() or "Unable to resolve pipeline commit")
    report = apply_verified_patch(
        args.pipeline_root,
        args.manifest,
        args.patch,
        resolved_commit=commit_result.stdout.strip(),
        runner=runner,
    )
    print(json.dumps({"status": report.status, "check_argv": report.check_argv, "apply_argv": report.apply_argv}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
