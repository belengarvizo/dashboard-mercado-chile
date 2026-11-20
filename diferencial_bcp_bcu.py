"""
Presentación del diferencial BCP − BCU a 10 años en el Resumen, el selector de Indicadores macro y el PDF del Brief
Premercado (I-6b-2). Mismo criterio que el PDF de renta fija (I-6c) y la sección Renta Fija (I-6b-1).

QUÉ ES
    Tasa del BCP a 10 años (nominal, en pesos) menos tasa del BCU a 10 años (real, sobre capital en UF), en puntos
    porcentuales, en las fechas con dato en ambas series. Es una aproximación a la compensación por inflación
    incorporada en las tasas de mercado, no una medición directa de la inflación esperada: puede incluir primas por
    riesgo de inflación y por liquidez, los bonos de ambas series pueden diferir en emisor, duración y cupones, y la UF
    se reajusta con rezago. La convención de capitalización de las dos series no está verificada, así que no se usa
    Fisher.

QUÉ NO HACE
    No calcula la serie: la resta sigue en app/dashboard.py (calcular_serie_inflacion_breakeven). Acá solo se leen sus
    dos últimas observaciones y se arman los textos. Sin dependencias de la base.
"""
from __future__ import annotations

import pandas as pd

# Selector de Indicadores macro (español): es el valor de la columna `nombre` de la serie calculada.
NOMBRE_SERIE = "Diferencial BCP − BCU a 10 años (pp)"
DESCRIPCION_SERIE = (
    "Tasa del BCP a 10 años (nominal, en pesos) menos tasa del BCU a 10 años (real, en UF), en puntos porcentuales, en las "
    "fechas con dato en ambas series. Es una aproximación a la compensación por inflación incorporada en las tasas de "
    "mercado, no una medición directa de la inflación esperada: puede incluir primas por riesgo de inflación y por "
    "liquidez, los bonos pueden diferir en emisor, duración y cupones, y la UF se reajusta con rezago."
)

# Resumen y Brief (inglés, como el resto de esas vistas).
ETIQUETA_RESUMEN = "BCP 10Y − BCU 10Y spread (pp)"
AYUDA_RESUMEN = (
    "Nominal 10-year BCP yield (pesos) minus real 10-year BCU yield (UF), in percentage points, on dates with data for "
    "both series."
)
LIMITES_EN = (
    "an approximation to the inflation compensation embedded in market yields, not a direct measure of expected "
    "inflation: it can include inflation-risk and liquidity premia, the bonds may differ in issuer, duration and coupons, "
    "and the UF lags CPI."
)


def ultimas_observaciones(serie: pd.Series) -> dict | None:
    """Las dos últimas observaciones de la serie (ya restringida a fechas con BCP y BCU) y su cambio en pp.

    Es la misma cuenta que hacía el Resumen: último valor menos el anterior de la serie. Solo se agrega la fecha de esa
    observación anterior, que no tiene por qué ser el día hábil previo (si falta uno de los dos bonos un día, se compara
    con la fecha común anterior). None si hay menos de dos observaciones."""
    if serie is None or len(serie) < 2:
        return None
    valor = float(serie.iloc[-1])
    anterior = float(serie.iloc[-2])
    cambio = valor - anterior
    return {
        "valor": valor, "fecha": pd.Timestamp(serie.index[-1]), "anterior": anterior,
        "fecha_anterior": pd.Timestamp(serie.index[-2]), "cambio": cambio, "sin_cambio": round(cambio, 2) == 0,
    }


def _dia(fecha: pd.Timestamp) -> str:
    return fecha.strftime("%Y-%m-%d")


def texto_resumen(obs: dict) -> str:
    """Caption del Resumen: fecha del dato, fecha con que se compara y la lectura correcta."""
    comparacion = "no change" if obs["sin_cambio"] else "change"
    return (f"as of {_dia(obs['fecha'])} · {comparacion} vs {_dia(obs['fecha_anterior'])}, the previous date with data for "
            f"both bonds. The spread is {LIMITES_EN}")


def mostrar_en_resumen(serie: pd.Series) -> None:
    """Métrica del Resumen. El cambio va sin color (delta_color="off"): que el diferencial suba o baje no es bueno ni
    malo en sí. Si se lee 0.00, va sin delta (sin flecha), como el resto de los indicadores del Resumen."""
    import streamlit as st

    obs = ultimas_observaciones(serie)
    if obs is None:
        return
    if obs["sin_cambio"]:
        st.metric(ETIQUETA_RESUMEN, f"{obs['valor']:.2f} pp", help=AYUDA_RESUMEN)
    else:
        st.metric(ETIQUETA_RESUMEN, f"{obs['valor']:.2f} pp", f"{obs['cambio']:+.2f} pp", delta_color="off",
                  help=AYUDA_RESUMEN)
    st.caption(texto_resumen(obs))


def parrafo_brief(serie: pd.Series) -> str | None:
    """Párrafo del PDF del Brief Premercado (marcado de reportlab), o None si hay menos de dos observaciones (como antes)."""
    obs = ultimas_observaciones(serie)
    if obs is None:
        return None
    return (f"<b>BCP 10Y − BCU 10Y spread:</b> {obs['valor']:.2f} pp as of {_dia(obs['fecha'])}. "
            f"It is {LIMITES_EN}")
