"""Pruebas del catálogo de ETFs de bonos, de sus explicaciones (tooltips) y de la tabla con tooltips.

Lo que se protege acá:
- que el catálogo describa EXACTAMENTE los tickers que baja el cron (si alguien agrega un ETF a la
  descarga y no al catálogo, la tabla mostraría una fila sin nombre);
- que cada explicación lleve el número real de su fila y no un ejemplo genérico;
- que la tabla pinte con la misma escala que las de acciones, escape el HTML y apague las filas atrasadas.
"""
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pytest

import estructura_tasas as et
import glosario_renta_fija as g
from catalogo_renta_fija import ETFS_RENTA_FIJA, nombre_de
from constants import TICKERS_RENTA_FIJA
from tabla_tooltips import CMAP_DIVERGENTE, CMAP_SECUENCIAL, color_de_gradiente, tabla_con_tooltips


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
def test_el_catalogo_describe_exactamente_los_tickers_que_baja_el_cron_y_en_el_mismo_orden():
    assert list(ETFS_RENTA_FIJA) == TICKERS_RENTA_FIJA


def test_cada_etf_tiene_nombre_grupo_descripcion_y_un_plazo_de_referencia_que_existe_en_la_curva():
    plazos_de_la_curva = set(et.PLAZOS_ANIOS.values())
    for ticker, d in ETFS_RENTA_FIJA.items():
        assert d["nombre"].strip() and d["grupo"].strip() and d["descripcion"].strip(), ticker
        assert float(d["plazo_referencia"]) in plazos_de_la_curva, f"{ticker}: el plazo {d['plazo_referencia']} no está en la curva"


def test_los_tickers_del_cron_no_estan_repetidos_ni_chocan_con_otros_universos():
    from constants import TICKERS_DOW_JONES, TICKERS_IPSA

    assert len(set(TICKERS_RENTA_FIJA)) == len(TICKERS_RENTA_FIJA)
    assert not set(TICKERS_RENTA_FIJA) & (set(TICKERS_DOW_JONES) | set(TICKERS_IPSA))


def test_el_cron_incluye_los_etfs_de_bonos():
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import actualizar_acciones as aa

    assert set(TICKERS_RENTA_FIJA) <= set(aa.TICKERS_A_DESCARGAR)


def test_el_cron_de_series_incluye_la_curva_chilena_nueva():
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import actualizar_bcch as ab

    nombres = {j["nombre"] for j in ab._construir_jobs()}
    for plazo in ("2 años", "5 años"):
        assert f"Bono BCCh en pesos (BCP) a {plazo} - tasa mercado secundario" in nombres
    for plazo in ("5 años", "30 años"):
        assert f"Bono BCCh en UF (BCU) a {plazo} - tasa mercado secundario" in nombres


def test_nombre_de_nunca_inventa_un_nombre():
    assert nombre_de("TLT") == "iShares 20+ Year Treasury Bond ETF"
    assert nombre_de("XXXX") == "XXXX"


# ---------------------------------------------------------------------------
# Explicaciones: cada una lleva el número real de la fila
# ---------------------------------------------------------------------------
def test_la_explicacion_de_instrumento_trae_nombre_y_descripcion():
    t = g.explicacion_instrumento("HYG")
    assert "iShares iBoxx $ High Yield Corporate Bond ETF" in t and "bajo grado de inversión" in t
    assert g.explicacion_instrumento("ZZZ") == "<b>ZZZ</b>"


def test_la_duracion_medida_dice_el_numero_el_margen_y_el_plazo_de_referencia():
    t = g.explicacion_duracion_medida(6.55, 0.09, 0.95, 7)
    assert "6.5" in t or "6.6" in t
    assert "±0.2" in t  # dos errores estándar
    assert "7 años" in t
    assert "R² = 0.95" in t and "casi todo" in t


def test_el_r2_cambia_la_lectura_segun_su_nivel():
    assert "casi todo" in g.explicacion_duracion_medida(6.0, 0.1, 0.9, 7)
    assert "riesgo de crédito" in g.explicacion_duracion_medida(3.1, 0.25, 0.65, 5) and "poco confiable" not in g.explicacion_duracion_medida(3.1, 0.25, 0.65, 5)
    assert "poco confiable" in g.explicacion_duracion_medida(3.1, 0.25, 0.38, 5)


