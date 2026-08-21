# Immutable run directory

`run prepare` creates `{output_root}/{project_slug}/{UTC}-{plan_digest}` and a
distinct work directory. Re-running one plan creates a new run ID. The run
contains immutable identity in `run.json`; mutable atomic status in
`status.json`; an exclusive `lock.json`; frozen plan, approval, reference,
profile, series, params, config, command, environment, pipeline/patch
inventories, and tx2gene under `frozen/`; a read-only local pipeline snapshot;
numbered attempt logs under `execution/attempts/`; task history; namespaced
results; artifact manifests; and support metadata.

`frozen/manifest.json` hashes every frozen file. Start and resume verify those
hashes before creating an attempt. Runtime state never modifies run identity.
All mutable JSON writes use a same-directory temporary file and atomic replace.
Locks use exclusive creation. Profile artifacts remain under
`results/quantification/<profile>/<sample>` and matrices retain the profile ID;
ambiguous names such as `counts.tsv` are forbidden.

Each capacity level uses independent run and work roots. The four retained C1
diagnostic runs are immutable historical attempts; later fixes were evaluated
in new run directories, not by rewriting frozen plans or attempt histories.
C2-C4 have no run directory because the C1 resource hard stop prohibited
progression.
For BAM-none runs, processed reads are under `results/preprocessing/fastp/` and
alignment output directories are not generated. Artifact manifests retain the
alignment roles as `NOT_APPLICABLE` evidence.

The GUI persists only the run-directory pointer in the URL/session. Refresh,
new session, or server restart reconstructs identity, state, attempts, lock,
tasks, and artifacts through application services. It never writes `run.json`,
`status.json`, tasks, lock, or frozen files.
