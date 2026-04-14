# Module: ois_swap

> Prices ZARONIA overnight index swaps using QuantLib's OIS swap helper; exposes NPV, BPV, DV01, and carry/roll.

**File:** `src/instruments/ois_swap.py` (253 lines)

## Classes

### `OISSwapSpec`

Dataclass holding trade terms:

```python
@dataclass
class OISSwapSpec:
    notional:    float          # ZAR
    fixed_rate:  float          # decimal
    tenor:       str            # e.g. "3Y"
    direction:   SwapDirection  # PAY_FIXED or RECEIVE_FIXED
    trade_id:    str
```

### `SwapDirection` (enum, shared with vanilla_irs)

```python
class SwapDirection(Enum):
    PAY_FIXED     = "pay_fixed"
    RECEIVE_FIXED = "recv_fixed"
```

### `ZARONIAOISSwap`

Main pricer. Constructor takes `(spec, curve_builder)` and builds a `ql.MakeOIS` swap object internally.

Conventions:
- Settlement lag: T+0 (overnight index convention)
- Day count: Actual/365 Fixed
- Payment frequency: Annual
- Calendar: South Africa

Key properties:
- `npv` — mark-to-market in ZAR (signed by direction)
- `bpv` — signed BPV (ZAR/bp)
- `dv01` — |BPV|
- `carry_and_roll(horizon_months)` — see [[concepts/carry_roll]]

### `make_ois_swap()`

Convenience factory:

```python
swap = make_ois_swap(
    notional=2_500_000_000,
    fixed_rate=0.0700,
    tenor="1Y",
    direction=SwapDirection.RECEIVE_FIXED,
    curve_builder=cb,
    trade_id="OIS-006-1Y-RCV",
)
```

## Book positions (April 2026)

| Trade | Tenor | Notional | Direction | Fixed Rate |
|-------|-------|----------|-----------|------------|
| OIS-005-3Y-PAY | 3Y | ZAR 1.5bn | pay | 7.30% |
| OIS-006-1Y-RCV | 1Y | ZAR 2.5bn | recv | 7.00% |

Both price at NPV ≈ 0 (at-market or near-market rates).

## See also

- [[modules/vanilla_irs]] — fixed/float IRS counterpart
- [[modules/zaronia_curve]] — curve used for pricing
- [[concepts/zaronia]] — ZARONIA index background
- [[concepts/carry_roll]] — carry & roll methodology
