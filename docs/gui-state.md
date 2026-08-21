# GUI state contract

Streamlit session state contains only draft selection and display state:
project/slug, sample edits, fixed reference/route/profile choices, explicit
library type, active page/language, current run directory, and the last valid
status snapshot. Defaults are copied per session and keys are centralized in
`ui/state.py`.

Frozen plans, approval identity, run/task/artifact state, locks, and results
remain in the immutable run directory. The run query parameter permits browser
refresh and a new session to reconnect. A draft changed after prepare creates a
new plan/run; it never edits the prepared run.

Auto-refresh enabled/disabled and the two/five-second display interval are
UI-only preferences. They are excluded from draft, plan, series, and approval
hashes. The last valid snapshot may be displayed with an explicit stale label;
it never becomes scientific source of truth.
