"""
Calendario de eventos económicos relevantes para 2026: RPM del Banco Central de
Chile, FOMC de la Reserva Federal, publicación de IPC (INE) e IMACEC (BCCh), y
reuniones ministeriales de la OPEP+. Vive fuera de app/dashboard.py (igual que
market_data.py) para que sea reutilizable sin depender de un contexto de
Streamlit.

Fuentes y fecha de verificación: ver CALENDARIO_VERIFICADO_AL más abajo. Cada
fecha fue verificada contra la fuente oficial correspondiente (bcentral.cl,
federalreserve.gov, ine.gob.cl) salvo donde se indica explícitamente que es
una fecha estimada (ver notas en EVENTOS_2026).
"""

from dataclasses import dataclass
from datetime import date, timedelta

CALENDARIO_VERIFICADO_AL = date(2026, 8, 18)

# Próximo año en que corresponde republicar cada calendario (los bancos
# centrales publican su calendario del año siguiente con meses de
# anticipación: BCCh en septiembre, Fed en diciembre).
NOTA_VIGENCIA = (
    f"Calendario verificado al {CALENDARIO_VERIFICADO_AL.strftime('%d-%m-%Y')}. "
    "RPM 2027 se publica en septiembre 2026, FOMC 2027 en diciembre 2026 "
    "— actualizar entonces."
)

# Indicador visual (color + etiqueta corta) por organismo/tipo de evento.
# Colores tomados de PALETA_CATEGORICA de app/dashboard.py, en el mismo orden
# de asignación fija que usa el resto del dashboard.
INDICADOR_POR_TIPO = {
    "RPM": {"color": "#2a78d6", "etiqueta": "RPM", "organismo": "Banco Central de Chile"},
    "FOMC": {"color": "#eb6834", "etiqueta": "FOMC", "organismo": "Reserva Federal (EEUU)"},
    "IPC": {"color": "#1baf7a", "etiqueta": "IPC", "organismo": "INE Chile"},
    "IMACEC": {"color": "#eda100", "etiqueta": "IMACEC", "organismo": "Banco Central de Chile"},
    "OPEP+": {"color": "#4a3aa7", "etiqueta": "OPEP+", "organismo": "OPEC+"},
}


@dataclass(frozen=True)
class EventoCalendario:
    fecha_inicio: date
    fecha_fin: date  # igual a fecha_inicio si el evento dura un solo día
    tipo: str  # clave de INDICADOR_POR_TIPO
    descripcion: str
    confirmado: bool  # False = estimado (ver nota), no publicado explícitamente por la fuente


# --- RPM (Banco Central de Chile) 2026 ---------------------------------
# Fuente: comunicado oficial "Banco Central publica calendario de Reuniones
# de Política Monetaria y Financiera... 2026" (bcentral.cl), cross-verificado
# contra el calendario económico de tradingeconomics.com (fechas de anuncio
# de septiembre/octubre/diciembre coinciden). Las reuniones de RPM se
# desarrollan en 1 o 2 días; la decisión se anuncia el último día.
_RPM_2026 = [
    (date(2026, 1, 26), date(2026, 1, 27)),
    (date(2026, 3, 24), date(2026, 3, 24)),
    (date(2026, 4, 27), date(2026, 4, 28)),
    (date(2026, 6, 16), date(2026, 6, 16)),
    (date(2026, 7, 27), date(2026, 7, 28)),
    (date(2026, 9, 8), date(2026, 9, 8)),
    (date(2026, 10, 26), date(2026, 10, 27)),
    (date(2026, 12, 15), date(2026, 12, 15)),
]

# --- FOMC (Reserva Federal de EEUU) 2026 --------------------------------
# Fuente: federalreserve.gov/monetarypolicy/fomccalendars.htm (verificado
# con fetch directo a la fuente oficial).
_FOMC_2026 = [
    (date(2026, 1, 27), date(2026, 1, 28)),
    (date(2026, 3, 17), date(2026, 3, 18)),
    (date(2026, 4, 28), date(2026, 4, 29)),
    (date(2026, 6, 16), date(2026, 6, 17)),
    (date(2026, 7, 28), date(2026, 7, 29)),
    (date(2026, 9, 15), date(2026, 9, 16)),
    (date(2026, 10, 27), date(2026, 10, 28)),
    (date(2026, 12, 8), date(2026, 12, 9)),
]

