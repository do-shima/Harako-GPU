# Harako-native v1 pipeline

This is the Harako-owned, fixed Nextflow DSL2 alignment/QC foundation. It has
no runtime module download, nf-schema plugin, hidden Salmon process, or CPU STAR
fallback. Python plan preparation supplies every parameter and validates every
selected image before launch.

No nf-core/modules source is vendored in v1. The pinned containers invoke
fastp, Parabricks, samtools, Subread FeatureCounts, and MultiQC. Controller-side
Salmon and artifact logic remains in `src/harako_gpu`.
