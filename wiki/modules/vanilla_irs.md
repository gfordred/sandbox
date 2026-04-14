# Module: vanilla_irs

> Prices ZAR fixed/float vanilla interest rate swaps against the ZARONIA curve; exposes NPV, BPV, DV01, and carry/roll.

**File:** `src/instruments/vanilla_irs.py` (316 lines)

## Classes

### `IRSSpec`

```python
@dataclass
class IRSSpec:
    notional:        float
    fixed_rate:      float
    maturity_tenor:  str            # e.g. "10Y"
    direction:       SwapDirection
    trade_id:        str
```

### `ZARVanillaIRS`

Prices using `ql.VanillaSwap` with:
- Fixed leg: Annual, Actual/365 Fixed
- Float leg: Annual, Actual/365 Fixed, linked to `ZARONIAIndex`
- Settlement: T+2

Key properties match `ZARONIAOISSwap`: `npv`, `bpv`, `dv01`, `carry_and_roll()`.

### `make_irs()`

Factory function:

```python
swap = make_irs(
    notional=5_000_000_000,
    fixed_rate=0.0810,
    maturity="10Y",
    direction=SwapDirection.RECEIVE_FIXED,
    curve_builder=cb,
    trade_id="IRS-001-10Y-RCV",
)
```

## Book positions (April 2026)

| Trade | Tenor | Notional | Direction | Fixed Rate | DV01 ZAR |
|-------|-------|----------|-----------|------------|----------|
| IRS-001-10Y-RCV | 10Y | ZAR 5.0bn | recv | 8.10% | 3,379,290 |
| IRS-002-5Y-PAY | 5Y | ZAR 3.0bn | pay | 7.60% | 1,216,447 |
| IRS-003-2Y-RCV | 2Y | ZAR 2.0bn | recv | 7.15% | 362,108 |
| IRS-004-7Y-RCV | 7Y | ZAR 4.0bn | recv | 7.85% | 2,112,392 |

The 10Y receiver is the dominant risk position.

## Difference from OIS swaps

Vanilla IRS uses a **fixed settlement lag of T+2** (vs T+0 for OIS) and a standard `VanillaSwap` structure (no daily compounding). In the current implementation both legs reference the ZARONIA curve for discounting, meaning there is no JIBAR/ZARONIA basis modelled.

## See also

- [[modules/ois_swap]] — OIS counterpart with daily compounding
- [[modules/zaronia_curve]] — discount and projection curve
- [[concepts/dv01_krd]] — how DV01 is computed
- [[concepts/carry_roll]] — 3-month carry & roll
