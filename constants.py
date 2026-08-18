"""
Listas de tickers compartidas entre los scripts de actualización
(scripts/actualizar_acciones.py) y el dashboard (app/dashboard.py),
para que ambos lados siempre coincidan.
"""

# Las 30 acciones del índice IPSA (Bolsa de Santiago), con el sufijo .SN
# que usa Yahoo Finance. Todos los tickers fueron verificados contra la
# API de Yahoo Finance antes de agregarlos.
TICKERS_IPSA = [
    "AGUAS-A.SN",
    "ANDINA-B.SN",
    "BCI.SN",
    "BSANTANDER.SN",
    "CAP.SN",
    "CCU.SN",
    "CENCOMALLS.SN",
    "CENCOSUD.SN",
    "CHILE.SN",
    "CMPC.SN",
    "COLBUN.SN",
    "CONCHATORO.SN",
    "COPEC.SN",
    "ECL.SN",
    "ENELAM.SN",
    "ENELCHILE.SN",
    "ENTEL.SN",
    "FALABELLA.SN",
    "IAM.SN",
    "ILC.SN",
    "ITAUCL.SN",
    "LTM.SN",
    "MALLPLAZA.SN",
    "PARAUCO.SN",
    "QUINENCO.SN",
    "RIPLEY.SN",
    "SALFACORP.SN",
    "SMU.SN",
    "SQM-B.SN",
    "VAPORES.SN",
]

# Las 5 acciones que se muestran destacadas en el gráfico principal de la
# pestaña "Acciones IPSA" (el v1 original del dashboard).
TICKERS_IPSA_PRINCIPALES = ["SQM-B.SN", "CHILE.SN", "FALABELLA.SN", "COPEC.SN", "CMPC.SN"]

# El índice IPSA no tiene ticker propio en Yahoo Finance (^IPSA, IPSA.SN y
# ^SPIPSA no devuelven datos). Se usa el ETF ECH (iShares MSCI Chile) como
# proxy del mercado chileno para el cálculo de Beta y la pestaña Benchmark.
TICKER_PROXY_IPSA = "ECH"

# Benchmarks internacionales para comparar el IPSA (vía el proxy ECH).
TICKERS_BENCHMARK = {
    TICKER_PROXY_IPSA: "IPSA (proxy ECH)",
    "^GSPC": "S&P 500",
    "EEM": "MSCI Emerging Markets",
    "^BVSP": "Bovespa",
}

# Las "7 Magníficas" tecnológicas de EEUU.
TICKERS_MAGNIFICAS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

# Futuro de petróleo WTI (Crude Oil), usado en el Brief Premercado.
TICKER_PETROLEO_WTI = "CL=F"

# Dow Jones Industrial Average, usado en el Brief Premercado.
TICKER_DOW_JONES = "^DJI"

# Las 30 acciones que componen el Dow Jones Industrial Average. Verificadas
# contra dos fuentes independientes y vigentes (Wikipedia y stockanalysis.com)
# y contra la API de Yahoo Finance antes de agregarlas — la composición del
# índice cambia periódicamente (ej. Nvidia y Sherwin-Williams reemplazaron a
# Intel y Dow Inc. en 2024; Alphabet reemplazó a Verizon después).
TICKERS_DOW_JONES = [
    "AAPL",
    "AMGN",
    "AMZN",
    "AXP",
    "BA",
    "CAT",
    "CRM",
    "CSCO",
    "CVX",
    "DIS",
    "GOOGL",
    "GS",
    "HD",
    "HON",
    "IBM",
    "JNJ",
    "JPM",
    "KO",
    "MCD",
    "MMM",
    "MRK",
    "MSFT",
    "NKE",
    "NVDA",
    "PG",
    "SHW",
    "TRV",
    "UNH",
    "V",
    "WMT",
]

# Las 5 acciones que se muestran destacadas por defecto en el gráfico
# principal de la pestaña "Acciones Dow Jones".
TICKERS_DOW_JONES_PRINCIPALES = ["AAPL", "MSFT", "JPM", "CAT", "KO"]
