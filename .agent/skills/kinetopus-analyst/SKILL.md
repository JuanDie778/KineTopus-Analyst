---
name: kinetopus-analyst
description: >-
  Executes standardized White-Box Multi-Lens physical-quantitative asset analysis using the
  KineTopus-Analyst CLI (`kinetopus_pro`). Use this skill whenever the user asks to analyze a
  financial asset, ticker (crypto, stock, ETF, index, commodity, FX), or CSV time series with
  KineTopus, evaluate market inertia/regimes across context windows, extract SINDy differential
  equations, or forecast price trajectories.
---

# KineTopus-Analyst Standardized Multi-Lens Protocol (Hito 2)

Follow this strict 4-step protocol to analyze any asset or time series with **zero numerical hallucination**, combining Multi-Lens physics (`2000v` Background · `1000v` Confirmation · `500v` Timing), strict full-window Walk-Forward validation, tiered visual inspection, and high-impact two-part storytelling.

## Step 1: Run the Multi-Lens Headless CLI

By default, run a single daily (`1d`) Multi-Lens pass (`10y` base download with automatic `max` fallback when `10y` lacks full-window Walk-Forward span for `2000v`):

```powershell
& "C:\Users\ussaa\AppData\Local\Programs\Python\Python314\python.exe" -m kinetopus_pro.cli --ticker "<TICKER>" --interval 1d
```

* For a local CSV file: replace `--ticker` with `--csv "<PATH>"` (add `--classic-price --disable-norm` only for idealized classical physics datasets).
* Capture the JSON summary printed to stdout: `report_dir`, `confluence_json`, `confluence_png`, and `lenses` (`lens_2000`, `lens_1000`, `lens_500`).

## Step 2: Tiered Quantitative & Visual Inspection (Mandatory)

You MUST inspect both the telemetry JSONs and rendered PNGs using `read_file` **before** writing a single word of analysis:

### 2A. Quantitative Channel
1. Read `confluence.json` first:
   * Check `metadata.download` (`effective_period_used`, `fallback_to_max_triggered`, `total_downloaded_candles`).
   * Enforce the **Fixed Hierarchy without Promotions** (`hierarchy_verdict`):
     * `2000v` = **Tendencia de Fondo** (`MACRO_FONDO`). If `N/D` or if `seal_passed == false` (`EXOGENO_FUNDAMENTALISTA` or `INSUFICIENTE` with `< 5` effective full-window OOS cuts), the background trend MUST remain `INDETERMINADA` / `N/D` and global confidence CANNOT exceed `BAJA_CAUTELA`. The `1000v` lens NEVER replaces `2000v`.
     * `1000v` = **Confirmación de Medio Plazo** (`MEDIO_CONFIRMACION`).
     * `500v`  = **Timing Táctico** (`CORTO_TIMING`).
2. Read each available `lens_<W>/telemetry.json`:
   * Extract `calibration` (`effective_cusum_k`, `effective_smooth_tol`, `autopilot_rescue`), `white_box_physics` (`active_equations`, `active_r2_score`, `linear_stability_spectrum`), `reliability_seal` (`double_seal_summary`, `ljung_box_whiteness`, `mini_walk_forward_oos` with `effective_cuts`), `geometry_and_phase_space` (`quadrant`, `price_vs_spline_gap_pct`, `last_30c_mean_gap_pct`, reversals/inflections, `rotation_sense`), `cusum_forensics` (`window_max_tension_peak`, `invalidation_levels_1candle`, `macro_breaks`, `active_regime_top_anomalies`), and `forecast_cone.horizon_checkpoints`.

