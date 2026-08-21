# Transcriptome BAM grouping compatibility

> Follow-up: the product candidate no longer attempts to repair this BAM for
> quantification. Parabricks transcriptome BAM remains provenance-only; the
> independent branch consumes the same nf-core fastp FASTQ as Parabricks and
> uses Salmon mapping mode on CPU.

Classification: `HARAKO_GPU_MAPPING_BASED_SALMON_FALLBACK_REQUIRED`

The public small paired-end fixture demonstrates that `samtools collate`
1.23.1 repairs QNAME contiguity without changing alignment records, but does
not restore the fixed Salmon numerical-reproducibility gate. No tolerance was
relaxed, no value was rounded, and no Salmon, Parabricks, or nf-core version
was changed.

## Runtime and input identity

The experiment retained nf-core/rnaseq 3.26.0 at resolved commit
`e7ca4627...217a4`, Nextflow 25.04.3, Parabricks 4.6.0-1, Salmon 1.10.3, and
the prior RTX 3090 fixture. The five raw transcriptome BAMs contained 73,886
records and 32,980 unique QNAMEs. Their canonical record multiset was one
value, `24794464...b1ca3f`, while all five byte and record-order checksums were
different.

Raw order produced 33,011-33,030 contiguous QNAME groups and 31-50 split
QNAMEs. In every retained raw Salmon run, `num_processed` and `num_mapped`
equalled the contiguous group count exactly rather than the unique-QNAME
count. A raw Parabricks transcriptome BAM therefore fails the Salmon-ready
input contract and is rejected by the Harako contract.

## Formal Salmon-ready BAM contract

The version-1 contract requires all records for a QNAME to be contiguous,
split QNAME count zero, and group count equal to unique QNAME count. It also
requires preservation of record count and multiset, primary/secondary/
supplementary/unmapped counts, paired flags, tags, non-order header content,
and reference dictionary. A grouping tool may update only the `@HD` order
declaration to describe its output. Group order must be neither target-sorted
nor coordinate-sorted.

Artifacts have separate roles:

- `raw_transcriptome_bam`: native Parabricks provenance; never presumed
  Salmon-ready;
- `salmon_ready_transcriptome_bam`: an output that passed grouping and
  fragment-accounting contracts, with tool and parameter provenance.

These roles do not alter the user-facing genomic coordinate-sorted BAM or its
retention state machine.

## Candidate A: samtools collate

The fixed command used samtools 1.23.1 from
`community.wave.seqera.io/library/htslib_samtools:1.23.1--5b6bb4ede7e612e5`,
digest `sha256:6df2a435...cd7f0`:

```text
samtools collate --no-PG -@ 2 -n 64 -T <fixed-prefix>
  -o <salmon-ready.bam> <raw-transcriptome.bam>
```

Fast mode `-f` was not used. Ten executions against one raw BAM were 10/10
successful and byte-identical (`30ae28b8...c6e1`). Each output had 73,886
records, 32,980 QNAMEs/groups, zero split QNAMEs, the unchanged record
multiset, 65,960 primary and 7,926 secondary records, no supplementary or
unmapped records, and unchanged flags, tags, read group, and reference
dictionary. The added `@HD VN:1.6 SO:unsorted GO:query` correctly declares the
new order. Outputs were neither target nor coordinate sorted.

Wall time was 1.89-2.18 seconds and output size was 4,369,775 bytes versus a
4,841,175-byte input. The wrapper-observed maximum RSS was 25,852 KiB; this is
not a container-internal peak-RAM qualification. Temporary bucket files were
removed by samtools on success, so peak scratch was not directly measured.
Full-size planning must reserve additional scratch on the order of the input
transcriptome BAM rather than extrapolate this small fixture.

## Candidate B: queryname-sort control

`samtools sort --no-PG -n -@ 2` was evaluated only as a diagnostic control. It
also produced 32,980 complete groups, zero splits, and an unchanged record
multiset. Its queryname order is not a random-order guarantee and it remains
forbidden as a production grouping strategy. Against the collate output,
Salmon count estimates differed by as much as 1,224.101 and transcript TPM by
397%; the control demonstrates the expected order sensitivity rather than a
safe replacement.

## Candidate C: deterministic shuffle reference

The Salmon tutorial describes deterministic QNAME grouping and shuffling with
`mudskipper shuffle`. The only upstream tag is v0.1.0, peeled commit
`59ba072b...54cc0`; it has no release binary. No mudskipper binary, container,
or Rust toolchain was present locally. A new unpinned build environment was
not downloaded or installed, so this reference is `NOT_RUN`, not PASS. It was
not adopted as a production dependency.

References:

- https://combine-lab.github.io/salmon-tutorials/2021/mudskipper-shuffle/
- https://github.com/OceanGenomics/mudskipper/tree/v0.1.0

## Salmon results after collate

Ten fresh Salmon executions on one byte-identical grouped BAM had exact
processed/mapped fragments at 32,980, exact IDs/order, exact total NumReads,
and no zero-state transition. Nevertheless, `quant.sf` and gene quantification
had ten distinct byte hashes. Maximum NumReads difference was 2.111,
EffectiveLength difference 0.030, and transcript/gene TPM >=1 relative
difference was 0.8010%/0.8011%. The fixed 0.1% ceiling failed.

The five retained fresh Parabricks BAMs were then independently collated and
quantified. All grouping and Salmon commands succeeded, records and unique
QNAME counts were invariant, and fragments were fixed at 32,980. However, the
five collated group-order checksums remained distinct because collate output
depends on raw input order. Across ten pairs, total NumReads was not exact,
maximum NumReads difference was 75.900, EffectiveLength difference 2.398,
minimum transcript/gene Spearman was 0.987543, and zero/non-zero transitions
occurred. Transcript/gene TPM >=1 relative differences reached approximately
399%. This is `MATERIAL_VARIABILITY`.

## Native STAR oracle

The native STAR 2.7.2a transcriptome BAM already had 32,980 contiguous groups
and zero splits. Its reference dictionary and record count matched, but its
full and first-11-field alignment-record multisets differed from Parabricks
(`2d236dab...560e` versus `004688fd...1b37`). Native STAR and grouped
Parabricks Salmon results therefore cannot be treated as an exact grouping-only
comparison. Their processed/mapped fragment counts were both 32,980, but the
expression comparison was materially different; alignment and grouping
effects remain separated rather than forced into an equivalence claim. Native
STAR timing was not used as a GPU performance comparison.

## Patch, pipeline, MultiQC, and resume

The candidate did not pass the numerical gate, so no nf-core grouping patch
was created. The existing SHA-pinned STAR metrics patch was not modified. No
corrected nf-core run, MultiQC regeneration, or resume test was performed, and
none is reported as PASS. The retained qualified genomic BAM and 87.33% STAR
metrics path were not changed or re-generated.

## Decision and boundary

`samtools collate` is qualified only for record-preserving QNAME grouping on
this small fixture; it is not qualified as the Salmon production input fix.
Raw transcriptome BAM input remains fail-closed. Alignment-mode Salmon on the
pinned Parabricks transcriptome output remains unqualified.

The next product strategy is a separate
`HARAKO_GPU_INDEPENDENT_FASTQ_SALMON_QUANTIFICATION` goal: retain Parabricks for
genomic BAM, junctions, and alignment QC, while independently qualifying
FASTQ-based Salmon quantification. This document does not qualify full-size
data, other versions, production use, or diagnostic use.
