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

# Event study TPM → tipo de cambio: ventana de estimación y ventana de evento (en días hábiles).
DIAS_ESTIMACION_EVENT_STUDY = 30
DIAS_EVENTO_EVENT_STUDY = range(-2, 3)  # -2, -1, 0, +1, +2

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

tab_premercado, tab_macro, tab_acciones, tab_magnificas, tab_benchmark, tab_event_study = st.tabs(
    ["Brief Premercado", "Indicadores macro", "Acciones IPSA", "7 Magníficas", "Benchmark", "Event Study TPM"]
)

# --- Tab 0: Brief Premercado ---
with tab_premercado:
    st.caption(
        "Para revisar antes de que abra la Bolsa de Santiago — pensado para leerse "
        "rápido, no para analizar en vivo."
    )

    st.subheader("Importante")

    # (etiqueta, tipo de tabla, nombre/ticker, unidad a mostrar)
    INDICADORES_PREMERCADO = [
        ("S&P 500", "accion", "^GSPC", ""),
        ("Cobre", "macro", "Precio del cobre (USD/oz troy)", "US$"),
        ("MSCI EM (EEM)", "accion", "EEM", "US$"),
        ("Bovespa", "accion", "^BVSP", ""),
        ("Bono UST 10 años", "macro", "Bono del Tesoro de EEUU a 10 años (UST10Y)", "%"),
    ]

    try:
        df_macro = cargar_series_macro()
        df_acciones = cargar_precios_acciones()

        columnas = st.columns(len(INDICADORES_PREMERCADO))
        for col, (etiqueta, tipo, clave, unidad) in zip(columnas, INDICADORES_PREMERCADO):
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

            resultado = calcular_cambio_reciente(serie)
            with col:
                if resultado:
                    valor, cambio_pct, fecha = resultado
                    valor_texto = f"{valor:,.2f}" + (f" {unidad}" if unidad else "")
                    st.metric(etiqueta, valor_texto, f"{cambio_pct:+.2f}%")
                    st.caption(f"al {pd.Timestamp(fecha).strftime('%d-%m-%Y')}")
                else:
                    st.metric(etiqueta, "—")
                    st.caption("sin datos suficientes")

    except Exception as e:
        st.error(f"No se pudo cargar el resumen internacional: {e}")

    st.divider()
    st.subheader("Titulares relevantes")

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
        "**Nota metodológica.** Esta sección muestra el contexto internacional y los "
        "titulares recientes lado a lado con el movimiento de mercado, como insumos "
        "para leer antes de la apertura — no afirma causalidad específica entre una "
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

        st.info(
            "**Nota metodológica.** Los eventos se detectan automáticamente como "
            "cambios en la serie diaria de la TPM respecto al día hábil anterior — "
            "esto captura únicamente las reuniones de política monetaria (RPM) en "
            "las que la tasa efectivamente cambió. No tenemos el calendario de "
            "reuniones RPM, así que las decisiones de \"mantener\" la tasa no "
            "quedan registradas como eventos y no forman parte de este análisis. "
            "El retorno normal esperado se estima como el retorno diario promedio "
            "del tipo de cambio en los 30 días hábiles previos a cada evento; el "
            "retorno anormal (AR) es la diferencia entre el retorno real y ese "
            "retorno normal, en la ventana de evento (-2 a +2 días hábiles). El "
            "t-test es una aproximación simple (normal estándar) que no corrige "
            "por autocorrelación ni por eventos superpuestos."
        )

    except Exception as e:
        st.error(f"No se pudo calcular el event study: {e}")
