"""
Graphify — Interactive Financial Charts for the ZAR ZARONIA Hedging Desk
=========================================================================
A lightweight chart-builder wrapping Plotly with desk-ready financial layouts.

Provides:
  * yield_curve_plot()         — bootstrapped ZARONIA OIS curve (zero, fwd, discount)
  * dv01_ladder_plot()         — bucket KRD / DV01 bar chart
  * scenario_pnl_plot()        — waterfall chart of scenario P&L
  * portfolio_heatmap()        — KRD heatmap across trades × tenors
  * hedge_effectiveness_plot() — pre/post hedge KRD comparison
  * carry_roll_plot()          — carry + roll decomposition
  * fair_rate_curve_plot()     — OIS par swap rate curve
  * pnl_attribution_plot()     — P&L breakdown by trade / bucket
  * dashboard()                — multi-panel HTML dashboard (all charts)

All charts return plotly Figure objects for further customisation or .show().
The dashboard() method writes a self-contained HTML file.
"""

from __future__ import annotations

import os
import textwrap
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from src.curves.zaronia_curve import ZARCurveBuilder
from src.risk.risk_engine import RiskReport, PortfolioRiskReport, _tenor_sort_key
from src.hedging.hedge_optimizer import HedgePlan


# ---------------------------------------------------------------------------
# Colour palette — inspired by South African flag
# ---------------------------------------------------------------------------

PALETTE = {
    "primary":    "#007A4D",   # SA green
    "secondary":  "#002395",   # SA blue
    "accent":     "#FFB612",   # SA gold
    "danger":     "#DE3831",   # SA red
    "neutral":    "#FFFFFF",
    "dark":       "#1A1A2E",
    "grid":       "#2E3340",
    "text":       "#E0E0E0",
    "pos":        "#2ECC71",   # positive values
    "neg":        "#E74C3C",   # negative values
}

CHART_TEMPLATE = dict(
    template="plotly_dark",
    font=dict(family="Consolas, monospace", size=12, color=PALETTE["text"]),
    paper_bgcolor=PALETTE["dark"],
    plot_bgcolor="#16213E",
    margin=dict(l=60, r=40, t=60, b=60),
)

TENORS_ORDER = ["1M","2M","3M","6M","9M","1Y","18M","2Y","3Y","4Y","5Y","7Y","10Y","12Y","15Y","20Y"]


def _sort_tenors(tenors):
    def _key(t):
        try:
            return _tenor_sort_key(t)
        except Exception:
            return 99
    return sorted(tenors, key=_key)


# ---------------------------------------------------------------------------
# Graphify class
# ---------------------------------------------------------------------------

