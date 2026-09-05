"""Valida la vista aislada del Laboratorio Financiero (?vista=labfin en
app/dashboard.py).

El dashboard lee st.query_params al inicio: si "vista" == "labfin", llama a
render_laboratorio_financiero() y corta con st.stop() ANTES del título, el
sidebar y st.tabs — así un link con ese parámetro muestra solo esa pestaña.
Sin el parámetro (o con cualquier otro valor) el dashboard se comporta como
siempre. NO es autenticación: quitar el parámetro de la URL muestra todo.

Estos tests fijan ese contrato para que no se rompa si alguien reordena el
layout del dashboard más adelante.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

load_dotenv()  # no pisa una DATABASE_URL ya presente en el entorno

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
LAB_HEADER = "Laboratorio Financiero — Frontera Media-Varianza"


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
    """Sin ?vista: título, st.tabs y sidebar presentes, y el Laboratorio
    Financiero igual se renderiza (dentro de su pestaña)."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420).run(timeout=420)
    assert not at.exception, f"La app lanzo una excepcion: {at.exception}"

    assert any("Mercado Económico Chileno" in t.value for t in at.title), "falta el titulo del dashboard"
    assert len(at.get("tab")) > 0, "deberia renderizarse st.tabs en modo normal"
    assert "Última actualización" in _texto_sidebar(at), "falta el sidebar de ultima actualizacion"
    assert LAB_HEADER in _texto_visible(at), "el Laboratorio Financiero deberia renderizarse igual en modo normal"


def test_vista_aislada_labfin_renderiza_solo_el_laboratorio():
    """Con ?vista=labfin: sin título, sin st.tabs, sin sidebar; solo el
    contenido del Laboratorio Financiero, sin errores de variables no
    definidas y sin encabezados de otras pestañas."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.query_params["vista"] = "labfin"
    at.run(timeout=420)
    assert not at.exception, f"La vista aislada lanzo una excepcion: {at.exception}"

    assert [t.value for t in at.title] == [], "en la vista aislada no deberia haber st.title"
    assert len(at.get("tab")) == 0, "en la vista aislada no deberia renderizarse st.tabs"
    assert _texto_sidebar(at).strip() == "", "en la vista aislada el sidebar deberia estar vacio"

    texto = _texto_visible(at)
    assert LAB_HEADER in texto, "la vista aislada no renderizo el Laboratorio Financiero"
    otras_pestanas = [
        "Modelo de Recesión EEUU (Probit)",
        "Simulación Mesa de Dinero",
        "Atribución del retorno diario de ECH",
    ]
    coladas = [p for p in otras_pestanas if p in texto]
    assert not coladas, f"la vista aislada dejo pasar contenido de otras pestanas: {coladas}"


def test_valor_de_vista_desconocido_se_comporta_como_dashboard_normal():
    """Solo ?vista=labfin activa la vista aislada; cualquier otro valor
    cae al dashboard completo."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.query_params["vista"] = "otracosa"
    at.run(timeout=420)
    assert not at.exception, f"?vista=otracosa lanzo una excepcion: {at.exception}"
    assert any("Mercado Económico Chileno" in t.value for t in at.title), "?vista=otracosa deberia mostrar el dashboard normal"
    assert len(at.get("tab")) > 0, "?vista=otracosa deberia renderizar st.tabs"


if __name__ == "__main__":
    test_dashboard_normal_sin_query_param()
    test_vista_aislada_labfin_renderiza_solo_el_laboratorio()
    test_valor_de_vista_desconocido_se_comporta_como_dashboard_normal()
    print("OK: las tres pruebas pasaron.")
