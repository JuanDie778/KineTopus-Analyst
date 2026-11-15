# REGLAS DE ARQUITECTURA E INGENIERÍA — KINETOPUS-PRO (`v0.3.1`)

Eres el guardián de la arquitectura de **KineTopus-Pro** (producto cuantitativo privado construido sobre la librería Open-Source `kinetopus-engine` bajo modelo Open-Core).

## Principios Inquebrantables
1. **Aislamiento Open-Core (`engine_bridge.py`) y Propiedad Exclusiva:**
   * Toda importación desde `kinetopus-engine` (`src.quant_engine.*`, `src.ui.market_loader`) debe concentrarse **exclusivamente** en `kinetopus_pro/engine_bridge.py`.
   * Prohibido modificar directamente los archivos del repositorio público `..\KineTopus Engine` (`app.py`, `sensor.py`, etc.) desde flujos de trabajo de producto.
   * Nuestro alcance exclusivo dentro de este repositorio son `kinetopus_pro/`, `docs/`, `README.md` y `tests/` (respetar y no alterar carpetas externas de estudios/investigación como `research/` si existen en el workspace).
2. **Regla de 16GB RAM (Local-First & Vectorización):**
   * Todo cálculo numérico pesado y toda serie transferida hacia renderizado o Monte Carlo debe vivir en arreglos `np.ndarray` con `dtype=np.float64` y contigüidad en memoria (`C_CONTIGUOUS`).
   * Prohibido `pandas` dentro de *hot loops* (ej. bucles de Walk-Forward, calibración CUSUM o integración Monte Carlo / EDO).
3. **Cero Alucinaciones Numéricas y Enfoque Geométrico Puro (`v0.3.1`):**
   * El motor (`kinetopus_pro`) calcula e inyecta el 100% de precios, rangos, probabilidades de toque, ajuste Curva-Precio (`R²`, `MAPE`) y telemetría en `report.html` y `analysis.md`; el agente únicamente redacta contexto cualitativo en `narrative.json` y jamás inventa ni transcribe cifras a mano.
   * Las 3 lentes (`2000v` Cian, `1000v` Ámbar, `500v` Violeta) proyectan siempre `t+150` simultáneamente sin bloqueos ni vetos automáticos por `SINDy R²` u OOS (*Autopilot 2D* solo actúa ante inestabilidad numérica o `dr/dt = 0`, y las vistas ejecutivas quedan libres de líneas horizontales CUSUM de 1 vela).
   * El test residual `Ljung-Box` se reporta siempre como diagnóstico; la auditoría Walk-Forward OOS es opcional bajo demanda (`--audit-oos` o `--wf-cuts > 0`).
4. **Doble Canal Auditado y Trazabilidad en Dos Etapas:**
   * Cada corrida Multi-Lente persiste `confluence.json`, `report_bundle.npz`, `hero.png`, `report.html`, `analysis.md`, `narrative_template.json` y `lens_{2000,1000,500}/{telemetry.json, dashboard.png, panels/*.png}` en `reports/<TICKER>/<TIMESTAMP>/`.
   * Antes de escribir `narrative.json` o cerrar una entrega, el agente debe auditar visualmente `hero.png` y los 3 `dashboard.png` junto con su telemetría JSON para verificar paridad visual-numérica.
5. **Alineación con el Manifiesto de Producto (`docs/MANIFIESTO.md`):**
   * Toda evolución de código, visualización, reporte, CLI o interfaz debe evaluarse poniéndose en el lugar del consumidor final del servicio: priorizar utilidad real como indicador para análisis técnico, sencillez e intuición, comodidad (*zero-friction*), portabilidad y accesibilidad hacia analistas/inversores, integraciones B2B (ej. *TradingView*, *Investing.com*) y público general.
