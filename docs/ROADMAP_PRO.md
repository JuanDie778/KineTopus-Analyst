# ROADMAP DE PRODUCTO — KINETOPUS-ANALYST (`kinetopus_pro`)

> **Norte Estratégico:** Toda iteración de este roadmap se rige por [docs/MANIFIESTO.md](MANIFIESTO.md) (utilidad real como indicador técnico, sencillez e intuición, comodidad, portabilidad y accesibilidad).

## Hito 1: Base Headless, CLI Estandarizado y Skill Agéntica
**Estado:** ✅ COMPLETADO (`v0.1.0`)
- Orquestador *headless* (`kinetopus_pro/headless_pipeline.py`) con normalización local sin fuga temporal, Autopilot 2D, Doble Sello (`Ljung-Box` + Mini Walk-Forward causal OOS), geometría cinemática y forense CUSUM.
- Renderizador estático oscuro de 5 paneles (`kinetopus_pro/static_renderer.py`).
- CLI instalable (`kinetopus-analyze` / `kinetopus_pro.cli`) y Skill `.agent/skills/kinetopus-analyst/SKILL.md` validada en corrida real (`BTC-USD`, `R² = 0.9217`, detección de `Alerta Caso GLD` con `40.0%` HR OOS).

---

## Hito 2: Doble Lente de Escala (Marea Macro + Ola Táctica)
**Estado:** 📋 PLANIFICADO
- Evaluar en paralelo la ventana secular (`1000v`, `tol = 0.0050`) y una ventana táctica de corto plazo (`~150v`) para eliminar el desfase temporal frente a caídas/rebotes de 2–8 semanas y detectar convergencia o divergencia entre escalas.

---

## Hito 3: Escáner Multi-Activo de Regímenes Coherentes
**Estado:** 📋 PLANIFICADO
- Ejecutar barridos en lote sobre listas de seguimiento (Acciones, ETFs, Índices, FX, Cripto) filtrando automáticamente únicamente los activos que cumplan `OOS Hit Ratio >= 55-60%`, `SINDy R² >= 0.75` y `CUSUM ESTABLE`.

---

## Hito 4: Empaquetado de Servicio, API e Indicador Portable
**Estado:** 📋 IDEACIÓN
- **Consumo Directo (Analistas / Público General):** Reportes ejecutivos intuitivos, visualizaciones claras y flujo *plug-and-play* de baja fricción (CLI, Skill/MCP o interfaz ligera).
- **Integración B2B (Plataformas como *TradingView* / *Investing.com*):** Endpoints/feeds JSON portables, indicador estructurado de régimen/invalidación CUSUM y widgets embebibles ligeros.
- **Alertas Activas:** Bot/servicio de notificaciones automáticas ante quiebres de umbral CUSUM ($H$) y transiciones de coherencia OOS.
