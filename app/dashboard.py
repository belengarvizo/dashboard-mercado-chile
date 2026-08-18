"""
Dashboard principal. Lee todo desde PostgreSQL (nunca llama a las
APIs directamente) para que cargue rápido sin importar quién lo abra.

Correr localmente con: streamlit run app/dashboard.py
"""

import math
import os
import sys
from datetime import date

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
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
from calendario_economico import proximos_eventos, NOTA_VIGENCIA, INDICADOR_POR_TIPO

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

# Momentum IPSA (Jegadeesh & Titman 12-1): señal = retorno compuesto de los
# meses [t-12, t-2] (11 meses), saltando el mes t-1 más reciente; se
# mantiene la cartera durante el mes t, rebalanceo mensual.
MESES_FORMACION_MOMENTUM = 12
MESES_SKIP_MOMENTUM = 1
N_GANADORAS_PERDEDORAS_MOMENTUM = 10
COSTO_TRANSACCION_MOMENTUM = 0.0015  # 15 puntos base por posición por rebalanceo
N_PERMUTACIONES_MOMENTUM = 1000

# Optimización de portafolios (Markowitz vía Monte Carlo, long-only).
N_PORTAFOLIOS_MC = 5000

st.title("Dashboard de mercado chileno")
st.caption("Datos del Banco Central de Chile y Yahoo Finance, actualizados diariamente")

engine = get_engine()


@st.cache_data(ttl=3600)  # cachea 1 hora, para no golpear la BD en cada click
def cargar_series_macro():
    query = "SELECT nombre, fecha, valor FROM series_macro ORDER BY fecha"
    df = pd.read_sql(query, engine)
    # Descarta filas con valor NaN (dato no disponible, ej. una sesión de
    # Yahoo Finance incompleta al momento de descargar) para que ningún
    # cálculo aguas abajo tome silenciosamente NaN como "el último valor" —
    # así, el último valor real que queda es siempre uno válido, con su
    # fecha real (nunca la fecha de hoy con un dato viejo disfrazado).
    return df.dropna(subset=["valor"])


@st.cache_data(ttl=3600)
def cargar_precios_acciones():
    query = "SELECT ticker, fecha, precio_cierre, volumen FROM precios_acciones ORDER BY fecha"
    df = pd.read_sql(query, engine)
    # Solo se descarta por precio_cierre NaN, no por volumen: varios
    # benchmarks/ETFs internacionales legítimamente no traen volumen.
    return df.dropna(subset=["precio_cierre"])


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


def calcular_cambios_periodo(serie: pd.Series) -> dict:
    """% de cambio 1D/1W/1M/YTD de una serie de precios ordenada por fecha,
    respecto al último valor disponible. Compartido entre el heatmap de
    "Acciones IPSA" y la tabla resumen de las 7 Magníficas en "Benchmark"."""
    if len(serie) < 2:
        return {"1D %": None, "1W %": None, "1M %": None, "YTD %": None}

    ultimo = serie.iloc[-1]
    fecha_ultima = serie.index[-1]

    def cambio_desde(dias_atras):
        objetivo = fecha_ultima - pd.Timedelta(days=dias_atras)
        previos = serie[serie.index <= objetivo]
        return (ultimo / previos.iloc[-1] - 1) * 100 if not previos.empty else None

    inicio_anio = serie[serie.index >= pd.Timestamp(fecha_ultima.year, 1, 1)]
    cambio_ytd = (ultimo / inicio_anio.iloc[0] - 1) * 100 if not inicio_anio.empty else None

    return {
        "1D %": cambio_desde(1),
        "1W %": cambio_desde(7),
        "1M %": cambio_desde(30),
        "YTD %": cambio_ytd,
    }


def calcular_spread_2s10s(df_macro: pd.DataFrame) -> dict | None:
    """Spread 2s10s (UST10Y - UST2Y) con marca de curva invertida si es negativo."""
    # Mismos strings "nombre" que scripts/actualizar_bcch.py usa al guardar la serie.
    ust10 = df_macro[df_macro["nombre"] == "Bono del Tesoro de EEUU a 10 años (UST10Y)"].sort_values("fecha")
    ust2 = df_macro[df_macro["nombre"] == "Bono del Tesoro de EEUU a 2 años (UST2Y, proxy 2YY=F)"].sort_values("fecha")
    if ust10.empty or ust2.empty:
        return None
    ust10_valor = float(ust10["valor"].iloc[-1])
    ust2_valor = float(ust2["valor"].iloc[-1])
    spread = ust10_valor - ust2_valor
    return {
        "ust10": ust10_valor,
        "ust2": ust2_valor,
        "spread": spread,
        "invertida": spread < 0,
        "fecha": ust10["fecha"].iloc[-1],
    }


NOMBRE_BCP_10Y = "Bono BCCh en pesos (BCP) a 10 años - tasa mercado secundario"
NOMBRE_BCU_10Y = "Bono BCCh en UF (BCU) a 10 años - tasa mercado secundario"
NOMBRE_BREAKEVEN = "Inflación breakeven (BCP 10Y − BCU 10Y, implícita)"


def calcular_serie_inflacion_breakeven(df_macro: pd.DataFrame) -> pd.Series:
    """Inflación breakeven = tasa BCP nominal a 10 años − tasa BCU real a 10
    años (mismo emisor y plazo, distinta indexación). Es la inflación que el
    mercado tiene implícita en los precios de ambos bonos — no un pronóstico
    oficial de nadie. Serie indexada por fecha, alineada automáticamente
    (pandas) entre ambas series de origen; se descartan fechas donde falta
    una de las dos."""
    bcp = df_macro[df_macro["nombre"] == NOMBRE_BCP_10Y].sort_values("fecha").set_index("fecha")["valor"]
    bcu = df_macro[df_macro["nombre"] == NOMBRE_BCU_10Y].sort_values("fecha").set_index("fecha")["valor"]
    if bcp.empty or bcu.empty:
        return pd.Series(dtype=float)
    return (bcp - bcu).dropna()


def evaluar_graham(
    precio, eps, pe_5y, dividendo, valor_libro, deuda_total,
    activos_corrientes, pasivos_corrientes, yield_aaa, eps_historico,
) -> list[dict]:
    """Evalúa los 10 criterios clásicos de Graham (adaptación al estilo del
    Screener de "The Intelligent Investor", cap. 14) sobre los inputs
    ingresados por el usuario. Función pura, sin dependencias de Streamlit."""
    criterios = []

    liquidez = activos_corrientes / pasivos_corrientes if pasivos_corrientes else None
    criterios.append({
        "criterio": "1. Liquidez corriente ≥ 2",
        "explicacion": "Los activos corrientes deben ser al menos el doble de los "
                       "pasivos corrientes — mide la solidez financiera de corto plazo.",
        "valor": f"Activos/Pasivos corrientes = {liquidez:.2f}" if liquidez is not None else "—",
        "cumple": liquidez is not None and liquidez >= 2,
    })

    capital_trabajo = activos_corrientes - pasivos_corrientes
    criterios.append({
        "criterio": "2. Deuda de largo plazo ≤ capital de trabajo neto",
        "explicacion": "La deuda total no debería superar el capital de trabajo neto "
                       "(activos corrientes menos pasivos corrientes).",
        "valor": f"Deuda {deuda_total:,.0f} vs. capital de trabajo {capital_trabajo:,.0f}",
        "cumple": deuda_total <= capital_trabajo,
    })

    criterios.append({
        "criterio": "3. Estabilidad de utilidades",
        "explicacion": "Utilidades positivas tanto hoy como hace 10 años. Simplificación: "
                       "Graham exige ganancias positivas en cada uno de los últimos 10 años, "
                       "acá solo se verifican los dos extremos del período.",
        "valor": f"EPS actual {eps:.2f}, EPS hace 10 años {eps_historico:.2f}",
        "cumple": eps > 0 and eps_historico > 0,
    })

    criterios.append({
        "criterio": "4. Historial de dividendos",
        "explicacion": "La empresa paga dividendos actualmente. Simplificación: Graham "
                       "exige un historial ininterrumpido de al menos 20 años; acá solo "
                       "se verifica el dividendo del último período.",
        "valor": f"Dividendo por acción = {dividendo:.2f}",
        "cumple": dividendo > 0,
    })

    crecimiento = (eps - eps_historico) / eps_historico if eps_historico else None
    criterios.append({
        "criterio": "5. Crecimiento de utilidades ≥ 33% en 10 años",
        "explicacion": "El EPS actual debe ser al menos un tercio mayor que el EPS de "
                       "hace 10 años (Graham compara promedios de 3 años en cada punta; "
                       "acá se usan los valores puntuales ingresados).",
        "valor": f"{crecimiento:+.1%}" if crecimiento is not None else "—",
        "cumple": crecimiento is not None and crecimiento >= 0.33,
    })

    criterios.append({
        "criterio": "6. P/E moderado (≤ 15)",
        "explicacion": "El precio no debería superar 15 veces las utilidades promedio "
                       "de los últimos años.",
        "valor": f"P/E promedio 5 años = {pe_5y:.2f}",
        "cumple": pe_5y is not None and pe_5y > 0 and pe_5y <= 15,
    })

    pb = precio / valor_libro if valor_libro else None
    criterios.append({
        "criterio": "7. P/B moderado (≤ 1,5)",
        "explicacion": "El precio no debería superar 1,5 veces el valor libro por acción.",
        "valor": f"P/B = {pb:.2f}" if pb is not None else "—",
        "cumple": pb is not None and pb <= 1.5,
    })

    pe_pb = pe_5y * pb if (pe_5y is not None and pb is not None) else None
    criterios.append({
        "criterio": "8. P/E × P/B ≤ 22,5",
        "explicacion": "El atajo combinado de Graham: si el P/E es bajo se tolera un P/B "
                       "más alto (y viceversa), mientras el producto no supere 22,5 "
                       "(≈ 15 × 1,5).",
        "valor": f"{pe_pb:.2f}" if pe_pb is not None else "—",
        "cumple": pe_pb is not None and pe_pb <= 22.5,
    })

    rendimiento_utilidades = 100 / pe_5y if pe_5y else None
    umbral_aaa = (2 / 3) * yield_aaa
    criterios.append({
        "criterio": "9. Rendimiento de utilidades ≥ 2/3 del yield de bonos AAA",
        "explicacion": "El rendimiento de utilidades (inverso del P/E, en %) debe ser al "
                       "menos dos tercios del rendimiento de un bono corporativo AAA — "
                       "compensación mínima exigible por el riesgo accionario.",
        "valor": (
            f"{rendimiento_utilidades:.2f}% vs. umbral {umbral_aaa:.2f}%"
            if rendimiento_utilidades is not None else "—"
        ),
        "cumple": rendimiento_utilidades is not None and rendimiento_utilidades >= umbral_aaa,
    })

    criterios.append({
        "criterio": "10. Dividendo sostenible (payout ≤ 100%)",
        "explicacion": "El dividendo por acción no debería superar las utilidades por "
                       "acción del mismo período.",
        "valor": f"Dividendo {dividendo:.2f} vs. EPS {eps:.2f}",
        "cumple": eps > 0 and dividendo <= eps,
    })

    return criterios


