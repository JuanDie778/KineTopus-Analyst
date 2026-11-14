# KineTopus-Pro

**Suite Cuantitativa Headless, Radar de Regímenes Físicos y Analista Agéntico** construida en arquitectura **Open-Core** sobre el motor científico público `kinetopus-engine` (`Apache-2.0`).

---

## Arquitectura Open-Core

- **Núcleo Público (`kinetopus-engine`):** Transformación Discreto-a-Continuo (`FFT` + Splines $C^2$), detección de quiebres estructurales (`CUSUM`), extracción simbólica de EDOs (`PySINDy` STLSQ) y simulación estocástica (`Euler-Maruyama`).
- **Capa Propietaria (`kinetopus-pro`):**
  - Orquestador *headless* tipado con calibración automática (`CUSUMAutoTuner` + *Autopilot 2D*).
  - **Doble Sello de Fiabilidad Física:** Test de ruido blanco `Ljung-Box` + **Mini Walk-Forward OOS causal** (clasificación `COHERENTE_INERCIAL` vs. `EXOGENO_FUNDAMENTALISTA` / *Alerta Caso GLD*).
  - Solver espectral analítico `2x2` sin bloqueos + forense de quiebres CUSUM e invalidación a 1 vela.
  - Renderizador estático multiescala de 5 paneles (`Matplotlib Agg`).
  - CLI reproducible (`kinetopus-analyze`) y Skill agéntica versionada (`.agent/skills/kinetopus-analyst/`).

## Instalación Local (Modo Editable Open-Core)

```powershell
# 1. Instalar librería científica pública en modo editable
pip install --no-build-isolation --no-deps -e "..\KineTopus Engine"

# 2. Instalar KineTopus-Pro en modo editable
pip install --no-build-isolation --no-deps -e .
```

## Uso Rápido (CLI)

```powershell
kinetopus-analyze --ticker "BTC-USD" --period 5y --interval 1d
# o vía módulo Python:
python -m kinetopus_pro.cli --ticker "BTC-USD" --period 5y --interval 1d
```

Los artefactos auditables se guardan en `reports/<TICKER>/<TIMESTAMP>/` (`telemetry.json`, `dashboard.png` y opcionalmente `analysis.md`).

## Tests de Auditoría

```powershell
pytest tests/test_headless_pipeline.py -v -W ignore::UserWarning
```
