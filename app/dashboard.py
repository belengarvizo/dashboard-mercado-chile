"""
Dashboard principal. Lee todo desde PostgreSQL (nunca llama a las
APIs directamente) para que cargue rápido sin importar quién lo abra.

Correr localmente con: streamlit run app/dashboard.py
"""

import math
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from matplotlib.colors import LinearSegmentedColormap
from scipy import stats
from sqlalchemy import text
from models import get_engine
from constants import (
    TICKERS_IPSA,
    TICKERS_IPSA_PRINCIPALES,
    TICKER_PROXY_IPSA,
    TICKERS_BENCHMARK,
    TICKERS_MAGNIFICAS,
)
from market_data import calcular_resumen_mercado

st.set_page_config(page_title="Mercado Chile", layout="wide")

# Paleta categórica de orden fijo (nunca se reasigna por índice de la
# selección), y diverging rojo-gris-verde para el heatmap de desempeño.
PALETA_CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
CMAP_DIVERGENTE = LinearSegmentedColormap.from_list("rojo_verde", ["#d03b3b", "#f0efec", "#0ca30c"])
# Secuencial (una sola tonalidad, claro→oscuro) para magnitudes que no son "ganancia/pérdida", como volatilidad.
CMAP_SECUENCIAL = LinearSegmentedColormap.from_list("azul_secuencial", ["#fcfcfb", "#2a78d6"])
# Diverging azul-gris-rojo para la matriz de correlación (no es un juicio de valor bueno/malo, por eso no usa verde/rojo).
COLORSCALE_CORRELACION = [[0.0, "#e34948"], [0.5, "#f0efec"], [1.0, "#2a78d6"]]

# Event study TPM → tipo de cambio: ventana de estimación y ventana de evento (en días hábiles).
DIAS_ESTIMACION_EVENT_STUDY = 30
DIAS_EVENTO_EVENT_STUDY = range(-2, 3)  # -2, -1, 0, +1, +2

# Métricas de riesgo: ventana de volatilidad (días hábiles) y de VaR (~2 años calendario).
VENTANA_VOLATILIDAD = 21
VENTANA_VAR = pd.DateOffset(years=2)

# Ajuste de VaR por liquidez: ventana para el monto transado diario promedio,
# y multiplicador heurístico aplicado al VaR del cuartil menos líquido.
VENTANA_LIQUIDEZ = pd.DateOffset(months=3)
MULTIPLICADOR_LIQUIDEZ = 1.3

# Backtester estrategia TPM: entrada en el cierre del día del evento, salida
# 2 días hábiles después, costo de transacción por operación (entrada+salida).
DIA_ENTRADA_BACKTEST = 0
DIA_SALIDA_BACKTEST = 2
COSTO_TRANSACCION_BACKTEST = 0.0008  # 8 puntos base por operación
N_PERMUTACIONES_BACKTEST = 1000

st.title("Dashboard de mercado chileno")
st.caption("Datos del Banco Central de Chile y Yahoo Finance, actualizados diariamente")

engine = get_engine()


@st.cache_data(ttl=3600)  # cachea 1 hora, para no golpear la BD en cada click
def cargar_series_macro():
    query = "SELECT nombre, fecha, valor FROM series_macro ORDER BY fecha"
    return pd.read_sql(query, engine)


@st.cache_data(ttl=3600)
def cargar_precios_acciones():
    query = "SELECT ticker, fecha, precio_cierre, volumen FROM precios_acciones ORDER BY fecha"
    return pd.read_sql(query, engine)


@st.cache_data(ttl=3600)
def cargar_ultima_actualizacion():
    query = "SELECT fuente, ultima_actualizacion FROM metadata_actualizacion"
    return pd.read_sql(query, engine)


@st.cache_data(ttl=3600)
def cargar_noticias():
    query = "SELECT fuente, titulo, link, fecha_publicacion FROM noticias ORDER BY fecha_publicacion DESC"
    return pd.read_sql(query, engine)


@st.cache_data(ttl=3600)
def cargar_brief_diario():
    # El más reciente disponible, no estrictamente "hoy": si el cron todavía no
    # corrió hoy (ej. antes de las 6 AM) es mejor mostrar el último brief real
    # que no mostrar nada.
    query = "SELECT fecha, contenido, generado_en FROM brief_diario ORDER BY fecha DESC LIMIT 1"
    return pd.read_sql(query, engine)


def calcular_retornos_reales(serie: pd.Series) -> pd.Series:
    """Retornos diarios de una serie de precios, excluyendo los días donde el
    precio no cambió respecto al anterior (dato congelado — no es volatilidad
    real cero, es ausencia de dato). Mismo criterio que la detección de
    "Atraso" del heatmap: comparar cada valor con el del día anterior."""
    cambia = serie.ne(serie.shift(1))
    return serie.pct_change()[cambia]


@st.cache_data(ttl=3600)
def calcular_crp_y_prima_mercado(df_macro: pd.DataFrame, df_acciones: pd.DataFrame) -> dict:
    """Tasa libre de riesgo local (PDBC), tasa libre de riesgo EEUU (UST10),
    spread PDBC-UST10 como proxy de prima de riesgo país (CRP, enfoque
    Damodaran, no EMBI+), y prima de mercado local (retorno histórico
    anualizado del proxy del IPSA menos la tasa libre de riesgo local).
    Todo en puntos porcentuales, reutilizando series que ya están en la BD."""
    df_macro = df_macro.assign(fecha=pd.to_datetime(df_macro["fecha"]))

    pdbc = (
        df_macro[df_macro["nombre"] == "Tasa libre de riesgo CLP (PDBC 14 días)"]
        .sort_values("fecha")["valor"]
    )
    ust10 = (
        df_macro[df_macro["nombre"] == "Bono del Tesoro de EEUU a 10 años (UST10Y)"]
        .sort_values("fecha")["valor"]
    )
    rf_cl = float(pdbc.iloc[-1]) if len(pdbc) else None
    rf_ust = float(ust10.iloc[-1]) if len(ust10) else None
    crp = (rf_cl - rf_ust) if rf_cl is not None and rf_ust is not None else None

    df_acciones = df_acciones.assign(fecha=pd.to_datetime(df_acciones["fecha"]))
    proxy = (
        df_acciones[df_acciones["ticker"] == TICKER_PROXY_IPSA]
        .sort_values("fecha")
        .set_index("fecha")["precio_cierre"]
    )
    retornos_proxy_reales = calcular_retornos_reales(proxy).dropna()
    retorno_anual_mercado = (
        retornos_proxy_reales.mean() * 252 * 100 if len(retornos_proxy_reales) >= 30 else None
    )
    prima_mercado_local = (
        retorno_anual_mercado - rf_cl
        if retorno_anual_mercado is not None and rf_cl is not None
        else None
    )

    return {"rf_cl": rf_cl, "rf_ust": rf_ust, "crp": crp, "prima_mercado_local": prima_mercado_local}


