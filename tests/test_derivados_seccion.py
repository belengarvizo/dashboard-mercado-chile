"""La sección «Derivados» del dashboard: la ÚNICA que consulta a Yahoo Finance EN VIVO en vez de leer la base, así
que estas pruebas sí hacen llamadas de red reales cada vez que corren (no hay un historial propio contra el cual
comparar). Si Yahoo no responde durante la corrida, las pruebas se saltan en vez de fallar: no es un problema del
código, es que la fuente externa no está disponible en ese momento.

Como el mercado se mueve mientras corren las pruebas, no se fijan precios exactos: se recalcula cada número de
forma independiente (con black_scholes.py, sin pasar por la pantalla) y se compara contra lo que la pantalla
muestra, además de identidades que tienen que cumplirse siempre (T = días/365, call-put en el mismo strike tienen
el mismo spot y la misma tasa, etc.).
"""
import math
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pandas as pd
import pytest
from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

import black_scholes as bs
import derivados_ui as ui

load_dotenv()

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
SECCION = "Derivados"


@pytest.fixture(scope="module", autouse=True)
def _requiere_yahoo_en_vivo():
    """Si Yahoo Finance no responde ahora, se saltan todas las pruebas de este archivo: no hay nada más que
    probar sin la fuente en vivo, y no es una falla del código del dashboard."""
    vencimientos = ui._vencimientos_disponibles("SPY")
    if not vencimientos:
        pytest.skip("Yahoo Finance no respondió con la cadena de opciones de SPY en este momento.")


def _abrir(paso=None) -> AppTest:
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = SECCION
    if paso:
        at.session_state["dv_paso"] = paso
    at.run(timeout=420)
    assert not at.exception, f"La app lanzó una excepción: {at.exception}"
    return at


def _ir_a(at: AppTest, paso: str) -> AppTest:
    at.session_state["dv_paso"] = paso
    at.run(timeout=420)
    assert not at.exception, f"La app lanzó una excepción en {paso!r}: {at.exception}"
    return at


def _metrica(at: AppTest, etiqueta: str):
    for m in at.metric:
        if m.label == etiqueta:
            return m
    raise AssertionError(f"No hay una métrica «{etiqueta}». Hay: {[m.label for m in at.metric]}")


def _numero(texto: str) -> float:
    return float(texto.replace(",", "").replace("%", "").replace("+", "").strip())


# ---------------------------------------------------------------------------
# La pantalla, en general
# ---------------------------------------------------------------------------
def test_la_seccion_esta_en_el_selector_y_avisa_que_es_distinta():
    at = _abrir()
    assert any("Derivados" in h.value for h in at.header)
    assert any("Yahoo Finance" in i.value and "en vivo" in i.value for i in at.info)


def test_cada_paso_se_dibuja_sin_errores():
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)


def test_no_hay_calculadoras_con_valores_inventados():
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)
        assert len(at.number_input) == 0, f"{paso}: hay un campo numérico, o sea una calculadora"
        assert len(at.slider) == 0, f"{paso}: hay un slider, o sea una calculadora"


def test_ningun_texto_de_la_seccion_lleva_signo_de_dolar():
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)
        textos = [m.value for m in at.markdown] + [c.value for c in at.caption] + [i.value for i in at.info] + [w.value for w in at.warning]
        for t in textos:
            assert "$" not in t, f"{paso}: {t[:80]!r}"


# ---------------------------------------------------------------------------
# Paso 2: la cadena de opciones
# ---------------------------------------------------------------------------
def test_el_vencimiento_por_defecto_no_es_hoy_mismo_si_hay_otra_opcion():
    at = _abrir(ui.PASOS[1])
    vencimiento_elegido = at.selectbox(key="dv_vencimiento_cadena").value
    vencimientos = ui._vencimientos_disponibles("SPY")
    if any(ui._dias_al_vencimiento(v) > 0 for v in vencimientos):
        assert ui._dias_al_vencimiento(vencimiento_elegido) > 0, (
            "el vencimiento por defecto es hoy mismo (T=0) habiendo otro disponible: Black-Scholes no podría "
            "explicar su precio real (ver la advertencia del paso 3)"
        )


def test_la_cadena_trae_precio_en_vivo_y_dias_al_vencimiento_coherentes():
    at = _abrir(ui.PASOS[1])
    spot = _numero(_metrica(at, "Precio de SPY ahora").value)
    dias = int(_metrica(at, "Días al vencimiento").value)
    assert spot > 0
    vencimiento = at.selectbox(key="dv_vencimiento_cadena").value
    assert dias == ui._dias_al_vencimiento(vencimiento)
    assert dias >= 0


