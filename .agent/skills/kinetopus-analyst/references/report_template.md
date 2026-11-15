# Esquema `narrative.json` y Estándar Geométrico de Informe (`v0.3.1`)

En `v0.3.1`, **`KinetopusReportBuilder` ensambla programáticamente tanto `report.html` como `analysis.md`**, inyectando el 100% de precios, distancias a las 3 curvas, ajuste Curva-Precio (`R²`, `MAPE`), rangos `P25–P75`, probabilidades de primer toque (`touch_probability_pct`) y métricas directamente desde `confluence.json` y `lens_<W>/telemetry.json`.

El agente **nunca transcribe tablas numéricas a mano**: redacta únicamente `<report_dir>/narrative.json` y ejecuta `--render-report <report_dir>`.

---

## 1. Esquema Cualitativo `narrative.json` (Etapa 2)

```json
{
  "headline": "Titular ejecutivo geométrico directo en 1 frase clara y accionable en español.",
  "scenarios_catalysts": {
    "base": "Qué condición de flujo o volumen mantiene al precio gravitando dentro del corredor probable P25–P75 hacia t+150.",
    "bullish": "Qué catalizador impulsaría una expansión sostenida sobre el cuartil P75 hacia la cola alcista P90–P95.",
    "bearish": "Qué evento adverso perforaría el soporte P25 empujando hacia la banda inferior P5–P10."
  },
  "top_insights": [
    {
      "title": "Idea clave 1 (Geometría y distancia a las 3 curvas)",
      "body": "Lectura directa de la posición del precio respecto a 2000v (Cian), 1000v (Ámbar) y 500v (Violeta)."
    },
    {
      "title": "Idea clave 2 (Confluencia t+150 y cuartiles P25–P75)",
      "body": "Lectura sobre la convergencia o divergencia entre las 3 proyecciones simultáneas a t+150."
    },
    {
      "title": "Idea clave 3 (Consenso y riesgo estructural)",
      "body": "Lectura frente al consenso externo citado y los catalizadores históricos."
    }
  ],
  "web_consensus": {
    "convergence_grade": "CONVERGENTE | DIVERGENTE | MIXTA",
    "summary": "Síntesis clara comparando la geometría física de KineTopus frente al consenso actual.",
    "sources": [
      {
        "source_name": "Casa de análisis o medio financiero",
        "date": "YYYY-MM-DD",
        "stance": "Tesis resumida y niveles vigilados por el consenso",
        "url": "https://..."
      }
    ]
  },
  "visual_discrepancies": "Confirmación de paridad visual/JSON tras auditar hero.png y los 3 dashboards (1000v Ámbar, 2000v Cian, 500v Violeta), declarando cualquier matiz visual relevante.",
  "sindy_translation": "Traducción a lenguaje llano de mercado (empuje, fricción elástica, absorción de volumen) de las EDOs acopladas de 1000v.",
  "cusum_catalysts": [
    {
      "date": "YYYY-MM-DD",
      "event": "Catalizador histórico real detrás del quiebre de régimen o pico de tensión CUSUM (Laboratorio 2.5)."
    }
  ],
  "reading_limits": [
    "Las proyecciones t+150 extrapolan la deriva determinista (EDO SINDy o amortiguamiento inercial geométrico) junto con la dispersión empírica de residuos EWMA.",
    "Walk-Forward OOS desactivado por defecto en v0.3.1 (prioridad geométrica; use --audit-oos para auditoría histórica); los choques exógenos reajustan la curvatura mediante detección CUSUM."
  ]
}
```

---

## 2. Arquitectura de 6 + 6 Bloques Generada por el Motor (`v0.3.1`)

Tanto `analysis.md` como las 3 pestañas de `report.html` (*Resumen Ejecutivo*, *Escenarios y Curvas*, *Laboratorio Técnico (3 Lentes)*) siguen esta estructura fija:

### PARTE 1 — Vista Ejecutiva (Lectura Geométrica Clara, Cero Barreras CUSUM de 1 Vela)
1. **Titular Ejecutivo Geométrico en 1 Frase:** Directo a la posición frente a las 3 curvas y proyección `t+150`.
2. **Tarjeta de Régimen y Confianza Geométrica:**
   * Estado humano de 5 categorías (`Impulso alcista`, `Alcista frenando`, `Lateral / Digestión` [`Lateral en máximos` si `>= 95%` del máximo de ventana], `Corrección bajista`, `Caída frenando / Suelo en formación`) + modificador de posición.
   * Lectura simultánea de `1000v` (Ámbar), `2000v` (Cian) y `500v` (Violeta) con ajuste Curva-Precio (`R²`, `MAPE`) y proyección `t+150`.
3. **Gráfico Héroe Interactivo (`hero.png` en MD / Plotly con 100% del historial en `report.html`):**
   * Vista inicial `500v + t+150` con auto-escalado Y limpio, botones `[120v | 500v | 1000v | 2000v | Todo el historial]`, selector `[Cono: 1000v | 2000v | 500v | Sin cono]`, las 3 curvas y sus 3 proyecciones `t+150` simultáneas, cortes históricos limpios y regla lateral derecha sin líneas horizontales CUSUM de 1 vela.
4. **Posición frente a las 3 Curvas y 3 Escenarios Geométricos (`P25/P75`):**
   * Tabla comparativa `2000v · 1000v · 500v` (distancia curva-precio, sesgo `30v`, `R²` curva-precio, `t+150`, cuartiles `P25–P75`) y 3 escenarios (*Base*, *Expansión Alcista*, *Reversión Bajista*) centrados en `P25/P75`.
5. **Tabla de Niveles y Rangos (`1 semana · 1 mes · 3 meses · t+150` + comparativa `2000v`/`500v`):** Sin filas de invalidación CUSUM de 1 vela.
6. **Las 3 Ideas Clave (`top_insights`):** Exactamente 3 puntos accionables.

### PARTE 2 — Laboratorio Técnico (3 Lentes)
1. **Tabla Comparativa de las 3 Lentes:** Curva-Precio `R²`, SINDy `R²`, `t+150`, auditoría OOS (cuando `--audit-oos`), cobertura del cono y lectura.
2. **Contraste con el Consenso de Analistas (Web Citada):** Grado de convergencia, síntesis y tabla con enlaces verificables.
3. **Selector de los 3 Dashboards Técnicos (`1000v Ámbar` · `2000v Cian` · `500v Violeta`) y Paridad Visual/JSON.**
4. **Física de Caja Blanca (EDOs SINDy de `1000v`):** Ecuaciones acopladas + traducción física a lenguaje de mercado.
5. **Forense Histórico CUSUM y Catalizadores:** Registro histórico de rupturas de curva y eventos reales asociados.
6. **Límites de Esta Lectura:** Extrapolación geométrica, activación eventual de amortiguamiento inercial, edad del régimen y opcionalidad `--audit-oos`.
