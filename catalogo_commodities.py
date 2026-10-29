"""
Catálogo de los commodities que muestra la sección «Commodities».

QUÉ SON. Todos son contratos de **futuros**, no ETFs: el precio de Yahoo Finance (CL=F, GC=F, ...) es el del contrato
más cercano a vencer (*front month*), que es la referencia estándar de precio de cada commodity en el mundo real —
la que citan los noticieros y el IPoM del Banco Central. Se prefirió a un ETF porque un ETF de materias primas (USO,
UNG) tiene un costo de "rolar" el contrato cada mes (*roll decay*) que distorsiona su retorno de largo plazo frente
al precio real del commodity; un futuro no lo tiene, porque lo que se mide es siempre el contrato cercano.

LA UNIDAD IMPORTA. Cada commodity se cotiza en una unidad y una convención distintas (dólares por onza, por libra,
por barril, centavos por bushel): son las especificaciones estándar de cada bolsa (CME, ICE), públicas y estables,
no un dato que este catálogo mida. `unidad` se muestra en el tooltip para que un precio nunca se lea sin su unidad.

LA LISTA QUE BAJA EL CRON vive en constants.TICKERS_COMMODITIES (una prueba comprueba que las dos coincidan).
"""

COMMODITIES: dict[str, dict] = {
    "CL=F": {
        "nombre": "Petróleo crudo WTI (West Texas Intermediate)", "grupo": "Energía", "unidad": "USD por barril",
        "descripcion": "El crudo de referencia de EEUU. Su futuro más cercano a vencer, en la bolsa NYMEX.",
    },
    "NG=F": {
        "nombre": "Gas natural (Henry Hub)", "grupo": "Energía", "unidad": "USD por millón de BTU",
        "descripcion": "El gas natural de referencia de EEUU. Mucho más volátil que el petróleo: la demanda cambia fuerte con el clima.",
    },
    "GC=F": {
        "nombre": "Oro", "grupo": "Metales", "unidad": "USD por onza troy",
        "descripcion": "El metal refugio por excelencia: suele subir cuando el mercado tiene miedo o espera más inflación.",
    },
    "SI=F": {
        "nombre": "Plata", "grupo": "Metales", "unidad": "USD por onza troy",
        "descripcion": "Metal precioso con uso industrial (electrónica, paneles solares): se mueve con el oro, pero con más volatilidad.",
    },
    "HG=F": {
        "nombre": "Cobre", "grupo": "Metales", "unidad": "USD por libra",
        "descripcion": "El metal del que depende buena parte de la economía chilena. Cotiza en la misma unidad que el precio del Banco Central.",
    },
    "ZC=F": {
        "nombre": "Maíz", "grupo": "Agrícolas", "unidad": "centavos de USD por bushel",
        "descripcion": "El grano más transado del mundo: insumo de alimentación animal y de etanol en EEUU.",
    },
    "ZW=F": {
        "nombre": "Trigo", "grupo": "Agrícolas", "unidad": "centavos de USD por bushel",
        "descripcion": "Base del pan y la pasta en buena parte del mundo. Sensible a sequías y a conflictos en zonas productoras.",
    },
    "ZS=F": {
        "nombre": "Soya (poroto de soja)", "grupo": "Agrícolas", "unidad": "centavos de USD por bushel",
        "descripcion": "Insumo clave de alimentación animal y de aceite. China es su mayor comprador mundial.",
    },
    "KC=F": {
        "nombre": "Café (arábica)", "grupo": "Agrícolas", "unidad": "centavos de USD por libra",
        "descripcion": "El café arábica, el de mejor calidad. Brasil y Vietnam son sus mayores productores; el clima en esos países lo mueve.",
    },
}

GRUPOS_EN_ORDEN = ["Energía", "Metales", "Agrícolas"]


def tickers_del_grupo(grupo: str) -> list[str]:
    return [t for t, d in COMMODITIES.items() if d["grupo"] == grupo]


def nombre_de(ticker: str) -> str:
    """Nombre completo del commodity; si no está en el catálogo, el ticker mismo (nunca inventa un nombre)."""
    return COMMODITIES.get(ticker, {}).get("nombre", ticker)