@st.cache_data(ttl=3600)
def calcular_crp_y_prima_mercado(df_macro: pd.DataFrame, df_acciones: pd.DataFrame) -> dict:
    """Tasa libre de riesgo local de corto plazo (PDBC, la base del CAPM),
    tasa libre de riesgo EEUU a 10 años (UST10), tasa del bono BCCh en pesos
    (BCP) a 10 años (mismo plazo que UST10, usada solo para el CRP — no
    reemplaza a PDBC como Rf del CAPM), spread BCP10-UST10 como proxy de
    prima de riesgo país (CRP, enfoque Damodaran, no EMBI+, ahora plazo
    contra plazo), y prima de mercado local (retorno histórico anualizado
    del proxy del IPSA menos PDBC). Todo en puntos porcentuales, reutilizando
    series que ya están en la BD."""
    df_macro = df_macro.assign(fecha=pd.to_datetime(df_macro["fecha"]))

    pdbc = (
        df_macro[df_macro["nombre"] == "Tasa libre de riesgo CLP (PDBC 14 días)"]
        .sort_values("fecha")["valor"]
    )
    ust10 = (
        df_macro[df_macro["nombre"] == "Bono del Tesoro de EEUU a 10 años (UST10Y)"]
        .sort_values("fecha")["valor"]
    )
    bcp10 = (
        df_macro[df_macro["nombre"] == "Bono BCCh en pesos (BCP) a 10 años - tasa mercado secundario"]
        .sort_values("fecha")["valor"]
    )
    rf_cl = float(pdbc.iloc[-1]) if len(pdbc) else None
    rf_ust = float(ust10.iloc[-1]) if len(ust10) else None
    rf_cl_10y = float(bcp10.iloc[-1]) if len(bcp10) else None
    crp = (rf_cl_10y - rf_ust) if rf_cl_10y is not None and rf_ust is not None else None

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

    return {
        "rf_cl": rf_cl,
        "rf_ust": rf_ust,
        "rf_cl_10y": rf_cl_10y,
        "crp": crp,
        "prima_mercado_local": prima_mercado_local,
    }


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

        fecha_ultima = serie.index[-1]
        cambios = calcular_cambios_periodo(serie)

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

        # Beta ajustada (Blume): tira la beta cruda hacia 1 (el beta "promedio
        # de mercado" de largo plazo), un ajuste estándar y simple.
        beta_ajustada = (2 / 3) * beta + (1 / 3) * 1 if beta is not None else None

        filas.append({
            "Ticker": ticker.replace(".SN", ""),
            "1D %": cambios["1D %"],
            "1W %": cambios["1W %"],
            "1M %": cambios["1M %"],
            "YTD %": cambios["YTD %"],
            "Beta": beta,
            "Beta ajustada": beta_ajustada,
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


def _escapar_markdown_matematico(texto: str) -> str:
    """Escapa "$" antes de mostrar texto externo/dinámico (titulares de
    noticias, resumen generado por IA) con st.markdown(). Streamlit
    interpreta cualquier par de "$" como delimitadores de fórmula LaTeX, así
    que un texto con dos signos de peso/dólar (ej. "US$/oz troy ... US$/barril")
    se renderiza como una fórmula ilegible en vez de texto normal."""
    return texto.replace("$", r"\$")


UMBRAL_SIGNIFICANCIA = 0.05
LEYENDA_SIGNIFICANCIA = (
    "🟢 Verde = estadísticamente significativo (p < 0.05) — "
    "🔴 Rojo = no significativo, no se puede afirmar con esta muestra."
)


def _color_significancia(p_valor) -> str:
    """Color de TEXTO (negrita), no de fondo, para no confundirse con el
    verde/rojo de fondo que usa el heatmap de ganancia/pérdida de precios en
    la pestaña "Acciones IPSA" — mismo par de colores, rol visual distinto."""
    if p_valor is None or pd.isna(p_valor):
        return ""
    color = "#0ca30c" if p_valor < UMBRAL_SIGNIFICANCIA else "#d03b3b"
    return f"color: {color}; font-weight: 700"


def _etiqueta_timba(distinguible_del_azar: bool) -> str:
    """"Timba" (jerga de mesa de dinero): especular sin ventaja estadística
    real, solo apostar. Traduce el resultado del test de permutación a ese
    concepto — mismo código de color verde/rojo que el resto de las señales
    de significancia del dashboard."""
    if distinguible_del_azar:
        texto = "Esto sí muestra evidencia de una ventaja real, no timba."
        color = "#0ca30c"
    else:
        texto = (
            "Esto sería timba, no una estrategia con ventaja real — el resultado "
            "no se distingue de apostar al azar en las mismas fechas."
        )
        color = "#d03b3b"
    return f"<span style='color:{color}; font-weight:700'>{texto}</span>"


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
            "p-valor CAAR": _p_valor_normal(t_caar) if t_caar is not None else None,
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
def calcular_distribucion_retornos(df_todas: pd.DataFrame) -> dict:
    """Retornos diarios "reales" (excluyendo días de precio congelado) de los
    últimos ~2 años para las 5 acciones principales, con skewness y kurtosis
    (exceso de Fisher, 0 = normal) — para contrastar visualmente con el
    supuesto de normalidad del VaR paramétrico."""
    df_todas = df_todas.assign(fecha=pd.to_datetime(df_todas["fecha"]))
    fecha_corte = pd.Timestamp.now().normalize() - VENTANA_VAR

    resultado = {}
    for ticker in TICKERS_IPSA_PRINCIPALES:
        serie = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")["precio_cierre"]
        )
        serie = serie[serie.index >= fecha_corte]
        r = calcular_retornos_reales(serie).dropna()
        if len(r) < 30:
            continue
        resultado[ticker.replace(".SN", "")] = {
            "retornos": r,
            "skewness": float(stats.skew(r)),
            "kurtosis": float(stats.kurtosis(r)),
        }
    return resultado


@st.cache_data(ttl=3600)
def calcular_peor_escenario_historico(df_todas: pd.DataFrame) -> dict:
    """Peor retorno acumulado de 5 y 10 días hábiles del proxy del IPSA (ECH)
    DENTRO de los datos disponibles — no es el peor caso históricamente
    posible, solo el peor observado en esta muestra."""
    df_todas = df_todas.assign(fecha=pd.to_datetime(df_todas["fecha"]))
    serie_ech = (
        df_todas[df_todas["ticker"] == TICKER_PROXY_IPSA]
        .sort_values("fecha")
        .set_index("fecha")["precio_cierre"]
    )
    retornos_reales = calcular_retornos_reales(serie_ech).dropna()

    peor_5d = None
    peor_10d = None
    if len(retornos_reales) >= 5:
        acumulado_5d = retornos_reales.rolling(5).apply(lambda x: (1 + x).prod() - 1, raw=True)
        peor_5d = float(acumulado_5d.min())
    if len(retornos_reales) >= 10:
        acumulado_10d = retornos_reales.rolling(10).apply(lambda x: (1 + x).prod() - 1, raw=True)
        peor_10d = float(acumulado_10d.min())

    return {"peor_5d": peor_5d, "peor_10d": peor_10d, "n_obs": len(retornos_reales)}


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
def calcular_resumen_magnificas(df_todas: pd.DataFrame) -> pd.DataFrame:
    """% de cambio 1D/1W/1M/YTD de las 7 Magníficas — versión simple del
    heatmap de "Acciones IPSA", sin Beta/VaR/CAPM."""
    df_todas = df_todas.assign(fecha=pd.to_datetime(df_todas["fecha"]))

    filas = []
    for ticker in TICKERS_MAGNIFICAS:
        serie = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")["precio_cierre"]
        )
        if len(serie) < 2:
            continue
        cambios = calcular_cambios_periodo(serie)
        filas.append({"Ticker": ticker, **cambios})

    return pd.DataFrame(filas).set_index("Ticker")


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


@st.cache_data(ttl=3600)
def calcular_retornos_mensuales_ipsa(df_todas: pd.DataFrame) -> pd.DataFrame:
    """Retornos mensuales "reales" para las 30 acciones del IPSA: se componen
    los retornos diarios reales (excluyendo días de precio congelado) dentro
    de cada mes calendario, así que un día congelado no aporta un 0% falso a
    ningún mes."""
    df_todas = df_todas.assign(fecha=pd.to_datetime(df_todas["fecha"]))

    retornos_por_ticker = {}
    for ticker in TICKERS_IPSA:
        serie = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")["precio_cierre"]
        )
        retornos_reales = calcular_retornos_reales(serie).dropna()
        if retornos_reales.empty:
            continue
        mensual = retornos_reales.groupby(retornos_reales.index.to_period("M")).apply(
            lambda x: (1 + x).prod() - 1
        )
        retornos_por_ticker[ticker.replace(".SN", "")] = mensual

    return pd.DataFrame(retornos_por_ticker)


def _wml_de_un_mes(retornos_hold: pd.Series, ganadoras, perdedoras) -> tuple[float, float, float]:
    """Retorno neto (con costo de transacción) de las patas Ganadoras y
    Perdedoras para un mes de holding, y su spread (WML)."""
    ret_g = retornos_hold[list(ganadoras)].mean() - COSTO_TRANSACCION_MOMENTUM
    ret_p = retornos_hold[list(perdedoras)].mean() - COSTO_TRANSACCION_MOMENTUM
    return ret_g, ret_p, ret_g - ret_p


@st.cache_data(ttl=3600)
def calcular_momentum_ipsa(df_todas: pd.DataFrame) -> dict:
    """Estrategia momentum 12-1 (Jegadeesh & Titman) sobre las 30 acciones del
    IPSA. Cada mes: rankea por retorno compuesto de los meses [t-12, t-2]
    (salta t-1), forma Ganadoras/Perdedoras (10 cada una, equiponderadas),
    mantiene 1 mes, rebalanceo mensual con costo de 15pb por posición. Incluye
    un test de permutación: en cada mes se sortean al azar 10+10 tickers
    entre los disponibles ese mes (en vez de usar el ranking real), 1000
    veces, preservando la estructura temporal (mismas fechas, mismos
    retornos, mismo costo — solo cambia qué tickers se etiquetan
    ganadoras/perdedoras)."""
    df_mensual = calcular_retornos_mensuales_ipsa(df_todas)
    meses = sorted(df_mensual.index)

    eventos = []
    for i in range(MESES_FORMACION_MOMENTUM, len(meses)):
        mes_hold = meses[i]
        ventana_señal = meses[i - MESES_FORMACION_MOMENTUM: i - MESES_SKIP_MOMENTUM]
        if len(ventana_señal) < MESES_FORMACION_MOMENTUM - MESES_SKIP_MOMENTUM:
            continue

        señal = (1 + df_mensual.loc[ventana_señal]).prod(min_count=len(ventana_señal)) - 1
        señal = señal.dropna()
        retornos_hold = df_mensual.loc[mes_hold].dropna()

        tickers_validos = señal.index.intersection(retornos_hold.index)
        if len(tickers_validos) < 2 * N_GANADORAS_PERDEDORAS_MOMENTUM:
            continue

        eventos.append({
            "mes": mes_hold,
            "señal": señal.loc[tickers_validos],
            "retornos_hold": retornos_hold.loc[tickers_validos],
        })

    if not eventos:
        return {"df_wml": pd.DataFrame(), "n_meses": 0}

    filas_wml = []
    for evento in eventos:
        ranking = evento["señal"].sort_values(ascending=False)
        ganadoras = ranking.index[:N_GANADORAS_PERDEDORAS_MOMENTUM]
        perdedoras = ranking.index[-N_GANADORAS_PERDEDORAS_MOMENTUM:]
        ret_g, ret_p, wml = _wml_de_un_mes(evento["retornos_hold"], ganadoras, perdedoras)
        filas_wml.append({
            "Mes": evento["mes"].to_timestamp(),
            "Ganadoras (%)": ret_g * 100,
            "Perdedoras (%)": ret_p * 100,
            "WML (%)": wml * 100,
        })

    df_wml = pd.DataFrame(filas_wml)
    df_wml["Equity WML"] = (1 + df_wml["WML (%)"] / 100).cumprod()

    wml_decimal = df_wml["WML (%)"] / 100
    t_stat, p_valor = stats.ttest_1samp(wml_decimal, popmean=0)
    retorno_total = (df_wml["Equity WML"].iloc[-1] - 1) * 100

    # --- Test de permutación ---
    # Se precomputan arrays de numpy puros (retornos alineados por posición, no
    # por nombre) para que el loop de 1000 permutaciones no pague el costo de
    # indexar un pandas Series por etiqueta ~50.000 veces (eso tardaba >3 min;
    # con arrays de numpy e índices enteros baja a unos pocos segundos).
    retornos_arrays = [evento["retornos_hold"].reindex(evento["señal"].index).to_numpy() for evento in eventos]
    n_disponibles_por_mes = [len(arr) for arr in retornos_arrays]

    rng = np.random.default_rng(42)  # semilla fija para reproducibilidad
    retornos_totales_perm = np.empty(N_PERMUTACIONES_MOMENTUM)
    for p in range(N_PERMUTACIONES_MOMENTUM):
        equity_perm = 1.0
        for retornos_array, n_disponibles in zip(retornos_arrays, n_disponibles_por_mes):
            elegidos = rng.choice(n_disponibles, size=2 * N_GANADORAS_PERDEDORAS_MOMENTUM, replace=False)
            ret_g_perm = retornos_array[elegidos[:N_GANADORAS_PERDEDORAS_MOMENTUM]].mean() - COSTO_TRANSACCION_MOMENTUM
            ret_p_perm = retornos_array[elegidos[N_GANADORAS_PERDEDORAS_MOMENTUM:]].mean() - COSTO_TRANSACCION_MOMENTUM
            equity_perm *= (1 + (ret_g_perm - ret_p_perm))
        retornos_totales_perm[p] = (equity_perm - 1) * 100

    percentil_real = float((retornos_totales_perm < retorno_total).mean() * 100)

    return {
        "df_wml": df_wml,
        "n_meses": len(df_wml),
        "t_stat": t_stat,
        "p_valor": p_valor,
        "retorno_total": retorno_total,
        "retornos_totales_perm": retornos_totales_perm,
        "percentil_real": percentil_real,
    }


