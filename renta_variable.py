"""
Matemática de la sección «Renta Variable y ETFs»: métricas de un ETF de acciones, correlaciones y
comparación de un ETF con el índice que replica. Sin Streamlit, para poder probarla con series de
respuesta conocida.

Las cuentas que ya existen para los ETFs de bonos (cambios por período, volatilidad, caída máxima,
beta, Sharpe) se reutilizan de renta_fija.py: son las mismas fórmulas aplicadas a otro precio. Aquí
se agrega lo propio de las acciones (correlación, retorno contra el mercado, matriz de correlaciones,
seguimiento de un índice) y no se calcula duración, que no tiene sentido para una acción.

Todos los precios son AJUSTADOS por distribuciones (así los baja el cron), así que los retornos de un
ETF incluyen los dividendos que repartió. Un índice como el S&P 500 (^GSPC) NO los incluye: la
diferencia entre el ETF y su índice es en buena parte esos dividendos (ver comparar_con_indice).
"""
from __future__ import annotations

import pandas as pd

import renta_fija as rf

DIAS_HABILES_ANIO = rf.DIAS_HABILES_ANIO
MINIMO_DE_OBSERVACIONES = rf.MINIMO_DE_OBSERVACIONES


def _retornos_diarios(precios: pd.Series) -> pd.Series:
    return precios.dropna().sort_index().pct_change().dropna()


def _ultimos_dias(serie: pd.Series, dias: int | None) -> pd.Series:
    """Las observaciones de los últimos `dias` días corridos (todas si `dias` es None)."""
    if dias is None or serie.empty:
        return serie
    return serie[serie.index >= serie.index[-1] - pd.Timedelta(days=dias)]


def correlacion_contra(retornos: pd.Series, retornos_mercado: pd.Series) -> float | None:
    """Correlación entre los retornos diarios de un instrumento y los del mercado, entre -1 y 1."""
    conjunto = pd.concat([retornos, retornos_mercado], axis=1, join="inner", keys=["x", "m"]).dropna()
    # Una serie que no varía no tiene correlación. Se mira si hay valores distintos y no si std() == 0: por redondeo,
    # la desviación de una serie constante sale como 1e-19 y no como 0, y la correlación saldría como un número sin sentido.
    if len(conjunto) < MINIMO_DE_OBSERVACIONES or conjunto["x"].nunique() < 2 or conjunto["m"].nunique() < 2:
        return None
    return float(conjunto["x"].corr(conjunto["m"]))


def resumen_de_etf(precios: pd.Series, precios_mercado: pd.Series, tasa_libre_de_riesgo_pct: float | None) -> dict | None:
    """Todas las métricas de una fila de la tabla de ETFs de acciones, o None si no hay al menos 2 precios.

    `precios_mercado` es el ETF que hace de mercado (SPY, el del S&P 500): contra él se miden el beta, la
    correlación y el retorno relativo. Se usa un ETF y no el índice para que los dos lados incluyan
    dividendos y para que cotice en el mismo horario que el instrumento medido."""
    precios = precios.dropna().sort_index()
    if len(precios) < 2:
        return None
    mercado = precios_mercado.dropna().sort_index()
    retorno_1a = rf.retorno_ultimo_anio(precios)
    volatilidad = rf.volatilidad_anualizada(precios)
    retornos_del_anio = _ultimos_dias(precios.pct_change().dropna(), rf.DIAS_DEL_ANIO)
    retornos_mercado = mercado.pct_change().dropna()
    retorno_mercado_1a = rf.retorno_ultimo_anio(mercado) if len(mercado) >= 2 else None
    return {
        **rf.cambios_por_periodo(precios),
        "Retorno 1 año (%)": retorno_1a,
        "Volatilidad (%)": volatilidad,
        "Caída máxima 1 año (%)": rf.caida_maxima(precios),
        "Beta vs S&P 500": rf.beta_contra(retornos_del_anio, retornos_mercado),
        "Correlación vs S&P 500": correlacion_contra(retornos_del_anio, retornos_mercado),
        "Sharpe": rf.razon_de_sharpe(retorno_1a, tasa_libre_de_riesgo_pct, volatilidad),
        "Vs S&P 500 (pp)": None if retorno_1a is None or retorno_mercado_1a is None else retorno_1a - retorno_mercado_1a,
        "ultima_fecha": precios.index[-1],
    }


def matriz_de_correlacion(precios: pd.DataFrame, dias: int | None = None) -> pd.DataFrame:
    """Correlación entre los retornos diarios de todas las columnas, en los últimos `dias` días corridos.

    Solo cuentan los días en que TODAS las columnas tienen retorno, para que cada par se mida sobre las
    mismas fechas. Devuelve un DataFrame vacío si quedan menos de MINIMO_DE_OBSERVACIONES días comunes."""
    retornos = precios.sort_index().pct_change().dropna(how="any")
    retornos = _ultimos_dias(retornos, dias)
    if len(retornos) < MINIMO_DE_OBSERVACIONES:
        return pd.DataFrame()
    return retornos.corr()


def comparar_con_indice(etf: pd.Series, indice: pd.Series, dias: int = rf.DIAS_DEL_ANIO) -> dict | None:
    """Cuánto se parece un ETF al índice que replica, en los últimos `dias` días.

    Devuelve el retorno de cada uno, la diferencia (ETF menos índice, en puntos porcentuales), la correlación
    de sus retornos diarios y el error de seguimiento (desviación estándar anualizada de la diferencia entre
    los retornos diarios: mientras más baja, más fiel es la réplica). Si el índice es de precio puro, la
    diferencia incluye los dividendos que el ETF repartió. Devuelve None si no hay historia común suficiente."""
    conjunto = pd.concat([etf, indice], axis=1, join="inner", keys=["etf", "indice"]).dropna().sort_index()
    conjunto = _ultimos_dias(conjunto, dias)
    if len(conjunto) < MINIMO_DE_OBSERVACIONES:
        return None
    retornos = conjunto.pct_change().dropna()
    total_etf = float((conjunto["etf"].iloc[-1] / conjunto["etf"].iloc[0] - 1) * 100)
    total_indice = float((conjunto["indice"].iloc[-1] / conjunto["indice"].iloc[0] - 1) * 100)
    diferencia_diaria = retornos["etf"] - retornos["indice"]
    return {
        "retorno_etf": total_etf,
        "retorno_indice": total_indice,
        "diferencia": total_etf - total_indice,
        "correlacion": float(retornos["etf"].corr(retornos["indice"])),
        "error_de_seguimiento": float(diferencia_diaria.std() * DIAS_HABILES_ANIO**0.5 * 100),
        "dias": len(conjunto),
        "desde": conjunto.index[0],
        "hasta": conjunto.index[-1],
    }
