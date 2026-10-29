"""Pruebas del catálogo de ETFs de acciones y de las explicaciones (tooltips) de «Renta Variable y ETFs».

Lo que se protege acá:
- que el catálogo describa EXACTAMENTE los tickers que baja el cron (si alguien agrega un ETF a la descarga y
  no al catálogo, la tabla mostraría una fila sin nombre), y que las tres tablas lo repartan sin repetir ni olvidar;
- que cada explicación lleve el número real de su fila y no un ejemplo genérico;
- que sin dato la explicación lo diga en vez de inventar un número.
"""
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import glosario_renta_variable as g
from catalogo_etfs_acciones import ETFS_ACCIONES, MERCADOS_EEUU, PAISES_Y_REGIONES, SECTORES_EEUU, nombre_de
from constants import TICKERS_ETFS_ACCIONES, TICKERS_RENTA_FIJA


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
def test_el_catalogo_describe_exactamente_los_tickers_que_baja_el_cron():
    assert set(ETFS_ACCIONES) == set(TICKERS_ETFS_ACCIONES)
    assert len(set(TICKERS_ETFS_ACCIONES)) == len(TICKERS_ETFS_ACCIONES)


def test_las_tres_tablas_reparten_el_catalogo_sin_repetir_ni_olvidar_ninguno():
    todos = MERCADOS_EEUU + SECTORES_EEUU + PAISES_Y_REGIONES
    assert len(todos) == len(set(todos))
    assert set(todos) == set(ETFS_ACCIONES)
    assert len(SECTORES_EEUU) == 11  # los once sectores del S&P 500


def test_cada_etf_tiene_nombre_grupo_y_descripcion():
    for ticker, d in ETFS_ACCIONES.items():
        assert d["nombre"].strip() and d["grupo"].strip() and d["descripcion"].strip(), ticker


def test_los_sectores_se_clasifican_en_los_tres_tipos_de_morningstar():
    tipos = {t: ETFS_ACCIONES[t]["grupo"] for t in SECTORES_EEUU}
    assert set(tipos.values()) == {"Cíclico", "Sensible", "Defensivo"}
    assert {t for t, v in tipos.items() if v == "Defensivo"} == {"XLV", "XLP", "XLU"}
    assert {t for t, v in tipos.items() if v == "Cíclico"} == {"XLY", "XLF", "XLB", "XLRE"}
    assert {t for t, v in tipos.items() if v == "Sensible"} == {"XLK", "XLC", "XLI", "XLE"}


def test_los_paises_se_marcan_como_desarrollado_o_emergente():
    assert {ETFS_ACCIONES[t]["grupo"] for t in PAISES_Y_REGIONES} == {"Desarrollado", "Emergente"}
    assert ETFS_ACCIONES["EWJ"]["grupo"] == "Desarrollado" and ETFS_ACCIONES["ECH"]["grupo"] == "Emergente"


def test_los_etfs_de_acciones_no_chocan_con_los_de_bonos():
    assert not set(TICKERS_ETFS_ACCIONES) & set(TICKERS_RENTA_FIJA)


def test_el_cron_incluye_los_etfs_de_acciones():
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import actualizar_acciones as aa

    assert set(TICKERS_ETFS_ACCIONES) <= set(aa.TICKERS_A_DESCARGAR)
    # y el cron no baja nada dos veces aunque ECH y EEM ya estuvieran en otras listas
    assert len(aa.TICKERS_A_DESCARGAR) == len(set(aa.TICKERS_A_DESCARGAR))


def test_nombre_de_nunca_inventa_un_nombre():
    assert nombre_de("SPY") == "State Street SPDR S&P 500 ETF Trust"
    assert nombre_de("XXXX") == "XXXX"


# ---------------------------------------------------------------------------
# Explicaciones: cada una lleva el número real de la fila
# ---------------------------------------------------------------------------
def test_la_explicacion_de_instrumento_trae_nombre_y_descripcion():
    t = g.explicacion_instrumento("XLU")
    assert "State Street Utilities Select Sector SPDR ETF" in t and "electricidad, agua y gas" in t
    assert g.explicacion_instrumento("ZZZ") == "<b>ZZZ</b>"


