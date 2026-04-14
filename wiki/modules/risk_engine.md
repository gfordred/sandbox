# Module: risk_engine

> Computes DV01, KRD, convexity, modified duration, scenario P&L, and IR delta ladder for any priceable instrument or portfolio.

**File:** `src/risk/risk_engine.py` (418 lines)

## Data classes

### `BucketRisk`
Sensitivity of a single instrument to a +1bp bump in one tenor bucket.
Fields: `tenor: str`, `krd_zar: float`, `krd_bps: float`.

### `ScenarioPnL`
P&L under a named market scenario.
Fields: `scenario: str`, `description: str`, `pnl_zar: float`, `pnl_bps: float`.

### `RiskReport`
Full risk output for one trade:

| Field | Description |
|-------|-------------|
| `trade_id` | Trade identifier |
| `npv_zar` | Mark-to-market (ZAR) |
| `bpv_zar` | Signed BPV (+1bp parallel shift) |
| `dv01_zar` | \|BPV\| |
| `modified_duration` | `−BPV × 10000 / notional` (years) |
| `convexity` | Second-order rate sensitivity |
| `bucket_risk` | `List[BucketRisk]` |
| `scenarios` | `List[ScenarioPnL]` |
| `carry_roll` | Dict from `instrument.carry_and_roll()` |

### `PortfolioRiskReport`
Aggregates `List[RiskReport]` with:
- `total_npv`, `total_bpv`, `total_dv01`
- `net_bucket_dv01` — summed KRD across all trades per bucket
- `bucket_heatmap_data()` — wide DataFrame (trades × tenors) for heatmap charts
- `summary_dataframe()` — tidy table including a PORTFOLIO total row

## RiskEngine

```python
engine = RiskEngine(curve_builder, bump_bps=1.0)
report  = engine.compute(instrument)
portf   = engine.portfolio_risk(instruments)
ladder  = engine.delta_ladder(instruments)
```

### `compute()` — single instrument

1. Prices the instrument at base curve → `base_npv`.
2. **BPV**: parallel shift +1bp, reprice → `bpv = npv_shocked − npv_base`.
3. **Convexity**: `(P(+1bp) + P(−1bp) − 2P) / (P × dr²)`.
4. **KRD**: for each bucket in `KRD_BUCKETS`, bump that quote only, re-bootstrap, reprice → `krd = npv_shocked − npv_base`.
5. **Scenarios**: run 7 named scenarios (see below).
6. **Carry & roll**: calls `instrument.carry_and_roll(horizon_months)` if available.

### Scenarios (hardcoded)

| Name | Type | Description |
|------|------|-------------|
| `PARALLEL_UP_25` | parallel | +25 bps all tenors |
| `PARALLEL_DN_25` | parallel | −25 bps all tenors |
| `PARALLEL_UP_100` | parallel | +100 bps |
| `PARALLEL_DN_100` | parallel | −100 bps |
| `STEEPENER_2s10s` | twist | 2Y +10 / 10Y −10 bps |
| `FLATTENER_2s10s` | twist | 2Y −10 / 10Y +10 bps |
| `STEEPENER_5s10s` | twist | 5Y +10 / 10Y −10 bps |

### `delta_ladder()` — portfolio 01 grid

Returns a DataFrame with rows = trades + NET, columns = tenor buckets, values = ZAR/bp. Computed by bumping each bucket in `KRD_BUCKETS` once for the entire portfolio.

### `_npv_with_curve()` — internal helper

Prices an instrument on an alternate curve **without mutating** the original. Creates a temporary copy of the instrument bound to the new curve. Dispatch: `isinstance` check for `ZARONIAOISSwap` vs `ZARVanillaIRS`.

## See also

- [[concepts/dv01_krd]] — what DV01 and KRD mean financially
- [[concepts/scenario_analysis]] — scenario definitions and interpretation
- [[concepts/carry_roll]] — carry & roll methodology
- [[modules/zaronia_curve]] — curve shocking (`parallel_shift`, `reprice_with_shock`)
- [[modules/hedge_optimizer]] — consumes `RiskEngine` outputs
- [[modules/graphify]] — visualises `RiskReport` and `PortfolioRiskReport`
