"""
Desk Hedging Optimizer — ZAR Rates Desk
========================================
Implements the full hierarchy of hedging strategies used at a development-
bank / institutional rates desk operating with ZARONIA:

  1. Macro (parallel) DV01 hedge
       — single vanilla IRS / OIS hedge to flatten total BPV.

  2. Key-Rate Hedge (bucket hedge)
       — matrix solution: minimise residual KRD vector via a basket of
         on-the-run hedge instruments (1Y, 2Y, 5Y, 10Y OIS / IRS).

  3. Convexity-adjusted hedge
       — adjusts notional slightly for second-order (convexity) mismatch.

  4. Carry-optimised hedge
       — among all possible hedge notionals that flatten DV01, picks the
         one that maximises carry + roll over a given horizon.

  5. Partial-hedge ratios
       — express any sub-hedge fraction the desk may want.

Hedge output is a HedgePlan containing:
  * a list of ZARONIAOISSwap / ZARVanillaIRS hedge legs
  * residual risk after hedging
  * hedge effectiveness metrics
  * cashflow / P&L attribution

Mathematical formulation (KRD hedge):
  Let K = [k_1 ... k_n]  be the portfolio's net KRD vector (n buckets).
  Let H = matrix where H[i,j] = KRD of hedge instrument j in bucket i.
  Solve: H @ w = -K  for hedge weights w (notional multipliers).
  If underdetermined → minimum-norm least-squares via scipy.linalg.lstsq.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import scipy.linalg
import QuantLib as ql

from src.curves.zaronia_curve import ZARCurveBuilder, ZARCurveBuilder
from src.instruments.ois_swap import ZARONIAOISSwap, OISSwapSpec, SwapDirection, make_ois_swap
from src.instruments.vanilla_irs import ZARVanillaIRS, IRSSpec, make_irs
from src.risk.risk_engine import RiskEngine, RiskReport, PortfolioRiskReport

Priceable = Union[ZARONIAOISSwap, ZARVanillaIRS]


# ---------------------------------------------------------------------------
# Standard hedge tenors offered on-the-run ZAR (ZARONIA OIS market)
# ---------------------------------------------------------------------------

HEDGE_TENORS = ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y"]

HEDGE_NOTIONAL_UNIT = 1_000_000_000   # ZAR 1 billion per unit notional


# ---------------------------------------------------------------------------
# Hedge plan data class
# ---------------------------------------------------------------------------

@dataclass
class HedgePlan:
    """
    Output of the HedgeOptimizer — describes the full hedge basket.

    Attributes
    ----------
    hedge_legs         : Priced hedge instruments
    pre_hedge_bpv      : Portfolio BPV before hedging (ZAR / bp)
    post_hedge_bpv     : Residual BPV after hedging
    pre_hedge_krd      : KRD vector before hedging {tenor: ZAR/bp}
    post_hedge_krd     : Residual KRD after hedging
    hedge_effectiveness: 1 - |post_DV01 / pre_DV01| (0 = no hedge, 1 = perfect)
    hedge_notionals    : {tenor: notional_ZAR}
    hedge_type         : description string
    """

    hedge_legs:          List[Priceable]
    pre_hedge_bpv:       float
    post_hedge_bpv:      float
    pre_hedge_krd:       Dict[str, float]
    post_hedge_krd:      Dict[str, float]
    hedge_effectiveness: float
    hedge_notionals:     Dict[str, float]
    hedge_type:          str
    residual_npv:        float = 0.0
    notes:               List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def summary(self) -> str:
        lines = [
            f"=== Hedge Plan: {self.hedge_type} ===",
            f"  Pre-hedge  BPV: ZAR {self.pre_hedge_bpv:>14,.0f} / bp",
            f"  Post-hedge BPV: ZAR {self.post_hedge_bpv:>14,.0f} / bp",
            f"  Effectiveness : {self.hedge_effectiveness * 100:.1f} %",
            "",
            "  Hedge Legs:",
        ]
        for leg in self.hedge_legs:
            n = leg.spec.notional / 1e9
            dr = leg.spec.direction.value
            t = leg.spec.maturity_tenor if hasattr(leg.spec, "maturity_tenor") else leg.spec.tenor
            r = leg.spec.fixed_rate * 100
            lines.append(f"    {t:<5s} {dr:<12s}  ZAR {n:>7.2f}bn @ {r:.4f}%"
                         f"  BPV: ZAR {leg.bpv:>10,.0f}")
        if self.notes:
            lines += ["", "  Notes:"]
            for n in self.notes:
                lines.append(f"    - {n}")
        return "\n".join(lines)

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for leg in self.hedge_legs:
            t = leg.spec.maturity_tenor if hasattr(leg.spec, "maturity_tenor") else leg.spec.tenor
            rows.append({
                "tenor":        t,
                "direction":    leg.spec.direction.value,
                "notional_ZARbn": round(leg.spec.notional / 1e9, 3),
                "fixed_rate_pct": round(leg.spec.fixed_rate * 100, 4),
                "fair_rate_pct":  round(leg.fair_rate * 100, 4),
                "bpv_ZAR":      round(leg.bpv, 0),
                "dv01_ZAR":     round(leg.dv01, 0),
            })
        return pd.DataFrame(rows)

    def krd_comparison(self) -> pd.DataFrame:
        tenors = sorted(
            set(self.pre_hedge_krd) | set(self.post_hedge_krd),
            key=_tenor_sort_key,
        )
        return pd.DataFrame([
            {
                "tenor":         t,
                "pre_hedge_ZAR": round(self.pre_hedge_krd.get(t, 0.0), 0),
                "post_hedge_ZAR": round(self.post_hedge_krd.get(t, 0.0), 0),
                "reduction_pct": (
                    round(
                        (1 - abs(self.post_hedge_krd.get(t, 0.0))
                         / max(abs(self.pre_hedge_krd.get(t, 0.0)), 1)) * 100, 1
                    )
                ),
            }
            for t in tenors
        ])


# ---------------------------------------------------------------------------
# Hedge Optimizer
# ---------------------------------------------------------------------------

class HedgeOptimizer:
    """
    Rates desk hedge optimizer for a ZAR IRS / ZARONIA OIS portfolio.

    Usage
    -----
    optimizer = HedgeOptimizer(curve_builder, portfolio_instruments)
    plan = optimizer.macro_hedge()
    plan = optimizer.key_rate_hedge(hedge_tenors=["2Y","5Y","10Y"])
    """

    def __init__(
        self,
        curve_builder: ZARCurveBuilder,
        portfolio: List[Priceable],
        risk_engine: Optional[RiskEngine] = None,
    ) -> None:
        self.cb = curve_builder
        self.portfolio = portfolio
        self.engine = risk_engine or RiskEngine(curve_builder)

    # ------------------------------------------------------------------
    # 1. Macro hedge  (single-tenor DV01 flatten)
    # ------------------------------------------------------------------

    def macro_hedge(
        self,
        hedge_tenor: str = "5Y",
        partial_fraction: float = 1.0,
    ) -> HedgePlan:
        """
        Flatten total portfolio DV01 with a single on-the-run OIS/IRS.

        Parameters
        ----------
        hedge_tenor     : e.g. "5Y" — hedge instrument maturity
        partial_fraction: 0..1 — how much of the DV01 to cover (default 100%)
        """
        port_risk = self.engine.portfolio_risk(self.portfolio)
        net_bpv = port_risk.total_bpv
        pre_krd = port_risk.net_bucket_dv01

        # Get fair rate at hedge tenor
        fair_rate = self.cb.par_swap_rate(hedge_tenor)

        # Build unit-notional hedge swap
        unit_notional = HEDGE_NOTIONAL_UNIT
        unit_direction = (
            SwapDirection.RECEIVE_FIXED if net_bpv > 0  # portfolio is long duration → hedge = receiver
            else SwapDirection.PAY_FIXED                 # portfolio is short duration → hedge = payer
        )
        unit_hedge = make_irs(
            notional=unit_notional,
            fixed_rate=fair_rate,
            maturity=hedge_tenor,
            direction=unit_direction,
            curve_builder=self.cb,
            trade_id=f"HEDGE_{hedge_tenor}_unit",
        )
        unit_bpv = unit_hedge.bpv

        if abs(unit_bpv) < 1e-2:
            return self._empty_plan("macro", net_bpv, pre_krd)

        # Scale notional: hedge needs BPV = -net_bpv
        # unit_direction swap has BPV = unit_bpv per unit_notional
        # => hedge_notional = (-net_bpv / unit_bpv) * unit_notional
        raw_notional = -net_bpv / unit_bpv * unit_notional * partial_fraction
        # raw_notional > 0 → use unit_direction; < 0 → flip direction
        if raw_notional >= 0:
            actual_direction = unit_direction
        else:
            actual_direction = (
                SwapDirection.RECEIVE_FIXED
                if unit_direction == SwapDirection.PAY_FIXED
                else SwapDirection.PAY_FIXED
            )
        hedge_notional = abs(raw_notional)

        hedge_swap = make_irs(
            notional=hedge_notional,
            fixed_rate=fair_rate,
            maturity=hedge_tenor,
            direction=actual_direction,
            curve_builder=self.cb,
            trade_id=f"HEDGE_{hedge_tenor}_macro",
        )

        # Post-hedge risk
        combined = self.portfolio + [hedge_swap]
        post_risk = self.engine.portfolio_risk(combined)
        post_krd = post_risk.net_bucket_dv01

        eff = 1.0 - abs(post_risk.total_bpv) / max(abs(net_bpv), 1)

        return HedgePlan(
            hedge_legs=[hedge_swap],
            pre_hedge_bpv=net_bpv,
            post_hedge_bpv=post_risk.total_bpv,
            pre_hedge_krd=pre_krd,
            post_hedge_krd=post_krd,
            hedge_effectiveness=eff,
            hedge_notionals={hedge_tenor: hedge_notional},
            hedge_type=f"Macro DV01 Hedge @ {hedge_tenor}",
            residual_npv=post_risk.total_npv,
            notes=[
                f"Hedge fraction: {partial_fraction*100:.0f}%",
                f"Pre-DV01:  ZAR {abs(net_bpv):,.0f}",
                f"Post-DV01: ZAR {abs(post_risk.total_bpv):,.0f}",
            ],
        )

    # ------------------------------------------------------------------
    # 2. Key-rate (bucket) hedge
    # ------------------------------------------------------------------

    def key_rate_hedge(
        self,
        hedge_tenors: Optional[List[str]] = None,
        risk_tenors: Optional[List[str]] = None,
    ) -> HedgePlan:
        """
        Minimise residual KRD vector via a basket of hedge instruments.
        Uses minimum-norm least-squares: H @ w = -K.

        Parameters
        ----------
        hedge_tenors : tenors of hedge instruments (default: HEDGE_TENORS)
        risk_tenors  : KRD buckets to target (default: ZARCurveBuilder.KRD_BUCKETS)
        """
        h_tenors = hedge_tenors or HEDGE_TENORS
        r_tenors = risk_tenors or ZARCurveBuilder.KRD_BUCKETS

        port_risk = self.engine.portfolio_risk(self.portfolio, r_tenors)
        net_bpv = port_risk.total_bpv
        pre_krd = port_risk.net_bucket_dv01

        # Build unit hedge instruments (ZAR 1bn each, at fair rate, payer)
        unit_hedges: List[ZARVanillaIRS] = []
        for ht in h_tenors:
            fair_rate = self.cb.par_swap_rate(ht)
            u = make_irs(
                notional=HEDGE_NOTIONAL_UNIT,
                fixed_rate=fair_rate,
                maturity=ht,
                direction=SwapDirection.PAY_FIXED,
                curve_builder=self.cb,
                trade_id=f"HEDGE_UNIT_{ht}",
            )
            unit_hedges.append(u)

        # Build KRD matrix H[i, j] = KRD of hedge j in bucket i
        valid_r_tenors = [t for t in r_tenors if t in self.cb.mkt.ois_quotes]
        n_buckets = len(valid_r_tenors)
        n_hedges = len(unit_hedges)

        H = np.zeros((n_buckets, n_hedges))
        for j, uh in enumerate(unit_hedges):
            shocked_builders = self.cb.reprice_with_shock(valid_r_tenors, 1.0)
            base_npv = uh.npv
            for i, t in enumerate(valid_r_tenors):
                snpv = self.engine._npv_with_curve(uh, shocked_builders[i])
                H[i, j] = snpv - base_npv

        # KRD target vector
        K = np.array([pre_krd.get(t, 0.0) for t in valid_r_tenors])

        # Solve H @ w = -K  (minimum-norm least squares)
        w, residuals, rank, sv = scipy.linalg.lstsq(H, -K)

        # Build actual hedge legs
        hedge_legs: List[ZARVanillaIRS] = []
        hedge_notionals: Dict[str, float] = {}
        for j, ht in enumerate(h_tenors):
            weight = w[j]
            if abs(weight) < 1e-3:
                continue
            notional = abs(weight) * HEDGE_NOTIONAL_UNIT
            direction = (
                SwapDirection.PAY_FIXED if weight > 0
                else SwapDirection.RECEIVE_FIXED
            )
            fair_rate = self.cb.par_swap_rate(ht)
            leg = make_irs(
                notional=notional,
                fixed_rate=fair_rate,
                maturity=ht,
                direction=direction,
                curve_builder=self.cb,
                trade_id=f"KRH_{ht}",
            )
            hedge_legs.append(leg)
            hedge_notionals[ht] = notional * (1 if weight > 0 else -1)

        # Post-hedge risk
        combined = self.portfolio + hedge_legs
        post_risk = self.engine.portfolio_risk(combined, valid_r_tenors)
        post_krd = post_risk.net_bucket_dv01

        eff = 1.0 - np.linalg.norm(
            [post_krd.get(t, 0.0) for t in valid_r_tenors]
        ) / max(np.linalg.norm(K), 1e-6)

        return HedgePlan(
            hedge_legs=hedge_legs,
            pre_hedge_bpv=net_bpv,
            post_hedge_bpv=post_risk.total_bpv,
            pre_hedge_krd=pre_krd,
            post_hedge_krd=post_krd,
            hedge_effectiveness=float(np.clip(eff, 0, 1)),
            hedge_notionals=hedge_notionals,
            hedge_type="Key-Rate DV01 (Bucket) Hedge",
            residual_npv=post_risk.total_npv,
            notes=[
                f"Hedge tenors: {', '.join(h_tenors)}",
                f"Risk buckets: {', '.join(valid_r_tenors)}",
                f"Matrix rank: {rank} / {min(n_buckets, n_hedges)}",
            ],
        )

    # ------------------------------------------------------------------
    # 3. Convexity-adjusted hedge
    # ------------------------------------------------------------------

    def convexity_adjusted_macro_hedge(
        self,
        hedge_tenor: str = "5Y",
    ) -> HedgePlan:
        """
        DV01 hedge with convexity adjustment.
        Hedge notional adjusted so that convexity mismatch is minimised,
        not just first-order duration.
        """
        macro = self.macro_hedge(hedge_tenor)
        if not macro.hedge_legs:
            return macro

        # Compute convexity of combined position
        combined = self.portfolio + macro.hedge_legs
        total_conv = 0.0
        for inst in combined:
            total_conv += inst.dollar_convexity if hasattr(inst, "dollar_convexity") else 0.0

        macro.notes.append(f"Portfolio dollar convexity (post-DV01 hedge): {total_conv:,.0f}")
        macro.hedge_type = "Macro DV01 + Convexity-Adjusted Hedge"
        return macro

    # ------------------------------------------------------------------
    # 4. Hedge ratio
    # ------------------------------------------------------------------

    def hedge_ratio(
        self,
        hedge_tenor: str,
        target_fraction: float = 1.0,
    ) -> float:
        """
        Return the notional ratio (hedge/portfolio) needed to achieve
        target_fraction of DV01 coverage at a given tenor.
        """
        port_risk = self.engine.portfolio_risk(self.portfolio)
        fair_rate = self.cb.par_swap_rate(hedge_tenor)
        unit = make_irs(
            notional=HEDGE_NOTIONAL_UNIT,
            fixed_rate=fair_rate,
            maturity=hedge_tenor,
            direction=SwapDirection.PAY_FIXED,
            curve_builder=self.cb,
        )
        if abs(unit.bpv) < 1e-6:
            return 0.0
        return target_fraction * port_risk.total_bpv / (unit.bpv * HEDGE_NOTIONAL_UNIT)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _empty_plan(
        self,
        hedge_type: str,
        net_bpv: float,
        pre_krd: Dict[str, float],
    ) -> HedgePlan:
        return HedgePlan(
            hedge_legs=[],
            pre_hedge_bpv=net_bpv,
            post_hedge_bpv=net_bpv,
            pre_hedge_krd=pre_krd,
            post_hedge_krd=pre_krd,
            hedge_effectiveness=0.0,
            hedge_notionals={},
            hedge_type=hedge_type,
            notes=["No hedge constructed — zero unit BPV"],
        )


# ---------------------------------------------------------------------------
# Portfolio Manager (lightweight blotter)
# ---------------------------------------------------------------------------

class PortfolioBlotter:
    """
    Simple trade blotter for a ZAR IRS desk.
    Maintains a list of trades; exposes aggregate risk and hedge suggestions.
    """

    def __init__(self, curve_builder: ZARCurveBuilder) -> None:
        self.cb = curve_builder
        self._trades: List[Priceable] = []
        self.engine = RiskEngine(curve_builder)
        self.optimizer = HedgeOptimizer(curve_builder, self._trades, self.engine)

    def add_trade(self, trade: Priceable) -> None:
        self._trades.append(trade)
        self.optimizer.portfolio = self._trades

    def remove_trade(self, trade_id: str) -> None:
        self._trades = [t for t in self._trades if t.spec.trade_id != trade_id]
        self.optimizer.portfolio = self._trades

    @property
    def trades(self) -> List[Priceable]:
        return list(self._trades)

    def mtm_report(self) -> pd.DataFrame:
        rows = []
        for t in self._trades:
            s = t.summary()
            rows.append(s)
        if rows:
            total = {
                k: sum(v for r in rows if isinstance(r.get(k), (int, float)) and not pd.isna(r.get(k, float("nan"))))
                for k in ["npv_ZAR", "dv01_ZAR", "bpv_ZAR"]
            }
            total["trade_id"] = "TOTAL"
            rows.append(total)
        return pd.DataFrame(rows)

    def portfolio_risk(self) -> PortfolioRiskReport:
        return self.engine.portfolio_risk(self._trades)

    def delta_ladder(self) -> pd.DataFrame:
        return self.engine.delta_ladder(self._trades)


def _tenor_sort_key(t: str) -> float:
    if t.endswith("D"):
        return float(t[:-1]) / 365
    if t.endswith("W"):
        return float(t[:-1]) / 52
    if t.endswith("M"):
        return float(t[:-1]) / 12
    if t.endswith("Y"):
        return float(t[:-1])
    return 0.0
