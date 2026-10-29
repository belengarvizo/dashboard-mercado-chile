"""
Sección «FX y Carry Trade» del dashboard: divisas REALES, tasas de varios países y el carry trade, con su explicación al pasar el mouse.

PARA QUÉ EXISTE
    Sigue el módulo de mercado FX de un curso de mercado de capitales y mesas de dinero (cómo se cotiza, qué mueve
    una divisa, diferencial de tasas, carry trade y su riesgo), con el criterio de las otras secciones nuevas: todo lo que
    se muestra son datos reales de la base y, al pasar el mouse por el nombre de una fila, aparece una explicación en
    palabras con los números de esa fila.

DE DÓNDE SALEN LOS DATOS (todos reales; ninguno es de ejemplo)
    - 13 pares de divisas y el índice dólar (tabla precios_acciones, bajados por scripts/actualizar_acciones.py), con 5 años.
    - Tasas de corto plazo: TPM de Chile y Fed funds (BCCh y FRED, ya en la base) y, para el carry, las de la zona euro,
      Reino Unido, Japón, México y Brasil (tabla series_macro, scripts/actualizar_bcch.py).
    - Dólar observado y precio del cobre del Banco Central de Chile, para el paso de Chile.
    - SIN DATOS: forwards y swaps de divisas (por eso no se calcula una cobertura), tasas al día de Canadá, Suiza,
      Australia y Nueva Zelanda (esas monedas están en la tabla de divisas pero no en el carry), costos de transacción
      y diferenciales compra/venta.
    - NO SE MUESTRAN las correlaciones de una divisa con la bolsa ni con el índice dólar: las barras diarias de Yahoo para
      divisas llevan otra convención de fecha (ver fx_carry.py, CORRELACIONES CON OTRAS SERIES) y saldrían cercanas a cero.

DECISIONES DE DISEÑO
    - La matemática vive en fx_carry.py (sin Streamlit, con sus pruebas); la tabla con tooltips en tabla_tooltips.py; las
      explicaciones en glosario_fx.py; los datos de cada par y moneda en catalogo_fx.py. Acá solo se arma la pantalla.
    - Los ayudantes de formato, gráficos y series son los de renta_fija_ui: son los mismos y ya están probados con datos reales.
    - Los controles son solo de vista (qué monedas graficar, qué período): no hay campos para inventar valores.
    - Selector de pasos con st.segmented_control (no st.tabs), estado bajo claves que empiezan con fx_.
    - Sin signo «$» en los textos: Streamlit lo toma como fórmula matemática.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import fx_carry as fx
import glosario_fx as gl
import renta_fija as rf
import renta_fija_ui as rfui
from catalogo_fx import (
    MONEDAS_CARRY, MONEDAS_SIN_TASA, NOMBRE_COBRE, NOMBRE_TASA_CHILE, NOMBRE_TASA_EEUU, NOMBRE_TIPO_DE_CAMBIO_OBSERVADO,
    PARES_FX, TICKER_DXY, TICKER_REFERENCIA, etiqueta_corta, nombre_de,
)
from tabla_tooltips import tabla_con_tooltips

PASOS = [
    "1. El mercado de divisas",
    "2. Tasas y carry",
    "3. La estrategia y su riesgo",
    "4. Chile: dólar, cobre y tasas",
]

NOMBRES_USADOS = {
    NOMBRE_TASA_EEUU, NOMBRE_TASA_CHILE, NOMBRE_TIPO_DE_CAMBIO_OBSERVADO, NOMBRE_COBRE,
    *(m["serie_tasa"] for m in MONEDAS_CARRY.values()),
}
# Cuántos días puede tener una tasa publicada antes de considerarla vencida (una mensual llega con ~1 mes de rezago).
ANTIGUEDAD_MAXIMA_DE_TASA = {"diaria": 10, "mensual": 75}
VENTANAS_ESTRATEGIA = {"1 año": 365, "3 años": 3 * 365, "5 años": 5 * 365}
VENTANAS_CHILE = {"1 año": 365, "5 años": 5 * 365, "Todo el historial": None}
VENTANA_CORRELACION_CHILE = 250  # ruedas (~1 año)

COLUMNAS_PARES = [
    "Grupo", "1D %", "1W %", "1M %", "YTD %", "Retorno 1 año (%)", "Volatilidad (%)", "Rango 1 año (%)", "Correlación vs referencia",
]
ENCABEZADOS_PARES = {
    "Retorno 1 año (%)": "1A %", "Volatilidad (%)": "Vol. %", "Rango 1 año (%)": "Rango 1A %", "Correlación vs referencia": "Correl. CLP",
}
COLUMNAS_DE_VARIACION_PARES = ["1D %", "1W %", "1M %", "YTD %"]
COLUMNAS_SECUENCIALES_PARES = ["Vol. %", "Rango 1A %"]

COLUMNAS_CARRY = [
    "Tasa local (%)", "Diferencial (pp)", "Spot 1 año (%)", "Carry 1 año (%)", "Total 1 año (%)", "Volatilidad (%)",
    "Caída máxima (%)", "Carry sobre riesgo",
]
ENCABEZADOS_CARRY = {
    "Tasa local (%)": "Tasa local", "Diferencial (pp)": "Difer. (pp)", "Spot 1 año (%)": "Spot 1A %", "Carry 1 año (%)": "Carry 1A %",
    "Total 1 año (%)": "Total 1A %", "Volatilidad (%)": "Vol. %", "Caída máxima (%)": "Caída máx. %", "Carry sobre riesgo": "Carry/Vol",
}
COLUMNAS_DE_VARIACION_CARRY = ["Difer. (pp)", "Spot 1A %", "Carry 1A %", "Total 1A %"]
COLUMNAS_SECUENCIALES_CARRY = ["Tasa local", "Vol. %"]

ROTULO_CARTERA = "Cartera"


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
def _recortar(df_macro: pd.DataFrame) -> pd.DataFrame:
    """Solo las series que usa esta sección (la tabla completa tiene ~90.000 filas)."""
    return df_macro[df_macro["nombre"].isin(NOMBRES_USADOS)]


def _tasa_de_la_moneda(macro: pd.DataFrame, codigo: str) -> pd.Series:
    return rfui._serie(macro, MONEDAS_CARRY[codigo]["serie_tasa"])


def _retornos_de_las_monedas(macro: pd.DataFrame, precios: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Retornos del carry (ver fx_carry.retornos_del_carry) de cada moneda que tiene tanto el par como su tasa."""
    tasa_usd = rfui._serie(macro, NOMBRE_TASA_EEUU)
    resultado = {}
    for codigo, datos in MONEDAS_CARRY.items():
        tasa = _tasa_de_la_moneda(macro, codigo)
        if datos["par"] not in precios or tasa.empty or tasa_usd.empty:
            continue
        valor = fx.valor_en_dolares(precios[datos["par"]], datos["base_es_dolar"])
        retornos = fx.retornos_del_carry(
            valor, tasa, tasa_usd, ANTIGUEDAD_MAXIMA_DE_TASA[datos["frecuencia"]], ANTIGUEDAD_MAXIMA_DE_TASA["diaria"],
        )
        if len(retornos):
            resultado[codigo] = retornos
    return resultado


