# Fixed human capacity reference pack

`human_grch38p14_gencode49_harako_gpu_v1` is the qualification-only full-human
reference pack. Its biological sources are the GENCODE release 49 GRCh38.p14
primary-assembly genome, primary-assembly GTF, and matching transcript FASTA.
It contains no SIRV or ERCC targets.

The normalized Salmon target universe contains 533,740 versioned ENST records.
The GTF contains 509,650 transcript IDs and 78,899 gene IDs; all 70 GTF contigs
occur in the 194-record primary-assembly genome. The generated tx2gene table,
gentrome, and 194-entry decoy list are fixed by SHA-256 in the runtime manifest.
Reference sequence and annotation files remain in WSL ext4 and are not tracked
by Git.

Three indices were built from the same biological sources:

- Parabricks-compatible STAR 2.7.2a, `sjdbOverhang=74`, ID
  `star-2.7.2a-c15a9d6fe6df9716` (30,161,099,016 bytes).
- Salmon 1.10.3 k=31 decoy-aware index, ID
  `salmon-1.10.3-52224ad2355cc52b` (18,223,695,337 bytes).
- Salmon 2.5.1 k=31 decoy-aware index, ID
  `salmon-2.5.1-1c037278d376f40f` (10,034,853,064 bytes).

The biological input ID set is common, but the two Salmon versions clean and
encode the reference differently. Their index files and IDs are deliberately
not interchangeable. The STAR build itself reached about 40.93 GB WSL memory,
already a constrained preparation workload on this host.

The local nf-core snapshot is patched only after exact upstream SHA checks so
that a supplied qualified Parabricks STAR index is reused instead of silently
starting a new index build. Unknown upstream content fails closed.

The one-pass qualification reused these exact assets read-only. No reference
or index was rebuilt. The C1 RAM failure occurred after successful index
loading and is a host-capacity finding, not an identity or reference-pack
failure.
