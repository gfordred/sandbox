"""
Risk Engine — PhD-Level Rates Greeks for ZAR IRS / OIS Desk
=============================================================
Computes the full suite of risk metrics used by a South African rates desk:

  * DV01 / BPV (parallel)         — total sensitivity to ±1 bp parallel shift
  * Key-Rate DV01 (KRD)           — per-bucket sensitivity (tenor ladder)
  * Convexity                     — second-order rate sensitivity
  * Duration (modified & Macaulay)— annualised rate sensitivity
  * Carry & Roll decomposition    — P&L attribution over holding horizon
  * Scenario P&L                  — parallel, steepener, flattener, fly
  * IR Delta Ladder               — full 01 grid for position management
  * Hedge Ratio                   — ratio to flatten a given bucket or total

All risk is reported in ZAR and in bps (per notional where appropriate).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd
import QuantLib as ql

from src.curves.zaronia_curve import ZARCurveBuilder, ZAR_DAY_COUNT, ZAR_CALENDAR


# ---------------------------------------------------------------------------
# Type alias for a priceable instrument
# ---------------------------------------------------------------------------

Priceable = Union[
    "src.instruments.ois_swap.ZARONIAOISSwap",  # type: ignore[name-defined]
    "src.instruments.vanilla_irs.ZARVanillaIRS", # type: ignore[name-defined]
]


# ---------------------------------------------------------------------------
# Risk report data classes
# ---------------------------------------------------------------------------

@dataclass
class BucketRisk:
    tenor:      str
    krd_zar:    float   # ZAR P&L per +1 bp in this bucket
    krd_bps:    float   # in bps of notional

    def __repr__(self) -> str:
        return f"BucketRisk({self.tenor}: ZAR {self.krd_zar:,.0f} | {self.krd_bps:.2f} bps)"


@dataclass
class ScenarioPnL:
    scenario:   str
    description: str
    pnl_zar:    float
    pnl_bps:    float   # bps of notional


@dataclass
class RiskReport:
    trade_id:           str
    npv_zar:            float
    bpv_zar:            float        # signed BPV (+1 bp parallel)
    dv01_zar:           float        # |BPV|
    modified_duration:  float        # years
    convexity:          float        # years^2
    bucket_risk:        List[BucketRisk] = field(default_factory=list)
    scenarios:          List[ScenarioPnL] = field(default_factory=list)
    carry_roll:         Dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dataframe(self) -> pd.DataFrame:
        top = {
            "trade_id":          self.trade_id,
            "npv_zar":           round(self.npv_zar, 0),
            "bpv_zar":           round(self.bpv_zar, 0),
            "dv01_zar":          round(self.dv01_zar, 0),
            "mod_duration_yrs":  round(self.modified_duration, 4),
            "convexity":         round(self.convexity, 6),
        }
        return pd.DataFrame([top])

    def bucket_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"tenor": b.tenor, "krd_zar": round(b.krd_zar, 0), "krd_bps": round(b.krd_bps, 4)}
            for b in self.bucket_risk
        ])

    def scenario_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "scenario":    s.scenario,
                "description": s.description,
                "pnl_zar":     round(s.pnl_zar, 0),
                "pnl_bps":     round(s.pnl_bps, 4),
            }
            for s in self.scenarios
        ])

    def __repr__(self) -> str:
        lines = [
            f"=== Risk Report: {self.trade_id} ===",
            f"  NPV          : ZAR {self.npv_zar:>15,.0f}",
            f"  BPV (+1bp)   : ZAR {self.bpv_zar:>15,.0f}",
            f"  DV01         : ZAR {self.dv01_zar:>15,.0f}",
            f"  Mod Duration : {self.modified_duration:.4f} yrs",
            f"  Convexity    : {self.convexity:.6f}",
            "",
            "  Bucket DV01 (KRD):",
        ]
        for b in self.bucket_risk:
            lines.append(f"    {b.tenor:>4s}  ZAR {b.krd_zar:>12,.0f}  ({b.krd_bps:+.4f} bps)")
        if self.scenarios:
            lines += ["", "  Scenario P&L:"]
            for s in self.scenarios:
                lines.append(f"    {s.scenario:<25s} ZAR {s.pnl_zar:>12,.0f}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Risk Engine
# ---------------------------------------------------------------------------

class RiskEngine:
    """
    Compute full risk on any priceable instrument or list of instruments.

    Parameters
    ----------
    curve_builder : ZARCurveBuilder
        Base curve (fully bootstrapped).
    bump_bps      : float
        Size of finite-difference bump for DV01 / KRD (default 1 bp).
    """

    # Standard scenario definitions
    SCENARIOS = [
        ("PARALLEL_UP_25",    "Parallel +25 bps",         25.0,  0.0,  "parallel"),
        ("PARALLEL_DN_25",    "Parallel -25 bps",        -25.0,  0.0,  "parallel"),
        ("PARALLEL_UP_100",   "Parallel +100 bps",       100.0,  0.0,  "parallel"),
        ("PARALLEL_DN_100",   "Parallel -100 bps",      -100.0,  0.0,  "parallel"),
        ("STEEPENER_2s10s",   "2s10s Steepener (+10/-10)", 10.0,-10.0, "steepener"),
        ("FLATTENER_2s10s",   "2s10s Flattener (-10/+10)",-10.0, 10.0, "steepener"),
        ("STEEPENER_5s10s",   "5s10s Steepener (+10/-10)", 10.0,-10.0, "steepener_5s"),
    ]

    def __init__(
        self,
        curve_builder: ZARCurveBuilder,
        bump_bps: float = 1.0,
    ) -> None:
        self.cb = curve_builder
        self.bump = bump_bps

    # ------------------------------------------------------------------
    # Single instrument risk
    # ------------------------------------------------------------------

    def compute(
        self,
        instrument: Priceable,
        buckets: Optional[List[str]] = None,
        compute_scenarios: bool = True,
        compute_carry_roll: bool = True,
        horizon_months: int = 3,
    ) -> RiskReport:
        """Full risk report for a single instrument."""
        notional = instrument.spec.notional
        base_npv = instrument.npv
        bpv = instrument.bpv
        dv01 = instrument.dv01

        # Modified duration
        mod_dur = -bpv * 10_000 / notional

        # Convexity
        up_cb = self.cb.parallel_shift(+self.bump)
        dn_cb = self.cb.parallel_shift(-self.bump)
        dr = self.bump / 10_000
        p_up = self._npv_with_curve(instrument, up_cb)
        p_dn = self._npv_with_curve(instrument, dn_cb)
        convexity = (p_up + p_dn - 2 * base_npv) / (base_npv * dr ** 2) if abs(base_npv) > 1 else 0.0

        # Bucket KRD
        bucket_tenors = buckets or ZARCurveBuilder.KRD_BUCKETS
        shocked_builders = self.cb.reprice_with_shock(bucket_tenors, self.bump)
        valid_tenors = [t for t in bucket_tenors if t in self.cb.mkt.ois_quotes]
        bucket_risk: List[BucketRisk] = []
        for i, t in enumerate(valid_tenors):
            shocked_npv = self._npv_with_curve(instrument, shocked_builders[i])
            krd_zar = shocked_npv - base_npv
            krd_bps = krd_zar / notional * 10_000
            bucket_risk.append(BucketRisk(t, krd_zar, krd_bps))

        # Scenarios
        scenario_pnl: List[ScenarioPnL] = []
        if compute_scenarios:
            scenario_pnl = self._run_scenarios(instrument, notional)

        # Carry & roll
        carry_roll: Dict[str, float] = {}
        if compute_carry_roll and hasattr(instrument, "carry_and_roll"):
            try:
                carry_roll = instrument.carry_and_roll(horizon_months)
            except Exception:
                carry_roll = {}

        return RiskReport(
            trade_id=instrument.spec.trade_id or "UNNAMED",
            npv_zar=base_npv,
            bpv_zar=bpv,
            dv01_zar=dv01,
            modified_duration=mod_dur,
            convexity=convexity,
            bucket_risk=bucket_risk,
            scenarios=scenario_pnl,
            carry_roll=carry_roll,
        )

    # ------------------------------------------------------------------
    # Portfolio-level risk (list of instruments)
    # ------------------------------------------------------------------

    def portfolio_risk(
        self,
        instruments: List[Priceable],
        buckets: Optional[List[str]] = None,
    ) -> "PortfolioRiskReport":
        """Aggregate risk across all instruments in a portfolio."""
        reports = [self.compute(i, buckets, compute_carry_roll=False) for i in instruments]
        return PortfolioRiskReport(reports, self.cb, buckets or ZARCurveBuilder.KRD_BUCKETS)

    # ------------------------------------------------------------------
    # IR Delta Ladder  (01 grid — continuous tenor buckets)
    # ------------------------------------------------------------------

    def delta_ladder(
        self,
        instruments: List[Priceable],
        tenor_grid: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Full delta ladder: columns = tenors, rows = individual trades + Net.
        Values in ZAR per +1bp.
        """
        tenors = tenor_grid or ZARCurveBuilder.KRD_BUCKETS
        rows: List[Dict] = []
        net: Dict[str, float] = {t: 0.0 for t in tenors}
        for inst in instruments:
            shocked_builders = self.cb.reprice_with_shock(tenors, self.bump)
            base_npv = inst.npv
            row: Dict = {"trade_id": inst.spec.trade_id}
            valid = [t for t in tenors if t in self.cb.mkt.ois_quotes]
            for i, t in enumerate(valid):
                snpv = self._npv_with_curve(inst, shocked_builders[i])
                krd = snpv - base_npv
                row[t] = round(krd, 0)
                net[t] = net.get(t, 0.0) + krd
            rows.append(row)
        # Net row
        net_row = {"trade_id": "NET"}
        for t in tenors:
            net_row[t] = round(net.get(t, 0.0), 0)
        rows.append(net_row)
        return pd.DataFrame(rows).set_index("trade_id")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _npv_with_curve(self, instrument: Priceable, cb: ZARCurveBuilder) -> float:
        """Price instrument on an alternate curve without mutating it."""
        import copy
        from src.instruments.ois_swap import ZARONIAOISSwap, OISSwapSpec
        from src.instruments.vanilla_irs import ZARVanillaIRS

        if isinstance(instrument, ZARONIAOISSwap):
            tmp = ZARONIAOISSwap(instrument.spec, cb)
        elif isinstance(instrument, ZARVanillaIRS):
            tmp = ZARVanillaIRS(instrument.spec, cb)
        else:
            raise TypeError(f"Unknown instrument type: {type(instrument)}")
        return tmp.npv

    def _run_scenarios(
        self,
        instrument: Priceable,
        notional: float,
    ) -> List[ScenarioPnL]:
        results: List[ScenarioPnL] = []
        base_npv = instrument.npv
        for (name, desc, long_end, short_end, stype) in self.SCENARIOS:
            try:
                if stype == "parallel":
                    shocked_cb = self.cb.parallel_shift(long_end)
                elif stype == "steepener":
                    shocked_cb = self.cb.steepener_shift(
                        short_end_bps=short_end,
                        long_end_bps=long_end,
                        pivot_tenor="2Y",
                    )
                elif stype == "steepener_5s":
                    shocked_cb = self.cb.steepener_shift(
                        short_end_bps=short_end,
                        long_end_bps=long_end,
                        pivot_tenor="5Y",
                    )
                else:
                    continue
                scn_npv = self._npv_with_curve(instrument, shocked_cb)
                pnl = scn_npv - base_npv
                results.append(ScenarioPnL(
                    scenario=name,
                    description=desc,
                    pnl_zar=pnl,
                    pnl_bps=pnl / notional * 10_000,
                ))
            except Exception:
                continue
        return results


