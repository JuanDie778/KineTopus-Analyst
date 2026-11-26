🌐 [Español](../ARCHITECTURE_PRO.md) | **English**

# OPEN-CORE ARCHITECTURE — KINETOPUS-ANALYST (`v0.4.0` · Pure Geometry + Portable B2B Service)

## 1. Decoupling Boundary (`engine_bridge.py`)
`KineTopus-Analyst` (`kinetopus_pro`) consumes the open-source scientific core [`kinetopus-engine`](https://github.com/JuanDie778/KineTopus-Engine) (`Apache-2.0`) exclusively through `kinetopus_pro/engine_bridge.py`, keeping the upstream codebase 100% untouched:

- **Upstream Scientific Dependencies (`kinetopus-engine`):**
  - `src.ui.market_loader.MarketLoader`
  - `src.quant_engine.sensor.SpectralAnalyzer`
  - `src.quant_engine.blender.ContinuousBlender`
  - `src.quant_engine.nervous.RegimeShiftDetector`
  - `src.quant_engine.physics.PhysicsDiscoverer`
  - `src.quant_engine.symbolic.SymbolicTranslator`
  - `src.quant_engine.auto_tuner.CUSUMAutoTuner`
- **Namespace Isolation & Clean `stdout`:** `kinetopus_pro/` imports `kinetopus-engine` as an external dependency (via `pip install` or resolving `KINETOPUS_ENGINE_DIR` / sibling `../KineTopus-Engine` clone) with zero collision against `src/`. Upstream diagnostic prints are redirected to `stderr` so CLI `stdout` remains pure JSON.

---

## 2. Pure-Geometric Multi-Lens Engine `v0.3.1` (`kinetopus_pro.multi_lens`)
By default (`kinetopus-analyze --ticker <SYM>`), `KinetopusMultiLensRunner` evaluates three simultaneous scales over a **single smart OHLCV fetch** (`10y` with automatic fallback to `max` when `< 2,690` bars or when `--audit-oos` needs extra history), preserving full OHLC (`np.float64` `C_CONTIGUOUS`) for candlestick rendering:

1. **Simultaneous `t+150` Projection Across All 3 Lenses (`ranges_by_lens` & `curves_comparison`):**
   - **`1000v` (`PRINCIPAL_PREDICTIVA` · Amber):** Primary axis for executive ranges (`1w · 1m · 3m · t+150`), default visible Monte Carlo cone, and `P25/P75` scenarios (only yields to `500v` on young assets with `< 1,000` bars).
   - **`2000v` (`CONTEXTO_FONDO` · Cyan):** Structural long-horizon tide with its own `t+150` curve, calibrated EWMA cone, and Curve-to-Price fit metrics.
   - **`500v` (`SENSOR_ALERTA` · Violet):** Short-term tactical pulse emitting recent CUSUM break pins ($\le 120\text{ bars}$), velocity zero-crossings ($\dot{r}=0 \le 50\text{ bars}$), and tension metrics, **also projecting its own `t+150` trajectory and cone**.
2. **Zero Predictive Vetoes or OOS Locks:**
   - Removed `"Sin escenario predictivo validado hoy"` locks and automatic discards triggered by `SINDy R²` or OOS thresholds; all 3 lenses always project simultaneously whenever sufficient window history exists.
   - **Global Physical Confidence** (`ALTA` / `MEDIA` / `BAJA`) transparently weights Curve-to-Price fit (`R²`, `MAPE`), directional harmony across all 3 lenses, current CUSUM tension, kinematic fallback activation, and (only when `--audit-oos` is enabled) retrospective Walk-Forward results.

---

## 3. Calibrated EWMA Cone, Curve-Price Fit, Human Taxonomy & Opt-In OOS (`kinetopus_pro.headless_pipeline`)
Each lens executes causally (*zero look-ahead*) up to `horizon_steps = 150`:

1. **Calibrated Single-Integration Log-Price Cone (`_simulate_calibrated_single_integration_cone`):**
   - Applies i.i.d. normal shocks once on log-price increments (eliminating double-integration noise inflation) scaled by RiskMetrics EWMA volatility (`span=30`, winsorized at $\pm 3.5\text{ MAD-sigma}$) around the deterministic drift $F(t)$ ($\text{median} \equiv F(t)$, width $\propto \sigma_{\text{ewma}}\sqrt{k}$, $N=2,000$ `np.float64` `C_CONTIGUOUS` paths).
2. **Curve-to-Price Fit & Guaranteed Projection (`_compute_curve_price_fit`, `_ensure_geometric_projection`):**
   - Computes `window_price_r2`, `active_regime_price_r2`, `mape_pct`, `rmse_price`, and `fit_quality_label` over the least-squares re-anchored log-price manifold.
   - *Autopilot 2D* intervenes **only** upon numerical instability or `dr/dt = 0` collapse (never due to `SINDy R² < 0.35`), backed by inertial kinematic damping so `t+150` is always finite.
3. **Opt-In Walk-Forward OOS (`--audit-oos`) & `Ljung-Box`:**
   - `Ljung-Box` residual diagnostics run on every lens.
   - Walk-Forward OOS is **disabled by default** (`audit_oos=False`, `wf_cuts=0`). Passing `--audit-oos` or `--wf-cuts > 0` runs strict full-window validation (`len(p_train) == W`, minimum `5` effective cuts) plus empirical cone coverage (`cone_calibration`: `P25–P75` target ~50%, `P5–P95` target ~90%).
4. **5-State Human Taxonomy & `P25/P75` First-Passage Scenarios:**
   - Classifies each lens into 5 plain-language states (`Impulso alcista`, `Alcista frenando`, `Lateral / Digestión` [`Lateral en máximos` when trading $\ge 95\%$ of window high], `Corrección bajista`, `Caída frenando / Suelo en formación`) + curve-proximity modifier (`sobreextendido`, `descolgado`, `cerca de su curva`).
   - Three probabilistic scenarios (*Central*, *Bullish Expansion*, *Bearish Reversion*) are derived directly from `1000v` geometry and `P25/P75` quantiles, eliminating noisy 1-bar CUSUM barrier lines from executive views.

---

## 4. Visual Clarity, Full-History Persistence & Two-Stage Reports (`static_renderer.py` + `report_builder.py`)
1. **Hero Chart (`hero.png`) & 6-Panel Technical Dashboards (`static_renderer.py`):**
   - `hero.png` renders a clean **1-panel** default view (~`500v + t+150`) with OHLC candlesticks (or close line), all **3 simultaneous curves and `t+150` projections** (`2000v` Cyan, `1000v` Amber + cone, `500v` Violet), clean regime dividers (`"Nuevo régimen · YYYY-MM-DD"`), tactical `500v` pins, zero 1-bar CUSUM lines, and a collision-free right price ruler.
   - Also exports **3 six-panel technical dashboards** (`2000v / 1000v / 500v`) and **18 individual panels** (keeping full historical CUSUM forensics in Panel 6 and Section 2.5).
2. **100% Offline Interactive History & Two-Stage Pipeline (`report_builder.py` + `templates/report.html.j2`):**
   - **Stage 1 (`--ticker` / `--csv`):** Persists `report_bundle.npz` with **100% of downloaded history** (`h_start=0`) plus all 3 trajectories and cones, emits `narrative_template.json`, and builds self-contained offline `report.html` (`plotly.min.js` + Jinja2, `[120v | 500v | 1000v | 2000v | Full history]` buttons, cone selector, Dark/Light toggle, 3-dashboard switcher) alongside `analysis.md`.
   - **Stage 2 (`--render-report <DIR>`):** Merges qualitative narrative from `narrative.json` over 100% engine-computed figures in `< 0.5 s`, refreshing `report.html`, `analysis.md`, `indicator_feed.json`, `widget.html`, `indicator.pine`, and `alerts.json`.

---

## 5. B2B Service Layer, Portable Indicator & Active Alerts (`v0.4.0` — Milestone 4)
1. **Portable B2B Exporter & `< 35 KB` SVG Widget (`kinetopus_pro/indicator_export.py` + `templates/widget.html.j2`):**
   - `indicator_feed.json` (`schema_version = "kinetopus.indicator.v1"`, `~5–12 KB`): compact JSON contract carrying all 3 lenses, `P25/P75` scenarios, tactical `500v` pins, and downsampled series (`120v` tail + `t+150` sampled every 5 bars).
   - `widget.html` (`< 35 KB`, zero `plotly.min.js`): pure vector SVG chart with Dark/Light mode (`?theme=light|dark`), clean CUSUM cuts, `P25–P75` cone, and collision-free labels ready for `<iframe>` embedding.
   - `indicator.pine`: **TradingView Pine Script v5** (`overlay=true`) plotting active `2000v/1000v/500v` curves, `t+150` projections, `P25–P75` corridor, and an inline HUD `table.new`.
2. **Active Alert Engine & Deduplication (`kinetopus_pro/alerts.py`):**
   - Evaluates 6 deterministic rules (`CUSUM_CRITICAL_TENSION`, `RECENT_CUSUM_BREAK`, `TACTICAL_500V_PIN`, `MULTI_LENS_DIVERGENCE`, `CURVE_EXTREME_STRETCH`, `REGIME_STATE_TRANSITION`), deduplicates SHA-256 fingerprints in `reports/.alerts_ledger.json`, and optionally dispatches HTTP POST JSON webhooks (`--webhook-url`, stdlib `urllib.request`).
3. **HTTP Micro-Service (`FastAPI` + Web Portal) & MCP Server (`service.py`, `mcp_server.py`):**
   - `kinetopus-serve`: exposes `GET /` (`templates/portal.html.j2`), `/api/v1/health` (with `hito3_scanner_attached` hook), `/api/v1/tickers`, `POST /api/v1/analyze` (serialized under `threading.Lock` for $\le 16\text{ GB}$ RAM safety), `/api/v1/indicator/{ticker}`, `/api/v1/pine/{ticker}`, `/api/v1/alerts`, `/reports/{ticker}/widget`, and `/reports/{ticker}/latest`.
   - `kinetopus-mcp`: `stdio` MCP server (`FastMCP`) exposing `list_analyzed_assets`, `get_asset_indicator`, `get_asset_alerts`, and `get_tradingview_pine`.
