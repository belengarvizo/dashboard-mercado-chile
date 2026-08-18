# Dashboard de mercado chileno

Panel que consolida indicadores macroeconómicos del Banco Central de Chile,
todas las acciones del IPSA y benchmarks internacionales en un solo lugar,
actualizado diariamente.

**Dashboard en vivo:** https://dashboard-mercado-chile-production.up.railway.app/

## Qué muestra

El dashboard tiene 9 pestañas:

1. **Brief Premercado** — para revisar antes de que abra la Bolsa de Santiago.
   Sección "Importante": % de cambio de la sesión más reciente de S&P 500,
   cobre, MSCI EM (EEM), Bovespa y el bono UST a 10 años, con flecha y color
   verde/rojo, pensado para leerse en 10 segundos. Justo debajo, el **spread
   2s10s** (UST10Y − UST2Y — UST2Y vía `2YY=F` de Yahoo Finance, ya que no
   existe un ticker "^" clásico para 2 años; verificado con datos reales
   antes de usarlo), marcado en rojo si la curva está invertida (spread
   negativo), con una nota breve y cautelosa sobre su asociación histórica
   con recesiones en EEUU — sin afirmar que sea una predicción garantizada.
   Debajo de eso, un **resumen diario
   generado por IA** (Gemini `gemini-3.6-flash`) con dos secciones — "Panorama
   global" (3-5 puntos) y "Posibles efectos para Chile" (lenguaje cauteloso,
   sin afirmaciones causales categóricas) — armado a partir de esos mismos
   indicadores más los titulares recientes, con un disclaimer visible de que
   es contenido generado por IA. Se genera **una vez al día en el cron**, no
   en cada visita. Los titulares crudos (24-48h de Diario Financiero, La
   Tercera Pulso y Emol Economía) quedan como detalle secundario colapsado,
   agrupados por fecha y enlazados a la fuente original (ver nota sobre las
   fuentes de noticias más abajo).
2. **Indicadores macro** — selector para explorar cualquiera de las series del
   BCCh (ver lista completa más abajo) con su gráfico histórico y último valor.
3. **Acciones IPSA** — gráfico de precios normalizables a base 100; el
   selector permite elegir entre **las 30 acciones del IPSA** (incluida
   LATAM, `LTM.SN`), con las mismas 5 destacadas de siempre (SQM-B, Banco de
   Chile, Falabella, Copec, CMPC) preseleccionadas por defecto. Debajo, un
   **heatmap de desempeño con las 30 acciones del IPSA**: % de cambio
   1D/1W/1M/YTD (coloreado verde/rojo), **volatilidad anualizada** (rolling
   21 días hábiles × √252), **Beta** cruda y **Beta ajustada** (ajuste tipo
   Blume: (2/3) × Beta + (1/3) × 1, tira la beta hacia el "promedio de
   mercado" de largo plazo) contra el mercado chileno (regresión de retornos
   diarios del último año vs el ETF ECH, ver limitación de datos más abajo),
   **costo de capital CAPM** ("CAPM local" y "CAPM + CRP", ver nota sobre
   riesgo país más abajo) y la fecha del último precio real de cada ticker.
   Volatilidad, Beta y CAPM excluyen los días de precio congelado del
   cálculo (ver limitación de datos más abajo) — un retorno de 0% por dato
   repetido no es volatilidad real cero.

   **CAPM y prima de riesgo país (CRP):** "CAPM local" = Rf local (PDBC 14
   días, la tasa libre de riesgo de corto plazo) + Beta × prima de mercado
   local (retorno histórico anualizado del proxy del IPSA menos PDBC).
   "CAPM + CRP" suma el spread entre el **bono BCCh en pesos (BCP) a 10
   años** (tasa de mercado secundario) y el UST10Y — mismo plazo en ambos
   lados, sin descalce. PDBC se mantiene como Rf del CAPM base; el bono a 10
   años se usa únicamente para calcular el CRP, no reemplaza a PDBC. Se
   muestran **ambas versiones a propósito**, porque sumar el spread completo
   puede implicar doble conteo del riesgo país (el Beta y la Rf locales ya
   lo capturan en parte implícitamente). Es una aproximación al estilo
   Damodaran, no el EMBI+ oficial (que requiere una fuente de pago).
