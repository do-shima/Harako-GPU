# GUI usability and acceptance-readiness contract

This contract prepares the local reference-aware GUI for external user
acceptance; it is not itself evidence that external users accepted the product.
The qualification has three levels: automated functional UI tests,
developer-mediated walkthroughs, and external user acceptance. The first two
are performed here. The third remains `PENDING_EXTERNAL_USERS`.

## Personas and success criteria

| Persona | Prior knowledge | Critical task | Expected mental model | Likely misconception | Success criterion |
|---|---|---|---|---|---|
| A — biomedical researcher | No command line | Human FASTQ, recommended quantification, gene TPM | CPU quantification can run without BAM | “Harako-GPU always uses a GPU” | Prepares the quant-only route and finds the primary gene TPM matrix |
| B — method comparator | RNA-seq concepts | Compare both Salmon profiles | One primary; secondary is descriptive | Both profiles feed downstream analysis | Identifies 2.5.1 as primary and explains method sensitivity |
| C — BAM collaborator | Needs genomic alignment | Explain blocked human BAM and export handoff | BAM requires a separately qualified high-memory host | Disabled BAM silently becomes quant-only | Finds the reason and handoff without starting a different route |
| D — small-reference GPU user | Basic alignment knowledge | Qualified small-reference BAM | GPU accelerates alignment; Salmon remains CPU-based | Human and small reference have the same capability | Finds BAM, GeneCounts, and MultiQC artifacts |
| E — recovery user | Has a failed run | Evidence, support bundle, resume | Resume preserves the immutable run | A force operation or new parameters are needed | Finds the failed stage and uses only supported recovery actions |
| F — returning user | Has a run path | Reconnect to CLI/GUI run | Run directory, not browser state, is authoritative | Refresh loses or restarts the run | Reconnects without a duplicate start |

## Critical mental models

Before Review and again at Results, wording must establish that human
quantification-only uses no GPU and generates no BAM; human BAM is unavailable
on this host; exact small-reference BAM does use GPU alignment; Salmon 2.5.1 is
recommended; 1.10.3 is for compatibility; compare-both still has one primary;
profile differences need not be errors; closing the browser does not stop a
run; recovery uses resume/support evidence; prepared inputs require a new
prepare to change; and every report is research-only and non-diagnostic.

## Critical scenarios

The fixed scenarios are: human recommended quantification, human compare-both,
blocked human BAM plus handoff, small-reference GPU BAM, failure and resume,
existing-run reconnection, English Review parity, keyboard-only Project to
Review, and route/Review/Run/Results at 200% zoom or a 900-pixel narrow desktop.
Runtime biological outputs from the GUI MVP qualification are reused read-only;
this goal does not rerun full-human BAM.

## Information and message hierarchy

Every page declares one purpose and one completion condition. A current blocker
is displayed only when present. Default views show the user-facing route, BAM,
GPU, primary profile, limitation, and next action. Versions, digests, index IDs,
plan IDs, approval hashes, reference checksums, and technical evidence remain
available under technical-detail expanders.

Messages use five textual levels—Information, Limitation, Warning, Blocked, and
Failure—with an icon/shape, concise heading, explanation, and next action.
Color is never the only carrier of meaning. User-facing terms prefer expression
quantification, BAM generation, GPU alignment, reproducibility-first,
compatibility-first, compare both, method sensitivity, unavailable on this
host, verified range, resume, and support information. Advanced details retain
the exact technical vocabulary.

## Developer walkthrough record

The developer-mediated walkthrough on 2026-08-17 used local Edge in headless
browser automation plus manual screenshot inspection. It included English and
Japanese Project views, keyboard traversal, a completed human quant-only
Results view, a 450-CSS-pixel viewport representing a 900-pixel viewport at
200% zoom, and a failed-run Recovery view. Runtime screenshot IDs are
`GUI-WALK-01` through `GUI-WALK-06`; screenshots remain outside Git and contain
no participant data. The narrow Results view had zero document-level horizontal
overflow. The keyboard-only Project→Samples→Reference→Analysis→Review path used
focus plus Tab/Space/Enter and reached an enabled Prepare action in 6.754
seconds with zero mouse clicks, moderator interventions, wrong-route starts, or
critical misconceptions. Timing is a technical baseline, not a user-performance
claim. This is developer evidence, not external user acceptance.

Issue severity is fixed as CRITICAL, MAJOR, MINOR, and COSMETIC. Qualification
requires zero CRITICAL and zero unresolved MAJOR issues. The initial audit found
an information-hierarchy issue in Results (provenance hashes preceded the user
summary); it was corrected by moving hashes to a technical-detail expander.
