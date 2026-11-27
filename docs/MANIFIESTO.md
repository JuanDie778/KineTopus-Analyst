🌐 **Español** | [English](en/MANIFESTO.md)

# MANIFIESTO DEL PROYECTO: KINETOPUS-ANALYST

> **Norte Estratégico del Producto:** Transformar la física computacional de [**KineTopus-Engine**](https://github.com/JuanDie778/KineTopus-Engine) en un **Microscopio de Espacio de Fases 2D e instrumento de navegación de riesgo** — intuitivo, portable y honesto — diseñado para ver la dinámica interna que una pantalla de precios en 1D oculta.

---

## 1. Propósito y Descubrimiento Central (`De Sombra 1D a Microscopio 2D`)

**KineTopus-Analyst** (`kinetopus_pro`) es la capa de producto y servicio construida en arquitectura Open-Core sobre el motor científico público [**KineTopus-Engine**](https://github.com/JuanDie778/KineTopus-Engine) ([SSRN Preprint 7431018](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7431018) · [Zenodo DOI](https://doi.org/10.5281/zenodo.24166175), licencia `Apache-2.0`).

Mientras los primeros desarrollos exploraron la extrapolación multi-lente de curvas de precio, el **Gran Estudio v3 (`26,294` instantáneas causales sobre `27` series, `2000–2026`, con `15` mercados vírgenes)** reveló dónde aporta KineTopus un valor práctico genuino y diferencial: **al abrir la segunda dimensión (`Eje X = Volumen normalizado Vz`, `Eje Y = Retorno suavizado %`) mediante el Atractor de Fase 2D sin mirar jamás el futuro.**

En lugar de competir como otra bola de cristal que adivina precios a meses vista, **KineTopus-Analyst** existe para responder tres preguntas estructurales que los indicadores clásicos en 1D (`OBV`, `CMF`, `AR(1)`) dejan invisibles:
1. **¿Quién lleva el volante (`Lz`)?** ¿Gira el mercado en **sentido antihorario (`Lz > 0`)** —acumulación paciente donde el volumen antecede al precio, como el `S&P 500` (`79%`)— o en **sentido horario (`Lz < 0`)** —persecución reactiva donde el precio salta primero, como `Bitcoin` (`33%`), `Oro` (`36%`) o `Tesla` (`39%`)?
2. **¿La órbita está contenida o escapando (`Fitzgibbon`)?** ¿Dibuja una **elipse cerrada** (`3` veces más estable en el `100%` de `25/25` mercados diarios) o se abre en una **hipérbola de eyección**?
3. **¿Cuánta fragilidad interna acumula el sistema (`Re(λ)`)?** ¿La inestabilidad de Lyapunov (`Re(λ) > +0.010 d⁻¹`) anticipa vulnerabilidad local antes de un desplome (`ROC-AUC = 0.603` vs `0.473` de `Scheffer AR(1)` en `166` caídas severas) para modular exposición a tiempo?

---

## 2. Estándares de Calidad del Servicio (Los 5 Pilares)

La calidad de **KineTopus-Analyst** se mide bajo cinco pilares irrenunciables:

1. **Utilidad Real como Instrumento de Navegación y Riesgo:**
   * Operar como un panel de diagnóstico de espacio de fases y termómetro de fragilidad sobre posiciones abiertas (sostener con serenidad cuando la elipse gira antihorario; recortar riesgo/apalancamiento a la mitad cuando vira a horario y la órbita se abre en rojo, reduciendo drawdown máximo en `8/8` criptoactivos), junto con detección causal de quiebres (`CUSUM`).
2. **Sencillez e Intuición:**
   * Rigor diferencial (`Splines C²`, `SINDy`, `Fitzgibbon`, `Lyapunov`) por dentro; lectura geométrica inmediata en cuatro estaciones por fuera, comprensible en segundos sin descifrar ecuaciones crudas.
3. **Comodidad (*Zero-Friction*):**
   * Flujo reproducible *Local-First* desde un comando (`kinetopus-analyze`), con calibración automática (`CUSUMAutoTuner`), rescate numérico *Autopilot 2D* y reportes interactivos offline.
4. **Portabilidad y Ligereza:**
   * Arquitectura desacoplada pensada para equipos de `≤ 16 GB` RAM (`np.float64` `C_CONTIGUOUS`) capaz de entregarse como CLI, `report.html` autocontenido, contrato JSON (`kinetopus.indicator.v1`), widget SVG `< 35 KB`, TradingView Pine Script v5, API `FastAPI` y servidor `MCP`.
5. **Accesibilidad:**
   * Traducir física compleja en visualizaciones limpias y comparables para analistas, desarrolladores y público curioso por igual.

---

## 3. Público y Segmentos Objetivo (`Targets`)

* **Analistas Cuantitativos, Gestores e Inversores:** Un microscopio de riesgo en 2D para distinguir rotación paciente de euforia reactiva y modular exposición ante fracturas internas antes del titular.
* **Plataformas Financieras y Socios B2B:** Telemetría de espacio de fases, widgets vectoriales `< 35 KB`, alertas deduplicadas y feeds HTTP integrables sobre terminales, brókers y portales.
* **Comunidad Científica y Divulgación:** Vitrina abierta y auditada que demuestra con `26,294` cortes históricos reales qué ve un sistema dinámico continuo cuando deja de mirar sombras 1D.

---

## 4. Honestidad Epistémica y Límites Explícitos

Un microscopio serio demuestra su rigor enseñando también lo que **no** puede ver:
1. **No es una bola de cristal ante choques exógenos:** Antes del crash del COVID (`12 de febrero de 2020`), el `S&P 500` dibujaba una elipse tranquila porque dentro del libro de órdenes aún no había fractura interna; la geometría mide fragilidad endógena del capital, jamás adivina pandemias ni noticias imprevistas.
2. **Respeto a los horizontes cortos de los splines:** Los bordes `not-a-knot` de un spline cúbico solo sostienen curvatura unos pocos días libres, nunca a meses vista; el valor central del producto reside en el **diagnóstico presente del atractor 2D y su estabilidad**, no en prometer precios lejanos deterministas.
3. **Complementariedad frente a crisis largas (`2008`):** Como regla total de mercado, filtros lentos (`SMA-200`, `VolTarget`) protegen mejor en mercados bajistas prolongados; el microscopio 2D brilla como **sismógrafo local y modulador de riesgo**.
