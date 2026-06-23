"""
ZARONIA IRS Desk — Streamlit App
South African Rand Overnight Index Average · Bank-Level Hedging Analytics
"""

import datetime
import sys
import os

import streamlit as st
import QuantLib as ql
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(__file__))

from src.curves.sa_market import SARates, SACurveBuilder, ZAR_DC, ZAR_CAL
from src.instruments.sa_swap import (
    SASwap, SwapSpec, Direction,
    portfolio_bpv, portfolio_npv, portfolio_krd,
    macro_hedge, OIS_BUCKET_LABELS, OIS_BUCKET_FIELDS,
)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ZARONIA Desk",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── IBM Plex fonts + dark theme CSS ─────────────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">

<style>
:root {
  --bg-base:       #080C14;
  --bg-panel:      #0D1420;
  --bg-card:       #111927;
  --border:        #1E2D42;
  --border-hi:     #2A3F5F;
  --sa-green:      #00A85A;
  --sa-blue:       #1A4FBF;
  --sa-gold:       #F5C400;
  --sa-red:        #E84040;
  --text-primary:  #E8EDF5;
  --text-secondary:#8A9BB5;
  --text-muted:    #4A5A72;
  --pos:           #00C875;
  --neg:           #E84040;
  --font-ui:       'IBM Plex Sans', 'Inter', sans-serif;
  --font-data:     'IBM Plex Mono', 'Consolas', monospace;
}

