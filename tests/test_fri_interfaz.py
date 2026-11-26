"""F0/F1: interfaz FRI sobre el dashboard existente (offline, sin base).

QUÉ SE PRUEBA
    - El interruptor: por defecto la interfaz clásica; FRI solo con FRI_INTERFAZ=fri; ?ui=clasica vuelve a la clásica,
      y con «clasica» configurado ?ui=fri no activa FRI.
    - Ninguna sección del dashboard se pierde: cada una está en una pestaña de FRI o sigue en la interfaz clásica.
    - navegar() devuelve exactamente el nombre de la sección existente que corresponde (el dashboard ejecuta el mismo
      código de siempre) y None en las pestañas sin sección todavía, mostrando que están pendientes.
    - Inicio no lleva barra superior; las secciones interiores sí, sin campana.
    - La interfaz no trae datos propios: no importa módulos de datos sintéticos.
La comparación completa antes/después de las 14 secciones (base local sintética) se hace con app/fri_local.py.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import ast
import os
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(RAIZ)

import fri.interfaz as fri  # noqa: E402

FUENTE = open(os.path.join(RAIZ, "app", "dashboard.py"), encoding="utf-8").read()


def _secciones_del_selector() -> list[str]:
    arbol = ast.parse(FUENTE)
    valores = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name) and nodo.targets[0].id in (
                "SECCIONES_TODAS", "SECCIONES_FUERA_DEL_SELECTOR"):
            valores[nodo.targets[0].id] = ast.literal_eval(nodo.value)
    return [s for s in valores["SECCIONES_TODAS"] if s not in valores["SECCIONES_FUERA_DEL_SELECTOR"]]


# ---------------------------------------------------------------------------
# Interruptor
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("valor, esperado", [(None, "clasica"), ("clasica", "clasica"), ("fri", "fri"), (" FRI ", "fri"),
                                             ("otra", "clasica"), ("", "clasica")])
def test_el_modo_por_defecto_es_la_interfaz_clasica(monkeypatch, valor, esperado):
    monkeypatch.delenv("FRI_INTERFAZ", raising=False)
    if valor is not None:
        monkeypatch.setenv("FRI_INTERFAZ", valor)
    assert fri.modo_configurado() == esperado


@pytest.mark.parametrize("configurado, ui, activo", [
    ("clasica", None, False), ("clasica", "fri", False),     # producción no cambia aunque alguien agregue ?ui=fri
    ("fri", None, True), ("fri", "fri", True), ("fri", "clasica", False), ("fri", "CLASICA", False),
])
def test_el_parametro_ui_solo_permite_volver_a_la_clasica(monkeypatch, configurado, ui, activo):
    monkeypatch.setenv("FRI_INTERFAZ", configurado)
    assert fri.modo_activo({} if ui is None else {"ui": ui}) is activo


def test_el_dashboard_conserva_la_interfaz_clasica_por_defecto():
    assert "_MODO_FRI = fri_ui.modo_activo(st.query_params) and not _SOLO_LABFIN" in FUENTE
    assert 'if _MODO_FRI:\n    # La interfaz FRI elige la sección' in FUENTE
    assert '"Sección", SECCIONES, default=SECCIONES[0], key="seccion_activa"' in FUENTE


# ---------------------------------------------------------------------------
# Ninguna sección se pierde
# ---------------------------------------------------------------------------
def test_cada_seccion_esta_en_fri_o_sigue_en_la_interfaz_clasica():
    secciones = _secciones_del_selector()
    assert len(secciones) == 14
    cubiertas, solo_clasica = fri.secciones_cubiertas(), set(fri.SOLO_INTERFAZ_CLASICA)
    assert not cubiertas & solo_clasica
    assert set(secciones) == cubiertas | solo_clasica
    assert {"Indicadores macro", "Renta Variable y ETFs", "Renta Fija", "FX y Carry Trade", "Commodities", "Riesgo", "Derivados"} <= cubiertas


# ---------------------------------------------------------------------------
# navegar()
# ---------------------------------------------------------------------------
def _app(seccion, pestaña, apartado):
    import os
    import streamlit as st
    import pandas as pd
    import fri.interfaz as fri
    os.environ["FRI_INTERFAZ"] = "fri"
    st.query_params["s"] = seccion
    if pestaña:
        st.session_state.setdefault(f"fri_pestana_{seccion}", pestaña)
    if apartado:
        st.session_state.setdefault(f"fri_apartado_{seccion}_{pestaña}", apartado)
    meta = pd.DataFrame({"fuente": ["bcch"], "ultima_actualizacion": [pd.Timestamp("2026-11-24 21:00")]})
    st.session_state["_devuelta"] = fri.navegar(lambda: meta, "Autora de prueba")


def _correr(seccion, pestaña=None, apartado=None) -> AppTest:
    at = AppTest.from_function(_app, args=(seccion, pestaña, apartado), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.mark.parametrize("seccion, pestaña, apartado, esperada", [
    ("macro", "Panorama general", None, "Indicadores macro"),
    ("mercados", "Renta variable", "Acciones IPSA", "Acciones IPSA"),
    ("mercados", "Renta variable", "Comparación internacional", "Benchmark"),
    ("mercados", "Renta fija", None, "Renta Fija"),
    ("mercados", "Divisas", None, "FX y Carry Trade"),
    ("mercados", "Materias primas", None, "Commodities"),
    ("riesgo", "Análisis de riesgo", None, "Riesgo"),
    ("riesgo", "Derivados", None, "Derivados"),
])
def test_cada_pestana_conectada_devuelve_la_seccion_existente(seccion, pestaña, apartado, esperada):
    assert _correr(seccion, pestaña, apartado).session_state["_devuelta"] == esperada


@pytest.mark.parametrize("seccion, pestaña", [("macro", "Inflación"), ("riesgo", "Correlaciones y diversificación"),
                                               ("investigacion", "Investigador"), ("informes", None)])
def test_las_pestanas_sin_seccion_dicen_que_estan_pendientes(seccion, pestaña):
    at = _correr(seccion, pestaña)
    assert at.session_state["_devuelta"] is None
    assert any("PENDIENTE DE IMPLEMENTACIÓN" in m.value for m in at.markdown)


def test_inicio_sin_barra_superior_y_secciones_interiores_con_barra_sin_campana():
    inicio = _correr("inicio")
    assert inicio.session_state["_devuelta"] is None
    assert not any('<div class="fri-barra">' in m.value for m in inicio.markdown)
    assert any("Financial Research<br>Intelligence" in m.value for m in inicio.markdown)
    interior = _correr("mercados", "Renta fija")
    barra = [m.value for m in interior.markdown if '<div class="fri-barra">' in m.value]
    assert barra and "campana" not in barra[0] and "PENDIENTE" in barra[0]
    assert any("Última actualización<br>BCCh: 24-11-2026 21:00" in m.value for m in interior.markdown if 'class="fri-encabezado"' in m.value)


def test_la_interfaz_no_trae_datos_propios():
    carpeta = os.path.join(RAIZ, "fri")
    for archivo in os.listdir(carpeta):
        if archivo.endswith(".py"):
            texto = open(os.path.join(carpeta, archivo), encoding="utf-8").read()
            assert "datos_sinteticos" not in texto and "read_sql" not in texto and "get_engine" not in texto, archivo


# ---------------------------------------------------------------------------
# Controles de acceso: FRI no abre ninguna sección protegida ni oculta
# ---------------------------------------------------------------------------
def test_fri_nunca_devuelve_secciones_ocultas_o_protegidas_con_contrasena():
    arbol = ast.parse(FUENTE)
    ocultas = next(ast.literal_eval(n.value) for n in arbol.body if isinstance(n, ast.Assign)
                   and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "SECCIONES_FUERA_DEL_SELECTOR")
    assert set(ocultas) == {"Divisas", "Simulación Mesa de Dinero", "Defensa Top-Down"}   # las tres con contraseña
    assert not set(ocultas) & (fri.secciones_cubiertas() | set(fri.SOLO_INTERFAZ_CLASICA))


@pytest.mark.parametrize("seccion", ["Divisas", "defensa", "Defensa Top-Down", "mesa", "../", "Riesgo", "inicio'><script>"])
def test_un_parametro_de_url_desconocido_lleva_a_inicio(seccion):
    at = _correr(seccion)
    assert at.session_state["_devuelta"] is None
    assert any("Financial Research<br>Intelligence" in m.value for m in at.markdown)
