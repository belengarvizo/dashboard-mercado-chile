"""
Dashboard principal. Lee todo desde PostgreSQL (nunca llama a las
APIs directamente) para que cargue rápido sin importar quién lo abra.

Correr localmente con: streamlit run app/dashboard.py
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from matplotlib.colors import LinearSegmentedColormap
from sqlalchemy import text
from models import get_engine
from constants import (
    TICKERS_IPSA,
    TICKERS_IPSA_PRINCIPALES,
    TICKER_PROXY_IPSA,
    TICKERS_BENCHMARK,
    TICKERS_MAGNIFICAS,
)

st.set_page_config(page_title="Mercado Chile", layout="wide")

# Paleta categórica de orden fijo (nunca se reasigna por índice de la
# selección), y diverging rojo-gris-verde para el heatmap de desempeño.
PALETA_CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
CMAP_DIVERGENTE = LinearSegmentedColormap.from_list("rojo_verde", ["#d03b3b", "#f0efec", "#0ca30c"])

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
def calcular_resumen_ipsa(df_todas: pd.DataFrame) -> pd.DataFrame:
    """% de cambio 1D/1W/1M/YTD y Beta (vs el proxy del IPSA) para cada acción del IPSA."""
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

        filas.append({
            "Ticker": ticker.replace(".SN", ""),
            "1D %": cambio_desde(1),
            "1W %": cambio_desde(7),
            "1M %": cambio_desde(30),
            "YTD %": cambio_ytd,
            "Beta": beta,
            "Última actualización": (
                ("⚠️ " if atrasado else "") + ultima_fecha_real.strftime("%Y-%m-%d")
            ),
            "Atraso": atrasado,
        })

    return pd.DataFrame(filas).set_index("Ticker")


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

tab_macro, tab_acciones, tab_magnificas, tab_benchmark = st.tabs(
    ["Indicadores macro", "Acciones IPSA", "7 Magníficas", "Benchmark"]
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

        df_resumen = calcular_resumen_ipsa(df_acciones)

        columnas_pct = ["1D %", "1W %", "1M %", "YTD %"]
        max_abs = df_resumen[columnas_pct].abs().max().max()
        max_abs = max_abs if pd.notna(max_abs) and max_abs > 0 else 1

        formato = {col: "{:+.2f}%" for col in columnas_pct}
        formato["Beta"] = "{:.2f}"

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
            .apply(marcar_datos_atrasados, axis=1)
            .format(formato, na_rep="—")
            .hide(["Atraso"], axis="columns")
        )
        st.dataframe(estilo, use_container_width=True)
        st.caption(
            "Beta calculado sobre retornos diarios del último año, respecto al ETF ECH "
            "(proxy del IPSA — el índice no tiene ticker propio en Yahoo Finance). "
            "⚠️ en \"Última actualización\" indica que Yahoo Finance no refrescó el precio "
            "de ese ticker hace más de 5 días hábiles — el % de cambio mostrado no es confiable."
        )

    except Exception as e:
        st.error(f"No se pudieron cargar los precios de acciones: {e}")

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