def test_las_explicaciones_sin_dato_lo_dicen_en_vez_de_inventar():
    for texto in (
        g.explicacion_volatilidad(None), g.explicacion_caida_maxima(None), g.explicacion_beta(None),
        g.explicacion_correlacion(None), g.explicacion_relativo(None, None), g.explicacion_sharpe(None, 4.0),
        g.explicacion_retorno(None, None),
    ):
        assert "no disponible" in texto
        assert not re.search(r"\d\.\d", texto), texto  # ningún número inventado


def test_retorno_volatilidad_y_caida_traen_su_numero_y_su_nivel():
    r = g.explicacion_retorno(1.2, -3.4)
    assert "+1.2%" in r and "-3.4%" in r and "dividendos" in r
    assert "35.0%" in g.explicacion_volatilidad(35.0) and "alta" in g.explicacion_volatilidad(35.0)
    assert "moderada" in g.explicacion_volatilidad(22.0) and "baja" in g.explicacion_volatilidad(12.0)
    assert "-16.1%" in g.explicacion_caida_maxima(-16.1) and "16.1%" in g.explicacion_caida_maxima(-16.1)


def test_la_lectura_del_beta_cambia_segun_su_nivel_y_siempre_dice_el_numero():
    assert "1.78" in g.explicacion_beta(1.78) and "amplifica" in g.explicacion_beta(1.78)
    assert "se mueve casi igual" in g.explicacion_beta(1.0)
    assert "amortigua" in g.explicacion_beta(0.7)
    assert "casi no depende" in g.explicacion_beta(0.11) and "casi no depende" in g.explicacion_beta(-0.42)
    assert "-0.42" in g.explicacion_beta(-0.42)
    # los límites: 0.9 y 1.1 ya son «casi igual», 0.5 ya amortigua
    assert "se mueve casi igual" in g.explicacion_beta(0.9) and "se mueve casi igual" in g.explicacion_beta(1.1)
    assert "amortigua" in g.explicacion_beta(0.5) and "amplifica" in g.explicacion_beta(1.11)


def test_la_lectura_de_la_correlacion_cambia_segun_su_nivel():
    assert "diversifica poco" in g.explicacion_correlacion(0.92) and "0.92" in g.explicacion_correlacion(0.92)
    assert "misma dirección" in g.explicacion_correlacion(0.6)
    assert "aporta diversificación" in g.explicacion_correlacion(0.3)
    assert "por su cuenta" in g.explicacion_correlacion(0.09) and "por su cuenta" in g.explicacion_correlacion(-0.1)
    assert "al revés" in g.explicacion_correlacion(-0.5)


def test_el_retorno_relativo_dice_mas_o_menos_con_la_cifra_en_puntos():
    mas = g.explicacion_relativo(13.54, 27.2)
    assert "+13.5 pp" in mas and "13.5 puntos porcentuales MÁS" in mas and "+27.2% propio" in mas
    menos = g.explicacion_relativo(-16.65, -3.0)
    assert "-16.6 pp" in menos or "-16.7 pp" in menos
    assert "16.6 puntos porcentuales MENOS" in menos or "16.7 puntos porcentuales MENOS" in menos
    assert "prácticamente lo mismo" in g.explicacion_relativo(0.0, 13.6)
    assert "Es solo un año" in mas  # no vende un año como prueba


def test_sharpe_trae_su_numero_la_tasa_libre_y_la_lectura():
    s = g.explicacion_sharpe(-0.44, 3.88)
    assert "-0.44" in s and "3.88%" in s and "mala" in s
    assert "buena" in g.explicacion_sharpe(1.5, 3.88) and "moderada" in g.explicacion_sharpe(0.3, 3.88)
    assert "3.88" not in g.explicacion_sharpe(0.3, None)  # sin tasa libre no se inventa una


def test_ningun_texto_lleva_signo_de_dolar_que_streamlit_toma_como_formula():
    textos = [
        g.explicacion_instrumento(t) for t in ETFS_ACCIONES
    ] + [
        g.explicacion_retorno(1.0, 2.0), g.explicacion_volatilidad(20.0), g.explicacion_caida_maxima(-10.0),
        g.explicacion_beta(1.2), g.explicacion_correlacion(0.5), g.explicacion_relativo(2.0, 10.0), g.explicacion_sharpe(0.5, 3.0),
    ]
    assert not any("$" in t for t in textos)
