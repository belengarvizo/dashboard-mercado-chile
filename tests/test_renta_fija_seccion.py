"""La sección «Renta Fija» del dashboard con datos REALES de la base: que se abra, que cada paso se dibuje,
que la tabla de ETFs traiga los números reales con sus tooltips y que lo que se muestre coincida con lo que
dice la base.

Es una prueba de la pantalla (AppTest sobre app/dashboard.py), complementaria a test_renta_fija.py (el motor)
y a test_catalogo_y_tabla_renta_fija.py (catálogo, explicaciones y tabla). Como los datos son reales, las
pruebas no fijan valores de mercado: comprueban relaciones que tienen que cumplirse siempre (la duración de un
bono del Tesoro corto es menor que la de uno largo, la inflación implícita es la resta de dos tasas mostradas,
una tasa es positiva, etc.).
"""
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pandas as pd
import pytest
from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

import renta_fija_ui as ui

load_dotenv()  # no pisa una DATABASE_URL ya presente en el entorno

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
SECCION = "Renta Fija"


def _abrir(paso=None) -> AppTest:
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = SECCION
    if paso:
        at.session_state["rf_paso"] = paso
    at.run(timeout=420)
    assert not at.exception, f"La app lanzó una excepción: {at.exception}"
    return at


def _ir_a(at: AppTest, paso: str) -> AppTest:
    at.session_state["rf_paso"] = paso
    at.run(timeout=420)
    assert not at.exception, f"La app lanzó una excepción en {paso!r}: {at.exception}"
    return at


def _metrica(at: AppTest, etiqueta: str):
    for m in at.metric:
        if m.label == etiqueta:
            return m
    raise AssertionError(f"No hay una métrica «{etiqueta}». Hay: {[m.label for m in at.metric]}")


def _numero(texto: str) -> float:
    """«1,234.56%» → 1234.56 (mismo formato que las tablas de acciones: coma de miles, punto decimal)."""
    limpio = texto.replace("%", "").replace("pp", "").replace("años", "").replace("+", "").strip()
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


# ---------------------------------------------------------------------------
# Nombres de series: que sigan siendo los que escribe el script de descarga
# ---------------------------------------------------------------------------
def test_los_nombres_de_series_coinciden_con_los_del_script_de_descarga():
    import actualizar_bcch as ab

    nombres_bcch = {info["nombre"] for info in ab.SERIES_A_DESCARGAR.values()}
    for grupo in ui.CURVA_CHILE.values():
        for nombre in grupo.values():
            assert nombre in nombres_bcch, nombre
    for nombre in (ui.NOMBRE_TPM_CHILE, ui.NOMBRE_PDBC14, ui.NOMBRE_SWAP90):
        assert nombre in nombres_bcch, nombre
    assert ui.NOMBRE_UST10 == ab.NOMBRE_UST10
    assert ui.NOMBRE_TPM_EEUU == ab.NOMBRE_TPM_EEUU
    assert ui.NOMBRE_BAA10Y == ab.SERIES_RECESION_FRED["BAA10Y"]["nombre"]
    descargadas = {j["nombre"] for j in ab._construir_jobs()}
    for plazo in ui.et.PLAZOS_ANIOS:
        assert ui.nombre_treasury(plazo) in descargadas, f"el script no descarga el plazo {plazo!r}"


