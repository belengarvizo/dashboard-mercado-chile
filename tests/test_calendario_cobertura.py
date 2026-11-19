"""El calendario económico vive de listas escritas a mano, así que se agota
solo. Estas pruebas hacen que eso se note ANTES de que pase.

QUÉ SE ESCAPÓ SIN ESTO. Al 01-10-2026 el módulo solo tenía 2026 cargado: el
último evento era el 16 de diciembre y, a partir del 17, la sección
"Economic calendar — next 7 days" del dashboard iba a mostrar "No events
scheduled" para siempre. Sin error, sin log, sin aviso: simplemente una
sección vacía que parece normal. El propio código tenía escrito que había
que actualizarlo ("RPM 2027 se publica en septiembre 2026"), pero un
comentario no falla cuando se incumple.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import sys
import warnings
from datetime import date, timedelta

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import calendario_economico as cal

# Con cuánta anticipación queremos enterarnos. Los organismos publican su
# calendario del año siguiente entre septiembre y diciembre, así que tres
# meses de aviso alcanzan de sobra para cargarlo sin apuro.
DIAS_MINIMOS_DE_COBERTURA = 90


def test_el_calendario_no_esta_a_punto_de_quedarse_vacio():
    hoy = date.today()
    ultimo = max(e.fecha_inicio for e in cal.EVENTOS)
    dias_restantes = (ultimo - hoy).days
    assert dias_restantes >= DIAS_MINIMOS_DE_COBERTURA, (
        f"El calendario económico se queda sin eventos el {ultimo}, en "
        f"{dias_restantes} días. A partir de ahí la sección del dashboard va a "
        f"mostrar 'No events scheduled' en silencio.\n"
        f"Hay que cargar el año siguiente en calendario_economico.py desde las "
        f"fuentes oficiales (bcentral.cl, federalreserve.gov, ine.gob.cl).\n"
        f"Cobertura actual por tipo: "
        + ", ".join(f"{t}={d}" for t, d in sorted(cal.cobertura_por_tipo().items()))
    )


class AvisoDeCobertura(UserWarning):
    """Espera legítima: la cobertura se agota y la agenda siguiente todavía no está disponible o no se verificó.
    Aparece en el resumen de advertencias de pytest; no hace fallar la suite."""


class AvisoDeCoberturaPrioritario(AvisoDeCobertura):
    """Se acerca la fecha operativa de revisión sin una verificación vigente de la fuente."""


def test_cada_tipo_mantenido_tiene_cobertura_suficiente():
    """Avisa por tipo, no solo en conjunto: el calendario puede tener meses de RPM cargadas y aun así haberse quedado
    sin IPC, y la sección quedaría coja sin que el chequeo global se entere.

    Desde C-1 distingue (ver cal.evaluar_cobertura):
      - FALLA DE DATOS: una agenda publicada sin incorporar, o fechas sin agenda oficial registrada. La prueba falla.
      - FALLA DE MANTENIMIENTO: llegó la fecha operativa de revisión sin una verificación vigente de la fuente. La
        prueba falla, con un mensaje que dice que no es un error de fechas oficiales.
      - ADVERTENCIA (prioritaria o no): espera legítima. Avisa con AvisoDeCobertura, visible en el resumen de pytest,
        y no falla: no hay nada que se pueda cargar."""
    diagnosticos = cal.evaluar_cobertura(date.today())
    for d in diagnosticos:
        if d.nivel == cal.NIVEL_ADVERTENCIA_PRIORITARIA:
            warnings.warn(d.mensaje, AvisoDeCoberturaPrioritario, stacklevel=1)
        elif d.nivel == cal.NIVEL_ADVERTENCIA:
            warnings.warn(d.mensaje, AvisoDeCobertura, stacklevel=1)
    datos = [d.mensaje for d in diagnosticos if d.nivel == cal.NIVEL_FALLA_DATOS]
    mantenimiento = [d.mensaje for d in diagnosticos if d.nivel == cal.NIVEL_FALLA_MANTENIMIENTO]
    assert not datos and not mantenimiento, (
        ("Errores de datos del calendario:\n" + "\n".join(f"  {m}" for m in datos) + "\n" if datos else "")
        + ("Mantenimiento pendiente:\n" + "\n".join(f"  {m}" for m in mantenimiento) if mantenimiento else "")
    )


# ---------------------------------------------------------------------------
# La política de cobertura con fechas simuladas (C-1). Nada de esto consulta
# páginas oficiales: el registro de agendas es un dato del módulo.
# ---------------------------------------------------------------------------
def _nivel(hoy, tipo="IPC", **kwargs):
    return next(d for d in cal.evaluar_cobertura(hoy, **kwargs) if d.tipo == tipo)


def _agendas_con(*reemplazos):
    """El registro real, con las agendas indicadas reemplazadas (mismo tipo y año)."""
    claves = {(a.tipo, a.anio) for a in reemplazos}
    return tuple(a for a in cal.AGENDAS if (a.tipo, a.anio) not in claves) + tuple(reemplazos)


def test_agenda_vigente_con_cobertura_suficiente():
    """El 01-10-2026 al IPC le quedaban 67 días (hasta el 07-12-2026): sin advertencias ni fallas."""
    d = _nivel(date(2026, 10, 1))
    assert d.nivel == cal.NIVEL_OK and d.dias_restantes == (date(2026, 12, 7) - date(2026, 10, 1)).days


def _verificada(hoy, dias_atras=2):
    """El registro real, pero con una consulta VIGENTE del INE que encontró la agenda 2027 todavía sin publicar."""
    return _agendas_con(cal.AgendaAnual("IPC", 2027, cal.AGENDA_NO_PUBLICADA, hoy - timedelta(days=dias_atras), "ine.gob.cl"))


def test_noviembre_2026_cobertura_corta_sin_agenda_2027_es_advertencia():
    """19-11-2026: quedan 18 días. La consulta del 01-10-2026 no encontró la agenda 2027, pero tiene 49 días: no se
    interpreta como que siga sin publicarse (estado efectivo: no verificada recientemente). La revisión corresponde
    desde el 01-12-2026. Es una espera, no un incumplimiento."""
    d = _nivel(date(2026, 11, 19))
    assert d.nivel == cal.NIVEL_ADVERTENCIA and d.dias_restantes == 18
    assert cal.AGENDA_NO_VERIFICADA in d.mensaje and "ya no describe el presente" in d.mensaje
    assert "01-12-2026" in d.mensaje and "no se estiman fechas" in d.mensaje


@pytest.mark.parametrize("hoy", [date(2026, 12, 8), date(2026, 12, 31), date(2027, 1, 15), date(2027, 1, 31)])
def test_diciembre_2026_y_enero_2027_dentro_del_plazo_habitual_es_advertencia(hoy):
    """Sin fechas de IPC futuras y con una consulta VIGENTE que no encontró la agenda: espera legítima.
    (Cambió con el ajuste de C-1: sin una verificación vigente, desde el 24-12 la advertencia es prioritaria y desde
    el 01-01 es falla de mantenimiento; ver las pruebas de la línea de tiempo más abajo.)"""
    d = _nivel(hoy, agendas=_verificada(hoy))
    assert d.nivel == cal.NIVEL_ADVERTENCIA and d.dias_restantes is None
    assert "fuente consultada el" in d.mensaje and "todavía no publicada" in d.mensaje


def test_vencido_el_plazo_dentro_del_margen_sigue_siendo_advertencia_pero_lo_anuncia():
    """10-02-2027, ya vencido el plazo habitual (31-01). (Cambió con el ajuste de C-1: el margen de 15 días se
    reemplazó por la fecha operativa del 01-01.) Con una consulta vigente, es una demora del INE: advertencia que lo
    dice. Sin consulta vigente, es falla de mantenimiento desde mucho antes."""
    con_consulta = _nivel(date(2027, 2, 10), agendas=_verificada(date(2027, 2, 10)))
    assert con_consulta.nivel == cal.NIVEL_ADVERTENCIA and "demora de la institución" in con_consulta.mensaje
    assert _nivel(date(2027, 2, 10)).nivel == cal.NIVEL_FALLA_MANTENIMIENTO


def test_vencido_el_plazo_y_el_margen_sin_verificar_la_fuente_es_falla():
    """El 20-02-2027 la última revisión del INE sigue siendo la del 01-10-2026. (Cambió con el ajuste de C-1: ahora es
    falla de MANTENIMIENTO, y lo es desde el 01-01-2027.) No se afirma que el INE haya publicado."""
    d = _nivel(date(2027, 2, 20))
    assert d.nivel == cal.NIVEL_FALLA_MANTENIMIENTO and "no es un error de fechas oficiales" in d.mensaje


def test_publicacion_esperada_no_es_publicacion_confirmada():
    """Misma fecha (15-01-2027), dos registros: si la consulta vigente no la encontró, es advertencia; si se registró
    que el INE la publicó y no está cargada, es falla de DATOS."""
    esperada = _nivel(date(2027, 1, 15), agendas=_verificada(date(2027, 1, 15)))
    confirmada = _nivel(date(2027, 1, 15), agendas=_agendas_con(cal.AgendaAnual(
        "IPC", 2027, cal.AGENDA_PUBLICADA_SIN_INCORPORAR, date(2027, 1, 5), "ine.gob.cl", publicada_el=date(2026, 12, 30))))
    assert esperada.nivel == cal.NIVEL_ADVERTENCIA
    assert confirmada.nivel == cal.NIVEL_FALLA_DATOS and "fue publicada el 30-12-2026 y no está incorporada" in confirmada.mensaje
    assert "Error de datos" in confirmada.mensaje


def test_agenda_publicada_y_no_incorporada_falla_aunque_quede_cobertura():
    d = _nivel(date(2026, 10, 1), agendas=_agendas_con(cal.AgendaAnual(
        "IPC", 2027, cal.AGENDA_PUBLICADA_SIN_INCORPORAR, date(2026, 9, 30), "ine.gob.cl")))
    assert d.nivel == cal.NIVEL_FALLA_DATOS


def test_verificacion_posterior_al_plazo_que_no_encontro_la_agenda_es_advertencia():
    """Si alguien revisó hace 4 días y el INE de verdad no publicó, no hay nada que cargar: advertencia, aunque sea
    después del plazo habitual (demora de la institución, no del calendario)."""
    d = _nivel(date(2027, 3, 1), agendas=_agendas_con(cal.AgendaAnual(
        "IPC", 2027, cal.AGENDA_NO_PUBLICADA, date(2027, 2, 25), "ine.gob.cl")))
    assert d.nivel == cal.NIVEL_ADVERTENCIA and "demora de la institución" in d.mensaje


# ---- Línea de tiempo de la revisión operativa (ajuste de C-1) -------------
@pytest.mark.parametrize("hoy, nivel, texto", [
    (date(2026, 11, 30), cal.NIVEL_ADVERTENCIA, "La revisión corresponde desde el 01-12-2026"),
    (date(2026, 12, 1), cal.NIVEL_ADVERTENCIA, "Corresponde revisar ine.gob.cl"),
    (date(2026, 12, 23), cal.NIVEL_ADVERTENCIA, "Corresponde revisar ine.gob.cl"),
    (date(2026, 12, 24), cal.NIVEL_ADVERTENCIA_PRIORITARIA, "Desde el 01-01-2027, sin una verificación vigente"),
    (date(2026, 12, 31), cal.NIVEL_ADVERTENCIA_PRIORITARIA, "Revisión prioritaria"),
    (date(2027, 1, 1), cal.NIVEL_FALLA_MANTENIMIENTO, "no es un error de fechas oficiales"),
    (date(2027, 1, 15), cal.NIVEL_FALLA_MANTENIMIENTO, "fecha operativa de revisión"),
])
def test_linea_de_tiempo_sin_verificacion_vigente(hoy, nivel, texto):
    """Con la única consulta registrada (01-10-2026, vencida): advertencia en diciembre, prioritaria desde el 24-12 y
    falla de mantenimiento desde el 01-01-2027, cuando la ventana visible puede incluir el primer IPC del año."""
    d = _nivel(hoy)
    assert d.nivel == nivel and texto in d.mensaje, d.mensaje


@pytest.mark.parametrize("dias_atras, nivel", [(0, cal.NIVEL_ADVERTENCIA), (7, cal.NIVEL_ADVERTENCIA),
                                               (8, cal.NIVEL_FALLA_MANTENIMIENTO)])
def test_vigencia_de_la_verificacion_en_su_borde(dias_atras, nivel):
    """El 05-01-2027: una consulta de hasta 7 días vale como estado actual; una de 8 días ya no."""
    hoy = date(2027, 1, 5)
    assert _nivel(hoy, agendas=_verificada(hoy, dias_atras)).nivel == nivel


def test_estado_efectivo_distingue_los_cuatro_casos():
    hoy = date(2026, 12, 20)
    def agenda(estado, verificado):
        return cal.AgendaAnual("IPC", 2027, estado, verificado, "ine.gob.cl")
    assert cal.estado_efectivo(None, hoy) == cal.AGENDA_NO_VERIFICADA
    assert cal.estado_efectivo(agenda(cal.AGENDA_NO_PUBLICADA, date(2026, 10, 1)), hoy) == cal.AGENDA_NO_VERIFICADA
    assert cal.estado_efectivo(agenda(cal.AGENDA_NO_PUBLICADA, date(2026, 12, 18)), hoy) == cal.AGENDA_NO_PUBLICADA
    assert cal.estado_efectivo(agenda(cal.AGENDA_PUBLICADA_SIN_INCORPORAR, date(2026, 12, 18)), hoy) == cal.AGENDA_PUBLICADA_SIN_INCORPORAR
    assert cal.estado_efectivo(agenda(cal.AGENDA_INCORPORADA, date(2026, 10, 1)), hoy) == cal.AGENDA_INCORPORADA
    # una consulta con fecha futura respecto de «hoy» (simulación hacia atrás) no cuenta como vigente
    assert cal.estado_efectivo(agenda(cal.AGENDA_NO_PUBLICADA, date(2026, 12, 25)), hoy) == cal.AGENDA_NO_VERIFICADA


def test_las_fechas_de_revision_son_configurables(monkeypatch):
    """La fecha operativa es una elección de trabajo, no un plazo legal: si se mueve al 20-12, la falla de
    mantenimiento llega antes."""
    ciclo = cal.CICLOS["IPC"]
    temprano = cal.CicloDePublicacion("IPC", ciclo.desde, ciclo.hasta, (-1, 12, 15), (-1, 12, 20), ciclo.respaldo)
    assert _nivel(date(2026, 12, 21), ciclos={"IPC": temprano}).nivel == cal.NIVEL_FALLA_MANTENIMIENTO
    assert _nivel(date(2026, 12, 21)).nivel == cal.NIVEL_ADVERTENCIA


# Una agenda sintética, de un año lejano (2036) para que nadie la confunda con datos reales: prueba el caso
# «publicada e incorporada» sin tocar el registro real ni inventar fechas de 2027.
_FICTICIOS_2036 = [cal.EventoCalendario(date(2036, m, 8), date(2036, m, 8), "IPC", "ficticio de prueba", True)
                   for m in range(1, 13)]


def test_agenda_publicada_e_incorporada_correctamente():
    agendas = (cal.AgendaAnual("IPC", 2036, cal.AGENDA_INCORPORADA, date(2036, 1, 2), "prueba"),)
    d = _nivel(date(2036, 3, 1), eventos=_FICTICIOS_2036, agendas=agendas)
    assert d.nivel == cal.NIVEL_OK


def test_fechas_sin_agenda_oficial_registrada_fallan():
    """Datos que contradicen el registro: hay fechas de 2036 pero ninguna agenda 2036 incorporada."""
    agendas = (cal.AgendaAnual("IPC", 2036, cal.AGENDA_NO_PUBLICADA, date(2036, 1, 2), "prueba"),)
    d = _nivel(date(2036, 3, 1), eventos=_FICTICIOS_2036, agendas=agendas)
    assert d.nivel == cal.NIVEL_FALLA_DATOS and "sin una agenda oficial de 2036" in d.mensaje


def test_agenda_marcada_incorporada_sin_fechas_falla():
    agendas = _agendas_con(cal.AgendaAnual("IPC", 2027, cal.AGENDA_INCORPORADA, date(2027, 1, 5), "ine.gob.cl"))
    d = _nivel(date(2026, 11, 19), agendas=agendas)
    assert d.nivel == cal.NIVEL_FALLA_DATOS and "figura como incorporada, pero no hay fechas de 2027" in d.mensaje


def test_sin_ciclo_registrado_solo_se_advierte():
    """RPM y FOMC no tienen ciclo registrado (una sola observación no hace un ciclo): cerca del fin de su cobertura,
    la política advierte y nunca exige por plazo."""
    for hoy in (date(2027, 12, 1), date(2028, 6, 1)):
        for tipo in ("RPM", "FOMC"):
            assert _nivel(hoy, tipo).nivel == cal.NIVEL_ADVERTENCIA


def test_el_registro_real_es_consistente_hoy_y_no_trae_ipc_2027():
    """Sin fechas inventadas: no hay ningún evento de IPC en 2027, la agenda 2027 sigue registrada con la única
    consulta real (01-10-2026, sin fecha de publicación) y el registro real no tiene errores de DATOS a ninguna fecha
    del ciclo. (Cambió con el ajuste de C-1: desde el 01-01-2027, sin una nueva verificación, hay una falla de
    MANTENIMIENTO; antes de esa fecha no hay ninguna falla.)"""
    assert not [e for e in cal.EVENTOS if e.tipo == "IPC" and e.fecha_inicio.year >= 2027]
    agenda_2027 = next(a for a in cal.AGENDAS if (a.tipo, a.anio) == ("IPC", 2027))
    assert agenda_2027.estado == cal.AGENDA_NO_PUBLICADA and agenda_2027.publicada_el is None
    assert agenda_2027.verificado_al == date(2026, 10, 1)
    for hoy in (date(2026, 10, 1), date(2026, 11, 19), date(2026, 12, 15), date(2027, 1, 15)):
        niveles = {d.nivel for d in cal.evaluar_cobertura(hoy)}
        assert cal.NIVEL_FALLA_DATOS not in niveles, hoy
        assert (cal.NIVEL_FALLA_MANTENIMIENTO in niveles) is (hoy >= date(2027, 1, 1)), hoy


def test_la_ventana_visible_de_siete_dias_solo_muestra_eventos_oficiales():
    """El dashboard muestra proximos_eventos(hoy, 7). Del 08-12-2026 en adelante no aparece ningún IPC: no hay fechas
    oficiales que mostrar y la política no agrega ninguna. Un IPC oficial a más de 7 días tampoco se muestra."""
    for hoy in (date(2026, 12, 8), date(2026, 12, 28), date(2027, 1, 4)):
        assert not [e for e in cal.proximos_eventos(hoy, dias=7) if e.tipo == "IPC"], hoy
    visibles = cal.proximos_eventos(date(2026, 11, 30), dias=7)  # ventana hasta el 07-12, inclusive
    assert [e.fecha_inicio for e in visibles if e.tipo == "IPC"] == [date(2026, 12, 7)]
    # el 29-11 la ventana llega al 06-12: el IPC oficial del 07-12 queda a 8 días y todavía no se muestra
    assert not [e for e in cal.proximos_eventos(date(2026, 11, 29), dias=7) if e.tipo == "IPC"]
    assert all(e.confirmado for e in cal.EVENTOS)


def test_la_politica_no_cambia_lo_que_usa_el_dashboard():
    """El dashboard importa proximos_eventos, cobertura_por_tipo, INDICADOR_POR_TIPO y CALENDARIO_VERIFICADO_AL.
    La política se agregó al lado; esas cuatro piezas no cambian de forma."""
    import inspect
    assert list(inspect.signature(cal.proximos_eventos).parameters) == ["hoy", "dias"]
    assert inspect.signature(cal.proximos_eventos).parameters["dias"].default == 7
    assert cal.cobertura_por_tipo()["IPC"] == date(2026, 12, 7)
    assert set(cal.INDICADOR_POR_TIPO) == {"RPM", "IPoM", "FOMC", "IPC", "IMACEC", "OPEP+"}
    assert cal.CALENDARIO_VERIFICADO_AL == date(2026, 10, 1)


def test_cada_agenda_registrada_tiene_su_tipo_y_un_estado_valido():
    # «no verificada recientemente» se DEDUCE (estado_efectivo); nunca se registra a mano.
    estados = {cal.AGENDA_INCORPORADA, cal.AGENDA_PUBLICADA_SIN_INCORPORAR, cal.AGENDA_NO_PUBLICADA}
    for a in cal.AGENDAS:
        assert a.tipo in cal.INDICADOR_POR_TIPO and a.estado in estados, a
        assert a.verificado_al is None or a.publicada_el is None or a.publicada_el <= a.verificado_al, a


def test_la_regla_del_ipc_reproduce_el_calendario_oficial_del_INE():
    """_fecha_ipc no genera fechas: las verifica. Cuando se carguen las del
    INE para un año nuevo, este contraste atrapa un error de tipeo al
    copiarlas. Para que sirva de verificador tiene que reproducir exactamente
    las 12 fechas oficiales de 2026, incluidos los tres ajustes por fin de
    semana y el del feriado del 8 de diciembre."""
    for fecha_oficial, periodo in cal._IPC_2026_OFICIAL:
        derivada = cal._fecha_ipc(2026, fecha_oficial.month)
        assert derivada == fecha_oficial, (
            f"IPC {periodo}: la regla da {derivada} pero el INE publicó {fecha_oficial}"
        )


def test_no_hay_ninguna_fecha_estimada():
    """El calendario solo muestra los próximos 7 días, así que para cuando
    una fila se ve en pantalla el organismo ya publicó la fecha real: una
    estimación solo puede ser redundante o estar mal. La política es cargar
    lo publicado o no mostrar nada — nunca rellenar con una regla.

    (El campo `confirmado` y el aviso "(estimated date...)" del dashboard se
    conservan: si alguna vez entra una fecha de una fuente secundaria, tiene
    que poder marcarse. Lo que no se acepta es generar fechas.)"""
    estimadas = [
        f"{e.tipo} {e.fecha_inicio}" for e in cal.EVENTOS if not e.confirmado
    ]
    assert not estimadas, (
        "Hay fechas sin confirmar en el calendario. Si no están publicadas por la "
        f"fuente, no deberían estar: {estimadas}"
    )


def test_no_hay_eventos_duplicados():
    vistos = [(e.tipo, e.fecha_inicio) for e in cal.EVENTOS]
    duplicados = {x for x in vistos if vistos.count(x) > 1}
    assert not duplicados, f"eventos duplicados en el calendario: {sorted(duplicados)}"


def test_el_pie_del_calendario_sale_de_los_datos_y_no_de_un_texto_fijo():
    """El dashboard arma el pie ("Loaded through: RPM Dec 2027, ...") con
    cobertura_por_tipo(). Antes era una frase escrita a mano y se volvió
    falsa apenas cambió el contenido: siguió diciendo que el calendario FOMC
    2027 estaba por publicarse cuando ya estaba cargado. Lo detectó una
    captura del navegador, no un test — de ahí este."""
    cobertura = cal.cobertura_por_tipo()
    assert cobertura, "cobertura_por_tipo() no devolvió nada"
    for tipo, hasta in cobertura.items():
        reales = [e.fecha_inicio for e in cal.EVENTOS if e.tipo == tipo]
        assert hasta == max(reales), (
            f"{tipo}: cobertura dice {hasta} pero el último evento cargado es {max(reales)}"
        )
    assert cal.CALENDARIO_VERIFICADO_AL <= date.today(), (
        "la fecha de verificación del calendario está en el futuro"
    )


def test_el_dashboard_no_tiene_el_pie_viejo_escrito_a_mano():
    """Guarda contra que alguien reponga la frase fija."""
    ruta = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
    with open(ruta, encoding="utf-8") as f:
        codigo = f.read()
    for frase in ("is published in September 2026", "the 2027 FOMC calendar in December"):
        assert frase not in codigo, (
            f"volvió el pie del calendario escrito a mano ({frase!r}): se desincroniza "
            "apenas se carga un año nuevo. Usar cobertura_por_tipo()."
        )