4. **Riesgo** — Value at Risk (VaR) histórico y paramétrico, a 95% y 99%, para
   las 5 acciones principales y un portafolio hipotético equiponderado, sobre
   los últimos ~2 años (mismo filtro de días congelados); y una matriz de
   correlación de retornos diarios entre las 30 acciones del IPSA. Nota
   metodológica visible: el VaR histórico asume que el pasado representa el
   riesgo futuro (no garantizado, sobre todo en crisis); el paramétrico asume
   normalidad, que en la práctica suele subestimar eventos extremos (colas
   gordas) — se muestran ambos lado a lado para que la diferencia sea
   visible.

   **Ajuste por liquidez:** el VaR de cada acción individual (no el del
   portafolio) se multiplica por 1,3× si su liquidez cae en el cuartil más
   bajo. La liquidez se mide como el monto transado diario promedio (precio
   × volumen) de los últimos 3 meses, comparado contra las 30 acciones del
   IPSA. Es una **aproximación heurística simplificada**, no un modelo
   riguroso de impacto de mercado ni de profundidad del libro de órdenes.

   También muestra, para las 5 acciones principales, un **histograma de
   retornos diarios con la curva normal superpuesta** (misma media y
   desviación estándar), junto con su **skewness y kurtosis (exceso)** — la
   distancia visible entre el histograma real y la curva normal es evidencia
   directa de las colas gordas que menciona la nota sobre el VaR paramétrico.
5. **7 Magníficas** — AAPL, MSFT, GOOGL, AMZN, NVDA, META y TSLA, normalizadas
   a base 100 para comparar su desempeño relativo.
6. **Benchmark** — el IPSA (vía el ETF ECH, ver nota abajo) comparado con el
   S&P 500, MSCI Emerging Markets (EEM) y el Bovespa, normalizado a base 100.
7. **Event Study TPM** — detecta automáticamente cada cambio de la Tasa de
   Política Monetaria (comparando la serie diaria de la TPM día a día) y mide
   su impacto sobre el tipo de cambio USD/CLP: retorno anormal (AR) y
   acumulado (CAR) en una ventana de -2 a +2 días hábiles alrededor de cada
   evento, estimados contra el retorno normal de los 30 días hábiles previos.
   Muestra el CAAR promedio de todos los eventos con un t-test simple de
   significancia, la tabla de cada evento individual, y un t-test separado del
   CAR contra cero para alzas vs. bajas de tasa (más un test de diferencia de
   medias entre ambos grupos). Las tablas de AAR/CAAR y de alzas/bajas marcan
   cada resultado en **texto verde si p < 0,05 (significativo) o rojo si
   p ≥ 0,05 (no significativo)** — texto en negrita, no fondo de celda, para
   no confundirse con el verde/rojo de fondo que usa el heatmap de
   ganancia/pérdida en "Acciones IPSA" (mismo par de colores, rol visual
   distinto). **Limitación metodológica:** solo detecta cambios efectivos de
   tasa, no las decisiones de "mantener" en cada Reunión de Política
   Monetaria (RPM), porque el dashboard no tiene el calendario de reuniones
   — queda documentado en la propia pestaña.

   **Hallazgo (con los datos hasta la fecha):** de 37 eventos (15 alzas,
   22 bajas), el CAR promedio es negativo tras alzas de TPM (el dólar tiende a
   bajar, el peso se aprecia levemente) y positivo tras bajas (el dólar tiende
   a subir, el peso se deprecia) — dirección **económicamente consistente con
   la teoría de paridad de tasas de interés**. Pero **ningún resultado es
   estadísticamente significativo al 5%**: ni el AAR/CAAR agregado en ningún
   día de la ventana de evento, ni el CAR de alzas o bajas contra cero por
   separado (t=-0,18 y t=1,04 respectivamente), ni la diferencia de medias
   entre ambos grupos (t=-0,91, p=0,37).

   Esa falta de significancia tiene (al menos) dos causas distintas, ambas
   documentadas en la propia pestaña: **(1) poca potencia estadística** — solo
   37 eventos totales, 15/22 por grupo, una muestra chica para detectar un
   efecto salvo que sea muy grande; y **(2) confusión con ciclos monetarios
   globales** — las decisiones de TPM del BCCh suelen coincidir con ciclos
   simultáneos en otros bancos centrales (ej. el BCCh subió tasas en 2021-2022
   al mismo tiempo que la Fed subía las suyas), así que este diseño no puede
   aislar limpiamente el efecto de la decisión local del efecto del ciclo
   global. **"No significativo" no equivale a "no hay efecto"** — solo
   significa que no se puede afirmar con esta muestra y este diseño. Una
   mejora futura sería controlar por el movimiento simultáneo del dólar a
   nivel global (ej. el índice DXY) en la ventana de evento, para aislar
   mejor el componente local del CAR.

