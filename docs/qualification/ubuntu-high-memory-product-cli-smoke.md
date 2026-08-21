# Ubuntu high-memory public product CLI smoke qualification

Classification: `PUBLIC_PRODUCT_CLI_ONE_PASS_TWO_PASS_QUALIFIED`.

The public `plan create`, `plan validate`, `run prepare`, `run inspect`, `run start`/`run resume`, `run status`, `artifacts list`, `artifacts verify --deep`, and `support-bundle create` lifecycle completed on the fixed C1 one-million-pair ERR188044 fixture. The tested implementation commit was `74cffb8fa8c40be3fcf2a99f60c4563ed88fbd88` with tree `b95b1cbfb96c2228e1f552a22954d0e5b25daa1d`.

The product freezes the Ubuntu verified task-image closure's `SAMTOOLS` role for BAM validation. Both runs used `sha256:b762af53a769d82aa0111bfbc4574c8bb8c07f9257a8e09c8403c4f540a10a07` with `--pull=never`; the historical static validator image was not used. The original retained P1 lacked a frozen SAMTOOLS-role contract and was left unchanged and superseded, rather than being mutated during resume.

P1 used `parabricks_star_one_pass_workstation` with resource contract `ubuntu_native_rtx3090_ram128_one_pass_42gb_v1` (42.GB, 12 CPUs, `--two-pass-mode None`). P2 used `parabricks_star_two_pass_high_memory` with `ubuntu_native_rtx3090_ram128_two_pass_96gb_v1` (96.GB, 12 CPUs, `--two-pass-mode Basic`). Both used `--low-memory`, `--quantMode TranscriptomeSAM GeneCounts`, `sjdbOverhang=74`, FeatureCounts `-t exon -g gene_type`, and recommended-only Salmon 2.5.1. No manual Nextflow process override, CPU STAR fallback, or hidden nf-core Salmon execution was used.

Both runs reached `COMPLETED`, each with 37 completed Nextflow tasks and no failed tasks. BAM quickcheck, coordinate sort, `@SQ`, `@RG`, reference consistency, STAR GeneCounts, junctions, Salmon 2.5.1, transcript/gene matrices, MultiQC, Nextflow report/timeline/trace/DAG, deep artifact verification, and sanitized support bundle checks passed. Support bundles contained no FASTQ, BAM/BAI, quantification outputs, matrices, reference/index data, Docker layers, plugin binary, or credentials.

Salmon 1.10.3 remains visible and executable as the bounded-numerical compatibility profile. Its exact historical full-human identity is known, but the complete ProfileIndex and 15-file index tree were not present in the authorized Ubuntu asset roots. Q1/Q2 were therefore not run; status is `PENDING_TARGETED_ASSET_HANDOFF`, not rejected. Salmon 2.5.1 remains the default recommendation.

This qualification is limited to the fixed C1 input, exact full-human assets, verified Ubuntu native RTX 3090/128-GB host receipt, and product contracts recorded in the adjacent JSON. It does not qualify arbitrary hosts, establish biological truth or clinical use, enable native scientific GUI launch, or evaluate cross-host equality.
