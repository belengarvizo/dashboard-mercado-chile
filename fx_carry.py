"""
Matemática de la sección «FX y Carry Trade»: valor de una moneda en dólares, retorno de un carry trade y
estadísticas de riesgo. Sin Streamlit, para poder probarla con series de respuesta conocida.

QUÉ ES UN CARRY TRADE. Pedir prestada una moneda de tasa baja y colocar el dinero en una de tasa alta: se gana el
diferencial de tasas mientras el tipo de cambio no se mueva en contra. Para una moneda C contra el dólar:

    posición «larga C financiada en dólares»: se compran dólares de C con dólares prestados.
    retorno de un tramo = (1 + spot) × (1 + tasa_C × días/365) − (1 + tasa_USD × días/365)

donde `spot` es la variación del valor de C en dólares en ese tramo. Se separa en `spot` y `carry` (lo que queda
sobre el spot: el diferencial de tasas más un término cruzado minúsculo), de modo que total = spot + carry exacto.

SIN MIRAR EL FUTURO. La tasa que corre en un tramo es la vigente al INICIO del tramo (la del día anterior), y la
estrategia de carry elige el lado de cada día (larga C si su tasa supera a la de EEUU, corta C si no) con el diferencial
conocido ese día anterior, nunca con el de hoy ni el de mañana.

CORRELACIONES CON OTRAS SERIES. Las barras diarias de las divisas de Yahoo («=X») NO comparten convención de fecha con la
bolsa ni con el índice dólar: en 50 % a 90 % de ellas el «cierre» es idéntico a la apertura del mismo día, y la fila de un día
corresponde a la rueda anterior de las otras series (EUR/USD contra el índice dólar da -0,09 el mismo día y -0,88 al día
siguiente, en TODOS los trimestres desde 2021). trading_correlacion.py ya lo documenta y decide NO corregirlo desplazando la serie,
porque alinear datos a partir de un ajuste de correlación es una suposición. Acá se sigue ese criterio: no se calcula ninguna
correlación entre una divisa y la bolsa o el índice dólar. Las que sí se calculan son entre divisas (misma fuente y convención:
las identidades de cruce entre los pares «=X» calzan en el mismo día) y entre series del Banco Central.

LO QUE NO MIDE. Es una aproximación con datos de dominio público: no incluye costos de transacción ni diferenciales
compra/venta, y la «tasa de financiamiento» es la de política o interbancaria de corto plazo, no la que pagaría
realmente un inversionista. Las tasas mensuales (Japón, México, Brasil) se mantienen constantes dentro del mes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import renta_fija as rf
import renta_variable as rv  # correlacion_contra

DIAS_DEL_ANIO_PARA_INTERES = 365
DIAS_HABILES_ANIO = rf.DIAS_HABILES_ANIO
DIAS_DE_UN_MES_HABIL = 21
# Un tramo (entre dos fechas con precio) más largo que esto es un hueco de datos, no un fin de semana largo: no se le devenga interés
# con la tasa de su primer día, porque eso inventaría semanas o meses de carry que nadie midió.
DIAS_MAXIMOS_POR_TRAMO = 10
MINIMO_DE_OBSERVACIONES = rf.MINIMO_DE_OBSERVACIONES


def valor_en_dolares(precio_del_par: pd.Series, base_es_dolar: bool) -> pd.Series:
    """Cuántos dólares vale 1 unidad de la moneda: el precio mismo si el par es «dólares por 1 moneda» (EUR/USD),
    o su inverso si es «monedas por 1 dólar» (USD/JPY). Los precios que no son positivos se descartan."""
    precio = precio_del_par.dropna().sort_index()
    precio = precio[precio > 0]
    return 1.0 / precio if base_es_dolar else precio


def tasa_en_cada_fecha(tasa_pct: pd.Series, fechas: pd.DatetimeIndex, antiguedad_maxima_dias: int | None = None) -> pd.Series:
    """Tasa (en %) vigente en cada fecha: el último valor publicado en esa fecha o antes (una tasa se mantiene hasta que se publica otra).

    Antes del primer dato queda vacía. Si se da `antiguedad_maxima_dias`, una tasa publicada hace más días que eso
    se considera vencida y queda vacía: así una serie que dejó de actualizarse no sigue «vigente» para siempre."""
    tasa = tasa_pct.dropna().sort_index()
    tasa = tasa[~tasa.index.duplicated(keep="last")]
    if tasa.empty:
        return pd.Series(np.nan, index=fechas)
    union = tasa.index.union(fechas)
    vigente = tasa.reindex(union).ffill()
    publicada_el = pd.Series(tasa.index, index=tasa.index).reindex(union).ffill()
    resultado = vigente.reindex(fechas)
    if antiguedad_maxima_dias is not None:
        antiguedad = (pd.Series(fechas, index=fechas) - publicada_el.reindex(fechas)).dt.days
        resultado = resultado.where(antiguedad <= antiguedad_maxima_dias)
    return resultado


def retornos_del_carry(valor_usd: pd.Series, tasa_moneda_pct: pd.Series, tasa_usd_pct: pd.Series,
                       antiguedad_maxima_moneda: int | None = None, antiguedad_maxima_usd: int | None = None,
                       dias_maximos_por_tramo: int = DIAS_MAXIMOS_POR_TRAMO) -> pd.DataFrame:
    """Retornos de cada tramo (entre dos fechas con precio) de una posición larga en la moneda financiada en dólares.

    Los tramos de más de `dias_maximos_por_tramo` días corridos (huecos en los precios) se descartan.

    Devuelve una fila por fecha con: `spot` (variación del valor en dólares), `carry` (total - spot), `total`, y `diferencial`
    (tasa de la moneda - tasa de EEUU, en puntos porcentuales, vigente al inicio del tramo: el que se conocía ese día)."""
    valor = valor_usd.dropna().sort_index()
    fechas = valor.index
    tasa_m = tasa_en_cada_fecha(tasa_moneda_pct, fechas, antiguedad_maxima_moneda).shift(1) / 100.0
    tasa_u = tasa_en_cada_fecha(tasa_usd_pct, fechas, antiguedad_maxima_usd).shift(1) / 100.0
    dias = pd.Series(fechas, index=fechas).diff().dt.days
    spot = valor.pct_change()
    factor = dias / DIAS_DEL_ANIO_PARA_INTERES
    total = (1 + spot) * (1 + tasa_m * factor) - (1 + tasa_u * factor)
    resultado = pd.DataFrame({"spot": spot, "carry": total - spot, "total": total, "diferencial": (tasa_m - tasa_u) * 100.0})
    return resultado[dias <= dias_maximos_por_tramo].dropna()


def estrategia_de_carry(retornos: pd.DataFrame) -> pd.DataFrame:
    """La estrategia de carry: cada día larga en la moneda si su diferencial era positivo (corta si era negativo).

    Corta en la moneda = larga en dólares financiada en esa moneda, cuyo retorno es el opuesto del de la posición larga.
    Devuelve `lado` (+1 / -1 / 0 si el diferencial era exactamente 0) y `retorno` (lado × total)."""
    lado = np.sign(retornos["diferencial"])
    return pd.DataFrame({"lado": lado, "retorno": lado * retornos["total"]})


def cartera_de_igual_peso(retornos: pd.DataFrame) -> pd.Series:
    """Retorno diario de repartir el dinero en partes iguales entre las columnas con dato ese día (se rebalancea a diario)."""
    return retornos.mean(axis=1, skipna=True).dropna()


def _ultimos_dias(datos, dias: int | None):
    """Las filas de los últimos `dias` días corridos (todas si `dias` es None)."""
    if dias is None or len(datos) == 0:
        return datos
    return datos[datos.index >= datos.index[-1] - pd.Timedelta(days=dias)]


def _acumulado(retornos: pd.Series) -> pd.Series:
    return (1 + retornos).cumprod()


def estadisticas_de_retornos(retornos: pd.Series, dias: int | None = None) -> dict | None:
    """Retorno, riesgo y peores momentos de una serie de retornos por tramo, en los últimos `dias` días (todos si None).

    `anualizado` es geométrico sobre el período real transcurrido; `peor_mes` y `mejor_mes` son los retornos compuestos
    de ventanas de 21 ruedas; `meses_ganadores` es el % de meses calendario con retorno positivo. None si hay pocos datos."""
    r = _ultimos_dias(retornos.dropna().sort_index(), dias)
    if len(r) < MINIMO_DE_OBSERVACIONES:
        return None
    acumulado = _acumulado(r)
    total = float(acumulado.iloc[-1] - 1)
    # Cada retorno está fechado al FINAL de su tramo: entre la primera y la última fecha hay n-1 tramos, no n. El tiempo real que cubren
    # los n retornos es ese lapso escalado por n/(n-1); sin eso se subestima el tiempo y se sobreestima el retorno anualizado.
    transcurrido = ((r.index[-1] - r.index[0]).days or 1) * len(r) / (len(r) - 1)
    ventana_mensual = (1 + r).rolling(DIAS_DE_UN_MES_HABIL).apply(np.prod, raw=True) - 1
    por_mes = (1 + r).groupby([r.index.year, r.index.month]).prod() - 1
    return {
        "retorno_total": total * 100,
        "anualizado": ((1 + total) ** (365.0 / transcurrido) - 1) * 100,
        "volatilidad": float(r.std() * DIAS_HABILES_ANIO**0.5 * 100),
        "caida_maxima": float((acumulado / acumulado.cummax() - 1).min() * 100),
        "peor_mes": float(ventana_mensual.min() * 100) if ventana_mensual.notna().any() else None,
        "fecha_peor_mes": ventana_mensual.idxmin() if ventana_mensual.notna().any() else None,
        "mejor_mes": float(ventana_mensual.max() * 100) if ventana_mensual.notna().any() else None,
        "meses_ganadores": float((por_mes > 0).mean() * 100),
        "dias": len(r), "desde": r.index[0], "hasta": r.index[-1],
    }


def resumen_del_carry(retornos: pd.DataFrame, dias: int = rf.DIAS_DEL_ANIO) -> dict | None:
    """Una fila de la tabla de carry: spot, carry y total acumulados en los últimos `dias` días, riesgo y diferencial actual.

    `diferencial_actual` es el del último tramo (el que corre hoy); `diferencial_promedio`, el del período. `carry` es
    `total - spot` acumulados, así que spot + carry = total. `carry_sobre_riesgo` = diferencial actual / volatilidad del spot:
    cuántos puntos de tasa se cobran por cada punto de riesgo cambiario."""
    r = _ultimos_dias(retornos, dias)
    if len(r) < MINIMO_DE_OBSERVACIONES:
        return None
    spot = float((1 + r["spot"]).prod() - 1) * 100
    total = float((1 + r["total"]).prod() - 1) * 100
    volatilidad_spot = float(r["spot"].std() * DIAS_HABILES_ANIO**0.5 * 100)
    acumulado = _acumulado(r["total"])
    actual = float(r["diferencial"].iloc[-1])
    return {
        "diferencial_actual": actual,
        "diferencial_promedio": float(r["diferencial"].mean()),
        "spot": spot, "carry": total - spot, "total": total,
        "volatilidad_spot": volatilidad_spot,
        "volatilidad_total": float(r["total"].std() * DIAS_HABILES_ANIO**0.5 * 100),
        "caida_maxima": float((acumulado / acumulado.cummax() - 1).min() * 100),
        "carry_sobre_riesgo": actual / volatilidad_spot if volatilidad_spot else None,
        "desde": r.index[0], "hasta": r.index[-1],
    }


def resumen_de_par(precios: pd.Series, precios_referencia: pd.Series) -> dict | None:
    """Una fila de la tabla de divisas: cambios por período, volatilidad, rango del año y correlación con un par de referencia.

    El rango es (máximo / mínimo - 1) del último año: no depende de la dirección en que se cotiza el par, a diferencia de
    una «caída máxima». `precios_referencia` debe ser OTRO PAR «=X» (misma fuente y convención de fecha); no se debe pasar
    la bolsa ni el índice dólar (ver CORRELACIONES CON OTRAS SERIES arriba). La correlación es de retornos diarios del último año."""
    precios = precios.dropna().sort_index()
    if len(precios) < 2:
        return None
    ultimo_anio = precios[precios.index >= precios.index[-1] - pd.Timedelta(days=rf.DIAS_DEL_ANIO)]
    retornos = _ultimos_dias(precios.pct_change().dropna(), rf.DIAS_DEL_ANIO)
    return {
        **rf.cambios_por_periodo(precios),
        "Retorno 1 año (%)": rf.retorno_ultimo_anio(precios),
        "Volatilidad (%)": rf.volatilidad_anualizada(precios),
        "Rango 1 año (%)": float((ultimo_anio.max() / ultimo_anio.min() - 1) * 100) if len(ultimo_anio) >= 2 else None,
        "Correlación vs referencia": rv.correlacion_contra(retornos, precios_referencia.dropna().sort_index().pct_change().dropna()),
        "ultima_fecha": precios.index[-1],
    }


def correlacion_movil(a: pd.Series, b: pd.Series, ventana: int = DIAS_HABILES_ANIO) -> pd.Series:
    """Correlación de los retornos diarios de dos series en una ventana móvil de `ventana` ruedas (solo fechas en común)."""
    conjunto = pd.concat([a, b], axis=1, join="inner", keys=["a", "b"]).dropna().sort_index().pct_change().dropna()
    return conjunto["a"].rolling(ventana).corr(conjunto["b"]).dropna()
