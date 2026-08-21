# Native high-memory full-human one-pass qualification

Classification: `FULL_SIZE_ONE_PASS_END_TO_END_QUALIFIED`.

The normalized `ubuntu-high-memory-host-capability-v1` evidence bundle records a terminally successful full `ERR188044` run on the fixed Ubuntu native RTX 3090 / 128-GB host class. It used `parabricks_star_one_pass_workstation`, Nextflow 25.04.3, nf-core/rnaseq 3.26.0 at `e7ca46272c8f9d5ceee3f71759f4ba551d3217a4`, the fixed GRCh38.p14/GENCODE 49 reference and STAR index, FeatureCounts `-t exon -g gene_type`, and deterministic Salmon 2.5.1. No CPU STAR fallback occurred.

The Parabricks task used 12 CPUs and an effective 42.GB container limit. BAM quickcheck, STAR GeneCounts, Salmon, matrices, MultiQC, and the verified `harako-gpu-terminal-results-archive-v1` receipt passed. The archive receipt SHA-256 is `91c2afbbefbd0968f60d59df3ac57966d17c335fd2438edcd3f10ec5d000b68e`.

Source identities are frozen in the adjacent JSON. The normalized evidence SHA-256 is `d13224114bdd9990bb4d299a654982380fcb85c253e95ee99120447be758f324`; the source report SHA-256 is `5b7cd86d0d24c00a51a7b9fc25806b659cdbf92eef0ae88610488d59835a59c9`. No external report, private absolute path, or biological artifact is copied here.

This qualifies only the fixed public input, assets, profile, and host class. It does not establish arbitrary-hardware support, biological accuracy, diagnostic or clinical use, scientific superiority, or cross-host BAM equality. Product Docker provenance remained pending in the scientific-run evidence and is a separate product availability gate.
