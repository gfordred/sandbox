# Concept: ZARONIA

> ZARONIA (Rand Overnight Index Average) is the South African risk-free overnight rate, analogous to SOFR (USD), SONIA (GBP), and €STR (EUR).

## What it is

ZARONIA measures the rate at which banks lend unsecured funds to each other overnight in the South African interbank market, weighted by transaction volume. It is published by the South African Reserve Bank (SARB) each business day and is the primary risk-free rate (RFR) for the ZAR market.

## Market conventions

| Convention | Value |
|------------|-------|
| Fixing | SARB, daily |
| Settlement | T+0 (same day) |
| Day count | Actual/365 Fixed |
| Compounding | Daily (for OIS) |
| Calendar | South Africa (`ql.SouthAfrica()`) |

## Role in the system

ZARONIA is the floating rate index for all instruments in this codebase:

- **OIS swaps**: pay/receive a compounded ZARONIA rate vs a fixed rate
- **Vanilla IRS**: float leg references ZARONIA as the projection index
- **Discount curve**: the bootstrapped ZARONIA OIS curve is used for discounting all ZAR cash flows

Current overnight rate (April 2026): **7.50%**

## Analogy to global RFRs

| Currency | RFR | Published by |
|----------|-----|-------------|
| ZAR | ZARONIA | SARB |
| USD | SOFR | NY Fed |
| GBP | SONIA | Bank of England |
| EUR | €STR | ECB |
| CHF | SARON | SIX |

## Implementation

```python
class ZARONIAIndex(ql.OvernightIndex):
    def __init__(self, ts_handle=None):
        super().__init__(
            "ZARONIA", 0, ZAR_CURRENCY,
            ZAR_CALENDAR, ZAR_DAY_COUNT,
            ts_handle or ql.YieldTermStructureHandle(),
        )
```

The index is constructed with settlement days = 0 (T+0). It is passed to OIS swap helpers and to the curve bootstrap as the floating index.

## See also

- [[modules/zaronia_curve]] — bootstraps the ZARONIA OIS discount curve
- [[modules/ois_swap]] — ZARONIA OIS swap pricer
- [[concepts/ois_bootstrap]] — how the curve is constructed from ZARONIA quotes
