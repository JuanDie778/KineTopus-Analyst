# ROADMAP DE PRODUCTO — KINETOPUS-ANALYST (`kinetopus_pro`)

> **Norte Estratégico:** Toda iteración de este roadmap se rige por [docs/MANIFIESTO.md](MANIFIESTO.md) (utilidad real como indicador técnico, sencillez e intuición, comodidad, portabilidad y accesibilidad).

## Hito 1: Base Headless, CLI Estandarizado y Skill Agéntica
**Estado:** ✅ COMPLETADO (`v0.1.0`)
- Orquestador *headless* (`kinetopus_pro/headless_pipeline.py`) con normalización local sin fuga temporal, Autopilot 2D, Doble Sello (`Ljung-Box` + Mini Walk-Forward causal OOS), geometría cinemática y forense CUSUM.
- Renderizador estático oscuro de 5 paneles (`kinetopus_pro/static_renderer.py`).
- CLI instalable (`kinetopus-analyze` / `kinetopus_pro.cli`) y Skill `.agent/skills/kinetopus-analyst/SKILL.md` validada en corrida real (`BTC-USD`, `R² = 0.9217`, detección de `Alerta Caso GLD` con `40.0%` HR OOS).

---

## Hito 2: Motor Multi-Lente Jerárquico, Refuerzos Visuales y Reporte en 2 Partes
**Estado:** ✅ COMPLETADO (`v0.2.0`)
- **Motor Multi-Lente (`2000v / 1000v / 500v`):** Descarga única inteligente (`10y` con respaldo automático a `max`), calibración `CUSUMAutoTuner` independiente por escala en paralelo (`ProcessPoolExecutor`), degradación limpia `"N/D"` y Jerarquía Fija inicial.
- **Doble Sello Estricto (`v2.2`):** Walk-Forward OOS de ventana completa estricta (`W` velas exactas por corte), mínimo `5` cortes efectivos, pureza mínima `SINDy R² >= 0.35` y variedad re-anclada por mínimos cuadrados.
- **Dashboards de 6 Paneles y Storytelling en 2 Partes:** Zoom táctico, cruces fechados, fronteras CUSUM a 1 vela, pico máximo CUSUM y contraste con consenso web citado.

---

## Hito 2.5 / v0.3.0: Estándar Definitivo de Análisis, Cono Calibrado y `report.html` Interactivo
**Estado:** ✅ COMPLETADO (`v0.3.0`)
- **Rama 1 — Precisión del Cono y Régimen:** Cono Monte Carlo de integración simple en log-precio con volatilidad EWMA (`span=30`, $N=2,000$), métrica no bloqueante de cobertura empírica OOS (`cone_calibration`), `Autopilot 2D` alineado a `R² >= 0.35`, nueva jerarquía centrada en **`1000v` como Lente Principal Predictiva** (`2000v` Contexto de Fondo, `500v` Sensor de Alerta sin rangos), regla estricta `"Sin escenario predictivo validado hoy"` si falla `1000v`, y taxonomía humana de 5 estados (`Lateral en máximos`, `sobreextendido`, etc.).
- **Rama 2 — Limpieza Visual y Gráfico Héroe:** `hero.png` de 1 solo panel con velas OHLC, cortes limpios en quiebres CUSUM (`"Nuevo régimen · YYYY-MM-DD"`), regla derecha de niveles sin solapes, omisión de conos reprobados, 100% español humano sin enums crudos y exposición al cliente enfocada en `hero.png` + dashboard `1000v` (conservando las 3 lentes en disco para el agente).
- **Rama 3 — Narrativa de Escenarios Operativos:** 3 escenarios calculados por el motor (*Base*, *Alcista*, *Bajista*) con probabilidad de primer toque antes de `t+150` y estructura fija de `6 + 6` bloques ejecutivos/técnicos.
- **Rama 4 — Presentación Dual en Dos Etapas (`report.html` + `analysis.md`):** Entregable interactivo offline autocontenido (`plotly.min.js` + Jinja2, tema Oscuro/Claro en vivo, 3 pestañas, selector `1S / 1M / 3M / t+150 / Vista Héroe`) y flujo `--render-report` donde el motor inyecta el 100% de las cifras y `narrative.json` aporta el análisis cualitativo. Validado de extremo a extremo con `BTC-USD` y `SPY`.

---

## Hito 3: Escáner Multi-Activo de Regímenes Coherentes
**Estado:** 📋 PLANIFICADO
- Ejecutar barridos en lote sobre listas de seguimiento (Acciones, ETFs, Índices, FX, Cripto) filtrando y clasificando activos según validación de la Lente Principal (`1000v`), taxonomía humana de 5 estados, cobertura empírica del cono y cercanía a fronteras CUSUM o pines de alerta `500v`.

---

## Hito 4: Empaquetado de Servicio, API e Indicador Portable
**Estado:** 📋 IDEACIÓN
- **Consumo Directo (Analistas / Público General):** Reportes interactivos `report.html` autocontenidos y flujo *plug-and-play* de baja fricción (CLI, Skill/MCP o interfaz web ligera).
- **Integración B2B (Plataformas como *TradingView* / *Investing.com*):** Endpoints/feeds JSON portables (`confluence.json`), indicador estructurado de régimen/invalidación CUSUM multi-escala y widgets embebibles ligeros.
- **Alertas Activas:** Servicio de notificaciones automáticas ante quiebres de umbral CUSUM ($H$), pines tácticos del Sensor de Alerta (`500v`) y transiciones de validación OOS en `1000v`.
