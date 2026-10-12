"""La hora que se escribe en el formulario es la que queda guardada.

EL RIESGO QUE CUBRE. Los selectores de hora se inicializan con la hora actual
de Chile. Si ese valor por defecto cambiara entre recargas —y llamando a
now() cambia siempre, por los segundos— Streamlit podría tratarlo como un
widget distinto y reemplazar lo que el usuario escribió por la hora actual
justo al enviar. En un diario de operaciones eso registra una hora falsa sin
que nadie lo note, y la hora es lo que define la regla de los 2 minutos del
torneo. Por eso la hora inicial se trunca al minuto y se calcula una sola vez
por sesión; este test comprueba el efecto, no la implementación.

ESTE TEST ESCRIBE EN LA BASE. No puede usar una transacción revertida porque
quien escribe es la app, con su propia conexión. En su lugar marca la fila
con una nota única, la borra en un `finally` pase lo que pase, y al terminar
verifica que el diario volvió a tener exactamente las filas que tenía antes.
"""
import os
import sys
import uuid

import pytest
from datetime import time
from zoneinfo import ZoneInfo

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

load_dotenv()

from models import get_engine

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
TZ_CHILE = ZoneInfo("America/Santiago")

# Una hora deliberadamente distinta de "ahora": si el formulario la pisara con
# la hora actual, la diferencia saltaría a la vista.
HORA_ESCRITA = time(3, 17)


def _contar(conn):
    return conn.execute(text("SELECT COUNT(*) FROM trading_operaciones")).scalar()


def _saltar_si_hay_operaciones_reales():
    """Un test no tiene por qué poder tocar el diario real.

    Mientras el diario esté vacío, escribir y borrar la propia fila es
    inocuo. Apenas haya operaciones de verdad, el riesgo de que una limpieza
    mal escrita se lleve una por delante deja de valer la pena: el test se
    salta y lo dice.
    """
    with get_engine().connect() as con:
        reales = con.execute(text(
            "SELECT COUNT(*) FROM trading_operaciones "
            "WHERE notas IS NULL OR notas NOT LIKE 'prueba-%'"
        )).scalar()
    if reales:
        pytest.skip(
            f"el diario tiene {reales} operación(es) real(es): este test no escribe "
            f"en la base para no arriesgarlas. Corrélo con el diario vacío.")


def test_la_hora_escrita_en_el_formulario_es_la_que_se_guarda():
    marca = f"prueba-{uuid.uuid4().hex[:12]}"
    engine = get_engine()
    _saltar_si_hay_operaciones_reales()
    with engine.connect() as con:
        antes = _contar(con)
    id_creado = None

    try:
        at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
        at.session_state["seccion_activa"] = "Divisas"
        at.run(timeout=420)
        assert not at.exception, at.exception

        at.number_input(key="trd_op_entrada").set_value(1.1234)
        at.number_input(key="trd_op_lotes").set_value(0.01)
        at.time_input(key="trd_op_hora_ap").set_value(HORA_ESCRITA)
        at.text_area(key="trd_op_notas").set_value(marca)
        fecha_escrita = at.date_input(key="trd_op_fecha_ap").value

        # Enviar el formulario
        enviar = [b for b in at.button if "Guardar operación" in str(b.label)]
        assert enviar, [str(b.label) for b in at.button]
        enviar[0].click().run(timeout=420)
        assert not at.exception, at.exception

        with engine.connect() as con:
            fila = con.execute(text(
                "SELECT id, fecha_apertura FROM trading_operaciones WHERE notas = :m"
            ), {"m": marca}).fetchone()
        assert fila is not None, "el formulario no guardó la operación"
        id_creado = fila[0]

        guardada = fila[1].astimezone(TZ_CHILE)
        assert (guardada.hour, guardada.minute) == (HORA_ESCRITA.hour, HORA_ESCRITA.minute), (
            f"se escribió {HORA_ESCRITA} y quedó guardada {guardada:%H:%M} "
            f"(hora de Chile): el formulario pisó la hora del usuario")
        assert guardada.date() == fecha_escrita, (
            f"se escribió la fecha {fecha_escrita} y quedó {guardada.date()}")
    finally:
        # Solo la fila de este test: por su marca única y, si se alcanzó a
        # leer, por su id exacto. Nunca por un rango de ids, que se llevaría
        # por delante cualquier operación real registrada mientras corría.
        with engine.begin() as con:
            con.execute(text("DELETE FROM trading_operaciones WHERE notas = :m"),
                        {"m": marca})
            if id_creado is not None:
                con.execute(text("DELETE FROM trading_operaciones WHERE id = :i"),
                            {"i": id_creado})

    with engine.connect() as con:
        despues = _contar(con)
    assert despues == antes, (
        f"el diario quedó con {despues} filas y antes tenía {antes}: la limpieza falló")