@st.cache_data(ttl=3600)
def calcular_resumen_ipsa(df_todas: pd.DataFrame, df_macro: pd.DataFrame) -> pd.DataFrame:
    """% de cambio 1D/1W/1M/YTD, Beta (vs el proxy del IPSA), volatilidad y
    costo de capital CAPM (local y ajustado por riesgo país) para cada acción
    del IPSA."""
    # pd.read_sql devuelve la columna "fecha" (tipo DATE en Postgres) como
    # datetime.date en vez de Timestamp; se convierte para poder comparar
    # fechas e indexar por Timedelta más abajo.
    df_todas = df_todas.assign(fecha=pd.to_datetime(df_todas["fecha"]))

    proxy = (
        df_todas[df_todas["ticker"] == TICKER_PROXY_IPSA]
        .sort_values("fecha")
        .set_index("fecha")["precio_cierre"]
    )
    retornos_proxy = proxy.pct_change()

    capm_insumos = calcular_crp_y_prima_mercado(df_macro, df_todas)
    rf_cl = capm_insumos["rf_cl"]
    crp = capm_insumos["crp"]
    prima_mercado_local = capm_insumos["prima_mercado_local"]

    filas = []
    for ticker in TICKERS_IPSA:
        serie = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")["precio_cierre"]
        )
        if len(serie) < 2:
            continue

        ultimo = serie.iloc[-1]
        fecha_ultima = serie.index[-1]

        def cambio_desde(dias_atras):
            objetivo = fecha_ultima - pd.Timedelta(days=dias_atras)
            previos = serie[serie.index <= objetivo]
            return (ultimo / previos.iloc[-1] - 1) * 100 if not previos.empty else None

        inicio_anio = serie[serie.index >= pd.Timestamp(fecha_ultima.year, 1, 1)]
        cambio_ytd = (ultimo / inicio_anio.iloc[0] - 1) * 100 if not inicio_anio.empty else None

        # Beta: regresión (cov/var) de retornos diarios del último año vs el proxy del IPSA.
        un_anio_atras = fecha_ultima - pd.Timedelta(days=365)
        retornos_ticker = serie.pct_change()
        conjunto = pd.concat(
            [
                retornos_ticker[retornos_ticker.index >= un_anio_atras],
                retornos_proxy[retornos_proxy.index >= un_anio_atras],
            ],
            axis=1, join="inner", keys=["ticker", "mercado"],
        ).dropna()
        beta = (
            conjunto["mercado"].cov(conjunto["ticker"]) / conjunto["mercado"].var()
            if len(conjunto) >= 30 and conjunto["mercado"].var() > 0
            else None
        )

        # Fecha del último dato "real": Yahoo Finance suele repetir el mismo
        # precio de cierre por varias semanas para tickers .SN antes de
        # refrescarlo, así que no basta con mirar la última fila descargada.
        cambia = serie.ne(serie.shift(1))
        cambia.iloc[0] = True  # el primer dato de la serie siempre cuenta como real
        ultima_fecha_real = serie.index[cambia][-1]

        hoy = pd.Timestamp.now().normalize()
        dias_habiles_atraso = int(np.busday_count(ultima_fecha_real.date(), hoy.date()))
        atrasado = dias_habiles_atraso > 5

        # Volatilidad anualizada: rolling 21 días hábiles sobre retornos "reales"
        # únicamente (se excluyen los días de precio congelado — un retorno de 0%
        # por dato congelado no es volatilidad real cero, es ausencia de dato).
        retornos_reales_ticker = retornos_ticker[cambia].dropna()
        volatilidad_anualizada = (
            retornos_reales_ticker.tail(VENTANA_VOLATILIDAD).std() * (252 ** 0.5) * 100
            if len(retornos_reales_ticker) >= VENTANA_VOLATILIDAD
            else None
        )

        # Costo de capital CAPM: versión local, y ajustada sumando el spread
        # PDBC-UST10 como proxy de prima de riesgo país (ver nota metodológica
        # en el dashboard sobre por qué se muestran ambas).
        if beta is not None and rf_cl is not None and prima_mercado_local is not None:
            capm_local = rf_cl + beta * prima_mercado_local
            capm_crp = capm_local + crp if crp is not None else None
        else:
            capm_local = None
            capm_crp = None

        filas.append({
            "Ticker": ticker.replace(".SN", ""),
            "1D %": cambio_desde(1),
            "1W %": cambio_desde(7),
            "1M %": cambio_desde(30),
            "YTD %": cambio_ytd,
            "Beta": beta,
            "Volatilidad anualizada (%)": volatilidad_anualizada,
            "CAPM local (%)": capm_local,
            "CAPM + CRP (%)": capm_crp,
            "Última actualización": (
                ("⚠️ " if atrasado else "") + ultima_fecha_real.strftime("%Y-%m-%d")
            ),
            "Atraso": atrasado,
        })

    return pd.DataFrame(filas).set_index("Ticker")


def _p_valor_normal(t_stat: float) -> float:
    """p-valor a dos colas para un estadístico t, aproximando con la normal estándar."""
    return 2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2))))


