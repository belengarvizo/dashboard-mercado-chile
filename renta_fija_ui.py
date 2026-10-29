"""
Sección «Renta Fija» del dashboard: instrumentos de bonos REALES, con su explicación al pasar el mouse.

PARA QUÉ EXISTE
    Sigue el módulo de renta fija de un curso de mercado de capitales y mesas de dinero
    (mercado, valorización, riesgo de mercado, riesgo de crédito, Banco Central, curva y
    estrategias, emisión internacional), pero con el criterio de las secciones de acciones:
    todo lo que se muestra son datos reales de la base del dashboard, y al pasar el mouse por
    el nombre de un instrumento aparece una explicación en palabras con los números de esa fila.

DE DÓNDE SALEN LOS DATOS (todos reales; ninguno es de ejemplo)
    - ETFs de bonos de EEUU (tabla precios_acciones, bajados por scripts/actualizar_acciones.py):
      SHY, IEI, IEF, TLT, AGG, VCSH, LQD, HYG, EMB y TIP. Los precios vienen ajustados por
      distribuciones, así que los retornos incluyen los cupones que el fondo repartió.
    - Curva del Tesoro de EEUU (1 mes a 30 años), BCP y BCU del Banco Central de Chile en varios
      plazos, spread de bonos corporativos Baa (BAA10Y), TPM de Chile y de EEUU y tasas cortas
      en pesos (tabla series_macro).
    - SIN DATOS: precios de bonos individuales, operaciones de mercado abierto del Banco Central,
      probabilidades de default y emisiones internacionales. Esas partes se explican y la pantalla
      dice que no hay datos; no se rellenan con supuestos.

DECISIONES DE DISEÑO
    - La matemática vive en renta_fija.py (sin Streamlit, con sus pruebas); la tabla con tooltips
      en tabla_tooltips.py; las explicaciones en glosario_renta_fija.py; los datos de cada ETF en
      catalogo_renta_fija.py. Acá solo se arma la pantalla.
    - Las tasas de la base están en % (4.5 = 4,5 %); el motor trabaja en decimales. La conversión
      se hace en esta pantalla, en un solo lugar por dato.
    - Mismo formato numérico que las tablas de acciones (punto decimal), para que las secciones
      se lean igual.
    - Los controles son solo de vista (qué ETFs graficar, qué período): no hay calculadoras con
      valores inventados.
    - Selector de pasos con st.segmented_control (no st.tabs), estado bajo claves que empiezan con rf_.
    - Sin signo «$» en los textos: Streamlit lo toma como fórmula matemática.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import estructura_tasas as et
import glosario_renta_fija as gl
import renta_fija as rf
from catalogo_renta_fija import ETFS_RENTA_FIJA, nombre_de
from tabla_tooltips import tabla_con_tooltips

PASOS = [
    "1. El mercado",
    "2. Valorización",
    "3. Riesgo de mercado",
    "4. Riesgo de crédito",
    "5. Banco Central y tasas",
    "6. Curva y estrategias",
    "7. Emitir un bono afuera",
]

TICKER_MERCADO = "^GSPC"  # el S&P 500, contra el que se mide el beta de cada ETF

# Nombres EXACTOS con que cada serie se guarda en series_macro (los define
# scripts/actualizar_bcch.py; una prueba comprueba que sigan siendo los mismos).
NOMBRE_UST10 = "Bono del Tesoro de EEUU a 10 años (UST10Y)"
NOMBRE_BCP2 = "Bono BCCh en pesos (BCP) a 2 años - tasa mercado secundario"
NOMBRE_BCP5 = "Bono BCCh en pesos (BCP) a 5 años - tasa mercado secundario"
NOMBRE_BCP10 = "Bono BCCh en pesos (BCP) a 10 años - tasa mercado secundario"
NOMBRE_BCU5 = "Bono BCCh en UF (BCU) a 5 años - tasa mercado secundario"
NOMBRE_BCU10 = "Bono BCCh en UF (BCU) a 10 años - tasa mercado secundario"
NOMBRE_BCU30 = "Bono BCCh en UF (BCU) a 30 años - tasa mercado secundario"
NOMBRE_BAA10Y = "Spread bonos corporativos Baa vs Treasury 10 años (BAA10Y)"
NOMBRE_TPM_CHILE = "Tasa de política monetaria (TPM)"
NOMBRE_TPM_EEUU = "Tasa de política monetaria de EEUU (Effective Federal Funds Rate)"
NOMBRE_PDBC14 = "Tasa libre de riesgo CLP (PDBC 14 días)"
NOMBRE_SWAP90 = "Swap Promedio Cámara nominal (90 días)"

CURVA_CHILE = {
    "BCP (pesos)": {2: NOMBRE_BCP2, 5: NOMBRE_BCP5, 10: NOMBRE_BCP10},
    "BCU (UF, tasa real)": {5: NOMBRE_BCU5, 10: NOMBRE_BCU10, 30: NOMBRE_BCU30},
}


def nombre_treasury(plazo: str) -> str:
    """Nombre de la serie H.15 (Treasury Constant Maturity) para un plazo como «10 años»."""
    return f"Bono del Tesoro de EEUU a {plazo} (Treasury Constant Maturity, H.15)"


SERIES_TASAS = {
    "TPM de Chile": NOMBRE_TPM_CHILE,
    "Tasa de política de EEUU (Fed funds)": NOMBRE_TPM_EEUU,
    "PDBC a 14 días (BCCh)": NOMBRE_PDBC14,
    "Swap Promedio Cámara a 90 días": NOMBRE_SWAP90,
}

NOMBRES_USADOS = {
    NOMBRE_UST10, NOMBRE_BAA10Y, *SERIES_TASAS.values(),
    *(n for grupo in CURVA_CHILE.values() for n in grupo.values()),
    *(nombre_treasury(plazo) for plazo in et.PLAZOS_ANIOS),
}

AZUL, ROJO, VERDE, GRIS = "#2a78d6", "#d03b3b", "#0ca30c", "#8a8f98"
VENTANAS = {"1 año": 365, "5 años": 5 * 365, "Todo el historial": None}
VENTANAS_ETF = {"1 año": 365, "3 años": 3 * 365, "Todo el historial": None}
PLAZOS_DE_ESTRATEGIA = (2, 3, 5, 7, 10)
HORIZONTES = {0.5: "6 meses", 1.0: "1 año"}
# Más de tantos días seguidos sin dato en una serie se considera un hueco: la línea
# del gráfico se corta ahí, en vez de unir los dos bordes con una recta que parece dato.
UMBRAL_HUECO_DIAS = 30
DIAS_HABILES_DE_ATRASO = 5

COLUMNAS_TABLA = [
    "Grupo", "1D %", "1W %", "1M %", "YTD %", "Retorno 1 año (%)", "Volatilidad (%)", "Caída máxima 1 año (%)",
    "Duración medida (años)", "R² con la tasa", "Beta vs S&P 500", "Sharpe",
]
# Encabezados cortos para que la tabla quepa en pantalla (los nombres largos viven en el tooltip y en la leyenda de abajo).
ENCABEZADOS = {
    "Retorno 1 año (%)": "1A %", "Volatilidad (%)": "Vol. %", "Caída máxima 1 año (%)": "Caída máx. %",
    "Duración medida (años)": "Duración", "R² con la tasa": "R²", "Beta vs S&P 500": "Beta",
}
COLUMNAS_DE_VARIACION = ["1D %", "1W %", "1M %", "YTD %"]
COLUMNAS_SECUENCIALES = ["Vol. %", "Duración", "R²", "Beta", "Sharpe"]


# ---------------------------------------------------------------------------
# Datos y formato
# ---------------------------------------------------------------------------
def _recortar(df_macro: pd.DataFrame) -> pd.DataFrame:
    """Solo las series que usa esta sección (la tabla completa tiene ~80.000 filas)."""
    return df_macro[df_macro["nombre"].isin(NOMBRES_USADOS)]


def _serie(macro: pd.DataFrame, nombre: str) -> pd.Series:
    """Serie de un indicador, indexada por fecha, en % (como está en la base)."""
    filas = macro[macro["nombre"] == nombre]
    return pd.Series(filas["valor"].to_numpy(dtype=float), index=pd.to_datetime(filas["fecha"])).sort_index()


def _ultimo(macro: pd.DataFrame, nombre: str):
    """(último valor, su fecha) o None si la serie no tiene datos."""
    s = _serie(macro, nombre)
    return (float(s.iloc[-1]), s.index[-1]) if len(s) else None


def _huecos(serie: pd.Series, umbral: int = UMBRAL_HUECO_DIAS) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Tramos sin datos: (último día con dato antes del hueco, primer día con dato después)."""
    dias_entre_datos = serie.index.to_series().diff().dt.days
    posiciones = np.flatnonzero((dias_entre_datos > umbral).to_numpy())
    return [(serie.index[i - 1], serie.index[i]) for i in posiciones]


