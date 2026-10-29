"""
Catálogo de los pares de divisas y de las monedas con tasa que muestra la sección «FX y Carry Trade».

QUÉ ES CADA PAR. Los 14 tickers de Yahoo Finance que ya baja el cron para el módulo de trading
(catalogo_instrumentos.TICKERS_YAHOO_FASE_1). Cada uno trae cómo se lee su precio y qué significa que suba o
baje, porque en divisas el color verde/rojo de un número no dice si «mejoró» algo: que USD/CLP suba es buena
noticia para un exportador y mala para un importador. Se dice en palabras en cada tooltip.

CONVENCIÓN DE COTIZACIÓN. En «EUR/USD» el euro es la moneda base y el precio dice cuántos dólares cuesta 1 euro.
En «USD/CLP» la base es el dólar y el precio dice cuántos pesos cuesta 1 dólar. Yahoo cotiza los pares con la misma
convención que los bancos, y por eso unos pares empiezan con USD y otros terminan en USD.

CARRY TRADE. `MONEDAS_CARRY` lista las monedas para las que existe en la base una tasa de corto plazo REAL, y por
lo tanto se puede medir el carry contra el dólar. Las series de tasas están declaradas en
scripts/actualizar_bcch.py (SERIES_TASAS_PAISES_FRED) y una prueba comprueba que los nombres coincidan. Para
Canadá, Suiza, Australia y Nueva Zelanda no hay una tasa gratuita al día (ver ese archivo): esas monedas salen en
la tabla de divisas pero NO en el carry, y la pantalla lo dice en vez de rellenar.
"""

TICKER_DXY = "DX-Y.NYB"
TICKER_REFERENCIA = "USDCLP=X"  # contra este par se mide la correlación de cada uno: es de la misma fuente y convención de fecha

NOMBRE_TASA_EEUU = "Tasa de política monetaria de EEUU (Effective Federal Funds Rate)"
NOMBRE_TASA_CHILE = "Tasa de política monetaria (TPM)"
NOMBRE_TIPO_DE_CAMBIO_OBSERVADO = "Tipo de cambio observado"
NOMBRE_COBRE = "Precio del cobre (USD/lb)"