# ---------------------------------------------------------------------------
# Portfolio Risk Report
# ---------------------------------------------------------------------------

@dataclass
class PortfolioRiskReport:
    """Aggregated risk across multiple instruments."""
    trade_reports: List[RiskReport]
    curve_builder: ZARCurveBuilder
    bucket_tenors: List[str]

    @property
    def total_npv(self) -> float:
        return sum(r.npv_zar for r in self.trade_reports)

    @property
    def total_bpv(self) -> float:
        return sum(r.bpv_zar for r in self.trade_reports)

    @property
    def total_dv01(self) -> float:
        return abs(self.total_bpv)

    @property
    def net_bucket_dv01(self) -> Dict[str, float]:
        """Sum of bucket KRDs across all trades."""
        result: Dict[str, float] = {}
        for r in self.trade_reports:
            for b in r.bucket_risk:
                result[b.tenor] = result.get(b.tenor, 0.0) + b.krd_zar
        return result

    def summary_dataframe(self) -> pd.DataFrame:
        rows = []
        for r in self.trade_reports:
            rows.append({
                "trade_id":    r.trade_id,
                "npv_ZAR":     round(r.npv_zar, 0),
                "bpv_ZAR":     round(r.bpv_zar, 0),
                "dv01_ZAR":    round(r.dv01_zar, 0),
                "mod_dur_yrs": round(r.modified_duration, 3),
            })
        # Add portfolio total
        rows.append({
            "trade_id":    "PORTFOLIO",
            "npv_ZAR":     round(self.total_npv, 0),
            "bpv_ZAR":     round(self.total_bpv, 0),
            "dv01_ZAR":    round(self.total_dv01, 0),
            "mod_dur_yrs": float("nan"),
        })
        return pd.DataFrame(rows)

    def bucket_heatmap_data(self) -> pd.DataFrame:
        """Wide DataFrame: rows = trades, columns = tenor buckets, values = KRD ZAR."""
        rows = []
        for r in self.trade_reports:
            row = {"trade_id": r.trade_id}
            for b in r.bucket_risk:
                row[b.tenor] = round(b.krd_zar, 0)
            rows.append(row)
        # Net row
        net_krd = self.net_bucket_dv01
        rows.append({"trade_id": "NET", **{t: round(v, 0) for t, v in net_krd.items()}})
        return pd.DataFrame(rows).set_index("trade_id").fillna(0)

    def __repr__(self) -> str:
        lines = [
            f"=== Portfolio Risk Report ({len(self.trade_reports)} trades) ===",
            f"  Total NPV  : ZAR {self.total_npv:>15,.0f}",
            f"  Total BPV  : ZAR {self.total_bpv:>15,.0f}",
            f"  Total DV01 : ZAR {self.total_dv01:>15,.0f}",
            "",
            "  Net Bucket DV01 (KRD):",
        ]
        for t, v in sorted(self.net_bucket_dv01.items(), key=lambda x: _tenor_sort_key(x[0])):
            lines.append(f"    {t:>4s}  ZAR {v:>12,.0f}")
        return "\n".join(lines)


def _tenor_sort_key(t: str) -> float:
    """Convert tenor string to float years for sorting."""
    if t.endswith("D"):
        return float(t[:-1]) / 365
    if t.endswith("W"):
        return float(t[:-1]) / 52
    if t.endswith("M"):
        return float(t[:-1]) / 12
    if t.endswith("Y"):
        return float(t[:-1])
    return 0.0
