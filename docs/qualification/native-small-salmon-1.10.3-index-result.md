# Native-small Salmon 1.10.3 index v1 result

Classification: `HARAKO_GPU_NATIVE_SMALL_SALMON_INDEX_NONDETERMINISTIC`

The prospective v1 contract was preregistered and pushed at commit
`f37871e308898227e7652b54955f772f1ba23bf4` before either build. The
preregistration files were not amended after build execution. This result does
not claim reproduction of the historical Salmon 1.10.3 index.

## Frozen identities and command

- genome: `df70973809f672aa58a414fef3f01e0e465bf26f10159174a616b0dee2d458e1`
- GTF: `913092a6524a7de2a95c3a1695d0dfc8143f047f4c9c9bc7b206719a7388242a`
- transcriptome: `4f6a6733546b01a96a71f13c63215d9b854dfb1873c2fa484ed69707d6443ac3`
- gentrome: `8e0b5df12173dfbb34ff64e3e3b6e028975a45678c0c6686f1a285c10f5cc802`
- decoys: `7fdca686b46a12886513de3f6166c815efcb501bbe0f6ecda4acd20c6d48fed7`
- tx2gene: `5a6168d1e9de15b8c8d3c7a05302906e346302b94ba827d87d151492e273c627`
- Salmon RepoDigest: `sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e`

Effective argv was exactly:

```text
salmon index -t /input/gentrome.fa -d /input/decoys.txt -i /output/index -k 31 -p 6
```

## Independent-build result

Both builds exited zero and produced the same 15 paths and sizes. Build A had
manifest SHA `3e3588a16a7aa1db9fa23349695a29111f49c0b47e09a29d5811f68bf0519d91`
and prospective index ID
`98605aae5f5e0bfa19d852e55d884fdff5aa7808addb9fc3f19b25bed985fa1f`.
Build B had manifest SHA
`2a18cfa2e127b830b70fd385425686a85c3cbb671c96a96a9c310cfb26674d0d`
and prospective index ID
`341d387aa76ce0412417fbca4af4c61bebdd8ff868662a29a9e239532716228d`.

SHA-256 differed for `ctable.bin`, `pos.bin`, `seq.bin`,
`pre_indexing.log`, and `ref_indexing.log`. The preregistered zero-tolerance
full-directory byte-identity gate therefore failed. Log files were not
excluded, no semantic-equivalence fallback was applied, and v1 remains FAIL.

No index was promoted. No legacy/profile manifest, product plan, or product
run was created. All build and comparison evidence remains under
The external evidence root is intentionally omitted from the public snapshot.
