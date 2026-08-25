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
    TICKERS_DOW_JONES,
    TICKERS_DOW_JONES_PRINCIPALES,
    TICKER_DOW_JONES,
    TICKERS_EEUU_ADICIONALES,
    TICKERS_LABORATORIO_50,
    TICKERS_LABORATORIO_AMPLIADO,
    SECTOR_POR_TICKER_LABORATORIO,
    EMPRESA_POR_TICKER_LABORATORIO,
    SECTORES_OBLIGATORIOS_LABORATORIO,
)
import portfolio_lab as lab
import estructura_tasas as et
from market_data import (
    calcular_resumen_mercado,
    calcular_retornos_reales,
    calcular_capm_regresion,
    detectar_apagon_mercado,
    calcular_atribucion_ipsa,
    validar_atribucion_out_of_sample,
    INDICADORES_PREMERCADO,
)
from calendario_economico import proximos_eventos, NOTA_VIGENCIA, INDICADOR_POR_TIPO, CALENDARIO_VERIFICADO_AL
from glosario import (
    nombre_completo,
    explicacion_rendimiento,
    explicacion_beta,
    explicacion_capm,
    explicacion_volatilidad,
    explicacion_sharpe,
    explicacion_treynor,
    explicacion_alfa,
    explicacion_atribucion,
    tooltip_html,
    TOOLTIP_CSS,
)

st.set_page_config(page_title="Mercado Económico Chileno", layout="wide")

# Paleta categórica de orden fijo (nunca se reasigna por índice de la
# selección), y diverging rojo-gris-verde para el heatmap de desempeño.
PALETA_CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
CMAP_DIVERGENTE = LinearSegmentedColormap.from_list("rojo_verde", ["#d03b3b", "#f0efec", "#0ca30c"])
# Secuencial (una sola tonalidad, claro→oscuro) para magnitudes que no son "ganancia/pérdida", como volatilidad.
CMAP_SECUENCIAL = LinearSegmentedColormap.from_list("azul_secuencial", ["#fcfcfb", "#2a78d6"])
# Diverging azul-gris-rojo para la matriz de correlación (no es un juicio de valor bueno/malo, por eso no usa verde/rojo).
COLORSCALE_CORRELACION = [[0.0, "#e34948"], [0.5, "#f0efec"], [1.0, "#2a78d6"]]

# Métricas de riesgo: ventana de volatilidad (días hábiles) y de VaR (~2 años calendario).
VENTANA_VOLATILIDAD = 21
VENTANA_VAR = pd.DateOffset(years=2)

# Ajuste de VaR por liquidez: ventana para el monto transado diario promedio,
# y multiplicador heurístico aplicado al VaR del cuartil menos líquido.
VENTANA_LIQUIDEZ = pd.DateOffset(months=3)
MULTIPLICADOR_LIQUIDEZ = 1.3


st.title("Mercado Económico Chileno")
st.caption("Datos del Banco Central de Chile y Yahoo Finance, actualizados diariamente")

engine = get_engine()


@st.cache_data(ttl=3600)  # cachea 1 hora, para no golpear la BD en cada click
def cargar_series_macro():
    # Sin ORDER BY en el SQL a propósito: con ~30.000 filas, Postgres elegía
    # un sort que no entraba en work_mem y se derramaba a disco ("Sort
    # Method: external merge" en EXPLAIN ANALYZE) — medido en producción,
    # esto solo tardaba 14.4s. Se ordena en pandas después de traer los
    # datos (más rápido: ~0.8s totales) en vez de pedirle a Postgres que
    # ordene 30k+ filas en el propio SELECT.
    query = "SELECT nombre, fecha, valor FROM series_macro"
    df = pd.read_sql(query, engine).sort_values("fecha")
    # Descarta filas con valor NaN (dato no disponible, ej. una sesión de
    # Yahoo Finance incompleta al momento de descargar) para que ningún
    # cálculo aguas abajo tome silenciosamente NaN como "el último valor" —
    # así, el último valor real que queda es siempre uno válido, con su
    # fecha real (nunca la fecha de hoy con un dato viejo disfrazado).
    return df.dropna(subset=["valor"])


@st.cache_data(ttl=3600)
def cargar_precios_acciones():
    # Mismo motivo que cargar_series_macro: sin ORDER BY en el SQL. Acá el
    # impacto es mucho mayor por el tamaño de la tabla (~206.000 filas y
    # creciendo ~164/día) — medido en producción, el ORDER BY en Postgres
    # (con el sort derramado a disco) hacía que esta consulta tardara
    # 60-72 segundos, de forma consistente y repetible (no un cold-start
    # de Neon: se probó 3 veces seguidas en la misma conexión ya "tibia" y
    # dio 60-67s las tres veces). Sin el ORDER BY, ordenando en pandas
    # después, baja a ~3.4s -- una mejora de ~20x, verificada con el mismo
    # benchmark antes/después, no asumida.
    query = "SELECT ticker, fecha, precio_cierre, volumen FROM precios_acciones"
    df = pd.read_sql(query, engine).sort_values("fecha")
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
    datos_proxy = (
        df_acciones[df_acciones["ticker"] == TICKER_PROXY_IPSA]
        .sort_values("fecha")
        .set_index("fecha")
    )
    retornos_proxy_reales = calcular_retornos_reales(datos_proxy["precio_cierre"], datos_proxy["volumen"]).dropna()
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


def _mostrar_banner_apagon(df_precios: pd.DataFrame, tickers: list, nombre_universo: str) -> None:
    """Banner a nivel de pestaña (visualmente distinto del "Atraso" por
    fila del heatmap) que avisa cuando la fuente dejó de refrescar un tramo
    amplio del universo de acciones usado en esa pestaña — ver
    detectar_apagon_mercado para el criterio exacto. No hace nada si no
    detecta apagón, así que desaparece solo apenas la fuente se ponga al
    día, y se activaría solo ante un apagón futuro sin tocar código."""
    apagon = detectar_apagon_mercado(df_precios, tickers)
    if apagon is None:
        return
    st.error(
        f"⚠️ **Apagón de datos detectado**: el {apagon['pct_afectado'] * 100:.0f}% de "
        f"{nombre_universo} no ha recibido precios nuevos de Yahoo Finance desde el "
        f"{apagon['fecha_apagon'].strftime('%Y-%m-%d')}. Esto afecta a un tramo amplio "
        "del mercado en esta fuente, no a acciones específicas — los cálculos de esta "
        "pestaña (retorno, volatilidad, Beta, correlación, optimización, etc.) usan el "
        "último dato real disponible antes del apagón."
    )


def _texto_atraso(atrasado: bool, dias_habiles_atraso: int) -> str:
    """Texto de la columna "Atraso" del heatmap: explícito sobre cuántos días
    hábiles lleva sin refrescarse el precio, en vez de un ícono booleano que
    no dice cuánto atraso hay. "Al día" (no "0 días") cuando no hay atraso,
    para no insinuar una cuenta que no se está mostrando."""
    if atrasado:
        return f"Precio congelado — {dias_habiles_atraso} días hábiles"
    return "Al día"


def _color_gradiente_hex(cmap, valor, vmin, vmax) -> str | None:
    """Replica a mano el color que Styler.background_gradient() calcularía
    para `valor` dentro de [vmin, vmax] con el colormap `cmap` — necesario
    porque st.dataframe() (el renderer real de la tabla) no soporta HTML
    dentro de las celdas, así que el heatmap con tooltips se arma como HTML
    propio en vez de con un Styler, y hay que reproducir el color a mano."""
    if pd.isna(valor) or vmax == vmin:
        return None
    fraccion = (valor - vmin) / (vmax - vmin)
    fraccion = min(max(fraccion, 0.0), 1.0)
    r, g, b, _a = cmap(fraccion)
    return f"rgb({int(r * 255)}, {int(g * 255)}, {int(b * 255)})"


def _armar_tooltip(bloques: list) -> str:
    """Une los bloques de un tooltip (nombre + explicaciones) con un
    separador visual, saltándose los que vinieron vacíos (ej.
    explicacion_atribucion() cuando no hay Beta disponible)."""
    return "<hr>".join(bloque for bloque in bloques if bloque)


def _renderizar_heatmap_con_tooltips(
    df_resumen: pd.DataFrame,
    columnas_pct: list,
    columnas_secuenciales: list,
    formato: dict,
    construir_tooltip,
) -> str:
    """Arma el heatmap de desempeño completo como una tabla HTML propia
    (en vez de un Styler + st.dataframe), para poder poner un tooltip con
    :hover en el nombre de cada ticker DENTRO de la misma tabla —
    st.dataframe no permite HTML arbitrario en las celdas, es justo lo que
    forzó a la versión anterior a mostrar los tooltips en una tabla aparte.

    Reproduce a mano el color de fondo que antes hacía
    Styler.background_gradient(): divergente compartido (-max_abs,
    +max_abs, calculado sobre TODAS las columnas de columnas_pct juntas)
    para columnas_pct, y secuencial POR COLUMNA (su propio min/max — mismo
    comportamiento por defecto de Styler cuando no se le pasa vmin/vmax)
    para columnas_secuenciales. Las filas atrasadas (`_atrasado_bool`)
    grisan texto y anulan el color de fondo, igual que antes.

    `construir_tooltip(ticker, fila)` arma el contenido HTML del tooltip
    para esa fila — lo decide quien llama, porque el IPSA y el Dow Jones
    quieren contenido distinto (el Dow Jones no conecta con el modelo de
    atribución del IPSA, que no le aplica)."""
    max_abs = df_resumen[columnas_pct].abs().max().max()
    max_abs = max_abs if pd.notna(max_abs) and max_abs > 0 else 1
    minmax_secuencial = {
        col: (df_resumen[col].min(), df_resumen[col].max()) for col in columnas_secuenciales
    }
    columnas_mostradas = [c for c in df_resumen.columns if c != "_atrasado_bool"]

    filas_html = []
    for ticker, fila in df_resumen.iterrows():
        atrasado = bool(fila["_atrasado_bool"])
        estilo_texto = "color:#898781;" if atrasado else ""

        tooltip_contenido = construir_tooltip(ticker, fila)
        celda_ticker = tooltip_html(ticker, tooltip_contenido) if tooltip_contenido else ticker
        celdas = [f"<td style='padding:6px 10px; white-space:nowrap; {estilo_texto}'>{celda_ticker}</td>"]

        for columna in columnas_mostradas:
            valor = fila[columna]
            fondo = ""
            if not atrasado:
                color = None
                if columna in columnas_pct:
                    color = _color_gradiente_hex(CMAP_DIVERGENTE, valor, -max_abs, max_abs)
                elif columna in columnas_secuenciales:
                    vmin, vmax = minmax_secuencial[columna]
                    color = _color_gradiente_hex(CMAP_SECUENCIAL, valor, vmin, vmax)
                if color:
                    fondo = f"background-color:{color};"
            if columna in formato and pd.notna(valor):
                texto = formato[columna].format(valor)
            elif pd.isna(valor):
                texto = "—"
            else:
                texto = str(valor)
            celdas.append(f"<td style='padding:6px 10px; white-space:nowrap; {estilo_texto}{fondo}'>{texto}</td>")

        filas_html.append(f"<tr>{''.join(celdas)}</tr>")

    encabezado = "".join(
        f"<th style='text-align:left; padding:6px 10px; border-bottom:1px solid #4a4a4a; white-space:nowrap;'>{c}</th>"
        for c in ["Ticker"] + columnas_mostradas
    )

    # Nota deliberada: NO se envuelve la tabla en un <div style="overflow-x:
    # auto"> (el patrón habitual para tablas anchas). Un div con overflow-x
    # distinto de "visible" fuerza a overflow-y a pasar a "auto" también
    # (regla del spec CSS: si un eje es "visible" y el otro no, el eje
    # "visible" se fuerza a "auto") — eso recorta verticalmente cualquier
    # tooltip position:absolute que intente sobresalir de esa fila,
    # confirmado con un screenshot real (el tooltip de AGUAS-A aparecía con
    # las primeras líneas cortadas). Sin el wrapper, la tabla puede empujar
    # el ancho de la página en vez de scrollear horizontalmente sola — un
    # trade-off aceptado a propósito para que los tooltips no se corten.
    return (
        TOOLTIP_CSS
        + "<table style='width:100%; border-collapse:collapse; font-size:0.88rem;'>"
        + f"<tr>{encabezado}</tr>"
        + "".join(filas_html)
        + "</table>"
    )


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

        # Alpha de Jensen (simplificado, sin la segunda etapa cross-sectional
        # del APT/CAPM académico): compara el retorno REALIZADO del último
        # año contra el mínimo que el CAPM decía que debía rendir dado su
        # riesgo. Usa la misma ventana de retornos diarios ("conjunto") que
        # Beta, para que ambos números describan el mismo período.
        retorno_real_1y = (
            ((1 + conjunto["ticker"]).prod() - 1) * 100
            if len(conjunto) >= 30
            else None
        )
        alpha = (
            retorno_real_1y - capm_local
            if retorno_real_1y is not None and capm_local is not None
            else None
        )

        # Sharpe y Treynor: mismos ingredientes ya calculados arriba
        # (retorno realizado del último año, Rf, volatilidad, Beta), sin
        # ninguna consulta ni cálculo nuevo.
        exceso_retorno = (
            retorno_real_1y - rf_cl
            if retorno_real_1y is not None and rf_cl is not None
            else None
        )
        sharpe = (
            exceso_retorno / volatilidad_anualizada
            if exceso_retorno is not None and volatilidad_anualizada not in (None, 0)
            else None
        )
        treynor = (
            exceso_retorno / beta
            if exceso_retorno is not None and beta not in (None, 0)
            else None
        )

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
            "Sharpe": sharpe,
            "Treynor (%)": treynor,
            "Alpha (%)": alpha,
            "Última actualización": ultima_fecha_real.strftime("%Y-%m-%d"),
            "Atraso": _texto_atraso(atrasado, dias_habiles_atraso),
            "_atrasado_bool": atrasado,
        })

    return pd.DataFrame(filas).set_index("Ticker")


