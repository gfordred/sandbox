# Concept: DV01 and Key-Rate Duration (KRD)

> DV01 measures total rate sensitivity; KRD decomposes it by tenor bucket, revealing which part of the curve drives the position's risk.

## DV01 / BPV

**DV01** (Dollar Value of 01) = change in NPV for a +1 basis point parallel shift in all rates.
In ZAR it is ZAR/bp. In this system it is computed as:

```
BPV = NPV(curve + 1bp parallel) − NPV(base curve)
DV01 = |BPV|
```

Sign convention: a **receiver swap** (long fixed) has **negative BPV** — when rates rise 1bp, NPV falls.

**Modified duration** is derived: `mod_dur = −BPV × 10000 / notional` (years).

## Key-Rate Duration (KRD)

KRD (also "bucket DV01") measures sensitivity to a 1bp shift in a **single tenor bucket only**, with all other quotes unchanged.

```
KRD(t) = NPV(quote[t] + 1bp) − NPV(base)
```

Summing all KRDs recovers the total BPV (approximately, for smooth curves).

### KRD buckets used

`["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y"]`

### Portfolio KRD (April 2026)

| Bucket | Net KRD (ZAR/bp) | Dominant trade |
|--------|-----------------|----------------|
| 1M | ~0 | — |
| 1Y | −232,772 | OIS-006-1Y-RCV |
| 2Y | −361,603 | IRS-003-2Y-RCV |
| 3Y | +392,342 | OIS-005-3Y-PAY |
| 5Y | +1,216,550 | IRS-002-5Y-PAY |
| 7Y | −2,113,164 | IRS-004-7Y-RCV |
| 10Y | −3,380,218 | IRS-001-10Y-RCV |

Negative KRD = long duration in that bucket (receive-fixed). Positive = short (pay-fixed).

## Convexity

Second-order sensitivity: `(P(+1bp) + P(−1bp) − 2P) / (P × dr²)`.

For the vanilla IRS positions this is non-zero but small relative to DV01. Convexity matters for large rate moves (>25bp).

## Delta ladder

The **delta ladder** is a 2D grid: trades (rows) × tenor buckets (columns), values in ZAR/bp. It shows exactly where each trade contributes risk. The NET row is the portfolio's aggregate KRD vector — the hedge target.

See [[modules/risk_engine]] for computation, [[modules/graphify]] for visualisation.

## See also

- [[concepts/scenario_analysis]] — DV01 used to estimate scenario P&L
- [[modules/risk_engine]] — computes DV01 / KRD via finite difference
- [[modules/hedge_optimizer]] — uses KRD vector to solve hedge notionals
- [[modules/graphify]] — `dv01_ladder_plot()` and `portfolio_heatmap()`
