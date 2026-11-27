"""Tiempo al vencimiento de las opciones de la sección Derivados, en años ACT/365F (H3-D2, Derivados).

QUÉ CAMBIA
    Antes: T = días completos entre la FECHA de hoy (reloj del servidor) y la fecha de vencimiento, / 365. Un contrato
    que vencía hoy quedaba con T = 0 aunque le quedaran horas de negociación, y T saltaba un día entero a medianoche.
    Ahora: T = (instante del horizonte − instante de valoración) en segundos / (365 × 86.400). Es ACT/365F en tiempo
    continuo: los días son de 24 horas reales (el día del cambio de horario de verano dura 23 o 25 horas).

TRES MOMENTOS DISTINTOS (no se mezclan)
    - CIERRE DE NEGOCIACIÓN: SPY, QQQ, IWM, DIA y TLT negocian de 9:30 a.m. a 4:15 p.m. hora de Nueva York (no hasta las
      4:00). Fuentes consultadas el 27-11-2026: Nasdaq Options Market Hours (lista de clases hasta las 4:15 p.m.), las
      listas «4:15 p.m. Options Late Close Exceptions» de NYSE American y NYSE Arca (incluyen las cinco) y Cboe (las
      opciones sobre ETF que negocian hasta las 4:15 p.m. siguen haciéndolo). Las opciones se negocian en varias bolsas;
      el horario puede diferir por bolsa y por contrato, y no se verificó cada una.
    - SESIÓN REDUCIDA: la NYSE anuncia cierre a la 1:15 p.m. «para opciones elegibles» (27-nov y 24-dic-2026), sin definir
      cuáles son; Cboe publica 1:00 p.m. para su mercado de opciones esos mismos días. Se usa 1:15 p.m. como APROXIMACIÓN:
      la aplicabilidad a estas cinco clases no está confirmada y el cierre efectivo depende de la bolsa.
    - PLAZO DE EJERCICIO: según FINRA Rule 2360, por regla general 5:30 p.m. hora de Nueva York del día de vencimiento; en
      una sesión acortada, 1 hora y 30 minutos después del cierre anunciado; si el vencimiento cae en un día no hábil, el
      día hábil anterior. Los intermediarios pueden fijar un plazo ANTERIOR. No es universal; aquí es informativo:
      Black-Scholes no lo usa.
    - HORIZONTE DEL MODELO: el cierre de negociación del día de vencimiento. Es una APROXIMACIÓN METODOLÓGICA: no se verificó
      la hora de cese el propio día de vencimiento. Cada aproximación queda escrita en `Horizonte.aproximaciones`.
      Fuera de la cobertura verificada del calendario de la NYSE no se infiere ningún horario especial: se usa el cierre
      regular y se advierte que el calendario no está verificado.

CUATRO MOMENTOS DISTINTOS EN PANTALLA
    - INSTANTE DE CONSULTA: cuando el usuario abre la pantalla (reloj.ahora_utc).
    - INSTANTE DE VALORACIÓN: el del precio del subyacente usado (no «ahora»), para que T corresponda a los precios con que
      se valora. Si no se conoce, se usa el instante de consulta y se dice. Nunca es posterior a la consulta.
    - FECHA Y HORA DE LA COTIZACIÓN DE LA OPCIÓN: la de su última operación, si se usa ese precio; Yahoo no informa la hora
      del bid/ask, así que en ese caso no se afirma que sea contemporáneo.
    - HORIZONTE DE NEGOCIACIÓN: el cierre de negociación del día de vencimiento.
    Si la consulta es posterior al horizonte, el contrato ya venció: lo que se muestra es una valorización HISTÓRICA al
    instante de valoración, nunca una vigente. Y el valor intrínseco con un precio anterior al cierre no es la liquidación
    contractual (que depende del precio al cierre y de las decisiones de ejercicio).

T = 0 Y HORIZONTE TERMINADO
    Si el instante de valoración es igual o posterior al horizonte, T = 0 y el horizonte está terminado: no se despeja
    volatilidad implícita ni se calculan griegas (black_scholes ya devuelve el valor intrínseco y no divide por cero).

LO QUE NO CAMBIA
    Black-Scholes europeo aplicado a opciones americanas (simplificación declarada en pantalla), sin dividendos (q = 0).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

import pandas as pd

import calendarios_financieros as calf
import reloj

CLASES_CIERRE_1615 = frozenset({"SPY", "QQQ", "IWM", "DIA", "TLT"})
FUENTE_HORARIO = ("Nasdaq Options Market Hours (https://www.nasdaqtrader.com/Trader.aspx?id=optionshours), consultada el "
                  "27-11-2026: estas clases negocian de 9:30 a.m. a 4:15 p.m. ET")
FUENTE_EJERCICIO = ("FINRA Rule 2360: por regla general, 5:30 p.m. ET del día de vencimiento (1 h 30 min después de un cierre "
                    "acortado); los intermediarios pueden fijar un plazo anterior")
CIERRE_REGULAR = time(16, 15)
CIERRE_REDUCIDO_APROXIMADO = time(13, 15)
CIERRE_GENERICO_APROXIMADO = time(16, 0)
PLAZO_DE_EJERCICIO = time(17, 30)
SEGUNDOS_DEL_ANIO = 365 * 86400          # ACT/365F

APROX_HORIZONTE = ("Horizonte del modelo = cierre de negociación del día de vencimiento. Aproximación metodológica: no se "
                   "verificó la hora de cese de negociación del propio día de vencimiento; se usa el cierre de la sesión.")


@dataclass(frozen=True)
class Horizonte:
    ticker: str
    vencimiento: date
    cierre_de_negociacion: datetime      # hora de Nueva York, con zona
    plazo_de_ejercicio: datetime          # hora de Nueva York, con zona (informativo)
    aproximaciones: tuple[str, ...]

    @property
    def instante(self) -> datetime:
        """El instante en que termina el horizonte del modelo (UTC)."""
        return self.cierre_de_negociacion.astimezone(timezone.utc)


def horizonte(ticker: str, vencimiento) -> Horizonte:
    d = pd.Timestamp(vencimiento).date()
    aproximaciones = [APROX_HORIZONTE]
    if ticker in CLASES_CIERRE_1615:
        hora = CIERRE_REGULAR
    else:
        hora = CIERRE_GENERICO_APROXIMADO
        aproximaciones.append(f"{ticker}: horario de negociación no verificado; se usa 4:00 p.m. ET.")
    sesion = calf.es_sesion("nyse", d)
    if sesion is None:
        aproximaciones.append("El calendario de la NYSE no está verificado para esa fecha: no se sabe si es una sesión "
                              "normal, reducida o feriado.")
    elif sesion is False:
        aproximaciones.append("La fecha de vencimiento informada no es una sesión de la NYSE; se usa tal como la informa "
                              "Yahoo Finance, sin corregirla.")
    if d in calf.cargar("nyse").sesiones_reducidas and ticker in CLASES_CIERRE_1615:
        hora = CIERRE_REDUCIDO_APROXIMADO
        aproximaciones.append("Sesión reducida: la NYSE anuncia 1:15 p.m. ET «para opciones elegibles» sin definirlas y Cboe "
                              "publica 1:00 p.m. para sus opciones; se usa 1:15 p.m. ET como aproximación.")
    cierre = datetime.combine(d, hora, tzinfo=reloj.ZONA_NUEVA_YORK)
    ejercicio = datetime.combine(d, PLAZO_DE_EJERCICIO, tzinfo=reloj.ZONA_NUEVA_YORK)
    return Horizonte(ticker, d, cierre, ejercicio, tuple(aproximaciones))


def instante_de_valoracion(instante_del_precio: datetime | None) -> tuple[datetime, bool]:
    """(instante de valoración en UTC, si es el del precio del subyacente). Nunca posterior a ahora."""
    ahora = reloj.ahora_utc()
    if instante_del_precio is None:
        return ahora, False
    if instante_del_precio.tzinfo is None:
        raise ValueError("el instante del precio necesita zona horaria")
    return min(instante_del_precio.astimezone(timezone.utc), ahora), True


# Barras de 1 minuto de Yahoo Finance: se fechan con el INICIO del intervalo (convención de yfinance, no documentada
# oficialmente por Yahoo). Su precio de cierre corresponde al FINAL del minuto, así que el instante del precio es el inicio
# más un minuto (recortado a la consulta si el minuto todavía no termina).
DURACION_DE_LA_BARRA = 60


def instante_del_cierre_de_barra(inicio_de_barra: datetime) -> datetime:
    """El instante del precio de cierre de una barra de 1 minuto fechada con su inicio, nunca posterior a ahora."""
    if inicio_de_barra.tzinfo is None:
        raise ValueError("el inicio de la barra necesita zona horaria")
    from datetime import timedelta
    return min(inicio_de_barra.astimezone(timezone.utc) + timedelta(seconds=DURACION_DE_LA_BARRA), reloj.ahora_utc())


def vencido_al_consultar(h: "Horizonte", consulta: datetime | None = None) -> bool:
    """True si el instante de consulta es posterior al horizonte: lo que se muestre es histórico, no vigente."""
    return (consulta or reloj.ahora_utc()).astimezone(timezone.utc) >= h.instante


def anios(h: Horizonte, valoracion: datetime) -> float:
    """T en años ACT/365F desde `valoracion` hasta el horizonte; 0 si el horizonte ya terminó."""
    segundos = (h.instante - valoracion.astimezone(timezone.utc)).total_seconds()
    return max(segundos, 0.0) / SEGUNDOS_DEL_ANIO


def terminado(h: Horizonte, valoracion: datetime) -> bool:
    return valoracion.astimezone(timezone.utc) >= h.instante


def dias_completos(T: float) -> int:
    """Días completos que quedan (para mostrar y elegir el vencimiento por defecto), no para valorar."""
    return int(T * 365 + 1e-9)


def texto_de_tiempo(T: float) -> str:
    """«3 días y 5 h», «6 h 15 min» o «terminado»."""
    if T <= 0:
        return "terminado"
    minutos = round(T * SEGUNDOS_DEL_ANIO / 60)
    dias, resto = divmod(minutos, 24 * 60)
    horas, mins = divmod(resto, 60)
    if dias:
        return f"{dias} {'día' if dias == 1 else 'días'} y {horas} h"
    return f"{horas} h {mins} min"
