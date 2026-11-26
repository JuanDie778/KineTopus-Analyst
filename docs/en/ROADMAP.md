🌐 [Español](../ROADMAP_PRO.md) | **English**

# PRODUCT ROADMAP — KINETOPUS-ANALYST (`kinetopus_pro`)

> **Strategic North Star:** Every milestone in this roadmap is governed by [docs/en/MANIFESTO.md](MANIFESTO.md) (real utility as a technical indicator, simplicity & intuition, zero-friction usability, portability, and accessibility).

## Milestone 1: Headless Core, Standardized CLI & Reproducible Protocol
**Status:** ✅ COMPLETED (`v0.1.0`)
- Headless causal orchestrator (`kinetopus_pro/headless_pipeline.py`) with zero-leakage local normalization, Autopilot 2D, Double Seal (`Ljung-Box` + mini causal Walk-Forward OOS), kinematic geometry, and CUSUM forensics.
- Static 5-panel dark-mode renderer (`kinetopus_pro/static_renderer.py`).
- Installable CLI (`kinetopus-analyze` / `kinetopus_pro.cli`) and zero-hallucination numerical protocol validated on real `BTC-USD` (`R² = 0.9217`, `GLD Alert` detection at `40.0%` OOS hit rate).

---

## Milestone 2: Hierarchical Multi-Lens Engine, Visual Enhancements & 2-Part Reports
**Status:** ✅ COMPLETED (`v0.2.0`)
- **Multi-Lens Engine (`2000v / 1000v / 500v`):** Single smart fetch (`10y` with automatic `max` fallback), independent `CUSUMAutoTuner` calibration per scale in parallel (`ProcessPoolExecutor`), clean `"N/D"` degradation, and initial hierarchy.
- **Strict Double Seal (`v2.2`):** Full-window causal Walk-Forward OOS (`W` exact bars per cut), minimum `5` effective cuts, `SINDy R² >= 0.35` gate, and least-squares re-anchored manifold.
- **6-Panel Dashboards & 2-Part Storytelling:** Tactical zoom, dated crossings, 1-bar CUSUM borders, CUSUM peak markers, and cited market-consensus comparison.

---

## Milestone 2.5: Analysis Standard, Calibrated Cone & Interactive `report.html`
**Status:** ✅ COMPLETED (`v0.3.0`)
- **Single-Integration EWMA Cone & Human Taxonomy:** Log-price Monte Carlo cone with RiskMetrics EWMA volatility (`span=30`, $N=2,000$), non-blocking empirical OOS calibration metric (`cone_calibration`), `1000v`-centered hierarchy, and 5-state human taxonomy. *(Note: OOS/`R²` locks and `500v` `t+150` suppression from `v0.3.0` were superseded in `v0.3.1`.)*
- **Two-Stage Dual Presentation (`report.html` + `analysis.md`):** Self-contained offline interactive deliverable (`plotly.min.js` + Jinja2, Dark/Light theme, 3 structured tabs) and `--render-report` deterministic numeric injection.

---

## Milestone 2.6: Pure-Geometric Approach & Simultaneous 3-Lens `t+150` Projections
**Status:** ✅ COMPLETED (`v0.3.1`)
- **Opt-In Walk-Forward OOS (`--audit-oos`) & Zero Predictive Locks:** Walk-Forward disabled by default (`audit_oos=False`); eliminated `"Sin escenario predictivo validado hoy"` locks and `SINDy R² < 0.35` discards. *Autopilot 2D* acts strictly upon numerical instability or `dr/dt = 0` collapse.
- **Simultaneous `t+150` Across All 3 Lenses & Curve-Price Fit:** `2000v` (Cyan), `1000v` (Amber, primary `P25/P75` scenario axis), and `500v` (Violet) all project `t+150` simultaneously while reporting explicit `curve_price_fit` (`window_price_r2`, `mape_pct`, `rmse_price`).
- **100% History in `report_bundle.npz` & Interactive Selectors:** Persists the entire downloaded series (`h_start=0`), default `500v + t+150` zoom, `[120v | 500v | 1000v | 2000v | Full history]` buttons, `[Cone: 1000v | 2000v | 500v | None]` selector, clean Y auto-scaling, and **3-dashboard switcher** in Tab 3.
- **Geometric Cleanup Without 1-Bar CUSUM Barriers:** Removed intraday dashed barriers (`up_brk` / `dn_brk`) from `hero.png`, Panels 1–2, right price ruler, and scenarios while keeping complete historical CUSUM forensics in Panel 6 and Section 2.5.

---

## Milestone 3: Multi-Asset & Multi-Series Scanner (`v0.5.0`)
**Status:** 📋 PLANNED (Next Frontier)
- **Practical Radar & Cross-Sectional Sweep Engine:** Support mixed batches of *Yahoo Finance* tickers (Equities, ETFs, Indices, FX, Crypto) and local CSV files (including coupled non-financial `(X, Y)` pairs under `--classic-price` that may contain zeros or negative values).
- **Deterministic Master Table (`JSON` / `CSV`) & Executive Synthesis:** Aggregate across every scanned series the 3-lens human state (`2000v / 1000v / 500v`), curve-price stretch `%`, Curve-to-Price fit (`R²`, `MAPE`), simultaneous `t+150` projections, SINDy archetype/eigenvalues + orbital rotation direction, and historical CUSUM peak/break timestamps (including OOS coverage when `--audit-oos` is enabled), hooking cleanly into the `hito3_scanner_attached` service endpoint prepared in Milestone 4.

---

## Milestone 4: Service Packaging, API, Portable Indicator & Active Alerts
**Status:** ✅ COMPLETED (`v0.4.0`)
- **Direct Consumption (Analysts & Public):** Lightweight Web Portal (`GET /` on `kinetopus-serve`, Dark/Light), self-contained `report.html` deliverables, and `stdio` MCP server (`kinetopus-mcp`) for AI agents.
- **B2B Integration (*TradingView* / *Investing.com* / Fintechs):** Compact `indicator_feed.json` (`kinetopus.indicator.v1`, `~5–12 KB`), `< 35 KB` pure-SVG embeddable `widget.html` for `<iframe>`, **TradingView Pine Script v5** overlay (`indicator.pine`), and `FastAPI` endpoints serialized with `threading.Lock` ($\le 16\text{ GB}$ RAM).
- **Active Alerts (`alerts.py`):** 6 deterministic physical-geometric rules over `confluence.json`, SHA-256 deduplication ledger (`reports/.alerts_ledger.json`), and optional outgoing HTTP POST JSON webhooks (`--webhook-url`).
