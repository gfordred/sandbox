"""
ZARONIA OIS Swap Instrument
===========================
Overnight Index Swap: fixed leg vs daily-compounded ZARONIA floating leg.

Market conventions (SARB / ICMA):
  Fixed leg  : Annual, Act/365 Fixed
  Float leg  : Daily compounding of ZARONIA overnight fixings
  Settlement : T+2 from today
  Calendar   : South Africa (Modified Following)
  Notional   : ZAR millions (stored in units, e.g. 100_000_000 = ZAR 100m)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import QuantLib as ql
import pandas as pd

from src.curves.zaronia_curve import (
    ZAR_BDC, ZAR_CALENDAR, ZAR_DAY_COUNT, ZARCurveBuilder, ZARONIAIndex,
    IRS_SETTLE_LAG,
)


class SwapDirection(Enum):
    PAY_FIXED = "pay_fixed"      # pay fixed, receive float (payer swap — long rates risk)
    RECEIVE_FIXED = "recv_fixed"  # receive fixed, pay float (receiver — short rates risk)


@dataclass
class OISSwapSpec:
    """Specification for a single ZARONIA OIS trade."""
    notional:    float        # ZAR amount e.g. 1_000_000_000 = 1bn ZAR
    fixed_rate:  float        # e.g. 0.0700 = 7.00 %
    tenor:       str          # e.g. "5Y"
    direction:   SwapDirection = SwapDirection.PAY_FIXED
    trade_id:    str = ""
    book:        str = "ZARONIA_DESK"
    start_date:  Optional[ql.Date] = None   # None = spot (T+2)


class ZARONIAOISSwap:
    """
    A ZARONIA Overnight Index Swap priced with QuantLib.

    The QL instrument is an OvernightIndexedSwap.
    The discount curve and index curve are both the ZARONIA OIS curve
    (single-curve for ZARONIA).
    """

    def __init__(
        self,
        spec: OISSwapSpec,
        curve_builder: ZARCurveBuilder,
    ) -> None:
        self.spec = spec
        self.cb = curve_builder
        self._swap: Optional[ql.OvernightIndexedSwap] = None
        self._engine: Optional[ql.DiscountingSwapEngine] = None
        self._build()

    # ------------------------------------------------------------------
    # QL instrument construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        ql.Settings.instance().evaluationDate = self.cb.mkt.valuation_date
        tod = self.cb.mkt.valuation_date

        start = self.spec.start_date or ql.TARGET().advance(
            tod, IRS_SETTLE_LAG, ql.Days
        )
        end = ZAR_CALENDAR.advance(start, ql.Period(self.spec.tenor), ZAR_BDC)

        ql_type = (
            ql.OvernightIndexedSwap.Payer
            if self.spec.direction == SwapDirection.PAY_FIXED
            else ql.OvernightIndexedSwap.Receiver
        )

        zaronia_index = ZARONIAIndex(self.cb.ois_handle)

        schedule = ql.MakeSchedule(
            start, end,
            ql.Period("1Y"),
            calendar=ZAR_CALENDAR,
            convention=ZAR_BDC,
            rule=ql.DateGeneration.Backward,
        )
        # OvernightIndexedSwap: Type, notional, schedule, fixedRate,
        # fixedDC, index, spread, paymentLag, paymentConvention,
        # paymentCalendar, telescopicValueDates
        self._swap = ql.OvernightIndexedSwap(
            ql_type,
            self.spec.notional,
            schedule,
            self.spec.fixed_rate,
            ZAR_DAY_COUNT,
            zaronia_index,
            0.0,          # spread
            0,            # paymentLag
            ZAR_BDC,      # paymentConvention
            ZAR_CALENDAR, # paymentCalendar
        )

        self._engine = ql.DiscountingSwapEngine(self.cb.ois_handle)
        self._swap.setPricingEngine(self._engine)

    def reprice(self, new_cb: ZARCurveBuilder) -> None:
        """Re-link to a new curve builder (used for scenario / DV01 calcs)."""
        self.cb = new_cb
        self._build()

    # ------------------------------------------------------------------
    # Greeks / analytics
    # ------------------------------------------------------------------

    @property
    def npv(self) -> float:
        return self._swap.NPV()

    @property
    def fair_rate(self) -> float:
        return self._swap.fairRate()

    @property
    def fixed_leg_npv(self) -> float:
        return self._swap.fixedLegNPV()

    @property
    def float_leg_npv(self) -> float:
        return self._swap.floatingLegNPV()

    @property
    def bpv(self) -> float:
        """
        Basis Point Value = dNPV / d(+1bp) — signed (positive = long duration).
        Computed by parallel-shifting the OIS curve +1 bp.
        """
        base_npv = self._swap.NPV()
        shocked_cb = self.cb.parallel_shift(+1.0)
        shocked_swap = ZARONIAOISSwap(self.spec, shocked_cb)
        return shocked_swap.npv - base_npv

    @property
    def dv01(self) -> float:
        """Absolute DV01 = |BPV|  (always positive by convention)."""
        return abs(self.bpv)

    @property
    def pv01(self) -> float:
        """Alias for DV01."""
        return self.dv01

    @property
    def modified_duration(self) -> float:
        """Approximate modified duration = -BPV * 10000 / notional."""
        return -self.bpv * 10_000 / self.spec.notional

    @property
    def dollar_convexity(self) -> float:
        """
        Dollar convexity = (NPV(+1bp) + NPV(-1bp) - 2*NPV(base)) * 10^8.
        """
        base = self.npv
        up_cb = self.cb.parallel_shift(+1.0)
        dn_cb = self.cb.parallel_shift(-1.0)
        up = ZARONIAOISSwap(self.spec, up_cb).npv
        dn = ZARONIAOISSwap(self.spec, dn_cb).npv
        return (up + dn - 2 * base) * 1e8

    def key_rate_dv01(
        self,
        buckets: Optional[List[str]] = None,
    ) -> dict[str, float]:
        """
        Key-rate DV01 per tenor bucket.
        Returns {tenor: dv01_zar} where dv01_zar is ZAR change for +1 bp in that bucket.
        """
        base = self.npv
        shocked_builders = self.cb.reprice_with_shock(buckets, bump_bps=1.0)
        result: dict[str, float] = {}
        tenors = buckets or ZARCurveBuilder.KRD_BUCKETS
        valid_tenors = [t for t in tenors if t in self.cb.mkt.ois_quotes]
        for i, t in enumerate(valid_tenors):
            shocked_swap = ZARONIAOISSwap(self.spec, shocked_builders[i])
            result[t] = shocked_swap.npv - base
        return result

    def cashflow_table(self) -> pd.DataFrame:
        """Return a DataFrame of fixed and floating leg cash flows."""
        rows = []
        for cf in self._swap.fixedLeg():
            rows.append({
                "leg":     "fixed",
                "accrual_start": cf.accrualStartDate().to_date() if hasattr(cf, "accrualStartDate") else None,
                "payment_date": cf.date().to_date(),
                "amount":  cf.amount(),
            })
        for cf in self._swap.overnightLeg():
            rows.append({
                "leg":     "float_zaronia",
                "accrual_start": None,
                "payment_date": cf.date().to_date(),
                "amount":  cf.amount(),
            })
        df = pd.DataFrame(rows).sort_values("payment_date").reset_index(drop=True)
        return df

    def summary(self) -> dict:
        return {
            "trade_id":          self.spec.trade_id,
            "instrument":        "ZARONIA OIS",
            "tenor":             self.spec.tenor,
            "notional_ZARm":     self.spec.notional / 1e6,
            "direction":         self.spec.direction.value,
            "fixed_rate_pct":    round(self.spec.fixed_rate * 100, 4),
            "fair_rate_pct":     round(self.fair_rate * 100, 4),
            "npv_ZAR":           round(self.npv, 2),
            "dv01_ZAR":          round(self.dv01, 2),
            "bpv_ZAR":           round(self.bpv, 2),
            "mod_duration_yrs":  round(self.modified_duration, 4),
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_ois_swap(
    notional: float,
    fixed_rate: float,
    tenor: str,
    direction: SwapDirection = SwapDirection.PAY_FIXED,
    curve_builder: Optional[ZARCurveBuilder] = None,
    trade_id: str = "",
) -> ZARONIAOISSwap:
    """Convenience constructor."""
    if curve_builder is None:
        from src.curves.zaronia_curve import build_zaronia_ois_curve
        curve_builder = build_zaronia_ois_curve()
    spec = OISSwapSpec(
        notional=notional,
        fixed_rate=fixed_rate,
        tenor=tenor,
        direction=direction,
        trade_id=trade_id,
    )
    return ZARONIAOISSwap(spec, curve_builder)
