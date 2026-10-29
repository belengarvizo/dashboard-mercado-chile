"""
Catálogo de los ETFs de acciones que muestra la sección «Renta Variable y ETFs».

Los nombres y las descripciones salen de lo que Yahoo Finance informa para cada fondo (verificados con
una consulta real el 29-10-2026, no de memoria). La lista de tickers que baja el cron diario vive en
constants.TICKERS_ETFS_ACCIONES (una prueba comprueba que las dos coincidan).

TRES TABLAS, TRES SIGNIFICADOS DE `grupo`
    - Mercados de EEUU: `grupo` es el índice que replica el fondo.
    - Sectores de EEUU: `grupo` es el tipo de sector según la clasificación de Morningstar (la que usa
      Yahoo para sus categorías): cíclico (sube y baja con la economía), sensible o defensivo (se mueve
      menos con el ciclo). Es una clasificación común, no una ley: un sector «defensivo» también cae.
    - Países y regiones: `grupo` es si el mercado es desarrollado o emergente según MSCI.
"""

MERCADOS_EEUU = ["SPY", "QQQ", "DIA", "IWM"]
SECTORES_EEUU = ["XLK", "XLC", "XLY", "XLF", "XLI", "XLE", "XLB", "XLRE", "XLV", "XLP", "XLU"]
PAISES_Y_REGIONES = ["EFA", "EEM", "EWJ", "EWZ", "FXI", "ECH"]

ETFS_ACCIONES: dict[str, dict] = {
    "SPY": {
        "nombre": "State Street SPDR S&P 500 ETF Trust",
        "grupo": "S&P 500",
        "descripcion": "Las 500 empresas grandes de EEUU del índice S&P 500, con el mismo peso que tienen en el índice.",
    },
    "QQQ": {
        "nombre": "Invesco QQQ Trust",
        "grupo": "Nasdaq-100",
        "descripcion": "Las 100 mayores empresas no financieras del Nasdaq (índice Nasdaq-100): pesa mucho la tecnología.",
    },
    "DIA": {
        "nombre": "State Street SPDR Dow Jones Industrial Average ETF Trust",
        "grupo": "Dow Jones",
        "descripcion": "Las 30 empresas del Dow Jones Industrial Average, ponderadas por precio de la acción.",
    },
    "IWM": {
        "nombre": "iShares Russell 2000 ETF",
        "grupo": "Russell 2000",
        "descripcion": "Cerca de 2.000 empresas pequeñas de EEUU (las más chicas del Russell 3000).",
    },
    "XLK": {
        "nombre": "State Street Technology Select Sector SPDR ETF",
        "grupo": "Sensible",
        "descripcion": "Las empresas de tecnología del S&P 500.",
    },
    "XLC": {
        "nombre": "State Street Communication Services Select Sector SPDR ETF",
        "grupo": "Sensible",
        "descripcion": "Las empresas de comunicaciones del S&P 500: telecomunicaciones, medios, entretenimiento y servicios de internet.",
    },
    "XLY": {
        "nombre": "State Street Consumer Discretionary Select Sector SPDR ETF",
        "grupo": "Cíclico",
        "descripcion": "Las empresas de consumo discrecional del S&P 500: lo que la gente compra cuando le alcanza (autos, comercio, restaurantes).",
    },
    "XLF": {
        "nombre": "State Street Financial Select Sector SPDR ETF",
        "grupo": "Cíclico",
        "descripcion": "Las empresas financieras del S&P 500: bancos, seguros, mercado de capitales y financiamiento al consumo.",
    },
    "XLI": {
        "nombre": "State Street Industrial Select Sector SPDR ETF",
        "grupo": "Sensible",
        "descripcion": "Las empresas industriales del S&P 500: aeroespacial y defensa, conglomerados y transporte.",
    },
    "XLE": {
        "nombre": "State Street Energy Select Sector SPDR ETF",
        "grupo": "Sensible",
        "descripcion": "Las empresas de energía del S&P 500: petróleo, gas y servicios para producirlos.",
    },
    "XLB": {
        "nombre": "State Street Materials Select Sector SPDR ETF",
        "grupo": "Cíclico",
        "descripcion": "Las empresas de materiales del S&P 500: químicos, metales y minería, papel, envases y materiales de construcción.",
    },
    "XLRE": {
        "nombre": "State Street Real Estate Select Sector SPDR ETF",
        "grupo": "Cíclico",
        "descripcion": "Las empresas inmobiliarias del S&P 500.",
    },
    "XLV": {
        "nombre": "State Street Health Care Select Sector SPDR ETF",
        "grupo": "Defensivo",
        "descripcion": "Las empresas de salud del S&P 500: farmacéuticas, equipos médicos, biotecnología y servicios de salud.",
    },
    "XLP": {
        "nombre": "State Street Consumer Staples Select Sector SPDR ETF",
        "grupo": "Defensivo",
        "descripcion": "Las empresas de consumo básico del S&P 500: lo que la gente compra aunque le falte plata (alimentos, bebidas, aseo).",
    },
    "XLU": {
        "nombre": "State Street Utilities Select Sector SPDR ETF",
        "grupo": "Defensivo",
        "descripcion": "Las empresas de servicios básicos del S&P 500: electricidad, agua y gas.",
    },
    "EFA": {
        "nombre": "iShares MSCI EAFE ETF",
        "grupo": "Desarrollado",
        "descripcion": "Empresas grandes y medianas de los mercados desarrollados fuera de EEUU y Canadá (Europa, Japón, Australia y otros).",
    },
    "EEM": {
        "nombre": "iShares MSCI Emerging Markets ETF",
        "grupo": "Emergente",
        "descripcion": "Empresas grandes y medianas de los mercados emergentes del mundo.",
    },
    "EWJ": {
        "nombre": "iShares MSCI Japan ETF",
        "grupo": "Desarrollado",
        "descripcion": "Empresas grandes y medianas de la bolsa de Japón.",
    },
    "EWZ": {
        "nombre": "iShares MSCI Brazil ETF",
        "grupo": "Emergente",
        "descripcion": "Empresas grandes y medianas de la bolsa de Brasil.",
    },
    "FXI": {
        "nombre": "iShares China Large-Cap ETF",
        "grupo": "Emergente",
        "descripcion": "Las mayores empresas de China que cotizan en la bolsa de Hong Kong y están abiertas a inversionistas internacionales.",
    },
    "ECH": {
        "nombre": "iShares MSCI Chile ETF",
        "grupo": "Emergente",
        "descripcion": "Empresas grandes, medianas y pequeñas de la bolsa de Chile. Es el ETF que este dashboard usa como proxy del IPSA.",
    },
}


def nombre_de(ticker: str) -> str:
    """Nombre completo del ETF; si no está en el catálogo, el ticker mismo (nunca inventa un nombre)."""
    return ETFS_ACCIONES.get(ticker, {}).get("nombre", ticker)
