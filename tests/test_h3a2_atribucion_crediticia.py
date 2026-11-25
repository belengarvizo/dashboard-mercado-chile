"""H3-A2: atribución de los fondos con crédito según el estado del spread Baa (offline, datos sintéticos).

Tres estados (ver informe_renta_fija._evaluar_atribucion):
    A  spread comparable con cambio material      → «credito» (efectos que pueden compensarse; no se separan)
    B  spread comparable sin cambio material      → la clase por tasas («consistente», «parcial»), con la aclaración de
                                                    que el Baa es una referencia agregada
    C  spread ausente o no comparable en la ventana → «credito_indeterminado»: nunca se trata como B

El estado C no cambia ninguna cifra: retorno, lo anticipado por la duración y la diferencia son los mismos.
Las pruebas son sintéticas: verifican la lógica, no validan datos reales.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import sys

import numpy as np
import pandas as pd
import pymupdf
import pytest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(RAIZ)

import informe_renta_fija as inf  # noqa: E402
import renta_fija_ui as rfui  # noqa: E402
import test_informe_renta_fija as tinf  # noqa: E402
import test_informe_renta_fija_conclusiones as tc  # noqa: E402

CTX = {**tc.CTX, "ruedas_spread": 21}   # sin variabilidad: manda el piso de 5 pb
FILAS = {
    "LQD_sube": ("LQD", tc._fila(1.45, 6.5, -0.20, plazo=10)),      # consistente, retorno positivo
    "LQD_baja": ("LQD", tc._fila(-1.45, 6.5, 0.20, plazo=10)),      # consistente, retorno negativo
    "HYG_sube": ("HYG", tc._fila(3.00, 6.5, -0.20, plazo=5)),       # parcial, retorno positivo
    "HYG_baja": ("HYG", tc._fila(-1.40, 6.5, 0.20, plazo=5)),       # consistente, retorno negativo
}
CLASE_POR_TASAS = {"LQD_sube": "consistente", "LQD_baja": "consistente", "HYG_sube": "parcial", "HYG_baja": "consistente"}


# ---------------------------------------------------------------------------
# Los tres estados en la evaluación de cada fondo
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("caso", list(FILAS))
@pytest.mark.parametrize("cambio_pp, estado, clase", [
    (0.02, inf.SPREAD_SIN_CAMBIO_MATERIAL, None),        # B: la clase por tasas
    (0.0499, inf.SPREAD_SIN_CAMBIO_MATERIAL, None),      # B: justo bajo el umbral de 5 pb
    (0.05, inf.SPREAD_MATERIAL, "credito"),               # A: en el umbral (material, umbral vigente)
    (0.25, inf.SPREAD_MATERIAL, "credito"),               # A: ampliación
    (-0.25, inf.SPREAD_MATERIAL, "credito"),              # A: compresión
])
def test_spread_comparable_con_y_sin_cambio_material(caso, cambio_pp, estado, clase):
    ticker, fila = FILAS[caso]
    ev = inf._evaluar_atribucion(ticker, fila, CTX, tc._credito(cambio_pp))
    assert ev["estado_spread"] == estado
    assert ev["clase"] == (clase or CLASE_POR_TASAS[caso])
    assert ev["spread_pb"] == pytest.approx(cambio_pp * 100)


@pytest.mark.parametrize("caso", list(FILAS))
def test_sin_spread_comparable_la_contribucion_del_credito_queda_indeterminada(caso):
    ticker, fila = FILAS[caso]
    con_b = inf._evaluar_atribucion(ticker, fila, CTX, tc._credito(0.02))
    ev = inf._evaluar_atribucion(ticker, fila, CTX, None)
    assert ev["clase"] == "credito_indeterminado" and ev["estado_spread"] == inf.SPREAD_NO_COMPARABLE
    assert ev["clase"] != con_b["clase"] and ev["nivel"] == inf.NIVEL_INSUFICIENTE   # C no se trata como B
    assert ev["clase_tasas"] == CLASE_POR_TASAS[caso]
    assert ev["spread_pb"] is None                                                   # no se reemplaza por cero
    assert ("spread comparable en la ventana", False, None, None) in ev["condiciones"]
    assert not any(c[0] == "spread sin cambio material" for c in ev["condiciones"])
    # los cálculos de duración no cambian
    for campo in ("retorno", "anticipado", "diferencia", "cambio_pb", "umbral_retorno"):
        assert ev[campo] == con_b[campo]
    frase = inf._frase_de_evaluacion(ev)
    assert "no hay datos comparables del spread Baa que permitan determinar la contribución del crédito" in frase
    assert "no puede atribuirse exclusivamente a los movimientos de tasas" in frase
    assert "da cuenta solo de una parte" not in frase and "en línea con" not in frase
    # «cercano» solo cuando se cumple el criterio de proximidad (clase por tasas «consistente»)
    assert ("numéricamente cercano" in frase) == (CLASE_POR_TASAS[caso] == "consistente")
    if CLASE_POR_TASAS[caso] == "parcial":
        assert "más de lo que permite el criterio de proximidad" in frase


def test_los_fondos_sin_credito_no_dependen_del_spread():
    fila = tc._fila(1.45, 6.5, -0.20)
    assert inf._evaluar_atribucion("IEF", fila, CTX, None)["clase"] == "consistente"
    assert "estado_spread" not in inf._evaluar_atribucion("IEF", fila, CTX, None)


def test_en_el_estado_b_no_se_afirma_que_el_credito_del_fondo_se_mantuvo():
    ticker, fila = FILAS["LQD_sube"]
    frase = inf._frase_de_evaluacion(inf._evaluar_atribucion(ticker, fila, CTX, tc._credito(0.02)))
    assert "referencia agregada" in frase and "no asegura que el riesgo de crédito propio del fondo se haya mantenido" in frase


def test_el_resumen_nombra_a_los_fondos_sin_spread_comparable_y_no_los_da_por_consistentes():
    etfs = tc._tabla({"LQD": FILAS["LQD_sube"][1], "IEF": tc._fila(1.45, 6.5, -0.20)})
    datos = tc._datos(etfs, CTX, None)
    a = inf._afirmacion_atribucion(datos, inf._evaluaciones(datos))
    assert "El retorno de IEF es consistente" in a.texto and "LQD es consistente" not in a.texto
    assert "En LQD, fondos con riesgo de crédito, no hay datos comparables del spread Baa" in a.texto
    assert ("LQD", "credito_indeterminado") in a.condiciones


# ---------------------------------------------------------------------------
# PDF completo: Baa constante, ausente, fuera de la ventana y con valores vacíos
# ---------------------------------------------------------------------------
def _mundo(variante: str):
    fechas = pd.bdate_range("2024-01-01", periods=500)
    tasa = tinf._tasa_sintetica(fechas, 4.0, 5.0)
    macro = tinf._macro_sintetico(fechas, tasa)
    precios = tinf._precios_sinteticos(fechas, tasa)
    rng = np.random.default_rng(4)
    cambios = pd.Series(tasa, index=fechas).diff().fillna(0.0).to_numpy() / 100.0
    for t, d in (("LQD", 8.0), ("HYG", 3.5)):
        precios[t] = 100 * (1 + (-d * cambios + rng.normal(0, 0.0004, len(fechas)))).cumprod()
    baa = macro["nombre"] == rfui.NOMBRE_BAA10Y
    if variante == "ausente":
        macro = macro[~baa]
    elif variante == "fuera_de_ventana":
        macro = macro[~baa | (macro["fecha"] <= sorted(macro.loc[baa, "fecha"].unique())[-10])]
    elif variante == "vacios_al_final":
        macro = macro.copy()
        macro.loc[baa & macro["fecha"].isin(sorted(macro.loc[baa, "fecha"].unique())[-5:]), "valor"] = np.nan
    return macro, precios


@pytest.mark.parametrize("variante", ["ausente", "fuera_de_ventana", "vacios_al_final"])
def test_el_pdf_no_atribuye_a_la_duracion_lo_que_no_puede_verificar(variante):
    macro, precios = _mundo(variante)
    base = inf.calcular(*_mundo("constante"), 30, "Último mes")
    d = inf.calcular(macro, precios, 30, "Último mes")
    clases = {e["ETF"]: e["clase"] for e in d["evaluaciones"]}
    assert clases["LQD"] == clases["HYG"] == "credito_indeterminado"
    assert {e["ETF"]: e["clase"] for e in base["evaluaciones"]}["LQD"] == "consistente"     # con Baa comparable
    pd.testing.assert_frame_equal(d["etfs"], base["etfs"])                                   # cifras intactas
    with pymupdf.open(stream=inf.generar(macro, precios, "Último mes"), filetype="pdf") as doc:
        texto = " ".join(" ".join(p.get_text() for p in doc).split())
    assert "no hay datos comparables del spread Baa que permitan determinar la contribución del crédito" in texto
    assert "contribución del crédito queda indeterminada" in texto                           # nota metodológica
