# Native high-memory full-human two-pass qualification

Classification: `FULL_SIZE_TWO_PASS_END_TO_END_QUALIFIED_96GB`.

The normalized `ubuntu-high-memory-host-capability-v1` evidence bundle records a terminally successful full `ERR188044` two-pass run on the fixed Ubuntu native RTX 3090 / 128-GB host class. The fully-qualified Parabricks process alone used contract `ubuntu_native_rtx3090_ram128_two_pass_96gb_v1`: 96.GB, 12 CPUs, `--two-pass-mode Basic`, `--low-memory`, `--quantMode TranscriptomeSAM GeneCounts`, and `sjdbOverhang=74`. Its cgroup peak was 80,275,611,648 bytes with no cgroup or host OOM and no CPU STAR fallback.

BAM quickcheck, STAR GeneCounts, FeatureCounts `-t exon -g gene_type`, deterministic Salmon 2.5.1, matrices, MultiQC, and the verified `harako-gpu-terminal-results-archive-v1` receipt passed. The archive receipt SHA-256 is `71d5a3fa60c569d3ddf84c6696acf0d338379e012205a6c845ac69df5a5ad711`.

Source identities are frozen in the adjacent JSON. The normalized evidence SHA-256 is `d13224114bdd9990bb4d299a654982380fcb85c253e95ee99120447be758f324`; the source report SHA-256 is `48b3af66048e4e111c880c04aa0d1ee48b6679a6cb332a2718fb867e8ce16569`. No external report, private absolute path, or biological artifact is copied here.

This qualifies only the fixed public input, assets, profile, resource contract, and host class. It does not establish arbitrary-hardware support, biological accuracy, diagnostic or clinical use, scientific superiority, or cross-host BAM equality. Product Docker provenance remained pending in the scientific-run evidence and is a separate product availability gate.
