"""Estados de frescura de los datos según frecuencia, calendario y horario de publicación (H3-D3).

CINCO ESTADOS
    - VIGENTE: llegó el último dato que se podía esperar a la fecha de referencia.
    - POSIBLEMENTE ATRASADO: falta un dato que ya se esperaba, pero el atraso es corto o el calendario/horario de
      publicación no está verificado, así que no se afirma.
    - ATRASADO: falta un dato con calendario VERIFICADO y la antigüedad supera el umbral único del dashboard (más de 5
      sesiones, calendarios_financieros.UMBRAL_SESIONES_DE_ATRASO): la misma regla que usan las tablas de cada sección.
    - NO DISPONIBLE: no hay datos de la serie.
    - COBERTURA DESCONOCIDA: el calendario de la serie no está verificado para ese tramo y, en la aproximación de lunes a
      viernes, no falta nada: no se puede certificar que esté vigente ni se dice que esté atrasada.

REGLAS POR FRECUENCIA
    - DIARIA: sesiones del calendario de la serie entre el último dato y la referencia (calendarios_financieros). Se descuenta
      el REZAGO ESPERADO en sesiones: el cron guarda una vez al día (14:00 UTC, antes del cierre de EE. UU.), así que el
      cierre de hoy llega mañana (1 sesión); las series publicadas al día hábil siguiente (FRED, BCCh) pueden llegar con 2.
      Faltantes ≤ rezago → vigente. Rezagos marcados como supuestos donde el horario de publicación no se verificó.
    - SEMANAL: días corridos desde el último dato, con el período (7 días) más el plazo de publicación y una tolerancia.
      Los calendarios semanales de publicación no se verificaron: nunca «atrasado», a lo más «posiblemente atrasado».
    - MENSUAL y TRIMESTRAL: el dato se fecha con el período de referencia (1.er día del mes; el desempleo chileno es un
      trimestre móvil fechado con su último mes y publicado cada mes). Se espera el período SIGUIENTE en su fecha OFICIAL
      de publicación si está cargada (INE, BLS; ver PERFILES_DE_SERIE) o, si no, al cierre del período más un plazo
      SUPUESTO; más una tolerancia de 7 días para el proveedor y la carga. Antes de eso está vigente aunque tenga meses
      de antigüedad: nunca se marca atrasada por no tener datos diarios. Como la disponibilidad en FRED o en la API del
      BCCh no está verificada, nunca «atrasado», a lo más «posiblemente atrasado».
    - DATOS POSTERIORES A LA REFERENCIA Y NaN: se ignoran (y se dice cuántos se ignoraron).
    - FECHA DE CORTE: `evaluar(..., referencia=corte)` evalúa un informe histórico contra su corte, no contra hoy.

CUATRO FECHAS QUE NO SE CONFUNDEN
    - FECHA ECONÓMICA: la del dato (día, semana, mes o trimestre al que se refiere). Es la única que guarda la base.
    - PUBLICACIÓN PREVISTA del organismo original (BCCh, INE, BLS, Fed): oficial donde se verificó, si no supuesta.
    - DISPONIBILIDAD EN EL PROVEEDOR (FRED, API del BCCh, Yahoo Finance): no verificada; se cubre con el rezago o la
      tolerancia, declarados como aproximación.
    - ACTUALIZACIÓN EFECTIVA DEL DASHBOARD: la base no registra cuándo se cargó cada dato; la ejecución programada del cron
      no prueba que el dato haya llegado. Si la carga falla, el dato envejece y el estado lo muestra.
    Si el estado depende de un plazo de publicación supuesto, `EstadoFrescura.estimado` es True y el texto lo dice.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

import calendarios_financieros as calf
import reloj

VIGENTE = "vigente"
POSIBLEMENTE_ATRASADO = "posiblemente atrasado"
ATRASADO = "atrasado"
NO_DISPONIBLE = "no disponible"
COBERTURA_DESCONOCIDA = "cobertura desconocida"
ESTADOS = (VIGENTE, POSIBLEMENTE_ATRASADO, ATRASADO, NO_DISPONIBLE, COBERTURA_DESCONOCIDA)

TOLERANCIA_PUBLICACION_DIAS = 7       # margen para la disponibilidad en el proveedor y la carga diaria (no verificado)


@dataclass(frozen=True)
class Perfil:
    frecuencia: str                       # diaria | semanal | mensual | trimestral
    calendario: str | tuple | None = None  # diaria: calendario(s) de calendarios_financieros
    rezago_sesiones: int = 1              # diaria: faltantes esperables por publicación + proveedor + carga diaria
    plazo_publicacion_dias: int = 0       # semanal/mensual/trimestral: días SUPUESTOS tras el cierre del período
    publicacion_verificada: bool = False  # diaria: el horario de publicación del organismo original está verificado
    nota: str = ""
    proveedor: str = ""                   # de dónde la toma el dashboard (FRED, API del BCCh, Yahoo Finance)
    publicaciones: tuple = ()             # mensual/trimestral: ((período «AAAA-MM», fecha oficial «AAAA-MM-DD»), ...)
    fuente_publicacion: str = ""          # de dónde salen las fechas oficiales de `publicaciones`


@dataclass(frozen=True)
class EstadoFrescura:
    estado: str
    texto: str
    ultima: date | None = None
    referencia: date | None = None
    estimado: bool = True                 # True si el estado depende de un plazo o rezago de publicación supuesto


def perfil_de_instrumento(ticker: str) -> Perfil:
    """Precios de Yahoo: diarios, con el calendario de su bolsa y 1 sesión de rezago por la carga diaria (cron)."""
    return Perfil("diaria", calf.calendario_de_instrumento(ticker), 1, publicacion_verificada=True, proveedor="Yahoo Finance",
                  nota="El precio de cierre existe al cierre de la sesión; la carga diaria corre a las 14:00 UTC, antes del "
                       "cierre de EE. UU., así que el cierre de hoy llega mañana.")


_BCCH = "supuesto: el BCCh publica la serie al día hábil siguiente (su calendario estadístico no pudo leerse)"

# Fechas OFICIALES de publicación, consultadas el 27-11-2026. Fuera de estas fechas se usa el plazo supuesto.
# INE, Agenda Estadística 2026 (https://www.ine.gob.cl/inicio/agendaestadistica): IPC de noviembre 2026 el 07-12-2026
# a las 08:00; «Empleo Nacional, período septiembre – noviembre 2026» el 30-12-2026 a las 09:00. El BCCh fecha el
# trimestre móvil con su ÚLTIMO mes (sep-nov → 01-11-2026): el 11-11-2026 la API devolvía jul-sep como 01-09-2026.
_INE = "INE, Agenda Estadística 2026, consultada el 27-11-2026"
_PUBLICACIONES_IPC = (("2026-11", "2026-12-07"),)
_PUBLICACIONES_DESOCUPACION = (("2026-11", "2026-12-30"),)
# BLS, Employment Situation (https://www.bls.gov/schedule/news_release/empsit.htm), 08:30 a.m. (la página no indica la zona).
_BLS = "BLS, calendario de Employment Situation, consultado el 27-11-2026"
_PUBLICACIONES_UNRATE = (
    ("2026-10", "2026-11-06"), ("2026-11", "2026-12-04"), ("2026-12", "2027-01-08"), ("2027-01", "2027-02-05"),
    ("2027-02", "2027-03-05"), ("2027-03", "2027-04-02"), ("2027-04", "2027-05-07"), ("2027-05", "2027-06-04"),
    ("2027-06", "2027-07-02"), ("2027-07", "2027-08-06"), ("2027-08", "2027-09-03"), ("2027-09", "2027-10-08"),
    ("2027-10", "2027-11-05"), ("2027-11", "2027-12-03"),
)

# Series de la base (series_macro) que muestran los panoramas.
PERFILES_DE_SERIE = {
    "Tipo de cambio observado": Perfil("diaria", "bcch_series", 2, nota=_BCCH, proveedor="API del BCCh"),
    # La TPM se publica todos los días hábiles aunque no cambie: la frescura mira la fecha, no si el valor se movió.
    "Tasa de política monetaria (TPM)": Perfil("diaria", "bcch_series", 2, nota=_BCCH + "; la TPM tiene dato cada día "
                                               "hábil aunque su valor no cambie", proveedor="API del BCCh"),
    "Precio del cobre (USD/lb)": Perfil("diaria", "bcch_series", 2, nota=_BCCH, proveedor="API del BCCh"),
    "Bono BCCh en pesos (BCP) a 10 años - tasa mercado secundario":
        Perfil("diaria", "bcch_series", 2, nota=_BCCH, proveedor="API del BCCh"),
    "Bono del Tesoro de EEUU a 10 años (Treasury Constant Maturity, H.15)":
        Perfil("diaria", "fed_junta", 2, proveedor="FRED",
               nota="La Junta de la Fed publica el H.15 cada día hábil salvo feriados (verificado); no informa la hora ni el "
                    "rezago del dato: se supone el día hábil siguiente"),
    "Tasa de política monetaria de EEUU (Effective Federal Funds Rate)":
        Perfil("diaria", "fed_nueva_york", 2, publicacion_verificada=True, proveedor="FRED",
               nota="La Fed de Nueva York publica la EFFR del día hábil anterior a las 9:00 a.m. ET aprox. (verificado; tras "
                    "un feriado, el día hábil siguiente); el rezago de FRED y de la carga diaria no está verificado"),
    "IPC variación 12 meses (inflación anual, empalme base 2023=100)":
        Perfil("mensual", plazo_publicacion_dias=8, proveedor="API del BCCh", publicaciones=_PUBLICACIONES_IPC,
               fuente_publicacion=_INE, nota="Fuera de las fechas oficiales cargadas, supuesto: el INE publica el IPC cerca "
                                             "del día 8 del mes siguiente"),
    "IMACEC variación 12 meses":
        Perfil("mensual", plazo_publicacion_dias=32, proveedor="API del BCCh",
               nota="supuesto: el BCCh publica el Imacec cerca del 1.er día hábil dos meses después (su calendario "
                    "estadístico no pudo leerse)"),
    "Tasa de desocupación nacional (INE, desestacionalizada)":
        Perfil("mensual", plazo_publicacion_dias=31, proveedor="API del BCCh", publicaciones=_PUBLICACIONES_DESOCUPACION,
               fuente_publicacion=_INE + " (la Agenda publica la serie original; se supone la misma fecha para la "
                                         "desestacionalizada)",
               nota="Trimestre móvil fechado con su último mes, publicado mensualmente; fuera de las fechas oficiales "
                    "cargadas, supuesto: a fines del mes siguiente"),
    "Tasa de desocupación nacional (INE, sin ajuste estacional)":
        Perfil("mensual", plazo_publicacion_dias=31, proveedor="API del BCCh", publicaciones=_PUBLICACIONES_DESOCUPACION,
               fuente_publicacion=_INE, nota="Trimestre móvil fechado con su último mes, publicado mensualmente; fuera de "
                                             "las fechas oficiales cargadas, supuesto: a fines del mes siguiente"),
    "Tasa de desempleo de EEUU (UNRATE)":
        Perfil("mensual", plazo_publicacion_dias=7, proveedor="FRED", publicaciones=_PUBLICACIONES_UNRATE,
               fuente_publicacion=_BLS, nota="Fuera de las fechas oficiales cargadas, supuesto: primer viernes del mes "
                                             "siguiente"),
    "Solicitudes iniciales de seguro de desempleo de EEUU (ICSA)":
        Perfil("semanal", plazo_publicacion_dias=5, proveedor="FRED",
               nota="supuesto: publicación los jueves por la semana terminada el sábado"),
    "Índice de condiciones financieras nacionales de Chicago Fed (NFCI)":
        Perfil("semanal", plazo_publicacion_dias=5, proveedor="FRED",
               nota="supuesto: publicación los miércoles por la semana terminada el viernes"),
}

_CARGA = ("La fecha es la económica del último dato guardado; el dashboard no registra cuándo se cargó, así que la carga "
          "diaria programada no prueba que haya llegado.")


def _texto_fecha(d: date) -> str:
    return pd.Timestamp(d).strftime("%d-%m-%Y")


def evaluar(serie_o_ultima, perfil: Perfil, referencia=None) -> EstadoFrescura:
    """Estado de frescura de una serie (o de la fecha de su último dato) a la fecha de `referencia` (por defecto, hoy en
    Santiago; un informe histórico pasa su fecha de corte). Se ignoran los NaN y los datos con fecha posterior a la
    referencia, así que el resultado a una fecha de corte no depende del reloj ni de datos cargados después."""
    ref = pd.Timestamp(referencia).date() if referencia is not None else reloj.hoy_santiago()
    if isinstance(serie_o_ultima, pd.Series):
        fechas = [pd.Timestamp(i).date() for i in serie_o_ultima.dropna().index]
    else:
        fechas = [] if serie_o_ultima is None else [pd.Timestamp(serie_o_ultima).date()]
    posteriores = sum(1 for d in fechas if d > ref)
    fechas = [d for d in fechas if d <= ref]
    if not fechas:
        texto = "No disponible: la serie no tiene datos"
        texto += f" hasta el {_texto_fecha(ref)}." if posteriores else "."
        return EstadoFrescura(NO_DISPONIBLE, texto, None, ref, estimado=False)
    ultima = max(fechas)
    if perfil.frecuencia == "diaria":
        e = _diaria(ultima, ref, perfil)
    elif perfil.frecuencia == "semanal":
        e = _periodica(ultima, ref, perfil, pd.Timedelta(days=7), "semana")
    elif perfil.frecuencia in ("mensual", "trimestral"):
        e = _por_periodo(ultima, ref, perfil)
    else:
        raise ValueError(f"frecuencia desconocida: {perfil.frecuencia}")
    if posteriores:
        e = EstadoFrescura(e.estado, f"{e.texto} Se ignoraron {posteriores} datos con fecha posterior al "
                                     f"{_texto_fecha(ref)}.", e.ultima, e.referencia, e.estimado)
    return e


def _sufijo_estimado(estimado: bool) -> str:
    return " Estado estimado: el plazo de publicación es un supuesto." if estimado else ""


def _diaria(ultima: date, ref: date, perfil: Perfil) -> EstadoFrescura:
    conteo = calf.sesiones_entre(perfil.calendario, ultima, ref)
    exceso = conteo.faltantes - perfil.rezago_sesiones
    estimado = not perfil.publicacion_verificada
    base = (f"Último dato: {_texto_fecha(ultima)}. Se esperan hasta {perfil.rezago_sesiones} sesiones sin dato nuevo "
            f"(publicación, {perfil.proveedor or 'proveedor'} y carga diaria). {_CARGA}")
    if not conteo.verificado:
        if exceso <= 0:
            return EstadoFrescura(COBERTURA_DESCONOCIDA, "Calendario no verificado: al día en la aproximación de lunes a "
                                  f"viernes, sin certificar. {base}", ultima, ref, True)
        return EstadoFrescura(POSIBLEMENTE_ATRASADO, f"Posiblemente atrasado: unas {conteo.faltantes} sesiones sin dato "
                              f"nuevo (aproximación; calendario no verificado). {base}", ultima, ref, True)
    if exceso <= 0:
        return EstadoFrescura(VIGENTE, f"Vigente. {base}{_sufijo_estimado(estimado)}", ultima, ref, estimado)
    if conteo.atrasado():
        return EstadoFrescura(ATRASADO, f"Atrasado: {conteo.faltantes} sesiones sin dato nuevo (más de "
                              f"{calf.UMBRAL_SESIONES_DE_ATRASO} de antigüedad, la regla de las tablas de cada sección). "
                              f"{base}", ultima, ref, False)
    return EstadoFrescura(POSIBLEMENTE_ATRASADO, f"Posiblemente atrasado: {conteo.faltantes} sesiones sin dato nuevo. "
                          f"{base}{_sufijo_estimado(estimado)}", ultima, ref, estimado)


def _periodica(ultima: date, ref: date, perfil: Perfil, periodo: pd.Timedelta, nombre: str) -> EstadoFrescura:
    esperado = pd.Timestamp(ultima) + periodo + pd.Timedelta(days=perfil.plazo_publicacion_dias)
    limite = esperado + pd.Timedelta(days=TOLERANCIA_PUBLICACION_DIAS)
    detalle = (f"Último dato: {nombre} del {_texto_fecha(ultima)}. Publicación supuesta del siguiente hacia el "
               f"{_texto_fecha(esperado.date())}, más {TOLERANCIA_PUBLICACION_DIAS} días para {perfil.proveedor or 'el proveedor'} "
               f"y la carga diaria (no verificado). {_CARGA}{_sufijo_estimado(True)}")
    if pd.Timestamp(ref) <= limite:
        return EstadoFrescura(VIGENTE, f"Vigente. {detalle}", ultima, ref, True)
    return EstadoFrescura(POSIBLEMENTE_ATRASADO, f"Posiblemente atrasado. {detalle}", ultima, ref, True)


def _por_periodo(ultima: date, ref: date, perfil: Perfil) -> EstadoFrescura:
    frecuencia = "M" if perfil.frecuencia == "mensual" else "Q"
    actual = pd.Timestamp(ultima).to_period(frecuencia)
    siguiente = actual + 1
    oficial = dict(perfil.publicaciones).get(siguiente.strftime("%Y-%m")) if frecuencia == "M" else None
    if oficial:
        esperado = pd.Timestamp(oficial)
        publicacion = f"publicación oficial prevista el {_texto_fecha(esperado.date())} ({perfil.fuente_publicacion})"
    else:
        esperado = siguiente.end_time.normalize() + pd.Timedelta(days=perfil.plazo_publicacion_dias)
        publicacion = f"publicación supuesta hacia el {_texto_fecha(esperado.date())}"
    estimado = not oficial
    limite = esperado + pd.Timedelta(days=TOLERANCIA_PUBLICACION_DIAS)
    detalle = (f"Último dato: período {actual.strftime('%m-%Y')}. Dato de {siguiente.strftime('%m-%Y')}: {publicacion}; "
               f"más {TOLERANCIA_PUBLICACION_DIAS} días para {perfil.proveedor or 'el proveedor'} y la carga diaria (no "
               f"verificado). {_CARGA}{_sufijo_estimado(estimado)}")
    if pd.Timestamp(ref) <= limite:
        return EstadoFrescura(VIGENTE, f"Vigente. {detalle}", ultima, ref, estimado)
    # Nunca «atrasado»: la disponibilidad en el proveedor no está verificada.
    return EstadoFrescura(POSIBLEMENTE_ATRASADO, f"Posiblemente atrasado. {detalle}", ultima, ref, estimado)
