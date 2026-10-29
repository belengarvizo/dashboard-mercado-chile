"""
Catálogo de los subyacentes sobre los que la sección «Derivados» muestra una cadena de opciones real.

Son ETFs que ya se siguen en otras secciones del dashboard (así hay precio e historial de volatilidad propios,
sin tener que bajar nada nuevo) y que, verificado con una consulta real a Yahoo Finance, tienen una cadena de
opciones líquida (decenas de vencimientos, con volumen y interés abierto reales en los strikes cercanos al precio).
"""

SUBYACENTES: dict[str, dict] = {
    "SPY": {"nombre": "State Street SPDR S&P 500 ETF Trust", "descripcion": "El ETF más transado del mundo: sigue al S&P 500."},
    "QQQ": {"nombre": "Invesco QQQ Trust", "descripcion": "Sigue al Nasdaq-100: pesa mucho la tecnología."},
    "IWM": {"nombre": "iShares Russell 2000 ETF", "descripcion": "Empresas pequeñas de EEUU."},
    "DIA": {"nombre": "SPDR Dow Jones Industrial Average ETF Trust", "descripcion": "Sigue al Dow Jones Industrial Average."},
    "TLT": {"nombre": "iShares 20+ Year Treasury Bond ETF", "descripcion": "Bonos largos del Tesoro de EEUU: para ver opciones sobre renta fija, no solo acciones."},
}


def nombre_de(ticker: str) -> str:
    """Nombre completo del subyacente; si no está en el catálogo, el ticker mismo (nunca inventa un nombre)."""
    return SUBYACENTES.get(ticker, {}).get("nombre", ticker)