def _fecha_de_la_tasa(macro: pd.DataFrame, codigo: str) -> str | None:
    ultimo = rfui._ultimo(macro, MONEDAS_CARRY[codigo]["serie_tasa"])
    return rfui._fecha(ultimo[1]) if ultimo else None


# ---------------------------------------------------------------------------
# Paso 1: el mercado de divisas
# ---------------------------------------------------------------------------
def _resumen_de_pares(precios: pd.DataFrame, hoy: pd.Timestamp) -> pd.DataFrame | None:
    """Una fila por par (indexada por su etiqueta corta, «USD/CLP»), o None si no hay datos."""
    referencia = precios[TICKER_REFERENCIA] if TICKER_REFERENCIA in precios else pd.Series(dtype=float)
    filas = {}
    for ticker, datos in PARES_FX.items():
        if ticker not in precios:
            continue
        # El índice dólar tiene otra convención de fecha que los pares «=X»: su correlación con USD/CLP no se calcula.
        r = fx.resumen_de_par(precios[ticker], pd.Series(dtype=float) if ticker == TICKER_DXY else referencia)
        if r is None:
            continue
        atraso = int(np.busday_count(r["ultima_fecha"].date(), hoy.date()))
        r.update({"Grupo": datos["grupo"], "ticker": ticker, "_atrasado_bool": atraso > rfui.DIAS_HABILES_DE_ATRASO})
        filas[etiqueta_corta(ticker)] = r
    if not filas:
        return None
    tabla = pd.DataFrame.from_dict(filas, orient="index")
    numericas = [c for c in COLUMNAS_PARES if c != "Grupo"]
    tabla[numericas] = tabla[numericas].apply(pd.to_numeric, errors="coerce")
    return tabla


