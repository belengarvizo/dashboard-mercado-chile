"""Pruebas del catálogo de divisas y monedas, de las series de tasas del cron y de las explicaciones (tooltips) de «FX y Carry Trade».

Lo que se protege acá:
- que el catálogo describa EXACTAMENTE los pares que baja el cron (si alguien agrega un par a la descarga y no al catálogo, la tabla
  mostraría una fila sin nombre);
- que los nombres de las series de tasas del catálogo sean los que realmente escribe el script de descarga (si no, la pantalla
  buscaría una serie que no existe y diría «sin datos» sin que nadie sepa por qué);
- que cada explicación lleve el número real de su fila y no un ejemplo genérico, y que sin dato lo diga.
"""
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest

import catalogo_fx as c
import glosario_fx as g
from catalogo_instrumentos import TICKERS_YAHOO_FASE_1


# ---------------------------------------------------------------------------
# Catálogo de pares
# ---------------------------------------------------------------------------
def test_el_catalogo_describe_exactamente_los_pares_que_baja_el_cron():
    assert set(c.PARES_FX) == set(TICKERS_YAHOO_FASE_1)
    import actualizar_acciones as aa

    assert set(c.PARES_FX) <= set(aa.TICKERS_A_DESCARGAR)


def test_cada_par_dice_como_se_cotiza_y_que_significa_que_suba_o_baje():
    for ticker, d in c.PARES_FX.items():
        for campo in ("nombre", "grupo", "cotiza", "sube", "baja", "descripcion"):
            assert d[campo].strip(), f"{ticker}: falta «{campo}»"
        assert d["sube"] != d["baja"], ticker


def test_el_texto_de_subida_y_de_bajada_es_coherente_con_el_orden_del_par():
    """En USD/XXX, que suba el par es que el dólar se fortalece; en XXX/USD, que se fortalece la otra moneda."""
    for ticker in ("USDJPY=X", "USDCHF=X", "USDCAD=X", "USDCLP=X", "USDBRL=X", "USDMXN=X"):
        assert "dólar" in c.PARES_FX[ticker]["sube"].lower() and "se fortaleció" in c.PARES_FX[ticker]["sube"], ticker
    for ticker in ("EURUSD=X", "GBPUSD=X", "AUDUSD=X", "NZDUSD=X"):
        assert "frente al dólar" in c.PARES_FX[ticker]["sube"], ticker  # sube = la moneda base se fortalece frente al dólar


def test_la_etiqueta_corta_y_el_nombre_nunca_inventan():
    assert c.etiqueta_corta("USDCLP=X") == "USD/CLP" and c.etiqueta_corta("EURJPY=X") == "EUR/JPY"
    assert c.etiqueta_corta(c.TICKER_DXY) == "DXY"
    assert c.nombre_de("USDCLP=X") == "Dólar / peso chileno (USD/CLP)" and c.nombre_de("XXX") == "XXX"


def test_el_par_de_referencia_es_un_par_de_divisas_y_no_el_indice_dolar():
    assert c.TICKER_REFERENCIA in c.PARES_FX and c.TICKER_REFERENCIA.endswith("=X")
    assert c.TICKER_REFERENCIA != c.TICKER_DXY


# ---------------------------------------------------------------------------
# Monedas con tasa
# ---------------------------------------------------------------------------
def test_cada_moneda_con_tasa_apunta_a_un_par_del_catalogo_con_la_orientacion_correcta():
    for codigo, m in c.MONEDAS_CARRY.items():
        assert m["par"] in c.PARES_FX, codigo
        # un par que empieza con USD cotiza «monedas por 1 dólar» y hay que invertirlo; uno que termina en USD, no
        assert m["base_es_dolar"] == m["par"].startswith("USD"), codigo
        assert codigo in m["par"].replace("=X", ""), codigo
        assert m["con_articulo"].split()[0] in ("el", "la") and m["nombre"].lower() in m["con_articulo"].lower(), codigo


def test_los_nombres_de_las_series_de_tasas_son_los_que_escribe_el_script_de_descarga():
    import actualizar_bcch as ab

    jobs = {j["nombre"]: j for j in ab._construir_jobs()}
    for codigo, m in c.MONEDAS_CARRY.items():
        assert m["serie_tasa"] in jobs, f"{codigo}: el script de descarga no escribe «{m['serie_tasa']}»"
        assert jobs[m["serie_tasa"]]["frecuencia"] == m["frecuencia"], f"{codigo}: la frecuencia declarada no coincide con la del script"
    assert c.NOMBRE_TASA_EEUU == ab.NOMBRE_TPM_EEUU
    assert c.NOMBRE_TASA_CHILE in jobs and c.NOMBRE_TIPO_DE_CAMBIO_OBSERVADO in jobs and c.NOMBRE_COBRE in jobs


