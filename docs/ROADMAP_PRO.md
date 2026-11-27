🌐 **Español** | [English](en/ROADMAP.md)

# ROADMAP DE PRODUCTO — KINETOPUS-ANALYST (`kinetopus_pro`)

> **Norte Estratégico:** Toda iteración de este roadmap se rige por [docs/MANIFIESTO.md](MANIFIESTO.md): convertir la física del **Atractor de Fase 2D** y la detección causal de regímenes en un instrumento práctico de diagnóstico y navegación de riesgo.

---

## Hito 1: Base Headless, CLI Estandarizado y Protocolo Reproducible
**Estado:** ✅ COMPLETADO (`v0.1.0`)
- Orquestador *headless* (`kinetopus_pro/headless_pipeline.py`) con normalización local sin fuga temporal, *Autopilot 2D*, Doble Sello (`Ljung-Box` + Walk-Forward causal OOS), geometría cinemática y forense CUSUM.
- Renderizador estático oscuro (`kinetopus_pro/static_renderer.py`) y CLI instalable (`kinetopus-analyze`).

---

## Hito 2: Motor Multi-Lente Jerárquico, Cono EWMA y Geometría Pura
**Estado:** ✅ COMPLETADO (`v0.2.0` → `v0.3.1`)
- **Multi-Lente (`2000v / 1000v / 500v`):** Descarga única inteligente (`10y` con respaldo automático a `max`), calibración `CUSUMAutoTuner` en paralelo (`ProcessPoolExecutor`), ajuste explícito Curva-Precio (`R²`, `MAPE`), cono Monte Carlo EWMA de integración simple (`span=30`), auditoría Walk-Forward OOS opcional (`--audit-oos`), dashboards de 6 paneles (con mapa 2D Retorno-Volumen y sentido de giro orbital en el Panel 5) y reporte interactivo offline `report.html` en dos etapas.

---

## Hito 4: Empaquetado de Servicio, API, Indicador Portable y Alertas Activas
**Estado:** ✅ COMPLETADO (`v0.4.0`)
- **Consumo Directo:** Portal Web Ligero (`GET /` en `kinetopus-serve`), `report.html` autocontenido y servidor MCP `stdio` (`kinetopus-mcp`).
- **Suite Portable B2B:** Contrato compacto `indicator_feed.json` (`kinetopus.indicator.v1`), widget SVG `< 35 KB` embebible (`widget.html`), overlay **TradingView Pine Script v5** (`indicator.pine`) y 6 reglas de alertas activas deduplicadas por SHA-256 con despacho webhook (`--webhook-url`).
- **Blindaje y Paridad `2.0-Core`:** Guardarraíl anti-explosión exponencial en EDOs SINDy, paridad exacta con `CUSUMAutoTuner` (`KineTopus 2.0-Core`) y compatibilidad `pandas 3.0` / Linux CI (`22/22` tests en verde).

---

## Hito 3: Microscopio 2D de Espacio de Fases + Escáner Multi-Activo (`v0.5.0`)
**Estado:** 📋 PLANIFICADO (Siguiente frente tras las conclusiones del Gran Estudio v3)

Con el cierre de la infraestructura `v0.4.0` y los resultados empíricos del **Gran Estudio v3 (`26,294` instantáneas causales, `2000–2026`)**, el siguiente hito alinea directamente la experiencia principal del producto con los cuatro pilares validados del microscopio 2D:

1. **Microscopio 2D de Atractor de Fase en Primer Plano (`CLI`, `Widget`, `Feed` y `Portal`):**
   - Promover el plano 2D (`Eje X = Volumen normalizado Vz`, `Eje Y = Retorno suavizado %`) del Panel 5 secundario a la vista protagonista.
   - Calcular y exponer de serie las métricas ganadoras del estudio: **momento angular y % de giro antihorario (`Lz`)**, clasificación geométrica de **cónica de Fitzgibbon** (elipse cerrada vs. hipérbola abierta), **sismógrafo de Lyapunov (`Re(λ)` en `d⁻¹`, alerta `> +0.010 d⁻¹`)** y **termómetro modulador de riesgo (ej. señal de recorte al `50%`)**.
   - Acotar las extrapolaciones temporales largas al horizonte honesto de curvatura local, evitando proyecciones exponenciales irreales a `150` velas como eje protagonista.
2. **Escáner Multi-Activo y Multi-Serie (`JSON` / `CSV`):**
   - Barrido transversal sobre lotes mixtos de tickers de *Yahoo Finance* (Acciones, ETFs, Índices, FX, Cripto) y archivos CSV locales (incluidos pares dinámicos acoplados `(X, Y)` no financieros con ceros o valores negativos bajo `--classic-price`).
   - Tabla maestra determinista (`JSON` / `CSV`) con estado del atractor 2D (`Lz`, Fitzgibbon, `Re(λ)`), tensión/quiebres CUSUM y ajuste multi-escala, conectándose al endpoint preparado en `service.py` (`hito3_scanner_attached`).
