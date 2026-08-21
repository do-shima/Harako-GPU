# Native-small Salmon 1.10.3 index preregistration

Status: `PREREGISTERED_BEFORE_INDEX_BUILD`

This is a new prospective index contract for the fixed small
`nf-core/test-datasets` reference at commit
`626c8fab639062eade4b10747e919341cbf9b41a`. It does not attempt or claim to
reproduce historical index ID
`364ab1bb39830756ae301b96839e986b47bd93af2ef2d321bbf80be05b615713`.

## Frozen derived inputs

The complete fixed genome is the decoy set. Genome identifiers are parsed in
source order from the first ASCII-whitespace-delimited header token and written
without sorting. The single decoy is `I`; `decoys.txt` SHA-256 is
`7fdca686b46a12886513de3f6166c815efcb501bbe0f6ecda4acd20c6d48fed7`.

The gentrome is exact byte concatenation of the 125-record transcriptome
followed immediately by the one-record genome. No records are reordered,
rewrapped, or normalized. Its SHA-256 is
`8e0b5df12173dfbb34ff64e3e3b6e028975a45678c0c6686f1a285c10f5cc802`.

The existing `parse_transcript_gene_map()` parser produces 124 mappings from
the fixed empty-transcript-ID GTF. `tx2gene.tsv` has a fixed header and rows
sorted by transcript ID; its SHA-256 is
`5a6168d1e9de15b8c8d3c7a05302906e346302b94ba827d87d151492e273c627`.

## Frozen builder

The builder is Salmon 1.10.3 from exact registry digest
`quay.io/biocontainers/salmon@sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e`.
Docker uses `--rm`, `--pull=never`, current UID/GID `1000:1000`, a read-only
`/input` mount, and one build-specific `/output` mount. Effective Salmon argv:

```text
salmon index -t /input/gentrome.fa -d /input/decoys.txt -i /output/index -k 31 -p 6
```

`--gencode`, `--keepDuplicates`, alternate k/thread values, partial decoys,
cDNA-only mode, arbitrary mounts, and arbitrary options are forbidden.

## Frozen identity and gate

Every regular file recursively beneath `index/` is included. Rows contain the
relative POSIX path, byte size, and SHA-256, sorted by path. Canonical compact
JSON of all rows is hashed as `index_manifest_sha256`; no file may be excluded
after either build.

The prospective index ID uses the existing Harako-GPU canonical payload with
builder 1.10.3, exact image digest, fixed transcript/genome/decoy hashes,
`["-k","31","decoy_aware_gentrome"]`, and the directory-manifest hash. The
resulting manifest hash and index ID are intentionally unknown before build.

Two sequential independent builds are mandatory. PASS requires exit 0 for
both and exact equality of the complete file list, every size/hash, manifest
hash, and prospective index ID. Tolerance, semantic fallback, and post-build
exclusions are zero/forbidden.

This preregistration does not qualify biological accuracy, external truth,
full-human scale, production use, or diagnostic use.
