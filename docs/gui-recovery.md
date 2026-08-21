# GUI recovery and support

The recovery view reads attempt history, failure classification, failed stage
and task, lock status, resumability, logs, and artifact status through existing
services. Resume is offered only for FAILED/INTERRUPTED resumable runs with the
same approval identity and no live lock. COMPLETED cannot resume and BLOCKED
requires a new preparation.

Artifact verification supports normal and explicit deep modes. Support bundle
creation retains existing redaction and biological-data exclusions. The view
has no force-unlock, force-resume, delete, archive, BAM removal, or arbitrary
command action.

Failure views label the failure class, user-facing explanation, preserved
evidence, and next action. Results instead lead with generated/not-generated
artifacts and identify the primary profile; comparison-only secondary output is
visually and textually subordinate.