def _tabla_de_pares_html(resumen: pd.DataFrame) -> str:
    def _valor(fila, columna):
        return None if pd.isna(fila[columna]) else float(fila[columna])

    def tooltip(etiqueta: str, fila: pd.Series) -> str:
        completa = resumen.loc[etiqueta]
        return "<hr>".join([
            gl.explicacion_par(completa["ticker"]),
            gl.explicacion_movimiento(completa["ticker"], _valor(completa, "1M %"), _valor(completa, "YTD %")),
            gl.explicacion_volatilidad(_valor(completa, "Volatilidad (%)")),
            gl.explicacion_rango(_valor(completa, "Rango 1 año (%)")),
            gl.explicacion_correlacion_referencia(
                _valor(completa, "Correlación vs referencia"), etiqueta, etiqueta_corta(TICKER_REFERENCIA),
                sin_convencion_comun=completa["ticker"] == TICKER_DXY),
        ])

    formatos = {c: "{:+.2f}%" for c in COLUMNAS_DE_VARIACION_PARES}
    formatos.update({"1A %": "{:+.2f}%", "Vol. %": "{:.2f}%", "Rango 1A %": "{:.2f}%", "Correl. CLP": "{:.2f}"})
    vista = resumen[COLUMNAS_PARES + ["_atrasado_bool"]].rename(columns=ENCABEZADOS_PARES)
    return tabla_con_tooltips(vista, COLUMNAS_DE_VARIACION_PARES, COLUMNAS_SECUENCIALES_PARES, formatos, tooltip, "Par")


def _paso_mercado(precios: pd.DataFrame) -> None:
    st.markdown(
        "Una **divisa** se compra y se vende contra otra: siempre es un par. En **EUR/USD** el euro es la moneda **base** y el "
        "precio dice cuántos dólares cuesta 1 euro; en **USD/CLP** la base es el dólar y el precio dice cuántos pesos cuesta "
        "1 dólar. Si el precio sube, la moneda base se fortaleció. El mercado funciona fuera de bolsa, entre bancos, las 24 horas "
        "de lunes a viernes, y es el más grande del mundo."
    )
    st.markdown(
        "Las **mesas de dinero** ganan con dos cosas: el **diferencial** entre el precio al que compran y al que venden "
        "(*bid* y *ask*) y la posición que toman. Los precios de abajo son los de cierre de cada día; la base no tiene los precios "
        "de compra y venta ni los *forwards* (precios a futuro) de las divisas, y por eso la pantalla no los muestra."
    )
    st.subheader("Los pares de divisas (datos reales)")
    resumen = _resumen_de_pares(precios, pd.Timestamp.now().normalize())
    if resumen is None:
        rfui._sin_datos("los pares de divisas")
        return
    st.markdown(_tabla_de_pares_html(resumen), unsafe_allow_html=True)
    st.caption(
        f"Datos al {rfui._fecha(resumen['ultima_fecha'].max())}. **1A** = retorno del último año · **Vol.** = volatilidad · "
        "**Rango 1A** = diferencia entre el precio más alto y el más bajo del último año · **Correl. CLP** = correlación de sus retornos "
        "diarios del último año con USD/CLP."
    )
    st.caption(
        "Aquí **verde** significa que el precio del par subió y **rojo** que bajó: no que haya sido bueno o malo. Si USD/CLP sube, "
        "el dólar se fortaleció y el peso chileno se debilitó. Los pares que empiezan con USD suben cuando el dólar se fortalece; "
        "los que terminan en USD (EUR/USD, GBP/USD) bajan, y por eso su correlación con USD/CLP sale negativa aunque se muevan "
        "«igual» frente al dólar. Pasa el mouse sobre cada par para ver la explicación con sus números."
    )
    st.info(
        "**Lo que esta tabla no muestra, a propósito:** la correlación de una divisa con la bolsa o con el índice dólar. Las barras diarias de "
        "divisas de Yahoo llevan otra convención de fecha que las acciones y el índice (en 50% a 90% de ellas el cierre es idéntico a la "
        "apertura del mismo día, y cada fila corresponde a la rueda anterior de las otras series): al compararlas el mismo día, EUR/USD contra "
        "el índice dólar da -0.09 y, con un día de desfase, -0.88. Correlacionarlas sin corregir saldría cerca de cero y se leería "
        "como «no tienen relación», lo que es falso; y corregirlas desplazando una serie sería suponer. Entre divisas sí se compara: "
        "todas tienen la misma fuente y la misma convención."
    )

    st.subheader("Comparar en el tiempo")
    disponibles = [t for t in PARES_FX if t in precios]
    elegidos = st.multiselect(
        "Elige pares a comparar", disponibles, default=[t for t in ("USDCLP=X", "EURUSD=X", "USDBRL=X", "USDJPY=X") if t in disponibles],
        key="fx_pares_grafico", format_func=lambda t: f"{etiqueta_corta(t)} · {nombre_de(t)}",
    )
    ventana = st.radio("Período", list(rfui.VENTANAS_ETF), horizontal=True, index=1, key="fx_ventana_pares")
    if not elegidos:
        st.info("Elige al menos un par para ver el gráfico.")
        return
    tramo = rfui._recortar_ventana(precios[elegidos].dropna(how="all"), rfui.VENTANAS_ETF[ventana]).ffill().dropna()
    fig = rfui._figura(380)
    for ticker in elegidos:
        fig.add_trace(go.Scatter(x=tramo.index, y=tramo[ticker] / tramo[ticker].iloc[0] * 100, mode="lines", name=etiqueta_corta(ticker)))
    fig.update_layout(yaxis_title="Precio del par, base 100")
    rfui._grafico(fig)


