# KineTopus-Analyst (`v0.3.1`)

**Producto y Servicio Cuantitativo de Caja Blanca (Enfoque Geométrico Puro)** construido en arquitectura **Open-Core** sobre el motor científico público `kinetopus-engine` (`Apache-2.0`). Incluye suite *headless* Multi-Lente (`2000v / 1000v / 500v`), proyección simultánea `t+150` en las tres escalas, cono calibrado de integración simple EWMA, ajuste Curva-Precio explícito, renderizador financiero (`Matplotlib Agg`), entregable interactivo offline (`report.html` + `analysis.md`), CLI en dos etapas y Skill agéntica (`kinetopus_pro`).

> 📖 **Norte del Proyecto:** Consulta el documento rector completo en [docs/MANIFIESTO.md](docs/MANIFIESTO.md).

---

## Visión de Producto y Norte Estratégico

**KineTopus-Analyst** nace para llevar a la práctica las capacidades teóricas del paper científico de `KineTopus Engine`, transformándolo en un **servicio e indicador cuantitativo accionable** diseñado desde la perspectiva del cliente que lo consume.

### Los 5 Pilares de Calidad del Servicio
- **Utilidad Real como Indicador Técnico:** Diagnóstico geométrico Multi-Lente simultáneo (`2000v` Cian, `1000v` Ámbar, `500v` Violeta) proyectando siempre `t+150`, ajuste explícito Curva-Precio (`R²`, `MAPE`), cono calibrado de integración simple EWMA (`P25–P75` y `P5–P95`), taxonomía humana de 5 estados, escenarios con probabilidad de primer toque (*first-passage*) y forense histórico CUSUM (más auditoría Walk-Forward OOS opcional con `--audit-oos`).
- **Sencillez e Intuición:** Rigor físico por dentro, lectura clara y directa por fuera en segundos (`hero.png` limpio en portada + `report.html` interactivo con pestañas ejecutivas y técnicas).
- **Comodidad (*Zero-Friction*):** Descarga única inteligente (`10y` con respaldo automático a `max`), auto-calibración (`k*`), *Autopilot 2D* por estabilidad numérica y flujo dual en 2 etapas sin fricción.
- **Portabilidad y Ligereza:** Núcleo desacoplado, `Local-First` ($\le 16\text{ GB}$ RAM con tensores `np.float64` `C_CONTIGUOUS`) y preparado para viajar como CLI, paquete Python, JSON/NPZ/HTML autocontenido, MCP o indicador embebible.
- **Accesibilidad:** Reportes HTML/Markdown autocontenidos offline sin barras técnicas opacas ni jerga de enums internos.

### Segmentos Objetivo (`Targets`)
1. **Analistas Técnicos, Traders e Inversores:** Radar estructural Multi-Lente para diagnosticar régimen, estiramiento frente a la curva y niveles probables en tres horizontes simultáneos.
2. **Plataformas Financieras y Empresas B2B:** Integración portable (`confluence.json`, feeds JSON/API, widgets o reportes interactivos) para ecosistemas como *TradingView*, *Investing.com*, brókers y fintechs.
3. **Público General:** Vitrina accesible y comprensible que demuestra el valor aplicado del motor matemático original.

---

## Arquitectura Open-Core (`v0.3.1`)

