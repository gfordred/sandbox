# Graph Report - .  (2026-04-15)

## Corpus Check
- Corpus is ~10,225 words - fits in a single context window. You may not need a graph.

## Summary
- 221 nodes · 666 edges · 16 communities detected
- Extraction: 45% EXTRACTED · 55% INFERRED · 0% AMBIGUOUS · INFERRED: 363 edges (avg confidence: 0.57)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Hedge Optimization Engine|Hedge Optimization Engine]]
- [[_COMMUNITY_Dashboard & Visualization|Dashboard & Visualization]]
- [[_COMMUNITY_Swap Analytics & Risk Metrics|Swap Analytics & Risk Metrics]]
- [[_COMMUNITY_ZARONIA OIS Instrument|ZARONIA OIS Instrument]]
- [[_COMMUNITY_CLI Entry Point|CLI Entry Point]]
- [[_COMMUNITY_Curve Construction|Curve Construction]]
- [[_COMMUNITY_Curve Analytics & Output|Curve Analytics & Output]]
- [[_COMMUNITY_Market Data & Bootstrap|Market Data & Bootstrap]]
- [[_COMMUNITY_Risk Engine|Risk Engine]]
- [[_COMMUNITY_Key Rate Duration|Key Rate Duration]]
- [[_COMMUNITY_Python Dependencies|Python Dependencies]]
- [[_COMMUNITY_Hedge Optimizer Module|Hedge Optimizer Module]]
- [[_COMMUNITY_Swap Repricing|Swap Repricing]]
- [[_COMMUNITY_Graphify Config|Graphify Config]]
- [[_COMMUNITY_Package Init|Package Init]]
- [[_COMMUNITY_Market Data Snapshot|Market Data Snapshot]]

## God Nodes (most connected - your core abstractions)
1. `ZARCurveBuilder` - 81 edges
2. `ZARVanillaIRS` - 43 edges
3. `ZARONIAOISSwap` - 40 edges
4. `RiskReport` - 35 edges
5. `PortfolioRiskReport` - 35 edges
6. `HedgePlan` - 31 edges
7. `OISSwapSpec` - 31 edges
8. `ZARONIAIndex` - 30 edges
9. `RiskEngine` - 28 edges
10. `SwapDirection` - 25 edges

## Surprising Connections (you probably didn't know these)
- `step_curve()` --calls--> `ZARCurveBuilder`  [INFERRED]
  main.py → src\curves\zaronia_curve.py
- `step_portfolio()` --calls--> `make_irs()`  [INFERRED]
  main.py → src\instruments\vanilla_irs.py
- `step_portfolio()` --calls--> `make_ois_swap()`  [INFERRED]
  main.py → src\instruments\ois_swap.py
- `step_risk()` --calls--> `RiskEngine`  [INFERRED]
  main.py → src\risk\risk_engine.py
- `step_delta_ladder()` --calls--> `RiskEngine`  [INFERRED]
  main.py → src\risk\risk_engine.py

## Hyperedges (group relationships)
- **Quantitative Finance Computation Stack** — requirements_quantlib, requirements_numpy, requirements_pandas, requirements_scipy [INFERRED 0.85]
- **Visualization Stack** — requirements_plotly, requirements_kaleido [INFERRED 0.90]

## Communities

### Community 0 - "Hedge Optimization Engine"
Cohesion: 0.12
Nodes (29): HedgeOptimizer, PortfolioBlotter, Desk Hedging Optimizer — ZAR Rates Desk =======================================, Rates desk hedge optimizer for a ZAR IRS / ZARONIA OIS portfolio.      Usage, Flatten total portfolio DV01 with a single on-the-run OIS/IRS.          Parame, Minimise residual KRD vector via a basket of hedge instruments.         Uses mi, DV01 hedge with convexity adjustment.         Hedge notional adjusted so that c, Return the notional ratio (hedge/portfolio) needed to achieve         target_fr (+21 more)

### Community 1 - "Dashboard & Visualization"
Cohesion: 0.1
Nodes (19): _dashboard_footer(), _dashboard_header(), _empty_fig(), Graphify, Graphify — Interactive Financial Charts for the ZAR ZARONIA Hedging Desk ======, Central chart factory for the ZARONIA desk.      Parameters     ----------, Horizontal bar chart of key-rate DV01 by tenor bucket.         Positive = long, Waterfall / bar chart of scenario P&L. (+11 more)

### Community 2 - "Swap Analytics & Risk Metrics"
Cohesion: 0.11
Nodes (8): Enum, bpv(), dollar_convexity(), npv(), ZARONIA OIS Swap Instrument =========================== Overnight Index Swap:, bpv(), convexity(), Shift all OIS quotes by bump_bps simultaneously.

### Community 3 - "ZARONIA OIS Instrument"
Cohesion: 0.2
Nodes (18): Basis Point Value = dNPV / d(+1bp) — signed (positive = long duration)., Absolute DV01 = |BPV|  (always positive by convention)., Approximate modified duration = -BPV * 10000 / notional., Dollar convexity = (NPV(+1bp) + NPV(-1bp) - 2*NPV(base)) * 10^8., Return a DataFrame of fixed and floating leg cash flows., Specification for a single ZARONIA OIS trade., A ZARONIA Overnight Index Swap priced with QuantLib.      The QL instrument is, SwapDirection (+10 more)

