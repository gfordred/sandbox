"""
SASwap — unified OIS instrument (ZARONIA overnight-indexed swap, NACQ fixed leg).
All notionals in ZAR. BPV/DV01 via finite-difference parallel curve shock.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
import QuantLib as ql

from src.curves.sa_market import (
    SACurveBuilder, SARates, ZAR_CAL, ZAR_DC, ZAR_BDC, IRS_LAG,
)

# KRD buckets: OIS curve nodes (all portfolio trades price off the OIS curve)
OIS_BUCKET_LABELS = ["1Y", "2Y", "3Y", "4Y", "5Y"]
OIS_BUCKET_FIELDS = ["ois_1y", "ois_2y", "ois_3y", "ois_4y", "ois_5y"]


class Direction(Enum):
    RCV = "RECEIVE"
    PAY = "PAY"


@dataclass
class SwapSpec:
    notional:  float
    rate:      float       # NACQ fixed rate
    tenor:     str         # e.g. "5Y", "10Y"
    direction: Direction
    trade_id:  str = "SWAP"
    inst_type: str = "OIS"  # "OIS" only for now


# ── Instrument ────────────────────────────────────────────────────────────────
class SASwap:
    def __init__(self, spec: SwapSpec, cb: SACurveBuilder) -> None:
        self.spec = spec
        self.cb   = cb
        self._inst: Optional[ql.OvernightIndexedSwap] = None
        self._build()

    # ── QuantLib instrument construction ──────────────────────────────────────
    def _build(self) -> None:
        ql.Settings.instance().evaluationDate = self.cb.rates.valuation_date
        self._seed_fixings()

        tod   = self.cb.rates.valuation_date
        start = ZAR_CAL.advance(tod, IRS_LAG, ql.Days)
        end   = ZAR_CAL.advance(start, ql.Period(self.spec.tenor))

        schedule = ql.MakeSchedule(
            effectiveDate=start,
            terminationDate=end,
            tenor=ql.Period("3M"),          # quarterly — NACQ
            calendar=ZAR_CAL,
            convention=ZAR_BDC,
        )

        zaronia_idx = ql.OvernightIndex(
            "ZARONIAON", 0, ql.ZARCurrency(), ZAR_CAL, ZAR_DC,
            self.cb.ois_handle,
        )
        # Seed fixings on the newly-created index instance as well
        d = tod
        for _ in range(7):
            if ZAR_CAL.isBusinessDay(d):
                zaronia_idx.addFixing(d, self.cb.rates.zaronia_on, True)
            d = d + 1

        swap_type = (
            ql.OvernightIndexedSwap.Receiver
            if self.spec.direction == Direction.RCV
            else ql.OvernightIndexedSwap.Payer
        )

        self._inst = ql.OvernightIndexedSwap(
            swap_type,
            self.spec.notional,
            schedule,
            self.spec.rate,
            ZAR_DC,
            zaronia_idx,
        )
        engine = ql.DiscountingSwapEngine(self.cb.ois_handle)
        self._inst.setPricingEngine(engine)

    def _seed_fixings(self) -> None:
        """Ensure overnight + JIBAR fixings exist for the settlement window."""
        zaronia_idx = ql.OvernightIndex(
            "ZARONIAON", 0, ql.ZARCurrency(), ZAR_CAL, ZAR_DC,
            ql.YieldTermStructureHandle(),
        )
        jibar_idx = ql.IborIndex(
            "JIBAR3M", ql.Period("3M"), IRS_LAG,
            ql.ZARCurrency(), ZAR_CAL, ZAR_BDC, False, ZAR_DC,
            ql.YieldTermStructureHandle(),
        )
        d = self.cb.rates.valuation_date
        for _ in range(7):
            if ZAR_CAL.isBusinessDay(d):
                zaronia_idx.addFixing(d, self.cb.rates.zaronia_on, True)
                jibar_idx.addFixing(d, self.cb.rates.jibar_3m, True)
            d = d + 1

    def _set_eval_date(self) -> None:
        ql.Settings.instance().evaluationDate = self.cb.rates.valuation_date

    # ── Pricing ───────────────────────────────────────────────────────────────
    @property
    def npv(self) -> float:
        self._set_eval_date()
        self._seed_fixings()
        return self._inst.NPV()

    @property
    def fair_rate(self) -> float:
        self._set_eval_date()
        self._seed_fixings()
        return self._inst.fairRate()

    # ── Risk measures (finite-difference, 1bp shock) ─────────────────────────
    @property
    def bpv(self) -> float:
        """ZAR change in NPV per 1bp parallel shift (signed)."""
        up_npv = SASwap(self.spec, self.cb.parallel_shift(+1.0)).npv
        dn_npv = SASwap(self.spec, self.cb.parallel_shift(-1.0)).npv
        return (up_npv - dn_npv) / 2.0

    @property
    def dv01(self) -> float:
        return abs(self.bpv)

    @property
    def duration(self) -> float:
        """Modified duration (years) ≈ DV01 / (notional × 1bp)."""
        return self.dv01 / max(self.spec.notional * 1e-4, 1.0)

    @property
    def convexity(self) -> float:
        """Dollar convexity per unit notional."""
        base = self.npv
        up_npv = SASwap(self.spec, self.cb.parallel_shift(+1.0)).npv
        dn_npv = SASwap(self.spec, self.cb.parallel_shift(-1.0)).npv
        denom = max(abs(base), 1.0) * 1e-8   # |NPV| × (1bp)²
        return (up_npv + dn_npv - 2.0 * base) / denom

    # ── Carry & roll (simple approximation) ──────────────────────────────────
    def carry_roll(self, months: int) -> dict:
        yf = months / 12.0
        on = self.cb.rates.zaronia_on
        sign = 1.0 if self.spec.direction == Direction.RCV else -1.0
        carry = sign * (self.spec.rate - on) * self.spec.notional * yf
        carry_bps = carry / max(self.spec.notional, 1.0) * 10_000.0

        # Roll: roll the valuation date forward and reprice
        new_val = ZAR_CAL.advance(
            self.cb.rates.valuation_date, ql.Period(months, ql.Months),
        )
        new_rates = dataclasses.replace(self.cb.rates, valuation_date=new_val)
        try:
            new_cb = SACurveBuilder(new_rates).build()
            roll = SASwap(self.spec, new_cb).npv - self.npv
        except Exception:
            roll = 0.0

        return {
            "carry_ZAR": carry,
            "carry_bps":  carry_bps,
            "roll_ZAR":   roll,
            "total_ZAR":  carry + roll,
        }

    # ── Summary dict ─────────────────────────────────────────────────────────
    def summary(self) -> dict:
        return {
            "trade_id":      self.spec.trade_id,
            "type":          self.spec.inst_type,
            "tenor":         self.spec.tenor,
            "direction":     self.spec.direction.value,
            "notional_ZARm": round(self.spec.notional / 1e6, 2),
            "fixed_rate_%":  round(self.spec.rate * 100, 6),
            "fair_rate_%":   round(self.fair_rate * 100, 6),
            "npv_ZAR":       round(self.npv, 2),
            "bpv_ZAR":       round(self.bpv, 2),
            "dv01_ZAR":      round(self.dv01, 2),
            "duration_yrs":  round(self.duration, 4),
        }


# ── Portfolio helpers ─────────────────────────────────────────────────────────
def portfolio_npv(trades: list[SASwap]) -> float:
    return sum(t.npv for t in trades)


def portfolio_bpv(trades: list[SASwap]) -> float:
    return sum(t.bpv for t in trades)


def portfolio_krd(trades: list[SASwap]) -> pd.DataFrame:
    """
    Key-rate DV01 (ZAR/bp) per OIS bucket, per trade + NET row.
    Shocks each OIS tenor node independently by ±1bp.
    """
    cb = trades[0].cb
    rows: dict[str, dict] = {}

    for trade in trades:
        krd_row: dict[str, float] = {}
        for bucket, field in zip(OIS_BUCKET_LABELS, OIS_BUCKET_FIELDS):
            base_val = getattr(cb.rates, field)
            up_rates = dataclasses.replace(cb.rates, **{field: base_val + 1e-4})
            dn_rates = dataclasses.replace(cb.rates, **{field: base_val - 1e-4})
            up_npv = SASwap(trade.spec, SACurveBuilder(up_rates).build()).npv
            dn_npv = SASwap(trade.spec, SACurveBuilder(dn_rates).build()).npv
            krd_row[bucket] = (up_npv - dn_npv) / 2.0
        rows[trade.spec.trade_id] = krd_row

    df = pd.DataFrame(rows).T
    df.loc["NET"] = df.sum()
    return df


# ── Macro hedge: single-tenor BPV flatten ────────────────────────────────────
def macro_hedge(
    trades: list[SASwap],
    cb: SACurveBuilder,
    hedge_tenor: str = "5Y",
    inst_type: str = "OIS",
    fraction: float = 1.0,
) -> Optional[SASwap]:
    """
    Returns a single hedge instrument that offsets `fraction` of the portfolio BPV.
    Direction is determined automatically (payer for receiver-heavy book, etc.).
    Returns None if the portfolio is already flat.
    """
    net_bpv = portfolio_bpv(trades)
    if abs(net_bpv) < 1.0:
        return None

    # net_bpv < 0 → receiver-biased → need payer to add positive BPV
    # net_bpv > 0 → payer-biased   → need receiver to add negative BPV
    direction = Direction.PAY if net_bpv < 0 else Direction.RCV

    unit_notional = 1_000_000_000.0  # 1bn
    unit_spec = SwapSpec(
        notional=unit_notional,
        rate=0.0,   # placeholder; will use fair rate
        tenor=hedge_tenor,
        direction=direction,
        trade_id=f"UNIT-{hedge_tenor}",
        inst_type=inst_type,
    )
    unit_swap = SASwap(unit_spec, cb)
    unit_spec_at_fair = dataclasses.replace(unit_spec, rate=unit_swap.fair_rate)
    unit_swap = SASwap(unit_spec_at_fair, cb)
    unit_bpv = unit_swap.bpv

    if abs(unit_bpv) < 1.0:
        return None

    # Required total BPV from hedge = -net_bpv * fraction
    required_bpv   = -net_bpv * fraction
    hedge_notional = required_bpv / (unit_bpv / unit_notional)

    if hedge_notional < 0:
        direction = Direction.PAY if direction == Direction.RCV else Direction.RCV
        hedge_notional = abs(hedge_notional)

    hedge_spec = SwapSpec(
        notional=hedge_notional,
        rate=unit_swap.fair_rate,
        tenor=hedge_tenor,
        direction=direction,
        trade_id=f"MACRO-HEDGE-{hedge_tenor}",
        inst_type=inst_type,
    )
    return SASwap(hedge_spec, cb)