# ---------------------------------------------------------------------------
# Huecos en las series: el gráfico no debe inventar una línea donde no hay datos
# ---------------------------------------------------------------------------
def test_un_hueco_corta_la_linea_en_vez_de_unir_los_bordes():
    s = pd.Series([1.0, 2.0, 3.0, 4.0], index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-03-15", "2024-03-16"]))
    assert ui._huecos(s) == [(pd.Timestamp("2024-01-02"), pd.Timestamp("2024-03-15"))]
    cortada = ui._cortar_en_huecos(s)
    assert len(cortada) == 5 and cortada.isna().sum() == 1
    assert cortada.index[2] == pd.Timestamp("2024-01-03") and pd.isna(cortada.iloc[2])
    assert cortada.dropna().tolist() == [1.0, 2.0, 3.0, 4.0]


def test_fines_de_semana_y_feriados_no_son_huecos():
    dias = pd.bdate_range("2024-01-01", "2024-03-29")
    s = pd.Series(range(len(dias)), index=dias, dtype=float).drop(pd.Timestamp("2024-02-14"))
    assert ui._huecos(s) == []
    assert ui._cortar_en_huecos(s) is s


def test_el_umbral_del_hueco_es_estricto():
    base = pd.Timestamp("2024-01-01")
    justo = pd.Series([1.0, 2.0], index=[base, base + pd.Timedelta(days=ui.UMBRAL_HUECO_DIAS)])
    uno_mas = pd.Series([1.0, 2.0], index=[base, base + pd.Timedelta(days=ui.UMBRAL_HUECO_DIAS + 1)])
    assert ui._huecos(justo) == []
    assert len(ui._huecos(uno_mas)) == 1


# ---------------------------------------------------------------------------
# La pantalla
# ---------------------------------------------------------------------------
def test_la_seccion_se_abre_y_dice_que_los_datos_son_reales():
    at = _abrir()
    assert any("Renta fija" in h.value for h in at.header)
    assert any("son **reales**" in i.value for i in at.info)


def test_cada_paso_se_dibuja_sin_errores():
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)


def test_ya_no_hay_calculadoras_con_valores_inventados():
    """Ningún paso debe pedir cupón, plazo o tasa ficticios: los únicos controles son de vista (qué graficar y en qué período)."""
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)
        assert len(at.number_input) == 0, f"{paso}: hay un campo numérico, o sea una calculadora"
        assert len(at.slider) == 0, f"{paso}: hay un slider, o sea una calculadora"


def test_la_tabla_de_etfs_trae_los_diez_instrumentos_con_su_tooltip():
    at = _abrir(ui.PASOS[0])
    html = _html(at)
    for ticker, datos in ui.ETFS_RENTA_FIJA.items():
        fila = _fila_de_etf(html, ticker)
        assert datos["nombre"] in fila, f"{ticker}: el tooltip no trae el nombre completo"
        for texto in ("Duración medida", "Volatilidad", "Caída máxima", "Beta vs S&amp;P 500", "Sharpe", "Retorno:"):
            assert texto in fila, f"{ticker}: al tooltip le falta «{texto}»"
        assert "no disponible" not in fila, f"{ticker}: hay un indicador sin datos reales"


def test_los_numeros_de_la_tabla_son_coherentes_con_el_riesgo_de_cada_instrumento():
    """Relaciones que deben cumplirse siempre con datos reales (no valores fijos de mercado)."""
    at = _abrir(ui.PASOS[0])
    html = _html(at)

    def celdas(ticker):
        fila = _fila_de_etf(html, ticker)
        return [re.sub(r"<[^>]+>", "", c).strip() for c in fila.split("</td>")]

    encabezados = [re.sub(r"<[^>]+>", "", h) for h in re.findall(r"<th[^>]*>(.*?)</th>", html)]
    col = {nombre: i for i, nombre in enumerate(encabezados)}
    duracion = {t: float(re.search(r"Duración medida = ([\d.]+) años", _fila_de_etf(html, t)).group(1)) for t in ui.ETFS_RENTA_FIJA}
    volatilidad = {t: _numero(celdas(t)[col["Vol. %"]]) for t in ui.ETFS_RENTA_FIJA}

    # el Tesoro más largo es más sensible a las tasas y más volátil que el más corto
    assert duracion["SHY"] < duracion["IEI"] < duracion["IEF"] < duracion["TLT"]
    assert volatilidad["SHY"] < volatilidad["IEF"] < volatilidad["TLT"]
    # y las caídas máximas son siempre negativas o cero
    for t in ui.ETFS_RENTA_FIJA:
        assert _numero(celdas(t)[col["Caída máx. %"]]) <= 0, t
    # el R² es una proporción
    for t in ui.ETFS_RENTA_FIJA:
        assert 0 <= _numero(celdas(t)[col["R²"]]) <= 1, t


