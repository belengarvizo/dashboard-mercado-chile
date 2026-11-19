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


# --- Agendas anuales y su ciclo de publicación ----------------------------
# El calendario se agota solo cada año, y la agenda siguiente no existe hasta
# que la institución la publica. Para distinguir un problema real (una agenda
# publicada que no se cargó, o fechas que no tienen respaldo) de una espera
# legítima (la institución todavía no publica), cada agenda anual queda
# registrada con su estado y con la fecha en que alguien revisó la fuente.
#
# Dos cosas que NO se confunden:
#   - El CICLO HABITUAL de publicación (cuándo suele publicar la institución)
#     no confirma nada: solo dice desde cuándo vale la pena revisar y hasta
#     cuándo es razonable esperar.
#   - La CONFIRMACIÓN es un dato: «se revisó la fuente el día X y la agenda
#     estaba (o no) publicada». Solo eso cambia el estado de una agenda.
#   - Una confirmación de que la agenda NO estaba publicada envejece: vale como
#     estado actual solo durante VIGENCIA_DE_VERIFICACION_DIAS. Después, lo que
#     se sabe es que «no se verificó recientemente», no que siga sin publicarse.
# Ninguna fecha de evento sale de aquí: este registro no genera eventos.
#
# Estados que se REGISTRAN (lo que alguien comprobó en la fuente):
AGENDA_INCORPORADA = "publicada e incorporada"
AGENDA_PUBLICADA_SIN_INCORPORAR = "publicada, sin incorporar"
AGENDA_NO_PUBLICADA = "fuente consultada: todavía no publicada"
# Estado que se DEDUCE (nunca se registra a mano): no hay registro, o la consulta que dice «no publicada» venció.
AGENDA_NO_VERIFICADA = "publicación no verificada recientemente"

# Una verificación de «todavía no publicada» deja de describir el presente después de 7 días: es el horizonte de la
# ventana visible del dashboard, así que una consulta más vieja no garantiza que los próximos 7 días estén cubiertos.
VIGENCIA_DE_VERIFICACION_DIAS = 7


@dataclass(frozen=True)
class AgendaAnual:
    tipo: str                         # clave de INDICADOR_POR_TIPO (el IPoM usa la agenda de RPM)
    anio: int
    estado: str                       # uno de los estados que se registran (no AGENDA_NO_VERIFICADA)
    verificado_al: date | None        # última vez que se revisó la fuente
    fuente: str
    publicada_el: date | None = None  # solo si se conoce el día en que la institución la publicó


def estado_efectivo(agenda: AgendaAnual | None, hoy: date) -> str:
    """El estado que vale HOY. Una agenda publicada (incorporada o no) lo sigue estando; una consulta que dijo «todavía
    no publicada» solo vale mientras esté vigente; sin registro, o con la consulta vencida, no se sabe."""
    if agenda is None:
        return AGENDA_NO_VERIFICADA
    if agenda.estado == AGENDA_NO_PUBLICADA:
        vigente = (agenda.verificado_al is not None
                   and 0 <= (hoy - agenda.verificado_al).days <= VIGENCIA_DE_VERIFICACION_DIAS)
        return AGENDA_NO_PUBLICADA if vigente else AGENDA_NO_VERIFICADA
    return agenda.estado