html, body, [class*="css"] {
  font-family: var(--font-ui) !important;
  background-color: var(--bg-base) !important;
  color: var(--text-primary) !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
  background: var(--bg-panel) !important;
  border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * { font-family: var(--font-ui) !important; }

/* Metric cards */
[data-testid="metric-container"] {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: 4px !important;
  padding: 12px 16px !important;
}
[data-testid="metric-container"] label {
  font-family: var(--font-data) !important;
  font-size: 10px !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase !important;
  color: var(--text-muted) !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
  font-family: var(--font-data) !important;
  font-size: 22px !important;
  color: var(--text-primary) !important;
}
[data-testid="metric-container"] [data-testid="stMetricDelta"] {
  font-family: var(--font-data) !important;
  font-size: 11px !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
  font-family: var(--font-data) !important;
  font-size: 11px !important;
}

/* Tabs */
[data-testid="stTab"] {
  font-family: var(--font-data) !important;
  font-size: 11px !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
  border-bottom: 2px solid var(--sa-gold) !important;
  color: var(--sa-gold) !important;
}

/* Section headers */
.desk-header {
  background: linear-gradient(90deg, #0A1628 0%, #0D1F3C 100%);
  border-left: 4px solid var(--sa-green);
  border-bottom: 1px solid var(--border);
  padding: 14px 20px;
  margin: -1rem -1rem 1.5rem -1rem;
  display: flex;
  align-items: center;
  gap: 16px;
}
.desk-header h1 {
  font-family: var(--font-ui) !important;
  font-size: 18px !important;
  font-weight: 600 !important;
  color: var(--text-primary) !important;
  margin: 0 !important;
  padding: 0 !important;
}
.desk-header .sub {
  font-family: var(--font-data);
  font-size: 10px;
  color: var(--text-muted);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-top: 2px;
}
.badge {
  font-family: var(--font-data);
  font-size: 9px;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: 3px;
  border: 1px solid;
  margin-left: 8px;
}
.badge-green { color: var(--sa-green); border-color: var(--sa-green); }
.badge-gold  { color: var(--sa-gold);  border-color: var(--sa-gold);  }
.badge-live  { color: var(--pos);      border-color: var(--pos);      }

.section-label {
  font-family: var(--font-data);
  font-size: 9.5px;
  font-weight: 500;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-muted);
  border-top: 1px solid var(--border);
  padding-top: 12px;
  margin-top: 20px;
  margin-bottom: 8px;
}

.krd-pos { color: var(--pos); font-family: var(--font-data); }
.krd-neg { color: var(--neg); font-family: var(--font-data); }
</style>
""", unsafe_allow_html=True)

# ── Chart palette & template ─────────────────────────────────────────────────
P = {
    "bg":      "#080C14",
    "panel":   "#0D1420",
    "card":    "#111927",
    "border":  "#1E2D42",
    "green":   "#00A85A",
    "blue":    "#1A4FBF",
    "gold":    "#F5C400",
    "red":     "#E84040",
    "pos":     "#00C875",
    "neg":     "#E84040",
    "txt1":    "#E8EDF5",
    "txt2":    "#8A9BB5",
    "txtm":    "#4A5A72",
    "grid":    "#111927",
}
FONT_MONO = "'IBM Plex Mono','Consolas',monospace"
FONT_SANS = "'IBM Plex Sans','Inter',sans-serif"

def _ct(**kw):
    """Base chart layout dict."""
    return dict(
        template="plotly_dark",
        font=dict(family=FONT_MONO, size=11, color=P["txt1"]),
        paper_bgcolor=P["panel"],
        plot_bgcolor=P["panel"],
        margin=dict(l=56, r=24, t=48, b=44),
        xaxis=dict(gridcolor=P["grid"], linecolor=P["border"],
                   tickfont=dict(family=FONT_MONO, size=10, color=P["txt2"])),
        yaxis=dict(gridcolor=P["grid"], linecolor=P["border"],
                   tickfont=dict(family=FONT_MONO, size=10, color=P["txt2"])),
        legend=dict(bgcolor="rgba(8,12,20,0.8)", bordercolor=P["border"],
                    borderwidth=1, font=dict(family=FONT_MONO, size=10, color=P["txt2"])),
        **kw,
    )

def _title(text):
    return dict(text=text, font=dict(family=FONT_SANS, size=13, color=P["gold"]),
                x=0.0, xanchor="left")

def _pc(fig):
    """Render a plotly chart full-width."""
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── Sidebar — rate inputs ────────────────────────────────────────────────────
def sidebar_rates() -> SARates:
    with st.sidebar:
        st.markdown("""
        <div style="padding:12px 0 8px;">
          <div style="font-family:'IBM Plex Sans',sans-serif;font-size:15px;
                      font-weight:600;color:#E8EDF5;">ZARONIA Desk</div>
          <div style="font-family:'IBM Plex Mono',monospace;font-size:9.5px;
                      letter-spacing:.12em;text-transform:uppercase;
                      color:#4A5A72;margin-top:3px;">
            ZAR Rates · QuantLib 1.42
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Valuation date
        st.markdown('<div class="section-label">Valuation Date</div>', unsafe_allow_html=True)
        val_date = st.date_input(
            "Date", value=datetime.date(2026, 4, 14),
            min_value=datetime.date(2020, 1, 1),
            max_value=datetime.date(2035, 12, 31),
            label_visibility="collapsed",
        )
        ql_date = ql.Date(val_date.day, val_date.month, val_date.year)

        def pct(label, default, key, step=0.25, fmt="%.4f%%"):
            return st.number_input(label, value=default, step=step,
                                   format="%.4f", key=key) / 100

        # ── SARB / Money Market ──────────────────────────────────────────────
        st.markdown('<div class="section-label">SARB / Money Market</div>',
                    unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            repo   = pct("Repo NACM",    7.50, "repo")
            jibar  = pct("JIBAR 3M",     7.83, "jibar3m")
        with col2:
            zaron  = pct("ZARONIA O/N",  7.50, "zaronia")

        # ── FRA Strip ───────────────────────────────────────────────────────
        st.markdown('<div class="section-label">FRA Strip (JIBAR, NACQ)</div>',
                    unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            fra36  = pct("3×6",   7.65, "fra36")
            fra912 = pct("9×12",  7.33, "fra912")
        with col2:
            fra69  = pct("6×9",   7.48, "fra69")
            fra1821= pct("18×21", 7.18, "fra1821")

        # ── JIBAR Swaps NACQ ────────────────────────────────────────────────
        st.markdown('<div class="section-label">JIBAR Swaps NACQ (SASW)</div>',
                    unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            sw1  = pct("1Y",  7.58, "sw1")
            sw5  = pct("5Y",  7.78, "sw5")
        with col2:
            sw2  = pct("2Y",  7.52, "sw2")
            sw7  = pct("7Y",  7.93, "sw7")
        with col3:
            sw3  = pct("3Y",  7.63, "sw3")
            sw10 = pct("10Y", 8.10, "sw10")

        # ── ZARONIA OIS NACQ ────────────────────────────────────────────────
        st.markdown('<div class="section-label">ZARONIA OIS NACQ</div>',
                    unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            ois1 = pct("OIS 1Y", 7.45, "ois1")
            ois3 = pct("OIS 3Y", 7.60, "ois3")
            ois5 = pct("OIS 5Y", 7.83, "ois5")
        with col2:
            ois2 = pct("OIS 2Y", 7.50, "ois2")
            ois4 = pct("OIS 4Y", 7.72, "ois4")

        st.markdown("---")
        st.markdown(
            '<div style="font-family:IBM Plex Mono,monospace;font-size:9px;'
            'color:#4A5A72;text-align:center;">zarswap.co.za conventions</div>',
            unsafe_allow_html=True,
        )

    return SARates(
        valuation_date=ql_date,
        repo_nacm=repo, zaronia_on=zaron, jibar_3m=jibar,
        fra_3x6=fra36, fra_6x9=fra69, fra_9x12=fra912, fra_18x21=fra1821,
        sasw1=sw1,  sasw2=sw2,  sasw3=sw3,
        sasw5=sw5,  sasw7=sw7,  sasw10=sw10,
        ois_1y=ois1, ois_2y=ois2, ois_3y=ois3,
        ois_4y=ois4, ois_5y=ois5,
    )


# ── Curve builder (cached per rate snapshot) ─────────────────────────────────
@st.cache_resource(max_entries=8)
def build_curve(rates_tuple: tuple) -> SACurveBuilder:
    year, month, day = int(rates_tuple[0]), int(rates_tuple[1]), int(rates_tuple[2])
    ql_date = ql.Date(day, month, year)
    r = SARates(ql_date, *rates_tuple[3:])
    return SACurveBuilder(r).build()

def rates_to_tuple(r: SARates) -> tuple:
    d = r.valuation_date
    return (
        d.year(), d.month(), d.dayOfMonth(),
        r.repo_nacm, r.zaronia_on, r.jibar_3m,
        r.fra_3x6, r.fra_6x9, r.fra_9x12, r.fra_18x21,
        r.sasw1, r.sasw2, r.sasw3, r.sasw5, r.sasw7, r.sasw10,
        r.ois_1y, r.ois_2y, r.ois_3y, r.ois_4y, r.ois_5y,
    )


# ── Demo portfolio ────────────────────────────────────────────────────────────
def build_portfolio(cb: SACurveBuilder) -> list[SASwap]:
    r = cb.rates
    return [
        SASwap(SwapSpec(5_000_000_000, 0.0810, "10Y", Direction.RCV, "IRS-001-10Y-RCV", "OIS"), cb),
        SASwap(SwapSpec(3_000_000_000, 0.0760, "5Y",  Direction.PAY, "IRS-002-5Y-PAY",  "OIS"), cb),
        SASwap(SwapSpec(2_000_000_000, 0.0715, "2Y",  Direction.RCV, "IRS-003-2Y-RCV",  "OIS"), cb),
        SASwap(SwapSpec(4_000_000_000, 0.0785, "7Y",  Direction.RCV, "IRS-004-7Y-RCV",  "OIS"), cb),
        SASwap(SwapSpec(1_500_000_000, 0.0730, "3Y",  Direction.PAY, "OIS-005-3Y-PAY",  "OIS"), cb),
        SASwap(SwapSpec(2_500_000_000, 0.0700, "1Y",  Direction.RCV, "OIS-006-1Y-RCV",  "OIS"), cb),
    ]


# ── TAB: Curve ────────────────────────────────────────────────────────────────
def tab_curve(cb: SACurveBuilder):
    df = cb.curve_df()

    # KPI row
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("ZARONIA O/N", f"{cb.rates.zaronia_on*100:.4f}%")
    col2.metric("JIBAR 3M",    f"{cb.rates.jibar_3m*100:.4f}%")
    col3.metric("OIS 5Y",      f"{cb.rates.ois_5y*100:.4f}%")
    col4.metric("SASW10",      f"{cb.rates.sasw10*100:.4f}%")
    col5.metric("SARB Repo",   f"{cb.rates.repo_nacm*100:.4f}%")

    st.markdown("---")

    # ── Yield curve chart ──────────────────────────────────────────────────
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=["OIS Zero Rates", "JIBAR Zero Rates",
                        "OIS vs JIBAR Spread (bps)", "Discount Factors"],
        vertical_spacing=0.16, horizontal_spacing=0.10,
    )

    tenors_x = df["tenor"].tolist()

    fig.add_trace(go.Scatter(
        x=tenors_x, y=df["ois_zero_pct"],
        mode="lines+markers", name="OIS Zero",
        line=dict(color=P["green"], width=2.5),
        marker=dict(size=6, color=P["green"]),
        hovertemplate="%{x}: <b>%{y:.4f}%</b><extra>OIS Zero</extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=tenors_x, y=df["jibar_zero_pct"],
        mode="lines+markers", name="JIBAR Zero",
        line=dict(color=P["blue"], width=2.5),
        marker=dict(size=6, color=P["blue"]),
        hovertemplate="%{x}: <b>%{y:.4f}%</b><extra>JIBAR Zero</extra>",
    ), row=1, col=2)

    spread_colors = [P["pos"] if v >= 0 else P["neg"] for v in df["ois_jibar_spread_bps"]]
    fig.add_trace(go.Bar(
        x=tenors_x, y=df["ois_jibar_spread_bps"],
        name="OIS-JIBAR Spread",
        marker_color=spread_colors,
        marker_line_width=0,
        hovertemplate="%{x}: <b>%{y:.2f} bps</b><extra>JIBAR−OIS</extra>",
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=tenors_x, y=df["discount_factor"],
        mode="lines+markers", name="Discount Factor",
        fill="tozeroy", fillcolor="rgba(0,168,90,0.08)",
        line=dict(color=P["gold"], width=2.5),
        marker=dict(size=6),
        hovertemplate="%{x}: <b>%{y:.6f}</b><extra>DF</extra>",
    ), row=2, col=2)

    fig.update_layout(title=_title("ZARONIA OIS + JIBAR Dual Curve"), **_ct())
    for ann in fig.layout.annotations:
        ann.font = dict(family=FONT_SANS, size=11, color=P["txt2"])
    for r, c in [(1,1),(1,2),(2,1),(2,2)]:
        fig.update_xaxes(gridcolor=P["grid"], tickfont=dict(family=FONT_MONO, size=9), row=r, col=c)
        fig.update_yaxes(gridcolor=P["grid"], tickfont=dict(family=FONT_MONO, size=9), row=r, col=c)
    fig.update_yaxes(ticksuffix="%", row=1, col=1)
    fig.update_yaxes(ticksuffix="%", row=1, col=2)
    fig.update_yaxes(ticksuffix=" bp", row=2, col=1)
    _pc(fig)

    # ── Curve table ────────────────────────────────────────────────────────
    with st.expander("Curve Data Table", expanded=False):
        st.dataframe(
            df.style.format({
                "discount_factor":     "{:.6f}",
                "ois_zero_pct":        "{:.4f}",
                "jibar_zero_pct":      "{:.4f}",
                "ois_jibar_spread_bps":"{:.2f}",
                "year_frac":           "{:.4f}",
            }),
            use_container_width=True, hide_index=True,
        )

    # ── Scenario overlay ───────────────────────────────────────────────────
    st.markdown('<div class="section-label">Curve Scenarios</div>', unsafe_allow_html=True)
    shocked = {
        "+25bp Parallel":    cb.parallel_shift(+25),
        "−25bp Parallel":    cb.parallel_shift(-25),
        "+100bp Parallel":   cb.parallel_shift(+100),
        "Steepener +10/−10": cb.steepener(-10, +10, "2Y"),
        "Flattener −10/+10": cb.steepener(+10, -10, "2Y"),
    }
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=tenors_x, y=df["ois_zero_pct"],
        mode="lines+markers", name="Base",
        line=dict(color=P["green"], width=3),
        marker=dict(size=7),
    ))
    scene_cols = [P["red"], P["gold"], "#9B72CF", "#2EC4B6", "#E07A5F"]
    dashes     = ["dot", "dash", "longdash", "dashdot", "longdashdot"]
    for i, (lbl, scb) in enumerate(shocked.items()):
        sdf = scb.curve_df()
        fig2.add_trace(go.Scatter(
            x=sdf["tenor"].tolist(), y=sdf["ois_zero_pct"],
            mode="lines", name=lbl,
            line=dict(color=scene_cols[i % len(scene_cols)],
                      width=1.5, dash=dashes[i % len(dashes)]),
        ))
    fig2.update_layout(title=_title("ZARONIA OIS Curve Scenarios"), **_ct())
    fig2.update_yaxes(ticksuffix="%")
    _pc(fig2)


# ── TAB: Portfolio ────────────────────────────────────────────────────────────
def tab_portfolio(cb: SACurveBuilder, trades: list[SASwap]):
    rows = [t.summary() for t in trades]
    df = pd.DataFrame(rows)

    # Portfolio totals
    tot_npv  = sum(t.npv  for t in trades)
    tot_bpv  = sum(t.bpv  for t in trades)
    tot_dv01 = abs(tot_bpv)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Portfolio NPV",  f"ZAR {tot_npv/1e6:,.1f}m",
                delta=f"{'Long' if tot_npv > 0 else 'Short'} MTM")
    col2.metric("Net BPV /bp",   f"ZAR {tot_bpv:,.0f}",
                delta=f"{'Receive' if tot_bpv < 0 else 'Pay'} bias")
    col3.metric("Total DV01",    f"ZAR {tot_dv01:,.0f}")
    col4.metric("# Trades",      len(trades))

    st.markdown("---")

    # Blotter table
    st.markdown('<div class="section-label">Trade Blotter</div>', unsafe_allow_html=True)

    display_df = df.rename(columns={
        "trade_id":      "Trade ID",
        "type":          "Type",
        "tenor":         "Tenor",
        "direction":     "Direction",
        "notional_ZARm": "Notional (ZARm)",
        "fixed_rate_%":  "Fixed Rate %",
        "fair_rate_%":   "Fair Rate %",
        "npv_ZAR":       "NPV (ZAR)",
        "bpv_ZAR":       "BPV (ZAR/bp)",
        "dv01_ZAR":      "DV01 (ZAR)",
        "duration_yrs":  "Duration (yrs)",
    })

    def colour_npv(val):
        c = "#00C875" if val > 0 else "#E84040"
        return f"color: {c}; font-family: IBM Plex Mono, monospace;"
    def colour_bpv(val):
        c = "#00C875" if val < 0 else "#E84040"
        return f"color: {c}; font-family: IBM Plex Mono, monospace;"

    styled = (
        display_df.style
        .applymap(colour_npv, subset=["NPV (ZAR)"])
        .applymap(colour_bpv, subset=["BPV (ZAR/bp)"])
        .format({
            "Notional (ZARm)": "{:,.0f}",
            "Fixed Rate %":    "{:.4f}",
            "Fair Rate %":     "{:.4f}",
            "NPV (ZAR)":       "{:+,.0f}",
            "BPV (ZAR/bp)":    "{:+,.0f}",
            "DV01 (ZAR)":      "{:,.0f}",
            "Duration (yrs)":  "{:.3f}",
        })
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # NPV bar chart
    st.markdown('<div class="section-label">Mark-to-Market by Trade</div>',
                unsafe_allow_html=True)
    npv_vals  = [t.npv for t in trades]
    npv_cols  = [P["pos"] if v >= 0 else P["neg"] for v in npv_vals]
    trade_ids = [t.spec.trade_id for t in trades]

    fig = go.Figure(go.Bar(
        x=trade_ids, y=npv_vals,
        marker_color=npv_cols, marker_line_width=0,
        text=[f"{v:+,.0f}" for v in npv_vals],
        textposition="outside",
        textfont=dict(family=FONT_MONO, size=9, color=P["txt2"]),
        hovertemplate="<b>%{x}</b><br>NPV: ZAR %{y:+,.0f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=P["border"], line_width=1)
    fig.update_layout(title=_title("NPV per Trade (ZAR)"), **_ct())
    _pc(fig)

    # Fair vs Fixed scatter
    st.markdown('<div class="section-label">Fair Rate vs Fixed Rate</div>',
                unsafe_allow_html=True)
    fig2 = go.Figure()
    for t in trades:
        off = (t.fair_rate - t.spec.rate) * 10_000
        col = P["pos"] if off > 0 else P["neg"]
        fig2.add_trace(go.Bar(
            x=[t.spec.trade_id], y=[off],
            marker_color=col, marker_line_width=0,
            name=t.spec.trade_id,
            showlegend=False,
            text=[f"{off:+.2f} bps"],
            textposition="outside",
            textfont=dict(family=FONT_MONO, size=9),
            hovertemplate=(
                f"<b>{t.spec.trade_id}</b><br>"
                f"Fixed: {t.spec.rate*100:.4f}%<br>"
                f"Fair:  {t.fair_rate*100:.4f}%<br>"
                f"Off-market: %{{y:+.2f}} bps<extra></extra>"
            ),
        ))
    fig2.add_hline(y=0, line_color=P["border"], line_width=1)
    fig2.update_layout(title=_title("Off-Market Spread (bps) — Fair − Fixed"), **_ct())
    fig2.update_yaxes(ticksuffix=" bps")
    _pc(fig2)


# ── TAB: Risk ─────────────────────────────────────────────────────────────────
def tab_risk(cb: SACurveBuilder, trades: list[SASwap]):
    krd_df = portfolio_krd(trades)
    net_krd = krd_df.loc["NET"]
    buckets  = [c for c in krd_df.columns]

    # KPIs
    tot_bpv = portfolio_bpv(trades)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Net BPV /bp",     f"ZAR {tot_bpv:,.0f}")
    col2.metric("Net DV01",        f"ZAR {abs(tot_bpv):,.0f}")
    col3.metric("Duration Bias",   "Receive" if tot_bpv < 0 else "Pay")
    max_b = max(net_krd.abs())
    col4.metric("Max KRD Bucket",  f"{net_krd.abs().idxmax()} — ZAR {max_b:,.0f}")

    st.markdown("---")

    # ── DV01 ladder ───────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Net KRD Bucket Ladder</div>',
                unsafe_allow_html=True)
    bar_cols = [P["pos"] if v >= 0 else P["neg"] for v in net_krd.values]
    fig = go.Figure(go.Bar(
        x=net_krd.values, y=buckets,
        orientation="h",
        marker_color=bar_cols, marker_line_width=0,
        text=[f"{v:+,.0f}" for v in net_krd.values],
        textposition="outside",
        textfont=dict(family=FONT_MONO, size=9, color=P["txt2"]),
        hovertemplate="<b>%{y}</b>: ZAR %{x:,.0f} /bp<extra></extra>",
    ))
    fig.add_vline(x=0, line_color=P["border"], line_width=1)
    fig.update_layout(title=_title("Net Key-Rate DV01 (ZAR / bp)"), height=380, **_ct())
    _pc(fig)

    # ── KRD heatmap ───────────────────────────────────────────────────────
    st.markdown('<div class="section-label">KRD Heatmap — Trade × Tenor</div>',
                unsafe_allow_html=True)
    hm_df = krd_df.copy()
    abs_max = max(hm_df.values.max(), abs(hm_df.values.min()), 1)
    fig2 = go.Figure(go.Heatmap(
        z=hm_df.values,
        x=buckets,
        y=list(hm_df.index),
        colorscale=[[0, P["neg"]], [0.5, P["panel"]], [1, P["pos"]]],
        zmid=0, zmin=-abs_max, zmax=abs_max,
        text=[[f"{v:,.0f}" for v in row] for row in hm_df.values],
        texttemplate="%{text}",
        textfont=dict(family=FONT_MONO, size=8),
        colorbar=dict(
            title=dict(text="ZAR/bp", font=dict(family=FONT_SANS, size=10, color=P["txt2"])),
            tickfont=dict(family=FONT_MONO, size=9),
            outlinewidth=0, thickness=10,
        ),
        hovertemplate="<b>%{y}</b> | %{x}<br>KRD: ZAR %{z:,.0f} /bp<extra></extra>",
    ))
    fig2.update_layout(title=_title("KRD Heatmap (ZAR / bp)"), **_ct())
    _pc(fig2)

    # ── Delta ladder table ─────────────────────────────────────────────────
    st.markdown('<div class="section-label">IR Delta Ladder (ZAR / bp)</div>',
                unsafe_allow_html=True)
    fmt = {col: "{:,.0f}" for col in krd_df.columns}
    st.dataframe(
        krd_df.style.format(fmt)
        .background_gradient(cmap="RdYlGn", axis=None, vmin=-abs_max, vmax=abs_max),
        use_container_width=True,
    )

    # ── Per-trade DV01 ────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Per-Trade DV01 & Duration</div>',
                unsafe_allow_html=True)
    dv_rows = [{"Trade": t.spec.trade_id,
                "DV01 ZAR": round(t.dv01, 0),
                "BPV ZAR":  round(t.bpv, 0),
                "Duration": round(t.duration, 3),
                "Convexity":round(t.convexity, 2)} for t in trades]
    st.dataframe(pd.DataFrame(dv_rows).style.format({
        "DV01 ZAR": "{:,.0f}", "BPV ZAR": "{:+,.0f}",
        "Duration": "{:.3f}", "Convexity": "{:.2f}",
    }), use_container_width=True, hide_index=True)


# ── TAB: Hedging ──────────────────────────────────────────────────────────────
def tab_hedging(cb: SACurveBuilder, trades: list[SASwap]):
    net_bpv = portfolio_bpv(trades)

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown('<div class="section-label">Hedge Parameters</div>',
                    unsafe_allow_html=True)
        hedge_tenor   = st.selectbox("Hedge Tenor", ["1Y","2Y","3Y","5Y","7Y","10Y"], index=3)
        hedge_frac    = st.slider("Coverage %", 25, 100, 100, 5) / 100
        hedge_type    = st.radio("Instrument", ["OIS", "IRS"], horizontal=True)

    with col2:
        pre_dv01 = abs(net_bpv)
        st.metric("Pre-Hedge DV01", f"ZAR {pre_dv01:,.0f}",
                  delta=f"{'Receiver' if net_bpv < 0 else 'Payer'} bias")

    # Build macro hedge
    try:
        hswap = macro_hedge(trades, cb, hedge_tenor, hedge_type, hedge_frac)
    except Exception as e:
        st.error(f"Hedge build error: {e}")
        return

    if hswap is None:
        st.warning("Portfolio is already flat — no hedge required.")
        return

    post_bpv  = net_bpv + hswap.bpv
    post_dv01 = abs(post_bpv)
    eff       = max(0.0, 1.0 - post_dv01 / max(pre_dv01, 1)) * 100

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hedge Notional",
              f"ZAR {hswap.spec.notional/1e9:.2f}bn",
              delta=hswap.spec.direction.value)
    c2.metric("Hedge Fixed Rate",
              f"{hswap.spec.rate*100:.4f}%",
              delta=f"Fair {hswap.fair_rate*100:.4f}%")
    c3.metric("Post-Hedge DV01", f"ZAR {post_dv01:,.0f}",
              delta=f"−{(pre_dv01-post_dv01)/max(pre_dv01,1)*100:.1f}%")
    c4.metric("Effectiveness", f"{eff:.1f}%",
              delta="✓" if eff >= 90 else "Partial")

    st.markdown("---")

    # ── KRD comparison ────────────────────────────────────────────────────
    st.markdown('<div class="section-label">KRD Before vs After</div>',
                unsafe_allow_html=True)
    pre_krd  = portfolio_krd(trades).loc["NET"]
    all_trades = trades + [hswap]
    post_krd = portfolio_krd(all_trades).loc["NET"]
    buckets  = list(pre_krd.index)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=buckets, y=pre_krd.values, name="Pre-Hedge",
        marker_color=P["neg"], marker_line_width=0, opacity=0.85,
        text=[f"{v:,.0f}" for v in pre_krd.values], textposition="outside",
        textfont=dict(family=FONT_MONO, size=8, color=P["txt2"]),
    ))
    fig.add_trace(go.Bar(
        x=buckets, y=post_krd.values, name="Post-Hedge",
        marker_color=P["pos"], marker_line_width=0, opacity=0.85,
        text=[f"{v:,.0f}" for v in post_krd.values], textposition="outside",
        textfont=dict(family=FONT_MONO, size=8, color=P["txt2"]),
    ))
    fig.add_hline(y=0, line_color=P["border"], line_width=1)
    fig.update_layout(
        title=_title(f"KRD Before vs After — {eff:.1f}% Effective"),
        barmode="group", **_ct(),
    )
    _pc(fig)

    # ── Hedge leg detail ──────────────────────────────────────────────────
    st.markdown('<div class="section-label">Hedge Instrument</div>',
                unsafe_allow_html=True)
    hdata = hswap.summary()
    hdf = pd.DataFrame([{
        "Field": k, "Value": str(v)
    } for k, v in hdata.items()])
    st.dataframe(hdf, use_container_width=True, hide_index=True)

    # ── Carry & Roll of hedge ─────────────────────────────────────────────
    st.markdown('<div class="section-label">Hedge Carry & Roll (3M)</div>',
                unsafe_allow_html=True)
    try:
        cr = hswap.carry_roll(3)
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Carry (3M)", f"ZAR {cr['carry_ZAR']:,.0f}", delta=f"{cr['carry_bps']:.2f} bps")
        cc2.metric("Roll (3M)",  f"ZAR {cr['roll_ZAR']:,.0f}")
        cc3.metric("Total C+R",  f"ZAR {cr['total_ZAR']:,.0f}")
    except Exception as e:
        st.caption(f"Carry calc: {e}")


