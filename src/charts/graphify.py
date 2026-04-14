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

import ast
import os
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from src.curves.zaronia_curve import ZARCurveBuilder
from src.risk.risk_engine import RiskReport, PortfolioRiskReport, _tenor_sort_key
from src.hedging.hedge_optimizer import HedgePlan


# ---------------------------------------------------------------------------
# Bank-grade colour system — South African flag tones, refined
# ---------------------------------------------------------------------------

PALETTE = {
    # Brand / SA flag
    "primary":      "#00A85A",   # SA green — slightly brighter for dark bg
    "secondary":    "#1A4FBF",   # SA blue — lifted for readability
    "accent":       "#F5C400",   # SA gold — warm, not harsh
    "danger":       "#E84040",   # loss red
    "black":        "#002395",   # deep SA blue (borders, accents)
    # Surface hierarchy
    "bg_base":      "#080C14",   # canvas — near-black navy
    "bg_panel":     "#0D1420",   # chart background
    "bg_card":      "#111927",   # card / panel surface
    "bg_header":    "#0A1628",   # header bar
    "border":       "#1E2D42",   # subtle panel border
    "border_bright":"#2A3F5F",   # highlighted border
    # Typography
    "text_primary": "#E8EDF5",   # primary label — cool white
    "text_secondary":"#8A9BB5",  # secondary / axis labels
    "text_muted":   "#4A5A72",   # disabled / minor annotation
    "text_accent":  "#F5C400",   # callout label (gold)
    # Semantic
    "pos":          "#00C875",   # gain / long
    "neg":          "#E84040",   # loss / short
    "neutral":      "#6B8ABF",   # flat / zero
    # Grid
    "grid_line":    "#162030",   # subtle gridlines
}

# IBM Plex Mono — the font used across Bloomberg, Refinitiv, institutional terminals.
# Falls back through JetBrains Mono → Consolas → monospace.
_FONT_MONO  = "'IBM Plex Mono', 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace"
_FONT_SANS  = "'IBM Plex Sans', 'Inter', 'Segoe UI', 'Helvetica Neue', sans-serif"
_FONT_NUM   = "'IBM Plex Mono', 'Tabular Numbers', 'Consolas', monospace"

