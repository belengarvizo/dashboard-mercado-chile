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


def test_el_formulario_no_pisa_la_hora_que_se_escribio():
    """La propiedad que importa, verificada SIN escribir en la base.

    Si el valor por defecto de un st.time_input cambiara entre reruns,
    Streamlit podría tratarlo como un widget nuevo y reemplazar la hora
    escrita por la actual justo al enviar. Acá se escribe una hora
    deliberadamente lejos de "ahora", se fuerza un rerun tocando otro widget,
    y se comprueba que la hora escrita sigue ahí.

    La otra mitad del problema —que lo que se guarda en la base conserve la
    zona horaria— la cubre tests/test_trading_zona_horaria.py con una
    transacción revertida. Partirlo así es lo que permite que NINGUNA prueba
    confirme escrituras en el diario real."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = "Divisas"
    # La pestaña ahora pide contraseña. Estas pruebas son del CONTENIDO, no
    # de la puerta: se desbloquea por session_state para no depender de una
    # variable de entorno. La puerta tiene sus propias pruebas en
    # tests/test_trading_acceso.py.
    at.session_state["trd_desbloqueado"] = True
    at.run(timeout=420)
    assert not at.exception, at.exception

    at.time_input(key="trd_op_hora_ap").set_value(HORA_ESCRITA)
    at.number_input(key="trd_op_entrada").set_value(1.2345).run(timeout=420)
    assert not at.exception, at.exception

    quedo = at.time_input(key="trd_op_hora_ap").value
    assert (quedo.hour, quedo.minute) == (HORA_ESCRITA.hour, HORA_ESCRITA.minute), (
        f"se escribió {HORA_ESCRITA} y tras un rerun el selector quedó en {quedo}: "
        f"el formulario está pisando la hora de la usuaria")


def test_ninguna_prueba_de_este_archivo_escribe_en_el_diario():
    """Red de seguridad explícita: este archivo trabaja solo con AppTest y
    lecturas. Si alguien agrega una escritura, que se note acá."""
    with open(__file__, encoding="utf-8") as f:
        codigo = f.read()
    # Los literales se arman por partes: si estuvieran enteros, este test se
    # encontraría a sí mismo y fallaría siempre.
    tabla = "trading_" + "operaciones"
    for prohibido in (f"INSERT INTO {tabla}", f"DELETE FROM {tabla}", f"UPDATE {tabla}"):
        assert prohibido not in codigo, (
            f"este archivo volvió a escribir en el diario real ({prohibido!r}). "
            f"Las pruebas que necesiten escribir van en test_trading_zona_horaria.py, "
            f"dentro de una transacción revertida.")


def test_la_hora_inicial_no_cambia_entre_recargas():
    """La causa raíz, aparte del efecto: si el valor por defecto se
    recalculara en cada rerun, el widget cambiaría de identidad."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = "Divisas"
    # La pestaña ahora pide contraseña. Estas pruebas son del CONTENIDO, no
    # de la puerta: se desbloquea por session_state para no depender de una
    # variable de entorno. La puerta tiene sus propias pruebas en
    # tests/test_trading_acceso.py.
    at.session_state["trd_desbloqueado"] = True
    at.run(timeout=420)
    primera = at.session_state["trd_hora_inicial"]
    assert primera.second == 0 and primera.microsecond == 0, (
        f"la hora inicial debe venir truncada al minuto, vino {primera!r}")

    at.run(timeout=420)
    assert at.session_state["trd_hora_inicial"] == primera, (
        "la hora inicial cambió entre recargas: el widget puede perder lo que "
        "el usuario escribió")


if __name__ == "__main__":
    test_el_formulario_no_pisa_la_hora_que_se_escribio()
    test_ninguna_prueba_de_este_archivo_escribe_en_el_diario()
    test_la_hora_inicial_no_cambia_entre_recargas()
    print("OK: las dos pruebas pasaron.")


def test_el_boton_ahora_actualiza_la_hora_por_defecto():
    """El efecto secundario de fijar la hora una vez por sesión: con la
    página abierta varias horas, el valor por defecto envejece y se podría
    registrar una hora equivocada sin notarlo. El botón "Ahora" existe para
    eso, y acá se comprueba que de verdad la mueve."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = "Divisas"
    # La pestaña ahora pide contraseña. Estas pruebas son del CONTENIDO, no
    # de la puerta: se desbloquea por session_state para no depender de una
    # variable de entorno. La puerta tiene sus propias pruebas en
    # tests/test_trading_acceso.py.
    at.session_state["trd_desbloqueado"] = True
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
    # La pestaña ahora pide contraseña. Estas pruebas son del CONTENIDO, no
    # de la puerta: se desbloquea por session_state para no depender de una
    # variable de entorno. La puerta tiene sus propias pruebas en
    # tests/test_trading_acceso.py.
    at.session_state["trd_desbloqueado"] = True
    at.run(timeout=420)
    textos = " ".join(str(c.value) for c in at.caption)
    assert "cuando abriste la página" in textos, textos[:300]
    # "Revísala" con tilde: el texto se corrigió a tuteo chileno (antes decía
    # "Revisala", voseo). La comparación se hace sin tildes para que una
    # corrección de acentuación no vuelva a romper el test.
    import unicodedata
    plano = "".join(c for c in unicodedata.normalize("NFD", textos.lower())
                    if unicodedata.category(c) != "Mn")
    assert "revisala" in plano, textos[:300]


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