# ── TAB: Scenarios ────────────────────────────────────────────────────────────
def tab_scenarios(cb: SACurveBuilder, trades: list[SASwap]):
    st.markdown('<div class="section-label">Rate Shock Controls</div>',
                unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        par_shift = st.slider("Parallel Shift (bps)", -200, 200, 0, 5)
    with col2:
        steep_short = st.slider("Short-End Shift (bps, 2s10s)", -50, 50, 0, 5)
    with col3:
        steep_long  = st.slider("Long-End Shift (bps, 2s10s)", -50, 50, 0, 5)

    # Build user scenario
    user_cb = cb.parallel_shift(par_shift).steepener(steep_short, steep_long, "2Y")

    # Standard scenarios
    SCENARIOS = [
        ("Base",              cb,                        "Base"),
        ("+25bp Parallel",    cb.parallel_shift(+25),    "Parallel"),
        ("−25bp Parallel",    cb.parallel_shift(-25),    "Parallel"),
        ("+100bp Parallel",   cb.parallel_shift(+100),   "Parallel"),
        ("−100bp Parallel",   cb.parallel_shift(-100),   "Parallel"),
        ("Steepener +10/−10", cb.steepener(-10, +10),    "Curve"),
        ("Flattener −10/+10", cb.steepener(+10, -10),    "Curve"),
        ("User Scenario",     user_cb,                   "Custom"),
    ]

    rows = []
    base_npv = portfolio_npv(trades)
    for name, scb, cat in SCENARIOS:
        shocked = [SASwap(t.spec, scb) for t in trades]
        pnl = portfolio_npv(shocked) - base_npv
        dv01 = abs(portfolio_bpv(shocked))
        rows.append({
            "Scenario":   name,
            "Category":   cat,
            "P&L (ZAR)":  round(pnl, 0),
            "Post DV01":  round(dv01, 0),
            "P&L (bps)":  round(pnl / max(sum(t.spec.notional for t in trades), 1) * 10_000, 2),
        })

    scen_df = pd.DataFrame(rows)

    # ── P&L bar chart ─────────────────────────────────────────────────────
    pnl_vals  = scen_df["P&L (ZAR)"].tolist()[1:]   # exclude Base
    scen_nms  = scen_df["Scenario"].tolist()[1:]
    pnl_cols  = [P["pos"] if v >= 0 else P["neg"] for v in pnl_vals]

    fig = go.Figure(go.Bar(
        x=scen_nms, y=pnl_vals,
        marker_color=pnl_cols, marker_line_width=0,
        text=[f"{v:+,.0f}" for v in pnl_vals],
        textposition="outside",
        textfont=dict(family=FONT_MONO, size=9),
        hovertemplate="<b>%{x}</b><br>P&L: ZAR %{y:+,.0f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=P["border"], line_width=1)
    fig.update_layout(title=_title("Scenario P&L (ZAR) — vs Base"), **_ct())
    _pc(fig)

    # ── Scenario table ────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Scenario P&L Table</div>',
                unsafe_allow_html=True)

    def colour_pnl(val):
        c = P["pos"] if val > 0 else (P["neg"] if val < 0 else P["txt2"])
        return f"color: {c}; font-family: IBM Plex Mono, monospace;"

    st.dataframe(
        scen_df.style
        .applymap(colour_pnl, subset=["P&L (ZAR)", "P&L (bps)"])
        .format({"P&L (ZAR)": "{:+,.0f}", "Post DV01": "{:,.0f}", "P&L (bps)": "{:+.2f}"}),
        use_container_width=True, hide_index=True,
    )

    # ── Per-trade scenario breakdown ──────────────────────────────────────
    st.markdown('<div class="section-label">Per-Trade P&L — User Scenario</div>',
                unsafe_allow_html=True)
    trade_rows = []
    for t in trades:
        base = t.npv
        shocked_npv = SASwap(t.spec, user_cb).npv
        trade_rows.append({
            "Trade":     t.spec.trade_id,
            "Base NPV":  round(base, 0),
            "Scen NPV":  round(shocked_npv, 0),
            "P&L ZAR":   round(shocked_npv - base, 0),
        })
    trade_pnl_df = pd.DataFrame(trade_rows)
    st.dataframe(
        trade_pnl_df.style
        .applymap(colour_pnl, subset=["P&L ZAR"])
        .format({"Base NPV": "{:,.0f}", "Scen NPV": "{:,.0f}", "P&L ZAR": "{:+,.0f}"}),
        use_container_width=True, hide_index=True,
    )


# ── Header banner ─────────────────────────────────────────────────────────────
def render_header(r: SARates):
    d = r.valuation_date
    date_str = f"{d.dayOfMonth():02d} {['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.month()]} {d.year()}"
    st.markdown(f"""
    <div class="desk-header">
      <div style="display:flex;flex-direction:column;gap:2px;border-left:3px solid #007A4D;
                  padding-left:14px;">
        <div style="display:flex;align-items:center;gap:8px;">
          <h1>ZARONIA IRS Desk</h1>
          <span class="badge badge-green">ZAR</span>
          <span class="badge badge-gold">NACQ</span>
          <span class="badge badge-live">● LIVE</span>
        </div>
        <div class="sub">
          South African Rand Overnight Index Average &nbsp;·&nbsp;
          QuantLib 1.42 &nbsp;·&nbsp;
          Valuation: {date_str} &nbsp;·&nbsp;
          Repo {r.repo_nacm*100:.2f}% NACM &nbsp;·&nbsp;
          ZARONIA {r.zaronia_on*100:.4f}%
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    rates = sidebar_rates()
    render_header(rates)

    # Build curve
    try:
        cb = build_curve(rates_to_tuple(rates))
    except Exception as e:
        st.error(f"Curve bootstrap failed: {e}")
        st.stop()

    # Build portfolio
    try:
        trades = build_portfolio(cb)
    except Exception as e:
        st.error(f"Portfolio build failed: {e}")
        st.stop()

    # Navigation tabs
    t_curve, t_port, t_risk, t_hedge, t_scen = st.tabs([
        "📈  CURVE",
        "📋  PORTFOLIO",
        "⚡  RISK",
        "🛡  HEDGING",
        "🌪  SCENARIOS",
    ])

    with t_curve:
        try:
            tab_curve(cb)
        except Exception as e:
            st.error(f"Curve tab error: {e}")

    with t_port:
        try:
            tab_portfolio(cb, trades)
        except Exception as e:
            st.error(f"Portfolio tab error: {e}")

    with t_risk:
        try:
            tab_risk(cb, trades)
        except Exception as e:
            st.error(f"Risk tab error: {e}")

    with t_hedge:
        try:
            tab_hedging(cb, trades)
        except Exception as e:
            st.error(f"Hedging tab error: {e}")

    with t_scen:
        try:
            tab_scenarios(cb, trades)
        except Exception as e:
            st.error(f"Scenarios tab error: {e}")


if __name__ == "__main__":
    main()
