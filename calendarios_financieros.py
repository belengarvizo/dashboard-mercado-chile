"""Calendarios financieros versionados (H3-D1, alternativa híbrida C).

Cada calendario vive en `calendarios/<id>.json` y registra el mercado o la fuente, el período cubierto, la fuente oficial, la
URL, la fecha de verificación, los feriados, los cierres extraordinarios conocidos, las sesiones reducidas y sus limitaciones.
Este módulo solo LEE esos archivos: no consulta internet ni depende de bibliotecas de calendarios. Las bibliotecas
instaladas localmente sirven únicamente como contraste en las pruebas, no como fuente.

COBERTURA
    Una fecha fuera del período cubierto NUNCA se interpreta como mercado cerrado: su estado es «calendario no verificado».
    El conteo usa entonces lunes a viernes como APROXIMACIÓN (más los feriados que sí se conocen dentro de la cobertura) y
    el resultado queda marcado `verificado=False`, para no sacar conclusiones categóricas sobre atrasos.
    Dentro de la cobertura, una fecha anterior a la verificación es «histórico verificado» y una posterior es «programado»:
    el calendario futuro puede cambiar.

CONTEO DE SESIONES (sesiones_entre): dos medidas distintas
    - ANTIGÜEDAD (`sesiones`): sesiones de `desde` (INCLUIDA, si es sesión) a `hasta` (EXCLUIDA). Es la convención de
      numpy.busday_count, la misma que usaba el dashboard antes de H3-D1, así que el umbral conserva su significado.
    - SESIONES FALTANTES (`faltantes`): sesiones estrictamente entre `desde` y `hasta` (las DOS fechas excluidas), es decir,
      sesiones que ya cerraron sin que llegara un dato nuevo. Si `desde` es una sesión, faltantes = antigüedad − 1.
    `hasta` suele ser hoy o la fecha de corte. La sesión de hoy, que puede seguir abierta, nunca se cuenta en ninguna de las
    dos. Ejemplo: último precio del viernes, consultado el lunes antes del cierre → antigüedad 1 (el viernes), faltantes 0.
    Un dato de hoy da 0 y 0. Si `desde` es posterior a `hasta` (por ejemplo la UF, que se publica por adelantado), la
    antigüedad es negativa y no hay faltantes. Una sesión de horario reducido cuenta como sesión.
    Varios calendarios a la vez (por ejemplo, un diferencial entre una tasa chilena y una de EE. UU.) cuentan solo los días
    que son sesión en TODOS; la cobertura es la de todos.

UMBRAL
    UMBRAL_SESIONES_DE_ATRASO = 5 es el único umbral de «dato atrasado» del dashboard. Se aplica a la ANTIGÜEDAD: atrasado
    si la antigüedad es mayor que 5. Con un dato fechado en una sesión, eso equivale a 5 o más sesiones faltantes (ya
    cerradas sin dato). El valor 5 no cambió respecto de antes de H3-D1.

CALENDARIO NO VERIFICADO
    El conteo aproximado (`verificado=False`) nunca debe presentarse como una afirmación categórica de atraso ni de cierre:
    quien lo muestra dice «unos N» o «posible», con el motivo (`nota`). `es_sesion` devuelve None, nunca «cerrado».
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Iterable

import numpy as np
import pandas as pd

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calendarios")
UMBRAL_SESIONES_DE_ATRASO = 5

TIPO_FERIADOS = "feriados"
TIPO_LUNES_A_VIERNES = "lunes_a_viernes"
TIPO_DIAS_CORRIDOS = "dias_corridos"

ESTADO_HISTORICO = "histórico verificado"
ESTADO_PROGRAMADO = "programado (puede cambiar)"
ESTADO_NO_VERIFICADO = "calendario no verificado"


def _fecha(valor) -> date:
    return pd.Timestamp(valor).date()


def _fechas(dic: dict | None) -> dict[date, str]:
    return {_fecha(k): v for k, v in (dic or {}).items()}


@dataclass(frozen=True)
class Calendario:
    id: str
    nombre: str
    tipo: str
    mercado_o_fuente: str
    fuente_oficial: str
    url: str
    fecha_verificacion: date
    cobertura: tuple[tuple[date, date], ...] | None      # None: calendario estructural, siempre cubierto
    feriados: dict[date, str]
    cierres_extraordinarios: dict[date, str]
    sesiones_reducidas: dict[date, str]
    limitaciones: tuple[str, ...]
    es_recomendacion: bool = False
    supuesto: str | None = None
    instrumentos: tuple[str, ...] = ()

    def sin_sesion(self) -> list[date]:
        """Días hábiles (lunes a viernes) sin sesión según el calendario: feriados y cierres extraordinarios."""
        return sorted(set(self.feriados) | set(self.cierres_extraordinarios))


def _leer(id_calendario: str) -> dict:
    ruta = os.path.join(CARPETA, f"{id_calendario}.json")
    if not os.path.isfile(ruta):
        raise KeyError(f"No existe el calendario «{id_calendario}» en {CARPETA}")
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def cargar(id_calendario: str) -> Calendario:
    """El calendario `calendarios/<id>.json`. Un archivo con «base» hereda cobertura y fechas de ese otro calendario."""
    datos = _leer(id_calendario)
    fechas = _leer(datos["base"]) if datos.get("base") else datos
    cobertura = fechas.get("cobertura", [])
    return Calendario(
        id=datos["id"], nombre=datos["nombre"], tipo=datos.get("tipo", TIPO_FERIADOS),
        mercado_o_fuente=datos.get("mercado_o_fuente", ""), fuente_oficial=datos.get("fuente_oficial", ""),
        url=datos.get("url", ""), fecha_verificacion=_fecha(datos["fecha_verificacion"]),
        cobertura=None if cobertura == "estructural" else tuple((_fecha(a), _fecha(b)) for a, b in cobertura),
        feriados=_fechas(fechas.get("feriados")), cierres_extraordinarios=_fechas(fechas.get("cierres_extraordinarios")),
        sesiones_reducidas=_fechas(fechas.get("sesiones_reducidas")),
        limitaciones=tuple(datos.get("limitaciones", [])) + (tuple(fechas.get("limitaciones", [])) if datos.get("base") else ()),
        es_recomendacion=bool(datos.get("es_recomendacion", False)), supuesto=datos.get("supuesto"),
        instrumentos=tuple(datos.get("instrumentos", [])),
    )


def disponibles() -> list[str]:
    return sorted(n[:-5] for n in os.listdir(CARPETA) if n.endswith(".json"))


def _como_calendario(c) -> Calendario:
    return c if isinstance(c, Calendario) else cargar(c)


def cubre(calendario, desde, hasta=None) -> bool:
    """True si TODAS las fechas de `desde` a `hasta` (ambas incluidas) están dentro de la cobertura verificada."""
    cal = _como_calendario(calendario)
    if cal.cobertura is None:
        return True
    a, b = _fecha(desde), _fecha(hasta if hasta is not None else desde)
    a, b = min(a, b), max(a, b)
    return any(inicio <= a and b <= fin for inicio, fin in cal.cobertura)


def estado_de_fecha(calendario, fecha) -> str:
    """«histórico verificado», «programado (puede cambiar)» o «calendario no verificado»."""
    cal = _como_calendario(calendario)
    if not cubre(cal, fecha):
        return ESTADO_NO_VERIFICADO
    if cal.cobertura is None:
        return ESTADO_HISTORICO
    return ESTADO_HISTORICO if _fecha(fecha) < cal.fecha_verificacion else ESTADO_PROGRAMADO


def es_sesion(calendario, fecha) -> bool | None:
    """True/False según el calendario; None si la fecha está fuera de la cobertura (nunca se supone cerrado)."""
    cal = _como_calendario(calendario)
    d = _fecha(fecha)
    if not cubre(cal, d):
        return None
    if cal.tipo == TIPO_DIAS_CORRIDOS:
        return True
    if d.weekday() >= 5:
        return False
    return cal.tipo == TIPO_LUNES_A_VIERNES or d not in set(cal.sin_sesion())


@dataclass(frozen=True)
class ConteoSesiones:
    sesiones: int            # antigüedad: `desde` incluida, `hasta` excluida
    verificado: bool
    calendarios: tuple[str, ...]
    nota: str = ""
    faltantes: int = 0       # sesiones ya cerradas sin dato: las dos fechas excluidas

    @property
    def aproximado(self) -> bool:
        return not self.verificado

    def atrasado(self, umbral: int = UMBRAL_SESIONES_DE_ATRASO) -> bool:
        return self.sesiones > umbral


def _lista(calendarios) -> list[Calendario]:
    if calendarios is None:
        return []
    if isinstance(calendarios, (str, Calendario)):
        return [_como_calendario(calendarios)]
    return [_como_calendario(c) for c in calendarios]


def sesiones_entre(calendarios, desde, hasta) -> ConteoSesiones | None:
    """Sesiones de `desde` (incluida si es sesión) a `hasta` (excluida). Ver la convención en el encabezado del módulo.

    `calendarios`: un id, un Calendario o varios (cuenta los días que son sesión en todos). None: sin calendario asignado,
    que se cuenta como aproximación de lunes a viernes. Devuelve None si falta alguna de las dos fechas."""
    if desde is None or hasta is None:
        return None
    a, b = _fecha(desde), _fecha(hasta)
    cals = _lista(calendarios)
    ids = tuple(c.id for c in cals)
    con_sesiones = [c for c in cals if c.tipo != TIPO_DIAS_CORRIDOS]

    def faltantes(n: int, desde_es_sesion: bool) -> int:
        return max(0, n - 1) if desde_es_sesion else max(0, n)

    if cals and not con_sesiones:                                            # solo días corridos
        dias = (b - a).days
        return ConteoSesiones(dias, True, ids, faltantes=faltantes(dias, True))
    if not cals:
        n = int(np.busday_count(a, b))
        return ConteoSesiones(n, False, ids, "aproximación de lunes a viernes: la serie no tiene un calendario asignado",
                              faltantes=faltantes(n, bool(np.is_busday(a))))
    # Días necesarios para el conteo: de min(a, b) al día anterior a max(a, b) (el extremo excluido no se cuenta).
    inicio, fin = min(a, b), max(a, b)
    ultimo_necesario = fin - pd.Timedelta(days=1) if fin > inicio else fin
    ultimo_necesario = _fecha(ultimo_necesario)
    verificado = all(cubre(c, inicio, ultimo_necesario) for c in con_sesiones)
    # Feriados conocidos (solo los que están dentro de la cobertura de su propio calendario).
    sin_sesion = sorted({d for c in con_sesiones for d in c.sin_sesion() if cubre(c, d)})
    n = int(np.busday_count(a, b, holidays=sin_sesion))
    n_faltantes = faltantes(n, bool(np.is_busday(a, holidays=sin_sesion)))
    if verificado:
        return ConteoSesiones(n, True, ids, faltantes=n_faltantes)
    faltan = ", ".join(c.nombre for c in con_sesiones if not cubre(c, inicio, ultimo_necesario))
    return ConteoSesiones(n, False, ids, f"aproximación de lunes a viernes: calendario no verificado para ese tramo ({faltan})",
                          faltantes=n_faltantes)


def calendario_de_instrumento(ticker: str) -> str:
    """Calendario de un ticker de Yahoo Finance. No supone que todos los ETF cotizan en NYSE ni que todos los futuros
    comparten calendario: sin el dato de la bolsa de listado, el instrumento queda en un calendario no verificado."""
    if ticker.endswith(".SN"):
        return "bolsa_santiago"
    if ticker.endswith("=X"):
        return "fx_24_5"
    for id_calendario in ("ice_futures_us_blandos", "cme_group", "ice_futures_us_divisas"):
        if ticker in cargar(id_calendario).instrumentos:
            return id_calendario
    return "eeuu_bolsa_no_registrada"


def texto_de_conteo(conteo: ConteoSesiones, unidad: str = "días hábiles") -> str:
    """«7 días hábiles», o «unos 7 días hábiles (aproximación: …)» si el calendario no está verificado para ese tramo."""
    if conteo.verificado:
        return f"{conteo.sesiones} {unidad}"
    return f"unos {conteo.sesiones} {unidad} ({conteo.nota})"


def resumen(ids: Iterable[str] | None = None) -> pd.DataFrame:
    """Tabla de trazabilidad: un calendario por fila con su fuente, cobertura y limitaciones."""
    filas = []
    for id_calendario in ids or disponibles():
        c = cargar(id_calendario)
        filas.append({
            "id": c.id, "calendario": c.nombre, "tipo": c.tipo, "fuente": c.fuente_oficial, "url": c.url,
            "verificado el": c.fecha_verificacion,
            "cobertura": "estructural" if c.cobertura is None else ("; ".join(f"{a} a {b}" for a, b in c.cobertura) or "ninguna"),
            "feriados": len(c.feriados), "cierres extraordinarios": len(c.cierres_extraordinarios),
            "sesiones reducidas": len(c.sesiones_reducidas), "recomendación": c.es_recomendacion,
            "limitaciones": " | ".join(c.limitaciones),
        })
    return pd.DataFrame(filas)
