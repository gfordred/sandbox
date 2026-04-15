# Wiki Log

Append-only. Newest entries at the top.

---

## [2026-04-15] lint | First health check

- Issues fixed:
  - `[[modules/ois_swap]]` summary and body falsely claimed `carry_and_roll()` — corrected; method does not exist on `ZARONIAOISSwap`
  - `[[concepts/carry_roll]]` said OIS swaps "return 0" — corrected; they are silently excluded via `hasattr` guard
  - `[[overview]]` had 0 inbound content-page links (orphan) — added link from `[[modules/zaronia_curve]]` See also
- Issues flagged: none requiring human review
- `raw/.gitkeep` added so empty staging directory is tracked in git

## [2026-04-14] init | Wiki bootstrapped from live codebase

- Created wiki structure: `wiki/`, `raw/`, `tools/`
- Created schema: `CLAUDE.md`
- Initial pages written from direct code reading (no raw sources — codebase is the source):
  - [[overview]]
  - [[modules/graphify]], [[modules/zaronia_curve]], [[modules/risk_engine]]
  - [[modules/hedge_optimizer]], [[modules/ois_swap]], [[modules/vanilla_irs]]
  - [[concepts/zaronia]], [[concepts/ois_bootstrap]], [[concepts/dv01_krd]]
  - [[concepts/carry_roll]], [[concepts/scenario_analysis]]
  - [[decisions/graphify_design]], [[decisions/quantlib_usage]]
- Search tool created: `tools/search.py`