- **Núcleo Público (`kinetopus-engine`):** Transformación Discreto-a-Continuo (`FFT` + Splines $C^2$), detección de quiebres estructurales (`CUSUM`), descubrimiento simbólico de EDOs (`PySINDy` STLSQ) y base de modelado estocástico.
- **Capa Propietaria (`kinetopus_pro` `v0.3.1`):**
  - **Orquestador Multi-Lente Paralelo (`kinetopus_pro/multi_lens.py`):** Evalúa en paralelo (`ProcessPoolExecutor`) tres ventanas (`2000v` Cian Marea Estructural, `1000v` Ámbar Eje Principal y Escenarios, `500v` Violeta Pulso Táctico) sobre descarga única inteligente (`10y` con ampliación automática a `max`). Las 3 lentes proyectan **siempre `t+150` simultáneamente**, sin bloqueos ni vetos automáticos por `SINDy R²` u OOS.
  - **Cono EWMA Calibrado, Curva-Precio y OOS Opcional (`kinetopus_pro/headless_pipeline.py`):** Cono Monte Carlo de integración simple en log-precio (`span=30` EWMA winsorizado por MAD, $N=2,000$ rutas `np.float64` `C_CONTIGUOUS`), métricas explícitas de ajuste Curva-Precio (`R²`, `MAPE`, `RMSE`), 3 escenarios probabilísticos centrados en `P25/P75`, solver espectral analítico `2x2`, rescate *Autopilot 2D* exclusivamente ante inestabilidad numérica o `dr/dt = 0`, test residual `Ljung-Box` y auditoría Walk-Forward OOS opcional (`--audit-oos`).
  - **Renderizador Financiero (`kinetopus_pro/static_renderer.py`):** Gráfico Héroe (`hero.png` / `confluence.png`) con velas OHLC, 3 curvas y 3 proyecciones `t+150` simultáneas, cortes limpios de régimen y regla lateral sin solapes (erradicando barreras horizontales CUSUM de 1 vela en vistas ejecutivas), más **3 dashboards técnicos de 6 paneles** (`2000v / 1000v / 500v`) y **18 paneles individuales**.
  - **Presentación Dual en Dos Etapas (`kinetopus_pro/report_builder.py`):** Etapa 1 persiste `report_bundle.npz` (100% del historial descargado) y genera `report.html` interactivo offline (`plotly.min.js` + Jinja2, Tema Oscuro/Claro, selectores de ventana, cono y los 3 dashboards) junto con `analysis.md`; Etapa 2 (`--render-report`) inyecta 100% de cifras del motor sobre el texto cualitativo de `narrative.json` en `< 0.5 s`.
  - **CLI Reproducible (`kinetopus-analyze`) y Skill Agéntica:** Versionados con protocolo de cero alucinaciones numéricas en `.agent/skills/kinetopus-analyst/`.

## Mapa de Documentación

- [docs/MANIFIESTO.md](docs/MANIFIESTO.md) — Visión de producto/servicio, pilares de calidad, targets y filtro norte.
- [docs/ARCHITECTURE_PRO.md](docs/ARCHITECTURE_PRO.md) — Frontera Open-Core (`engine_bridge.py`), arquitectura geométrica `v0.3.1` y flujo en dos etapas.
- [docs/ROADMAP_PRO.md](docs/ROADMAP_PRO.md) — Hitos completados (`v0.1.0` → `v0.3.1`) y evolución hacia Hito 3 (Escáner Multi-Activo/Multi-Serie) y Hito 4.

## Instalación Local (Modo Editable Open-Core)

```powershell
# 1. Instalar librería científica pública en modo editable
pip install --no-build-isolation --no-deps -e "..\KineTopus Engine"

# 2. Instalar KineTopus-Analyst (paquete kinetopus_pro con matplotlib, plotly y Jinja2) en modo editable
pip install --no-build-isolation --no-deps -e .
```

## Uso Rápido (CLI en Dos Etapas)

```powershell
# Etapa 1 (Cuantitativa pura — funciona de extremo a extremo sin IA):
kinetopus-analyze --ticker "BTC-USD" --interval 1d

# Analizar CSV local o activar auditoría Walk-Forward OOS opcional:
python -m kinetopus_pro.cli --csv "datos.csv" --interval 1d
python -m kinetopus_pro.cli --ticker "BTC-USD" --interval 1d --audit-oos

# Etapa 2 (Re-renderizado instantáneo <0.5 s fusionando narrativa cualitativa en narrative.json):
python -m kinetopus_pro.cli --render-report "reports/<TICKER>/<TIMESTAMP>"
```

Los artefactos auditables se guardan en `reports/<TICKER>/<TIMESTAMP>/`: `confluence.json`, `report_bundle.npz`, `hero.png` (`confluence.png`), `report.html`, `analysis.md`, `narrative_template.json` y `lens_{2000,1000,500}/` (`telemetry.json`, `dashboard.png`, `panels/01..06_*.png`).

## Tests de Auditoría

```powershell
pytest tests/ -v -W ignore::UserWarning
```