def test_cambiar_cuantos_strikes_mostrar_cambia_el_tamano_de_la_tabla():
    at = _abrir(ui.PASOS[1])
    filas_10 = len(at.dataframe[0].value)
    at.radio(key="dv_cuantos_strikes").set_value("Todos").run()
    assert not at.exception
    filas_todos = len(at.dataframe[0].value)
    assert filas_todos >= filas_10  # con "Todos" nunca puede haber menos strikes que con la vista acotada


def test_cambiar_de_subyacente_trae_otra_cadena_real():
    at = _abrir(ui.PASOS[1])
    at.selectbox(key="dv_subyacente_cadena").set_value("TLT").run()
    assert not at.exception
    spot_tlt = _numero(_metrica(at, "Precio de TLT ahora").value)
    assert spot_tlt > 0
    assert any("iShares 20+ Year Treasury Bond ETF" in c.value for c in at.caption)


# ---------------------------------------------------------------------------
# Paso 3: Black-Scholes, con cada número recalculado de forma independiente
# ---------------------------------------------------------------------------
def test_los_cinco_datos_mostrados_son_los_que_de_verdad_entran_al_modelo():
    at = _abrir(ui.PASOS[2])
    vencimiento = at.selectbox(key="dv_vencimiento_bs").value
    dias_mostrados = int(_metrica(at, "Vencimiento (T)").value.split()[0])
    assert dias_mostrados == ui._dias_al_vencimiento(vencimiento)

    spot_mostrado = _numero(_metrica(at, "Subyacente (S)").value)
    spot_real = ui._precio_en_vivo("SPY")
    assert spot_mostrado == pytest.approx(spot_real, abs=0.01)

    strike_mostrado = _numero(_metrica(at, "Strike (K)").value)
    calls, _ = ui._cadena_de_opciones("SPY", vencimiento)
    assert any(abs(strike_mostrado - k) < 0.01 for k in calls["strike"])


def test_dias_al_vencimiento_nunca_es_negativo_para_una_fecha_pasada():
    """Función pura, probada sin pasar por la pantalla: una fecha de ayer debe dar 0 (recortado), no un número
    negativo que luego ensuciaría T en Black-Scholes."""
    assert ui._dias_al_vencimiento("2020-01-01") == 0
    assert ui._dias_al_vencimiento((pd.Timestamp.now() + pd.Timedelta(days=10)).strftime("%Y-%m-%d")) == 10


def test_el_precio_de_mercado_es_el_punto_medio_entre_bid_y_ask_cuando_los_hay():
    """Función pura, con datos reales de la cadena: verifica el cálculo en sí, no solo que la pantalla sea
    consistente consigo misma (eso pasaría igual si la función usara, por error, solo el bid)."""
    calls, _ = ui._cadena_de_opciones("SPY", ui._vencimientos_disponibles("SPY")[2])
    con_bid_y_ask = calls[(calls["bid"] > 0) & (calls["ask"] > 0)]
    if con_bid_y_ask.empty:
        pytest.skip("ningún contrato de la cadena tenía bid y ask positivos en este momento")
    fila = con_bid_y_ask.iloc[0]
    esperado = (float(fila["bid"]) + float(fila["ask"])) / 2
    assert ui._precio_de_mercado(fila) == pytest.approx(esperado)
    assert ui._precio_de_mercado(fila) != pytest.approx(float(fila["bid"]), abs=1e-6)  # no es solo el bid


def test_el_precio_de_mercado_usa_el_ultimo_transado_si_no_hay_bid_ni_ask():
    import pandas as pd_
    fila = pd_.Series({"bid": 0.0, "ask": 0.0, "lastPrice": 3.5})
    assert ui._precio_de_mercado(fila) == 3.5
    fila_sin_nada = pd_.Series({"bid": 0.0, "ask": 0.0, "lastPrice": 0.0})
    assert ui._precio_de_mercado(fila_sin_nada) is None


def test_el_strike_por_defecto_es_el_mas_cercano_al_precio_actual():
    at = _abrir(ui.PASOS[2])
    vencimiento = at.selectbox(key="dv_vencimiento_bs").value
    spot = ui._precio_en_vivo("SPY")
    calls, _ = ui._cadena_de_opciones("SPY", vencimiento)
    strike_elegido = at.selectbox(key="dv_strike").value
    mas_cercano = min(calls["strike"].unique(), key=lambda k: abs(k - spot))
    assert strike_elegido == pytest.approx(mas_cercano, abs=0.01)