# ticker -> datos. «sube»/«baja» dicen en palabras qué significa que el precio suba o baje.
PARES_FX: dict[str, dict] = {
    "EURUSD=X": {
        "nombre": "Euro / dólar (EUR/USD)", "grupo": "Mayores", "cotiza": "dólares por 1 euro",
        "sube": "el euro se fortaleció frente al dólar", "baja": "el dólar se fortaleció frente al euro",
        "descripcion": "El par más transado del mundo: el euro (la segunda moneda de reserva) contra el dólar.",
    },
    "GBPUSD=X": {
        "nombre": "Libra / dólar (GBP/USD)", "grupo": "Mayores", "cotiza": "dólares por 1 libra",
        "sube": "la libra se fortaleció frente al dólar", "baja": "el dólar se fortaleció frente a la libra",
        "descripcion": "La libra esterlina contra el dólar, conocida en el mercado como «cable».",
    },
    "USDJPY=X": {
        "nombre": "Dólar / yen (USD/JPY)", "grupo": "Mayores", "cotiza": "yenes por 1 dólar",
        "sube": "el dólar se fortaleció frente al yen (el yen se debilitó)", "baja": "el yen se fortaleció frente al dólar",
        "descripcion": "El yen suele ser la moneda desde la que se financia el carry trade, porque Japón tiene tasas muy bajas.",
    },
    "USDCHF=X": {
        "nombre": "Dólar / franco suizo (USD/CHF)", "grupo": "Mayores", "cotiza": "francos suizos por 1 dólar",
        "sube": "el dólar se fortaleció frente al franco (el franco se debilitó)", "baja": "el franco se fortaleció frente al dólar",
        "descripcion": "El franco suizo es una moneda refugio: tiende a fortalecerse cuando el mercado tiene miedo.",
    },
    "AUDUSD=X": {
        "nombre": "Dólar australiano / dólar (AUD/USD)", "grupo": "Materias primas", "cotiza": "dólares por 1 dólar australiano",
        "sube": "el dólar australiano se fortaleció frente al dólar", "baja": "el dólar de EEUU se fortaleció frente al australiano",
        "descripcion": "Australia exporta metales y energía: su moneda suele moverse con las materias primas y con el apetito por riesgo.",
    },
    "NZDUSD=X": {
        "nombre": "Dólar neozelandés / dólar (NZD/USD)", "grupo": "Materias primas", "cotiza": "dólares por 1 dólar neozelandés",
        "sube": "el dólar neozelandés se fortaleció frente al dólar", "baja": "el dólar de EEUU se fortaleció frente al neozelandés",
        "descripcion": "Nueva Zelanda exporta alimentos (lácteos, carne): su moneda sigue ese mercado y el apetito por riesgo.",
    },
    "USDCAD=X": {
        "nombre": "Dólar / dólar canadiense (USD/CAD)", "grupo": "Materias primas", "cotiza": "dólares canadienses por 1 dólar",
        "sube": "el dólar de EEUU se fortaleció frente al canadiense", "baja": "el dólar canadiense se fortaleció frente al de EEUU",
        "descripcion": "Canadá exporta petróleo: su moneda se mueve con el precio del crudo y con la economía de EEUU.",
    },
    "USDCLP=X": {
        "nombre": "Dólar / peso chileno (USD/CLP)", "grupo": "Latinoamérica", "cotiza": "pesos chilenos por 1 dólar",
        "sube": "el dólar se fortaleció (el peso chileno se debilitó)", "baja": "el peso chileno se fortaleció frente al dólar",
        "descripcion": "El peso chileno, atado al precio del cobre, que es la mitad de las exportaciones de Chile.",
    },
    "USDBRL=X": {
        "nombre": "Dólar / real brasileño (USD/BRL)", "grupo": "Latinoamérica", "cotiza": "reales por 1 dólar",
        "sube": "el dólar se fortaleció (el real se debilitó)", "baja": "el real se fortaleció frente al dólar",
        "descripcion": "El real brasileño: una de las monedas con tasas más altas del mundo, y por eso muy usada en el carry trade.",
    },
    "USDMXN=X": {
        "nombre": "Dólar / peso mexicano (USD/MXN)", "grupo": "Latinoamérica", "cotiza": "pesos mexicanos por 1 dólar",
        "sube": "el dólar se fortaleció (el peso mexicano se debilitó)", "baja": "el peso mexicano se fortaleció frente al dólar",
        "descripcion": "El peso mexicano, la moneda emergente más transada: muy ligada a la economía y al comercio de EEUU.",
    },
    "EURGBP=X": {
        "nombre": "Euro / libra (EUR/GBP)", "grupo": "Cruces", "cotiza": "libras por 1 euro",
        "sube": "el euro se fortaleció frente a la libra", "baja": "la libra se fortaleció frente al euro",
        "descripcion": "Un cruce: dos monedas distintas del dólar. Mide a Europa contra Reino Unido sin pasar por EEUU.",
    },
    "EURJPY=X": {
        "nombre": "Euro / yen (EUR/JPY)", "grupo": "Cruces", "cotiza": "yenes por 1 euro",
        "sube": "el euro se fortaleció frente al yen", "baja": "el yen se fortaleció frente al euro",
        "descripcion": "Un cruce que se usa mucho en el carry trade: euro (tasa media) contra yen (tasa muy baja).",
    },
    "GBPJPY=X": {
        "nombre": "Libra / yen (GBP/JPY)", "grupo": "Cruces", "cotiza": "yenes por 1 libra",
        "sube": "la libra se fortaleció frente al yen", "baja": "el yen se fortaleció frente a la libra",
        "descripcion": "Un cruce muy volátil: libra contra yen, el favorito de los operadores de carry trade.",
    },
    TICKER_DXY: {
        "nombre": "Índice dólar (DXY)", "grupo": "Índice", "cotiza": "puntos de un índice (no es un precio en dólares)",
        "sube": "el dólar se fortaleció frente a una canasta de monedas", "baja": "el dólar se debilitó frente a la canasta",
        "descripcion": "Mide el dólar contra una canasta de seis monedas (más de la mitad es el euro). Es la forma estándar de decir «el dólar sube».",
    },
}

