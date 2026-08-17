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
import plotly.express as px
from sqlalchemy import text
from models import get_engine

st.set_page_config(page_title="Mercado Chile", layout="wide")

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


# --- Sidebar: info de última actualización ---
with st.sidebar:
    st.subheader("Última actualización")
    try:
        meta = cargar_ultima_actualizacion()
        for _, fila in meta.iterrows():
            st.text(f"{fila['fuente']}: {fila['ultima_actualizacion']}")
    except Exception:
        st.warning("Aún no hay datos cargados. Corre los scripts de actualización primero.")

tab_macro, tab_acciones = st.tabs(["Indicadores macro", "Acciones IPSA"])

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

        tickers_disponibles = df_acciones["ticker"].unique()
        tickers_elegidos = st.multiselect(
            "Elige acciones a comparar", tickers_disponibles, default=list(tickers_disponibles)[:2]
        )

        df_filtrado = df_acciones[df_acciones["ticker"].isin(tickers_elegidos)]

        fig = px.line(
            df_filtrado, x="fecha", y="precio_cierre", color="ticker",
            title="Precio de cierre histórico"
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Volumen transado")
        fig_vol = px.bar(df_filtrado, x="fecha", y="volumen", color="ticker")
        st.plotly_chart(fig_vol, use_container_width=True)

    except Exception as e:
        st.error(f"No se pudieron cargar los precios de acciones: {e}")
