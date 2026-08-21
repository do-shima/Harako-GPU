# External truth failure cause isolation

## Completion classification

`HARAKO_GPU_EXTERNAL_TRUTH_FAILURE_CAUSES_MIXED`

The original external-truth v2 verdict remains
`HARAKO_GPU_SALMON_2_5_1_EXTERNAL_TRUTH_FAILED`. Its preregistrations,
thresholds, selected lanes, results, and documents were not overwritten.

## SIRV cause

The 67-group partition is mechanically valid, but 66 groups are singletons.
Its relative-error limits are asymmetric and materially stricter than the
absolute-log2 transcript limits, so the scales are `INCOMPARABLE_METRICS`.
The only multi-transcript group passes while singleton summaries fail. SIRV502
has a strong coverage defect but diagnostic removal does not rescue the frozen
gate. Combined and SIRV-only indices are numerically identical, and Salmon
1.10.3, 1.12.1, and 2.5.1 all fail. The gate is therefore invalid as evidence
of a 2.5.1-specific algorithm defect, although its historical FAIL is retained.

## ERCC cause

Unused L03/L04 lanes were frozen by metadata before acquisition. Held-out Mix
2 reproduced aggregate mapping above the historical 0.10% limit. Independent
exact and pinned-minimap2 evidence classifies virtually every `MT-RNR2`/
`MT-CO2` pair as genuine human mitochondrial evidence, predominantly already
present in raw reads. That named component is external-sample contamination.

Most aggregate records name nuclear human targets and remain unresolved because
the prospective oracle reference was restricted to ERCC plus mitochondrial
sequences. Expanding it after results would change the classification contract,
so this analysis does not claim that the full aggregate has been isolated.
There is no evidence here of a Salmon 2.5.1-specific defect.

## Decision and scope

The two failed gates have different causes: SIRV is a metric-contract/shared
limitation; the named ERCC mitochondrial signal is sample contamination; the
remaining ERCC aggregate is unresolved. No new adoption gate is created.
Salmon 2.5.1 remains qualification-only and non-default. Production use, a
default change, and GUI work remain unauthorized.

Detailed evidence is recorded in
`sirv-equivalence-group-cause-analysis.{md,json}` and
`ercc-mitochondrial-offtarget-cause-analysis.{md,json}`. Runtime FASTQ,
indices, mapping output, quantification output, and per-read details remain
outside Git.

The later versioned-profile goal does not revise this evidence. It uses the
absence of a confirmed Salmon-2.5.1-specific defect together with exact
technical/internal qualification to offer 2.5.1 for new internal-research
series, while retaining this external FAIL as a stated limitation. Salmon
1.10.3 remains a comparison/compatibility option; neither result is described
as the universal biological truth.