def test_las_explicaciones_sin_dato_lo_dicen_en_vez_de_inventar():
    for texto in (
        g.explicacion_duracion_medida(None, None, None, None), g.explicacion_volatilidad(None), g.explicacion_caida_maxima(None),
        g.explicacion_beta(None), g.explicacion_sharpe(None, 4.0), g.explicacion_retorno(None, None),
    ):
        assert "no disponible" in texto
        assert not re.search(r"\d\.\d", texto), texto  # ningún número inventado


def test_retorno_volatilidad_caida_beta_y_sharpe_traen_su_numero():
    assert "+1.2%" in g.explicacion_retorno(1.2, -3.4) and "-3.4%" in g.explicacion_retorno(1.2, -3.4)
    assert "9.6%" in g.explicacion_volatilidad(9.58) and "alta" in g.explicacion_volatilidad(9.58)
    assert "baja" in g.explicacion_volatilidad(1.4) and "moderada" in g.explicacion_volatilidad(5.0)
    assert "12.5%" in g.explicacion_caida_maxima(-12.47)
    assert "0.22" in g.explicacion_beta(0.22) and "en parte junto con la bolsa" in g.explicacion_beta(0.22)
    assert "al revés" in g.explicacion_beta(-0.3) and "prácticamente no depende" in g.explicacion_beta(0.0)
    s = g.explicacion_sharpe(-0.4, 3.88)
    assert "-0.40" in s and "3.88%" in s and "mala" in s
    assert "buena" in g.explicacion_sharpe(1.5, 3.88) and "moderada" in g.explicacion_sharpe(0.3, 3.88)


# ---------------------------------------------------------------------------
# Colores
# ---------------------------------------------------------------------------
def _rgb(texto):
    return tuple(int(n) for n in re.findall(r"\d+", texto)[:3])


def test_la_escala_divergente_es_verde_arriba_rojo_abajo_y_neutra_al_medio():
    verde, _ = color_de_gradiente(CMAP_DIVERGENTE, 1.0, -1.0, 1.0)
    rojo, _ = color_de_gradiente(CMAP_DIVERGENTE, -1.0, -1.0, 1.0)
    medio, texto_medio = color_de_gradiente(CMAP_DIVERGENTE, 0.0, -1.0, 1.0)
    assert _rgb(verde) == pytest.approx((12, 163, 12), abs=1)
    assert _rgb(rojo) == pytest.approx((208, 59, 59), abs=1)
    assert _rgb(medio) == pytest.approx((240, 239, 236), abs=1)
    assert texto_medio == "#1a1a1a"  # sobre un fondo casi blanco, texto oscuro


def test_la_escala_secuencial_va_de_casi_blanco_a_azul_y_el_texto_se_adapta():
    claro, texto_claro = color_de_gradiente(CMAP_SECUENCIAL, 0.0, 0.0, 10.0)
    oscuro, texto_oscuro = color_de_gradiente(CMAP_SECUENCIAL, 10.0, 0.0, 10.0)
    assert _rgb(claro) == pytest.approx((252, 252, 251), abs=1) and texto_claro == "#1a1a1a"
    assert _rgb(oscuro) == pytest.approx((42, 120, 214), abs=1) and texto_oscuro == "#f5f5f5"


def test_no_se_pinta_un_valor_vacio_ni_una_escala_sin_rango():
    assert color_de_gradiente(CMAP_SECUENCIAL, np.nan, 0.0, 1.0) is None
    assert color_de_gradiente(CMAP_SECUENCIAL, 1.0, 5.0, 5.0) is None
    # un valor fuera del rango se recorta a los extremos, no rompe
    fuera = color_de_gradiente(CMAP_DIVERGENTE, 5.0, -1.0, 1.0)
    assert _rgb(fuera[0]) == pytest.approx((12, 163, 12), abs=1)


# ---------------------------------------------------------------------------
# Tabla con tooltips
# ---------------------------------------------------------------------------
def _datos():
    return pd.DataFrame(
        {"1D %": [0.5, -0.5, np.nan], "Volatilidad (%)": [2.0, 9.0, 5.0], "Nota": ["a<b", "b", "c"], "_atrasado_bool": [False, False, True]},
        index=["AAA", "BBB", "CCC"],
    )


