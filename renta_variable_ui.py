"""
Sección «Renta Variable y ETFs» del dashboard: ETFs de acciones REALES, con su explicación al pasar el mouse.

PARA QUÉ EXISTE
    Sigue el módulo de renta variable de un curso de mercado de capitales (qué es una acción y un ETF,
    mercados y sectores, países, riesgo y diversificación, réplica de un índice), con el criterio de las
    secciones de acciones y de Renta Fija: todo lo que se muestra son datos reales de la base y, al pasar
    el mouse por el ticker de un ETF, aparece una explicación en palabras con los números de esa fila.

DE DÓNDE SALEN LOS DATOS (todos reales; ninguno es de ejemplo)
    - ETFs de acciones de EEUU y del mundo (tabla precios_acciones, bajados por
      scripts/actualizar_acciones.py; lista en constants.TICKERS_ETFS_ACCIONES). Los precios vienen
      ajustados por distribuciones, así que los retornos incluyen los dividendos que el fondo repartió.
    - Los índices ^GSPC (S&P 500) y ^DJI (Dow Jones), que son de precio puro (sin dividendos), y los ETFs de
      bonos de la sección Renta Fija, para comparar acciones con bonos.
    - La tasa de política de EEUU (tabla series_macro) como tasa libre de riesgo del Sharpe.
    - SIN DATOS: la composición de cada fondo, su valor liquidativo (y por lo tanto si cotiza con prima o
      descuento) y los dividendos por separado. Esas partes se explican y la pantalla dice que no hay datos.

DECISIONES DE DISEÑO
    - La matemática vive en renta_variable.py (sin Streamlit, con sus pruebas); la tabla con tooltips en
      tabla_tooltips.py; las explicaciones en glosario_renta_variable.py; los datos de cada ETF en
      catalogo_etfs_acciones.py. Acá solo se arma la pantalla.
    - Los ayudantes de formato, gráficos y series (_figura, _grafico, _ultimo, ...) son los de renta_fija_ui:
      son los mismos y ya están probados con datos reales.
    - Beta, correlación y retorno relativo se miden contra SPY (el ETF del S&P 500) y no contra el índice
      ^GSPC: así los dos lados incluyen dividendos y cotizan en el mismo horario.
    - Los controles son solo de vista (qué ETFs graficar, qué período): no hay campos para inventar valores.
    - Selector de pasos con st.segmented_control (no st.tabs), estado bajo claves que empiezan con rv_.
    - Sin signo «$» en los textos: Streamlit lo toma como fórmula matemática.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import glosario_renta_variable as gl
import renta_fija as rf
import renta_fija_ui as rfui
import renta_variable as rv
from catalogo_etfs_acciones import ETFS_ACCIONES, MERCADOS_EEUU, PAISES_Y_REGIONES, SECTORES_EEUU, nombre_de
from catalogo_renta_fija import ETFS_RENTA_FIJA
from tabla_tooltips import tabla_con_tooltips

PASOS = [
    "1. El mercado de EEUU",
    "2. Países y regiones",
    "3. Riesgo y diversificación",
    "4. ¿Replica al índice?",
]

TICKER_MERCADO = "SPY"  # el ETF del S&P 500, contra el que se miden beta, correlación y retorno relativo

# (ETF, índice que replica, nombre del índice). Solo pares donde el índice de la base ES el que replica el ETF:
# QQQ replica el Nasdaq-100 y la base tiene el Nasdaq Composite (^IXIC), que es otro índice.
PARES_ETF_INDICE = [("SPY", "^GSPC", "S&P 500"), ("DIA", "^DJI", "Dow Jones")]

VENTANAS_CORRELACION = {"1 año": 365, "3 años": 3 * 365}
CORRELACION_POR_DEFECTO = ["SPY", "XLK", "XLU", "XLE", "EFA", "EEM", "ECH", "IEF", "TLT", "HYG"]

COLUMNAS_TABLA = [
    "Grupo", "1D %", "1W %", "1M %", "YTD %", "Retorno 1 año (%)", "Volatilidad (%)", "Caída máxima 1 año (%)",
    "Beta vs S&P 500", "Correlación vs S&P 500", "Sharpe", "Vs S&P 500 (pp)",
]
# Encabezados cortos para que la tabla quepa en pantalla (los nombres largos viven en el tooltip y en la leyenda de abajo).
ENCABEZADOS = {
    "Retorno 1 año (%)": "1A %", "Volatilidad (%)": "Vol. %", "Caída máxima 1 año (%)": "Caída máx. %",
    "Beta vs S&P 500": "Beta", "Correlación vs S&P 500": "Correl.", "Vs S&P 500 (pp)": "vs S&P (pp)",
}
COLUMNAS_DE_VARIACION = ["1D %", "1W %", "1M %", "YTD %", "vs S&P (pp)"]
COLUMNAS_SECUENCIALES = ["Vol. %", "Beta", "Correl.", "Sharpe"]

# Qué grupos dibuja el gráfico de riesgo y retorno. Los bonos son muy parecidos entre sí y, junto a 21 acciones,
# sus etiquetas se amontonan: cada vista deja el gráfico legible.
VISTAS_RIESGO_RETORNO = {
    "Acciones y bonos": ("Mercados de EEUU", "Sectores de EEUU", "Países y regiones", "Bonos"),
    "Solo acciones": ("Mercados de EEUU", "Sectores de EEUU", "Países y regiones"),
    "Solo bonos": ("Bonos",),
}

COLORES_DE_GRUPO = {"Mercados de EEUU": "#2a78d6", "Sectores de EEUU": "#0ca30c", "Países y regiones": "#d68a2a", "Bonos": "#8a8f98"}


# ---------------------------------------------------------------------------
# Tablas de ETFs (el equivalente al heatmap de las acciones)
# ---------------------------------------------------------------------------
def _resumen_de_etfs(precios: pd.DataFrame, tickers: list[str], tasa_libre: float | None, hoy: pd.Timestamp) -> pd.DataFrame | None:
    """Una fila por ETF con todas las métricas (ver renta_variable.resumen_de_etf), o None si no hay datos."""
    mercado = precios[TICKER_MERCADO] if TICKER_MERCADO in precios else pd.Series(dtype=float)
    filas = {}
    for ticker in tickers:
        if ticker not in precios:
            continue
        r = rv.resumen_de_etf(precios[ticker], mercado, tasa_libre)
        if r is None:
            continue
        atraso = int(np.busday_count(r["ultima_fecha"].date(), hoy.date()))
        r.update({"Grupo": ETFS_ACCIONES[ticker]["grupo"], "_atrasado_bool": atraso > rfui.DIAS_HABILES_DE_ATRASO})
        filas[ticker] = r
    if not filas:
        return None
    tabla = pd.DataFrame.from_dict(filas, orient="index")
    # Una columna con algún None queda de tipo «object»: se fuerza a número para que los colores y los máximos funcionen.
    numericas = [c for c in COLUMNAS_TABLA if c != "Grupo"]
    tabla[numericas] = tabla[numericas].apply(pd.to_numeric, errors="coerce")
    return tabla


def _tabla_de_etfs_html(resumen: pd.DataFrame, tasa_libre: float | None, titulo_grupo: str) -> str:
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
            gl.explicacion_relativo(_valor(completa, "Vs S&P 500 (pp)"), _valor(completa, "Retorno 1 año (%)")),
            gl.explicacion_sharpe(_valor(completa, "Sharpe"), tasa_libre),
        ])

    formatos = {c: "{:+.2f}%" for c in COLUMNAS_DE_VARIACION if c != "vs S&P (pp)"}
    formatos.update({
        "1A %": "{:+.2f}%", "Vol. %": "{:.2f}%", "Caída máx. %": "{:.2f}%",
        "Beta": "{:.2f}", "Correl.": "{:.2f}", "Sharpe": "{:.2f}", "vs S&P (pp)": "{:+.2f}",
    })
    vista = resumen[COLUMNAS_TABLA + ["_atrasado_bool"]].rename(columns={**ENCABEZADOS, "Grupo": titulo_grupo})
    return tabla_con_tooltips(vista, COLUMNAS_DE_VARIACION, COLUMNAS_SECUENCIALES, formatos, tooltip, "ETF")


def _mostrar_tabla(precios: pd.DataFrame, tickers: list[str], titulo_grupo: str, tasa_libre: float | None) -> pd.DataFrame | None:
    """Dibuja una tabla de ETFs y devuelve su resumen (o avisa que no hay datos y devuelve None)."""
    resumen = _resumen_de_etfs(precios, tickers, tasa_libre, pd.Timestamp.now().normalize())
    if resumen is None:
        rfui._sin_datos("estos ETFs")
        return None
    st.markdown(_tabla_de_etfs_html(resumen, tasa_libre, titulo_grupo), unsafe_allow_html=True)
    return resumen


def _leyenda_de_la_tabla(resumen: pd.DataFrame) -> None:
    st.caption(
        f"Datos al {rfui._fecha(resumen['ultima_fecha'].max())}. **1A** = retorno del último año · **Vol.** = volatilidad · "
        "**Caída máx.** = peor caída del último año · **Beta** y **Correl.** = contra el S&P 500 · "
        "**vs S&P (pp)** = retorno de 1 año menos el del S&P 500, en puntos porcentuales."
    )


def _mejor_y_peor(resumen: pd.DataFrame, columna: str, etiqueta: str) -> str | None:
    datos = resumen[columna].dropna()
    if len(datos) < 2:
        return None
    return (
        f"{etiqueta}: el mejor fue **{datos.idxmax()}** ({datos.max():+.1f}%) y el peor **{datos.idxmin()}** ({datos.min():+.1f}%)."
    )


def _grafico_de_comparacion(precios: pd.DataFrame, candidatos: list[str], por_defecto: list[str], clave: str) -> None:
    """Gráfico de líneas en base 100 con selector de ETFs y de período (solo controles de vista)."""
    disponibles = [t for t in candidatos if t in precios]
    elegidos = st.multiselect(
        "Elige ETFs a comparar", disponibles, default=[t for t in por_defecto if t in disponibles],
        key=f"rv_etfs_{clave}", format_func=lambda t: f"{t} · {nombre_de(t)}",
    )
    ventana = st.radio("Período", list(rfui.VENTANAS_ETF), horizontal=True, index=1, key=f"rv_ventana_{clave}")
    if not elegidos:
        st.info("Elige al menos un ETF para ver el gráfico.")
        return
    tramo = rfui._recortar_ventana(precios[elegidos].dropna(how="all"), rfui.VENTANAS_ETF[ventana]).ffill().dropna()
    fig = rfui._figura(380)
    for ticker in elegidos:
        fig.add_trace(go.Scatter(x=tramo.index, y=tramo[ticker] / tramo[ticker].iloc[0] * 100, mode="lines", name=ticker))
    fig.update_layout(yaxis_title="Retorno total en dólares, base 100")
    rfui._grafico(fig)


# ---------------------------------------------------------------------------
# Paso 1: el mercado de EEUU
# ---------------------------------------------------------------------------
def _paso_mercado(precios: pd.DataFrame, tasa_libre: float | None) -> None:
    st.markdown(
        "Una **acción** es una parte de la propiedad de una empresa: quien la tiene gana si la empresa vale más "
        "(el precio sube) y cobra una parte de las utilidades si la empresa reparte **dividendos**. Por eso se llama "
        "*renta variable*: no hay pagos definidos de antemano, y el riesgo es mayor que el de un bono."
    )
    st.markdown(
        "Un **ETF** es un fondo que cotiza en bolsa como una acción y que compra una canasta de ellas, normalmente para "
        "replicar un **índice**. Con una sola compra se tiene el mercado completo, un sector o un país. Su precio se "
        "mantiene cerca del valor de lo que contiene porque entidades autorizadas pueden crear y rescatar cuotas del "
        "fondo a cambio de las acciones que lo componen."
    )

    st.subheader("Los cuatro mercados de EEUU (datos reales)")
    resumen_mercados = _mostrar_tabla(precios, MERCADOS_EEUU, "Índice", tasa_libre)
    if resumen_mercados is not None:
        _leyenda_de_la_tabla(resumen_mercados)
        st.caption(
            "Un ETF de acciones es una canasta de acciones que se compra como una sola. Los precios vienen **ajustados por "
            "distribuciones**, así que 1D / 1W / 1M / YTD son retornos totales: incluyen los dividendos que el fondo repartió. "
            "**Volatilidad, caída máxima, Sharpe, beta y correlación** usan el último año de retornos diarios. **Sharpe** = "
            "(retorno del año − tasa de política de EEUU) / volatilidad. **Beta** y **correlación** se miden contra SPY, el ETF "
            "del S&P 500 (por eso SPY tiene beta 1 y correlación 1). Pasa el mouse sobre el ticker de cada ETF para ver una "
            "explicación en simple de cada indicador, con los números de esa fila."
        )

    st.subheader("Los sectores del S&P 500: ¿quién lidera y quién arrastra?")
    st.markdown(
        "El S&P 500 se divide en 11 **sectores**. La clasificación de Morningstar los agrupa en **cíclicos** (dependen de "
        "cómo le vaya a la economía: consumo discrecional, financieras, materiales, inmobiliario), **sensibles** (tecnología, "
        "comunicaciones, industriales, energía) y **defensivos** (salud, consumo básico, servicios básicos: la gente los "
        "usa aunque la economía se enfríe). Un defensivo suele tener beta menor a 1; pero cae igual cuando todo cae."
    )
    resumen_sectores = _mostrar_tabla(precios, SECTORES_EEUU, "Tipo", tasa_libre)
    if resumen_sectores is not None:
        _leyenda_de_la_tabla(resumen_sectores)
        for columna, etiqueta in (("1M %", "En el último mes"), ("Retorno 1 año (%)", "En el último año")):
            frase = _mejor_y_peor(resumen_sectores, columna, etiqueta)
            if frase:
                st.markdown(frase)

    if resumen_mercados is not None or resumen_sectores is not None:
        st.subheader("Comparar en el tiempo")
        _grafico_de_comparacion(precios, MERCADOS_EEUU + SECTORES_EEUU, ["SPY", "XLK", "XLU", "XLE"], "mercado")


# ---------------------------------------------------------------------------
# Paso 2: países y regiones
# ---------------------------------------------------------------------------
def _paso_paises(precios: pd.DataFrame, tasa_libre: float | None) -> None:
    st.markdown(
        "Para invertir en otro país no hace falta abrir cuenta allá: hay ETFs que cotizan en EEUU y compran las acciones de "
        "una bolsa extranjera. Los de abajo cotizan **en dólares**, así que su retorno suma dos cosas: lo que hicieron las "
        "acciones de ese país en su moneda y lo que hizo esa moneda contra el dólar. La base no separa las dos partes."
    )
    st.subheader("ETFs de países y regiones (datos reales)")
    resumen = _mostrar_tabla(precios, PAISES_Y_REGIONES, "Mercado", tasa_libre)
    if resumen is None:
        return
    _leyenda_de_la_tabla(resumen)
    st.caption(
        "**Mercado** es la clasificación de MSCI: desarrollado o emergente. Como estos ETFs cotizan en la bolsa de EEUU, sus "
        "retornos diarios se miden en el mismo horario que los del S&P 500, y por eso el beta y la correlación no se "
        "distorsionan por la diferencia de horario que tendría la bolsa de Tokio o de Santiago. Pasa el mouse sobre cada "
        "ticker para ver la explicación con sus números."
    )
    frase = _mejor_y_peor(resumen, "Retorno 1 año (%)", "En el último año")
    if frase:
        st.markdown(frase)
    if "ECH" in resumen.index:
        chile = resumen.loc["ECH"]
        st.markdown(
            f"**Chile (ECH)**, el ETF que este dashboard usa como proxy del IPSA: retorno de 1 año {chile['Retorno 1 año (%)']:+.1f}%, "
            f"beta {chile['Beta vs S&P 500']:.2f} y correlación {chile['Correlación vs S&P 500']:.2f} contra el S&P 500."
            if pd.notna(chile["Retorno 1 año (%)"]) and pd.notna(chile["Beta vs S&P 500"]) and pd.notna(chile["Correlación vs S&P 500"])
            else "**Chile (ECH)**: todavía no hay historia suficiente para medir su beta."
        )

    st.subheader("Comparar en el tiempo")
    _grafico_de_comparacion(precios, ["SPY"] + PAISES_Y_REGIONES, ["SPY", "ECH", "EEM", "EWZ"], "paises")


# ---------------------------------------------------------------------------
# Paso 3: riesgo y diversificación
# ---------------------------------------------------------------------------
def _grupo_de(ticker: str) -> str:
    if ticker in MERCADOS_EEUU:
        return "Mercados de EEUU"
    if ticker in SECTORES_EEUU:
        return "Sectores de EEUU"
    if ticker in PAISES_Y_REGIONES:
        return "Países y regiones"
    return "Bonos"


# Posiciones posibles de la etiqueta de un punto, y hacia dónde cae su centro (en unidades relativas al tamaño del
# gráfico). Plotly no evita que se pisen dos etiquetas: con los puntos vecinos mirando todos hacia arriba, se encimaban.
DESPLAZAMIENTO_DE_ETIQUETA = {
    "top center": (0.0, 0.055), "bottom center": (0.0, -0.055), "middle right": (0.055, 0.0), "middle left": (-0.055, 0.0),
    "top right": (0.045, 0.045), "top left": (-0.045, 0.045), "bottom right": (0.045, -0.045), "bottom left": (-0.045, -0.045),
}


# Cuánto se puede salir una etiqueta del rango de los puntos y seguir dentro del área del gráfico (Plotly deja un margen).
MARGEN_DEL_AREA = 0.03


def _posiciones_de_etiquetas(puntos: list[tuple], con_etiqueta: set[str] | None = None) -> dict[str, str]:
    """Posición de la etiqueta de cada punto (ticker, grupo, x, y): cada una toma el lado más despejado.

    `con_etiqueta` son los tickers que llevan etiqueta (todos si es None). Los demás no se rotulan pero siguen
    contando como obstáculos: una etiqueta no se pone encima de un punto aunque ese punto no tenga texto.

    Los puntos se llevan a una escala de 0 a 1 en cada eje. Para cada punto, en orden de izquierda a derecha, se prueba
    cada lado y se elige el que deja el centro de la etiqueta más lejos de todos los demás puntos y de las etiquetas que
    ya se colocaron; un lado que dejaría la etiqueta fuera del área del gráfico se descarta (así un punto del borde no
    pierde su etiqueta). Es un criterio simple (no garantiza que nada se pise si hay demasiados puntos juntos), pero separa
    a los vecinos: de dos puntos casi iguales, uno pone su etiqueta arriba y el otro abajo."""
    if not puntos:
        return {}
    xs, ys = [p[2] for p in puntos], [p[3] for p in puntos]
    ancho, alto = (max(xs) - min(xs)) or 1.0, (max(ys) - min(ys)) or 1.0
    ubicados = {p[0]: ((p[2] - min(xs)) / ancho, (p[3] - min(ys)) / alto) for p in puntos}
    etiquetas: list[tuple[float, float]] = []
    elegidas = {}
    for ticker, (x, y) in sorted(ubicados.items(), key=lambda par: par[1]):
        if con_etiqueta is not None and ticker not in con_etiqueta:
            continue
        obstaculos = [xy for otro, xy in ubicados.items() if otro != ticker] + etiquetas

        def despejo(lado: str) -> float:
            cx, cy = x + DESPLAZAMIENTO_DE_ETIQUETA[lado][0], y + DESPLAZAMIENTO_DE_ETIQUETA[lado][1]
            if not (-MARGEN_DEL_AREA <= cx <= 1 + MARGEN_DEL_AREA and -MARGEN_DEL_AREA <= cy <= 1 + MARGEN_DEL_AREA):
                return -1.0
            return min((((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5 for ox, oy in obstaculos), default=1.0)

        mejor = max(DESPLAZAMIENTO_DE_ETIQUETA, key=despejo)
        elegidas[ticker] = mejor
        etiquetas.append((x + DESPLAZAMIENTO_DE_ETIQUETA[mejor][0], y + DESPLAZAMIENTO_DE_ETIQUETA[mejor][1]))
    return elegidas


def _grafico_riesgo_retorno(precios: pd.DataFrame) -> None:
    """Un punto por ETF: volatilidad (eje X) contra retorno del último año (eje Y)."""
    puntos = []
    for ticker in list(ETFS_ACCIONES) + list(ETFS_RENTA_FIJA):
        if ticker not in precios:
            continue
        serie = precios[ticker].dropna()
        retorno, volatilidad = rf.retorno_ultimo_anio(serie), rf.volatilidad_anualizada(serie)
        if retorno is not None and volatilidad is not None:
            puntos.append((ticker, _grupo_de(ticker), volatilidad, retorno))
    vista = st.radio("Qué mostrar", list(VISTAS_RIESGO_RETORNO), horizontal=True, key="rv_vista_riesgo")
    puntos = [p for p in puntos if p[1] in VISTAS_RIESGO_RETORNO[vista]]
    if not puntos:
        rfui._sin_datos("riesgo y retorno de los ETFs")
        return
    # Los bonos están tan juntos que, entre las acciones, sus diez etiquetas se pisan y se tapan con los puntos vecinos:
    # en la vista combinada van sin texto (el ticker sale al pasar el mouse) y «Solo bonos» los rotula todos.
    rotulados = {p[0] for p in puntos if vista == "Solo bonos" or p[1] != "Bonos"}
    posiciones = _posiciones_de_etiquetas(puntos, rotulados)
    fig = rfui._figura(640)
    fig.update_layout(hovermode="closest")
    for grupo, color in COLORES_DE_GRUPO.items():
        del_grupo = [p for p in puntos if p[1] == grupo]
        if not del_grupo:
            continue
        fig.add_trace(go.Scatter(
            x=[p[2] for p in del_grupo], y=[p[3] for p in del_grupo], text=[p[0] for p in del_grupo],
            mode="markers+text" if del_grupo[0][0] in rotulados else "markers",
            textposition=[posiciones.get(p[0], "top center") for p in del_grupo], name=grupo,
            marker=dict(size=9, color=color), textfont=dict(size=11),
            hovertemplate="%{text}<br>Volatilidad %{x:.1f}%<br>Retorno 1 año %{y:+.1f}%<extra></extra>",
        ))
    fig.update_layout(xaxis_title="Volatilidad del último año (%)", yaxis_title="Retorno del último año (%)")
    rfui._grafico(fig)


def _grafico_correlaciones(precios: pd.DataFrame) -> None:
    candidatos = [t for t in list(ETFS_ACCIONES) + list(ETFS_RENTA_FIJA) if t in precios]
    elegidos = st.multiselect(
        "Elige ETFs (acciones y bonos)", candidatos, default=[t for t in CORRELACION_POR_DEFECTO if t in candidatos],
        key="rv_corr_etfs", format_func=lambda t: f"{t} · {nombre_de(t) if t in ETFS_ACCIONES else ETFS_RENTA_FIJA[t]['nombre']}",
    )
    ventana = st.radio("Período", list(VENTANAS_CORRELACION), horizontal=True, key="rv_ventana_corr")
    if len(elegidos) < 2:
        st.info("Elige al menos dos ETFs para ver sus correlaciones.")
        return
    matriz = rv.matriz_de_correlacion(precios[elegidos].dropna(how="all"), VENTANAS_CORRELACION[ventana])
    if matriz.empty:
        rfui._sin_datos("suficientes días en común para correlacionar esos ETFs")
        return
    fig = rfui._figura(520)
    fig.update_layout(hovermode="closest")
    fig.add_trace(go.Heatmap(
        z=matriz.values, x=list(matriz.columns), y=list(matriz.index), zmin=-1, zmax=1,
        colorscale=[[0, "#d03b3b"], [0.5, "#f5f5f2"], [1, "#2a78d6"]],
        text=np.round(matriz.values, 2), texttemplate="%{text}", colorbar=dict(title="Correlación"),
        hovertemplate="%{y} y %{x}: %{z:.2f}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed")
    rfui._grafico(fig)

    pares = matriz.where(np.triu(np.ones(matriz.shape, dtype=bool), k=1)).stack()
    if len(pares) > 0:
        (a, b), valor = pares.idxmin(), pares.min()
        st.markdown(f"De los ETFs elegidos, la pareja que menos se parece es **{a}** y **{b}**: correlación {valor:.2f}.")


def _paso_riesgo(precios: pd.DataFrame) -> None:
    st.markdown(
        "**Diversificar** es repartir el dinero en cosas que no se mueven igual: si una cae, la otra la compensa. La clave "
        "es la **correlación** entre los retornos diarios: cerca de +1 se mueven juntas (diversifican poco), cerca de 0 "
        "van por su cuenta y bajo 0 tienden a ir al revés. Abajo está lo que pasó de verdad en el último año y en los últimos tres."
    )
    st.subheader("Riesgo y retorno de cada ETF")
    st.caption(
        "Cada punto es un ETF: a la derecha se movió más (más riesgo), arriba ganó más en el último año. En general más "
        "riesgo debería pagar más retorno, pero en un año concreto no siempre pasa. Los bonos de la sección Renta Fija van en gris: están "
        "tan juntos que, junto a las acciones, no llevan etiqueta (pasa el mouse por un punto para ver cuál es); con «Solo bonos» salen todos."
    )
    _grafico_riesgo_retorno(precios)

    st.subheader("Correlaciones entre ETFs")
    st.caption(
        "Azul = se mueven juntos, rojo = se mueven al revés, blanco = independientes. Cada par se mide solo en los días en "
        "que todos los ETFs elegidos tienen dato. Una correlación medida en un período no es una promesa para el siguiente: "
        "en las crisis suele subir justo cuando más se necesitaba que fuera baja."
    )
    _grafico_correlaciones(precios)


# ---------------------------------------------------------------------------
# Paso 4: ¿replica al índice?
# ---------------------------------------------------------------------------
def _paso_indice(precios: pd.DataFrame) -> None:
    st.markdown(
        "Un ETF indexado promete **replicar un índice**. Se puede comprobar con datos: se compara el precio del ETF con "
        "el del índice. Dos números dicen cuán fiel es: la **diferencia de retorno** y el **error de seguimiento** "
        "(cuánto se separan los dos en el día a día, anualizado; mientras más bajo, más fiel)."
    )
    filas = []
    for etf, indice, nombre in PARES_ETF_INDICE:
        if etf not in precios or indice not in precios:
            continue
        comparacion = rv.comparar_con_indice(precios[etf], precios[indice])
        if comparacion is not None:
            filas.append((etf, indice, nombre, comparacion))
    if not filas:
        rfui._sin_datos("los ETFs y sus índices")
        return

    st.subheader("ETF contra su índice, último año (datos reales)")
    rfui._tabla(
        pd.DataFrame(
            [
                (
                    etf, nombre, f"{c['retorno_etf']:+.2f}%", f"{c['retorno_indice']:+.2f}%", f"{c['diferencia']:+.2f}",
                    f"{c['correlacion']:.4f}", f"{c['error_de_seguimiento']:.2f}%",
                    f"{rfui._fecha(c['desde'])} a {rfui._fecha(c['hasta'])}",
                )
                for etf, _, nombre, c in filas
            ],
            columns=["ETF", "Índice", "Retorno ETF", "Retorno índice", "Diferencia (pp)", "Correlación diaria", "Error de seguimiento", "Período"],
        ),
        numericas=["Retorno ETF", "Retorno índice", "Diferencia (pp)", "Correlación diaria", "Error de seguimiento"],
    )
    st.caption(
        "El ETF usa precios **ajustados por dividendos** y el índice (S&P 500, Dow Jones) es de **precio puro**, sin "
        "dividendos. Por eso la diferencia de retorno no es un error del fondo: en buena parte son los dividendos que las "
        "empresas pagaron, menos la comisión del fondo. La base no tiene los dividendos por separado, así que no se puede "
        "descomponer. La correlación diaria cercana a 1 y un error de seguimiento bajo muestran que lo que se compra es, "
        "en la práctica, el índice."
    )

    st.subheader("Los dos precios, en el tiempo")
    etiquetas = {f"{etf} y {nombre}": (etf, indice) for etf, indice, nombre, _ in filas}
    elegido = st.radio("Par", list(etiquetas), horizontal=True, key="rv_par_indice")
    etf, indice = etiquetas[elegido]
    conjunto = precios[[etf, indice]].dropna()
    tramo = rfui._recortar_ventana(conjunto, rf.DIAS_DEL_ANIO)
    fig = rfui._figura(380)
    for columna, nombre_serie in ((etf, f"{etf} (ETF, con dividendos)"), (indice, f"{indice} (índice, precio puro)")):
        fig.add_trace(go.Scatter(x=tramo.index, y=tramo[columna] / tramo[columna].iloc[0] * 100, mode="lines", name=nombre_serie))
    fig.update_layout(yaxis_title="Base 100 hace un año")
    rfui._grafico(fig)

    st.info(
        "Lo que la base **no** tiene: la composición de cada fondo, su valor liquidativo (y por lo tanto si el ETF cotiza "
        "con prima o descuento contra lo que contiene) y las comisiones. Por eso la pantalla mide la réplica solo con precios."
    )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def render_renta_variable(df_macro: pd.DataFrame, df_precios: pd.DataFrame) -> None:
    st.header("Renta variable y ETFs: mercados, sectores y países")
    st.info(
        "Todos los datos de esta sección son **reales**: ETFs de acciones de EEUU y del mundo (Yahoo Finance) y la tasa de "
        "política de EEUU (FRED) para el Sharpe. Donde la base no tiene un dato, la pantalla lo dice."
    )
    macro = rfui._recortar(df_macro)
    precios = rfui._precios_en_columnas(df_precios)
    tasa = rfui._ultimo(macro, rfui.NOMBRE_TPM_EEUU)
    tasa_libre = tasa[0] if tasa else None
    paso = st.segmented_control("Paso", PASOS, default=PASOS[0], key="rv_paso", label_visibility="collapsed") or PASOS[0]

    if precios.empty:
        rfui._sin_datos("los ETFs de acciones")
    elif paso == PASOS[0]:
        _paso_mercado(precios, tasa_libre)
    elif paso == PASOS[1]:
        _paso_paises(precios, tasa_libre)
    elif paso == PASOS[2]:
        _paso_riesgo(precios)
    else:
        _paso_indice(precios)
