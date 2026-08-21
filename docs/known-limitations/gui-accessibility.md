# Known GUI accessibility limitations

- This is a WCAG 2.2 AA-informed audit, not a formal conformance claim.
- Streamlit 1.60.0 controls internal widget markup, disabled-state contrast,
  focus announcements, and live-region behavior.
- Programmatic focus is not forced after validation; users receive a page-level
  error summary and field-local messages instead.
- A browser/keyboard technical audit was completed, but external screen-reader,
  voice-control, switch-device, and low-vision participant testing is pending.
- Status polling can be paused to reduce repeated updates. Screen-reader
  verbosity during long active runs still requires external-user evaluation.
- The narrow-layout audit found no document-level horizontal overflow, but wide
  artifact tables may use their own bounded horizontal scrolling.

These residual items are MINOR limitations for acceptance readiness. They do
not authorize a formal WCAG claim and must be revisited with external users.

