🌐 [Español](../MANIFIESTO.md) | **English**

# PROJECT MANIFESTO: KINETOPUS-ANALYST

> **Product North Star:** Turn the Computational Financial Physics theory behind [**KineTopus-Engine**](https://github.com/JuanDie778/KineTopus-Engine) into a **real, useful, intuitive, portable, and accessible quantitative service and indicator** for technical analysts, financial platforms, and curious minds everywhere.

---

## 1. Purpose & Product North Star (`From Scientific Paper to Live Service`)

**KineTopus-Analyst** (`kinetopus_pro`) is the product and service layer built under an Open-Core architecture on top of the open-source scientific core [**KineTopus-Engine**](https://github.com/JuanDie778/KineTopus-Engine) ([SSRN Preprint 7431018](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7431018) · [Zenodo DOI](https://doi.org/10.5281/zenodo.24166175), `Apache-2.0`).

While `KineTopus-Engine` demonstrates in academia that financial time series conceal continuous dynamics discoverable via **FFT**, **$C^2$ Splines**, **CUSUM**, symbolic ODE discovery (**SINDy**), and stochastic integration (**Euler-Maruyama**), **KineTopus-Analyst** exists for a distinct and complementary mission:

* **Prove practical applicability and tangible value:** Bring the engine out of the research notebook and turn it into a tool that solves real decision-making needs in live markets.
* **Operate as a service powered by KineTopus-Engine:** Translate differential equations, derivatives, and phase-space attractors into clean, actionable readings that an analyst, investor, or external platform can consume effortlessly.

---

## 2. Customer-First Product Mindset (`Think Like the Consumer of the Service`)

Every technical, visual, and integration decision in this repository is designed **from the perspective of the end user consuming the service**.

Mathematical rigor is necessary, never sufficient. A quantitative product creates genuine adoption only when it clearly answers the user's operational questions:
1. **Is this asset currently governed by its own physical inertia, or dominated by exogenous noise and shocks?**
2. **Is the prevailing trajectory accelerating, exhausting, or approaching a kinematic turning point?**
3. **Where exactly do the mathematical regimes break or shift?**

If a calculation does not improve clarity or forces the reader to decode unnecessary jargon, the product is not finished yet.

---

## 3. Service Quality Standards (The 5 Pillars)

**KineTopus-Analyst** holds itself to five non-negotiable engineering and design standards:

1. **Real Utility as a Technical Indicator:**
   * Serve as a genuinely useful structural indicator and regime radar for technical analysis and portfolio monitoring (multi-lens regime state, kinematic inflection zones, CUSUM regime breaks, and calibrated $P_5\text{–}P_{95}$ cones), elevating traditional charting with objective, non-discretionary geometry.
2. **Simplicity & Intuition:**
   * Mathematical sophistication inside; immediate readability outside.
   * Visual outputs and summaries must be legible in seconds without requiring a background in differential equations.
3. **Zero-Friction Comfort:**
   * Plug-and-play workflow: automatic CUSUM drift calibration (`k*`), *Autopilot 2D* numerical stability rescue, optional out-of-sample Walk-Forward auditing, and reproducible reporting in a single command.
4. **Portability & Lightweight Design:**
   * Decoupled architecture (`Local-First`, memory-bounded for $\le 16\text{ GB}$ RAM machines), engineered to travel cleanly as a CLI, Python package, JSON/NPZ/HTML self-contained artifact, HTTP API, MCP server, TradingView Pine Script overlay, or `< 35 KB` embeddable widget.
5. **Accessibility:**
   * Technically and cognitively approachable across delivery channels and experience levels, removing both infrastructure and interpretation barriers.

---

## 4. Target Audiences (`Targets`)

The service serves three complementary segments:

* **Technical Analysts, Traders & Investors:**
  * Independent and professional market participants seeking an emotion-free regime radar to assess trend health, stretch vs. underlying geometry, and probabilistic cones across three time scales simultaneously.
* **Financial Platforms & B2B Partners (*TradingView*, *Investing.com*, Brokers, Terminals, Fintechs):**
  * Integrate `KineTopus-Engine` intelligence via lightweight JSON contracts (`kinetopus.indicator.v1`), embeddable `< 35 KB` SVG widgets, Pine Script overlays, and FastAPI/webhook telemetry.
* **General Public & Applied Science Showcase:**
  * An open, visual showcase proving how theoretical computational physics research can become practical everyday software.

---

## 5. Unbreakable Governance Principles (Science + Product)

1. **Epistemic Honesty Over Over-Trading:**
   * Expose Curve-to-Price fit (`R²`, `MAPE`), residual diagnostics (`Ljung-Box`), historical regime breaks (`CUSUM`), and optional Walk-Forward OOS audits (`--audit-oos`) transparently without hiding uncertainty.
2. **White-Box Without Hallucinations:**
   * Zero opaque black boxes and zero fabricated numbers. Every price, band, touch probability, and equation metric is computed and injected deterministically by the engine.
3. **Development North-Star Filter:**
   * Before designing or shipping any feature, every change must pass three checks:
     1. *Does it add direct utility for the analyst, investor, platform, or reader?*
     2. *Does it make the service simpler, more intuitive, and zero-friction?*
     3. *Does it preserve or improve portability and accessibility?*
