# Dashboard de mercado chileno

Panel que consolida indicadores macroeconómicos del Banco Central de Chile,
todas las acciones del IPSA y benchmarks internacionales en un solo lugar,
actualizado diariamente.

**Dashboard en vivo:** https://dashboard-mercado-chile-production.up.railway.app/

## Qué muestra

El dashboard tiene 10 pestañas:

1. **Brief Premercado** — para revisar antes de que abra la Bolsa de Santiago.
   Sección "Importante": % de cambio de la última sesión de S&P 500, Dow
   Jones, cobre, **petróleo WTI** (`CL=F`), el bono UST a 10 años, la tasa
   de política monetaria de EEUU (Effective Federal Funds Rate, vía FRED),
   el IPSA (proxy ECH), la TPM de Chile, el IPC, el Imacec y la tasa de
   desempleo (INE, desestacionalizada, vía BCCh) — con flecha y color
   verde/rojo, pensado para leerse en 10 segundos. Si el dato más reciente
   de un indicador no está disponible (ej. NaN), cae automáticamente al
   último valor válido y muestra su fecha real en vez de la de hoy. Justo
   debajo, el **spread 2s10s** (UST10Y − UST2Y — UST2Y vía `2YY=F` de
   Yahoo Finance, ya que no existe un ticker "^" clásico para 2 años;
   verificado con datos reales antes de usarlo), marcado en rojo si la curva
   está invertida (spread negativo), con una nota breve y cautelosa sobre su
   asociación histórica con recesiones en EEUU — sin afirmar que sea una
   predicción garantizada. Justo debajo, la **inflación breakeven** (tasa
   nominal del bono BCP a 10 años menos tasa real del bono BCU a 10 años,
   ambos del BCCh y del mismo plazo): es la inflación que el mercado tiene
   implícita en los precios de ambos bonos, no un pronóstico oficial de
   nadie — nota metodológica visible en la propia pestaña. A continuación,
   el **calendario económico de los
   próximos 7 días** (`calendario_economico.py`): RPM del Banco Central,
   FOMC de la Fed, publicaciones de IPC (INE) e IMACEC (BCCh), y reuniones
   ministeriales de la OPEP+, cada una con una etiqueta de color por
   organismo y, cuando corresponde, una nota de que la fecha es estimada y
   no confirmada explícitamente por la fuente — ver "Calendario económico
   2026" más abajo para el detalle de fuentes y limitaciones. Debajo de eso,
   un **resumen diario
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
   Incluye la **inflación breakeven** (tasa BCP nominal a 10 años − tasa BCU
   real a 10 años) como una serie calculada más del selector, y también los
   **indicadores de "Importante" del Brief Premercado que vienen de precios
   de acciones** (S&P 500, Dow Jones, Petróleo WTI, IPSA vía ECH) — así todos
   los indicadores de esa sección quedan explorables acá, no solo los que ya
   vivían en `series_macro` — ver detalle en el punto 1 y en "Fuentes de datos".
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
4. **Acciones Dow Jones** — la misma estructura que "Acciones IPSA", aplicada
   a **las 30 acciones que componen el Dow Jones Industrial Average**
   (verificadas contra Wikipedia, stockanalysis.com y Yahoo Finance antes de
   agregarlas), con AAPL, MSFT, JPM, CAT y KO preseleccionadas por defecto.
   El heatmap de desempeño usa el mismo criterio de % de cambio, volatilidad
   anualizada, Beta y Beta ajustada — pero el Beta se calcula contra el
   **índice Dow Jones (`^DJI`) directamente**, no contra un proxy, porque a
   diferencia del IPSA sí tiene ticker propio en Yahoo Finance. El CAPM usa
   como Rf la Effective Federal Funds Rate (TPM EEUU) y una sola versión (sin
   la distinción "local" vs. "+ CRP" del IPSA): no aplica una prima de riesgo
   país de EEUU respecto a sí mismo.