def _matriz_retornos_alineados(df_todas: pd.DataFrame, tickers: list) -> pd.DataFrame:
    """DataFrame de retornos diarios "reales" (excluyendo días de precio
    congelado) para los tickers dados, alineados por fecha: solo se
    conservan los días donde TODOS tienen un retorno real ese día
    (complete-case), para garantizar una matriz de covarianza válida."""
    df_todas = df_todas.assign(fecha=pd.to_datetime(df_todas["fecha"]))
    retornos = {}
    for ticker in tickers:
        serie = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")["precio_cierre"]
        )
        retornos[ticker.replace(".SN", "")] = calcular_retornos_reales(serie)
    return pd.DataFrame(retornos).dropna()


def _simular_portafolios_mc(mu_anual: pd.Series, cov_anual: pd.DataFrame, rf: float, rng: np.random.Generator) -> dict:
    """N_PORTAFOLIOS_MC portafolios long-only (pesos vía Dirichlet, suman 1)
    sobre los activos de mu_anual/cov_anual. Devuelve arrays de pesos,
    retorno, volatilidad y Sharpe, más los índices del portafolio de mínima
    varianza y de máximo Sharpe DENTRO de la nube simulada."""
    n_activos = len(mu_anual)
    pesos = rng.dirichlet(np.ones(n_activos), size=N_PORTAFOLIOS_MC)

    retorno = pesos @ mu_anual.values
    varianza = np.einsum("ij,jk,ik->i", pesos, cov_anual.values, pesos)
    volatilidad = np.sqrt(np.maximum(varianza, 0))
    with np.errstate(divide="ignore", invalid="ignore"):
        sharpe = np.where(volatilidad > 0, (retorno - rf) / volatilidad, -np.inf)

    idx_min_var = int(np.argmin(volatilidad))
    idx_max_sharpe = int(np.argmax(sharpe))

    return {
        "pesos": pesos,
        "retorno": retorno,
        "volatilidad": volatilidad,
        "sharpe": sharpe,
        "idx_min_var": idx_min_var,
        "idx_max_sharpe": idx_max_sharpe,
    }


