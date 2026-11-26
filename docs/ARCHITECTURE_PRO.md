🌐 **Español** | [English](en/ARCHITECTURE.md)

# ARQUITECTURA OPEN-CORE — KINETOPUS-ANALYST (`v0.4.0` · Geometría Pura + Servicio & Indicador Portable)

## 1. Frontera de Desacoplamiento (`engine_bridge.py`)
`KineTopus-Analyst` (`kinetopus_pro`) consume el motor científico público [`kinetopus-engine`](https://github.com/JuanDie778/KineTopus-Engine) (`Apache-2.0`) exclusivamente a través de `kinetopus_pro/engine_bridge.py`, manteniendo el repositorio base 100% intacto:

- **Dependencias Upstream (`kinetopus-engine`):**
  - `src.ui.market_loader.MarketLoader`
  - `src.quant_engine.sensor.SpectralAnalyzer`
  - `src.quant_engine.blender.ContinuousBlender`
  - `src.quant_engine.nervous.RegimeShiftDetector`
  - `src.quant_engine.physics.PhysicsDiscoverer`
  - `src.quant_engine.symbolic.SymbolicTranslator`
  - `src.quant_engine.auto_tuner.CUSUMAutoTuner`
- **Aislamiento de Namespace y Salida Estándar:** El paquete `kinetopus_pro/` consume `kinetopus-engine` como dependencia externa (vía `pip install` o resolviendo `KINETOPUS_ENGINE_DIR` / clon hermano `../KineTopus-Engine`) sin colisiones con `src/` y sin modificar el código fuente *upstream*. Cualquier diagnóstico impreso por módulos *upstream* se redirige a `stderr` para preservar la pureza JSON en `stdout` del CLI.

---

## 2. Arquitectura Geométrica Multi-Lente `v0.3.1` (`kinetopus_pro.multi_lens`)
Por defecto (`kinetopus-analyze --ticker <SYM>`), `KinetopusMultiLensRunner` evalúa tres escalas sobre una **única descarga inteligente** (`10y` con respaldo automático a `max` cuando `< 2,690` velas o cuando `--audit-oos` requiere margen adicional), conservando OHLC completo (`np.float64` `C_CONTIGUOUS`) para renderizado de velas:

1. **Proyección Simultánea `t+150` en las 3 Lentes (`ranges_by_lens` y `curves_comparison`):**
   - **`1000v` (`PRINCIPAL_PREDICTIVA` · Ámbar):** Eje Principal para rangos ejecutivos (`1s · 1m · 3m · t+150`), cono visible por defecto y escenarios probabilísticos `P25/P75` (solo cede al pulso `500v` en activos ultra-jóvenes `< 1,000` velas).
   - **`2000v` (`CONTEXTO_FONDO` · Cian):** Marea estructural de largo plazo con su propia trayectoria `t+150`, cono EWMA calibrado y métricas de ajuste Curva-Precio.
   - **`500v` (`SENSOR_ALERTA` · Violeta):** Pulso táctico de corto plazo que emite pines de quiebre CUSUM recientes ($\le 120\text{v}$), giros de velocidad ($\dot{r}=0 \le 50\text{v}$) y tensión acumulada, **proyectando también su propia trayectoria y cono `t+150`**.
2. **Cero Bloqueos Predictivos ni Vetos OOS:**
   - Eliminados el bloqueo `"Sin escenario predictivo validado hoy"` y los descartes por `SINDy R²` u OOS; las 3 lentes proyectan siempre de forma simultánea cuando disponen de ventana suficiente.
   - La **confianza física global** (`ALTA` / `MEDIA` / `BAJA`) pondera de forma transparente el ajuste Curva-Precio (`R²`, `MAPE`), la armonía direccional entre las 3 lentes, la tensión CUSUM vigente, la activación o no de respaldo cinemático y, únicamente si se solicita `--audit-oos`, el resultado de la auditoría retrospectiva.

---

## 3. Cono EWMA Calibrado, Curva-Precio, Taxonomía Humana y OOS Opcional (`kinetopus_pro.headless_pipeline` `v0.3.1`)
Cada lente ejecuta de forma causal (*zero look-ahead*) hasta `horizon_steps = 150`:

1. **Cono Monte Carlo Calibrado en Log-Precio (`_simulate_calibrated_single_integration_cone`):**
   - Aplica shocks i.i.d. normales una sola vez sobre incrementos de log-precio (eliminando la doble integración) escalados por volatilidad EWMA RiskMetrics (`span=30`, winsorizada a $\pm 3.5\text{ MAD-sigma}$) alrededor de la deriva determinista $F(t)$ ($\text{mediana} \equiv F(t)$, ancho $\propto \sigma_{\text{ewma}}\sqrt{k}$, $N=2,000$ trayectorias `np.float64` `C_CONTIGUOUS`).
2. **Ajuste Curva-Precio y Proyección Garantizada (`_compute_curve_price_fit`, `_ensure_geometric_projection`):**
   - Calcula `window_price_r2`, `active_regime_price_r2`, `mape_pct`, `rmse_price` y `fit_quality_label` sobre la variedad nominal re-anclada por mínimos cuadrados en log-precio.
   - *Autopilot 2D* interviene **exclusivamente** ante inestabilidad numérica o colapso `dr/dt = 0` (nunca por `SINDy R² < 0.35`), respaldado por amortiguamiento cinemático inercial para garantizar siempre `t+150` finito.
3. **Auditoría Walk-Forward OOS Opcional (`--audit-oos`) y `Ljung-Box`:**
   - `Ljung-Box` se calcula siempre como diagnóstico residual del Spline y la EDO.
   - El Walk-Forward OOS está **desactivado por defecto** (`audit_oos=False`, `wf_cuts=0`). Al pasar `--audit-oos` o `--wf-cuts > 0`, ejecuta validación de ventana completa estricta (`len(p_train) == W`, mínimo `5` cortes efectivos) más cobertura empírica informativa del cono (`cone_calibration`: `P25–P75` objetivo ~50%, `P5–P95` objetivo ~90%).
4. **Taxonomía Humana de 5 Estados y Escenarios `P25/P75` (*First-Passage*):**
   - Clasifica cada lente en 5 estados legibles (`Impulso alcista`, `Alcista frenando`, `Lateral / Digestión` [`Lateral en máximos` si cotiza $\ge 95\%$ del techo de ventana], `Corrección bajista`, `Caída frenando / Suelo en formación`) + modificador (`sobreextendido`, `descolgado`, `cerca de su curva`).
   - Los 3 escenarios (*Central*, *Expansión Alcista*, *Reversión Bajista*) se calculan directamente sobre la geometría de `1000v` y sus cuartiles `P25/P75`, erradicando las líneas de invalidación CUSUM de 1 vela de la vista ejecutiva.

---

## 4. Limpieza Visual, Historial Completo y Flujo Dual en Dos Etapas (`static_renderer.py` + `report_builder.py`)
1. **Gráfico Héroe (`hero.png`) y Dashboards de Laboratorio Técnico (`static_renderer.py`):**
   - `hero.png` muestra en **1 panel** la vista inicial (~`500v + t+150`) con velas OHLC (o línea de cierre), las **3 curvas y sus 3 proyecciones `t+150` simultáneas** (`2000v` Cian, `1000v` Ámbar + cono, `500v` Violeta), cortes limpios en quiebres históricos (`"Nuevo régimen · YYYY-MM-DD"`), pines tácticos `500v`, cero barreras horizontales CUSUM de 1 vela y **regla lateral derecha** sin solapes (`Hoy`, `2000v t+150`, `1000v t+150`, `500v t+150`, `P75`, `P25`).
   - Genera **3 dashboards técnicos de 6 paneles** (`2000v / 1000v / 500v`) y **18 paneles individuales** en español humano sin enums crudos, con los Paneles 1 y 2 libres de barreras CUSUM horizontales de 1 vela y `t+150` activo en las 3 escalas (conservando el forense histórico CUSUM completo en el Panel 6 y Sección 2.5).
2. **Historial 100% Offline y Flujo en Dos Etapas (`report_builder.py` + `templates/report.html.j2`):**
   - **Etapa 1 (`--ticker` / `--csv`):** Persiste `report_bundle.npz` con **el 100% del historial descargado** (`h_start=0`) y las 3 trayectorias/conos completos, crea `narrative_template.json`, y ensambla `report.html` autocontenido (`plotly.min.js`, vista inicial `500v + t+150`, botones `[120v | 500v | 1000v | 2000v | Todo el historial]`, selector `[Cono: 1000v | 2000v | 500v | Sin cono]`, auto-escalado Y limpio, interruptor Oscuro/Claro y selector de los **3 dashboards técnicos** en la Pestaña 3) junto con `analysis.md` en modo cuantitativo puro.
   - **Etapa 2 (`--render-report <DIR>`):** Fusiona el texto cualitativo de `narrative.json` con el 100% de cifras del motor en `< 0.5 s`, actualizando `report.html`, `analysis.md`, `indicator_feed.json`, `widget.html`, `indicator.pine` y `alerts.json`, y copiando en `--artifact-dir` `hero.png`, los **3 dashboards** (`2000v`, `1000v`, `500v`), `report.html`, `widget.html` y el Markdown listo para artefactos.

---

## 5. Capa de Servicio B2B, Indicador Portable y Alertas Activas (`v0.4.0` — Hito 4)
1. **Exportador B2B y Widget SVG `< 35 KB` (`kinetopus_pro/indicator_export.py` + `templates/widget.html.j2`):**
   - `indicator_feed.json` (`schema_version = "kinetopus.indicator.v1"`, `~5–12 KB`): contrato JSON compacto con las 3 lentes, escenarios `P25/P75`, pines tácticos `500v` y series muestreadas (`120v` cola + `t+150` cada `5` pasos).
   - `widget.html` (`< 35 KB`, cero `plotly.min.js`): gráfico vectorial SVG puro con Tema Oscuro/Claro (`?theme=light|dark`), cortes limpios CUSUM, cono `P25–P75` y etiquetas anti-colisión listo para `<iframe>` en portales externos.
   - `indicator.pine`: código **TradingView Pine Script v5** (`overlay=true`) con curvas vigentes `2000v/1000v/500v`, proyecciones `t+150`, corredor `P25–P75` y HUD `table.new`.
2. **Motor de Alertas Activas y Deduplicación (`kinetopus_pro/alerts.py`):**
   - Evalúa 6 reglas deterministas (`CUSUM_CRITICAL_TENSION`, `RECENT_CUSUM_BREAK`, `TACTICAL_500V_PIN`, `MULTI_LENS_DIVERGENCE`, `CURVE_EXTREME_STRETCH`, `REGIME_STATE_TRANSITION`), deduplica huellas SHA-256 en `reports/.alerts_ledger.json` y despacha webhooks HTTP POST JSON opcionales (`--webhook-url`, `urllib.request` stdlib).
3. **Micro-Servicio HTTP (`FastAPI` + Portal Web) y Servidor MCP (`service.py`, `mcp_server.py`):**
   - `kinetopus-serve`: expone `GET /` (`templates/portal.html.j2`), `/api/v1/health` (con gancho `hito3_scanner_attached`), `/api/v1/tickers`, `POST /api/v1/analyze` (serializado bajo `threading.Lock` para proteger la regla de `16 GB` RAM), `/api/v1/indicator/{ticker}`, `/api/v1/pine/{ticker}`, `/api/v1/alerts`, `/reports/{ticker}/widget` y `/reports/{ticker}/latest`.
   - `kinetopus-mcp`: servidor MCP `stdio` (`FastMCP`) con `list_analyzed_assets`, `get_asset_indicator`, `get_asset_alerts` y `get_tradingview_pine`.
