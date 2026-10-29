"""La sección «Renta Variable y ETFs» del dashboard con datos REALES de la base: que se abra, que cada paso se dibuje,
que las tablas traigan los números reales con sus tooltips y que lo que se muestre sea coherente consigo mismo.

Es una prueba de la pantalla (AppTest sobre app/dashboard.py), complementaria a test_renta_variable.py (el motor) y a
test_catalogo_y_glosario_renta_variable.py (catálogo y explicaciones). Como los datos son reales, las pruebas no fijan
valores de mercado: comprueban relaciones que tienen que cumplirse siempre (SPY contra sí mismo tiene beta 1; el beta es
la correlación por el cociente de volatilidades; la diferencia contra el S&P 500 es una resta de dos columnas mostradas).
"""
import html as html_lib
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pandas as pd
import pytest
from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

import renta_variable_ui as ui

load_dotenv()  # no pisa una DATABASE_URL ya presente en el entorno

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
SECCION = "Renta Variable y ETFs"


def _abrir(paso=None) -> AppTest:
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = SECCION
    if paso:
        at.session_state["rv_paso"] = paso
    at.run(timeout=420)
    assert not at.exception, f"La app lanzó una excepción: {at.exception}"
    return at


def _ir_a(at: AppTest, paso: str) -> AppTest:
    at.session_state["rv_paso"] = paso
    at.run(timeout=420)
    assert not at.exception, f"La app lanzó una excepción en {paso!r}: {at.exception}"
    return at


def _numero(texto: str) -> float:
    """«1,234.56%» → 1234.56 (mismo formato que las tablas de acciones: coma de miles, punto decimal)."""
    limpio = texto.replace("%", "").replace("pp", "").replace("+", "").strip()
    return float(limpio.replace(",", ""))


def _tabla(at: AppTest, columna: str) -> pd.DataFrame:
    for d in at.dataframe:
        if columna in d.value.columns:
            return d.value
    raise AssertionError(f"No hay una tabla con la columna «{columna}».")


def _html(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def _fila_de_etf(html: str, ticker: str) -> str:
    filas = [f for f in html.split("<tr>") if f"glosario-tooltip\">{ticker}<" in f]
    assert len(filas) == 1, f"no encontré la fila de {ticker} en la tabla"
    return filas[0]


def _encabezados(html: str) -> list[str]:
    return [html_lib.unescape(re.sub(r"<[^>]+>", "", h)) for h in re.findall(r"<th[^>]*>(.*?)</th>", html)]


def _celdas(html: str, ticker: str) -> dict[str, str]:
    """Texto de cada celda de la fila de un ETF, por encabezado, de la primera tabla que lo trae."""
    fila = _fila_de_etf(html, ticker)
    valores = [html_lib.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in fila.split("</td>")][:-1]
    # los tooltips meten texto dentro de la primera celda: se toma el ticker, que es lo primero que aparece
    valores[0] = ticker
    tabla = next(t for t in html.split("<table")[1:] if f"glosario-tooltip\">{ticker}<" in t)
    encabezados = _encabezados("<table" + tabla.split("</tr>")[0] + "</tr>")
    assert len(encabezados) == len(valores), (encabezados, valores)
    return dict(zip(encabezados, valores))


# ---------------------------------------------------------------------------
# La pantalla
# ---------------------------------------------------------------------------
def test_la_seccion_esta_en_el_selector_y_se_abre_diciendo_que_los_datos_son_reales():
    at = _abrir()
    assert any("Renta variable" in h.value for h in at.header)
    assert any("son **reales**" in i.value for i in at.info)


def test_cada_paso_se_dibuja_sin_errores():
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)


def test_no_hay_calculadoras_con_valores_inventados():
    """Los únicos controles son de vista (qué graficar, qué período): nada para escribir cifras."""
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)
        assert len(at.number_input) == 0, f"{paso}: hay un campo numérico, o sea una calculadora"
        assert len(at.slider) == 0, f"{paso}: hay un slider, o sea una calculadora"


def test_ningun_texto_de_la_seccion_lleva_signo_de_dolar():
    """Streamlit toma el «$» como inicio de una fórmula matemática y rompe el texto."""
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)
        textos = [m.value for m in at.markdown] + [c.value for c in at.caption] + [i.value for i in at.info]
        for t in textos:
            assert "$" not in re.sub(r"<[^>]*>", "", t), f"{paso}: {t[:80]!r}"


