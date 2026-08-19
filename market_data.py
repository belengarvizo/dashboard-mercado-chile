"""
Cálculo de los indicadores de mercado de la sección "Importante" del Brief
Premercado. Vive fuera de app/dashboard.py (que tiene llamadas a Streamlit a
nivel de módulo) para que scripts/generar_brief.py pueda reutilizar la misma
lógica sin depender de un contexto de Streamlit.
"""

import numpy as np
import pandas as pd
from scipy import stats

# (etiqueta, tipo de tabla de origen, nombre/ticker, unidad a mostrar)
INDICADORES_PREMERCADO = [
    ("S&P 500", "accion", "^GSPC", ""),
    ("Dow Jones", "accion", "^DJI", ""),
    ("Cobre", "macro", "Precio del cobre (USD/oz troy)", "US$/oz troy"),
    ("Petróleo WTI", "accion", "CL=F", "US$/barril"),
    ("Bono UST 10 años", "macro", "Bono del Tesoro de EEUU a 10 años (UST10Y)", "%"),
    ("TPM EEUU", "macro", "Tasa de política monetaria de EEUU (Effective Federal Funds Rate)", "%"),
    ("IPSA (proxy ECH)", "accion", "ECH", ""),
    ("TPM Chile", "macro", "Tasa de política monetaria (TPM)", "%"),
    ("IPC (inflación anual)", "macro", "IPC variación 12 meses (inflación anual, empalme base 2023=100)", "%"),
    ("Imacec", "macro", "IMACEC", ""),
    ("Tasa de desempleo", "macro", "Tasa de desocupación nacional (INE, desestacionalizada)", "%"),
]


def calcular_cambio_reciente(serie: pd.Series) -> tuple[float, float, object, float] | None:
    """(valor actual, % de cambio vs la sesión anterior, fecha, cambio
    absoluto) a partir de una serie ordenada por fecha. Descarta
    observaciones NaN (dato no disponible, ej. una sesión de mercado
    todavía incompleta) y usa el último valor VÁLIDO junto con su fecha
    real — nunca devuelve NaN, y nunca junta un dato viejo con la fecha de
    hoy.

    El cambio absoluto es necesario además del % porque para un indicador
    que YA es una tasa/porcentaje (ej. TPM, inflación anual), el "% de
    cambio" es el cambio porcentual de la tasa misma (ej. de 4,34% a 3,52%
    es -18,8%), no el cambio en puntos porcentuales (-0,82 pp) que es lo
    que normalmente se espera ver para ese tipo de indicador — quien llama
    decide cuál mostrar según la unidad."""
    serie = serie.dropna()
    if len(serie) < 2:
        return None
    valor_actual = serie.iloc[-1]
    valor_anterior = serie.iloc[-2]
    if not valor_anterior:
        return None
    cambio_pct = (valor_actual / valor_anterior - 1) * 100
    cambio_absoluto = valor_actual - valor_anterior
    return float(valor_actual), float(cambio_pct), serie.index[-1], float(cambio_absoluto)


def calcular_retornos_reales(serie: pd.Series) -> pd.Series:
    """Retornos diarios de una serie de precios, excluyendo los días donde el
    precio no cambió respecto al anterior (dato congelado — no es volatilidad
    real cero, es ausencia de dato). Mismo criterio que la detección de
    "Atraso" del heatmap del dashboard: comparar cada valor con el del día
    anterior."""
    cambia = serie.ne(serie.shift(1))
    return serie.pct_change()[cambia]


def calcular_capm_regresion(exceso_portafolio: pd.Series, exceso_mercado: pd.Series) -> dict | None:
    """Regresión CAPM por mínimos cuadrados ordinarios sobre retornos DIARIOS
    en exceso: Rp,t - Rf,t = α + β(Rm,t - Rf,t) + εt. Devuelve α, β, R², sus
    errores estándar clásicos de OLS, el estadístico t de α (test bilateral
    H0: α=0), su p-value exacto vía la distribución t con n-2 grados de
    libertad (no la aproximación normal), y el intervalo de confianza 95%
    de α. t y p-value son invariantes a la frecuencia de anualización
    (anualizar α y SE(α) por el mismo factor no cambia t=α/SE(α))."""
    x = exceso_mercado.to_numpy()
    y = exceso_portafolio.to_numpy()
    n = len(x)
    if n < 3:
        return None

    x_media = x.mean()
    sxx = float(np.sum((x - x_media) ** 2))
    if sxx <= 0:
        return None

    beta = float(np.sum((x - x_media) * (y - y.mean())) / sxx)
    alfa = float(y.mean() - beta * x_media)

    residuos = y - (alfa + beta * x)
    gl = n - 2
    sigma2 = float(np.sum(residuos ** 2) / gl)
    se_alfa = (sigma2 * (1 / n + x_media ** 2 / sxx)) ** 0.5
    se_beta = (sigma2 / sxx) ** 0.5

    t_alfa = alfa / se_alfa if se_alfa > 0 else float("inf")
    p_valor = float(2 * stats.t.sf(abs(t_alfa), df=gl))
    t_critico = float(stats.t.ppf(0.975, df=gl))
    ic_95 = (alfa - t_critico * se_alfa, alfa + t_critico * se_alfa)

    ss_res = float(np.sum(residuos ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None

    return {
        "alfa": alfa, "beta": beta, "r2": r2, "se_alfa": se_alfa, "se_beta": se_beta,
        "t_alfa": t_alfa, "p_valor": p_valor, "ic_95": ic_95, "n": n, "gl": gl,
    }


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
