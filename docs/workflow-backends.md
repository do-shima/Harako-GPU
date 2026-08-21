# Workflow backends

Harako-GPU keeps Nextflow 25.04.3 as its execution engine and exposes two
fixed workflow backend identities.

| Internal ID | CLI value | Purpose | Qualification/default status |
|---|---|---|---|
| `nfcore_rnaseq_3_26_reference` | `nfcore-rnaseq-3-26-reference` | Qualified comparison/reference path using the pinned nf-core/rnaseq 3.26.0 snapshot | Historical and Windows/WSL default; always explicitly selectable |
| `harako_native_v1` | `harako-native-v1` | Small Harako-owned DSL2 alignment and QC path | Qualified default for new receipt-backed native Ubuntu high-memory plans |

Plans created before `workflow_backend` was introduced retain their historical
meaning and are read as `nfcore_rnaseq_3_26_reference`. They are never
rewritten or silently reinterpreted as Harako-native runs. New plans freeze the
backend, alignment adapter, processed-FASTQ contract, output contract, image
closure, and resource contract in the approval identity.

The fixed alignment adapter catalog is `parabricks_star`, `none`, and
`star_cpu`. `parabricks_star` is implemented for GPU BAM routes and `none` is
used by quantification-only routes. `star_cpu` is schema-reserved but
`NOT_QUALIFIED`; no CLI execution choice or fallback is exposed.

`harako_native_v1` does not load nf-schema and does not depend on the full
nf-core task-image closure. Python validates the immutable plan before prepare;
the native workflow uses only fixed parameters and locally present, pinned
images. The reference backend retains its existing plugin, patches, pipeline
commit, and 18-image closure.

The new-plan resolver selects `harako_native_v1` only when the native Ubuntu
high-memory host receipt validates and the committed one-pass/two-pass C1
parity report hashes are exact. Missing or altered evidence fails closed to the
reference backend. An explicit `--workflow-backend` always wins. Historical
plans lacking the field retain their original approval identity and resolve to
the reference backend. This parity establishes a bounded backend comparison,
not scientific superiority or arbitrary-input equivalence.

The GUI follows the same resolver and freezes the selected backend into the
immutable plan and approval identity. On a receipt-backed genuine native Ubuntu
host, Harako-native is the standard choice and the nf-core 3.26 reference path
is an advanced option. On Windows/WSL, only the nf-core reference backend is
offered for scientific execution. A backend change invalidates any earlier GUI
eligibility result and requires a new plan; Streamlit session state is not an
execution authority. Native GUI C1 launch qualification remains pending.