def test_las_tres_tablas_traen_todos_sus_etfs_con_su_tooltip_completo():
    for paso, tickers in ((ui.PASOS[0], ui.MERCADOS_EEUU + ui.SECTORES_EEUU), (ui.PASOS[1], ui.PAISES_Y_REGIONES)):
        html = _html(_abrir(paso))
        for ticker in tickers:
            fila = _fila_de_etf(html, ticker)
            assert ui.ETFS_ACCIONES[ticker]["nombre"] in fila, f"{ticker}: el tooltip no trae el nombre completo"
            for texto in ("Retorno:", "Volatilidad", "Caída máxima", "Beta vs S&amp;P 500", "Correlación", "Contra el S&amp;P 500", "Sharpe"):
                assert texto in fila, f"{ticker}: al tooltip le falta «{texto}»"
            assert "no disponible" not in fila, f"{ticker}: hay un indicador sin datos reales"


def test_las_tablas_caben_en_pantalla_encabezados_cortos_y_sin_columnas_de_mas():
    """Una tabla HTML más ancha que la pantalla esconde sus últimas columnas."""
    for paso in ui.PASOS[:2]:
        for tabla in _html(_abrir(paso)).split("<table")[1:]:
            encabezados = _encabezados("<table" + tabla.split("</tr>")[0] + "</tr>")
            assert encabezados[0] == "ETF" and {"Beta", "Correl.", "Sharpe", "vs S&P (pp)"} <= set(encabezados)
            assert len(encabezados) <= 13, encabezados
            assert max(len(e) for e in encabezados) <= 12, [e for e in encabezados if len(e) > 12]


def test_spy_contra_si_mismo_tiene_beta_1_correlacion_1_y_diferencia_cero():
    c = _celdas(_html(_abrir(ui.PASOS[0])), "SPY")
    assert _numero(c["Beta"]) == pytest.approx(1.0, abs=0.005)
    assert _numero(c["Correl."]) == pytest.approx(1.0, abs=0.005)
    assert _numero(c["vs S&P (pp)"]) == pytest.approx(0.0, abs=0.005)


def test_el_beta_de_cada_etf_es_su_correlacion_por_el_cociente_de_volatilidades():
    """Identidad estadística entre tres columnas independientes de la tabla: beta = correlación × vol(ETF) / vol(SPY).

    Se calcula en dos ventanas ligeramente distintas (retornos de precios o de la serie completa), de ahí la tolerancia."""
    html = _html(_abrir(ui.PASOS[0]))
    vol_spy = _numero(_celdas(html, "SPY")["Vol. %"])
    for ticker in ui.MERCADOS_EEUU + ui.SECTORES_EEUU:
        c = _celdas(html, ticker)
        esperado = _numero(c["Correl."]) * _numero(c["Vol. %"]) / vol_spy
        assert _numero(c["Beta"]) == pytest.approx(esperado, abs=0.05), ticker


def test_la_diferencia_contra_el_sp500_es_el_retorno_del_etf_menos_el_de_spy():
    html = _html(_abrir(ui.PASOS[0]))
    retorno_spy = _numero(_celdas(html, "SPY")["1A %"])
    for ticker in ui.MERCADOS_EEUU + ui.SECTORES_EEUU:
        c = _celdas(html, ticker)
        assert _numero(c["vs S&P (pp)"]) == pytest.approx(_numero(c["1A %"]) - retorno_spy, abs=0.011), ticker


def test_los_numeros_de_las_tablas_estan_dentro_de_su_rango_posible():
    for paso, tickers in ((ui.PASOS[0], ui.MERCADOS_EEUU + ui.SECTORES_EEUU), (ui.PASOS[1], ui.PAISES_Y_REGIONES)):
        html = _html(_abrir(paso))
        for ticker in tickers:
            c = _celdas(html, ticker)
            assert -1 <= _numero(c["Correl."]) <= 1, ticker
            assert _numero(c["Vol. %"]) > 0, ticker
            assert _numero(c["Caída máx. %"]) <= 0, ticker
            assert abs(_numero(c["1D %"])) < 25, ticker  # un ETF no se mueve 25 % en un día


def test_el_paso_de_sectores_nombra_el_mejor_y_el_peor_con_numeros_de_la_tabla():
    at = _abrir(ui.PASOS[0])
    frases = [m.value for m in at.markdown if m.value.startswith("En el último")]
    assert len(frases) == 2
    for frase in frases:
        assert re.search(r"el mejor fue \*\*[A-Z]+\*\* \([+-]\d+\.\d%\) y el peor \*\*[A-Z]+\*\* \([+-]\d+\.\d%\)", frase), frase
    # el mejor y el peor del último año son realmente el máximo y el mínimo de la columna 1A % de los sectores
    html = _html(at)
    retornos = {t: _numero(_celdas(html, t)["1A %"]) for t in ui.SECTORES_EEUU}
    anual = next(f for f in frases if "año" in f)
    assert f"**{max(retornos, key=retornos.get)}**" in anual and f"**{min(retornos, key=retornos.get)}**" in anual


