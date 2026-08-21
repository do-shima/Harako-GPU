# GUI source provenance

Read-only source: `do-shima/harako-rnaseq` at commit
`9d8628f48226c330e159ac79c14595f2cf65a551`. Harako-RNAseq is not a runtime
dependency and no directory or scientific workflow was copied.

| Source path | Imported concept | Harako-GPU target | Adaptation and reason |
|---|---|---|---|
| `requirements.in` | exact `streamlit==1.60.0` pin | `pyproject.toml` | Reused the proven UI version; retained Harako-GPU dependencies and Python 3.12 qualification. |
| `app/ui/state.py` | centralized, copy-on-initialize session keys and query persistence | `ui/state.py`, `ui/app.py` | Reduced to draft/display state; frozen run and approval identities remain backend-owned. |
| `app/ui/i18n.py`, `app/ui/locales/{ja,en}.json` | keyed bilingual wording and translation completeness | `ui/labels.py` | Reimplemented as a small in-code catalog with equal Japanese/English claims. |
| `app/ui/pages/project.py` | project-first navigation and review flow | `ui/pages/projects.py`, `navigation.py` | Uses bounded run-manifest discovery instead of Harako-RNAseq configuration. |
| `app/ui/pages/samples.py`, `app/ui/samples_table.py` | editable sample table and inline validation | `ui/pages/samples.py` | Delegates pairing and sample validation to Harako-GPU services; no Snakemake schema. |
| `app/ui/error_messages.py` | concise actionable errors | `ui/errors.py` | Restricts caught presentation errors to service `OSError`/`ValueError`. |
| `app/ui/launcher_ui.py` | CLI-mediated local launch | `ui/launcher.py`, `adapters/gui_launcher.py` | Structured `shell=False` argv; start/resume use Harako-GPU immutable run services. |

Not ported: Snakemake, old run/reference schemas, old workflow/report paths,
scientific stages, CLI, agents, all-in-one container assumptions, or the large
summary page.
