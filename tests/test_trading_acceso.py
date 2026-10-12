"""La pestaña Divisas no se abre sin contraseña.

QUÉ PROTEGE. Esa pestaña muestra el diario, el equity, los planes y las
tesis; el resto del dashboard es público. Lo que se verifica acá no es que
"aparezca un formulario", sino la propiedad que importa: que SIN la
contraseña correcta no se ejecute ni una sola consulta a las tablas del
módulo. Si se consultara primero y se protegiera después, los datos
quedarían en la caché del proceso —que es compartida entre visitantes—
aunque la pantalla no los dibuje.

LA CONTRASEÑA REAL NO APARECE ACÁ. Estas pruebas definen una de juguete en
la variable de entorno, la usan y la borran. No leen ni escriben la de
producción, y ninguna prueba toca la base de datos.
"""
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import pytest
from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

load_dotenv()

import trading_acceso
from trading_acceso import (
    MAX_INTENTOS,
    SEGUNDOS_BLOQUEO,
    VARIABLE_ENTORNO,
    estado_bloqueo,
    password_configurada,
    reiniciar_estado,
    verificar,
)

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
# De juguete, solo para las pruebas. No es la de producción.
CLAVE_DE_PRUEBA = "clave-de-prueba-no-es-la-real"
TABLAS_DEL_MODULO = ("trading_instrumentos", "trading_operaciones",
                     "trading_estado_cuenta", "evento_planes", "evento_checklist",
                     "trading_revision_semanal")


@pytest.fixture(autouse=True)
def _estado_limpio():
    """Cada prueba parte sin bloqueo y sin contraseña configurada."""
    original = os.environ.get(VARIABLE_ENTORNO)
    os.environ.pop(VARIABLE_ENTORNO, None)
    reiniciar_estado()
    yield
    reiniciar_estado()
    if original is None:
        os.environ.pop(VARIABLE_ENTORNO, None)
    else:
        os.environ[VARIABLE_ENTORNO] = original


# --------------------------------------------------------- lógica pura
def test_sin_variable_configurada_no_entra_ni_con_cadena_vacia():
    """Falla CERRADA: sin la variable no se abre de ninguna manera."""
    assert not password_configurada()
    for intento in ("", "lo que sea", CLAVE_DE_PRUEBA):
        acerto, motivo = verificar(intento)
        assert not acerto, f"entró con {intento!r} sin la variable configurada"
        assert VARIABLE_ENTORNO in motivo


def test_una_variable_vacia_cuenta_como_no_configurada():
    os.environ[VARIABLE_ENTORNO] = "   "
    assert not password_configurada()
    assert not verificar("")[0]


def test_la_contrasena_correcta_entra_y_la_incorrecta_no():
    os.environ[VARIABLE_ENTORNO] = CLAVE_DE_PRUEBA
    assert password_configurada()
    assert verificar(CLAVE_DE_PRUEBA)[0]
    assert not verificar(CLAVE_DE_PRUEBA + "x")[0]
    assert not verificar(CLAVE_DE_PRUEBA.upper())[0]
    assert not verificar("")[0]


def test_el_motivo_nunca_revela_la_contrasena():
    """Un mensaje de error que filtre la contraseña o el intento la haría
    aparecer en los logs del servidor."""
    os.environ[VARIABLE_ENTORNO] = CLAVE_DE_PRUEBA
    intento = "intento-secreto-del-visitante"
    _acerto, motivo = verificar(intento)
    assert CLAVE_DE_PRUEBA not in motivo
    assert intento not in motivo


def test_el_limite_de_intentos_es_del_servidor_y_no_de_la_sesion():
    """Si el contador viviera en la sesión, abrir una pestaña nueva lo
    reiniciaría y el límite no serviría de nada. Es de módulo, así que lo
    comparten todos los visitantes del mismo proceso."""
    os.environ[VARIABLE_ENTORNO] = CLAVE_DE_PRUEBA

    for i in range(MAX_INTENTOS - 1):
        acerto, motivo = verificar("mala")
        assert not acerto
        assert "Quedan" in motivo, motivo
        assert not estado_bloqueo()[0], f"se bloqueó antes de tiempo, al intento {i+1}"

    acerto, motivo = verificar("mala")
    assert not acerto
    assert str(SEGUNDOS_BLOQUEO) in motivo, motivo
    bloqueado, restante = estado_bloqueo()
    assert bloqueado and 0 < restante <= SEGUNDOS_BLOQUEO + 1

    # durante el bloqueo, NI SIQUIERA la contraseña correcta entra
    acerto, motivo = verificar(CLAVE_DE_PRUEBA)
    assert not acerto, "el bloqueo se saltea con la contraseña correcta"
    assert "intentos fallidos" in motivo


def test_el_bloqueo_se_levanta_solo_al_pasar_el_tiempo():
    os.environ[VARIABLE_ENTORNO] = CLAVE_DE_PRUEBA
    base = time.time()
    for _ in range(MAX_INTENTOS):
        verificar("mala", ahora=base)
    assert estado_bloqueo(base)[0]
    assert not estado_bloqueo(base + SEGUNDOS_BLOQUEO + 1)[0]
    assert verificar(CLAVE_DE_PRUEBA, ahora=base + SEGUNDOS_BLOQUEO + 1)[0]