def test_el_paso_de_paises_incluye_a_chile_y_dice_que_los_retornos_estan_en_dolares():
    at = _abrir(ui.PASOS[1])
    html = _html(at)
    assert "Chile (ECH)" in html and "en dólares" in html
    chile = _celdas(html, "ECH")
    assert f"beta {_numero(chile['Beta']):.2f}" in html


def test_el_grafico_de_comparacion_acepta_cambiar_la_seleccion_y_el_periodo():
    at = _abrir(ui.PASOS[0])
    at.multiselect(key="rv_etfs_mercado").set_value(["QQQ", "XLF"]).run()
    assert not at.exception
    at.radio(key="rv_ventana_mercado").set_value("Todo el historial").run()
    assert not at.exception
    at.multiselect(key="rv_etfs_mercado").set_value([]).run()
    assert not at.exception and any("al menos un ETF" in i.value for i in at.info)


def test_el_riesgo_y_la_diversificacion_dibujan_el_grafico_y_dicen_la_pareja_menos_correlacionada():
    at = _abrir(ui.PASOS[2])
    assert len(at.get("plotly_chart")) == 2  # dispersión riesgo-retorno y mapa de correlaciones
    frases = [m.value for m in at.markdown if "la pareja que menos se parece" in m.value]
    assert len(frases) == 1
    asi = re.search(r"es \*\*([A-Z]+)\*\* y \*\*([A-Z]+)\*\*: correlación (-?\d\.\d\d)", frases[0])
    assert asi and -1 <= float(asi.group(3)) <= 1 and asi.group(1) != asi.group(2)


def test_las_correlaciones_se_pueden_cambiar_y_con_menos_de_dos_etfs_avisan():
    at = _abrir(ui.PASOS[2])
    at.multiselect(key="rv_corr_etfs").set_value(["SPY", "TLT"]).run()
    assert not at.exception
    frase = next(m.value for m in at.markdown if "la pareja que menos se parece" in m.value)
    assert "**SPY** y **TLT**" in frase or "**TLT** y **SPY**" in frase
    at.radio(key="rv_ventana_corr").set_value("3 años").run()
    assert not at.exception
    at.multiselect(key="rv_corr_etfs").set_value(["SPY"]).run()
    assert not at.exception and any("al menos dos ETFs" in i.value for i in at.info)


def test_la_replica_del_indice_compara_spy_y_dia_con_sus_indices_reales():
    at = _abrir(ui.PASOS[3])
    t = _tabla(at, "Error de seguimiento").set_index("ETF")
    assert list(t.index) == ["SPY", "DIA"]
    for etf, fila in t.iterrows():
        # un ETF indexado se mueve casi igual que su índice día a día…
        assert float(fila["Correlación diaria"]) > 0.99, etf
        assert _numero(fila["Error de seguimiento"]) < 3, etf
        # …y la diferencia es una resta de dos columnas mostradas
        assert _numero(fila["Diferencia (pp)"]) == pytest.approx(_numero(fila["Retorno ETF"]) - _numero(fila["Retorno índice"]), abs=0.011), etf
        assert re.fullmatch(r"\d{2}-\d{2}-\d{4} a \d{2}-\d{2}-\d{4}", fila["Período"]), fila["Período"]
    assert any("dividendos" in c.value and "precio puro" in c.value for c in at.caption)
    at.radio(key="rv_par_indice").set_value("DIA y Dow Jones").run()
    assert not at.exception


def test_la_pantalla_dice_que_datos_no_tiene_en_vez_de_inventarlos():
    at = _abrir(ui.PASOS[3])
    assert any("valor liquidativo" in i.value and "no** tiene" in i.value for i in at.info)


