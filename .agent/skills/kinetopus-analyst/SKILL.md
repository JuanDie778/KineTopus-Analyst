---
name: kinetopus-analyst
description: >-
  Executes standardized White-Box physical-quantitative asset analysis using the
  KineTopus-Pro CLI. Use this skill whenever the user asks to analyze a financial
  asset, ticker (crypto, stock, ETF, index, commodity, FX), or CSV time series with
  KineTopus, evaluate market inertia/regimes, extract SINDy differential equations,
  or forecast price trajectories.
---

# KineTopus-Pro Standardized Quantitative Analysis Protocol

Follow this strict 4-step protocol to analyze any asset or time series with **zero numerical hallucination**, combining deterministic/stochastic physics (`SINDy` + `CUSUM` + `Euler-Maruyama`) via `kinetopus-engine` with real-world macro/event forensics.

## Step 1: Run the Headless Engine CLI

By default, run a **single timeframe (`1d` / `5y`)** matching the production reference. Run additional timeframes (`1wk`, `1h`) **only** if the user explicitly requests them.

```powershell
& "C:\Users\ussaa\AppData\Local\Programs\Python\Python314\python.exe" -m kinetopus_pro.cli --ticker "<TICKER>" --period 5y --interval 1d
```

*(Alternatively, inside the `KineTopus-Pro` repo root you can run `scripts/kinetopus_analyze.py` with the same flags.)*

* For a local CSV file: replace `--ticker` with `--csv "<PATH>"` (add `--classic-price --disable-norm` only for idealized classical physics datasets).
* Capture the JSON summary printed to stdout, specifically `report_dir`, `telemetry_json`, and `dashboard_png`.

## Step 2: Dual-Channel Inspection (Mandatory)

You MUST inspect **both** outputs using `read_file` before writing a single word of analysis:

1. **Quantitative Channel (`telemetry.json`):**
   * `calibration`: Check `effective_cusum_k`, `effective_smooth_tol`, and whether `autopilot_rescue.applied` was triggered.
   * `executive_kpis` & `reliability_seal`: Check `overall_physical_confidence`, `ljung_box_whiteness.verdict`, and `mini_walk_forward_oos` (`asset_physics_class` and `consensus_hit_ratio_pct`).
     * If `asset_physics_class == "EXOGENO_FUNDAMENTALISTA"` (<50% OOS HR), issue an explicit **"Alerta Caso GLD"** warning that exogenous/macro shocks override $(r, V)$ inertia.
   * `white_box_physics`: Read the exact `active_equations` ($\mathrm{d}r/\mathrm{d}t$ and $\mathrm{d}V/\mathrm{d}t$), `active_r2_score`, `residual_sigma_r`, and `analytical_sympy_solution`. Translate each non-zero coefficient physically (e.g., positive $r$ = self-reinforcing momentum; negative $r$ = mean-reverting friction; $V$ coupling = volume propulsion vs. absorption drag).
   * `geometry_and_phase_space`: Read `kinematics.quadrant` ($\dot{r}$ vs. $\ddot{r}$), `recent_velocity_reversals`, `recent_acceleration_inflections`, and `phase_space.topology_class`.
   * `cusum_forensics` & `forecast_cone`: Read `active_regime_start_date`, `macro_breaks`, `active_regime_top_anomalies`, `invalidation_levels_1candle`, and `horizon_checkpoints` ($t+1, t+5, t+15, t+30, t+60, t+150$).
2. **Visual Channel (`dashboard.png`):**
   * Call `read_file` on `dashboard.png` to visually verify all 5 panels: spline fit fidelity vs. raw price scatter, cone spread/curvature, derivative zero-crossings, phase-space orbit vs. projected attractor, and CUSUM tension spikes.

## Step 3: CUSUM Event Forensics & Catalyst Radar (`search_web`)

Honor Principle #2 (*"Mathematics models the rule; AI explains the anomaly"*):

1. **Origin of the Active Regime:** Search the web (`search_web`) around `cusum_forensics.active_regime_start_date` (and the most extreme dates in `active_regime_top_anomalies` or the latest `macro_breaks`) for `<TICKER>` + macro news to identify **what real-world event birthed the current physical regime**.
2. **Upcoming Catalyst Radar:** Search current news/macro calendar for `<TICKER>` (central bank decisions, CPI/jobs data, earnings, regulatory rulings, ETF/liquidity flows) that could push price past `invalidation_levels_1candle` (`upside_regime_break_price` / `downside_regime_break_price`) and break the $H=5.0$ CUSUM boundary.

## Step 4: Dual Deliverable (Artifact + Persistent Audit Log)

Read [report_template.md](./references/report_template.md) and follow its structure strictly:

1. **Stage the PNG for Artifact Embedding:** Copy `dashboard.png` into your conversation's `<Artifact Directory Path>` (e.g., `dashboard_<SANITIZED_TICKER>.png`) using PowerShell `Copy-Item`, and embed it via its absolute artifact path.
2. **Formatting Rules:** Escape every literal currency dollar sign in prose as `\$` (e.g., `\$92,450.00`) so KaTeX never turns prose into broken math. Reserve `$$...$$` and `$...$` strictly for actual LaTeX equations.
3. **Write Both Copies:**
   * Create the user-facing **Artifact** in `<Artifact Directory Path>` (`ArtifactMetadata` with `UserFacing=true`, `RequestFeedback=false`).
   * Save an archival copy to `<report_dir>/analysis.md` (replacing the embedded image path with `./dashboard.png` so the local `reports/<TICKER>/<TIMESTAMP>/` folder is 100% self-contained alongside `telemetry.json` and `dashboard.png`).
4. **Chat Response:** Keep the chat reply concise — point to the Artifact and the saved folder in `reports/`, highlighting only the executive verdict and key invalidation levels.