def _cortar_en_huecos(serie: pd.Series) -> pd.Series:
    """La misma serie con un punto vacío (NaN) justo después de cada hueco, para que el gráfico corte la línea."""
    huecos = _huecos(serie)
    if not huecos:
        return serie
    vacios = pd.Series(np.nan, index=pd.DatetimeIndex([antes + pd.Timedelta(days=1) for antes, _ in huecos]))
    return pd.concat([serie, vacios]).sort_index()


def _pivote_curva(macro: pd.DataFrame) -> pd.DataFrame:
    """Curva del Tesoro: una fila por fecha, una columna por plazo (en años), en %."""
    columnas = []
    for etiqueta, anios in et.PLAZOS_ANIOS.items():
        s = _serie(macro, nombre_treasury(etiqueta))
        s.name = anios
        columnas.append(s)
    return pd.concat(columnas, axis=1)


def _curva_actual(macro: pd.DataFrame):
    """(pivote en decimales, fecha de la última curva completa, esa curva) o None si no hay ninguna."""
    pivote = _pivote_curva(macro) / 100.0
    try:
        fecha, curva = rf.curva_en_fecha(pivote, pivote.index.max())
    except (ValueError, TypeError):
        return None
    return pivote, fecha, curva


def _rendimiento_del_tesoro(macro: pd.DataFrame, plazo: float) -> pd.Series:
    """Rendimiento diario (en decimales) del Tesoro al plazo dado, de la curva H.15."""
    etiqueta = next(k for k, v in et.PLAZOS_ANIOS.items() if v == float(plazo))
    return _serie(macro, nombre_treasury(etiqueta)) / 100.0


def _precios_en_columnas(df_precios: pd.DataFrame) -> pd.DataFrame:
    """Una fila por fecha, una columna por ticker (precio de cierre ajustado)."""
    if df_precios is None or df_precios.empty:
        return pd.DataFrame()
    d = df_precios.assign(fecha=pd.to_datetime(df_precios["fecha"]))
    return d.pivot_table(index="fecha", columns="ticker", values="precio_cierre").sort_index()


def _fmt(valor: float, decimales: int = 2) -> str:
    """Número con el mismo formato que las tablas de acciones: coma de miles y punto decimal."""
    return f"{valor:,.{decimales}f}"


def _pct(decimal: float, decimales: int = 2) -> str:
    return f"{decimal * 100:.{decimales}f}%"


def _fecha(fecha) -> str:
    return pd.Timestamp(fecha).strftime("%d-%m-%Y")


def _sin_datos(que: str) -> None:
    st.info(f"No hay datos de {que} en la base del dashboard en este momento.")


def _figura(alto: int = 380) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        height=alto, margin=dict(t=30, b=40, l=10, r=10),
        legend=dict(orientation="h", y=-0.2), hovermode="x unified",
    )
    return fig