5. **Riesgo** — Value at Risk (VaR) histórico y paramétrico, a 95% y 99%, para
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

   **Stress test paramétrico:** un slider simula un shock hipotético al
   mercado chileno (-30% a +30%, proxy ECH) y calcula el impacto estimado
   (Beta × shock) para cada una de las 30 acciones y para el portafolio
   equiponderado de las 5 principales. Modelo de un solo factor: ignora el
   riesgo idiosincrático y el quiebre de correlaciones típico en crisis
   reales — queda documentado en la nota metodológica.

   **Peor escenario histórico:** identifica el peor retorno acumulado de 5 y
   10 días hábiles que existe **dentro de los datos reales disponibles** del
   proxy ECH (no una cifra externa de una crisis pasada), lo aplica vía Beta
   a cada acción y al portafolio, y lo etiqueta explícitamente como el peor
   caso observado en la muestra — no el peor caso históricamente posible.
6. **Benchmark** — el IPSA (vía el ETF ECH, ver nota abajo) comparado con el
   S&P 500, MSCI Emerging Markets (EEM) y el Bovespa, normalizado a base 100.
   Debajo, la sección **7 Magníficas**: AAPL, MSFT, GOOGL, AMZN, NVDA, META y
   TSLA normalizadas a base 100 (gráfico sin cambios), más una tabla simple
   de % de cambio 1D/1W/1M/YTD (coloreada verde/rojo, mismo estilo que el
   heatmap del IPSA pero sin Beta/VaR/CAPM).
7. **Momentum IPSA** — estrategia momentum "12-1" de Jegadeesh & Titman
   (1993) sobre las 30 acciones del IPSA: cada fin de mes rankea por retorno
   compuesto de los meses [t-12, t-2] (saltando el mes t-1 más reciente),
   forma portafolios equiponderados "Ganadoras" y "Perdedoras" (10 acciones
   cada uno), los mantiene 1 mes con rebalanceo mensual y 15 puntos base de
   costo de transacción por posición. Muestra la curva de equity del spread
   WML (Ganadoras − Perdedoras), un t-test simple contra cero, la tabla de
   retornos mensuales, y un **test de permutación**: mezcla al azar qué
   10+10 acciones son "ganadoras/perdedoras" cada mes (preservando fechas y
   retornos reales), 1.000 veces. Nota metodológica visible: distingue este
   diseño (momentum de corto/mediano plazo) de De Bondt & Thaler (1985), que
   documentan el efecto contrario — reversión a **largo plazo** (3-5 años) —
   dejando claro que ambos coexisten en la literatura porque operan en
   horizontes distintos. Debajo del resultado del test de permutación, una
   etiqueta explícita conecta el resultado con la jerga de mesa de dinero:
   **"timba"** (apostar sin ventaja estadística real) si cae en la zona
   central, o **"evidencia de una ventaja real, no timba"** si cae en el 5%
   extremo.

   **Hallazgo:** sobre 49 meses de datos, el WML acumulado es +42,9% (t =
   1,03, p = 0,31 — no significativo al 5%), y el resultado real cae en el
   **percentil 88,5 de 1.000 mezclas aleatorias** — elevado, pero sin cruzar
   el umbral de 95% para considerarse distinguible del azar (timba, con este
   criterio).
8. **Calculadora Financiera** — tres modelos interactivos donde el usuario
    ingresa sus propios valores, sin depender de datos fundamentales de la
    base:
    - **CAPM interactivo**: sliders para Rf, Beta y prima de mercado, con el
      costo de capital resultante en tiempo real. Un selector opcional
      precarga la Rf (PDBC) y el Beta real de cualquiera de las 30 acciones
      del IPSA como punto de partida, que el usuario puede seguir ajustando
      libremente.
    - **Dodd-Graham Value Screener**: los 10 criterios clásicos (adaptados de
      *Security Analysis*, Dodd & Graham 1934, y *The Intelligent Investor*,
      cap. 14) — liquidez corriente, deuda vs. capital de trabajo,
      estabilidad y crecimiento de utilidades, P/E y P/B moderados, el atajo
      P/E×P/B ≤ 22,5, rendimiento de utilidades vs. bonos AAA, y dividendo
      sostenible — cada uno mostrado como cumple/no cumple con su fórmula y
      una explicación breve. Nota visible: estos criterios se diseñaron para
      el mercado de EEUU de mediados del siglo XX; aplicarlos sin ajuste a un
      mercado emergente como Chile es una simplificación.
    - **Modelo de Descuento de Dividendos (Gordon Growth)**: precio implícito
      = D₁ / (r − g), con advertencia visible si g ≥ r (el modelo no es
      matemáticamente válido en ese caso).
