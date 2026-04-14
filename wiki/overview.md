# ZARONIA IRS Desk — System Overview

> A QuantLib-based rates desk analytics system for South African ZAR interest rate swaps and OIS, covering curve bootstrap, risk, hedging, carry/roll, and interactive charting.

## What it does

The system models a South African development-bank rates desk operating ZARONIA-indexed OIS swaps and vanilla fixed/float IRS. It runs a complete analytics pipeline in a single `python main.py` invocation:

1. **Curve bootstrap** — fits a ZARONIA OIS discount curve from overnight + 18 OIS quotes (1W → 20Y) using QuantLib's `PiecewiseLogLinearDiscount` bootstrapper.
2. **Portfolio construction** — builds a 6-trade book (4 vanilla IRS + 2 OIS) with realistic ZAR notionals (ZAR 1.5bn – 5bn).
3. **Risk computation** — computes DV01, BPV, KRD (per-bucket), convexity, modified duration, and scenario P&L for each trade and the portfolio.
4. **Delta ladder** — a full 01-grid showing each trade's sensitivity to each tenor bucket.
5. **Hedging** — solves for macro (single-tenor DV01 flatten) and key-rate (multi-tenor bucket) hedges.
6. **Carry & roll** — 3-month horizon carry and roll attribution per trade.
7. **Charting** — 12 interactive Plotly charts + a self-contained HTML dashboard.

## Module map

```
main.py                     CLI entry point / orchestrator
src/
  curves/zaronia_curve.py   Market data, curve builder, accessors
  instruments/
    ois_swap.py             ZARONIA OIS swap pricer
    vanilla_irs.py          Fixed/float IRS pricer
  risk/risk_engine.py       DV01, KRD, scenario, delta ladder
  hedging/hedge_optimizer.py Macro + key-rate hedge solver
  charts/graphify.py        12-chart Plotly factory + dashboard
```

## South Africa market conventions

| Convention | Value |
|------------|-------|
| Calendar | `ql.SouthAfrica()` |
| Day count | `Actual/365 Fixed` |
| OIS settlement | T+0 |
| IRS settlement | T+2 |
| Business day | Modified Following |
| Currency | ZAR |

## Key design choices

- **QuantLib native** — all pricing runs through QuantLib objects on a `RelinkableYieldTermStructureHandle`; curve shocks reprice all instruments automatically.
- **Finite-difference risk** — DV01 and KRD are computed by bumping OIS quotes and re-bootstrapping, not analytically.
- **Plotly for charts** — all output is interactive HTML; no static image dependencies.
- **Pure Python** — no database, no message bus, no external services.

## Entry point

```bash
python main.py                      # full run + HTML dashboard
python main.py --no-dashboard       # suppress dashboard
python main.py --output-dir ./out   # custom chart directory
```

## See also

- [[modules/zaronia_curve]] — curve bootstrap details
- [[modules/risk_engine]] — how DV01/KRD are computed
- [[modules/hedge_optimizer]] — hedge solver
- [[modules/graphify]] — chart factory
- [[concepts/zaronia]] — what ZARONIA is
