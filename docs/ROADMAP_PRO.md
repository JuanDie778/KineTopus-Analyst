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
- **Motor Multi-Lente (`2000v / 1000v / 500v`):** Descarga única inteligente (`10y` con respaldo automático a `max` cuando `10y < 2,690` velas para activos bursátiles de ~252 sesiones/año), calibración `CUSUMAutoTuner` independiente por escala en paralelo (`ProcessPoolExecutor`), degradación limpia `"N/D"` en activos jóvenes y **Jerarquía Fija sin promociones** (`2000v` = Tendencia de Fondo, `1000v` = Confirmación de Medio Plazo, `500v` = Timing Táctico).
- **Doble Sello Estricto (`v2.2`):** Walk-Forward OOS de **ventana completa estricta (`W` velas exactas por corte, cero truncamiento)**, exigencia de mínimo `5` cortes efectivos (`INSUFICIENTE` en caso contrario), pureza mínima `SINDy R² >= 0.35`, FFT calculada en el mismo proceso y variedad de precio re-anclada por mínimos cuadrados.
- **Refuerzos Visuales A–E y Lectura Escalonada:** Lienzo maestro `confluence.png` (3 splines $C^2$ superpuestos + zoom `220v` + 3 velocidades $\dot{r}$ superpuestas), dashboard de **6 paneles** por lente incorporando **Zoom Táctico (`120v + t+60`)**, etiquetas fechadas de cruces $\dot{r}=0$ / $\ddot{r}=0$, fronteras CUSUM a 1 vela, brecha Precio vs. Spline, pico máximo CUSUM y flechas orbitales en espacio de fase, más paneles individuales `dpi=200` en `lens_<W>/panels/`.
- **Storytelling Ejecutivo en 2 Partes:** Ficha Ejecutiva de 1 Minuto (cero jerga matemática, 5 preguntas clave, `confluence.png`, niveles y 3 insights de alto impacto) + Análisis Técnico/Físico Detallado (tabla jerárquica de sellos, auditoría `"Lo que veo vs. lo que dice el JSON"`, EDOs SINDy, forense CUSUM, contraste exclusivo con consenso web citado y sección obligatoria `"Límites de esta lectura"`). Validado empíricamente sobre `BTC-USD` y `SPY`.

---

## Hito 3: Escáner Multi-Activo de Regímenes Coherentes
**Estado:** 📋 PLANIFICADO
- Ejecutar barridos en lote sobre listas de seguimiento (Acciones, ETFs, Índices, FX, Cripto) filtrando y clasificando activos según alineación Multi-Lente (`ALINEACION_ALCISTA_PLENA` / `ALINEACION_BAJISTA_PLENA`), aprobación del Doble Sello Estricto (`OOS Hit Ratio >= 55–60%` en `>= 5` cortes completos, `SINDy R² >= 0.50`) y estado `CUSUM ESTABLE` o proximidad a ruptura.

---

## Hito 4: Empaquetado de Servicio, API e Indicador Portable
**Estado:** 📋 IDEACIÓN
- **Consumo Directo (Analistas / Público General):** Reportes ejecutivos intuitivos en 2 partes, visualizaciones claras y flujo *plug-and-play* de baja fricción (CLI, Skill/MCP o interfaz web ligera).
- **Integración B2B (Plataformas como *TradingView* / *Investing.com*):** Endpoints/feeds JSON portables (`confluence.json`), indicador estructurado de régimen/invalidación CUSUM multi-escala y widgets embebibles ligeros.
- **Alertas Activas:** Servicio de notificaciones automáticas ante quiebres de umbral CUSUM ($H$), cruces de velocidad ($\dot{r}=0$) en la lente de Timing (`500v`) y transiciones de coherencia OOS.
