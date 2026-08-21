# Salmon 1.12.1 release-scope audit

Scope is the official Salmon [1.12.0 release](https://github.com/COMBINE-lab/salmon/releases/tag/v1.12.0)
and [1.12.1 release](https://github.com/COMBINE-lab/salmon/releases/tag/v1.12.1),
applied only to Harako-GPU's FASTQ mapping profile (ISR, six threads, no bias
options, no `--writeMappings`, no alignment mode).

| Change | Classification | Qualification meaning |
|---|---|---|
| SSHash streaming k-mer orientation | `DIRECTLY_RELEVANT` | Mapping-mode and the 1.12.1-built SSHash index exercise this path. The fixture's large mapping-rate shift means the effect cannot be assumed benign. |
| `--seqBias` training | `RELEVANT_ONLY_IF_OPTION_ENABLED` | The option is disabled and was not enabled merely to exercise the fix. |
| Alignment-mode mate pairing | `ALIGNMENT_MODE_ONLY` | Harako-GPU forbids alignment-mode Salmon. |
| Positional-bias correction | `RELEVANT_ONLY_IF_OPTION_ENABLED` | `--posBias` is disabled. |
| Mapping-output flush | `NOT_EXERCISED_BY_CURRENT_PROFILE` | `--writeMappings` is absent. |
| BAMQueue startup-memory change | `ALIGNMENT_MODE_ONLY` | No transcriptome BAM is supplied. |
| Deterministic offline M-step | `DIRECTLY_RELEVANT` | It targets the variability that motivated this candidate, but does not make the complete reads path deterministic. |
| Uniform offline initialization | `DIRECTLY_RELEVANT` | Default 1.12.1 behavior; no compatibility flag was added. |
| Selective-alignment and decoy attribution fixes | `DIRECTLY_RELEVANT` | The fixed decoy-aware reads profile exercises these defaults. |
| `maxReadOcc` enforcement/default 250 | `DIRECTLY_RELEVANT` | Enforcement is newly effective. No override was introduced to recover the old mapping rate. |
| `--writeMappings` + `--gcBias` maintenance fix | `NOT_EXERCISED_BY_CURRENT_PROFILE` | Both options are absent. |
| Residual FLD-feedback variability | `UNKNOWN_REQUIRES_TEST` | The release explicitly retains this limitation; the 10-repeat and thread tests measured material variation. |

The official notes describe 1.12.1 as the legacy C++ 1.x line and recommend
2.x as the actively developed line. This audit does not introduce 2.x and does
not interpret that recommendation as qualification. The 1.12.1 release asset
was tied to source commit `971a2ad6e86cc32315d919faed0be0e88d36c9e5`.

The observed mapping-rate reduction is consistent with execution of changed
mapping code, but this audit does not attribute it to one fix without a broader
truth-based fixture. Options that are absent from the fixed command remain
`NOT_EXERCISED` rather than being advertised as tested.