9. **Optimización de Portafolios** — Markowitz (1952) vía simulación de Monte
   Carlo sobre las 30 acciones del IPSA:
   - **5.000 portafolios simulados** con pesos aleatorios long-only (vía
     distribución de Dirichlet, suman 100%), graficados como nube
     volatilidad (X) vs. retorno esperado (Y), ambos anualizados, usando
     retorno promedio y matriz de covarianza históricos (excluyendo días de
     precio congelado). Se marcan el portafolio de **mínima varianza** y el
     de **máximo Sharpe** (con la tasa libre de riesgo PDBC) dentro de esa
     nube, con sus 10 posiciones más grandes en una tabla.
   - **Constructor interactivo**: elige entre 3 y 8 acciones, asigna pesos
     con sliders (deben sumar 100%, con validación visible), y el
     portafolio se ubica en tiempo real en la misma nube, con su
     volatilidad, retorno esperado, Sharpe y VaR histórico 95%.
   - **Validación out-of-sample** (la pieza central): los pesos de mínima
     varianza y máximo Sharpe se calculan usando solo la primera mitad
     cronológica de los datos (in-sample), se congelan sin recalcular, y se
     aplican sobre la segunda mitad (out-of-sample) — comparados contra un
     portafolio ingenuo de peso igual (1/30) en el mismo período.

   **Hallazgo:** en el período out-of-sample, el portafolio **ingenuo
   (1/N)** tuvo el mejor Sharpe ratio real (2,30) — superando tanto al de
   mínima varianza (2,11) como al de máximo Sharpe (2,26) calculados con
   datos in-sample. Consistente con hallazgos documentados en la literatura
   (DeMiguel, Garlappi & Uppal, 2009): la optimización de Markowitz no
   siempre le gana a la diversificación ingenua fuera de muestra.

   Nota metodológica visible: crítica clásica de **Michaud (1989)** sobre la
   sensibilidad del modelo a la estimación del retorno esperado, con la
   validación out-of-sample como demostración directa del problema.
   Soluciones más robustas de la industria (Black-Litterman, matrices de
   covarianza por régimen de mercado) quedan fuera del alcance del
   proyecto — los pesos "óptimos" son ilustrativos del framework, no una
   recomendación de inversión.
10. **Práctica: Riesgo Bancario** — cinco calculadoras educativas
    interactivas, **sin datos hardcodeados ni ligados a ninguna institución
    real** (etiquetado explícito en la propia pestaña); todos los valores
    los ingresa el usuario:
    - **LCR** (Coeficiente de Cobertura de Liquidez): HQLA / salidas netas
      de efectivo a 30 días, contra el mínimo regulatorio de Basilea III
      (100%).
    - **ΔEVE y ΔNII**: impacto de un shock de tasas (slider en puntos base)
      sobre el valor económico del patrimonio (largo plazo) y sobre el
      margen de interés neto a 12 meses (corto plazo), a partir de gaps de
      repreciación ingresados por el usuario — con una nota explícita de
      que un banco puede tener ΔNII saludable y ΔEVE muy negativo al mismo
      tiempo (el patrón general detrás del colapso de Silicon Valley Bank
      en 2023).
    - **CVA**: Exposición esperada × PD × LGD (LGD = 1 − tasa de
      recuperación).
    - **ROIC vs. ROE**: NOPAT/Capital invertido vs. Utilidad neta/Patrimonio,
      con la diferencia explicada como efecto del apalancamiento.
    - **Days to Cover** (short squeeze): Interés corto / volumen diario
      promedio — con una nota visible de que **no es calculable con datos
      reales del mercado chileno**, porque no existe información pública de
      posiciones cortas en la Bolsa de Santiago (a diferencia de EEUU, donde
      FINRA publica el short interest quincenalmente); ese vacío de
      transparencia es parte de lo que motivó este proyecto desde el
      inicio.

