"""F2: panoramas de FRI con los datos y motores existentes (offline, datos de PRUEBA construidos aquí).

QUÉ SE PRUEBA
    - Cada cifra de las tarjetas es la de market_data.calcular_cambio_reciente (la misma del Resumen), con su fecha real y
      su fuente; el 1A de las tablas es renta_fija.retorno_ultimo_anio; la curva es renta_fija.curva_en_fecha.
    - Sin datos, todo dice «No disponible»: ninguna cifra de relleno.
    - El IPSA nunca se reemplaza por ECH, aunque ECH tenga precios.
    - El código de los panoramas no trae datos propios (ni generadores aleatorios ni cargas directas de la base).
Los datos de este archivo son de prueba y viven solo aquí.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import re
import sys

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(RAIZ)

import fri.panoramas as p  # noqa: E402
import renta_fija as rf  # noqa: E402
import renta_fija_ui as rfui  # noqa: E402
from formato_numerico import cifra  # noqa: E402
from market_data import calcular_cambio_reciente  # noqa: E402

FIN = pd.Timestamp("2026-11-24")
DIAS = pd.bdate_range(end=FIN, periods=400)
MESES = pd.date_range(end=FIN, periods=24, freq="MS")


def _macro(sin=()):
    rng = np.random.default_rng(3)
    series = {
        p.NOMBRE_IMACEC: (MESES, 2 + rng.normal(0, .5, len(MESES))), p.NOMBRE_IPC: (MESES, 4 + rng.normal(0, .2, len(MESES))),
        p.NOMBRE_DESEMPLEO: (MESES, 8.5 + rng.normal(0, .1, len(MESES))), p.NOMBRE_TASA_CHILE: (DIAS, np.r_[np.full(300, 5.0), np.full(100, 4.75)]),
        p.NOMBRE_TIPO_DE_CAMBIO_OBSERVADO: (DIAS, 940 + rng.normal(0, 5, len(DIAS)).cumsum()),
        p.NOMBRE_COBRE: (DIAS, 4.3 + rng.normal(0, .02, len(DIAS)).cumsum()),
        p.NOMBRE_TASA_EEUU: (DIAS, np.r_[np.full(350, 4.33), np.full(50, 3.88)]),
        p.NOMBRE_TREASURY_10: (DIAS[:-1], 4.1 + rng.normal(0, .02, len(DIAS) - 1).cumsum()),
    }
    for plazo, nombre in rfui.CURVA_CHILE["BCP (pesos)"].items():
        series[nombre] = (DIAS, 4 + plazo * .1 + rng.normal(0, .01, len(DIAS)).cumsum())
    filas = [{"nombre": n, "fecha": f.date(), "valor": float(v)} for n, (fs, vs) in series.items() if n not in sin for f, v in zip(fs, vs)]
    return pd.DataFrame(filas, columns=["nombre", "fecha", "valor"])


def _precios(con_ech=True):
    rng = np.random.default_rng(4)
    tickers = list(p.tickers_necesarios("mercados")) + [p.TICKER_DXY] + (["ECH"] if con_ech else [])
    filas = [{"ticker": t, "fecha": f.date(), "precio_cierre": float(v), "volumen": 1000}
             for t in tickers for f, v in zip(DIAS, 100 * np.exp(rng.normal(0, .01, len(DIAS)).cumsum()))]
    return pd.DataFrame(filas)


def _app(cual, macro, precios):
    import fri.panoramas as p
    {"macro": p.panorama_macro, "mercados": p.panorama_mercados}[cual](macro, precios)


def _correr(cual, macro, precios) -> str:
    at = AppTest.from_function(_app, args=(cual, macro, precios), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return " ".join(m.value for m in at.markdown)


# ---------------------------------------------------------------------------
# Correspondencia con los motores existentes
# ---------------------------------------------------------------------------
def test_las_tarjetas_macro_son_las_cifras_del_resumen_con_su_fecha_y_fuente():
    macro = _macro()
    html = _correr("macro", macro, _precios())
    for nombre, decimales, fuente in ((p.NOMBRE_TIPO_DE_CAMBIO_OBSERVADO, 2, "BCCh"), (p.NOMBRE_COBRE, 2, "BCCh"),
                                      (p.NOMBRE_TASA_CHILE, 2, "BCCh"), (p.NOMBRE_TREASURY_10, 2, "FRED (H.15)"),
                                      (p.NOMBRE_IPC, 2, "INE/BCCh")):
        valor, cambio_pct, fecha, cambio_abs = calcular_cambio_reciente(p.serie_macro(macro, nombre))
        assert cifra(valor, decimales) in html, nombre
        assert f"{fuente} · " in html
    tpm = calcular_cambio_reciente(p.serie_macro(macro, p.NOMBRE_TASA_CHILE))
    assert f"{cifra(tpm[3] * 100, 0, True)} pb" in html                # cambio de la TPM en puntos base
    treasury = p.serie_macro(macro, p.NOMBRE_TREASURY_10)
    assert f"FRED (H.15) · {treasury.index[-1].strftime('%d-%m-%Y')}" in html   # fecha real de esa serie, no la de hoy
    assert "Actividad económica de China" in html and "Sin fuente verificada" in html


def test_las_tablas_de_mercados_usan_retorno_ultimo_anio_y_la_curva_de_renta_fija():
    macro, precios = _macro(), _precios()
    html = _correr("mercados", macro, precios)
    spx = p.serie_precio(precios, p.TICKER_SP500)
    assert f"{cifra(rf.retorno_ultimo_anio(spx), 1, True)} %" in html
    assert cifra(calcular_cambio_reciente(spx)[0], 2) in html
    f1, c1, _f0, _c0 = p._curva_bcp(macro)
    pivote = pd.concat({pl: p.serie_macro(macro, n) for pl, n in rfui.CURVA_CHILE["BCP (pesos)"].items()}, axis=1)
    esperada = rf.curva_en_fecha(pivote, pivote.index.max())
    assert f1 == esperada[0] and c1.equals(esperada[1])


# ---------------------------------------------------------------------------
# IPSA y datos faltantes
# ---------------------------------------------------------------------------
def test_el_ipsa_no_se_reemplaza_por_ech():
    html = _correr("mercados", _macro(), _precios(con_ech=True))
    assert "IPSA (Chile)" in html and "No disponible" in html and "ECH (un ETF en dólares) no se presenta como IPSA" in html
    assert "volumen tampoco se inventa" in html


@pytest.mark.parametrize("cual", ["macro", "mercados"])
def test_sin_datos_todo_dice_no_disponible_y_no_hay_cifras(cual):
    vacio_macro = pd.DataFrame(columns=["nombre", "fecha", "valor"])
    vacio_precios = pd.DataFrame(columns=["ticker", "fecha", "precio_cierre", "volumen"])
    html = _correr(cual, vacio_macro, vacio_precios)
    assert "No disponible" in html
    valores = re.findall(r'<div class="valor"[^>]*>([^<]*)<', html)
    assert valores and all(v == "No disponible" for v in valores), valores


def test_una_serie_faltante_solo_afecta_a_su_tarjeta():
    html = _correr("macro", _macro(sin=(p.NOMBRE_COBRE,)), _precios())
    valores = re.findall(r'<div class="nombre">([^<]*)</div><div class="valor"[^>]*>([^<]*)<', html)
    estado = dict(valores)
    assert estado["Precio del cobre"] == "No disponible"
    assert estado["TPM Chile"] != "No disponible" and estado["USD/CLP"] != "No disponible"


def test_el_codigo_de_los_panoramas_no_trae_datos_propios():
    texto = open(os.path.join(RAIZ, "fri", "panoramas.py"), encoding="utf-8").read()
    for prohibido in ("random", "datos_sinteticos", "read_sql", "get_engine", "create_engine", "ECH\""):
        assert prohibido not in texto, prohibido


# ---------------------------------------------------------------------------
# Cierre de F2: fechas de las comparaciones
# ---------------------------------------------------------------------------
def test_la_variacion_se_rotula_con_la_fecha_del_dato_anterior_no_como_un_dia():
    fechas = pd.DatetimeIndex(["2026-11-10", "2026-11-11", "2026-11-20"])           # hueco de 9 días antes del último
    html = p.tarjeta("Prueba", pd.Series([1.0, 2.0, 3.0], index=fechas), "Fuente")
    assert "vs. 11-11-2026" in html and "1 día" not in html and "dato anterior" not in html
    mensual = p.tarjeta("IPC", pd.Series([3.0, 3.2], index=pd.DatetimeIndex(["2026-09-01", "2026-10-01"])), "INE", mensual=True)
    assert "vs. sep 2026" in mensual and "Fuente" not in mensual


def test_las_curvas_comparadas_usan_fechas_completas_efectivas():
    macro = _macro()
    dos_anios = rfui.CURVA_CHILE["BCP (pesos)"][2]
    ultima = macro[macro["nombre"] == dos_anios]["fecha"].max()
    macro = macro[~((macro["nombre"] == dos_anios) & (macro["fecha"] == ultima))]   # el plazo de 2 años no tiene el último día
    f1, c1, f0, c0 = p._curva_bcp(macro)
    assert f1 < pd.Timestamp(ultima) and c1.notna().all()                           # la curva actual es la última COMPLETA
    assert f0 <= p.objetivo_mes_anterior(f1) and c0.notna().all()                   # la de comparación: completa, en o antes de un mes atrás
    html = _correr("mercados", macro, _precios())
    assert f"la actual es del {f1.strftime('%d-%m-%Y')}" in html
    assert f"en o antes del {p.objetivo_mes_anterior(f1).strftime('%d-%m-%Y')} (un mes antes): {f0.strftime('%d-%m-%Y')}" in html