8. **Backtester: Estrategia TPM** — backtest hipotético e ilustrativo sobre
   los mismos 37 eventos del Event Study: TPM sube → posición corta en
   USD/CLP, TPM baja → posición larga; entrada al cierre del día del evento,
   salida al cierre 2 días hábiles después, con 8 puntos base de costo de
   transacción por operación. Muestra la curva de equity, retorno total
   acumulado, retorno promedio por trade, % de operaciones ganadoras, Sharpe
   ratio (anualizado por el número de eventos/año) y máximo drawdown. La
   pieza central de rigor es un **test de permutación**: mezcla al azar la
   dirección de los 37 eventos 1.000 veces, corre el mismo backtest con cada
   mezcla, y muestra en qué percentil de esa distribución cae el resultado
   real — para saber si el criterio direccional aporta algo por sobre el
   azar, o si el resultado es indistinguible de simplemente apostar una
   dirección cualquiera en esas mismas fechas. El resultado del percentil se
   marca en **texto verde si cae en el 5% extremo de la distribución
   (distinguible del azar) o rojo si cae en el rango central (indistinguible
   del azar)**, con el mismo criterio visual (texto, no fondo) que las tablas
   de significancia del Event Study.

   **Hallazgo:** el resultado real (-3,75% acumulado en 37 trades, Sharpe
   -0,13) cae en el **percentil ~44 de 1.000 mezclas aleatorias de
   dirección** — indistinguible del azar. Consistente con el hallazgo del
   Event Study: no hay evidencia de que esta estrategia direccional le gane
   al mercado con los datos disponibles.
9. **Momentum IPSA** — estrategia momentum "12-1" de Jegadeesh & Titman
   (1993) sobre las 30 acciones del IPSA: cada fin de mes rankea por retorno
   compuesto de los meses [t-12, t-2] (saltando el mes t-1 más reciente),
   forma portafolios equiponderados "Ganadoras" y "Perdedoras" (10 acciones
   cada uno), los mantiene 1 mes con rebalanceo mensual y 15 puntos base de
   costo de transacción por posición. Muestra la curva de equity del spread
   WML (Ganadoras − Perdedoras), un t-test simple contra cero, la tabla de
   retornos mensuales, y el mismo **test de permutación** que el Backtester
   de TPM — mezcla al azar qué 10+10 acciones son "ganadoras/perdedoras"
   cada mes (preservando fechas y retornos reales), 1.000 veces. Nota
   metodológica visible: distingue este diseño (momentum de corto/mediano
   plazo) de De Bondt & Thaler (1985), que documentan el efecto contrario —
   reversión a **largo plazo** (3-5 años) — dejando claro que ambos
   coexisten en la literatura porque operan en horizontes distintos.

   **Hallazgo:** sobre 49 meses de datos, el WML acumulado es +42,9% (t =
   1,03, p = 0,31 — no significativo al 5%), y el resultado real cae en el
   **percentil 88,5 de 1.000 mezclas aleatorias** — elevado, pero sin cruzar
   el umbral de 95% para considerarse distinguible del azar.

Arriba de las pestañas, y también en la barra lateral, se muestra la fecha y
hora de la última actualización de cada fuente de datos.

## Fuentes de datos

**Banco Central de Chile (API REST, autenticada con `BCCH_TOKEN`):**
- Tipo de cambio observado
- Tasa de política monetaria (TPM)
- IPC (índice)
- IMACEC
- Precio del cobre (USD/oz troy)
- Swap Promedio Cámara nominal (90 días)
- Tasa libre de riesgo CLP (PDBC a 14 días)
- Bono BCCh en pesos (BCP) a 10 años, tasa de mercado secundario — usado
  junto al UST10Y para calcular el CRP (spread plazo contra plazo)

**Yahoo Finance (vía `yfinance`, sin autenticación):**
- Las 30 acciones del índice IPSA
- El ETF ECH (iShares MSCI Chile) — usado como proxy del IPSA para el
  cálculo de Beta y la pestaña Benchmark, porque el índice IPSA no tiene
  ticker propio en Yahoo Finance
- Benchmarks: S&P 500 (`^GSPC`), MSCI Emerging Markets (`EEM`), Bovespa (`^BVSP`)
- Las 7 Magníficas: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
- El bono del Tesoro de EEUU a 10 años (`^TNX`) y a 2 años (`2YY=F` — Yahoo
  no tiene un ticker "^" clásico para 2 años, verificado con datos reales
  antes de usarlo) — se descargan junto con las series del BCCh porque el
  Banco Central no publica tasas de EEUU en su catálogo

