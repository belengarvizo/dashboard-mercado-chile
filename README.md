# Dashboard de mercado chileno

Panel que consolida indicadores macroeconómicos del Banco Central de Chile,
todas las acciones del IPSA y benchmarks internacionales en un solo lugar,
actualizado diariamente.

**Dashboard en vivo:** https://dashboard-mercado-chile-production.up.railway.app/

## Qué muestra

El dashboard tiene 4 pestañas:

1. **Indicadores macro** — selector para explorar cualquiera de las series del
   BCCh (ver lista completa más abajo) con su gráfico histórico y último valor.
2. **Acciones IPSA** — gráfico de precios normalizables a base 100 para las 5
   acciones más importantes (SQM-B, Banco de Chile, Falabella, Copec, CMPC),
   más un **heatmap de desempeño con las 30 acciones del IPSA**: % de cambio
   1D/1W/1M/YTD (coloreado verde/rojo), **Beta** de cada acción contra el
   mercado chileno (regresión de retornos diarios del último año vs el ETF
   ECH, ver limitación de datos más abajo) y la fecha del último precio
   real de cada ticker.
3. **7 Magníficas** — AAPL, MSFT, GOOGL, AMZN, NVDA, META y TSLA, normalizadas
   a base 100 para comparar su desempeño relativo.
4. **Benchmark** — el IPSA (vía el ETF ECH, ver nota abajo) comparado con el
   S&P 500, MSCI Emerging Markets (EEM) y el Bovespa, normalizado a base 100.

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

**Yahoo Finance (vía `yfinance`, sin autenticación):**
- Las 30 acciones del índice IPSA
- El ETF ECH (iShares MSCI Chile) — usado como proxy del IPSA para el
  cálculo de Beta y la pestaña Benchmark, porque el índice IPSA no tiene
  ticker propio en Yahoo Finance
- Benchmarks: S&P 500 (`^GSPC`), MSCI Emerging Markets (`EEM`), Bovespa (`^BVSP`)
- Las 7 Magníficas: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
- El bono del Tesoro de EEUU a 10 años (`^TNX`) — se descarga junto con las
  series del BCCh porque el Banco Central no publica tasas de EEUU en su
  catálogo

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
    `python scripts/actualizar_todo.py`, que descarga las series del BCCh y
    los precios de acciones en un solo paso y actualiza la base de datos
    antes de que empiece el día bursátil.

## Estructura del proyecto

```
dashboard-mercado-chile/
├── app/
│   └── dashboard.py            # La app de Streamlit (lo que ves en el navegador)
├── scripts/
│   ├── actualizar_bcch.py      # Descarga series del Banco Central (+ UST10 vía Yahoo)
│   ├── actualizar_acciones.py  # Descarga precios de acciones vía Yahoo Finance
│   └── actualizar_todo.py      # Corre los dos anteriores en secuencia (usado por el cron de Railway)
├── constants.py                 # Listas de tickers compartidas entre scripts y dashboard
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