def _tabla(**cambios):
    args = dict(
        datos=_datos(), columnas_divergentes=["1D %"], columnas_secuenciales=["Volatilidad (%)"],
        formatos={"1D %": "{:+.2f}%", "Volatilidad (%)": "{:.1f}%"},
        construir_tooltip=lambda nombre, fila: f"<b>explica {nombre}</b> vol={fila['Volatilidad (%)']}",
    )
    args.update(cambios)
    return tabla_con_tooltips(**args)


def test_la_tabla_tiene_un_tooltip_por_fila_con_los_datos_de_esa_fila():
    h = _tabla()
    for nombre, vol in (("AAA", 2.0), ("BBB", 9.0), ("CCC", 5.0)):
        assert f"explica {nombre}</b> vol={vol}" in h
    assert h.count('class="glosario-tooltip"') == 3
    assert ".glosario-tooltip" in h and "<style>" in h  # lleva el CSS del tooltip


def test_la_tabla_formatea_muestra_guion_en_los_vacios_y_escapa_el_html():
    h = _tabla()
    assert "+0.50%" in h and "-0.50%" in h and "9.0%" in h
    assert "—" in h  # el 1D de CCC es NaN
    assert "a&lt;b" in h and "a<b" not in h


def test_un_formato_puede_ser_una_funcion_y_una_columna_sin_color_se_muestra_igual():
    h = _tabla(formatos={"1D %": lambda v: f"{v * 100:.0f} bps", "Volatilidad (%)": "{:.1f}%"}, columnas_secuenciales=[])
    assert "50 bps" in h and "-50 bps" in h
    assert "9.0%" in h
    fila_bbb = [f for f in h.split("<tr>") if "BBB" in f][0]
    assert fila_bbb.count("background-color") == 1  # solo la columna divergente, la de volatilidad quedó sin pintar


def test_el_encabezado_incluye_la_primera_columna_y_oculta_la_columna_de_atraso():
    h = _tabla(titulo_primera_columna="ETF")
    assert "<th" in h and ">ETF<" in h and ">Volatilidad (%)<" in h
    assert "_atrasado_bool" not in h


def test_una_fila_atrasada_va_en_gris_y_sin_color_de_fondo():
    h = _tabla()
    fila_ccc = [f for f in h.split("<tr>") if "CCC" in f][0]
    assert "#898781" in fila_ccc and "background-color" not in fila_ccc
    fila_aaa = [f for f in h.split("<tr>") if "AAA" in f][0]
    assert "background-color" in fila_aaa and "#898781" not in fila_aaa


def test_la_escala_divergente_se_comparte_entre_columnas_y_la_secuencial_es_por_columna():
    datos = pd.DataFrame({"x": [1.0, -1.0], "y": [0.1, -0.1]}, index=["A", "B"])
    h = tabla_con_tooltips(datos, ["x", "y"], [], {}, lambda n, f: "")
    colores = re.findall(r"background-color:(rgb\([^)]*\))", h)
    # orden de las celdas: A.x, A.y, B.x, B.y. «y» (0.1) usa la escala de «x» (±1): casi neutro, no verde pleno
    assert _rgb(colores[0]) == pytest.approx((12, 163, 12), abs=1)
    assert _rgb(colores[1])[1] < 245 and _rgb(colores[1])[0] > 150  # 0.1 de 1.0: apenas teñido


def test_el_relleno_horizontal_es_parametrizable_y_por_defecto_es_angosto():
    por_defecto = _tabla()
    assert "padding:6px 7px" in por_defecto and "padding:6px 10px" not in por_defecto
    ancho = _tabla(relleno_horizontal=14)
    assert "padding:6px 14px" in ancho and "padding:6px 7px" not in ancho


def test_sin_columna_de_atraso_ninguna_fila_se_apaga():
    datos = _datos().drop(columns="_atrasado_bool")
    h = _tabla(datos=datos)
    assert "#898781" not in h


def test_la_tabla_no_depende_de_streamlit():
    codigo = open(os.path.join(os.path.dirname(__file__), "..", "tabla_tooltips.py"), encoding="utf-8").read()
    assert "import streamlit" not in codigo
