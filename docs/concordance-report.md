# Concordance report

Concordance is built only after both profile matrices and selected STAR counts
validate. The execution adapter copies the self-contained result into the run
report namespace and records it in the artifact manifest. Missing STAR evidence
is never fabricated; a future limited comparator state must remain explicit.
`harako-gpu concordance build` creates a self-contained HTML report and
profile-qualified TSV/JSON artifacts. It uses exact feature IDs without silent
version-suffix removal and reports unmatched IDs separately. The fixed
abundance transform is `log2(TPM + 0.1)`; primary values are never rounded or
changed.

High-priority method sensitivity means max TPM at least 1 and absolute log2
ratio at least 1. Moderate sensitivity uses 0.585 to below 1. A high-priority
zero transition has one TPM at least 1 and the other below 0.1. These are
reporting categories, not errors.

The descriptive tiers are: A (gene Spearman ≥0.99, top-100 overlap ≥90%, high
zero transitions ≤0.5%), B (≥0.95, ≥75%, ≤2%), and C otherwise. Labels are
「高い一致」「一部に方法依存性」「広範な方法依存性」; they are not PASS/FAIL.
STAR comparison uses count-derived CPM only. The report contains no external
JavaScript, CDN, font, or correctness claim and explicitly states that only the
primary profile may proceed downstream.