@st.cache_data(ttl=3600)
def calcular_resumen_dow_jones(df_todas: pd.DataFrame, df_macro: pd.DataFrame) -> pd.DataFrame:
    """% de cambio 1D/1W/1M/YTD, Beta (vs el propio índice Dow Jones, que sí
    tiene ticker en Yahoo Finance a diferencia del IPSA), volatilidad y CAPM
    para cada acción del Dow Jones. Mismo criterio que calcular_resumen_ipsa,
    pero sin CRP: no aplica una prima de riesgo país de EEUU respecto a sí
    mismo, así que el CAPM acá es una sola versión (sin la distinción
    "local" vs. "+ CRP" del IPSA)."""
    df_todas = df_todas.assign(fecha=pd.to_datetime(df_todas["fecha"]))

    datos_proxy = (
        df_todas[df_todas["ticker"] == TICKER_DOW_JONES]
        .sort_values("fecha")
        .set_index("fecha")
    )
    proxy = datos_proxy["precio_cierre"]
    retornos_proxy = proxy.pct_change()

    # Rf de corto plazo para EEUU: Effective Federal Funds Rate — el
    # análogo de EEUU al PDBC que se usa como Rf de corto plazo en el CAPM
    # del IPSA.
    tpm_eeuu = (
        df_macro[df_macro["nombre"] == "Tasa de política monetaria de EEUU (Effective Federal Funds Rate)"]
        .sort_values("fecha")["valor"]
    )
    rf_eeuu = float(tpm_eeuu.iloc[-1]) if len(tpm_eeuu) else None

    retornos_proxy_reales = calcular_retornos_reales(datos_proxy["precio_cierre"], datos_proxy["volumen"]).dropna()
    retorno_anual_mercado = (
        retornos_proxy_reales.mean() * 252 * 100 if len(retornos_proxy_reales) >= 30 else None
    )
    prima_mercado = (
        retorno_anual_mercado - rf_eeuu
        if retorno_anual_mercado is not None and rf_eeuu is not None
        else None
    )

    filas = []
    for ticker in TICKERS_DOW_JONES:
        serie = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")["precio_cierre"]
        )
        if len(serie) < 2:
            continue

        fecha_ultima = serie.index[-1]
        cambios = calcular_cambios_periodo(serie)

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

        # Mismo criterio de "dato atrasado" que el IPSA (precio congelado,
        # no solo la última fila descargada).
        cambia = serie.ne(serie.shift(1))
        cambia.iloc[0] = True
        ultima_fecha_real = serie.index[cambia][-1]

        hoy = pd.Timestamp.now().normalize()
        dias_habiles_atraso = int(np.busday_count(ultima_fecha_real.date(), hoy.date()))
        atrasado = dias_habiles_atraso > 5

        retornos_reales_ticker = retornos_ticker[cambia].dropna()
        volatilidad_anualizada = (
            retornos_reales_ticker.tail(VENTANA_VOLATILIDAD).std() * (252 ** 0.5) * 100
            if len(retornos_reales_ticker) >= VENTANA_VOLATILIDAD
            else None
        )

        capm = (
            rf_eeuu + beta * prima_mercado
            if beta is not None and rf_eeuu is not None and prima_mercado is not None
            else None
        )

        # Alpha de Jensen (ver misma nota en calcular_resumen_ipsa): retorno
        # realizado del último año menos el mínimo que el CAPM exigía dado
        # el riesgo (Beta) de esta acción.
        retorno_real_1y = (
            ((1 + conjunto["ticker"]).prod() - 1) * 100
            if len(conjunto) >= 30
            else None
        )
        alpha = (
            retorno_real_1y - capm
            if retorno_real_1y is not None and capm is not None
            else None
        )

        # Sharpe y Treynor (ver misma nota en calcular_resumen_ipsa).
        exceso_retorno = (
            retorno_real_1y - rf_eeuu
            if retorno_real_1y is not None and rf_eeuu is not None
            else None
        )
        sharpe = (
            exceso_retorno / volatilidad_anualizada
            if exceso_retorno is not None and volatilidad_anualizada not in (None, 0)
            else None
        )
        treynor = (
            exceso_retorno / beta
            if exceso_retorno is not None and beta not in (None, 0)
            else None
        )

        beta_ajustada = (2 / 3) * beta + (1 / 3) * 1 if beta is not None else None

        filas.append({
            "Ticker": ticker,
            "1D %": cambios["1D %"],
            "1W %": cambios["1W %"],
            "1M %": cambios["1M %"],
            "YTD %": cambios["YTD %"],
            "Beta": beta,
            "Beta ajustada": beta_ajustada,
            "Volatilidad anualizada (%)": volatilidad_anualizada,
            "CAPM (%)": capm,
            "Sharpe": sharpe,
            "Treynor (%)": treynor,
            "Alpha (%)": alpha,
            "Última actualización": ultima_fecha_real.strftime("%Y-%m-%d"),
            "Atraso": _texto_atraso(atrasado, dias_habiles_atraso),
            "_atrasado_bool": atrasado,
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
        datos = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")
        )
        datos = datos[datos.index >= fecha_corte]
        retornos_por_ticker[ticker.replace(".SN", "")] = calcular_retornos_reales(datos["precio_cierre"], datos["volumen"])

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
        datos = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")
        )
        datos = datos[datos.index >= fecha_corte]
        r = calcular_retornos_reales(datos["precio_cierre"], datos["volumen"]).dropna()
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
    datos_ech = (
        df_todas[df_todas["ticker"] == TICKER_PROXY_IPSA]
        .sort_values("fecha")
        .set_index("fecha")
    )
    retornos_reales = calcular_retornos_reales(datos_ech["precio_cierre"], datos_ech["volumen"]).dropna()

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
        datos = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")
        )
        retornos_por_ticker[ticker.replace(".SN", "")] = calcular_retornos_reales(datos["precio_cierre"], datos["volumen"])

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
def calcular_retornos_mensuales_ipsa(df_todas: pd.DataFrame) -> pd.DataFrame:
    """Retornos mensuales "reales" para las 30 acciones del IPSA: se componen
    los retornos diarios reales (excluyendo días de precio congelado) dentro
    de cada mes calendario, así que un día congelado no aporta un 0% falso a
    ningún mes."""
    df_todas = df_todas.assign(fecha=pd.to_datetime(df_todas["fecha"]))

    retornos_por_ticker = {}
    for ticker in TICKERS_IPSA:
        datos = (
            df_todas[df_todas["ticker"] == ticker]
            .sort_values("fecha")
            .set_index("fecha")
        )
        retornos_reales = calcular_retornos_reales(datos["precio_cierre"], datos["volumen"]).dropna()
        if retornos_reales.empty:
            continue
        mensual = retornos_reales.groupby(retornos_reales.index.to_period("M")).apply(
            lambda x: (1 + x).prod() - 1
        )
        retornos_por_ticker[ticker.replace(".SN", "")] = mensual

    return pd.DataFrame(retornos_por_ticker)


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
    tab_premercado, tab_macro, tab_acciones, tab_atribucion, tab_acciones_dow, tab_riesgo,
    tab_benchmark, tab_laboratorio,
) = st.tabs([
    "Brief Premercado", "Indicadores macro", "Acciones IPSA", "Atribución IPSA", "Acciones Dow Jones",
    "Riesgo", "Benchmark", "Laboratorio Financiero",
])

# --- Tab 0: Brief Premercado ---
ETIQUETA_EN_POR_ES = {
    "S&P 500": "S&P 500",
    "Dow Jones": "Dow Jones",
    "Cobre": "Copper",
    "Petróleo WTI": "WTI Oil",
    "Bono UST 10 años": "UST 10Y Bond",
    "TPM EEUU": "US Fed Funds Rate",
    "IPSA (proxy ECH)": "IPSA (ECH proxy)",
    "TPM Chile": "Chile Policy Rate",
    "IPC (inflación anual)": "CPI (annual inflation)",
    "Imacec": "Imacec (economic activity index)",
    "Tasa de desempleo": "Unemployment rate",
}

ORGANISMO_EN_POR_TIPO = {
    "RPM": "Central Bank of Chile", "FOMC": "US Federal Reserve", "IPC": "INE Chile",
    "IMACEC": "Central Bank of Chile", "OPEP+": "OPEC+",
}
DESCRIPCION_EN_POR_TIPO = {
    "RPM": "Monetary Policy Meeting",
    "FOMC": "FOMC Meeting (Fed rate decision)",
    "OPEP+": "OPEC+ ministerial meeting",
}


def _evento_en_ingles(evento) -> str:
    """Traduce la descripción de un evento del calendario económico (los
    datos en calendario_economico.py quedan en español porque también los
    lee el resto del código internamente — la traducción es solo para
    mostrarla en esta pestaña)."""
    if evento.tipo in ("IPC", "IMACEC"):
        periodo = evento.descripcion.split("(")[-1].rstrip(")")
        nombre = "CPI release" if evento.tipo == "IPC" else "Imacec release"
        return f"{nombre} ({periodo})"
    return DESCRIPCION_EN_POR_TIPO.get(evento.tipo, evento.descripcion)


