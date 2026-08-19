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
SECTOR_POR_TICKER_LABORATORIO = {t: sector for t, _, sector in UNIVERSO_LABORATORIO_50}
EMPRESA_POR_TICKER_LABORATORIO = {t: nombre for t, nombre, _ in UNIVERSO_LABORATORIO_50}

# Sectores en los que la tarea exige al menos 2 acciones en la selección.
SECTORES_OBLIGATORIOS_LABORATORIO = [
    "Energy", "Financials", "Health Care", "Industrials",
    "Information Technology", "Utilities",
]
