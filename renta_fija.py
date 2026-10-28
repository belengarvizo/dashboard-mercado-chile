"""
Renta fija: la matemática de un bono y el análisis de instrumentos REALES, en Python puro (sin Streamlit).

PARA QUÉ EXISTE
    Es el motor de la sección «Renta Fija» del dashboard (la pantalla vive en
    renta_fija_ui.py). Tiene dos partes:

    1. Matemática de un bono, con fórmulas que se pueden comprobar a mano:
       precio como valor presente de los flujos, duración, convexidad, curva
       de descuento y «rodar» por la curva de tasas.
    2. Análisis de instrumentos reales (ETFs de bonos) a partir de sus precios
       de la base de datos: retornos, volatilidad, caída máxima, beta contra
       las acciones, y la DURACIÓN MEDIDA CON DATOS: cuánto se movió de verdad
       su precio por cada punto que se movió la tasa del Tesoro.

CONVENCIONES (para no confundirse al leerlo)
    - Las tasas entran y salen como DECIMALES: 5 % = 0.05. La pantalla es la
      que convierte desde y hacia porcentajes, porque la base de datos guarda
      los porcentajes tal cual (4.5 = 4,5 %).
    - Los bonos se valorizan EN UNA FECHA DE CUPÓN: no hay interés devengado,
      así que precio limpio = precio sucio. Es la simplificación estándar para
      aprender; en la mesa real se agrega el devengo entre cupones.
    - La tasa de un bono (YTM, «tasa al vencimiento») es nominal anual con la
      capitalización de sus cupones: un bono semestral descuenta cada flujo a
      (1 + y/2)^k, con k = número de semestres.

QUÉ NO ES
    No es un sistema de valorización profesional: no maneja calendarios de
    días hábiles, convenciones de días (30/360, act/365), amortizaciones,
    opciones embebidas ni reinversión de cupones.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq

# Cuántos cupones se pagan al año, por nombre.
FRECUENCIAS = {"Anual": 1, "Semestral": 2, "Trimestral": 4}

# Un punto base (pb) es 0,01 % = 0.0001 en decimales.
PUNTO_BASE = 1e-4

# Cotas de la búsqueda de la tasa al vencimiento (decimales): de -50 % a 1.000 %.
_TASA_MINIMA, _TASA_MAXIMA = -0.5, 10.0


# ---------------------------------------------------------------------------
# Flujos y precio
# ---------------------------------------------------------------------------
def _periodos(anios: float, frecuencia: int) -> int:
    """Número de períodos de cupón. El plazo debe calzar con la frecuencia: un
    bono semestral a 10,3 años no tiene un número entero de semestres."""
    if frecuencia not in FRECUENCIAS.values():
        raise ValueError(f"Frecuencia no soportada: {frecuencia}. Usa una de {sorted(FRECUENCIAS.values())}.")
    n = round(anios * frecuencia)
    if n < 1 or abs(anios * frecuencia - n) > 1e-9:
        raise ValueError(
            f"El plazo ({anios} años) debe ser un múltiplo de un período de cupón (1/{frecuencia} de año)."
        )
    return int(n)


def flujos_de_bono(nominal: float, cupon_anual: float, anios: float, frecuencia: int) -> pd.DataFrame:
    """Calendario de pagos del bono: una fila por cupón, y en el último se suma el nominal.

    Columnas: `periodo` (1..n), `anios` (cuándo se paga, en años desde hoy) y
    `flujo` (cuánto se paga en esa fecha)."""
    if nominal <= 0:
        raise ValueError("El valor nominal debe ser positivo.")
    if cupon_anual < 0:
        raise ValueError("El cupón no puede ser negativo.")
    n = _periodos(anios, frecuencia)
    periodo = np.arange(1, n + 1)
    flujo = np.full(n, nominal * cupon_anual / frecuencia)
    flujo[-1] += nominal  # al vencimiento se devuelve el capital
    return pd.DataFrame({"periodo": periodo, "anios": periodo / frecuencia, "flujo": flujo})


def _tasa_por_periodo(ytm: float, frecuencia: int) -> float:
    tasa = ytm / frecuencia
    if tasa <= -1:
        raise ValueError("La tasa por período debe ser mayor que -100 %.")
    return tasa


def precio(nominal: float, cupon_anual: float, anios: float, frecuencia: int, ytm: float) -> float:
    """Valor presente de todos los flujos descontados a la tasa de mercado (`ytm`)."""
    f = flujos_de_bono(nominal, cupon_anual, anios, frecuencia)
    tasa = _tasa_por_periodo(ytm, frecuencia)
    return float(np.sum(f["flujo"].to_numpy() / (1 + tasa) ** f["periodo"].to_numpy()))


def tabla_de_valorizacion(nominal: float, cupon_anual: float, anios: float, frecuencia: int, ytm: float) -> pd.DataFrame:
    """Los flujos con su factor de descuento y su valor presente. La suma de
    la columna `valor_presente` es el precio del bono."""
    f = flujos_de_bono(nominal, cupon_anual, anios, frecuencia)
    tasa = _tasa_por_periodo(ytm, frecuencia)
    f["factor_descuento"] = (1 + tasa) ** -f["periodo"].to_numpy()
    f["valor_presente"] = f["flujo"] * f["factor_descuento"]
    return f


def tasa_al_vencimiento(precio_de_mercado: float, nominal: float, cupon_anual: float, anios: float, frecuencia: int) -> float:
    """La tasa (YTM) que hace que el valor presente de los flujos sea igual al precio pagado.

    No tiene fórmula cerrada para un bono con cupones: se busca numéricamente
    (el precio baja siempre cuando sube la tasa, así que hay una sola solución)."""
    if precio_de_mercado <= 0:
        raise ValueError("El precio debe ser positivo.")

    def diferencia(y: float) -> float:
        return precio(nominal, cupon_anual, anios, frecuencia, y) - precio_de_mercado

    if diferencia(_TASA_MINIMA) * diferencia(_TASA_MAXIMA) > 0:
        raise ValueError("Ese precio no corresponde a ninguna tasa razonable para este bono.")
    return float(brentq(diferencia, _TASA_MINIMA, _TASA_MAXIMA, xtol=1e-14, rtol=1e-14))


def rendimiento_corriente(precio_de_mercado: float, nominal: float, cupon_anual: float) -> float:
    """Cupón anual dividido por el precio: lo que rinde en efectivo por año, sin contar la ganancia o pérdida de capital."""
    return nominal * cupon_anual / precio_de_mercado


# ---------------------------------------------------------------------------
# Riesgo de mercado: duración y convexidad
# ---------------------------------------------------------------------------
def metricas_de_riesgo(nominal: float, cupon_anual: float, anios: float, frecuencia: int, ytm: float) -> dict:
    """Precio, duración (Macaulay y modificada), DV01 y convexidad de un bono.

    - Duración de Macaulay: el plazo promedio en que recibes tu dinero, medido
      en años y ponderado por el valor presente de cada flujo. Un bono sin
      cupones (cero cupón) tiene una duración igual a su plazo.
    - Duración modificada: cuánto cambia el precio, en %, por cada 1 punto
      porcentual de cambio en la tasa. Es la de Macaulay dividida por (1 + y/m).
    - DV01: cuánto cambia el precio, en unidades de precio, por 1 punto base.
    - Convexidad: la curvatura de la relación precio-tasa; corrige el error
      de usar solo la duración (que supone una línea recta)."""
    f = flujos_de_bono(nominal, cupon_anual, anios, frecuencia)
    tasa = _tasa_por_periodo(ytm, frecuencia)
    k = f["periodo"].to_numpy()
    flujo = f["flujo"].to_numpy()
    valor_presente = flujo / (1 + tasa) ** k
    p = float(valor_presente.sum())

    macaulay = float(np.sum((k / frecuencia) * valor_presente) / p)
    modificada = macaulay / (1 + tasa)
    convexidad = float(np.sum(flujo * k * (k + 1) / (frecuencia**2 * (1 + tasa) ** (k + 2))) / p)
    return {
        "precio": p,
        "macaulay": macaulay,
        "modificada": modificada,
        "dv01": modificada * p * PUNTO_BASE,
        "convexidad": convexidad,
    }


def aproximar_cambio_de_precio(precio_inicial: float, duracion_modificada: float, convexidad: float, cambio_de_tasa: float) -> dict:
    """Cambio de precio estimado para un cambio de tasa (en decimales), de dos maneras.

    - Solo duración: ΔP ≈ -D · Δy · P           (una línea recta)
    - Duración + convexidad: suma ½ · C · Δy² · P (una parábola, más fiel)"""
    por_duracion = -duracion_modificada * cambio_de_tasa * precio_inicial
    por_convexidad = 0.5 * convexidad * cambio_de_tasa**2 * precio_inicial
    return {
        "solo_duracion": por_duracion,
        "duracion_y_convexidad": por_duracion + por_convexidad,
    }


def descomponer_retorno(tasa_inicial: float, cambio_de_tasa: float, duracion_modificada: float, convexidad: float, horizonte: float = 1.0) -> dict:
    """De dónde sale el retorno de un bono en un horizonte (en % del precio inicial, como decimal).

    retorno ≈ carry (los intereses que devenga) − efecto duración + efecto convexidad.
    El carry es lo seguro; los otros dos dependen de hacia dónde se muevan las tasas."""
    carry = tasa_inicial * horizonte
    efecto_duracion = -duracion_modificada * cambio_de_tasa
    efecto_convexidad = 0.5 * convexidad * cambio_de_tasa**2
    return {
        "carry": carry,
        "efecto_duracion": efecto_duracion,
        "efecto_convexidad": efecto_convexidad,
        "total": carry + efecto_duracion + efecto_convexidad,
    }


# ---------------------------------------------------------------------------
# Curva de tasas
# ---------------------------------------------------------------------------
def curva_en_fecha(pivote: pd.DataFrame, fecha) -> tuple[pd.Timestamp, pd.Series]:
    """La curva de la última fecha con TODOS los plazos disponibles, a esa fecha o antes.

    `pivote` tiene una fila por fecha y una columna por plazo (en años). Devuelve
    (fecha real usada, serie plazo → tasa en la unidad del pivote)."""
    completo = pivote.dropna()
    candidatas = completo[completo.index <= pd.Timestamp(fecha)]
    if candidatas.empty:
        raise ValueError("No hay ninguna curva completa a esa fecha o antes.")
    return candidatas.index[-1], candidatas.iloc[-1]


def interpolar_tasa(curva: pd.Series, plazo: float) -> float:
    """Tasa para un plazo cualquiera, uniendo los puntos de la curva con rectas.

    Es la forma más simple de leer entre dos vértices; modelos como
    Nelson-Siegel (ver Laboratorio Financiero) ajustan una curva suave."""
    plazos = curva.index.to_numpy(dtype=float)
    if plazo < plazos.min() or plazo > plazos.max():
        raise ValueError(f"El plazo {plazo} está fuera de la curva ({plazos.min():.3g} a {plazos.max():.3g} años).")
    return float(np.interp(plazo, plazos, curva.to_numpy(dtype=float)))


def bono_a_la_par(curva: pd.Series, plazo: float, frecuencia: int = 2, nominal: float = 100.0) -> dict:
    """Un bono que paga como cupón la tasa de la curva a su plazo, o sea que vale exactamente su nominal.

    Así es, a grandes rasgos, como el Tesoro construye la curva de rendimientos
    que publica (bonos «a la par»), por eso sirve de modelo."""
    y = interpolar_tasa(curva, plazo)
    return {"plazo": plazo, "tasa": y, **metricas_de_riesgo(nominal, y, plazo, frecuencia, y)}


def rodar_en_la_curva(curva: pd.Series, plazo: float, horizonte: float, frecuencia: int = 2, nominal: float = 100.0) -> dict:
    """Retorno de comprar un bono a la par y venderlo pasado `horizonte` años, SI LA CURVA NO SE MUEVE.

    Con una curva de pendiente positiva, al envejecer el bono su plazo
    restante es más corto y se descuenta a una tasa menor: sube de precio.
    Eso es «rodar por la curva» (roll-down), y se suma al carry (los cupones).
    No incluye reinversión de cupones ni cambios en la curva."""
    restante = plazo - horizonte
    if restante <= 0:
        raise ValueError("El horizonte debe ser menor que el plazo del bono.")
    _periodos(restante, frecuencia)  # el plazo restante tiene que calzar con la frecuencia
    _periodos(horizonte, frecuencia)  # y los cupones cobrados también

    y_compra = interpolar_tasa(curva, plazo)
    y_venta = interpolar_tasa(curva, restante)
    precio_venta = precio(nominal, y_compra, restante, frecuencia, y_venta)
    cupones = nominal * y_compra * horizonte
    carry = cupones / nominal
    efecto_precio = (precio_venta - nominal) / nominal
    total = carry + efecto_precio
    return {
        "tasa_compra": y_compra,
        "tasa_venta": y_venta,
        "precio_venta": precio_venta,
        "carry": carry,
        "efecto_precio": efecto_precio,
        "retorno_total": total,
        "retorno_anualizado": (1 + total) ** (1 / horizonte) - 1,
    }


def curva_de_descuento(curva: pd.Series, anios_maximos: float = 30.0, frecuencia: int = 2) -> pd.DataFrame:
    """Cuánto vale hoy 1 peso pagado dentro de N años, sacado de la curva REAL de rendimientos.

    La curva del Tesoro son rendimientos de bonos «a la par» (cupón = tasa).
    Para llegar al factor de descuento de cada plazo se resuelve, de a un
    semestre a la vez (bootstrapping), la condición de que un bono a la par
    vale 100:  100 = c · Σ(factores anteriores) + (100 + c) · factor_n,
    con c = tasa_par / frecuencia · 100.

    Devuelve una fila por período de cupón: `anios`, `tasa_par`, `factor` y
    `tasa_cero` (la tasa de un bono sin cupones a ese plazo)."""
    periodos = int(round(anios_maximos * frecuencia))
    factores: list[float] = []
    filas = []
    for n in range(1, periodos + 1):
        anios = n / frecuencia
        tasa_par = interpolar_tasa(curva, anios)
        cupon = tasa_par / frecuencia * 100
        factor = (100 - cupon * sum(factores)) / (100 + cupon)
        factores.append(factor)
        tasa_cero = (factor ** (-1 / n) - 1) * frecuencia
        filas.append({"anios": anios, "tasa_par": tasa_par, "factor": factor, "tasa_cero": tasa_cero})
    return pd.DataFrame(filas)


def bono_a_la_par_hoy(tasa_de_compra: float, plazo: float, transcurrido: float, tasa_hoy: float,
                      frecuencia: int = 2, nominal: float = 100.0) -> dict:
    """Qué pasó con un bono comprado a la par con la tasa REAL de una fecha pasada, valorizado con la tasa REAL de hoy.

    - `tasa_de_compra`: rendimiento de ese plazo cuando se compró (cupón = esa tasa).
    - `transcurrido`: años desde la compra hasta hoy.
    - `tasa_hoy`: rendimiento de hoy para el plazo que le queda (plazo - transcurrido).
    Devuelve el precio de hoy, los cupones cobrados y el retorno (sin reinvertir cupones)."""
    restante = plazo - transcurrido
    if restante <= 0:
        raise ValueError("El tiempo transcurrido debe ser menor que el plazo del bono.")
    _periodos(restante, frecuencia)
    _periodos(transcurrido, frecuencia)
    precio_hoy = precio(nominal, tasa_de_compra, restante, frecuencia, tasa_hoy)
    cupones = nominal * tasa_de_compra * transcurrido
    efecto_precio = (precio_hoy - nominal) / nominal
    carry = cupones / nominal
    return {
        "precio_hoy": precio_hoy, "cupones": cupones, "efecto_precio": efecto_precio,
        "carry": carry, "retorno_total": efecto_precio + carry,
    }


# ---------------------------------------------------------------------------
# Instrumentos reales: métricas a partir de una serie de precios
# ---------------------------------------------------------------------------
DIAS_HABILES_ANIO = 252
MINIMO_DE_OBSERVACIONES = 30
DIAS_DEL_ANIO = 365


def _un_anio_atras(precios: pd.Series) -> pd.Series:
    return precios[precios.index >= precios.index[-1] - pd.Timedelta(days=DIAS_DEL_ANIO)]


def cambios_por_periodo(precios: pd.Series) -> dict:
    """Cambio % a 1 día, 1 semana, 1 mes y en lo que va del año, contra el último precio.

    Mismo criterio que las tablas de acciones del dashboard: «hace N días»
    es el último precio en esa fecha o antes, y el YTD parte desde el primer
    dato del año. Con precios AJUSTADOS por distribuciones (como los que baja
    el cron) es un retorno total: incluye lo que el ETF repartió."""
    vacio = {"1D %": None, "1W %": None, "1M %": None, "YTD %": None}
    if len(precios) < 2:
        return vacio
    ultimo, fecha = precios.iloc[-1], precios.index[-1]

    def desde(dias: int):
        previos = precios[precios.index <= fecha - pd.Timedelta(days=dias)]
        return (ultimo / previos.iloc[-1] - 1) * 100 if not previos.empty else None

    del_anio = precios[precios.index >= pd.Timestamp(fecha.year, 1, 1)]
    return {
        "1D %": desde(1), "1W %": desde(7), "1M %": desde(30),
        "YTD %": (ultimo / del_anio.iloc[0] - 1) * 100 if not del_anio.empty else None,
    }


def retorno_ultimo_anio(precios: pd.Series) -> float | None:
    """Retorno % entre el primer dato del último año y el último."""
    ventana = _un_anio_atras(precios)
    return float((ventana.iloc[-1] / ventana.iloc[0] - 1) * 100) if len(ventana) >= 2 else None


def volatilidad_anualizada(precios: pd.Series) -> float | None:
    """Desviación estándar de los retornos diarios del último año, anualizada (× raíz de 252), en %."""
    retornos = _un_anio_atras(precios).pct_change().dropna()
    return float(retornos.std() * DIAS_HABILES_ANIO**0.5 * 100) if len(retornos) >= MINIMO_DE_OBSERVACIONES else None


def caida_maxima(precios: pd.Series) -> float | None:
    """La peor caída desde un máximo previo, dentro del último año, en % (negativo)."""
    ventana = _un_anio_atras(precios)
    if len(ventana) < 2:
        return None
    return float((ventana / ventana.cummax() - 1).min() * 100)


def beta_contra(retornos: pd.Series, retornos_mercado: pd.Series) -> float | None:
    """Cuánto se mueve el instrumento por cada 1 % que se mueve el mercado (cov / var, retornos diarios)."""
    conjunto = pd.concat([retornos, retornos_mercado], axis=1, join="inner", keys=["x", "m"]).dropna()
    if len(conjunto) < MINIMO_DE_OBSERVACIONES or conjunto["m"].var() <= 0:
        return None
    return float(conjunto["m"].cov(conjunto["x"]) / conjunto["m"].var())


def razon_de_sharpe(retorno_pct: float | None, tasa_libre_de_riesgo_pct: float | None, volatilidad_pct: float | None) -> float | None:
    """(retorno del último año - tasa libre de riesgo) / volatilidad."""
    if retorno_pct is None or tasa_libre_de_riesgo_pct is None or not volatilidad_pct:
        return None
    return (retorno_pct - tasa_libre_de_riesgo_pct) / volatilidad_pct


def pares_para_duracion(precios: pd.Series, rendimientos: pd.Series, ventana: int = DIAS_HABILES_ANIO) -> pd.DataFrame:
    """Los pares (cambio diario de la tasa, retorno diario del precio) con que se mide la duración.

    Se alinean precio y rendimiento SOLO en las fechas en que existen los dos y se toman los últimos
    `ventana` días, así que el cambio de tasa y el retorno de cada fila cubren el mismo período
    aunque falte algún día en una de las series. Columnas: `cambio_de_tasa` (decimal) y `retorno` (decimal)."""
    comun = pd.concat([precios, rendimientos], axis=1, join="inner", keys=["p", "y"]).dropna().tail(ventana + 1)
    pares = pd.DataFrame({"cambio_de_tasa": comun["y"].diff(), "retorno": comun["p"].pct_change()}).dropna()
    return pares


def duracion_empirica(precios: pd.Series, rendimientos: pd.Series, ventana: int = DIAS_HABILES_ANIO) -> dict | None:
    """Duración MEDIDA con datos: cuánto cayó el precio por cada punto que subió la tasa de referencia.

    Se alinean precio y rendimiento en las fechas en que existen los dos,
    se toman los últimos `ventana` días y se hace una regresión del retorno
    diario del precio contra el cambio diario de la tasa (en decimales). La
    pendiente es -duración: 6,5 significa que el precio cayó cerca de 6,5 %
    por cada punto porcentual que subió la tasa.

    Devuelve `duracion`, `error_estandar` (de la pendiente: la duración real
    suele estar a ±2 errores), `r2` (qué parte del movimiento del precio la
    explica la tasa; baja en bonos de empresas, donde pesa el riesgo de crédito)
    y `n`."""
    pares = pares_para_duracion(precios, rendimientos, ventana)
    retornos, cambios = pares["retorno"], pares["cambio_de_tasa"]
    n = len(pares)
    if n < MINIMO_DE_OBSERVACIONES or cambios.std() == 0 or retornos.std() == 0:
        return None
    pendiente = float(np.cov(retornos, cambios)[0, 1] / cambios.var())
    correlacion = float(np.corrcoef(retornos, cambios)[0, 1])
    error = float(np.sqrt((1 - correlacion**2) / (n - 2)) * retornos.std() / cambios.std())
    return {"duracion": -pendiente, "error_estandar": error, "r2": correlacion**2, "n": n}


def resumen_de_instrumento(precios: pd.Series, precios_mercado: pd.Series, rendimiento_referencia: pd.Series,
                           tasa_libre_de_riesgo_pct: float | None) -> dict | None:
    """Todas las métricas de una fila de la tabla de ETFs de bonos.

    `precios_mercado`: serie del mercado de acciones para el beta. `rendimiento_referencia`:
    tasa del Tesoro (en decimales) con la que se mide la duración."""
    precios = precios.dropna().sort_index()
    if len(precios) < 2:
        return None
    retorno_1a = retorno_ultimo_anio(precios)
    volatilidad = volatilidad_anualizada(precios)
    medida = duracion_empirica(precios, rendimiento_referencia)
    retornos = precios.pct_change()
    retornos_mercado = precios_mercado.dropna().sort_index().pct_change()
    recientes = retornos[retornos.index >= precios.index[-1] - pd.Timedelta(days=DIAS_DEL_ANIO)]
    return {
        **cambios_por_periodo(precios),
        "Retorno 1 año (%)": retorno_1a,
        "Volatilidad (%)": volatilidad,
        "Caída máxima 1 año (%)": caida_maxima(precios),
        "Beta vs S&P 500": beta_contra(recientes, retornos_mercado),
        "Duración medida (años)": medida["duracion"] if medida else None,
        "Error de la duración": medida["error_estandar"] if medida else None,
        "R² con la tasa": medida["r2"] if medida else None,
        "Sharpe": razon_de_sharpe(retorno_1a, tasa_libre_de_riesgo_pct, volatilidad),
        "ultima_fecha": precios.index[-1],
    }


# ---------------------------------------------------------------------------
# Carteras armadas con instrumentos reales
# ---------------------------------------------------------------------------
def retornos_de_cartera(retornos: pd.DataFrame, pesos: dict) -> pd.Series:
    """Retorno diario de una cartera con pesos constantes (se rebalancea cada día): Σ peso × retorno."""
    if abs(sum(pesos.values()) - 1) > 1e-9:
        raise ValueError("Los pesos deben sumar 1.")
    return sum(retornos[nombre] * peso for nombre, peso in pesos.items()).dropna()


def estadisticas_de_retornos(retornos: pd.Series) -> dict:
    """Retorno acumulado, volatilidad anualizada y caída máxima de una serie de retornos diarios, en %."""
    if len(retornos) < 2:
        raise ValueError("Se necesitan al menos 2 retornos.")
    acumulado = (1 + retornos).cumprod()
    return {
        "retorno_total": float((acumulado.iloc[-1] - 1) * 100),
        "volatilidad": float(retornos.std() * DIAS_HABILES_ANIO**0.5 * 100),
        "caida_maxima": float((acumulado / acumulado.cummax() - 1).min() * 100),
    }


def pesos_para_igualar_duracion(duracion_corta: float, duracion_larga: float, duracion_objetivo: float) -> tuple[float, float]:
    """Peso en el instrumento corto y en el largo para que la cartera tenga la duración objetivo (un «barbell»).

    w · D_corta + (1 - w) · D_larga = D_objetivo, con el objetivo entre las dos duraciones."""
    if not duracion_corta < duracion_objetivo < duracion_larga:
        raise ValueError("Se necesita duración corta < objetivo < larga.")
    peso_corto = (duracion_larga - duracion_objetivo) / (duracion_larga - duracion_corta)
    return peso_corto, 1 - peso_corto
