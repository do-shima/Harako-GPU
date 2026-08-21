# Salmon reproducibility contract

> Follow-up: alignment-mode remains fail-closed. The independent FASTQ mapping
> candidate uses the same tolerance schema and is documented separately in
> `independent-fastq-salmon-quantification.md`; its fixed six-thread repeat gate
> must pass before this path can become execution-qualified.

Classification: `HARAKO_GPU_SALMON_REPRODUCIBILITY_BLOCKED`

Contract decision: `MATERIAL_VARIABILITY` for the fresh
Parabricks-transcriptome-BAM to Salmon path. The comparator and a narrower
frozen-BAM result are valid, but the current backend does not pass the
predeclared release ceiling. No threshold was relaxed and no output was
rounded or rewritten to obtain this result.

This qualification uses only the previously qualified public paired-end test
fixture. It does not qualify a full-size dataset, another Salmon/Parabricks
version, or production use.

## Pinned Salmon identity

The actual nf-core task was
`NFCORE_RNASEQ:RNASEQ:QUANTIFY_BAM_SALMON:SALMON_QUANT`. It used Salmon 1.10.3
from `quay.io/biocontainers/salmon:1.10.3--h6dccd9a_2`, digest
`sha256:f83ebb15...f08e`. The nf-core module SHA-256 was
`0bccc867...9cf3` in rnaseq 3.26.0 at resolved commit
`e7ca4627...217a4`.

The fixed alignment-mode argv was:

```text
salmon quant --geneMap gene_map.gtf --threads 6 --libType=ISR
  -t transcriptome.fasta -a transcriptome.bam -o WT_REP1
```

Sequence and GC bias correction were both false. The frozen transcript FASTA
SHA-256 was `4f6a6733...43ac3`; the gene map was
`3274bed8...fa61`. The container ran as the current WSL user under the same
30-GiB task memory cap and fixed nf-core environment variables for every
repeat.

The pinned binary's `salmon quant --help-alignment` contains neither
`--deterministic` nor a random-seed option. The deterministic candidate is
therefore `NOT_AVAILABLE_IN_PINNED_BACKEND`; no upgrade or unverified option
was introduced.

## Frozen-BAM repeats

The read-only frozen transcriptome BAM had byte SHA-256
`ef611c28...2a179`, normalized-header SHA `13803055...96da`, 73,886 alignment
records, 32,980 unique QNAMEs, and scientific input checksum
`87f73033...5c9db`. Its 33,024 contiguous QNAME groups included 44 QNAMEs split
across multiple groups.

Ten fresh 6-thread Salmon executions produced ten distinct `quant.sf` byte
SHAs and ten distinct exact numerical digests. Across all 45 pairs:

| Gate | Result |
| --- | ---: |
| processed / mapped fragments | exact at 33,024 / 33,024 |
| transcript and gene IDs/order | exact, 124 features |
| total NumReads | exact at 32,775 |
| NumReads maximum absolute difference | 0.001, one output serialization quantum |
| EffectiveLength maximum absolute difference | 0.002 |
| EffectiveLength median / p95 maximum | 0.001 / 0.002 |
| transcript TPM >=1 maximum relative difference | 0.067664% |
| gene TPM >=1 maximum relative difference | 0.067554% |
| transcript / gene minimum Spearman | 1.0 / 1.0 |
| zero/non-zero transitions | 0 |

The 124-feature fixture contained 42 zero-TPM and 82 TPM >=1 features; it had
no features in the two lower non-zero strata. Fragment-length distribution
content differed in all ten executions, with mean 167.350420-167.351984 and SD
68.012431-68.012770. Sequence-bias files were byte-identical and bias
correction was disabled. This localizes frozen-input variation to Salmon's
fragment-length/inference path, not input identity.

The frozen-BAM result is `BOUNDED_NUMERICAL_REPRODUCIBILITY` under tolerance
schema 1. It is not byte-exact reproducibility.

## Thread-count matrix

The same frozen BAM was run three times each at 1, 2, 4, and 8 threads. Within
thread-count maximum TPM relative differences were 0.0385%, 0.0574%, 0.0779%,
and 0.1183%, respectively. The 8-thread group also reached a 0.002 NumReads
difference. Across all thread counts, maximum TPM relative difference was
0.1357% and NumReads difference was 0.002.

