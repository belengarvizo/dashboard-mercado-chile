"""
Modelo de Black-Scholes para la sección «Derivados»: precio teórico de una opción europea, sus griegas y la
volatilidad implícita. Sin Streamlit, para poder probarlo con casos de respuesta conocida.

QUÉ ES BLACK-SCHOLES. Una fórmula que dice cuánto "debería" valer una opción europea (que solo se puede ejercer al
vencimiento) dados cinco datos: el precio de hoy del subyacente (S), el precio al que se puede ejercer (K), el
tiempo que falta para el vencimiento (T, en años), la tasa libre de riesgo (r) y la volatilidad esperada del
subyacente (sigma). De los cinco, CUATRO se observan directamente en el mercado; sigma es el único que no se ve:
hay que suponerlo o, al revés, despejarlo del precio real de mercado (eso es la "volatilidad implícita").

CONVENCIONES
    - T se mide en AÑOS, con días corridos sobre 365 (no días hábiles sobre 252): es la convención estándar de
      Black-Scholes y la que usa Yahoo Finance para su propia volatilidad implícita, así que los números quedan
      comparables.
    - No se descuentan dividendos (q = 0): válido para un ETF que no reparte muy seguido dentro del plazo de la
      opción, pero es una simplificación — Black-Scholes "puro" asume que el subyacente no reparte nada.
    - "Call" y "put" son los únicos dos tipos; no hay opciones americanas (que se pueden ejercer antes) ni exóticas.

LÍMITES QUE EL MÓDULO DECLARA
    - El modelo asume que la volatilidad es constante hasta el vencimiento, que no hay costos de transacción y que
      se puede operar continuamente: ninguna de las tres es exactamente cierta en el mercado real.
    - La volatilidad implícita que se despeja acá puede no coincidir con la que publica Yahoo, porque Yahoo puede
      usar otra convención de tasa libre de riesgo o de dividendos; la pantalla muestra las dos por separado.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

DIAS_DEL_ANIO = 365.0
# Límites de búsqueda de la volatilidad implícita (como decimal: 0.001 = 0,1%, 5.0 = 500%). Una opción muy fuera
# de dinero con poco tiempo puede, en teoría, necesitar una volatilidad absurda para explicar su precio; 500% es
# un techo generoso que cubre casos reales sin dejar la búsqueda abierta a cualquier número.
VOLATILIDAD_MINIMA = 0.001
VOLATILIDAD_MAXIMA = 5.0
ITERACIONES_MAXIMAS = 100
TOLERANCIA = 1e-6


def _validar(S: float, K: float, T: float, sigma: float) -> None:
    if S <= 0 or K <= 0:
        raise ValueError("El precio del subyacente y el strike deben ser positivos.")
    if T < 0:
        raise ValueError("El tiempo al vencimiento no puede ser negativo.")
    if sigma < 0:
        raise ValueError("La volatilidad no puede ser negativa.")


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    if T == 0 or sigma == 0:
        # Sin tiempo o sin volatilidad, el precio es determinista (ver valor_intrinseco): d1/d2 no se usan.
        return float("nan"), float("nan")
    raiz_t = math.sqrt(T)
    d1 = (math.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * raiz_t)
    d2 = d1 - sigma * raiz_t
    return d1, d2


def _cdf_normal(x: float) -> float:
    """Función de distribución acumulada de la normal estándar, vía la función error (sin depender de scipy)."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _pdf_normal(x: float) -> float:
    return math.exp(-x**2 / 2) / math.sqrt(2 * math.pi)


def valor_intrinseco(S: float, K: float, tipo: str) -> float:
    """Lo que vale la opción si se pudiera ejercer AHORA MISMO, sin valor de tiempo: max(S-K, 0) para un call,
    max(K-S, 0) para un put. Es el precio al que Black-Scholes converge cuando T llega a 0."""
    if tipo == "call":
        return max(S - K, 0.0)
    if tipo == "put":
        return max(K - S, 0.0)
    raise ValueError(f"tipo debe ser 'call' o 'put', llegó {tipo!r}")


