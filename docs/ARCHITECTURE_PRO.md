# ARQUITECTURA OPEN-CORE — KINETOPUS-PRO

## Frontera de Desacoplamiento
`KineTopus-Pro` consume `kinetopus-engine` exclusivamente a través de `kinetopus_pro/engine_bridge.py`:

- **Dependencias Upstream (`kinetopus-engine`):**
  - `src.ui.market_loader.MarketLoader`
  - `src.quant_engine.sensor.SpectralAnalyzer`
  - `src.quant_engine.blender.ContinuousBlender`
  - `src.quant_engine.nervous.RegimeShiftDetector`
  - `src.quant_engine.physics.PhysicsDiscoverer`
  - `src.quant_engine.symbolic.SymbolicTranslator`
  - `src.quant_engine.auto_tuner.CUSUMAutoTuner`
- **Aislamiento de Namespace:** El paquete propietario reside en `kinetopus_pro/`, evitando colisiones con `src/` del motor científico y permitiendo la coexistencia editable con `pip install -e`.

## Flujo de Ejecución (`kinetopus_pro.headless_pipeline`)
1. **Ingesta & Ventana Activa:** Recorta primero a `context_window` (por defecto `1000` velas) y normaliza retornos/volumen in-window para garantizar paridad exacta con `CUSUMAutoTuner` y `WalkForwardEvaluator`.
2. **Calibración & Autopilot 2D:** Calcula `k*` óptimo y rescata tolerancias (`0.0005`, `0.0001`, `0.00005`) si el régimen activo detona inestabilidad con $R^2 \ge 0.40$.
3. **Integración Espectral & Doble Sello:** Resuelve EDOs lineales `2x2` analíticamente en `< 1 ms`, ejecuta Ljung-Box sobre residuos y corre Mini Walk-Forward causal (`~10` cortes OOS) calibrando `k` In-Sample por cada corte.
4. **Telemetría & Renderizado:** Exporta `telemetry.json` puro y `dashboard.png` (`Matplotlib Agg`) con variedad de precio re-anclada por régimen y atractor de fase homogéneo.
