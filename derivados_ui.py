"""
Sección «Derivados» del dashboard: una cadena de opciones REAL, en vivo, con Black-Scholes contra el precio real
de mercado.

PARA QUÉ EXISTE
    Sigue el módulo de derivados de un curso de mercado de capitales (qué es una opción, la cadena de opciones de
    hoy, el modelo de Black-Scholes y la volatilidad implícita), con el mismo criterio de las otras secciones: los
    datos son reales, no un ejemplo con valores inventados.

POR QUÉ ESTA SECCIÓN ES DISTINTA A LAS DEMÁS
    Todas las otras secciones leen de la base (df_macro, df_precios), que el cron diario llena de antemano. Acá NO:
    una opción es un contrato con strike y vencimiento fijos, así que "la cadena de opciones de hoy" son contratos
    DISTINTOS a los de ayer. No existe una serie histórica real de la cadena completa (nadie la ha bajado desde
    antes), y guardar una tabla con cientos de combinaciones de strike y vencimiento todos los días es un proyecto
    aparte. Por eso esta sección consulta a Yahoo Finance EN VIVO, cada vez que se abre, y muestra solo el estado
    de HOY: no hay gráfico de evolución ni selector de período, porque no hay con qué compararlo.

DE DÓNDE SALEN LOS DATOS (todos reales; ninguno es de ejemplo)
    - La cadena de opciones de hoy (strikes, primas, bid/ask, volumen, interés abierto, volatilidad implícita que
      calcula el propio Yahoo) para 5 ETFs ya seguidos en otras secciones (catalogo_derivados.SUBYACENTES).
    - El precio del subyacente en vivo, también de Yahoo Finance.
    - La tasa libre de riesgo: la curva real del Tesoro de EEUU (tabla series_macro, la misma de Renta Fija),
      interpolada al plazo exacto de cada opción.
    - La volatilidad REALIZADA (histórica) del subyacente: medida con el mismo motor de Renta Fija y Renta
      Variable (renta_fija.volatilidad_anualizada) sobre los precios que ya trae la base.
    - SIN DATOS: historial de la cadena de opciones (ver arriba), dividendos del subyacente (Black-Scholes acá no
      los descuenta), opciones americanas (se ejercen antes del vencimiento; el modelo solo vale para europeas).

DECISIONES DE DISEÑO
    - La matemática de Black-Scholes vive en black_scholes.py (sin Streamlit, sin red, con sus pruebas). Acá se
      arma la pantalla y se hace la única llamada en vivo del módulo.
    - Las llamadas a Yahoo están cacheadas con un TTL corto (ver _TTL_CADENA): lo justo para que cambiar de
      vencimiento o de strike en la misma sesión no dispare una llamada nueva cada vez, pero sin servir un precio
      de hace horas como si fuera de ahora.
    - Los controles son solo de vista (qué subyacente, qué vencimiento, qué strike, cuántos strikes mostrar): no
      hay campos para inventar un precio o una volatilidad.
    - Selector de pasos con st.segmented_control (no st.tabs), estado bajo claves que empiezan con dv_.
    - Sin signo «$» en los textos: Streamlit lo toma como fórmula matemática.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import black_scholes as bs
import renta_fija as rf
import renta_fija_ui as rfui
from catalogo_derivados import SUBYACENTES, nombre_de

PASOS = ["1. Qué es una opción", "2. La cadena de opciones hoy", "3. Black-Scholes contra el mercado"]

# TTL corto a propósito: es la única sección que llama a una fuente externa EN VIVO (no desde la base). 5 minutos
# alcanza para que navegar entre pasos en la misma sesión no dispare una llamada nueva cada vez, sin servir un
# precio de hace horas como si fuera el de ahora.
_TTL_CADENA = 300
_TIMEOUT_YAHOO = 8  # igual de corto que el resto del dashboard cuando hay un usuario esperando (ver app/dashboard.py)

CANTIDADES_DE_STRIKES = {"10 strikes alrededor del precio": 10, "25 strikes alrededor del precio": 25, "Todos": None}


# ---------------------------------------------------------------------------
# Las únicas llamadas en vivo del dashboard: Yahoo Finance, cacheadas con TTL corto
# ---------------------------------------------------------------------------
@st.cache_data(ttl=_TTL_CADENA, show_spinner=False)
def _vencimientos_disponibles(ticker: str) -> tuple[str, ...]:
    """Las fechas de vencimiento que Yahoo tiene listadas HOY para este subyacente, o () si falla."""
    try:
        import yfinance as yf
        return tuple(yf.Ticker(ticker).options)
    except Exception:
        return ()


@st.cache_data(ttl=_TTL_CADENA, show_spinner=False)
def _cadena_de_opciones(ticker: str, vencimiento: str):
    """(calls, puts) como DataFrames de Yahoo, o (None, None) si falla. No se reprocesa acá: se devuelve tal cual
    viene, y cada paso toma de ahí lo que necesita."""
    try:
        import yfinance as yf
        cadena = yf.Ticker(ticker).option_chain(vencimiento)
        return cadena.calls, cadena.puts
    except Exception:
        return None, None


@st.cache_data(ttl=_TTL_CADENA, show_spinner=False)
def _precio_en_vivo(ticker: str) -> float | None:
    """El último precio del subyacente, en vivo (no el cierre de ayer que trae la base)."""
    try:
        import yfinance as yf
        historico = yf.Ticker(ticker).history(period="1d", timeout=_TIMEOUT_YAHOO)
        if historico is None or historico.empty:
            return None
        return float(historico["Close"].iloc[-1])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tasa libre de riesgo: la curva real del Tesoro, interpolada al plazo exacto de la opción
# ---------------------------------------------------------------------------
def _tasa_libre_para(macro: pd.DataFrame, plazo_anios: float) -> tuple[float, bool] | None:
    """(tasa en decimal, se_recorto_al_plazo_minimo_de_la_curva) para el plazo pedido, o None sin datos.

    La curva real empieza en 1 mes (~0,083 años): una opción que vence en menos de eso usa igual la tasa a 1 mes
    (no hay una más corta en la base), y el segundo valor avisa que se hizo esa aproximación."""
    actual = rfui._curva_actual(macro)
    if actual is None:
        return None
    _, _, curva = actual
    minimo, maximo = float(curva.index.min()), float(curva.index.max())
    plazo_usado = min(max(plazo_anios, minimo), maximo)
    return rf.interpolar_tasa(curva, plazo_usado), plazo_usado != plazo_anios


# ---------------------------------------------------------------------------
# Controles compartidos (subyacente + vencimiento)
# ---------------------------------------------------------------------------
def _elegir_subyacente_y_vencimiento(clave: str) -> tuple[str, str] | None:
    ticker = st.selectbox(
        "Subyacente", list(SUBYACENTES), key=f"dv_subyacente_{clave}", format_func=lambda t: f"{t} · {nombre_de(t)}",
    )
    vencimientos = _vencimientos_disponibles(ticker)
    if not vencimientos:
        rfui._sin_datos(f"los vencimientos de {ticker} (Yahoo Finance no respondió)")
        return None
    # Por defecto, el primer vencimiento que NO sea hoy mismo: un contrato que vence hoy todavía tiene horas de
    # mercado por delante, pero _dias_al_vencimiento (en días completos) le da T=0, con lo que Black-Scholes deja
    # de poder explicar su precio (ver la nota en _paso_black_scholes). Igual se puede elegir a propósito.
    no_hoy = [i for i, v in enumerate(vencimientos) if _dias_al_vencimiento(v) > 0]
    vencimiento = st.selectbox("Vencimiento", vencimientos, index=no_hoy[0] if no_hoy else 0, key=f"dv_vencimiento_{clave}")
    return ticker, vencimiento


def _dias_al_vencimiento(vencimiento: str) -> int:
    return max((pd.Timestamp(vencimiento) - pd.Timestamp.now().normalize()).days, 0)


# ---------------------------------------------------------------------------
# Paso 1: qué es una opción
# ---------------------------------------------------------------------------
def _paso_concepto() -> None:
    st.markdown(
        "Una **opción** da el derecho, pero no la obligación, de comprar o vender un activo a un precio fijado de "
        "antemano (el **strike**), antes o en una fecha futura (el **vencimiento**). Quien la compra paga una "
        "**prima** hoy por ese derecho; quien la vende (el emisor) cobra la prima y asume la obligación si la otra "
        "parte decide ejercer."
    )
    st.markdown(
        "**Call** = derecho a *comprar* al strike. Conviene ejercerlo si el precio de mercado terminó por encima "
        "del strike. **Put** = derecho a *vender* al strike. Conviene ejercerlo si el precio de mercado terminó "
        "por debajo. Una opción cuyo ejercicio ya conviene HOY (un call con el subyacente sobre el strike, o un "
        "put con el subyacente bajo el strike) está **en dinero** (*in the money*, ITM); si no conviene, está "
        "**fuera de dinero** (*out of the money*, OTM)."
    )
    st.markdown(
        "El precio de una opción tiene dos partes: el **valor intrínseco** (lo que valdría si se ejerciera ahora "
        "mismo: max(precio − strike, 0) en un call) y el **valor de tiempo** (lo que se paga de más por la "
        "posibilidad de que, antes del vencimiento, el precio se mueva a favor). El valor de tiempo se reduce "
        "todos los días (eso se llama *theta*) y llega a cero justo en el vencimiento."
    )
    st.info(
        "Las opciones del mundo real (las que emite una bolsa, como las de esta sección) son **americanas**: se "
        "pueden ejercer en cualquier momento antes del vencimiento, no solo al final. Black-Scholes, el modelo del "
        "paso 3, está pensado para opciones **europeas** (solo al vencimiento). Es la aproximación más usada en la "
        "práctica y en la que se basa toda esta sección, pero es una simplificación: el modelo exacto para una "
        "americana es más complejo y no está implementado acá."
    )


# ---------------------------------------------------------------------------
# Paso 2: la cadena de opciones hoy
# ---------------------------------------------------------------------------
_COLUMNAS_CADENA = {
    "strike": "Strike", "lastPrice": "Último", "bid": "Bid", "ask": "Ask",
    "volume": "Volumen", "openInterest": "Interés abierto", "impliedVolatility": "Vol. implícita (Yahoo)",
}


def _preparar_tabla(cruda: pd.DataFrame, spot: float, cuantos: int | None) -> pd.DataFrame:
    tabla = cruda[list(_COLUMNAS_CADENA)].rename(columns=_COLUMNAS_CADENA).copy()
    tabla["En dinero"] = cruda["inTheMoney"].map({True: "Sí", False: "No"})
    tabla["Vol. implícita (Yahoo)"] = (tabla["Vol. implícita (Yahoo)"] * 100).round(1)
    tabla = tabla.sort_values("Strike").reset_index(drop=True)
    if cuantos is not None:
        cerca = (tabla["Strike"] - spot).abs().sort_values().index[:cuantos]
        tabla = tabla.loc[sorted(cerca)]
    return tabla


def _paso_cadena(macro: pd.DataFrame) -> None:
    st.markdown(
        "La **cadena de opciones** de hoy: todos los contratos de call y de put que se transan ahora mismo sobre "
        "un subyacente, para un vencimiento elegido. Es información en vivo de la bolsa, no un dato que se guarde "
        "día a día en este dashboard (ver el porqué arriba, en la descripción de la sección)."
    )
    elegido = _elegir_subyacente_y_vencimiento("cadena")
    if elegido is None:
        return
    ticker, vencimiento = elegido
    spot = _precio_en_vivo(ticker)
    calls, puts = _cadena_de_opciones(ticker, vencimiento)
    if spot is None or calls is None or calls.empty:
        rfui._sin_datos(f"la cadena de opciones de {ticker} para el {vencimiento} (Yahoo Finance no respondió)")
        return

    dias = _dias_al_vencimiento(vencimiento)
    c1, c2 = st.columns(2)
    c1.metric(f"Precio de {ticker} ahora", f"{rfui._fmt(spot, 2)}")
    c2.metric("Días al vencimiento", f"{dias}")
    st.caption(f"Vencimiento: {vencimiento} · Subyacente: {nombre_de(ticker)} · Consultado ahora mismo a Yahoo Finance.")

    cuantos_nombre = st.radio("Cuántos strikes mostrar", list(CANTIDADES_DE_STRIKES), horizontal=True, key="dv_cuantos_strikes")
    cuantos = CANTIDADES_DE_STRIKES[cuantos_nombre]

    st.subheader("Calls")
    rfui._tabla(_preparar_tabla(calls, spot, cuantos), numericas=list(_COLUMNAS_CADENA.values())[1:], mostrar_todo=True)
    if puts is not None and not puts.empty:
        st.subheader("Puts")
        rfui._tabla(_preparar_tabla(puts, spot, cuantos), numericas=list(_COLUMNAS_CADENA.values())[1:], mostrar_todo=True)

    st.caption(
        "**Último** = precio de la última operación cerrada (puede ser de hace rato si el contrato no se transa seguido); "
        "**Bid/Ask** = lo que un comprador ofrece pagar y un vendedor pedir ahora mismo, la referencia más fresca. "
        "**Vol. implícita (Yahoo)** es la que calcula el propio Yahoo con su modelo: en el paso 3 se calcula la de un "
        "contrato puntual con Black-Scholes y se compara."
    )


# ---------------------------------------------------------------------------
# Paso 3: Black-Scholes contra el mercado
# ---------------------------------------------------------------------------
def _precio_de_mercado(fila: pd.Series) -> float | None:
    """Precio de referencia de un contrato: el punto medio entre bid y ask si los hay (más fresco), si no el último
    precio transado. None si no hay ningún dato utilizable."""
    bid, ask, ultimo = float(fila["bid"]), float(fila["ask"]), float(fila["lastPrice"])
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    return ultimo if ultimo > 0 else None


def _paso_black_scholes(macro: pd.DataFrame, precios: pd.DataFrame) -> None:
    st.markdown(
        "**Black-Scholes** calcula cuánto *debería* valer una opción a partir de cinco datos: el precio de hoy del "
        "subyacente, el strike, el tiempo al vencimiento, la tasa libre de riesgo y la volatilidad esperada. De "
        "esos cinco, los cuatro primeros se observan; la volatilidad no se observa, hay que suponerla."
    )
    elegido = _elegir_subyacente_y_vencimiento("bs")
    if elegido is None:
        return
    ticker, vencimiento = elegido
    spot = _precio_en_vivo(ticker)
    calls, puts = _cadena_de_opciones(ticker, vencimiento)
    if spot is None or calls is None or calls.empty:
        rfui._sin_datos(f"la cadena de opciones de {ticker} para el {vencimiento} (Yahoo Finance no respondió)")
        return

    tipo_nombre = st.radio("Tipo de opción", ["Call", "Put"], horizontal=True, key="dv_tipo")
    tipo = tipo_nombre.lower()
    tabla_elegida = calls if tipo == "call" else puts
    if tabla_elegida is None or tabla_elegida.empty:
        rfui._sin_datos(f"los {tipo_nombre.lower()}s de {ticker} para el {vencimiento}")
        return
    strikes = sorted(tabla_elegida["strike"].unique())
    strike_por_defecto = min(strikes, key=lambda k: abs(k - spot))
    strike = st.selectbox("Strike", strikes, index=strikes.index(strike_por_defecto), key="dv_strike",
                          format_func=lambda k: f"{rfui._fmt(k, 2)}" + (" (el más cercano al precio actual)" if k == strike_por_defecto else ""))
    fila = tabla_elegida[tabla_elegida["strike"] == strike].iloc[0]
    precio_mercado = _precio_de_mercado(fila)
    if precio_mercado is None:
        rfui._sin_datos("un precio de mercado utilizable para este contrato (ni bid/ask ni última operación)")
        return

    dias = _dias_al_vencimiento(vencimiento)
    if dias == 0:
        st.warning(
            "Este contrato **vence hoy**: todavía le quedan horas de mercado, pero este modelo mide el tiempo al "
            "vencimiento en días completos (T=0), así que Black-Scholes lo trata como si ya no quedara nada de tiempo "
            "y solo puede explicar su **valor intrínseco**, no el precio real de mercado. Elige otro vencimiento para "
            "ver la comparación completa."
        )
    T = dias / bs.DIAS_DEL_ANIO
    tasa = _tasa_libre_para(macro, T)
    if tasa is None:
        rfui._sin_datos("la curva de tasas del Tesoro para calcular la tasa libre de riesgo")
        return
    r, tasa_recortada = tasa

    vol_realizada = None
    if ticker in precios:
        vol_pct = rf.volatilidad_anualizada(precios[ticker])
        vol_realizada = vol_pct / 100 if vol_pct is not None else None

    vol_implicita = bs.volatilidad_implicita(precio_mercado, spot, strike, T, r, tipo) if T > 0 else None

    st.subheader("Los cinco datos de Black-Scholes para este contrato")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Subyacente (S)", f"{rfui._fmt(spot, 2)}")
    c2.metric("Strike (K)", f"{rfui._fmt(strike, 2)}")
    c3.metric("Vencimiento (T)", f"{dias} días")
    c4.metric("Tasa libre de riesgo (r)", f"{r * 100:.2f}%")
    c5.metric("Precio de mercado", f"{rfui._fmt(precio_mercado, 2)}")
    if tasa_recortada:
        st.caption(
            "La tasa usada es la del plazo más corto que tiene la curva real (1 mes): este contrato vence antes de eso "
            "y no hay una tasa más corta en la base."
        )

    st.subheader("Dos volatilidades, dos precios")
    if vol_realizada is not None:
        precio_con_realizada = bs.precio(spot, strike, T, r, vol_realizada, tipo)
        st.markdown(
            f"**Con la volatilidad REALIZADA** (lo que el precio de {ticker} se movió de verdad en el último año: "
            f"{vol_realizada * 100:.1f}%), Black-Scholes da un precio teórico de **{rfui._fmt(precio_con_realizada, 2)}**, "
            f"contra un precio de mercado de **{rfui._fmt(precio_mercado, 2)}**."
            + (" El mercado paga más de lo que la volatilidad pasada justificaría."
               if precio_mercado > precio_con_realizada
               else " El mercado paga menos de lo que la volatilidad pasada justificaría."
               if precio_mercado < precio_con_realizada else "")
        )
    else:
        st.info(f"No hay suficiente historial de precios de {ticker} en la base para medir su volatilidad realizada.")

    if vol_implicita is not None:
        st.markdown(
            f"**Despejando al revés** — qué volatilidad hace que Black-Scholes dé exactamente el precio de mercado — "
            f"sale una **volatilidad implícita de {vol_implicita * 100:.1f}%**. Yahoo calcula la suya propia para este "
            f"contrato en {float(fila['impliedVolatility']) * 100:.1f}%; la diferencia es normal y viene de usar una "
            "tasa o una convención de tiempo levemente distinta."
        )
        if vol_realizada is not None:
            diferencia = (vol_implicita - vol_realizada) * 100
            if abs(diferencia) < 0.05:
                comparacion = "prácticamente igual a la realizada"
            else:
                comparacion = f"{abs(diferencia):.1f} puntos {'por sobre' if diferencia > 0 else 'por debajo de'} la realizada"
            st.caption(
                f"La implícita está {comparacion}. Que la implícita sea mayor es lo más común: el mercado suele cobrar "
                "un premio por la incertidumbre futura, no solo repetir lo que ya pasó. Se conoce como *prima de riesgo "
                "de volatilidad*."
            )
    else:
        st.info(
            "No se pudo despejar una volatilidad implícita para este contrato: su precio de mercado está fuera de lo "
            "que Black-Scholes puede explicar con una volatilidad entre 0,1% y 500% (pasa en contratos con muy poca "
            "liquidez, donde el precio mostrado no es confiable)."
        )

    if vol_implicita is not None:
        g = bs.griegas(spot, strike, T, r, vol_implicita, tipo)
        st.subheader("Las griegas de este contrato")
        st.caption("Calculadas con la volatilidad implícita (la que hace que el modelo calce con el precio de mercado).")
        d1, d2, d3, d4, d5 = st.columns(5)
        d1.metric("Delta", f"{g.delta:+.3f}", help="Cuánto cambia el precio de la opción por 1 que sube el subyacente.")
        d2.metric("Gamma", f"{g.gamma:.4f}", help="Cuánto cambia el delta por 1 que sube el subyacente.")
        d3.metric("Theta (por día)", f"{g.theta:+.3f}", help="Cuánto pierde la opción de valor cada día que pasa, solo por el paso del tiempo.")
        d4.metric("Vega (por 1 pp de vol.)", f"{g.vega:+.3f}", help="Cuánto cambia el precio si la volatilidad sube 1 punto porcentual.")
        d5.metric("Rho (por 1 pp de tasa)", f"{g.rho:+.3f}", help="Cuánto cambia el precio si la tasa libre de riesgo sube 1 punto porcentual.")

    st.info(
        "**Lo que este paso no hace:** no descuenta dividendos del subyacente, no corrige por ser una opción americana "
        "(se puede ejercer antes del vencimiento) y asume que la volatilidad es constante hasta el vencimiento. Ninguna "
        "de las tres es exactamente cierta en el mercado real; son las simplificaciones estándar de Black-Scholes."
    )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def render_derivados(df_macro: pd.DataFrame, df_precios: pd.DataFrame) -> None:
    st.header("Derivados: la cadena de opciones de hoy")
    st.info(
        "Esta sección es distinta a las demás: en vez de leer la base, consulta a **Yahoo Finance en vivo** cada vez "
        "que se abre. Una opción es un contrato de strike y vencimiento fijos, así que no existe un historial propio "
        "que guardar: lo que se muestra es la cadena de **hoy**, nada más."
    )
    macro = rfui._recortar(df_macro)
    precios = rfui._precios_en_columnas(df_precios)
    paso = st.segmented_control("Paso", PASOS, default=PASOS[0], key="dv_paso", label_visibility="collapsed") or PASOS[0]

    if paso == PASOS[0]:
        _paso_concepto()
    elif paso == PASOS[1]:
        _paso_cadena(macro)
    else:
        _paso_black_scholes(macro, precios)
