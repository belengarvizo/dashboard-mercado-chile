"""I-6 / I-6c: tasas de Chile en el informe (BCP nominal, BCU real, diferencial BCP − BCU, TPM) sin cifras fijas ni
lecturas económicas incorrectas (offline, datos sintéticos).

QUÉ SE PRUEBA
    - La función de Fisher, (1 + i) = (1 + r) × (1 + π) en decimales, sigue calculando lo mismo y se conserva en los
      datos; pero (I-6c) el PDF ya no imprime su resultado: la documentación pública revisada no confirma que las series
      BCP y BCU usen la misma convención de capitalización.
    - La cifra principal es el diferencial BCP − BCU, en puntos porcentuales, presentado como aproximación a la
      compensación por inflación; nunca como inflación esperada ni como medición exacta.
    - El texto distingue la exactitud algebraica de la identidad de Fisher de la exactitud de una medición.
    - El recuadro de la UF usa las tasas de su fecha o ninguna cifra, no presenta el diferencial como umbral exacto y
      distingue el rendimiento al vencimiento de la rentabilidad realizada si se vende antes.
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
def test_el_resumen_presenta_el_diferencial_en_pp_como_aproximacion_y_no_imprime_fisher():
    macro, precios = _mundo(CHILE)
    datos = inf.calcular(macro, precios, 30, "Último mes")
    frase = next(a.texto for a in datos["afirmaciones"] if a.clave == "chile")
    assert "diferencial BCP − BCU a 10 años es de 3.35 pp" in frase
    assert ib.pct(5.80) in frase and ib.pct(2.45) in frase
    assert "aproximación a la compensación por inflación" in frase
    assert "No equivale a la inflación esperada ni es una medición exacta" in frase
    for limite in ("primas por riesgo de inflación y por liquidez", "diferencias de emisor y de duración", "rezago de la UF"):
        assert limite in frase, limite
    # I-6c: ni la cifra de Fisher ni la diferencia escrita como tasa («3.35%»)
    assert ib.pct(_fisher(5.80, 2.45)) not in frase and ib.pct(5.80 - 2.45) not in frase and "Fisher" not in frase
    assert "descuenta una inflación" not in frase and "inflación implícita" not in frase


def test_el_pdf_no_trae_cifras_fijas_y_el_recuadro_usa_las_tasas_de_su_fecha():
    macro, precios = _mundo(CHILE)
    texto = _texto_pdf(inf.generar(macro, precios, "Último mes"))
    assert "2,6%" not in texto and "6,0%" not in texto
    recuadro = texto[texto.find("Error frecuente: comparar una tasa en UF"):texto.find("5. QUÉ PASARÍA")]
    assert ib.pct(2.45) in recuadro and ib.pct(5.80) in recuadro
    assert "inflación que efectivamente ocurra" in recuadro
    # Rendimiento al vencimiento frente a rentabilidad realizada si se vende antes.
    assert "Mantenido hasta el vencimiento" in recuadro and "rendimiento al vencimiento" in recuadro
    assert "si se vende antes" in recuadro and "rentabilidad realizada" in recuadro and "precio de mercado" in recuadro
    # I-6c: el diferencial no es un umbral exacto de inflación, ni promete que un bono rinda más que el otro.
    assert "no un umbral exacto" in recuadro and "bonos comparables" in recuadro and "horizonte concreto" in recuadro
    assert "habrá rendido más" not in recuadro and ib.pct(_fisher(5.80, 2.45)) not in recuadro
    # La cifra lleva la fecha de la curva, no «hoy», y está en pp.
    fecha = ib.fecha(inf.calcular(macro, precios, 30, "Último mes")["chile"]["fecha_curva_chile"])
    assert f"al {fecha}, 3.35 pp" in recuadro and "(hoy" not in recuadro


def test_sin_datos_de_chile_el_recuadro_explica_sin_ninguna_cifra():
    macro, precios = _mundo()
    texto = _texto_pdf(inf.generar(macro, precios, "Último mes"))
    recuadro = texto[texto.find("Error frecuente: comparar una tasa en UF"):texto.find("5. QUÉ PASARÍA")]
    assert recuadro and not re.search(r"\d+[.,]\d+\s?(%|pp)", recuadro), recuadro
    assert "no un umbral exacto" in recuadro
    assert not any(a.clave == "chile" for a in inf.calcular(macro, precios, 30, "Último mes")["afirmaciones"])


def test_la_seccion_4_usa_el_diferencial_y_separa_la_identidad_de_fisher_de_una_medicion():
    macro, precios = _mundo(CHILE)
    seccion = _seccion_4(_texto_pdf(inf.generar(macro, precios, "Último mes")))
    assert "que es justamente la implícita" not in seccion
    assert "diferencial de 3.35 pp" in seccion and "aproximación a la compensación por inflación" in seccion
    assert "No es la inflación esperada, ni una predicción, ni una medición exacta" in seccion
    for limite in ("primas por riesgo de inflación y por liquidez", "mismo emisor", "bonos de la Tesorería",
                   "distinta duración, cupones", "rezago respecto del IPC"):
        assert limite in seccion, limite
    # Fisher: la identidad es exacta como álgebra; aplicada a estas series no es una medición exacta, y no se imprime.
    assert "La relación de Fisher." in seccion and "exacta como relación algebraica" in seccion
    assert "no entregaría una medición exacta" in seccion and "no permite confirmar" in seccion
    assert "relación exacta de Fisher" not in seccion and "inflación implícita" not in seccion
    assert ib.pct(_fisher(5.80, 2.45)) not in seccion and ib.pct(5.80 - 2.45) not in seccion
    assert "Ese diferencial es lo que gana" not in seccion
    assert "no una ganancia asegurada" in seccion and "tasa efectiva de fondos federales" in seccion


# ---------------------------------------------------------------------------
# I-6c: en todo el PDF, sin precisión económica injustificada y sin contradicciones
# ---------------------------------------------------------------------------
ESCENARIOS = {
    "base": CHILE,
    "tasa_real_baja": {rfui.NOMBRE_BCP10: (8.40, None), rfui.NOMBRE_BCU10: (1.20, None)},
    "bcu_sobre_bcp": {rfui.NOMBRE_BCP10: (2.10, None), rfui.NOMBRE_BCU10: (2.60, FECHAS[-10])},
}
EXPRESIONES_PROHIBIDAS = (
    "inflación implícita exacta", "relación exacta de Fisher", "el mercado espera", "inflación esperada del mercado",
    "descuenta una inflación", "puesta en precio", "habrá rendido más", "inflación implícita a diez años",
)


@pytest.mark.parametrize("escenario", ESCENARIOS)
@pytest.mark.parametrize("periodo", ["Último mes", "Último año"])
def test_ninguna_parte_del_pdf_atribuye_precision_economica_al_diferencial_ni_a_fisher(escenario, periodo):
    macro, precios = _mundo(ESCENARIOS[escenario])
    texto = _texto_pdf(inf.generar(macro, precios, periodo))
    for expresion in EXPRESIONES_PROHIBIDAS:
        assert expresion not in texto, expresion
    chile = inf.calcular(macro, precios, 30, "Último mes")["chile"]
    # La cifra de Fisher no aparece en ninguna parte (ni como tasa ni como número suelto).
    assert ib.pct(chile["inflacion_implicita_exacta"]) not in texto
    # El mismo diferencial, en pp, en el resumen, la sección 4 y el recuadro: no hay dos cifras distintas.
    pp = f"{ib.num(chile['inflacion_implicita'], 2)} pp"
    resumen_chile, seccion = texto[texto.find("En Chile,"):texto.find("1. QUÉ PASÓ")], _seccion_4(texto)
    recuadro = texto[texto.find("Error frecuente: comparar una tasa en UF"):texto.find("5. QUÉ PASARÍA")]
    assert pp in resumen_chile and pp in seccion and pp in recuadro
    assert set(re.findall(r"-?\d+\.\d{2} pp", resumen_chile + seccion)) == {pp}


def test_con_el_bcu_sobre_el_bcp_el_recuadro_no_dice_que_el_bcu_rinde_menos():
    macro, precios = _mundo(ESCENARIOS["bcu_sobre_bcp"])
    texto = _texto_pdf(inf.generar(macro, precios, "Último mes"))
    recuadro = texto[texto.find("Error frecuente: comparar una tasa en UF"):texto.find("5. QUÉ PASARÍA")]
    assert "-0.50 pp" in recuadro and "Eso no significa que el BCU rinda menos" not in recuadro
    macro, precios = _mundo(CHILE)
    recuadro = _texto_pdf(inf.generar(macro, precios, "Último mes"))
    assert "Eso no significa que el BCU rinda menos" in recuadro    # con BCU < BCP la aclaración sí corresponde


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
