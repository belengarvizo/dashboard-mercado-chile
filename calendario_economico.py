"""
Calendario de eventos económicos relevantes: RPM del Banco Central de Chile,
IPoM (Informe de Política Monetaria) del BCCh, FOMC de la Reserva Federal,
publicación de IPC (INE) e IMACEC (BCCh), y reuniones ministeriales de la
OPEP+. Vive fuera de app/dashboard.py (igual que market_data.py) para que sea
reutilizable sin depender de un contexto de Streamlit.

Fuentes y fecha de verificación: ver CALENDARIO_VERIFICADO_AL más abajo. Cada
fecha fue verificada contra la fuente oficial correspondiente (bcentral.cl,
federalreserve.gov, ine.gob.cl) salvo donde se indica explícitamente que es
una fecha derivada por regla y no publicada (confirmado=False).

El IPoM NO se hardcodea: se deriva de las fechas de RPM. El Banco Central
publica el IPoM la mañana siguiente a cada RPM "ampliada", y esas son una de
cada dos reuniones del año (la 2ª, 4ª, 6ª y 8ª). Derivarlo de la lista de RPM
—en vez de listar las 4 fechas aparte— evita que se desincronice al cargar el
calendario de un año nuevo. tests/test_calendario_ipom.py contrasta lo
derivado contra las fechas de IPoM que el BCCh publica, para que un año que
rompa el patrón se note en vez de pasar en silencio.
"""

from dataclasses import dataclass
from datetime import date, timedelta

CALENDARIO_VERIFICADO_AL = date(2026, 10, 1)

# Qué falta y cuándo se puede cargar. Los organismos publican con meses de
# anticipación, pero no todos a la vez.

