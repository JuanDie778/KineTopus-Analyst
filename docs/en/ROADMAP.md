🌐 [Español](../ROADMAP_PRO.md) | **English**

# PRODUCT ROADMAP — KINETOPUS-ANALYST (`kinetopus_pro`)

> **Strategic North Star:** Every milestone in this roadmap follows [docs/en/MANIFESTO.md](MANIFESTO.md): turning **2D Phase-Space Attractor** physics and causal regime detection into a practical risk-navigation and diagnostic instrument.

---

## Milestone 1: Headless Core, Standardized CLI & Reproducible Protocol
**Status:** ✅ COMPLETED (`v0.1.0`)
- Headless causal orchestrator (`kinetopus_pro/headless_pipeline.py`) with zero-leakage local normalization, *Autopilot 2D*, Double Seal (`Ljung-Box` + causal Walk-Forward OOS), kinematic geometry, and CUSUM forensics.
- Static dark-mode renderer (`kinetopus_pro/static_renderer.py`) and installable CLI (`kinetopus-analyze`).

---

## Milestone 2: Multi-Lens Engine, Calibrated EWMA Cone & Pure Geometry
**Status:** ✅ COMPLETED (`v0.2.0` → `v0.3.1`)
- **Multi-Lens (`2000v / 1000v / 500v`):** Single smart OHLCV fetch (`10y` with automatic `max` fallback), parallel `CUSUMAutoTuner` calibration (`ProcessPoolExecutor`), explicit Curve-to-Price fit (`R²`, `MAPE`), single-integration EWMA Monte Carlo cone (`span=30`), opt-in Walk-Forward OOS audit (`--audit-oos`), 6-panel dashboards (including 2D Return-Volume phase space & orbital rotation in Panel 5), and two-stage offline `report.html`.

---

## Milestone 4: Service Packaging, API, Portable B2B Suite & Active Alerts
**Status:** ✅ COMPLETED (`v0.4.0`)
- **Direct Consumption:** Lightweight Web Portal (`GET /` on `kinetopus-serve`), self-contained `report.html`, and `stdio` MCP server (`kinetopus-mcp`).
- **Portable B2B Suite:** Compact `indicator_feed.json` (`kinetopus.indicator.v1`), `< 35 KB` pure-SVG `widget.html`, **TradingView Pine Script v5** overlay (`indicator.pine`), and 6 deterministic alert rules deduplicated via SHA-256 ledger with webhook dispatch (`--webhook-url`).
- **Hardening & `2.0-Core` Parity:** Finite ODE exponential blow-up guard, exact `CUSUMAutoTuner` parity (`KineTopus 2.0-Core`), and `pandas 3.0` CoW / Linux CI green (`22/22` tests passing).

---

## Milestone 3: 2D Phase-Space Microscope & Multi-Asset Scanner (`v0.5.0`)
**Status:** 📋 PLANNED (Next Frontier — Guided by Gran Estudio v3 Findings)

With `v0.4.0` infrastructure complete and the empirical conclusions of **Gran Estudio v3 (`26,294` causal snapshots, `2000–2026`)**, the next release promotes the 2D Phase-Space Microscope to the center of the user-facing product:

1. **Front-and-Center 2D Phase-Space Attractor Microscope (`CLI`, `Widget`, `Feed` & `Portal`):**
   - Elevate the 2D phase plane (`Vz` vs. smoothed return) from Panel 5 into the primary hero output and embeddable widget.
   - Surface the validated study metrics directly: **angular momentum & counterclockwise % (`Lz`)**, **Fitzgibbon conic classification** (closed ellipse vs. open escape hyperbola), **Lyapunov seismograph (`Re(λ)` in `d⁻¹`, `+0.010 d⁻¹` alert threshold)**, and **50% risk-modulation indicator**.
   - Bound forward path visuals to honest local spline curvature horizons rather than showcasing speculative 150-bar extrapolations as the primary centerpiece.
2. **Multi-Asset & Multi-Series Scanner (`JSON` / `CSV`):**
   - Batch sweeps across mixed *Yahoo Finance* tickers (Equities, ETFs, Indices, FX, Crypto) and local CSV files (including coupled non-financial `(X, Y)` dynamical systems with zeros or negative values under `--classic-price`).
   - Deterministic `JSON` / `CSV` master table consolidating 2D attractor state (`Lz`, Fitzgibbon, `Re(λ)`), CUSUM tension/breaks, and multi-scale fit, wired cleanly into `service.py` (`hito3_scanner_attached`).
