# Module: zaronia_curve

> Bootstraps a QuantLib ZARONIA OIS discount curve from overnight + 18 tenor quotes; exposes discount factors, zero rates, forward rates, and par swap rates.

**File:** `src/curves/zaronia_curve.py` (437 lines)

## Key classes

### `ZARONIAIndex`

Subclass of `ql.OvernightIndex`. Defines ZARONIA as a T+0, Act/365 Fixed overnight index on the ZAR currency and South Africa calendar. Passed to all OIS swap helpers.

### `ZARONIAMarketData`

Dataclass holding a single valuation snapshot:

```python
@dataclass
class ZARONIAMarketData:
    valuation_date: ql.Date
    overnight_rate: float           # decimal, e.g. 0.075
    ois_quotes: Dict[str, float]    # {"1W": 0.0748, "1Y": 0.0677, ...}
    jibar_quotes: Dict[str, float]  # not used in pricing, kept for reference
```

`ZARONIAMarketData.current_market()` returns a hardcoded current-market snapshot (as of April 2026) with 18 OIS tenors from 1W to 20Y and an overnight rate of 7.50%.

### `ZARCurveBuilder`

Main curve object. Call `.build()` after construction to bootstrap; returns `self` for chaining.

```python
cb = ZARCurveBuilder(mkt).build()
```

Internally uses `ql.PiecewiseLogLinearDiscount` with log-linear interpolation between pillar discount factors. The resulting curve lives on a `ql.RelinkableYieldTermStructureHandle` (`_ts_handle`) so all downstream pricers reprice automatically when the curve is relinked.

**Class constant:** `KRD_BUCKETS = ["1M","3M","6M","1Y","2Y","3Y","5Y","7Y","10Y"]` — the standard tenor grid for DV01 bumping.

## Key methods

| Method | Returns | Notes |
|--------|---------|-------|
| `discount(tenor_or_date)` | `float` | Discount factor |
| `zero_rate(tenor_or_date)` | `float` | Continuous zero rate (decimal) |
| `forward_rate(d1, d2)` | `float` | Simple forward rate |
| `par_swap_rate(maturity)` | `float` | Implied par OIS rate |
| `curve_dataframe()` | `pd.DataFrame` | Tidy table of all curve points |
| `parallel_shift(bps)` | `ZARCurveBuilder` | New builder with all quotes shifted |
| `steepener_shift(short, long, pivot)` | `ZARCurveBuilder` | Linear twist around pivot tenor |
| `reprice_with_shock(tenors, bps)` | `List[ZARCurveBuilder]` | One bumped builder per tenor (used for KRD) |

## Curve shape (April 2026)

The bootstrapped curve is upward-sloping. Selected zero rates (continuous):

| Tenor | Zero Rate |
|-------|-----------|
| 1Y | 6.77% |
| 5Y | 7.37% |
| 10Y | 7.93% |
| 20Y | 8.47% |

Overnight rate: 7.50%.

## See also

- [[concepts/zaronia]] — what ZARONIA is and its market role
- [[concepts/ois_bootstrap]] — bootstrapping mechanics
- [[modules/risk_engine]] — how the curve is shocked for KRD
- [[modules/ois_swap]] — consumes this curve
- [[modules/vanilla_irs]] — consumes this curve
