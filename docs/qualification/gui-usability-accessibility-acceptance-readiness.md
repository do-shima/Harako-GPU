# GUI usability, accessibility, and acceptance-readiness qualification

## Completion classification

`HARAKO_GPU_GUI_USABILITY_ACCESSIBILITY_ACCEPTANCE_READY_WITH_LIMITATIONS`

The GUI is ready to begin actual external-user acceptance. External-user
acceptance has not been performed, and no participant result is represented in
this qualification. The residual limitations are Streamlit/browser-controlled
MINOR accessibility items; there are zero unresolved CRITICAL or MAJOR issues.

## Repository and commits

Qualification started from `ba3018640fc4f433733530cbebe2d56329461434` on
`test/gui-usability-accessibility-acceptance-readiness`, exactly equal to
`origin/main`. Required ancestor
`39c9bdfc594b2781f8fb2bd51277a49eb86bf6ca` was present, the tree was clean,
Python was 3.12.13, Streamlit was exactly 1.60.0, and 298 start-gate tests passed.

## Qualification levels

Level 1 automated functional UI passed through AppTest, local Edge/Playwright,
polling, state, wording, route, result-summary, performance, and architecture
tests. Level 2 developer-mediated walkthrough passed using public retained
fixtures and six runtime screenshots kept outside Git. Level 3 remains
`PENDING_EXTERNAL_USERS`; only its protocol, forms, instructions, and frozen
thresholds are supplied.

## Personas and critical scenarios

Personas A–F cover a non-CLI biomedical researcher, method comparator, BAM
collaborator, small-reference GPU user, recovery user, and returning user.
Their knowledge, task, mental model, misconception, and success criteria are
fixed in `docs/usability.md`.

The nine scenarios passed by a combination of retained GUI-MVP runtime evidence
and this goal's presentation walkthrough: human recommended quantification;
human compare-both; blocked human BAM plus handoff; small-reference GPU BAM;
failure/support/resume contract; existing-run reconnection; English/Japanese
Review parity; keyboard-only Project→Review; and narrow/200%-equivalent route,
Review, Run, and Results presentation. No new biological workflow was required.

## Critical mental models and information architecture

Before preparation and again in Results, the interface states whether GPU and
BAM are used, what is absent from quant-only, which profile is primary, why a
secondary exists, and why human BAM is blocked. Every page has one purpose and
one completion condition plus a blocker only when applicable. Default views
prioritize route/BAM/GPU/profile/limitation/next action; hashes, images, indices,
and evidence remain available in technical-detail expanders.

## Terminology and warning hierarchy

Default wording uses expression quantification, BAM generation, GPU alignment,
reproducibility-first, compatibility-first, compare both, method sensitivity,
verified range, resume, and support information. FASTQ, BAM, TPM, and GPU have
short first-use explanations. Five message levels—Information, Limitation,
Warning, Blocked, and Failure—include text, icon/shape, heading, explanation,
and next action. No status relies on red/green alone.

## Accessibility target

The audit is WCAG 2.2 AA-informed and is not a formal conformity claim. Edge
confirmed one H1 followed by the page heading, accessible names for language
and navigation, visible focus, at least six distinct Tab targets, no observed
keyboard trap, and keyboard activation with Space/Enter. Validation presents a
page summary plus field-local correction rather than unsupported focus forcing.

Viewport checks covered 1920, 1366, 1280, and 900 pixels plus 720, 600, and 450
CSS-pixel reflow equivalents for 125%, 150%, and 200% zoom on the critical
narrow layout. Document-level overflow was zero. Long paths use bounded wrapped
code; matrices remain byte/row/column bounded. Streamlit default contrast is
retained and custom CSS does not suppress focus.

## Status polling accessibility

Run status can auto-refresh every two or five seconds, be paused, or refresh on
demand. These are UI-only preferences excluded from canonical plan and approval
identity. Polling remains fragment-scoped; pause does not stop a run. Bounded
retry retains and labels the last valid stale snapshot and never guesses a run
state. The retained 1,000-update regression observed no corrupt JSON or state
regression.

## Capability and profile comprehension

The human BAM choice remains visibly unavailable with host-memory reason and an
explicit handoff action. Quant-only explicitly says no BAM, junction,
GeneCounts, or GPU. The exact small reference exposes GPU BAM. Discard remains
visible and disabled. No route is silently selected.

