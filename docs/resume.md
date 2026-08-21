# Resume contract

Resume uses the same run directory, approval hash, plan, analysis series,
pipeline snapshot, params/config, work directory, references, samples,
profiles, images, indices, library type, patch set, and retention policy.
Frozen SHA mismatch fails closed.

An incomplete nf-core task uses the same launch/work directories with
Nextflow `-resume`. A validated nf-core task is not rerun. Validated Salmon
tasks are reused only inside the same run when task and output identities
match; failed, missing, or invalid outputs are rerun. Incomplete output is
archived into the new attempt rather than accepted or silently deleted.
Matrices/concordance are reused only with unchanged validated dependencies.
Every resume creates a new attempt and retains all earlier logs and trace.
