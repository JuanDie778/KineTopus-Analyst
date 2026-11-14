# KineTopus-Analyst

**Producto y Servicio Cuantitativo de Caja Blanca** construido en arquitectura **Open-Core** sobre el motor científico público `kinetopus-engine` (`Apache-2.0`). Incluye suite *headless*, radar de regímenes físicos, sellos de fiabilidad empírica, renderizador multipanel, CLI y analista agéntico (`kinetopus_pro`).

> 📖 **Norte del Proyecto:** Consulta el documento rector completo en [docs/MANIFIESTO.md](docs/MANIFIESTO.md).

---

## Visión de Producto y Norte Estratégico

**KineTopus-Analyst** nace para llevar a la práctica las capacidades teóricas del paper científico de `KineTopus Engine`, transformándolo en un **servicio e indicador cuantitativo accionable** diseñado desde la perspectiva del cliente que lo consume.

### Los 5 Pilares de Calidad del Servicio
- **Utilidad Real como Indicador Técnico:** Diagnóstico objetivo de régimen, puntos de giro e inflexión cinemática, cono estocástico ($P_5\text{–}P_{95}$) y niveles matemáticos de invalidación CUSUM.
- **Sencillez e Intuición:** Rigor físico por dentro, lectura clara y directa por fuera en segundos.
- **Comodidad (*Zero-Friction*):** Auto-calibración (`k*`, *Autopilot 2D*), doble sello de validez y síntesis contextual listos sin configuración manual pesada.
- **Portabilidad y Ligereza:** Núcleo desacoplado, `Local-First` ($\le 16\text{ GB}$ RAM) y preparado para viajar como CLI, paquete Python, API/JSON, MCP o indicador embebible.
- **Accesibilidad:** Diseñado para consumirse sin barreras técnicas ni cognitivas en múltiples canales.

### Segmentos Objetivo (`Targets`)
1. **Analistas Técnicos, Traders e Inversores:** Radar estructural sin sesgo para filtrar activos operables y gestionar invalidaciones de régimen.
2. **Plataformas Financieras y Empresas B2B:** Integración portable (indicadores, feeds JSON/API, widgets o reportes) para ecosistemas como *TradingView*, *Investing.com*, brókers y fintechs.
3. **Público General:** Vitrina accesible y comprensible que demuestra el valor aplicado del motor matemático original.

---

## Arquitectura Open-Core

- **Núcleo Público (`kinetopus-engine`):** Transformación Discreto-a-Continuo (`FFT` + Splines $C^2$), detección de quiebres estructurales (`CUSUM`), extracción simbólica de EDOs (`PySINDy` STLSQ) y simulación estocástica (`Euler-Maruyama`).
- **Capa Propietaria (`kinetopus_pro`):**
  - Orquestador *headless* tipado con calibración automática (`CUSUMAutoTuner` + *Autopilot 2D*).
  - **Doble Sello de Fiabilidad Física:** Test de ruido blanco `Ljung-Box` + **Mini Walk-Forward OOS causal** (clasificación `COHERENTE_INERCIAL` vs. `EXOGENO_FUNDAMENTALISTA` / *Alerta Caso GLD*).
  - Solver espectral analítico `2x2` sin bloqueos + forense de quiebres CUSUM e invalidación a 1 vela.
  - Renderizador estático multiescala de 5 paneles (`Matplotlib Agg`).
  - CLI reproducible (`kinetopus-analyze`) y Skill agéntica versionada (`.agent/skills/kinetopus-analyst/`).

## Mapa de Documentación

- [docs/MANIFIESTO.md](docs/MANIFIESTO.md) — Visión de producto/servicio, pilares de calidad, targets y filtro norte.
- [docs/ARCHITECTURE_PRO.md](docs/ARCHITECTURE_PRO.md) — Frontera Open-Core (`engine_bridge.py`) y flujo de ejecución *headless*.
- [docs/ROADMAP_PRO.md](docs/ROADMAP_PRO.md) — Hitos de evolución hacia Doble Lente, Escáner Multi-Activo y Empaquetado de Servicio.

## Instalación Local (Modo Editable Open-Core)

```powershell
# 1. Instalar librería científica pública en modo editable
pip install --no-build-isolation --no-deps -e "..\KineTopus Engine"

# 2. Instalar KineTopus-Analyst (paquete kinetopus_pro) en modo editable
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
