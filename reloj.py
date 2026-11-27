"""Reloj centralizado del dashboard (H3-D2). Un único lugar para «ahora» y «hoy», con zona horaria explícita.

POR QUÉ
    `date.today()`, `datetime.now()` y `pd.Timestamp.now()` sin zona dependen de la zona del servidor, que en Railway no
    está configurada en el repositorio. Con este módulo el resultado es el mismo con el servidor en UTC o en hora de Chile.

CUATRO TIPOS DE FECHA (no se mezclan)
    - INSTANTE: un momento exacto, con zona (`ahora_utc`, `ahora_santiago`). Lo usan los registros y la hora impresa en
      un PDF («generado el … (hora de Santiago)»).
    - FECHA ECONÓMICA: la fecha de un dato en la base (`series_macro.fecha`, `precios_acciones.fecha`): una fecha simple,
      sin zona. No se convierte: es la fecha que trae la fuente.
    - FECHA DE SESIÓN: la fecha de una sesión en la zona de SU mercado (`fecha_de_sesion`): las 22:00 del lunes en Nueva
      York ya son el martes en Santiago, pero la sesión es la del lunes. Yahoo ya entrega los precios con la fecha de sesión.
    - FECHA DE CORTE: la que fija un informe a partir de sus propios datos (por ejemplo, el PDF de renta fija). No sale de
      este reloj: un informe histórico da el mismo resultado sin importar cuándo se genere.

«HOY» DEL DASHBOARD = FECHA DE SANTIAGO (`hoy_santiago`)
    Es la fecha que ve el usuario y la que se usa para medir la antigüedad de los datos (calendarios_financieros cuenta
    hasta «hoy», EXCLUIDO). Es correcta también para los mercados de EE. UU.: Santiago va 0 a 2 horas ADELANTE de Nueva
    York, así que cuando la fecha de Santiago ya cambió y la de Nueva York todavía no (entre las 22:00 y las 24:00 de
    Nueva York), la sesión de Nueva York de ese día ya cerró (16:00). Contarla como sesión pasada no adelanta ningún
    atraso. Con un mercado al ESTE de Santiago esto no vale: en Tokio la fecha cambia antes, y entre la medianoche de Tokio
    y la de Santiago la fecha de Santiago va un día ATRÁS de la del mercado (contaría una sesión menos). Para un mercado así
    se usa su propia fecha, `hoy_en(zona)`. Hoy el dashboard no mide la frescura de ningún mercado asiático (los pares de
    divisas «=X» usan el calendario 24/5 y su convención de fecha está pendiente, H3-10).
    La fecha de Santiago es la referencia GENERAL de la interfaz; no reemplaza las fechas de los datos (fecha económica) ni
    las fechas de sesión de cada mercado, que se conservan tal como las entrega la fuente.

PRUEBAS
    `fijar(instante)` congela el reloj (context manager) para probar fines de día, cambios de horario y servidores en
    distintas zonas sin tocar el reloj del sistema.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

ZONA_SANTIAGO = ZoneInfo("America/Santiago")
ZONA_NUEVA_YORK = ZoneInfo("America/New_York")
UTC = timezone.utc

_instante_fijo: datetime | None = None


def ahora_utc() -> datetime:
    """El instante actual, con zona UTC."""
    if _instante_fijo is not None:
        return _instante_fijo.astimezone(UTC)
    return datetime.now(UTC)


def ahora_santiago() -> datetime:
    """El instante actual en hora de Santiago (con zona)."""
    return ahora_utc().astimezone(ZONA_SANTIAGO)


def hoy_santiago() -> date:
    """La fecha de hoy en Santiago."""
    return ahora_santiago().date()


def hoy_santiago_ts() -> pd.Timestamp:
    """La fecha de hoy en Santiago como Timestamp a medianoche y SIN zona, para compararla con fechas económicas."""
    return pd.Timestamp(hoy_santiago())


def hoy_en(zona: ZoneInfo) -> date:
    """La fecha de hoy en la zona de un mercado (por ejemplo, Tokio), para los mercados al este de Santiago."""
    return ahora_utc().astimezone(zona).date()


def fecha_de_sesion(instante: datetime, zona: ZoneInfo) -> date:
    """La fecha de un instante en la zona de un mercado (por ejemplo, ZONA_NUEVA_YORK para la NYSE)."""
    if instante.tzinfo is None:
        raise ValueError("fecha_de_sesion necesita un instante con zona horaria")
    return instante.astimezone(zona).date()


def marca_de_generacion(formato: str = "%d-%m-%Y %H:%M") -> str:
    """«27-11-2026 10:05 (hora de Santiago)»: la hora en que se genera un documento, con su zona escrita."""
    return f"{ahora_santiago().strftime(formato)} (hora de Santiago)"


@contextmanager
def fijar(instante: datetime):
    """Congela el reloj en `instante` (con zona) mientras dura el bloque. Solo para pruebas."""
    global _instante_fijo
    if instante.tzinfo is None:
        raise ValueError("fijar necesita un instante con zona horaria")
    anterior = _instante_fijo
    _instante_fijo = instante
    try:
        yield
    finally:
        _instante_fijo = anterior
