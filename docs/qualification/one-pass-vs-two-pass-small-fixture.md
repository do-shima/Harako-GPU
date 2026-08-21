# One-pass versus two-pass small-fixture comparison

WT_REP1 completed with the explicit one-pass command. The actual Parabricks
task contained `--two-pass-mode None` and no `Basic`; `TranscriptomeSAM` and
`GeneCounts` remained enabled. One Parabricks task ran, while native STAR and
nf-core Salmon tasks remained at zero.

One-pass and historical two-pass total mapping were both 89.95%. Unique
mapping was 88.12% versus 88.04%. The BAMs passed quickcheck but differed in
record count (88,586 versus 88,628). STAR reported 534 versus 693 splice
events, and the exact SJ row sets overlapped in 4 of 19 rows. These are
descriptive method/profile differences, not an equivalence or correctness
verdict.

Selected GeneCounts had 124 common genes, Spearman 1.0, and no zero/non-zero
transition. Salmon 2.5.1 `quant.sf` was byte-identical because both runs used
the same processed FASTQ and index. Salmon 1.10.3 retained feature identity and
the same 47,605 processed fragments; byte identity was not required.

The one-pass run completed in 96 seconds, peaked at 18,170,785,792 bytes WSL
RAM and 9,626 MiB VRAM. These tiny-fixture resources do not predict the
full-human result.