# ---------------------------------------------------------------------------
# Paso 2: tasas y carry
# ---------------------------------------------------------------------------
def _resumen_del_carry(macro: pd.DataFrame, precios: pd.DataFrame, hoy: pd.Timestamp) -> pd.DataFrame | None:
    retornos = _retornos_de_las_monedas(macro, precios)
    tasa_usd = rfui._ultimo(macro, NOMBRE_TASA_EEUU)
    filas = {}
    for codigo, r in retornos.items():
        resumen = fx.resumen_del_carry(r, rf.DIAS_DEL_ANIO)
        if resumen is None:
            continue
        tasa_local = rfui._ultimo(macro, MONEDAS_CARRY[codigo]["serie_tasa"])
        atraso = int(np.busday_count(resumen["hasta"].date(), hoy.date()))
        filas[codigo] = {
            "Tasa local (%)": tasa_local[0] if tasa_local else None,
            "Diferencial (pp)": resumen["diferencial_actual"], "Spot 1 año (%)": resumen["spot"],
            "Carry 1 año (%)": resumen["carry"], "Total 1 año (%)": resumen["total"],
            "Volatilidad (%)": resumen["volatilidad_spot"], "Caída máxima (%)": resumen["caida_maxima"],
            "Carry sobre riesgo": resumen["carry_sobre_riesgo"],
            "tasa_usd": tasa_usd[0] if tasa_usd else None, "diferencial_promedio": resumen["diferencial_promedio"],
            "hasta": resumen["hasta"], "_atrasado_bool": atraso > rfui.DIAS_HABILES_DE_ATRASO,
        }
    if not filas:
        return None
    tabla = pd.DataFrame.from_dict(filas, orient="index")
    tabla[COLUMNAS_CARRY] = tabla[COLUMNAS_CARRY].apply(pd.to_numeric, errors="coerce")
    return tabla


def _tabla_de_carry_html(resumen: pd.DataFrame, macro: pd.DataFrame) -> str:
    def _valor(fila, columna):
        return None if pd.isna(fila[columna]) else float(fila[columna])

    def tooltip(codigo: str, fila: pd.Series) -> str:
        completa = resumen.loc[codigo]
        articulo = MONEDAS_CARRY[codigo]["con_articulo"]
        return "<hr>".join([
            gl.explicacion_moneda(codigo, _valor(completa, "Tasa local (%)"), _fecha_de_la_tasa(macro, codigo)),
            gl.explicacion_diferencial(articulo, _valor(completa, "Tasa local (%)"), _valor(completa, "tasa_usd"), _valor(completa, "Diferencial (pp)")),
            gl.explicacion_spot_y_total(articulo, _valor(completa, "Spot 1 año (%)"), _valor(completa, "Carry 1 año (%)"), _valor(completa, "Total 1 año (%)")),
            gl.explicacion_riesgo_carry(_valor(completa, "Volatilidad (%)"), _valor(completa, "Caída máxima (%)"), _valor(completa, "Carry sobre riesgo")),
        ])

    formatos = {c: "{:+.2f}%" for c in ("Spot 1A %", "Carry 1A %", "Total 1A %")}
    formatos.update({
        "Tasa local": "{:.2f}%", "Difer. (pp)": "{:+.2f}", "Vol. %": "{:.2f}%", "Caída máx. %": "{:.2f}%",
        "Carry/Vol": "{:.2f}",
    })
    vista = resumen[COLUMNAS_CARRY + ["_atrasado_bool"]].rename(columns=ENCABEZADOS_CARRY)
    return tabla_con_tooltips(vista, COLUMNAS_DE_VARIACION_CARRY, COLUMNAS_SECUENCIALES_CARRY, formatos, tooltip, "Moneda")


