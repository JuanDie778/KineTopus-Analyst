# Plantilla Estándar de Informe Multi-Lente de Alto Impacto (Hito 2)

Usa esta estructura exacta dividida en **dos partes** (ejecutiva intuitiva primero, argumentación técnica profunda después) tanto para el **Artifact** como para `reports/<TICKER>/<TIMESTAMP>/analysis.md`. Escapa siempre el signo de moneda como `\$` fuera de fórmulas matemáticas. Sin avisos legales ni restricciones artificiales de tono por ahora (uso interno).

---

# PARTE 1 — Ficha Ejecutiva de 1 Minuto (Lectura Rápida y Sin Jerga)

## 1. Titular y Semáforo de Confluencia
* **Titular en una sola frase directa:** Qué está haciendo el activo y cuál es el mensaje principal hoy.
* **Bloque de Semáforo (`> [!IMPORTANT]` / `> [!WARNING]` / `> [!CAUTION]`):**
  * **Confianza Física Global:** `ALTA` / `MEDIA` / `BAJA_CAUTELA` / `NULA_O_DEGRADADA` (recordando el tope en `BAJA_CAUTELA` si la lente de `2000v` no aprueba el sello o es `N/D`).
  * **Fondo (`2000v`) · Confirmación (`1000v`) · Timing (`500v`):** Estado claro en 1 línea por nivel.

## 2. Las 5 Preguntas Clave (1–2 líneas por respuesta, lenguaje llano para cualquier persona)
1. **¿Hacia dónde va en el fondo, a medio plazo y a corto plazo?**
2. **¿Es fiable esta lectura hoy?** *(explicar en lenguaje cotidiano si el activo está respetando su propia inercia o si está movido por noticias externas).*
3. **¿Qué niveles de precio importan de verdad?** *(pivotes actuales y fronteras alcistas/bajistas donde cambia el escenario).*
4. **¿Qué rango de precios esperar a 1 semana, 1 mes y 3 meses?** *(usar `t+5`/`t+21`/`t+63` en acciones/ETFs de ~252 sesiones y `t+7`/`t+30`/`t+90` en cripto 24/7, indicando centro y banda razonable `P25–P75`).*
5. **¿Qué podría romper este escenario?** *(catalizadores próximos y nivel exacto de ruptura).*

## 3. Gráfico Principal de Confluencia Multi-Lente
* Incrustar `confluence.png` (ruta absoluta del directorio de artefactos en el Artifact; `./confluence.png` en `analysis.md`).

## 4. Tabla Ejecutiva de Niveles Clave y Rangos Esperados
* Tabla compacta y limpia con: **Precio Actual**, **Invalidación Bajista / Ruptura Alcista**, **Rango 1 Semana**, **Rango 1 Mes** y **Rango 3 Meses**.

## 5. Los 3 Insights de Mayor Impacto
* Exactamente **3 viñetas cortas y contundentes** con los hallazgos más valiosos del análisis (lo que un stakeholder o trader debe llevarse en la cabeza).

---

# PARTE 2 — Análisis Técnico, Físico y Argumentativo Detallado

## 6. Jerarquía Multi-Lente (`2000v` → `1000v` → `500v`) y Doble Sello Estricto
* Tabla comparativa completa de las 3 lentes:
  * Columnas: `Lente / Rol`, `Rango de Fechas`, `Calibración (k* / tol)`, `Dirección y Cuadrante`, `Brecha Precio vs Spline`, `SINDy R²`, `Ljung-Box (p)`, `Walk-Forward Estricto (HR% y Cortes Efectivos)`, `Veredicto del Sello`.
* Explicación argumentada de cómo opera la jerarquía fija en este activo concreto (por qué la lente larga dicta o deja indeterminado el fondo sin ser reemplazada por la media, cómo confirma `1000v` y qué matiz táctico aporta `500v`). Mentionar si la descarga escaló automáticamente de `10y` a `max`.

## 7. Auditoría Visual Escalonada y Cruce "Lo que veo vs. Lo que dice el JSON"
* Mostrar los dashboards completos de 6 paneles de las lentes disponibles (en el Artifact usar un bloque ````carousel` con `<!-- slide -->` para navegar cómodamente entre `2000v`, `1000v` y `500v`; en `analysis.md` enlazar/incrustar `./lens_2000/dashboard.png`, `./lens_1000/dashboard.png`, `./lens_500/dashboard.png`). Indicar si fue necesario abrir algún panel individual de alta resolución (`panels/01..06.png`).
* **Tabla/Bloque Obligatorio — Cruce Visual vs. Telemetría JSON:**
  * Contrastar panel por panel (`Confluencia`, `Zoom Táctico 120v`, `Derivadas dr/dt y d²r/dt²`, `Atractor con flechas`, `Tensión y Pico Máximo CUSUM`) lo que muestra la geometría visual frente a las cifras del JSON, **declarando explícitamente cualquier discrepancia o matiz visual** (ej. caída reciente de velas crudas bajo un spline secular alcista, compresión del cono, cuasi-rupturas CUSUM previas).

## 8. Física de Caja Blanca, Cinemática y Conos por Escala
* Ecuaciones diferenciales acopladas ($\mathrm{d}r/\mathrm{d}t$ y $\mathrm{d}V/\mathrm{d}t$) en LaTeX (`$$...$$`) de las lentes relevantes, traduciendo físicamente el signo y magnitud de cada término (deriva basal, amortiguamiento elástico de retorno, empuje o absorción por volumen, autovalores de estabilidad y período intrínseco).
* Fechas y precios exactos de los giros $\dot{r}=0$ e inflexiones $\ddot{r}=0$, sentido de rotación en el espacio de fase y tabla detallada de hitos del cono Monte Carlo (`P5`, `P25`, `P50`, `P75`, `P95`, $F(t)$ y *Skew*) junto con las fronteras de invalidación CUSUM a 1 vela por lente.

## 9. Forense CUSUM, Catalizadores y Contraste con el Consenso Tradicional (Web Citada)
* **Forense Histórico y Catalizadores Próximos:** Qué evento real originó los regímenes/picos CUSUM y qué citas macro/corporativas próximas amenazan las bandas de invalidación.
* **Tabla Comparativa: KineTopus Multi-Lente vs. Consenso de Analistas Tradicionales (Fuentes Web Citadas):**
  * Comparar niveles de soporte, resistencia/objetivos, sesgo de tendencia (largo vs. corto plazo) y lectura de flujos/volumen frente a analistas y casas de análisis reales consultadas en la web (citando cada fuente con enlace), calificando el **Grado de Convergencia** (`Alta`, `Parcial`, `Divergente`) y explicando por qué coinciden o difieren.

## 10. Límites de Esta Lectura
* Cerrar siempre con total transparencia enumerando las limitaciones específicas del diagnóstico actual (ej. resolución temporal de `500v` frente a movimientos de pocas semanas, ausencia de mechas `High`/`Low` y liquidez horizontal del libro de órdenes, peso de factores exógenos fuera de `(r, V)`, número de cortes OOS efectivos, etc.).