# --- IPC (INE Chile) 2026 -----------------------------------------------
# Fuente: "Calendario 2026 — Indicadores de Coyuntura INE" (ine.gob.cl),
# actualización del 10 de abril de 2026, fila "Índice de Precios al
# Consumidor (IPC)". Cada fecha es el día de publicación del IPC del mes
# indicado entre paréntesis.
_IPC_2026 = [
    (date(2026, 1, 8), "dic-25"),
    (date(2026, 2, 6), "ene-26"),
    (date(2026, 3, 6), "feb-26"),
    (date(2026, 4, 8), "mar-26"),
    (date(2026, 5, 8), "abr-26"),
    (date(2026, 6, 8), "may-26"),
    (date(2026, 7, 8), "jun-26"),
    (date(2026, 8, 7), "jul-26"),
    (date(2026, 9, 8), "ago-26"),
    (date(2026, 10, 8), "sept-26"),
    (date(2026, 11, 6), "oct-26"),
    (date(2026, 12, 7), "nov-26"),
]

# --- IMACEC (Banco Central de Chile) 2026 -------------------------------
# Metodología oficial: primer día hábil del mes, con rezago de ~31 días
# respecto al mes medido (ej. Imacec de julio se publica el primer día
# hábil de septiembre). El 1 de septiembre de 2026 está confirmado
# explícitamente (fxstreet.com, "Next Release Sep 1"); las fechas de
# octubre, noviembre y diciembre se calcularon aplicando la misma regla
# (primer día hábil del mes) y NO están confirmadas de forma explícita por
# el Banco Central para esos meses — quedan marcadas con confirmado=False.
_IMACEC_2026 = [
    (date(2026, 9, 1), "jul-26", True),
    (date(2026, 10, 1), "ago-26", False),
    (date(2026, 11, 2), "sept-26", False),
    (date(2026, 12, 1), "oct-26", False),
]

# --- OPEP+ (reuniones ministeriales) 2026 -------------------------------
# A diferencia de los bancos centrales, la OPEP+ no publica un calendario
# anual fijo de reuniones: desde 2024 el grupo de países con recortes
# voluntarios se reúne aproximadamente cada mes, pero cada fecha se
# confirma solo semanas antes. Fuente: tradingeconomics.com/opec/calendar
# (verificado con fetch directo el 18-08-2026), única reunión ministerial
# confirmada a esa fecha para el resto de 2026.
_OPEP_2026 = [
    (date(2026, 9, 6), True),
]


def _construir_eventos() -> list[EventoCalendario]:
    eventos = []
    for inicio, fin in _RPM_2026:
        eventos.append(EventoCalendario(inicio, fin, "RPM", "Reunión de Política Monetaria", True))
    for inicio, fin in _FOMC_2026:
        eventos.append(EventoCalendario(inicio, fin, "FOMC", "Reunión del FOMC (decisión de tasas Fed)", True))
    for fecha, periodo in _IPC_2026:
        eventos.append(EventoCalendario(fecha, fecha, "IPC", f"Publicación IPC ({periodo})", True))
    for fecha, periodo, confirmado in _IMACEC_2026:
        eventos.append(EventoCalendario(fecha, fecha, "IMACEC", f"Publicación IMACEC ({periodo})", confirmado))
    for fecha, confirmado in _OPEP_2026:
        eventos.append(EventoCalendario(fecha, fecha, "OPEP+", "Reunión ministerial OPEP+", confirmado))
    return sorted(eventos, key=lambda e: e.fecha_inicio)


EVENTOS_2026 = _construir_eventos()


def proximos_eventos(hoy: date, dias: int = 7) -> list[EventoCalendario]:
    """Eventos cuyo rango [fecha_inicio, fecha_fin] se solapa con los
    próximos `dias` días desde `hoy` (inclusive), ordenados cronológicamente."""
    limite = hoy + timedelta(days=dias)
    return [e for e in EVENTOS_2026 if e.fecha_inicio <= limite and e.fecha_fin >= hoy]
