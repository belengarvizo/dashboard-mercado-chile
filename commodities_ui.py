"""
Sección «Commodities» del dashboard: materias primas REALES, con su explicación al pasar el mouse.

PARA QUÉ EXISTE
    Sigue el módulo de commodities de un curso de mercado de capitales (energía, metales, agrícolas, y el cobre
    como caso chileno), con el criterio de las otras secciones nuevas: todo lo que se muestra son datos reales de
    la base y, al pasar el mouse por el nombre de una fila, aparece una explicación en palabras con los números de
    esa fila.

DE DÓNDE SALEN LOS DATOS (todos reales; ninguno es de ejemplo)
    - 9 futuros de commodities (tabla precios_acciones, bajados por scripts/actualizar_acciones.py; lista en
      constants.TICKERS_COMMODITIES): petróleo WTI, gas natural, oro, plata, cobre, maíz, trigo, soya y café. Son
      el contrato más cercano a vencer (front month) de cada uno, la referencia estándar de precio en el mundo real.
    - SPY (ETF del S&P 500) para medir beta y correlación, y la tasa de política de EEUU para el Sharpe.
    - El precio del cobre que publica el Banco Central de Chile (tabla series_macro), para comparar dos fuentes
      independientes del mismo commodity.
    - SIN DATOS: la curva completa de vencimientos de cada futuro (Yahoo solo entrega el contrato más cercano), así
      que no se puede calcular contango ni backwardation; costos de almacenamiento y de transporte.

DECISIONES DE DISEÑO
    - Se usan FUTUROS y no ETFs (como USO o UNG): un ETF de materias primas pierde valor cada mes al "rolar" el
      contrato (roll decay), lo que distorsiona su retorno de largo plazo frente al precio real del commodity.
    - El motor es el mismo de Renta Variable (renta_variable.resumen_de_etf): no hay nada específico de acciones en
      esas fórmulas, son solo precio, volatilidad, beta y correlación contra un instrumento de mercado. Igual que
      ahí, se mide contra SPY y no contra el índice ^GSPC.
    - Los ayudantes de formato, gráficos y series son los de renta_fija_ui: son los mismos y ya están probados.
    - Los controles son solo de vista (qué commodities graficar, qué período): no hay campos para inventar valores.
    - Selector de pasos con st.segmented_control (no st.tabs), estado bajo claves que empiezan con cm_.
    - Sin signo «$» en los textos: Streamlit lo toma como fórmula matemática.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import glosario_commodities as gl
import renta_fija_ui as rfui
import renta_variable as rv
from catalogo_commodities import COMMODITIES, GRUPOS_EN_ORDEN, nombre_de, tickers_del_grupo
from tabla_tooltips import tabla_con_tooltips

PASOS = ["1. El mercado", "2. Chile y el cobre"]

TICKER_MERCADO = "SPY"
NOMBRE_COBRE_BCCH = "Precio del cobre (USD/lb)"
TICKER_COBRE_COMEX = "HG=F"

VENTANAS_COBRE = {"1 año": 365, "5 años": 5 * 365, "Todo el historial": None}
# A partir de esta diferencia (%) entre las dos fuentes de cobre, la pantalla avisa que el día fue inusual.
UMBRAL_DIVERGENCIA_COBRE_INUSUAL = 15.0
# Ventana real del único episodio que la pantalla explica con una causa (el arancel de EEUU al cobre importado,
# anunciado el 8-7-2025): si el máximo del período elegido NO cae acá, no se afirma esa causa para otra fecha.
VENTANA_ARANCEL_COBRE_2025 = (pd.Timestamp("2025-06-01"), pd.Timestamp("2025-08-31"))

COLUMNAS_TABLA = [
    "1D %", "1W %", "1M %", "YTD %", "Retorno 1 año (%)", "Volatilidad (%)", "Caída máxima 1 año (%)",
    "Beta vs S&P 500", "Correlación vs S&P 500", "Sharpe",
]
ENCABEZADOS = {
    "Retorno 1 año (%)": "1A %", "Volatilidad (%)": "Vol. %", "Caída máxima 1 año (%)": "Caída máx. %",
    "Beta vs S&P 500": "Beta", "Correlación vs S&P 500": "Correl.",
}
COLUMNAS_DE_VARIACION = ["1D %", "1W %", "1M %", "YTD %"]
COLUMNAS_SECUENCIALES = ["Vol. %", "Beta", "Correl.", "Sharpe"]


# ---------------------------------------------------------------------------
# Tabla de un grupo (el equivalente al heatmap de las otras secciones)
# ---------------------------------------------------------------------------
def _resumen_del_grupo(precios: pd.DataFrame, tickers: list[str], tasa_libre: float | None, hoy: pd.Timestamp) -> pd.DataFrame | None:
    mercado = precios[TICKER_MERCADO] if TICKER_MERCADO in precios else pd.Series(dtype=float)
    filas = {}
    for ticker in tickers:
        if ticker not in precios:
            continue
        r = rv.resumen_de_etf(precios[ticker], mercado, tasa_libre)
        if r is None:
            continue
        atraso = int(np.busday_count(r["ultima_fecha"].date(), hoy.date()))
        r["_atrasado_bool"] = atraso > rfui.DIAS_HABILES_DE_ATRASO
        filas[ticker] = r
    if not filas:
        return None
    tabla = pd.DataFrame.from_dict(filas, orient="index")
    numericas = [c for c in COLUMNAS_TABLA]
    tabla[numericas] = tabla[numericas].apply(pd.to_numeric, errors="coerce")
    return tabla


def _tabla_html(resumen: pd.DataFrame, tasa_libre: float | None) -> str:
    def _valor(fila, columna):
        return None if pd.isna(fila[columna]) else float(fila[columna])

    def tooltip(ticker: str, fila: pd.Series) -> str:
        completa = resumen.loc[ticker]
        return "<hr>".join([
            gl.explicacion_instrumento(ticker),
            gl.explicacion_retorno(_valor(completa, "1M %"), _valor(completa, "YTD %")),
            gl.explicacion_volatilidad(_valor(completa, "Volatilidad (%)")),
            gl.explicacion_caida_maxima(_valor(completa, "Caída máxima 1 año (%)")),
            gl.explicacion_beta(_valor(completa, "Beta vs S&P 500")),
            gl.explicacion_correlacion(_valor(completa, "Correlación vs S&P 500")),
            gl.explicacion_sharpe(_valor(completa, "Sharpe"), tasa_libre),
        ])

    formatos = {c: "{:+.2f}%" for c in COLUMNAS_DE_VARIACION}
    formatos.update({
        "1A %": "{:+.2f}%", "Vol. %": "{:.2f}%", "Caída máx. %": "{:.2f}%", "Beta": "{:.2f}", "Correl.": "{:.2f}", "Sharpe": "{:.2f}",
    })
    vista = resumen[COLUMNAS_TABLA + ["_atrasado_bool"]].rename(columns=ENCABEZADOS)
    return tabla_con_tooltips(vista, COLUMNAS_DE_VARIACION, COLUMNAS_SECUENCIALES, formatos, tooltip, "Ticker")


def _mostrar_grupo(precios: pd.DataFrame, grupo: str, tasa_libre: float | None) -> pd.DataFrame | None:
    st.subheader(grupo)
    resumen = _resumen_del_grupo(precios, tickers_del_grupo(grupo), tasa_libre, pd.Timestamp.now().normalize())
    if resumen is None:
        rfui._sin_datos(f"los commodities de {grupo.lower()}")
        return None
    st.markdown(_tabla_html(resumen, tasa_libre), unsafe_allow_html=True)
    st.caption(f"Datos al {rfui._fecha(resumen['ultima_fecha'].max())}.")
    return resumen


def _tramo_para_grafico(precios: pd.DataFrame, elegidos: list[str], dias: int | None) -> pd.DataFrame:
    """Precios de SOLO los commodities elegidos, en el período pedido, con los huecos de un día rellenados.

    Función pura a propósito: solo debe mirar las columnas de `elegidos`. Si se filtrara por una lista más amplia
    (por ejemplo, todos los disponibles), un commodity no elegido con un día sin dato distinto al de los elegidos
    cambiaría qué fechas sobreviven al dropna y, con eso, el relleno hacia adelante de los que sí se grafican."""
    return rfui._recortar_ventana(precios[elegidos].dropna(how="all"), dias).ffill().dropna()


# ---------------------------------------------------------------------------
# Paso 1: el mercado
# ---------------------------------------------------------------------------
def _paso_mercado(precios: pd.DataFrame, tasa_libre: float | None) -> None:
    st.markdown(
        "Un **commodity** es una materia prima estandarizada: un barril de petróleo WTI o una onza de oro son iguales "
        "sin importar quién los produce. Se transan sobre todo con **futuros**: contratos para comprar o vender una "
        "cantidad fija en una fecha futura, a un precio que se fija hoy. El precio de abajo es el del contrato más "
        "cercano a vencer, que es la referencia que usa todo el mercado."
    )
    resumenes = {}
    for grupo in GRUPOS_EN_ORDEN:
        r = _mostrar_grupo(precios, grupo, tasa_libre)
        if r is not None:
            resumenes[grupo] = r
    if resumenes:
        st.caption(
            "Los precios vienen del contrato de futuro más cercano a vencer; no incluyen dividendos (no los hay) ni el costo de "
            "rolar el contrato mes a mes. **Volatilidad, caída máxima, beta, correlación y Sharpe** usan el último año de retornos "
            "diarios. **Beta** y **Correlación** se miden contra SPY, el ETF del S&P 500. **Sharpe** = (retorno del año − tasa de "
            "política de EEUU) / volatilidad. Pasa el mouse sobre el ticker de cada fila para ver una explicación en simple de cada "
            "indicador, con los números de esa fila."
        )

    st.subheader("Comparar en el tiempo")
    disponibles = [t for t in COMMODITIES if t in precios]
    elegidos = st.multiselect(
        "Elige commodities a comparar", disponibles, default=[t for t in ("CL=F", "GC=F", "HG=F", "NG=F") if t in disponibles],
        key="cm_commodities_grafico", format_func=lambda t: f"{t} · {nombre_de(t)}",
    )
    ventana = st.radio("Período", list(rfui.VENTANAS_ETF), horizontal=True, index=1, key="cm_ventana_grafico")
    if not elegidos:
        st.info("Elige al menos un commodity para ver el gráfico.")
        return
    tramo = _tramo_para_grafico(precios, elegidos, rfui.VENTANAS_ETF[ventana])
    fig = rfui._figura(380)
    for ticker in elegidos:
        fig.add_trace(go.Scatter(x=tramo.index, y=tramo[ticker] / tramo[ticker].iloc[0] * 100, mode="lines", name=ticker))
    fig.update_layout(yaxis_title="Precio, base 100")
    rfui._grafico(fig)
    st.caption(
        "Base 100: compara el movimiento relativo de commodities que se cotizan en unidades distintas (dólares por "
        "barril, por onza, centavos por bushel). No compara sus niveles de precio."
    )


def _mensaje_de_divergencia(diferencias: pd.Series) -> str | None:
    """Texto del aviso cuando el máximo del período se separa de lo normal, o None si no corresponde avisar.

    Función pura (sin Streamlit) a propósito: la condición de fecha es lo único que impide atribuirle al cobre de
    cualquier día una causa que solo es cierta para julio de 2025, y eso se puede probar sin levantar la pantalla."""
    maximo = diferencias.abs().max()
    if pd.isna(maximo) or maximo <= UMBRAL_DIVERGENCIA_COBRE_INUSUAL:
        return None
    fecha_del_maximo = diferencias.abs().idxmax()
    if VENTANA_ARANCEL_COBRE_2025[0] <= fecha_del_maximo <= VENTANA_ARANCEL_COBRE_2025[1]:
        return (
            f"**El {rfui._fecha(fecha_del_maximo)} las dos fuentes se separaron mucho más de lo normal.** No es un error de datos: "
            "en julio de 2025 EEUU anunció un arancel a las importaciones de cobre, y el precio en COMEX (el mercado de EEUU) subió "
            "muy por sobre el precio de referencia global, porque reflejaba el costo de traer cobre hacia dentro de EEUU con el "
            "arancel incluido. Episodios así muestran que «el precio del cobre» no es un único número: depende de en qué mercado "
            "se mida."
        )
    return (
        f"**El {rfui._fecha(fecha_del_maximo)} las dos fuentes se separaron mucho más de lo normal**, sin una causa identificada "
        "en los datos de esta sección."
    )


# ---------------------------------------------------------------------------
# Paso 2: Chile y el cobre
# ---------------------------------------------------------------------------
def _paso_cobre(macro: pd.DataFrame, precios: pd.DataFrame) -> None:
    st.markdown(
        "El cobre es cerca de la mitad de las exportaciones de Chile. El dashboard tiene **dos fuentes independientes** de su "
        "precio: la que publica el **Banco Central de Chile** cada día, y el futuro que cotiza en la bolsa **COMEX** de EEUU "
        "(HG=F). Las dos están en la misma unidad, dólares por libra, así que se pueden comparar directamente."
    )
    bcch = rfui._serie(macro, NOMBRE_COBRE_BCCH).dropna()
    comex = precios[TICKER_COBRE_COMEX].dropna() if TICKER_COBRE_COMEX in precios else pd.Series(dtype=float)
    if bcch.empty or comex.empty:
        rfui._sin_datos("el cobre del Banco Central o del futuro COMEX")
        return

    conjunto = pd.concat([bcch, comex], axis=1, join="inner", keys=["bcch", "comex"]).dropna()
    if conjunto.empty:
        rfui._sin_datos("fechas en común entre las dos fuentes de cobre")
        return
    ultima = conjunto.index[-1]
    diferencia = (conjunto["comex"].loc[ultima] / conjunto["bcch"].loc[ultima] - 1) * 100

    c1, c2, c3 = st.columns(3)
    c1.metric("Cobre, Banco Central de Chile", f"{rfui._fmt(conjunto['bcch'].loc[ultima], 2)} USD/lb")
    c1.caption(f"Al {rfui._fecha(ultima)}")
    c2.metric("Cobre, futuro COMEX (HG=F)", f"{rfui._fmt(conjunto['comex'].loc[ultima], 2)} USD/lb")
    c2.caption(f"Al {rfui._fecha(ultima)}")
    c3.metric("Diferencia entre las dos fuentes", f"{diferencia:+.2f}%")
    c3.caption("COMEX menos Banco Central, sobre el mismo día")

    ventana = st.radio("Período", list(VENTANAS_COBRE), horizontal=True, index=1, key="cm_ventana_cobre")
    tramo = rfui._recortar_ventana(conjunto, VENTANAS_COBRE[ventana])
    fig = rfui._figura(380)
    fig.add_trace(go.Scatter(x=tramo.index, y=tramo["bcch"], mode="lines", name="Banco Central de Chile", line=dict(color=rfui.AZUL)))
    fig.add_trace(go.Scatter(x=tramo.index, y=tramo["comex"], mode="lines", name="Futuro COMEX (HG=F)", line=dict(color=rfui.ROJO)))
    fig.update_layout(yaxis_title="USD por libra")
    rfui._grafico(fig)

    diferencias = (tramo["comex"] / tramo["bcch"] - 1) * 100
    st.caption(
        f"En el período elegido, la diferencia entre las dos fuentes promedió {diferencias.mean():+.2f}% y llegó a un máximo de "
        f"{diferencias.abs().max():.2f}%, el {rfui._fecha(diferencias.abs().idxmax())}. Lo normal es una diferencia pequeña y estable: "
        "miden el mismo metal, pero el Banco Central usa su propio procedimiento de referencia y el futuro COMEX refleja el precio "
        "exacto de ese contrato en la bolsa de EEUU."
    )
    mensaje = _mensaje_de_divergencia(diferencias)
    if mensaje:
        st.markdown(mensaje)
    st.info(
        "**Lo que esta sección no tiene:** la curva completa de vencimientos del cobre (Yahoo solo entrega el contrato más "
        "cercano), así que no se puede calcular si el mercado está en *contango* o en *backwardation*. Tampoco hay costos de "
        "almacenamiento ni de transporte."
    )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def render_commodities(df_macro: pd.DataFrame, df_precios: pd.DataFrame) -> None:
    st.header("Commodities: energía, metales y agrícolas")
    st.info(
        "Todos los datos de esta sección son **reales**: futuros de commodities (Yahoo Finance) y el precio del cobre que publica "
        "el Banco Central de Chile. Donde la base no tiene un dato, la pantalla lo dice."
    )
    macro = df_macro[df_macro["nombre"].isin({NOMBRE_COBRE_BCCH, rfui.NOMBRE_TPM_EEUU})]
    precios = rfui._precios_en_columnas(df_precios)
    tasa = rfui._ultimo(macro, rfui.NOMBRE_TPM_EEUU)
    tasa_libre = tasa[0] if tasa else None
    paso = st.segmented_control("Paso", PASOS, default=PASOS[0], key="cm_paso", label_visibility="collapsed") or PASOS[0]

    if precios.empty:
        rfui._sin_datos("los commodities")
    elif paso == PASOS[0]:
        _paso_mercado(precios, tasa_libre)
    else:
        _paso_cobre(macro, precios)