def test_la_tabla_de_etfs_cabe_en_pantalla_encabezados_cortos_y_sin_columnas_de_mas():
    """Una tabla HTML más ancha que la pantalla esconde sus últimas columnas (Beta y Sharpe quedaron cortadas una vez)."""
    at = _abrir(ui.PASOS[0])
    encabezados = [re.sub(r"<[^>]+>", "", h) for h in re.findall(r"<th[^>]*>(.*?)</th>", _html(at))]
    assert encabezados[:2] == ["ETF", "Grupo"] and {"Beta", "Sharpe", "Duración"} <= set(encabezados)
    assert len(encabezados) <= 13, encabezados
    assert max(len(e) for e in encabezados) <= 12, [e for e in encabezados if len(e) > 12]


def test_el_mercado_muestra_las_tasas_reales_a_10_anos():
    at = _abrir(ui.PASOS[0])
    for etiqueta in ("Tesoro de EEUU a 10 años", "BCP a 10 años (pesos)", "BCU a 10 años (UF, tasa real)"):
        valor = _metrica(at, etiqueta).value
        assert valor != "—", f"{etiqueta}: no llegó el dato real de la base"
        assert 0 < _numero(valor) < 30


def test_el_grafico_de_etfs_acepta_cambiar_la_seleccion_y_el_periodo():
    at = _abrir(ui.PASOS[0])
    at.multiselect(key="rf_etfs_grafico").set_value(["TLT", "AGG"]).run()
    assert not at.exception
    at.radio(key="rf_ventana_etfs").set_value("Todo el historial").run()
    assert not at.exception
    at.multiselect(key="rf_etfs_grafico").set_value([]).run()
    assert not at.exception and any("al menos un ETF" in i.value for i in at.info)


def test_la_valorizacion_usa_la_curva_real_y_un_bono_a_la_par_vale_100():
    at = _abrir(ui.PASOS[1])
    t = _tabla(at, "1 peso de ese plazo vale hoy")
    factores = [float(v) for v in t["1 peso de ese plazo vale hoy"]]
    assert all(0 < f < 1 for f in factores) and factores == sorted(factores, reverse=True)  # el futuro vale cada vez menos
    compras = _tabla(at, "Retorno ETF")
    assert set(compras["ETF"]) <= {"SHY", "IEI", "IEF", "TLT"}
    assert len(compras) >= 8  # 6 meses, 1 año y 2 años × 4 plazos, menos los que no caben


def test_si_la_tasa_subio_el_bono_comprado_a_la_par_hoy_vale_menos_de_100():
    """Coherencia entre dos columnas reales de la misma fila: tasa de hoy mayor que la de compra ⇒ precio bajo 100."""
    at = _abrir(ui.PASOS[1])
    compras = _tabla(at, "Retorno ETF")
    for _, f in compras.iterrows():
        subio = _numero(f["Tasa hoy"]) > _numero(f["Tasa compra"])
        assert (_numero(f["Precio hoy"]) < 100) == subio, f.to_dict()


def test_la_duracion_del_paso_3_es_la_medida_con_datos_y_el_grafico_sigue_al_etf_elegido():
    at = _abrir(ui.PASOS[2])
    t = _tabla(at, "Duración teórica").set_index("ETF")
    assert _numero(t.loc["SHY", "Duración medida"]) < _numero(t.loc["IEF", "Duración medida"]) < _numero(t.loc["TLT", "Duración medida"])
    assert _numero(t.loc["SHY", "Duración teórica"]) < _numero(t.loc["IEF", "Duración teórica"]) < _numero(t.loc["TLT", "Duración teórica"])
    # los bonos del Tesoro se explican casi por completo con las tasas; los de alto rendimiento, no
    assert _numero(t.loc["IEF", "R²"]) > 0.8
    assert _numero(t.loc["HYG", "R²"]) < _numero(t.loc["IEF", "R²"])
    at.selectbox(key="rf_etf_duracion").set_value("TLT").run()
    assert not at.exception