with tab_premercado:
    st.caption(
        "This is the only tab shown in English — the rest of the dashboard is in "
        "Spanish. Meant to be read before the Santiago Stock Exchange opens, quickly, "
        "not for live analysis."
    )

    st.subheader("Key indicators")

    try:
        df_macro = cargar_series_macro()
        df_acciones = cargar_precios_acciones()
        indicadores = calcular_resumen_mercado(df_macro, df_acciones)

        # En filas de a INDICADORES_POR_FILA (no todos en una sola fila): con
        # 11 indicadores y etiquetas largas (ej. "IPSA (ECH proxy)",
        # "Unemployment rate"), una sola fila de columnas angostas cortaba
        # tanto las etiquetas como los valores.
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
                    etiqueta_en = ETIQUETA_EN_POR_ES.get(ind["etiqueta"], ind["etiqueta"])
                    unidad_en = ind["unidad"].replace("barril", "barrel")
                    if ind["resultado"]:
                        valor, cambio_pct, fecha, cambio_absoluto = ind["resultado"]
                        valor_texto = f"{valor:,.2f}" + (f" {unidad_en}" if unidad_en else "")
                        # Si el indicador ya es una tasa/porcentaje (ej. TPM,
                        # inflación anual), mostrar puntos porcentuales: el "%
                        # de cambio" de una tasa (ej. de 4,34% a 3,52% = -18,8%)
                        # es confuso, lo esperable es el cambio en pp (-0,82 pp).
                        delta_texto = f"{cambio_absoluto:+.2f} pp" if ind["unidad"] == "%" else f"{cambio_pct:+.2f}%"
                        st.metric(etiqueta_en, valor_texto, delta_texto)
                        st.caption(f"as of {pd.Timestamp(fecha).strftime('%Y-%m-%d')}")
                    else:
                        st.metric(etiqueta_en, "—")
                        st.caption("not enough data")

        spread_2s10s = calcular_spread_2s10s(df_macro)
        if spread_2s10s:
            fecha_spread = pd.Timestamp(spread_2s10s["fecha"]).strftime("%Y-%m-%d")
            texto_spread = (
                f"2s10s spread (UST10Y − UST2Y): {spread_2s10s['spread']:+.2f} pp "
                f"(UST10Y {spread_2s10s['ust10']:.2f}% − UST2Y {spread_2s10s['ust2']:.2f}%) as of {fecha_spread}."
            )
            if spread_2s10s["invertida"]:
                st.error(f"🔻 **Inverted curve.** {texto_spread}")
            else:
                st.success(texto_spread)
            st.caption(
                "An inverted curve (negative 2s10s spread) has historically been associated "
                "with a higher probability of a US recession over the following 12-24 months "
                "— it's a historical correlation, not a guaranteed prediction, and it has "
                "given false signals in the past."
            )

        breakeven = calcular_serie_inflacion_breakeven(df_macro)
        if len(breakeven) >= 2:
            valor_actual = float(breakeven.iloc[-1])
            cambio_pp = valor_actual - float(breakeven.iloc[-2])
            fecha_breakeven = pd.Timestamp(breakeven.index[-1]).strftime("%Y-%m-%d")
            st.metric(
                "Breakeven inflation (BCP 10Y − BCU 10Y)",
                f"{valor_actual:.2f} pp",
                f"{cambio_pp:+.2f} pp",
            )
            st.caption(
                f"as of {fecha_breakeven}. This is the inflation the market has priced into "
                "both bonds (nominal BCP rate minus real BCU rate, same issuer and tenor) — "
                "not an official forecast from anyone."
            )

    except Exception as e:
        st.error(f"Could not load the international summary: {e}")

    st.divider()
    st.subheader("Economic calendar — next 7 days")

    try:
        hoy = date.today()
        eventos_semana = proximos_eventos(hoy, dias=7)

        if not eventos_semana:
            st.info("No events scheduled in the next 7 days.")
        else:
            for evento in eventos_semana:
                indicador = INDICADOR_POR_TIPO[evento.tipo]
                if evento.fecha_inicio == evento.fecha_fin:
                    fecha_texto = evento.fecha_inicio.strftime("%Y-%m-%d")
                else:
                    fecha_texto = (
                        f"{evento.fecha_inicio.strftime('%b %d')} to "
                        f"{evento.fecha_fin.strftime('%Y-%m-%d')}"
                    )
                nota_estimado = "" if evento.confirmado else " *(estimated date, not explicitly confirmed)*"
                st.markdown(
                    f"<span style='background-color:{indicador['color']}; color:white; "
                    f"padding:2px 8px; border-radius:4px; font-weight:700; font-size:0.85em'>"
                    f"{indicador['etiqueta']}</span> &nbsp; **{fecha_texto}** — "
                    f"{ORGANISMO_EN_POR_TIPO.get(evento.tipo, indicador['organismo'])}: "
                    f"{_evento_en_ingles(evento)}{nota_estimado}",
                    unsafe_allow_html=True,
                )

        st.caption(
            f"Calendar verified as of {CALENDARIO_VERIFICADO_AL.strftime('%Y-%m-%d')}. "
            "The 2027 Monetary Policy Meeting calendar is published in September 2026, "
            "and the 2027 FOMC calendar in December 2026 — update then."
        )
        st.caption(
            "OPEC+ meetings don't follow a fixed annual calendar (unlike central banks): "
            "since 2024 they've been confirmed only weeks in advance, so this calendar may "
            "not include meetings that haven't been announced yet."
        )

    except Exception as e:
        st.error(f"Could not load the economic calendar: {e}")

    st.divider()
    st.subheader("Today's summary")

    try:
        df_brief = cargar_brief_diario()

        if df_brief.empty:
            st.info(
                "The daily summary hasn't been generated yet. Run "
                "scripts/generar_brief.py (requires GEMINI_API_KEY) — it's generated "
                "once a day as part of the cron job, not on every visit."
            )
        else:
            fila_brief = df_brief.iloc[0]
            st.caption(
                f"Generated on {pd.Timestamp(fila_brief['generado_en']).strftime('%Y-%m-%d %H:%M')} "
                f"for {pd.Timestamp(fila_brief['fecha']).strftime('%Y-%m-%d')}."
            )
            st.markdown(_escapar_markdown_matematico(fila_brief["contenido"]))
            st.warning(
                "⚠️ Summary generated automatically by AI from public headlines — it may "
                "contain errors or inaccuracies, and does not constitute investment advice."
            )

    except Exception as e:
        st.error(f"Could not load the daily summary: {e}")

    st.divider()

    with st.expander("Relevant headlines (detail)"):
        try:
            df_noticias = cargar_noticias()

            if df_noticias.empty:
                st.info("No headlines downloaded yet. Run scripts/actualizar_noticias.py.")
            else:
                df_noticias = df_noticias.assign(fecha_publicacion=pd.to_datetime(df_noticias["fecha_publicacion"]))
                df_noticias["dia"] = df_noticias["fecha_publicacion"].dt.date

                # df_noticias ya viene ordenado desc por fecha_publicacion (ver cargar_noticias),
                # así que agrupar sin volver a ordenar deja primero el día más reciente.
                for dia, grupo in df_noticias.groupby("dia", sort=False):
                    st.markdown(f"**{dia.strftime('%Y-%m-%d')}**")
                    for _, fila in grupo.iterrows():
                        hora = fila["fecha_publicacion"].strftime("%H:%M")
                        titulo_seguro = _escapar_markdown_matematico(fila["titulo"])
                        st.markdown(f"- {hora} · *{fila['fuente']}* — [{titulo_seguro}]({fila['link']})")

        except Exception as e:
            st.error(f"Could not load headlines: {e}")

    st.divider()
    st.caption(
        "**Methodology note.** The summary above is generated automatically once a day "
        "from the \"Key indicators\" above and the headlines in the detail section — it "
        "doesn't claim specific causality between a given news item and a price move. "
        "Headlines are shown in their original language (mostly Spanish for Chilean "
        "sources, English for Yahoo Finance) — they aren't translated, so the quoted "
        "headline matches exactly what each outlet published. \"La Tercera Pulso\" and "
        "\"Emol Economía\" don't have a working RSS feed of their own today, so their "
        "headlines come via a site-filtered Google News search instead — not the "
        "outlet's official feed."
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

        # Los indicadores de "Importante" del Brief Premercado que vienen de
        # precios de acciones (S&P 500, Dow Jones, Petróleo WTI, IPSA) viven
        # en precios_acciones, no en series_macro — se agregan acá con el
        # mismo formato nombre/fecha/valor para que todos los indicadores de
        # esa sección también se puedan explorar en este selector.
        df_acciones_indicadores = cargar_precios_acciones()
        for etiqueta, tipo, clave, _unidad in INDICADORES_PREMERCADO:
            if tipo != "accion":
                continue
            serie_accion = (
                df_acciones_indicadores[df_acciones_indicadores["ticker"] == clave]
                .sort_values("fecha")[["fecha", "precio_cierre"]]
                .rename(columns={"precio_cierre": "valor"})
                .assign(nombre=etiqueta)
            )
            if not serie_accion.empty:
                df_macro = pd.concat([df_macro, serie_accion[["nombre", "fecha", "valor"]]], ignore_index=True)

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
        _mostrar_banner_apagon(df_acciones, TICKERS_IPSA, "las acciones del IPSA")

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

        formato = {col: "{:+.2f}%" for col in columnas_pct}
        formato["Beta"] = "{:.2f}"
        formato["Beta ajustada"] = "{:.2f}"
        formato["Volatilidad anualizada (%)"] = "{:.2f}%"
        formato["CAPM local (%)"] = "{:.2f}%"
        formato["CAPM + CRP (%)"] = "{:.2f}%"
        formato["Sharpe"] = "{:.2f}"
        formato["Treynor (%)"] = "{:+.2f}%"
        formato["Alpha (%)"] = "{:+.2f}%"

        def _tooltip_ipsa(ticker: str, fila: pd.Series) -> str:
            beta = fila["Beta"] if pd.notna(fila["Beta"]) else None
            beta_ajustada = fila["Beta ajustada"] if pd.notna(fila["Beta ajustada"]) else None
            capm_local_valor = fila["CAPM local (%)"] if pd.notna(fila["CAPM local (%)"]) else None
            return _armar_tooltip([
                f"<b>{nombre_completo(ticker)}</b>",
                explicacion_rendimiento(fila["1M %"] if pd.notna(fila["1M %"]) else None),
                explicacion_beta(beta, beta_ajustada),
                explicacion_capm(
                    capm_local_valor,
                    fila["CAPM + CRP (%)"] if pd.notna(fila["CAPM + CRP (%)"]) else None,
                ),
                explicacion_volatilidad(
                    fila["Volatilidad anualizada (%)"] if pd.notna(fila["Volatilidad anualizada (%)"]) else None
                ),
                explicacion_sharpe(fila["Sharpe"] if pd.notna(fila["Sharpe"]) else None),
                explicacion_treynor(fila["Treynor (%)"] if pd.notna(fila["Treynor (%)"]) else None),
                explicacion_alfa(
                    fila["Alpha (%)"] if pd.notna(fila["Alpha (%)"]) else None,
                    (capm_local_valor + fila["Alpha (%)"]) if capm_local_valor is not None and pd.notna(fila["Alpha (%)"]) else None,
                    capm_local_valor,
                ),
                explicacion_atribucion(beta),
            ])

        st.markdown(
            _renderizar_heatmap_con_tooltips(
                df_resumen, columnas_pct,
                ["Volatilidad anualizada (%)", "Sharpe", "Treynor (%)", "Alpha (%)"] + columnas_capm,
                formato, _tooltip_ipsa,
            ),
            unsafe_allow_html=True,
        )
        st.caption(
            "Volatilidad anualizada: rolling 21 días hábiles de retornos diarios × √252, "
            "excluyendo días de precio congelado (mismo criterio que \"Atraso\"). "
            "Beta calculado sobre retornos diarios del último año, respecto al ETF ECH "
            "(proxy del IPSA — el índice no tiene ticker propio en Yahoo Finance). "
            "\"Beta ajustada\" = (2/3) × Beta + (1/3) × 1 (ajuste tipo Blume): tira la beta "
            "cruda hacia 1, el valor \"promedio de mercado\" de largo plazo, para corregir "
            "el sesgo de que betas históricas muy altas o muy bajas tienden a acercarse a 1 "
            "en períodos futuros. "
            "La columna \"Atraso\" muestra \"Precio congelado — N días hábiles\" cuando Yahoo "
            "Finance no refrescó el precio de ese ticker hace más de 5 días hábiles (contados "
            "desde la última fecha con cambio real de precio) — el % de cambio mostrado no es "
            "confiable en ese caso. "
            "\"Sharpe\" = (retorno realizado del último año − Rf) / volatilidad: retorno extra "
            "por unidad de riesgo TOTAL. \"Treynor\" = (retorno realizado − Rf) / Beta: retorno "
            "extra por unidad de riesgo NO diversificable, asumiendo que el resto ya se "
            "diversificó teniendo otras acciones. "
            "\"Alpha\" (Jensen, simplificado): retorno realizado del último año menos el mínimo "
            "que el CAPM exigía dado el riesgo de esa acción — no es la versión académica "
            "completa (le falta la segunda etapa que estima el precio de riesgo de cada factor), "
            "así que describe lo que ya pasó, no predice lo que va a pasar. "
            "Pasa el mouse sobre el nombre de cada ticker para ver el "
            "nombre completo de la empresa y una explicación en simple de su rendimiento "
            "reciente, Beta, CAPM, volatilidad, Sharpe, Treynor, Alpha, y su relación con el "
            "modelo de atribución multi-factor (pestaña \"Atribución IPSA\") — con los números "
            "reales de esa fila."
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

# --- Tab 2a: Atribución multi-factor del IPSA (proxy ECH) ---
COLOR_POR_COMPONENTE_ATRIBUCION = {
    "Alfa (intercepto)": "#8a8a8a",
    "Cobre": "#eda100",
    "S&P 500": "#2a78d6",
    "USD/CLP": "#1baf7a",
    "Residual": "#eb6834",
}


@st.cache_data(ttl=3600)
def calcular_atribucion_ipsa_cacheada(df_acciones: pd.DataFrame, df_macro: pd.DataFrame) -> pd.DataFrame:
    return calcular_atribucion_ipsa(df_acciones, df_macro)


@st.cache_data(ttl=3600)
def validar_atribucion_out_of_sample_cacheada(df_acciones: pd.DataFrame, df_macro: pd.DataFrame) -> dict:
    return validar_atribucion_out_of_sample(df_acciones, df_macro)


with tab_atribucion:
    st.subheader("Atribución del Movimiento de Hoy")
    st.caption(
        "Modelo de 3 factores: R_ECH = α + β_cobre·R_cobre + β_SP500·R_SP500 + "
        "β_USDCLP·R_USDCLP + ε, sobre el proxy ECH del IPSA (no un ticker `.SN`, "
        "así que no le afecta el apagón de Yahoo Finance documentado para el "
        "mercado chileno — verificado con datos reales antes de construir esto: "
        "ECH tiene precio y volumen frescos y distintos cada rueda). Los β se "
        "re-estiman cada día con los 120 días hábiles ANTERIORES (sin el día "
        "actual) — walk-forward, sin mirar el futuro."
    )

    try:
        df_acciones_atrib = cargar_precios_acciones()
        df_macro_atrib = cargar_series_macro()

        df_atribucion = calcular_atribucion_ipsa_cacheada(df_acciones_atrib, df_macro_atrib)

        if len(df_atribucion) == 0:
            st.warning("No hay suficiente historia común entre ECH, cobre, S&P 500 y USD/CLP todavía.")
        else:
            fila_hoy = df_atribucion.iloc[-1]
            fecha_hoy = df_atribucion.index[-1]

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Retorno real de ECH", f"{fila_hoy['retorno_ech']:+.2%}")
            col_m2.metric("Retorno predicho (3 factores)", f"{fila_hoy['retorno_predicho']:+.2%}")
            col_m3.metric("Residual", f"{fila_hoy['residual']:+.2%}")
            st.caption(f"Última sesión con datos: {fecha_hoy.strftime('%Y-%m-%d')}.")

            componentes = {
                "Alfa (intercepto)": fila_hoy["alfa"],
                "Cobre": fila_hoy["contrib_cobre"],
                "S&P 500": fila_hoy["contrib_sp500"],
                "USD/CLP": fila_hoy["contrib_usdclp"],
                "Residual": fila_hoy["residual"],
            }
            fig_atrib = go.Figure()
            for nombre, valor in componentes.items():
                fig_atrib.add_trace(go.Bar(
                    x=["Retorno de hoy"], y=[valor * 100], name=nombre,
                    marker_color=COLOR_POR_COMPONENTE_ATRIBUCION[nombre],
                ))
            fig_atrib.add_hline(
                y=fila_hoy["retorno_ech"] * 100, line_dash="dash", line_color="#2b2b2b",
                annotation_text=f"Retorno real total: {fila_hoy['retorno_ech']:+.2%}",
            )
            fig_atrib.update_layout(
                barmode="relative", title="Descomposición del retorno de hoy (%)",
                yaxis_title="Contribución (%)",
            )
            st.plotly_chart(fig_atrib, use_container_width=True)
            st.caption(
                "Las barras apiladas suman exactamente el retorno real de ECH (línea "
                "punteada) — el residual no es un error de cálculo, es la definición "
                "de \"lo que estos 3 factores no explican\"."
            )

            if pd.notna(fila_hoy["z_residual"]) and abs(fila_hoy["z_residual"]) > 2:
                st.error(
                    "⚠️ **Movimiento local inusual, no explicado por factores globales.** "
                    f"El residual de hoy tiene z = {fila_hoy['z_residual']:+.2f} contra la "
                    "distribución de los últimos 120 días hábiles — algo más allá de cobre, "
                    "S&P 500 o el tipo de cambio está moviendo el mercado chileno hoy."
                )

            st.subheader("Z-scores (vs. últimos 120 días hábiles)")
            df_z = pd.DataFrame({
                "Factor": ["Cobre", "S&P 500", "USD/CLP", "Residual"],
                "Retorno de hoy": [
                    fila_hoy["retorno_cobre"], fila_hoy["retorno_sp500"],
                    fila_hoy["retorno_usdclp"], fila_hoy["residual"],
                ],
                "Z-score": [
                    fila_hoy["z_cobre"], fila_hoy["z_sp500"],
                    fila_hoy["z_usdclp"], fila_hoy["z_residual"],
                ],
            }).set_index("Factor")
            st.dataframe(
                df_z.style.format({"Retorno de hoy": "{:+.2%}", "Z-score": "{:+.2f}"}),
                use_container_width=True,
            )
            st.caption(
                "Z-score = (valor de hoy − media de los 120 días hábiles anteriores) / "
                "desviación estándar de esos mismos 120 días — mismo criterio walk-forward "
                "que los β: la distribución de referencia nunca incluye el día que se está "
                "evaluando."
            )

            st.subheader("Historial del residual")
            fig_residual = px.line(
                df_atribucion.reset_index(), x="fecha", y="residual",
                title="Residual diario de la atribución (todo el histórico disponible)",
            )
            fig_residual.add_hline(y=0, line_color="#898781")
            fig_residual.update_yaxes(tickformat=".1%", title="Residual")
            st.plotly_chart(fig_residual, use_container_width=True)
            st.caption(
                "Picos hacia arriba o abajo son ruedas donde ECH se movió más de lo que "
                "cobre, S&P 500 y USD/CLP explican — no necesariamente \"solo lo local\", "
                "ver nota metodológica más abajo."
            )

            st.subheader("Validación out-of-sample")
            validacion = validar_atribucion_out_of_sample_cacheada(df_acciones_atrib, df_macro_atrib)
            if not validacion["suficientes_datos"]:
                st.warning("No hay suficiente historia para dividir en in-sample / out-of-sample todavía.")
            else:
                col_v1, col_v2, col_v3, col_v4 = st.columns(4)
                col_v1.metric("R² (out-of-sample)", f"{validacion['r2_oos']:.3f}" if validacion["r2_oos"] is not None else "—")
                col_v2.metric(
                    "Correlación predicho vs. real",
                    f"{validacion['correlacion_oos']:.3f}" if validacion["correlacion_oos"] is not None else "—",
                )
                col_v3.metric("Días in-sample", f"{validacion['n_in_sample']:,}")
                col_v4.metric("Días out-of-sample", f"{validacion['n_out_of_sample']:,}")
                st.caption(
                    f"Período out-of-sample: {validacion['fecha_inicio_oos']} a "
                    f"{validacion['fecha_fin_oos']}. Los β se estiman **una sola vez** con "
                    "el primer ~70% cronológico de los datos (in-sample) y se aplican sin "
                    "volver a ajustar sobre el 30% restante — el resultado se reporta tal "
                    "cual sale, sea alto o bajo: un R² o correlación bajos también son una "
                    "conclusión válida sobre qué tan bien generaliza este modelo de 3 "
                    "factores, no un motivo para ocultarlo."
                )

            st.info(
                "**Nota metodológica.** Modelo de 3 factores (cobre, S&P 500, USD/CLP) — "
                "no captura todo lo que mueve al IPSA, solo estos tres canales globales "
                "específicos. **Multicolinealidad posible:** cobre y S&P 500 suelen moverse "
                "juntos en episodios de apetito por riesgo global, lo que puede inflar el "
                "error estándar de sus β individuales y hacer inestable la atribución entre "
                "ambos en algunos períodos (la suma total sigue siendo válida aunque el "
                "reparto entre los dos sea ruidoso). **Ventana de 120 días hábiles:** es una "
                "elección con trade-off — una ventana más corta reacciona más rápido a "
                "cambios de régimen pero con β más ruidosos (menos observaciones); una más "
                "larga da β más estables pero más lentos para adaptarse. **El residual "
                "captura TODO lo que estos 3 factores específicos no explican** — no es "
                "necesariamente \"solo noticias locales\": incluye cualquier otro factor "
                "global no incluido en el modelo (ej. tasas de interés, otros commodities, "
                "flujos de fondos EM) además de eventos genuinamente locales."
            )

    except Exception as e:
        st.error(f"No se pudo calcular la atribución del IPSA: {e}")

# --- Tab 2b: Precios de acciones del Dow Jones ---
with tab_acciones_dow:
    try:
        df_acciones = cargar_precios_acciones()

        tickers_disponibles_dow = TICKERS_DOW_JONES
        tickers_elegidos_dow = st.multiselect(
            "Elige acciones a comparar", tickers_disponibles_dow,
            default=TICKERS_DOW_JONES_PRINCIPALES, key="dow_multiselect",
        )

        df_filtrado_dow = df_acciones[df_acciones["ticker"].isin(tickers_elegidos_dow)]

        normalizar_dow = st.checkbox("Normalizar a base 100", value=True, key="dow_normalizar")

        if normalizar_dow:
            df_filtrado_dow = df_filtrado_dow.copy()
            df_filtrado_dow["precio_normalizado"] = df_filtrado_dow.groupby("ticker")["precio_cierre"].transform(
                lambda serie: serie / serie.iloc[0] * 100
            )
            columna_precio_dow = "precio_normalizado"
            titulo_precio_dow = "Desempeño relativo (base 100)"
        else:
            columna_precio_dow = "precio_cierre"
            titulo_precio_dow = "Precio de cierre histórico"

        fig_dow = px.line(
            df_filtrado_dow, x="fecha", y=columna_precio_dow, color="ticker",
            title=titulo_precio_dow
        )
        st.plotly_chart(fig_dow, use_container_width=True)

        st.subheader("Volumen transado")
        fig_vol_dow = px.bar(df_filtrado_dow, x="fecha", y="volumen", color="ticker")
        st.plotly_chart(fig_vol_dow, use_container_width=True)

        # --- Heatmap de desempeño: las 30 acciones del Dow Jones ---
        st.subheader("Resumen de desempeño — todas las acciones del Dow Jones")

        df_macro = cargar_series_macro()
        df_resumen_dow = calcular_resumen_dow_jones(df_acciones, df_macro)

        columnas_pct_dow = ["1D %", "1W %", "1M %", "YTD %"]

        formato_dow = {col: "{:+.2f}%" for col in columnas_pct_dow}
        formato_dow["Beta"] = "{:.2f}"
        formato_dow["Beta ajustada"] = "{:.2f}"
        formato_dow["Volatilidad anualizada (%)"] = "{:.2f}%"
        formato_dow["CAPM (%)"] = "{:.2f}%"
        formato_dow["Sharpe"] = "{:.2f}"
        formato_dow["Treynor (%)"] = "{:+.2f}%"
        formato_dow["Alpha (%)"] = "{:+.2f}%"

        def _tooltip_dow(ticker: str, fila: pd.Series) -> str:
            # Sin bloque de atribución: el modelo de atribución multi-factor
            # (market_data.calcular_atribucion_ipsa) es específico del mercado
            # chileno (cobre, S&P 500, USD/CLP explicando a ECH) y no le
            # aplica a una acción del Dow Jones de la misma forma.
            capm_valor = fila["CAPM (%)"] if pd.notna(fila["CAPM (%)"]) else None
            return _armar_tooltip([
                f"<b>{nombre_completo(ticker)}</b>",
                explicacion_rendimiento(fila["1M %"] if pd.notna(fila["1M %"]) else None),
                explicacion_beta(
                    fila["Beta"] if pd.notna(fila["Beta"]) else None,
                    fila["Beta ajustada"] if pd.notna(fila["Beta ajustada"]) else None,
                ),
                explicacion_capm(capm_valor),
                explicacion_volatilidad(
                    fila["Volatilidad anualizada (%)"] if pd.notna(fila["Volatilidad anualizada (%)"]) else None
                ),
                explicacion_sharpe(fila["Sharpe"] if pd.notna(fila["Sharpe"]) else None),
                explicacion_treynor(fila["Treynor (%)"] if pd.notna(fila["Treynor (%)"]) else None),
                explicacion_alfa(
                    fila["Alpha (%)"] if pd.notna(fila["Alpha (%)"]) else None,
                    (capm_valor + fila["Alpha (%)"]) if capm_valor is not None and pd.notna(fila["Alpha (%)"]) else None,
                    capm_valor,
                ),
            ])

        st.markdown(
            _renderizar_heatmap_con_tooltips(
                df_resumen_dow, columnas_pct_dow,
                ["Volatilidad anualizada (%)", "CAPM (%)", "Sharpe", "Treynor (%)", "Alpha (%)"],
                formato_dow, _tooltip_dow,
            ),
            unsafe_allow_html=True,
        )
        st.caption(
            "Volatilidad anualizada: rolling 21 días hábiles de retornos diarios × √252, "
            "excluyendo días de precio congelado (mismo criterio que \"Atraso\"). "
            "Beta calculado sobre retornos diarios del último año, respecto al índice Dow "
            "Jones (`^DJI` — a diferencia del IPSA, sí tiene ticker propio en Yahoo Finance, "
            "así que no hace falta un proxy). \"Beta ajustada\" = (2/3) × Beta + (1/3) × 1 "
            "(ajuste tipo Blume). CAPM = Rf (Effective Federal Funds Rate) + Beta × prima de "
            "mercado (retorno histórico anualizado del Dow Jones menos esa misma Rf) — a "
            "diferencia del IPSA, no se suma una prima de riesgo país: no aplica un CRP de "
            "EEUU respecto a sí mismo. "
            "La columna \"Atraso\" muestra \"Precio congelado — N días hábiles\" cuando Yahoo "
            "Finance no refrescó el precio de ese ticker hace más de 5 días hábiles (contados "
            "desde la última fecha con cambio real de precio) — el % de cambio mostrado no es "
            "confiable en ese caso. "
            "\"Sharpe\" = (retorno realizado del último año − Rf) / volatilidad. \"Treynor\" = "
            "(retorno realizado − Rf) / Beta. "
            "\"Alpha\" (Jensen, simplificado): retorno realizado del último año menos el mínimo "
            "que el CAPM exigía dado el riesgo de esa acción — describe lo que ya pasó, no "
            "predice lo que va a pasar. "
            "Pasa el mouse sobre el nombre de cada ticker para ver el "
            "nombre completo de la empresa y una explicación en simple de su rendimiento "
            "reciente, Beta, CAPM, volatilidad, Sharpe, Treynor y Alpha, con los números reales "
            "de esa fila."
        )

    except Exception as e:
        st.error(f"No se pudieron cargar los precios de acciones del Dow Jones: {e}")

# --- Tab 3: Riesgo ---
with tab_riesgo:
    try:
        df_acciones = cargar_precios_acciones()
        _mostrar_banner_apagon(df_acciones, TICKERS_IPSA, "las acciones del IPSA")

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


# --- Tab 10: Laboratorio Financiero ---
OPCIONES_LABORATORIO = sorted(set(
    TICKERS_LABORATORIO_AMPLIADO + TICKERS_DOW_JONES + TICKERS_MAGNIFICAS + TICKERS_EEUU_ADICIONALES
))
FECHA_FIN_TAREA = pd.Timestamp("2026-07-31")
NOMBRE_TREASURY_1Y = "Bono del Tesoro de EEUU a 1 año (Treasury Constant Maturity, H.15)"


@st.cache_data(ttl=3600)
def preparar_datos_lab_cacheado(df_precios: pd.DataFrame, tickers: tuple, fecha_inicio, fecha_fin) -> dict:
    return lab.preparar_datos_laboratorio(df_precios, list(tickers), fecha_inicio, fecha_fin)


@st.cache_data(ttl=3600)
def calcular_frontera_lab_cacheada(
    df_retornos: pd.DataFrame, rf: float, permitir_short: bool, limite_abs, restriccion_sectorial, usar_ingenua: bool,
) -> dict | None:
    cov_opt = None
    if usar_ingenua:
        cov_opt = lab.matriz_covarianza_diagonal(lab.matriz_covarianza_anual(df_retornos))
    return lab.calcular_frontera(
        df_retornos, rf, permitir_short=permitir_short, limite_abs=limite_abs,
        restriccion_sectorial=restriccion_sectorial, cov_optimizacion=cov_opt,
    )


@st.cache_data(ttl=3600)
def diagnosticar_cobertura_cacheado(df_precios: pd.DataFrame, tickers: tuple, fecha_inicio, fecha_fin) -> dict:
    return lab.diagnosticar_cobertura(df_precios, list(tickers), fecha_inicio, fecha_fin)


# --- Pregunta 2: Modelos de Estructura de Tasas ---
NOMBRE_A_PLAZO_TREASURY = {
    f"Bono del Tesoro de EEUU a {plazo} (Treasury Constant Maturity, H.15)": plazo
    for plazo in et.PLAZOS_ANIOS
}
ANIOS_TAREA_ESTRUCTURA_TASAS = tuple(range(2017, 2027))


@st.cache_data(ttl=3600)
def _cargar_curva_treasury(df_macro: pd.DataFrame) -> pd.DataFrame:
    """Pivotea las 11 series de Treasury Constant Maturity (una fila por
    fecha, una columna por plazo) para poder ajustar Nelson-Siegel y
    Svensson. Mismas series que ya carga cargar_series_macro() — no hace
    ninguna consulta nueva a la BD."""
    # pd.read_sql devuelve "fecha" (columna DATE en Postgres) como
    # datetime.date, no Timestamp -- se convierte explícitamente para
    # poder comparar con pd.Timestamp(...) más abajo (mismo ajuste que
    # calcular_resumen_ipsa hace con df_todas al principio).
    df = df_macro[df_macro["nombre"].isin(NOMBRE_A_PLAZO_TREASURY)].assign(
        fecha=lambda d: pd.to_datetime(d["fecha"])
    ).copy()
    df["plazo"] = df["nombre"].map(NOMBRE_A_PLAZO_TREASURY)
    pivote = df.pivot_table(index="fecha", columns="plazo", values="valor")
    return pivote.reindex(columns=list(et.PLAZOS_ANIOS.keys()))


def _ultima_fecha_habil_junio(pivote: pd.DataFrame, anio: int):
    """Última fecha de junio de `anio` con curva completa (los 11 plazos
    sin NaN) — el "último día transado de junio" que pide el enunciado."""
    ventana = pivote[(pivote.index >= pd.Timestamp(anio, 6, 1)) & (pivote.index <= pd.Timestamp(anio, 6, 30))]
    ventana = ventana.dropna()
    return ventana.index[-1] if len(ventana) else None


@st.cache_data(ttl=3600)
def _ajustar_modelos_por_anio(pivote: pd.DataFrame, anios: tuple) -> pd.DataFrame:
    """Ajusta Nelson-Siegel y Svensson para el último día hábil de junio
    de cada año en `anios` — devuelve una fila por año con RMSE,
    parámetros de Nelson-Siegel, y las curvas ajustadas (para graficar)."""
    filas = []
    plazos = list(et.PLAZOS_ANIOS.values())
    for anio in anios:
        fecha = _ultima_fecha_habil_junio(pivote, anio)
        if fecha is None:
            continue
        tasas = pivote.loc[fecha].tolist()
        ns = et.ajustar_nelson_siegel(plazos, tasas)
        sv = et.ajustar_svensson(plazos, tasas)
        filas.append({
            "Año": anio,
            "Fecha": fecha.date(),
            "RMSE Nelson-Siegel": ns["rmse"],
            "RMSE Svensson": sv["rmse"],
            "Mejora Svensson (%)": (1 - sv["rmse"] / ns["rmse"]) * 100 if ns["rmse"] else None,
            "β0 (nivel)": ns["parametros"]["beta0"],
            "β1 (pendiente)": ns["parametros"]["beta1"],
            "β2 (curvatura)": ns["parametros"]["beta2"],
            "τ1": ns["parametros"]["tau1"],
            "_tasas_obs": tasas,
            "_ns_ajustado": ns["ajustado"].tolist(),
            "_sv_ajustado": sv["ajustado"].tolist(),
        })
    return pd.DataFrame(filas)


def _grafico_base_frontera() -> go.Figure:
    fig = go.Figure()
    fig.update_layout(xaxis_title="Volatilidad anualizada", yaxis_title="Retorno esperado anualizado", height=550)
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(tickformat=".0%")
    return fig


def _agregar_frontera_a_grafico(fig: go.Figure, resultado: dict, nombre: str, color: str, dash: str = "solid"):
    if resultado is None or not resultado["frontera"]:
        return
    vols, rets = zip(*sorted(resultado["frontera"]))
    fig.add_trace(go.Scatter(
        x=vols, y=rets, mode="lines", line=dict(color=color, width=3, dash=dash), name=nombre,
    ))
    fig.add_trace(go.Scatter(
        x=[resultado["vol_minvar"]], y=[resultado["ret_minvar"]], mode="markers",
        marker=dict(size=12, color=color, symbol="star", line=dict(width=1, color="black")),
        name=f"GMV — {nombre}", showlegend=False,
    ))


def _tabla_pesos(pesos: pd.Series, sector_por_ticker: dict, empresa_por_ticker: dict) -> pd.DataFrame:
    df = pesos.rename("Peso").to_frame()
    df["Empresa"] = [empresa_por_ticker.get(t, t) for t in df.index]
    df["Sector"] = [sector_por_ticker.get(t, "Otro") for t in df.index]
    df.index.name = "Ticker"
    return df.reset_index()[["Ticker", "Empresa", "Sector", "Peso"]].sort_values("Peso", ascending=False)


with tab_laboratorio:
    st.header("Laboratorio Financiero — Frontera Media-Varianza + LMC + Desempeño")
    st.caption(
        "Pestaña independiente para reproducir y **experimentar** con la tarea de Frontera "
        "Media-Varianza (1A) y LMC/Desempeño (1B): cambia el universo, la ventana, las "
        "restricciones y la aversión al riesgo, y observa cómo cambian la frontera, el "
        "portafolio de tangencia y sus estadísticos. No modifica la pestaña "
        "\"Optimización de Portafolios\" existente."
    )

    try:
        df_acciones_lab = cargar_precios_acciones()
        df_macro_lab = cargar_series_macro()
        _mostrar_banner_apagon(
            df_acciones_lab, TICKERS_LABORATORIO_AMPLIADO, "las acciones del universo del Laboratorio Financiero",
        )

        # ============================================================
        # 1-2. Universo de acciones
        # ============================================================
        st.subheader("1. Universo de acciones (S&P 500)")

        st.session_state.setdefault("lab_tickers", TICKERS_LABORATORIO_50)
        if st.button("↺ Usar muestra recomendada de 50 acciones"):
            st.session_state["lab_tickers"] = TICKERS_LABORATORIO_50
            st.rerun()

        tickers_lab = st.multiselect(
            "Acciones seleccionadas", OPCIONES_LABORATORIO, key="lab_tickers",
        )
        st.caption(f"Número de acciones seleccionadas: **{len(tickers_lab)}**")

        conteo_sectorial = lab.contar_por_sector(tickers_lab, SECTOR_POR_TICKER_LABORATORIO)
        cols_sectores = st.columns(len(SECTORES_OBLIGATORIOS_LABORATORIO))
        sectores_insuficientes = []
        for col, sector in zip(cols_sectores, SECTORES_OBLIGATORIOS_LABORATORIO):
            n_sector = conteo_sectorial.get(sector, 0)
            with col:
                st.metric(sector, n_sector)
            if n_sector < 2:
                sectores_insuficientes.append(sector)

        if sectores_insuficientes:
            st.warning(
                "⚠️ La selección actual no cumple el requisito de al menos dos acciones de "
                f"cada sector de la tarea (falta en: {', '.join(sectores_insuficientes)}). "
                "El cálculo igual se ejecuta — esto es solo una advertencia."
            )

        if len(tickers_lab) < 2:
            st.error("Elige al menos 2 acciones para continuar.")
            st.stop()

        # ============================================================
        # 3. Ventana temporal
        # ============================================================
        st.subheader("2. Ventana temporal")
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            anios_ventana = st.select_slider(
                "Ventana histórica (años)", options=[1, 2, 3, 4, 5], value=3, key="lab_ventana_anios",
            )
        with col_v2:
            modo_fecha = st.radio(
                "Fecha final", ["Modo Tarea (31-07-2026)", "Fecha personalizada"], key="lab_modo_fecha",
            )

        if modo_fecha == "Modo Tarea (31-07-2026)":
            fecha_fin_lab = FECHA_FIN_TAREA
        else:
            fecha_fin_lab = pd.Timestamp(st.date_input(
                "Fecha final personalizada", value=FECHA_FIN_TAREA.date(), key="lab_fecha_fin_custom",
            ))
        fecha_inicio_lab = fecha_fin_lab - pd.DateOffset(years=anios_ventana)

        datos_lab = preparar_datos_lab_cacheado(df_acciones_lab, tuple(tickers_lab), fecha_inicio_lab, fecha_fin_lab)

        if datos_lab["tickers_excluidos"]:
            lista_excl = ", ".join(f"{t} ({n} obs.)" for t, n in datos_lab["tickers_excluidos"])
            st.warning(f"⚠️ Excluidos por historia insuficiente (< 60 observaciones reales): {lista_excl}.")

        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        col_f1.metric("Fecha inicial", datos_lab["fecha_inicio"].strftime("%d-%m-%Y"))
        col_f2.metric("Fecha final", datos_lab["fecha_fin"].strftime("%d-%m-%Y"))
        col_f3.metric("Observaciones", f"{datos_lab['n_observaciones']:,}")
        col_f4.metric("Acciones usadas", len(datos_lab["tickers_validos"]))

        diagnostico_cobertura = diagnosticar_cobertura_cacheado(
            df_acciones_lab, tuple(datos_lab["tickers_validos"]), fecha_inicio_lab, fecha_fin_lab,
        )
        sesiones_teoricas = diagnostico_cobertura["sesiones_teoricas"]
        n_perdidas = sesiones_teoricas - datos_lab["n_observaciones"]
        cobertura_pct = (datos_lab["n_observaciones"] / sesiones_teoricas * 100) if sesiones_teoricas else None

        col_cov1, col_cov2, col_cov3, col_cov4 = st.columns(4)
        col_cov1.metric("Sesiones teóricas (vía S&P 500)", f"{sesiones_teoricas:,}")
        col_cov2.metric("Observaciones comunes usadas", f"{datos_lab['n_observaciones']:,}")
        col_cov3.metric("Cobertura", f"{cobertura_pct:.1f}%" if cobertura_pct is not None else "—")
        col_cov4.metric("Fechas perdidas", f"{n_perdidas:,}")

        with st.expander("¿Por qué se perdieron observaciones?"):
            st.caption(
                "\"Sesiones teóricas\" son los días con retorno real del S&P 500 (`^GSPC`) dentro de "
                "la ventana, que coincide con el calendario bursátil real. Una fecha se pierde de la "
                "matriz final si **al menos una** de las acciones elegidas no tiene un retorno real ese "
                "día, lo cual ocurre por dos motivos distintos: (1) no hay **ninguna fila de precio** en "
                "la base para esa fecha (dato genuinamente ausente en la fuente), o (2) el precio de "
                "cierre es idéntico al del día anterior **y** el volumen de ese día es 0 o repite "
                "exactamente el volumen del día anterior (evidencia de que la fuente dejó de refrescar "
                "el dato, no de un empate real de mercado). Un precio repetido con volumen propio y "
                "distinto de cero **sí se conserva** como retorno de 0% real — una auditoría cruzada "
                "contra una fuente independiente (Nasdaq.com) confirmó que ese tipo de empate suele ser "
                "un movimiento real de mercado. Alinear las fechas exactamente así entre todas las "
                "acciones sigue siendo necesario para que la matriz de covarianzas conjunta sea válida — "
                "basta que una sola acción tenga un día problemático para que ese día se pierda también "
                "para las demás."
            )
            if diagnostico_cobertura["tabla"].empty:
                st.caption("Ninguna acción de la selección actual perdió observaciones dentro de la ventana.")
            else:
                n_con_perdidas = len(diagnostico_cobertura["tabla"])
                n_total = len(datos_lab["tickers_validos"])
                st.caption(
                    f"{n_con_perdidas} de {n_total} acciones perdieron al menos un día (dato ausente o "
                    "precio congelado sin evidencia de trading) — la tabla lista todas ellas (no es un "
                    "top parcial), ordenadas de mayor a menor pérdida; las "
                    f"{n_total - n_con_perdidas} restantes tuvieron cobertura completa."
                )
                st.dataframe(diagnostico_cobertura["tabla"], use_container_width=True, hide_index=True)

        df_retornos_lab = datos_lab["df_retornos"]
        if len(df_retornos_lab.columns) < 2 or len(df_retornos_lab) < 30:
            st.error("No hay suficientes datos comunes para este universo/ventana. Ajusta la selección.")
            st.stop()

        # ============================================================
        # 4. Estadísticas de las acciones
        # ============================================================
        st.subheader("3. Retornos y estadísticos de las acciones")

        df_stats_lab = lab.estadisticas_activos(
            df_retornos_lab, SECTOR_POR_TICKER_LABORATORIO, EMPRESA_POR_TICKER_LABORATORIO,
        )
        st.dataframe(
            df_stats_lab.style.format({
                "Retorno esperado": "{:+.2%}", "Volatilidad": "{:.2%}", "Varianza": "{:.4f}",
            }),
            use_container_width=True,
        )

        cov_anual_lab = lab.matriz_covarianza_anual(df_retornos_lab)
        with st.expander("Matriz de correlaciones (heatmap)"):
            corr_lab = df_retornos_lab.corr()
            fig_corr = go.Figure(data=go.Heatmap(
                z=corr_lab.values, x=corr_lab.columns, y=corr_lab.columns,
                colorscale=COLORSCALE_CORRELACION, zmin=-1, zmax=1,
            ))
            fig_corr.update_layout(height=650)
            st.plotly_chart(fig_corr, use_container_width=True)

        # ============================================================
        # Rf (se necesita desde acá para poder mostrar tangencia en cualquier frontera)
        # ============================================================
        rf_treasury_serie = (
            df_macro_lab[df_macro_lab["nombre"] == NOMBRE_TREASURY_1Y]
            .assign(fecha=lambda d: pd.to_datetime(d["fecha"]))
            .sort_values("fecha")
            .set_index("fecha")["valor"]
        ) / 100

        rf_modo = st.radio(
            "Tasa libre de riesgo", ["Modo Tarea: Treasury 1Y al 31-07-2026", "Modo experimental (Rf manual)"],
            key="lab_rf_modo",
        )
        if rf_modo == "Modo experimental (Rf manual)":
            rf_lab_pct = st.slider("Rf manual (% anual)", 0.0, 15.0, 4.08, step=0.05, key="lab_rf_manual")
            rf_lab = rf_lab_pct / 100
            fuente_rf_texto = "manual (modo experimental)"
        else:
            serie_hasta_fin = rf_treasury_serie[rf_treasury_serie.index <= fecha_fin_lab]
            if serie_hasta_fin.empty:
                st.error("No hay datos de Treasury 1Y disponibles hasta la fecha elegida.")
                st.stop()
            rf_lab = float(serie_hasta_fin.iloc[-1])
            fecha_rf_real = serie_hasta_fin.index[-1]
            fuente_rf_texto = f"Federal Reserve / H.15 (FRED, serie DGS1), observada el {fecha_rf_real.strftime('%d-%m-%Y')}"

        st.info(f"**Rf utilizado: {rf_lab * 100:.2f}% anual** — Fuente: {fuente_rf_texto}.")
        if rf_modo == "Modo experimental (Rf manual)":
            st.caption(
                "📌 **LMC/Sharpe/Treynor/x\\*** usan el Rf manual puntual de arriba; **CAPM** usa esa misma "
                "Rf manual pero convertida a una serie diaria constante (÷252) — nunca la serie real de "
                "Treasury 1Y en este modo."
            )
        else:
            st.caption(
                "📌 **LMC/Sharpe/Treynor/x\\*** usan el Rf puntual del 31-07-2026 (arriba); **CAPM** usa la "
                "serie diaria de Treasury 1Y (no un promedio) — mismo instrumento y misma serie, distinto "
                "uso temporal (valor puntual vs. serie diaria), no dos tasas distintas."
            )

        # Rf que alimenta el CAPM: en Modo Tarea es la serie diaria real de
        # Treasury 1Y (la regresión trabaja con excesos de retorno diarios,
        # así que conserva la variación día a día de la tasa); en Modo
        # experimental es una Rf diaria CONSTANTE derivada de la Rf manual
        # (Rf manual ÷ 252 cada día) — nunca se mezcla la serie real con la
        # manual sin avisarlo. Las medidas ESTÁTICAS (M, LMC, Sharpe,
        # Treynor, x*) siempre usan el valor puntual rf_lab de arriba, nunca
        # un promedio de la serie.
        if rf_modo == "Modo experimental (Rf manual)":
            rf_serie_para_capm = pd.Series(
                rf_lab, index=[fecha_inicio_lab - pd.Timedelta(days=5), fecha_fin_lab + pd.Timedelta(days=5)],
            )
            nota_capm_rf = (
                f"En modo experimental, el CAPM usa una Rf diaria **constante** derivada de la Rf manual "
                f"({rf_lab*100:.2f}% anual ÷ 252 cada día) — no la serie real de Treasury 1Y."
            )
        else:
            rf_serie_para_capm = rf_treasury_serie
            nota_capm_rf = (
                "El CAPM usa la **serie diaria** de Treasury 1Y (FRED, DGS1) alineada a cada fecha de la "
                "regresión — no su promedio. Las medidas estáticas (M, LMC, Sharpe, Treynor, x*) usan en "
                f"cambio el valor **puntual** del 31-07-2026 ({rf_lab*100:.2f}%) mostrado arriba: es el "
                "mismo instrumento y la misma serie (Treasury 1Y), con distinto **uso temporal** — "
                "valor puntual de una fecha vs. serie diaria — no dos tasas distintas. La serie diaria "
                "evita perder la variación de la tasa dentro de la regresión, y el valor puntual es "
                "consistentemente el que pide la tarea para M/LMC/Sharpe/Treynor."
            )

        st.divider()
        st.markdown("## Parte 1A — Frontera Media-Varianza")

        # ============================================================
        # 5-9 y 21-22. Panel de restricciones ("jugar con los supuestos") + presets
        # ============================================================
        st.subheader("4. Restricciones — jugar con los supuestos")
        st.caption(
            "Estos controles arman la frontera que se grafica más abajo (sección 5). Usa "
            "los presets para saltar directo a cada punto de la tarea, o combina los "
            "controles libremente para experimentar."
        )

        DEFAULTS_LAB = {
            "lab_permitir_short": True, "lab_usar_limite": False, "lab_limite_abs": 0.10,
            "lab_usar_sector": False, "lab_sectores_elegidos": ["Energy", "Industrials"],
            "lab_peso_min_sector": 0.40, "lab_usar_ingenua": False,
        }
        for k, v in DEFAULTS_LAB.items():
            st.session_state.setdefault(k, v)

        PRESETS_LAB = {
            "Punto 2 — Base (short libre)": {
                "lab_permitir_short": True, "lab_usar_limite": False, "lab_usar_sector": False, "lab_usar_ingenua": False,
            },
            "Punto 3 — Covarianzas ignoradas": {
                "lab_permitir_short": True, "lab_usar_limite": False, "lab_usar_sector": False, "lab_usar_ingenua": True,
            },
            "Punto 4 — Límite ±10%": {
                "lab_permitir_short": True, "lab_usar_limite": True, "lab_limite_abs": 0.10,
                "lab_usar_sector": False, "lab_usar_ingenua": False,
            },
            "Punto 5 — Sin venta corta": {
                "lab_permitir_short": False, "lab_usar_limite": False, "lab_usar_sector": False, "lab_usar_ingenua": False,
            },
            "Punto 6 — Sin corta + Energy/Industrials≥40%": {
                "lab_permitir_short": False, "lab_usar_limite": False, "lab_usar_sector": True,
                "lab_sectores_elegidos": ["Energy", "Industrials"], "lab_peso_min_sector": 0.40,
                "lab_usar_ingenua": False,
            },
        }
        cols_presets = st.columns(len(PRESETS_LAB))
        for col, (nombre_preset, valores) in zip(cols_presets, PRESETS_LAB.items()):
            with col:
                if st.button(nombre_preset, key=f"preset_{nombre_preset}"):
                    for k, v in valores.items():
                        st.session_state[k] = v
                    st.rerun()

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            permitir_short_lab = st.checkbox("Permitir venta corta", key="lab_permitir_short")
            usar_limite_lab = st.checkbox("Límite absoluto por acción", key="lab_usar_limite")
            limite_abs_lab = None
            if usar_limite_lab:
                limite_abs_lab = st.slider(
                    "Máximo |wi|", 0.05, 1.0, step=0.05, key="lab_limite_abs",
                )
        with col_r2:
            usar_sector_lab = st.checkbox("Restricción sectorial", key="lab_usar_sector")
            restriccion_sectorial_lab = None
            if usar_sector_lab:
                sectores_elegidos_lab = st.multiselect(
                    "Sector(es)", SECTORES_OBLIGATORIOS_LABORATORIO, key="lab_sectores_elegidos",
                )
                peso_min_sector_lab = st.slider(
                    "Peso mínimo conjunto", 0.0, 1.0, step=0.05, key="lab_peso_min_sector",
                )
                tickers_sector_lab = [
                    t for t in datos_lab["tickers_validos"]
                    if SECTOR_POR_TICKER_LABORATORIO.get(t) in sectores_elegidos_lab
                ]
                if tickers_sector_lab:
                    restriccion_sectorial_lab = (tuple(tickers_sector_lab), peso_min_sector_lab)
            usar_ingenua_lab = st.checkbox(
                "Ignorar covarianzas al optimizar (Ω_diag)", key="lab_usar_ingenua",
            )

        resultado_actual = calcular_frontera_lab_cacheada(
            df_retornos_lab, rf_lab, permitir_short_lab, limite_abs_lab, restriccion_sectorial_lab, usar_ingenua_lab,
        )

        # ============================================================
        # 5. Resultado de la frontera actual
        # ============================================================
        st.subheader("5. Frontera resultante")

        if resultado_actual is None:
            st.error(
                "No se pudo calcular la frontera con esta combinación de restricciones "
                "(¿matriz de covarianza no invertible, o restricciones incompatibles entre sí?)."
            )
        else:
            if resultado_actual["regularizado"]:
                st.caption(
                    "ℹ️ La matriz de covarianza estaba mal condicionada (activos casi "
                    "colineales) — se aplicó una regularización de Tikhonov ínfima "
                    "(1e-8 × traza(Ω)/n en la diagonal) para poder invertirla."
                )

            fig_actual = _grafico_base_frontera()
            _agregar_frontera_a_grafico(fig_actual, resultado_actual, "Frontera actual", "#2a78d6")
            fig_actual.add_trace(go.Scatter(
                x=df_stats_lab["Volatilidad"], y=df_stats_lab["Retorno esperado"],
                mode="markers", marker=dict(size=7, color="#8a8a8a"), text=df_stats_lab.index,
                name="Activos individuales",
            ))
            if resultado_actual.get("w_tangencia") is not None:
                fig_actual.add_trace(go.Scatter(
                    x=[resultado_actual["vol_tangencia"]], y=[resultado_actual["ret_tangencia"]],
                    mode="markers", marker=dict(size=16, color="#e34948", symbol="star", line=dict(width=1, color="black")),
                    name="Tangencia (config. actual)",
                ))
            st.plotly_chart(fig_actual, use_container_width=True)

            col_g1, col_g2, col_g3, col_g4 = st.columns(4)
            col_g1.metric("GMV — retorno", f"{resultado_actual['ret_minvar']*100:.2f}%")
            col_g2.metric("GMV — volatilidad", f"{resultado_actual['vol_minvar']*100:.2f}%")
            n_efectivo = 1 / float((resultado_actual["w_minvar"] ** 2).sum())
            col_g3.metric("N efectivo de posiciones (GMV)", f"{n_efectivo:.1f}")
            col_g4.metric("Σwi (GMV, validación)", f"{resultado_actual['w_minvar'].sum()*100:.2f}%")

            if usar_limite_lab:
                st.caption(f"Concentración máxima observada: {resultado_actual['w_minvar'].abs().max()*100:.1f}% (límite: {limite_abs_lab*100:.0f}%).")
            if not permitir_short_lab:
                st.caption(f"Peso mínimo/máximo en GMV: {resultado_actual['w_minvar'].min()*100:.2f}% / {resultado_actual['w_minvar'].max()*100:.2f}% (sin venta corta: no debería haber negativos).")
            if usar_sector_lab and restriccion_sectorial_lab is not None:
                peso_sector_actual = resultado_actual["w_minvar"][list(restriccion_sectorial_lab[0])].sum()
                cumple = "✅" if peso_sector_actual >= restriccion_sectorial_lab[1] - 1e-6 else "⚠️"
                st.caption(f"{cumple} Peso conjunto de {', '.join(sectores_elegidos_lab)} en GMV: {peso_sector_actual*100:.2f}% (mínimo exigido: {restriccion_sectorial_lab[1]*100:.0f}%).")

            # --- "¿Qué estoy viendo?" — explicación basada en los resultados reales ---
            with st.expander("¿Qué estoy viendo?", expanded=False):
                texto_explicacion = []
                if usar_ingenua_lab:
                    frontera_base_cmp = calcular_frontera_lab_cacheada(df_retornos_lab, rf_lab, True, None, None, False)
                    if frontera_base_cmp is not None:
                        diff_vol = (resultado_actual["vol_minvar"] - frontera_base_cmp["vol_minvar"]) * 100
                        texto_explicacion.append(
                            f"Al **ignorar las covarianzas** (Ω_diag) para optimizar, la volatilidad real del GMV "
                            f"sube en **{diff_vol:+.2f} puntos porcentuales** respecto a la frontera correcta "
                            f"({resultado_actual['vol_minvar']*100:.2f}% vs. {frontera_base_cmp['vol_minvar']*100:.2f}%). "
                            "Esto pasa porque la matriz diagonal no \"ve\" que ciertos activos se mueven juntos "
                            "(correlación positiva) o se compensan (correlación negativa) — el optimizador no puede "
                            "aprovechar esa información para diversificar de verdad, así que el resultado, evaluado "
                            "con el riesgo real, es peor."
                        )
                elif usar_limite_lab:
                    texto_explicacion.append(
                        f"El límite de ±{limite_abs_lab*100:.0f}% por acción reduce el conjunto factible: ya no se "
                        "puede concentrar el portafolio en pocas posiciones grandes (largas o cortas). El GMV con "
                        f"límite tiene {n_efectivo:.1f} posiciones efectivas — compara con la frontera base (sin "
                        "límite) en la sección de comparación de abajo para ver cuánto cambia."
                    )
                elif not permitir_short_lab and usar_sector_lab:
                    texto_explicacion.append(
                        "Sin venta corta, el conjunto factible ya es más chico (todos los pesos entre 0 y 1). "
                        "Agregar además un piso sectorial (Energy+Industrials ≥ mínimo exigido) lo reduce todavía "
                        "más: el optimizador ya no puede elegir libremente el mix de sectores que minimiza "
                        "varianza, tiene que aceptar una porción mínima de sectores que quizás no son los más "
                        "eficientes en términos de riesgo — por eso la volatilidad del GMV con esta restricción "
                        "suele ser mayor que sin ella."
                    )
                elif not permitir_short_lab:
                    texto_explicacion.append(
                        "Prohibir la venta corta (wi ≥ 0) elimina todas las combinaciones de pesos negativos que "
                        "la frontera base sí permite — el conjunto factible se reduce, así que la volatilidad "
                        "mínima alcanzable con esta restricción nunca puede ser menor que la de la frontera base "
                        "(compáralas en la sección 7)."
                    )
                else:
                    texto_explicacion.append(
                        "Esta es la frontera **base**: venta corta permitida, sin límites de concentración ni "
                        "restricciones sectoriales — el conjunto factible más grande posible, y por lo tanto la "
                        "frontera con menor volatilidad para cada nivel de retorno (referencia para comparar "
                        "todas las demás restricciones)."
                    )
                st.markdown("\n\n".join(texto_explicacion))

            # ============================================================
            # 25. Selector de punto de la frontera
            # ============================================================
            st.subheader("6. Explorar un punto de la frontera")
            if resultado_actual["frontera"]:
                rets_frontera = [r for _, r in resultado_actual["frontera"]]
                retorno_objetivo = st.slider(
                    "Retorno objetivo", float(min(rets_frontera)), float(max(rets_frontera)),
                    value=float(resultado_actual["ret_minvar"]), format="%.4f", key="lab_retorno_objetivo",
                )
                idx_cercano = int(np.argmin([abs(r - retorno_objetivo) for r in rets_frontera]))
                pesos_punto = resultado_actual["pesos_frontera"][idx_cercano]
                vol_punto, ret_punto = resultado_actual["frontera"][idx_cercano]
                sharpe_punto = (ret_punto - rf_lab) / vol_punto if vol_punto > 0 else None

                col_p1, col_p2, col_p3 = st.columns(3)
                col_p1.metric("Retorno del punto más cercano", f"{ret_punto*100:.2f}%")
                col_p2.metric("Volatilidad", f"{vol_punto*100:.2f}%")
                col_p3.metric("Sharpe", f"{sharpe_punto:.2f}" if sharpe_punto is not None else "—")

                resumen_sect_punto = lab.resumen_sectorial(pesos_punto, SECTOR_POR_TICKER_LABORATORIO)
                st.caption(
                    "Exposición sectorial de este punto: " +
                    ", ".join(f"{s}: {v*100:.1f}%" for s, v in resumen_sect_punto.sort_values(ascending=False).items())
                )
                with st.expander("Pesos de este punto de la frontera"):
                    st.dataframe(
                        _tabla_pesos(pesos_punto, SECTOR_POR_TICKER_LABORATORIO, EMPRESA_POR_TICKER_LABORATORIO)
                        .style.format({"Peso": "{:+.2%}"}),
                        use_container_width=True,
                    )
            else:
                st.info("Esta configuración no generó puntos de frontera para explorar.")

        # ============================================================
        # 10. Comparación de todas las fronteras
        # ============================================================
        st.subheader("7. Comparación de restricciones")
        st.caption("Activa las fronteras que quieras superponer en un solo gráfico.")

        col_chk1, col_chk2, col_chk3, col_chk4, col_chk5 = st.columns(5)
        mostrar_base = col_chk1.checkbox("Frontera base", value=True, key="lab_cmp_base")
        mostrar_ingenua = col_chk2.checkbox("Frontera ingenua", key="lab_cmp_ingenua")
        mostrar_10 = col_chk3.checkbox("±10%", key="lab_cmp_10")
        mostrar_noshort = col_chk4.checkbox("Sin venta corta", key="lab_cmp_noshort")
        mostrar_sector = col_chk5.checkbox("Sin corta + sectorial ≥40%", key="lab_cmp_sector")

        fig_cmp = _grafico_base_frontera()
        tickers_ei_cmp = tuple(
            t for t in datos_lab["tickers_validos"]
            if SECTOR_POR_TICKER_LABORATORIO.get(t) in ("Energy", "Industrials")
        )

        if mostrar_base:
            _agregar_frontera_a_grafico(
                fig_cmp, calcular_frontera_lab_cacheada(df_retornos_lab, rf_lab, True, None, None, False),
                "Base", "#2a78d6",
            )
        if mostrar_ingenua:
            _agregar_frontera_a_grafico(
                fig_cmp, calcular_frontera_lab_cacheada(df_retornos_lab, rf_lab, True, None, None, True),
                "Ingenua (evaluada con Ω real)", "#eda100", dash="dot",
            )
        if mostrar_10:
            _agregar_frontera_a_grafico(
                fig_cmp, calcular_frontera_lab_cacheada(df_retornos_lab, rf_lab, True, 0.10, None, False),
                "±10%", "#1baf7a", dash="dash",
            )
        if mostrar_noshort:
            _agregar_frontera_a_grafico(
                fig_cmp, calcular_frontera_lab_cacheada(df_retornos_lab, rf_lab, False, None, None, False),
                "Sin venta corta", "#e34948", dash="dashdot",
            )
        if mostrar_sector and tickers_ei_cmp:
            _agregar_frontera_a_grafico(
                fig_cmp,
                calcular_frontera_lab_cacheada(df_retornos_lab, rf_lab, False, None, (tickers_ei_cmp, 0.40), False),
                "Sin corta + Energy/Industrials≥40%", "#4a3aa7", dash="longdash",
            )
        st.plotly_chart(fig_cmp, use_container_width=True)
        st.caption(
            "Cada restricción reduce (nunca amplía) el conjunto factible respecto a la frontera "
            "base — por eso ninguna otra frontera puede quedar a la izquierda de la base (para el "
            "mismo retorno, siempre necesita igual o más volatilidad, es decir, queda a la derecha "
            "en el eje X)."
        )

        st.divider()
        st.markdown("## Parte 1B — LMC y Desempeño")
        st.caption(
            "Esta parte usa siempre la **frontera base** (venta corta permitida, sin otras "
            "restricciones) del punto 1A.2, independiente de la configuración elegida arriba en "
            "la sección 4 — así lo pide la tarea (1B.2)."
        )

        frontera_base_1b = calcular_frontera_lab_cacheada(df_retornos_lab, rf_lab, True, None, None, False)
        if frontera_base_1b is None or frontera_base_1b.get("w_tangencia") is None:
            st.error("No se pudo calcular el portafolio de tangencia M con la frontera base — revisa el universo elegido.")
        else:
            # ============================================================
            # 12. Portafolio de tangencia M
            # ============================================================
            st.subheader("8. Portafolio de tangencia M")
            w_M = frontera_base_1b["w_tangencia"]
            n_no_cero = int((w_M.abs() > 1e-4).sum())

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("Retorno esperado anual", f"{frontera_base_1b['ret_tangencia']*100:.2f}%")
            col_m2.metric("Volatilidad anual", f"{frontera_base_1b['vol_tangencia']*100:.2f}%")
            col_m3.metric("Sharpe", f"{frontera_base_1b['sharpe_tangencia']:.2f}")
            col_m4.metric("Activos con peso ≠ 0", n_no_cero)

            st.warning(
                "⚠️ M es la solución **exacta y sin restricciones** (venta corta libre, sin "
                "límites): con 50 activos correlacionados, esto típicamente produce pesos "
                "extremos (posiciones largas y cortas muy grandes) y un Sharpe poco realista — "
                "es la crítica clásica de Michaud (1989) al \"error-maximizador\" de Markowitz. "
                "Es la solución que pide el punto 1B.2 de la tarea, no una recomendación de "
                "inversión."
            )

            tabla_pesos_M = _tabla_pesos(w_M, SECTOR_POR_TICKER_LABORATORIO, EMPRESA_POR_TICKER_LABORATORIO)
            col_pw1, col_pw2 = st.columns(2)
            with col_pw1:
                st.markdown("**Pesos positivos (top 10)**")
                st.dataframe(
                    tabla_pesos_M[tabla_pesos_M["Peso"] > 0].head(10).style.format({"Peso": "{:+.2%}"}),
                    use_container_width=True,
                )
            with col_pw2:
                st.markdown("**Pesos negativos (top 10)**")
                st.dataframe(
                    tabla_pesos_M[tabla_pesos_M["Peso"] < 0].sort_values("Peso").head(10).style.format({"Peso": "{:+.2%}"}),
                    use_container_width=True,
                )
            fig_pesos_M = go.Figure(go.Bar(
                x=tabla_pesos_M["Ticker"], y=tabla_pesos_M["Peso"],
                marker_color=["#1baf7a" if p >= 0 else "#e34948" for p in tabla_pesos_M["Peso"]],
            ))
            fig_pesos_M.update_layout(yaxis_title="Peso", height=350)
            fig_pesos_M.update_yaxes(tickformat=".0%")
            st.plotly_chart(fig_pesos_M, use_container_width=True)
            st.caption(
                f"Suma pesos positivos: {tabla_pesos_M[tabla_pesos_M['Peso']>0]['Peso'].sum()*100:+.1f}% — "
                f"Suma pesos negativos: {tabla_pesos_M[tabla_pesos_M['Peso']<0]['Peso'].sum()*100:+.1f}% — "
                f"Suma total: {tabla_pesos_M['Peso'].sum()*100:.2f}% (validación: debe ser 100%)."
            )

            # ============================================================
            # 13. LMC
            # ============================================================
            st.subheader("9. Línea de Mercado de Capitales (LMC)")
            vol_max_lmc = max(
                frontera_base_1b["vol_tangencia"],
                max((v for v, _ in frontera_base_1b["frontera"]), default=frontera_base_1b["vol_tangencia"]),
            ) * 1.4
            xs_lmc, ys_lmc, pendiente_lmc = lab.linea_mercado_capitales(
                rf_lab, frontera_base_1b["ret_tangencia"], frontera_base_1b["vol_tangencia"], vol_max_lmc,
            )
            fig_lmc = _grafico_base_frontera()
            _agregar_frontera_a_grafico(fig_lmc, frontera_base_1b, "Frontera base", "#2a78d6")
            fig_lmc.add_trace(go.Scatter(
                x=xs_lmc, y=ys_lmc, mode="lines", line=dict(color="#eda100", width=2, dash="dash"), name="LMC",
            ))
            fig_lmc.add_trace(go.Scatter(
                x=[0], y=[rf_lab], mode="markers", marker=dict(size=12, color="black"), name="Rf (σ=0)",
            ))
            fig_lmc.add_trace(go.Scatter(
                x=[frontera_base_1b["vol_tangencia"]], y=[frontera_base_1b["ret_tangencia"]],
                mode="markers", marker=dict(size=16, color="#e34948", symbol="star", line=dict(width=1, color="black")),
                name="Portafolio M",
            ))
            st.plotly_chart(fig_lmc, use_container_width=True)

            interseccion_ok = abs(ys_lmc[0] - rf_lab) < 1e-9
            pasa_por_M = abs((rf_lab + pendiente_lmc * frontera_base_1b["vol_tangencia"]) - frontera_base_1b["ret_tangencia"]) < 1e-6
            col_l1, col_l2, col_l3 = st.columns(3)
            col_l1.metric("Pendiente LMC (= Sharpe de M)", f"{pendiente_lmc:.2f}")
            col_l2.metric("Intercepta en Rf (σ=0)", "✅" if interseccion_ok else "⚠️")
            col_l3.metric("Pasa exactamente por M", "✅" if pasa_por_M else "⚠️")
            st.caption(f"E(Rc) = Rf + [(E(RM) − Rf)/σM] × σc = {rf_lab*100:.2f}% + {pendiente_lmc:.2f} × σc")

            # ============================================================
            # 14-15. CAPM y test t de Jensen
            # ============================================================
            st.subheader("10. CAPM: M vs. S&P 500")

            datos_sp500_lab = (
                df_acciones_lab[df_acciones_lab["ticker"] == "^GSPC"]
                .assign(fecha=lambda d: pd.to_datetime(d["fecha"]))
                .sort_values("fecha")
                .set_index("fecha")
            )
            retornos_M = lab.retornos_portafolio(df_retornos_lab, w_M)
            df_capm_lab = lab.preparar_regresion_capm(
                retornos_M, datos_sp500_lab["precio_cierre"], datos_sp500_lab["volumen"], rf_serie_para_capm,
            )

            if len(df_capm_lab) < 30:
                st.error("No hay suficientes observaciones comunes entre M, el S&P 500 y Rf para el CAPM.")
            else:
                exceso_M_lab = df_capm_lab["portafolio"] - df_capm_lab["rf"]
                exceso_mkt_lab = df_capm_lab["mercado"] - df_capm_lab["rf"]
                reg_M = calcular_capm_regresion(exceso_M_lab, exceso_mkt_lab)
                reg_auto_lab = calcular_capm_regresion(exceso_mkt_lab, exceso_mkt_lab)

                st.caption(
                    f"Regresión sobre retornos diarios en exceso — {len(df_capm_lab)} observaciones "
                    f"comunes ({df_capm_lab.index.min().strftime('%d-%m-%Y')} a "
                    f"{df_capm_lab.index.max().strftime('%d-%m-%Y')})."
                )
                st.caption(f"ℹ️ {nota_capm_rf}")

                col_c1, col_c2 = st.columns(2)
                col_c1.metric("Alfa diario", f"{reg_M['alfa']*100:+.4f}%")
                col_c2.metric("Alfa anualizado", f"{reg_M['alfa']*252*100:+.2f}%")
                col_c3, col_c4 = st.columns(2)
                col_c3.metric("Beta", f"{reg_M['beta']:.3f}")
                col_c4.metric("R²", f"{reg_M['r2']:.3f}" if reg_M["r2"] is not None else "—")
                col_c5, col_c6 = st.columns(2)
                col_c5.metric("Error estándar de alfa (anual)", f"{reg_M['se_alfa']*252*100:.2f}%")
                col_c6.metric("IC 95% de alfa (anual)", f"[{reg_M['ic_95'][0]*252*100:+.2f}%, {reg_M['ic_95'][1]*252*100:+.2f}%]")

                st.caption(
                    f"Validación interna — β(S&P 500 vs. sí mismo) = {reg_auto_lab['beta']:.4f} (≈1) — "
                    f"α = {reg_auto_lab['alfa']*252*100:+.4f}% (≈0)."
                )

                st.subheader("11. Test t de Jensen: H0: α = 0 vs. H1: α ≠ 0")
                col_t1, col_t2, col_t3 = st.columns(3)
                col_t1.metric("t = α̂ / SE(α̂)", f"{reg_M['t_alfa']:.2f}")
                col_t2.metric("Grados de libertad", f"{reg_M['gl']:,}")
                col_t3.metric("p-value", f"{reg_M['p_valor']:.4g}")

                if reg_M["p_valor"] < 0.05:
                    st.success(
                        "✅ Se rechaza H0 al 5%: existe evidencia estadística de que el alfa de "
                        "Jensen es distinto de cero."
                    )
                else:
                    st.info(
                        "ℹ️ No se rechaza H0 al 5%: no existe evidencia estadística suficiente de "
                        "que el alfa de Jensen sea distinto de cero."
                    )

                st.subheader("12. ¿Es esto consistente con eficiencia de mercado?")
                alfa_anual_M = reg_M["alfa"] * 252
                st.markdown(
                    f"El alfa de Jensen anualizado de M es **{alfa_anual_M*100:+.2f}%** "
                    f"(p = {reg_M['p_valor']:.4g}), con β = {reg_M['beta']:.2f} y R² = "
                    f"{reg_M['r2']:.2f} respecto al S&P 500 — un R² bajo significa que la mayor "
                    "parte de la varianza de M no la explica el mercado (consistente con un "
                    "portafolio con posiciones largas y cortas grandes, poco parecido al índice)."
                )
                st.warning(
                    "⚠️ **Sesgo in-sample.** El desempeño de M es in-sample: los mismos retornos "
                    "utilizados para escoger los pesos óptimos (maximizar Sharpe dentro de esta "
                    "misma ventana) se utilizan después para evaluar α, Sharpe y Treynor. Esto "
                    "puede generar *data snooping* / *overfitting* y sobreestimar el desempeño "
                    "que M habría tenido fuera de muestra — "
                    f"{'especialmente relevante acá, dado que un alfa anualizado de ' + f'{alfa_anual_M*100:+.1f}%' if abs(alfa_anual_M) > 0.15 else 'aunque en este caso el alfa no es extremo'} "
                    "es exactamente el tipo de resultado que la optimización in-sample tiende a "
                    "inflar."
                )

                # ============================================================
                # 17-19. Sharpe y Treynor: M vs. S&P 500
                # ============================================================
                st.subheader("13. Sharpe y Treynor: M vs. S&P 500")

                ret_anual_M = float(df_capm_lab["portafolio"].mean() * lab.N_RUEDAS_ANIO)
                vol_anual_M = float(df_capm_lab["portafolio"].std() * (lab.N_RUEDAS_ANIO ** 0.5))
                ret_anual_mkt = float(df_capm_lab["mercado"].mean() * lab.N_RUEDAS_ANIO)
                vol_anual_mkt = float(df_capm_lab["mercado"].std() * (lab.N_RUEDAS_ANIO ** 0.5))
                # Rf puntual (rf_lab, la misma de la tangencia M y la LMC) —
                # NO el promedio de la serie diaria usada en el CAPM. Ver
                # nota_capm_rf arriba: el CAPM necesita la serie diaria para
                # los excesos de retorno, pero Sharpe/Treynor son medidas
                # estáticas y deben usar la misma Rf puntual que el resto de
                # la Parte 1B.
                rf_anual_muestra = rf_lab

                sharpe_M_lab, treynor_M_lab = lab.sharpe_treynor(ret_anual_M, vol_anual_M, rf_anual_muestra, reg_M["beta"])
                sharpe_mkt_lab, treynor_mkt_lab = lab.sharpe_treynor(ret_anual_mkt, vol_anual_mkt, rf_anual_muestra, reg_auto_lab["beta"])
                st.caption(f"Rf utilizada para Sharpe y Treynor: **{rf_anual_muestra*100:.2f}%** (valor puntual, no el promedio de la serie diaria del CAPM).")

                df_desempeno = pd.DataFrame([
                    {"Portafolio": "M", "Retorno": ret_anual_M, "Volatilidad": vol_anual_M, "Beta": reg_M["beta"],
                     "Sharpe": sharpe_M_lab, "Treynor": treynor_M_lab},
                    {"Portafolio": "S&P 500", "Retorno": ret_anual_mkt, "Volatilidad": vol_anual_mkt, "Beta": reg_auto_lab["beta"],
                     "Sharpe": sharpe_mkt_lab, "Treynor": treynor_mkt_lab},
                ]).set_index("Portafolio")
                st.dataframe(
                    df_desempeno.style.format({
                        "Retorno": "{:+.2%}", "Volatilidad": "{:.2%}", "Beta": "{:.2f}",
                        "Sharpe": "{:.2f}", "Treynor": "{:+.2%}",
                    }),
                    use_container_width=True,
                )
                ganador_sharpe_lab = "M" if sharpe_M_lab > sharpe_mkt_lab else "el S&P 500"
                ganador_treynor_lab = "M" if treynor_M_lab > treynor_mkt_lab else "el S&P 500"
                st.markdown(
                    f"**Sharpe** penaliza por **riesgo total (σ)**: {ganador_sharpe_lab} tiene mayor Sharpe "
                    f"(M: {sharpe_M_lab:.2f} vs. S&P 500: {sharpe_mkt_lab:.2f}). **Treynor** penaliza solo por "
                    f"**riesgo sistemático (β)**: {ganador_treynor_lab} tiene mayor Treynor "
                    f"(M: {treynor_M_lab:+.2%} vs. S&P 500: {treynor_mkt_lab:+.2%}). Si el ranking difiere entre "
                    "ambos, la diferencia viene del riesgo idiosincrático (diversificable) que Treynor ignora "
                    "y Sharpe sí penaliza."
                )

                # ============================================================
                # 20. Asignación óptima según aversión al riesgo
                # ============================================================
                st.subheader("14. Asignación óptima según aversión al riesgo")
                st.caption("x* = (E[RM] − Rf) / (c × σM²) — fracción del capital invertida en M; el resto en Rf.")

                cols_c = st.columns(3)
                for col, c_val in zip(cols_c, (2, 5, 10)):
                    x_c = lab.asignacion_optima(frontera_base_1b["ret_tangencia"], rf_lab, frontera_base_1b["vol_tangencia"], c_val)
                    with col:
                        st.metric(f"c = {c_val}", f"x* = {x_c*100:.1f}% en M" if x_c is not None else "—")
                        if x_c is not None:
                            st.caption(f"{(1-x_c)*100:.1f}% en Rf")

                c_slider = st.slider("Aversión al riesgo c", 1.0, 20.0, value=5.0, step=0.5, key="lab_c_aversion")
                x_slider = lab.asignacion_optima(frontera_base_1b["ret_tangencia"], rf_lab, frontera_base_1b["vol_tangencia"], c_slider)

                if x_slider is not None:
                    col_x1, col_x2 = st.columns(2)
                    col_x1.metric("% invertido en M", f"{x_slider*100:.1f}%")
                    col_x2.metric("% invertido en Rf", f"{(1-x_slider)*100:.1f}%")

                    if x_slider < 0:
                        interpretacion_x = (
                            "**x\\* < 0**: posición contraria — el modelo sugiere ir corto en M y largo en Rf/"
                            "más de 100% en el activo libre de riesgo. Económicamente implica una aversión al "
                            "riesgo tan alta (o un M tan poco atractivo ajustado por riesgo) que ni siquiera "
                            "conviene una posición larga en M; en la práctica, un resultado así con este M "
                            "(no restringido) suele reflejar el mismo problema de sobreajuste in-sample "
                            "mencionado arriba, no una recomendación real."
                        )
                    elif x_slider < 1:
                        interpretacion_x = (
                            "**0 < x\\* < 1 (lending)**: se invierte una parte en M y el resto en el activo "
                            "libre de riesgo — la combinación clásica de un inversionista con aversión al "
                            "riesgo moderada/alta relativa al Sharpe de M."
                        )
                    elif abs(x_slider - 1) < 1e-6:
                        interpretacion_x = "**x\\* = 1**: 100% del capital en M, nada en Rf."
                    else:
                        interpretacion_x = (
                            "**x\\* > 1 (borrowing)**: se invierte más del 100% del capital en M, financiando "
                            "el exceso mediante endeudamiento a la tasa Rf — apalancamiento. Es coherente con "
                            "el modelo si el inversionista tiene baja aversión al riesgo (c chico) relativa al "
                            "Sharpe de M, pero asume que puede endeudarse exactamente a Rf, algo poco realista "
                            "en la práctica."
                        )
                    st.markdown(interpretacion_x)

                    fig_alloc = _grafico_base_frontera()
                    _agregar_frontera_a_grafico(fig_alloc, frontera_base_1b, "Frontera base", "#2a78d6")
                    fig_alloc.add_trace(go.Scatter(
                        x=xs_lmc, y=ys_lmc, mode="lines", line=dict(color="#eda100", width=2, dash="dash"), name="LMC",
                    ))
                    for c_val, color_c in zip((2, 5, 10), ("#1baf7a", "#e87ba4", "#4a3aa7")):
                        x_c = lab.asignacion_optima(frontera_base_1b["ret_tangencia"], rf_lab, frontera_base_1b["vol_tangencia"], c_val)
                        if x_c is not None:
                            vol_c = x_c * frontera_base_1b["vol_tangencia"]
                            ret_c = rf_lab + x_c * (frontera_base_1b["ret_tangencia"] - rf_lab)
                            fig_alloc.add_trace(go.Scatter(
                                x=[vol_c], y=[ret_c], mode="markers",
                                marker=dict(size=12, color=color_c, symbol="diamond"), name=f"c={c_val}",
                            ))
                    vol_slider_pt = x_slider * frontera_base_1b["vol_tangencia"]
                    ret_slider_pt = rf_lab + x_slider * (frontera_base_1b["ret_tangencia"] - rf_lab)
                    fig_alloc.add_trace(go.Scatter(
                        x=[vol_slider_pt], y=[ret_slider_pt], mode="markers",
                        marker=dict(size=14, color="black", symbol="x"), name=f"c={c_slider:.1f} (slider)",
                    ))
                    st.plotly_chart(fig_alloc, use_container_width=True)

                # ============================================================
                # 27. Validaciones
                # ============================================================
                st.subheader("15. Validaciones")
                validaciones = [
                    ("Σwi ≈ 1 (M)", abs(w_M.sum() - 1) < 1e-3),
                    ("LMC pasa por (0, Rf)", interseccion_ok),
                    ("LMC pasa por (σM, E(RM))", pasa_por_M),
                    ("β(S&P 500 vs. sí mismo) ≈ 1", abs(reg_auto_lab["beta"] - 1) < 0.01),
                    ("Observaciones suficientes para la regresión (≥30)", len(df_capm_lab) >= 30),
                    ("p-value coherente con t (|t| grande ⇒ p chico)", (reg_M["p_valor"] < 0.05) == (abs(reg_M["t_alfa"]) > 1.96)),
                ]
                cols_val = st.columns(3)
                for i, (nombre_val, ok_val) in enumerate(validaciones):
                    with cols_val[i % 3]:
                        st.markdown(f"{'✅' if ok_val else '⚠️'} {nombre_val}")

                # ============================================================
                # 28. Exportar resultados
                # ============================================================
                st.subheader("16. Exportar resultados")
                col_e1, col_e2, col_e3 = st.columns(3)
                col_e1.download_button(
                    "📥 Estadísticas de acciones (CSV)", df_stats_lab.to_csv().encode("utf-8"),
                    "laboratorio_estadisticas.csv", "text/csv",
                )
                col_e1.download_button(
                    "📥 Matriz de covarianzas (CSV)", cov_anual_lab.to_csv().encode("utf-8"),
                    "laboratorio_covarianzas.csv", "text/csv",
                )
                if resultado_actual is not None and resultado_actual["frontera"]:
                    df_frontera_export = pd.DataFrame(resultado_actual["frontera"], columns=["Volatilidad", "Retorno"])
                    col_e2.download_button(
                        "📥 Puntos de la frontera actual (CSV)", df_frontera_export.to_csv(index=False).encode("utf-8"),
                        "laboratorio_frontera.csv", "text/csv",
                    )
                col_e2.download_button(
                    "📥 Pesos de M (CSV)", tabla_pesos_M.to_csv(index=False).encode("utf-8"),
                    "laboratorio_pesos_M.csv", "text/csv",
                )
                df_capm_export = pd.DataFrame([{
                    "alfa_diario": reg_M["alfa"], "alfa_anual": reg_M["alfa"] * 252, "beta": reg_M["beta"],
                    "r2": reg_M["r2"], "se_alfa": reg_M["se_alfa"], "t_alfa": reg_M["t_alfa"],
                    "p_valor": reg_M["p_valor"], "ic_95_low": reg_M["ic_95"][0], "ic_95_high": reg_M["ic_95"][1],
                }])
                col_e3.download_button(
                    "📥 Resultados CAPM (CSV)", df_capm_export.to_csv(index=False).encode("utf-8"),
                    "laboratorio_capm.csv", "text/csv",
                )
                col_e3.download_button(
                    "📥 Sharpe/Treynor M vs. S&P 500 (CSV)", df_desempeno.to_csv().encode("utf-8"),
                    "laboratorio_sharpe_treynor.csv", "text/csv",
                )

        st.divider()
        st.info(
            "**Nota metodológica.** Retornos diarios reales (un precio idéntico al día anterior "
            "se conserva como retorno de 0% válido solo si tiene volumen propio y distinto de "
            "cero ese día; si el volumen es 0 o repite el del día anterior, se excluye por "
            "tratarse de un corte de la fuente de datos, no de un empate real de mercado), "
            "covarianza y frontera anualizadas × 252 ruedas — sin mezclar frecuencias. La "
            "frontera \"base\" (venta corta libre, sin límites) se resuelve con la solución "
            "matricial cerrada de Markowitz/Merton; cualquier restricción de desigualdad "
            "(límite ±X%, sin venta corta, piso sectorial) se resuelve con SLSQP (QP no lineal "
            "convexo) porque la solución cerrada ya no aplica. Si Ω está mal condicionada se "
            "regulariza (ver aviso en la sección 5 cuando ocurre). El desempeño de M es "
            "**in-sample** — ver advertencia en la sección 12. Herramienta educativa para "
            "reproducir la tarea, no una recomendación de inversión."
        )

        # ============================================================
        # Pregunta 2: Modelos de Estructura de Tasas
        # ============================================================
        st.divider()
        st.header("Pregunta 2: Modelos de Estructura de Tasas")
        st.caption(
            "Ajusta Nelson-Siegel (1987) y Svensson (1994) sobre la curva de tasas del "
            "Tesoro de EEUU (Treasury Constant Maturity, H.15 de la Reserva Federal), el "
            "último día hábil de junio de cada año entre 2017 y 2026 (10 fechas, 20 curvas "
            "ajustadas — 10 de cada modelo), encontrando los parámetros óptimos GLOBALES en "
            "cada ajuste (múltiples puntos de partida para τ, no solo el primer mínimo que "
            "encuentre el optimizador). "
            "**Nota de fuente:** los datos vienen de FRED (Federal Reserve Bank of St. "
            "Louis) en vez del downloader interactivo de federalreserve.gov/datadownload — "
            "es la MISMA serie H.15 (Treasury Constant Maturity), publicada por el mismo "
            "Sistema de la Reserva Federal, vía un endpoint CSV público más simple de "
            "automatizar que la herramienta de descarga manual."
        )

        # Detrás de un botón a propósito: ajustar 20 curvas (10 años × 2
        # modelos, cada uno con múltiples reintentos del optimizador para
        # encontrar el óptimo global) es la parte más pesada de todo el
        # dashboard — no debería correr automáticamente cada vez que
        # alguien abre la pestaña, solo cuando alguien realmente lo pide.
        st.session_state.setdefault("calcular_estructura_tasas", False)
        if st.button("📈 Calcular curvas de tasas (Nelson-Siegel + Svensson)"):
            st.session_state["calcular_estructura_tasas"] = True

        if not st.session_state["calcular_estructura_tasas"]:
            st.info("Apretá el botón de arriba para correr el ajuste (tarda unos segundos).")
        else:
            try:
                pivote_treasury = _cargar_curva_treasury(df_macro_lab)
                tabla_modelos = _ajustar_modelos_por_anio(pivote_treasury, ANIOS_TAREA_ESTRUCTURA_TASAS)

                if tabla_modelos.empty:
                    st.warning("Todavía no hay suficientes datos de Treasury Constant Maturity para ajustar los modelos.")
                else:
                    plazos_anios_lista = list(et.PLAZOS_ANIOS.values())

                    st.subheader("1. Curva observada vs. ajustada, por año")
                    anio_elegido = st.selectbox(
                        "Año (último día hábil de junio)", tabla_modelos["Año"].tolist(),
                        index=len(tabla_modelos) - 1,
                    )
                    fila_elegida = tabla_modelos[tabla_modelos["Año"] == anio_elegido].iloc[0]

                    fig_curva = go.Figure()
                    fig_curva.add_trace(go.Scatter(
                        x=plazos_anios_lista, y=fila_elegida["_tasas_obs"], mode="markers",
                        name="Observado (FRED)", marker=dict(size=10, color="black"),
                    ))
                    fig_curva.add_trace(go.Scatter(
                        x=plazos_anios_lista, y=fila_elegida["_ns_ajustado"], mode="lines", name="Nelson-Siegel",
                    ))
                    fig_curva.add_trace(go.Scatter(
                        x=plazos_anios_lista, y=fila_elegida["_sv_ajustado"], mode="lines", name="Svensson",
                        line=dict(dash="dash"),
                    ))
                    fig_curva.update_layout(
                        title=f"Curva de tasas del Tesoro de EEUU — {fila_elegida['Fecha']}",
                        xaxis_title="Plazo (años)", yaxis_title="Tasa (%)", height=450,
                    )
                    st.plotly_chart(fig_curva, use_container_width=True)
                    st.caption(
                        f"RMSE Nelson-Siegel: **{fila_elegida['RMSE Nelson-Siegel']:.4f} pp** — "
                        f"RMSE Svensson: **{fila_elegida['RMSE Svensson']:.4f} pp**."
                    )

                    st.subheader("2. Comparación de ajuste entre modelos (RMSE)")
                    tabla_rmse = tabla_modelos[
                        ["Año", "Fecha", "RMSE Nelson-Siegel", "RMSE Svensson", "Mejora Svensson (%)"]
                    ]
                    st.dataframe(
                        tabla_rmse.style.format({
                            "RMSE Nelson-Siegel": "{:.4f}",
                            "RMSE Svensson": "{:.4f}",
                            "Mejora Svensson (%)": "{:+.1f}%",
                        }),
                        use_container_width=True, hide_index=True,
                    )
                    fila_mejor = tabla_rmse.loc[tabla_rmse["Mejora Svensson (%)"].idxmax()]
                    fila_peor = tabla_rmse.loc[tabla_rmse["Mejora Svensson (%)"].idxmin()]
                    st.caption(
                        f"Svensson mejora MÁS el ajuste en **{int(fila_mejor['Año'])}** "
                        f"({fila_mejor['Mejora Svensson (%)']:+.1f}%) y MENOS en "
                        f"**{int(fila_peor['Año'])}** ({fila_peor['Mejora Svensson (%)']:+.1f}%). "
                        "En general, el término extra de Svensson (un segundo parámetro de "
                        "curvatura con su propio τ) ayuda más cuando la curva tiene una forma "
                        "compleja — invertida o con más de una \"joroba\" — y menos cuando la "
                        "curva es suave y sube monótonamente. Cambiá el año de la sección 1 para "
                        "ver la forma real de la curva en cada caso y confirmarlo vos mismo."
                    )

                    st.subheader("3. Evolución de los parámetros de Nelson-Siegel")
                    fig_params = go.Figure()
                    for columna, nombre_serie in [
                        ("β0 (nivel)", "β0 — nivel de largo plazo"),
                        ("β1 (pendiente)", "β1 — pendiente (corto − largo)"),
                        ("β2 (curvatura)", "β2 — curvatura"),
                    ]:
                        fig_params.add_trace(go.Scatter(
                            x=tabla_modelos["Año"], y=tabla_modelos[columna], mode="lines+markers", name=nombre_serie,
                        ))
                    fig_params.add_hline(y=0, line_dash="dot", line_color="gray")
                    fig_params.update_layout(xaxis_title="Año", yaxis_title="Valor del parámetro (pp)", height=450)
                    st.plotly_chart(fig_params, use_container_width=True)
                    st.caption(
                        "**β0 (nivel):** hacia dónde converge la tasa a plazos muy largos — el "
                        "\"piso\" de largo plazo de toda la curva. **β1 (pendiente):** aproximadamente "
                        "la tasa corta menos la larga — negativo cuando la curva sube (normal), "
                        "positivo cuando está invertida. **β2 (curvatura):** qué tan pronunciada es "
                        "la \"joroba\" en el tramo medio de la curva (plazos de 2-7 años)."
                    )

                    st.subheader("4. Datos objetivos para la Pregunta 3 (inversiones de la curva)")
                    st.caption(
                        "Esto calcula HECHOS de los datos — fechas y duración de cada inversión — "
                        "no es el análisis en sí. Conectalo vos con noticias y eventos económicos "
                        "reales de cada período para responder la Pregunta 3."
                    )
                    spread_10y2y = (pivote_treasury["10 años"] - pivote_treasury["2 años"]).dropna()
                    if len(spread_10y2y) < 2:
                        st.warning("Todavía no hay suficiente historia de 10 años y 2 años para calcular el spread.")
                    else:
                        fig_spread = go.Figure()
                        fig_spread.add_trace(go.Scatter(
                            x=spread_10y2y.index, y=spread_10y2y.values, mode="lines",
                            name="Spread 10 años − 2 años", line=dict(color="steelblue"),
                        ))
                        fig_spread.add_hline(y=0, line_dash="dash", line_color="red")
                        fig_spread.update_layout(
                            title="Spread 10Y-2Y del Tesoro de EEUU (negativo = curva invertida)",
                            xaxis_title="Fecha", yaxis_title="Spread (pp)", height=400,
                        )
                        st.plotly_chart(fig_spread, use_container_width=True)

                        invertida = spread_10y2y < 0
                        cambios = invertida.astype(int).diff().fillna(0)
                        inicios = spread_10y2y.index[cambios == 1].tolist()
                        if invertida.iloc[0]:
                            inicios = [spread_10y2y.index[0]] + inicios
                        finales = spread_10y2y.index[cambios == -1].tolist()
                        if invertida.iloc[-1]:
                            finales = finales + [spread_10y2y.index[-1]]
                        tramos_inversion = list(zip(inicios, finales))

                        if tramos_inversion:
                            st.write("**Períodos con curva invertida (spread 10Y-2Y negativo):**")
                            for inicio, fin in tramos_inversion:
                                dias = (fin - inicio).days
                                st.write(f"- {inicio.date()} a {fin.date()} ({dias} días corridos)")
                        else:
                            st.write("El spread 10Y-2Y no estuvo negativo en el período con datos disponible.")
            except Exception as e_estructura_tasas:
                st.warning(f"No se pudo calcular la sección de estructura de tasas: {e_estructura_tasas}")

    except Exception as e:
        st.error(f"No se pudo calcular el laboratorio financiero: {e}")
