# Changelog

All notable changes to **KineTopus-Analyst (`kinetopus_pro`)** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.0] - 2026-11-15

### Added
- **Portable B2B Indicator Contract (`kinetopus_pro/indicator_export.py`):** Exports `indicator_feed.json` (`schema_version = "kinetopus.indicator.v1"`, ~5–12 KB) containing all 3 geometric lenses, `t+150` projections, `P25/P75` first-passage scenarios, tactical `500v` pins, and downsampled curve telemetry.
- **Standalone Vector Widget (`templates/widget.html.j2`):** Generates `widget.html` (`< 35 KB` pure SVG, zero Plotly runtime overhead, Dark/Light toggle via `?theme=light|dark`, clean CUSUM cuts, collision-free right-margin price ruler) ready for `<iframe>` embedding.
- **TradingView Pine Script v5 (`indicator.pine`):** Exports a ready-to-paste `overlay=true` Pine Script indicator plotting `2000v/1000v/500v` curves, `t+150` extensions, `P25–P75` corridor, and an inline HUD table.
- **Active Alert Engine (`kinetopus_pro/alerts.py`):** Evaluates 6 deterministic physical-geometric rules (`CUSUM_CRITICAL_TENSION`, `RECENT_CUSUM_BREAK`, `TACTICAL_500V_PIN`, `MULTI_LENS_DIVERGENCE`, `CURVE_EXTREME_STRETCH`, `REGIME_STATE_TRANSITION`), deduplicates SHA-256 alert fingerprints in `reports/.alerts_ledger.json`, and supports optional HTTP POST JSON webhooks (`--webhook-url`).
- **FastAPI Micro-Service & Lightweight Web Portal (`kinetopus_pro/service.py`, `templates/portal.html.j2`):** Exposes `kinetopus-serve` with interactive web UI (`GET /`), `/api/v1/health`, `/api/v1/tickers`, `POST /api/v1/analyze` (serialized via `threading.Lock` for 16 GB RAM safety), `/api/v1/indicator/{ticker}`, `/api/v1/pine/{ticker}`, `/api/v1/alerts`, `/reports/{ticker}/widget`, and `/reports/{ticker}/latest`.
- **MCP `stdio` Server (`kinetopus_pro/mcp_server.py`):** Exposes `kinetopus-mcp` (`FastMCP`) with `list_analyzed_assets`, `get_asset_indicator`, `get_asset_alerts`, and `get_tradingview_pine`.
- **CLI & Packaging:** Added `--export-portable` and `--webhook-url` flags to `kinetopus-analyze`; registered `kinetopus-serve` and `kinetopus-mcp` console scripts; added PEP 562 lazy loading in `__init__.py` and `cli.py` for `< 10 s` Stage-2 cold-start rendering.

### Fixed
- **Finite ODE Exponential Blow-Up Guard (`headless_pipeline.py`):** Added `_is_projection_numerically_divergent` to catch finite IEEE-754 exponential blow-ups (`> 10x` or `< 1e-4x` spot) triggered by positive SINDy eigenvalues, routing them through Autopilot 2D rescue and inertial kinematic fallback before rendering.
- **`KineTopus 2.0-Core` Parity (`headless_pipeline.py`):** Delegated `_run_fast_cusum_autotune` directly to upstream `CUSUMAutoTuner` (in-process FFT for `n_features <= 4` and BIC-pruned `R2_BIC_dr` scoring) for bit-exact parity.

---

## [0.3.1] - 2026-11-15

### Changed
- **Pure-Geometric 3-Lens Architecture:** Removed predictive locks (`"Sin escenario predictivo validado hoy"`) and `SINDy R²` / OOS vetoes; `2000v` (Cyan), `1000v` (Amber), and `500v` (Violet) now always project `t+150` simultaneously.
- **Optional Walk-Forward OOS (`--audit-oos`):** Walk-Forward validation is now opt-in (`audit_oos=False` by default), while `Ljung-Box` residual diagnostics and explicit `curve_price_fit` (`window_price_r2`, `mape_pct`, `rmse_price`) remain computed on every run.
- **Calibrated Single-Integration EWMA Cone:** RiskMetrics `span=30` winsorized log-price Monte Carlo cone (`N=2,000`, `np.float64` `C_CONTIGUOUS`) eliminating double-integration noise distortion.
- **Visual Cleanup & Full-History Interactive Reports:** Removed 1-bar CUSUM horizontal barriers from `hero.png` and Panels 1–2 (preserving full CUSUM forensics in Panel 6 and Section 2.5); persisted 100% downloaded history in `report_bundle.npz`; upgraded `report.html` with window selectors (`120v` to full history), cone selector, and 3-lens dashboard switcher.

---

## [0.3.0] - 2026-11-14

### Added
- Initial EWMA single-integration Monte Carlo cone with empirical OOS calibration check (`cone_calibration`).
- Human-readable 5-state regime taxonomy (`Impulso alcista`, `Alcista frenando`, `Lateral / Digestión`, `Corrección bajista`, `Caída frenando / Suelo en formación`) and curve-proximity modifiers.
- Dual-stage offline presentation pipeline (`report.html` powered by embedded `plotly.min.js` + `analysis.md` + `narrative_template.json` / `--render-report`).

---

## [0.2.0] - 2026-11-14

### Added
- Parallel Multi-Lens Orchestrator (`2000v / 1000v / 500v`) over a single smart OHLCV fetch (`10y` with automatic `max` fallback) via `ProcessPoolExecutor`.
- Upgraded static renderer from 5 panels to **6-panel technical dashboards** per scale plus individual panel exports and multi-lens Hero chart (`hero.png` / `confluence.png`).
- Strict full-window causal Walk-Forward OOS seal (`len(p_train) == W`, minimum 5 effective cuts).

---

## [0.1.0] - 2026-11-14

### Added
- Initial Open-Core separation via `kinetopus_pro/engine_bridge.py` keeping upstream `kinetopus-engine` untouched.
- Headless causal pipeline (`headless_pipeline.py`), Autopilot 2D numerical stability rescue, and `Ljung-Box` + Walk-Forward OOS diagnostics.
- Standardized CLI (`kinetopus-analyze`) and static 5-panel dark-mode renderer.