def test_el_riesgo_de_credito_trae_el_spread_real_y_avisa_que_no_hay_probabilidades_de_default():
    at = _abrir(ui.PASOS[3])
    assert _numero(_metrica(at, "Spread Baa − Tesoro 10 años").value) > 0
    assert any("probabilidades de default" in c.value for c in at.caption)
    at.radio(key="rf_ventana_credito").set_value("Todo el historial").run()
    assert not at.exception


def test_el_banco_central_muestra_las_cuatro_tasas_el_diferencial_y_la_curva_chilena():
    at = _abrir(ui.PASOS[4])
    for etiqueta in ui.SERIES_TASAS:
        assert _metrica(at, etiqueta).value != "—", f"{etiqueta}: no llegó el dato real"
    chile = _numero(_metrica(at, "TPM de Chile").value)
    eeuu = _numero(_metrica(at, "Tasa de política de EEUU (Fed funds)").value)
    diferencial = _numero(_metrica(at, "Diferencial de política monetaria (Chile − EEUU)").value)
    assert diferencial == pytest.approx(chile - eeuu, abs=0.011)

    curva = _tabla(at, "Tasa (%)")
    assert list(curva["Bono"]) == ["BCP (pesos)"] * 3 + ["BCU (UF, tasa real)"] * 3
    assert all(0 < float(v) < 30 for v in curva["Tasa (%)"] if v != "—")
    # la inflación implícita de cada plazo es una tasa nominal menos una real: positiva y de un orden razonable
    for plazo in ("A 5 años", "A 10 años"):
        assert -1 < _numero(_metrica(at, plazo).value) < 10


def test_el_paso_5_avisa_los_huecos_de_datos_en_vez_de_unir_los_bordes():
    at = _abrir(ui.PASOS[4])
    at.radio(key="rf_ventana_tasas").set_value("Todo el historial").run()
    assert not at.exception
    avisos = [c.value for c in at.caption if "Sin datos en la base" in c.value]
    for aviso in avisos:
        assert re.search(r"\d{2}-\d{2}-\d{4} al \d{2}-\d{2}-\d{4}", aviso)


def test_la_curva_las_carteras_con_etfs_y_el_rodar():
    at = _abrir(ui.PASOS[5])
    pendiente = _numero(_metrica(at, "Pendiente 10 años − 2 años").value)
    assert (_metrica(at, "Forma de la curva").value == "Invertida") == (pendiente <= 0)

    rodar = _tabla(at, "Efecto de rodar")
    assert len(rodar) >= 8
    for _, f in rodar.iterrows():  # retorno total = carry + efecto de rodar (por filas)
        assert _numero(f["Retorno total"]) == pytest.approx(_numero(f["Cupones (carry)"]) + _numero(f["Efecto de rodar"]), abs=0.011)

    carteras = _tabla(at, "Estrategia").set_index("Estrategia")
    assert list(carteras.index) == ["Bullet", "Barbell", "Escalera"]
    # el barbell se arma para tener la misma duración medida que el bullet
    assert _numero(carteras.loc["Barbell", "Duración medida"]) == pytest.approx(_numero(carteras.loc["Bullet", "Duración medida"]), abs=0.011)
    for periodo in ("3 años", "Todo el historial"):
        at.radio(key="rf_ventana_carteras").set_value(periodo).run()
        assert not at.exception


def test_la_emision_muestra_referencias_reales_y_no_pide_supuestos():
    at = _abrir(ui.PASOS[6])
    for plazo in (5, 10, 30):
        assert 0 < _numero(_metrica(at, f"Tesoro de EEUU a {plazo} años").value) < 30
    corporativo = _numero(_metrica(at, "Rendimiento de un bono corporativo Baa a 10 años (Tesoro + spread)").value)
    assert corporativo > _numero(_metrica(at, "Tesoro de EEUU a 10 años").value)  # el crédito paga más que el Tesoro
    assert any("no tiene datos de emisiones reales" in m.value for m in at.markdown)