# ---------------------------------------------------------------------------
# Gráfico de riesgo y retorno: que las etiquetas no se pisen
# ---------------------------------------------------------------------------
def test_dos_puntos_casi_iguales_ponen_su_etiqueta_uno_arriba_y_el_otro_abajo():
    """Caso real: SPY y DIA son casi el mismo punto. Con todas las etiquetas arriba, la de uno quedaba bajo el punto del otro."""
    # los extremos de los ejes se parecen a los del gráfico real (XLE arriba, FXI abajo, EWZ a la derecha): 2 puntos de
    # diferencia entre SPY y DIA son una fracción mínima del eje, como en pantalla
    pos = ui._posiciones_de_etiquetas([
        ("SPY", "g", 12.70, 13.62), ("DIA", "g", 12.57, 11.57), ("EWZ", "g", 34.9, 13.6), ("XLE", "g", 22.2, 61.2), ("FXI", "g", 18.9, -19.1),
    ])
    assert pos["SPY"].startswith("top") and pos["DIA"].startswith("bottom")  # el de arriba rotula hacia arriba, el de abajo hacia abajo


def test_un_punto_en_el_borde_no_pone_su_etiqueta_hacia_afuera_del_grafico():
    puntos = [("A", "g", 0.0, 0.0), ("B", "g", 10.0, 10.0), ("C", "g", 5.0, 5.0)]
    pos = ui._posiciones_de_etiquetas(puntos)
    assert pos["A"] not in ("bottom center", "middle left", "bottom left", "top left", "bottom right")  # esquina inferior izquierda
    assert pos["B"] not in ("top center", "middle right", "top right", "top left", "bottom right")  # esquina superior derecha


def test_cada_punto_recibe_una_posicion_valida_y_los_casos_degenerados_no_rompen():
    puntos = [(f"E{i}", "g", float(i % 7), float(i % 5)) for i in range(40)]
    pos = ui._posiciones_de_etiquetas(puntos)
    assert set(pos) == {p[0] for p in puntos} and set(pos.values()) <= set(ui.DESPLAZAMIENTO_DE_ETIQUETA)
    assert ui._posiciones_de_etiquetas([]) == {}
    assert set(ui._posiciones_de_etiquetas([("A", "g", 1.0, 1.0)]).values()) <= set(ui.DESPLAZAMIENTO_DE_ETIQUETA)
    assert len(ui._posiciones_de_etiquetas([("A", "g", 1.0, 1.0), ("B", "g", 1.0, 1.0)])) == 2  # puntos idénticos


def _nombres_de_series_del_grafico(at, indice: int = 0) -> list[str]:
    import json

    return [serie["name"] for serie in json.loads(at.get("plotly_chart")[indice].proto.spec)["data"]]


def test_el_grafico_de_riesgo_y_retorno_deja_elegir_acciones_bonos_o_las_dos_cosas():
    at = _abrir(ui.PASOS[2])
    assert _nombres_de_series_del_grafico(at) == ["Mercados de EEUU", "Sectores de EEUU", "Países y regiones", "Bonos"]
    at.radio(key="rv_vista_riesgo").set_value("Solo bonos").run()
    assert not at.exception and _nombres_de_series_del_grafico(at) == ["Bonos"]
    at.radio(key="rv_vista_riesgo").set_value("Solo acciones").run()
    assert not at.exception and _nombres_de_series_del_grafico(at) == ["Mercados de EEUU", "Sectores de EEUU", "Países y regiones"]


def test_los_puntos_sin_etiqueta_no_reciben_posicion_pero_siguen_siendo_obstaculos():
    # B está justo encima de A: si B no se rotula, la etiqueta de A tiene que evitarlo (no ir hacia arriba)
    puntos = [("A", "g", 10.0, 10.0), ("B", "g", 10.0, 10.6), ("X", "g", 0.0, 0.0), ("Y", "g", 20.0, 20.0)]
    pos = ui._posiciones_de_etiquetas(puntos, {"A"})
    assert set(pos) == {"A"}
    assert pos["A"] != "top center"
    assert set(ui._posiciones_de_etiquetas(puntos)) == {"A", "B", "X", "Y"}  # sin filtro se rotulan todos


def _modos_de_series_del_grafico(at) -> dict[str, str]:
    import json

    return {s["name"]: s["mode"] for s in json.loads(at.get("plotly_chart")[0].proto.spec)["data"]}


def test_en_la_vista_combinada_los_bonos_van_sin_etiqueta_y_en_solo_bonos_con_ellas():
    at = _abrir(ui.PASOS[2])
    modos = _modos_de_series_del_grafico(at)
    assert modos["Bonos"] == "markers" and modos["Sectores de EEUU"] == "markers+text"
    at.radio(key="rv_vista_riesgo").set_value("Solo bonos").run()
    assert not at.exception and _modos_de_series_del_grafico(at) == {"Bonos": "markers+text"}
    assert any("no llevan etiqueta" in c.value and "Solo bonos" in c.value for c in at.caption)
