# ROADMAP DE PRODUCTO — KINETOPUS-PRO

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

## Hito 4: Empaquetado API / Servicio Comercial
**Estado:** 📋 IDEACIÓN
- Exponer reportes JSON + visualizaciones en API local/privada o bot de alertas de invalidación CUSUM y cambios de régimen.