def _grafico(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch")


def _tabla(datos: pd.DataFrame, numericas=(), mostrar_todo: bool = False) -> None:
    """Tabla simple; las columnas numéricas (ya formateadas como texto) se alinean a la derecha.

    `mostrar_todo` ajusta el alto para ver todas las filas sin scroll interno (para tablas de hasta ~20 filas)."""
    configuracion = {c: st.column_config.TextColumn(alignment="right") for c in numericas}
    altura = min(35 * (len(datos) + 1) + 3, 760) if mostrar_todo else "auto"
    st.dataframe(datos, hide_index=True, width="stretch", column_config=configuracion, height=altura)


def _recortar_ventana(serie_o_tabla, dias: int | None):
    if dias is None or len(serie_o_tabla) == 0:
        return serie_o_tabla
    return serie_o_tabla[serie_o_tabla.index >= serie_o_tabla.index[-1] - pd.Timedelta(days=dias)]


def _etiqueta_de_etf(ticker: str) -> str:
    return f"{ticker} · {nombre_de(ticker)}"


# ---------------------------------------------------------------------------
# Tabla de ETFs de bonos (el equivalente al heatmap de las acciones)
# ---------------------------------------------------------------------------
def _resumen_de_etfs(precios: pd.DataFrame, macro: pd.DataFrame, hoy: pd.Timestamp) -> pd.DataFrame | None:
    """Una fila por ETF con todas las métricas (ver renta_fija.resumen_de_instrumento), o None si no hay datos."""
    tasa_libre = _ultimo(macro, NOMBRE_TPM_EEUU)
    mercado = precios[TICKER_MERCADO] if TICKER_MERCADO in precios else pd.Series(dtype=float)
    filas = {}
    for ticker, datos in ETFS_RENTA_FIJA.items():
        if ticker not in precios:
            continue
        r = rf.resumen_de_instrumento(
            precios[ticker], mercado, _rendimiento_del_tesoro(macro, datos["plazo_referencia"]),
            tasa_libre[0] if tasa_libre else None,
        )
        if r is None:
            continue
        atraso = int(np.busday_count(r["ultima_fecha"].date(), hoy.date()))
        r.update({
            "Grupo": datos["grupo"], "Plazo de referencia": datos["plazo_referencia"],
            "_atrasado_bool": atraso > DIAS_HABILES_DE_ATRASO,
        })
        filas[ticker] = r
    if not filas:
        return None
    tabla = pd.DataFrame.from_dict(filas, orient="index")
    # Una columna con algún None queda de tipo «object»: se fuerza a número para que los colores y los máximos funcionen.
    numericas = [c for c in COLUMNAS_TABLA if c != "Grupo"] + ["Error de la duración"]
    tabla[numericas] = tabla[numericas].apply(pd.to_numeric, errors="coerce")
    return tabla


def _tabla_de_etfs_html(resumen: pd.DataFrame, tasa_libre: float | None) -> str:
    def _valor(fila, columna):
        return None if pd.isna(fila[columna]) else float(fila[columna])

    def tooltip(ticker: str, fila: pd.Series) -> str:
        completa = resumen.loc[ticker]
        return "<hr>".join([
            gl.explicacion_instrumento(ticker),
            gl.explicacion_retorno(_valor(completa, "1M %"), _valor(completa, "YTD %")),
            gl.explicacion_duracion_medida(
                _valor(completa, "Duración medida (años)"), _valor(completa, "Error de la duración"),
                _valor(completa, "R² con la tasa"), int(completa["Plazo de referencia"]),
            ),
            gl.explicacion_volatilidad(_valor(completa, "Volatilidad (%)")),
            gl.explicacion_caida_maxima(_valor(completa, "Caída máxima 1 año (%)")),
            gl.explicacion_beta(_valor(completa, "Beta vs S&P 500")),
            gl.explicacion_sharpe(_valor(completa, "Sharpe"), tasa_libre),
        ])

    formatos = {c: "{:+.2f}%" for c in COLUMNAS_DE_VARIACION}
    formatos.update({
        "1A %": "{:+.2f}%", "Vol. %": "{:.2f}%", "Caída máx. %": "{:.2f}%",
        "Duración": "{:.2f}", "R²": "{:.2f}", "Beta": "{:.2f}", "Sharpe": "{:.2f}",
    })
    vista = resumen[COLUMNAS_TABLA + ["_atrasado_bool"]].rename(columns=ENCABEZADOS)
    return tabla_con_tooltips(vista, COLUMNAS_DE_VARIACION, COLUMNAS_SECUENCIALES, formatos, tooltip, "ETF")


# ---------------------------------------------------------------------------
# Paso 1: el mercado
# ---------------------------------------------------------------------------
def _paso_mercado(macro: pd.DataFrame, precios: pd.DataFrame) -> None:
    st.markdown(
        "Un **bono** es un préstamo que se vuelve un papel que se puede comprar y vender: quien lo emite "
        "(un gobierno, un banco, una empresa) se compromete a pagar **cupones** cada cierto tiempo y a "
        "devolver el **capital** al vencimiento. Por eso se llama *renta fija*: los pagos están definidos "
        "de antemano. Lo que **no** es fijo es su precio, que sube y baja todos los días."
    )
    st.markdown(
        "**Cómo se transa.** Gran parte del mercado funciona fuera de bolsa: las **mesas de dinero** de bancos y "
        "corredoras cotizan un precio al que compran (*bid*) y otro al que venden (*ask*), y esa diferencia es "
        "su ganancia por intermediar. El precio se cotiza en **porcentaje del valor nominal** (100 = a la par) o "
        "directamente en **tasa**, porque precio y tasa se convierten el uno en el otro."
    )

    st.subheader("ETFs de bonos: desempeño y riesgo (datos reales)")
    hoy = pd.Timestamp.now().normalize()
    resumen = _resumen_de_etfs(precios, macro, hoy) if len(precios) else None
    if resumen is None:
        _sin_datos("los ETFs de bonos")
    else:
        tasa_libre = _ultimo(macro, NOMBRE_TPM_EEUU)
        st.markdown(_tabla_de_etfs_html(resumen, tasa_libre[0] if tasa_libre else None), unsafe_allow_html=True)
        st.caption(
            f"Datos al {_fecha(resumen['ultima_fecha'].max())}. **1A** = retorno del último año · **Vol.** = volatilidad · "
            "**Caída máx.** = peor caída del último año · **Duración** = duración medida, en años · **Beta** = contra el S&P 500."
        )
        st.caption(
            "Un ETF de bonos es una canasta de bonos que se compra como una acción. Los precios vienen **ajustados por "
            "distribuciones**, así que 1D / 1W / 1M / YTD son retornos totales: incluyen los cupones que el fondo repartió. "
            "**Volatilidad, caída máxima, Sharpe y beta** usan el último año de retornos diarios (a diferencia de las tablas "
            "de acciones, que miden la volatilidad en 21 días: la de un bono es más estable y un año la mide mejor). "
            "**Sharpe** = (retorno del año − tasa de política de EEUU) / volatilidad. **Beta** se mide contra el S&P 500. "
            "**Duración medida** = cuánto cayó el precio por cada punto que subió la tasa del Tesoro de referencia (la regresión "
            "diaria del último año); **R²** dice cuánto de su movimiento explican las tasas. "
            "Pasa el mouse sobre el ticker de cada ETF para ver una explicación en simple de cada indicador, con los números de esa fila."
        )

        elegidos = st.multiselect(
            "Elige ETFs a comparar", list(ETFS_RENTA_FIJA), default=["SHY", "IEF", "LQD", "HYG"],
            key="rf_etfs_grafico", format_func=_etiqueta_de_etf,
        )
        ventana = st.radio("Período", list(VENTANAS_ETF), horizontal=True, index=1, key="rf_ventana_etfs")
        elegidos = [t for t in elegidos if t in precios]
        if elegidos:
            tramo = _recortar_ventana(precios[elegidos].dropna(how="all"), VENTANAS_ETF[ventana]).ffill().dropna()
            fig = _figura(380)
            for ticker in elegidos:
                fig.add_trace(go.Scatter(x=tramo.index, y=tramo[ticker] / tramo[ticker].iloc[0] * 100, mode="lines", name=ticker))
            fig.update_layout(yaxis_title="Retorno total, base 100")
            _grafico(fig)
        else:
            st.info("Elige al menos un ETF para ver el gráfico.")

    st.subheader("Instrumentos de renta fija")
    _tabla(pd.DataFrame(
        [
            ("Letras (bills) del Tesoro de EEUU", "Gobierno de EEUU", "Hasta 1 año", "Sin cupones: se compran con descuento"),
            ("Notas y bonos del Tesoro", "Gobierno de EEUU", "2 a 30 años", "Cupones, de forma semestral"),
            ("PDBC", "Banco Central de Chile", "Corto plazo", "Pagaré descontable, sin cupones"),
            ("BCP", "Banco Central de Chile", "Largo plazo", "Bono en pesos, con cupones"),
            ("BCU", "Banco Central de Chile", "Largo plazo", "Bono en UF: el capital se reajusta con la inflación"),
            ("Bono corporativo", "Empresas", "3 a 30 años", "Cupones; paga más que el Estado por el riesgo de crédito"),
            ("Bono de alto rendimiento (high yield)", "Empresas con menor clasificación", "Variable", "Cupones más altos, mayor riesgo de default"),
        ],
        columns=["Instrumento", "Quién lo emite", "Plazo típico", "Cómo paga"],
    ))

    st.subheader("Tasas a 10 años hoy")
    ust, bcp, bcu = _ultimo(macro, NOMBRE_UST10), _ultimo(macro, NOMBRE_BCP10), _ultimo(macro, NOMBRE_BCU10)
    c1, c2, c3 = st.columns(3)
    for col, dato, etiqueta, fuente in (
        (c1, ust, "Tesoro de EEUU a 10 años", "Yahoo Finance"),
        (c2, bcp, "BCP a 10 años (pesos)", "Banco Central de Chile"),
        (c3, bcu, "BCU a 10 años (UF, tasa real)", "Banco Central de Chile"),
    ):
        with col:
            st.metric(etiqueta, f"{_fmt(dato[0])}%" if dato else "—")
            st.caption(f"Al {_fecha(dato[1])} · {fuente}" if dato else "Sin datos")


# ---------------------------------------------------------------------------
# Paso 2: valorización
# ---------------------------------------------------------------------------
COMPRAS = {"hace 6 meses": (pd.DateOffset(months=6), 0.5), "hace 1 año": (pd.DateOffset(years=1), 1.0), "hace 2 años": (pd.DateOffset(years=2), 2.0)}
BONOS_DEL_TESORO = {2: "SHY", 5: "IEI", 10: "IEF", 30: "TLT"}  # plazo del bono -> ETF del tramo equivalente


def _precio_en(precios: pd.DataFrame, ticker: str, fecha) -> float | None:
    s = precios[ticker].dropna() if ticker in precios else pd.Series(dtype=float)
    s = s[s.index <= fecha]
    return float(s.iloc[-1]) if len(s) else None


def _bonos_comprados_a_la_par(pivote: pd.DataFrame, fecha_hoy, curva_hoy: pd.Series, precios: pd.DataFrame) -> pd.DataFrame:
    """Qué le pasó a un bono del Tesoro comprado a la par con la tasa REAL de una fecha pasada, valorizado con la tasa REAL de hoy,
    junto al retorno REAL del ETF del tramo en el mismo período."""
    filas = []
    for etiqueta, (desplazamiento, transcurrido) in COMPRAS.items():
        try:
            fecha_compra, curva_compra = rf.curva_en_fecha(pivote, fecha_hoy - desplazamiento)
        except ValueError:
            continue
        for plazo, ticker in BONOS_DEL_TESORO.items():
            if plazo <= transcurrido:
                continue
            tasa_compra = rf.interpolar_tasa(curva_compra, plazo)
            restante = plazo - transcurrido
            tasa_hoy = rf.interpolar_tasa(curva_hoy, restante)
            r = rf.bono_a_la_par_hoy(tasa_compra, plazo, transcurrido, tasa_hoy)
            p0, p1 = _precio_en(precios, ticker, fecha_compra), _precio_en(precios, ticker, fecha_hoy)
            filas.append({
                "Comprado hace": f"{etiqueta.removeprefix('hace ')} ({_fecha(fecha_compra)})", "Bono a": f"{plazo} años",
                "Tasa compra": _pct(tasa_compra), "Tasa hoy": _pct(tasa_hoy), "Precio hoy": _fmt(r["precio_hoy"]),
                "Cupones": _fmt(r["cupones"]), "Retorno bono": f"{r['retorno_total'] * 100:+.2f}%",
                "ETF": ticker, "Retorno ETF": f"{(p1 / p0 - 1) * 100:+.2f}%" if p0 and p1 else "—",
            })
    return pd.DataFrame(filas)


def _paso_valorizacion(macro: pd.DataFrame, precios: pd.DataFrame) -> None:
    st.markdown(
        "El precio de un bono es el **valor presente de sus flujos**: cada cupón y el capital final se traen a hoy "
        "descontándolos con la tasa de mercado. Un peso dentro de dos años vale menos que un peso hoy, y mientras más alta "
        "la tasa, menos vale. Aquí se ve con la **curva real de hoy**, no con un bono inventado."
    )
    actual = _curva_actual(macro)
    if actual is None:
        _sin_datos("la curva de bonos del Tesoro de EEUU")
        return
    pivote, fecha, curva = actual

    st.subheader("Cuánto vale hoy un peso que se paga en el futuro")
    d = rf.curva_de_descuento(curva, 30)
    fig = _figura(340)
    fig.add_trace(go.Scatter(x=d["anios"], y=d["factor"], mode="lines", name="Valor de hoy de 1 peso", line=dict(color=AZUL, width=3)))
    fig.update_layout(xaxis_title="Años hasta el pago", yaxis_title="Valor de hoy de 1 peso", showlegend=False)
    _grafico(fig)
    elegidos = d[d["anios"].isin([1, 2, 3, 5, 7, 10, 20, 30])]
    _tabla(pd.DataFrame({
        "Plazo": [f"{int(a)} año" + ("s" if a != 1 else "") for a in elegidos["anios"]],
        "Tasa del bono a la par": [_pct(v) for v in elegidos["tasa_par"]],
        "Tasa de un bono sin cupones": [_pct(v) for v in elegidos["tasa_cero"]],
        "1 peso de ese plazo vale hoy": [f"{v:.4f}" for v in elegidos["factor"]],
    }), numericas=("Tasa del bono a la par", "Tasa de un bono sin cupones", "1 peso de ese plazo vale hoy"))
    st.caption(
        f"Curva de bonos del Tesoro de EEUU (H.15, vía FRED) al {_fecha(fecha)}. Las tasas publicadas son de bonos «a la par» "
        "(cupón = tasa); de ahí se despejan, plazo por plazo, los factores de descuento. Con esos factores, **cualquier bono del "
        "Tesoro a la par vale exactamente 100**: es la prueba de que el cálculo es consistente."
    )

    st.subheader("Un bono del Tesoro comprado a la par en el pasado, valorizado hoy")
    st.markdown(
        "Se toma la tasa **real** de ese plazo en la fecha de compra (el cupón del bono) y la tasa **real** de hoy para el plazo "
        "que le queda. Si la tasa subió, el precio bajó: es la relación inversa entre precio y tasa, con datos de verdad."
    )
    tabla = _bonos_comprados_a_la_par(pivote, fecha, curva, precios)
    if tabla.empty:
        _sin_datos("las curvas pasadas del Tesoro")
    else:
        _tabla(tabla, numericas=[c for c in tabla.columns if c not in ("Comprado hace", "Bono a", "ETF")], mostrar_todo=True)
        st.caption(
            "«Tasa hoy» es la tasa real de hoy para el plazo que le queda al bono (el plazo original menos el tiempo transcurrido). "
            "«Cupones» y «Retorno bono» cuentan lo cobrado más el cambio de precio, sin reinvertir cupones. «Retorno ETF» es el del fondo "
            "de ese tramo (SHY 1-3 años, IEI 3-7, IEF 7-10, TLT 20+) entre las mismas fechas: una comparación aproximada, porque el ETF "
            "renueva sus bonos y el bono de la tabla envejece."
        )
    st.caption(
        "Simplificación: se valoriza en fechas de cupón, así que no hay interés devengado (precio limpio = sucio). El dashboard no tiene "
        "precios de bonos individuales (solo de los ETFs y de la curva), por eso no se muestra el precio de un bono específico del mercado."
    )


# ---------------------------------------------------------------------------
# Paso 3: riesgo de mercado
# ---------------------------------------------------------------------------
def _paso_riesgo_mercado(macro: pd.DataFrame, precios: pd.DataFrame) -> None:
    st.markdown(
        "Si las tasas suben, el precio de un bono ya emitido **baja**: nadie paga lo mismo por un cupón de 5% si "
        "puede comprar uno nuevo que paga 6%. La **duración** mide cuánto: es la sensibilidad del precio a la tasa. "
        "Aquí no se calcula con una fórmula: se **mide** con datos reales, viendo cuánto se movió de verdad el precio de cada ETF "
        "cuando se movió la tasa del Tesoro."
    )
    resumen = _resumen_de_etfs(precios, macro, pd.Timestamp.now().normalize()) if len(precios) else None
    if resumen is None:
        _sin_datos("los ETFs de bonos")
        return
    actual = _curva_actual(macro)

    filas = []
    for ticker, r in resumen.iterrows():
        plazo = int(r["Plazo de referencia"])
        teorica = rf.bono_a_la_par(actual[2], plazo)["modificada"] if actual else None
        medida, error = r["Duración medida (años)"], r["Error de la duración"]
        filas.append({
            "ETF": ticker, "Grupo": r["Grupo"], "Ref. Tesoro": f"{plazo} años",
            "Duración medida": _fmt(medida) if pd.notna(medida) else "—",
            "Margen (±2 err.)": f"±{_fmt(2 * error)}" if pd.notna(error) else "—",
            "R²": _fmt(r["R² con la tasa"]) if pd.notna(r["R² con la tasa"]) else "—",
            "Duración teórica": _fmt(teorica) if teorica is not None else "—",
        })
    _tabla(pd.DataFrame(filas), numericas=[c for c in filas[0] if c not in ("ETF", "Grupo", "Ref. Tesoro")], mostrar_todo=True)
    st.caption(
        "Lectura: una duración medida de 6.5 significa que, en el último año, el precio cayó cerca de 6.5% por cada punto porcentual que subió la "
        "tasa. «Duración teórica» es la de un bono del Tesoro a la par con el plazo de «Ref. Tesoro» (la tasa contra la que se mide): la diferencia con la medida se debe a que "
        "el ETF mezcla bonos de distintos plazos y cupones. Con un **R² bajo** (los bonos de empresas y de alto rendimiento), la tasa explica poco del "
        "movimiento: manda el riesgo de crédito y la duración medida es poco confiable."
    )

    disponibles = list(resumen.index)
    ticker = st.selectbox("ETF para ver la medición", disponibles, index=min(2, len(disponibles) - 1), key="rf_etf_duracion",
                          format_func=_etiqueta_de_etf)
    datos = ETFS_RENTA_FIJA[ticker]
    pares = rf.pares_para_duracion(precios[ticker], _rendimiento_del_tesoro(macro, datos["plazo_referencia"]))
    medida = rf.duracion_empirica(precios[ticker], _rendimiento_del_tesoro(macro, datos["plazo_referencia"]))
    if medida is None or pares.empty:
        _sin_datos("la tasa del Tesoro de referencia de ese ETF")
        return
    x = pares["cambio_de_tasa"] * 100  # puntos porcentuales
    fig = _figura(420)
    fig.add_trace(go.Scatter(x=x, y=pares["retorno"] * 100, mode="markers", name="Cada día del último año",
                             marker=dict(color=AZUL, size=6, opacity=0.6)))
    recta = np.array([x.min(), x.max()])
    fig.add_trace(go.Scatter(x=recta, y=-medida["duracion"] * recta, mode="lines", name=f"Duración medida {_fmt(medida['duracion'], 1)}",
                             line=dict(color=ROJO, width=3)))
    fig.update_layout(xaxis_title=f"Cambio diario de la tasa del Tesoro a {datos['plazo_referencia']} años (puntos porcentuales)",
                      yaxis_title="Retorno diario de " + ticker + " (%)", hovermode="closest")
    _grafico(fig)
    st.caption(
        f"Cada punto es un día. La pendiente de la recta roja es la duración: {_fmt(medida['duracion'], 1)} años (±{_fmt(2 * medida['error_estandar'], 1)}), "
        f"con un R² de {_fmt(medida['r2'])} sobre {medida['n']} días. Mientras más alineados estén los puntos, más confiable la medición."
    )


# ---------------------------------------------------------------------------
# Paso 4: riesgo de crédito
# ---------------------------------------------------------------------------
PARES_DE_CREDITO = {
    "HYG / IEI: alto rendimiento frente al Tesoro de 3 a 7 años": ("HYG", "IEI"),
    "LQD / IEF: empresas de buena calidad frente al Tesoro de 7 a 10 años": ("LQD", "IEF"),
}


def _paso_riesgo_credito(macro: pd.DataFrame, precios: pd.DataFrame) -> None:
    st.markdown(
        "El **riesgo de crédito** es que quien emitió el bono **no pague**. El mercado lo cobra como un **spread**: "
        "la tasa extra que exige sobre un bono sin riesgo (el del Tesoro) del mismo plazo. A mayor riesgo, mayor spread."
    )
    st.markdown(
        "Las agencias clasifican a los emisores. De **BBB− (S&P y Fitch) o Baa3 (Moody's) hacia arriba** se llama "
        "*grado de inversión*; por debajo, *alto rendimiento* (*high yield*): paga más porque quiebra más seguido."
    )
    ventana_nombre = st.radio("Período", list(VENTANAS), horizontal=True, index=1, key="rf_ventana_credito")
    dias = VENTANAS[ventana_nombre]

    st.subheader("El spread de los bonos corporativos")
    baa = _serie(macro, NOMBRE_BAA10Y).dropna()
    if len(baa) == 0:
        _sin_datos("el spread de bonos corporativos Baa (BAA10Y)")
    else:
        actual = (float(baa.iloc[-1]), baa.index[-1])
        recorte = _recortar_ventana(baa, dias)
        percentil = float((recorte <= actual[0]).mean() * 100)
        c1, c2, c3 = st.columns(3)
        c1.metric("Spread Baa − Tesoro 10 años", f"{_fmt(actual[0])} pp")
        c2.metric(f"Percentil en «{ventana_nombre.lower()}»", f"{_fmt(percentil, 0)}%",
                  help="Porcentaje de los días de ese período en que el spread fue igual o menor que hoy.")
        c3.metric("Máximo del período", f"{_fmt(recorte.max())} pp", help=f"Ocurrió el {_fecha(recorte.idxmax())}.")
        fig = _figura(340)
        fig.add_trace(go.Scatter(x=recorte.index, y=recorte.values, mode="lines", name="BAA10Y", line=dict(color=AZUL)))
        fig.update_layout(yaxis_title="Spread (puntos porcentuales)", showlegend=False)
        _grafico(fig)
        st.caption(
            f"Datos al {_fecha(actual[1])}. Es la diferencia entre el rendimiento de los bonos corporativos clasificados Baa por Moody's "
            "y el del Tesoro a 10 años (FRED). Es un indicador de **EEUU**, no de empresas chilenas. Suele dispararse en las crisis, "
            "cuando el mercado teme más defaults."
        )

    st.subheader("El crédito en los precios de los ETFs")
    st.markdown(
        "Dividir el precio de un ETF de bonos de empresas por el de uno del Tesoro de plazo parecido muestra cuánto le gana (o pierde) el "
        "crédito al Tesoro. **Si la línea sube, el crédito lo está haciendo mejor**; si baja, el mercado está pidiendo más premio por el riesgo."
    )
    if len(precios) == 0:
        _sin_datos("los ETFs de bonos")
        return
    fig = _figura(360)
    hubo = False
    for etiqueta, (credito, tesoro) in PARES_DE_CREDITO.items():
        if credito in precios and tesoro in precios:
            razon = (precios[credito] / precios[tesoro]).dropna()
            razon = _recortar_ventana(razon, dias)
            fig.add_trace(go.Scatter(x=razon.index, y=razon / razon.iloc[0] * 100, mode="lines", name=etiqueta))
            hubo = True
    if hubo:
        fig.update_layout(yaxis_title="Precio del crédito ÷ precio del Tesoro, base 100")
        _grafico(fig)
    st.caption(
        "No hay datos de probabilidades de default por clasificación en el dashboard, por eso no se calcula una pérdida esperada. "
        "Los pares no tienen exactamente el mismo plazo, así que la comparación es aproximada."
    )


# ---------------------------------------------------------------------------
# Paso 5: Banco Central y tasas
# ---------------------------------------------------------------------------
def _ultimo_comun(a: pd.Series, b: pd.Series):
    """(valor de a, valor de b, fecha) en la última fecha con dato en las dos series, o None."""
    juntas = pd.concat([a, b], axis=1, join="inner").dropna()
    return (float(juntas.iloc[-1, 0]), float(juntas.iloc[-1, 1]), juntas.index[-1]) if len(juntas) else None


def _paso_banco_central(macro: pd.DataFrame) -> None:
    st.markdown(
        "El banco central fija la **tasa de política monetaria** (TPM en Chile) y usa **operaciones de mercado abierto**: "
        "compra o vende bonos, o hace *repos* (compra con compromiso de recompra), para inyectar o retirar liquidez del "
        "sistema bancario. Así mantiene la tasa de interés entre bancos cerca de la TPM."
    )
    st.markdown(
        "**Cómo llega al precio de los bonos.** Cuando sube la TPM, las tasas cortas suben casi de inmediato; las largas "
        "dependen de lo que el mercado espere que haga el banco central en el futuro. Como un alza de tasas baja el precio "
        "de los bonos ya emitidos (paso 3), la política monetaria es el principal motor de la renta fija."
    )

    ultimos = {etiqueta: _ultimo(macro, nombre) for etiqueta, nombre in SERIES_TASAS.items()}
    columnas = st.columns(len(ultimos))
    for col, (etiqueta, dato) in zip(columnas, ultimos.items()):
        with col:
            st.metric(etiqueta, f"{_fmt(dato[0])}%" if dato else "—")
            st.caption(f"Al {_fecha(dato[1])}" if dato else "Sin datos")
    chile, eeuu = ultimos["TPM de Chile"], ultimos["Tasa de política de EEUU (Fed funds)"]
    if chile and eeuu:
        st.metric("Diferencial de política monetaria (Chile − EEUU)", f"{_fmt(chile[0] - eeuu[0])} pp")
        st.caption("Las dos fechas pueden diferir de uno a unos pocos días. Este diferencial es la base del *carry trade* de divisas.")

    ventana = st.radio("Período", list(VENTANAS), horizontal=True, index=1, key="rf_ventana_tasas")
    dias = VENTANAS[ventana]
    fig = _figura(400)
    colores = [AZUL, ROJO, VERDE, GRIS]
    hubo_datos = False
    avisos_de_huecos = []
    for color, (etiqueta, nombre) in zip(colores, SERIES_TASAS.items()):
        s = _serie(macro, nombre).dropna()
        if len(s) == 0:
            continue
        s = _recortar_ventana(s, dias)
        avisos_de_huecos += [f"{etiqueta}: del {_fecha(antes)} al {_fecha(despues)}" for antes, despues in _huecos(s)]
        s = _cortar_en_huecos(s)
        fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", name=etiqueta, line=dict(color=color)))
        hubo_datos = True
    fig.update_layout(yaxis_title="Tasa (%)")
    if hubo_datos:
        _grafico(fig)
    else:
        _sin_datos("las tasas de política monetaria")
    if avisos_de_huecos:
        st.caption("**Sin datos en la base** (la línea se corta en vez de unir los bordes): " + "; ".join(avisos_de_huecos) + ".")

    st.subheader("La curva de bonos del Banco Central de Chile")
    st.markdown(
        "El BCP paga en pesos y el BCU en UF (tasa real, sobre la inflación). La diferencia entre los dos, al mismo plazo, es la "
        "**inflación que el mercado tiene puesta en precio**."
    )
    ultimos_chile = {(grupo, plazo): _ultimo(macro, nombre) for grupo, plazos in CURVA_CHILE.items() for plazo, nombre in plazos.items()}
    if not any(ultimos_chile.values()):
        _sin_datos("los bonos del Banco Central")
    else:
        fig2 = _figura(340)
        for color, (grupo, plazos) in zip((AZUL, ROJO), CURVA_CHILE.items()):
            puntos = [(p, ultimos_chile[(grupo, p)]) for p in plazos if ultimos_chile[(grupo, p)]]
            fig2.add_trace(go.Scatter(
                x=[p for p, _ in puntos], y=[d[0] for _, d in puntos], mode="lines+markers", name=grupo, line=dict(color=color, width=3),
                text=[f"al {_fecha(d[1])}" for _, d in puntos], hovertemplate="%{x} años: %{y:.2f}% (%{text})<extra></extra>",
            ))
        fig2.update_layout(xaxis_title="Plazo (años)", yaxis_title="Tasa (%)", hovermode="closest")
        _grafico(fig2)
        filas = []
        for grupo, plazos in CURVA_CHILE.items():
            for plazo in plazos:
                dato = ultimos_chile[(grupo, plazo)]
                filas.append({"Bono": grupo, "Plazo": f"{plazo} años", "Tasa (%)": _fmt(dato[0]) if dato else "—", "Al": _fecha(dato[1]) if dato else "—"})
        _tabla(pd.DataFrame(filas), numericas=("Tasa (%)",))

        st.markdown("**Inflación implícita (BCP − BCU del mismo plazo)**")
        c1, c2 = st.columns(2)
        implicitas = {}
        for col, plazo in ((c1, 5), (c2, 10)):
            nominal, real = _serie(macro, CURVA_CHILE["BCP (pesos)"][plazo]), _serie(macro, CURVA_CHILE["BCU (UF, tasa real)"][plazo])
            comun = _ultimo_comun(nominal, real)
            implicitas[plazo] = (nominal - real).dropna()
            with col:
                st.metric(f"A {plazo} años", f"{_fmt(comun[0] - comun[1])} pp" if comun else "—")
                st.caption(f"Al {_fecha(comun[2])}" if comun else "Sin datos")
        fig3 = _figura(320)
        for color, (plazo, serie) in zip((AZUL, ROJO), implicitas.items()):
            serie = _cortar_en_huecos(_recortar_ventana(serie, dias))
            fig3.add_trace(go.Scatter(x=serie.index, y=serie.values, mode="lines", name=f"A {plazo} años", line=dict(color=color)))
        fig3.update_layout(yaxis_title="Puntos porcentuales")
        _grafico(fig3)
        st.caption(
            "Incluye también una prima por riesgo y por liquidez: **no es un pronóstico oficial** de nadie. La base no incluye el BCU a 20 años: "
            "esa serie no devolvió datos recientes cuando se consultó al Banco Central."
        )
    st.caption(
        "Fuentes: Banco Central de Chile (TPM, PDBC, Swap Cámara, BCP y BCU) y FRED (Fed funds). El dashboard **no tiene** los montos de "
        "las operaciones de mercado abierto ni de las licitaciones del Banco Central: esa parte solo se explica aquí."
    )


# ---------------------------------------------------------------------------
# Paso 6: curva y estrategias
# ---------------------------------------------------------------------------
def _tabla_de_rodar(curva: pd.Series) -> pd.DataFrame:
    filas = []
    for horizonte, etiqueta in HORIZONTES.items():
        for plazo in PLAZOS_DE_ESTRATEGIA:
            if plazo <= horizonte:
                continue
            r = rf.rodar_en_la_curva(curva, plazo, horizonte)
            filas.append({
                "Compras un bono a": f"{plazo} años", "Lo vendes después de": etiqueta,
                "Tasa de compra": _pct(r["tasa_compra"]), "Tasa al vender": _pct(r["tasa_venta"]),
                "Cupones (carry)": _pct(r["carry"]), "Efecto de rodar": _pct(r["efecto_precio"]),
                "Retorno total": _pct(r["retorno_total"]), "Retorno anualizado": _pct(r["retorno_anualizado"]),
            })
    return pd.DataFrame(filas)


def _paso_curva(macro: pd.DataFrame, precios: pd.DataFrame) -> None:
    st.markdown(
        "La **curva de rendimientos** muestra la tasa de bonos del mismo emisor para cada plazo. Normalmente sube con el "
        "plazo (se pide más por esperar más). Cuando los plazos cortos pagan **más** que los largos, la curva está "
        "**invertida**, y históricamente eso ha antecedido recesiones en EEUU, aunque no es una predicción segura."
    )
    actual = _curva_actual(macro)
    if actual is None:
        _sin_datos("la curva de bonos del Tesoro de EEUU")
        return
    pivote, fecha, curva = actual

    fig = _figura(400)
    etiquetas = list(et.PLAZOS_ANIOS)
    fig.add_trace(go.Scatter(x=etiquetas, y=(curva * 100).tolist(), mode="lines+markers", name=_fecha(fecha), line=dict(color=AZUL, width=4)))
    for etiqueta, desplazamiento, color in (("hace 1 mes", pd.DateOffset(months=1), GRIS), ("hace 1 año", pd.DateOffset(years=1), ROJO)):
        try:
            fecha_ant, curva_ant = rf.curva_en_fecha(pivote, fecha - desplazamiento)
        except ValueError:
            continue
        fig.add_trace(go.Scatter(
            x=etiquetas, y=(curva_ant * 100).tolist(), mode="lines+markers",
            name=f"{etiqueta} ({_fecha(fecha_ant)})", line=dict(color=color, dash="dash"),
        ))
    fig.update_layout(xaxis_title="Plazo", yaxis_title="Rendimiento (%)", xaxis=dict(type="category"))
    _grafico(fig)

    pendiente = (curva.loc[10.0] - curva.loc[2.0]) * 100
    c1, c2 = st.columns(2)
    c1.metric("Pendiente 10 años − 2 años", f"{_fmt(pendiente)} pp")
    c2.metric("Forma de la curva", "Pendiente positiva (normal)" if pendiente > 0 else "Invertida")
    st.caption(
        f"Curva de bonos del Tesoro de EEUU (H.15, vía FRED) al {_fecha(fecha)}. Para ajustar una curva suave con Nelson-Siegel, "
        "mira Laboratorio Financiero."
    )

    st.subheader("Rodar por la curva (roll-down)")
    st.markdown(
        "Con una curva de pendiente positiva, un bono que envejece pasa a un plazo más corto, que se descuenta a una tasa más "
        "baja, y **sube de precio** aunque nada cambie. Se suma al carry (los cupones). La tabla supone que la curva de hoy **no se "
        "mueve**: es un escenario base calculado con la curva real, no una predicción."
    )
    _tabla(_tabla_de_rodar(curva), numericas=("Tasa de compra", "Tasa al vender", "Cupones (carry)", "Efecto de rodar", "Retorno total", "Retorno anualizado"))

    st.subheader("Estrategias con ETFs reales: bullet, barbell y escalera")
    st.markdown(
        "- **Bullet:** todo en un solo plazo (IEF, Tesoro de 7 a 10 años).\n"
        "- **Barbell:** en los extremos (SHY, 1 a 3 años, y TLT, 20 años o más), con pesos elegidos para que tenga **la misma duración medida** que el bullet.\n"
        "- **Escalera (ladder):** partes iguales en SHY, IEI, IEF y TLT."
    )
    resumen = _resumen_de_etfs(precios, macro, pd.Timestamp.now().normalize()) if len(precios) else None
    necesarios = {"SHY", "IEI", "IEF", "TLT"}
    if resumen is None or not necesarios <= set(resumen.index) or resumen.loc[list(necesarios), "Duración medida (años)"].isna().any():
        _sin_datos("los ETFs del Tesoro (SHY, IEI, IEF y TLT) o su duración medida")
        return
    d = resumen["Duración medida (años)"]
    try:
        peso_corto, peso_largo = rf.pesos_para_igualar_duracion(d["SHY"], d["TLT"], d["IEF"])
    except ValueError:
        _sin_datos("duraciones medidas coherentes para armar el barbell")
        return
    carteras = {
        "Bullet": {"IEF": 1.0},
        "Barbell": {"SHY": peso_corto, "TLT": peso_largo},
        "Escalera": {"SHY": 0.25, "IEI": 0.25, "IEF": 0.25, "TLT": 0.25},
    }
    ventana = st.radio("Período", list(VENTANAS_ETF), horizontal=True, index=0, key="rf_ventana_carteras")
    retornos = _recortar_ventana(precios[sorted(necesarios)].dropna().pct_change().dropna(), VENTANAS_ETF[ventana])
    filas, fig = [], _figura(360)
    for nombre, pesos in carteras.items():
        r = rf.retornos_de_cartera(retornos, pesos)
        e = rf.estadisticas_de_retornos(r)
        fig.add_trace(go.Scatter(x=r.index, y=(1 + r).cumprod() * 100, mode="lines", name=nombre))
        filas.append({
            "Estrategia": nombre, "Composición": " · ".join(f"{t} {p * 100:.0f}%" for t, p in pesos.items()),
            "Duración medida": _fmt(sum(p * d[t] for t, p in pesos.items())),
            "Retorno total (%)": f"{e['retorno_total']:+.2f}", "Volatilidad (%)": _fmt(e["volatilidad"]),
            "Caída máxima (%)": _fmt(e["caida_maxima"]),
        })
    fig.update_layout(yaxis_title="Retorno total, base 100")
    _grafico(fig)
    _tabla(pd.DataFrame(filas), numericas=("Duración medida", "Retorno total (%)", "Volatilidad (%)", "Caída máxima (%)"))
    st.caption(
        "Carteras reales armadas con los ETFs de la tabla, con pesos constantes (se rebalancean cada día) e incluyendo lo que cada fondo repartió. "
        "La duración de cada una es el promedio de las duraciones **medidas**. A igual duración, el barbell debería rendir distinto al bullet cuando la "
        "curva se tuerce o se mueve en forma desigual: compara las filas y el gráfico en el período elegido. Es lo que pasó, no una promesa de lo que pasará."
    )


# ---------------------------------------------------------------------------
# Paso 7: emitir un bono afuera
# ---------------------------------------------------------------------------
def _paso_emision(macro: pd.DataFrame) -> None:
    st.markdown(
        "Cuando una empresa chilena quiere financiarse en dólares con inversionistas de todo el mundo, **emite un bono "
        "internacional**. Los pasos habituales:"
    )
    st.markdown(
        "1. **Mandato:** la empresa contrata a bancos de inversión (los *bookrunners*) que organizan la emisión.\n"
        "2. **Preparación:** documentos legales y financieros (el prospecto u *offering memorandum*) y clasificaciones de "
        "riesgo de las agencias. Para emisores latinoamericanos es habitual usar la regla 144A / Reg S y ley de Nueva York.\n"
        "3. **Roadshow:** presentaciones a inversionistas para medir el interés.\n"
        "4. **Anuncio con *guidance* inicial:** una referencia de precio, expresada como un **spread sobre el bono del "
        "Tesoro** del mismo plazo.\n"
        "5. **Libro de órdenes (*bookbuilding*):** los inversionistas piden montos y precios. Si hay mucha demanda, el spread "
        "final se **ajusta a la baja** respecto de la guidance.\n"
        "6. **Fijación de precio y colocación:** se fija la tasa definitiva, se asignan los bonos y, unos días después, se "
        "liquida la emisión y la empresa recibe el dinero."
    )
    st.subheader("Las referencias de hoy (datos reales)")
    st.markdown(
        "El costo de una emisión se arma sobre el Tesoro de EEUU: **tasa del Tesoro + spread**. Estas son las referencias reales de hoy; "
        "el spread concreto de una emisión lo fija el mercado el día de la colocación, y el dashboard no tiene datos de emisiones reales."
    )
    actual = _curva_actual(macro)
    if actual is None:
        _sin_datos("la curva de bonos del Tesoro de EEUU")
    else:
        _, fecha, curva = actual
        c1, c2, c3 = st.columns(3)
        for col, plazo in ((c1, 5), (c2, 10), (c3, 30)):
            col.metric(f"Tesoro de EEUU a {plazo} años", f"{_fmt(curva.loc[float(plazo)] * 100)}%")
        st.caption(f"Bonos del Tesoro (H.15, vía FRED) al {_fecha(fecha)}.")

    baa = _ultimo(macro, NOMBRE_BAA10Y)
    ust10 = _ultimo_comun(_serie(macro, nombre_treasury("10 años")), _serie(macro, NOMBRE_BAA10Y))
    if baa and ust10:
        st.metric("Rendimiento de un bono corporativo Baa a 10 años (Tesoro + spread)", f"{_fmt(ust10[0] + ust10[1])}%")
        st.caption(
            f"Es el Tesoro a 10 años ({_fmt(ust10[0])}%) más el spread Baa ({_fmt(ust10[1] * 100, 0)} pb), al {_fecha(ust10[2])}: una referencia para "
            "una empresa de grado de inversión de EEUU, **no** el costo de una empresa chilena."
        )
    chile_vs_tesoro = _ultimo_comun(_serie(macro, NOMBRE_BCP10), _serie(macro, nombre_treasury("10 años")))
    if chile_vs_tesoro:
        st.metric("Spread del bono en pesos del Banco Central frente al Tesoro, a 10 años (BCP − Tesoro)",
                  f"{_fmt(chile_vs_tesoro[0] - chile_vs_tesoro[1])} pp")
        st.caption(
            "Una aproximación al estilo Damodaran del riesgo país, no el EMBI oficial (que requiere una fuente de pago que este dashboard no tiene). "
            "Compara un bono en pesos con uno en dólares, así que también incluye diferencias de inflación y de moneda."
        )


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------
def _descarga_del_informe(macro: pd.DataFrame, precios: pd.DataFrame) -> None:
    """Prepara y entrega el informe en PDF de esta sección.

    Son dos pasos a propósito. `st.download_button` necesita los bytes del archivo ANTES de dibujarse, así que ponerlo
    directo obligaría a armar el PDF (~0,8 s medidos) en cada interacción de la pantalla, incluso cuando nadie lo pide."""
    import informe_renta_fija as informe  # acá adentro: informe_renta_fija importa este módulo, y arriba sería circular

    with st.expander("Descargar el informe en PDF"):
        st.caption(
            "Cinco páginas que explican qué pasó con los bonos en el período, **por qué** pasó (cuánto del movimiento explica la "
            "duración y cuánto no) y qué lectura equivocada conviene evitar. Se arma en el momento con lo último que hay en la base."
        )
        periodo = st.selectbox("Período que cubre el informe", list(informe.PERIODOS), key="rf_periodo_informe")
        if st.button("Preparar informe", key="rf_preparar_informe"):
            with st.spinner("Armando el informe…"):
                st.session_state["rf_informe"] = (periodo, informe.generar(macro, precios, periodo))
        preparado = st.session_state.get("rf_informe")
        if preparado and preparado[0] == periodo:
            st.download_button(
                "Descargar PDF", data=preparado[1], mime="application/pdf", key="rf_descargar_informe",
                file_name=f"informe-renta-fija-{pd.Timestamp.now():%Y-%m-%d}.pdf",
            )
        elif preparado:
            st.caption(f"El informe preparado es de «{preparado[0].lower()}». Vuelve a prepararlo para el período elegido.")


def render_renta_fija(df_macro: pd.DataFrame, df_precios: pd.DataFrame) -> None:
    st.header("Renta fija: instrumentos reales, riesgo y curva de tasas")
    st.info(
        "Todos los datos de esta sección son **reales**: ETFs de bonos (Yahoo Finance), curva del Tesoro y spread corporativo (FRED), "
        "bonos y tasas del Banco Central de Chile. Donde la base no tiene un dato, la pantalla lo dice."
    )
    macro = _recortar(df_macro)
    precios = _precios_en_columnas(df_precios)
    if len(precios):
        _descarga_del_informe(macro, precios)
    paso = st.segmented_control("Paso", PASOS, default=PASOS[0], key="rf_paso", label_visibility="collapsed") or PASOS[0]

    if paso == PASOS[0]:
        _paso_mercado(macro, precios)
    elif paso == PASOS[1]:
        _paso_valorizacion(macro, precios)
    elif paso == PASOS[2]:
        _paso_riesgo_mercado(macro, precios)
    elif paso == PASOS[3]:
        _paso_riesgo_credito(macro, precios)
    elif paso == PASOS[4]:
        _paso_banco_central(macro)
    elif paso == PASOS[5]:
        _paso_curva(macro, precios)
    else:
        _paso_emision(macro)