11. **Laboratorio Financiero** — pestaña independiente (no modifica la de
    "Optimización de Portafolios") pensada como herramienta interactiva de
    estudio para la tarea de Frontera Media-Varianza + LMC + Desempeño,
    sobre un universo de hasta 50 acciones del S&P 500 (con al menos 2 de
    cada uno de los sectores Energy, Financials, Health Care, Industrials,
    Information Technology y Utilities):
    - **Universo y ventana**: selección editable de acciones (con botón para
      volver a la muestra recomendada de 50) y ventana histórica de 1 a 5
      años terminando el 31-07-2026 (modo "Tarea") o en una fecha
      personalizada.
    - **Parte 1A — Frontera media-varianza**: un panel de restricciones
      ("jugar con los supuestos": venta corta, límite ±X% por acción, piso
      sectorial, ignorar covarianzas) con **presets** para saltar directo a
      cada punto de la tarea, más una sección de comparación que superpone
      las 5 fronteras (base, ingenua, ±10%, sin venta corta, sin venta corta
      + Energy/Industrials≥40%) en un solo gráfico. La frontera "base" (sin
      restricciones) se resuelve con la solución matricial cerrada de
      Markowitz/Merton; cualquier restricción de desigualdad se resuelve con
      SLSQP. Incluye un slider para explorar cualquier punto de la frontera
      y ver sus pesos.
    - **Parte 1B — LMC y desempeño**: portafolio de tangencia M (sobre la
      frontera base), Línea de Mercado de Capitales, regresión CAPM de M
      contra el S&P 500 (α, β, R², error estándar, test t bilateral de
      H0: α=0 con p-value exacto vía distribución t, IC 95%), comparación de
      Sharpe y Treynor entre M y el S&P 500, y asignación óptima según
      aversión al riesgo (x* = (E[RM]−Rf)/(c·σM²), con slider de c). Incluye
      una advertencia explícita de **sesgo in-sample**: M se optimiza y se
      evalúa con la misma ventana de datos.
    - **Tasa libre de riesgo**: Treasury Constant Maturity a 1 año (serie
      `DGS1` del H.15 de la Reserva Federal, vía FRED) — no la Effective
      Federal Funds Rate que usa el resto del dashboard.
    - **Validaciones visibles** (Σwi≈1, LMC pasa por Rf y por M, β del S&P
      500 contra sí mismo ≈1, p-value coherente con el estadístico t) y
      **exportación a CSV** de estadísticas, matriz de covarianzas, puntos
      de la frontera, pesos de M y resultados CAPM/Sharpe/Treynor.
    - Lógica separada en `portfolio_lab.py` (sin dependencias de Streamlit,
      testeable de forma aislada) para no inflar `app/dashboard.py`.

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
- Bono BCCh en UF (BCU) a 10 años, tasa de mercado secundario — tasa
  **real** (indexada a UF), usada junto al BCP nominal del mismo plazo para
  calcular la **inflación breakeven** (BCP − BCU). Serie encontrada vía
  `SearchSeries` del catálogo del BCCh (código `F022.BUF.TIS.AN10.UF.Z.D`),
  con datos recientes y limpios verificados antes de usarla — mismo patrón
  ya usado para el cobre, el swap cámara y el BCP.
- Tasa de desocupación nacional (INE, desestacionalizada) — serie
  `F049.DES.TAS.INE.10.M`, encontrada vía `SearchSeries`, usada en
  "Importante" del Brief Premercado.

**FRED (Federal Reserve Economic Data, vía su endpoint CSV público, sin API key):**
- Effective Federal Funds Rate (serie `DFF`) — usada como la tasa de
  política monetaria de EEUU en "Importante" del Brief Premercado; el BCCh
  no publica tasas de política de EEUU en su catálogo, y Yahoo Finance no
  tiene un ticker que la represente directamente (a diferencia de los
  rendimientos de bonos del Tesoro).
- Treasury Constant Maturity a 1 año (serie `DGS1`, del H.15 de la Reserva
  Federal) — la tasa libre de riesgo que usa "Laboratorio Financiero"
  (distinta de la Effective Federal Funds Rate: es un rendimiento de
  mercado de bonos, no la tasa de política monetaria).

**Yahoo Finance (vía `yfinance`, sin autenticación):**
- Las 30 acciones del índice IPSA
- El ETF ECH (iShares MSCI Chile) — usado como proxy del IPSA para el
  cálculo de Beta, la pestaña Benchmark y el indicador "IPSA" de
  "Importante" del Brief Premercado, porque el índice IPSA no tiene ticker
  propio en Yahoo Finance
- Benchmarks: S&P 500 (`^GSPC`), MSCI Emerging Markets (`EEM`), Bovespa (`^BVSP`)
- Las 7 Magníficas: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
- Petróleo WTI (`CL=F`, futuro Crude Oil) — usado en "Importante" del Brief
  Premercado y en el prompt de Gemini, para que el resumen diario pueda
  conectar titulares geopolíticos con su efecto en el precio del petróleo
