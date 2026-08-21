# Native-small Salmon 1.10.3 index cause-isolation result

Primary classification:
`HARAKO_GPU_SALMON_1103_INDEX_CAUSE_ISOLATION_QUANT_DIAGNOSTIC_UNSTABLE`

This diagnostic ran from preregistration commit
`f03dfe8e8cbd7af4abff63d6bdfbc1b166d206ff`. It preserves the original v1
preregistration and its immutable negative result. It does not promote an
index, execute a product plan/run, or adopt semantic equivalence as a
qualification gate.

## Fixed contract

All six builds used the same fixed source/derived inputs, Salmon 1.10.3
RepoDigest, UID/GID `1000:1000`, `/input` read-only and `/output` mounts,
`--pull=never`, k=31, and `LC_ALL=C`, `LANG=C`, `TZ=UTC`. S1/S2/S3 used
`-p 1`; P1/P2/P3 used `-p 6`. They ran sequentially.

- genome: `df70973809f672aa58a414fef3f01e0e465bf26f10159174a616b0dee2d458e1`
- GTF: `913092a6524a7de2a95c3a1695d0dfc8143f047f4c9c9bc7b206719a7388242a`
- transcriptome: `4f6a6733546b01a96a71f13c63215d9b854dfb1873c2fa484ed69707d6443ac3`
- gentrome: `8e0b5df12173dfbb34ff64e3e3b6e028975a45678c0c6686f1a285c10f5cc802`
- decoys: `7fdca686b46a12886513de3f6166c815efcb501bbe0f6ecda4acd20c6d48fed7`
- tx2gene: `5a6168d1e9de15b8c8d3c7a05302906e346302b94ba827d87d151492e273c627`
- Salmon RepoDigest: `sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e`

## Build matrix

All six builds exited zero and produced the frozen 15 paths. Their full and
13-file runtime-payload-candidate manifest SHA-256 values were:

| Build | Threads | Full manifest | Runtime payload manifest |
| --- | ---: | --- | --- |
| S1 | 1 | `1af47e3cba6c7fd5e77511024c7b0b3286c65cbdd79693f93166575ed14debd1` | `df4c55ff3c2ad6e87e9f31165fe576c0cd787c9a9aa36da2e72de4ada67066ed` |
| S2 | 1 | `779ebd242e820cbe1941dd379f08e19fa6040b9643bd5a803b3d1316404fa50e` | `e9ddca9baff975d9cbe826a741e3f4fa75c37fd5adf37434724a2ac8923189f0` |
| S3 | 1 | `e031aad74c63a30ae3cd8b89b46ec074b2286371bf3a22abac40b689b7a586ed` | `a76609fcbc19af0b9bf0dcf43c6904b0274d23a33a1580cbe429f23a3312b99a` |
| P1 | 6 | `39100f94b43f9853613e45507fc5b7fc1e2dce8ca790fbe87c2576f74b3524d9` | `bfb5f865540aa738627826e05401eea3d2382e10deb79f1f314963db9c9ac55a` |
| P2 | 6 | `85955df0d43a3c1b860815555b941d2dd173d4124c56fa8b750465272ec2d6fc` | `1c048c90e49a35a5fedd906d003c6784f7a6a0f0c342e30ccf4d28e839995ae4` |
| P3 | 6 | `696d2efc9c86e3d79aaaa0cf7da22a003d9d38f5afc51d4564f9b7d4c3da7fc7` | `ffb75935d5744c354ae001dff29f75f1c6c586adf1d7f4e8cc6d51c85112708e` |

Neither arm is byte-identical for the full directory or the preregistered
runtime payload candidate. Every within-arm pair differs in exactly
`ctable.bin`, `pos.bin`, `seq.bin`, `pre_indexing.log`, and
`ref_indexing.log`. Thus `-p 1` does not remove the v1 binary nondeterminism.

For representative S1/S2 comparison, equal-size binary differences were 783
bytes in `ctable.bin`, 126,276 bytes in `pos.bin`, and 18,408 bytes in
`seq.bin`. For representative P1/P2 comparison they were 525, 129,407, and
17,492 bytes respectively. Bounded inspection found no timestamp, path, PID,
or random-looking printable marker in these binaries. The log differences
contain timestamps, and `ref_indexing.log` contains fixed container paths.
Full bounded pairwise offsets and ranges remain in external evidence.

