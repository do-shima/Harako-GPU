# Parabricks STAR metrics compatibility qualification

Classification: `HARAKO_GPU_PARABRICKS_STAR_METRICS_COMPATIBILITY_QUALIFIED`

This qualification resolves the reporting defect for the same one-sample
public fixture used by the minimal feasibility run. It does not broaden the
qualified biological, hardware, memory, or performance envelope.

## Logfile experiments and STAR oracle

Three isolated direct Parabricks runs used the same trimmed FASTQs, reference,
STAR index, read group, GPU, `--low-memory --x3`, and `--no-markdups`:

| Experiment | Parabricks logfile option | Top-level STAR final summary | Result |
| --- | --- | --- | --- |
| A | `WT_REP1.Log.final.out` | hidden by the generic 6,730-byte PB log | exit 0, 40 s |
| B | `WT_REP1.parabricks.log` | genuine second-pass summary | exit 0, 39 s |
| C | omitted; stderr captured | genuine second-pass summary | exit 0, 39 s |

B and C separated a 1,988-byte standard final summary from the generic
Parabricks stream. The final summary differs correctly from the nested
first-pass summary (87.33% versus 87.39% unique mapping). Native STAR 2.7.2a
ran once as a metrics oracle with the same index and equivalent STAR options.
All non-timing fields matched experiment B exactly; the comparison tolerance
was zero for counts, percentages, lengths, mismatch/indel rates, and splice
metrics. Runtime speed was excluded from scientific comparison.

## Metric-source assessment

| Source | Unit and policy | Display / QC decision |
| --- | --- | --- |
| Standard `Log.final.out` | paired fragments; STAR final two-pass rules | selected for STAR display and the 5% unique-mapping gate |
| Parabricks generic log | runtime events, no alignment metric unit | retained as provenance only |
| Parabricks QC metrics | primarily aligned-read/Picard summaries | useful support data; not a STAR unique-mapping replacement |
| samtools flagstat/stats | BAM alignment records; secondary records explicit | validates BAM; its 100% mapped value cannot represent input or uniqueness |
| BAM `NH`/`HI` tags | aligned records only | not adopted because no substitution was needed and the input denominator is absent |
| Salmon alignment mode | transcriptome fragments accepted by Salmon | never labelled STAR unique mapping |
| FASTQ count | raw/trimmed paired fragments | denominator evidence only |

The paired-end STAR `Number of input reads` value is treated as paired
fragments: each trimmed mate file contained 49,747 records and STAR reported
49,747 inputs, not 99,494 individual reads.

## Selected compatibility strategy

Branch A was selected. The four-line SHA-pinned source change moves the generic
log to `${prefix}.parabricks.log`, exposes the genuine
`${prefix}.Log.final.out`, adds the generic log as a module output, and includes
`.log` in the alignment-log publish pattern. The patch is in
`patches/nf-core-rnaseq-3.26.0/`; its SHA-256 is
`fce22aa2...d72410`. It applies only to revision 3.26.0 at commit
`e7ca4627...217a4`, source module SHA `231d896e...94321`, and source config SHA
`23276136...308`. Unknown or mixed target state is rejected before `git apply`.

No synthetic STAR log, mapping-threshold override, CPU fallback, container
override, or arbitrary command string was introduced.

## Corrected actual run

The corrected run used Nextflow 25.04.3, Docker, Parabricks 4.6.0-1 at digest
`sha256:d0761eb4...4650447`, one RTX 3090, and Harako plan
`5c048b2a...6a1d`. The local patched source remained based on tag 3.26.0 and
commit `e7ca4627...217a4`; Nextflow does not permit `-r` with a local script, so
the revision was enforced by the pre-application commit/SHA gate and recorded
in the run manifest.

The run completed 47 tasks with exit 0 in 4m30s. Trace evidence contains one
`PARABRICKS_RNA_FQ2BAM` task and zero native `ALIGN_STAR:STAR_ALIGN` tasks.
The task used `pbrun rna_fq2bam`, `--low-memory --x3`, `--no-markdups`, the
separate logfile, and the fixed container. During its 39.3-second trace window,
39 one-second monitor samples recorded peak VRAM 9,398 MiB, maximum GPU
utilization 83%, peak power 211.44 W, and maximum temperature 53 C. Parabricks
logged CUDA success and version 4.6.0-1.

The published STAR summary and native oracle both reported:

- input paired fragments: 49,747
- uniquely mapped: 43,442 (87.33%)
- multiple loci: 986 (1.98%)
- too many loci: 0 (0%)
- final mapped percentage shown by MultiQC: 89.31%

The nf-core 5% gate passed. No `fail_mapped` artifact or warning was produced.
MultiQC wrote HTML and its data directory, parsed `WT_REP1` from the genuine
STAR summary, showed 87.33% unique mapping, and did not register the generic
Parabricks log as a STAR source.

## Computational invariance

The corrected final BAM byte SHA-256 (`6e017271...3ea6`) differs from the prior
qualified SHA (`33372ca6...2d5`) because STAR records absolute work/output
paths in `@PG` and `@CO`; the new Nextflow task necessarily has a different
work path. This is not an alignment-record difference. Samtools 1.23.1
`checksum -a` matched all 92,113 records across both BAMs, including sequence,
name, quality, auxiliary tags, reference position, CIGAR, mate fields, and
flags (`combined=51410770`). Quickcheck, coordinate sort, reference contig, and
sample/read-group checks passed.

`SJ.out.tab`, merged gene counts, and merged transcript counts were byte
identical. Salmon `NumReads` was identical for all 124 transcripts. Independent
Salmon executions produced up to 0.081 effective-length difference and a
maximum TPM relative difference of 0.0007638 (0.0764%); counts were unchanged.
The transcriptome BAM record checksum also differed among the otherwise
identical direct A/B/C Parabricks runs, while their genomic BAM record checksum
was identical. This establishes fresh-run transcriptome-output variability
independently of logfile strategy. The bounded Salmon re-estimation variance is
reported, not attributed to the logfile patch or hidden behind a byte-identity
claim.

That two-run observation was later superseded as a release decision by the
dedicated Salmon reproducibility contract. A frozen-BAM/six-thread series was
bounded, but five fresh transcriptome BAM orders changed contiguous QNAME group
counts and exceeded the fixed TPM ceiling. STAR reporting remains qualified;
fresh alignment-mode Salmon reproducibility is separately blocked.

## Resume

The identical command, plan, patch, inputs, reference, result root, and work
root completed with `-resume` in 34 seconds. Forty-six tasks were cached;
MultiQC alone regenerated as run-specific aggregation. Parabricks alignment,
BAM sort/index, Salmon, and every other computational task were cached. BAM
SHA/mtime, STAR metric SHA, Salmon quant SHA, plan identity, patch targets,
reference, and input checksums were unchanged. The regenerated MultiQC report
still showed 87.33% and no false fail row.

## Qualification boundary

Qualified: genuine final STAR metrics, nf-core mapping gate, MultiQC STAR
reporting, minimal-fixture Parabricks alignment/BAM/count invariance, and
resume caching under the pinned versions above.

Unqualified: full-size data, scientific equivalence beyond this fixture,
performance comparison, standard-memory mode, mark duplicates, multi-GPU,
other Parabricks/nf-core/Nextflow versions, production use, and diagnostics.
