# Contributing to Harako-GPU

Focused bug fixes, tests, documentation, and scientifically justified changes
consistent with the local single-user research scope are welcome.

Before contributing:

- Read [AGENTS.md](AGENTS.md), [PUBLIC_ALPHA.md](PUBLIC_ALPHA.md), and the
  relevant product/qualification contracts.
- Search existing issues. Keep one purpose per branch and pull request.
- Never post FASTQ, BAM, reference/index assets, credentials, private host
  paths, identifiable samples, or unredacted support bundles.
- Describe scientific assumptions, compatibility effects, frozen-schema
  effects, and qualification gaps before changing analysis behavior.
- Preserve Windows/WSL/native path safety and the no-fallback contracts.

Development setup:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
python -m pytest -ra -rs
python -m pip check
python -m compileall -q src tests scripts
git diff --check
```

Use small synthetic or public fixtures only. Scientific changes require a
documented prospective contract, behavioral coverage, platform-specific
validation, and explicit limitations. Do not silently reinterpret historical
runs or qualification results.

Submitted material must be original or legally reusable under terms compatible
with this repository. Identify third-party provenance. Contributions accepted
into Harako-GPU are distributed under the PolyForm Noncommercial License 1.0.0;
no contributor license agreement is implied.

Disclose material AI assistance in the pull request. A human remains
responsible for scientific interpretation, licensing, privacy, and acceptance.
