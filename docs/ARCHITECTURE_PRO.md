# ARQUITECTURA OPEN-CORE — KINETOPUS-PRO (`v0.2.0`)

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

## 2. Orquestación Multi-Lente Jerárquica (`kinetopus_pro.multi_lens`)
Por defecto (`kinetopus-analyze --ticker <SYM>`), `KinetopusMultiLensRunner` evalúa simultáneamente tres escalas de contexto sobre una **única descarga**:

1. **Descarga Inteligente (`10y` → `max`):** Solicita `10y` en `yfinance`; si el activo devuelve `< 2,690` velas (típico de acciones/ETFs de ~252 sesiones/año al requerir holgura para `10` cortes OOS de `2,000` velas completas), amplía automáticamente a `max` en una sola petición de respaldo.
2. **Ejecución Paralela y Degradación Limpia:** Lanza las 3 lentes (`2000v`, `1000v`, `500v`) en paralelo mediante `ProcessPoolExecutor` (`max_workers <= 3`, arreglos `np.float64` `C_CONTIGUOUS` aptos para 16 GB RAM). Si un activo joven posee `< W` velas totales, esa lente se reporta como `"N/D"` sin abortar las demás.
3. **Jerarquía Fija sin Votación ni Promociones (`_synthesize_fixed_hierarchy`):**
   - `2000v` (`MACRO_FONDO`): **Tendencia de Fondo**. Si es `"N/D"` o reprueba su Doble Sello, el fondo queda `INDETERMINADA` / `N/D` (nunca es suplantado por `1000v`) y la confianza física global se limita como máximo a `BAJA_CAUTELA`.
   - `1000v` (`MEDIO_CONFIRMACION`): **Confirmación de Medio Plazo**. Confirma o diverge respecto al fondo únicamente si supera su propio Doble Sello.
   - `500v` (`CORTO_TIMING`): **Timing Táctico**. Mide aceleración reciente, brecha contra el spline y proximidad a fronteras CUSUM.

---

## 3. Pipeline Headless y Doble Sello Estricto (`kinetopus_pro.headless_pipeline` v2.2)
Cada lente ejecuta de forma independiente y libre de fuga de futuro (*zero look-ahead*):

1. **Recorte Causal & Normalización Local:** Extrae las últimas `W` velas y normaliza retornos logarítmicos y volumen *in-window*.
2. **FFT In-Process & Calibración Independiente:** Calcula los periodos dominantes FFT en el mismo proceso y calibra `k*` óptimo (`CUSUMAutoTuner` + rescate `Autopilot 2D` sobre tolerancias `0.0005`, `0.0001`, `0.00005` cuando hay inestabilidad con $R^2 \ge 0.40$).
3. **Integración Espectral & Re-Anclaje por Mínimos Cuadrados:** Resuelve analíticamente el sistema EDO lineal `2x2` (`< 1 ms`), simula `1,000` trayectorias Euler-Maruyama (`seed=42`) y centra la variedad de precio nominal por régimen minimizando el residuo logarítmico medio.
4. **Doble Sello Estricto (`evaluate_double_seal`):**
   - **Walk-Forward Causal de Ventana Completa:** Cada corte histórico entrena con **exactamente `W` velas completas** (`len(p_train) == W`, cero ventanas truncadas) usando calibración rápida cacheada sobre el spline pre-suavizado del corte. Si se obtienen `< 5` cortes efectivos, el sello se declara `"INSUFICIENTE"` (`seal_passed = False`).
   - **Pureza Interna y Blancura:** Exige `SINDy R² >= 0.35` más clase OOS `COHERENTE_INERCIAL` o `TRANSICIONAL_BORDE`, diferenciando `APROBADO_PLENO` (`Ljung-Box p > 0.05` y `HR >= 55%`) de `APROBADO_CONDICIONAL`.

---

## 4. Renderizado Estático y Auditoría Visual (`kinetopus_pro.static_renderer`)
Genera `22` artefactos gráficos oscuros (`Matplotlib Agg`, cierre explícito de figuras) por corrida Multi-Lente:

- **`confluence.png` (`dpi=165`):** Lienzo ejecutivo maestro de 3 paneles (3 variedades Spline $C^2$ superpuestas + Zoom de confluencia `220v + t+60` + 3 curvas de velocidad $\dot{r}$ superpuestas).
- **`lens_<W>/dashboard.png` (`dpi=160`):** Dashboard compuesto de **6 paneles** con carril lateral anti-colisión para etiquetas:
  1. Variedad de Precio Nominal + Cono Monte Carlo + Fronteras CUSUM a 1 vela + Brecha Precio vs. Spline.
  2. **Zoom Táctico (`120v + t+60`)** con bandas `P25–P75` y niveles operativos legibles al dólar.
  3. Velocidad inercial ($\dot{r}$) con cruces por cero ($\dot{r}=0$) fechados.
  4. Aceleración inercial ($\ddot{r}$) con inflexiones ($\ddot{r}=0$) fechadas.
  5. Atractor en Espacio de Fase $(V_z, r_{\%})$ con flechas direccionales de sentido de giro (`HORARIO` / `ANTIHORARIO`).
  6. Tensión CUSUM ($S^+, S^-$) con quiebres escalonados y marcador obligatorio de `Pico Máx` en la ventana.
- **`lens_<W>/panels/01..06_*.png` (`dpi=200`):** Los 6 paneles individuales en alta resolución para inspección focalizada sin recorte manual.
