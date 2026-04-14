# Module: graphify

> 12-chart Plotly factory and HTML dashboard for the ZARONIA desk; also generates an Obsidian-style module dependency graph.

**File:** `src/charts/graphify.py` (≈1340 lines)

## Class: `Graphify`

```python
g = Graphify(output_dir="./charts_output")
```

`output_dir` is created on init. All `save()` and `dashboard()` calls write here.

## Chart inventory

| Method | Output | Type |
|--------|--------|------|
| `yield_curve_plot(cb)` | 4-panel: zero rates, 3M fwd, discount factors, par vs OIS | Scatter subplots |
| `fair_rate_curve_plot(cb)` | Par swap rates vs OIS quotes + spread (bps) | Scatter + bar subplots |
| `dv01_ladder_plot(risk)` | Horizontal bar of net KRD by bucket | Bar |
| `portfolio_heatmap(port_risk)` | Trades × tenors KRD heatmap | Heatmap |
| `pnl_attribution_plot(port_risk)` | NPV and BPV per trade, side-by-side | Horizontal bar |
| `scenario_pnl_plot(risk_report)` | Scenario P&L waterfall | Bar |
| `hedge_effectiveness_plot(hedge_plan)` | Pre/post hedge KRD, grouped bars | Grouped bar |
| `carry_roll_plot(instruments)` | Carry + roll per trade, stacked | Stacked bar + scatter |
| `delta_ladder_plot(ladder_df)` | Per-trade KRD stacked by bucket | Relative bar |
| `curve_scenario_overlay(cb, scenarios)` | Multiple shocked curves overlaid | Multi-line |
| `obsidian_graph(root_dir)` | Force-directed module dependency graph | Network (Scatter + annotations) |
| `mtm_gauge(instruments)` | Indicator tiles for each trade's NPV | Indicator |

## `obsidian_graph()`

Walks the project tree with `ast` to extract import edges between local Python modules. Builds a directed `networkx` graph, computes a spring layout (`seed=42`), and renders as Plotly Scatter with arrow annotations. Nodes are coloured by top-level package and sized by degree.

```python
fig = g.obsidian_graph(root_dir=".")
fig = g.obsidian_graph(root_dir=".", include_external=True)  # adds numpy, ql, etc.
```

## `dashboard()`

Assembles all charts into a single self-contained HTML file. Sections (with dividers):

1. **Curve & Rates** — yield curve, fair-rate curve
2. **Risk & Greeks** — DV01 ladder, KRD heatmap, P&L attribution
3. **Hedging** — hedge effectiveness (key-rate and/or macro)
4. **P&L Attribution** — carry/roll, scenario P&L
5. **Delta Ladder** — full 01 grid (full-width)
6. **Curve Scenarios** — shocked curve overlay
7. **Codebase** — obsidian module graph (full-width)

CSS uses IBM Plex Mono/Sans, dark theme (`#080C14` background), SA flag colour accents.

## Colour system

Central `PALETTE` dict with semantic names: `"primary"` (SA green `#00A85A`), `"accent"` (SA gold `#F5C400`), `"secondary"` (SA blue `#1A4FBF`), `"pos"` / `"neg"` for gain/loss. All charts share this palette via `CHART_TEMPLATE`.

## `save()` and file outputs

```python
path = g.save(fig, "yield_curve")   # writes charts_output/yield_curve.html
```

Each chart is a standalone interactive HTML file. The dashboard bundles everything with a single Plotly CDN `<script>` tag.

## See also

- [[decisions/graphify_design]] — design rationale
- [[modules/risk_engine]] — `RiskReport` / `PortfolioRiskReport` consumed here
- [[modules/hedge_optimizer]] — `HedgePlan` consumed here
- [[modules/zaronia_curve]] — `ZARCurveBuilder` consumed here
- [[concepts/dv01_krd]] — what the KRD charts represent
