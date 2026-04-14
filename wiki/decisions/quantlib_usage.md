# Decision: Using QuantLib for All Pricing

> Why QuantLib rather than a bespoke Python pricer.

## Context

For a rates desk analytics system, pricing accuracy and convention correctness matter. Options were:
1. **Bespoke Python** — manual cash flow generation, discount factor interpolation, date arithmetic.
2. **QuantLib** — mature C++ library with Python bindings, covering all standard rates instruments.

## Decision

Use QuantLib 1.42 for all pricing. All instruments are QuantLib objects; dates, calendars, day counts, and schedule generation are handled by QuantLib primitives.

## Rationale

- **Convention correctness**: QuantLib's `SouthAfrica()` calendar, `Actual365Fixed()` day count, `ModifiedFollowing` business day convention are market-standard.
- **RelinkableHandle**: QuantLib's term structure handle pattern allows curve shocks without copying instruments — essential for efficient KRD computation.
- **OIS compounding**: `ql.OvernightIndex` and `ql.MakeOIS` implement daily compounded OIS correctly, including payment delays.
- **Maturity**: QuantLib has been in production at institutions since 2000. Edge cases (holiday calendars, stub periods, IMM dates) are handled.

## Trade-offs

- **Complexity**: QuantLib's API is large and non-Pythonic. Simple tasks (build an OIS swap) require 5–10 lines of boilerplate.
- **Opacity**: when something prices incorrectly, debugging QuantLib internals is hard.
- **Performance**: re-bootstrapping the curve for every KRD bump (~9 bumps × all instruments) is the dominant runtime cost. Currently ~50ms per bootstrap, acceptable.

## The `_npv_with_curve()` pattern

Since QuantLib instruments hold a reference to the curve handle (not the curve itself), re-linking the handle reprices everything. But this would mutate the base instrument. The workaround is `_npv_with_curve()` in `RiskEngine`, which constructs a temporary copy of the instrument bound to a new curve. This adds overhead but keeps the base instrument clean.

## See also

- [[modules/zaronia_curve]] — curve construction
- [[modules/risk_engine]] — `_npv_with_curve()` pattern
- [[concepts/ois_bootstrap]] — how QuantLib's bootstrapper works
