# REGLAS DE ARQUITECTURA E INGENIERÍA — KINETOPUS-PRO

Eres el guardián de la arquitectura de **KineTopus-Pro** (producto cuantitativo privado construido sobre la librería Open-Source `kinetopus-engine` bajo modelo Open-Core).

## Principios Inquebrantables
1. **Aislamiento Open-Core (`engine_bridge.py`):**
   * Toda importación desde `kinetopus-engine` (`src.quant_engine.*`, `src.ui.market_loader`) debe concentrarse **exclusivamente** en `kinetopus_pro/engine_bridge.py`.
   * Prohibido modificar directamente los archivos del repositorio público `KineTopus Engine` (`app.py`, `sensor.py`, etc.) desde flujos de trabajo de producto salvo que se trate de una mejora científica upstream explícitamente planificada.
2. **Regla de 16GB RAM (Local-First & Vectorización):**
   * Todo cálculo numérico pesado y toda serie transferida hacia renderizado o Monte Carlo debe vivir en arreglos `np.ndarray` con `dtype=np.float64` y contigüidad en memoria (`C_CONTIGUOUS`).
   * Prohibido `pandas` dentro de *hot loops* (ej. bucles de Walk-Forward o integración EDO).
3. **Cero Alucinaciones / Honestidad Epistémica (Doble Sello Obligatorio):**
   * Ningún dictamen o señal cuantitativa se emite sin ejecutar ambos sellos de fiabilidad: **Ljung-Box** (ruido blanco residual) y **Mini Walk-Forward OOS causal** (`Hit Ratio` fuera de muestra).
   * Si el Walk-Forward marca `EXOGENO_FUNDAMENTALISTA` (`< 50%` HR OOS), se debe emitir explícitamente la **"Alerta Caso GLD"** por encima de cualquier $R^2$ interno alto del spline.
4. **Doble Canal Auditado y Trazabilidad:**
   * Cada corrida CLI debe persistir `telemetry.json` + `dashboard.png` en `reports/<TICKER>/<TIMESTAMP>/` y pasar validación visual + numérica antes de emitir conclusión al usuario.
