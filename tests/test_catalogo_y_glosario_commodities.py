"""Pruebas del catálogo de commodities y de las explicaciones (tooltips) de «Commodities».

Lo que se protege acá:
- que el catálogo describa EXACTAMENTE los tickers que baja el cron (CL=F vía TICKER_PETROLEO_WTI, los otros 8 vía
  TICKERS_COMMODITIES): si alguien agrega un futuro a la descarga y no al catálogo, la tabla mostraría una fila
  sin nombre, y si lo saca del catálogo sin sacarlo de la descarga quedaría un ticker fantasma;
- que cada grupo (Energía, Metales, Agrícolas) reparta el catálogo sin repetir ni olvidar ninguno;
- que cada explicación lleve el número real de su fila y no un ejemplo genérico, y que sin dato lo diga.
"""
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import glosario_commodities as g
from catalogo_commodities import COMMODITIES, GRUPOS_EN_ORDEN, nombre_de, tickers_del_grupo


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
def test_el_catalogo_describe_exactamente_los_tickers_que_baja_el_cron():
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import actualizar_acciones as aa
    from constants import TICKER_PETROLEO_WTI, TICKERS_COMMODITIES

    esperados = set(TICKERS_COMMODITIES) | {TICKER_PETROLEO_WTI}
    assert set(COMMODITIES) == esperados
    assert len(set(TICKERS_COMMODITIES)) == len(TICKERS_COMMODITIES)
    assert esperados <= set(aa.TICKERS_A_DESCARGAR)


def test_los_grupos_reparten_el_catalogo_sin_repetir_ni_olvidar_ninguno():
    todos = [t for g in GRUPOS_EN_ORDEN for t in tickers_del_grupo(g)]
    assert len(todos) == len(set(todos))
    assert set(todos) == set(COMMODITIES)
    assert set(GRUPOS_EN_ORDEN) == {"Energía", "Metales", "Agrícolas"}


def test_cada_commodity_tiene_nombre_grupo_unidad_y_descripcion():
    for ticker, d in COMMODITIES.items():
        for campo in ("nombre", "grupo", "unidad", "descripcion"):
            assert d[campo].strip(), f"{ticker}: falta «{campo}»"
        assert d["grupo"] in GRUPOS_EN_ORDEN, ticker


def test_el_cobre_esta_en_la_misma_unidad_que_el_precio_del_banco_central():
    """La comparación del paso 2 solo tiene sentido si las dos fuentes están en USD/lb, sin conversión de por medio."""
    assert COMMODITIES["HG=F"]["unidad"] == "USD por libra"


def test_tickers_del_grupo_de_un_grupo_sin_commodities_es_una_lista_vacia():
    assert tickers_del_grupo("Inexistente") == []


def test_nombre_de_nunca_inventa_un_nombre():
    assert nombre_de("GC=F") == "Oro" and nombre_de("XXXX") == "XXXX"


# ---------------------------------------------------------------------------
# Explicaciones: cada una lleva el número real de la fila
# ---------------------------------------------------------------------------
def test_la_explicacion_de_instrumento_trae_nombre_descripcion_y_unidad():
    t = g.explicacion_instrumento("HG=F")
    assert "Cobre" in t and "economía chilena" in t and "USD por libra" in t
    assert g.explicacion_instrumento("ZZZ") == "<b>ZZZ</b>"


def test_las_explicaciones_sin_dato_lo_dicen_en_vez_de_inventar():
    for texto in (
        g.explicacion_volatilidad(None), g.explicacion_caida_maxima(None), g.explicacion_beta(None),
        g.explicacion_correlacion(None), g.explicacion_sharpe(None, 4.0), g.explicacion_retorno(None, None),
    ):
        assert "no disponible" in texto
        assert not re.search(r"\d\.\d", texto), texto  # ningún número inventado


def test_el_retorno_aclara_que_un_futuro_no_tiene_dividendos():
    t = g.explicacion_retorno(2.5, -10.0)
    assert "+2.5%" in t and "-10.0%" in t
    assert "no hay dividendos" in t.lower()


def test_volatilidad_y_caida_traen_su_numero_y_su_nivel():
    assert "40.0%" in g.explicacion_volatilidad(40.0) and "alta" in g.explicacion_volatilidad(40.0)
    assert "moderada" in g.explicacion_volatilidad(25.0) and "baja" in g.explicacion_volatilidad(10.0)
    assert "-18.3%" in g.explicacion_caida_maxima(-18.3) and "18.3%" in g.explicacion_caida_maxima(-18.3)


def test_la_lectura_del_beta_cambia_segun_su_nivel():
    assert "0.69" in g.explicacion_beta(0.69) and "junto con la bolsa" in g.explicacion_beta(0.69)
    assert "casi no depende" in g.explicacion_beta(0.0)
    assert "al revés de la bolsa" in g.explicacion_beta(-0.48)


def test_la_correlacion_cambia_de_lectura_segun_su_nivel():
    assert "misma dirección" in g.explicacion_correlacion(0.6)
    assert "aporta diversificación" in g.explicacion_correlacion(0.3)
    assert "por su cuenta" in g.explicacion_correlacion(0.0)
    assert "al revés" in g.explicacion_correlacion(-0.5)


def test_sharpe_trae_su_numero_la_tasa_libre_y_la_lectura():
    s = g.explicacion_sharpe(1.19, 3.88)
    assert "1.19" in s and "3.88%" in s and "buena" in s
    assert "moderada" in g.explicacion_sharpe(0.3, 3.88) and "mala" in g.explicacion_sharpe(-0.2, 3.88)
    assert "3.88" not in g.explicacion_sharpe(0.3, None)


def test_ningun_texto_lleva_signo_de_dolar_que_streamlit_toma_como_formula():
    textos = [g.explicacion_instrumento(t) for t in COMMODITIES] + [
        g.explicacion_retorno(1.0, 2.0), g.explicacion_volatilidad(20.0), g.explicacion_caida_maxima(-10.0),
        g.explicacion_beta(0.5), g.explicacion_correlacion(0.3), g.explicacion_sharpe(0.5, 3.0),
    ]
    assert not any("$" in t for t in textos)
