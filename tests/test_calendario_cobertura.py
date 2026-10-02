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
import os
import sys
from datetime import date, timedelta

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


# Tipos que SÍ nos comprometemos a mantener al día, con la fuente de donde
# se recargan. OPEP+ e IMACEC quedan fuera a propósito: ninguno de los dos
# organismos publica una lista de fechas (la OPEP+ confirma cada reunión
# semanas antes; el calendario estadístico del BCCh está congelado en
# 2018-2019), así que no hay nada que recargar y el módulo no inventa.
FUENTE_POR_TIPO = {
    "RPM": "bcentral.cl > Monetary and Financial Policy calendar",
    "IPoM": "se deriva de las RPM (cargar el año de RPM alcanza)",
    "FOMC": "federalreserve.gov/monetarypolicy/fomccalendars.htm",
    "IPC": "ine.gob.cl > Agenda Estadística del año",
}
DIAS_MINIMOS_POR_TIPO = 21


def test_cada_tipo_mantenido_tiene_cobertura_suficiente():
    """Avisa por tipo, no solo en conjunto: el calendario puede tener meses
    de RPM cargadas y aun así haberse quedado sin IPC, y la sección quedaría
    coja sin que el chequeo global se entere."""
    hoy = date.today()
    cortos = []
    for tipo, fuente in FUENTE_POR_TIPO.items():
        fechas = [e.fecha_inicio for e in cal.EVENTOS if e.tipo == tipo and e.fecha_inicio >= hoy]
        dias = (max(fechas) - hoy).days if fechas else -1
        if dias < DIAS_MINIMOS_POR_TIPO:
            cortos.append(f"  {tipo}: {'sin eventos futuros' if dias < 0 else f'solo {dias} días'} — recargar desde {fuente}")
    assert not cortos, "Tipos de evento a punto de quedarse sin fechas:\n" + "\n".join(cortos)


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


if __name__ == "__main__":
    test_el_calendario_no_esta_a_punto_de_quedarse_vacio()
    test_cada_tipo_mantenido_tiene_cobertura_suficiente()
    test_la_regla_del_ipc_reproduce_el_calendario_oficial_del_INE()
    test_no_hay_ninguna_fecha_estimada()
    test_no_hay_eventos_duplicados()
    test_el_pie_del_calendario_sale_de_los_datos_y_no_de_un_texto_fijo()
    test_el_dashboard_no_tiene_el_pie_viejo_escrito_a_mano()
    print("OK: las siete pruebas pasaron.")
