"""I-6d: el diferencial de tasas y el carry trade se explican sin presentarlos como ganancias (offline, datos sintéticos).

Corre las funciones reales de la pantalla (renta_fija_ui._paso_banco_central y fx_carry_ui.render_fx_carry) con
AppTest.from_function, sin base de datos, y los textos del glosario de FX.

QUÉ SE PRUEBA
    - Renta Fija: el diferencial TPM Chile − tasa efectiva de fondos federales conserva su valor; se rotula como tal y se
      presenta como referencia de condiciones monetarias, no como la base o la rentabilidad de un carry trade.
    - FX: el diferencial del gráfico «Dólar y diferencial de tasas» conserva sus puntos; la nota ya no dice que «es lo que
      gana» un inversionista; la introducción distingue el mecanismo teórico de la rentabilidad real y explica la cobertura.
    - Glosario: el diferencial positivo, negativo y nulo se explica sin ganancias automáticas; el carry sobre riesgo es
      una relación descriptiva, sin umbrales ni juicios.
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

import catalogo_fx as c  # noqa: E402
import fx_carry_ui as fxui  # noqa: E402
import glosario_fx as gl  # noqa: E402
import renta_fija_ui as ui  # noqa: E402

FECHAS = pd.bdate_range(end="2026-11-18", periods=600)
GANANCIAS_AUTOMATICAS = ("base del *carry trade*", "base del carry", "es lo que gana", "lo gana quien", "gana el diferencial",
                         "paga razonablemente", "se cobra poco", "ganancia asegurada de")


def _arreglo(valor) -> np.ndarray:
    if isinstance(valor, dict) and "bdata" in valor:
        return np.frombuffer(base64.b64decode(valor["bdata"]), dtype=np.dtype(valor["dtype"]))
    return np.asarray(valor, dtype=float)


# ---------------------------------------------------------------------------
# Renta Fija: paso «Banco Central»
# ---------------------------------------------------------------------------
def _macro_renta_fija(tpm=4.75, fed=3.90, fecha_fed=None) -> pd.DataFrame:
    filas = []
    for nombre, valor in {ui.NOMBRE_TPM_CHILE: tpm, ui.NOMBRE_TPM_EEUU: fed}.items():
        hasta = fecha_fed if (nombre == ui.NOMBRE_TPM_EEUU and fecha_fed is not None) else FECHAS[-1]
        filas += [{"nombre": nombre, "fecha": f, "valor": valor} for f in FECHAS if f <= hasta]
    return pd.DataFrame(filas)


def _app_renta_fija(macro):
    import renta_fija_ui as ui
    ui._paso_banco_central(macro)


def _metrica(at, etiqueta):
    return next(m for m in at.metric if m.label == etiqueta)


def test_renta_fija_rotula_la_tasa_efectiva_y_conserva_el_diferencial():
    at = AppTest.from_function(_app_renta_fija, args=(_macro_renta_fija(4.75, 3.90, FECHAS[-3]),), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert _metrica(at, "Tasa efectiva de fondos federales (EE. UU.)").value == "3.90%"
    assert _metrica(at, "Diferencial TPM Chile − fondos federales (pp)").value == f"{4.75 - 3.90:,.2f} pp"
    etiquetas = [m.label for m in at.metric]
    assert "Tasa de política de EEUU (Fed funds)" not in etiquetas
    assert "Diferencial de política monetaria (Chile − EEUU)" not in etiquetas
    # la fecha de cada tasa sigue siendo la suya (H3, fuera de alcance: no se alinean)
    assert f"Al {FECHAS[-3].strftime('%d-%m-%Y')}" in [x.value for x in at.caption]


def test_renta_fija_explica_el_diferencial_como_referencia_y_no_como_rentabilidad():
    at = AppTest.from_function(_app_renta_fija, args=(_macro_renta_fija(),), default_timeout=60)
    at.run()
    nota = ui.NOTA_DIFERENCIAL_TPM_FED
    assert nota in [x.value for x in at.caption]
    for idea in ("referencia de las condiciones monetarias", "no una rentabilidad", "tasas de mercado (no a las de política)",
                 "costos de transacción y de financiamiento", "sin cobertura", "tipo de cambio", "*forward*",
                 "puntos forward tienden a compensar", "FX y Carry Trade"):
        assert idea in nota, idea
    textos = " ".join(x.value for x in at.caption) + " ".join(x.value for x in at.markdown)
    for expresion in GANANCIAS_AUTOMATICAS:
        assert expresion not in textos, expresion


# ---------------------------------------------------------------------------
# FX y Carry Trade
# ---------------------------------------------------------------------------
def _datos_fx(tpm=4.75, fed=4.00):
    rng = np.random.default_rng(7)
    tasas = {c.NOMBRE_TASA_EEUU: fed, c.NOMBRE_TASA_CHILE: tpm}
    for cod, nivel in {"EUR": 4.0, "GBP": 4.6, "JPY": 0.5, "MXN": 9.5, "BRL": 13.9}.items():
        tasas[c.MONEDAS_CARRY[cod]["serie_tasa"]] = nivel
    filas = [{"nombre": n, "fecha": f, "valor": float(v)} for n, v in tasas.items() for f in FECHAS]
    for nombre, nivel in ((c.NOMBRE_TIPO_DE_CAMBIO_OBSERVADO, 940.0), (c.NOMBRE_COBRE, 4.2)):
        serie = nivel * np.exp(rng.normal(0, 0.006, len(FECHAS)).cumsum())
        filas += [{"nombre": nombre, "fecha": f, "valor": float(x)} for f, x in zip(FECHAS, serie)]
    precios = [{"ticker": t, "fecha": f, "precio_cierre": float(x)} for t in c.PARES_FX
               for f, x in zip(FECHAS, 1.3 * np.exp(rng.normal(0, 0.005, len(FECHAS)).cumsum()))]
    return pd.DataFrame(filas), pd.DataFrame(precios)


def _app_fx(macro, precios):
    import fx_carry_ui
    fx_carry_ui.render_fx_carry(macro, precios)


def _abrir_fx(paso, **tasas) -> AppTest:
    at = AppTest.from_function(_app_fx, args=_datos_fx(**tasas), default_timeout=120)
    at.session_state["fx_paso"] = paso
    at.run()
    assert not at.exception, at.exception
    return at


def test_fx_la_nota_del_grafico_no_presenta_el_diferencial_como_ganancia_y_el_grafico_no_cambia():
    at = _abrir_fx(fxui.PASOS[3])
    nota = next(x.value for x in at.caption if x.value.startswith("Hoy la TPM de Chile"))
    assert "(4.75%) está 0.75 puntos porcentuales sobre la tasa efectiva de fondos federales (4.00%)" in nota
    for idea in ("tasas de referencia, no una ganancia", "tasas de mercado", "paga costos", "asume el tipo de cambio"):
        assert idea in nota, idea
    for expresion in GANANCIAS_AUTOMATICAS:
        assert expresion not in nota, expresion
    figuras = [pio.from_json(g.proto.spec) for g in at.get("plotly_chart")]
    (traza,) = [t for f in figuras for t in f.data if (t.name or "").startswith("TPM de Chile −")]
    assert traza.name == "TPM de Chile − tasa efectiva de fondos federales (pp, eje izquierdo)"
    assert np.allclose(_arreglo(traza.y), 0.75, atol=1e-12)      # la diferencia de las tasas, punto por punto


def test_fx_con_tasas_iguales_la_nota_no_inventa_un_sentido():
    nota = next(x.value for x in _abrir_fx(fxui.PASOS[3], tpm=4.0, fed=4.0).caption if x.value.startswith("Hoy la TPM"))
    assert "está igual a la tasa efectiva de fondos federales" in nota and "sobre" not in nota.split(".")[0]


def test_fx_la_introduccion_distingue_el_mecanismo_de_la_rentabilidad_y_explica_la_cobertura():
    at = _abrir_fx(fxui.PASOS[1])
    intro = next(x.value for x in at.markdown if "**carry trade**" in x.value)
    for idea in ("En teoría", "en la práctica", "tasas a las que realmente se puede invertir y financiarse",
                 "no las de referencia", "los costos", "paridad cubierta de tasas", "instrumentos comparables",
                 "puntos forward lo compensan", "calculada con las tasas de referencia"):
        assert idea in intro, idea
    textos = " ".join(x.value for x in at.caption) + intro
    assert "tasa efectiva de fondos federales" in textos and "Fed funds" not in textos
    for expresion in GANANCIAS_AUTOMATICAS:
        assert expresion not in textos, expresion
    assert "sin garantía de ganancia" in textos       # el diferencial negativo tampoco se presenta como ganancia al revés


# ---------------------------------------------------------------------------
# Glosario de FX
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tasa,diferencial,cifra", [(13.94, 10.06, "+10.06"), (1.04, -2.84, "-2.84"), (3.88, 0.0, "0.00"),
                                                    (3.88, -0.001, "0.00")])
def test_el_diferencial_del_glosario_nunca_es_una_ganancia_automatica(tasa, diferencial, cifra):
    texto = gl.explicacion_diferencial("el euro", tasa, 3.88, diferencial)
    assert f"Diferencial de tasas = {cifra} pp al año" in texto and "Tasas de referencia" in texto
    assert not re.search(r"\b(gana|pierde)\b", texto)
    if cifra == "0.00":
        assert "prácticamente no hay diferencial" in texto and "a favor" not in texto
    else:
        # positivo y negativo: no es una ganancia, porque intervienen las tasas efectivas, los costos y el tipo de cambio
        assert "el resultado depende de las tasas efectivas, los costos y el tipo de cambio" in texto
        if diferencial < 0:
            assert "a favor del dólar" in texto and "No hace rentable por sí solo la operación inversa" in texto
        else:
            assert "a favor del euro" in texto and "No es una ganancia realizable" in texto
    assert len(re.sub(r"<[^>]+>", "", texto)) <= 260        # breve (antes del ajuste, hasta ~430 caracteres)


@pytest.mark.parametrize("valor", [0.1, 0.49, 0.5, 0.71, 2.3, -0.6])
def test_el_carry_sobre_riesgo_se_explica_igual_sin_importar_su_valor(valor):
    texto = gl.explicacion_riesgo_carry(10.0, -5.0, valor)
    assert f"Carry sobre riesgo = {valor:.2f}" in texto
    explicacion = texto.split(f"Carry sobre riesgo = {valor:.2f}</b>")[1]
    assert explicacion == gl.explicacion_riesgo_carry(10.0, -5.0, 1.0).split("Carry sobre riesgo = 1.00</b>")[1]  # sin umbrales
    for idea in ("diferencial de tasas de referencia dividido por la volatilidad anualizada", "Es descriptivo",
                 "no es una rentabilidad ajustada por riesgo", "recomendación de inversión"):
        assert idea in texto, idea
    assert "razonablemente" not in texto and "poco por el riesgo" not in texto
