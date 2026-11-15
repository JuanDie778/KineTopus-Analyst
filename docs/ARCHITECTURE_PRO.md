# ARQUITECTURA OPEN-CORE — KINETOPUS-PRO (`v0.3.0`)

## 1. Frontera de Desacoplamiento (`engine_bridge.py`)
`KineTopus-Analyst` (`kinetopus_pro`) consume el motor científico `kinetopus-engine` exclusivamente a través de `kinetopus_pro/engine_bridge.py`, manteniendo el repositorio base 100% intacto:

- **Dependencias Upstream (`kinetopus-engine`):**
  - `src.ui.market_loader.MarketLoader`
  - `src.quant_engine.sensor.SpectralAnalyzer`
  - `src.quant_engine.blender.ContinuousBlender`
  - `src.quant_engine.nervous.RegimeShiftDetector`
  - `src.quant_engine.physics.PhysicsDiscoverer`
  - `src.quant_engine.symbolic.SymbolicTranslator`
  - `src.quant_engine.auto_tuner.CUSUMAutoTuner`
- **Aislamiento de Namespace y Salida Estándar:** El paquete propietario reside en `kinetopus_pro/`, coexistiendo editable (`pip install -e`) sin colisiones con `src/`. Cualquier diagnóstico impreso por módulos *upstream* se redirige a `stderr` para preservar la pureza JSON en `stdout` del CLI.

---

## 2. Jerarquía Multi-Lente Centrada en `1000v` (`kinetopus_pro.multi_lens`)
Por defecto (`kinetopus-analyze --ticker <SYM>`), `KinetopusMultiLensRunner` evalúa tres escalas sobre una **única descarga inteligente** (`10y` con respaldo automático a `max` cuando `< 2,690` velas), conservando OHLC completo (`np.float64` `C_CONTIGUOUS`) para renderizado de velas:

1. **`1000v` (`PRINCIPAL_PREDICTIVA` — Lente Principal Predictiva):** Única lente autorizada para emitir rangos de precio (`1s · 1m · 3m · t+150`), cono Monte Carlo calibrado y los 3 escenarios probabilísticos (*Base*, *Alcista*, *Bajista*).
2. **`2000v` (`CONTEXTO_FONDO` — Contexto de Fondo):** Aporta la marea estructural de largo plazo sin emitir escenarios rivales.
3. **`500v` (`SENSOR_ALERTA` — Sensor de Alerta):** Emitida exclusivamente como radar táctico (pines puntuales de giro $\dot{r}=0$, tensión CUSUM $\ge 70\% H$ y estiramiento estadístico), suprimiendo conos y tablas de objetivos para evitar contradicciones.
4. **Regla Estricta ante Fallo (Cero Promociones):** Si `1000v` es `"N/D"` o reprueba su Doble Sello (`seal_passed == False`), el sistema declara `"Sin escenario predictivo validado hoy"` y fija la confianza global en `"BAJA"`, prohibiendo promover `2000v` o `500v` como sustitutas predictivas.

---

## 3. Cono de Integración Simple EWMA, Taxonomía Humana y Escenarios (`kinetopus_pro.headless_pipeline` v0.3.0)
Cada lente ejecuta de forma causal (*zero look-ahead*) hasta `horizon_steps = 150`:

1. **Cono Monte Carlo Calibrado en Log-Precio (`_simulate_calibrated_single_integration_cone`):**
   - Elimina la doble integración browniana sobre aceleración y modela shocks i.i.d. normales sobre incrementos de log-precio escalados por volatilidad EWMA RiskMetrics (`span=30`, winsorizada por MAD) anclada exactamente a la trayectoria determinista SINDy $F(t)$ ($\text{mediana} \equiv F(t)$, ancho $\propto \sigma_{\text{ewma}}\sqrt{k}$, $N=2,000$ trayectorias `np.float64` `C_CONTIGUOUS`).
2. **Auditoría Empírica OOS del Cono (`cone_calibration`):**
   - Durante el Walk-Forward causal de ventana completa (`len(p_train) == W`, mínimo `5` cortes efectivos, `R² >= 0.35`, `Autopilot 2D` alineado a `R² >= 0.35`), mide la cobertura empírica real de `P25–P75` (objetivo ~50%) y `P5–P95` (objetivo ~90%) como métrica transparente no bloqueante.
3. **Taxonomía Humana de 5 Estados y Escenarios con Probabilidad de Primer Toque:**
   - Clasifica cada lente en 5 estados legibles (`Impulso alcista`, `Alcista frenando`, `Lateral / Digestión` [`Lateral en máximos` cuando cotiza $\ge 95\%$ del techo de ventana], `Corrección bajista`, `Caída frenando / Suelo en formación`) + modificador de posición (`sobreextendido`, `descolgado`, `cerca de su curva`).
   - Calcula para `1000v` las probabilidades de primer toque (*first-passage*) antes de `t+150` contra las fronteras CUSUM al cierre y las medianas condicionales post-ruptura.

---

## 4. Limpieza Visual y Presentación Dual en Dos Etapas (`static_renderer.py` + `report_builder.py`)
1. **Gráfico Héroe (`hero.png`) y Dashboards Sin Códigos Crudos (`static_renderer.py`):**
   - `hero.png` unifica en **1 solo panel** velas OHLC (o línea de cierre), curva y cono `1000v` (o gris discontinua sin cono cuando reprueba), curva `2000v` de fondo, pines puntuales `500v`, **cortes limpios** en cada quiebre CUSUM con pastilla `"Nuevo régimen · YYYY-MM-DD"` (sin escalones verticales artificiales) y **regla lateral derecha** sin solapes.
   - Se mantienen los 3 dashboards (`2000v`, `1000v`, `500v`) y 18 paneles individuales en disco para auditoría del agente (`xlim` de derivadas truncado a `Hoy`, cero enums crudos), mostrando al usuario final únicamente `hero.png` y el dashboard de `1000v`.
2. **Flujo en Dos Etapas con Cero Alucinación Numérica (`report_builder.py` + `templates/report.html.j2`):**
   - **Etapa 1 (`--ticker` / `--csv`):** Persiste `report_bundle.npz` + `narrative_template.json` y genera `report.html` autocontenido offline (`plotly.min.js` embebido, tema oscuro por defecto + interruptor Claro/Oscuro en vivo, 3 pestañas y selector de horizonte `1S / 1M / 3M / t+150 / Vista Héroe`) junto con `analysis.md` en modo cuantitativo puro.
   - **Etapa 2 (`--render-report <DIR>`):** Fusiona el texto cualitativo de `narrative.json` con el 100% de cifras del motor en `< 0.5 s`, actualizando `report.html`, `analysis.md` y opcionalmente los artefactos listos para incrustar vía `--artifact-dir`.
