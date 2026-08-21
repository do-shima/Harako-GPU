# Salmon 1.10.3 native-small index cause-isolation preregistration

Status: `PREREGISTERED_BEFORE_MATRIX`

This diagnostic contract follows the immutable v1 byte-identity FAIL recorded
at commit `5281063ab362f2a4929247d523ae4ff961049593`. It does not amend v1,
promote an index, execute the product route, or adopt semantic equivalence as a
qualification gate.

## Fixed matrix and environment

The fixed source, gentrome, decoy, tx2gene, Salmon RepoDigest, UID/GID, k=31,
and container paths are identical to v1. Every container receives exactly
`LC_ALL=C`, `LANG=C`, and `TZ=UTC`; `SOURCE_DATE_EPOCH` is not set. Docker uses
`--pull=never`, user `1000:1000`, read-only `/input`, and `/output`.

Six fresh builds run sequentially: S1/S2/S3 use `-p 1`; P1/P2/P3 use the fixed
product build count `-p 6`. Host output roots differ, while all container paths
and remaining argv are identical. The original v1 A/B builds remain historical
evidence and are not members of this matrix.

## Frozen comparisons

The full diagnostic set is the exact 15-file v1 inventory. The runtime payload
candidate is fixed before build as the same set excluding only
`pre_indexing.log` and `ref_indexing.log`. This diagnostic exclusion cannot
retroactively change v1, does not define a promoted package, and cannot be
expanded after results. No binary file is excluded.

For each non-identical file the analysis counts every differing byte and stores
only the first 32 offsets and first 32 contiguous ranges, plus bounded printable
string markers for timestamps, host/container paths, PIDs, and random-looking
identifiers. Equal size never establishes equivalence.

## Functional diagnostic

The fixed fastp 1.0.1 RepoDigest processes WT_REP1 once using the existing
paired option profile, reports, failed/unpaired outputs, six threads, and
adapter detection. The validated read-only output pair is reused everywhere.

Each of the six indexes is loaded twice by exact Salmon 1.10.3 with thread-1
quantification, ISR, the fixed tx2gene, and new output directories. The
diagnostic comparison freezes exact ordered transcript/gene parsed rows and
selected fragment/mapping metadata. This is an index-function isolation probe,
not a biological-accuracy or semantic qualification gate.

No build is promoted regardless of classification. No product plan or run is
created. A separate prospective contract would be required for any future
adoption decision.
