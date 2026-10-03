"""Valida la vista aislada del Laboratorio Financiero (?vista=labfin en
app/dashboard.py).

El dashboard lee st.query_params al inicio: si "vista" == "labfin", llama a
render_laboratorio_financiero() y corta con st.stop() ANTES del título, el
sidebar y el selector de secciones — así un link con ese parámetro muestra
solo esa sección. Sin el parámetro (o con cualquier otro valor) el dashboard
se comporta como siempre. NO es autenticación: quitar el parámetro de la URL
muestra todo.

Estos tests fijan ese contrato para que no se rompa si alguien reordena el
layout del dashboard más adelante.

El marcador de "dashboard completo" es el st.segmented_control de secciones.
Antes era st.tabs, pero se reemplazó porque st.tabs ejecuta el cuerpo de las
once secciones en cada rerun; el selector ejecuta solo la activa. Como
consecuencia, para ver el contenido de una sección hay que fijar
session_state["seccion_activa"] antes de correr.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

load_dotenv()  # no pisa una DATABASE_URL ya presente en el entorno

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
LAB_HEADER = "Laboratorio Financiero — Frontera Media-Varianza"
SECCION_LABFIN = "Laboratorio Financiero"
AUTORA_ESPERADA = "Belén Muñoz Garvizo"


def _texto_visible(at):
    partes = []
    for attr in ("title", "header", "subheader", "markdown", "caption", "info", "error", "warning"):
        for el in getattr(at, attr):
            partes.append(str(getattr(el, "value", "")))
    return " || ".join(partes)


def _texto_sidebar(at):
    partes = []
    for attr in ("subheader", "text", "markdown", "caption", "warning"):
        for el in getattr(at.sidebar, attr, []):
            partes.append(str(getattr(el, "value", "")))
    return " || ".join(partes)


def test_dashboard_normal_sin_query_param():
    """Sin ?vista: título, selector de secciones y sidebar presentes, y el
    Laboratorio Financiero igual se renderiza al seleccionar su sección."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = SECCION_LABFIN
    at.run(timeout=420)
    assert not at.exception, f"La app lanzo una excepcion: {at.exception}"

    assert any("Mercado Económico Chileno" in t.value for t in at.title), "falta el titulo del dashboard"
    assert len(at.segmented_control) > 0, "deberia renderizarse el selector de secciones en modo normal"
    assert "Última actualización" in _texto_sidebar(at), "falta el sidebar de ultima actualizacion"
    assert LAB_HEADER in _texto_visible(at), "el Laboratorio Financiero deberia renderizarse igual en modo normal"


def test_vista_aislada_labfin_renderiza_solo_el_laboratorio():
    """Con ?vista=labfin: sin título, sin selector de secciones, sin
    sidebar; solo el contenido del Laboratorio Financiero, sin errores de
    variables no definidas y sin encabezados de otras secciones."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.query_params["vista"] = "labfin"
    at.run(timeout=420)
    assert not at.exception, f"La vista aislada lanzo una excepcion: {at.exception}"

    assert [t.value for t in at.title] == [], "en la vista aislada no deberia haber st.title"
    assert len(at.segmented_control) == 0, "en la vista aislada no deberia renderizarse el selector de secciones"
    assert _texto_sidebar(at).strip() == "", "en la vista aislada el sidebar deberia estar vacio"

    texto = _texto_visible(at)
    assert LAB_HEADER in texto, "la vista aislada no renderizo el Laboratorio Financiero"
    otras_secciones = [
        "Modelo de Recesión EEUU (Probit)",
        "Simulación Mesa de Dinero",
        "Atribución del retorno diario de ECH",
    ]
    coladas = [p for p in otras_secciones if p in texto]
    assert not coladas, f"la vista aislada dejo pasar contenido de otras secciones: {coladas}"


def test_la_autoria_aparece_en_el_sidebar():
    """El crédito de autoría va al pie del sidebar, así que se ve en todas
    las secciones. Si alguien reordena el sidebar y lo pierde, esto falla."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420).run(timeout=420)
    assert not at.exception, f"La app lanzo una excepcion: {at.exception}"

    texto = _texto_sidebar(at)
    # El nombre va literal y no importado de app.dashboard: importar ese
    # módulo ejecutaría el script entero fuera de Streamlit, y además un test
    # que compara la constante consigo misma pasaría aunque el nombre quedara
    # mal escrito.
    assert AUTORA_ESPERADA in texto, (
        f"falta el crédito de autoría ({AUTORA_ESPERADA!r}) en el sidebar. Texto del "
        f"sidebar: {texto[:300]!r}"
    )
    assert "Creado por" in texto, "falta la frase 'Creado por' junto al nombre"


def test_la_autoria_no_se_cuela_en_la_vista_aislada():
    """La vista ?vista=labfin no tiene sidebar: es un link para mostrar solo
    el Laboratorio Financiero, y su contrato es que no renderiza nada del
    layout normal."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.query_params["vista"] = "labfin"
    at.run(timeout=420)
    assert not at.exception, f"La vista aislada lanzo una excepcion: {at.exception}"
    assert _texto_sidebar(at).strip() == "", (
        "la vista aislada no debería mostrar el sidebar, ni siquiera la autoría"
    )


def test_valor_de_vista_desconocido_se_comporta_como_dashboard_normal():
    """Solo ?vista=labfin activa la vista aislada; cualquier otro valor
    cae al dashboard completo."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.query_params["vista"] = "otracosa"
    at.run(timeout=420)
    assert not at.exception, f"?vista=otracosa lanzo una excepcion: {at.exception}"
    assert any("Mercado Económico Chileno" in t.value for t in at.title), "?vista=otracosa deberia mostrar el dashboard normal"
    assert len(at.segmented_control) > 0, "?vista=otracosa deberia renderizar el selector de secciones"


if __name__ == "__main__":
    test_dashboard_normal_sin_query_param()
    test_vista_aislada_labfin_renderiza_solo_el_laboratorio()
    test_la_autoria_aparece_en_el_sidebar()
    test_la_autoria_no_se_cuela_en_la_vista_aislada()
    test_valor_de_vista_desconocido_se_comporta_como_dashboard_normal()
    print("OK: las cinco pruebas pasaron.")
