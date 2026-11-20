"""I-5a: la pendiente de la regresión se presenta como SENSIBILIDAD EMPÍRICA, no como la duración del fondo (offline).

QUÉ SE PRUEBA
    - Ni el PDF ni la pantalla ni el glosario dicen que la pendiente «es» la duración, que el R² mide confiabilidad, que
      la regresión es preferible a la ficha del fondo, que una diferencia «se debe a» la composición, ni que un R² bajo
      prueba que domina el crédito.
    - El PDF y la pantalla usan el mismo término («sensibilidad empírica») y conservan «duración teórica» solo para la
      duración modificada de un bono a la par, que sí es una duración.
    - Solo cambia el lenguaje: las cifras, los errores estándar, las reglas de I-2 y las clasificaciones siguen iguales
      (lo cubren las pruebas de I-0 a I-4a, que no se tocaron en sus números).
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import inspect
import os
import re
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import estructura_tasas as et  # noqa: E402
import glosario_renta_fija as gl  # noqa: E402
import informe_renta_fija as inf  # noqa: E402
import renta_fija_ui as rfui  # noqa: E402

FECHAS = pd.bdate_range("2025-01-06", periods=420)
N = len(FECHAS)

PROHIBIDAS = [
    r"pendiente de (esa relación|la recta roja) es la duración",
    r"es la duración\b(?! (efectiva|modificada))",   # «duración efectiva/modificada» sí son conceptos de duración
    r"(cuán|más|poco|muy) confiable",
    r"preferible a uno sacado de una ficha",
    r"medida con datos reales y no con la ficha",
    r"se debe a que el ETF",
    r"manda el riesgo de crédito",
    r"lo explican las tasas",
    r"R²\*{0,2} (indica|dice) (qué parte|cuánto)",
]


def _sin_prohibidas(texto: str, donde: str):
    for patron in PROHIBIDAS:
        assert not re.search(patron, texto, re.I), f"{donde}: «{patron}»"


def _mundo(semilla=3):
    rng = np.random.default_rng(semilla)
    tasa = 4.0 + np.concatenate([[0.0], rng.normal(0, 0.03, N - 1)]).cumsum()
    cambios = np.diff(tasa, prepend=tasa[0]) / 100
    spread = np.concatenate([[0.0], rng.normal(0, 0.01, N - 1)]).cumsum() / 100
    dspread = np.diff(spread, prepend=spread[0])
    filas = [{"nombre": rfui.nombre_treasury(e), "fecha": f, "valor": float(v)} for e in et.PLAZOS_ANIOS for f, v in zip(FECHAS, tasa)]
    filas += [{"nombre": rfui.NOMBRE_BAA10Y, "fecha": f, "valor": 1.5 + float(s) * 100} for f, s in zip(FECHAS, spread)]
    precios = pd.DataFrame({t: 100 * np.cumprod(1 - d * cambios) for t, d in {"SHY": 1.9, "IEF": 6.5, "TLT": 16.0}.items()},
                           index=FECHAS)
    precios["HYG"] = 100 * np.cumprod(1 - 3.9 * (cambios + dspread))
    precios["TIP"] = 100 * np.cumprod(1 - 4.5 * cambios * 0.4)
    return pd.DataFrame(filas), precios


def _texto_pdf(pdf: bytes) -> str:
    pymupdf = pytest.importorskip("pymupdf", reason="pymupdf no está instalado: no se puede leer el PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return " ".join(" ".join(p.get_text().split()) for p in doc)


@pytest.mark.parametrize("periodo", list(inf.PERIODOS))
def test_el_pdf_no_presenta_la_pendiente_como_duracion_ni_el_r2_como_confiabilidad(periodo):
    macro, precios = _mundo()
    texto = _texto_pdf(inf.generar(macro, precios, periodo))
    _sin_prohibidas(texto, f"PDF {periodo}")
    assert "Recuadro 1. Sensibilidad empírica y duración efectiva: no son lo mismo" in texto
    assert "no es la duración efectiva del fondo" in texto                  # nota del Cuadro 2
    assert "Sensibilidad empírica (años)" in texto                         # Cuadros 1, 2 y 3
    assert "no recoge los errores de especificación" in texto              # margen ≠ toda la incertidumbre
    assert "supuestos de mínimos cuadrados ordinarios" in texto            # el margen es el error OLS convencional


def test_el_glosario_de_la_pantalla_usa_el_mismo_lenguaje():
    for r2 in (0.92, 0.6, 0.2, None):
        texto = gl.explicacion_duracion_medida(5.2, 0.15, r2, 7)
        _sin_prohibidas(texto, f"glosario R² {r2}")
        assert "Sensibilidad empírica" in texto and "no la duración efectiva del fondo" in texto
    assert "no disponible" in gl.explicacion_duracion_medida(None, None, None, None)


def test_los_textos_de_la_pantalla_no_presentan_la_pendiente_como_duracion():
    for funcion in (rfui._paso_mercado, rfui._paso_riesgo_mercado, rfui._filas_de_duracion):
        _sin_prohibidas(inspect.getsource(funcion), funcion.__name__)
    fuente = inspect.getsource(rfui)
    assert "La pendiente de la recta roja es la sensibilidad empírica" in fuente
    assert "no dice si esta sensibilidad es la duración efectiva del fondo" in fuente


def test_el_rotulo_de_la_tabla_del_dashboard_es_la_sensibilidad_empirica_y_se_define_en_la_leyenda():
    encabezado = rfui.ENCABEZADOS["Duración medida (años)"]
    assert encabezado.startswith("Sensib") and encabezado in rfui.COLUMNAS_SECUENCIALES
    assert "Duración" not in rfui.ENCABEZADOS.values()
    leyenda = inspect.getsource(rfui._paso_mercado)
    assert f"**{encabezado}** = sensibilidad empírica a tasas, en años" in leyenda


def test_la_duracion_teorica_sigue_siendo_la_de_un_bono_a_la_par_y_no_se_renombra():
    """«Duración teórica» sí es una duración (modificada, de un bono del Tesoro a la par): se conserva, definida."""
    fuente = inspect.getsource(rfui._paso_riesgo_mercado)
    assert "«Duración teórica» es la duración modificada de un bono del Tesoro a la par" in fuente
    filas = rfui._filas_de_duracion(pd.DataFrame({
        "Plazo de referencia": [7], "Grupo": ["Tesoro EEUU"], "Duración medida (años)": [6.4],
        "Error de la duración": [0.1], "R² con la tasa": [0.95]}, index=["IEF"]), None)
    assert set(filas[0]) == {"ETF", "Grupo", "Ref. Tesoro", "Sensibilidad empírica (años)", "Margen (±2 err.)", "R²",
                             "Duración teórica"}
    assert filas[0]["Sensibilidad empírica (años)"] == "6.40" and filas[0]["Margen (±2 err.)"] == "±0.20"