**Noticias (vía `feedparser`, RSS):**
- **Diario Financiero** — tiene RSS propio funcionando (`df.cl/noticias/site/list/port/rss.xml`).
- **La Tercera Pulso** y **Emol Economía** — se verificó que **no** tienen un
  feed RSS propio funcionando (La Tercera marca `"rss": null` en toda su
  configuración de sitio; el sistema legado de Emol en `rss.emol.com` está
  caído). Para ambas se usa como sustituto una búsqueda de Google Noticias
  filtrada por sitio (`news.google.com/rss/search?q=site:...`) — funciona y
  trae titulares reales, pero no es el feed oficial del medio.

**Resumen diario con IA (Gemini, vía `google-genai`):** `scripts/generar_brief.py`
arma un prompt con los indicadores de "Importante" y hasta 60 titulares
recientes, y llama a Gemini (`gemini-3.6-flash`, autenticado con
`GEMINI_API_KEY`) para generar el resumen de dos secciones que se muestra en
"Brief Premercado". Se guarda en la tabla `brief_diario` y se regenera una
vez al día en el cron — el dashboard nunca llama a Gemini directamente, solo
lee el resultado ya guardado. (Se pidió originalmente `gemini-2.5-flash`,
pero esa API key ya no tiene acceso a ese modelo — el propio catálogo de
Google devuelve `gemini-3.6-flash` como el flash vigente.)

### ⚠️ Limitación conocida: precios congelados en tickers `.SN`

Yahoo Finance suele repetir el mismo precio de cierre durante varias semanas
para varios tickers de la Bolsa de Santiago (`.SN`) antes de refrescarlo — es
una limitación de su cobertura gratuita para ese mercado, no un bug del
dashboard. Por eso el heatmap de la pestaña "Acciones IPSA" no mira solo la
última fila descargada, sino la fecha del **último cambio de precio real**
para cada ticker. Si esa fecha tiene más de 5 días hábiles de atraso respecto
a hoy, la fila se marca con ⚠️ y se muestra en gris (sin el color verde/rojo
del heatmap), para dejar claro que el % de cambio mostrado para ese ticker en
particular no es confiable.

## Arquitectura de despliegue

- **Base de datos:** PostgreSQL en [Neon](https://neon.tech) (`DATABASE_URL`).
- **App + cron job:** [Railway](https://railway.app), conectado a este repo
  de GitHub.
  - El dashboard (`streamlit run app/dashboard.py`) corre como servicio web
    permanente.
  - Un **cron job diario a las 6:00 AM (hora de Chile)** corre
    `python scripts/actualizar_todo.py`, que descarga las series del BCCh,
    los precios de acciones, los titulares de noticias, y genera el resumen
    diario con Gemini, en un solo paso, antes de que empiece el día bursátil.
    Necesita `GEMINI_API_KEY` configurada como variable de entorno en Railway.

## Estructura del proyecto

```
dashboard-mercado-chile/
├── app/
│   └── dashboard.py            # La app de Streamlit (lo que ves en el navegador)
├── scripts/
│   ├── actualizar_bcch.py      # Descarga series del Banco Central (+ UST10 vía Yahoo)
│   ├── actualizar_acciones.py  # Descarga precios de acciones vía Yahoo Finance
│   ├── actualizar_noticias.py  # Descarga titulares de noticias vía RSS
│   ├── generar_brief.py        # Genera el resumen diario del Brief Premercado con Gemini
│   └── actualizar_todo.py      # Corre los cuatro anteriores en secuencia (usado por el cron de Railway)
├── constants.py                 # Listas de tickers compartidas entre scripts y dashboard
├── market_data.py                # Cálculo de los indicadores de "Importante", compartido entre el dashboard y generar_brief.py
├── models.py                    # Define las tablas de la base de datos
├── requirements.txt              # Librerías necesarias
└── .env.example                  # Plantilla de variables de entorno
```

## Cómo correrlo en local (VS Code)

1. Instala las librerías:
   ```
   py -m pip install -r requirements.txt --break-system-packages
   ```

2. Copia `.env.example` a `.env` y completa tus credenciales:
   - Token de la API del BCCh (gratis): https://si3.bcentral.cl/Siete/en/Siete/API
   - Una base de datos PostgreSQL (puedes usar una gratuita de Neon o Supabase mientras no tengas Railway conectado)
   - API key de Gemini (gratis): https://aistudio.google.com/apikey — solo
     necesaria para correr `scripts/generar_brief.py`; el resto del dashboard
     funciona sin ella.

3. Crea las tablas (solo la primera vez):
   ```
   py models.py
   ```

4. Descarga los datos:
   ```
   py scripts/actualizar_todo.py
   ```

5. Corre el dashboard:
   ```
   streamlit run app/dashboard.py
   ```