- Dow Jones Industrial Average (`^DJI`) — usado en "Importante" del Brief
  Premercado y como proxy de mercado (Beta, CAPM) en la pestaña "Acciones
  Dow Jones"
- Las 30 acciones que componen el Dow Jones Industrial Average — verificadas
  contra Wikipedia y stockanalysis.com (dos fuentes independientes y
  vigentes, la composición del índice cambia periódicamente) antes de
  agregarlas; 5 de ellas (AAPL, MSFT, GOOGL, AMZN, NVDA) ya se descargaban
  como parte de las 7 Magníficas, así que no se piden dos veces
- El bono del Tesoro de EEUU a 10 años (`^TNX`) y a 2 años (`2YY=F` — Yahoo
  no tiene un ticker "^" clásico para 2 años, verificado con datos reales
  antes de usarlo) — se descargan junto con las series del BCCh porque el
  Banco Central no publica tasas de EEUU en su catálogo
- Universo de 50 acciones del S&P 500 de "Laboratorio Financiero"
  (`constants.UNIVERSO_LABORATORIO_50`) — verificadas contra la API de
  Yahoo Finance y clasificadas por sector GICS; cubre con margen los 6
  sectores que exige la tarea (Energy, Financials, Health Care,
  Industrials, Information Technology, Utilities)

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

### Calendario económico 2026 (`calendario_economico.py`)

Archivo con fechas verificadas de forma manual contra la fuente oficial de
cada organismo (no se generan ni se infieren automáticamente):

- **RPM (Banco Central de Chile):** comunicado oficial de bcentral.cl
  "Banco Central publica calendario de RPM, RPF, IPoM, IEF 2026", cruzado
  contra el calendario económico de tradingeconomics.com.
- **FOMC (Reserva Federal):** verificado con fetch directo a
  `federalreserve.gov/monetarypolicy/fomccalendars.htm`.
- **IPC (INE):** verificado con el PDF oficial "Calendario 2026 —
  Indicadores de Coyuntura INE" (actualización del 10-04-2026).
- **IMACEC (Banco Central de Chile):** el Banco Central no publica un
  calendario anual con todas las fechas exactas; se usa su regla
  metodológica publicada ("primer día hábil del mes, con rezago de 31 días
  respecto al mes medido"). Solo la fecha del 1 de septiembre de 2026 está
  confirmada de forma explícita (fxstreet.com); las de octubre, noviembre y
  diciembre se calcularon aplicando la misma regla y quedan marcadas como
  no confirmadas (`confirmado=False`) en el archivo.
- **OPEP+:** a diferencia de los bancos centrales, la OPEP+ **no** publica
  un calendario anual fijo — desde 2024 el grupo de países con recortes
  voluntarios confirma cada reunión con solo semanas de anticipación. Solo
  se incluye la próxima reunión ministerial confirmada al momento de
  escribir esto (tradingeconomics.com/opec/calendar); el calendario puede
  no reflejar reuniones futuras aún no anunciadas.

El calendario completo, con la fuente y el nivel de confianza de cada
fecha, queda documentado como comentarios en el propio archivo. La pestaña
"Brief Premercado" muestra una nota de vigencia ("Calendario verificado
al...") y recuerda cuándo hay que actualizarlo: el Banco Central publica el
calendario de RPM del año siguiente en septiembre, y la Fed publica el
calendario de FOMC del año siguiente en diciembre.

### CMF "Hechos Esenciales": evaluado, no implementado

Se investigó si `cmfchile.cl/institucional/hechos/hechos.php` se podía
consultar de forma programática para mostrar los hechos esenciales
recientes de las empresas del IPSA. El formulario de búsqueda de esa página
**requiere resolver un CAPTCHA** para ejecutar la consulta, y no se
encontró una API pública, feed RSS/XML ni endpoint JSON documentado como
alternativa. Como un CAPTCHA existe específicamente para bloquear el acceso
automatizado, no se implementó esta sección — forzarlo requeriría eludir
esa protección, lo que no corresponde.

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
├── portfolio_lab.py               # Frontera media-varianza, LMC y CAPM de "Laboratorio Financiero" (sin dependencias de Streamlit)
├── calendario_economico.py       # Fechas verificadas de RPM, FOMC, IPC, IMACEC y OPEP+ 2026
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
