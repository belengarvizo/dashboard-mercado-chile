"""F3: Inicio e Informes de FRI (offline, datos de PRUEBA construidos aquí).

QUÉ SE PRUEBA
    - El informe dominical muestra su estado real (no implementado, sin ediciones) y sus botones están inactivos.
    - El archivo no muestra ediciones ficticias.
    - El informe especializado de renta fija es el EXISTENTE (mismo botón de renta_fija_ui) y se rotula como no dominical;
      sin datos, dice «No disponible» en vez de armar un PDF incompleto.
    - Inicio: «En foco» no publica textos ficticios y muestra el estado real del informe y la fecha de los datos.
    - La interfaz no activa tareas programadas ni Gemini.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import sys

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(RAIZ)


def _app(pestaña, con_precios):
    import os
    import numpy as np
    import pandas as pd
    import streamlit as st
    import fri.interfaz as fri
    from constants import TICKERS_RENTA_FIJA
    os.environ["FRI_INTERFAZ"] = "fri"
    st.query_params["s"] = "informes" if pestaña else "inicio"
    if pestaña:
        st.session_state.setdefault("fri_pestana_informes", pestaña)
    fechas = pd.bdate_range(end="2026-11-24", periods=300)

    def macro():
        return pd.DataFrame(columns=["nombre", "fecha", "valor"])

    def precios(tickers=None, fecha_inicio=None, fecha_fin=None):
        if not con_precios:
            return pd.DataFrame(columns=["ticker", "fecha", "precio_cierre", "volumen"])
        return pd.DataFrame([{"ticker": t, "fecha": f, "precio_cierre": 100.0 + i * .01, "volumen": 1}
                             for t in tickers for i, f in enumerate(fechas)])
    meta = pd.DataFrame({"fuente": ["bcch"], "ultima_actualizacion": [pd.Timestamp("2026-11-24 21:00")]})
    st.session_state["_devuelta"] = fri.navegar(lambda: meta, "Autora", cargadores={"macro": macro, "precios": precios})


def _correr(pestaña, con_precios=True) -> AppTest:
    at = AppTest.from_function(_app, args=(pestaña, con_precios), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def _texto(at) -> str:
    return " ".join(m.value for m in at.markdown) + " " + " ".join(x.value for x in at.caption)


def test_el_informe_dominical_muestra_su_estado_real_y_no_publica():
    at = _correr("Informe semanal")
    texto = _texto(at)
    assert "No implementado" in texto and "Todavía no hay ediciones publicadas" in texto
    assert "boton-inactivo" in texto and not at.button and not at.get("download_button")
    assert "publicación automática está deshabilitada" in texto
    assert "no una publicación programada" in texto and "Próxima publicación" not in texto


def test_el_archivo_no_muestra_ediciones_ficticias():
    at = _correr("Archivo de informes")
    texto = _texto(at)
    assert "Sin ediciones publicadas" in texto and "DESHABILITADO" in texto
    assert not at.button


def test_el_informe_especializado_es_el_existente_y_no_el_dominical():
    at = _correr("Informes especializados")
    texto = _texto(at)
    assert "no es el informe dominical" in texto and "no es el informe semanal" in texto
    assert [b.label for b in at.button] == ["Preparar informe"]                # el mismo botón de renta_fija_ui
    assert at.selectbox[0].label == "Período que cubre el informe"
    assert "Brief Premercado (diario)" in texto and "No se presenta como informe semanal" in texto


def test_sin_precios_el_informe_especializado_no_se_arma():
    at = _correr("Informes especializados", con_precios=False)
    assert "No disponible: la base no tiene precios de los ETF de bonos" in _texto(at)
    assert not at.button


def test_inicio_no_publica_analisis_ficticios_y_muestra_el_estado_real():
    at = _correr(None)
    texto = _texto(at)
    assert "Sin análisis publicado" in texto and "ni generado ni de ejemplo" in texto
    assert "Estado: no implementado · publicación automática deshabilitada · sin ediciones" in texto
    assert "Fecha prevista (no programada)" in texto and "PRÓXIMO INFORME" not in texto
    assert "Datos del dashboard: BCCh: 24-11-2026 21:00" in texto
    assert '<div class="fri-barra">' not in texto


def test_la_interfaz_no_activa_tareas_programadas_ni_gemini():
    carpeta = os.path.join(RAIZ, "fri")
    for archivo in os.listdir(carpeta):
        if archivo.endswith(".py"):
            texto = open(os.path.join(carpeta, archivo), encoding="utf-8").read().lower()
            for prohibido in ("genai", "gemini", "schedule", "cron", "apscheduler", "threading.timer"):
                assert prohibido not in texto, (archivo, prohibido)


def test_los_panoramas_advierten_que_aun_no_se_marcan_los_datos_atrasados():
    import fri.panoramas as p
    # H3-D1: la nota no contradice a los motores: los panoramas aún no marcan atraso (H3-D3); las tablas sí, con su calendario.
    assert "corrección H3-D3 pendiente" in p.NOTA_ANTIGUEDAD and "aproximación de lunes a viernes" in p.NOTA_ANTIGUEDAD
    fuente = open(os.path.join(RAIZ, "fri", "panoramas.py"), encoding="utf-8").read()
    assert fuente.count("{NOTA_ANTIGUEDAD}") == 2   # en Macroeconomía y en Mercados
