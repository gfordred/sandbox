#!/usr/bin/env python3
"""
ZARONIA IRS Desk Hedging System — Main Runner
==============================================
Entry point for the South African development-bank-level rates desk.

Demonstrates a complete desk workflow:
  1.  Bootstrap ZARONIA OIS discount curve from market data
  2.  Price a portfolio of ZAR IRS / OIS trades
  3.  Compute full risk suite (DV01, KRD, convexity, duration)
  4.  Run scenario analysis (parallel, steepener, flattener)
  5.  Compute carry & roll attribution
  6.  Build macro and key-rate hedges
  7.  Output the full IR delta ladder
  8.  Generate all Graphify charts + HTML dashboard

Usage
-----
  python main.py                      # full run + HTML dashboard
  python main.py --no-dashboard       # suppress HTML output
  python main.py --scenario stress    # extra stress scenarios
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

import QuantLib as ql
import numpy as np
import pandas as pd

# Project imports
from src.curves.zaronia_curve import (
    ZARCurveBuilder, ZARONIAMarketData, build_zaronia_ois_curve
)
from src.instruments.ois_swap import (
    ZARONIAOISSwap, OISSwapSpec, SwapDirection, make_ois_swap
)
from src.instruments.vanilla_irs import (
    ZARVanillaIRS, IRSSpec, make_irs
)
from src.risk.risk_engine import RiskEngine, RiskReport, PortfolioRiskReport
from src.hedging.hedge_optimizer import (
    HedgeOptimizer, PortfolioBlotter, HedgePlan
)
from src.charts.graphify import Graphify


# ---------------------------------------------------------------------------
# ANSI colour helpers (terminal output)
# ---------------------------------------------------------------------------

GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"

def hdr(msg):  print(f"\n{BOLD}{CYAN}{'='*70}{RESET}");\
               print(f"{BOLD}{CYAN}  {msg}{RESET}");\
               print(f"{BOLD}{CYAN}{'='*70}{RESET}")
def ok(msg):   print(f"  {GREEN}✔ {msg}{RESET}")
def info(msg): print(f"  {YELLOW}▶ {msg}{RESET}")
def dim(msg):  print(f"  {DIM}{msg}{RESET}")


# ---------------------------------------------------------------------------
# 1. Curve bootstrap
# ---------------------------------------------------------------------------

def step_curve(mkt: ZARONIAMarketData) -> ZARCurveBuilder:
    hdr("STEP 1 — ZARONIA OIS Curve Bootstrap")
    t0 = time.perf_counter()
    cb = ZARCurveBuilder(mkt).build()
    elapsed = (time.perf_counter() - t0) * 1000

    ok(f"ZARONIA OIS curve bootstrapped in {elapsed:.1f} ms")
    info(f"Valuation date : {mkt.valuation_date}")
    info(f"Overnight rate : {mkt.overnight_rate*100:.4f}%")
    info(f"OIS quotes     : {len(mkt.ois_quotes)} instruments")

    curve_df = cb.curve_dataframe()
    print()
    print(curve_df.to_string(index=False, max_rows=20))

    # Sanity checks
    df_10y = cb.discount("10Y")
    z_10y  = cb.zero_rate("10Y") * 100
    ok(f"10Y discount factor : {df_10y:.6f}")
    ok(f"10Y zero rate (cont): {z_10y:.4f}%")

    return cb


# ---------------------------------------------------------------------------
# 2. Build portfolio
# ---------------------------------------------------------------------------

def step_portfolio(cb: ZARCurveBuilder) -> list:
    hdr("STEP 2 — Portfolio Construction")

    # Realistic South African development-bank IRS book:
    # Mix of receiver and payer swaps at different tenors
    trades = [
        # Large 10Y receiver — funded asset hedge
        make_irs(
            notional     = 5_000_000_000,    # ZAR 5bn
            fixed_rate   = 0.0810,
            maturity     = "10Y",
            direction    = SwapDirection.RECEIVE_FIXED,
            curve_builder= cb,
            trade_id     = "IRS-001-10Y-RCV",
        ),
        # 5Y payer — liability hedge
        make_irs(
            notional     = 3_000_000_000,
            fixed_rate   = 0.0760,
            maturity     = "5Y",
            direction    = SwapDirection.PAY_FIXED,
            curve_builder= cb,
            trade_id     = "IRS-002-5Y-PAY",
        ),
        # 2Y receiver — short-dated liability
        make_irs(
            notional     = 2_000_000_000,
            fixed_rate   = 0.0715,
            maturity     = "2Y",
            direction    = SwapDirection.RECEIVE_FIXED,
            curve_builder= cb,
            trade_id     = "IRS-003-2Y-RCV",
        ),
        # 7Y receiver — bond hedge
        make_irs(
            notional     = 4_000_000_000,
            fixed_rate   = 0.0785,
            maturity     = "7Y",
            direction    = SwapDirection.RECEIVE_FIXED,
            curve_builder= cb,
            trade_id     = "IRS-004-7Y-RCV",
        ),
        # 3Y OIS payer — funding hedge
        make_ois_swap(
            notional     = 1_500_000_000,
            fixed_rate   = 0.0730,
            tenor        = "3Y",
            direction    = SwapDirection.PAY_FIXED,
            curve_builder= cb,
            trade_id     = "OIS-005-3Y-PAY",
        ),
        # 1Y OIS receiver — short-end position
        make_ois_swap(
            notional     = 2_500_000_000,
            fixed_rate   = 0.0700,
            tenor        = "1Y",
            direction    = SwapDirection.RECEIVE_FIXED,
            curve_builder= cb,
            trade_id     = "OIS-006-1Y-RCV",
        ),
    ]

    for t in trades:
        spec = t.spec
        tenor = getattr(spec, "maturity_tenor", getattr(spec, "tenor", "?"))
        ok(f"Trade {spec.trade_id:<22s}  {tenor:<5s}  "
           f"ZAR {spec.notional/1e9:.1f}bn  {spec.direction.value:<12s}  "
           f"NPV ZAR {t.npv:>15,.0f}")
    return trades


# ---------------------------------------------------------------------------
# 3. Risk engine
# ---------------------------------------------------------------------------

def step_risk(cb: ZARCurveBuilder, trades: list) -> PortfolioRiskReport:
    hdr("STEP 3 — Risk Computation (DV01 / KRD / Convexity / Scenarios)")
    engine = RiskEngine(cb)

    # Individual trade risk
    print(f"\n  {'Trade':<22s}  {'NPV ZAR':>15s}  {'BPV ZAR':>12s}  "
          f"{'DV01 ZAR':>12s}  {'Mod Dur':>9s}  {'Convexity':>12s}")
    print("  " + "-" * 100)

    for t in trades:
        rpt = engine.compute(t, compute_carry_roll=False)
        print(f"  {rpt.trade_id:<22s}  {rpt.npv_zar:>15,.0f}  {rpt.bpv_zar:>12,.0f}  "
              f"{rpt.dv01_zar:>12,.0f}  {rpt.modified_duration:>9.4f}  "
              f"{rpt.convexity:>12.4f}")

    # Portfolio aggregation
    port_risk = engine.portfolio_risk(trades)
    print()
    ok(f"Portfolio Total NPV  : ZAR {port_risk.total_npv:>15,.0f}")
    ok(f"Portfolio Total BPV  : ZAR {port_risk.total_bpv:>15,.0f}")
    ok(f"Portfolio Total DV01 : ZAR {port_risk.total_dv01:>15,.0f}")

    # KRD display
    print(f"\n  {'Bucket':>6s}  {'Net KRD (ZAR/bp)':>20s}")
    print("  " + "-" * 32)
    net_krd = port_risk.net_bucket_dv01
    for t in sorted(net_krd, key=lambda x: _sort_key(x)):
        bar_len = int(abs(net_krd[t]) / max(abs(v) for v in net_krd.values()) * 30) if net_krd.values() else 0
        direction = "+" if net_krd[t] >= 0 else "-"
        bar = f"{'█' * bar_len}"
        print(f"  {t:>6s}  {net_krd[t]:>20,.0f}  {direction}{bar}")

    # Scenarios for first trade
    if trades:
        rpt = engine.compute(trades[0], compute_carry_roll=False)
        print(f"\n  Scenario P&L — {trades[0].spec.trade_id}:")
        for s in rpt.scenarios:
            colour = GREEN if s.pnl_zar >= 0 else RED
            print(f"  {colour}  {s.description:<35s} ZAR {s.pnl_zar:>14,.0f}  "
                  f"({s.pnl_bps:+.2f} bps){RESET}")

    return port_risk


# ---------------------------------------------------------------------------
# 4. Delta ladder
# ---------------------------------------------------------------------------

def step_delta_ladder(cb: ZARCurveBuilder, trades: list) -> pd.DataFrame:
    hdr("STEP 4 — IR Delta Ladder (01 Grid)")
    engine = RiskEngine(cb)
    ladder = engine.delta_ladder(trades)
    pd.set_option("display.float_format", "{:,.0f}".format)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 200)
    print(ladder.to_string())
    pd.reset_option("display.float_format")
    return ladder


# ---------------------------------------------------------------------------
# 5. Hedging
# ---------------------------------------------------------------------------

def step_hedging(cb: ZARCurveBuilder, trades: list) -> tuple[HedgePlan, HedgePlan]:
    hdr("STEP 5 — Desk Hedging (Macro + Key-Rate)")
    engine    = RiskEngine(cb)
    optimizer = HedgeOptimizer(cb, trades, engine)

    # 5a. Macro DV01 hedge
    info("Computing macro DV01 hedge at 5Y …")
    macro_plan = optimizer.macro_hedge(hedge_tenor="5Y")
    print(f"\n{macro_plan.summary()}")

    # 5b. Key-rate hedge
    info("\nComputing key-rate bucket hedge …")
    krd_plan = optimizer.key_rate_hedge(
        hedge_tenors=["1Y","2Y","5Y","7Y","10Y"],
    )
    print(f"\n{krd_plan.summary()}")

    # KRD comparison tables
    print("\n  KRD comparison (Macro hedge):")
    print(macro_plan.krd_comparison().to_string(index=False))

    print("\n  KRD comparison (Key-Rate hedge):")
    print(krd_plan.krd_comparison().to_string(index=False))

    return macro_plan, krd_plan


# ---------------------------------------------------------------------------
# 6. Carry & roll
# ---------------------------------------------------------------------------

def step_carry_roll(trades: list) -> None:
    hdr("STEP 6 — Carry & Roll Attribution (3M horizon)")
    print(f"\n  {'Trade':<22s}  {'Carry ZAR':>14s}  {'Roll ZAR':>14s}  "
          f"{'Total ZAR':>14s}  {'Carry bps':>10s}")
    print("  " + "-" * 85)
    for t in trades:
        if hasattr(t, "carry_and_roll"):
            try:
                cr = t.carry_and_roll(horizon_months=3)
                colour = GREEN if cr.get("carry_roll_ZAR", 0) >= 0 else RED
                print(f"  {colour}{t.spec.trade_id:<22s}  "
                      f"{cr.get('carry_ZAR',0):>14,.0f}  "
                      f"{cr.get('roll_ZAR',0):>14,.0f}  "
                      f"{cr.get('carry_roll_ZAR',0):>14,.0f}  "
                      f"{cr.get('carry_bps',0):>10.2f}{RESET}")
            except Exception as e:
                print(f"  {t.spec.trade_id:<22s}  [error: {e}]")


# ---------------------------------------------------------------------------
# 7. Charts
# ---------------------------------------------------------------------------

def step_charts(
    cb: ZARCurveBuilder,
    trades: list,
    port_risk: PortfolioRiskReport,
    macro_plan: HedgePlan,
    krd_plan: HedgePlan,
    ladder: pd.DataFrame,
    output_dir: str,
    build_dashboard: bool,
) -> None:
    hdr("STEP 7 — Graphify Charts")
    g = Graphify(output_dir=output_dir)

    charts = {
        "yield_curve":        g.yield_curve_plot(cb),
        "fair_rate_curve":    g.fair_rate_curve_plot(cb),
        "dv01_ladder":        g.dv01_ladder_plot(port_risk),
        "krd_heatmap":        g.portfolio_heatmap(port_risk),
        "pnl_attribution":    g.pnl_attribution_plot(port_risk),
        "hedge_effect_macro": g.hedge_effectiveness_plot(macro_plan, "Macro Hedge Effectiveness"),
        "hedge_effect_krd":   g.hedge_effectiveness_plot(krd_plan,   "Key-Rate Hedge Effectiveness"),
        "delta_ladder":       g.delta_ladder_plot(ladder),
        "carry_roll":         g.carry_roll_plot(trades),
        "obsidian_graph":     g.obsidian_graph(root_dir="."),
    }

    # Scenario overlay
    scenarios = {
        "+25bp Parallel":     cb.parallel_shift(+25),
        "-25bp Parallel":     cb.parallel_shift(-25),
        "+100bp Parallel":    cb.parallel_shift(+100),
        "Steepener 2s10s":    cb.steepener_shift(-10, +10, "2Y"),
        "Flattener 2s10s":    cb.steepener_shift(+10, -10, "2Y"),
    }
    charts["curve_scenarios"] = g.curve_scenario_overlay(cb, scenarios)

    # Scenario P&L for the portfolio (first trade for demo)
    if port_risk.trade_reports:
        charts["scenario_pnl"] = g.scenario_pnl_plot(port_risk.trade_reports[0])

    for name, fig in charts.items():
        path = g.save(fig, name)
        ok(f"Saved chart: {path}")

    if build_dashboard:
        dash_path = g.dashboard(
            curve_builder=cb,
            portfolio_risk=port_risk,
            hedge_plan=krd_plan,
            instruments=trades,
            ladder_df=ladder,
        )
        print()
        ok(f"Dashboard saved: {BOLD}{dash_path}{RESET}")
        info("Open in browser: file://" + os.path.abspath(dash_path))


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _sort_key(t: str) -> float:
    if t.endswith("D"): return float(t[:-1]) / 365
    if t.endswith("W"): return float(t[:-1]) / 52
    if t.endswith("M"): return float(t[:-1]) / 12
    if t.endswith("Y"): return float(t[:-1])
    return 0.0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ZARONIA IRS Desk Hedging System"
    )
    parser.add_argument("--no-dashboard", action="store_true",
                        help="Skip HTML dashboard generation")
    parser.add_argument("--output-dir", default="./charts_output",
                        help="Directory for chart HTML files")
    args = parser.parse_args()

    print(f"""
{BOLD}{GREEN}
╔══════════════════════════════════════════════════════════════════════╗
║         ZARONIA IRS Desk — Bank-Level Hedging Analytics             ║
║    South African Rand Overnight Index Average  ·  QuantLib 1.42     ║
║    Development Bank Desk  ·  PhD-Level Rates Analytics              ║
╚══════════════════════════════════════════════════════════════════════╝
{RESET}""")

    # Market data
    mkt = ZARONIAMarketData.current_market()

    # Run all steps
    cb         = step_curve(mkt)
    trades     = step_portfolio(cb)
    port_risk  = step_risk(cb, trades)
    ladder     = step_delta_ladder(cb, trades)
    macro_plan, krd_plan = step_hedging(cb, trades)
    step_carry_roll(trades)
    step_charts(
        cb, trades, port_risk,
        macro_plan, krd_plan, ladder,
        output_dir=args.output_dir,
        build_dashboard=not args.no_dashboard,
    )

    hdr("DONE")
    ok("All analytics complete.")
    ok(f"Charts output: {os.path.abspath(args.output_dir)}")


if __name__ == "__main__":
    main()