# Indicador visual (color + etiqueta corta) por organismo/tipo de evento.
# Colores tomados de PALETA_CATEGORICA de app/dashboard.py, en el mismo orden
# de asignación fija que usa el resto del dashboard.
INDICADOR_POR_TIPO = {
    "RPM": {"color": "#2a78d6", "etiqueta": "RPM", "organismo": "Banco Central de Chile"},
    "IPoM": {"color": "#e87ba4", "etiqueta": "IPoM", "organismo": "Banco Central de Chile"},
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
    confirmado: bool  # False = derivado por regla, no publicado por la fuente
    hora: str = ""  # hora de Chile "HH:MM" si es un evento con hora conocida; "" si no


# --- RPM (Banco Central de Chile) ---------------------------------------
# Fuente: bcentral.cl, "Monetary and Financial Policy calendar"
# (/en/news-and-publications/press/monetary-and-financial-policy-calendar),
# secciones "Monetary Policy Calendar 2026" y "Monetary Policy Calendar 2027".
# El calendario 2027 se publicó el 30-09-2026 y se leyó de la fuente el
# 01-10-2026. Las reuniones duran 1 o 2 días; la decisión se anuncia el
# último día.
_RPM_POR_ANIO = {
    2026: [
        (date(2026, 1, 26), date(2026, 1, 27)),
        (date(2026, 3, 24), date(2026, 3, 24)),
        (date(2026, 4, 27), date(2026, 4, 28)),
        (date(2026, 6, 16), date(2026, 6, 16)),
        (date(2026, 7, 27), date(2026, 7, 28)),
        (date(2026, 9, 8), date(2026, 9, 8)),
        (date(2026, 10, 26), date(2026, 10, 27)),
        (date(2026, 12, 15), date(2026, 12, 15)),
    ],
    2027: [
        (date(2027, 1, 25), date(2027, 1, 26)),
        (date(2027, 3, 30), date(2027, 3, 30)),
        (date(2027, 4, 26), date(2027, 4, 27)),
        (date(2027, 6, 15), date(2027, 6, 15)),
        (date(2027, 7, 26), date(2027, 7, 27)),
        (date(2027, 8, 31), date(2027, 8, 31)),
        (date(2027, 10, 25), date(2027, 10, 26)),
        (date(2027, 12, 14), date(2027, 12, 14)),
    ],
}

# --- IPoM (Banco Central de Chile) -------------------------------------
# Se deriva de _RPM_POR_ANIO: la mañana siguiente (día calendario) a cada RPM
# "ampliada", a las 09:00 hora de Chile.
#
# CUIDADO CON LA REGLA. Antes se identificaba la RPM ampliada por su MES
# ({3, 6, 9, 12}), lo cual funcionaba para 2026 pero se rompe en 2027: ese año
# la reunión que precede al IPoM de septiembre es el 31 de AGOSTO, así que la
# regla por mes habría perdido ese IPoM y no habría encontrado ninguno en
# septiembre. La regla real es posicional: el IPoM sigue a una de cada dos
# reuniones del año (la 2ª, 4ª, 6ª y 8ª). Verificado contra las fechas de
# IPoM que el propio BCCh publica:
#   2026 -> 25-03, 17-06, 09-09, 16-12   (derivadas: idénticas)
#   2027 -> 31-03, 16-06, 01-09, 15-12   (derivadas: idénticas)
# tests/test_calendario_ipom.py fija ese contraste.
_PASO_RPM_AMPLIADA = 2
_HORA_IPOM = "09:00"

# El comunicado de la RPM se publica "a partir de las 18:00 horas" (nota de
# prensa del Banco Central). El IPC del INE se publica a las 08:00 horas. El
# Imacec no tiene hora publicada de forma oficial, así que queda sin hora.
_HORA_RPM = "18:00"
_HORA_IPC = "08:00"

# --- FOMC (Reserva Federal de EEUU) -------------------------------------
# Fuente: federalreserve.gov/monetarypolicy/fomccalendars.htm, leído de la
# fuente el 01-10-2026 (la página declara "Last Update: September 16, 2026").
# La Fed advierte que "each meeting date is tentative until confirmed at the
# meeting immediately preceding it", pero son las fechas oficiales publicadas.
_FOMC_POR_ANIO = {
    2026: [
        (date(2026, 1, 27), date(2026, 1, 28)),
        (date(2026, 3, 17), date(2026, 3, 18)),
        (date(2026, 4, 28), date(2026, 4, 29)),
        (date(2026, 6, 16), date(2026, 6, 17)),
        (date(2026, 7, 28), date(2026, 7, 29)),
        (date(2026, 9, 15), date(2026, 9, 16)),
        (date(2026, 10, 27), date(2026, 10, 28)),
        (date(2026, 12, 8), date(2026, 12, 9)),
    ],
    2027: [
        (date(2027, 1, 26), date(2027, 1, 27)),
        (date(2027, 3, 16), date(2027, 3, 17)),
        (date(2027, 4, 27), date(2027, 4, 28)),
        (date(2027, 6, 8), date(2027, 6, 9)),
        (date(2027, 7, 27), date(2027, 7, 28)),
        (date(2027, 9, 14), date(2027, 9, 15)),
        (date(2027, 10, 26), date(2027, 10, 27)),
        (date(2027, 12, 7), date(2027, 12, 8)),
    ],
}

# --- Reglas de publicación de IPC e IMACEC ------------------------------
# Feriados fijos de Chile que pueden caer sobre una fecha de publicación. No
# es la lista completa de feriados del país: solo los de fecha fija, que son
# los únicos que la regla puede tener en cuenta sin una tabla anual. Los
# móviles (Viernes Santo, por ejemplo) caen siempre en marzo/abril y nunca
# sobre el día 1 ni el día 8, así que no afectan a estas dos reglas.
_FERIADOS_FIJOS_CHILE = {(1, 1), (5, 1), (9, 18), (9, 19), (12, 8), (12, 25)}


def _es_habil(d: date) -> bool:
    return d.weekday() < 5 and (d.month, d.day) not in _FERIADOS_FIJOS_CHILE


def _fecha_ipc(anio: int, mes: int) -> date:
    """Día 8, o el día hábil ANTERIOR si el 8 cae en fin de semana o feriado.

    OJO: esto NO es una fuente de fechas, es un VERIFICADOR. Las fechas de
    IPC que entran al calendario se copian del INE; esta regla existe para
    contrastarlas y que un error de tipeo al cargarlas no pase inadvertido
    (tests/test_calendario_cobertura.py la corre contra las 12 fechas
    oficiales de 2026 y las reproduce las 12, incluidos los tres ajustes por
    fin de semana y el del feriado del 8 de diciembre). Usarla para
    GENERAR fechas que el INE no publicó sería justo lo que este módulo
    decidió no hacer; ver "POR QUÉ ACÁ NO HAY ESTIMACIONES".
    """
    d = date(anio, mes, 8)
    while not _es_habil(d):
        d -= timedelta(days=1)
    return d


# --- IPC (INE Chile) ----------------------------------------------------
# 2026: fuente "Calendario 2026 — Indicadores de Coyuntura INE" (ine.gob.cl),
# actualización del 10-04-2026, fila "Índice de Precios al Consumidor (IPC)".
# Fechas oficiales, confirmadas.
_IPC_2026_OFICIAL = [
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

# 2027: el INE todavía no publicó su Agenda Estadística 2027 (verificado el
# 01-10-2026; la publica hacia fines de año). NO se rellena con fechas
# derivadas: ver "POR QUÉ ACÁ NO HAY ESTIMACIONES" más abajo.

# --- IMACEC (Banco Central de Chile) ------------------------------------
# Metodología oficial: primer día hábil del mes, con rezago de ~31 días
# respecto al mes medido (ej. el Imacec de julio se publica el primer día
# hábil de septiembre). Pero el BCCh no publica una lista de fechas: su
# "Calendario de difusión estadística" (si3.bcentral.cl) quedó congelado en
# 2018-2019, verificado el 01-10-2026. Acá solo va lo que tiene fuente.
_IMACEC_OFICIAL = [
    # Confirmado explícitamente (fxstreet.com, "Next Release Sep 1").
    (date(2026, 9, 1), "jul-26"),
]

# --- POR QUÉ ACÁ NO HAY ESTIMACIONES ------------------------------------
# Tentación evidente: las fechas de IPC e IMACEC siguen reglas conocidas
# (día 8 o hábil anterior; primer día hábil del mes), así que es fácil
# generarlas para los años que falten y marcarlas como "estimadas" — el
# dashboard incluso sabe mostrar el aviso "(estimated date, not explicitly
# confirmed)". Se hizo, y se descartó por una razón que lo zanja:
#
#   el widget muestra SOLO los próximos 7 días.
#
# Para cuando una de esas filas llega a verse en pantalla, el organismo ya
# publicó la fecha real hace semanas. O sea, la estimación nunca puede
# aportar nada: en el mejor caso coincide con el dato real y era redundante,
# y en el peor caso contradice al dato real y es ruido. Lo único que cambia
# es si el usuario ve una fecha correcta o una inventada.
#
# Así que acá va solo lo publicado. Cuando el INE saque su Agenda
# Estadística 2027, se cargan las 12 fechas de IPC desde la fuente.
# tests/test_calendario_cobertura.py avisa con anticipación cuando la
# cobertura de cualquier tipo de evento se está por agotar, para que esto no
# se descubra con la sección ya vacía.

# --- OPEP+ (reuniones ministeriales) ------------------------------------
# A diferencia de los bancos centrales, la OPEP+ no publica un calendario
# anual fijo: desde 2024 el grupo se reúne aproximadamente cada mes, pero
# cada fecha se confirma solo semanas antes. Fuente:
# tradingeconomics.com/opec/calendar (verificado el 18-08-2026). No hay
# reuniones confirmadas más allá de esa fecha, y por eso esta categoría
# queda vacía hacia adelante: el dashboard ya lo explica en una nota al pie.
_OPEP = [
    (date(2026, 9, 6), True),
]

ANIOS_CARGADOS = (2026, 2027)


def _construir_eventos() -> list[EventoCalendario]:
    eventos = []

    for anio in ANIOS_CARGADOS:
        rpm = _RPM_POR_ANIO[anio]
        for indice, (inicio, fin) in enumerate(rpm):
            eventos.append(EventoCalendario(
                inicio, fin, "RPM", "Reunión de Política Monetaria", True, hora=_HORA_RPM,
            ))
            # RPM ampliada (una de cada dos: la 2ª, 4ª, 6ª y 8ª) -> IPoM la
            # mañana siguiente.
            if indice % _PASO_RPM_AMPLIADA == 1:
                fecha_ipom = fin + timedelta(days=1)
                eventos.append(EventoCalendario(
                    fecha_ipom, fecha_ipom, "IPoM",
                    "Publicación del Informe de Política Monetaria (IPoM)", True,
                    hora=_HORA_IPOM,
                ))

        for inicio, fin in _FOMC_POR_ANIO[anio]:
            eventos.append(EventoCalendario(
                inicio, fin, "FOMC", "Reunión del FOMC (decisión de tasas Fed)", True,
            ))

    for fecha, periodo in _IPC_2026_OFICIAL:
        eventos.append(EventoCalendario(
            fecha, fecha, "IPC", f"Publicación IPC ({periodo})", True, hora=_HORA_IPC,
        ))

    for fecha, periodo in _IMACEC_OFICIAL:
        eventos.append(EventoCalendario(
            fecha, fecha, "IMACEC", f"Publicación IMACEC ({periodo})", True,
        ))

    for fecha, confirmado in _OPEP:
        eventos.append(EventoCalendario(
            fecha, fecha, "OPEP+", "Reunión ministerial OPEP+", confirmado,
        ))

    return sorted(eventos, key=lambda e: e.fecha_inicio)


EVENTOS = _construir_eventos()


def cobertura_por_tipo() -> dict[str, date]:
    """Hasta qué fecha llega cada tipo de evento cargado.

    El pie del calendario en el dashboard se arma con esto en vez de con un
    texto escrito a mano. Antes era una frase fija y se volvió falsa apenas
    cambió el contenido: siguió diciendo "el calendario FOMC 2027 se publica
    en diciembre 2026 — actualizar entonces" cuando el FOMC 2027 ya estaba
    cargado. Un pie derivado de los datos no puede desincronizarse.
    """
    ultimas: dict[str, date] = {}
    for e in EVENTOS:
        if e.fecha_inicio > ultimas.get(e.tipo, date.min):
            ultimas[e.tipo] = e.fecha_inicio
    return ultimas


def proximos_eventos(hoy: date, dias: int = 7) -> list[EventoCalendario]:
    """Eventos cuyo rango [fecha_inicio, fecha_fin] se solapa con los
    próximos `dias` días desde `hoy` (inclusive), ordenados cronológicamente."""
    limite = hoy + timedelta(days=dias)
    return [e for e in EVENTOS if e.fecha_inicio <= limite and e.fecha_fin >= hoy]