def test_el_cron_descarga_las_cinco_series_de_tasas_de_otros_paises_sin_repetir_codigos():
    import actualizar_bcch as ab

    jobs = ab._construir_jobs()
    codigos = [j["codigo"] for j in jobs]
    assert len(codigos) == len(set(codigos))
    for fred_id, info in ab.SERIES_TASAS_PAISES_FRED.items():
        j = next(x for x in jobs if x["codigo"] == f"FRED.{fred_id}")
        assert j["kind"] == "fred" and j["ident"] == fred_id and j["nombre"] == info["nombre"]
    assert len(ab.SERIES_TASAS_PAISES_FRED) == 5
    # las tasas del catálogo que no son de Chile ni de EEUU son exactamente estas cinco
    del_catalogo = {m["serie_tasa"] for k, m in c.MONEDAS_CARRY.items() if k != "CLP"}
    assert del_catalogo == {info["nombre"] for info in ab.SERIES_TASAS_PAISES_FRED.values()}


def test_las_monedas_sin_tasa_estan_en_la_tabla_de_divisas_pero_no_en_el_carry():
    assert not set(c.MONEDAS_SIN_TASA) & set(c.MONEDAS_CARRY)
    for codigo in c.MONEDAS_SIN_TASA:
        assert any(codigo in ticker for ticker in c.PARES_FX), f"{codigo} no tiene par en el catálogo"


# ---------------------------------------------------------------------------
# Explicaciones: cada una lleva el número real de la fila
# ---------------------------------------------------------------------------
def test_la_explicacion_del_par_trae_nombre_descripcion_y_como_se_cotiza():
    t = g.explicacion_par("USDCLP=X")
    assert "Dólar / peso chileno (USD/CLP)" in t and "cobre" in t and "pesos chilenos por 1 dólar" in t
    assert g.explicacion_par("ZZZ") == "<b>ZZZ</b>"


def test_el_movimiento_dice_hacia_donde_fue_el_par_con_las_palabras_del_catalogo_y_aclara_que_el_color_no_es_bueno_ni_malo():
    sube = g.explicacion_movimiento("USDCLP=X", 1.8, 8.8)
    assert "+1.8%" in sube and "+8.8%" in sube and c.PARES_FX["USDCLP=X"]["sube"] in sube and "no si fue bueno o malo" in sube
    baja = g.explicacion_movimiento("USDCLP=X", -2.5, 1.0)
    assert "-2.5%" in baja and c.PARES_FX["USDCLP=X"]["baja"] in baja
    quieto = g.explicacion_movimiento("USDCLP=X", 0.01, 1.0)
    assert "prácticamente no se movió" in quieto
    assert "no disponible" in g.explicacion_movimiento("USDCLP=X", None, None)


def test_volatilidad_y_rango_traen_su_numero_y_su_nivel():
    assert "12.5%" in g.explicacion_volatilidad(12.5) and "alta" in g.explicacion_volatilidad(12.5)
    assert "moderada" in g.explicacion_volatilidad(8.0) and "baja" in g.explicacion_volatilidad(4.0)
    assert "16.7%" in g.explicacion_rango(16.7)


def test_la_correlacion_con_la_referencia_se_lee_con_el_signo_del_par_y_el_indice_dolar_no_se_calcula():
    alto = g.explicacion_correlacion_referencia(0.62, "USD/BRL", "USD/CLP")
    assert "0.62" in alto and "tiende a subir cuando USD/CLP sube" in alto
    negativo = g.explicacion_correlacion_referencia(-0.62, "EUR/USD", "USD/CLP")
    assert "-0.62" in negativo and "tiende a bajar cuando USD/CLP sube" in negativo and "Ojo con el signo" in negativo
    assert "por su cuenta" in g.explicacion_correlacion_referencia(0.1, "USD/CAD", "USD/CLP")
    assert "por su cuenta" in g.explicacion_correlacion_referencia(-0.34, "EUR/USD", "USD/CLP")  # bajo el umbral de ±0.5
    assert "contra sí mismo" in g.explicacion_correlacion_referencia(1.0, "USD/CLP", "USD/CLP")
    dxy = g.explicacion_correlacion_referencia(None, "DXY", "USD/CLP", sin_convencion_comun=True)
    assert "No se calcula" in dxy and "convención de fecha" in dxy and not re.search(r"\d\.\d", dxy)
    assert "no disponible" in g.explicacion_correlacion_referencia(None, "USD/CAD", "USD/CLP")


