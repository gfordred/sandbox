# Concept: Carry and Roll

> Carry is P&L from holding a position as time passes; roll is P&L from the position "rolling down" a positively-sloped curve as its maturity shortens.

## Definitions

**Carry** — the income (or cost) of holding a position for a period, assuming rates stay unchanged. For a receiver swap: carry ≈ (fixed rate − current overnight rate) × notional × time. For a pay-fixed swap it is the opposite sign.

**Roll** — when you hold a 10Y receiver for 3 months, it becomes a 9Y9M receiver. If the curve is upward-sloping (10Y rate > 9Y9M rate), the fair value increases as the instrument rolls to a lower-rate tenor. This P&L is the roll.

**Carry + Roll (C+R)** — the total 3-month horizon P&L assuming a static curve. A core measure for rates desk P&L forecasting.

## Implementation

`carry_and_roll(horizon_months=3)` is defined on both `ZARVanillaIRS` and `ZARONIAOISSwap`. It:

1. Prices the instrument today: `npv_t0`.
2. Advances QuantLib's valuation date by `horizon_months`.
3. Re-prices the instrument on the same curve (static rates): `npv_t1`.
4. `carry_roll_ZAR = npv_t1 − npv_t0`.

The carry and roll components are estimated separately:
- `carry_bps` is an approximation based on fixed rate vs overnight rate
- `carry_ZAR = carry_bps × notional / 10000 × horizon`
- `roll_ZAR = carry_roll_ZAR − carry_ZAR`

## April 2026 book (3M horizon, static curve)

| Trade | Carry ZAR | Roll ZAR | Total ZAR |
|-------|-----------|----------|-----------|
| IRS-001-10Y-RCV | +7.5m | +6.5m | +14.0m |
| IRS-002-5Y-PAY | −0.7m | −4.7m | −5.4m |
| IRS-003-2Y-RCV | −1.7m | +1.5m | −0.3m |
| IRS-004-7Y-RCV | +3.5m | +5.8m | +9.2m |

OIS swaps (001, 006) return 0 in the current implementation — `carry_and_roll` is not wired for OIS instruments.

## See also

- [[modules/vanilla_irs]] — implements `carry_and_roll()`
- [[modules/ois_swap]] — partially implements `carry_and_roll()`
- [[modules/graphify]] — `carry_roll_plot()` visualises this
- [[concepts/scenario_analysis]] — carry is a static-curve scenario
