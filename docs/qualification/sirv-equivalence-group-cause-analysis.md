# SIRV equivalence-group cause analysis

The historical 28.9838% median and 78.6794% p90 failures are preserved. This
analysis finds that they are not evidence of a Salmon 2.5.1-specific defect.

The transcript gates use symmetric absolute-log2 error, while the group gates
use asymmetric relative error. A 25% relative error corresponds to 0.322 log2
on over-estimation but 0.415 log2 on under-estimation; 50% corresponds to
0.585 and 1.0 respectively. Those limits are materially stricter than the
transcript limits of 0.75 and 1.50, so transcript PASS and group FAIL can occur
without mathematical contradiction. The metrics are classified
`INCOMPARABLE_METRICS`.

The frozen 67 groups are a valid partition of all 69 transcripts: no duplicate,
missing, or zero-denominator membership exists and both expected and estimated
fractions sum to one. However, 66 groups are singletons and only one is a true
multi-transcript aggregate. That multi-transcript group passes at 13.42%; the
singleton median and p90 fail at 30.79% and 78.69%. The gate therefore mostly
re-tests individual transcript error on a stricter, asymmetric scale.

SIRV502 has severe uneven coverage (coverage CV 0.5803; 4.42% zero coverage;
first-quartile mean 546.6 versus 2,711--3,258 elsewhere), consistent with the
documented batch fragmentation problem. Its group error is 99.92%, but the
diagnostic summary excluding it still fails at 28.83% median and 78.28% p90.
It is a `PARTIAL_CONTRIBUTOR`, not the dominant cause. The official amendment
does not specify a nucleotide interval, so none is invented here.

Combined human+SIRV and SIRV-only indices produce the same SIRV values; the
combined result assigns zero estimated mass to human targets. Reference
competition is not the cause. Salmon 1.10.3, 1.12.1, and 2.5.1 all fail the
same frozen group limits. No independent quantifier was locally available and
SIRVsuite was optional and not run.

Cause classification is `METRIC_CONTRACT_INVALID_FOR_ALGORITHMIC_REJECTION`:
the original gate remains a historical FAIL, but its scale and nearly all-
singleton grouping cannot support a Salmon 2.5.1-specific rejection. No limit
was changed and no failed feature was removed from the original result.
