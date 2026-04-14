# Concept: OIS Curve Bootstrap

> The process of fitting a smooth discount curve to overnight index swap market quotes, so that the model reprices all quoted instruments exactly.

## What bootstrapping means

Given a set of market OIS quotes (rates at which the market will transact for fixed tenors), bootstrapping finds the discount factors at each maturity that make all those swap NPVs equal to zero. The discount curve is "exact" — it fits the instruments used to build it.

## Instruments used

The ZARONIA curve uses 18 instruments:

| Type | Tenors |
|------|--------|
| Overnight deposit | ON (T+0) |
| OIS swaps | 1W, 2W, 1M, 2M, 3M, 6M, 9M, 1Y, 18M, 2Y, 3Y, 4Y, 5Y, 7Y, 10Y, 12Y, 15Y, 20Y |

Each OIS swap pays compounded overnight ZARONIA vs a fixed rate. At fair value, NPV = 0.

## QuantLib mechanics

```python
ql.PiecewiseLogLinearDiscount(
    valuation_date,
    ois_helpers,       # list of ql.OISRateHelper
    ZAR_DAY_COUNT,
)
```

`PiecewiseLogLinearDiscount` interpolates `log(DF)` linearly between pillar dates. This ensures positive forward rates and smooth discount factors.

The result is a `ql.DiscountCurve` linked to a `ql.RelinkableYieldTermStructureHandle`. Any instrument that holds a reference to the handle reprices automatically when the curve is relinked — this is how KRD bumping works without copying instruments.

## KRD bumping (finite difference)

To compute the sensitivity to a single tenor bucket:

1. Copy the market data dict.
2. Add `+1bp` to one OIS quote.
3. Re-bootstrap a new curve.
4. Reprice all instruments on the new curve.
5. KRD = new NPV − base NPV.

This is done in `ZARCurveBuilder.reprice_with_shock()` which returns one shocked builder per bumped tenor.

## Interpolation implications

Log-linear discount interpolation means:
- Forward rates are **piecewise constant** between pillars (they jump at each tenor pillar date)
- Discount factors are smooth and positive everywhere
- Zero rates are continuous but not differentiable at pillar dates

This is standard for OIS curve construction. More exotic interpolations (cubic spline, monotone convex) give smoother forwards but add complexity.

## See also

- [[concepts/zaronia]] — the overnight index underlying the curve
- [[modules/zaronia_curve]] — implementation details
- [[concepts/dv01_krd]] — how the bootstrapped curve is used for risk
