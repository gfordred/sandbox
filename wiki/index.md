# Wiki Index

_15 pages · last updated 2026-04-14_

---

## Overview

| Page | Summary |
|------|---------|
| [[overview]] | System-level description: pipeline, module map, SA market conventions |

## Modules

| Page | Summary |
|------|---------|
| [[modules/zaronia_curve]] | OIS curve bootstrap — `ZARCurveBuilder`, market data, shocks, accessors |
| [[modules/risk_engine]] | DV01, KRD, convexity, scenario P&L, delta ladder — `RiskEngine` |
| [[modules/hedge_optimizer]] | Macro and key-rate hedge solver — `HedgeOptimizer`, `HedgePlan` |
| [[modules/ois_swap]] | ZARONIA OIS swap pricer — `ZARONIAOISSwap`, `make_ois_swap()` |
| [[modules/vanilla_irs]] | Fixed/float vanilla IRS pricer — `ZARVanillaIRS`, `make_irs()` |
| [[modules/graphify]] | 12-chart Plotly factory + HTML dashboard — `Graphify` |

## Concepts

| Page | Summary |
|------|---------|
| [[concepts/zaronia]] | What ZARONIA is: RFR analogue of SOFR/SONIA for ZAR, T+0, Act/365 |
| [[concepts/ois_bootstrap]] | Bootstrapping mechanics: instruments, QuantLib internals, interpolation |
| [[concepts/dv01_krd]] | DV01 (parallel BPV) and key-rate duration — definition, formula, book numbers |
| [[concepts/carry_roll]] | 3-month horizon carry + roll — definition, implementation, book numbers |
| [[concepts/scenario_analysis]] | 7 named rate scenarios: parallel, steepener, flattener — P&L methodology |

## Decisions

| Page | Summary |
|------|---------|
| [[decisions/graphify_design]] | Why a dedicated chart factory; the obsidian_graph outlier |
| [[decisions/quantlib_usage]] | Why QuantLib: convention correctness, RelinkableHandle, `_npv_with_curve()` |

## Sources

_No raw sources ingested yet. Drop files into `raw/` and ask to ingest._
