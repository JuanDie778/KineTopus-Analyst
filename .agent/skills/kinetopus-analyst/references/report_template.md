# Plantilla Estándar de Dictamen Cuantitativo KineTopus

Usa esta estructura exacta tanto para el **Artifact** presentado al usuario como para la copia persistente en `reports/<TICKER>/<TIMESTAMP>/analysis.md`:

---

## 1. Encabezado y Ficha Ejecutiva (KPIs + Sello de Fiabilidad)
* Título con `<TICKER>`, temporalidad (`interval` / `period`), fecha de última vela y precio de cierre (`\$...`).
* Alert GitHub (`> [!IMPORTANT]`, `> [!WARNING]` o `> [!CAUTION]`) con el **Veredicto Sintético**:
  * **Confianza Física Global:** `ALTA` / `MEDIA` / `BAJA_CAUTELA` / `NULA_O_DEGRADADA` y su justificación.
  * **Sello Empírico (Mini Walk-Forward OOS):** Clase (`COHERENTE_INERCIAL`, `TRANSICIONAL_BORDE` o `EXOGENO_FUNDAMENTALISTA`), Hit Ratio OOS consenso, validez matemática y Alpha vs. Naive.
  * **Sello Estadístico (Ljung-Box):** Veredicto y $p$-value de referencia sobre los residuos.
* Tabla resumen de los **4 KPIs Ejecutivos** + parámetros calibrados (`k`, `smooth_tol`, y si actuó *Autopilot 2D*).

## 2. Panel Visual de Telemetría (5 Capas)
* Incrustar la imagen `dashboard.png` (apuntando a la copia en `<Artifact Directory Path>` dentro del Artifact, y a `./dashboard.png` dentro de `reports/.../analysis.md`).
* Síntesis visual breve de lo observado directamente en los 5 paneles.

## 3. Física de Caja Blanca (Ecuaciones SINDy y Lectura Mecánica)
* Mostrar en bloque LaTeX (`$$...$$`) el sistema acoplado descubierto en el régimen activo ($\mathrm{d}r/\mathrm{d}t$ y $\mathrm{d}V/\mathrm{d}t$), junto con $R^2$, MSE del Spline y $\sigma_r$.
* **Traducción Física-Financiera término a término:** explicar qué fuerza representa cada coeficiente activo (deriva constante, retroalimentación o amortiguamiento de $r$, empuje o fricción de volumen $V$, y amortiguador hidrodinámico $\lambda = 0.99$).
* Incluir la solución analítica general de `SymPy` (o nota de sistema no lineal si aplica) y los períodos dominantes detectados por `FFT`.

## 4. Geometría Cinemática y Topología del Espacio de Fase
* **Cuadrante Cinemático ($\dot{r}$ vs. $\ddot{r}$):** explicar si el movimiento está acelerando o frenando, citando fechas y precios exactos de los últimos giros de velocidad ($\dot{r}=0$) e inflexiones de aceleración ($\ddot{r}=0$).
* **Atractor de Espacio de Fase ($V_z$ vs. $\tilde{r}_{\%}$):** interpretar la clase topológica (`COMPRESION_EQUILIBRIO_CENTRAL`, `CICLO_ORBITAL_ACTIVO`, `ESPIRAL_AMORTIGUADA_CONVERGENTE` o `ESCAPE_RUPTURA_CENTRIFUGA`) y el radio orbital relativo.

## 5. Proyección Estocástica ($t+N$) y Niveles de Invalidación CUSUM
* Tabla completa de hitos (`t+1`, `t+5`, `t+15`, `t+30`, `t+60`, `t+100`, `t+150`) con:
  * Trayectoria Determinista $F(t)$ y retorno `%`.
  * Cono Monte Carlo (`P5`, `P25`, `P50`, `P75`, `P95`), amplitud y asimetría (*Upside/Downside Skew*).
* **Fronteras Matemáticas de Invalidación (1 vela):** precios exactos al alza y a la baja (`upside_regime_break_price` / `downside_regime_break_price`) donde la tensión CUSUM superaría $H=5.0$ y mataría la validez de la EDO actual.

## 6. Forense de Quiebres CUSUM y Radar de Catalizadores (Contexto Real)
* **Nacimiento del Régimen Vigente:** vincular la fecha exacta `active_regime_start_date` (y anomalías residuales clave) con los eventos reales encontrados en web que originaron la inercia actual.
* **Radar de Catalizadores y Riesgo Exógeno:** eventos macro, sectoriales o corporativos próximos que podrían actuar como fuerza externa y perforar las bandas de invalidación CUSUM.
* **Conclusión Operativa de Caja Blanca:** síntesis accionable integrando física + geometría + contexto.
