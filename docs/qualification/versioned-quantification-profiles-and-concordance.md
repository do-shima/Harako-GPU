# Versioned quantification profiles and concordance qualification

## Completion classification

`HARAKO_GPU_VERSIONED_QUANTIFICATION_PROFILES_AND_CONCORDANCE_QUALIFIED`

Two visible, fixed profiles are available: deterministic Salmon 2.5.1 is the
recommendation for new internal research series, while Salmon 1.10.3 is an
explicit compatibility choice. Salmon 1.12.1 remains hidden/rejected. This
product position preserves every historical verdict; it does not declare one
version universally correct.

WT_REP1 used identical processed R1/R2 for six sequential fresh runs. Salmon
2.5.1 was byte-identical in 3/3; 1.10.3 retained exact processed/mapped counts
but had two quant.sf byte identities across three runs, preserving its bounded
numerical classification. Both used dedicated version-built indices from the
same biological source.

Profile concordance had 125 common genes, Spearman 0.993064, log-Pearson
0.979156, top-100 overlap 98%, and two high-priority zero transitions. This is
descriptive Tier B, 「一部に方法依存性」. Four reported method-sensitive genes
are not labelled errors. The unmatched ID `I` is explicitly retained.

The qualified ISR STAR comparator had 124 common genes. STAR-versus-2.5.1
Spearman was 0.975567 and STAR-versus-1.10.3 was 0.979524. Comparison used CPM
from STAR raw counts and Salmon estimated counts, never STAR count versus TPM.
Annotation strata preserve missing fields as `unknown`.

Existing truth-v2 outputs produced profile-qualified matrices for six ordered
samples and 30 common GTF-aggregated genes plus descriptive condition mean
fold changes. Gene effective length uses one fixed contract for both profiles:
TPM-weighted transcript effective length, with an arithmetic mean only for a
zero-mass gene. No P value, FDR, DEG, or enrichment result was generated.

The HTML report is self-contained and bilingual. Only the immutable primary
profile can proceed to future downstream work. Secondary and STAR results are
robustness comparators. Profile changes require a new parent-linked analysis
series. Scope is internal research, non-diagnostic, non-clinical, and not
full-size-human qualified.