The provisional 0.1% ceiling was not changed. Thread count is part of the plan
and quantification identity, and the only selected contract value remains the
actual nf-core task value of 6. The 1/2/4-thread observations are
characterization results, not alternate qualified profiles; 8 threads and
cross-thread identity failed this goal's ceiling.

## Fresh Parabricks repeats

Five fresh Parabricks 4.6.0-1 executions used the same FASTQ, reference, STAR
index, RTX 3090, `--low-memory --x3`, and `--no-markdups`. All five Parabricks
and all five subsequent 6-thread Salmon commands exited zero. Parabricks took
39.016-39.526 seconds. The 165 GPU samples reached 9,537 MiB VRAM, 90%
utilization, and 217.45 W.

The five genomic BAMs had different byte SHAs but one normalized header, one
92,113-record multiset, and one record-order checksum. The five transcriptome
BAMs likewise shared one normalized header and one 73,886-record multiset, but
all five record-order checksums differed. Their scientific record content did
not differ; order did.

Each transcriptome BAM contained the same 32,980 unique QNAMEs. Depending on
record order, those records formed 33,011-33,030 contiguous QNAME groups, with
31-50 QNAMEs split across groups. Salmon reported processed and mapped fragment
counts of exactly 33,011-33,030: in every run the reported count equalled the
contiguous group count, not the unique-QNAME count. Thus fresh Parabricks output
order changes Salmon's fragment interpretation under this pinned alignment
mode.

Across all ten fresh-output pairs, transcript/gene IDs and order, total
NumReads, zero status, and Spearman remained exact. However, processed and
mapped fragment counts were not exact. EffectiveLength differed by up to
0.067, transcript TPM >=1 by 0.257480%, and gene TPM >=1 by 0.257645%. Both TPM
values exceed the predeclared 0.1% ceiling. This is material contract
variability even though rank correlation remained 1.0.

## Selected contract

Tolerance schema version 1 keeps the requested ceilings:

- exact feature sets/order, processed/mapped fragments, library type, total
  NumReads, zero status, and plan/input/reference/container identity;
- one fixed 0.001 NumReads serialization quantum, with total unchanged;
- EffectiveLength maximum absolute difference <=0.1;
- TPM >=1 maximum relative difference <=0.1% at transcript and gene level;
- 0.1<=TPM<1 maximum absolute difference <=0.001;
- transcript and gene TPM Spearman >=0.999999.

The scientific BAM checksum includes normalized header identity, record count,
record multiset, and record order. Byte SHA remains provenance but is not the
scientific identity, while order cannot be omitted because this experiment
shows that it affects alignment-mode Salmon.

Every future quantification manifest must store Salmon version, image digest,
structured argv, thread count, input BAM scientific checksum, transcript FASTA
checksum, `quant.sf` byte SHA, canonical numerical digest, reproducibility
class, and tolerance schema version.

## Qualification boundary and next goal

Qualified here: strict parsers/comparators, BAM content-versus-order identity,
manifest identity schema, and bounded frozen-BAM behavior at six threads for
this small fixture.

Not qualified: the fresh Parabricks-to-Salmon release path, eight-thread or
cross-thread identity, full-size data, other versions, and production or
diagnostic use. Because mandatory fragment identity and the TPM ceiling fail,
Harako-GPU must not proceed to an execution adapter on this backend contract.

Recommended next goal:
`HARAKO_GPU_TRANSCRIPTOME_BAM_GROUPING_COMPATIBILITY`. It should establish an
upstream-supported, scientifically justified QNAME-grouping contract without
silently sorting/shuffling output, upgrading the pinned backend, or hiding the
observed variability.

## Grouping follow-up

The follow-up is complete with decision
`HARAKO_GPU_MAPPING_BASED_SALMON_FALLBACK_REQUIRED`. Samtools collate restored
32,980 complete QNAME groups and preserved the alignment-record multiset, but
did not restore the unchanged numerical ceiling. No alignment-mode grouping
patch was adopted. See
`docs/qualification/transcriptome-bam-grouping-compatibility.md`.