The two visible profile cards identify Salmon 2.5.1 as recommended and 1.10.3
as compatibility-oriented. Compare-both requires a primary, visually labels the
other profile comparison-only, and explains that method sensitivity is not an
error verdict. Salmon 1.12.1 remains hidden.

## Error prevention and Results comprehension

Existing service gates continue to prevent unsupported human BAM, missing
library type, duplicate/orphan samples, missing compare primary, unsafe paths,
duplicate start, and invalid resume. The GUI adds nearby reasons instead of an
unexplained disabled action. Results now lead with Generated and Not generated,
then primary and comparison-only secondary. Provenance hashes moved into an
expander after the initial audit found they obscured the result summary.

## Bilingual parity

Japanese and English catalogs have identical key sets, zero placeholder labels,
and equivalent BAM/GPU/profile/limitation claims. Literal versions and hashes
are not translated. The Project and Review walkthroughs verified both language
paths.

## Browser tests and AppTest

Playwright 1.62.0 is exact-pinned as a test-only dependency and used the existing
local Edge executable. No browser binary is committed or downloaded by the
test. The browser run passed keyboard, focus, heading/name, fixed-navigation,
and seven-width reflow assertions. AppTest passed initial navigation, Japanese
rerun, state isolation, route wording, status retry, reconnection, and existing
GUI equivalence regressions. Streamlit's automatically discovered duplicate
module navigation was found during visual review and removed through the fixed
`--client.showSidebarNavigation false` launcher argument.

## Developer walkthrough and issue severity

Runtime screenshots `GUI-WALK-01`–`06` remain outside Git. The keyboard-only
Q1 path reached enabled Review in 6.754 seconds with zero mouse clicks. Human
quant-only Results correctly showed no BAM/GPU; failed Recovery showed its
NEXTFLOW classification, preserved attempt, support action, and resumability.
Times are technical baselines, not user-performance claims.

Resolved MAJOR: duplicate automatic Streamlit module navigation. Resolved
MINOR: raw provenance hashes preceding Results. Unresolved CRITICAL: 0.
Unresolved MAJOR: 0. Residual MINOR limitations are listed in
`docs/known-limitations/gui-accessibility.md`.

## External acceptance protocol and criteria

The protocol recommends two non-CLI biomedical researchers, one RNA-seq
researcher, and one technical user, all anonymous role codes. It uses public
fixtures only and collects no names, patient/study identifiers, credentials, or
unconsented recordings. Frozen thresholds are 80% unassisted completion per
critical task, 80% BAM/GPU/primary comprehension, zero unsafe/silent-fallback/
data-loss actions, zero CRITICAL, and zero unresolved MAJOR issues. The results
template contains empty arrays and status `PENDING_EXTERNAL_USERS`.

## Performance and responsiveness

Observed locally: health 0.536 s, capability 0.014 s, status poll 0.024 s,
matrix preview 0.019 s, report load 0.040 s, 100-file scan 0.020 s, and
1,000-file scan 0.187 s. All fixed targets passed. Polling remains negligible
relative to scientific execution and large matrices are never loaded in full.

## Fixes and tests

Fixes were limited to presentation and launcher configuration: centralized
bilingual guidance, semantic messages, page introductions, error summary,
discoverable BAM limitation/handoff, primary/secondary explanation, polling
controls, generated/not-generated summary, progressive provenance disclosure,
wrapped paths, target height, and duplicate-navigation suppression. Scientific
capability, route, threshold, plan identity, and backend output were unchanged.

Full pytest: 308 passed and one explicitly gated browser test skipped in 14.34
seconds. The browser test was then run explicitly: one passed in 5.58 seconds.
Python compile, architecture boundaries, JSON parsing, and diff checks are part
of terminal verification.

## Qualified and unqualified scope

Qualified: readiness to begin local external acceptance for the existing fixed
routes, profiles, preparation/status/results/recovery surfaces, Japanese and
English, keyboard use, and tested reflow widths. Unqualified: actual external
acceptance, formal WCAG conformance, screen-reader/voice/switch participant
use, remote bind, authentication, cancel, custom reference, full-human BAM,
DESeq2, enrichment, diagnostic, and clinical use.

## Recommended next goal

Conduct the prospectively frozen external local-user acceptance protocol with
anonymous participants. Resolve any observed CRITICAL/MAJOR issues without
changing thresholds after results are known, then publish only an anonymized
aggregate acceptance record.