def _grafico_de_compensacion(resumen: pd.DataFrame) -> None:
    """Un punto por moneda: diferencial de tasas promedio (eje X) contra lo que se movió su tipo de cambio (eje Y)."""
    fig = rfui._figura(430)
    fig.update_layout(hovermode="closest")
    limite = float(max(resumen["diferencial_promedio"].abs().max(), resumen["Spot 1 año (%)"].abs().max(), 1.0)) * 1.15
    fig.add_trace(go.Scatter(
        x=[-limite, limite], y=[limite, -limite], mode="lines", name="La teoría: el tipo de cambio anula el diferencial",
        line=dict(color=rfui.GRIS, dash="dash"), hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=resumen["diferencial_promedio"], y=resumen["Spot 1 año (%)"], text=list(resumen.index), mode="markers+text",
        textposition="top center", name="Lo que pasó", marker=dict(size=11, color=rfui.AZUL),
        hovertemplate="%{text}<br>Diferencial promedio %{x:+.2f} pp<br>Tipo de cambio %{y:+.1f}%<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(title="Diferencial de tasas promedio del año (puntos porcentuales)", range=[-limite, limite], zeroline=True),
        yaxis=dict(title="Cuánto se movió la moneda frente al dólar en el año (%)", range=[-limite, limite], zeroline=True),
    )
    rfui._grafico(fig)


def _paso_carry(macro: pd.DataFrame, precios: pd.DataFrame) -> None:
    st.markdown(
        "Cada país fija una **tasa de interés** distinta. El **carry trade** aprovecha la diferencia: se pide prestada una moneda "
        "de tasa baja y se coloca el dinero en una de tasa alta; se gana el **diferencial** mientras el tipo de cambio no se mueva "
        "en contra. Abajo, cada fila es la posición «**comprar esa moneda financiándose en dólares**»: el resultado del año es el "
        "**spot** (cuánto se movió la moneda frente al dólar) más el **carry** (el diferencial de tasas)."
    )
    st.subheader("Carry de cada moneda contra el dólar (datos reales)")
    resumen = _resumen_del_carry(macro, precios, pd.Timestamp.now().normalize())
    if resumen is None:
        rfui._sin_datos("tasas y tipos de cambio para calcular el carry")
        return
    st.markdown(_tabla_de_carry_html(resumen, macro), unsafe_allow_html=True)
    tasa_usd = resumen["tasa_usd"].dropna()
    st.caption(
        f"Datos al {rfui._fecha(resumen['hasta'].max())}. La tasa de EEUU es la Fed funds"
        + (f" ({tasa_usd.iloc[0]:.2f}%)" if len(tasa_usd) else "")
        + ". **Difer.** = tasa local − tasa de EEUU, en puntos porcentuales; **Spot / Carry / Total 1A** = resultado de comprar la moneda "
        "financiándose en dólares durante el último año; **Carry/Vol** = diferencial dividido por la volatilidad del tipo de cambio. "
        "Un diferencial **negativo** significa que el carry va al revés: "
        "lo gana quien compra dólares y se financia en esa moneda (el caso clásico del yen)."
    )
    st.caption(
        "Las tasas de Japón, México y Brasil son tasas interbancarias de corto plazo de la OCDE, **mensuales**, y llegan con cerca de un mes "
        "de rezago: dentro de cada mes se mantienen constantes. Las del BCE, Reino Unido, Chile y EEUU son diarias. No son lo que "
        "pagaría un inversionista de verdad (no hay costos de transacción ni diferenciales compra/venta)."
    )
    sin_tasa = ", ".join(MONEDAS_SIN_TASA.values())
    st.info(
        f"**Sin tasa al día en la base:** {sin_tasa}. Esas monedas están en la tabla de divisas del paso 1, pero no aquí: las series "
        "gratuitas de sus tasas no existen o terminan en 2023-2024, y no se rellenan con otra cosa."
    )

    positivas = int((resumen["Total 1 año (%)"] > 0).sum())
    st.subheader("¿Se compensó el diferencial con el tipo de cambio?")
    st.markdown(
        "La teoría (paridad descubierta de tasas) dice que una moneda de tasa alta debería **debilitarse** lo justo para anular su "
        "ventaja: así nadie ganaría con el carry. En el gráfico, esa teoría es la línea punteada. Los puntos **sobre** la línea son "
        "monedas que se debilitaron menos de lo que la teoría esperaba (o se fortalecieron), y el carry ganó; los puntos **bajo** ella, "
        "lo contrario."
    )
    _grafico_de_compensacion(resumen)
    st.markdown(f"En el último año, comprar la moneda financiándose en dólares ganó en **{positivas} de {len(resumen)}** monedas.")


# ---------------------------------------------------------------------------
# Paso 3: la estrategia y su riesgo
# ---------------------------------------------------------------------------
def _estadisticas_de_estrategias(retornos: dict[str, pd.DataFrame], dias: int) -> tuple[dict, dict, pd.DataFrame]:
    """(estadísticas por moneda y de la cartera, lado de hoy de cada moneda, retornos diarios de cada estrategia + cartera)."""
    estrategias = {codigo: fx.estrategia_de_carry(r) for codigo, r in retornos.items()}
    series = pd.DataFrame({codigo: e["retorno"] for codigo, e in estrategias.items()})
    series[ROTULO_CARTERA] = fx.cartera_de_igual_peso(pd.DataFrame({c: e["retorno"] for c, e in estrategias.items()}))
    lados = {codigo: ("larga" if e["lado"].iloc[-1] > 0 else "corta" if e["lado"].iloc[-1] < 0 else None) for codigo, e in estrategias.items()}
    estadisticas = {nombre: fx.estadisticas_de_retornos(series[nombre], dias) for nombre in series.columns}
    return estadisticas, lados, series


def _tabla_de_estrategias_html(estadisticas: dict, lados: dict) -> str:
    filas = {}
    for nombre, e in estadisticas.items():
        if e is None:
            continue
        filas[nombre] = {
            "Lado hoy": {"larga": "Larga", "corta": "Corta"}.get(lados.get(nombre), "Mixto" if nombre == ROTULO_CARTERA else "—"),
            "Retorno/año %": e["anualizado"], "Vol. %": e["volatilidad"], "Caída máx. %": e["caida_maxima"],
            "Peor mes %": e["peor_mes"], "Meses gan. %": e["meses_ganadores"],
        }
    tabla = pd.DataFrame.from_dict(filas, orient="index")
    numericas = [c for c in tabla.columns if c != "Lado hoy"]
    tabla[numericas] = tabla[numericas].apply(pd.to_numeric, errors="coerce")

    def tooltip(nombre: str, fila: pd.Series) -> str:
        articulo = MONEDAS_CARRY[nombre]["con_articulo"] if nombre in MONEDAS_CARRY else "la cartera de monedas"
        return gl.explicacion_estrategia(articulo, lados.get(nombre), estadisticas.get(nombre))

    formatos = {"Retorno/año %": "{:+.2f}%", "Vol. %": "{:.2f}%", "Caída máx. %": "{:.2f}%", "Peor mes %": "{:+.2f}%", "Meses gan. %": "{:.0f}%"}
    return tabla_con_tooltips(tabla, ["Retorno/año %"], ["Vol. %"], formatos, tooltip, "Estrategia")


def _paso_estrategia(macro: pd.DataFrame, precios: pd.DataFrame) -> None:
    st.markdown(
        "La **estrategia de carry** es mecánica: cada día compra la moneda cuya tasa supera a la de EEUU (financiándose en dólares) y "
        "vende la que tiene tasa menor (comprando dólares). El lado de cada día se decide con el diferencial que se conocía **el día "
        "anterior**, no con datos del futuro. La **cartera** reparte el dinero en partes iguales entre las monedas con dato."
    )
    retornos = _retornos_de_las_monedas(macro, precios)
    if not retornos:
        rfui._sin_datos("tasas y tipos de cambio para armar la estrategia")
        return
    ventana = st.radio("Período", list(VENTANAS_ESTRATEGIA), horizontal=True, index=2, key="fx_ventana_estrategia")
    dias = VENTANAS_ESTRATEGIA[ventana]
    estadisticas, lados, series = _estadisticas_de_estrategias(retornos, dias)

    st.subheader("Resultado y riesgo de la estrategia (datos reales)")
    if all(e is None for e in estadisticas.values()):
        rfui._sin_datos("suficientes días para medir la estrategia en este período")
        return
    st.markdown(_tabla_de_estrategias_html(estadisticas, lados), unsafe_allow_html=True)
    st.caption(
        "**Retorno/año** es geométrico; **Peor mes** es el peor retorno de 21 ruedas seguidas; **Meses gan.** es el porcentaje de meses "
        "calendario con retorno positivo. **Lado hoy** es la posición con la que la estrategia amanece hoy. Pasa el mouse sobre cada fila "
        "para ver la explicación con sus números."
    )
    cartera = estadisticas.get(ROTULO_CARTERA)
    if cartera and cartera.get("peor_mes") is not None:
        st.markdown(
            f"El peor mes de la **cartera** fue **{cartera['peor_mes']:+.1f}%** (21 ruedas terminadas el {rfui._fecha(cartera['fecha_peor_mes'])}), "
            f"y su peor caída desde un máximo fue de **{abs(cartera['caida_maxima']):.1f}%**."
        )

    st.subheader("Cómo creció cada estrategia")
    opciones = [ROTULO_CARTERA] + [c for c in retornos]
    elegidas = st.multiselect(
        "Elige estrategias a comparar", opciones, default=[o for o in (ROTULO_CARTERA, "JPY", "BRL") if o in opciones],
        key="fx_estrategias_grafico",
        format_func=lambda o: "Cartera de igual peso" if o == ROTULO_CARTERA else f"{o} · {MONEDAS_CARRY[o]['nombre']}",
    )
    if not elegidas:
        st.info("Elige al menos una estrategia para ver el gráfico.")
        return
    fig = rfui._figura(400)
    for nombre in elegidas:
        r = rfui._recortar_ventana(series[nombre].dropna(), dias)
        if len(r):
            fig.add_trace(go.Scatter(x=r.index, y=(1 + r).cumprod() * 100, mode="lines", name=nombre))
    fig.update_layout(yaxis_title="Valor de 100 invertidos al inicio del período")
    rfui._grafico(fig)
    st.caption(
        "El carry suele subir de a poco y caer de golpe: las pérdidas grandes llegan cuando muchos inversionistas deshacen la posición a la vez "
        "(a comienzos de agosto de 2024 el yen se fortaleció de golpe). Un período largo muestra esos golpes; uno corto puede esconderlos. "
        "Un límite de lo que se ve aquí: no se muestra qué hizo la bolsa esos mismos días, porque no se pueden alinear con confianza (ver el aviso del paso 1)."
    )


# ---------------------------------------------------------------------------
# Paso 4: Chile
# ---------------------------------------------------------------------------
def _paso_chile(macro: pd.DataFrame, precios: pd.DataFrame) -> None:
    dolar = rfui._serie(macro, NOMBRE_TIPO_DE_CAMBIO_OBSERVADO)
    cobre = rfui._serie(macro, NOMBRE_COBRE)
    tpm = rfui._serie(macro, NOMBRE_TASA_CHILE)
    fed = rfui._serie(macro, NOMBRE_TASA_EEUU)
    st.markdown(
        "La explicación habitual es que el peso chileno se mueve con las **materias primas**: cerca de la mitad de lo que Chile exporta es "
        "cobre, y cuando el cobre sube entran más dólares al país y el peso tiende a fortalecerse, es decir, **USD/CLP baja**. A eso se "
        "suman las **tasas**: la diferencia entre la TPM y la tasa de la Fed cambia lo atractivo que es tener pesos. Abajo está lo "
        "que muestran los datos del Banco Central, y cuánta de esa relación se ve de verdad."
    )
    if dolar.empty or cobre.empty:
        rfui._sin_datos("el dólar observado o el precio del cobre")
        return
    ventana = st.radio("Período", list(VENTANAS_CHILE), horizontal=True, index=1, key="fx_ventana_chile")
    dias = VENTANAS_CHILE[ventana]

    st.subheader("Dólar y cobre")
    movil = fx.correlacion_movil(dolar, cobre, VENTANA_CORRELACION_CHILE)
    c1, c2, c3 = st.columns(3)
    c1.metric("Dólar observado (pesos)", f"{rfui._fmt(dolar.iloc[-1], 2)}")
    c1.caption(f"Al {rfui._fecha(dolar.index[-1])} · Banco Central")
    c2.metric("Cobre (USD por libra)", f"{rfui._fmt(cobre.iloc[-1], 2)}")
    c2.caption(f"Al {rfui._fecha(cobre.index[-1])} · Banco Central")
    if len(movil):
        c3.metric("Correlación dólar-cobre, último año", f"{movil.iloc[-1]:.2f}")
        c3.caption("De los retornos diarios, ventana de 250 ruedas")
    conjunto = rfui._recortar_ventana(pd.concat([dolar, cobre], axis=1, join="inner", keys=["dolar", "cobre"]).dropna(), dias)
    if len(conjunto) >= 2:
        fig = rfui._figura(380)
        fig.add_trace(go.Scatter(x=conjunto.index, y=conjunto["dolar"] / conjunto["dolar"].iloc[0] * 100, mode="lines", name="Dólar observado (USD/CLP)"))
        fig.add_trace(go.Scatter(x=conjunto.index, y=conjunto["cobre"] / conjunto["cobre"].iloc[0] * 100, mode="lines", name="Cobre"))
        fig.update_layout(yaxis_title="Base 100 al inicio del período")
        rfui._grafico(fig)
    if len(movil):
        recortada = rfui._recortar_ventana(movil, dias)
        fig = rfui._figura(260)
        fig.add_trace(go.Scatter(x=recortada.index, y=recortada.values, mode="lines", name="Correlación móvil de 1 año", line=dict(color=rfui.ROJO)))
        fig.add_hline(y=0, line_dash="dot", line_color=rfui.GRIS)
        fig.update_layout(yaxis=dict(title="Correlación", range=[-1, 1]), showlegend=False)
        rfui._grafico(fig)
        actual = float(movil.iloc[-1])
        fuerza = "débil" if abs(actual) < 0.2 else "moderada" if abs(actual) < 0.5 else "fuerte"
        sentido = "negativa (cuando el cobre sube, el dólar tiende a bajar)" if actual < 0 else "positiva (cuando el cobre sube, el dólar tiende a subir)"
        st.caption(
            f"La correlación del último año es **{actual:.2f}**: una relación **{fuerza}** y {sentido} en los retornos diarios. "
            "Una correlación diaria baja no descarta que los dos se muevan juntos en tendencias más largas, y no prueba que uno cause al otro; "
            "cambia con el momento del mercado."
        )

    st.subheader("Dólar y diferencial de tasas")
    if tpm.empty or fed.empty:
        rfui._sin_datos("la TPM o la tasa de la Fed")
    else:
        fechas = dolar.index
        diferencial = fx.tasa_en_cada_fecha(tpm, fechas, 10) - fx.tasa_en_cada_fecha(fed, fechas, 10)
        tramo_dolar = rfui._recortar_ventana(dolar, dias)
        tramo_dif = rfui._recortar_ventana(diferencial.dropna(), dias)
        fig = rfui._figura(380)
        fig.add_trace(go.Scatter(x=tramo_dif.index, y=tramo_dif.values, mode="lines", name="TPM de Chile − tasa de la Fed (puntos, eje izquierdo)", line=dict(color=rfui.VERDE)))
        fig.add_trace(go.Scatter(x=tramo_dolar.index, y=tramo_dolar.values, mode="lines", name="Dólar observado (eje derecho)", yaxis="y2", line=dict(color=rfui.AZUL)))
        fig.update_layout(
            yaxis=dict(title="Diferencial (pp)"), yaxis2=dict(title="Pesos por dólar", overlaying="y", side="right", showgrid=False),
        )
        rfui._grafico(fig)
        if len(diferencial.dropna()):
            st.caption(
                f"Hoy la TPM de Chile ({tpm.iloc[-1]:.2f}%) está {abs(diferencial.dropna().iloc[-1]):.2f} puntos "
                f"{'sobre' if diferencial.dropna().iloc[-1] >= 0 else 'bajo'} la tasa de la Fed ({fed.iloc[-1]:.2f}%). Esa diferencia es lo que "
                "gana, antes del tipo de cambio, quien compra pesos financiándose en dólares."
            )

    if "USDCLP=X" in precios and len(dolar):
        yahoo = precios["USDCLP=X"].dropna()
        comun = dolar.index.intersection(yahoo.index)
        if len(comun):
            ultima = comun[-1]
            diferencia = (yahoo.loc[ultima] / dolar.loc[ultima] - 1) * 100
            st.caption(
                f"Comprobación de datos: el último día en común ({rfui._fecha(ultima)}), el USD/CLP de Yahoo ({yahoo.loc[ultima]:,.2f}) y el dólar "
                f"observado del Banco Central ({dolar.loc[ultima]:,.2f}) difieren {diferencia:+.2f}%. No son iguales porque son datos distintos: "
                "el observado es un promedio del día en Chile y el de Yahoo trae su propia convención de fecha (ver el aviso del paso 1)."
            )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def render_fx_carry(df_macro: pd.DataFrame, df_precios: pd.DataFrame) -> None:
    st.header("FX y carry trade: divisas, tasas y el diferencial")
    st.info(
        "Todos los datos de esta sección son **reales**: tipos de cambio (Yahoo Finance), tasas de política o interbancarias de varios países "
        "(Banco Central de Chile, FRED y la OCDE) y el dólar observado y el cobre del Banco Central. Donde la base no tiene un dato, la pantalla lo dice."
    )
    macro = _recortar(df_macro)
    precios = rfui._precios_en_columnas(df_precios)
    paso = st.segmented_control("Paso", PASOS, default=PASOS[0], key="fx_paso", label_visibility="collapsed") or PASOS[0]

    if precios.empty:
        rfui._sin_datos("los pares de divisas")
    elif paso == PASOS[0]:
        _paso_mercado(precios)
    elif paso == PASOS[1]:
        _paso_carry(macro, precios)
    elif paso == PASOS[2]:
        _paso_estrategia(macro, precios)
    else:
        _paso_chile(macro, precios)
