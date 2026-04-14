# Concept: Scenario Analysis

> Scenario P&L measures the gain or loss on a position if the yield curve shifts in a specified way. Used to stress-test the book against realistic and tail market moves.

## Scenarios defined

Seven scenarios are hardcoded in `RiskEngine.SCENARIOS`:

| Key | Description | Type | Short (bps) | Long (bps) |
|-----|-------------|------|-------------|-----------|
| `PARALLEL_UP_25` | Parallel +25 bps | parallel | +25 | +25 |
| `PARALLEL_DN_25` | Parallel −25 bps | parallel | −25 | −25 |
| `PARALLEL_UP_100` | Parallel +100 bps | parallel | +100 | +100 |
| `PARALLEL_DN_100` | Parallel −100 bps | parallel | −100 | −100 |
| `STEEPENER_2s10s` | 2s10s Steepener | twist @ 2Y | +10 | −10 |
| `FLATTENER_2s10s` | 2s10s Flattener | twist @ 2Y | −10 | +10 |
| `STEEPENER_5s10s` | 5s10s Steepener | twist @ 5Y | +10 | −10 |

"Short" = 2Y end; "Long" = 10Y end.

## How scenarios are computed

For each scenario:
1. Apply the shock to the curve (via `parallel_shift` or `steepener_shift`).
2. Re-price the instrument on the shocked curve.
3. `P&L = shocked NPV − base NPV`.

Results reported in ZAR and in bps of notional.

## Example: IRS-001-10Y-RCV (ZAR 5bn receiver)

| Scenario | P&L ZAR | P&L bps |
|----------|---------|---------|
| Parallel +25 | −83.6m | −167 bps |
| Parallel −25 | +85.5m | +171 bps |
| Parallel +100 | −323m | −646 bps |
| 2s10s Steepener | −230m | −460 bps |
| 2s10s Flattener | +239m | +479 bps |

The asymmetry between +25 and −25 P&L reflects convexity (positive for receivers).

## Adding custom scenarios

The curve builder supports both shift types:

```python
# Custom parallel
shocked = cb.parallel_shift(+50)

# Custom steepener
shocked = cb.steepener_shift(
    short_end_bps=-20,
    long_end_bps=+20,
    pivot_tenor="5Y",
)
```

The dashboard's "Curve Scenarios" panel uses 3 scenarios: +25bp, −25bp, 2s10s steepener.

## See also

- [[concepts/dv01_krd]] — DV01 approximates parallel scenario P&L (P&L ≈ DV01 × bps)
- [[modules/risk_engine]] — `_run_scenarios()` implementation
- [[modules/zaronia_curve]] — `parallel_shift()` and `steepener_shift()`
- [[modules/graphify]] — `scenario_pnl_plot()` and `curve_scenario_overlay()`
