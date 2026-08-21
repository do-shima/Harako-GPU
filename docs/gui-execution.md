# GUI execution and polling

Only `adapters/gui_launcher.py` creates GUI-related processes. Streamlit is
launched by exact Python executable and structured argv. Start/resume launches
`python -m harako_gpu run start|resume` with the exact run directory and
approval hash, `shell=False`, fixed cwd, and controller logs. The existing run
lock/state machine remains authoritative and rejects duplicate launch.

Status uses the application status service at a two-second default interval.
The reader performs six bounded retries with increasing 50 ms backoff, keeps
the last valid snapshot on transient UNC sharing denial, rejects older
timestamps, and never infers completion. The existing writer uses atomic
same-directory replace with the matching bounded retry contract. Browser/tab
closure and Streamlit reruns do not stop an already launched controller;
reconnection reads the run directory. No daemon or global detached job service
is introduced.

Users may pause automatic polling, refresh manually, or select a two/five-
second interval. Polling pause never pauses or cancels execution. Fragment-
scoped updates avoid unnecessary whole-page replacement, and stale reads keep
the last valid snapshot with a textual warning. Screen-reader live-region
behavior remains Streamlit-controlled and awaits external evaluation.
