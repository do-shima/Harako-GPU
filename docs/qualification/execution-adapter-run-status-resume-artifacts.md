# Execution adapter run/status/resume/artifacts qualification

## Completion classification

`HARAKO_GPU_EXECUTION_ADAPTER_RUN_STATUS_RESUME_ARTIFACTS_QUALIFIED`

## Scope and identity

Start commit was `c34c6006433b48361ae97132af5f3732263737b8` on
`feat/execution-adapter-run-status-resume-artifacts`. The required ancestor,
193-test minimum, Docker/WSL/Java/Nextflow, fixed images, versioned indices,
profile/series/concordance contracts, and WT_REP1 runtime assets all passed the
start gate. The run snapshot resolved nf-core/rnaseq 3.26.0 commit
`e7ca46272c8f9d5ceee3f71759f4ba551d3217a4`, verified the existing patch, and
added fixed `TranscriptomeSAM GeneCounts` configuration. No mutable remote
pipeline was executed.

## Lifecycle and execution

Preparation freezes plan/approval/reference/profile/series/params/config,
structured argv/env, pipeline inventory, and path roles before analysis.
Approval mismatch, live lock, unsafe/mounted path, image/index/reference or
snapshot mismatch fail closed. WSL execution uses the fixed JSON exec runner;
native Linux shares the structured process projection. Mutable state is atomic.

The fixed lifecycle fixture failed once with exit 42, retained attempt 0001,
then succeeded with `-resume`; attempt 0002 reported one cached and one newly
completed task. During WT_REP1 a separate status command observed `RUNNING`,
current nf-core stage/task, elapsed time, task counts, GPU/VRAM/RAM/disk, and
the watch contract did not control the run. A deliberately terminated stale
controller lock was archived, classified `INTERRUPTED`, and successfully
resumed without changing plan/snapshot/work.

The final recommended-only run first stopped at artifact verification because
of a validator defect, correctly retained the successful scientific stages as
non-terminal evidence, and resumed as attempt 0002 after the defect was fixed.
Six validated tasks were reused and only the invalid/pending terminal work was
rerun. This is retained as real application-level failure/resume evidence.

## Runtime modes

- recommended-only run `20260817T033359Z-088c586f`: Salmon 2.5.1 deterministic,
  STAR GeneCounts, matrices, report, and artifacts completed. Attempts 0001 and
  0002 are retained; the run ended `COMPLETED` after 199 seconds elapsed.
- compatibility-only run `20260817T033744Z-46d30edf`: 39/39 Nextflow processes,
  nine fixed tasks, `COMPLETED` in 103 seconds.
- compare-both run `20260817T033952Z-69ee2e22`: primary 2.5.1 then secondary
  1.10.3 sequentially from identical processed FASTQ, 39/39 Nextflow processes,
  twelve fixed tasks, STAR/profile concordance and self-contained report,
  `COMPLETED` in 108 seconds.

Trace contained Parabricks alignment and zero native STAR alignment, BAM-based
Salmon, or nf-core FASTQ Salmon processes. Deep verification hashed all selected
artifacts and returned no failures. Both successful modes retained BAM/BAI,
STAR log/junction/ReadsPerGene, MultiQC, trace/report/timeline/DAG, profile
outputs/matrices, and report.

The completed-run public resume command was rejected as required. A separate
qualification harness replayed the exact frozen nf-core snapshot, params,
config, launch directory, and work directory with `-resume`: 38 processes were
cached and the time-bearing MultiQC report was regenerated. BAM/BAI, STAR log,
junction, and ReadsPerGene SHA-256 values were unchanged.

## Reproducibility and multi-sample evidence

Three fresh 2.5.1 repeats produced one identical quant.sf SHA-256. Three fresh
1.10.3 repeats produced three byte hashes while retaining Spearman 1.0, top-100
overlap 1.0, and no zero transitions, confirming bounded numerical behavior.
Fresh truth-v2 execution ran six biological samples through both fixed profiles,
preserved sample/feature order, created all profile-specific matrices and only
descriptive condition fold change (no P value, FDR, DEG, or enrichment).

## Artifacts and support

Default/deep structural and identity verification passed. Successful and failed
run support ZIPs were generated with role redaction and without biological
artifacts or secrets. Failed-task collection is hash-bounded to the declared
work root and rejects ambiguous paths/symlink escape. The final ZIP contained
28 manifest entries, no biological filenames, no absolute user home, no test
secret literal, and a 64-character SHA-256 for every entry.

## Limits

Foreground local single-user execution only. No daemon, cancel/delete/archive,
cluster/cloud scheduler, GUI, DESeq2/enrichment, BAM deletion, full-size human
qualification, or automatic reference/image/index acquisition. Native Linux is
contract/unit qualified; this machine's runtime evidence is Windows+WSL2.
Small-fixture performance is not extrapolated.
