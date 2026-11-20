"""H2 + H4: una sola regla para escribir cifras (formato_numerico.cifra) y la lectura correcta de beta (offline).

QUÉ SE PRUEBA
    - cifra escribe exactamente como el formato de Python de siempre, salvo que lo que se lee como cero va sin signo;
      con 0, 1 y 2 decimales, con y sin signo, con y sin miles, valores grandes, NaN e infinito.
    - informe_base.num (PDF, I-7) y renta_fija_ui._fmt (pantallas) usan esa misma regla y no cambian nada más.
    - Los textos corregidos en H2 (tooltips de los cuatro glosarios, notas de Renta Variable) no muestran ceros con
      signo y conservan las demás cifras.
    - Beta (H4): sensibilidad histórica estimada con una relación lineal, sin unidades; un rendimiento del índice 1 pp
      mayor se asocia con uno β pp mayor del activo (menor si β es negativa); una beta negativa nunca se lee como
      ausencia de relación; cerca de cero se dice así, sin sugerir bajo riesgo ni independencia; la diversificación es
      posible, no garantizada; nunca como predicción. La misma frase en los tres glosarios.
    - El PDF escribe el diferencial TPM − fondos federales en puntos porcentuales (pp).
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import math
import os
import re
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import glosario_commodities as gcm  # noqa: E402
import glosario_fx as gfx  # noqa: E402
import glosario_renta_fija as grf  # noqa: E402
import glosario_renta_variable as grv  # noqa: E402
import informe_base as ib  # noqa: E402
import renta_fija_ui as rfui  # noqa: E402
import renta_variable_ui as rvui  # noqa: E402
from formato_numerico import cifra  # noqa: E402

CERO_CON_SIGNO = re.compile(r"(?<![\d.,])[+\-]0(?:\.0+)?(?![\d.,])")
BARRIDO = list(np.round(np.linspace(-0.03, 0.03, 601), 6)) + [-0.0, 0.0, 0.049, -0.051, 0.5, -0.5, 1234.5678, -98765.4321]


def _antes(valor, decimales, con_signo, miles):
    """El formato que se usaba en cada lugar antes de H2."""
    return f"{valor:{'+' if con_signo else ''}{',' if miles else ''}.{decimales}f}"


# ---------------------------------------------------------------------------
# La regla
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("decimales", [0, 1, 2])
@pytest.mark.parametrize("con_signo", [False, True])
@pytest.mark.parametrize("miles", [False, True])
def test_cifra_solo_cambia_lo_que_se_lee_como_cero(decimales, con_signo, miles):
    for valor in BARRIDO:
        antes, ahora = _antes(valor, decimales, con_signo, miles), cifra(valor, decimales, con_signo, miles)
        if float(f"{abs(valor):.{decimales}f}") == 0:
            assert ahora == f"{0.0:.{decimales}f}", (valor, ahora)            # «0», «0.0», «0.00»: sin signo
        else:
            assert ahora == antes, (valor, antes, ahora)                     # todo lo demás, idéntico


def test_cifra_con_nan_e_infinito_escribe_lo_mismo_que_antes():
    for valor in (math.nan, math.inf, -math.inf):
        assert cifra(valor, 2, True) == _antes(valor, 2, True, True)
    assert cifra(np.float64(-0.004), 2, True) == "0.00" and cifra(np.float32(1.5), 1) == "1.5"


def test_informe_base_num_es_la_misma_regla_y_conserva_el_guion_de_los_faltantes():
    for valor in BARRIDO:
        for decimales in (0, 1, 2):
            for con_signo in (False, True):
                assert ib.num(valor, decimales, con_signo) == cifra(valor, decimales, con_signo)
    assert ib.num(None) == "—" and ib.num(float("nan")) == "—" and ib.pct(None) == "—"
    assert ib.pct(-0.004, 2, True) == "0.00%" and ib.pct(1.25, 2, True) == "+1.25%"


def test_fmt_de_renta_fija_solo_cambia_los_ceros():
    for valor in BARRIDO:
        for decimales in (0, 1, 2):
            antes = f"{valor:,.{decimales}f}"
            esperado = f"{0.0:,.{decimales}f}" if float(f"{abs(valor):.{decimales}f}") == 0 else antes
            assert rfui._fmt(valor, decimales) == esperado
    assert rfui._fmt(-0.001) + " pp" == "0.00 pp" and rfui._fmt(12345.678) == "12,345.68"


# ---------------------------------------------------------------------------
# Textos corregidos (H2)
# ---------------------------------------------------------------------------
def _sin_html(texto: str) -> str:
    return re.sub(r"<[^>]+>", " ", texto)


@pytest.mark.parametrize("valor", [-0.04, -0.0, 0.0, 0.04])
def test_los_tooltips_no_muestran_ceros_con_signo(valor):
    textos = [m.explicacion_retorno(valor, -valor) for m in (grf, grv, gcm)]
    textos += [gfx.explicacion_movimiento("USDCLP=X", valor, -valor), gfx.explicacion_spot_y_total("el yen", valor, -valor, valor),
               grv.explicacion_relativo(valor, valor), gfx.explicacion_riesgo_carry(8.0, -3.0, valor / 10)]
    estadisticas = {"dias": 250, "anualizado": valor, "volatilidad": 8.0, "caida_maxima": -1.0, "peor_mes": valor,
                    "fecha_peor_mes": pd.Timestamp("2026-01-05"), "meses_ganadores": 50.0}
    textos.append(gfx.explicacion_estrategia("el yen", "larga", estadisticas))
    for texto in textos:
        assert not CERO_CON_SIGNO.search(_sin_html(texto)), texto


def test_los_tooltips_conservan_las_cifras_distintas_de_cero():
    assert "en el último mes +1.2% y en lo que va del año -3.4%" in grf.explicacion_retorno(1.234, -3.4)
    assert "Resultado del último año = +6.1%" in gfx.explicacion_spot_y_total("el real", -2.0, 8.1, 6.1)
    assert "Contra el S&amp;P 500 = -2.5 pp" in grv.explicacion_relativo(-2.5, 10.0)
    assert "(+10.0% propio)" in grv.explicacion_relativo(-2.5, 10.0)
    assert "Carry sobre riesgo = 0.71" in gfx.explicacion_riesgo_carry(14.2, -7.7, 0.71)


def test_mejor_y_peor_de_renta_variable_sin_ceros_con_signo():
    resumen = pd.DataFrame({"Retorno 1 año (%)": [0.04, -0.03, 5.2]}, index=["A", "B", "C"])
    texto = rvui._mejor_y_peor(resumen, "Retorno 1 año (%)", "En el último año")
    assert "**C** (+5.2%)" in texto and "**B** (0.0%)" in texto


# ---------------------------------------------------------------------------
# Beta (H4)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("modulo,sujeto", [(grf, "este ETF"), (grv, "este ETF"), (gcm, "este commodity")])
@pytest.mark.parametrize("beta,magnitud,mismo,contrario", [(1.2, "1.20", "mayor", "menor"), (0.35, "0.35", "mayor", "menor"),
                                                           (-0.42, "0.42", "menor", "mayor"), (-1.5, "1.50", "menor", "mayor")])
def test_la_beta_se_explica_como_sensibilidad_lineal_con_su_signo(modulo, sujeto, beta, magnitud, mismo, contrario):
    texto = modulo.explicacion_beta(beta)
    assert f"Beta vs S&amp;P 500 = {beta:.2f}" in texto
    assert "sensibilidad histórica estimada con una relación lineal; no tiene unidades" in texto
    assert (f"un rendimiento del S&amp;P 500 1 punto porcentual (pp) mayor se asocia con un rendimiento de {sujeto} unos "
            f"{magnitud} pp {mismo}; uno 1 pp menor, con un rendimiento unos {magnitud} pp {contrario}") in texto
    assert "No garantiza movimientos futuros" in texto
    assert "sube o baja 1%" not in texto and "se movió cerca de" not in texto


@pytest.mark.parametrize("modulo", [grf, grv, gcm])
@pytest.mark.parametrize("beta", [-1.5, -0.42, -0.2, -0.06])
def test_una_beta_negativa_nunca_se_lee_como_ausencia_de_relacion(modulo, beta):
    texto = modulo.explicacion_beta(beta)
    lectura = texto.split("No garantiza movimientos futuros.")[1]
    assert "no depende" not in lectura
    if beta <= -0.2:
        assert "dirección contraria" in lectura
    else:   # negativa pequeña: la lectura por tramos habla de magnitud baja, sin negar la relación
        assert "dirección contraria" in lectura or "baja" in lectura or "cercana a cero" in lectura
    assert "pp menor; uno 1 pp menor, con un rendimiento" in texto            # la frase principal también va al revés


@pytest.mark.parametrize("modulo", [grf, grv, gcm])
@pytest.mark.parametrize("beta", [0.0, 0.003, -0.004])
def test_una_beta_cercana_a_cero_se_dice_asi_sin_signo_y_sin_sugerir_independencia(modulo, beta):
    texto = modulo.explicacion_beta(beta)
    assert "Beta vs S&amp;P 500 = 0.00" in texto and "Aquí es cercana a cero" in texto
    assert "no implica bajo riesgo ni independencia" in texto and "no depende" not in texto
    assert not CERO_CON_SIGNO.search(_sin_html(texto))


def test_la_diversificacion_se_presenta_como_posible_y_no_garantizada():
    for texto in (grf.explicacion_beta(-0.3), grf.explicacion_beta(0.1), gcm.explicacion_beta(-0.48)):
        assert "puede ayudar a diversificar" in texto and "no lo garantiza" in texto
    assert "Mientras más baja, más sirve" not in grf.explicacion_beta(-0.3)
    assert "lo vuelve útil para diversificar" not in gcm.explicacion_beta(-0.48)


def test_los_tres_glosarios_usan_la_misma_frase_de_beta():
    for beta in (0.8, -0.3, 0.0):
        frases = {re.search(r"Beta es una sensibilidad.*?No garantiza movimientos futuros\.", m.explicacion_beta(beta)).group(0)
                  .replace("commodity", "ETF") for m in (grf, grv, gcm)}
        assert len(frases) == 1, frases


# ---------------------------------------------------------------------------
# PDF (H4)
# ---------------------------------------------------------------------------
def test_el_pdf_escribe_el_diferencial_de_tasas_cortas_en_pp():
    import test_informe_renta_fija_chile as tc
    import informe_renta_fija as inf
    macro, precios = tc._mundo(tc.CHILE)
    texto = tc._texto_pdf(inf.generar(macro, precios, "Último mes"))
    assert "un diferencial de +0.85 puntos porcentuales (pp) entre las tasas de corto plazo" in texto
    assert "+0.85 puntos entre" not in texto
