🌐 [Español](../MANIFIESTO.md) | **English**

# PROJECT MANIFESTO: KINETOPUS-ANALYST

> **Product North Star:** Turn the computational physics of [**KineTopus-Engine**](https://github.com/JuanDie778/KineTopus-Engine) into a **2D Phase-Space Attractor Microscope and risk-navigation instrument** — intuitive, portable, and epistemically honest — built to reveal the internal market dynamics that flat 1D price charts hide.

---

## 1. Core Purpose & Central Discovery (`From 1D Shadows to a 2D Microscope`)

**KineTopus-Analyst** (`kinetopus_pro`) is the product and service layer built under an Open-Core architecture on top of the open-source scientific core [**KineTopus-Engine**](https://github.com/JuanDie778/KineTopus-Engine) ([SSRN Preprint 7431018](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7431018) · [Zenodo DOI](https://doi.org/10.5281/zenodo.24166175), `Apache-2.0`).

While early milestones focused on multi-scale 1D price extrapolation, **Gran Estudio v3 (`26,294` causal snapshots across `27` series, `2000–2026`, including `15` untouched blind markets)** revealed where KineTopus delivers unmistakable practical value: **opening the second dimension (`X-axis = Normalized Volume Vz`, `Y-axis = Smoothed Return %`) via the 2D Phase-Space Attractor without ever peeking at future data.**

Rather than pretending to be a crystal ball for distant price targets, **KineTopus-Analyst** exists to answer three structural questions that classic 1D indicators (`OBV`, `CMF`, `AR(1)`) cannot see:
1. **Who is holding the wheel (`Lz`)?** Does the market orbit **counterclockwise (`Lz > 0`)** — patient accumulation where volume enters before price moves, like the `S&P 500` (`79%`) — or **clockwise (`Lz < 0`)** — reactive trend-chasing where price jumps first, like `Bitcoin` (`33%`), `Gold` (`36%`), or `Tesla` (`39%`)?
2. **Is the orbit trapped or escaping (`Fitzgibbon`)?** Does it trace a **closed ellipse** (`3x` more stable in `100%` of `25/25` daily markets) or open into an **escape hyperbola**?
3. **How much internal fragility is building (`Re(λ)`)?** Does local Lyapunov instability (`Re(λ) > +0.010 d⁻¹`) detect structural vulnerability ahead of sharp sell-offs (`ROC-AUC = 0.603` vs `0.473` for `Scheffer AR(1)` across `166` severe drops) so exposure can be dialed back in time?

---

## 2. Service Quality Standards (The 5 Pillars)

1. **Real Utility as a Risk-Navigation Instrument:**
   * Serve as a live phase-space diagnostic panel and fragility thermometer for open positions (hold calmly while a stable counterclockwise ellipse absorbs pullbacks; cut risk/leverage in half when rotation flips clockwise and the orbit opens into red instability — reducing max drawdown across `8/8` crypto assets), paired with causal `CUSUM` break detection.
2. **Simplicity & Intuition:**
   * Differential rigor (`C² Splines`, `SINDy`, `Fitzgibbon`, `Lyapunov`) inside; a clean four-season orbital reading outside that anyone can grasp in seconds.
3. **Zero-Friction Comfort:**
   * Reproducible *Local-First* CLI workflow (`kinetopus-analyze`) with automatic drift tuning (`CUSUMAutoTuner`), *Autopilot 2D* numerical rescue, and offline interactive reports.
4. **Portability & Lightweight Design:**
   * Decoupled `≤ 16 GB` RAM architecture (`np.float64` `C_CONTIGUOUS`) engineered to travel seamlessly as a CLI, self-contained `report.html`, compact JSON feed (`kinetopus.indicator.v1`), `< 35 KB` SVG widget, TradingView Pine Script v5 overlay, `FastAPI` service, and `MCP` server.
5. **Accessibility:**
   * Turn complex dynamical systems into clear, visual telemetry approachable by practitioners, engineers, and curious minds alike.

---

## 3. Target Audiences (`Targets`)

* **Quantitative Analysts, Portfolio Managers & Traders:** A 2D risk microscope to separate patient accumulation from reactive chasing and modulate exposure when internal fragility spikes.
* **Financial Platforms & B2B Integrators:** Phase-space telemetry, `< 35 KB` vector widgets, deduplicated alerts, and HTTP/MCP feeds ready to embed in brokers, fintechs, and research portals.
* **Scientific & Applied Finance Community:** An open, audited showcase proving on `26,294` real historical snapshots what continuous phase-space geometry reveals beyond flat 1D charts.

---

## 4. Epistemic Honesty & Explicit Boundaries

A serious scientific instrument proves its rigor by clearly stating what it **cannot** see:
1. **Not a crystal ball for exogenous shocks:** Ahead of the COVID crash (`February 12, 2020`), the `S&P 500` traced a calm green ellipse because no internal order-book fracture existed yet. The microscope measures endogenous capital fragility; it never predicts a virus or surprise macro headline.
2. **Respect for spline boundary horizons:** Cubic spline `not-a-knot` boundaries only preserve reliable curvature for a few free days ahead, never across many weeks. The core value lies in **live 2D attractor diagnostics and stability**, not long-range deterministic price prophecies.
3. **Complementarity in prolonged crises (`2008`):** Slow trend/volatility rules (`SMA-200`, `VolTarget`) still protect better as standalone allocation rules in multi-year bear markets; the 2D microscope shines as a **local seismograph and risk modulator**.