### 2B. Tiered Visual Channel & Per-Panel Checklist (Refuerzo D)
1. **Tier 1 (Always Mandatory):** Call `read_file` on `confluence.png` AND every available `lens_<W>/dashboard.png` (`2000`, `1000`, `500`).
2. **Tier 2 (On Ambiguity or Discrepancy):** Open individual high-res panels in `lens_<W>/panels/01..06.png` whenever an annotation looks crowded, a tactical turn is subtle, or a visual pattern appears to contradict the JSON numbers.
3. **Mandatory Per-Panel Checklist & Cross-Audit ("Lo que veo vs. Lo que dice el JSON"):**
   * **Confluence Chart (`confluence.png`):** Are the 3 splines (`2000v` sky-blue, `1000v` amber, `500v` emerald) fanning out in alignment, or is raw price breaking away from the slower curves in Panel 2 (`~220v` zoom)? Do the 3 velocity curves in Panel 3 cross `0` in sequence or diverge?
   * **Panels 1 & 2 (Macro Price + Tactical Zoom `120v + t+60`):** Is raw daily price sitting above or below the $C^2$ spline over the last 20–60 candles? Do recent swing highs/lows respect or threaten the dotted CUSUM invalidation lines? Is the Monte Carlo cone visibly skewed?
   * **Panels 3 & 4 ($\dot{r}$ and $\ddot{r}$):** Do the visual slopes and dated zero-crossing markers match the JSON `quadrant`? Is $\dot{r}$ approaching `0` (imminent turn) even while still positive/negative?
   * **Panel 5 (Phase-Space Attractor):** Do the directional arrows confirm clockwise/counter-clockwise flow and compression vs. centrifugal escape?
   * **Panel 6 (CUSUM Tension):** Did `window_max_tension_peak` brush near $H=5.0$ (a near-break stress test) even if `macro_breaks` is empty?
   * **Declare any discrepancy explicitly** in Part 2 (e.g., when a secular spline remains `ALCISTA` in JSON while raw candles in the Tactical Zoom show a multi-week pullback below the manifold).

## Step 3: CUSUM Event Forensics & Traditional Analyst Consensus (`search_web`)

1. **CUSUM Forensics & Upcoming Catalysts:** Search the web around key `active_regime_start_date`, `macro_breaks`, or `window_max_tension_peak` dates to explain what real-world shock caused them, and identify upcoming macro/earnings/liquidity catalysts that could breach the 1-candle CUSUM invalidation levels.
2. **Cited Web Analyst Consensus (Part 2 Contrast):** Search current market/technical analyst coverage on the web for `<TICKER>` (support/resistance levels, trend bias, flow narrative) **citing the sources explicitly**. Do NOT compute local classical indicators (`RSI`/`EMA`/`MACD`) in Python; contrast KineTopus strictly against cited external analyst consensus.

## Step 4: Two-Part High-Impact Deliverable (Artifact + Persistent `analysis.md`)

Read [report_template.md](./references/report_template.md) and follow its exact **Two-Part Structure**:

1. **Stage PNGs for Artifact Embedding:** Copy `confluence.png` and the available `lens_<W>/dashboard.png` files into `<Artifact Directory Path>` (e.g., `confluence_<TICKER>.png`, `dashboard_<TICKER>_2000v.png`, etc.) and embed them via their absolute artifact paths (using a `carousel` block in Part 2 of the Artifact for the 3 lens dashboards).
2. **Formatting Rules:** Escape every literal currency dollar sign in prose/tables as `\$` (e.g., `\$69,328.06`) so KaTeX never corrupts prose. Reserve `$...$` and `$$...$$` strictly for real mathematical expressions. Use internal direct tone without legal disclaimers for now.
3. **Write Both Copies:**
   * User-facing **Artifact** in `<Artifact Directory Path>` (`UserFacing=true`, `RequestFeedback=false`).
   * Self-contained archival copy at `<report_dir>/analysis.md` rewriting embedded image paths to `./confluence.png` and `./lens_<W>/dashboard.png`.
4. **Chat Response:** Keep the chat summary concise, pointing to the Artifact and `<report_dir>/analysis.md` with the 1-minute verdict and key levels.
