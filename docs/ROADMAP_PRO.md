🌐 **Español** | [English](en/ROADMAP.md)

# ROADMAP DE PRODUCTO — KINETOPUS-ANALYST (`kinetopus_pro`)

> **Norte Estratégico:** Toda iteración de este roadmap se rige por [docs/MANIFIESTO.md](MANIFIESTO.md) (utilidad real como indicador técnico, sencillez e intuición, comodidad, portabilidad y accesibilidad).

## Hito 1: Base Headless, CLI Estandarizado y Protocolo Reproducible
**Estado:** ✅ COMPLETADO (`v0.1.0`)
- Orquestador *headless* (`kinetopus_pro/headless_pipeline.py`) con normalización local sin fuga temporal, Autopilot 2D, Doble Sello (`Ljung-Box` + Mini Walk-Forward causal OOS), geometría cinemática y forense CUSUM.
- Renderizador estático oscuro de 5 paneles (`kinetopus_pro/static_renderer.py`).
- CLI instalable (`kinetopus-analyze` / `kinetopus_pro.cli`) y protocolo reproducible de cero alucinaciones numéricas validado en corrida real (`BTC-USD`, `R² = 0.9217`, detección de `Alerta Caso GLD` con `40.0%` HR OOS).

---

## Hito 2: Motor Multi-Lente Jerárquico, Refuerzos Visuales y Reporte en 2 Partes
**Estado:** ✅ COMPLETADO (`v0.2.0`)
- **Motor Multi-Lente (`2000v / 1000v / 500v`):** Descarga única inteligente (`10y` con respaldo automático a `max`), calibración `CUSUMAutoTuner` independiente por escala en paralelo (`ProcessPoolExecutor`), degradación limpia `"N/D"` y Jerarquía Fija inicial.
- **Doble Sello Estricto (`v2.2`):** Walk-Forward OOS de ventana completa estricta (`W` velas exactas por corte), mínimo `5` cortes efectivos, pureza mínima `SINDy R² >= 0.35` y variedad re-anclada por mínimos cuadrados.
- **Dashboards de 6 Paneles y Storytelling en 2 Partes:** Zoom táctico, cruces fechados, fronteras CUSUM a 1 vela, pico máximo CUSUM y contraste con consenso web citado.

---

## Hito 2.5: Estándar de Análisis, Cono Calibrado y `report.html` Interactivo
**Estado:** ✅ COMPLETADO (`v0.3.0`)
- **Cono de Integración Simple EWMA y Taxonomía Humana:** Cono Monte Carlo en log-precio con volatilidad EWMA (`span=30`, $N=2,000$), métrica no bloqueante de cobertura empírica OOS (`cone_calibration`), jerarquía centrada en `1000v` y taxonomía humana de 5 estados (`Lateral en máximos`, `sobreextendido`, etc.). *(Nota: los bloqueos por OOS/`R²` y la supresión de `t+150` en `500v` presentes en `v0.3.0` fueron superados en `v0.3.1`.)*
- **Presentación Dual en Dos Etapas (`report.html` + `analysis.md`):** Entregable interactivo offline autocontenido (`plotly.min.js` + Jinja2, tema Oscuro/Claro, 3 pestañas de `6 + 6` bloques) y flujo `--render-report` con cifras blindadas.

---

## Hito 2.6: Enfoque Geométrico Puro y 3 Lentes `t+150` Simultáneas
**Estado:** ✅ COMPLETADO (`v0.3.1`)
- **Walk-Forward OOS Opcional (`--audit-oos`) y Cero Bloqueos:** Walk-Forward desactivado por defecto (`audit_oos=False`); eliminados el veto `"Sin escenario predictivo validado hoy"` y los cortes por `SINDy R² < 0.35`. *Autopilot 2D* solo interviene ante inestabilidad numérica o colapso `dr/dt = 0`.
- **Proyección Simultánea `t+150` en las 3 Lentes y Ajuste Curva-Precio:** `2000v` (Cian), `1000v` (Ámbar, eje principal de escenarios `P25/P75`) y `500v` (Violeta) proyectan siempre `t+150` simultáneamente, reportando ajuste explícito `curve_price_fit` (`window_price_r2`, `mape_pct`, `rmse_price`).
- **Historial 100% en `report_bundle.npz` y Selectores Interactivos:** Almacena la serie descargada completa (`h_start=0`), vista inicial `500v + t+150`, botones `[120v | 500v | 1000v | 2000v | Todo el historial]`, selector `[Cono: 1000v | 2000v | 500v | Sin cono]`, auto-escalado Y limpio y selector de los **3 dashboards técnicos** en Tab 3.
- **Limpieza Geométrica sin Barreras CUSUM de 1 Vela:** Retiradas las líneas punteadas intradía (`up_brk` / `dn_brk`) de `hero.png`, Paneles 1–2, regla derecha y escenarios; auditoría histórica CUSUM preservada intacta en Sección 2.5 y Panel 6. Validado con `15/15` tests en verde y corrida real `BTC-USD`.

---

## Hito 3: Escáner Multi-Activo y Multi-Serie (`v0.5.0`)
**Estado:** 📋 PLANIFICADO (Siguiente frente)
- **Radar Práctico y Motor de Barrido Transversal:** Soportar lotes mixtos de tickers de *Yahoo Finance* (Acciones, ETFs, Índices, FX, Cripto) y archivos CSV locales (incluidos pares acoplados `(X, Y)` no financieros bajo `--classic-price` que puedan contener ceros o valores negativos).
- **Tabla Maestra Determinista (`JSON` / `CSV`) y Síntesis Ejecutiva:** Consolidar para cada serie el estado humano de las 3 lentes (`2000v / 1000v / 500v`), brechas precio-curva `%`, ajuste Curva-Precio (`R²`, `MAPE`), proyecciones simultáneas `t+150`, arquetipo/autovalores SINDy + sentido de giro orbital, y fechas/scores de quiebres o picos históricos CUSUM (incorporando cobertura y métricas OOS cuando se active `--audit-oos`), conectándose directamente al endpoint preparado en Hito 4 (`hito3_scanner_attached`).

---

## Hito 4: Empaquetado de Servicio, API, Indicador Portable y Alertas Activas
**Estado:** ✅ COMPLETADO (`v0.4.0`)
- **Consumo Directo (Analistas / Público General):** Portal Web Ligero (`GET /` en `kinetopus-serve`, Oscuro/Claro), reportes interactivos `report.html` autocontenidos y servidor MCP `stdio` (`kinetopus-mcp`) para agentes.
- **Integración B2B (Plataformas como *TradingView* / *Investing.com*):** Contrato ligero `indicator_feed.json` (`kinetopus.indicator.v1`, `~5–12 KB`), widget vectorial embebible `widget.html` (`< 35 KB` SVG puro para `<iframe>`), overlay **TradingView Pine Script v5** (`indicator.pine`) y endpoints HTTP `FastAPI` protegidos con `threading.Lock` ($\le 16\text{ GB}$ RAM).
- **Alertas Activas (`alerts.py`):** 6 reglas físico-geométricas deterministas sobre `confluence.json`, ledger de deduplicación SHA-256 (`reports/.alerts_ledger.json`) y despacho saliente opcional vía HTTP POST JSON (`--webhook-url`).
