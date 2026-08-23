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

# Acciones chilenas y estadounidenses adicionales, fuera del IPSA/Dow
# Jones/Magníficas, agregadas únicamente para ampliar el universo
# seleccionable en "Optimización de Portafolios" (no son una categoría por
# sector: Sigdo Koppers es industrial/servicios, y el resto de EEUU mezcla
# energía, salud, financiero y tecnología). Verificadas contra la API de
# Yahoo Finance antes de agregarlas.
TICKERS_CHILE_ADICIONALES = [
    "SK.SN",  # Sigdo Koppers
]

TICKERS_EEUU_ADICIONALES = [
    "XOM",   # ExxonMobil
    "LLY",   # Eli Lilly
    "GE",    # GE Aerospace
    "AVGO",  # Broadcom
    "NEE",   # NextEra Energy
    "DUK",   # Duke Energy
    "SO",    # Southern Company
]

# Tickers adicionales solo para el universo de 50 acciones del S&P 500 de
# "Laboratorio Financiero" (app/portfolio_lab.py) — no forman parte del Dow
# Jones ni de TICKERS_EEUU_ADICIONALES, así que hay que descargarlos aparte.
# Verificados contra la API de Yahoo Finance antes de agregarlos.
TICKERS_LABORATORIO_ADICIONALES = [
    "COP",   # ConocoPhillips
    "SLB",   # SLB (Schlumberger)
    "MA",    # Mastercard
    "BAC",   # Bank of America
    "WFC",   # Wells Fargo
    "MS",    # Morgan Stanley
    "BLK",   # BlackRock
    "PFE",   # Pfizer
    "ABBV",  # AbbVie
    "TMO",   # Thermo Fisher Scientific
    "ABT",   # Abbott Laboratories
    "UNP",   # Union Pacific
    "UPS",   # United Parcel Service
    "LMT",   # Lockheed Martin
    "DE",    # Deere & Company
    "ORCL",  # Oracle
    "ADBE",  # Adobe
    "AEP",   # American Electric Power
    "COST",  # Costco Wholesale
]

# Universo de 50 acciones del S&P 500 para "Laboratorio Financiero": (ticker,
# nombre de la empresa, sector GICS). Cubre con margen los 6 sectores que
# exige la tarea (Energy, Financials, Health Care, Industrials, Information
# Technology, Utilities, con 4 a 8 acciones cada uno, todas ≥2) más otros
# sectores para completar 50 con nombres grandes y líquidos. Pertenencia al
# S&P 500 y sector verificados antes de incluirlas; disponibilidad de datos
# verificada contra la API de Yahoo Finance.
UNIVERSO_LABORATORIO_50 = [
    ("XOM", "ExxonMobil", "Energy"),
    ("CVX", "Chevron", "Energy"),
    ("COP", "ConocoPhillips", "Energy"),
    ("SLB", "SLB", "Energy"),
    ("JPM", "JPMorgan Chase", "Financials"),
    ("GS", "Goldman Sachs", "Financials"),
    ("V", "Visa", "Financials"),
    ("MA", "Mastercard", "Financials"),
    ("BAC", "Bank of America", "Financials"),
    ("WFC", "Wells Fargo", "Financials"),
    ("MS", "Morgan Stanley", "Financials"),
    ("BLK", "BlackRock", "Financials"),
    ("LLY", "Eli Lilly", "Health Care"),
    ("JNJ", "Johnson & Johnson", "Health Care"),
    ("UNH", "UnitedHealth Group", "Health Care"),
    ("PFE", "Pfizer", "Health Care"),
    ("MRK", "Merck & Co.", "Health Care"),
    ("ABBV", "AbbVie", "Health Care"),
    ("TMO", "Thermo Fisher Scientific", "Health Care"),
    ("ABT", "Abbott Laboratories", "Health Care"),
    ("CAT", "Caterpillar", "Industrials"),
    ("HON", "Honeywell", "Industrials"),
    ("GE", "GE Aerospace", "Industrials"),
    ("BA", "Boeing", "Industrials"),
    ("UNP", "Union Pacific", "Industrials"),
    ("UPS", "United Parcel Service", "Industrials"),
    ("LMT", "Lockheed Martin", "Industrials"),
    ("DE", "Deere & Company", "Industrials"),
    ("NVDA", "Nvidia", "Information Technology"),
    ("AAPL", "Apple", "Information Technology"),
    ("MSFT", "Microsoft", "Information Technology"),
    ("AVGO", "Broadcom", "Information Technology"),
    ("ORCL", "Oracle", "Information Technology"),
    ("CRM", "Salesforce", "Information Technology"),
    ("ADBE", "Adobe", "Information Technology"),
    ("CSCO", "Cisco Systems", "Information Technology"),
    ("NEE", "NextEra Energy", "Utilities"),
    ("DUK", "Duke Energy", "Utilities"),
    ("SO", "Southern Company", "Utilities"),
    ("AEP", "American Electric Power", "Utilities"),
    ("AMZN", "Amazon", "Consumer Discretionary"),
    ("HD", "Home Depot", "Consumer Discretionary"),
    ("MCD", "McDonald's", "Consumer Discretionary"),
    ("NKE", "Nike", "Consumer Discretionary"),
    ("PG", "Procter & Gamble", "Consumer Staples"),
    ("KO", "Coca-Cola", "Consumer Staples"),
    ("WMT", "Walmart", "Consumer Staples"),
    ("COST", "Costco Wholesale", "Consumer Staples"),
    ("GOOGL", "Alphabet", "Communication Services"),
    ("META", "Meta Platforms", "Communication Services"),
]