### Community 4 - "CLI Entry Point"
Cohesion: 0.41
Nodes (12): hdr(), info(), main(), ok(), _sort_key(), step_carry_roll(), step_charts(), step_curve() (+4 more)

### Community 5 - "Curve Construction"
Cohesion: 0.17
Nodes (8): make_ois_swap(), Convenience constructor., build_jibar_swap_curve(), build_zaronia_ois_curve(), current_market(), ZARONIA OIS Curve Construction — South African Rand Overnight Index Average ===, One-shot builder — returns a fully built ZARCurveBuilder., Alias; both curves are built simultaneously in ZARCurveBuilder.

### Community 6 - "Curve Analytics & Output"
Cohesion: 0.21
Nodes (6): Triple-panel: zero rates, forward rates, discount factors., _add_period(), Par rate of a ZARONIA OIS at given maturity (used for implied swap rate)., Return a tidy DataFrame of the bootstrapped OIS curve., Advance ref date by a QL period string, respecting SA calendar., _tenor_to_date()

### Community 7 - "Market Data & Bootstrap"
Cohesion: 0.22
Nodes (6): Estimate carry & roll over a horizon.         Carry = coupon income - funding c, Bootstrap both curves; wire handles., Linear steepener / flattener centred at pivot_tenor., JIBAR projection curve bootstrapped from legacy swap quotes., Raw OIS market quotes for a single valuation date.     All rates are in decimal, ZARONIAMarketData

### Community 8 - "Risk Engine"
Cohesion: 0.25
Nodes (1): _tenor_sort_key()

### Community 9 - "Key Rate Duration"
Cohesion: 0.29
Nodes (3): Key-rate DV01 per tenor bucket.         Returns {tenor: dv01_zar} where dv01_za, Per-bucket KRD: {tenor: ZAR_per_1bp}., Return a list of shocked curve builders — one per bucket tenor.         Used fo

### Community 10 - "Python Dependencies"
Cohesion: 0.48
Nodes (7): kaleido >=0.2, numpy >=1.26, pandas >=2.2, plotly >=5.20, QuantLib >=1.42, scipy >=1.12, Python Requirements

### Community 11 - "Hedge Optimizer Module"
Cohesion: 0.5
Nodes (0): 

### Community 12 - "Swap Repricing"
Cohesion: 0.5
Nodes (1): Re-link to a new curve builder (used for scenario / DV01 calcs).

### Community 13 - "Graphify Config"
Cohesion: 0.5
Nodes (4): Graph Report (graphify-out/GRAPH_REPORT.md), Graphify Configuration, graphify update . command, Wiki Index (graphify-out/wiki/index.md)

### Community 14 - "Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 15 - "Market Data Snapshot"
Cohesion: 1.0
Nodes (1): Indicative market snapshot — April 2026.         SARB repo held at 7.50 % follo

## Knowledge Gaps
- **18 isolated node(s):** `ZARONIA OIS Curve Construction — South African Rand Overnight Index Average ===`, `ZARONIA — Rand Overnight Index Average.     Mirrors the SONIA / SOFR / €STR fam`, `Raw OIS market quotes for a single valuation date.     All rates are in decimal`, `Indicative market snapshot — April 2026.         SARB repo held at 7.50 % follo`, `Constructs the ZARONIA OIS discount curve and (optionally) a     JIBAR projecti` (+13 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Market Data Snapshot`** (1 nodes): `Indicative market snapshot — April 2026.         SARB repo held at 7.50 % follo`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ZARCurveBuilder` connect `ZARONIA OIS Instrument` to `Hedge Optimization Engine`, `Dashboard & Visualization`, `Swap Analytics & Risk Metrics`, `CLI Entry Point`, `Curve Construction`, `Curve Analytics & Output`, `Market Data & Bootstrap`, `Key Rate Duration`, `Swap Repricing`?**
  _High betweenness centrality (0.350) - this node is a cross-community bridge._
- **Why does `ZARVanillaIRS` connect `Hedge Optimization Engine` to `Dashboard & Visualization`, `Swap Analytics & Risk Metrics`, `ZARONIA OIS Instrument`, `Market Data & Bootstrap`, `Key Rate Duration`?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **Why does `ZARONIAOISSwap` connect `Hedge Optimization Engine` to `Dashboard & Visualization`, `Swap Analytics & Risk Metrics`, `ZARONIA OIS Instrument`, `Curve Construction`, `Key Rate Duration`, `Swap Repricing`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Are the 66 inferred relationships involving `ZARCurveBuilder` (e.g. with `Graphify` and `Graphify — Interactive Financial Charts for the ZAR ZARONIA Hedging Desk ======`) actually correct?**
  _`ZARCurveBuilder` has 66 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `ZARVanillaIRS` (e.g. with `HedgePlan` and `HedgeOptimizer`) actually correct?**
  _`ZARVanillaIRS` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `ZARONIAOISSwap` (e.g. with `HedgePlan` and `HedgeOptimizer`) actually correct?**
  _`ZARONIAOISSwap` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `RiskReport` (e.g. with `Graphify` and `Graphify — Interactive Financial Charts for the ZAR ZARONIA Hedging Desk ======`) actually correct?**
  _`RiskReport` has 29 INFERRED edges - model-reasoned connections that need verification._