def test_un_acierto_reinicia_el_contador():
    os.environ[VARIABLE_ENTORNO] = CLAVE_DE_PRUEBA
    for _ in range(MAX_INTENTOS - 1):
        verificar("mala")
    assert trading_acceso.intentos_fallidos() == MAX_INTENTOS - 1
    assert verificar(CLAVE_DE_PRUEBA)[0]
    assert trading_acceso.intentos_fallidos() == 0


# ------------------------------------------------------------- AppTest
def _correr_divisas(password_env=None, intento=None):
    if password_env is None:
        os.environ.pop(VARIABLE_ENTORNO, None)
    else:
        os.environ[VARIABLE_ENTORNO] = password_env
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = "Divisas"
    at.run(timeout=420)
    if intento is not None:
        at.text_input(key="trd_password").set_value(intento)
        [b for b in at.button if "Entrar" in str(b.label)][0].click().run(timeout=420)
    return at


def _texto(at):
    partes = []
    for attr in ("markdown", "caption", "info", "warning", "error", "subheader"):
        for el in getattr(at, attr, []):
            partes.append(str(getattr(el, "value", "")))
    return " || ".join(partes)


def test_sin_la_variable_la_pestana_no_se_abre():
    at = _correr_divisas(password_env=None)
    assert not at.exception, at.exception
    texto = _texto(at)
    assert "no está disponible" in texto, texto[:300]
    assert VARIABLE_ENTORNO in texto
    assert "Diario de operaciones" not in texto, "se dibujó contenido sin contraseña"


def test_con_la_variable_pero_sin_contrasena_no_se_ve_nada():
    at = _correr_divisas(password_env=CLAVE_DE_PRUEBA)
    assert not at.exception, at.exception
    texto = _texto(at)
    assert "Esta sección es privada" in texto, texto[:300]
    for prohibido in ("Diario de operaciones", "Estadísticas del proceso",
                      "Control de reglas", "Estado de la cuenta"):
        assert prohibido not in texto, f"se filtró {prohibido!r} sin contraseña"


def test_con_contrasena_incorrecta_tampoco():
    at = _correr_divisas(password_env=CLAVE_DE_PRUEBA, intento="esta-no-es")
    assert not at.exception, at.exception
    texto = _texto(at)
    assert "incorrecta" in texto.lower(), texto[:300]
    assert "Diario de operaciones" not in texto


def test_con_la_contrasena_correcta_si_se_abre():
    at = _correr_divisas(password_env=CLAVE_DE_PRUEBA, intento=CLAVE_DE_PRUEBA)
    assert not at.exception, at.exception
    texto = _texto(at)
    assert "Diario de operaciones" in texto, texto[:400]
    assert "Control de reglas del torneo" in texto
    assert any("Cerrar sesión" in str(b.label) for b in at.button), "falta el botón de salir"


def test_las_otras_pestanas_se_ven_sin_contrasena():
    """El dashboard sigue público: la contraseña es solo de Divisas."""
    os.environ.pop(VARIABLE_ENTORNO, None)
    for seccion, marca in [("Brief Premercado", "Economic calendar"),
                           ("Riesgo", "VaR")]:
        at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
        at.session_state["seccion_activa"] = seccion
        at.run(timeout=420)
        assert not at.exception, f"{seccion}: {at.exception}"
        assert marca in _texto(at), f"{seccion} no cargó sin contraseña"


def test_sin_contrasena_no_se_consulta_ninguna_tabla_del_modulo(monkeypatch):
    """LA PRUEBA QUE IMPORTA.

    No alcanza con que la pantalla no dibuje el diario: los cargadores están
    cacheados con @st.cache_data y esa caché es del PROCESO, compartida entre
    visitantes. Si se consultara primero y se protegiera después, los datos
    quedarían en memoria del servidor igual. Así que se cuenta cuántas
    consultas a las tablas del módulo llegan a ejecutarse.
    """
    consultas = []
    real = pd.read_sql

    def espia(sql, *a, **kw):
        texto = str(sql)
        if any(t in texto for t in TABLAS_DEL_MODULO):
            consultas.append(texto[:60])
        return real(sql, *a, **kw)

    monkeypatch.setattr(pd, "read_sql", espia)

    # sin la variable configurada
    _correr_divisas(password_env=None)
    assert consultas == [], f"consultó la base sin contraseña: {consultas}"

    # con la variable pero sin entrar
    consultas.clear()
    _correr_divisas(password_env=CLAVE_DE_PRUEBA)
    assert consultas == [], f"consultó la base sin desbloquear: {consultas}"

    # con contraseña incorrecta
    consultas.clear()
    _correr_divisas(password_env=CLAVE_DE_PRUEBA, intento="esta-no-es")
    assert consultas == [], f"consultó la base con contraseña incorrecta: {consultas}"

    # y con la correcta SÍ consulta
    consultas.clear()
    _correr_divisas(password_env=CLAVE_DE_PRUEBA, intento=CLAVE_DE_PRUEBA)
    assert consultas, "con la contraseña correcta debería consultar las tablas"


def test_la_exportacion_a_csv_no_existe_sin_contrasena():
    at = _correr_divisas(password_env=CLAVE_DE_PRUEBA)
    etiquetas = [str(b.label) for b in at.button]
    assert not any("CSV" in e for e in etiquetas), (
        f"el botón de exportar quedó accesible sin contraseña: {etiquetas}")


if __name__ == "__main__":
    print("Correr con pytest: python -m pytest tests/test_trading_acceso.py")