@st.cache_data(ttl=3600)
def calcular_event_study_tpm(df_macro: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Event study: impacto de los cambios de la TPM sobre el tipo de cambio USD/CLP.

    Eventos = fechas donde la TPM cambió respecto al día hábil anterior. Para
    cada evento se estima el retorno "normal" del tipo de cambio (promedio de
    los 30 días hábiles previos) y se calcula el retorno anormal (AR) en la
    ventana de evento (-2 a +2 días hábiles). El t-test usa la desviación
    estándar de cada ventana de estimación (enfoque simple tipo Brown &
    Warner / MacKinlay), no la dispersión entre eventos.
    """
    df_macro = df_macro.assign(fecha=pd.to_datetime(df_macro["fecha"]))

    tpm = (
        df_macro[df_macro["nombre"] == "Tasa de política monetaria (TPM)"]
        .sort_values("fecha")
        .set_index("fecha")["valor"]
    )
    tco = (
        df_macro[df_macro["nombre"] == "Tipo de cambio observado"]
        .sort_values("fecha")
        .set_index("fecha")["valor"]
    )
    retornos_tco = tco.pct_change() * 100  # en % para que AAR/CAAR queden directamente en %
    fechas_tco = tco.index

    cambia = tpm.ne(tpm.shift(1))
    if len(cambia):
        cambia.iloc[0] = False  # el primer dato de la serie no es un "cambio"
    fechas_evento = tpm.index[cambia]
    tpm_dia_anterior = tpm.shift(1)

    dias_evento = list(DIAS_EVENTO_EVENT_STUDY)
    filas_eventos = []
    eventos_validos = []  # {"ars": {dia: AR}, "sigma": desviación de la ventana de estimación}

    for fecha_evt in fechas_evento:
        pos = fechas_tco.searchsorted(fecha_evt)
        if pos >= len(fechas_tco) or fechas_tco[pos] != fecha_evt:
            continue  # el evento no cae en un día con dato de tipo de cambio

        inicio_estimacion = pos - DIAS_ESTIMACION_EVENT_STUDY
        if inicio_estimacion < 1 or pos + max(dias_evento) >= len(fechas_tco):
            continue  # sin suficiente historia antes o después del evento

        ventana_estimacion = retornos_tco.iloc[inicio_estimacion:pos]
        if len(ventana_estimacion) < DIAS_ESTIMACION_EVENT_STUDY or ventana_estimacion.isna().any():
            continue

        retorno_normal = ventana_estimacion.mean()
        sigma_estimacion = ventana_estimacion.std()
        if not sigma_estimacion or pd.isna(sigma_estimacion):
            continue

        retornos_evento = retornos_tco.iloc[pos + min(dias_evento): pos + max(dias_evento) + 1]
        if len(retornos_evento) != len(dias_evento) or retornos_evento.isna().any():
            continue

        ars = {dia: retornos_evento.iloc[i] - retorno_normal for i, dia in enumerate(dias_evento)}
        car_evento = sum(ars.values())
        cambio_pb = round((tpm.loc[fecha_evt] - tpm_dia_anterior.loc[fecha_evt]) * 100)

        filas_eventos.append({
            "Fecha": fecha_evt.strftime("%Y-%m-%d"),
            "Dirección": "Alza" if cambio_pb > 0 else "Baja",
            "Magnitud (pb)": cambio_pb,
            "CAR (%)": car_evento,
        })
        eventos_validos.append({"ars": ars, "sigma": sigma_estimacion})

    df_eventos = pd.DataFrame(filas_eventos)

    n = len(eventos_validos)
    var_promedio = sum(e["sigma"] ** 2 for e in eventos_validos) / n if n else None

    filas_agg = []
    caar = 0.0
    for k, dia in enumerate(dias_evento, start=1):
        if n:
            aar = sum(e["ars"][dia] for e in eventos_validos) / n
            caar += aar
            se_aar = (var_promedio / n) ** 0.5
            se_caar = se_aar * (k ** 0.5)
            t_aar = aar / se_aar if se_aar else None
            t_caar = caar / se_caar if se_caar else None
        else:
            aar = t_aar = t_caar = None

        filas_agg.append({
            "Día relativo": dia,
            "AAR (%)": aar,
            "t-stat AAR": t_aar,
            "p-valor AAR": _p_valor_normal(t_aar) if t_aar is not None else None,
            "CAAR (%)": caar if n else None,
            "t-stat CAAR": t_caar,
        })

    df_agregado = pd.DataFrame(filas_agg)
    return df_eventos, df_agregado, n


@st.cache_data(ttl=3600)
def calcular_tests_direccion(df_eventos: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """t-test del CAR contra cero para cada dirección (alza/baja), y test de
    diferencia de medias (Welch, sin asumir varianzas iguales) entre ambas."""
    car_alza = df_eventos.loc[df_eventos["Dirección"] == "Alza", "CAR (%)"]
    car_baja = df_eventos.loc[df_eventos["Dirección"] == "Baja", "CAR (%)"]

    filas = []
    for etiqueta, serie in [("Alza (sube TPM)", car_alza), ("Baja (baja TPM)", car_baja)]:
        if len(serie) >= 2:
            t_stat, p_valor = stats.ttest_1samp(serie, popmean=0)
        else:
            t_stat, p_valor = None, None
        filas.append({
            "Grupo": etiqueta,
            "n": len(serie),
            "CAR medio (%)": serie.mean() if len(serie) else None,
            "t-stat (vs 0)": t_stat,
            "p-valor (vs 0)": p_valor,
        })
    df_direccion = pd.DataFrame(filas)

    if len(car_alza) >= 2 and len(car_baja) >= 2:
        t_diff, p_diff = stats.ttest_ind(car_alza, car_baja, equal_var=False)
        diferencia = {
            "diferencia_medias": car_alza.mean() - car_baja.mean(),
            "t_stat": t_diff,
            "p_valor": p_diff,
        }
    else:
        diferencia = {"diferencia_medias": None, "t_stat": None, "p_valor": None}

    return df_direccion, diferencia


@st.cache_data(ttl=3600)
def calcular_cuartiles_liquidez(df_todas: pd.DataFrame) -> pd.DataFrame:
    """Monto transado diario promedio (precio × volumen) de los últimos 3
    meses para las 30 acciones del IPSA, clasificado en cuartiles de liquidez."""
    df_todas = df_todas.assign(fecha=pd.to_datetime(df_todas["fecha"]))
    fecha_corte = pd.Timestamp.now().normalize() - VENTANA_LIQUIDEZ

    filas = []
    for ticker in TICKERS_IPSA:
        datos = df_todas[(df_todas["ticker"] == ticker) & (df_todas["fecha"] >= fecha_corte)]
        if datos.empty:
            continue
        monto_diario = (datos["precio_cierre"] * datos["volumen"].fillna(0)).mean()
        filas.append({"Activo": ticker.replace(".SN", ""), "Monto transado diario promedio": monto_diario})

    df_liquidez = pd.DataFrame(filas).set_index("Activo")
    df_liquidez["Cuartil liquidez"] = pd.qcut(
        df_liquidez["Monto transado diario promedio"], 4,
        labels=["Q1 (menos líquido)", "Q2", "Q3", "Q4 (más líquido)"],
    )
    return df_liquidez


@st.cache_data(ttl=3600)
def calcular_var(df_todas: pd.DataFrame) -> pd.DataFrame:
    """VaR histórico y paramétrico (95% y 99%) para las 5 acciones principales
    y un portafolio hipotético equiponderado, sobre los últimos ~2 años de
    retornos "reales" (excluyendo días de precio congelado). El VaR de cada
    acción individual se multiplica por MULTIPLICADOR_LIQUIDEZ si su liquidez
    (monto transado diario promedio de los últimos 3 meses, contra las 30
    acciones del IPSA) cae en el cuartil menos líquido — el portafolio no se
    ajusta, porque esa clasificación es por acción individual."""
    df_todas = df_todas.assign(fecha=pd.to_datetime(df_todas["fecha"]))
    fecha_corte = pd.Timestamp.now().normalize() - VENTANA_VAR

    retornos_por_ticker = {}
    for ticker in TICKERS_IPSA_PRINCIPALES:
        serie = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")["precio_cierre"]
        )
        serie = serie[serie.index >= fecha_corte]
        retornos_por_ticker[ticker.replace(".SN", "")] = calcular_retornos_reales(serie)

    df_retornos = pd.DataFrame(retornos_por_ticker)
    # Portafolio equiponderado: promedio simple de los 5 retornos, solo en fechas
    # donde los 5 tienen un retorno "real" ese día (skipna=False descarta la
    # fecha completa si a algún componente le falta el dato).
    df_retornos["Portafolio (equiponderado)"] = df_retornos.mean(axis=1, skipna=False)

    df_liquidez = calcular_cuartiles_liquidez(df_todas)

    filas = []
    for nombre in df_retornos.columns:
        r = df_retornos[nombre].dropna()
        if len(r) < 30:
            continue
        mu, sigma = r.mean(), r.std()

        es_menos_liquido = (
            nombre in df_liquidez.index
            and df_liquidez.loc[nombre, "Cuartil liquidez"] == "Q1 (menos líquido)"
        )
        multiplicador = MULTIPLICADOR_LIQUIDEZ if es_menos_liquido else 1.0

        filas.append({
            "Activo": nombre,
            "n": len(r),
            "Cuartil liquidez": df_liquidez.loc[nombre, "Cuartil liquidez"] if nombre in df_liquidez.index else "—",
            "VaR histórico 95% (%)": -np.percentile(r, 5) * 100 * multiplicador,
            "VaR paramétrico 95% (%)": -(mu + stats.norm.ppf(0.05) * sigma) * 100 * multiplicador,
            "VaR histórico 99% (%)": -np.percentile(r, 1) * 100 * multiplicador,
            "VaR paramétrico 99% (%)": -(mu + stats.norm.ppf(0.01) * sigma) * 100 * multiplicador,
        })

    return pd.DataFrame(filas).set_index("Activo")


@st.cache_data(ttl=3600)
def calcular_matriz_correlacion_ipsa(df_todas: pd.DataFrame) -> pd.DataFrame:
    """Matriz de correlación de retornos diarios "reales" (sin días de precio
    congelado) entre las 30 acciones del IPSA."""
    df_todas = df_todas.assign(fecha=pd.to_datetime(df_todas["fecha"]))

    retornos_por_ticker = {}
    for ticker in TICKERS_IPSA:
        serie = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")["precio_cierre"]
        )
        retornos_por_ticker[ticker.replace(".SN", "")] = calcular_retornos_reales(serie)

    # .corr() usa observaciones pairwise-completas: cada par de acciones se
    # correlaciona solo con las fechas donde ambas tienen un retorno real,
    # sin exigir que las 30 coincidan el mismo día.
    return pd.DataFrame(retornos_por_ticker).corr()


@st.cache_data(ttl=3600)
def calcular_trades_backtest_tpm(df_macro: pd.DataFrame) -> pd.DataFrame:
    """Retorno crudo del USD/CLP para cada evento de TPM (misma detección de
    eventos que el Event Study), entre el cierre del día del evento y el
    cierre DIA_SALIDA_BACKTEST días hábiles después."""
    df_macro = df_macro.assign(fecha=pd.to_datetime(df_macro["fecha"]))

    tpm = (
        df_macro[df_macro["nombre"] == "Tasa de política monetaria (TPM)"]
        .sort_values("fecha")
        .set_index("fecha")["valor"]
    )
    tco = (
        df_macro[df_macro["nombre"] == "Tipo de cambio observado"]
        .sort_values("fecha")
        .set_index("fecha")["valor"]
    )
    fechas_tco = tco.index

    cambia = tpm.ne(tpm.shift(1))
    if len(cambia):
        cambia.iloc[0] = False
    fechas_evento = tpm.index[cambia]
    tpm_dia_anterior = tpm.shift(1)

    filas = []
    for fecha_evt in fechas_evento:
        pos = fechas_tco.searchsorted(fecha_evt)
        if pos >= len(fechas_tco) or fechas_tco[pos] != fecha_evt:
            continue  # el evento no cae en un día con dato de tipo de cambio
        if pos + DIA_SALIDA_BACKTEST >= len(fechas_tco):
            continue  # sin suficientes días después del evento para salir

        precio_entrada = tco.iloc[pos + DIA_ENTRADA_BACKTEST]
        precio_salida = tco.iloc[pos + DIA_SALIDA_BACKTEST]
        retorno_crudo = precio_salida / precio_entrada - 1

        cambio_pb = round((tpm.loc[fecha_evt] - tpm_dia_anterior.loc[fecha_evt]) * 100)

        filas.append({
            "Fecha": fecha_evt,
            "Dirección": "Alza" if cambio_pb > 0 else "Baja",
            "Retorno crudo USD/CLP": retorno_crudo,
        })

    return pd.DataFrame(filas).sort_values("Fecha").reset_index(drop=True)


def _retornos_netos_estrategia(retornos_crudos: pd.Series, direcciones) -> pd.Series:
    """Retorno neto por trade: TPM sube → corto USD/CLP (gana si el dólar baja);
    TPM baja → largo USD/CLP (gana si el dólar sube); menos el costo de
    transacción por operación."""
    signo = np.where(np.asarray(direcciones) == "Alza", -1, 1)
    return signo * retornos_crudos.to_numpy() - COSTO_TRANSACCION_BACKTEST


@st.cache_data(ttl=3600)
def calcular_backtest_tpm(df_macro: pd.DataFrame) -> dict:
    """Backtest de la estrategia direccional TPM → USD/CLP, con curva de
    equity, métricas de desempeño, y un test de permutación (mezclando la
    dirección de los eventos 1000 veces) como control de significancia."""
    df_trades = calcular_trades_backtest_tpm(df_macro)
    n_eventos = len(df_trades)

    if n_eventos < 2:
        return {"df_trades": df_trades, "n_eventos": n_eventos}

    retornos_netos = _retornos_netos_estrategia(df_trades["Retorno crudo USD/CLP"], df_trades["Dirección"])
    df_trades = df_trades.copy()
    df_trades["Retorno neto"] = retornos_netos
    df_trades["Equity"] = (1 + df_trades["Retorno neto"]).cumprod()

    retorno_total = (df_trades["Equity"].iloc[-1] - 1) * 100
    retorno_promedio = df_trades["Retorno neto"].mean() * 100
    pct_ganadoras = (df_trades["Retorno neto"] > 0).mean() * 100

    años_span = (df_trades["Fecha"].max() - df_trades["Fecha"].min()).days / 365.25
    eventos_por_año = n_eventos / años_span if años_span > 0 else None

    media, desvio = df_trades["Retorno neto"].mean(), df_trades["Retorno neto"].std()
    sharpe = (
        media / desvio * (eventos_por_año ** 0.5)
        if desvio and eventos_por_año
        else None
    )

    drawdown = df_trades["Equity"] / df_trades["Equity"].cummax() - 1
    max_drawdown = drawdown.min() * 100

    # --- Test de permutación: ¿el resultado real supera a mezclas al azar de la dirección? ---
    rng = np.random.default_rng(42)  # semilla fija para que el resultado sea reproducible
    direcciones_originales = df_trades["Dirección"].to_numpy()
    retornos_crudos = df_trades["Retorno crudo USD/CLP"]

    retornos_totales_perm = np.empty(N_PERMUTACIONES_BACKTEST)
    for i in range(N_PERMUTACIONES_BACKTEST):
        direcciones_mezcladas = rng.permutation(direcciones_originales)
        retornos_netos_mezcla = _retornos_netos_estrategia(retornos_crudos, direcciones_mezcladas)
        equity_mezcla = np.cumprod(1 + retornos_netos_mezcla)
        retornos_totales_perm[i] = (equity_mezcla[-1] - 1) * 100

    percentil_real = float((retornos_totales_perm < retorno_total).mean() * 100)

    return {
        "df_trades": df_trades,
        "n_eventos": n_eventos,
        "retorno_total": retorno_total,
        "retorno_promedio": retorno_promedio,
        "pct_ganadoras": pct_ganadoras,
        "eventos_por_año": eventos_por_año,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "retornos_totales_perm": retornos_totales_perm,
        "percentil_real": percentil_real,
    }


# --- Sidebar: info de última actualización ---
with st.sidebar:
    st.subheader("Última actualización")
    try:
        meta = cargar_ultima_actualizacion()
        for _, fila in meta.iterrows():
            st.text(f"{fila['fuente']}: {fila['ultima_actualizacion']}")
    except Exception:
        st.warning("Aún no hay datos cargados. Corre los scripts de actualización primero.")

# --- Barra de última actualización (visible arriba, antes de las pestañas) ---
NOMBRES_FUENTE = {"bcch": "Banco Central de Chile", "yfinance": "Yahoo Finance"}
try:
    meta = cargar_ultima_actualizacion()
    columnas_meta = st.columns(len(meta)) if len(meta) else []
    for col, (_, fila) in zip(columnas_meta, meta.iterrows()):
        with col:
            st.caption(
                f"🔄 **{NOMBRES_FUENTE.get(fila['fuente'], fila['fuente'])}**: "
                f"{fila['ultima_actualizacion'].strftime('%d-%m-%Y %H:%M')}"
            )
except Exception:
    st.caption("Aún no hay datos cargados. Corre los scripts de actualización primero.")

(
    tab_premercado, tab_macro, tab_acciones, tab_riesgo, tab_magnificas,
    tab_benchmark, tab_event_study, tab_backtester,
) = st.tabs([
    "Brief Premercado", "Indicadores macro", "Acciones IPSA", "Riesgo", "7 Magníficas",
    "Benchmark", "Event Study TPM", "Backtester: Estrategia TPM",
])

# --- Tab 0: Brief Premercado ---
with tab_premercado:
    st.caption(
        "Para revisar antes de que abra la Bolsa de Santiago — pensado para leerse "
        "rápido, no para analizar en vivo."
    )

    st.subheader("Importante")

    try:
        df_macro = cargar_series_macro()
        df_acciones = cargar_precios_acciones()
        indicadores = calcular_resumen_mercado(df_macro, df_acciones)

        columnas = st.columns(len(indicadores))
        for col, ind in zip(columnas, indicadores):
            with col:
                if ind["resultado"]:
                    valor, cambio_pct, fecha = ind["resultado"]
                    valor_texto = f"{valor:,.2f}" + (f" {ind['unidad']}" if ind["unidad"] else "")
                    st.metric(ind["etiqueta"], valor_texto, f"{cambio_pct:+.2f}%")
                    st.caption(f"al {pd.Timestamp(fecha).strftime('%d-%m-%Y')}")
                else:
                    st.metric(ind["etiqueta"], "—")
                    st.caption("sin datos suficientes")

    except Exception as e:
        st.error(f"No se pudo cargar el resumen internacional: {e}")

    st.divider()
    st.subheader("Resumen del día (generado por IA)")

    try:
        df_brief = cargar_brief_diario()

        if df_brief.empty:
            st.info(
                "Todavía no se ha generado el resumen diario. Corre "
                "scripts/generar_brief.py (requiere GEMINI_API_KEY) — se genera "
                "una vez al día como parte del cron, no en cada visita."
            )
        else:
            fila_brief = df_brief.iloc[0]
            st.caption(
                f"Generado el {pd.Timestamp(fila_brief['generado_en']).strftime('%d-%m-%Y %H:%M')} "
                f"para el {pd.Timestamp(fila_brief['fecha']).strftime('%d-%m-%Y')}."
            )
            st.markdown(fila_brief["contenido"])
            st.warning(
                "⚠️ Resumen generado automáticamente por IA a partir de titulares "
                "públicos — puede contener errores o imprecisiones, no constituye "
                "asesoría de inversión."
            )

    except Exception as e:
        st.error(f"No se pudo cargar el resumen diario: {e}")

    st.divider()

    with st.expander("Titulares relevantes (detalle)"):
        try:
            df_noticias = cargar_noticias()

            if df_noticias.empty:
                st.info("Todavía no hay titulares descargados. Corre scripts/actualizar_noticias.py.")
            else:
                df_noticias = df_noticias.assign(fecha_publicacion=pd.to_datetime(df_noticias["fecha_publicacion"]))
                df_noticias["dia"] = df_noticias["fecha_publicacion"].dt.date

                # df_noticias ya viene ordenado desc por fecha_publicacion (ver cargar_noticias),
                # así que agrupar sin volver a ordenar deja primero el día más reciente.
                for dia, grupo in df_noticias.groupby("dia", sort=False):
                    st.markdown(f"**{dia.strftime('%d-%m-%Y')}**")
                    for _, fila in grupo.iterrows():
                        hora = fila["fecha_publicacion"].strftime("%H:%M")
                        st.markdown(f"- {hora} · *{fila['fuente']}* — [{fila['titulo']}]({fila['link']})")

        except Exception as e:
            st.error(f"No se pudieron cargar los titulares: {e}")

    st.divider()
    st.caption(
        "**Nota metodológica.** El resumen de arriba se genera automáticamente una "
        "vez al día a partir de los indicadores de \"Importante\" y los titulares "
        "de la sección de detalle — no afirma causalidad específica entre una "
        "noticia puntual y un movimiento de precio. \"La Tercera Pulso\" y \"Emol "
        "Economía\" no tienen un feed RSS propio funcionando hoy, así que sus "
        "titulares se obtienen vía una búsqueda de Google Noticias filtrada por "
        "sitio — no es el feed oficial del medio."
    )

# --- Tab 1: Series macro del BCCh ---
with tab_macro:
    try:
        df_macro = cargar_series_macro()

        series_disponibles = df_macro["nombre"].unique()
        serie_elegida = st.selectbox("Elige un indicador", series_disponibles)

        df_filtrado = df_macro[df_macro["nombre"] == serie_elegida]

        fig = px.line(df_filtrado, x="fecha", y="valor", title=serie_elegida)
        st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Último valor", f"{df_filtrado['valor'].iloc[-1]:,.2f}")
        with col2:
            st.metric("Fecha", str(df_filtrado["fecha"].iloc[-1]))

    except Exception as e:
        st.error(f"No se pudieron cargar los datos macro: {e}")

# --- Tab 2: Precios de acciones ---
with tab_acciones:
    try:
        df_acciones = cargar_precios_acciones()

        # Gráfico principal: solo las 5 acciones más importantes (igual que antes).
        df_principales = df_acciones[df_acciones["ticker"].isin(TICKERS_IPSA_PRINCIPALES)]
        tickers_disponibles = TICKERS_IPSA_PRINCIPALES
        tickers_elegidos = st.multiselect(
            "Elige acciones a comparar", tickers_disponibles, default=tickers_disponibles[:2]
        )

        df_filtrado = df_principales[df_principales["ticker"].isin(tickers_elegidos)]

        normalizar = st.checkbox("Normalizar a base 100", value=True)

        if normalizar:
            df_filtrado = df_filtrado.copy()
            df_filtrado["precio_normalizado"] = df_filtrado.groupby("ticker")["precio_cierre"].transform(
                lambda serie: serie / serie.iloc[0] * 100
            )
            columna_precio = "precio_normalizado"
            titulo_precio = "Desempeño relativo (base 100)"
        else:
            columna_precio = "precio_cierre"
            titulo_precio = "Precio de cierre histórico"

        fig = px.line(
            df_filtrado, x="fecha", y=columna_precio, color="ticker",
            title=titulo_precio
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Volumen transado")
        fig_vol = px.bar(df_filtrado, x="fecha", y="volumen", color="ticker")
        st.plotly_chart(fig_vol, use_container_width=True)

        # --- Heatmap de desempeño: todas las acciones del IPSA ---
        st.subheader("Resumen de desempeño — todas las acciones del IPSA")

        df_macro = cargar_series_macro()
        df_resumen = calcular_resumen_ipsa(df_acciones, df_macro)
        capm_insumos = calcular_crp_y_prima_mercado(df_macro, df_acciones)

        columnas_pct = ["1D %", "1W %", "1M %", "YTD %"]
        columnas_capm = ["CAPM local (%)", "CAPM + CRP (%)"]
        max_abs = df_resumen[columnas_pct].abs().max().max()
        max_abs = max_abs if pd.notna(max_abs) and max_abs > 0 else 1

        formato = {col: "{:+.2f}%" for col in columnas_pct}
        formato["Beta"] = "{:.2f}"
        formato["Volatilidad anualizada (%)"] = "{:.2f}%"
        formato["CAPM local (%)"] = "{:.2f}%"
        formato["CAPM + CRP (%)"] = "{:.2f}%"

        def marcar_datos_atrasados(fila):
            # Si el último dato "real" del ticker tiene más de 5 días hábiles de
            # atraso, se grisa toda la fila (y se anula el color del heatmap) para
            # no dar una falsa sensación de precisión en un % que no se actualizó.
            if fila["Atraso"]:
                return ["color: #898781; background-color: transparent"] * len(fila)
            return [""] * len(fila)

        estilo = (
            df_resumen.style
            .background_gradient(cmap=CMAP_DIVERGENTE, subset=columnas_pct, vmin=-max_abs, vmax=max_abs)
            .background_gradient(cmap=CMAP_SECUENCIAL, subset=["Volatilidad anualizada (%)"] + columnas_capm)
            .apply(marcar_datos_atrasados, axis=1)
            .format(formato, na_rep="—")
            .hide(["Atraso"], axis="columns")
        )
        st.dataframe(estilo, use_container_width=True)
        st.caption(
            "Volatilidad anualizada: rolling 21 días hábiles de retornos diarios × √252, "
            "excluyendo días de precio congelado (mismo criterio que \"Atraso\"). "
            "Beta calculado sobre retornos diarios del último año, respecto al ETF ECH "
            "(proxy del IPSA — el índice no tiene ticker propio en Yahoo Finance). "
            "⚠️ en \"Última actualización\" indica que Yahoo Finance no refrescó el precio "
            "de ese ticker hace más de 5 días hábiles — el % de cambio mostrado no es confiable."
        )

        if capm_insumos["rf_cl"] is not None:
            st.info(
                f"**Nota metodológica — CAPM y prima de riesgo país (CRP).** "
                f"Rf local (PDBC 14d) = {capm_insumos['rf_cl']:.2f}%, "
                f"Rf EEUU (UST10Y) = {capm_insumos['rf_ust']:.2f}%, "
                f"spread PDBC−UST10 = {capm_insumos['crp']:+.2f} pp (proxy de CRP), "
                f"prima de mercado local = {capm_insumos['prima_mercado_local']:.2f} pp "
                "(retorno histórico anualizado del proxy del IPSA menos Rf local). "
                "**CAPM local** = Rf local + Beta × prima de mercado local. "
                "**CAPM + CRP** = CAPM local + el spread de arriba. Se muestran ambas "
                "versiones a propósito: sumar el spread completo puede implicar un "
                "**doble conteo** del riesgo país, ya que el Beta y la Rf locales ya "
                "capturan parte de ese riesgo implícitamente (el mercado chileno se mueve "
                "distinto a EEUU en parte *por* el riesgo país). Este spread PDBC-UST10 es "
                "una **aproximación al estilo Damodaran**, no el EMBI+ oficial (que "
                "requiere una fuente de datos de pago que este dashboard no tiene). También "
                "hay un **descalce de plazos**: PDBC es a 14 días y UST10Y es a 10 años, así "
                "que el spread mezcla riesgo país con diferencias de duración/curva de "
                "tasas — por eso puede salir negativo (como ahora) sin que eso implique que "
                "el mercado percibe a Chile como \"menos riesgoso\" que EEUU."
            )

    except Exception as e:
        st.error(f"No se pudieron cargar los precios de acciones: {e}")

# --- Tab 2b: Riesgo ---
with tab_riesgo:
    try:
        df_acciones = cargar_precios_acciones()

        st.subheader("Value at Risk (VaR)")
        st.caption(
            "Acciones principales y un portafolio hipotético equiponderado (20% cada una), "
            "sobre los últimos ~2 años de retornos diarios, excluyendo días de precio "
            "congelado (mismo criterio que \"Atraso\" en el heatmap). El VaR de las acciones "
            "en el cuartil de liquidez más bajo (contra las 30 del IPSA, ver nota abajo) se "
            "multiplica por 1,3× como ajuste heurístico por liquidez."
        )

        df_var = calcular_var(df_acciones)
        columnas_var_pct = [c for c in df_var.columns if c not in ("n", "Cuartil liquidez")]
        st.dataframe(
            df_var.style.format({col: "{:.2f}%" for col in columnas_var_pct}),
            use_container_width=True,
        )

        st.divider()
        st.subheader("Matriz de correlación — retornos diarios, 30 acciones del IPSA")

        matriz_corr = calcular_matriz_correlacion_ipsa(df_acciones)
        fig_corr = px.imshow(
            matriz_corr,
            color_continuous_scale=COLORSCALE_CORRELACION,
            zmin=-1, zmax=1,
            aspect="auto",
        )
        fig_corr.update_layout(height=750)
        st.plotly_chart(fig_corr, use_container_width=True)

        st.divider()
        st.info(
            "**Nota metodológica.** El **VaR histórico** asume que la distribución de "
            "retornos pasados representa razonablemente el riesgo futuro — supuesto no "
            "garantizado, sobre todo en episodios de crisis o cambios estructurales del "
            "mercado. El **VaR paramétrico** asume que los retornos siguen una "
            "distribución normal, lo que en la práctica suele **subestimar la "
            "probabilidad de eventos extremos** (los retornos reales suelen tener colas "
            "más gordas que la normal). Se muestran ambos lado a lado justamente para "
            "que la diferencia entre ellos sea visible: cuando el histórico supera "
            "claramente al paramétrico, es señal de colas gordas en los datos reales."
        )
        st.caption(
            "**Ajuste de VaR por liquidez.** El cuartil de liquidez se calcula sobre el "
            "monto transado diario promedio (precio × volumen) de los últimos 3 meses, "
            "de las 30 acciones del IPSA. El multiplicador de 1,3× para el cuartil menos "
            "líquido es una **aproximación heurística simplificada** — no un modelo "
            "riguroso de impacto de mercado ni de profundidad del libro de órdenes (order "
            "book), que requeriría datos de microestructura que este dashboard no tiene. "
            "Solo se aplica a las acciones individuales, no al portafolio."
        )

    except Exception as e:
        st.error(f"No se pudieron calcular las métricas de riesgo: {e}")

# --- Tab 3: 7 Magníficas ---
with tab_magnificas:
    try:
        df_siete = cargar_precios_acciones()
        df_siete = df_siete[df_siete["ticker"].isin(TICKERS_MAGNIFICAS)].copy()

        df_siete["precio_normalizado"] = df_siete.groupby("ticker")["precio_cierre"].transform(
            lambda serie: serie / serie.iloc[0] * 100
        )

        fig = px.line(
            df_siete, x="fecha", y="precio_normalizado", color="ticker",
            title="7 Magníficas — desempeño normalizado (base 100)",
            color_discrete_sequence=PALETA_CATEGORICA,
            category_orders={"ticker": TICKERS_MAGNIFICAS},
        )
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"No se pudieron cargar los datos de las 7 Magníficas: {e}")

# --- Tab 4: Benchmark ---
with tab_benchmark:
    try:
        df_bench = cargar_precios_acciones()
        df_bench = df_bench[df_bench["ticker"].isin(TICKERS_BENCHMARK.keys())].copy()
        df_bench["nombre"] = df_bench["ticker"].map(TICKERS_BENCHMARK)

        df_bench["indice_normalizado"] = df_bench.groupby("ticker")["precio_cierre"].transform(
            lambda serie: serie / serie.iloc[0] * 100
        )

        fig = px.line(
            df_bench, x="fecha", y="indice_normalizado", color="nombre",
            title="IPSA vs benchmarks internacionales — base 100",
            color_discrete_sequence=PALETA_CATEGORICA,
            category_orders={"nombre": list(TICKERS_BENCHMARK.values())},
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "El IPSA se representa mediante el ETF ECH (iShares MSCI Chile), "
            "ya que el índice no tiene ticker propio en Yahoo Finance."
        )

    except Exception as e:
        st.error(f"No se pudieron cargar los datos de benchmark: {e}")

# --- Tab 5: Event Study TPM ---
with tab_event_study:
    try:
        df_macro = cargar_series_macro()
        df_eventos, df_agregado, n_eventos = calcular_event_study_tpm(df_macro)

        st.subheader("CAAR promedio del tipo de cambio USD/CLP ante cambios de la TPM")

        fig = px.line(
            df_agregado, x="Día relativo", y="CAAR (%)",
            title=f"CAAR promedio — {n_eventos} eventos de cambio de TPM",
            markers=True,
        )
        fig.add_hline(y=0, line_dash="dot", line_color="#898781")
        fig.update_xaxes(dtick=1)
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "AAR/CAAR por día relativo, con t-test simple contra cero "
            "(usando la desviación estándar de la ventana de estimación de cada evento)."
        )
        st.dataframe(
            df_agregado.style.format({
                "AAR (%)": "{:+.3f}%",
                "t-stat AAR": "{:.2f}",
                "p-valor AAR": "{:.3f}",
                "CAAR (%)": "{:+.3f}%",
                "t-stat CAAR": "{:.2f}",
            }, na_rep="—"),
            use_container_width=True,
        )

        st.subheader(f"Eventos individuales ({n_eventos})")
        st.dataframe(
            df_eventos.style.format({"CAR (%)": "{:+.3f}%"}),
            use_container_width=True,
        )

        # --- Tests por dirección: ¿el CAR es distinto de cero en alzas / bajas, y entre sí? ---
        st.subheader("¿Alzas y bajas de TPM mueven el dólar de forma distinta?")

        df_direccion, diferencia = calcular_tests_direccion(df_eventos)

        n_alza = int(df_direccion.loc[df_direccion["Grupo"].str.startswith("Alza"), "n"].iloc[0])
        n_baja = int(df_direccion.loc[df_direccion["Grupo"].str.startswith("Baja"), "n"].iloc[0])
        st.warning(
            f"⚠️ Muestra chica: n={n_alza} alzas y n={n_baja} bajas. Con tan pocos eventos "
            "por grupo, es esperable que ninguno de estos tests alcance significancia "
            "estadística aunque exista un efecto real — no interpretar un t-stat bajo "
            "como evidencia de que la TPM \"no importa\"."
        )

        st.dataframe(
            df_direccion.style.format({
                "CAR medio (%)": "{:+.3f}%",
                "t-stat (vs 0)": "{:.2f}",
                "p-valor (vs 0)": "{:.3f}",
            }, na_rep="—"),
            use_container_width=True,
        )

        if diferencia["t_stat"] is not None:
            sig_dif = "sí" if diferencia["p_valor"] < 0.05 else "no"
            st.markdown(
                f"**Diferencia de medias (Alza − Baja), test de Welch:** "
                f"{diferencia['diferencia_medias']:+.3f} puntos porcentuales de CAR "
                f"(t = {diferencia['t_stat']:.2f}, p = {diferencia['p_valor']:.3f}) "
                f"— {'**significativa**' if sig_dif == 'sí' else 'no significativa'} al 5%."
            )
        else:
            st.markdown("No hay suficientes eventos en algún grupo para el test de diferencia de medias.")

        st.caption(
            "El CAR promedio es negativo tras alzas de TPM (el dólar tiende a bajar, el "
            "peso se aprecia) y positivo tras bajas (el dólar tiende a subir, el peso se "
            "deprecia) — dirección consistente con la teoría de paridad de tasas de "
            "interés. Pero ninguno de los dos t-test contra cero, ni la diferencia entre "
            "grupos, es significativo al 5%: no se puede descartar que el efecto "
            "observado sea puro ruido con esta muestra."
        )

        st.info(
            "**Nota metodológica.**\n\n"
            "**Detección de eventos.** Los eventos se detectan automáticamente como "
            "cambios en la serie diaria de la TPM respecto al día hábil anterior — "
            "esto captura únicamente las reuniones de política monetaria (RPM) en "
            "las que la tasa efectivamente cambió. No tenemos el calendario de "
            "reuniones RPM, así que las decisiones de \"mantener\" la tasa no "
            "quedan registradas como eventos y no forman parte de este análisis. "
            "El retorno normal esperado se estima como el retorno diario promedio "
            "del tipo de cambio en los 30 días hábiles previos a cada evento; el "
            "retorno anormal (AR) es la diferencia entre el retorno real y ese "
            "retorno normal, en la ventana de evento (-2 a +2 días hábiles). El "
            "t-test agregado (AAR/CAAR) es una aproximación simple (normal estándar) "
            "que no corrige por autocorrelación ni por eventos superpuestos.\n\n"
            "**Limitación 1 — poca potencia estadística.** Solo 37 eventos en total "
            "(15 alzas, 22 bajas) desde 2015. Con muestras tan chicas, un test "
            "estadístico tiene poca capacidad de detectar un efecto real aunque "
            "exista (poca \"potencia\"): se necesitaría un efecto muy grande para "
            "que sea detectable con este N.\n\n"
            "**Limitación 2 — confusión con ciclos monetarios globales.** Las "
            "decisiones de TPM del BCCh no ocurren de forma aislada: suelen coincidir "
            "con ciclos monetarios simultáneos en otros bancos centrales (ej. el BCCh "
            "subió tasas en 2021-2022 al mismo tiempo que la Fed subía las suyas). "
            "Este diseño no puede aislar limpiamente el efecto de la decisión local "
            "sobre el tipo de cambio del efecto de esos movimientos globales "
            "simultáneos — parte del AR medido en cada evento podría deberse al "
            "ciclo global, no a la decisión del BCCh en sí.\n\n"
            "**\"No significativo\" no es \"no hay efecto\".** La falta de "
            "significancia estadística (acá y en la sección de arriba) solo dice que "
            "esta muestra no permite afirmar que el efecto es distinto de cero — no "
            "dice que el efecto no exista. Con las dos limitaciones anteriores, es "
            "exactamente el resultado esperable aunque la TPM sí tenga un impacto "
            "real sobre el tipo de cambio.\n\n"
            "**Mejora futura.** Controlar por el movimiento simultáneo del dólar a "
            "nivel global (ej. el índice DXY) en la ventana de evento permitiría "
            "aislar mejor el componente local del CAR, restando el efecto que ya "
            "viene dado por el ciclo monetario global."
        )

    except Exception as e:
        st.error(f"No se pudo calcular el event study: {e}")

# --- Tab 7: Backtester Estrategia TPM ---
with tab_backtester:
    try:
        st.subheader("Backtest: dirección de la TPM → USD/CLP")
        st.caption(
            "Estrategia hipotética sobre los mismos 37 eventos del Event Study: "
            "TPM sube → posición corta en USD/CLP; TPM baja → posición larga. "
            "Entrada al cierre del día del evento, salida al cierre 2 días hábiles "
            "después, con un costo de transacción de 8 puntos base por operación "
            "(entrada + salida)."
        )

        df_macro = cargar_series_macro()
        resultado = calcular_backtest_tpm(df_macro)

        if resultado["n_eventos"] < 2:
            st.warning("No hay suficientes eventos de TPM con datos completos para backtestear.")
        else:
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Retorno total acumulado", f"{resultado['retorno_total']:+.2f}%")
            col2.metric("Retorno promedio / trade", f"{resultado['retorno_promedio']:+.3f}%")
            col3.metric("% operaciones ganadoras", f"{resultado['pct_ganadoras']:.1f}%")
            col4.metric("Sharpe (anualizado)", f"{resultado['sharpe']:.2f}" if resultado["sharpe"] is not None else "—")
            col5.metric("Máximo drawdown", f"{resultado['max_drawdown']:.2f}%")

            df_trades = resultado["df_trades"].copy()
            df_trades["Retorno acumulado (%)"] = (df_trades["Equity"] - 1) * 100
            fig_equity = px.line(
                df_trades, x="Fecha", y="Retorno acumulado (%)",
                title="Curva de equity (retorno acumulado de la estrategia)",
                markers=True,
            )
            fig_equity.add_hline(y=0, line_dash="dot", line_color="#898781")
            st.plotly_chart(fig_equity, use_container_width=True)

            st.divider()
            st.subheader("Test de permutación: ¿le gana la dirección elegida al azar?")
            st.caption(
                f"Se mezcló aleatoriamente la dirección (alza/baja) de los "
                f"{resultado['n_eventos']} eventos {N_PERMUTACIONES_BACKTEST:,} veces, "
                "corriendo el mismo backtest (mismas fechas de entrada/salida y mismo "
                "costo de transacción) con cada mezcla. Esto aísla si el criterio "
                "direccional (y no solo el momento de entrada/salida) aporta algo por "
                "sobre el azar."
            )

            fig_hist = px.histogram(
                x=resultado["retornos_totales_perm"],
                nbins=50,
                title="Distribución de retornos totales bajo 1.000 mezclas aleatorias de dirección",
                labels={"x": "Retorno total acumulado (%)"},
            )
            fig_hist.add_vline(
                x=resultado["retorno_total"], line_color="#e34948", line_width=2,
                annotation_text="Resultado real", annotation_position="top",
            )
            st.plotly_chart(fig_hist, use_container_width=True)

            percentil = resultado["percentil_real"]
            if percentil >= 95 or percentil <= 5:
                interpretacion = (
                    "un resultado así de extremo es poco común bajo mezclas al azar — "
                    "compatible con que el criterio direccional (y no solo el momento "
                    "de entrada/salida) esté aportando algo, aunque con solo 37 eventos "
                    "esto debe leerse con cautela."
                )
            else:
                interpretacion = (
                    "el resultado real es indistinguible de simplemente elegir una "
                    "dirección al azar en esas mismas 37 fechas — no hay evidencia de "
                    "que el criterio direccional (TPM sube → corto, TPM baja → largo) "
                    "aporte valor por sobre el azar, más allá de si el retorno total "
                    "fue positivo o negativo."
                )
            st.markdown(
                f"**El resultado real ({resultado['retorno_total']:+.2f}%) cae en el "
                f"percentil {percentil:.0f} de la distribución de mezclas al azar** "
                f"— {interpretacion}"
            )

            st.divider()
            st.subheader(f"Trades individuales ({resultado['n_eventos']})")
            st.dataframe(
                df_trades.drop(columns=["Retorno acumulado (%)"]).style.format({
                    "Retorno crudo USD/CLP": "{:+.3%}",
                    "Retorno neto": "{:+.3%}",
                    "Equity": "{:.4f}",
                }),
                use_container_width=True,
            )

            st.info(
                "**Nota metodológica.** Este es un backtest hipotético e ilustrativo, "
                "no una recomendación de inversión. Comparte todas las limitaciones del "
                "Event Study TPM (muestra chica de 37 eventos, posible confusión con "
                "ciclos monetarios globales simultáneos, calendario de RPM no "
                "disponible). Además asume que se puede entrar exactamente al cierre "
                "del día del anuncio de TPM — en la práctica el anuncio puede ocurrir "
                "durante o después de la sesión, lo que podría hacer inalcanzable ese "
                "precio de entrada. El costo de transacción (8 puntos base) es una "
                "aproximación fija; costos reales de financiamiento, spread y slippage "
                "podrían ser mayores, especialmente en episodios de alta volatilidad."
            )

    except Exception as e:
        st.error(f"No se pudo calcular el backtest: {e}")
