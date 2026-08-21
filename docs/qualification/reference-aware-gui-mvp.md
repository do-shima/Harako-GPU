# Reference-aware GUI MVP qualification

## Completion classification

`HARAKO_GPU_REFERENCE_AWARE_GUI_MVP_QUALIFIED`

## Identity and implementation

Start commit: `6f6a106a4e431d6b0c0f8c1089719940f360bc30` on
`feat/reference-aware-gui-mvp`. The start gate passed 275 tests and all fixed
Windows/WSL/Docker/reference/backend/source identities. Streamlit 1.60.0 was
selected from the exact read-only Harako-RNAseq commit and verified under
Python 3.12.

The fixed eight-page GUI delegates capability, canonical plan/series identity,
prepare/approval, execution/status/resume, artifacts, support bundles, and
handoff to existing services. Only the GUI launcher adapter creates processes;
core/services do not import Streamlit. Default binding is loopback-only.

## Runtime evidence

- Loopback server health returned HTTP 200 `ok` at `/\_stcore/health`.
- Human 1M recommended-only run `20260817T120140Z-fb0d7922` completed all nine
  tasks in 78 seconds. Artifact verification was complete with no failures;
  BAM/BAI/STAR/GeneCounts/MultiQC were `NOT_APPLICABLE`. A sanitized support
  bundle was created.
- Human 1M compare-both run `20260817T120506Z-b41f8c39` completed all twelve
  tasks in 192 seconds. Both fixed Salmon profiles used identical processed
  FASTQ, all 39 artifacts validated, and concordance tables/report were
  generated with no STAR comparator.
- The first small-BAM GUI run retained a FAILED `NEXTFLOW` attempt when the
  unbounded 72-GB nf-core request exposed that the exact small-fixture
  qualification selector had not been projected. Its logs and support bundle
  remain historical evidence. The GUI service was fixed to select only the
  existing exact small-reference x3/30-GB qualification mode; no scientific
  parameter or human capability was changed.
- Fresh small-reference GPU BAM run `20260817T121311Z-19125d89` completed 38/38
  Nextflow processes and nine controller tasks in 109 seconds. BAM/BAI, STAR
  log/junction/GeneCounts, Salmon 2.5.1, matrices, MultiQC, Nextflow reports,
  and Harako report all validated.
- GUI high-memory handoff export wrote the fixed full-human reference/index,
  backend/profile, host-class, and prior-failure identities with both
  `contains_biological_data` and `contains_credentials` false.
- GUI child controllers outlived the short launching process and remained
  observable through independent bounded status reads, proving page/browser
  rerun and Streamlit-server reconnection behavior without a daemon.

The existing fixed fail-once qualification retains FAILED→resume→COMPLETED and
cached-work evidence. GUI tests verify the same exact structured resume action,
state gate, support action, and completed-run suppression. No biological run
was forced to fail.

## Polling and equivalence

The status stress test performed 1,000 atomic writer updates with concurrent
reads and observed no corrupt JSON or state regression. Injected UNC sharing
denial recovered on the third bounded attempt; exhausted reads retained the
last valid stale snapshot. GUI-generated Q1 plan ID
`fb0d79228a2e440cae76ba3363ec12b6bded8429377098aed9202257b8b4d189`
was accepted unchanged by `harako-gpu plan validate`; frozen route, profile,
reference, library type, series identity, and approval hash were shared by GUI
and CLI.

Loopback health was ready in 0.72 s. Fixed Q1 FASTQ discovery took 0.040 s,
capability projection 0.009 s, a status read 0.036 s, bounded 20-row matrix
preview 0.017 s, and self-contained report read 0.039 s. The idle health-only
server process showed about 5.2 MB working set before a browser WebSocket
session; this is diagnostic, not a production sizing claim. Two-second polling
is therefore materially below scientific-stage CPU/I/O load.

## Limits

Local single user only. No authentication, remote-bind qualification, cancel,
delete/archive, custom reference, full-human BAM, DESeq2/enrichment, daemon,
queue, or general background service. Human quantification is CPU-only.
Research use only; non-diagnostic and non-clinical.
