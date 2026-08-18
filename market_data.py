"""
Cálculo de los indicadores de mercado de la sección "Importante" del Brief
Premercado. Vive fuera de app/dashboard.py (que tiene llamadas a Streamlit a
nivel de módulo) para que scripts/generar_brief.py pueda reutilizar la misma
lógica sin depender de un contexto de Streamlit.
"""

import pandas as pd

# (etiqueta, tipo de tabla de origen, nombre/ticker, unidad a mostrar)
INDICADORES_PREMERCADO = [
    ("S&P 500", "accion", "^GSPC", ""),
    ("Cobre", "macro", "Precio del cobre (USD/oz troy)", "US$/oz troy"),
    ("Petróleo WTI", "accion", "CL=F", "US$/barril"),
    ("MSCI EM (EEM)", "accion", "EEM", "US$"),
    ("Bovespa", "accion", "^BVSP", ""),
    ("Bono UST 10 años", "macro", "Bono del Tesoro de EEUU a 10 años (UST10Y)", "%"),
]


def calcular_cambio_reciente(serie: pd.Series) -> tuple[float, float, object] | None:
    """(valor actual, % de cambio vs la sesión anterior, fecha) a partir de una serie ordenada por fecha."""
    if len(serie) < 2:
        return None
    valor_actual = serie.iloc[-1]
    valor_anterior = serie.iloc[-2]
    if not valor_anterior:
        return None
    cambio_pct = (valor_actual / valor_anterior - 1) * 100
    return float(valor_actual), float(cambio_pct), serie.index[-1]


def calcular_resumen_mercado(df_macro: pd.DataFrame, df_acciones: pd.DataFrame) -> list[dict]:
    """Para cada indicador de INDICADORES_PREMERCADO, devuelve
    {etiqueta, unidad, resultado} donde resultado es lo que devuelve
    calcular_cambio_reciente (o None si no hay datos suficientes)."""
    resultados = []
    for etiqueta, tipo, clave, unidad in INDICADORES_PREMERCADO:
        if tipo == "accion":
            serie = (
                df_acciones[df_acciones["ticker"] == clave]
                .sort_values("fecha")
                .set_index("fecha")["precio_cierre"]
            )
        else:
            serie = (
                df_macro[df_macro["nombre"] == clave]
                .sort_values("fecha")
                .set_index("fecha")["valor"]
            )
        resultados.append({
            "etiqueta": etiqueta,
            "unidad": unidad,
            "resultado": calcular_cambio_reciente(serie),
        })
    return resultados
