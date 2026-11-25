"""H1-b1: Commodities sin Sharpe y con la advertencia sobre series continuas de futuros (offline, datos sintéticos).

Las cotizaciones «=F» de Yahoo son series continuas del futuro más cercano a vencer, empalmadas al cambiar de contrato;
sus retornos no describen una inversión verificable, así que el Sharpe se retiró. Las demás métricas se conservan.

QUÉ SE PRUEBA
    - La tabla no tiene columna Sharpe, el tooltip no trae su bloque y ningún texto visible de la sección lo menciona.
    - La advertencia sobre series continuas está visible.
    - Las demás columnas siguen ahí, con los valores que calcula el motor (sin cambios).
    - La función del glosario se conserva (no la usa la pantalla).
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import re
import sys

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import commodities_ui as cui  # noqa: E402
import glosario_commodities as gcm  # noqa: E402
from catalogo_commodities import COMMODITIES  # noqa: E402

FECHAS = pd.bdate_range(end="2026-11-18", periods=400)


def _datos():
    rng = np.random.default_rng(4)
    macro = pd.DataFrame([{"nombre": n, "fecha": f, "valor": v} for n, v in ((cui.NOMBRE_COBRE_BCCH, 4.2),
                          (cui.rfui.NOMBRE_TPM_EEUU, 4.0)) for f in FECHAS])
    precios = [{"ticker": t, "fecha": f, "precio_cierre": float(x), "volumen": 1}
               for t in [*COMMODITIES, "SPY"] for f, x in zip(FECHAS, 100 * np.exp(rng.normal(0, 0.012, len(FECHAS)).cumsum()))]
    return macro, pd.DataFrame(precios)


def _app(macro, precios):
    import commodities_ui
    commodities_ui.render_commodities(macro, precios)


def _abrir():
    at = AppTest.from_function(_app, args=_datos(), default_timeout=120)
    at.session_state["cm_paso"] = cui.PASOS[0]
    at.run()
    assert not at.exception, at.exception
    return at


def test_la_tabla_no_tiene_sharpe_y_conserva_las_demas_columnas():
    assert "Sharpe" not in cui.COLUMNAS_TABLA and "Sharpe" not in cui.COLUMNAS_SECUENCIALES
    at = _abrir()
    tablas = [m.value for m in at.markdown if "<table" in m.value]
    assert tablas
    for tabla in tablas:
        encabezados = re.findall(r"<th[^>]*>(.*?)</th>", tabla)
        assert encabezados == ["Ticker", "1D %", "1W %", "1M %", "YTD %", "1A %", "Vol. %", "Caída máx. %", "Beta", "Correl."]


def test_ningun_texto_visible_menciona_el_sharpe_y_la_advertencia_esta():
    at = _abrir()
    visibles = " ".join([m.value for m in at.markdown] + [c.value for c in at.caption] + [i.value for i in at.info])
    assert "Sharpe" not in visibles and "sharpe" not in visibles
    assert cui.ADVERTENCIA_SERIES_CONTINUAS in [c.value for c in at.caption]
    for idea in ("series continuas de futuros próximos a vencer", "cambios de contrato pueden generar discontinuidades",
                 "no representan directamente ganancias o pérdidas", "deben interpretarse con cautela"):
        assert idea in cui.ADVERTENCIA_SERIES_CONTINUAS


def test_el_tooltip_trae_las_demas_explicaciones():
    tabla = next(m.value for m in _abrir().markdown if "<table" in m.value)
    for texto in ("Retorno:", "Volatilidad", "Caída máxima", "Beta vs S&amp;P 500", "Correlación con el S&amp;P 500"):
        assert texto in tabla, texto


def test_la_funcion_del_glosario_se_conserva():
    assert "Sharpe = 0.50" in gcm.explicacion_sharpe(0.5, 4.0)