def test_la_moneda_dice_que_tasa_usa_su_valor_y_la_fecha_del_dato():
    t = g.explicacion_moneda("BRL", 13.94, "01-09-2026")
    assert "Real (BRL)" in t and "13.94%" in t and "01-09-2026" in t and "interbancaria de corto plazo de Brasil" in t
    assert "No hay una tasa vigente" in g.explicacion_moneda("BRL", None, None)


def test_el_diferencial_positivo_dice_cuanto_se_gana_y_el_negativo_dice_que_el_carry_va_al_reves():
    pos = g.explicacion_diferencial("el real", 13.94, 3.88, 10.06)
    assert "+10.06 puntos" in pos and "13.94%" in pos and "3.88%" in pos and "gana 10.06 puntos" in pos
    neg = g.explicacion_diferencial("el yen", 1.04, 3.88, -2.84)
    assert "-2.84 puntos" in neg and "pierde 2.84 puntos" in neg and "al revés" in neg and "se financia en el yen" in neg
    assert "no disponible" in g.explicacion_diferencial("el yen", None, 3.88, None)


def test_el_spot_el_carry_y_el_total_se_explican_segun_quien_pesa_mas():
    mismo = g.explicacion_spot_y_total("el euro", 3.0, 1.0, 4.0)
    assert "+4.0%" in mismo and "+3.0%" in mismo and "+1.0%" in mismo and "mismo sentido" in mismo
    gana_cambio = g.explicacion_spot_y_total("el real", -9.5, 8.1, -1.4)
    assert "decidió el resultado" in gana_cambio
    gana_carry = g.explicacion_spot_y_total("el real", -2.0, 8.1, 6.1)
    assert "el carry pesó más" in gana_carry
    assert "no disponible" in g.explicacion_spot_y_total("el real", None, None, None)


def test_el_riesgo_del_carry_trae_la_volatilidad_la_caida_y_la_lectura_del_carry_sobre_riesgo():
    t = g.explicacion_riesgo_carry(14.2, -7.7, 0.71)
    assert "14.2%" in t and "7.7%" in t and "0.71" in t and "razonablemente" in t
    assert "poco por el riesgo" in g.explicacion_riesgo_carry(10.0, -5.0, 0.1)
    assert "Carry sobre riesgo" not in g.explicacion_riesgo_carry(10.0, -5.0, None)
    assert "no disponible" in g.explicacion_riesgo_carry(None, None, None)


def test_la_explicacion_de_la_estrategia_dice_el_lado_de_hoy_y_los_numeros_del_periodo():
    import pandas as pd

    e = {"dias": 1250, "anualizado": 9.7, "volatilidad": 9.9, "caida_maxima": -14.5, "peor_mes": -9.8,
         "fecha_peor_mes": pd.Timestamp("2024-08-06"), "meses_ganadores": 65.0}
    larga = g.explicacion_estrategia("el yen", "larga", e)
    assert "larga" in larga and "+9.7%" in larga and "9.9%" in larga
    assert "14.5%" in larga and "-9.8%" in larga
    assert "06-08-2024" in larga and "65%" in larga and "1250 ruedas" in larga
    assert "corta" in g.explicacion_estrategia("el yen", "corta", e)
    cartera = g.explicacion_estrategia("la cartera de monedas", None, e)
    assert "Hoy la estrategia" not in cartera
    assert "No hay datos suficientes" in g.explicacion_estrategia("el yen", "larga", None)


def test_ningun_texto_lleva_signo_de_dolar_que_streamlit_toma_como_formula():
    import pandas as pd

    e = {"dias": 100, "anualizado": 1.0, "volatilidad": 2.0, "caida_maxima": -3.0, "peor_mes": -1.0,
         "fecha_peor_mes": pd.Timestamp("2024-01-05"), "meses_ganadores": 50.0}
    textos = [g.explicacion_par(t) for t in c.PARES_FX] + [
        g.explicacion_movimiento("USDCLP=X", 1.0, 2.0), g.explicacion_volatilidad(9.0), g.explicacion_rango(10.0),
        g.explicacion_correlacion_referencia(0.4, "USD/BRL", "USD/CLP"), g.explicacion_moneda("EUR", 2.5, "29-10-2026"),
        g.explicacion_diferencial("el euro", 2.5, 3.88, -1.38), g.explicacion_spot_y_total("el euro", 1.0, 2.0, 3.0),
        g.explicacion_riesgo_carry(5.0, -3.0, 0.4), g.explicacion_estrategia("el euro", "larga", e),
    ]
    assert not any("$" in t for t in textos)
