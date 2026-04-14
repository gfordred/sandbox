"""
ZARONIA OIS Curve Construction — South African Rand Overnight Index Average
===========================================================================
Bootstrap a fully QuantLib-native OIS discount curve from:
  * ZARONIA overnight deposit (T+0)
  * ZARONIA OIS swap quotes at standard tenors (1W → 10Y)
  * Optional JIBAR FRA / IRS instruments for the cross-curve comparison

The resulting term structure lives on a ql.RelinkableYieldTermStructureHandle
so that all downstream pricers reprice automatically when the curve is
relinked or shocked (curve perturbation for DV01 / KRD calculation).

South Africa market conventions (SARB):
  calendar        : South Africa (ql.SouthAfrica)
  day count       : Actual/365 Fixed
  settlement lag  : T+0 for overnight / T+2 for IRS
  compounding     : Continuous (used internally by QuantLib curves)
  business day    : Modified Following
  ZARONIA fixing  : weighted avg of SARB-repo-based overnight transactions
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import QuantLib as ql
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# South Africa market constants
# ---------------------------------------------------------------------------

ZAR_CALENDAR = ql.SouthAfrica()
ZAR_DAY_COUNT = ql.Actual365Fixed()
ZAR_BDC = ql.ModifiedFollowing                # business day convention
ZAR_SETTLE_LAG = 0                            # ZARONIA overnight — T+0
IRS_SETTLE_LAG = 2                            # vanilla IRS — T+2
ZAR_CURRENCY = ql.ZARCurrency()


# ---------------------------------------------------------------------------
# ZARONIA Index definition
# ---------------------------------------------------------------------------

class ZARONIAIndex(ql.OvernightIndex):
    """
    ZARONIA — Rand Overnight Index Average.
    Mirrors the SONIA / SOFR / €STR family.  Day count = Act/365 Fixed.
    Settlement = T+0, compounding = daily.
    """

    def __init__(
        self,
        ts_handle: Optional[ql.YieldTermStructureHandle] = None,
    ) -> None:
        super().__init__(
            "ZARONIA",                     # family name
            0,                             # settlement days (T+0)
            ZAR_CURRENCY,
            ZAR_CALENDAR,
            ZAR_DAY_COUNT,
            ts_handle or ql.YieldTermStructureHandle(),
        )


# ---------------------------------------------------------------------------
# Market quote container
# ---------------------------------------------------------------------------

@dataclass
class ZARONIAMarketData:
    """
    Raw OIS market quotes for a single valuation date.
    All rates are in decimal form (e.g. 0.0825 = 8.25 %).

    Attributes
    ----------
    valuation_date   : QuantLib Date
    overnight_rate   : ZARONIA fixing / deposit rate
    ois_quotes       : {tenor_str: mid_rate}  e.g. {"1Y": 0.0770}
    jibar_quotes     : {tenor_str: mid_rate}  optional legacy JIBAR swaps
    """

    valuation_date: ql.Date
    overnight_rate: float
    ois_quotes: Dict[str, float] = field(default_factory=dict)
    jibar_quotes: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "ZARONIAMarketData":
        return cls(**d)

    @classmethod
    def current_market(cls) -> "ZARONIAMarketData":
        """
        Indicative market snapshot — April 2026.
        SARB repo held at 7.50 % following 75 bps cuts in 2025.
        ZARONIA circa repo.
        """
        today = ql.Date(14, 4, 2026)
        return cls(
            valuation_date=today,
            overnight_rate=0.0750,
            ois_quotes={
                "1W":  0.0749,
                "2W":  0.0748,
                "1M":  0.0745,
                "2M":  0.0740,
                "3M":  0.0735,
                "6M":  0.0720,
                "9M":  0.0710,
                "1Y":  0.0700,
                "18M": 0.0705,
                "2Y":  0.0715,
                "3Y":  0.0730,
                "4Y":  0.0745,
                "5Y":  0.0760,
                "7Y":  0.0785,
                "10Y": 0.0810,
                "12Y": 0.0825,
                "15Y": 0.0840,
                "20Y": 0.0850,
            },
            jibar_quotes={
                "3M":  0.0780,
                "6M":  0.0775,
                "1Y":  0.0760,
                "2Y":  0.0755,
                "3Y":  0.0770,
                "5Y":  0.0790,
                "7Y":  0.0815,
                "10Y": 0.0835,
            },
        )


# ---------------------------------------------------------------------------
# Curve builder
# ---------------------------------------------------------------------------

class ZARCurveBuilder:
    """
    Constructs the ZARONIA OIS discount curve and (optionally) a
    JIBAR projection curve using QuantLib's piecewise bootstrapper.

    Parameters
    ----------
    market_data : ZARONIAMarketData
    interp      : QuantLib interpolation trait (default: log-linear on discounts)
    """

    # Standard OIS bucket tenors for KRD / bucket-DV01 reporting
    KRD_BUCKETS: List[str] = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y"]

    def __init__(
        self,
        market_data: Optional[ZARONIAMarketData] = None,
        interp: str = "loglinear",
    ) -> None:
        self.mkt = market_data or ZARONIAMarketData.current_market()
        self.interp = interp

        # Relinkable handles — downstream pricers use these
        self.ois_handle = ql.RelinkableYieldTermStructureHandle()
        self.jibar_handle = ql.RelinkableYieldTermStructureHandle()

        # ZARONIA index wired to OIS discount curve
        self.zaronia_index = ZARONIAIndex(self.ois_handle)
        self._ois_curve: Optional[ql.PiecewiseLogLinearDiscount] = None
        self._jibar_curve: Optional[ql.PiecewiseFlatForward] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> "ZARCurveBuilder":
        """Bootstrap both curves; wire handles."""
        ql.Settings.instance().evaluationDate = self.mkt.valuation_date
        self._ois_curve   = self._build_ois_curve()
        self._jibar_curve = self._build_jibar_curve()
        self.ois_handle.linkTo(self._ois_curve)
        self.jibar_handle.linkTo(self._jibar_curve)
        return self

    def reprice_with_shock(
        self,
        bucket_tenors: Optional[List[str]] = None,
        bump_bps: float = 1.0,
    ) -> List["ZARCurveBuilder"]:
        """
        Return a list of shocked curve builders — one per bucket tenor.
        Used for key-rate DV01 (KRD) computation.
        Applies a localised ±bump_bps shift to each tenor's OIS quote.
        """
        tenors = bucket_tenors or self.KRD_BUCKETS
        shocked: List[ZARCurveBuilder] = []
        for t in tenors:
            if t not in self.mkt.ois_quotes:
                continue
            new_quotes = dict(self.mkt.ois_quotes)
            new_quotes[t] = new_quotes[t] + bump_bps / 10_000
            new_mkt = ZARONIAMarketData(
                valuation_date=self.mkt.valuation_date,
                overnight_rate=self.mkt.overnight_rate + bump_bps / 10_000
                if t == "ON" else self.mkt.overnight_rate,
                ois_quotes=new_quotes,
                jibar_quotes=dict(self.mkt.jibar_quotes),
            )
            shocked.append(ZARCurveBuilder(new_mkt, self.interp).build())
        return shocked

    def parallel_shift(self, bump_bps: float) -> "ZARCurveBuilder":
        """Shift all OIS quotes by bump_bps simultaneously."""
        b = bump_bps / 10_000
        new_quotes = {k: v + b for k, v in self.mkt.ois_quotes.items()}
        new_mkt = ZARONIAMarketData(
            valuation_date=self.mkt.valuation_date,
            overnight_rate=self.mkt.overnight_rate + b,
            ois_quotes=new_quotes,
            jibar_quotes={k: v + b for k, v in self.mkt.jibar_quotes.items()},
        )
        return ZARCurveBuilder(new_mkt, self.interp).build()

    def steepener_shift(
        self,
        short_end_bps: float = -5.0,
        long_end_bps: float = +5.0,
        pivot_tenor: str = "2Y",
    ) -> "ZARCurveBuilder":
        """Linear steepener / flattener centred at pivot_tenor."""
        pivot_date = _tenor_to_date(pivot_tenor, self.mkt.valuation_date)
        tod = self.mkt.valuation_date
        new_quotes: Dict[str, float] = {}
        for t, r in self.mkt.ois_quotes.items():
            tdate = _tenor_to_date(t, tod)
            frac = ZAR_DAY_COUNT.yearFraction(tod, tdate)
            pivot_frac = ZAR_DAY_COUNT.yearFraction(tod, pivot_date)
            alpha = (frac - pivot_frac) / max(pivot_frac, 1e-6)
            bump = short_end_bps / 10_000 + alpha * (long_end_bps - short_end_bps) / 10_000
            new_quotes[t] = r + bump
        new_mkt = ZARONIAMarketData(
            valuation_date=self.mkt.valuation_date,
            overnight_rate=self.mkt.overnight_rate + short_end_bps / 10_000,
            ois_quotes=new_quotes,
            jibar_quotes=dict(self.mkt.jibar_quotes),
        )
        return ZARCurveBuilder(new_mkt, self.interp).build()

    # ------------------------------------------------------------------
    # Discount factor / rate accessors
    # ------------------------------------------------------------------

    def discount(self, date_or_tenor: ql.Date | str) -> float:
        d = date_or_tenor if isinstance(date_or_tenor, ql.Date) else \
            _tenor_to_date(date_or_tenor, self.mkt.valuation_date)
        return self._ois_curve.discount(d)

    def zero_rate(self, date_or_tenor: ql.Date | str, compounding=ql.Continuous) -> float:
        d = date_or_tenor if isinstance(date_or_tenor, ql.Date) else \
            _tenor_to_date(date_or_tenor, self.mkt.valuation_date)
        return self._ois_curve.zeroRate(d, ZAR_DAY_COUNT, compounding).rate()

    def forward_rate(
        self,
        d1: ql.Date | str,
        d2: ql.Date | str,
        compounding=ql.Simple,
    ) -> float:
        def _d(x):
            return x if isinstance(x, ql.Date) else _tenor_to_date(x, self.mkt.valuation_date)
        return self._ois_curve.forwardRate(_d(d1), _d(d2), ZAR_DAY_COUNT, compounding).rate()

    def par_swap_rate(self, maturity_tenor: str) -> float:
        """Par rate of a ZARONIA OIS at given maturity (used for implied swap rate)."""
        end_date = _tenor_to_date(maturity_tenor, self.mkt.valuation_date)
        sched = ql.MakeSchedule(
            self.mkt.valuation_date,
            end_date,
            ql.Period("1Y"),
            calendar=ZAR_CALENDAR,
            convention=ZAR_BDC,
        )
        annuity = sum(
            ZAR_DAY_COUNT.yearFraction(sched[i], sched[i + 1])
            * self._ois_curve.discount(sched[i + 1])
            for i in range(len(sched) - 1)
        )
        if annuity == 0:
            return float("nan")
        return (1.0 - self._ois_curve.discount(end_date)) / annuity

    def curve_dataframe(self) -> pd.DataFrame:
        """Return a tidy DataFrame of the bootstrapped OIS curve."""
        tenors = [
            "1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y",
            "18M", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y", "12Y", "15Y", "20Y",
        ]
        tod = self.mkt.valuation_date
        rows = []
        for t in tenors:
            try:
                d = _tenor_to_date(t, tod)
                yf = ZAR_DAY_COUNT.yearFraction(tod, d)
                rows.append({
                    "tenor":        t,
                    "maturity":     d.to_date(),
                    "year_frac":    round(yf, 4),
                    "discount_factor": round(self._ois_curve.discount(d), 8),
                    "zero_rate_cc": round(self._ois_curve.zeroRate(d, ZAR_DAY_COUNT, ql.Continuous).rate() * 100, 4),
                    "zero_rate_a365": round(self._ois_curve.zeroRate(d, ZAR_DAY_COUNT, ql.Annual).rate() * 100, 4),
                    "fwd_rate_3m":  round(self.forward_rate(d, _add_period(d, "3M")) * 100, 4),
                })
            except Exception:
                continue
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_ois_curve(self) -> ql.PiecewiseLogLinearDiscount:
        tod = self.mkt.valuation_date
        helpers: List[ql.RateHelper] = []

        # Overnight deposit
        helpers.append(
            ql.DepositRateHelper(
                ql.QuoteHandle(ql.SimpleQuote(self.mkt.overnight_rate)),
                ql.Period("1D"),
                0,                   # settlement days
                ZAR_CALENDAR,
                ZAR_BDC,
                False,
                ZAR_DAY_COUNT,
            )
        )

        # OIS swaps
        for tenor_str, rate in self.mkt.ois_quotes.items():
            try:
                period = ql.Period(tenor_str)
                helpers.append(
                    ql.OISRateHelper(
                        IRS_SETTLE_LAG,
                        period,
                        ql.QuoteHandle(ql.SimpleQuote(rate)),
                        self.zaronia_index,
                        telescopicValueDates=False,
                    )
                )
            except Exception:
                continue

        curve = ql.PiecewiseLogLinearDiscount(tod, helpers, ZAR_DAY_COUNT)
        curve.enableExtrapolation()
        return curve

    def _build_jibar_curve(self) -> ql.PiecewiseFlatForward:
        """JIBAR projection curve bootstrapped from legacy swap quotes."""
        tod = self.mkt.valuation_date
        if not self.mkt.jibar_quotes:
            # flat forward at overnight level
            flat = ql.FlatForward(tod, self.mkt.overnight_rate, ZAR_DAY_COUNT)
            flat.enableExtrapolation()
            return flat  # type: ignore

        # 3M JIBAR index
        jibar3m = ql.IborIndex(
            "JIBAR3M", ql.Period("3M"), 2,
            ZAR_CURRENCY, ZAR_CALENDAR,
            ZAR_BDC, False, ZAR_DAY_COUNT,
            self.ois_handle,           # discount curve = OIS
        )
        helpers: List[ql.RateHelper] = []
        for tenor_str, rate in self.mkt.jibar_quotes.items():
            try:
                period = ql.Period(tenor_str)
                helpers.append(
                    ql.SwapRateHelper(
                        ql.QuoteHandle(ql.SimpleQuote(rate)),
                        period,
                        ZAR_CALENDAR,
                        ql.Annual,
                        ZAR_BDC,
                        ZAR_DAY_COUNT,
                        jibar3m,
                        ql.QuoteHandle(),
                        ql.Period("0D"),
                        self.ois_handle,   # exogenous discount
                    )
                )
            except Exception:
                continue
        if not helpers:
            flat = ql.FlatForward(tod, self.mkt.overnight_rate, ZAR_DAY_COUNT)
            flat.enableExtrapolation()
            return flat  # type: ignore
        curve = ql.PiecewiseFlatForward(tod, helpers, ZAR_DAY_COUNT)
        curve.enableExtrapolation()
        return curve


# ---------------------------------------------------------------------------
# Convenience factory functions
# ---------------------------------------------------------------------------

def build_zaronia_ois_curve(
    market_data: Optional[ZARONIAMarketData] = None,
) -> ZARCurveBuilder:
    """One-shot builder — returns a fully built ZARCurveBuilder."""
    return ZARCurveBuilder(market_data).build()


def build_jibar_swap_curve(
    market_data: Optional[ZARONIAMarketData] = None,
) -> ZARCurveBuilder:
    """Alias; both curves are built simultaneously in ZARCurveBuilder."""
    return build_zaronia_ois_curve(market_data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tenor_to_date(tenor: str, ref: ql.Date) -> ql.Date:
    """Advance ref date by a QL period string, respecting SA calendar."""
    p = ql.Period(tenor)
    d = ZAR_CALENDAR.advance(ref, p, ZAR_BDC)
    return d


def _add_period(date: ql.Date, tenor: str) -> ql.Date:
    return ZAR_CALENDAR.advance(date, ql.Period(tenor), ZAR_BDC)
