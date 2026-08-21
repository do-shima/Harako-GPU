# GUI capability display

The UI displays, but does not calculate, the versioned capability-service
result. Cards include exact host profile, reference pack/resource class,
requested BAM mode, route, GPU/BAM flags, reason, evidence, allowed action, and
forbidden fallback.

- GRCh38.p14/GENCODE 49 + BAM `none`: CPU-only quantification, available.
- The same reference + BAM `keep`: disabled on this host; high-memory handoff
  is available.
- Exact small reference + BAM `keep`: qualified GPU alignment.
- `discard_after_validation`: visible but disabled because deletion is not
  implemented.

No request is silently converted. Human quant-only capacity messaging is one
sample, sequential execution, recommended to 20M pairs and tested to 36.35M.
It is not extrapolated to custom references or concurrent samples.

Disabled choices remain visible with a textual Limitation/Blocked heading, an
explanation, and an explicit alternative action. The human-BAM handoff is
discoverable without first selecting an impossible route. BAM, FASTQ, TPM, and
GPU receive short first-use explanations; exact evidence remains under
technical details.
