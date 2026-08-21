# GUI accessibility-informed audit

Harako-GPU applies a WCAG 2.2 AA-informed technical audit to its local
Streamlit GUI. This is not a formal WCAG conformance claim. Automated checks do
not replace assistive-technology or external-participant evaluation.

The audit covers keyboard operation, logical focus order, visible browser and
Streamlit focus indication, absence of keyboard traps, accessible widget names,
heading order, labels and instructions, error summaries, status messages,
color-independent meaning, reflow, target size, predictable navigation, and
Japanese/English claim parity. The app supplies one H1 and a page H2, preserves
the framework focus outline, gives buttons a 44-pixel minimum height, and gives
each error summary both a textual severity and actionable correction.

The Edge browser audit exercises Tab navigation and confirms multiple distinct
focus targets without returning focus to the document body. Native radio,
select, checkbox, button, and expander keyboard semantics remain those of
Streamlit 1.60.0. We do not inject unsupported focus movement after validation;
the page-level error summary and field-local messages identify corrections.

Reflow is checked at 1920×1080, 1366×768, 1280×720, approximately 900 pixels,
and an effective 200% narrow viewport. Long technical values are placed in
expanders or wrapped code blocks. Large matrices are bounded by the existing
row, column, and byte gates. Status auto-refresh can be paused, manually
refreshed, or set to two/five seconds; pausing polling does not stop the run.
The bounded reader keeps the last valid snapshot and labels it stale rather
than inferring a state.

Contrast uses Streamlit's default theme. No custom status colors replace text
labels. Streamlit-controlled component internals, focus-announcement timing,
screen-reader live-region verbosity, and disabled-control contrast remain
known limitations requiring external assistive-technology evaluation.

