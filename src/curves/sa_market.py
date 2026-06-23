"""
SA dual-curve builder: ZARONIA OIS + JIBAR projection (OIS-discounted).
Conventions per zarswap.co.za:
  - Settlement:   T+2
  - Day count:    Actual/365 (Fixed)
  - Fixed leg:    NACQ (quarterly)
  - Calendar:     South Africa
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import QuantLib as ql

# ── ZAR market constants ─────────────────────────────────────────────────────
ZAR_CAL = ql.SouthAfrica()
ZAR_DC  = ql.Actual365Fixed()
ZAR_BDC = ql.ModifiedFollowing
IRS_LAG = 2  # T+2 business-day settlement


# ── Market data snapshot ─────────────────────────────────────────────────────
@dataclass
class SARates:
    valuation_date: ql.Date
    repo_nacm:   float = 0.0750
    zaronia_on:  float = 0.0750
    jibar_3m:    float = 0.0783
    fra_3x6:     float = 0.0765
    fra_6x9:     float = 0.0748
    fra_9x12:    float = 0.0733
    fra_18x21:   float = 0.0718
    sasw1:       float = 0.0758
    sasw2:       float = 0.0752
    sasw3:       float = 0.0763
    sasw5:       float = 0.0778
    sasw7:       float = 0.0793
    sasw10:      float = 0.0810
    ois_1y:      float = 0.0745
    ois_2y:      float = 0.0750
    ois_3y:      float = 0.0760
    ois_4y:      float = 0.0772
    ois_5y:      float = 0.0783


# ── Curve builder ─────────────────────────────────────────────────────────────
class SACurveBuilder:
    def __init__(self, rates: SARates) -> None:
        self.rates = rates
        self._ois_curve:   Optional[ql.YieldTermStructure] = None
        self._jibar_curve: Optional[ql.YieldTermStructure] = None
        self.ois_handle   = ql.RelinkableYieldTermStructureHandle()
        self.jibar_handle = ql.RelinkableYieldTermStructureHandle()

    # ── Bootstrap ─────────────────────────────────────────────────────────────
    def build(self) -> "SACurveBuilder":
        ql.Settings.instance().evaluationDate = self.rates.valuation_date
        self._seed_fixings()
        self._ois_curve   = self._build_ois()
        self._jibar_curve = self._build_jibar()
        self.ois_handle.linkTo(self._ois_curve)
        self.jibar_handle.linkTo(self._jibar_curve)
        return self

    # ── Fixing seeder — prevents "Missing fixing" at pricing time ─────────────
    def _seed_fixings(self) -> None:
        """Register overnight + 3M JIBAR fixings covering the T+2 settlement window."""
        zaronia_idx = self._make_zaronia_idx(ql.YieldTermStructureHandle())
        jibar_idx   = self._make_jibar_idx(ql.YieldTermStructureHandle())
        d = self.rates.valuation_date
        for _ in range(10):
            if ZAR_CAL.isBusinessDay(d):
                zaronia_idx.addFixing(d, self.rates.zaronia_on, True)
                jibar_idx.addFixing(d, self.rates.jibar_3m, True)
            d = d + 1

    # ── OIS curve: O/N deposit + 1Y–5Y ZARONIA OIS (NACQ fixed) ─────────────
    def _build_ois(self) -> ql.YieldTermStructure:
        r = self.rates
        zaronia = self._make_zaronia_idx(ql.YieldTermStructureHandle())

        helpers: list = []

        helpers.append(ql.DepositRateHelper(
            ql.QuoteHandle(ql.SimpleQuote(r.zaronia_on)),
            ql.Period("1D"), 0, ZAR_CAL, ZAR_BDC, False, ZAR_DC,
        ))

        for tenor, rate in zip(
            ["1Y", "2Y", "3Y", "4Y", "5Y"],
            [r.ois_1y, r.ois_2y, r.ois_3y, r.ois_4y, r.ois_5y],
        ):
            helpers.append(ql.OISRateHelper(
                IRS_LAG,
                ql.Period(tenor),
                ql.QuoteHandle(ql.SimpleQuote(rate)),
                zaronia,
                ql.YieldTermStructureHandle(),  # no exogenous discounting (single-curve OIS)
                False,          # telescopicValueDates
                0,              # paymentLag
                ql.Following,   # paymentConvention
                ql.Quarterly,   # paymentFrequency — NACQ
            ))

        curve = ql.PiecewiseLogLinearDiscount(IRS_LAG, ZAR_CAL, helpers, ZAR_DC)
        curve.enableExtrapolation()
        return curve

    # ── JIBAR curve: 3M deposit + FRA strip + NACQ swaps (OIS-discounted) ────
    def _build_jibar(self) -> ql.YieldTermStructure:
        r = self.rates
        exo_disc = ql.YieldTermStructureHandle(self._ois_curve)
        jibar3m  = self._make_jibar_idx(ql.YieldTermStructureHandle())

        helpers: list = []

        helpers.append(ql.DepositRateHelper(
            ql.QuoteHandle(ql.SimpleQuote(r.jibar_3m)),
            ql.Period("3M"), IRS_LAG, ZAR_CAL, ZAR_BDC, False, ZAR_DC,
        ))

        # FRA 9×12 omitted: same 1Y pillar as SASW1 — use SASW1 for that node.
        for m_start, m_end, rate in [
            (3,  6,  r.fra_3x6),
            (6,  9,  r.fra_6x9),
            (18, 21, r.fra_18x21),
        ]:
            helpers.append(ql.FraRateHelper(
                ql.QuoteHandle(ql.SimpleQuote(rate)),
                m_start, m_end, IRS_LAG, ZAR_CAL, ZAR_BDC, False, ZAR_DC,
            ))

        for tenor, rate in zip(
            ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y"],
            [r.sasw1, r.sasw2, r.sasw3, r.sasw5, r.sasw7, r.sasw10],
        ):
            helpers.append(ql.SwapRateHelper(
                ql.QuoteHandle(ql.SimpleQuote(rate)),
                ql.Period(tenor), ZAR_CAL,
                ql.Quarterly,   # NACQ fixed leg
                ZAR_BDC, ZAR_DC,
                jibar3m,
                ql.QuoteHandle(), ql.Period("0D"),
                exo_disc,
            ))

        curve = ql.PiecewiseLogLinearDiscount(IRS_LAG, ZAR_CAL, helpers, ZAR_DC)
        curve.enableExtrapolation()
        return curve

    # ── Index factories ───────────────────────────────────────────────────────
    @staticmethod
    def _make_zaronia_idx(h: ql.YieldTermStructureHandle) -> ql.OvernightIndex:
        return ql.OvernightIndex(
            "ZARONIAON", 0, ql.ZARCurrency(), ZAR_CAL, ZAR_DC, h,
        )

    @staticmethod
    def _make_jibar_idx(h: ql.YieldTermStructureHandle) -> ql.IborIndex:
        return ql.IborIndex(
            "JIBAR3M", ql.Period("3M"), IRS_LAG,
            ql.ZARCurrency(), ZAR_CAL, ZAR_BDC, False, ZAR_DC, h,
        )

    # ── Curve data for display ─────────────────────────────────────────────────
    def curve_df(self) -> pd.DataFrame:
        ql.Settings.instance().evaluationDate = self.rates.valuation_date
        settle = ZAR_CAL.advance(self.rates.valuation_date, IRS_LAG, ql.Days)
        rows = []
        for mths, lbl in zip(
            [3, 6, 12, 18, 24, 36, 48, 60, 84, 120],
            ["3M", "6M", "1Y", "18M", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y"],
        ):
            d = ZAR_CAL.advance(settle, ql.Period(mths, ql.Months))
            try:
                ois_df  = self._ois_curve.discount(d)
                jib_df  = self._jibar_curve.discount(d)
                ois_z   = self._ois_curve.zeroRate(d, ZAR_DC, ql.Continuous).rate() * 100
                jib_z   = self._jibar_curve.zeroRate(d, ZAR_DC, ql.Continuous).rate() * 100
                yf      = ZAR_DC.yearFraction(settle, d)
                rows.append({
                    "tenor":                lbl,
                    "year_frac":            round(yf, 4),
                    "ois_zero_pct":         round(ois_z, 6),
                    "jibar_zero_pct":       round(jib_z, 6),
                    "ois_jibar_spread_bps": round((jib_z - ois_z) * 100, 4),
                    "discount_factor":      round(ois_df, 8),
                })
            except Exception:
                continue
        return pd.DataFrame(rows)

    # ── Scenario builders ──────────────────────────────────────────────────────
    def parallel_shift(self, bps: float) -> "SACurveBuilder":
        shift = bps / 10_000.0
        r = self.rates
        return SACurveBuilder(dataclasses.replace(
            r,
            zaronia_on = r.zaronia_on + shift,
            jibar_3m   = r.jibar_3m   + shift,
            fra_3x6    = r.fra_3x6    + shift,
            fra_6x9    = r.fra_6x9    + shift,
            fra_9x12   = r.fra_9x12   + shift,
            fra_18x21  = r.fra_18x21  + shift,
            sasw1      = r.sasw1      + shift,
            sasw2      = r.sasw2      + shift,
            sasw3      = r.sasw3      + shift,
            sasw5      = r.sasw5      + shift,
            sasw7      = r.sasw7      + shift,
            sasw10     = r.sasw10     + shift,
            ois_1y     = r.ois_1y     + shift,
            ois_2y     = r.ois_2y     + shift,
            ois_3y     = r.ois_3y     + shift,
            ois_4y     = r.ois_4y     + shift,
            ois_5y     = r.ois_5y     + shift,
        )).build()

    def steepener(
        self,
        short_bps: float,
        long_bps: float,
        pivot: str = "2Y",
    ) -> "SACurveBuilder":
        """Shift rates ≤ pivot by short_bps; rates > pivot by long_bps."""
        pivot_months = {"1Y": 12, "2Y": 24, "3Y": 36, "4Y": 48, "5Y": 60}.get(pivot, 24)
        s = short_bps / 10_000.0
        lg = long_bps  / 10_000.0

        def adj(months: int) -> float:
            return s if months <= pivot_months else lg

        r = self.rates
        return SACurveBuilder(dataclasses.replace(
            r,
            zaronia_on = r.zaronia_on + adj(0),
            jibar_3m   = r.jibar_3m   + adj(3),
            fra_3x6    = r.fra_3x6    + adj(6),
            fra_6x9    = r.fra_6x9    + adj(9),
            fra_9x12   = r.fra_9x12   + adj(12),
            fra_18x21  = r.fra_18x21  + adj(21),
            sasw1      = r.sasw1      + adj(12),
            sasw2      = r.sasw2      + adj(24),
            sasw3      = r.sasw3      + adj(36),
            sasw5      = r.sasw5      + adj(60),
            sasw7      = r.sasw7      + adj(84),
            sasw10     = r.sasw10     + adj(120),
            ois_1y     = r.ois_1y     + adj(12),
            ois_2y     = r.ois_2y     + adj(24),
            ois_3y     = r.ois_3y     + adj(36),
            ois_4y     = r.ois_4y     + adj(48),
            ois_5y     = r.ois_5y     + adj(60),
        )).build()