class Graphify:
    """
    Central chart factory for the ZARONIA desk.

    Parameters
    ----------
    output_dir : path where HTML charts are saved (default: './charts_output')
    """

    def __init__(self, output_dir: str = "./charts_output") -> None:
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. ZARONIA Yield Curve
    # ------------------------------------------------------------------

    def yield_curve_plot(
        self,
        curve_builder: ZARCurveBuilder,
        compare_builder: Optional[ZARCurveBuilder] = None,
        title: str = "ZARONIA OIS Yield Curve — ZAR",
    ) -> go.Figure:
        """
        Triple-panel: zero rates, forward rates, discount factors.
        """
        df = curve_builder.curve_dataframe()
        df = df[df["tenor"].isin(TENORS_ORDER)].copy()
        df["tenor_yf"] = df["year_frac"]

        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=[
                "Zero Rates (Continuous)",
                "Instantaneous Forward Rates (3M)",
                "Discount Factors",
                "Par Swap Rates vs OIS Quotes",
            ],
            vertical_spacing=0.14,
            horizontal_spacing=0.1,
        )

        # --- Zero rates ---
        fig.add_trace(go.Scatter(
            x=df["tenor"], y=df["zero_rate_cc"],
            mode="lines+markers",
            name="Zero Rate (Cont.)",
            line=dict(color=PALETTE["primary"], width=2.5),
            marker=dict(size=7, symbol="circle"),
            hovertemplate="Tenor: %{x}<br>Zero (cc): %{y:.4f}%<extra></extra>",
        ), row=1, col=1)

        if compare_builder:
            dfc = compare_builder.curve_dataframe()
            dfc = dfc[dfc["tenor"].isin(TENORS_ORDER)]
            fig.add_trace(go.Scatter(
                x=dfc["tenor"], y=dfc["zero_rate_cc"],
                mode="lines+markers", name="Stressed Zero",
                line=dict(color=PALETTE["danger"], width=2, dash="dash"),
                marker=dict(size=5),
            ), row=1, col=1)

        # --- Forward rates ---
        fig.add_trace(go.Scatter(
            x=df["tenor"], y=df["fwd_rate_3m"],
            mode="lines+markers", name="3M Fwd Rate",
            line=dict(color=PALETTE["accent"], width=2.5),
            marker=dict(size=7, symbol="diamond"),
            hovertemplate="Tenor: %{x}<br>3M Fwd: %{y:.4f}%<extra></extra>",
        ), row=1, col=2)

        # --- Discount factors ---
        fig.add_trace(go.Scatter(
            x=df["tenor"], y=df["discount_factor"],
            mode="lines+markers", name="Discount Factor",
            fill="tozeroy", fillcolor="rgba(0,122,77,0.15)",
            line=dict(color=PALETTE["secondary"], width=2.5),
            hovertemplate="Tenor: %{x}<br>DF: %{y:.6f}<extra></extra>",
        ), row=2, col=1)

        # --- Par swap rates ---
        par_rates = {}
        for t in ["1Y","2Y","3Y","5Y","7Y","10Y","12Y","15Y","20Y"]:
            try:
                par_rates[t] = curve_builder.par_swap_rate(t) * 100
            except Exception:
                pass
        if par_rates:
            par_df = pd.DataFrame(list(par_rates.items()), columns=["tenor","par_rate"])
            fig.add_trace(go.Scatter(
                x=par_df["tenor"], y=par_df["par_rate"],
                mode="lines+markers", name="Par Swap Rate",
                line=dict(color=PALETTE["primary"], width=2.5),
                marker=dict(size=8, symbol="square"),
            ), row=2, col=2)
            # OIS market quotes
            ois_df = pd.DataFrame(
                [(k, v*100) for k, v in curve_builder.mkt.ois_quotes.items()
                 if k in TENORS_ORDER],
                columns=["tenor","ois_rate"],
            )
            fig.add_trace(go.Scatter(
                x=ois_df["tenor"], y=ois_df["ois_rate"],
                mode="markers", name="OIS Mid Quotes",
                marker=dict(size=9, color=PALETTE["accent"], symbol="x", line=dict(width=2)),
            ), row=2, col=2)

        fig.update_layout(
            title=dict(text=title, font=dict(size=16, color=PALETTE["accent"])),
            showlegend=True,
            legend=dict(bgcolor="rgba(0,0,0,0.4)", bordercolor="#444"),
            **CHART_TEMPLATE,
        )
        fig.update_yaxes(ticksuffix="%", row=1, col=1)
        fig.update_yaxes(ticksuffix="%", row=1, col=2)
        fig.update_yaxes(tickformat=".4f", row=2, col=1)
        fig.update_yaxes(ticksuffix="%", row=2, col=2)

        return fig

    # ------------------------------------------------------------------
    # 2. DV01 Ladder (Bucket Risk)
    # ------------------------------------------------------------------

    def dv01_ladder_plot(
        self,
        risk_report: Union[RiskReport, PortfolioRiskReport],
        title: str = "DV01 Bucket Ladder — ZAR / bp",
    ) -> go.Figure:
        """
        Horizontal bar chart of key-rate DV01 by tenor bucket.
        Positive = long duration (receive fixed), negative = short.
        """
        if isinstance(risk_report, PortfolioRiskReport):
            net_krd = risk_report.net_bucket_dv01
            df = pd.DataFrame(
                [(t, v) for t, v in net_krd.items()],
                columns=["tenor", "krd_zar"],
            )
        else:
            df = risk_report.bucket_dataframe()

        df = df.sort_values("tenor", key=lambda s: s.map(lambda x: _tenor_sort_key(x)))
        colors = [PALETTE["pos"] if v >= 0 else PALETTE["neg"] for v in df["krd_zar"]]

        fig = go.Figure(go.Bar(
            x=df["krd_zar"],
            y=df["tenor"],
            orientation="h",
            marker_color=colors,
            text=[f"ZAR {v:>+,.0f}" for v in df["krd_zar"]],
            textposition="outside",
            hovertemplate="Tenor: %{y}<br>KRD: ZAR %{x:,.0f}<extra></extra>",
            name="KRD",
        ))

        fig.add_vline(x=0, line_dash="solid", line_color="white", line_width=1)

        fig.update_layout(
            title=dict(text=title, font=dict(size=15, color=PALETTE["accent"])),
            xaxis_title="ZAR per +1 bp",
            yaxis_title="Tenor Bucket",
            **CHART_TEMPLATE,
        )
        return fig

    # ------------------------------------------------------------------
    # 3. Scenario P&L
    # ------------------------------------------------------------------

    def scenario_pnl_plot(
        self,
        risk_report: RiskReport,
        title: str = "Scenario P&L — ZAR",
    ) -> go.Figure:
        """Waterfall / bar chart of scenario P&L."""
        df = risk_report.scenario_dataframe()
        if df.empty:
            return self._empty_fig(title)

        colors = [PALETTE["pos"] if v >= 0 else PALETTE["neg"] for v in df["pnl_zar"]]

        fig = go.Figure(go.Bar(
            x=df["scenario"],
            y=df["pnl_zar"],
            marker_color=colors,
            text=[f"ZAR {v:+,.0f}" for v in df["pnl_zar"]],
            textposition="outside",
            customdata=df["description"],
            hovertemplate="<b>%{customdata}</b><br>P&L: ZAR %{y:+,.0f}<extra></extra>",
            name="Scenario P&L",
        ))
        fig.add_hline(y=0, line_color="white", line_width=1)
        fig.update_layout(
            title=dict(text=title, font=dict(size=15, color=PALETTE["accent"])),
            xaxis_title="Scenario",
            yaxis_title="P&L (ZAR)",
            **CHART_TEMPLATE,
        )
        return fig

    # ------------------------------------------------------------------
    # 4. Portfolio KRD Heatmap
    # ------------------------------------------------------------------

    def portfolio_heatmap(
        self,
        portfolio_risk: PortfolioRiskReport,
        title: str = "KRD Heatmap — ZAR / bp by Trade × Tenor",
    ) -> go.Figure:
        """
        Heatmap: rows = trades, columns = tenor buckets.
        Diverging colour scale centred at zero.
        """
        df = portfolio_risk.bucket_heatmap_data()
        cols = _sort_tenors([c for c in df.columns])
        df = df[[c for c in cols if c in df.columns]]

        zmin = df.values.min()
        zmax = df.values.max()
        abs_max = max(abs(zmin), abs(zmax), 1)

        fig = go.Figure(go.Heatmap(
            z=df.values,
            x=list(df.columns),
            y=list(df.index),
            colorscale=[
                [0.0, PALETTE["danger"]],
                [0.5, "#1A1A2E"],
                [1.0, PALETTE["pos"]],
            ],
            zmid=0,
            zmin=-abs_max,
            zmax=abs_max,
            text=[[f"{v:,.0f}" for v in row] for row in df.values],
            texttemplate="%{text}",
            colorbar=dict(title="ZAR / bp", tickformat=","),
            hovertemplate="Trade: %{y}<br>Tenor: %{x}<br>KRD: ZAR %{z:,.0f}<extra></extra>",
        ))
        fig.update_layout(
            title=dict(text=title, font=dict(size=15, color=PALETTE["accent"])),
            xaxis_title="Tenor Bucket",
            yaxis_title="Trade ID",
            **CHART_TEMPLATE,
        )
        return fig

    # ------------------------------------------------------------------
    # 5. Pre/Post Hedge KRD Comparison
    # ------------------------------------------------------------------

    def hedge_effectiveness_plot(
        self,
        hedge_plan: HedgePlan,
        title: str = "Hedge Effectiveness — KRD Before vs After",
    ) -> go.Figure:
        """
        Grouped bar chart: pre-hedge and post-hedge KRD side by side.
        """
        df = hedge_plan.krd_comparison()
        if df.empty:
            return self._empty_fig(title)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df["tenor"], y=df["pre_hedge_ZAR"],
            name="Pre-Hedge KRD",
            marker_color=PALETTE["danger"],
            opacity=0.85,
            text=[f"{v:,.0f}" for v in df["pre_hedge_ZAR"]],
            textposition="outside",
        ))
        fig.add_trace(go.Bar(
            x=df["tenor"], y=df["post_hedge_ZAR"],
            name="Post-Hedge KRD",
            marker_color=PALETTE["pos"],
            opacity=0.85,
            text=[f"{v:,.0f}" for v in df["post_hedge_ZAR"]],
            textposition="outside",
        ))
        fig.add_hline(y=0, line_color="white", line_width=1)
        fig.update_layout(
            title=dict(
                text=f"{title}<br><sup>Effectiveness: {hedge_plan.hedge_effectiveness*100:.1f}%  |  "
                     f"Pre DV01: ZAR {abs(hedge_plan.pre_hedge_bpv):,.0f}  →  "
                     f"Post DV01: ZAR {abs(hedge_plan.post_hedge_bpv):,.0f}</sup>",
                font=dict(size=14, color=PALETTE["accent"]),
            ),
            barmode="group",
            xaxis_title="Tenor Bucket",
            yaxis_title="KRD (ZAR / bp)",
            **CHART_TEMPLATE,
        )
        return fig

    # ------------------------------------------------------------------
    # 6. Carry & Roll Attribution
    # ------------------------------------------------------------------

    def carry_roll_plot(
        self,
        instruments: list,
        horizon_months: int = 3,
        title: str = "3-Month Carry & Roll Attribution",
    ) -> go.Figure:
        """
        Stacked bar: carry vs roll per trade.
        """
        rows = []
        for inst in instruments:
            if hasattr(inst, "carry_and_roll"):
                try:
                    cr = inst.carry_and_roll(horizon_months)
                    rows.append({
                        "trade_id": inst.spec.trade_id or "?",
                        "carry":    cr.get("carry_ZAR", 0.0),
                        "roll":     cr.get("roll_ZAR", 0.0),
                        "total":    cr.get("carry_roll_ZAR", 0.0),
                    })
                except Exception:
                    pass
        if not rows:
            return self._empty_fig(title)

        df = pd.DataFrame(rows)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df["trade_id"], y=df["carry"],
            name="Carry (ZAR)",
            marker_color=PALETTE["secondary"],
            text=[f"{v:+,.0f}" for v in df["carry"]],
            textposition="inside",
        ))
        fig.add_trace(go.Bar(
            x=df["trade_id"], y=df["roll"],
            name="Roll (ZAR)",
            marker_color=PALETTE["accent"],
            text=[f"{v:+,.0f}" for v in df["roll"]],
            textposition="inside",
        ))
        fig.add_trace(go.Scatter(
            x=df["trade_id"], y=df["total"],
            mode="markers+text", name="Total C+R",
            marker=dict(size=12, color=PALETTE["primary"], symbol="star"),
            text=[f"Σ {v:+,.0f}" for v in df["total"]],
            textposition="top center",
        ))
        fig.update_layout(
            title=dict(text=f"{title} ({horizon_months}M)", font=dict(size=15, color=PALETTE["accent"])),
            barmode="stack",
            xaxis_title="Trade",
            yaxis_title="ZAR",
            **CHART_TEMPLATE,
        )
        return fig

    # ------------------------------------------------------------------
    # 7. Delta Ladder (full 01 grid)
    # ------------------------------------------------------------------

    def delta_ladder_plot(
        self,
        ladder_df: pd.DataFrame,
        title: str = "IR Delta Ladder — ZAR DV01 per Tenor Bucket",
    ) -> go.Figure:
        """
        Grouped bar chart from the delta ladder DataFrame.
        Rows are trades; columns are tenor buckets.
        """
        trades = [i for i in ladder_df.index if i != "NET"]
        net = ladder_df.loc["NET"] if "NET" in ladder_df.index else None
        tenors = _sort_tenors([c for c in ladder_df.columns])
        tenors = [t for t in tenors if t in ladder_df.columns]

        colors = px.colors.qualitative.Pastel
        fig = go.Figure()
        for i, trade in enumerate(trades):
            row = ladder_df.loc[trade]
            fig.add_trace(go.Bar(
                x=tenors,
                y=[row.get(t, 0) for t in tenors],
                name=trade,
                marker_color=colors[i % len(colors)],
                opacity=0.8,
            ))
        if net is not None:
            fig.add_trace(go.Scatter(
                x=tenors,
                y=[net.get(t, 0) for t in tenors],
                mode="lines+markers+text",
                name="NET",
                line=dict(color=PALETTE["accent"], width=3, dash="dash"),
                marker=dict(size=10, symbol="diamond"),
                text=[f"{net.get(t,0):+,.0f}" for t in tenors],
                textposition="top center",
                textfont=dict(color=PALETTE["accent"], size=9),
            ))
        fig.add_hline(y=0, line_color="white", line_width=1)
        fig.update_layout(
            title=dict(text=title, font=dict(size=15, color=PALETTE["accent"])),
            barmode="relative",
            xaxis_title="Tenor Bucket",
            yaxis_title="ZAR / bp",
            **CHART_TEMPLATE,
        )
        return fig

    # ------------------------------------------------------------------
    # 8. Curve Scenario Overlay
    # ------------------------------------------------------------------

    def curve_scenario_overlay(
        self,
        base_cb: ZARCurveBuilder,
        scenarios: Dict[str, ZARCurveBuilder],
        title: str = "ZARONIA Curve Scenarios",
    ) -> go.Figure:
        """
        Overlay multiple shocked curves on the base.
        scenarios = {"label": shocked_curve_builder}
        """
        tenors = ["1M","3M","6M","1Y","2Y","3Y","5Y","7Y","10Y","15Y","20Y"]
        fig = go.Figure()

        base_df = base_cb.curve_dataframe()
        base_df = base_df[base_df["tenor"].isin(tenors)]
        fig.add_trace(go.Scatter(
            x=base_df["tenor"], y=base_df["zero_rate_cc"],
            mode="lines+markers", name="Base",
            line=dict(color=PALETTE["primary"], width=3),
            marker=dict(size=8),
        ))

        scene_colors = [
            PALETTE["danger"], PALETTE["accent"], PALETTE["secondary"],
            "#9B59B6", "#1ABC9C",
        ]
        for i, (label, scb) in enumerate(scenarios.items()):
            sdf = scb.curve_dataframe()
            sdf = sdf[sdf["tenor"].isin(tenors)]
            fig.add_trace(go.Scatter(
                x=sdf["tenor"], y=sdf["zero_rate_cc"],
                mode="lines+markers", name=label,
                line=dict(color=scene_colors[i % len(scene_colors)], width=2, dash="dot"),
                marker=dict(size=6),
            ))

        fig.update_layout(
            title=dict(text=title, font=dict(size=15, color=PALETTE["accent"])),
            xaxis_title="Tenor",
            yaxis_title="Zero Rate (%) Continuous",
            yaxis_ticksuffix="%",
            **CHART_TEMPLATE,
        )
        return fig

    # ------------------------------------------------------------------
    # 9. NPV / MTM Gauge
    # ------------------------------------------------------------------

    def mtm_gauge(
        self,
        instruments: list,
        title: str = "Portfolio MTM (NPV) — ZAR",
    ) -> go.Figure:
        """Indicator tiles for each trade's NPV."""
        fig = go.Figure()
        for inst in instruments:
            npv = inst.npv
            fig.add_trace(go.Indicator(
                mode="number+delta",
                value=npv,
                number={"prefix": "ZAR ", "valueformat": ",.0f"},
                delta={"reference": 0, "relative": False,
                       "valueformat": ",.0f",
                       "increasing": {"color": PALETTE["pos"]},
                       "decreasing": {"color": PALETTE["neg"]}},
                title={"text": inst.spec.trade_id or "Trade"},
            ))
        fig.update_layout(
            title=dict(text=title, font=dict(size=15, color=PALETTE["accent"])),
            grid={"rows": max(1, len(instruments) // 3 + 1), "columns": 3, "pattern": "independent"},
            **CHART_TEMPLATE,
        )
        return fig

    # ------------------------------------------------------------------
    # 10. Full HTML Dashboard
    # ------------------------------------------------------------------

    def dashboard(
        self,
        curve_builder: ZARCurveBuilder,
        portfolio_risk: PortfolioRiskReport,
        hedge_plan: Optional[HedgePlan],
        instruments: list,
        ladder_df: Optional[pd.DataFrame] = None,
        output_file: str = "zaronia_desk_dashboard.html",
    ) -> str:
        """
        Render a comprehensive multi-chart HTML dashboard.
        Returns the path to the saved file.
        """
        figs: List[Tuple[str, go.Figure]] = [
            ("ZARONIA Yield Curve",          self.yield_curve_plot(curve_builder)),
            ("DV01 Bucket Ladder",           self.dv01_ladder_plot(portfolio_risk)),
            ("Portfolio KRD Heatmap",        self.portfolio_heatmap(portfolio_risk)),
            ("Carry & Roll Attribution",     self.carry_roll_plot(instruments)),
        ]

        if hedge_plan:
            figs.append(("Hedge Effectiveness", self.hedge_effectiveness_plot(hedge_plan)))

        if len(portfolio_risk.trade_reports) > 0:
            figs.append((
                "Scenario P&L",
                self.scenario_pnl_plot(portfolio_risk.trade_reports[0]),
            ))

        if ladder_df is not None:
            figs.append(("IR Delta Ladder", self.delta_ladder_plot(ladder_df)))

        # Curve scenarios
        scenarios = {
            "Parallel +25bp":  curve_builder.parallel_shift(+25),
            "Parallel -25bp":  curve_builder.parallel_shift(-25),
            "Steepener +10/-10": curve_builder.steepener_shift(-10, +10, "2Y"),
        }
        figs.append(("Curve Scenarios", self.curve_scenario_overlay(curve_builder, scenarios)))

        # Build HTML
        html_parts = [self._dashboard_header()]
        for panel_title, fig in figs:
            html_parts.append(f'<div class="chart-panel"><h2>{panel_title}</h2>')
            html_parts.append(fig.to_html(full_html=False, include_plotlyjs=False))
            html_parts.append("</div>")
        html_parts.append(self._dashboard_footer())

        out_path = os.path.join(self.output_dir, output_file)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(html_parts))
        return out_path

    # ------------------------------------------------------------------
    # Save helper
    # ------------------------------------------------------------------

    def save(self, fig: go.Figure, name: str) -> str:
        """Save a single figure as HTML."""
        path = os.path.join(self.output_dir, f"{name}.html")
        fig.write_html(path)
        return path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_fig(title: str) -> go.Figure:
        fig = go.Figure()
        fig.update_layout(
            title=title,
            annotations=[dict(text="No data available", showarrow=False,
                              font=dict(size=18, color="grey"),
                              xref="paper", yref="paper", x=0.5, y=0.5)],
            **CHART_TEMPLATE,
        )
        return fig

    @staticmethod
    def _dashboard_header() -> str:
        return textwrap.dedent("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>ZARONIA IRS Desk — Hedging Dashboard</title>
          <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
          <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
              background: #1A1A2E;
              color: #E0E0E0;
              font-family: 'Consolas', monospace;
              padding: 20px;
            }
            header {
              background: linear-gradient(135deg, #007A4D, #002395);
              color: white;
              padding: 24px 32px;
              border-radius: 10px;
              margin-bottom: 24px;
              border-left: 6px solid #FFB612;
            }
            header h1 { font-size: 26px; letter-spacing: 1px; }
            header p  { font-size: 13px; color: #ccc; margin-top: 6px; }
            .chart-grid {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(680px, 1fr));
              gap: 20px;
            }
            .chart-panel {
              background: #16213E;
              border-radius: 10px;
              padding: 16px;
              border: 1px solid #2E3340;
            }
            .chart-panel h2 {
              font-size: 13px;
              color: #FFB612;
              text-transform: uppercase;
              letter-spacing: 2px;
              margin-bottom: 12px;
              border-bottom: 1px solid #2E3340;
              padding-bottom: 8px;
            }
            footer {
              margin-top: 32px;
              text-align: center;
              font-size: 11px;
              color: #555;
            }
          </style>
        </head>
        <body>
          <header>
            <h1>ZARONIA IRS Desk — Hedging Analytics Dashboard</h1>
            <p>South African Rand Overnight Index Average &nbsp;|&nbsp;
               QuantLib 1.42 &nbsp;|&nbsp; PhD-Level Rates Analytics &nbsp;|&nbsp;
               Development Bank Desk</p>
          </header>
          <div class="chart-grid">
        """)

    @staticmethod
    def _dashboard_footer() -> str:
        return textwrap.dedent("""
          </div>
          <footer>
            ZARONIA Desk Hedging System &copy; 2026 &nbsp;|&nbsp;
            Built with QuantLib + Plotly &nbsp;|&nbsp;
            All analytics for institutional use only.
          </footer>
        </body>
        </html>
        """)