# Monedas con tasa de corto plazo real en la base. `par`: ticker de Yahoo contra el dólar; `base_es_dolar`: True si el
# par cotiza «moneda por 1 dólar» (USD/JPY) y hay que invertirlo para tener «dólares por 1 moneda».
MONEDAS_CARRY: dict[str, dict] = {
    "EUR": {
        "nombre": "Euro", "con_articulo": "el euro", "par": "EURUSD=X", "base_es_dolar": False,
        "serie_tasa": "Tasa de política del BCE, zona euro (facilidad de depósito, ECBDFR)",
        "tasa": "tasa de depósito del Banco Central Europeo", "frecuencia": "diaria",
    },
    "GBP": {
        "nombre": "Libra", "con_articulo": "la libra", "par": "GBPUSD=X", "base_es_dolar": False,
        "serie_tasa": "Tasa overnight SONIA de Reino Unido (IUDSOIA)",
        "tasa": "tasa overnight SONIA de Reino Unido", "frecuencia": "diaria",
    },
    "JPY": {
        "nombre": "Yen", "con_articulo": "el yen", "par": "USDJPY=X", "base_es_dolar": True,
        "serie_tasa": "Tasa interbancaria de corto plazo de Japón (OCDE, IRSTCI01JPM156N)",
        "tasa": "tasa interbancaria de corto plazo de Japón", "frecuencia": "mensual",
    },
    "MXN": {
        "nombre": "Peso mexicano", "con_articulo": "el peso mexicano", "par": "USDMXN=X", "base_es_dolar": True,
        "serie_tasa": "Tasa interbancaria de corto plazo de México (OCDE, IRSTCI01MXM156N)",
        "tasa": "tasa interbancaria de corto plazo de México", "frecuencia": "mensual",
    },
    "BRL": {
        "nombre": "Real", "con_articulo": "el real", "par": "USDBRL=X", "base_es_dolar": True,
        "serie_tasa": "Tasa interbancaria de corto plazo de Brasil (OCDE, IRSTCI01BRM156N)",
        "tasa": "tasa interbancaria de corto plazo de Brasil", "frecuencia": "mensual",
    },
    "CLP": {
        "nombre": "Peso chileno", "con_articulo": "el peso chileno", "par": "USDCLP=X", "base_es_dolar": True,
        "serie_tasa": NOMBRE_TASA_CHILE,
        "tasa": "tasa de política monetaria (TPM) del Banco Central de Chile", "frecuencia": "diaria",
    },
}

# Monedas que están en la tabla de divisas pero sin tasa al día en la base (no se rellenan con otra cosa).
MONEDAS_SIN_TASA = {"AUD": "dólar australiano", "NZD": "dólar neozelandés", "CAD": "dólar canadiense", "CHF": "franco suizo"}


def nombre_de(ticker: str) -> str:
    """Nombre del par; si no está en el catálogo, el ticker mismo (nunca inventa un nombre)."""
    return PARES_FX.get(ticker, {}).get("nombre", ticker)


def etiqueta_corta(ticker: str) -> str:
    """«USDCLP=X» -> «USD/CLP»; el índice dólar queda como «DXY»."""
    if ticker == TICKER_DXY:
        return "DXY"
    limpio = ticker.replace("=X", "")
    return f"{limpio[:3]}/{limpio[3:]}"

