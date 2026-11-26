"""Panoramas generales de FRI (etapa F2) con los datos y motores existentes del dashboard.

Solo presentación. Los datos llegan por los MISMOS cargadores del dashboard (cargar_series_macro y
cargar_precios_acciones, con su caché); los cálculos son funciones que ya existen:
    market_data.calcular_cambio_reciente   valor, fecha y cambio contra el dato anterior (el del Resumen)
    renta_fija.retorno_ultimo_anio          retorno de 12 meses (el de las tablas de Renta Fija, Divisas y Commodities)
    renta_fija.curva_en_fecha               última curva completa en una fecha (el de Renta Fija)
No se agrega ninguna fórmula financiera. Cuando falta un dato, la tarjeta o el gráfico dicen «No disponible» con el
motivo; nunca se rellena con otra serie ni con un número.

IPSA: el panorama usa SOLO una serie directa del índice. Hoy no hay una verificada en la base (el código de la serie del
Banco Central no se pudo confirmar en el catálogo público), así que se muestra «No disponible». ECH no se usa como IPSA.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import renta_fija as rf
import renta_fija_ui as rfui
from catalogo_commodities import COMMODITIES
from catalogo_fx import NOMBRE_COBRE, NOMBRE_TASA_CHILE, NOMBRE_TASA_EEUU, NOMBRE_TIPO_DE_CAMBIO_OBSERVADO, PARES_FX, TICKER_DXY, etiqueta_corta
from constants import TICKER_DOW_JONES, TICKER_NASDAQ
from fri import componentes as c
from fri.estilos import SANS, T
from market_data import INDICADORES_PREMERCADO, calcular_cambio_reciente

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
NOMBRE_POR_ETIQUETA = {etiqueta: clave for etiqueta, tipo, clave, *_ in INDICADORES_PREMERCADO if tipo == "macro"}
NOMBRE_IMACEC = NOMBRE_POR_ETIQUETA["Imacec"]
NOMBRE_IPC = NOMBRE_POR_ETIQUETA["IPC (inflación anual)"]
NOMBRE_DESEMPLEO = NOMBRE_POR_ETIQUETA["Tasa de desempleo"]
NOMBRE_TREASURY_10 = rfui.nombre_treasury("10 años")      # H.15 (decisión de H3-A: referencia preferida del Treasury)
TICKER_SP500 = "^GSPC"
INDICES = [(TICKER_SP500, "S&P 500"), (TICKER_DOW_JONES, "Dow Jones"), (TICKER_NASDAQ, "Nasdaq Composite"), ("EEM", "MSCI Emergentes (EEM)")]
PARES_PANORAMA = ["USDCLP=X", "EURUSD=X", "USDJPY=X", "USDBRL=X", "USDMXN=X"]
MOTIVO_IPSA = ("No hay una serie directa del IPSA verificada en la base. ECH (un ETF en dólares) no se presenta como IPSA. "
               "Fuente candidata: serie diaria del Banco Central de Chile, pendiente de confirmar.")


# ---------------------------------------------------------------------------
# Datos (de los cargadores del dashboard)
# ---------------------------------------------------------------------------
def tickers_necesarios(cual: str) -> tuple[str, ...]:
    """Solo los precios que usa cada panorama (cargar_precios_acciones filtra por ticker en la consulta)."""
    if cual == "macro":
        return (TICKER_DXY,)
    return tuple(dict.fromkeys([t for t, _ in INDICES] + PARES_PANORAMA + list(COMMODITIES)))


def serie_macro(df_macro: pd.DataFrame, nombre: str) -> pd.Series:
    if df_macro is None or df_macro.empty:
        return pd.Series(dtype=float)
    filas = df_macro[df_macro["nombre"] == nombre]
    s = pd.Series(pd.to_numeric(filas["valor"], errors="coerce").to_numpy(dtype=float), index=pd.to_datetime(filas["fecha"]))
    return s[~s.index.duplicated(keep="last")].sort_index().dropna()


def serie_precio(df_precios: pd.DataFrame, ticker: str) -> pd.Series:
    if df_precios is None or df_precios.empty:
        return pd.Series(dtype=float)
    filas = df_precios[df_precios["ticker"] == ticker]
    s = pd.Series(pd.to_numeric(filas["precio_cierre"], errors="coerce").to_numpy(dtype=float), index=pd.to_datetime(filas["fecha"]))
    return s[~s.index.duplicated(keep="last")].sort_index().dropna()


def _fecha(f, mensual: bool = False) -> str:
    f = pd.Timestamp(f)
    return f"{MESES[f.month - 1]} {f.year}" if mensual else f.strftime("%d-%m-%Y")


# ---------------------------------------------------------------------------
# Tarjetas
# ---------------------------------------------------------------------------
def tarjeta(nombre: str, serie: pd.Series, fuente: str, *, decimales: int = 2, sufijo: str = "", variacion: str = "pct",
            invertir: bool = False, mensual: bool = False, unidad: str = "", motivo_vacio: str = "Sin datos en la base.") -> str:
    """Valor, cambio contra el dato anterior (calcular_cambio_reciente) y su fecha real. variacion: pct | pp | pb."""
    r = calcular_cambio_reciente(serie)
    if r is None:
        return no_disponible(nombre, motivo_vacio)
    valor, cambio_pct, fecha, cambio_abs = r
    if variacion == "pp":
        ch = c.chip(cambio_abs, "pp", 1 if decimales <= 1 else 2, invertir)
    elif variacion == "pb":
        ch = c.chip(cambio_abs * 100, "pb", 0, invertir)
    else:
        ch = c.chip(cambio_pct, "%", 2, invertir)
    # La comparación se rotula con la FECHA del dato anterior: tras fines de semana, feriados o huecos no es «1 día».
    anterior = serie.dropna().index[-2]
    etiqueta = f"vs. {_fecha(anterior, mensual)}"
    return c.kpi(nombre, f"{c.num(valor, decimales)}{sufijo}", ch, etiqueta, serie.tail(60 if not mensual else 24).to_numpy(),
                 T["azul_dato"] if variacion != "pct" else c.color_tendencia(serie.tail(60).to_numpy()),
                 f"{fuente} · {_fecha(fecha, mensual)}", unidad)


def no_disponible(nombre: str, motivo: str) -> str:
    return (f'<div class="fri-kpi"><div class="nombre">{nombre}</div><div class="valor" style="font-size:20px;color:{T["texto_3"]}">No disponible</div>'
            f'<p style="color:{T["texto_2"]};font-size:13px;margin:6px 0 10px 0">{motivo}</p></div>')


def _fila(grupo_html: str, tarjetas: list[str]) -> None:
    columnas = "minmax(0,.8fr) " + " ".join(["minmax(0,1fr)"] * len(tarjetas))
    st.markdown(f'<div class="fri-kpis" style="grid-template-columns:{columnas}">{grupo_html}{"".join(tarjetas)}</div>', unsafe_allow_html=True)


def _titulo_panel(texto: str, nota: str = "") -> None:
    st.markdown(f'<div class="fri-panel-titulo"><div class="t">{texto}</div><span>{nota}</span></div>', unsafe_allow_html=True)


def _vacio(texto: str) -> None:
    st.markdown(f'<p style="color:{T["texto_3"]};font-size:14px;margin:18px 4px">No disponible: {texto}</p>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Gráficos (estilo FRI; los datos son las series de la base, sin transformaciones financieras)
# ---------------------------------------------------------------------------
def _figura(alto: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(height=alto, margin=dict(l=6, r=64, t=12, b=6), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family=SANS, color=T["texto_2"], size=13), hovermode="x unified",
                      legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
                      hoverlabel=dict(bgcolor=T["superficie_destacada"], font=dict(color=T["texto"], family=SANS), bordercolor=T["borde_fuerte"]))
    fig.update_xaxes(gridcolor="rgba(0,0,0,0)", linecolor=T["borde_fuerte"], tickfont=dict(color=T["texto_2"]))
    fig.update_yaxes(gridcolor="rgba(151,174,185,0.14)", zeroline=False, tickfont=dict(color=T["texto_2"]))
    return fig


def _etiqueta_final(fig, serie: pd.Series, texto: str, color: str) -> None:
    fig.add_annotation(x=serie.index[-1], y=float(serie.iloc[-1]), text=f"<b>{texto}</b>", showarrow=False, xanchor="left", xshift=8,
                       font=dict(color=T["fondo"], size=12.5), bgcolor=color, borderpad=3)


def _mostrar(fig) -> None:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _linea(series: list[tuple[str, pd.Series, str, str]], sufijo: str, decimales: int, alto: int = 300, escalon: bool = False) -> None:
    """series: (nombre, serie, color, estilo). Solo dibuja las que tienen datos; si ninguna tiene, lo dice."""
    con_datos = [(n, s, col, est) for n, s, col, est in series if len(s)]
    if not con_datos:
        _vacio("las series no tienen datos en la base.")
        return
    fig = _figura(alto)
    for nombre, s, color, estilo in con_datos:
        fig.add_scatter(x=s.index, y=s.values, name=nombre, line=dict(color=color, width=2.5, dash=estilo, shape="hv" if escalon else "linear"))
        _etiqueta_final(fig, s, f"{c.num(s.iloc[-1], decimales)}{sufijo}", color)
    fig.update_yaxes(ticksuffix=sufijo, tickformat=f",.{decimales}f")
    _mostrar(fig)


def _ultimo_anio(s: pd.Series, dias: int = 730) -> pd.Series:
    return s[s.index >= s.index[-1] - pd.Timedelta(days=dias)] if len(s) else s


# ---------------------------------------------------------------------------
# Macroeconomía → Panorama general
# ---------------------------------------------------------------------------
def panorama_macro(df_macro: pd.DataFrame, df_precios: pd.DataFrame) -> None:
    imacec, ipc, desempleo = (serie_macro(df_macro, n) for n in (NOMBRE_IMACEC, NOMBRE_IPC, NOMBRE_DESEMPLEO))
    tpm, dolar, cobre = (serie_macro(df_macro, n) for n in (NOMBRE_TASA_CHILE, NOMBRE_TIPO_DE_CAMBIO_OBSERVADO, NOMBRE_COBRE))
    fed, ust10 = serie_macro(df_macro, NOMBRE_TASA_EEUU), serie_macro(df_macro, NOMBRE_TREASURY_10)
    dxy = serie_precio(df_precios, TICKER_DXY)
    _fila(f'<div class="fri-kpi fri-grupo"><b>{c.bandera_chile(28)} Chile</b><span>Principales indicadores macroeconómicos</span></div>', [
        tarjeta("Imacec a/a", imacec, "BCCh", decimales=2, sufijo=" %", variacion="pp", mensual=True),
        tarjeta("IPC anual", ipc, "INE/BCCh", decimales=2, sufijo=" %", variacion="pp", invertir=True, mensual=True),
        tarjeta("Desempleo", desempleo, "INE", decimales=2, sufijo=" %", variacion="pp", invertir=True, mensual=True),
        tarjeta("TPM Chile", tpm, "BCCh", sufijo=" %", variacion="pb"),
        tarjeta("USD/CLP", dolar, "BCCh (dólar observado)", invertir=True),
        tarjeta("Precio del cobre", cobre, "BCCh", unidad="USD/lb"),
    ])
    _fila(f'<div class="fri-kpi fri-grupo"><b>{c.icono("globo", 24)} Entorno internacional</b><span>Referencias clave del contexto global</span></div>', [
        tarjeta("Tasa efectiva de fondos federales", fed, "FRED (DFF)", sufijo=" %", variacion="pb"),
        tarjeta("Treasury 10 años (H.15)", ust10, "FRED (H.15)", sufijo=" %", variacion="pb"),
        tarjeta("Dólar global (DXY)", dxy, "Yahoo Finance", decimales=2),
        no_disponible("Actividad económica de China", "Sin fuente verificada en FRI; no se muestra una cifra inventada."),
    ])
    col1, col2, col3 = st.columns(3, gap="medium")
    with col1, st.container(border=True):
        _titulo_panel("Inflación: IPC anual", "Variación en 12 meses (%)")
        _linea([("IPC anual", _ultimo_anio(ipc), T["dorado"], "solid")], " %", 2)
    with col2, st.container(border=True):
        _titulo_panel("TPM y tasa efectiva de fondos federales", "Tasa (%)")
        _linea([("TPM Chile", _ultimo_anio(tpm), T["dorado"], "solid"),
                ("Tasa efectiva de fondos federales", _ultimo_anio(fed), T["azul_dato"], "dash")], " %", 2, escalon=True)
    with col3, st.container(border=True):
        _titulo_panel("Mercado laboral: tasa de desempleo", "Tasa (%)")
        _linea([("Desempleo", _ultimo_anio(desempleo), T["dorado"], "solid")], " %", 2)
    st.markdown(f'<div class="fri-nota">Cada tarjeta muestra su fecha real y su fuente; el cambio es contra el dato anterior de la '
                f'misma serie (diario o mensual según la serie). El análisis interpretativo («Análisis FRI») está pendiente.</div>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Mercados → Panorama general
# ---------------------------------------------------------------------------
def _curva_bcp(df_macro: pd.DataFrame):
    """(fecha actual, curva actual, fecha hace un mes, curva hace un mes) con rf.curva_en_fecha, o None."""
    plazos = rfui.CURVA_CHILE["BCP (pesos)"]
    pivote = pd.concat({p: serie_macro(df_macro, n) for p, n in plazos.items()}, axis=1)
    if pivote.dropna().empty:
        return None
    f1, c1 = rf.curva_en_fecha(pivote, pivote.index.max())
    try:
        f0, c0 = rf.curva_en_fecha(pivote, f1 - pd.DateOffset(months=1))
    except ValueError:
        f0, c0 = None, None
    return f1, c1, f0, c0


def objetivo_mes_anterior(f1) -> pd.Timestamp:
    """La fecha buscada para la curva de comparación: un mes antes de la curva actual (se usa la última completa en o antes)."""
    return pd.Timestamp(f1) - pd.DateOffset(months=1)


def _tabla_instrumentos(filas_datos: list[tuple[str, pd.Series]], decimales: int = 2) -> str:
    filas, clases = [], []
    for nombre, s in filas_datos:
        r = calcular_cambio_reciente(s)
        anual = rf.retorno_ultimo_anio(s) if len(s) >= 2 else None
        if r is None:
            filas.append([nombre, "—", "—", "—"]); clases.append(["", "", "", ""]); continue
        filas.append([nombre, c.num(r[0], decimales), f"{c.num(r[1], 2, True)} %", f"{c.num(anual, 1, True)} %" if anual is not None else "—"])
        clases.append(["", "", c.clase_signo(r[1]), c.clase_signo(anual, 1) if anual is not None else ""])
    return c.tabla(["Instrumento", "Nivel", "Var.", "1A"], filas, clases)


def panorama_mercados(df_macro: pd.DataFrame, df_precios: pd.DataFrame) -> None:
    spx, dolar = serie_precio(df_precios, TICKER_SP500), serie_macro(df_macro, NOMBRE_TIPO_DE_CAMBIO_OBSERVADO)
    bcp10 = serie_macro(df_macro, rfui.NOMBRE_BCP10)
    st.markdown('<div class="fri-kpis" style="grid-template-columns:repeat(4,1fr)">' + "".join([
        no_disponible("IPSA (Chile)", MOTIVO_IPSA),
        tarjeta("S&P 500 (EE. UU.)", spx, "Yahoo Finance"),
        tarjeta("Tasa 10 años Chile (BCP)", bcp10, "BCCh", sufijo=" %", variacion="pb", invertir=True),
        tarjeta("USD/CLP (dólar observado)", dolar, "BCCh", invertir=True),
    ]) + "</div>", unsafe_allow_html=True)
    izq, der = st.columns([1.55, 1], gap="medium")
    with izq, st.container(border=True):
        _titulo_panel("IPSA: evolución y volumen")
        _vacio(MOTIVO_IPSA + " El volumen tampoco se inventa: requiere una fuente propia.")
    with der, st.container(border=True):
        _titulo_panel("Curva de tasas soberanas de Chile", "BCP · tasa (%) por plazo")
        curva = _curva_bcp(df_macro)
        if curva is None:
            _vacio("la base no tiene una curva BCP completa.")
        else:
            f1, c1, f0, c0 = curva
            fig = _figura(330)
            fig.add_scatter(x=list(c1.index), y=list(c1.values), name=f"Al {_fecha(f1)}", mode="lines+markers",
                            line=dict(color=T["dorado"], width=2.6), marker=dict(size=8))
            if c0 is not None:
                fig.add_scatter(x=list(c0.index), y=list(c0.values), name=f"Al {_fecha(f0)}", mode="lines+markers",
                                line=dict(color=T["azul_dato"], width=2.2), marker=dict(size=7))
            fig.update_xaxes(tickvals=list(c1.index), ticktext=[f"{p} años" for p in c1.index])
            fig.update_yaxes(ticksuffix=" %", tickformat=",.2f")
            fig.update_layout(hovermode="closest")
            _mostrar(fig)
            nota_previa = (f" La de comparación es la última completa en o antes del {_fecha(objetivo_mes_anterior(f1))} "
                           f"(un mes antes): {_fecha(f0)}." if f0 is not None else
                           " No hay una curva completa un mes antes: no se muestra la comparación.")
            st.markdown('<div class="fri-nota">Fuente: Banco Central de Chile (BCP 2, 5 y 10 años). Cada curva usa una sola fecha con los '
                        f'tres plazos (renta_fija.curva_en_fecha): la actual es del {_fecha(f1)}.{nota_previa}</div>', unsafe_allow_html=True)
    t1, t2, t3, t4 = st.columns([1.1, 1, 1.15, 1], gap="medium")
    with t1, st.container(border=True):
        _titulo_panel("Principales índices")
        st.markdown(_tabla_instrumentos([(n, serie_precio(df_precios, t)) for t, n in INDICES]), unsafe_allow_html=True)
    with t2, st.container(border=True):
        _titulo_panel("Divisas")
        st.markdown(_tabla_instrumentos([(etiqueta_corta(t), serie_precio(df_precios, t)) for t in PARES_PANORAMA if t in PARES_FX]),
                    unsafe_allow_html=True)
    with t3, st.container(border=True):
        _titulo_panel("Materias primas")
        filas = [("Cobre BCCh (USD/lb)", serie_macro(df_macro, NOMBRE_COBRE))]
        filas += [(datos["nombre"].split(" (")[0], serie_precio(df_precios, t)) for t, datos in COMMODITIES.items()][:5]
        st.markdown(_tabla_instrumentos(filas), unsafe_allow_html=True)
        st.markdown('<div class="fri-nota">Futuros continuos (Yahoo Finance): los cambios de contrato pueden generar saltos.</div>', unsafe_allow_html=True)
    with t4, st.container(border=True):
        st.markdown(f'<div class="fri-comentario"><div class="h4">{c.icono("documento", 22)} Panorama de mercados</div>'
                    f'<p>Comentario interpretativo pendiente: se redactará con datos verificados y fuentes visibles.</p>'
                    f'<span class="estado estado-pendiente">PENDIENTE</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="fri-nota">Var.: cambio contra el dato ANTERIOR de cada serie (calcular_cambio_reciente); no es necesariamente '
                'un cambio de un día (fines de semana, feriados o huecos). 1A: retorno de los últimos '
                '12 meses (renta_fija.retorno_ultimo_anio). Cada tabla usa la última fecha disponible de su propia serie.</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Riesgo y derivados → Panorama general
# ---------------------------------------------------------------------------
def panorama_riesgo() -> None:
    motivo = ("Requiere la serie directa del IPSA (no disponible). Los motores existentes (volatilidad, VaR, drawdown) se aplican hoy a "
              "acciones individuales en «Análisis de riesgo»; no se trasladan al índice sin validarlos.")
    st.markdown('<div class="fri-kpis" style="grid-template-columns:repeat(4,1fr)">' + "".join(
        no_disponible(n, motivo) for n in ("Volatilidad anualizada IPSA", "VaR IPSA (95 %, 1 día)", "Drawdown máximo IPSA",
                                           "Correlación IPSA / S&P 500")) + "</div>", unsafe_allow_html=True)
    st.markdown('<div class="fri-nota">Las métricas de riesgo disponibles (por acción y por cartera) están en las pestañas «Análisis de riesgo» y '
                '«Derivados».</div>', unsafe_allow_html=True)
