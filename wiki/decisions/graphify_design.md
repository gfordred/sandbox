# Decision: Graphify Design

> Why a dedicated chart factory class rather than inline Plotly calls in main.py.

## Context

The system produces 12 charts and a multi-panel dashboard. The early prototype had chart code scattered through `main.py` — hard to maintain, no consistent styling, and dashboard assembly was ad hoc.

## Decision

Centralise all charting in a single `Graphify` class (`src/charts/graphify.py`) that:
1. Owns a shared `PALETTE` dict and `CHART_TEMPLATE` dict.
2. Exposes one method per chart, each returning a `go.Figure`.
3. Provides `save(fig, name)` for single-chart HTML export.
4. Provides `dashboard(...)` to assemble everything into one HTML file.

## Consequences

**Good:**
- Every chart automatically uses the same dark theme, fonts, and colour system.
- `main.py` is clean — `step_charts()` is a flat dictionary of method calls.
- New charts are added in one place; dashboard picks them up by adding one line.
- Charts are independently viewable as standalone HTML files.

**Trade-off:**
- `Graphify.__init__` takes no data — all data is passed to each method. This means the dashboard method re-computes some charts (yield curve, scenarios) that were already computed in `step_charts()`. Acceptable duplication at this scale.

## The obsidian_graph outlier

`obsidian_graph()` is unusual — it has nothing to do with rates analytics. It uses `ast` and `networkx` to visualise the codebase's import graph. It was added to `Graphify` rather than a separate tool because:
- It fits the "interactive HTML chart" pattern.
- Obsidian's graph view inspired the wiki; embedding it in the dashboard is thematically appropriate.
- It reuses `PALETTE` and `CHART_TEMPLATE` for consistent styling.

## See also

- [[modules/graphify]] — full chart inventory
- [[decisions/quantlib_usage]] — analogous decision for the pricing layer
