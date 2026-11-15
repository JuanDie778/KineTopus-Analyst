---
name: kinetopus-analyst
description: >-
  Executes standardized White-Box Multi-Lens physical-quantitative asset analysis using the
  KineTopus-Analyst CLI (`kinetopus_pro` v0.3.1). Use this skill whenever the user asks to analyze
  a financial asset, ticker (crypto, stock, ETF, index, commodity, FX), or CSV time series with
  KineTopus, evaluate market inertia/regimes across context windows, extract SINDy differential
  equations, or forecast price trajectories.
---

# KineTopus-Analyst Definitive Two-Stage Protocol (`v0.3.1` — Pure Geometric Mode)

Follow this strict **Two-Stage Zero-Hallucination Protocol** to analyze any asset or time series. The motor computes and injects **100% of prices, ranges, touch probabilities, curve-price fit (`R²`, `MAPE`), and telemetry figures** into both `report.html` (interactive offline deliverable) and `analysis.md` (archival Markdown + IDE Artifact); the agent only writes qualitative context in `narrative.json`.

## Stage 1: Quantitative Engine Execution (`--ticker` or `--csv`)

Run the Multi-Lens CLI (`10y` download with automatic `max` fallback when `10y < 2,690` candles; Walk-Forward OOS is off by default and optional via `--audit-oos`):

```powershell
& "C:\Users\ussaa\AppData\Local\Programs\Python\Python314\python.exe" -m kinetopus_pro.cli --ticker "<TICKER>" --interval 1d
```

* For a local CSV file: replace `--ticker` with `--csv "<PATH>"` (add `--classic-price --disable-norm` only for idealized classical physics datasets).
* Pass `--audit-oos` only when the user explicitly requests historical Walk-Forward OOS scoring.
* Capture the JSON summary printed to `stdout`: `report_dir`, `confluence_json`, `hero_png`, `report_html`, `analysis_md`, `narrative_template_json`, and `lenses` (`2000`, `1000`, `500`).
* Note: Stage 1 already produces a valid standalone `report.html` and `analysis.md` in `cuantitativo` mode even without AI intervention.

## Step 2: Mandatory Quantitative & Visual Audit + Web Research

Before writing `narrative.json`, inspect both telemetry JSONs and rendered PNGs via `read_file`:

### 2A. Quantitative & Geometric Rules (`v0.3.1`)
1. Read `<report_dir>/confluence.json` and `<report_dir>/lens_1000/telemetry.json` (plus `2000`/`500`):
   * **Simultaneous 3-Lens `t+150` Geometry (`v0.3.1`):**
     * **All 3 lenses (`2000v` Cian, `1000v` Ámbar, `500v` Violeta)** ALWAYS project `t+150` trajectories with calibrated single-integration EWMA cones and `P25/P75` quartiles. No Walk-Forward or SINDy `R²` cutoff ever blocks forecasts or emits `"Sin escenario predictivo validado hoy"`.
     * **`1000v` (Ámbar)** remains the primary anchor for executive horizon tables (`1s · 1m · 3m · t+150`) and P25/P75 scenarios, while **`2000v` (Cian)** gives long-cycle context and **`500v` (Violeta)** gives short-cycle geometry & tactical pins.
     * Prioritize **Curve-Price Fit (`R²`, `MAPE %`)** and **visual curve geometry** over SINDy `R²`; Autopilot 2D activates solely on numerical instability or `dr/dt = 0`.
     * **No 1-candle CUSUM barrier lines** in executive charts, right-hand ruler, scenarios, or executive tables—center narrative on the 3 curves, price-to-curve distance `%`, and `P25/P75` quartiles (historical CUSUM regime cuts stay in Lab Section 2.5 & Panels 1/6).
   * **5-State Human Taxonomy:** Always refer to states in human Spanish (`Impulso alcista`, `Alcista frenando`, `Lateral / Digestión` / `Lateral en máximos`, `Corrección bajista`, `Caída frenando / Suelo en formación` + modifier `sobreextendido` / `descolgado` / `cerca de su curva`), never raw `Q1–Q4` enums.

### 2B. Visual Audit
1. Call `read_file` on `<report_dir>/hero.png` AND all available `<report_dir>/lens_<W>/dashboard.png` (`2000`, `1000`, `500`). Open high-res `lens_<W>/panels/01..06_*.png` if any detail needs closer inspection.
2. Verify visual-quantitative parity:
   * **`hero.png`:** Candlesticks (~500v default view + `t+150`), all 3 curves + simultaneous `t+150` projections (`2000v` Cian, `1000v` Ámbar + cone, `500v` Violeta), zero horizontal 1-candle CUSUM lines, clean vertical historical CUSUM cuts (`"Nuevo régimen · YYYY-MM-DD"`), and de-overlapped right-hand Level Ruler (`Hoy`, `2000v t+150`, `1000v t+150`, `500v t+150`, `P75`, `P25`).
   * **`report.html`:** Full 100% history in `report_bundle.npz` with initial `500v + t+150` view, window buttons `[120v | 500v | 1000v | 2000v | Todo el historial]`, cone selector `[Cono: 1000v | 2000v | 500v | Sin cono]`, clean dynamic Y auto-scaling, and Tab 3 selector across all 3 technical dashboards.
   * **Dashboards (`2000v`, `1000v`, `500v`):** Check raw candles vs. spline in Panel 2 (`t+150` horizon, zero horizontal 1-candle CUSUM barriers), derivative zero-crossings in Panels 3 & 4, phase-space flow in Panel 5, and CUSUM history in Panel 6. Declare visual nuance in `visual_discrepancies`.

### 2C. Web Research (`search_web`)
1. **Historical CUSUM Catalysts (Tab 3 / Lab Section 2.5):** Identify real-world events behind historical `active_regime_start_date`, `macro_breaks`, or `window_max_tension_peak` dates for `cusum_catalysts`.
2. **Cited External Analyst Consensus:** Search current market/analyst consensus for `<TICKER>` with explicit URLs (`source_name`, `date`, `stance`, `url`). Never compute local `RSI`/`EMA`/`MACD` in Python as a substitute.

## Stage 2: Qualitative `narrative.json` & Deterministic Re-Render (`--render-report`)

Read [report_template.md](./references/report_template.md) and `<report_dir>/narrative_template.json`:

1. Write `<report_dir>/narrative.json` containing **qualitative Spanish text only** (`headline`, `scenarios_catalysts`, `top_insights` [3 items], `web_consensus` with cited `sources`, `visual_discrepancies`, `sindy_translation`, `cusum_catalysts`, `reading_limits`). Do NOT write manual numeric tables—the motor injects all numbers automatically.
2. Run Stage 2 to re-render `<report_dir>/report.html`, `<report_dir>/analysis.md`, and stage images (`hero` + 3 dashboards) + Markdown into `<Artifact Directory Path>`:

```powershell
& "C:\Users\ussaa\AppData\Local\Programs\Python\Python314\python.exe" -m kinetopus_pro.cli --render-report "<REPORT_DIR>" --artifact-dir "<ARTIFACT_DIR>" --artifact-slug "<SLUG>"
```

3. Register the staged Markdown file in `<Artifact Directory Path>` as a user-facing Artifact (`UserFacing=true`, `RequestFeedback=false`) or point the user directly to `<report_dir>/report.html` and the Artifact without re-summarizing all sections in chat. Escape any literal currency `$` in chat prose as `\$`.