def test_la_hora_inicial_no_cambia_entre_recargas():
    """La causa raíz, aparte del efecto: si el valor por defecto se
    recalculara en cada rerun, el widget cambiaría de identidad."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = "Divisas"
    at.run(timeout=420)
    primera = at.session_state["trd_hora_inicial"]
    assert primera.second == 0 and primera.microsecond == 0, (
        f"la hora inicial debe venir truncada al minuto, vino {primera!r}")

    at.run(timeout=420)
    assert at.session_state["trd_hora_inicial"] == primera, (
        "la hora inicial cambió entre recargas: el widget puede perder lo que "
        "el usuario escribió")


if __name__ == "__main__":
    test_la_hora_escrita_en_el_formulario_es_la_que_se_guarda()
    test_la_hora_inicial_no_cambia_entre_recargas()
    print("OK: las dos pruebas pasaron.")


def test_el_boton_ahora_actualiza_la_hora_por_defecto():
    """El efecto secundario de fijar la hora una vez por sesión: con la
    página abierta varias horas, el valor por defecto envejece y se podría
    registrar una hora equivocada sin notarlo. El botón "Ahora" existe para
    eso, y acá se comprueba que de verdad la mueve."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = "Divisas"
    at.run(timeout=420)
    assert not at.exception, at.exception

    # Se simula una sesión vieja: la hora por defecto quedó horas atrás.
    vieja = at.session_state["trd_hora_inicial"].replace(hour=3, minute=17)
    at.session_state["trd_hora_inicial"] = vieja
    at.session_state["trd_op_hora_ap"] = vieja.time()
    at.run(timeout=420)
    assert at.time_input(key="trd_op_hora_ap").value == vieja.time()

    botones = [b for b in at.button if "Ahora" in str(b.label)]
    assert botones, f"falta el botón Ahora: {[str(b.label) for b in at.button]}"
    botones[0].click().run(timeout=420)
    assert not at.exception, at.exception

    actualizada = at.session_state["trd_hora_inicial"]
    assert actualizada != vieja, "el botón no movió la hora"
    assert actualizada.second == 0 and actualizada.microsecond == 0, actualizada
    assert at.time_input(key="trd_op_hora_ap").value == actualizada.time(), (
        "el botón actualizó la hora interna pero no el selector que ve la usuaria")


def test_el_aviso_de_hora_vieja_esta_visible():
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = "Divisas"
    at.run(timeout=420)
    textos = " ".join(str(c.value) for c in at.caption)
    assert "cuando abriste la página" in textos, textos[:300]
    assert "Revisala" in textos or "revisala" in textos.lower(), textos[:300]


def test_no_quedan_filas_de_prueba_en_el_diario_real():
    """Red de seguridad de todo el archivo: ninguna prueba debe dejar
    operaciones inventadas en el diario que la usuaria va a presentar."""
    with get_engine().connect() as con:
        # Solo por la marca: un precio o una fecha "de prueba" podrían ser
        # perfectamente una operación real de la usuaria.
        sospechosas = con.execute(text(
            "SELECT id, instrumento, notas FROM trading_operaciones "
            "WHERE notas LIKE 'prueba-%'"
        )).fetchall()
    assert not sospechosas, f"quedaron filas de prueba: {sospechosas}"
