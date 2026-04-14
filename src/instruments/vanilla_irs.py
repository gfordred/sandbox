"""
ZAR Vanilla Interest Rate Swap (IRS)
=====================================
Fixed-for-floating swap where the floating leg is linked to ZARONIA
(or legacy 3M JIBAR in the separate jibar_leg_type mode).

ZARONIA IRS conventions (post-JIBAR transition, SARB 2024):
  Fixed leg  : Annual, Actual/365 Fixed, Modified Following
  Float leg  : Annual, daily-compounded ZARONIA, Actual/365 Fixed
  Settlement : T+2
  Calendar   : South Africa
  Notional   : ZAR (no amortisation in vanilla version)

The instrument supports:
  - Fair rate calculation
  - Full NPV decomposition
  - DV01 / BPV (parallel and key-rate)
  - Carry & roll estimation
  - Forward starting swaps
  - Par rate bootstrapping for any maturity
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import QuantLib as ql
import numpy as np
import pandas as pd

from src.curves.zaronia_curve import (
    ZAR_BDC, ZAR_CALENDAR, ZAR_DAY_COUNT, ZARCurveBuilder,
    ZARONIAIndex, IRS_SETTLE_LAG, _tenor_to_date, ZARONIAMarketData,
)
from src.instruments.ois_swap import SwapDirection


@dataclass
class IRSSpec:
    """Specification for a single vanilla ZAR IRS trade."""
    notional:        float
    fixed_rate:      float        # decimal e.g. 0.0760
    maturity_tenor:  str          # e.g. "10Y"
    direction:       SwapDirection = SwapDirection.PAY_FIXED
    start_tenor:     str = "2D"   # "2D" = spot-starting; "3M" = 3M fwd-start
    trade_id:        str = ""
    book:            str = "ZAR_IRS_DESK"
    fixed_freq:      ql.Frequency = ql.Annual
    float_freq:      ql.Frequency = ql.Quarterly
    float_day_count: Optional[ql.DayCounter] = None


class ZARVanillaIRS:
    """
    ZAR vanilla interest rate swap.
    Float leg = quarterly ZARONIA compounded (post-transition standard).
    """

    def __init__(
        self,
        spec: IRSSpec,
        curve_builder: ZARCurveBuilder,
    ) -> None:
        self.spec = spec
        self.cb = curve_builder
        self._swap: Optional[ql.VanillaSwap] = None
        self._build()

    # ------------------------------------------------------------------
    # Internal QL build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        ql.Settings.instance().evaluationDate = self.cb.mkt.valuation_date
        tod = self.cb.mkt.valuation_date

        # Start / end dates
        if self.spec.start_tenor in ("0D", "2D", "T+2"):
            start = ZAR_CALENDAR.advance(tod, IRS_SETTLE_LAG, ql.Days)
        else:
            start = _tenor_to_date(self.spec.start_tenor, tod)
        end = ZAR_CALENDAR.advance(start, ql.Period(self.spec.maturity_tenor), ZAR_BDC)

        ql_type = (
            ql.OvernightIndexedSwap.Payer
            if self.spec.direction == SwapDirection.PAY_FIXED
            else ql.OvernightIndexedSwap.Receiver
        )

        zaronia = ZARONIAIndex(self.cb.ois_handle)

        # Fixed leg schedule (annual coupon, standard ZAR IRS)
        fixed_sched = ql.MakeSchedule(
            start, end,
            ql.Period(ql.Annual),
            calendar=ZAR_CALENDAR,
            convention=ZAR_BDC,
            rule=ql.DateGeneration.Backward,
        )

        # OvernightIndexedSwap: Type, notional, schedule, fixedRate,
        # fixedDC, overnightIndex, spread, paymentLag, paymentConvention,
        # paymentCalendar, telescopicValueDates
        self._swap = ql.OvernightIndexedSwap(
            ql_type,
            self.spec.notional,
            fixed_sched,
            self.spec.fixed_rate,
            ZAR_DAY_COUNT,
            zaronia,
            0.0,          # spread
            0,            # paymentLag
            ZAR_BDC,      # paymentConvention
            ZAR_CALENDAR, # paymentCalendar
        )

        engine = ql.DiscountingSwapEngine(self.cb.ois_handle)
        self._swap.setPricingEngine(engine)

    def reprice(self, new_cb: ZARCurveBuilder) -> None:
        self.cb = new_cb
        self._build()

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    @property
    def npv(self) -> float:
        return self._swap.NPV()

    @property
    def fair_rate(self) -> float:
        return self._swap.fairRate()

    @property
    def bpv(self) -> float:
        """BPV = NPV sensitivity to +1bp parallel shift (signed)."""
        base = self.npv
        up_cb = self.cb.parallel_shift(+1.0)
        up_swap = ZARVanillaIRS(self.spec, up_cb)
        return up_swap.npv - base

    @property
    def dv01(self) -> float:
        return abs(self.bpv)

    @property
    def modified_duration(self) -> float:
        return -self.bpv * 10_000 / self.spec.notional

    @property
    def convexity(self) -> float:
        """
        Convexity (years^-2) = dollar_convexity / (notional * duration^2).
        Dollar convexity = (P+ + P- - 2P) / (P * dr^2).
        """
        base = self.npv
        up_cb = self.cb.parallel_shift(+1.0)
        dn_cb = self.cb.parallel_shift(-1.0)
        p_up = ZARVanillaIRS(self.spec, up_cb).npv
        p_dn = ZARVanillaIRS(self.spec, dn_cb).npv
        dr = 0.0001
        if abs(base) < 1e-6:
            return 0.0
        return (p_up + p_dn - 2 * base) / (base * dr ** 2)

    def key_rate_dv01(
        self,
        buckets: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """Per-bucket KRD: {tenor: ZAR_per_1bp}."""
        base = self.npv
        shocked_builders = self.cb.reprice_with_shock(buckets, bump_bps=1.0)
        tenors = buckets or ZARCurveBuilder.KRD_BUCKETS
        valid_tenors = [t for t in tenors if t in self.cb.mkt.ois_quotes]
        result: Dict[str, float] = {}
        for i, t in enumerate(valid_tenors):
            shocked = ZARVanillaIRS(self.spec, shocked_builders[i])
            result[t] = shocked.npv - base
        return result

    def carry_and_roll(self, horizon_months: int = 3) -> Dict[str, float]:
        """
        Estimate carry & roll over a horizon.
        Carry = coupon income - funding cost over horizon.
        Roll = change in NPV as swap ages by horizon (curve unchanged).
        """
        ql.Settings.instance().evaluationDate = self.cb.mkt.valuation_date
        base_npv = self.npv
        base_rate = self.fair_rate

        # Roll: advance valuation date by horizon months
        horizon_date = ZAR_CALENDAR.advance(
            self.cb.mkt.valuation_date, ql.Period(horizon_months, ql.Months)
        )
        # Rebuild market data without deepcopy (QL objects are not picklable)
        new_mkt = ZARONIAMarketData(
            valuation_date=horizon_date,
            overnight_rate=self.cb.mkt.overnight_rate,
            ois_quotes=dict(self.cb.mkt.ois_quotes),
            jibar_quotes=dict(self.cb.mkt.jibar_quotes),
        )
        rolled_cb = ZARCurveBuilder(new_mkt).build()

        # Adjust tenor
        remaining_months = int(self.spec.maturity_tenor[:-1]) * 12 \
            if self.spec.maturity_tenor.endswith("Y") \
            else int(self.spec.maturity_tenor[:-1])
        if self.spec.maturity_tenor.endswith("Y"):
            remaining_months = int(self.spec.maturity_tenor[:-1]) * 12 - horizon_months
        elif self.spec.maturity_tenor.endswith("M"):
            remaining_months = int(self.spec.maturity_tenor[:-1]) - horizon_months

        if remaining_months <= 0:
            return {"carry": 0.0, "roll": 0.0, "total": 0.0}

        if remaining_months % 12 == 0:
            new_tenor = f"{remaining_months // 12}Y"
        else:
            new_tenor = f"{remaining_months}M"

        rolled_spec = IRSSpec(
            notional=self.spec.notional,
            fixed_rate=self.spec.fixed_rate,
            maturity_tenor=new_tenor,
            direction=self.spec.direction,
            trade_id=self.spec.trade_id,
        )
        rolled_swap = ZARVanillaIRS(rolled_spec, rolled_cb)
        roll = rolled_swap.npv - base_npv

        # Carry: net coupon * notional * yf_horizon
        yf = ZAR_DAY_COUNT.yearFraction(
            self.cb.mkt.valuation_date, horizon_date
        )
        net_coupon = (
            (self.spec.fixed_rate - self.cb.mkt.overnight_rate) * yf
            * self.spec.notional
        )
        # Payer = pay fixed (negative carry if fixed > floating)
        carry = -net_coupon if self.spec.direction == SwapDirection.PAY_FIXED else net_coupon

        return {
            "carry_ZAR":         round(carry, 2),
            "roll_ZAR":          round(roll, 2),
            "carry_roll_ZAR":    round(carry + roll, 2),
            "horizon_months":    horizon_months,
            "carry_bps":         round(carry / (self.spec.notional * yf) * 10_000, 2),
        }

    def cashflow_table(self) -> pd.DataFrame:
        """Fixed and floating cash flows."""
        rows = []
        for cf in self._swap.fixedLeg():
            rows.append({
                "leg": "fixed",
                "payment_date": cf.date().to_date(),
                "amount_ZAR": cf.amount(),
            })
        for cf in self._swap.overnightLeg():
            rows.append({
                "leg": "float_zaronia",
                "payment_date": cf.date().to_date(),
                "amount_ZAR": cf.amount(),
            })
        return pd.DataFrame(rows).sort_values("payment_date").reset_index(drop=True)

    def summary(self) -> dict:
        krd = self.key_rate_dv01()
        return {
            "trade_id":         self.spec.trade_id,
            "instrument":       "ZAR IRS (ZARONIA float)",
            "tenor":            self.spec.maturity_tenor,
            "notional_ZARbn":   self.spec.notional / 1e9,
            "direction":        self.spec.direction.value,
            "fixed_rate_pct":   round(self.spec.fixed_rate * 100, 4),
            "fair_rate_pct":    round(self.fair_rate * 100, 4),
            "npv_ZAR":          round(self.npv, 0),
            "bpv_ZAR":          round(self.bpv, 0),
            "dv01_ZAR":         round(self.dv01, 0),
            "mod_duration":     round(self.modified_duration, 4),
            "convexity":        round(self.convexity, 4),
            "krd_1Y":           round(krd.get("1Y", 0.0), 0),
            "krd_5Y":           round(krd.get("5Y", 0.0), 0),
            "krd_10Y":          round(krd.get("10Y", 0.0), 0),
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_irs(
    notional: float,
    fixed_rate: float,
    maturity: str,
    direction: SwapDirection = SwapDirection.PAY_FIXED,
    curve_builder: Optional[ZARCurveBuilder] = None,
    trade_id: str = "",
    start_tenor: str = "2D",
) -> ZARVanillaIRS:
    if curve_builder is None:
        from src.curves.zaronia_curve import build_zaronia_ois_curve
        curve_builder = build_zaronia_ois_curve()
    spec = IRSSpec(
        notional=notional,
        fixed_rate=fixed_rate,
        maturity_tenor=maturity,
        direction=direction,
        trade_id=trade_id,
        start_tenor=start_tenor,
    )
    return ZARVanillaIRS(spec, curve_builder)
