"""I-6b-1: el diferencial BCP − BCU en el paso «Banco Central» de la sección Renta Fija (offline, datos sintéticos).

Corre la función real de la pantalla (renta_fija_ui._paso_banco_central) con AppTest.from_function, sin base de datos.

QUÉ SE PRUEBA
    - Los diferenciales a 5 y 10 años son la misma resta de siempre (BCP − BCU en la última fecha común), en pp.
    - Cada plazo usa sus propias series y su propia fecha común.
    - El gráfico histórico conserva la serie (mismos puntos); solo cambian nombres, eje y tooltip, que van en pp.
    - Se presenta como aproximación a la compensación por inflación, con sus límites; nunca como inflación esperada,
      «puesta en precio» o medición exacta (coherente con el PDF, I-6c).
    - Sin datos (falta un plazo, faltan todos los bonos, base vacía), la sección se dibuja sin inventar cifras.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import base64
import os
import re
import sys

import numpy as np
import pandas as pd
import plotly.io as pio
import pytest
from streamlit.testing.v1 import AppTest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import renta_fija_ui as ui  # noqa: E402

FECHAS = pd.bdate_range("2023-01-02", periods=400)
BCP5, BCP10 = ui.CURVA_CHILE["BCP (pesos)"][5], ui.CURVA_CHILE["BCP (pesos)"][10]
BCU5, BCU10 = ui.CURVA_CHILE["BCU (UF, tasa real)"][5], ui.CURVA_CHILE["BCU (UF, tasa real)"][10]
NIVELES = {**{n: 5.0 for n in ui.SERIES_TASAS.values()}, ui.CURVA_CHILE["BCP (pesos)"][2]: 5.2, BCP5: 5.5, BCP10: 5.8,
           BCU5: 2.1, BCU10: 2.45, ui.CURVA_CHILE["BCU (UF, tasa real)"][30]: 2.7}
TODOS_LOS_BONOS = tuple(n for g in ui.CURVA_CHILE.values() for n in g.values())


def _macro(sin=(), cortes=None, semilla=3) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    filas = []
    for nombre, nivel in NIVELES.items():
        valores = nivel + rng.normal(0, 0.02, len(FECHAS)).cumsum()
        if nombre in sin:
            continue
        filas += [{"nombre": nombre, "fecha": f, "valor": float(v)} for f, v in zip(FECHAS, valores)
                  if not (cortes and nombre in cortes and f > cortes[nombre])]
    return pd.DataFrame(filas, columns=["nombre", "fecha", "valor"])


def _serie(macro, nombre) -> pd.Series:
    filas = macro[macro["nombre"] == nombre]
    return pd.Series(filas["valor"].to_numpy(float), index=pd.to_datetime(filas["fecha"])).sort_index()


def _app(macro):
    import renta_fija_ui as ui
    ui._paso_banco_central(macro)


def _abrir(macro, ventana=None) -> AppTest:
    at = AppTest.from_function(_app, args=(macro,), default_timeout=60)
    at.run()
    if ventana:
        at.radio(key="rf_ventana_tasas").set_value(ventana).run()
    assert not at.exception, at.exception
    return at


def _metrica(at, etiqueta):
    return next(m for m in at.metric if m.label == etiqueta)


def _textos(at) -> str:
    return " ".join([m.value for m in at.markdown] + [c.value for c in at.caption]
                    + [f"{m.label} {m.proto.help}" for m in at.metric])


def _arreglo(valor) -> np.ndarray:
    """Arreglo de una traza: plotly ≥ 6 lo envía como {"dtype", "bdata" (base64)} en vez de una lista."""
    if isinstance(valor, dict) and "bdata" in valor:
        return np.frombuffer(base64.b64decode(valor["bdata"]), dtype=np.dtype(valor["dtype"]))
    return np.asarray(valor, dtype=float)


def _grafico_del_diferencial(at):
    """La figura de plotly tal como la recibe el navegador (los arreglos vienen codificados: se decodifican con plotly)."""
    for g in at.get("plotly_chart"):
        figura = pio.from_json(g.proto.spec)
        if any("BCP − BCU" in (t.name or "") for t in figura.data):
            return figura
    raise AssertionError("no está el gráfico del diferencial")


# ---------------------------------------------------------------------------
# Cifras: la misma resta, en pp, con la fecha común de cada plazo
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("plazo,bcp,bcu", [(5, BCP5, BCU5), (10, BCP10, BCU10)])
def test_el_diferencial_es_la_resta_en_la_ultima_fecha_comun_y_va_en_pp(plazo, bcp, bcu):
    corte = FECHAS[-12]
    macro = _macro(cortes={bcu: corte})          # el BCU de este plazo termina antes que el BCP
    at = _abrir(macro)
    juntas = pd.concat([_serie(macro, bcp), _serie(macro, bcu)], axis=1, join="inner").dropna()
    esperado = juntas.iloc[-1, 0] - juntas.iloc[-1, 1]
    metrica = _metrica(at, f"Diferencial BCP − BCU a {plazo} años")
    assert metrica.value == f"{esperado:,.2f} pp"
    assert juntas.index[-1] == corte
    assert f"Al {corte.strftime('%d-%m-%Y')}, última fecha con dato en ambas series" in [c.value for c in at.caption]


def test_cada_plazo_usa_sus_propias_series_y_su_propia_fecha():
    macro = _macro(cortes={BCU10: FECHAS[-30], BCU5: FECHAS[-5]})
    at = _abrir(macro)
    fechas = [c.value for c in at.caption if "última fecha con dato en ambas series" in c.value]
    assert fechas == [f"Al {FECHAS[-5].strftime('%d-%m-%Y')}, última fecha con dato en ambas series",
                      f"Al {FECHAS[-30].strftime('%d-%m-%Y')}, última fecha con dato en ambas series"]
    v5 = _serie(macro, BCP5)[FECHAS[-5]] - _serie(macro, BCU5)[FECHAS[-5]]
    v10 = _serie(macro, BCP10)[FECHAS[-30]] - _serie(macro, BCU10)[FECHAS[-30]]
    assert _metrica(at, "Diferencial BCP − BCU a 5 años").value == f"{v5:,.2f} pp"
    assert _metrica(at, "Diferencial BCP − BCU a 10 años").value == f"{v10:,.2f} pp"


def test_el_grafico_conserva_la_serie_y_la_muestra_en_pp():
    macro = _macro(cortes={BCU10: FECHAS[-12]})
    figura = _grafico_del_diferencial(_abrir(macro, "Todo el historial"))
    assert figura.layout.yaxis.title.text == "Diferencial (pp)"
    trazas = {t.name: t for t in figura.data}
    assert set(trazas) == {"BCP − BCU a 5 años", "BCP − BCU a 10 años"}     # solo el diferencial: sin Fisher
    for plazo, bcp, bcu in ((5, BCP5, BCU5), (10, BCP10, BCU10)):
        esperado = (_serie(macro, bcp) - _serie(macro, bcu)).dropna()
        traza = trazas[f"BCP − BCU a {plazo} años"]
        assert np.array_equal(_arreglo(traza.y), esperado.to_numpy())    # los mismos puntos, sin redondeo
        assert pd.DatetimeIndex(pd.to_datetime(traza.x)).equals(esperado.index)
        assert traza.hovertemplate == f"BCP − BCU a {plazo} años: %{{y:.2f}} pp<extra></extra>"


def test_las_demas_tasas_y_el_diferencial_de_politica_no_cambian():
    macro = _macro()
    at = _abrir(macro)
    for etiqueta, nombre in ui.SERIES_TASAS.items():
        assert _metrica(at, etiqueta).value == f"{_serie(macro, nombre).iloc[-1]:,.2f}%"
    curva = next(d.value for d in at.dataframe if "Tasa (%)" in d.value.columns)
    assert list(curva["Bono"]) == ["BCP (pesos)"] * 3 + ["BCU (UF, tasa real)"] * 3


# ---------------------------------------------------------------------------
# Interpretación: aproximación, con límites; sin lecturas engañosas
# ---------------------------------------------------------------------------
EXPRESIONES_ENGANOSAS = ("puesta en precio", "Inflación implícita", "inflación implícita", "el mercado espera",
                         "medición exacta de", "es la inflación", "pronóstico oficial")


def test_la_seccion_presenta_el_diferencial_como_aproximacion_con_sus_limites():
    textos = _textos(_abrir(_macro()))
    for expresion in EXPRESIONES_ENGANOSAS:
        assert expresion not in textos, expresion
    assert "nominal** en pesos" in textos and "**real** sobre un capital que se reajusta con la UF" in textos
    assert "referencia aproximada de la compensación por inflación" in textos
    assert "no equivale a la inflación esperada" in textos
    for limite in ("primas por riesgo de inflación y por liquidez", "mismo emisor", "duración o cupones",
                   "rezago respecto del IPC", "no una medición exacta ni un pronóstico"):
        assert limite in textos, limite
    # «inflación esperada» solo aparece negada
    for m in re.finditer(r"inflación esperada", textos):
        assert re.search(r"(no equivale a|no) la $", textos[max(0, m.start() - 20):m.start()]), textos[m.start() - 40:m.end()]


def test_la_ayuda_de_cada_metrica_explica_la_cifra():
    at = _abrir(_macro())
    for plazo in (5, 10):
        ayuda = _metrica(at, f"Diferencial BCP − BCU a {plazo} años").proto.help
        assert "puntos porcentuales" in ayuda and "última fecha con dato en ambas series" in ayuda
        assert "no la inflación esperada" in ayuda


# ---------------------------------------------------------------------------
# Sin datos
# ---------------------------------------------------------------------------
def test_sin_el_bcu_a_5_anios_ese_plazo_queda_vacio_y_el_otro_sigue():
    at = _abrir(_macro(sin=(BCU5,)))
    assert _metrica(at, "Diferencial BCP − BCU a 5 años").value == "—"
    assert _metrica(at, "Diferencial BCP − BCU a 10 años").value.endswith(" pp")
    assert "Sin datos" in [c.value for c in at.caption]


@pytest.mark.parametrize("macro", [_macro(sin=TODOS_LOS_BONOS), pd.DataFrame(columns=["nombre", "fecha", "valor"])],
                         ids=["sin_bonos_de_chile", "base_vacia"])
def test_sin_bonos_de_chile_no_se_inventa_ninguna_cifra(macro):
    at = _abrir(macro)
    assert any("bonos del Banco Central" in i.value for i in at.info)
    assert not any(m.label.startswith("Diferencial BCP − BCU") for m in at.metric)
