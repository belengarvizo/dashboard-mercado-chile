"""La sección «Commodities» del dashboard con datos REALES de la base: que se abra, que cada paso se dibuje, que la
tabla traiga los números reales con sus tooltips y que la comparación cobre BCCh-COMEX sea coherente consigo misma.

Es una prueba de la pantalla (AppTest sobre app/dashboard.py), complementaria a test_catalogo_y_glosario_commodities.py
(catálogo y explicaciones). Como los datos son reales, las pruebas no fijan valores de mercado: comprueban relaciones
que tienen que cumplirse siempre (la diferencia mostrada es exactamente comex/bcch - 1, el aviso del arancel de 2025
solo aparece cuando el máximo del período realmente cae en esa fecha).
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

import commodities_ui as ui

load_dotenv()

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
SECCION = "Commodities"


def _abrir(paso=None) -> AppTest:
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = SECCION
    if paso:
        at.session_state["cm_paso"] = paso
    at.run(timeout=420)
    assert not at.exception, f"La app lanzó una excepción: {at.exception}"
    return at


def _ir_a(at: AppTest, paso: str) -> AppTest:
    at.session_state["cm_paso"] = paso
    at.run(timeout=420)
    assert not at.exception, f"La app lanzó una excepción en {paso!r}: {at.exception}"
    return at


def _numero(texto: str) -> float:
    limpio = texto.replace("%", "").replace("+", "").strip()
    return float(limpio.replace(",", ""))


def _html(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def _fila(html: str, ticker: str) -> str:
    filas = [f for f in html.split("<tr>") if f"glosario-tooltip\">{ticker}<" in f]
    assert len(filas) == 1, f"no encontré la fila de {ticker} en la tabla"
    return filas[0]


def _encabezados(html: str) -> list[str]:
    return [html_lib.unescape(re.sub(r"<[^>]+>", "", h)) for h in re.findall(r"<th[^>]*>(.*?)</th>", html)]


def _celdas(html: str, ticker: str) -> dict[str, str]:
    fila = _fila(html, ticker)
    valores = [html_lib.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in fila.split("</td>")][:-1]
    valores[0] = ticker
    tabla = next(t for t in html.split("<table")[1:] if f"glosario-tooltip\">{ticker}<" in t)
    encabezados = _encabezados("<table" + tabla.split("</tr>")[0] + "</tr>")
    assert len(encabezados) == len(valores), (encabezados, valores)
    return dict(zip(encabezados, valores))


def _metrica(at: AppTest, etiqueta: str):
    for m in at.metric:
        if m.label == etiqueta:
            return m
    raise AssertionError(f"No hay una métrica «{etiqueta}». Hay: {[m.label for m in at.metric]}")


# ---------------------------------------------------------------------------
# La pantalla
# ---------------------------------------------------------------------------
def test_la_seccion_esta_en_el_selector_y_dice_que_los_datos_son_reales():
    at = _abrir()
    assert any("Commodities" in h.value for h in at.header)
    assert any("son **reales**" in i.value for i in at.info)


def test_cada_paso_se_dibuja_sin_errores():
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)


def test_no_hay_calculadoras_con_valores_inventados():
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)
        assert len(at.number_input) == 0, f"{paso}: hay un campo numérico, o sea una calculadora"
        assert len(at.slider) == 0, f"{paso}: hay un slider, o sea una calculadora"


def test_ningun_texto_de_la_seccion_lleva_signo_de_dolar():
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)
        textos = [m.value for m in at.markdown] + [c.value for c in at.caption] + [i.value for i in at.info]
        for t in textos:
            assert "$" not in re.sub(r"<[^>]*>", "", t), f"{paso}: {t[:80]!r}"


# ---------------------------------------------------------------------------
# Paso 1: el mercado
# ---------------------------------------------------------------------------
def test_los_tres_grupos_traen_todos_sus_commodities_con_su_tooltip_completo():
    from catalogo_commodities import GRUPOS_EN_ORDEN, tickers_del_grupo

    html = _html(_abrir(ui.PASOS[0]))
    for grupo in GRUPOS_EN_ORDEN:
        for ticker in tickers_del_grupo(grupo):
            fila = _fila(html, ticker)
            assert ui.COMMODITIES[ticker]["nombre"] in fila, f"{ticker}: el tooltip no trae el nombre completo"
            for texto in ("Retorno:", "Volatilidad", "Caída máxima", "Beta vs S&amp;P 500", "Correlación con el S&amp;P 500", "Sharpe"):
                assert texto in fila, f"{ticker}: al tooltip le falta «{texto}»"
            assert "no disponible" not in fila, f"{ticker}: hay un indicador sin datos reales"


def test_las_tablas_caben_en_pantalla_con_encabezados_cortos():
    for tabla in _html(_abrir(ui.PASOS[0])).split("<table")[1:]:
        encabezados = _encabezados("<table" + tabla.split("</tr>")[0] + "</tr>")
        assert encabezados[0] == "Ticker" and {"Beta", "Correl.", "Sharpe"} <= set(encabezados)
        assert len(encabezados) <= 11, encabezados
        assert max(len(e) for e in encabezados) <= 12, [e for e in encabezados if len(e) > 12]


def test_los_numeros_de_la_tabla_estan_dentro_de_su_rango_posible():
    html = _html(_abrir(ui.PASOS[0]))
    for ticker in ui.COMMODITIES:
        c = _celdas(html, ticker)
        assert _numero(c["Vol. %"]) > 0, ticker
        assert _numero(c["Caída máx. %"]) <= 0, ticker
        assert abs(_numero(c["1D %"])) < 25, ticker  # un commodity no se mueve 25 % en un día


def test_el_grafico_de_comparacion_acepta_cambiar_la_seleccion_y_el_periodo():
    at = _abrir(ui.PASOS[0])
    at.multiselect(key="cm_commodities_grafico").set_value(["ZC=F", "KC=F"]).run()
    assert not at.exception
    at.radio(key="cm_ventana_grafico").set_value("Todo el historial").run()
    assert not at.exception
    at.multiselect(key="cm_commodities_grafico").set_value([]).run()
    assert not at.exception and any("al menos un commodity" in i.value for i in at.info)


# ---------------------------------------------------------------------------
# Paso 2: Chile y el cobre
# ---------------------------------------------------------------------------
def test_chile_muestra_las_dos_fuentes_del_cobre_y_su_diferencia_real():
    at = _abrir(ui.PASOS[1])
    bcch = _numero(_metrica(at, "Cobre, Banco Central de Chile").value.replace(" USD/lb", ""))
    comex = _numero(_metrica(at, "Cobre, futuro COMEX (HG=F)").value.replace(" USD/lb", ""))
    diferencia = _numero(_metrica(at, "Diferencia entre las dos fuentes").value)
    assert 1 < bcch < 20 and 1 < comex < 20  # dólares por libra, un rango posible
    # tolerancia amplia: bcch y comex ya vienen redondeados a 2 decimales en pantalla, y ese redondeo mueve el cociente
    # más de lo que movería comparar los valores sin redondear
    assert diferencia == pytest.approx((comex / bcch - 1) * 100, abs=0.15)


def test_el_grafico_de_cobre_tiene_las_dos_series_y_acepta_cambiar_el_periodo():
    at = _abrir(ui.PASOS[1])
    assert len(at.get("plotly_chart")) == 1
    for periodo in ("1 año", "Todo el historial"):
        at.radio(key="cm_ventana_cobre").set_value(periodo).run()
        assert not at.exception


def test_el_aviso_del_arancel_solo_aparece_si_el_maximo_del_periodo_cae_en_julio_de_2025():
    """Con 5 años (el máximo real de toda la historia) debe salir; con 1 año (que no incluye julio de 2025) no debe salir."""
    at = _abrir(ui.PASOS[1])
    assert any("se separaron mucho más de lo normal" in m.value for m in at.markdown)
    assert any("arancel a las importaciones de cobre" in m.value for m in at.markdown)

    at.radio(key="cm_ventana_cobre").set_value("1 año").run()
    assert not at.exception
    # un año atrás de "hoy" (2026-10-29) no llega a julio de 2025: no debería citarse ese episodio en esa ventana
    assert not any("arancel a las importaciones de cobre" in m.value for m in at.markdown)


def test_la_pantalla_dice_que_no_puede_calcular_contango():
    at = _abrir(ui.PASOS[1])
    assert any("contango" in i.value and "backwardation" in i.value for i in at.info)


# ---------------------------------------------------------------------------
# _mensaje_de_divergencia: función pura, probada con casos sintéticos
# ---------------------------------------------------------------------------
def test_sin_una_divergencia_grande_no_hay_mensaje():
    serie = pd.Series([1.0, -1.0, 2.0, -2.0], index=pd.bdate_range("2024-01-01", periods=4))
    assert ui._mensaje_de_divergencia(serie) is None
    assert ui._mensaje_de_divergencia(serie * 0) is None


def test_justo_en_el_umbral_no_hay_mensaje_y_un_poco_mas_arriba_si():
    base = pd.bdate_range("2024-01-01", periods=3)
    en_el_umbral = pd.Series([0.0, ui.UMBRAL_DIVERGENCIA_COBRE_INUSUAL, 0.0], index=base)
    assert ui._mensaje_de_divergencia(en_el_umbral) is None  # estrictamente mayor, no igual
    sobre_el_umbral = pd.Series([0.0, ui.UMBRAL_DIVERGENCIA_COBRE_INUSUAL + 0.01, 0.0], index=base)
    assert ui._mensaje_de_divergencia(sobre_el_umbral) is not None


def test_una_divergencia_grande_dentro_de_la_ventana_del_arancel_cita_esa_causa():
    serie = pd.Series([0.0, 30.0, 0.0], index=[pd.Timestamp("2025-06-15"), pd.Timestamp("2025-07-23"), pd.Timestamp("2025-08-01")])
    mensaje = ui._mensaje_de_divergencia(serie)
    assert mensaje is not None and "23-07-2025" in mensaje and "arancel a las importaciones de cobre" in mensaje


def test_una_divergencia_grande_fuera_de_la_ventana_del_arancel_no_inventa_una_causa():
    """Mismo tamaño de divergencia que el caso anterior, pero en una fecha donde esa causa no es verdad."""
    serie = pd.Series([0.0, 30.0, 0.0], index=[pd.Timestamp("2026-01-01"), pd.Timestamp("2026-03-10"), pd.Timestamp("2026-05-01")])
    mensaje = ui._mensaje_de_divergencia(serie)
    assert mensaje is not None and "10-03-2026" in mensaje
    assert "arancel" not in mensaje and "sin una causa identificada" in mensaje


def test_justo_en_los_bordes_de_la_ventana_del_arancel():
    inicio, fin = ui.VENTANA_ARANCEL_COBRE_2025
    dentro = pd.Series([0.0, 20.0], index=[inicio - pd.Timedelta(days=5), inicio])
    fuera = pd.Series([0.0, 20.0], index=[fin, fin + pd.Timedelta(days=1)])
    assert "arancel" in ui._mensaje_de_divergencia(dentro)
    assert "arancel" not in ui._mensaje_de_divergencia(fuera)


# ---------------------------------------------------------------------------
# Filas atrasadas y respeto de la selección del gráfico
# ---------------------------------------------------------------------------
def test_una_fila_con_precio_viejo_se_marca_como_atrasada_y_una_fresca_no():
    hoy = pd.Timestamp("2026-10-29")
    fechas_frescas = pd.bdate_range("2025-01-01", "2026-10-28")
    fechas_viejas = pd.bdate_range("2025-01-01", "2026-09-01")  # más de DIAS_HABILES_DE_ATRASO hábiles antes de "hoy"
    precios = pd.DataFrame({
        "GC=F": pd.Series(100.0, index=fechas_frescas),
        "SI=F": pd.Series(20.0, index=fechas_viejas),
    })
    resumen = ui._resumen_del_grupo(precios, ["GC=F", "SI=F"], tasa_libre=4.0, hoy=hoy)
    assert resumen.loc["GC=F", "_atrasado_bool"] == False  # noqa: E712 (es un bool de numpy, no identidad)
    assert resumen.loc["SI=F", "_atrasado_bool"] == True  # noqa: E712


def test_el_tramo_del_grafico_solo_mira_las_columnas_elegidas_y_no_las_demas():
    """Un commodity NO elegido, con huecos AL INICIO de su historia (que ffill no puede rellenar porque no hay
    un valor previo), no debe hacer perder filas al commodity que sí se eligió. Si la función mirara de más
    (`precios[disponibles]` en vez de `precios[elegidos]`), esas filas sin dato del no elegido las tira el
    dropna final y el elegido pierde puntos que sí tenía."""
    fechas = pd.bdate_range("2024-01-01", periods=5)
    precios = pd.DataFrame({
        "GC=F": [100.0, 101.0, 102.0, 103.0, 104.0],  # elegido, sin huecos
        "HG=F": [float("nan"), float("nan"), 4.2, 4.3, 4.4],  # NO elegido, con huecos al inicio (ffill no los llena)
    }, index=fechas)
    tramo = ui._tramo_para_grafico(precios, ["GC=F"], dias=None)
    assert list(tramo.columns) == ["GC=F"]
    assert "HG=F" not in tramo.columns
    assert len(tramo) == 5  # ninguna fila de GC=F debería perderse por culpa de un commodity que ni se graficó
    assert tramo["GC=F"].tolist() == [100.0, 101.0, 102.0, 103.0, 104.0]


def test_el_grafico_de_comparacion_muestra_exactamente_los_commodities_elegidos():
    import json

    at = _abrir(ui.PASOS[0])
    at.multiselect(key="cm_commodities_grafico").set_value(["ZC=F", "KC=F", "GC=F"]).run()
    assert not at.exception
    nombres = {s["name"] for s in json.loads(at.get("plotly_chart")[0].proto.spec)["data"]}
    assert nombres == {"ZC=F", "KC=F", "GC=F"}

    at.multiselect(key="cm_commodities_grafico").set_value(["HG=F"]).run()
    assert not at.exception
    nombres = {s["name"] for s in json.loads(at.get("plotly_chart")[0].proto.spec)["data"]}
    assert nombres == {"HG=F"}
