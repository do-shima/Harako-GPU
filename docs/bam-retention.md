# BAM retention contract

Schema version: `1`.

The BAM lifecycle is a state machine, not a boolean:

```text
planned -> generated -> verified -> retained -> archived
                    \-> discarded_after_validation
planned/generated -> absent_due_to_failure
not_applicable (terminal and separate)
```

For `keep`, genomic BAM, BAI, and verification results are final artifacts.

For `discard_after_validation`, the transition from `verified` to
`discarded_after_validation` is invalid until every gate is true:

1. alignment process success
2. BAM exists
3. BAM index exists
4. `samtools quickcheck` success
5. coordinate-sort confirmation
6. reference-contig consistency confirmation
7. downstream quantification success
8. required alignment QC success
9. MultiQC success
10. terminal run success
11. finalized artifact manifest

The implemented contract validates these gates. No file-deletion code exists in
this goal. Failure records `absent_due_to_failure`; it must not be reported as a
successful discard.

The retention policy applies to the user-facing coordinate-sorted genomic BAM.
Parabricks raw transcriptome BAM is provenance-only and forbidden as a Salmon
input. FASTQ Salmon quantification has its own artifact identity and is
unchanged by a future genomic BAM keep/discard decision.
