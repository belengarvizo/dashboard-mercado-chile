"""
Catálogo de los ETFs de bonos que muestra la sección «Renta Fija».

Los nombres son los que Yahoo Finance informa para cada fondo (verificados con una
consulta real antes de escribirlos, no de memoria), y la descripción resume el índice
que cada fondo replica. La lista de tickers que baja el cron diario vive en
constants.TICKERS_RENTA_FIJA (una prueba comprueba que las dos coincidan).

`plazo_referencia` es el plazo de la curva del Tesoro con el que se compara el precio
del fondo para MEDIR su duración (ver renta_fija.duracion_empirica). Es una referencia
APROXIMADA elegida según el rango de vencimientos del fondo: para un fondo de empresas o
de emergentes no existe un único plazo del Tesoro «correcto», y por eso la pantalla
muestra también el R² de la medición.
"""

ETFS_RENTA_FIJA: dict[str, dict] = {
    "SHY": {
        "nombre": "iShares 1-3 Year Treasury Bond ETF",
        "grupo": "Tesoro EEUU",
        "descripcion": "Bonos del Tesoro de EEUU que vencen en 1 a 3 años.",
        "plazo_referencia": 2,
    },
    "IEI": {
        "nombre": "iShares 3-7 Year Treasury Bond ETF",
        "grupo": "Tesoro EEUU",
        "descripcion": "Bonos del Tesoro de EEUU que vencen en 3 a 7 años.",
        "plazo_referencia": 5,
    },
    "IEF": {
        "nombre": "iShares 7-10 Year Treasury Bond ETF",
        "grupo": "Tesoro EEUU",
        "descripcion": "Bonos del Tesoro de EEUU que vencen en 7 a 10 años.",
        "plazo_referencia": 7,
    },
    "TLT": {
        "nombre": "iShares 20+ Year Treasury Bond ETF",
        "grupo": "Tesoro EEUU",
        "descripcion": "Bonos del Tesoro de EEUU que vencen en 20 años o más.",
        "plazo_referencia": 20,
    },
    "AGG": {
        "nombre": "iShares Core U.S. Aggregate Bond ETF",
        "grupo": "Mercado total",
        "descripcion": "Todo el mercado de bonos de EEUU de grado de inversión: Tesoro, hipotecarios respaldados por agencias y empresas.",
        "plazo_referencia": 7,
    },
    "VCSH": {
        "nombre": "Vanguard Short-Term Corporate Bond Index Fund ETF Shares",
        "grupo": "Empresas",
        "descripcion": "Bonos de empresas de EEUU de grado de inversión que vencen en 1 a 5 años.",
        "plazo_referencia": 3,
    },
    "LQD": {
        "nombre": "iShares iBoxx $ Investment Grade Corporate Bond ETF",
        "grupo": "Empresas",
        "descripcion": "Bonos en dólares de empresas de grado de inversión (las de mejor clasificación de crédito).",
        "plazo_referencia": 10,
    },
    "HYG": {
        "nombre": "iShares iBoxx $ High Yield Corporate Bond ETF",
        "grupo": "High yield",
        "descripcion": "Bonos en dólares de empresas con clasificación bajo grado de inversión: pagan más, pero quiebran más seguido.",
        "plazo_referencia": 5,
    },
    "EMB": {
        "nombre": "iShares J.P. Morgan USD Emerging Markets Bond ETF",
        "grupo": "Emergentes",
        "descripcion": "Bonos en dólares emitidos por gobiernos, entidades públicas y empresas de países emergentes.",
        "plazo_referencia": 10,
    },
    "TIP": {
        "nombre": "iShares TIPS Bond ETF",
        "grupo": "Inflación",
        "descripcion": "Bonos del Tesoro de EEUU ligados a la inflación (TIPS): su capital se reajusta con el IPC de EEUU.",
        "plazo_referencia": 5,
    },
}


def nombre_de(ticker: str) -> str:
    """Nombre completo del ETF; si no está en el catálogo, el ticker mismo (nunca inventa un nombre)."""
    return ETFS_RENTA_FIJA.get(ticker, {}).get("nombre", ticker)
