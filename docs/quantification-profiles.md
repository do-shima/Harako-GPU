# Versioned quantification profiles

The execution adapter materializes each profile under its own quantification and
matrix namespace, from the same validated fastp pair in comparison mode.
Primary then secondary run sequentially. A task can be reused on resume only
inside the same run when input/index/image/command identity and structural
output validation all match.
The visible catalog is fixed at version `harako-quantification-profiles-v1`.

| Profile | Label | Fixed backend | Reproducibility | Product position |
|---|---|---|---|---|
| `salmon_2_5_1_deterministic` | 再現性優先・推奨 / Reproducibility-first — recommended | Salmon 2.5.1 Rust, deterministic, serial decoder, ISR/ISF/U explicit, six CPU threads | `exact_deterministic` | recommended for new internal research series |
| `salmon_1_10_3_compatibility` | 互換性優先 / Compatibility-first | Salmon 1.10.3 legacy C++, six CPU threads, explicit library type | `bounded_numerical` | historical Salmon 1.x/nf-core continuity |

Salmon 1.12.1 remains `rejected_candidate_hidden` and cannot be selected.
Salmon 1.10.3 is not identical to Harako-RNAseq Salmon 1.10.0. Profile
availability does not rewrite historical qualification verdicts.

Modes are `recommended_only`, `compatibility_only`, and `compare_both`.
Comparison requires an explicit primary; the other visible profile is the
secondary comparator. The same processed R1/R2 identities, fragment count,
fastp provenance, library type, reference sources, and version-specific index
identities are mandatory. Salmon runs sequentially on CPU; GPU acceleration is
limited to alignment.
Both visible Salmon profiles are CPU processes. In BAM-none mode they consume the
same fixed fastp processed FASTQ. No profile is presented as GPU accelerated.

GUI cards expose only 2.5.1 reproducibility-first, 1.10.3 compatibility-first,
and compare-both with an explicit primary. The hidden 1.12.1 candidate and raw
version/image/index selectors are not user-facing.
