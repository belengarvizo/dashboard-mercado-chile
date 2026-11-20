"""I-6: tasas de Chile en el informe (BCP nominal, BCU real, inflación implícita, TPM) sin cifras fijas ni lecturas
económicas incorrectas (offline, datos sintéticos).

QUÉ SE PRUEBA
    - La inflación implícita usa la relación EXACTA de Fisher, (1 + i) = (1 + r) × (1 + π), calculada en decimales; la
      resta simple BCP − BCU se informa como aproximación (y sigue siendo la cifra que muestra el dashboard).
    - La inflación implícita no se presenta como inflación esperada (incluye primas y el rezago de la UF).
    - El recuadro de la UF usa las tasas de su fecha o ninguna cifra: nunca ejemplos fijos que parezcan actuales.
    - El diferencial TPM − fondos federales se presenta como referencia, no como ganancia de una estrategia.
    - Sin datos, no se inventa nada; los ETFs no cambian.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import re
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import estructura_tasas as et  # noqa: E402
import informe_base as ib  # noqa: E402
import informe_renta_fija as inf  # noqa: E402
import renta_fija_ui as rfui  # noqa: E402

FECHAS = pd.bdate_range("2025-01-06", periods=420)
N = len(FECHAS)


def _fisher(i_pct, r_pct):
    """Cálculo aparte: π = (1 + i) / (1 + r) − 1, con las tasas en decimales; resultado en %."""
    return ((1 + i_pct / 100) / (1 + r_pct / 100) - 1) * 100


def _mundo(chile=None, semilla=5):
    rng = np.random.default_rng(semilla)
    tasa = 4.0 + np.concatenate([[0.0], rng.normal(0, 0.03, N - 1)]).cumsum()
    filas = [{"nombre": rfui.nombre_treasury(e), "fecha": f, "valor": float(v)} for e in et.PLAZOS_ANIOS for f, v in zip(FECHAS, tasa)]
    for nombre, (valor, hasta) in (chile or {}).items():
        filas += [{"nombre": nombre, "fecha": f, "valor": float(valor)} for f in FECHAS if hasta is None or f <= hasta]
    cambios = np.diff(tasa, prepend=tasa[0]) / 100
    precios = pd.DataFrame({t: 100 * np.cumprod(1 - d * cambios) for t, d in {"SHY": 1.9, "IEF": 6.5}.items()}, index=FECHAS)
    return pd.DataFrame(filas), precios


CHILE = {rfui.NOMBRE_BCP10: (5.80, None), rfui.NOMBRE_BCU10: (2.45, None),
         rfui.NOMBRE_TPM_CHILE: (4.75, None), rfui.NOMBRE_TPM_EEUU: (3.90, None)}


def _texto_pdf(pdf: bytes) -> str:
    pymupdf = pytest.importorskip("pymupdf", reason="pymupdf no está instalado: no se puede leer el PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return " ".join(" ".join(p.get_text().split()) for p in doc)


def _seccion_4(texto: str) -> str:
    return texto[texto.find("4. CHILE"):texto.find("5. QUÉ PASARÍA")]


# ---------------------------------------------------------------------------
# Fisher: exacta frente a aproximada, unidades
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("i,r", [(6.0, 2.6), (5.8, 2.45), (8.4, 1.2), (3.0, 3.0), (2.0, -0.5)])
def test_la_inflacion_implicita_exacta_es_la_de_fisher_y_difiere_de_la_resta(i, r):
    exacta = inf.inflacion_implicita_fisher(i, r)
    assert exacta == pytest.approx(_fisher(i, r), abs=1e-12)
    # De (1 + i) = (1 + r)(1 + π): i = r + π + r·π, así que la resta i − r excede a π exactamente en r·π (en decimales).
    assert (i - r) - exacta == pytest.approx((r / 100) * (exacta / 100) * 100, abs=1e-9)
    # Unidades: entra y sale en % anual (6,0 y 2,6 dan ≈ 3,31, no 0,0331 ni 331).
    if (i, r) == (6.0, 2.6):
        assert 3.3 < exacta < 3.32 and i - r == pytest.approx(3.4)


@pytest.mark.parametrize("i,r", [(None, 2.0), (5.0, None), (float("nan"), 2.0), (5.0, -100.0)])
def test_sin_datos_validos_no_hay_inflacion_implicita(i, r):
    assert inf.inflacion_implicita_fisher(i, r) is None


def test_los_datos_de_chile_traen_la_exacta_y_la_resta_simple_que_muestra_el_dashboard():
    macro, precios = _mundo(CHILE)
    chile = inf.calcular(macro, precios, 30, "Último mes")["chile"]
    assert chile["inflacion_implicita"] == pytest.approx(5.80 - 2.45)                 # la del dashboard, sin cambios
    assert chile["inflacion_implicita_exacta"] == pytest.approx(_fisher(5.80, 2.45))
    assert chile["diferencial"] == pytest.approx(4.75 - 3.90)


def test_bcp_y_bcu_se_toman_en_su_ultima_fecha_comun():
    corte_bcu = FECHAS[-15]
    macro, precios = _mundo({rfui.NOMBRE_BCP10: (5.8, None), rfui.NOMBRE_BCU10: (2.45, corte_bcu)})
    chile = inf.calcular(macro, precios, 30, "Último mes")["chile"]
    assert chile["fecha_curva_chile"] == corte_bcu


# ---------------------------------------------------------------------------
# Textos del PDF y del resumen
# ---------------------------------------------------------------------------
def test_el_resumen_distingue_la_exacta_de_la_aproximacion_y_no_la_llama_inflacion_esperada():
    macro, precios = _mundo(CHILE)
    datos = inf.calcular(macro, precios, 30, "Último mes")
    frase = next(a.texto for a in datos["afirmaciones"] if a.clave == "chile")
    assert ib.pct(_fisher(5.80, 2.45)) in frase and ib.pct(5.80 - 2.45) in frase
    assert "es una aproximación" in frase and "No es una medición directa de la inflación esperada" in frase
    assert "descuenta una inflación" not in frase


def test_el_pdf_no_trae_cifras_fijas_y_el_recuadro_usa_las_tasas_de_su_fecha():
    macro, precios = _mundo(CHILE)
    texto = _texto_pdf(inf.generar(macro, precios, "Último mes"))
    assert "2,6%" not in texto and "6,0%" not in texto
    recuadro = texto[texto.find("Error frecuente: comparar una tasa en UF"):texto.find("5. QUÉ PASARÍA")]
    assert ib.pct(2.45) in recuadro and ib.pct(5.80) in recuadro
    assert ib.pct(_fisher(5.80, 2.45)) in recuadro
    assert "inflación que efectivamente ocurra" in recuadro
    # El rendimiento nominal del BCU no se presenta como asegurado: vale hasta el vencimiento; antes, manda el precio.
    assert "Mantenido hasta el vencimiento" in recuadro and "si se vende antes" in recuadro
    # La cifra lleva la fecha de la curva, no «hoy».
    fecha = ib.fecha(inf.calcular(macro, precios, 30, "Último mes")["chile"]["fecha_curva_chile"])
    assert f"al {fecha}, {ib.pct(_fisher(5.80, 2.45))}" in recuadro and "(hoy" not in recuadro


def test_sin_datos_de_chile_el_recuadro_explica_sin_ninguna_cifra():
    macro, precios = _mundo()
    texto = _texto_pdf(inf.generar(macro, precios, "Último mes"))
    recuadro = texto[texto.find("Error frecuente: comparar una tasa en UF"):texto.find("5. QUÉ PASARÍA")]
    assert recuadro and not re.search(r"\d+[.,]\d+\s?%", recuadro), recuadro
    assert not any(a.clave == "chile" for a in inf.calcular(macro, precios, 30, "Último mes")["afirmaciones"])


def test_ya_no_se_iguala_la_implicita_con_la_esperada_ni_el_diferencial_con_una_ganancia():
    macro, precios = _mundo(CHILE)
    seccion = _seccion_4(_texto_pdf(inf.generar(macro, precios, "Último mes")))
    assert "que es justamente la implícita" not in seccion
    assert "No es la inflación esperada" in seccion and "relación exacta de Fisher" in seccion
    assert "Ese diferencial es lo que gana" not in seccion
    assert "no una ganancia asegurada" in seccion and "tasa efectiva de fondos federales" in seccion


def test_con_solo_el_bcp_no_se_inventa_la_tasa_real_ni_la_implicita():
    macro, precios = _mundo({rfui.NOMBRE_BCP10: (5.8, None)})
    datos = inf.calcular(macro, precios, 30, "Último mes")
    assert datos["chile"]["inflacion_implicita"] is None and datos["chile"]["inflacion_implicita_exacta"] is None
    seccion = _seccion_4(_texto_pdf(inf.generar(macro, precios, "Último mes")))
    assert ib.pct(5.8) not in seccion            # sin el BCU, el párrafo de la curva chilena no se escribe


# ---------------------------------------------------------------------------
# Lo demás no cambia
# ---------------------------------------------------------------------------
def test_los_datos_de_chile_no_cambian_nada_de_los_etfs():
    macro_con, precios = _mundo(CHILE)
    macro_sin, _ = _mundo()
    a = inf.calcular(macro_con, precios, 365, "Último año")
    b = inf.calcular(macro_sin, precios, 365, "Último año")
    columnas = [c for c in a["etfs"].columns if c != "ultima_fecha"]
    pd.testing.assert_frame_equal(a["etfs"][columnas], b["etfs"][columnas])
    assert [(e["ETF"], e["clase"]) for e in a["evaluaciones"]] == [(e["ETF"], e["clase"]) for e in b["evaluaciones"]]