TICKERS_LABORATORIO_50 = [t for t, _, _ in UNIVERSO_LABORATORIO_50]

# Universo AMPLIADO: acciones adicionales del S&P 500 (fuera de las 50 de
# arriba) para dar margen real de elección dentro de cada sector al armar
# la selección final de la tarea — no son "las 50 recomendadas", son
# opciones extra en el selector. Se evitaron deliberadamente spin-offs
# recientes (ej. GE Vernova/GEV, Kenvue/KVUE, Veralto/VLTO, Solventum/SOLV
# — todos posteriores a jul-2023) porque no tendrían los 3 años completos
# de historia que exige la ventana fija de la tarea. Pertenencia al S&P
# 500, sector y disponibilidad de datos en la ventana 31-07-2023 a
# 31-07-2026 verificados contra la API de Yahoo Finance antes de
# agregarlas (0 problemas de cobertura en las 76).
UNIVERSO_LABORATORIO_ADICIONAL = [
    ("EOG", "EOG Resources", "Energy"),
    ("WMB", "Williams Companies", "Energy"),
    ("KMI", "Kinder Morgan", "Energy"),
    ("OXY", "Occidental Petroleum", "Energy"),
    ("PSX", "Phillips 66", "Energy"),
    ("VLO", "Valero Energy", "Energy"),
    ("C", "Citigroup", "Financials"),
    ("AXP", "American Express", "Financials"),
    ("SCHW", "Charles Schwab", "Financials"),
    ("SPGI", "S&P Global", "Financials"),
    ("ICE", "Intercontinental Exchange", "Financials"),
    ("CME", "CME Group", "Financials"),
    ("PGR", "Progressive Corp.", "Financials"),
    ("USB", "U.S. Bancorp", "Financials"),
    ("DHR", "Danaher", "Health Care"),
    ("BMY", "Bristol-Myers Squibb", "Health Care"),
    ("AMGN", "Amgen", "Health Care"),
    ("GILD", "Gilead Sciences", "Health Care"),
    ("CVS", "CVS Health", "Health Care"),
    ("ELV", "Elevance Health", "Health Care"),
    ("ISRG", "Intuitive Surgical", "Health Care"),
    ("VRTX", "Vertex Pharmaceuticals", "Health Care"),
    ("RTX", "RTX Corporation", "Industrials"),
    ("NOC", "Northrop Grumman", "Industrials"),
    ("GD", "General Dynamics", "Industrials"),
    ("MMM", "3M", "Industrials"),
    ("ETN", "Eaton Corporation", "Industrials"),
    ("EMR", "Emerson Electric", "Industrials"),
    ("ITW", "Illinois Tool Works", "Industrials"),
    ("CSX", "CSX Corporation", "Industrials"),
    ("AMD", "Advanced Micro Devices", "Information Technology"),
    ("QCOM", "Qualcomm", "Information Technology"),
    ("TXN", "Texas Instruments", "Information Technology"),
    ("INTC", "Intel", "Information Technology"),
    ("IBM", "IBM", "Information Technology"),
    ("NOW", "ServiceNow", "Information Technology"),
    ("INTU", "Intuit", "Information Technology"),
    ("MU", "Micron Technology", "Information Technology"),
    ("EXC", "Exelon", "Utilities"),
    ("XEL", "Xcel Energy", "Utilities"),
    ("SRE", "Sempra", "Utilities"),
    ("D", "Dominion Energy", "Utilities"),
    ("PEG", "Public Service Enterprise Group", "Utilities"),
    ("ED", "Consolidated Edison", "Utilities"),
    ("TSLA", "Tesla", "Consumer Discretionary"),
    ("LOW", "Lowe's", "Consumer Discretionary"),
    ("SBUX", "Starbucks", "Consumer Discretionary"),
    ("BKNG", "Booking Holdings", "Consumer Discretionary"),
    ("TJX", "TJX Companies", "Consumer Discretionary"),
    ("MAR", "Marriott International", "Consumer Discretionary"),
    ("GM", "General Motors", "Consumer Discretionary"),
    ("YUM", "Yum! Brands", "Consumer Discretionary"),
    ("PEP", "PepsiCo", "Consumer Staples"),
    ("PM", "Philip Morris International", "Consumer Staples"),
    ("MO", "Altria Group", "Consumer Staples"),
    ("MDLZ", "Mondelez International", "Consumer Staples"),
    ("CL", "Colgate-Palmolive", "Consumer Staples"),
    ("TGT", "Target Corporation", "Consumer Staples"),
    ("NFLX", "Netflix", "Communication Services"),
    ("DIS", "Walt Disney", "Communication Services"),
    ("CMCSA", "Comcast", "Communication Services"),
    ("TMUS", "T-Mobile US", "Communication Services"),
    ("VZ", "Verizon Communications", "Communication Services"),
    ("T", "AT&T", "Communication Services"),
    ("LIN", "Linde plc", "Materials"),
    ("APD", "Air Products and Chemicals", "Materials"),
    ("SHW", "Sherwin-Williams", "Materials"),
    ("ECL", "Ecolab", "Materials"),
    ("NEM", "Newmont Corporation", "Materials"),
    ("FCX", "Freeport-McMoRan", "Materials"),
    ("PLD", "Prologis", "Real Estate"),
    ("AMT", "American Tower", "Real Estate"),
    ("EQIX", "Equinix", "Real Estate"),
    ("PSA", "Public Storage", "Real Estate"),
    ("O", "Realty Income", "Real Estate"),
    ("WELL", "Welltower", "Real Estate"),
]

UNIVERSO_LABORATORIO_AMPLIADO = UNIVERSO_LABORATORIO_50 + UNIVERSO_LABORATORIO_ADICIONAL
TICKERS_LABORATORIO_AMPLIADO = [t for t, _, _ in UNIVERSO_LABORATORIO_AMPLIADO]
TICKERS_LABORATORIO_ADICIONAL_DESCARGA = [t for t, _, _ in UNIVERSO_LABORATORIO_ADICIONAL]

SECTOR_POR_TICKER_LABORATORIO = {t: sector for t, _, sector in UNIVERSO_LABORATORIO_AMPLIADO}
EMPRESA_POR_TICKER_LABORATORIO = {t: nombre for t, nombre, _ in UNIVERSO_LABORATORIO_AMPLIADO}

# Sectores en los que la tarea exige al menos 2 acciones en la selección.
SECTORES_OBLIGATORIOS_LABORATORIO = [
    "Energy", "Financials", "Health Care", "Industrials",
    "Information Technology", "Utilities",
]