def precio(S: float, K: float, T: float, r: float, sigma: float, tipo: str) -> float:
    """Precio teórico de una opción europea según Black-Scholes."""
    _validar(S, K, T, sigma)
    if T == 0 or sigma == 0:
        return valor_intrinseco(S, K, tipo)
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    descuento = math.exp(-r * T)
    if tipo == "call":
        return S * _cdf_normal(d1) - K * descuento * _cdf_normal(d2)
    if tipo == "put":
        return K * descuento * _cdf_normal(-d2) - S * _cdf_normal(-d1)
    raise ValueError(f"tipo debe ser 'call' o 'put', llegó {tipo!r}")


@dataclass
class Griegas:
    """Cuánto cambia el precio de la opción si cambia, de a uno, cada dato de entrada.

    delta: por 1 unidad que sube el subyacente (S). gamma: cuánto cambia el propio delta por esa misma unidad
    (es la misma para call y put). theta: por el paso de UN DÍA (no un año; es la convención que se usa en la
    práctica, porque "cuánto pierde la opción mañana" es la pregunta útil). vega: por 1 punto porcentual de
    volatilidad (0.01 en sigma). rho: por 1 punto porcentual de tasa (0.01 en r)."""
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


def griegas(S: float, K: float, T: float, r: float, sigma: float, tipo: str) -> Griegas:
    _validar(S, K, T, sigma)
    if T <= 0 or sigma <= 0:
        # Sin tiempo o sin volatilidad no hay valor de tiempo que perder ni sensibilidad que medir con sentido.
        return Griegas(delta=float("nan"), gamma=float("nan"), theta=float("nan"), vega=float("nan"), rho=float("nan"))
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    raiz_t = math.sqrt(T)
    descuento = math.exp(-r * T)
    gamma = _pdf_normal(d1) / (S * sigma * raiz_t)
    vega = S * _pdf_normal(d1) * raiz_t / 100  # por 1 punto porcentual (0.01) de sigma, no por 1.0 completo
    if tipo == "call":
        delta = _cdf_normal(d1)
        theta_anual = -(S * _pdf_normal(d1) * sigma) / (2 * raiz_t) - r * K * descuento * _cdf_normal(d2)
        rho = K * T * descuento * _cdf_normal(d2) / 100
    elif tipo == "put":
        delta = _cdf_normal(d1) - 1
        theta_anual = -(S * _pdf_normal(d1) * sigma) / (2 * raiz_t) + r * K * descuento * _cdf_normal(-d2)
        rho = -K * T * descuento * _cdf_normal(-d2) / 100
    else:
        raise ValueError(f"tipo debe ser 'call' o 'put', llegó {tipo!r}")
    return Griegas(delta=delta, gamma=gamma, theta=theta_anual / DIAS_DEL_ANIO, vega=vega, rho=rho)


def volatilidad_implicita(precio_de_mercado: float, S: float, K: float, T: float, r: float, tipo: str) -> float | None:
    """La volatilidad que, metida en Black-Scholes, hace que el precio teórico sea EXACTAMENTE el de mercado.

    Se busca por bisección (no Newton-Raphson): es más lento pero no depende de una derivada (vega) que puede ser
    casi cero en opciones muy fuera de dinero, donde Newton-Raphson diverge. Devuelve None si el precio de mercado
    es menor que el valor intrínseco (correspondería a una volatilidad negativa, imposible) o si no hay una
    volatilidad dentro de [VOLATILIDAD_MINIMA, VOLATILIDAD_MAXIMA] que lo explique."""
    _validar(S, K, T, 0.0)
    if T <= 0:
        return None
    intrinseco = valor_intrinseco(S, K, tipo)
    if precio_de_mercado < intrinseco - TOLERANCIA:
        return None  # un precio bajo el intrínseco no es explicable por ninguna volatilidad

    bajo, alto = VOLATILIDAD_MINIMA, VOLATILIDAD_MAXIMA
    precio_bajo = precio(S, K, T, r, bajo, tipo)
    precio_alto = precio(S, K, T, r, alto, tipo)
    if not (precio_bajo - TOLERANCIA <= precio_de_mercado <= precio_alto + TOLERANCIA):
        return None  # ninguna volatilidad en el rango explica ese precio

    for _ in range(ITERACIONES_MAXIMAS):
        medio = (bajo + alto) / 2
        precio_medio = precio(S, K, T, r, medio, tipo)
        if abs(precio_medio - precio_de_mercado) < TOLERANCIA:
            return medio
        if precio_medio < precio_de_mercado:
            bajo = medio
        else:
            alto = medio
    return (bajo + alto) / 2