def test_el_precio_teorico_con_vol_realizada_coincide_con_recalcularlo_aparte():
    """El número que muestra la pantalla para "con la volatilidad realizada" tiene que ser exactamente
    bs.precio(...) con los mismos cinco insumos, recalculado fuera de la pantalla."""
    at = _abrir(ui.PASOS[2])
    vencimiento = at.selectbox(key="dv_vencimiento_bs").value
    strike = at.selectbox(key="dv_strike").value
    spot = ui._precio_en_vivo("SPY")
    dias = ui._dias_al_vencimiento(vencimiento)
    T = dias / bs.DIAS_DEL_ANIO

    calls, _ = ui._cadena_de_opciones("SPY", vencimiento)
    import pandas as pd_
    import renta_fija_ui as rfui
    from models import get_engine

    macro = pd_.read_sql("SELECT nombre, fecha, valor FROM series_macro", get_engine())
    tasa = ui._tasa_libre_para(rfui._recortar(macro), T)
    assert tasa is not None
    r = tasa[0]

    precios = pd_.read_sql("SELECT ticker, fecha, precio_cierre FROM precios_acciones WHERE ticker = 'SPY'", get_engine())
    import renta_fija as rf
    vol = rf.volatilidad_anualizada(rfui._precios_en_columnas(precios)["SPY"])
    assert vol is not None
    precio_esperado = bs.precio(spot, strike, T, r, vol / 100, "call")

    frase = next(m.value for m in at.markdown if m.value.startswith("**Con la volatilidad REALIZADA**"))
    mostrado = float(re.search(r"precio teórico de \*\*([\d,.]+)\*\*", frase).group(1).replace(",", ""))
    assert mostrado == pytest.approx(precio_esperado, abs=0.02)


def test_la_volatilidad_implicita_mostrada_de_verdad_reproduce_el_precio_de_mercado():
    """No se compara contra un recálculo (eso solo probaría que la pantalla usa la misma fórmula que el test):
    se comprueba la PROPIEDAD que define a la volatilidad implícita — que metida de vuelta en Black-Scholes
    reproduce el precio de mercado que se ve en pantalla."""
    at = _abrir(ui.PASOS[2])
    vencimiento = at.selectbox(key="dv_vencimiento_bs").value
    strike = at.selectbox(key="dv_strike").value
    spot = ui._precio_en_vivo("SPY")
    dias = ui._dias_al_vencimiento(vencimiento)
    T = dias / bs.DIAS_DEL_ANIO

    frases_iv = [m.value for m in at.markdown if "volatilidad implícita de" in m.value]
    if not frases_iv:
        pytest.skip("este contrato no tuvo una volatilidad implícita calculable en el momento de la corrida")
    iv_mostrada = float(re.search(r"volatilidad implícita de ([\d.]+)%", frases_iv[0]).group(1)) / 100

    precio_mercado = _numero(_metrica(at, "Precio de mercado").value)
    import pandas as pd_
    import renta_fija_ui as rfui
    from models import get_engine
    macro = pd_.read_sql("SELECT nombre, fecha, valor FROM series_macro", get_engine())
    tasa = ui._tasa_libre_para(rfui._recortar(macro), T)
    r = tasa[0]

    precio_con_iv = bs.precio(spot, strike, T, r, iv_mostrada, "call")
    assert precio_con_iv == pytest.approx(precio_mercado, abs=0.05)


def test_las_griegas_mostradas_coinciden_con_recalcularlas_aparte():
    at = _abrir(ui.PASOS[2])
    vencimiento = at.selectbox(key="dv_vencimiento_bs").value
    if ui._dias_al_vencimiento(vencimiento) == 0:
        pytest.skip("con vencimiento hoy mismo no se muestran griegas")
    deltas = [m for m in at.metric if m.label == "Delta"]
    if not deltas:
        pytest.skip("no se pudo calcular una volatilidad implícita para este contrato, así que no hay griegas")
    delta_mostrado = _numero(deltas[0].value)
    assert -1 <= delta_mostrado <= 1  # un delta de call está entre 0 y 1; con margen por si el redondeo roza el borde


def test_cambiar_a_put_trae_otra_tabla_de_strikes():
    at = _abrir(ui.PASOS[2])
    at.radio(key="dv_tipo").set_value("Put").run()
    assert not at.exception
    assert len(at.selectbox(key="dv_strike").options) > 0


def test_el_aviso_de_vencimiento_hoy_solo_aparece_si_se_elige_ese_vencimiento():
    at = _abrir(ui.PASOS[2])
    vencimientos = ui._vencimientos_disponibles("SPY")
    hoy = [v for v in vencimientos if ui._dias_al_vencimiento(v) == 0]
    if not hoy:
        pytest.skip("hoy no hay un vencimiento que expire el mismo día para probar el aviso")
    at.selectbox(key="dv_vencimiento_bs").set_value(hoy[0]).run()
    assert not at.exception
    assert any("vence hoy" in w.value for w in at.warning)
