"""I-7b: las tablas con tooltips del dashboard no muestran ceros con signo («+0.00%», «-0.00%») (offline, sintético).

La regla vive en tabla_tooltips (el componente que comparten renta fija, renta variable, commodities y FX) y solo
cambia el TEXTO de una celda cuyo valor, ya formateado con su plantilla, se lee como cero. El valor, el color de la
celda, las demás cifras, los textos sin plantilla y el «—» de los datos faltantes no cambian.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import re
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import commodities_ui as cui  # noqa: E402
import fx_carry_ui as fxui  # noqa: E402
import renta_variable_ui as rvui  # noqa: E402
import tabla_tooltips as tt  # noqa: E402
from _html_table_utils import parsear_tabla_heatmap  # noqa: E402

CERO_CON_SIGNO = re.compile(r"^[+\-]0(\.0+)?\D*$")


# ---------------------------------------------------------------------------
# La regla
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("plantilla,valor,esperado", [
    ("{:+.2f}%", -0.004, "0.00%"), ("{:+.2f}%", 0.004, "0.00%"), ("{:+.2f}%", 0.0, "0.00%"), ("{:+.2f}%", -0.0, "0.00%"),
    ("{:.2f}%", -0.001, "0.00%"), ("{:+.2f}", -0.0049, "0.00"), ("{:.0f}%", -0.4, "0%"), ("{:+.1f} pp", 0.04, "0.0 pp"),
    ("{:+.2f}%", -0.006, "-0.01%"), ("{:+.2f}%", 0.006, "+0.01%"), ("{:+.2f}%", 1.234, "+1.23%"), ("{:.2f}%", -5.28, "-5.28%"),
    ("{:+.0f}%", 0.6, "+1%"), ("{:+,.2f}", -12345.678, "-12,345.68"), ("{:.2f}", 0.0, "0.00"), ("{:+.2f}%", -10.0, "-10.00%"),
])
def test_la_regla_sobre_el_texto_formateado(plantilla, valor, esperado):
    assert tt.sin_signo_en_cero(plantilla.format(valor)) == esperado


@pytest.mark.parametrize("texto", ["—", "n. e.", "Larga", "+0.00e+00", "-0.001", "+10%", "0.00%", "-", "+", ""])
def test_los_demas_textos_no_cambian(texto):
    assert tt.sin_signo_en_cero(texto) == texto


@pytest.mark.parametrize("valor", np.linspace(-0.03, 0.03, 601))
def test_solo_cambia_el_texto_que_se_lee_como_cero(valor):
    original = f"{valor:+.2f}%"
    if float(original[:-1]) == 0:
        assert tt.sin_signo_en_cero(original) == "0.00%"
    else:
        assert tt.sin_signo_en_cero(original) == original


# ---------------------------------------------------------------------------
# El componente: texto sí, color y datos no
# ---------------------------------------------------------------------------
def _tabla_de_prueba():
    datos = pd.DataFrame({
        "Var %": [-0.004, 0.0, 0.006, np.nan], "Nivel %": [-0.001, 2.5, -5.28, 1.0], "Dif (pp)": [0.003, -0.2, 0.0, -0.0],
        "Meses %": [-0.4, 55.0, 0.6, 12.0], "Texto": ["+0.00", "—", "Larga", "x"], "Propio": [-0.001, 1.0, 2.0, 3.0],
    }, index=["A", "B", "C", "D"])
    formatos = {"Var %": "{:+.2f}%", "Nivel %": "{:.2f}%", "Dif (pp)": "{:+.2f}", "Meses %": "{:.0f}%",
                "Propio": lambda v: f"{v:+.2f}*"}
    return datos, formatos


def test_el_componente_quita_el_signo_solo_en_los_ceros_y_respeta_el_resto():
    datos, formatos = _tabla_de_prueba()
    copia = datos.copy()
    tabla = parsear_tabla_heatmap(tt.tabla_con_tooltips(datos, ["Var %", "Dif (pp)"], ["Nivel %"], formatos, lambda n, f: "x", "Fila"))
    assert list(tabla["Var %"]) == ["0.00%", "0.00%", "+0.01%", "—"]
    assert list(tabla["Nivel %"]) == ["0.00%", "2.50%", "-5.28%", "1.00%"]
    assert list(tabla["Dif (pp)"]) == ["0.00", "-0.20", "0.00", "0.00"]
    assert list(tabla["Meses %"]) == ["0%", "55%", "1%", "12%"]
    assert list(tabla["Texto"]) == ["+0.00", "—", "Larga", "x"]            # sin plantilla: intacto
    assert tabla.loc["A", "Propio"] == "-0.00*"                            # función propia: decide su texto
    pd.testing.assert_frame_equal(datos, copia)                             # los datos no se modifican


def test_el_color_de_cada_celda_sigue_saliendo_del_valor():
    datos, formatos = _tabla_de_prueba()
    html_con = tt.tabla_con_tooltips(datos, ["Var %", "Dif (pp)"], ["Nivel %"], formatos, lambda n, f: "x", "Fila")
    html_sin = tt.tabla_con_tooltips(datos, ["Var %", "Dif (pp)"], ["Nivel %"], {}, lambda n, f: "x", "Fila")
    estilos = lambda h: re.findall(r"<td style='([^']*)'", h)  # noqa: E731
    assert estilos(html_con) == estilos(html_sin)


# ---------------------------------------------------------------------------
# Las tablas de las cuatro secciones (constructores reales, datos sintéticos)
# ---------------------------------------------------------------------------
def _resumen(columnas, filas, extra=None):
    datos = {c: [f[i] for f in filas.values()] for i, c in enumerate(columnas)}
    tabla = pd.DataFrame(datos, index=list(filas))
    tabla["_atrasado_bool"] = False
    for c, v in (extra or {}).items():
        tabla[c] = v
    return tabla


def _celdas(html):
    return parsear_tabla_heatmap(html)


def _sin_ceros_con_signo(tabla):
    for columna in tabla.columns:
        for valor in tabla[columna]:
            assert not CERO_CON_SIGNO.match(str(valor)), (columna, valor)


VALORES = [-0.004, 0.003, 0.0, 1.25, -2.5, 0.8, -0.002, 0.5, 0.65, 0.004, -0.001]


def test_tabla_de_renta_variable():
    columnas = [c for c in rvui.COLUMNAS_TABLA if c != "Grupo"]
    filas = {"SPY": VALORES[:len(columnas)], "EEM": [v * 3 for v in VALORES[:len(columnas)]]}
    resumen = _resumen(columnas, filas, {"Grupo": ["EEUU", "Emergentes"]})
    tabla = _celdas(rvui._tabla_de_etfs_html(resumen, 4.0, "Grupo"))
    _sin_ceros_con_signo(tabla)
    assert tabla.loc["SPY", "1D %"] == "0.00%" and tabla.loc["SPY", "YTD %"] == "+1.25%" and tabla.loc["SPY", "1A %"] == "-2.50%"


def test_tabla_de_commodities():
    filas = {"GC=F": VALORES[:len(cui.COLUMNAS_TABLA)], "CL=F": [v * 3 for v in VALORES[:len(cui.COLUMNAS_TABLA)]]}
    tabla = _celdas(cui._tabla_html(_resumen(cui.COLUMNAS_TABLA, filas), 4.0))
    _sin_ceros_con_signo(tabla)
    assert tabla.loc["GC=F", "1D %"] == "0.00%" and tabla.loc["GC=F", "1W %"] == "0.00%" and tabla.loc["CL=F", "1D %"] == "-0.01%"


def test_tabla_de_pares_fx():
    columnas = [c for c in fxui.COLUMNAS_PARES if c != "Grupo"]
    filas = {"USD/CLP": VALORES[:len(columnas)], "EUR/USD": [v * 3 for v in VALORES[:len(columnas)]]}
    resumen = _resumen(columnas, filas, {"Grupo": ["Latam", "Desarrollados"], "ticker": ["CLP=X", "EURUSD=X"]})
    tabla = _celdas(fxui._tabla_de_pares_html(resumen))
    _sin_ceros_con_signo(tabla)
    assert tabla.loc["USD/CLP", "1D %"] == "0.00%" and tabla.loc["EUR/USD", "1D %"] == "-0.01%"


def test_tabla_de_carry_fx():
    codigo = next(iter(fxui.MONEDAS_CARRY))
    fila = [5.0, -0.003, 0.002, -0.004, 0.0, 9.5, -12.0, 0.4]
    resumen = _resumen(fxui.COLUMNAS_CARRY, {codigo: fila}, {"tasa_usd": [4.0]})
    tabla = _celdas(fxui._tabla_de_carry_html(resumen, pd.DataFrame(columns=["nombre", "fecha", "valor"])))
    _sin_ceros_con_signo(tabla)
    assert tabla.loc[codigo, "Difer. (pp)"] == "0.00" and tabla.loc[codigo, "Caída máx. %"] == "-12.00%"


def test_tabla_de_estrategias_fx():
    import fx_carry
    codigo = next(iter(fxui.MONEDAS_CARRY))
    retornos = pd.Series(np.random.default_rng(9).normal(0, 0.004, 300), index=pd.bdate_range("2025-01-06", periods=300))
    base = fx_carry.estadisticas_de_retornos(retornos)          # todos los campos que usa el tooltip, de la función real
    estadisticas = {codigo: {**base, "anualizado": -0.003, "volatilidad": 8.0, "caida_maxima": -0.001, "peor_mes": 0.0,
                             "meses_ganadores": 0.4}}
    tabla = _celdas(fxui._tabla_de_estrategias_html(estadisticas, {codigo: "larga"}))
    _sin_ceros_con_signo(tabla)
    assert list(tabla.loc[codigo]) == ["Larga", "0.00%", "8.00%", "0.00%", "0.00%", "0%"]
