# Decoy leakage metric audit

The original `harako_truth_bulk_v1` value of 19.4% is reproducible, but it is
not a read-level leakage measurement. Its numerator is the larger of
zero-expression transcript estimated-count mass and total estimated-count mass
above the known transcript-origin fragment count. Its denominator is the 3,000
generated decoy-origin paired fragments. Thus it is an aggregate `quant.sf`
proxy (possibilities A, C, D, and F), not a unique attribution of generated
decoy reads (not E).

For Salmon 2.5.1 the fixed inputs produce zero-expression mass 582.000, total
estimated mass 297,582.000, and 297,000 transcript-origin fragments. Both proxy
numerators are therefore 582 and `582 / 3000 = 0.194`. Unmapped fragments and
decoy-best fragments are not individually visible in this formula. Ambiguous,
multi-mapped, and exact-tie observations cannot be disambiguated from aggregate
mass alone.

An independent sequence oracle audited all 3,000 v1 decoy-origin fragments:

| Class | Fragments |
|---|---:|
| `DECOY_UNIQUE` | 1,621 |
| `DECOY_DOMINANT` | 767 |
| `DECOY_AMBIGUOUS` | 30 |
| `DECOY_EXACT_TIE` | 582 |

Each v1 decoy contains a 400 bp interval that is exactly identical to one
zero-expression transcript interval. The exact-tie count equals the old proxy
numerator. The old 19.4% result is retained, but a single percentage containing
information-theoretically indistinguishable observations is not a valid
primary candidate-rejection gate.

The replacement metric uses generated paired fragments as denominator and
estimated transcript count mass as numerator, separately for preclassified
diagnostic samples. Only `DECOY_UNIQUE` and `DECOY_DOMINANT` receive the
unchanged absolute 1% gate. `DECOY_AMBIGUOUS` is reported without PASS/FAIL;
`DECOY_EXACT_TIE` is reported as unidentifiable assignment mass, never as
leakage. The machine-readable audit is in
`decoy-leakage-metric-audit.json`.
