# Human quantification-only capacity qualification

The fixed CPU FASTQ route completed Q1 1M, Q2 5M compare-both, Q3 10M,
conditional Q4 20M compare-both, and optional full-source Q5 36,349,964 pairs.
Every required quantification artifact passed structural verification. BAM, BAI,
junction, STAR GeneCounts, and alignment MultiQC were `NOT_APPLICABLE` throughout.
The fixed Salmon index sizes were 18,223,695,337 bytes for 1.10.3 and
10,034,853,064 bytes for 2.5.1.

| Level | Mode | Result | Peak WSL RAM | Minimum available | Wall time |
|---|---|---|---:|---:|---:|
| Q1 1M | 2.5.1 | comfortable | 11.41 GiB | 35.63 GiB | 64 s |
| Q2 5M | compare-both | comfortable | 19.55 GiB | 27.50 GiB | 297 s |
| Q3 10M | 2.5.1 | comfortable | 11.91 GiB | 35.14 GiB | 242 s |
| Q4 20M | compare-both | comfortable | 19.83 GiB | 27.22 GiB | 735 s |
| Q5 36.35M | 2.5.1 | comfortable after controller recovery | 11.43 GiB | 35.61 GiB | 402 s successful resume attempt |

Q5 initially recorded a controller failure when Windows temporarily denied an
atomic `status.json` replace over the WSL UNC view. The scientific container was
allowed to finish, the exact failed output was archived, and immutable resume
reused the validated preprocessing tasks while rerunning Salmon. Both attempts
and the recovery-inclusive 1,160-second duration remain recorded. A bounded
atomic-replace retry and non-fatal telemetry heartbeat now prevent a transient
status update from aborting scientific process supervision.

The maximum tested successful and comfortable scale is the full 36.35M-pair
source. The conservative recommended internal operating scale remains 20M pairs
because only one public sample and one host were tested. This does not qualify a
full-human BAM workflow.

Across the successful attempts, mean host CPU utilization ranged from 13.94% to
33.03% and observed peaks from 51.79% to 59.65%. Processed FASTQ storage grew
from 133,529,736 bytes at Q1 to 4,994,167,035 bytes at Q5. The highest observed
run-result high-water was 9,369,153,674 bytes at Q5; the fixed reference indices
are accounted separately.
