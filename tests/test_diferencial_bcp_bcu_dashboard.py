"""I-6b-2: el diferencial BCP − BCU a 10 años en el Resumen, el selector de Indicadores macro y el PDF del Brief
Premercado (offline, datos sintéticos).

CÓMO SE PRUEBA SIN LA BASE
    app/dashboard.py es un script de Streamlit que lee la base al cargarse. Para probar sus piezas se cargan solo sus
    DEFINICIONES (imports, constantes y funciones; ver _definiciones_del_dashboard) y se reemplazan las funciones que
    leen la base por datos sintéticos. Los bloques de pantalla del Resumen y del selector se ejecutan tal como están en
    el archivo (se recortan del código fuente), dentro de AppTest.

QUÉ SE PRUEBA
    - La serie es la misma resta de siempre (BCP − BCU en las fechas con dato en ambos), y el selector la conserva.
    - El Resumen: etiqueta en pp, el cambio sin color, la fecha con que se compara (que no tiene por qué ser el día
      anterior) y la lectura como aproximación a la compensación por inflación.
    - El Brief: la misma cifra y fecha, con la advertencia; el resto del PDF sale igual.
    - Ninguna vista lo llama inflación esperada, «priced», «same issuer» ni medición exacta.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import ast
import os
import pickle
import re
import sys
import textwrap

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(RAIZ)

import diferencial_bcp_bcu as dif  # noqa: E402
from market_data import INDICADORES_PREMERCADO  # noqa: E402

DASHBOARD = os.path.join(RAIZ, "app", "dashboard.py")
FUENTE = open(DASHBOARD, encoding="utf-8").read()
BCP = "Bono BCCh en pesos (BCP) a 10 años - tasa mercado secundario"
BCU = "Bono BCCh en UF (BCU) a 10 años - tasa mercado secundario"
FIN = pd.Timestamp("2026-11-18")
FECHAS = pd.bdate_range(end=FIN, periods=40)
ENGANOSAS = ("priced", "same issuer", "Breakeven inflation", "breakeven inflation", "Inflación breakeven",
             "inflación breakeven", "expected inflation of the market", "exact measure")


# ---------------------------------------------------------------------------
# Datos sintéticos y carga de las definiciones del dashboard
# ---------------------------------------------------------------------------
def _macro(huecos=False, sin_bcu=False, sin_cambio=False) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    filas = []
    nombres = [c for _e, tipo, c, *_ in INDICADORES_PREMERCADO if tipo != "accion"]
    for n in nombres + ["Tasa Tesoro EEUU 10 años", "Tasa Tesoro EEUU 2 años"]:
        v = 4 + rng.normal(0, 0.05, len(FECHAS)).cumsum()
        filas += [{"nombre": n, "fecha": f.date(), "valor": float(x)} for f, x in zip(FECHAS, v)]
    bcp = 6.0 + rng.normal(0, 0.03, len(FECHAS)).cumsum()
    bcu = 2.7 + rng.normal(0, 0.03, len(FECHAS)).cumsum()
    if sin_cambio:
        bcp[-1], bcu[-1] = bcp[-2] + 0.001, bcu[-2]
    if huecos:
        bcp[-3] += 0.25          # un cambio visible en la última fecha común, para ver el delta
    for f, x, y in zip(FECHAS, bcp, bcu):
        if not sin_bcu and not (huecos and f in (FECHAS[-2], FECHAS[-5])):
            filas.append({"nombre": BCU, "fecha": f.date(), "valor": float(y)})
        if not (huecos and f == FECHAS[-1]):
            filas.append({"nombre": BCP, "fecha": f.date(), "valor": float(x)})
    return pd.DataFrame(filas)


def _acciones(tickers=None, fecha_inicio=None, fecha_fin=None) -> pd.DataFrame:
    claves = [c for _e, tipo, c, *_ in INDICADORES_PREMERCADO if tipo == "accion"]
    return pd.DataFrame([{"ticker": t, "fecha": f.date(), "precio_cierre": 100.0 + i, "volumen": 1000}
                         for t in claves for i, f in enumerate(FECHAS)])


def _usa_widgets(nodo) -> bool:
    return any(isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == "st"
               and x.attr != "cache_data" for x in ast.walk(nodo))


def _definiciones_del_dashboard(reemplazos: dict | None = None) -> dict:
    """Imports, constantes y funciones de app/dashboard.py, sin las sentencias que dibujan la pantalla ni las
    asignaciones que leen widgets. Las funciones que leen la base se reemplazan con `reemplazos`."""
    for p in (RAIZ, os.path.join(RAIZ, "app")):
        if p not in sys.path:
            sys.path.insert(0, p)
    arbol = ast.parse(FUENTE)
    cuerpo = [n for n in arbol.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef))
              or (isinstance(n, (ast.Assign, ast.AnnAssign)) and not _usa_widgets(n))]
    ns = {"__name__": "dashboard_sin_ui", "__file__": DASHBOARD}
    exec(compile(ast.Module(body=cuerpo, type_ignores=[]), DASHBOARD, "exec"), ns)
    ns.update(reemplazos or {})
    return ns


def _bloque(desde: str, hasta: str, despues_de: str = "") -> str:
    """Las líneas de app/dashboard.py entre `desde` (incluida) y `hasta` (excluida), sin sangría."""
    i = FUENTE.index(desde, FUENTE.index(despues_de) if despues_de else 0)
    j = FUENTE.index(hasta, i)
    return textwrap.dedent(FUENTE[FUENTE.rfind("\n", 0, i) + 1:FUENTE.rfind("\n", 0, j) + 1])


GUION = '''
import sys, pickle
sys.path[:0] = [{tests!r}, {raiz!r}]
import _guardia_bd
import streamlit as st
import test_diferencial_bcp_bcu_dashboard as t
ns = t._definiciones_del_dashboard()
ns["df_macro"] = pickle.load(open({datos!r}, "rb"))
ns["st"] = st
for bloque in {bloques!r}:
    exec(bloque, ns)
'''


def _correr(tmp_path, df_macro, bloques, seleccion=None) -> AppTest:
    datos = tmp_path / "macro.pkl"
    pickle.dump(df_macro, open(datos, "wb"))
    at = AppTest.from_string(GUION.format(tests=os.path.dirname(os.path.abspath(__file__)), raiz=RAIZ, datos=str(datos),
                                          bloques=bloques), default_timeout=120)
    at.run()
    if seleccion is not None:
        at.selectbox[0].set_value(seleccion).run()
    assert not at.exception, at.exception
    return at


def _serie_esperada(df: pd.DataFrame) -> pd.Series:
    """Cálculo aparte: BCP − BCU en las fechas con dato en ambos."""
    bcp = df[df["nombre"] == BCP].set_index("fecha")["valor"].sort_index()
    bcu = df[df["nombre"] == BCU].set_index("fecha")["valor"].sort_index()
    juntas = pd.concat([bcp, bcu], axis=1, join="inner").dropna()
    return juntas.iloc[:, 0] - juntas.iloc[:, 1]


# ---------------------------------------------------------------------------
# La serie no cambia
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kwargs", [{}, {"huecos": True}, {"sin_bcu": True}])
def test_la_serie_es_la_resta_en_las_fechas_comunes(kwargs):
    df = _macro(**kwargs)
    serie = _definiciones_del_dashboard()["calcular_serie_inflacion_breakeven"](df)
    esperada = _serie_esperada(df)
    assert len(serie) == len(esperada)
    if len(esperada):
        assert list(serie.index) == list(esperada.index)
        assert np.array_equal(serie.to_numpy(), esperada.to_numpy())


# ---------------------------------------------------------------------------
# Las dos últimas observaciones y los textos
# ---------------------------------------------------------------------------
def test_las_ultimas_observaciones_son_las_dos_ultimas_fechas_comunes():
    df = _macro(huecos=True)                     # falta el BCP del último día y el BCU del penúltimo
    serie = _serie_esperada(df)
    obs = dif.ultimas_observaciones(serie)
    assert obs["fecha"] == pd.Timestamp(FECHAS[-3]) and obs["fecha_anterior"] == pd.Timestamp(FECHAS[-4])
    assert obs["valor"] == serie.iloc[-1] and obs["cambio"] == serie.iloc[-1] - serie.iloc[-2]
    assert dif.ultimas_observaciones(serie.iloc[:1]) is None and dif.ultimas_observaciones(pd.Series(dtype=float)) is None


def test_los_textos_no_tienen_lecturas_enganosas_y_dicen_lo_que_es():
    obs = dif.ultimas_observaciones(_serie_esperada(_macro()))
    textos = " ".join([dif.ETIQUETA_RESUMEN, dif.AYUDA_RESUMEN, dif.texto_resumen(obs), dif.parrafo_brief(
        _serie_esperada(_macro())), dif.NOMBRE_SERIE, dif.DESCRIPCION_SERIE])
    for expresion in ENGANOSAS:
        assert expresion not in textos, expresion
    assert "not a direct measure of expected inflation" in textos and "no una medición directa de la inflación esperada" in textos
    for limite in ("inflation-risk and liquidity premia", "issuer, duration and coupons", "the UF lags CPI",
                   "primas por riesgo de inflación", "emisor, duración y cupones", "rezago"):
        assert limite in textos, limite
    assert "(pp)" in dif.ETIQUETA_RESUMEN and dif.NOMBRE_SERIE == "Diferencial BCP − BCU a 10 años (pp)"


# ---------------------------------------------------------------------------
# Resumen (el bloque tal como está en app/dashboard.py)
# ---------------------------------------------------------------------------
BLOQUE_RESUMEN = _bloque("breakeven = calcular_serie_inflacion_breakeven(df_macro)", "except Exception as e:",
                         despues_de="given false signals in the past")


def test_el_resumen_muestra_la_cifra_en_pp_y_el_cambio_sin_color_con_su_fecha(tmp_path):
    df = _macro(huecos=True)
    serie = _serie_esperada(df)
    at = _correr(tmp_path, df, [BLOQUE_RESUMEN])
    (metrica,) = at.metric
    assert metrica.label == "BCP 10Y − BCU 10Y spread (pp)"
    assert metrica.value == f"{serie.iloc[-1]:.2f} pp"
    assert metrica.proto.delta == f"{serie.iloc[-1] - serie.iloc[-2]:+.2f} pp"
    assert metrica.proto.color == 2              # MetricColor GRAY: ni verde ni rojo
    (caption,) = at.caption
    # el cambio se compara con la fecha común anterior (aquí NO es el día hábil anterior) y lo dice
    assert caption.value.startswith(f"as of {FECHAS[-3]:%Y-%m-%d} · change vs {FECHAS[-4]:%Y-%m-%d}, the previous date "
                                    "with data for both bonds.")
    assert "1D" not in caption.value and "daily" not in caption.value.lower()
    for expresion in ENGANOSAS:
        assert expresion not in caption.value + metrica.label + metrica.proto.help


def test_sin_cambio_visible_el_resumen_no_pone_delta(tmp_path):
    at = _correr(tmp_path, _macro(sin_cambio=True), [BLOQUE_RESUMEN])
    (metrica,) = at.metric
    assert metrica.proto.delta == "" and "· no change vs" in at.caption[0].value


def test_sin_bcu_el_resumen_no_muestra_nada(tmp_path):
    at = _correr(tmp_path, _macro(sin_bcu=True), [BLOQUE_RESUMEN])
    assert len(at.metric) == 0 and len(at.caption) == 0


# ---------------------------------------------------------------------------
# Selector de Indicadores macro (los bloques tal como están en app/dashboard.py)
# ---------------------------------------------------------------------------
BLOQUE_AGREGA_SERIE = _bloque("breakeven = calcular_serie_inflacion_breakeven(df_macro)", "# Los indicadores de",
                              despues_de='if _seccion == "Indicadores macro":')
BLOQUE_SELECTOR = _bloque("series_disponibles = df_macro", "except Exception as e:",
                          despues_de='if _seccion == "Indicadores macro":')


def test_el_selector_conserva_la_serie_con_su_nuevo_nombre_y_su_descripcion(tmp_path):
    df = _macro(huecos=True)
    serie = _serie_esperada(df)
    at = _correr(tmp_path, df, [BLOQUE_AGREGA_SERIE, BLOQUE_SELECTOR], seleccion=dif.NOMBRE_SERIE)
    assert dif.NOMBRE_SERIE in at.selectbox[0].options
    assert not any("breakeven" in o.lower() for o in at.selectbox[0].options)
    assert at.metric[0].value == f"{serie.iloc[-1]:,.2f}"                       # «Último valor», sin cambios
    assert at.metric[1].value == str(serie.index[-1])
    assert dif.DESCRIPCION_SERIE in [c.value for c in at.caption]
    # los puntos del gráfico son la serie completa
    import plotly.io as pio
    figura = pio.from_json(at.get("plotly_chart")[0].proto.spec)
    assert figura.layout.title.text == dif.NOMBRE_SERIE
    assert len(figura.data[0].x) == len(serie)


def test_otra_serie_del_selector_no_lleva_la_descripcion(tmp_path):
    at = _correr(tmp_path, _macro(), [BLOQUE_AGREGA_SERIE, BLOQUE_SELECTOR], seleccion=BCP)
    assert dif.DESCRIPCION_SERIE not in [c.value for c in at.caption]


# ---------------------------------------------------------------------------
# PDF del Brief Premercado
# ---------------------------------------------------------------------------
def _texto_del_brief(df_macro) -> str:
    pymupdf = pytest.importorskip("pymupdf")
    ns = _definiciones_del_dashboard({"cargar_series_macro": lambda: df_macro, "cargar_precios_acciones": _acciones,
                                      "cargar_brief_diario": lambda: pd.DataFrame()})
    generar = ns["generar_pdf_brief_premercado"]
    pdf = getattr(generar, "__wrapped__", generar)()
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return " ".join(" ".join(p.get_text().split()) for p in doc)


def test_el_brief_trae_la_misma_cifra_y_fecha_con_su_advertencia():
    df = _macro(huecos=True)
    serie = _serie_esperada(df)
    texto = _texto_del_brief(df)
    assert f"BCP 10Y − BCU 10Y spread: {serie.iloc[-1]:.2f} pp as of {FECHAS[-3]:%Y-%m-%d}." in texto
    assert "not a direct measure of expected inflation" in texto and "the UF lags CPI" in texto
    for expresion in ENGANOSAS:
        assert expresion not in texto, expresion
    assert "KEY INDICATORS" in texto and "ECONOMIC CALENDAR" in texto


def test_sin_bcu_el_brief_no_menciona_el_diferencial():
    assert "BCP 10Y" not in _texto_del_brief(_macro(sin_bcu=True))


# ---------------------------------------------------------------------------
# Lo que queda en app/dashboard.py
# ---------------------------------------------------------------------------
def test_el_dashboard_no_conserva_lecturas_enganosas_del_diferencial():
    for expresion in ("priced into", "same issuer", "Breakeven inflation", "Inflación breakeven",
                      "inflación breakeven", "es la inflación que el"):
        assert expresion not in FUENTE, expresion
    assert "dif_bcp_bcu.mostrar_en_resumen(breakeven)" in FUENTE and "dif_bcp_bcu.parrafo_brief(breakeven)" in FUENTE
