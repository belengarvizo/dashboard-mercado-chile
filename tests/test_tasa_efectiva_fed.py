"""H1: la serie DFF de FRED se presenta como «tasa efectiva de fondos federales de EE. UU.», no como «tasa de política»
(offline, datos sintéticos).

QUÉ SE PRUEBA
    - Ningún texto visible del alcance la llama «tasa de política de EEUU»; en inglés es «US Effective Federal Funds Rate».
    - El Sharpe la presenta como referencia aproximada de tasa libre de riesgo; su cifra no cambia.
    - La ayuda de la métrica distingue la tasa efectiva (observada) del rango objetivo que fija el FOMC.
    - El selector de Indicadores macro muestra un alias, pero la opción, la selección y los datos siguen siendo los de la
      clave original de la base, que no cambia (ni NOMBRE_TPM_EEUU, NOMBRE_TASA_EEUU ni la clave interna «TPM EEUU»).
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import sys

import pytest
from streamlit.testing.v1 import AppTest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(RAIZ)
sys.path.append(os.path.join(RAIZ, "scripts"))

import catalogo_fx  # noqa: E402
import glosario_commodities as gcm  # noqa: E402
import glosario_renta_fija as grf  # noqa: E402
import glosario_renta_variable as grv  # noqa: E402
import market_data  # noqa: E402
import renta_fija as rf  # noqa: E402
import renta_fija_ui as rfui  # noqa: E402
import test_carry_trade_textos as tct  # noqa: E402
import test_diferencial_bcp_bcu_dashboard as tdash  # noqa: E402

CLAVE_EN_LA_BASE = "Tasa de política monetaria de EEUU (Effective Federal Funds Rate)"
ALIAS = "Tasa efectiva de fondos federales de EE. UU."


def _fuente(nombre: str) -> str:
    return open(os.path.join(RAIZ, nombre), encoding="utf-8").read()


# ---------------------------------------------------------------------------
# Las claves de datos no cambian
# ---------------------------------------------------------------------------
def test_las_claves_de_la_serie_no_cambian():
    import actualizar_bcch
    assert rfui.NOMBRE_TPM_EEUU == catalogo_fx.NOMBRE_TASA_EEUU == actualizar_bcch.NOMBRE_TPM_EEUU == CLAVE_EN_LA_BASE
    claves = {etiqueta: clave for etiqueta, _tipo, clave, *_ in market_data.INDICADORES_PREMERCADO}
    assert claves["TPM EEUU"] == CLAVE_EN_LA_BASE
    assert rfui.SERIES_TASAS[ALIAS] == CLAVE_EN_LA_BASE                 # rótulo nuevo, misma serie


# ---------------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("archivo", ["renta_fija_ui.py", "renta_variable_ui.py", "commodities_ui.py", "glosario_renta_fija.py",
                                     "glosario_renta_variable.py", "glosario_commodities.py"])
def test_ningun_texto_la_llama_tasa_de_politica(archivo):
    texto = _fuente(archivo).lower()
    assert "tasa de política de eeuu" not in texto and "política de eeuu" not in texto


def test_el_rotulo_en_ingles_es_la_tasa_efectiva():
    fuente = _fuente(os.path.join("app", "dashboard.py"))
    assert "US Fed Funds Rate" not in fuente
    ns = tdash._definiciones_del_dashboard()
    assert ns["ETIQUETA_EN_POR_ES"]["TPM EEUU"] == "US Effective Federal Funds Rate"


@pytest.mark.parametrize("modulo", [grf, grv, gcm])
def test_el_sharpe_la_presenta_como_referencia_aproximada_y_no_cambia_su_cifra(modulo):
    texto = modulo.explicacion_sharpe(0.42, 3.88)
    assert "(la tasa efectiva de fondos federales de EE. UU., 3.88%, usada como referencia aproximada)" in texto
    assert "Sharpe = 0.42" in texto
    assert rf.razon_de_sharpe(5.0, 3.88, 4.0) == pytest.approx((5.0 - 3.88) / 4.0)   # la fórmula no cambia


def test_la_ayuda_distingue_la_tasa_efectiva_del_rango_objetivo():
    at = AppTest.from_function(tct._app_renta_fija, args=(tct._macro_renta_fija(4.75, 3.90),), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    metrica = next(m for m in at.metric if m.label == ALIAS)
    assert metrica.value == "3.90%"
    ayuda = metrica.proto.help
    assert "rango objetivo" in ayuda and "no es el rango" in ayuda and "FOMC" in ayuda and "DFF" in ayuda
    assert all(not m.proto.help for m in at.metric if m.label == "TPM de Chile")          # la aclaración va una sola vez


# ---------------------------------------------------------------------------
# Selector de Indicadores macro: alias visible, clave intacta
# ---------------------------------------------------------------------------
def _macro_con_la_fed():
    df = tdash._macro()
    assert CLAVE_EN_LA_BASE in set(df["nombre"])
    return df


def test_el_selector_muestra_el_alias_y_conserva_la_clave_y_los_datos(tmp_path):
    df = _macro_con_la_fed()
    at = tdash._correr(tmp_path, df, [tdash.BLOQUE_AGREGA_SERIE, tdash.BLOQUE_SELECTOR], seleccion=CLAVE_EN_LA_BASE)
    selector = at.selectbox[0]
    assert ALIAS in selector.options and CLAVE_EN_LA_BASE not in selector.options     # lo que se ve
    assert selector.value == CLAVE_EN_LA_BASE                                          # lo que se usa
    serie = df[df["nombre"] == CLAVE_EN_LA_BASE].sort_values("fecha")
    assert at.metric[0].value == f"{serie['valor'].iloc[-1]:,.2f}"
    assert at.metric[1].value == str(serie["fecha"].iloc[-1])
    import plotly.io as pio
    figura = pio.from_json(at.get("plotly_chart")[0].proto.spec)
    assert figura.layout.title.text == ALIAS and len(figura.data[0].x) == len(serie)


def test_el_alias_es_unico_y_reversible(tmp_path):
    at = tdash._correr(tmp_path, _macro_con_la_fed(), [tdash.BLOQUE_AGREGA_SERIE, tdash.BLOQUE_SELECTOR])
    visibles = list(at.selectbox[0].options)
    assert len(visibles) == len(set(visibles)) and visibles.count(ALIAS) == 1
    ns = tdash._definiciones_del_dashboard()
    assert ns["ALIAS_SERIES_MACRO"] == {CLAVE_EN_LA_BASE: ALIAS}                         # uno a uno: se puede deshacer