CHART_TEMPLATE = dict(
    template="plotly_dark",
    font=dict(family=_FONT_MONO, size=11, color=PALETTE["text_primary"]),
    paper_bgcolor=PALETTE["bg_panel"],
    plot_bgcolor=PALETTE["bg_panel"],
    margin=dict(l=68, r=32, t=68, b=52),
    colorway=[
        PALETTE["primary"], PALETTE["accent"], PALETTE["secondary"],
        "#9B72CF", "#2EC4B6", "#E07A5F", "#81B29A", "#F2CC8F",
    ],
    xaxis=dict(
        gridcolor=PALETTE["grid_line"],
        linecolor=PALETTE["border"],
        tickfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_secondary"]),
        title_font=dict(family=_FONT_SANS, size=11, color=PALETTE["text_secondary"]),
        zeroline=False,
    ),
    yaxis=dict(
        gridcolor=PALETTE["grid_line"],
        linecolor=PALETTE["border"],
        tickfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_secondary"]),
        title_font=dict(family=_FONT_SANS, size=11, color=PALETTE["text_secondary"]),
        zeroline=False,
    ),
    legend=dict(
        bgcolor="rgba(8,12,20,0.75)",
        bordercolor=PALETTE["border_bright"],
        borderwidth=1,
        font=dict(family=_FONT_MONO, size=10, color=PALETTE["text_secondary"]),
    ),
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
            title=dict(
                text=title,
                font=dict(family=_FONT_SANS, size=15, color=PALETTE["text_accent"]),
                x=0.0, xanchor="left", pad=dict(l=4),
            ),
            showlegend=True,
            **CHART_TEMPLATE,
        )
        # Uniform axis styling across all subplots
        for row in (1, 2):
            for col in (1, 2):
                fig.update_xaxes(
                    gridcolor=PALETTE["grid_line"], linecolor=PALETTE["border"],
                    tickfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_secondary"]),
                    row=row, col=col,
                )
                fig.update_yaxes(
                    gridcolor=PALETTE["grid_line"], linecolor=PALETTE["border"],
                    tickfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_secondary"]),
                    row=row, col=col,
                )
        fig.update_yaxes(ticksuffix="%", row=1, col=1)
        fig.update_yaxes(ticksuffix="%", row=1, col=2)
        fig.update_yaxes(tickformat=".5f", row=2, col=1)
        fig.update_yaxes(ticksuffix="%", row=2, col=2)
        # Subplot title font
        for ann in fig.layout.annotations:
            ann.font = dict(family=_FONT_SANS, size=11, color=PALETTE["text_secondary"])

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
            marker_line=dict(width=0),
            text=[f"{v:>+,.0f}" for v in df["krd_zar"]],
            textposition="outside",
            textfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_secondary"]),
            hovertemplate="<b>%{y}</b><br>KRD: ZAR %{x:,.0f}/bp<extra></extra>",
            name="KRD",
        ))

        fig.add_vline(x=0, line_dash="solid", line_color=PALETTE["border_bright"], line_width=1)

        fig.update_layout(
            title=dict(
                text=title,
                font=dict(family=_FONT_SANS, size=14, color=PALETTE["text_accent"]),
                x=0.0, xanchor="left",
            ),
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
            marker_line=dict(width=0),
            text=[f"{v:+,.0f}" for v in df["pnl_zar"]],
            textposition="outside",
            textfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_primary"]),
            customdata=df["description"],
            hovertemplate="<b>%{customdata}</b><br>P&L: ZAR %{y:+,.0f}<extra></extra>",
            name="Scenario P&L",
        ))
        fig.add_hline(y=0, line_color=PALETTE["border_bright"], line_width=1)
        fig.update_layout(
            title=dict(
                text=title,
                font=dict(family=_FONT_SANS, size=14, color=PALETTE["text_accent"]),
                x=0.0, xanchor="left",
            ),
            **CHART_TEMPLATE,
        )
        fig.update_xaxes(title_text="Scenario",
                         tickfont=dict(family=_FONT_MONO, size=9))
        fig.update_yaxes(title_text="P&L (ZAR)")
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
                [0.0,  PALETTE["neg"]],
                [0.42, "#162030"],
                [0.5,  PALETTE["bg_panel"]],
                [0.58, "#0D2318"],
                [1.0,  PALETTE["pos"]],
            ],
            zmid=0,
            zmin=-abs_max,
            zmax=abs_max,
            text=[[f"{v:,.0f}" for v in row] for row in df.values],
            texttemplate="%{text}",
            textfont=dict(family=_FONT_MONO, size=9, color=PALETTE["text_primary"]),
            colorbar=dict(
                title=dict(text="ZAR/bp", font=dict(family=_FONT_SANS, size=10, color=PALETTE["text_secondary"])),
                tickfont=dict(family=_FONT_MONO, size=9, color=PALETTE["text_secondary"]),
                tickformat=",",
                outlinewidth=0,
                thickness=12,
            ),
            hovertemplate="Trade: <b>%{y}</b><br>Tenor: <b>%{x}</b><br>KRD: ZAR %{z:,.0f}<extra></extra>",
        ))
        fig.update_layout(
            title=dict(
                text=title,
                font=dict(family=_FONT_SANS, size=14, color=PALETTE["text_accent"]),
                x=0.0, xanchor="left",
            ),
            **CHART_TEMPLATE,
        )
        fig.update_xaxes(title_text="Tenor Bucket",
                         tickfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_secondary"]))
        fig.update_yaxes(title_text="Trade ID",
                         tickfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_secondary"]))
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
            marker_color=PALETTE["neg"],
            marker_line=dict(width=0),
            opacity=0.9,
            text=[f"{v:,.0f}" for v in df["pre_hedge_ZAR"]],
            textposition="outside",
            textfont=dict(family=_FONT_MONO, size=9, color=PALETTE["text_muted"]),
        ))
        fig.add_trace(go.Bar(
            x=df["tenor"], y=df["post_hedge_ZAR"],
            name="Post-Hedge KRD",
            marker_color=PALETTE["pos"],
            marker_line=dict(width=0),
            opacity=0.9,
            text=[f"{v:,.0f}" for v in df["post_hedge_ZAR"]],
            textposition="outside",
            textfont=dict(family=_FONT_MONO, size=9, color=PALETTE["text_secondary"]),
        ))
        fig.add_hline(y=0, line_color=PALETTE["border_bright"], line_width=1)
        eff_pct = hedge_plan.hedge_effectiveness * 100
        eff_colour = PALETTE["pos"] if eff_pct >= 80 else PALETTE["accent"]
        fig.update_layout(
            title=dict(
                text=(
                    f"{title}  "
                    f"<span style='color:{eff_colour}'>{eff_pct:.1f}% effective</span>"
                    f"<br><sup style='color:{PALETTE['text_muted']}'>"
                    f"Pre DV01: {abs(hedge_plan.pre_hedge_bpv):,.0f}  →  "
                    f"Post DV01: {abs(hedge_plan.post_hedge_bpv):,.0f}</sup>"
                ),
                font=dict(family=_FONT_SANS, size=13, color=PALETTE["text_primary"]),
                x=0.0, xanchor="left",
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
            name="Carry",
            marker_color=PALETTE["secondary"],
            marker_line=dict(width=0),
            text=[f"{v:+,.0f}" for v in df["carry"]],
            textposition="inside",
            textfont=dict(family=_FONT_MONO, size=9, color=PALETTE["text_primary"]),
        ))
        fig.add_trace(go.Bar(
            x=df["trade_id"], y=df["roll"],
            name="Roll",
            marker_color=PALETTE["accent"],
            marker_line=dict(width=0),
            text=[f"{v:+,.0f}" for v in df["roll"]],
            textposition="inside",
            textfont=dict(family=_FONT_MONO, size=9, color=PALETTE["bg_base"]),
        ))
        fig.add_trace(go.Scatter(
            x=df["trade_id"], y=df["total"],
            mode="markers+text", name="Total C+R",
            marker=dict(size=10, color=PALETTE["primary"], symbol="diamond",
                        line=dict(color=PALETTE["bg_base"], width=1)),
            text=[f"{v:+,.0f}" for v in df["total"]],
            textposition="top center",
            textfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_accent"]),
        ))
        fig.update_layout(
            title=dict(
                text=f"{title} ({horizon_months}M)",
                font=dict(family=_FONT_SANS, size=14, color=PALETTE["text_accent"]),
                x=0.0, xanchor="left",
            ),
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

        # Distinct but harmonious trade colours
        trade_colors = [
            "#1A6FBF", "#00A85A", "#9B72CF", "#E07A5F",
            "#2EC4B6", "#F2CC8F", "#81B29A", "#6A8EAE",
        ]
        fig = go.Figure()
        for i, trade in enumerate(trades):
            row = ladder_df.loc[trade]
            fig.add_trace(go.Bar(
                x=tenors,
                y=[row.get(t, 0) for t in tenors],
                name=trade,
                marker_color=trade_colors[i % len(trade_colors)],
                marker_line=dict(width=0),
                opacity=0.88,
                hovertemplate=f"<b>{trade}</b><br>%{{x}}: ZAR %{{y:,.0f}}<extra></extra>",
            ))
        if net is not None:
            fig.add_trace(go.Scatter(
                x=tenors,
                y=[net.get(t, 0) for t in tenors],
                mode="lines+markers+text",
                name="NET",
                line=dict(color=PALETTE["accent"], width=2.5, dash="dash"),
                marker=dict(size=9, symbol="diamond",
                            color=PALETTE["accent"],
                            line=dict(color=PALETTE["bg_base"], width=1)),
                text=[f"{net.get(t,0):+,.0f}" for t in tenors],
                textposition="top center",
                textfont=dict(family=_FONT_MONO, size=9, color=PALETTE["text_accent"]),
            ))
        fig.add_hline(y=0, line_color=PALETTE["border_bright"], line_width=1)
        fig.update_layout(
            title=dict(
                text=title,
                font=dict(family=_FONT_SANS, size=14, color=PALETTE["text_accent"]),
                x=0.0, xanchor="left",
            ),
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
            marker=dict(size=7, color=PALETTE["primary"],
                        line=dict(color=PALETTE["bg_base"], width=1)),
            hovertemplate="Base<br>%{x}: %{y:.4f}%<extra></extra>",
        ))

        scene_colors = [
            PALETTE["neg"], PALETTE["accent"], PALETTE["secondary"],
            "#9B72CF", "#2EC4B6",
        ]
        dash_styles = ["dot", "dash", "longdash", "dashdot", "longdashdot"]
        for i, (label, scb) in enumerate(scenarios.items()):
            sdf = scb.curve_dataframe()
            sdf = sdf[sdf["tenor"].isin(tenors)]
            fig.add_trace(go.Scatter(
                x=sdf["tenor"], y=sdf["zero_rate_cc"],
                mode="lines+markers", name=label,
                line=dict(color=scene_colors[i % len(scene_colors)],
                          width=1.8, dash=dash_styles[i % len(dash_styles)]),
                marker=dict(size=5),
                hovertemplate=f"{label}<br>%{{x}}: %{{y:.4f}}%<extra></extra>",
            ))

        fig.update_layout(
            title=dict(
                text=title,
                font=dict(family=_FONT_SANS, size=14, color=PALETTE["text_accent"]),
                x=0.0, xanchor="left",
            ),
            **CHART_TEMPLATE,
        )
        fig.update_xaxes(title_text="Tenor")
        fig.update_yaxes(title_text="Zero Rate (cc, %)", ticksuffix="%")
        return fig

    # ------------------------------------------------------------------
    # 9. Obsidian-style Module Dependency Graph
    # ------------------------------------------------------------------

    def obsidian_graph(
        self,
        root_dir: str = ".",
        title: str = "Module Dependency Graph — Obsidian View",
        include_external: bool = False,
    ) -> go.Figure:
        """
        Renders a force-directed node-link graph of Python module imports —
        styled like Obsidian's graph view.

        Parameters
        ----------
        root_dir         : root of the project to scan (default: cwd)
        title            : chart title
        include_external : if True, add external packages (numpy, ql, …)
                           as dim satellite nodes; False = project-only
        """
        root = Path(root_dir).resolve()

        # ── 1. Collect all .py files as nodes ───────────────────────────
        py_files: List[Path] = sorted(root.rglob("*.py"))
        # Drop __pycache__ and hidden dirs
        py_files = [
            p for p in py_files
            if "__pycache__" not in p.parts and not any(
                part.startswith(".") for part in p.parts
            )
        ]

        def _node_id(p: Path) -> str:
            """Short dotted module name relative to root."""
            rel = p.relative_to(root)
            parts = list(rel.with_suffix("").parts)
            # drop trailing __init__
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            return ".".join(parts) if parts else p.stem

        # Map path → node label
        node_map: Dict[Path, str] = {p: _node_id(p) for p in py_files}
        all_local: Set[str] = set(node_map.values())

        # ── 2. Parse imports from each file ─────────────────────────────
        edges: List[Tuple[str, str]] = []
        external_nodes: Set[str] = set()

        for p, src_id in node_map.items():
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if alias.name in all_local:
                            edges.append((src_id, alias.name))
                        elif include_external:
                            external_nodes.add(top)
                            edges.append((src_id, top))
                elif isinstance(node, ast.ImportFrom):
                    if node.module is None:
                        continue
                    mod = node.module
                    # Resolve relative imports
                    if node.level:
                        pkg_parts = src_id.split(".")
                        base = ".".join(pkg_parts[: max(0, len(pkg_parts) - node.level)])
                        mod = f"{base}.{mod}" if base else mod
                    # Match longest prefix against known local modules
                    matched = None
                    for local in all_local:
                        if mod == local or mod.startswith(local + "."):
                            if matched is None or len(local) > len(matched):
                                matched = local
                    if matched:
                        if matched != src_id:
                            edges.append((src_id, matched))
                    elif include_external:
                        top = mod.split(".")[0]
                        external_nodes.add(top)
                        edges.append((src_id, top))

        # ── 3. Build NetworkX graph & spring layout ──────────────────────
        G = nx.DiGraph()
        for nid in all_local:
            G.add_node(nid)
        if include_external:
            for ext in external_nodes:
                G.add_node(ext)
        for src, dst in edges:
            G.add_edge(src, dst)

        # Remove self-loops
        G.remove_edges_from(list(nx.selfloop_edges(G)))

        # Spring layout — more iterations = better separation
        pos = nx.spring_layout(
            G.to_undirected(),
            k=3.2 / max(1, G.number_of_nodes() ** 0.5),
            iterations=120,
            seed=42,
        )

        # ── 4. Node metadata ─────────────────────────────────────────────
        # Colour by top-level package
        _pkg_colors: Dict[str, str] = {}
        pkg_palette = [
            PALETTE["primary"],    # src.charts
            PALETTE["secondary"],  # src.curves
            PALETTE["accent"],     # src.instruments
            "#9B72CF",             # src.risk
            "#2EC4B6",             # src.hedging
            "#E07A5F",             # root / main
            "#81B29A",             # external
        ]
        _color_idx = 0

        def _pkg_color(nid: str) -> str:
            nonlocal _color_idx
            pkg = nid.split(".")[0] if "." in nid else nid
            if pkg not in _pkg_colors:
                _pkg_colors[pkg] = pkg_palette[_color_idx % len(pkg_palette)]
                _color_idx += 1
            return _pkg_colors[pkg]

        # Node degree for sizing
        degree = dict(G.degree())
        max_deg = max(degree.values()) if degree else 1

        def _node_size(nid: str) -> int:
            d = degree.get(nid, 0)
            return int(12 + 24 * (d / max(max_deg, 1)))

        # ── 5. Build Plotly traces ───────────────────────────────────────
        # --- Edge traces (one thin grey Scatter per edge for hover) -----
        edge_x, edge_y = [], []
        for src, dst in G.edges():
            if src not in pos or dst not in pos:
                continue
            x0, y0 = pos[src]
            x1, y1 = pos[dst]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]

        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            mode="lines",
            line=dict(width=0.8, color=PALETTE["border_bright"]),
            hoverinfo="none",
            showlegend=False,
            name="edge",
        )

        # --- One node trace per top-level package (for legend grouping) --
        pkg_groups: Dict[str, List[str]] = {}
        for nid in G.nodes():
            pkg = nid.split(".")[0] if "." in nid else nid
            pkg_groups.setdefault(pkg, []).append(nid)

        node_traces: List[go.Scatter] = []
        for pkg, members in sorted(pkg_groups.items()):
            nx_arr = [pos[m][0] for m in members if m in pos]
            ny_arr = [pos[m][1] for m in members if m in pos]
            sizes   = [_node_size(m) for m in members if m in pos]
            labels  = [m.split(".")[-1] for m in members if m in pos]
            hover   = [
                f"<b>{m}</b><br>Degree: {degree.get(m,0)}"
                for m in members if m in pos
            ]
            color = _pkg_color(members[0])
            is_ext = pkg in external_nodes

            node_traces.append(go.Scatter(
                x=nx_arr, y=ny_arr,
                mode="markers+text",
                name=pkg,
                text=labels,
                textposition="top center",
                textfont=dict(
                    family=_FONT_MONO,
                    size=9,
                    color=PALETTE["text_muted"] if is_ext else PALETTE["text_secondary"],
                ),
                hovertext=hover,
                hoverinfo="text",
                marker=dict(
                    size=sizes,
                    color=color,
                    opacity=0.55 if is_ext else 0.92,
                    line=dict(
                        width=1.5,
                        color=PALETTE["border_bright"] if is_ext else PALETTE["bg_base"],
                    ),
                    symbol="circle",
                ),
                legendgroup=pkg,
                showlegend=True,
            ))

        # ── 6. Assemble figure ───────────────────────────────────────────
        fig = go.Figure(data=[edge_trace] + node_traces)

        # Arrow-head annotation for each edge (small triangle)
        annotations = []
        for src, dst in G.edges():
            if src not in pos or dst not in pos:
                continue
            x0, y0 = pos[src]
            x1, y1 = pos[dst]
            annotations.append(dict(
                ax=x0, ay=y0,
                x=x1,  y=y1,
                xref="x", yref="y",
                axref="x", ayref="y",
                showarrow=True,
                arrowhead=2,
                arrowsize=1.0,
                arrowwidth=0.8,
                arrowcolor=PALETTE["border_bright"],
            ))

        fig.update_layout(
            title=dict(
                text=(
                    f"{title}"
                    f"<br><sup style='color:{PALETTE['text_muted']}'>"
                    f"{G.number_of_nodes()} nodes · "
                    f"{G.number_of_edges()} edges · "
                    f"spring layout</sup>"
                ),
                font=dict(family=_FONT_SANS, size=14, color=PALETTE["text_accent"]),
                x=0.0, xanchor="left",
            ),
            annotations=annotations,
            hovermode="closest",
            **CHART_TEMPLATE,
        )
        fig.update_xaxes(showgrid=False, zeroline=False, showticklabels=False)
        fig.update_yaxes(showgrid=False, zeroline=False, showticklabels=False)
        return fig

    # ------------------------------------------------------------------
    # 10. OIS Par Swap Fair-Rate Curve
    # ------------------------------------------------------------------

    def fair_rate_curve_plot(
        self,
        curve_builder: ZARCurveBuilder,
        title: str = "OIS Par Swap Fair-Rate Curve — ZAR",
    ) -> go.Figure:
        """
        Dedicated OIS par swap rate chart — two panels:
          Top   : implied par swap rates vs market OIS mid quotes
          Bottom: spread between par swap rate and OIS quote (bps)
        """
        tenor_labels = ["1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y", "12Y", "15Y", "20Y"]

        par_rates: dict = {}
        for t in tenor_labels:
            try:
                par_rates[t] = curve_builder.par_swap_rate(t) * 100
            except Exception:
                pass

        ois_rates = {
            k: v * 100
            for k, v in curve_builder.mkt.ois_quotes.items()
            if k in tenor_labels
        }

        common = [t for t in tenor_labels if t in par_rates and t in ois_rates]
        spread_bps = {t: (par_rates[t] - ois_rates[t]) * 100 for t in common}

        par_df = pd.DataFrame(
            [(t, par_rates[t]) for t in tenor_labels if t in par_rates],
            columns=["tenor", "par_rate"],
        )
        ois_df = pd.DataFrame(
            [(t, ois_rates[t]) for t in common],
            columns=["tenor", "ois_rate"],
        )
        spread_df = pd.DataFrame(
            [(t, spread_bps[t]) for t in common],
            columns=["tenor", "spread_bps"],
        )

        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=[
                "Par Swap Rate vs OIS Mid Quotes",
                "Spread: Par Swap − OIS Quote (bps)",
            ],
            vertical_spacing=0.18,
            row_heights=[0.65, 0.35],
        )

        # --- Par swap rates ---
        fig.add_trace(go.Scatter(
            x=par_df["tenor"], y=par_df["par_rate"],
            mode="lines+markers", name="Par Swap Rate",
            line=dict(color=PALETTE["primary"], width=2.5),
            marker=dict(size=8, symbol="square", color=PALETTE["primary"],
                        line=dict(color=PALETTE["bg_base"], width=1)),
            hovertemplate="Tenor: %{x}<br>Par Rate: %{y:.4f}%<extra></extra>",
        ), row=1, col=1)

        # --- OIS market mid quotes ---
        fig.add_trace(go.Scatter(
            x=ois_df["tenor"], y=ois_df["ois_rate"],
            mode="markers", name="OIS Mid Quote",
            marker=dict(size=10, color=PALETTE["accent"], symbol="x",
                        line=dict(width=2.5, color=PALETTE["accent"])),
            hovertemplate="Tenor: %{x}<br>OIS Mid: %{y:.4f}%<extra></extra>",
        ), row=1, col=1)

        # --- Spread bars ---
        spread_colors = [PALETTE["pos"] if v >= 0 else PALETTE["neg"] for v in spread_df["spread_bps"]]
        fig.add_trace(go.Bar(
            x=spread_df["tenor"], y=spread_df["spread_bps"],
            name="Spread (bps)",
            marker_color=spread_colors,
            marker_line=dict(width=0),
            text=[f"{v:+.1f}" for v in spread_df["spread_bps"]],
            textposition="outside",
            textfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_secondary"]),
            hovertemplate="Tenor: %{x}<br>Spread: %{y:.2f} bps<extra></extra>",
        ), row=2, col=1)

        fig.add_hline(y=0, line_color=PALETTE["border_bright"], line_width=1, row=2, col=1)

        fig.update_layout(
            title=dict(
                text=title,
                font=dict(family=_FONT_SANS, size=14, color=PALETTE["text_accent"]),
                x=0.0, xanchor="left",
            ),
            showlegend=True,
            **CHART_TEMPLATE,
        )
        fig.update_yaxes(ticksuffix="%", title_text="Rate (%)", row=1, col=1)
        fig.update_xaxes(title_text="Tenor", row=2, col=1)
        fig.update_yaxes(title_text="Spread (bps)", row=2, col=1)
        for ann in fig.layout.annotations:
            ann.font = dict(family=_FONT_SANS, size=11, color=PALETTE["text_secondary"])

        return fig

    # ------------------------------------------------------------------
    # 10. P&L Attribution (NPV + BPV by trade)
    # ------------------------------------------------------------------

    def pnl_attribution_plot(
        self,
        portfolio_risk: "PortfolioRiskReport",
        title: str = "P&L Attribution — NPV & BPV by Trade",
    ) -> go.Figure:
        """
        Two-panel attribution view:
          Left  : NPV contribution per trade (horizontal bars)
          Right : BPV (signed) contribution per trade (horizontal bars)

        Positive BPV ⇒ short duration (pay-fixed); negative BPV ⇒ long duration.
        """
        rows_data = [
            {
                "trade_id": r.trade_id,
                "npv_zar":  r.npv_zar,
                "bpv_zar":  r.bpv_zar,
            }
            for r in portfolio_risk.trade_reports
        ]
        if not rows_data:
            return self._empty_fig(title)

        df = pd.DataFrame(rows_data)

        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=[
                "NPV Contribution (ZAR)",
                "BPV Contribution (ZAR / bp)",
            ],
            horizontal_spacing=0.14,
        )

        # --- NPV bars ---
        npv_colors = [PALETTE["pos"] if v >= 0 else PALETTE["neg"] for v in df["npv_zar"]]
        fig.add_trace(go.Bar(
            x=df["npv_zar"], y=df["trade_id"],
            orientation="h",
            marker_color=npv_colors,
            marker_line=dict(width=0),
            text=[f"{v:+,.0f}" for v in df["npv_zar"]],
            textposition="outside",
            textfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_secondary"]),
            hovertemplate="<b>%{y}</b><br>NPV: ZAR %{x:+,.0f}<extra></extra>",
            name="NPV",
        ), row=1, col=1)

        # --- BPV bars (negative BPV = long duration = receiver = "good" in rates terms) ---
        bpv_colors = [PALETTE["pos"] if v <= 0 else PALETTE["neg"] for v in df["bpv_zar"]]
        fig.add_trace(go.Bar(
            x=df["bpv_zar"], y=df["trade_id"],
            orientation="h",
            marker_color=bpv_colors,
            marker_line=dict(width=0),
            text=[f"{v:+,.0f}" for v in df["bpv_zar"]],
            textposition="outside",
            textfont=dict(family=_FONT_MONO, size=10, color=PALETTE["text_secondary"]),
            hovertemplate="<b>%{y}</b><br>BPV: ZAR %{x:+,.0f}<extra></extra>",
            name="BPV",
        ), row=1, col=2)

        for col in (1, 2):
            fig.add_vline(x=0, line_color=PALETTE["border_bright"], line_width=1, row=1, col=col)

        # Portfolio totals as annotations
        total_npv = sum(r.npv_zar for r in portfolio_risk.trade_reports)
        total_bpv = sum(r.bpv_zar for r in portfolio_risk.trade_reports)
        subtitle = (
            f"Portfolio: NPV ZAR {total_npv:+,.0f}  |  "
            f"BPV ZAR {total_bpv:+,.0f} / bp"
        )

        fig.update_layout(
            title=dict(
                text=f"{title}<br><sup style='color:{PALETTE['text_muted']}'>{subtitle}</sup>",
                font=dict(family=_FONT_SANS, size=13, color=PALETTE["text_accent"]),
                x=0.0, xanchor="left",
            ),
            showlegend=False,
            **CHART_TEMPLATE,
        )
        fig.update_xaxes(title_text="ZAR", row=1, col=1)
        fig.update_xaxes(title_text="ZAR / bp", row=1, col=2)
        for ann in fig.layout.annotations:
            ann.font = dict(family=_FONT_SANS, size=11, color=PALETTE["text_secondary"])

        return fig

    # ------------------------------------------------------------------
    # 11. NPV / MTM Gauge
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
            ("OIS Fair-Rate Curve",          self.fair_rate_curve_plot(curve_builder)),
            ("DV01 Bucket Ladder",           self.dv01_ladder_plot(portfolio_risk)),
            ("Portfolio KRD Heatmap",        self.portfolio_heatmap(portfolio_risk)),
            ("P&L Attribution",              self.pnl_attribution_plot(portfolio_risk)),
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

        # Obsidian module graph
        figs.append(("Module Dependency Graph", self.obsidian_graph(root_dir=".")))

        # Section groupings for the dashboard layout
        risk_section    = {"DV01 Bucket Ladder", "Portfolio KRD Heatmap"}
        hedge_section   = {"Hedge Effectiveness", "Key-Rate Hedge Effectiveness",
                           "Macro Hedge Effectiveness"}
        pnl_section     = {"Carry & Roll Attribution", "Scenario P&L"}
        ladder_section  = {"IR Delta Ladder"}
        curve_section   = {"Curve Scenarios"}
        graph_section   = {"Module Dependency Graph"}

        current_section = "Curve & Rates"

        def _panel(title: str, fig: go.Figure) -> str:
            tag = {
                "ZARONIA Yield Curve":      "Bootstrapped OIS",
                "OIS Fair-Rate Curve":      "Par Swap vs Quotes",
                "DV01 Bucket Ladder":       "KRD per bp",
                "Portfolio KRD Heatmap":    "Trade × Tenor",
                "P&L Attribution":          "NPV & BPV",
                "IR Delta Ladder":          "01 Grid",
                "Scenario P&L":             "Stress P&L",
                "Carry & Roll Attribution": "3M Horizon",
                "Curve Scenarios":          "Parallel / Twist",
                "Module Dependency Graph":  "Obsidian View",
            }.get(title, "Analytics")
            html = fig.to_html(full_html=False, include_plotlyjs=False)
            return (
                f'<div class="chart-panel">'
                f'<div class="panel-header">'
                f'<span class="panel-title">{title}</span>'
                f'<span class="panel-tag">{tag}</span>'
                f'</div>'
                f'<div class="panel-body">{html}</div>'
                f'</div>'
            )

        html_parts = [self._dashboard_header()]
        for panel_title, fig in figs:
            # Inject section dividers
            if panel_title in risk_section and current_section != "Risk":
                html_parts.append('</div><div class="section-label">Risk &amp; Greeks</div><div class="chart-grid">')
                current_section = "Risk"
            elif panel_title in hedge_section and current_section != "Hedging":
                html_parts.append('</div><div class="section-label">Hedging</div><div class="chart-grid">')
                current_section = "Hedging"
            elif panel_title in pnl_section and current_section != "P&L":
                html_parts.append('</div><div class="section-label">P&amp;L Attribution</div><div class="chart-grid">')
                current_section = "P&L"
            elif panel_title in ladder_section and current_section != "Ladder":
                html_parts.append('</div><div class="section-label">Delta Ladder</div><div class="chart-grid full-width">')
                current_section = "Ladder"
            elif panel_title in curve_section and current_section != "Scenarios":
                html_parts.append('</div><div class="section-label">Curve Scenarios</div><div class="chart-grid">')
                current_section = "Scenarios"
            elif panel_title in graph_section and current_section != "Graph":
                html_parts.append('</div><div class="section-label">Codebase</div><div class="chart-grid full-width">')
                current_section = "Graph"
            html_parts.append(_panel(panel_title, fig))
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
            title=dict(text=title,
                       font=dict(family=_FONT_SANS, size=13, color=PALETTE["text_accent"])),
            annotations=[dict(text="No data available", showarrow=False,
                              font=dict(family=_FONT_MONO, size=14,
                                        color=PALETTE["text_muted"]),
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

          <!-- Bank-grade fonts: IBM Plex Sans (UI) + IBM Plex Mono (data) -->
          <link rel="preconnect" href="https://fonts.googleapis.com">
          <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
          <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">

          <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>

          <style>
            /* ── Reset ───────────────────────────────────────────────── */
            *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

            /* ── Tokens ──────────────────────────────────────────────── */
            :root {
              --bg-base:       #080C14;
              --bg-panel:      #0D1420;
              --bg-card:       #111927;
              --bg-header:     #0A1628;
              --border:        #1E2D42;
              --border-bright: #2A3F5F;
              --sa-green:      #00A85A;
              --sa-blue:       #1A4FBF;
              --sa-gold:       #F5C400;
              --sa-red:        #E84040;
              --text-primary:  #E8EDF5;
              --text-secondary:#8A9BB5;
              --text-muted:    #4A5A72;
              --pos:           #00C875;
              --neg:           #E84040;
              --font-ui:       'IBM Plex Sans',  'Inter', 'Segoe UI', sans-serif;
              --font-data:     'IBM Plex Mono', 'JetBrains Mono', 'Consolas', monospace;
            }

            /* ── Base ────────────────────────────────────────────────── */
            html { font-size: 14px; -webkit-font-smoothing: antialiased; }
            body {
              background: var(--bg-base);
              color: var(--text-primary);
              font-family: var(--font-ui);
              line-height: 1.55;
              padding: 20px 24px 40px;
              min-height: 100vh;
            }

            /* ── Top bar ─────────────────────────────────────────────── */
            .topbar {
              display: flex;
              align-items: center;
              gap: 0;
              background: var(--bg-header);
              border: 1px solid var(--border);
              border-radius: 6px;
              margin-bottom: 20px;
              overflow: hidden;
            }
            .topbar-flag {
              display: flex;
              flex-direction: column;
              width: 6px;
              flex-shrink: 0;
              align-self: stretch;
            }
            .topbar-flag span { flex: 1; display: block; }
            .topbar-body {
              padding: 16px 24px;
              flex: 1;
            }
            .topbar-title {
              font-family: var(--font-ui);
              font-size: 17px;
              font-weight: 600;
              letter-spacing: 0.02em;
              color: var(--text-primary);
            }
            .topbar-title em {
              font-style: normal;
              color: var(--sa-gold);
            }
            .topbar-meta {
              font-family: var(--font-data);
              font-size: 10.5px;
              color: var(--text-muted);
              margin-top: 4px;
              letter-spacing: 0.04em;
            }
            .topbar-meta span { margin-right: 18px; }
            .topbar-meta .live {
              color: var(--sa-green);
              font-weight: 500;
            }
            .topbar-badges {
              display: flex;
              flex-direction: column;
              align-items: flex-end;
              gap: 6px;
              padding: 16px 24px;
              flex-shrink: 0;
            }
            .badge {
              font-family: var(--font-data);
              font-size: 9.5px;
              font-weight: 500;
              letter-spacing: 0.08em;
              text-transform: uppercase;
              padding: 3px 8px;
              border-radius: 3px;
              border: 1px solid;
            }
            .badge-green  { color: var(--sa-green); border-color: var(--sa-green); }
            .badge-gold   { color: var(--sa-gold);  border-color: var(--sa-gold);  }
            .badge-blue   { color: var(--sa-blue);  border-color: var(--sa-blue);  }

            /* ── Divider labels ──────────────────────────────────────── */
            .section-label {
              font-family: var(--font-data);
              font-size: 9.5px;
              font-weight: 500;
              letter-spacing: 0.15em;
              text-transform: uppercase;
              color: var(--text-muted);
              border-top: 1px solid var(--border);
              padding-top: 16px;
              margin: 20px 0 12px;
            }

            /* ── Chart grid ──────────────────────────────────────────── */
            .chart-grid {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(700px, 1fr));
              gap: 16px;
            }
            .chart-grid.full-width { grid-template-columns: 1fr; }

            /* ── Chart panels ────────────────────────────────────────── */
            .chart-panel {
              background: var(--bg-card);
              border: 1px solid var(--border);
              border-radius: 5px;
              overflow: hidden;
            }
            .chart-panel:hover {
              border-color: var(--border-bright);
              transition: border-color 0.18s ease;
            }
            .panel-header {
              display: flex;
              align-items: center;
              justify-content: space-between;
              padding: 10px 16px;
              border-bottom: 1px solid var(--border);
              background: var(--bg-panel);
            }
            .panel-title {
              font-family: var(--font-data);
              font-size: 10px;
              font-weight: 500;
              letter-spacing: 0.12em;
              text-transform: uppercase;
              color: var(--sa-gold);
            }
            .panel-tag {
              font-family: var(--font-data);
              font-size: 9px;
              letter-spacing: 0.06em;
              color: var(--text-muted);
              text-transform: uppercase;
            }
            .panel-body { padding: 4px; }

            /* ── Footer ──────────────────────────────────────────────── */
            footer {
              margin-top: 36px;
              padding-top: 16px;
              border-top: 1px solid var(--border);
              display: flex;
              justify-content: space-between;
              align-items: center;
            }
            footer p {
              font-family: var(--font-data);
              font-size: 9.5px;
              color: var(--text-muted);
              letter-spacing: 0.04em;
            }
            footer .mark {
              font-family: var(--font-data);
              font-size: 9px;
              color: var(--text-muted);
              letter-spacing: 0.1em;
              text-transform: uppercase;
            }
          </style>
        </head>
        <body>

          <!-- Top bar -->
          <div class="topbar">
            <div class="topbar-flag">
              <span style="background:#007A4D"></span>
              <span style="background:#FFB612"></span>
              <span style="background:#002395"></span>
              <span style="background:#DE3831"></span>
              <span style="background:#FFFFFF"></span>
            </div>
            <div class="topbar-body">
              <div class="topbar-title">
                <em>ZARONIA</em> IRS Desk &mdash; Hedging Analytics
              </div>
              <div class="topbar-meta">
                <span>South African Rand Overnight Index Average</span>
                <span class="live">&#9679; LIVE</span>
                <span>QuantLib 1.42</span>
                <span>Development Bank &mdash; Rates Desk</span>
              </div>
            </div>
            <div class="topbar-badges">
              <span class="badge badge-green">PhD Analytics</span>
              <span class="badge badge-gold">ZAR Rates</span>
              <span class="badge badge-blue">OIS / IRS</span>
            </div>
          </div>

          <div class="section-label">Curve &amp; Rates</div>
          <div class="chart-grid">
        """)

    @staticmethod
    def _dashboard_footer() -> str:
        return textwrap.dedent("""
          </div>

          <footer>
            <p>ZARONIA Desk Hedging System &copy; 2026 &nbsp;&mdash;&nbsp;
               Built with QuantLib + Plotly &nbsp;&mdash;&nbsp;
               Institutional use only.</p>
            <p class="mark">ZAR &bull; OIS &bull; IRS &bull; KRD &bull; DV01</p>
          </footer>

        </body>
        </html>
        """)
