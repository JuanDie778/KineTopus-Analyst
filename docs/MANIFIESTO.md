# MANIFIESTO DEL PROYECTO: KINETOPUS-ANALYST

> **Norte Estratégico del Producto:** Convertir la teoría de Física Computacional Financiera de **KineTopus Engine** en un **servicio e indicador cuantitativo real, útil, intuitivo, portable y accesible** para analistas técnicos, plataformas financieras y público general.

---

## 1. Propósito y Norte del Proyecto (`De Paper Científico a Servicio Real`)

**KineTopus-Analyst** (paquete `kinetopus_pro`) es la capa de producto y servicio construida en arquitectura Open-Core sobre el motor científico público **KineTopus Engine** (preprint formal en SSRN / Zenodo bajo licencia `Apache-2.0`).

Mientras `KineTopus Engine` demuestra en el ámbito académico que las series financieras esconden dinámicas continuas analizables mediante **FFT**, **Splines $C^2$**, **CUSUM**, descubrimiento simbólico de EDOs (**SINDy**) y proyección estocástica (**Euler-Maruyama**), **KineTopus-Analyst** nace con una misión distinta y complementaria:

* **Demostrar aplicabilidad y valor práctico:** Sacar el motor del entorno teórico/experimental para convertirlo en una herramienta que resuelva necesidades concretas del mercado.
* **Operar como un servicio ofrecido por KineTopus Engine:** Traducir ecuaciones diferenciales, derivadas y atractores en lecturas accionables que un analista, un inversor o una plataforma externa puedan consumir con naturalidad.

---

## 2. Mentalidad Producto-Cliente (`Pensar como quien consume el servicio`)

Todo el desarrollo técnico, visual y agéntico de este proyecto debe diseñarse **poniéndonos en los zapatos del cliente final que va a consumir el servicio**.

El rigor matemático es condición necesaria, pero no suficiente. Un servicio genera adopción y necesidad real únicamente cuando responde con claridad a las preguntas operativas del usuario:
1. **¿Este activo está gobernado por su propia inercia física o dominado por ruido y shocks exógenos?**
2. **¿La dinámica vigente está acelerando, agotándose o cerca de un punto de giro?**
3. **¿Dónde están exactamente los niveles matemáticos donde el régimen actual queda invalidado?**

Si un cálculo no ayuda a decidir mejor o exige descifrar jerga innecesaria, el producto aún no está terminado.

---

## 3. Estándares de Calidad del Servicio (Los 5 Pilares)

La calidad de **KineTopus-Analyst** se mide bajo cinco atributos irrenunciables:

1. **Utilidad Real como Indicador Técnico:**
   * Funcionar como un indicador estructural y radar de regímenes genuinamente útil para el análisis técnico e inversión (estado del régimen, zonas de giro e inflexión cinemática, fronteras de ruptura CUSUM y cono probabilístico $P_5\text{–}P_{95}$), elevando el análisis tradicional con métricas objetivas sin sesgo subjetivo.
2. **Sencillez e Intuición:**
   * Complejidad matemática por dentro; claridad inmediata por fuera.
   * La salida visual y ejecutiva debe leerse en segundos, sin obligar al usuario a dominar ecuaciones diferenciales para aprovechar el diagnóstico.
3. **Comodidad (*Zero-Friction*):**
   * Experiencia lista para usar (*plug-and-play*): calibración automática de deriva (`k*`), rescate de suavizado (*Autopilot 2D*), validación fuera de muestra incorporada y síntesis contextual automatizada en un único flujo.
4. **Portabilidad y Ligereza:**
   * Arquitectura desacoplada, rápida y liviana (`Local-First`, diseño consciente de memoria $\le 16\text{ GB}$ RAM), pensada para viajar sin fricción como CLI, librería Python, telemetría JSON/API, servidor MCP, widget gráfico o indicador embebible.
5. **Accesibilidad:**
   * Fácil de acceder técnica y cognitivamente desde distintos canales de consumo y niveles de experiencia, eliminando barreras tanto de infraestructura como de interpretación.

---

## 4. Público y Segmentos Objetivo (`Targets`)

El servicio está orientado a tres horizontes complementarios:

* **Analistas Técnicos, Traders e Inversores:**
  * Profesionales e independientes que necesitan un indicador de régimen libre de sesgo emocional para filtrar activos operables con coherencia física, vigilar la salud de la tendencia y definir niveles matemáticos de invalidación de riesgo.
* **Plataformas Financieras y Empresas B2B (ej. *TradingView*, *Investing.com*, brókers, terminales y fintechs):**
  * Proveer la inteligencia de `KineTopus Engine` como servicio integrable (API/feeds de telemetría de regímenes, indicadores propietarios, widgets interactivos o reportes enriquecidos automatizados) que aporte diferenciación técnica real dentro de sus propios ecosistemas.
* **Público General y Vitrina de Innovación Aplicada:**
  * Acercar y mostrar de forma abierta, visual y comprensible de qué es capaz `KineTopus Engine`, evidenciando cómo una investigación teórica de física computacional puede transformarse en herramientas cotidianas de utilidad tangible.

---

## 5. Principios Inquebrantables de Gobernanza (Ciencia + Producto)

1. **Honestidad Epistémica antes que Sobre-Operar:**
   * El servicio protege al usuario advirtiendo explícitamente cuando la inercia interna pierde validez frente a catalizadores macroeconómicos mediante el **Doble Sello de Fiabilidad** (`Ljung-Box` + `Mini Walk-Forward OOS`, incluyendo la *Alerta Caso GLD* cuando el acierto fuera de muestra cae bajo el umbral operable).
2. **Caja Blanca sin Alucinaciones:**
   * Cero cajas negras opacas y cero cifras inventadas. La capa de IA y los reportes traducen fielmente las matrices, ecuaciones y geometrías calculadas por el motor, conectando únicamente los residuos o quiebres con contexto verificable del mundo real.
3. **Filtro Norte de Desarrollo:**
   * Antes de diseñar o implementar cualquier nueva característica, todo cambio debe superar tres preguntas de control:
     1. *¿Le aporta utilidad directa al analista, inversor, plataforma o usuario que lo consume?*
     2. *¿Hace el servicio más sencillo, intuitivo y cómodo?*
     3. *¿Mantiene o mejora su portabilidad y accesibilidad como producto/servicio?*
