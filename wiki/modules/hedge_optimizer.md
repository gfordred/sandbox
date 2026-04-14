# Module: hedge_optimizer

> Computes macro (single-tenor DV01 flatten) and key-rate (multi-bucket) hedges for the portfolio using least-squares optimisation.

**File:** `src/hedging/hedge_optimizer.py` (516 lines)

## Classes

### `HedgePlan`

The output of any hedge computation. Holds:

| Field | Description |
|-------|-------------|
| `hedge_legs` | `List[dict]` — each leg: tenor, direction, notional, rate, BPV |
| `pre_hedge_bpv` | Portfolio BPV before hedging (ZAR/bp) |
| `post_hedge_bpv` | Residual BPV after adding hedge legs |
| `hedge_effectiveness` | `1 − |post| / |pre|` (0–1) |

Key methods:
- `summary()` — human-readable text table
- `krd_comparison()` — DataFrame with pre/post KRD per bucket and `reduction_pct`

### `HedgeOptimizer`

```python
optimizer = HedgeOptimizer(curve_builder, instruments, risk_engine)
```

#### `macro_hedge(hedge_tenor="5Y")`

Solves for a single hedge swap at `hedge_tenor` that neutralises the portfolio's total BPV:

```
notional_hedge = −total_portfolio_bpv / bpv_per_unit_notional(hedge_tenor)
```

The hedge direction is the opposite of the portfolio's net BPV sign. Returns a `HedgePlan` with one leg.

At 5Y (April 2026): a ZAR 5bn receiver portfolio requires a ~ZAR 11.05bn pay-fixed 5Y swap to flatten DV01 (100% effectiveness on total BPV, but large residual KRDs in other buckets).

#### `key_rate_hedge(hedge_tenors=[...])`

Solves for one hedge swap per specified tenor bucket, minimising residual KRD exposure simultaneously. Uses `scipy.linalg.lstsq` on the KRD sensitivity matrix:

```
A · x = −b
```
where `A[i,j]` = KRD of a unit-notional hedge swap at tenor j in bucket i, and `b[i]` = portfolio KRD in bucket i.

The solution `x` gives the notional for each hedge leg. Typical effectiveness on the April 2026 book: **90.7%** (5 hedge tenors: 1Y, 2Y, 5Y, 7Y, 10Y).

### `PortfolioBlotter`

Simple container for a list of instruments. Not directly used by `HedgeOptimizer` in the current implementation.

## Hedge effectiveness: macro vs key-rate

| Metric | Macro Hedge (5Y) | Key-Rate Hedge |
|--------|-----------------|----------------|
| Total BPV reduction | 100% | ~91% |
| Residual KRD in non-5Y buckets | Large | Near zero |
| Number of hedge legs | 1 | 5 |
| Practical use | Quick DV01 flatten | Full bucket hedge |

## See also

- [[concepts/dv01_krd]] — KRD bucketing methodology
- [[modules/risk_engine]] — provides `RiskEngine` and `PortfolioRiskReport`
- [[modules/zaronia_curve]] — curve used to price hedge legs
- [[modules/graphify]] — `hedge_effectiveness_plot()` visualises `HedgePlan`