@st.cache_data(ttl=3600)
def calcular_optimizacion_portafolios(df_todas: pd.DataFrame, df_macro: pd.DataFrame) -> dict:
    """Simulación de Monte Carlo (Markowitz, long-only) sobre las 30 acciones
    del IPSA, más una validación out-of-sample: los pesos de mínima varianza
    y máximo Sharpe se calculan SOLO con la primera mitad cronológica de los
    datos (in-sample), se congelan, y se aplican sobre la segunda mitad
    (out-of-sample) para medir el desempeño real — comparado contra un
    portafolio ingenuo de peso igual (1/30) en el mismo período."""
    df_retornos = _matriz_retornos_alineados(df_todas, TICKERS_IPSA)
    tickers_cols = list(df_retornos.columns)
    n_activos = len(tickers_cols)

    df_macro = df_macro.assign(fecha=pd.to_datetime(df_macro["fecha"]))
    pdbc = df_macro[df_macro["nombre"] == "Tasa libre de riesgo CLP (PDBC 14 días)"].sort_values("fecha")["valor"]
    rf = float(pdbc.iloc[-1]) / 100 if len(pdbc) else 0.0

    rng = np.random.default_rng(42)  # semilla fija para reproducibilidad

    # --- Nube completa (todo el histórico disponible) ---
    mu_anual = df_retornos.mean() * 252
    cov_anual = df_retornos.cov() * 252
    sim = _simular_portafolios_mc(mu_anual, cov_anual, rf, rng)

    pesos_min_var = pd.Series(sim["pesos"][sim["idx_min_var"]], index=tickers_cols)
    pesos_max_sharpe = pd.Series(sim["pesos"][sim["idx_max_sharpe"]], index=tickers_cols)

    resultado = {
        "tickers": tickers_cols,
        "n_dias": len(df_retornos),
        "df_retornos": df_retornos,
        "rf": rf,
        "mu_anual": mu_anual,
        "cov_anual": cov_anual,
        "vol_mc": sim["volatilidad"],
        "retorno_mc": sim["retorno"],
        "sharpe_mc": sim["sharpe"],
        "vol_min_var": float(sim["volatilidad"][sim["idx_min_var"]]),
        "retorno_min_var": float(sim["retorno"][sim["idx_min_var"]]),
        "sharpe_min_var": float(sim["sharpe"][sim["idx_min_var"]]),
        "pesos_min_var": pesos_min_var,
        "vol_max_sharpe": float(sim["volatilidad"][sim["idx_max_sharpe"]]),
        "retorno_max_sharpe": float(sim["retorno"][sim["idx_max_sharpe"]]),
        "sharpe_max_sharpe": float(sim["sharpe"][sim["idx_max_sharpe"]]),
        "pesos_max_sharpe": pesos_max_sharpe,
    }

    # --- Validación out-of-sample ---
    n_dias = len(df_retornos)
    mitad = n_dias // 2
    if mitad >= n_activos + 5:  # margen mínimo para una matriz de covarianza razonable
        df_in = df_retornos.iloc[:mitad]
        df_out = df_retornos.iloc[mitad:]

        mu_in = df_in.mean() * 252
        cov_in = df_in.cov() * 252
        sim_in = _simular_portafolios_mc(mu_in, cov_in, rf, rng)

        pesos_min_var_in = sim_in["pesos"][sim_in["idx_min_var"]]
        pesos_max_sharpe_in = sim_in["pesos"][sim_in["idx_max_sharpe"]]
        pesos_igual_in = np.full(n_activos, 1 / n_activos)

        mu_out = df_out.mean() * 252
        cov_out = df_out.cov() * 252

        def _metricas_oos(pesos):
            ret = float(pesos @ mu_out.values)
            var = float(pesos @ cov_out.values @ pesos)
            vol = var ** 0.5
            sharpe = (ret - rf) / vol if vol > 0 else None
            return {"retorno": ret, "volatilidad": vol, "sharpe": sharpe}

        resultado["oos"] = {
            "fecha_corte": df_retornos.index[mitad],
            "n_in": mitad,
            "n_out": n_dias - mitad,
            "Mínima varianza (in-sample)": _metricas_oos(pesos_min_var_in),
            "Máximo Sharpe (in-sample)": _metricas_oos(pesos_max_sharpe_in),
            "Ingenuo (1/N)": _metricas_oos(pesos_igual_in),
        }
    else:
        resultado["oos"] = None

    return resultado


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
    tab_premercado, tab_macro, tab_acciones, tab_riesgo,
    tab_benchmark, tab_tpm, tab_momentum, tab_calculadora, tab_portafolios,
    tab_riesgo_bancario,
) = st.tabs([
    "Brief Premercado", "Indicadores macro", "Acciones IPSA", "Riesgo",
    "Benchmark", "TPM y Tipo de Cambio", "Momentum IPSA",
    "Calculadora Financiera", "Optimización de Portafolios",
    "Práctica: Riesgo Bancario",
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

        # En filas de a INDICADORES_POR_FILA (no todos en una sola fila): con
        # 11 indicadores y etiquetas largas (ej. "IPSA (proxy ECH)", "Tasa de
        # desempleo"), una sola fila de columnas angostas cortaba tanto las
        # etiquetas como los valores.
        INDICADORES_POR_FILA = 4
        for inicio in range(0, len(indicadores), INDICADORES_POR_FILA):
            grupo = indicadores[inicio:inicio + INDICADORES_POR_FILA]
            # Siempre INDICADORES_POR_FILA columnas (no len(grupo)): así la
            # última fila, aunque tenga menos elementos, usa columnas del
            # mismo ancho que las filas de arriba y queda alineada con ellas
            # en vez de repartir el ancho completo en menos columnas más anchas.
            columnas = st.columns(INDICADORES_POR_FILA)
            for col, ind in zip(columnas, grupo):
                with col:
                    if ind["resultado"]:
                        valor, cambio_pct, fecha, cambio_absoluto = ind["resultado"]
                        valor_texto = f"{valor:,.2f}" + (f" {ind['unidad']}" if ind["unidad"] else "")
                        # Si el indicador ya es una tasa/porcentaje (ej. TPM,
                        # inflación anual), mostrar puntos porcentuales: el "%
                        # de cambio" de una tasa (ej. de 4,34% a 3,52% = -18,8%)
                        # es confuso, lo esperable es el cambio en pp (-0,82 pp).
                        delta_texto = f"{cambio_absoluto:+.2f} pp" if ind["unidad"] == "%" else f"{cambio_pct:+.2f}%"
                        st.metric(ind["etiqueta"], valor_texto, delta_texto)
                        st.caption(f"al {pd.Timestamp(fecha).strftime('%d-%m-%Y')}")
                    else:
                        st.metric(ind["etiqueta"], "—")
                        st.caption("sin datos suficientes")

        spread_2s10s = calcular_spread_2s10s(df_macro)
        if spread_2s10s:
            fecha_spread = pd.Timestamp(spread_2s10s["fecha"]).strftime("%d-%m-%Y")
            texto_spread = (
                f"Spread 2s10s (UST10Y − UST2Y): {spread_2s10s['spread']:+.2f} pp "
                f"(UST10Y {spread_2s10s['ust10']:.2f}% − UST2Y {spread_2s10s['ust2']:.2f}%) al {fecha_spread}."
            )
            if spread_2s10s["invertida"]:
                st.error(f"🔻 **Curva invertida.** {texto_spread}")
            else:
                st.success(texto_spread)
            st.caption(
                "Una curva invertida (spread 2s10s negativo) se ha asociado históricamente "
                "con mayor probabilidad de recesión en EEUU en los siguientes 12-24 meses "
                "— es una correlación histórica, no una predicción garantizada, y ha dado "
                "falsas señales en el pasado."
            )

        breakeven = calcular_serie_inflacion_breakeven(df_macro)
        if len(breakeven) >= 2:
            valor_actual = float(breakeven.iloc[-1])
            cambio_pp = valor_actual - float(breakeven.iloc[-2])
            fecha_breakeven = pd.Timestamp(breakeven.index[-1]).strftime("%d-%m-%Y")
            st.metric(
                "Inflación breakeven (BCP 10Y − BCU 10Y)",
                f"{valor_actual:.2f} pp",
                f"{cambio_pp:+.2f} pp",
            )
            st.caption(
                f"al {fecha_breakeven}. Es la inflación que el mercado tiene implícita en los "
                "precios de ambos bonos (tasa nominal del BCP menos tasa real del BCU, mismo "
                "emisor y plazo) — no es un pronóstico oficial de nadie."
            )

    except Exception as e:
        st.error(f"No se pudo cargar el resumen internacional: {e}")

    st.divider()
    st.subheader("Calendario económico — próximos 7 días")

    try:
        hoy = date.today()
        eventos_semana = proximos_eventos(hoy, dias=7)

        if not eventos_semana:
            st.info("No hay eventos programados en los próximos 7 días.")
        else:
            for evento in eventos_semana:
                indicador = INDICADOR_POR_TIPO[evento.tipo]
                if evento.fecha_inicio == evento.fecha_fin:
                    fecha_texto = evento.fecha_inicio.strftime("%d-%m-%Y")
                else:
                    fecha_texto = (
                        f"{evento.fecha_inicio.strftime('%d-%m')} al "
                        f"{evento.fecha_fin.strftime('%d-%m-%Y')}"
                    )
                nota_estimado = "" if evento.confirmado else " *(fecha estimada, no confirmada explícitamente)*"
                st.markdown(
                    f"<span style='background-color:{indicador['color']}; color:white; "
                    f"padding:2px 8px; border-radius:4px; font-weight:700; font-size:0.85em'>"
                    f"{indicador['etiqueta']}</span> &nbsp; **{fecha_texto}** — "
                    f"{indicador['organismo']}: {evento.descripcion}{nota_estimado}",
                    unsafe_allow_html=True,
                )

        st.caption(NOTA_VIGENCIA)
        st.caption(
            "Las reuniones de la OPEP+ no siguen un calendario anual fijo (a diferencia de "
            "los bancos centrales): desde 2024 se confirman con solo semanas de anticipación, "
            "así que este calendario puede no incluir reuniones aún no anunciadas."
        )

    except Exception as e:
        st.error(f"No se pudo cargar el calendario económico: {e}")

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
            st.markdown(_escapar_markdown_matematico(fila_brief["contenido"]))
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
                        titulo_seguro = _escapar_markdown_matematico(fila["titulo"])
                        st.markdown(f"- {hora} · *{fila['fuente']}* — [{titulo_seguro}]({fila['link']})")

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

        # La inflación breakeven no es una serie propia del BCCh: se calcula
        # (BCP - BCU) y se agrega como una serie más al selector, igual que
        # las que sí vienen directas de la base de datos.
        breakeven = calcular_serie_inflacion_breakeven(df_macro)
        if not breakeven.empty:
            df_breakeven = pd.DataFrame({
                "nombre": NOMBRE_BREAKEVEN,
                "fecha": breakeven.index,
                "valor": breakeven.values,
            })
            df_macro = pd.concat([df_macro, df_breakeven], ignore_index=True)

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

        # Gráfico principal: las 30 acciones del IPSA están disponibles para elegir,
        # pero por defecto se muestran las mismas 5 destacadas de siempre.
        tickers_disponibles = TICKERS_IPSA
        tickers_elegidos = st.multiselect(
            "Elige acciones a comparar", tickers_disponibles, default=TICKERS_IPSA_PRINCIPALES
        )

        df_filtrado = df_acciones[df_acciones["ticker"].isin(tickers_elegidos)]

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
        formato["Beta ajustada"] = "{:.2f}"
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
            "\"Beta ajustada\" = (2/3) × Beta + (1/3) × 1 (ajuste tipo Blume): tira la beta "
            "cruda hacia 1, el valor \"promedio de mercado\" de largo plazo, para corregir "
            "el sesgo de que betas históricas muy altas o muy bajas tienden a acercarse a 1 "
            "en períodos futuros. "
            "⚠️ en \"Última actualización\" indica que Yahoo Finance no refrescó el precio "
            "de ese ticker hace más de 5 días hábiles — el % de cambio mostrado no es confiable."
        )

        if capm_insumos["rf_cl"] is not None:
            spread_texto = (
                f"spread BCP10−UST10 = {capm_insumos['crp']:+.2f} pp (proxy de CRP)"
                if capm_insumos["crp"] is not None
                else "spread BCP10−UST10 no disponible"
            )
            st.info(
                f"**Nota metodológica — CAPM y prima de riesgo país (CRP).** "
                f"Rf local para el CAPM base (PDBC 14 días) = {capm_insumos['rf_cl']:.2f}%. "
                f"Para el CRP se compara **plazo contra plazo**: bono BCCh en pesos (BCP) a "
                f"10 años = {capm_insumos['rf_cl_10y']:.2f}% vs. UST10Y = "
                f"{capm_insumos['rf_ust']:.2f}%, {spread_texto}. La tasa a 10 años se usa "
                "únicamente para el CRP — el CAPM base sigue usando PDBC como tasa libre de "
                "riesgo de corto plazo, sin mezclarlas. "
                f"Prima de mercado local = {capm_insumos['prima_mercado_local']:.2f} pp "
                "(retorno histórico anualizado del proxy del IPSA menos PDBC). "
                "**CAPM local** = Rf local (PDBC) + Beta × prima de mercado local. "
                "**CAPM + CRP** = CAPM local + el spread BCP10-UST10. Se muestran ambas "
                "versiones a propósito: sumar el spread completo puede implicar un "
                "**doble conteo** del riesgo país, ya que el Beta y la Rf locales ya "
                "capturan parte de ese riesgo implícitamente (el mercado chileno se mueve "
                "distinto a EEUU en parte *por* el riesgo país). Este spread es una "
                "**aproximación al estilo Damodaran**, no el EMBI+ oficial (que requiere una "
                "fuente de datos de pago que este dashboard no tiene)."
            )

    except Exception as e:
        st.error(f"No se pudieron cargar los precios de acciones: {e}")

# --- Tab 3: Riesgo ---
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

        # La diagonal es siempre 1.0 (cada acción consigo misma) y no aporta
        # información; si se deja en la escala, domina el rango de color y
        # aplasta visualmente las correlaciones reales (típicamente 0.2-0.6
        # entre acciones individuales) cerca del punto medio gris. Se oculta
        # y la escala se ajusta al rango real de los datos, no al [-1, 1]
        # teórico.
        # ("mask" en vez de mutar .values directamente: el array que devuelve
        # una función @st.cache_data puede venir de solo lectura, y
        # np.fill_diagonal sobre esa vista lanza "underlying array is read-only".)
        mascara_diagonal = np.eye(len(matriz_corr), dtype=bool)
        matriz_display = matriz_corr.mask(mascara_diagonal)
        max_abs_offdiag = np.nanmax(np.abs(matriz_display.to_numpy()))
        max_abs_offdiag = max_abs_offdiag if pd.notna(max_abs_offdiag) and max_abs_offdiag > 0 else 1

        fig_corr = px.imshow(
            matriz_display,
            color_continuous_scale=COLORSCALE_CORRELACION,
            zmin=-max_abs_offdiag, zmax=max_abs_offdiag,
            aspect="auto",
        )
        fig_corr.update_layout(height=750)
        st.plotly_chart(fig_corr, use_container_width=True)
        st.caption(
            f"Escala de color ajustada al rango real de los datos (±{max_abs_offdiag:.2f}), "
            "no al [-1, 1] teórico — así las correlaciones moderadas típicas entre acciones "
            "individuales no se ven aplastadas cerca de cero. La diagonal se deja en blanco "
            "porque es trivialmente 1.0 y no aporta información."
        )

        st.divider()
        st.subheader("Distribución de retornos diarios — 5 acciones principales")
        st.caption(
            "Histograma de retornos diarios reales (últimos ~2 años, excluyendo días de "
            "precio congelado) con la curva normal superpuesta (misma media y desviación "
            "estándar). La distancia visible entre el histograma y la curva es evidencia "
            "directa de las colas gordas que menciona la nota sobre el VaR paramétrico "
            "más abajo."
        )

        distribuciones = calcular_distribucion_retornos(df_acciones)
        if distribuciones:
            columnas_dist = st.columns(len(distribuciones))
            for col, (nombre, datos) in zip(columnas_dist, distribuciones.items()):
                with col:
                    r = datos["retornos"]
                    mu, sigma = r.mean(), r.std()
                    xs = np.linspace(r.min(), r.max(), 200)
                    normal_pdf = stats.norm.pdf(xs, mu, sigma)

                    fig_hist = go.Figure()
                    fig_hist.add_trace(go.Histogram(
                        x=r, histnorm="probability density", name="Real",
                        marker_color="#2a78d6", opacity=0.75,
                    ))
                    fig_hist.add_trace(go.Scatter(
                        x=xs, y=normal_pdf, mode="lines", name="Normal",
                        line=dict(color="#e34948", width=2),
                    ))
                    fig_hist.update_layout(
                        title=nombre, showlegend=False, height=280,
                        margin=dict(l=10, r=10, t=30, b=10),
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)
                    st.caption(f"Skewness: {datos['skewness']:+.2f} | Kurtosis (exceso): {datos['kurtosis']:+.2f}")
        else:
            st.info("No hay suficientes datos para calcular las distribuciones.")

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

        def _mostrar_tabla_impacto(df_impacto: pd.DataFrame):
            max_abs_impacto = df_impacto["Impacto estimado (%)"].abs().max()
            max_abs_impacto = max_abs_impacto if pd.notna(max_abs_impacto) and max_abs_impacto > 0 else 1
            estilo_impacto = (
                df_impacto.style
                .background_gradient(cmap=CMAP_DIVERGENTE, subset=["Impacto estimado (%)"], vmin=-max_abs_impacto, vmax=max_abs_impacto)
                .format({"Beta": "{:.2f}", "Impacto estimado (%)": "{:+.2f}%"})
            )
            st.dataframe(estilo_impacto, use_container_width=True)

        df_macro_riesgo = cargar_series_macro()
        df_resumen_riesgo = calcular_resumen_ipsa(df_acciones, df_macro_riesgo)
        betas_todas = df_resumen_riesgo["Beta"].dropna()
        tickers_principales_sin_sufijo = [t.replace(".SN", "") for t in TICKERS_IPSA_PRINCIPALES]
        beta_portafolio_5 = betas_todas.reindex(tickers_principales_sin_sufijo).dropna().mean()

        st.divider()
        st.subheader("Stress test paramétrico")
        st.caption(
            "Simula el impacto estimado de un shock hipotético al mercado chileno "
            "(proxy ECH) sobre cada acción del IPSA y sobre el portafolio equiponderado "
            "de las 5 principales, con un modelo de un solo factor: "
            "**impacto estimado = Beta × shock**."
        )

        shock_mercado = st.slider(
            "Shock hipotético al mercado (%, proxy ECH)", -30.0, 30.0, -10.0, step=1.0, key="stress_shock"
        )

        if pd.notna(beta_portafolio_5):
            col_beta_port, col_impacto_port = st.columns(2)
            col_beta_port.metric("Beta del portafolio (5 principales, equiponderado)", f"{beta_portafolio_5:.2f}")
            col_impacto_port.metric(
                f"Impacto estimado del portafolio (shock {shock_mercado:+.0f}%)",
                f"{beta_portafolio_5 * shock_mercado:+.2f}%",
            )

        df_impacto_stress = betas_todas.to_frame(name="Beta")
        df_impacto_stress["Impacto estimado (%)"] = df_impacto_stress["Beta"] * shock_mercado
        df_impacto_stress = df_impacto_stress.sort_values("Impacto estimado (%)")
        _mostrar_tabla_impacto(df_impacto_stress)

        st.caption(
            "**Nota metodológica.** Este es un modelo de un solo factor (CAPM/Beta): "
            "asume que todo el movimiento de una acción ante un shock de mercado se "
            "explica por su Beta, **ignorando el riesgo idiosincrático** (noticias "
            "específicas de la empresa) y el **quiebre de correlaciones** típico en "
            "crisis reales (en una crisis real las correlaciones entre activos suelen "
            "subir hacia 1, y la volatilidad de todos los activos se dispara más allá de "
            "lo que el Beta histórico predice) — es una aproximación simplificada, no un "
            "modelo riguroso de riesgo de cola (tail risk)."
        )

        st.divider()
        st.subheader("Peor escenario histórico (dentro de los datos disponibles)")

        resultado_peor = calcular_peor_escenario_historico(df_acciones)
        st.warning(
            "⚠️ Esto es el **peor caso observado dentro de los datos disponibles** "
            "(desde que empezó la descarga), **no el peor caso históricamente posible** "
            "— no se citan ni asumen cifras externas de crisis pasadas (ej. 2008): un "
            "mercado real puede caer más de lo que ya cayó en esta muestra."
        )

        if resultado_peor["peor_5d"] is not None and resultado_peor["peor_10d"] is not None:
            col_5d, col_10d = st.columns(2)
            col_5d.metric("Peor retorno acumulado 5 días hábiles (ECH)", f"{resultado_peor['peor_5d'] * 100:+.2f}%")
            col_10d.metric("Peor retorno acumulado 10 días hábiles (ECH)", f"{resultado_peor['peor_10d'] * 100:+.2f}%")
            st.caption(f"Calculado sobre {resultado_peor['n_obs']} retornos diarios reales del proxy ECH.")

            if pd.notna(beta_portafolio_5):
                col_port_5d, col_port_10d = st.columns(2)
                col_port_5d.metric(
                    "Impacto estimado en el portafolio (shock 5 días)",
                    f"{beta_portafolio_5 * resultado_peor['peor_5d'] * 100:+.2f}%",
                )
                col_port_10d.metric(
                    "Impacto estimado en el portafolio (shock 10 días)",
                    f"{beta_portafolio_5 * resultado_peor['peor_10d'] * 100:+.2f}%",
                )

            col_tab5, col_tab10 = st.columns(2)
            with col_tab5:
                st.markdown("**Impacto estimado por acción — shock de 5 días**")
                df_impacto_5d = betas_todas.to_frame(name="Beta")
                df_impacto_5d["Impacto estimado (%)"] = df_impacto_5d["Beta"] * resultado_peor["peor_5d"] * 100
                df_impacto_5d = df_impacto_5d.sort_values("Impacto estimado (%)")
                _mostrar_tabla_impacto(df_impacto_5d)
            with col_tab10:
                st.markdown("**Impacto estimado por acción — shock de 10 días**")
                df_impacto_10d = betas_todas.to_frame(name="Beta")
                df_impacto_10d["Impacto estimado (%)"] = df_impacto_10d["Beta"] * resultado_peor["peor_10d"] * 100
                df_impacto_10d = df_impacto_10d.sort_values("Impacto estimado (%)")
                _mostrar_tabla_impacto(df_impacto_10d)
        else:
            st.info("No hay suficientes datos del proxy ECH para calcular el peor escenario histórico.")

    except Exception as e:
        st.error(f"No se pudieron calcular las métricas de riesgo: {e}")

# --- Tab 4: Benchmark (incluye 7 Magníficas) ---
with tab_benchmark:
    st.subheader("Benchmark internacional")
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

    st.divider()
    st.subheader("7 Magníficas")
    try:
        df_siete = cargar_precios_acciones()
        df_siete = df_siete[df_siete["ticker"].isin(TICKERS_MAGNIFICAS)].copy()

        df_siete["precio_normalizado"] = df_siete.groupby("ticker")["precio_cierre"].transform(
            lambda serie: serie / serie.iloc[0] * 100
        )

        fig_siete = px.line(
            df_siete, x="fecha", y="precio_normalizado", color="ticker",
            title="7 Magníficas — desempeño normalizado (base 100)",
            color_discrete_sequence=PALETA_CATEGORICA,
            category_orders={"ticker": TICKERS_MAGNIFICAS},
        )
        st.plotly_chart(fig_siete, use_container_width=True)

        df_resumen_magnificas = calcular_resumen_magnificas(df_siete)
        columnas_pct_magnificas = ["1D %", "1W %", "1M %", "YTD %"]
        max_abs_magnificas = df_resumen_magnificas[columnas_pct_magnificas].abs().max().max()
        max_abs_magnificas = max_abs_magnificas if pd.notna(max_abs_magnificas) and max_abs_magnificas > 0 else 1

        estilo_magnificas = (
            df_resumen_magnificas.style
            .background_gradient(cmap=CMAP_DIVERGENTE, subset=columnas_pct_magnificas, vmin=-max_abs_magnificas, vmax=max_abs_magnificas)
            .format({col: "{:+.2f}%" for col in columnas_pct_magnificas}, na_rep="—")
        )
        st.dataframe(estilo_magnificas, use_container_width=True)

    except Exception as e:
        st.error(f"No se pudieron cargar los datos de las 7 Magníficas: {e}")

# --- Tab 5: TPM y Tipo de Cambio (Event Study + Backtester) ---
with tab_tpm:
    st.header("Parte 1: ¿Hay un efecto estadístico?")
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

        def _marcar_significancia_agregado(fila):
            color_aar = _color_significancia(fila["p-valor AAR"])
            color_caar = _color_significancia(fila["p-valor CAAR"])
            return [
                color_aar if col in ("AAR (%)", "t-stat AAR", "p-valor AAR") else
                color_caar if col in ("CAAR (%)", "t-stat CAAR", "p-valor CAAR") else ""
                for col in fila.index
            ]

        st.dataframe(
            df_agregado.style
            .apply(_marcar_significancia_agregado, axis=1)
            .format({
                "AAR (%)": "{:+.3f}%",
                "t-stat AAR": "{:.2f}",
                "p-valor AAR": "{:.3f}",
                "CAAR (%)": "{:+.3f}%",
                "t-stat CAAR": "{:.2f}",
                "p-valor CAAR": "{:.3f}",
            }, na_rep="—"),
            use_container_width=True,
        )
        st.caption(LEYENDA_SIGNIFICANCIA)

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

        def _marcar_significancia_direccion(fila):
            return [_color_significancia(fila["p-valor (vs 0)"])] * len(fila)

        st.dataframe(
            df_direccion.style
            .apply(_marcar_significancia_direccion, axis=1)
            .format({
                "CAR medio (%)": "{:+.3f}%",
                "t-stat (vs 0)": "{:.2f}",
                "p-valor (vs 0)": "{:.3f}",
            }, na_rep="—"),
            use_container_width=True,
        )
        st.caption(LEYENDA_SIGNIFICANCIA)

        if diferencia["t_stat"] is not None:
            sig_dif = diferencia["p_valor"] < UMBRAL_SIGNIFICANCIA
            color_dif = "#0ca30c" if sig_dif else "#d03b3b"
            etiqueta_dif = "significativa" if sig_dif else "no significativa"
            st.markdown(
                f"**Diferencia de medias (Alza − Baja), test de Welch:** "
                f"{diferencia['diferencia_medias']:+.3f} puntos porcentuales de CAR "
                f"(t = {diferencia['t_stat']:.2f}, p = {diferencia['p_valor']:.3f}) — "
                f"<span style='color:{color_dif}; font-weight:700'>{etiqueta_dif}</span> al 5%.",
                unsafe_allow_html=True,
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

    st.divider()
    st.header("Parte 2: ¿Se podría haber ganado plata con eso?")
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
            distinguible_del_azar = percentil >= 95 or percentil <= 5
            if distinguible_del_azar:
                etiqueta_pct = "distinguible del azar"
                interpretacion = (
                    "un resultado así de extremo es poco común bajo mezclas al azar — "
                    "compatible con que el criterio direccional (y no solo el momento "
                    "de entrada/salida) esté aportando algo, aunque con solo 37 eventos "
                    "esto debe leerse con cautela."
                )
            else:
                etiqueta_pct = "indistinguible del azar"
                interpretacion = (
                    "el resultado real es indistinguible de simplemente elegir una "
                    "dirección al azar en esas mismas 37 fechas — no hay evidencia de "
                    "que el criterio direccional (TPM sube → corto, TPM baja → largo) "
                    "aporte valor por sobre el azar, más allá de si el retorno total "
                    "fue positivo o negativo."
                )
            color_pct = "#0ca30c" if distinguible_del_azar else "#d03b3b"
            st.markdown(
                f"**El resultado real ({resultado['retorno_total']:+.2f}%) cae en el "
                f"percentil {percentil:.0f} de la distribución de mezclas al azar** — "
                f"<span style='color:{color_pct}; font-weight:700'>{etiqueta_pct}</span> "
                f"({interpretacion})",
                unsafe_allow_html=True,
            )
            st.caption(
                "🟢 Verde = cae en el 5% extremo (superior o inferior) de la distribución "
                "aleatoria, distinguible del azar — 🔴 Rojo = cae en el rango central, "
                "indistinguible del azar."
            )
            st.markdown(_etiqueta_timba(distinguible_del_azar), unsafe_allow_html=True)

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

# --- Tab 6: Momentum IPSA ---
with tab_momentum:
    try:
        st.subheader("Momentum IPSA — estrategia 12-1 (Jegadeesh & Titman)")
        st.caption(
            "Cada fin de mes, rankea las 30 acciones del IPSA por su retorno "
            "compuesto de los meses [t-12, t-2] (11 meses, saltando el mes t-1 más "
            "reciente — el clásico \"12-1\" de Jegadeesh & Titman). Forma dos "
            "portafolios equiponderados de 10 acciones — \"Ganadoras\" (mejor "
            "ranking) y \"Perdedoras\" (peor ranking) — que se mantienen 1 mes y se "
            "rebalancean mensualmente, con 15 puntos base de costo de transacción "
            "por posición por rebalanceo. Excluye días de precio congelado del "
            "cálculo de retornos (mismo filtro que el resto del dashboard)."
        )

        df_acciones = cargar_precios_acciones()
        resultado_momentum = calcular_momentum_ipsa(df_acciones)

        if resultado_momentum["n_meses"] < 2:
            st.warning("No hay suficientes meses de datos para construir la estrategia de momentum.")
        else:
            df_wml = resultado_momentum["df_wml"].copy()

            col1, col2, col3 = st.columns(3)
            col1.metric("Retorno total WML acumulado", f"{resultado_momentum['retorno_total']:+.2f}%")
            col2.metric("Meses en el backtest", f"{resultado_momentum['n_meses']}")
            with col3:
                st.markdown("**t-test WML vs 0**")
                st.markdown(
                    f"<span style='{_color_significancia(resultado_momentum['p_valor'])}'>"
                    f"t = {resultado_momentum['t_stat']:.2f}, p = {resultado_momentum['p_valor']:.3f}</span>",
                    unsafe_allow_html=True,
                )
            st.caption(LEYENDA_SIGNIFICANCIA)

            df_wml["Retorno acumulado WML (%)"] = (df_wml["Equity WML"] - 1) * 100
            fig_wml = px.line(
                df_wml, x="Mes", y="Retorno acumulado WML (%)",
                title="Curva de equity del spread WML (Ganadoras − Perdedoras)",
                markers=True,
            )
            fig_wml.add_hline(y=0, line_dash="dot", line_color="#898781")
            st.plotly_chart(fig_wml, use_container_width=True)

            st.subheader(f"Retornos mensuales ({resultado_momentum['n_meses']} meses)")
            st.dataframe(
                df_wml.drop(columns=["Retorno acumulado WML (%)"]).style.format({
                    "Ganadoras (%)": "{:+.2f}%",
                    "Perdedoras (%)": "{:+.2f}%",
                    "WML (%)": "{:+.2f}%",
                    "Equity WML": "{:.4f}",
                }),
                use_container_width=True,
            )

            st.divider()
            st.subheader("Test de permutación: ¿le gana el momentum al azar?")
            st.caption(
                f"En cada uno de los {resultado_momentum['n_meses']} meses se sortearon al azar "
                f"10 \"ganadoras\" y 10 \"perdedoras\" entre las acciones disponibles ese mes "
                f"(en vez de usar el ranking de momentum real), {N_PERMUTACIONES_MOMENTUM:,} veces, "
                "preservando la estructura temporal (mismas fechas, mismos retornos, mismo "
                "costo de transacción — solo cambia qué acciones se etiquetan "
                "ganadoras/perdedoras cada mes)."
            )

            fig_hist_momentum = px.histogram(
                x=resultado_momentum["retornos_totales_perm"],
                nbins=50,
                title=f"Distribución de retornos totales bajo {N_PERMUTACIONES_MOMENTUM:,} mezclas aleatorias",
                labels={"x": "Retorno total acumulado (%)"},
            )
            fig_hist_momentum.add_vline(
                x=resultado_momentum["retorno_total"], line_color="#e34948", line_width=2,
                annotation_text="Resultado real", annotation_position="top",
            )
            st.plotly_chart(fig_hist_momentum, use_container_width=True)

            percentil_momentum = resultado_momentum["percentil_real"]
            distinguible_del_azar_momentum = percentil_momentum >= 95 or percentil_momentum <= 5
            etiqueta_momentum = "distinguible del azar" if distinguible_del_azar_momentum else "indistinguible del azar"
            color_momentum = "#0ca30c" if distinguible_del_azar_momentum else "#d03b3b"
            st.markdown(
                f"**El resultado real ({resultado_momentum['retorno_total']:+.2f}%) cae en el "
                f"percentil {percentil_momentum:.0f} de la distribución de mezclas al azar** — "
                f"<span style='color:{color_momentum}; font-weight:700'>{etiqueta_momentum}</span>.",
                unsafe_allow_html=True,
            )
            st.caption(
                "🟢 Verde = cae en el 5% extremo (superior o inferior), distinguible del azar "
                "— 🔴 Rojo = cae en el rango central, indistinguible del azar."
            )
            st.markdown(_etiqueta_timba(distinguible_del_azar_momentum), unsafe_allow_html=True)

        st.divider()
        st.info(
            "**Nota metodológica.** Esta pestaña prueba la versión de **momentum de "
            "corto/mediano plazo** de Jegadeesh & Titman (1993): acciones que subieron "
            "en los últimos 12 meses (saltando el más reciente) tienden a seguir "
            "subiendo en el mes siguiente. Esto es **distinto** — y en apariencia "
            "contradictorio — de De Bondt & Thaler (1985), que documentan reversión a "
            "**largo plazo** (3-5 años): acciones \"perdedoras\" durante varios años "
            "tienden a superar a las \"ganadoras\" en el período siguiente. Ambos "
            "efectos coexisten en la literatura porque operan en horizontes distintos: "
            "el diseño de esta pestaña (formación de 11 meses, mantención de 1 mes) "
            "prueba específicamente el momentum de corto/mediano plazo, no la reversión "
            "de largo plazo de De Bondt & Thaler. Es un backtest hipotético e "
            "ilustrativo, con solo 10 acciones por pata (n chico) sobre un universo de "
            "30 — no es una recomendación de inversión."
        )

    except Exception as e:
        st.error(f"No se pudo calcular la estrategia de momentum: {e}")

# --- Tab 7: Calculadora Financiera ---
with tab_calculadora:
    try:
        st.caption(
            "Tres modelos interactivos de valorización clásicos. A diferencia del resto "
            "del dashboard, estos NO dependen de datos fundamentales descargados — el "
            "usuario ingresa sus propios valores."
        )

        # ============ 1. CAPM interactivo ============
        st.subheader("1. CAPM interactivo")
        st.markdown(
            "**Fórmula:** Costo de capital = Rf + Beta × Prima de mercado. El CAPM "
            "estima el retorno anual que un inversionista debería exigir por invertir "
            "en una acción, según su riesgo sistemático (Beta) relativo al mercado — "
            "el mismo modelo que ya usa el heatmap de \"Acciones IPSA\", acá con "
            "inputs libres para explorar escenarios."
        )

        OPCION_SIN_PRECARGA = "(ninguno — ajustar manualmente)"

        def _precargar_capm():
            ticker_sel = st.session_state.get("capm_preload_selector")
            if not ticker_sel or ticker_sel == OPCION_SIN_PRECARGA:
                return
            try:
                df_macro_c = cargar_series_macro()
                df_acciones_c = cargar_precios_acciones()
                df_resumen_c = calcular_resumen_ipsa(df_acciones_c, df_macro_c)
                capm_insumos_c = calcular_crp_y_prima_mercado(df_macro_c, df_acciones_c)
                if ticker_sel in df_resumen_c.index:
                    beta_real = df_resumen_c.loc[ticker_sel, "Beta"]
                    if pd.notna(beta_real):
                        st.session_state["capm_beta_slider"] = float(min(max(beta_real, 0.0), 3.0))
                if capm_insumos_c["rf_cl"] is not None:
                    st.session_state["capm_rf_slider"] = float(min(max(capm_insumos_c["rf_cl"], 0.0), 15.0))
                if capm_insumos_c["prima_mercado_local"] is not None:
                    st.session_state["capm_prima_slider"] = float(
                        min(max(capm_insumos_c["prima_mercado_local"], 0.0), 15.0)
                    )
            except Exception:
                pass  # si falla la precarga, el usuario igual puede ajustar los sliders a mano

        opciones_precarga = [OPCION_SIN_PRECARGA] + [t.replace(".SN", "") for t in TICKERS_IPSA]
        st.selectbox(
            "Precargar valores reales de:", opciones_precarga,
            key="capm_preload_selector", on_change=_precargar_capm,
            help="Precarga Rf (PDBC) y Beta reales de la acción elegida como punto de "
                 "partida — después puedes ajustar los sliders libremente.",
        )

        # setdefault (no value=) evita el warning de Streamlit por mezclar un
        # valor por defecto fijo con session_state ya escrito por _precargar_capm.
        st.session_state.setdefault("capm_rf_slider", 4.5)
        st.session_state.setdefault("capm_beta_slider", 1.0)
        st.session_state.setdefault("capm_prima_slider", 6.0)

        col_rf, col_beta, col_prima = st.columns(3)
        with col_rf:
            rf_capm = st.slider("Tasa libre de riesgo (Rf) %", 0.0, 15.0, step=0.1, key="capm_rf_slider")
        with col_beta:
            beta_capm = st.slider("Beta", 0.0, 3.0, step=0.05, key="capm_beta_slider")
        with col_prima:
            prima_capm = st.slider("Prima de mercado %", 0.0, 15.0, step=0.1, key="capm_prima_slider")

        costo_capital_capm = rf_capm + beta_capm * prima_capm
        st.metric("Costo de capital (CAPM)", f"{costo_capital_capm:.2f}%")
        st.caption(
            "Interpretación: es el retorno anual mínimo que debería exigir un "
            "inversionista para mantener esta acción, dado su riesgo sistemático — un "
            "Beta > 1 amplifica los movimientos del mercado, un Beta < 1 los atenúa."
        )

        st.divider()

        # ============ 2. Dodd-Graham Value Screener ============
        st.subheader("2. Dodd-Graham Value Screener")
        st.markdown(
            "**Los 10 criterios clásicos** (adaptados de *Security Analysis*, Dodd & "
            "Graham, 1934, y *The Intelligent Investor*, Graham, cap. 14) para "
            "identificar acciones \"value\" según el inversionista defensivo de Graham: "
            "solidez financiera, estabilidad y crecimiento de utilidades, precio "
            "moderado respecto a utilidades y activos, y dividendos sostenibles."
        )
        st.warning(
            "⚠️ Estos criterios se diseñaron para el mercado bursátil de EEUU de "
            "mediados del siglo XX (múltiplos, tasas y estructura de capital muy "
            "distintos a los de hoy). Aplicarlos sin ajuste a un mercado emergente como "
            "Chile — con menor liquidez, mayor prima de riesgo país y otra estructura "
            "tributaria — es una simplificación; no deben tomarse como un veredicto "
            "definitivo de \"barata\" o \"cara\"."
        )

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            g_precio = st.number_input("Precio actual", min_value=0.0, value=100.0, step=1.0, key="graham_precio")
            g_eps = st.number_input("EPS (utilidad por acción, actual)", value=8.0, step=0.5, key="graham_eps")
            g_pe5 = st.number_input("P/E promedio últimos 5 años", min_value=0.0, value=12.0, step=0.5, key="graham_pe5")
            g_dividendo = st.number_input("Dividendo por acción", min_value=0.0, value=3.0, step=0.5, key="graham_div")
            g_valor_libro = st.number_input("Valor libro por acción", min_value=0.0, value=70.0, step=1.0, key="graham_vl")
        with col_g2:
            g_deuda = st.number_input("Deuda total", min_value=0.0, value=200.0, step=10.0, key="graham_deuda")
            g_activos_c = st.number_input("Activos corrientes", min_value=0.0, value=400.0, step=10.0, key="graham_ac")
            g_pasivos_c = st.number_input("Pasivos corrientes", min_value=0.01, value=150.0, step=10.0, key="graham_pc")
            g_yield_aaa = st.number_input("Yield de bonos AAA (%)", min_value=0.0, value=5.0, step=0.1, key="graham_aaa")
            g_eps_hist = st.number_input("EPS hace 10 años", value=5.0, step=0.5, key="graham_eps_hist")

        criterios_graham = evaluar_graham(
            precio=g_precio, eps=g_eps, pe_5y=g_pe5, dividendo=g_dividendo,
            valor_libro=g_valor_libro, deuda_total=g_deuda,
            activos_corrientes=g_activos_c, pasivos_corrientes=g_pasivos_c,
            yield_aaa=g_yield_aaa, eps_historico=g_eps_hist,
        )
        n_cumple_graham = sum(c["cumple"] for c in criterios_graham)
        st.metric("Criterios que cumple", f"{n_cumple_graham} / 10")

        for c in criterios_graham:
            icono = "✅" if c["cumple"] else "❌"
            st.markdown(f"{icono} **{c['criterio']}** — {c['valor']}")
            st.caption(c["explicacion"])

        st.divider()

        # ============ 3. Modelo de Descuento de Dividendos (Gordon Growth) ============
        st.subheader("3. Modelo de Descuento de Dividendos (Gordon Growth)")
        st.markdown(
            "**Fórmula:** Precio implícito = D₁ / (r − g), donde D₁ es el dividendo "
            "esperado el próximo año, r la tasa de descuento (retorno exigido) y g la "
            "tasa de crecimiento esperada de los dividendos a perpetuidad. Estima "
            "cuánto \"debería\" valer una acción según el flujo de dividendos futuros "
            "que promete, descontado a valor presente."
        )

        col_d1, col_r, col_g = st.columns(3)
        with col_d1:
            d1_gordon = st.number_input(
                "Dividendo esperado próximo año (D₁)", min_value=0.0, value=5.0, step=0.5, key="gordon_d1"
            )
        with col_r:
            r_gordon = st.slider("Tasa de descuento (r) %", 0.1, 30.0, 10.0, step=0.1, key="gordon_r")
        with col_g:
            g_gordon = st.slider("Tasa de crecimiento esperada (g) %", 0.0, 30.0, 4.0, step=0.1, key="gordon_g")

        if g_gordon >= r_gordon:
            st.error(
                "⚠️ **g ≥ r: el modelo no es matemáticamente válido.** Con crecimiento "
                "mayor o igual a la tasa de descuento, el denominador (r − g) es cero o "
                "negativo, lo que implicaría un precio infinito o negativo — sin sentido "
                "económico. Ajusta los valores para que r > g."
            )
        else:
            precio_implicito_gordon = d1_gordon / ((r_gordon - g_gordon) / 100)
            st.metric("Precio implícito", f"${precio_implicito_gordon:,.2f}")
            st.caption(
                "Interpretación: si el precio de mercado actual es mayor a este valor "
                "implícito, el modelo sugiere que la acción podría estar sobrevalorada "
                "(y viceversa) — asumiendo que los supuestos de r y g se cumplan "
                "indefinidamente, lo cual rara vez es realista para horizontes largos."
            )

    except Exception as e:
        st.error(f"No se pudo calcular la calculadora financiera: {e}")

# --- Tab 8: Optimización de Portafolios ---
with tab_portafolios:
    try:
        st.subheader("Simulación de Monte Carlo — frontera eficiente")
        st.caption(
            f"{N_PORTAFOLIOS_MC:,} portafolios con pesos aleatorios (suman 100%, sin "
            "posiciones cortas) entre las 30 acciones del IPSA, usando retorno promedio "
            "histórico y matriz de covarianza anualizados — excluyendo días de precio "
            "congelado (mismo filtro que el resto del dashboard). Cada punto es un "
            "portafolio simulado."
        )

        df_acciones = cargar_precios_acciones()
        df_macro = cargar_series_macro()
        resultado_opt = calcular_optimizacion_portafolios(df_acciones, df_macro)

        fig_mc = go.Figure()
        fig_mc.add_trace(go.Scatter(
            x=resultado_opt["vol_mc"] * 100, y=resultado_opt["retorno_mc"] * 100,
            mode="markers",
            marker=dict(
                size=5, color=resultado_opt["sharpe_mc"],
                colorscale=[[0, "#fcfcfb"], [1, "#2a78d6"]],
                colorbar=dict(title="Sharpe"), opacity=0.6,
            ),
            name="Portafolios simulados",
            hovertemplate="Vol: %{x:.2f}%<br>Retorno: %{y:.2f}%<extra></extra>",
        ))
        fig_mc.add_trace(go.Scatter(
            x=[resultado_opt["vol_min_var"] * 100], y=[resultado_opt["retorno_min_var"] * 100],
            mode="markers", marker=dict(size=18, color="#0ca30c", symbol="star", line=dict(width=1, color="black")),
            name="Mínima varianza",
        ))
        fig_mc.add_trace(go.Scatter(
            x=[resultado_opt["vol_max_sharpe"] * 100], y=[resultado_opt["retorno_max_sharpe"] * 100],
            mode="markers", marker=dict(size=18, color="#e34948", symbol="star", line=dict(width=1, color="black")),
            name="Máximo Sharpe",
        ))
        fig_mc.update_layout(
            xaxis_title="Volatilidad anualizada (%)", yaxis_title="Retorno esperado anualizado (%)",
            height=550,
        )
        # El gráfico se muestra una sola vez, más abajo — después de que el
        # constructor interactivo decida si agrega o no el punto del usuario,
        # para no duplicar el mismo gráfico dos veces en la pantalla.

        col_mv, col_ms = st.columns(2)
        with col_mv:
            st.markdown(
                f"**⭐ Mínima varianza** — vol {resultado_opt['vol_min_var'] * 100:.2f}%, "
                f"retorno {resultado_opt['retorno_min_var'] * 100:.2f}%, "
                f"Sharpe {resultado_opt['sharpe_min_var']:.2f}"
            )
            st.markdown("Top 10 posiciones:")
            top_mv = resultado_opt["pesos_min_var"].sort_values(ascending=False).head(10) * 100
            st.dataframe(top_mv.to_frame("Peso (%)").style.format("{:.1f}%"), use_container_width=True)
        with col_ms:
            st.markdown(
                f"**⭐ Máximo Sharpe** — vol {resultado_opt['vol_max_sharpe'] * 100:.2f}%, "
                f"retorno {resultado_opt['retorno_max_sharpe'] * 100:.2f}%, "
                f"Sharpe {resultado_opt['sharpe_max_sharpe']:.2f}"
            )
            st.markdown("Top 10 posiciones:")
            top_ms = resultado_opt["pesos_max_sharpe"].sort_values(ascending=False).head(10) * 100
            st.dataframe(top_ms.to_frame("Peso (%)").style.format("{:.1f}%"), use_container_width=True)

        st.divider()
        st.subheader("Constructor interactivo de portafolio")
        st.caption(
            "Elige entre 3 y 8 acciones y asigna sus pesos — deben sumar 100%. Tu "
            "portafolio se ubica en tiempo real dentro de la misma nube de arriba."
        )

        tickers_construir = st.multiselect(
            "Elige entre 3 y 8 acciones", resultado_opt["tickers"],
            default=resultado_opt["tickers"][:5], key="construir_tickers",
        )

        if len(tickers_construir) < 3 or len(tickers_construir) > 8:
            st.warning(f"⚠️ Elige entre 3 y 8 acciones (llevas {len(tickers_construir)}).")
            st.plotly_chart(fig_mc, use_container_width=True)
        else:
            peso_default = round(100 / len(tickers_construir), 1)
            cols_pesos = st.columns(len(tickers_construir))
            pesos_construidos = {}
            for col, ticker in zip(cols_pesos, tickers_construir):
                key_slider = f"peso_construir_{ticker}"
                st.session_state.setdefault(key_slider, peso_default)
                with col:
                    pesos_construidos[ticker] = st.slider(ticker, 0.0, 100.0, step=1.0, key=key_slider)

            suma_pesos = sum(pesos_construidos.values())
            if abs(suma_pesos - 100) > 0.5:
                st.error(f"⚠️ Los pesos suman {suma_pesos:.1f}% — deben sumar 100%. Ajusta los sliders.")
                st.plotly_chart(fig_mc, use_container_width=True)
            else:
                st.success(f"✅ Los pesos suman {suma_pesos:.1f}%")

                pesos_vector = pd.Series(0.0, index=resultado_opt["tickers"])
                for ticker, peso in pesos_construidos.items():
                    pesos_vector[ticker] = peso / 100

                ret_custom = float(pesos_vector.values @ resultado_opt["mu_anual"].values)
                var_custom = float(pesos_vector.values @ resultado_opt["cov_anual"].values @ pesos_vector.values)
                vol_custom = var_custom ** 0.5
                sharpe_custom = (ret_custom - resultado_opt["rf"]) / vol_custom if vol_custom > 0 else None

                pesos_array_construir = np.array([pesos_construidos[t] / 100 for t in tickers_construir])
                retornos_diarios_custom = resultado_opt["df_retornos"][tickers_construir].to_numpy() @ pesos_array_construir
                var_hist_95_custom = -np.percentile(retornos_diarios_custom, 5) * 100

                fig_mc.add_trace(go.Scatter(
                    x=[vol_custom * 100], y=[ret_custom * 100],
                    mode="markers", marker=dict(size=20, color="#eda100", symbol="diamond", line=dict(width=1, color="black")),
                    name="Tu portafolio",
                ))
                st.plotly_chart(fig_mc, use_container_width=True)

                col_c1, col_c2, col_c3, col_c4 = st.columns(4)
                col_c1.metric("Volatilidad anualizada", f"{vol_custom * 100:.2f}%")
                col_c2.metric("Retorno esperado anualizado", f"{ret_custom * 100:.2f}%")
                col_c3.metric("Sharpe ratio", f"{sharpe_custom:.2f}" if sharpe_custom is not None else "—")
                col_c4.metric("VaR histórico 95% (diario)", f"{var_hist_95_custom:.2f}%")

        st.divider()
        st.subheader("Validación out-of-sample")
        st.caption(
            "La parte más importante: los pesos de \"Mínima varianza\" y \"Máximo "
            "Sharpe\" de esta sección se calculan usando **solo la primera mitad "
            "cronológica** de los datos disponibles (in-sample), se congelan sin "
            "recalcular, y se aplican sobre la **segunda mitad** (out-of-sample) para "
            "medir el desempeño real que habrían tenido — comparados contra un "
            "portafolio ingenuo de peso igual (1/30) en el mismo período."
        )

        oos = resultado_opt["oos"]
        if oos is None:
            st.info("No hay suficientes datos históricos para dividir en dos mitades y validar out-of-sample.")
        else:
            st.caption(
                f"Corte in-sample/out-of-sample: {pd.Timestamp(oos['fecha_corte']).strftime('%d-%m-%Y')} "
                f"({oos['n_in']} días in-sample, {oos['n_out']} días out-of-sample)."
            )

            filas_oos = []
            for nombre, m in oos.items():
                if isinstance(m, dict) and "retorno" in m:
                    filas_oos.append({
                        "Portafolio": nombre,
                        "Retorno OOS anualizado (%)": m["retorno"] * 100,
                        "Volatilidad OOS anualizada (%)": m["volatilidad"] * 100,
                        "Sharpe OOS": m["sharpe"] if m["sharpe"] is not None else float("nan"),
                    })
            df_oos = pd.DataFrame(filas_oos).set_index("Portafolio")
            st.dataframe(
                df_oos.style.format({
                    "Retorno OOS anualizado (%)": "{:+.2f}%",
                    "Volatilidad OOS anualizada (%)": "{:.2f}%",
                    "Sharpe OOS": "{:.2f}",
                }),
                use_container_width=True,
            )

            ganador_sharpe = df_oos["Sharpe OOS"].idxmax()
            if ganador_sharpe == "Ingenuo (1/N)":
                st.warning(
                    f"📊 **Resultado:** en este período out-of-sample, el portafolio "
                    f"**ingenuo (1/N)** tuvo el mejor Sharpe ratio real "
                    f"({df_oos.loc['Ingenuo (1/N)', 'Sharpe OOS']:.2f}), superando a los "
                    f"portafolios \"óptimos\" calculados con datos in-sample. Esto es "
                    "consistente con hallazgos documentados en la literatura (ej. "
                    "DeMiguel, Garlappi & Uppal, 2009): la optimización de Markowitz es "
                    "muy sensible al error de estimación, y en la práctica frecuentemente "
                    "no le gana a la diversificación ingenua fuera de muestra."
                )
            else:
                st.success(
                    f"📊 **Resultado:** en este período out-of-sample, **\"{ganador_sharpe}\"** "
                    f"tuvo el mejor Sharpe ratio real ({df_oos.loc[ganador_sharpe, 'Sharpe OOS']:.2f}), "
                    "superando al portafolio ingenuo (1/N) — en este caso particular, la "
                    "optimización in-sample sí se tradujo en mejor desempeño real. Esto no "
                    "garantiza que se repita en otros períodos."
                )

        st.divider()
        st.info(
            "**Nota metodológica.** Este es el modelo clásico de **Markowitz (1952)**: "
            "maximizar retorno esperado para un nivel de riesgo dado (o minimizar riesgo "
            "para un retorno dado), usando la media y covarianza históricas como "
            "estimadores del futuro. La **crítica clásica de Michaud (1989)** — el "
            "\"error-maximizador\" de Markowitz — es que el modelo es muy sensible a la "
            "estimación del retorno esperado: con solo unos años de historia, esas "
            "estimaciones tienen alta incertidumbre, y pequeños cambios en los inputs "
            "pueden producir carteras \"óptimas\" muy distintas. La validación "
            "out-of-sample de arriba es precisamente una forma directa de exponer ese "
            "problema. Los portafolios de mínima varianza y máximo Sharpe se identifican "
            f"por búsqueda entre los {N_PORTAFOLIOS_MC:,} portafolios simulados (Monte "
            "Carlo), no mediante un solver de optimización cuadrática exacto — una "
            "aproximación adicional. Soluciones más robustas usadas en la industria "
            "(Black-Litterman, matrices de covarianza por régimen de mercado, "
            "shrinkage estimators) quedan fuera del alcance de este proyecto. **Los "
            "pesos \"óptimos\" mostrados son ilustrativos del framework, no una "
            "recomendación de inversión.**"
        )

    except Exception as e:
        st.error(f"No se pudo calcular la optimización de portafolios: {e}")

# --- Tab 9: Práctica - Riesgo Bancario ---
with tab_riesgo_bancario:
    st.warning(
        "🎓 **Herramientas educativas — no ligadas a ninguna institución real.** "
        "Todos los valores de esta pestaña los ingresa el usuario; no hay datos "
        "de ningún banco (chileno o extranjero), reales ni hardcodeados. El "
        "objetivo es practicar los conceptos de riesgo bancario, no evaluar a "
        "ninguna entidad en particular."
    )
    st.caption(
        "Cinco calculadoras interactivas: cada una muestra su fórmula, pide los "
        "inputs y explica qué significa el resultado."
    )

    try:
        # ============ 1. LCR ============
        st.subheader("1. LCR — Coeficiente de Cobertura de Liquidez")
        st.markdown(
            "**Fórmula:** LCR = HQLA / Salidas netas de efectivo a 30 días. Mide si "
            "un banco tiene suficientes activos líquidos de alta calidad (HQLA — "
            "efectivo, reservas en el banco central, deuda soberana de alta calidad) "
            "para sobrevivir 30 días de estrés de liquidez severo sin depender de "
            "financiamiento externo. Parte del marco de Basilea III."
        )
        col_hqla, col_salidas = st.columns(2)
        with col_hqla:
            lcr_hqla = st.number_input(
                "HQLA — activos líquidos de alta calidad", min_value=0.0, value=1_000.0,
                step=50.0, key="lcr_hqla",
            )
        with col_salidas:
            lcr_salidas = st.number_input(
                "Salidas netas de efectivo proyectadas a 30 días", min_value=0.01,
                value=800.0, step=50.0, key="lcr_salidas",
            )

        lcr = lcr_hqla / lcr_salidas * 100
        st.metric("LCR", f"{lcr:.1f}%", f"{lcr - 100:+.1f} pp vs. mínimo regulatorio (100%)")
        if lcr >= 100:
            st.success(f"✅ LCR de {lcr:.1f}% ≥ 100% — cumpliría el mínimo regulatorio de Basilea III.")
        else:
            st.error(f"🔻 LCR de {lcr:.1f}% < 100% — no cumpliría el mínimo regulatorio de Basilea III.")
        st.caption(
            "El mínimo regulatorio internacional (Basilea III) es 100%: los HQLA "
            "deben cubrir por completo las salidas netas de efectivo proyectadas a "
            "30 días bajo un escenario de estrés severo (retiro de depósitos, "
            "pérdida de acceso a financiamiento mayorista, etc.)."
        )

        st.divider()

        # ============ 2. ΔEVE y ΔNII ============
        st.subheader("2. ΔEVE y ΔNII — riesgo de tasa de interés en el libro bancario")
        st.markdown(
            "**ΔEVE** (cambio en el Valor Económico del Patrimonio) mide el impacto "
            "de un shock de tasas sobre el valor presente de todo el balance — riesgo "
            "de **largo plazo**. **ΔNII** (cambio en el Margen de Interés Neto) mide "
            "el impacto sobre las utilidades de los próximos 12 meses — riesgo de "
            "**corto plazo**. Se calculan con gaps de repreciación distintos porque "
            "responden preguntas distintas."
        )
        st.markdown(
            "**Fórmulas simplificadas (con fines ilustrativos):**\n"
            "- ΔEVE ≈ −(VP activos que reprecian − VP pasivos que reprecian) × shock\n"
            "- ΔNII ≈ (Monto activos que reprecian en 12m − Monto pasivos que "
            "reprecian en 12m) × shock"
        )

        shock_pb = st.slider(
            "Shock de tasas (puntos base)", -300, 300, 200, step=25, key="riesgo_shock_pb",
            help="Shock paralelo de tasas, en puntos base (100 pb = 1 punto porcentual).",
        )
        shock_frac = shock_pb / 10_000  # puntos base -> fracción

        col_eve1, col_eve2 = st.columns(2)
        with col_eve1:
            vp_activos = st.number_input(
                "VP de activos que reprecian (sensibles a tasa)", min_value=0.0,
                value=1_000.0, step=50.0, key="eve_vp_activos",
            )
            monto_activos_12m = st.number_input(
                "Monto de activos que reprecian en 12 meses", min_value=0.0,
                value=400.0, step=25.0, key="nii_activos_12m",
            )
        with col_eve2:
            vp_pasivos = st.number_input(
                "VP de pasivos que reprecian (sensibles a tasa)", min_value=0.0,
                value=400.0, step=50.0, key="eve_vp_pasivos",
            )
            monto_pasivos_12m = st.number_input(
                "Monto de pasivos que reprecian en 12 meses", min_value=0.0,
                value=350.0, step=25.0, key="nii_pasivos_12m",
            )

        gap_eve = vp_activos - vp_pasivos
        delta_eve = -gap_eve * shock_frac * 100  # en las mismas unidades que los inputs (%), ver caption

        gap_nii = monto_activos_12m - monto_pasivos_12m
        delta_nii = gap_nii * shock_frac * 100

        etiqueta_shock = f"shock de {shock_pb:+d} pb"
        col_res_eve, col_res_nii = st.columns(2)
        with col_res_eve:
            st.metric(f"ΔEVE ({etiqueta_shock})", f"{delta_eve:+.1f}")
        with col_res_nii:
            st.metric(f"ΔNII ({etiqueta_shock})", f"{delta_nii:+.1f}")

        st.info(
            "💡 **Un banco puede tener ΔNII saludable y ΔEVE muy negativo al mismo "
            "tiempo** (fue, en términos generales, el patrón detrás del colapso de "
            "Silicon Valley Bank en 2023): si los depósitos son \"pegajosos\" y no "
            "reprecian rápido, el gap de 12 meses puede verse controlado — pero si el "
            "banco financia bonos de **largo plazo** con esos mismos depósitos de "
            "**corto plazo**, el valor económico del patrimonio (ΔEVE) puede caer con "
            "fuerza ante un alza de tasas, aunque las utilidades del año siguiente no "
            "lo reflejen todavía. Por eso los reguladores exigen mirar ambas métricas, "
            "no solo el margen de interés del año en curso."
        )
        st.caption(
            "Simplificación pedagógica: se asume una sensibilidad lineal (duración "
            "efectiva ≈ 1) sobre el gap de repreciación, en vez de un cálculo de "
            "duración/convexidad por tramo — suficiente para ilustrar la dirección e "
            "intuición del riesgo, no para un cálculo regulatorio real."
        )

        st.divider()

        # ============ 3. CVA ============
        st.subheader("3. CVA — Ajuste de Valoración por Riesgo de Crédito")
        st.markdown(
            "**Fórmula:** CVA = Exposición esperada × PD × LGD (donde LGD = 1 − Tasa "
            "de recuperación). Es el descuento que se le aplica al valor de un "
            "derivado o instrumento de crédito por el riesgo de que la contraparte "
            "no pague — cuánto \"vale\" ese riesgo de no pago, en la misma moneda del "
            "instrumento."
        )
        col_cva1, col_cva2, col_cva3 = st.columns(3)
        with col_cva1:
            cva_ee = st.number_input(
                "Exposición esperada (EE)", min_value=0.0, value=1_000.0, step=50.0, key="cva_ee",
            )
        with col_cva2:
            cva_pd = st.slider("Probabilidad de incumplimiento (PD) %", 0.0, 100.0, 2.0, step=0.1, key="cva_pd")
        with col_cva3:
            cva_recuperacion = st.slider("Tasa de recuperación %", 0.0, 100.0, 40.0, step=1.0, key="cva_recuperacion")

        cva_lgd = 1 - cva_recuperacion / 100
        cva = cva_ee * (cva_pd / 100) * cva_lgd
        st.metric("CVA", f"{cva:,.2f}")
        st.caption(
            f"LGD (pérdida dado el incumplimiento) = 1 − {cva_recuperacion:.0f}% = "
            f"{cva_lgd:.2f}. Interpretación: es el monto que, en valor esperado, se "
            "pierde por el riesgo de contraparte — cuanto mayor la PD o menor la tasa "
            "de recuperación, mayor el ajuste."
        )

        st.divider()

        # ============ 4. ROIC vs ROE ============
        st.subheader("4. ROIC vs. ROE — el efecto del apalancamiento")
        st.markdown(
            "**Fórmulas:** ROIC = NOPAT / Capital invertido. ROE = Utilidad neta / "
            "Patrimonio. El ROIC mide el retorno sobre **todo** el capital que "
            "financia el negocio (deuda + patrimonio); el ROE mide el retorno que le "
            "queda solo a los **dueños**, después de pagar a los acreedores. La "
            "diferencia entre ambos es, en gran medida, el efecto del apalancamiento."
        )
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            roic_nopat = st.number_input(
                "NOPAT (utilidad operacional neta de impuestos)", value=150.0, step=10.0, key="roic_nopat",
            )
            roic_capital = st.number_input(
                "Capital invertido (deuda + patrimonio)", min_value=0.01, value=1_500.0, step=50.0, key="roic_capital",
            )
        with col_r2:
            roe_utilidad = st.number_input("Utilidad neta", value=120.0, step=10.0, key="roe_utilidad")
            roe_patrimonio = st.number_input("Patrimonio", min_value=0.01, value=800.0, step=50.0, key="roe_patrimonio")

        roic = roic_nopat / roic_capital * 100
        roe = roe_utilidad / roe_patrimonio * 100
        col_res_r1, col_res_r2 = st.columns(2)
        with col_res_r1:
            st.metric("ROIC", f"{roic:.2f}%")
        with col_res_r2:
            st.metric("ROE", f"{roe:.2f}%")

        if roe > roic:
            st.caption(
                f"ROE ({roe:.2f}%) > ROIC ({roic:.2f}%): el apalancamiento está "
                "amplificando el retorno para los dueños — el negocio genera, sobre el "
                "capital total, más de lo que cuesta la deuda que lo financia. Ese "
                "mismo apalancamiento amplifica las pérdidas si el ROIC cae por debajo "
                "del costo de la deuda."
            )
        else:
            st.caption(
                f"ROE ({roe:.2f}%) ≤ ROIC ({roic:.2f}%): el apalancamiento no está "
                "beneficiando a los dueños en este escenario — puede indicar que el "
                "costo de la deuda supera el retorno que genera el capital invertido."
            )

        st.divider()

        # ============ 5. Days to Cover (Short Squeeze) ============
        st.subheader("5. Days to Cover — riesgo de short squeeze")
        st.markdown(
            "**Fórmula:** Days to Cover = Interés corto (acciones vendidas en corto) "
            "/ Volumen promedio diario transado. Estima cuántos días de negociación "
            "tomaría cerrar todas las posiciones cortas al ritmo de volumen actual — "
            "cuanto más alto, mayor el riesgo de un *short squeeze* (una subida de "
            "precio forzada por los propios vendedores en corto corriendo a comprar "
            "para cerrar posición)."
        )
        col_dtc1, col_dtc2 = st.columns(2)
        with col_dtc1:
            dtc_interes_corto = st.number_input(
                "Interés corto (acciones vendidas en corto)", min_value=0.0,
                value=5_000_000.0, step=100_000.0, key="dtc_interes_corto",
            )
        with col_dtc2:
            dtc_volumen = st.number_input(
                "Volumen promedio diario transado", min_value=0.01, value=1_000_000.0,
                step=50_000.0, key="dtc_volumen",
            )

        days_to_cover = dtc_interes_corto / dtc_volumen
        st.metric("Days to Cover", f"{days_to_cover:.1f} días")
        st.caption(
            "Como referencia informal de mercado: valores altos (aprox. > 5-10 días, "
            "sin un umbral regulatorio único) suelen asociarse a mayor riesgo de "
            "short squeeze — pero depende mucho del contexto de cada acción."
        )
        st.error(
            "🇨🇱 **No calculable con datos reales del mercado chileno.** A diferencia "
            "de EEUU (donde FINRA publica el short interest de cada acción cada dos "
            "semanas), en la Bolsa de Santiago **no existe información pública de "
            "posiciones cortas** — no hay una fuente oficial de \"interés corto\" para "
            "ninguna acción del IPSA. Esta calculadora es puramente ilustrativa con "
            "cifras hipotéticas que ingresa el usuario. Este vacío de transparencia "
            "en el mercado chileno es parte de lo que motivó este proyecto desde el "
            "inicio."
        )

    except Exception as e:
        st.error(f"No se pudo calcular la práctica de riesgo bancario: {e}")