A copy of S1 with only `pre_indexing.log` and `ref_indexing.log` removed
retained the exact frozen 13-file list and loaded successfully in Salmon quant.
No binary was removed. This is diagnostic evidence only and does not create a
qualified package or retroactively alter v1.

## Source audit

The official Salmon v1.10.3 release resolves to
`a2f6912b3f9f9af91e3a4b0d74adcb3bdc4c9a32` and pins the Pufferfish
`salmon-v1.10.3` archive SHA-256
`52b6699de0d33814b73edb3455175568c2330d8014be017dce7b564e54134860`.
The archive matched and its tag resolves to
`484243eb6f72e0868389b4edc7fdb8b8f29f92aa`.

The canonical source passes the requested thread count into graph/index
construction and contains worker/TBB/concurrent paths. It also creates each
TwoPaCo cyclic-hash key set from a default Mersenne Twister seeded from
`/dev/urandom`, with a time/clock fallback; the Salmon argv exposes no fixed
seed. That is a source-supported thread-count-independent mechanism consistent
with the three changing graph-derived binaries. It does not prove that every
changed byte has that sole cause, and the container inspect metadata does not
prove its exact source commit.

## Fixed processed input and quantification diagnostic

Fixed fastp processed WT_REP1 once. It produced 47,605 paired fragments with
R1 SHA-256
`a39a425c9c0e652bc0df0a5a59d172a073ebc78f9d741cb65bad7f4cedcad625`
and R2 SHA-256
`75fcc5e66900610fbf3777840f991c27611a0210b21565279cb44ec604e91143`.
The pair was made read-only and reused by every quantification.

Each index loaded twice successfully using Salmon 1.10.3, `--threads 1`, ISR,
the same tx2gene, and the same processed pair. Each run processed 47,605 and
mapped 37,586 fragments (78.9538913979624%). Transcript IDs were unique and
ordered identically, but the exact frozen functional digest differed between
Q1 and Q2 for every index:

| Index | Q1 digest | Q2 digest | Equal |
| --- | --- | --- | --- |
| S1 | `9cdde372c869fa3d77a25ba6ead6e4c35f4a00df5d32abd3cfb6cd66e8205d8b` | `81d2c6d00a025665f713f2168a1e1cabeb9ee1a095b5fc0dbeb1910cb047cd16` | no |
| S2 | `536de796fc8cc4b9e15fd6d971953833032bdd76a27e20795d2d39aff6e59f82` | `9cdde372c869fa3d77a25ba6ead6e4c35f4a00df5d32abd3cfb6cd66e8205d8b` | no |
| S3 | `51f52a96234226b8c817ef880f5461c594bcd33a79d0e0790126fb77a6b54560` | `666c5800c9023fc5eda8944f31f02fba50d2f0e408236da653377060ff3bd993` | no |
| P1 | `6f9127530d964225b83e8e5e61a0ff16a3f786c8985665f2a65fead9ff90e2ba` | `81d2c6d00a025665f713f2168a1e1cabeb9ee1a095b5fc0dbeb1910cb047cd16` | no |
| P2 | `02d3e4d1fb5b4c45aab0449adb9b797bc65644bd17beb8a93266f5c510958d4b` | `280c015639629930feaef89c49a485a35577e39fcf6824b333e1915b65ff7f7c` | no |
| P3 | `cbb957a8d7846d44f1dd69f9bb3b534ef9c2d0958aabb10994d00622f9036672` | `5fe28506e4ca36182d20460663c0dbe1d6b0d40e9055ce4e66103c017d6ecbf5` | no |

Because within-index thread-1 repeats are unstable, an across-index functional
equivalence conclusion is not identifiable under this preregistered diagnostic.
The primary classification is therefore the quant-diagnostic-unstable result,
not functional divergence.

No index was promoted and no product plan/run was performed. Native-built
Salmon 1.10.3 index adoption for this route is rejected under this contract;
all evidence is retained at
The external evidence root is intentionally omitted from the public snapshot.