AGENDAS = (
    AgendaAnual("RPM", 2026, AGENDA_INCORPORADA, date(2026, 10, 1),
                "bcentral.cl > Monetary and Financial Policy calendar"),
    AgendaAnual("RPM", 2027, AGENDA_INCORPORADA, date(2026, 10, 1),
                "bcentral.cl > Monetary and Financial Policy calendar", publicada_el=date(2026, 9, 30)),
    AgendaAnual("FOMC", 2026, AGENDA_INCORPORADA, date(2026, 10, 1), "federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    AgendaAnual("FOMC", 2027, AGENDA_INCORPORADA, date(2026, 10, 1), "federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    # INE: «Instituto Nacional de Estadísticas publica Agenda Estadística 2026», nota de prensa del 30-12-2025.
    AgendaAnual("IPC", 2026, AGENDA_INCORPORADA, date(2026, 10, 1), "ine.gob.cl > Agenda Estadística 2026",
                publicada_el=date(2025, 12, 30)),
    # Al 01-10-2026 el INE no había publicado su Agenda Estadística 2027 (ver «POR QUÉ ACÁ NO HAY ESTIMACIONES»).
    AgendaAnual("IPC", 2027, AGENDA_NO_PUBLICADA, date(2026, 10, 1), "ine.gob.cl > Agenda Estadística 2027"),
)

# El IPoM no tiene agenda propia: se deriva de las RPM (ver _PASO_RPM_AMPLIADA).
AGENDA_DE = {"IPoM": "RPM"}


def _fecha_relativa(anio: int, desplazamiento: tuple[int, int, int]) -> date:
    a, m, d = desplazamiento
    return date(anio + a, m, d)


@dataclass(frozen=True)
class CicloDePublicacion:
    """Cuándo suele publicar la institución la agenda del año t y cuándo le corresponde al equipo revisarla. Cada
    fecha es (desplazamiento de año respecto de t, mes, día).

    - desde / hasta: ventana HABITUAL de publicación. Es una expectativa, no una confirmación.
    - revision_prioritaria: desde aquí, sin una verificación vigente, la advertencia sube de prioridad.
    - revision_operativa: desde aquí, sin una verificación vigente, hay una FALLA DE MANTENIMIENTO. Es una fecha de
      trabajo del equipo, configurable; no es un plazo legal ni dice nada sobre lo que hizo la institución."""
    tipo: str
    desde: tuple[int, int, int]
    hasta: tuple[int, int, int]
    revision_prioritaria: tuple[int, int, int]
    revision_operativa: tuple[int, int, int]
    respaldo: str

    def ventana(self, anio: int) -> tuple[date, date]:
        return _fecha_relativa(anio, self.desde), _fecha_relativa(anio, self.hasta)

    def revisiones(self, anio: int) -> tuple[date, date]:
        return _fecha_relativa(anio, self.revision_prioritaria), _fecha_relativa(anio, self.revision_operativa)


CICLOS = {
    # Ventana habitual. Norma: la agenda de boletines coyunturales «deberá ser difundida en diciembre del año t-1 o en
    # el mes de enero del año t» (DIPRES). Observado: agenda 2026 publicada el 30-12-2025; la de 2022, el 31-12-2021.
    # Revisión operativa: el 1 de enero. Desde ese día la ventana visible de 7 días puede incluir el primer IPC del
    # año (se publica el día 8 o el hábil anterior: el 08-01-2026 en 2026), así que un calendario sin revisar puede
    # estar dejando fuera un evento oficial visible. La revisión prioritaria empieza 8 días antes (24-12), para que la
    # alerta llegue con al menos una ventana visible de anticipación.
    "IPC": CicloDePublicacion("IPC", (-1, 12, 1), (0, 1, 31), (-1, 12, 24), (0, 1, 1),
                              "DIPRES: diciembre del año anterior o enero del año; INE publicó la de 2026 el 30-12-2025"),
    # RPM y FOMC: una sola observación por institución (RPM 2027 publicada el 30-09-2026) no hace un ciclo; sin ciclo
    # registrado, la política solo puede advertir, nunca exigir por plazo.
}

# Tipos que el calendario se compromete a mantener al día, con dónde se recargan. OPEP+ e IMACEC quedan fuera a
# propósito: ninguno de los dos organismos publica una lista anual de fechas.
TIPOS_MANTENIDOS = {
    "RPM": "bcentral.cl > Monetary and Financial Policy calendar",
    "IPoM": "se deriva de las RPM (cargar el año de RPM alcanza)",
    "FOMC": "federalreserve.gov/monetarypolicy/fomccalendars.htm",
    "IPC": "ine.gob.cl > Agenda Estadística del año",
}
COBERTURA_MINIMA_DIAS = 21

NIVEL_OK = "ok"
NIVEL_ADVERTENCIA = "advertencia"
NIVEL_ADVERTENCIA_PRIORITARIA = "advertencia prioritaria"
# Dos fallas distintas, que nunca se mezclan en un mismo mensaje:
NIVEL_FALLA_DATOS = "falla de datos"                  # el calendario contradice o no incorpora agendas oficiales
NIVEL_FALLA_MANTENIMIENTO = "falla de mantenimiento"  # nadie verificó la fuente cuando correspondía
NIVELES_DE_FALLA = (NIVEL_FALLA_DATOS, NIVEL_FALLA_MANTENIMIENTO)


@dataclass(frozen=True)
class DiagnosticoCobertura:
    tipo: str
    nivel: str
    dias_restantes: int | None  # None: no quedan fechas futuras de ese tipo
    mensaje: str


def _f(d: date | None) -> str:
    return d.strftime("%d-%m-%Y") if d else "nunca"


def evaluar_cobertura(hoy: date, eventos=None, agendas=None, ciclos=None,
                      minimo: int = COBERTURA_MINIMA_DIAS) -> list[DiagnosticoCobertura]:
    """Diagnóstico de cobertura por tipo de evento, a la fecha `hoy` (que se pasa explícita, para poder simularla).

    FALLA DE DATOS: una agenda registrada como publicada que no está incorporada; fechas de un año sin agenda
      registrada como incorporada; una agenda «incorporada» sin fechas de ese año.
    FALLA DE MANTENIMIENTO: con la cobertura corta, llegó la fecha operativa de revisión y no hay una verificación
      vigente de la fuente. No afirma nada sobre la institución: dice que el equipo no revisó.
    ADVERTENCIA PRIORITARIA: se acerca la fecha operativa y no hay verificación vigente.
    ADVERTENCIA: espera legítima. La cobertura está corta y la agenda siguiente todavía no corresponde revisarla, o
      corresponde y aún no se revisa, o se revisó hace poco y la institución todavía no la publica (aunque sea
      después de su plazo habitual: eso es una demora de la institución, no un error del calendario).
    OK: cobertura de al menos `minimo` días y registro consistente."""
    eventos = EVENTOS if eventos is None else eventos
    agendas = AGENDAS if agendas is None else agendas
    ciclos = CICLOS if ciclos is None else ciclos
    registro = {(a.tipo, a.anio): a for a in agendas}
    diagnosticos = []
    for tipo, fuente in TIPOS_MANTENIDOS.items():
        tipo_agenda = AGENDA_DE.get(tipo, tipo)
        propios = [e for e in eventos if e.tipo == tipo]
        anios = sorted({e.fecha_inicio.year for e in propios})
        futuras = [e.fecha_inicio for e in propios if e.fecha_inicio >= hoy]
        dias = (max(futuras) - hoy).days if futuras else None

        problemas = []
        for anio in anios:
            agenda = registro.get((tipo_agenda, anio))
            if agenda is None or agenda.estado != AGENDA_INCORPORADA:
                problemas.append(f"hay fechas de {anio} sin una agenda oficial de {anio} registrada como incorporada")
        for (t, anio), agenda in sorted(registro.items()):
            if t != tipo_agenda:
                continue
            if agenda.estado == AGENDA_INCORPORADA and anio not in anios:
                problemas.append(f"la agenda {anio} figura como incorporada, pero no hay fechas de {anio}")
            if agenda.estado == AGENDA_PUBLICADA_SIN_INCORPORAR:
                cuando = f" el {_f(agenda.publicada_el)}" if agenda.publicada_el else ""
                problemas.append(f"la agenda {anio} fue publicada{cuando} y no está incorporada: cargarla desde {fuente}")
        if problemas:
            diagnosticos.append(DiagnosticoCobertura(
                tipo, NIVEL_FALLA_DATOS, dias, f"Error de datos del calendario. {tipo}: " + "; ".join(problemas) + "."))
            continue
        if dias is not None and dias >= minimo:
            diagnosticos.append(DiagnosticoCobertura(tipo, NIVEL_OK, dias, f"{tipo}: cubre {dias} días."))
            continue

        siguiente = anios[-1] + 1 if anios else hoy.year
        agenda = registro.get((tipo_agenda, siguiente))
        efectivo = estado_efectivo(agenda, hoy)
        verificado = agenda.verificado_al if agenda else None
        cobertura = f"le quedan {dias} días de fechas" if dias is not None else "ya no tiene fechas futuras"
        if efectivo == AGENDA_NO_VERIFICADA and agenda is not None and agenda.estado == AGENDA_NO_PUBLICADA:
            sabido = (f"la consulta del {_f(verificado)} no la encontró, pero esa verificación ya no describe el presente "
                      f"(vigencia: {VIGENCIA_DE_VERIFICACION_DIAS} días)")
        elif efectivo == AGENDA_NO_PUBLICADA:
            sabido = f"fuente consultada el {_f(verificado)}: todavía no publicada"
        else:
            sabido = "no hay una verificación registrada"
        base = f"{tipo}: {cobertura}; agenda {siguiente}: {efectivo} ({sabido})"
        cierre = " Se carga cuando la institución la publique; no se estiman fechas."
        ciclo = ciclos.get(tipo_agenda)
        if ciclo is None:
            diagnosticos.append(DiagnosticoCobertura(
                tipo, NIVEL_ADVERTENCIA, dias, f"{base}. Sin ciclo de publicación registrado: revisar {fuente}.{cierre}"))
            continue
        desde, hasta = ciclo.ventana(siguiente)
        prioritaria, operativa = ciclo.revisiones(siguiente)
        habitual = f"el organismo la publica habitualmente entre el {_f(desde)} y el {_f(hasta)}"

        if efectivo == AGENDA_NO_PUBLICADA:  # verificación vigente: espera legítima, aun después del plazo habitual
            demora = (f" Ya pasó su plazo habitual ({_f(hasta)}): es una demora de la institución, no un error del "
                      "calendario." if hoy > hasta else "")
            diagnosticos.append(DiagnosticoCobertura(tipo, NIVEL_ADVERTENCIA, dias, f"{base}.{demora}{cierre}"))
        elif hoy >= operativa:
            diagnosticos.append(DiagnosticoCobertura(
                tipo, NIVEL_FALLA_MANTENIMIENTO, dias,
                f"Mantenimiento pendiente (no es un error de fechas oficiales). {base}. Desde el {_f(operativa)}, fecha "
                f"operativa de revisión, la ventana visible de 7 días puede incluir el primer evento de {siguiente}: "
                f"revisar {fuente} y, si la agenda está publicada, incorporarla; si no, registrar la verificación."))
        elif hoy >= prioritaria:
            diagnosticos.append(DiagnosticoCobertura(
                tipo, NIVEL_ADVERTENCIA_PRIORITARIA, dias,
                f"Revisión prioritaria. {base}. Desde el {_f(operativa)}, sin una verificación vigente, esto será una falla "
                f"de mantenimiento; {habitual}.{cierre}"))
        elif hoy >= desde:
            diagnosticos.append(DiagnosticoCobertura(
                tipo, NIVEL_ADVERTENCIA, dias,
                f"{base}. Corresponde revisar {fuente}: {habitual}.{cierre}"))
        else:
            diagnosticos.append(DiagnosticoCobertura(
                tipo, NIVEL_ADVERTENCIA, dias, f"{base}. La revisión corresponde desde el {_f(desde)}; {habitual}.{cierre}"))
    return diagnosticos
