"""La sección «FX y Carry Trade» del dashboard con datos REALES de la base: que se abra, que cada paso se dibuje, que las tablas
traigan los números reales con sus tooltips y que lo que se muestre sea coherente consigo mismo, incluso entre pasos distintos.

Es una prueba de la pantalla (AppTest sobre app/dashboard.py), complementaria a test_fx_carry.py (el motor) y a
test_catalogo_y_glosario_fx.py (catálogo, tasas del cron y explicaciones). Como los datos son reales, las pruebas no fijan valores de
mercado: comprueban relaciones que tienen que cumplirse siempre (total = spot + carry, el lado de la estrategia sigue el signo del
diferencial, el cruce EUR/GBP es el cociente de EUR/USD y GBP/USD).
"""
import html as html_lib
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest
from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

import fx_carry_ui as ui

load_dotenv()  # no pisa una DATABASE_URL ya presente en el entorno

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
SECCION = "FX y Carry Trade"


def _abrir(paso=None) -> AppTest:
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = SECCION
    if paso:
        at.session_state["fx_paso"] = paso
    at.run(timeout=420)
    assert not at.exception, f"La app lanzó una excepción: {at.exception}"
    return at


def _ir_a(at: AppTest, paso: str) -> AppTest:
    at.session_state["fx_paso"] = paso
    at.run(timeout=420)
    assert not at.exception, f"La app lanzó una excepción en {paso!r}: {at.exception}"
    return at


def _numero(texto: str) -> float:
    """«1,234.56%» → 1234.56 (mismo formato que las tablas de acciones: coma de miles, punto decimal)."""
    limpio = texto.replace("%", "").replace("pp", "").replace("+", "").strip()
    return float(limpio.replace(",", ""))


def _html(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def _fila(html: str, etiqueta: str) -> str:
    filas = [f for f in html.split("<tr>") if f"glosario-tooltip\">{etiqueta}<" in f]
    assert len(filas) == 1, f"no encontré la fila de {etiqueta} en la tabla"
    return filas[0]


def _encabezados(html: str) -> list[str]:
    return [html_lib.unescape(re.sub(r"<[^>]+>", "", h)) for h in re.findall(r"<th[^>]*>(.*?)</th>", html)]


def _celdas(html: str, etiqueta: str) -> dict[str, str]:
    """Texto de cada celda de la fila de una etiqueta, por encabezado."""
    fila = _fila(html, etiqueta)
    valores = [html_lib.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in fila.split("</td>")][:-1]
    valores[0] = etiqueta  # los tooltips meten texto dentro de la primera celda
    tabla = next(t for t in html.split("<table")[1:] if f"glosario-tooltip\">{etiqueta}<" in t)
    encabezados = _encabezados("<table" + tabla.split("</tr>")[0] + "</tr>")
    assert len(encabezados) == len(valores), (encabezados, valores)
    return dict(zip(encabezados, valores))


def _tickers_del_paso_1() -> list[str]:
    return [ui.etiqueta_corta(t) for t in ui.PARES_FX]


# ---------------------------------------------------------------------------
# La pantalla
# ---------------------------------------------------------------------------
def test_la_seccion_esta_en_el_selector_y_dice_que_los_datos_son_reales():
    at = _abrir()
    assert any("FX y carry trade" in h.value for h in at.header)
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
    """Streamlit toma el «$» como inicio de una fórmula matemática y rompe el texto."""
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)
        textos = [m.value for m in at.markdown] + [c.value for c in at.caption] + [i.value for i in at.info]
        for t in textos:
            assert "$" not in re.sub(r"<[^>]*>", "", t), f"{paso}: {t[:80]!r}"


def test_ninguna_pantalla_muestra_correlaciones_con_la_bolsa_ni_con_el_indice_dolar():
    """Las barras de divisas de Yahoo llevan otra convención de fecha: esas correlaciones saldrían engañosas y no se muestran."""
    at = _abrir()
    for paso in ui.PASOS:
        _ir_a(at, paso)
        todo = _html(at)
        encabezados = _encabezados(todo)
        assert not [e for e in encabezados if "S&P" in e or "DXY" in e], (paso, encabezados)
        assert "Correlación con el S&amp;P 500" not in todo and "Correlación con el índice dólar" not in todo, paso
    assert any("a propósito" in i.value for i in _ir_a(at, ui.PASOS[0]).info)


# ---------------------------------------------------------------------------
# Paso 1: el mercado de divisas
# ---------------------------------------------------------------------------
def test_la_tabla_de_divisas_trae_los_14_pares_con_su_tooltip_completo():
    html = _html(_abrir(ui.PASOS[0]))
    for ticker, datos in ui.PARES_FX.items():
        fila = _fila(html, ui.etiqueta_corta(ticker))
        assert datos["nombre"] in fila and datos["cotiza"] in fila, f"{ticker}: el tooltip no trae el nombre ni cómo se cotiza"
        for texto in ("Movimiento", "Volatilidad", "Rango del año", "Correlación"):
            assert texto in fila, f"{ticker}: al tooltip le falta «{texto}»"
        assert "no disponible" not in fila, f"{ticker}: hay un indicador sin datos reales"


def test_el_indice_dolar_no_calcula_su_correlacion_y_lo_explica():
    html = _html(_abrir(ui.PASOS[0]))
    fila = _fila(html, "DXY")
    assert "No se calcula" in fila and "convención de fecha" in fila
    assert _celdas(html, "DXY")["Correl. CLP"] == "—"


def test_la_tabla_de_divisas_cabe_en_pantalla_y_usa_la_correlacion_con_usd_clp():
    encabezados = _encabezados(_html(_abrir(ui.PASOS[0])))
    assert encabezados[0] == "Par" and encabezados[-1] == "Correl. CLP" and {"Vol. %", "Rango 1A %"} <= set(encabezados)
    assert len(encabezados) <= 13, encabezados
    assert max(len(e) for e in encabezados) <= 12, [e for e in encabezados if len(e) > 12]


def test_los_numeros_de_la_tabla_de_divisas_estan_dentro_de_su_rango_posible():
    html = _html(_abrir(ui.PASOS[0]))
    for etiqueta in _tickers_del_paso_1():
        c = _celdas(html, etiqueta)
        assert _numero(c["Vol. %"]) > 0, etiqueta
        assert abs(_numero(c["1D %"])) < 15, etiqueta  # una divisa no se mueve 15 % en un día
        # el rango del año (máximo / mínimo - 1) no puede ser menor que lo que se movió entre el primer y el último día
        assert _numero(c["Rango 1A %"]) >= abs(_numero(c["1A %"])) - 0.02, etiqueta
        if etiqueta != "DXY":
            assert -1 <= _numero(c["Correl. CLP"]) <= 1, etiqueta
    assert _numero(_celdas(html, "USD/CLP")["Correl. CLP"]) == pytest.approx(1.0, abs=0.005)


def test_los_cruces_cumplen_la_identidad_de_triangulacion_con_los_pares_contra_el_dolar():
    """EUR/GBP = EUR/USD ÷ GBP/USD: lo mismo tiene que valer para los retornos de 1 año de la tabla (misma fuente y convención)."""
    html = _html(_abrir(ui.PASOS[0]))
    retorno = {e: _numero(_celdas(html, e)["1A %"]) / 100 for e in ("EUR/GBP", "EUR/USD", "GBP/USD", "EUR/JPY", "USD/JPY", "GBP/JPY")}
    assert (1 + retorno["EUR/GBP"]) == pytest.approx((1 + retorno["EUR/USD"]) / (1 + retorno["GBP/USD"]), abs=0.005)
    assert (1 + retorno["EUR/JPY"]) == pytest.approx((1 + retorno["EUR/USD"]) * (1 + retorno["USD/JPY"]), abs=0.005)
    assert (1 + retorno["GBP/JPY"]) == pytest.approx((1 + retorno["GBP/USD"]) * (1 + retorno["USD/JPY"]), abs=0.005)


def test_el_grafico_de_pares_acepta_cambiar_la_seleccion_y_el_periodo():
    at = _abrir(ui.PASOS[0])
    at.multiselect(key="fx_pares_grafico").set_value(["EURUSD=X", "USDMXN=X"]).run()
    assert not at.exception
    at.radio(key="fx_ventana_pares").set_value("Todo el historial").run()
    assert not at.exception
    at.multiselect(key="fx_pares_grafico").set_value([]).run()
    assert not at.exception and any("al menos un par" in i.value for i in at.info)


# ---------------------------------------------------------------------------
# Paso 2: tasas y carry
# ---------------------------------------------------------------------------
def _tabla_del_carry(at: AppTest) -> dict[str, dict[str, str]]:
    html = _html(at)
    return {codigo: _celdas(html, codigo) for codigo in ui.MONEDAS_CARRY}


def test_el_carry_trae_las_seis_monedas_con_su_tooltip_y_avisa_cuales_no_tienen_tasa():
    at = _abrir(ui.PASOS[1])
    html = _html(at)
    for codigo, datos in ui.MONEDAS_CARRY.items():
        fila = _fila(html, codigo)
        for texto in ("Diferencial de tasas", "Resultado del último año", "Riesgo", datos["tasa"]):
            assert texto in fila, f"{codigo}: al tooltip le falta «{texto}»"
        assert "no disponible" not in fila and "No hay una tasa vigente" not in fila, f"{codigo}: hay un dato sin cubrir"
    for nombre in ui.MONEDAS_SIN_TASA.values():
        assert any(nombre in i.value for i in at.info), nombre


def test_el_total_es_spot_mas_carry_y_el_diferencial_es_la_tasa_local_menos_la_de_eeuu():
    at = _abrir(ui.PASOS[1])
    fed = float(re.search(r"Fed funds \((\d+\.\d+)%\)", " ".join(c.value for c in at.caption)).group(1))
    for codigo, c in _tabla_del_carry(at).items():
        assert _numero(c["Total 1A %"]) == pytest.approx(_numero(c["Spot 1A %"]) + _numero(c["Carry 1A %"]), abs=0.015), codigo
        # el diferencial es el del último tramo (tasa vigente el día anterior), así que puede diferir un poco si una tasa cambió ayer
        assert _numero(c["Difer. (pp)"]) == pytest.approx(_numero(c["Tasa local"]) - fed, abs=0.5), codigo
        assert _numero(c["Vol. %"]) > 0 and _numero(c["Caída máx. %"]) <= 0, codigo


def test_el_carry_sobre_riesgo_es_el_diferencial_dividido_por_la_volatilidad():
    for codigo, c in _tabla_del_carry(_abrir(ui.PASOS[1])).items():
        assert _numero(c["Carry/Vol"]) == pytest.approx(_numero(c["Difer. (pp)"]) / _numero(c["Vol. %"]), abs=0.012), codigo


def test_la_tabla_del_carry_cabe_en_pantalla_y_el_grafico_de_compensacion_cuenta_las_monedas_que_ganaron():
    at = _abrir(ui.PASOS[1])
    encabezados = _encabezados(_html(at))
    assert encabezados[0] == "Moneda" and {"Difer. (pp)", "Spot 1A %", "Carry 1A %", "Total 1A %", "Carry/Vol"} <= set(encabezados)
    assert len(encabezados) <= 13 and max(len(e) for e in encabezados) <= 12, encabezados
    assert len(at.get("plotly_chart")) == 1
    ganaron = sum(_numero(c["Total 1A %"]) > 0 for c in _tabla_del_carry(at).values())
    assert any(f"ganó en **{ganaron} de 6**" in m.value for m in at.markdown)


# ---------------------------------------------------------------------------
# Paso 3: la estrategia
# ---------------------------------------------------------------------------
def test_la_estrategia_va_larga_si_el_diferencial_de_hoy_es_positivo_y_corta_si_es_negativo():
    """Coherencia entre dos pasos: el «lado hoy» del paso 3 sale del mismo diferencial que muestra el paso 2."""
    at = _abrir(ui.PASOS[1])
    diferencial = {codigo: _numero(c["Difer. (pp)"]) for codigo, c in _tabla_del_carry(at).items()}
    _ir_a(at, ui.PASOS[2])
    html = _html(at)
    for codigo, valor in diferencial.items():
        lado = _celdas(html, codigo)["Lado hoy"]
        assert lado == ("Larga" if valor > 0 else "Corta"), f"{codigo}: diferencial {valor:+.2f} y lado {lado}"
    assert _celdas(html, ui.ROTULO_CARTERA)["Lado hoy"] == "Mixto"


def test_la_tabla_de_la_estrategia_trae_las_monedas_y_la_cartera_con_numeros_posibles():
    html = _html(_abrir(ui.PASOS[2]))
    for nombre in list(ui.MONEDAS_CARRY) + [ui.ROTULO_CARTERA]:
        c = _celdas(html, nombre)
        assert _numero(c["Vol. %"]) > 0 and _numero(c["Caída máx. %"]) <= 0, nombre
        assert 0 <= _numero(c["Meses gan. %"]) <= 100, nombre
        assert _numero(c["Peor mes %"]) <= _numero(c["Retorno/año %"]) + 25, nombre  # el peor mes no puede superar un año de retorno por mucho
        assert "no disponible" not in _fila(html, nombre) and "No hay datos suficientes" not in _fila(html, nombre), nombre


def test_la_cartera_diversifica_su_volatilidad_es_menor_que_la_de_cualquiera_de_sus_monedas():
    html = _html(_abrir(ui.PASOS[2]))
    vol_cartera = _numero(_celdas(html, ui.ROTULO_CARTERA)["Vol. %"])
    assert all(vol_cartera < _numero(_celdas(html, codigo)["Vol. %"]) for codigo in ui.MONEDAS_CARRY)


def test_la_frase_del_peor_mes_de_la_cartera_coincide_con_la_tabla():
    at = _abrir(ui.PASOS[2])
    cartera = _celdas(_html(at), ui.ROTULO_CARTERA)
    frase = next(m.value for m in at.markdown if m.value.startswith("El peor mes de la **cartera**"))
    peor = float(re.search(r"fue \*\*([+-]\d+\.\d)%\*\*", frase).group(1))
    caida = float(re.search(r"fue de \*\*(\d+\.\d)%\*\*", frase).group(1))
    assert peor == pytest.approx(_numero(cartera["Peor mes %"]), abs=0.06)
    assert caida == pytest.approx(abs(_numero(cartera["Caída máx. %"])), abs=0.06)
    assert re.search(r"terminadas el \d{2}-\d{2}-\d{4}", frase)


def test_cambiar_el_periodo_cambia_los_numeros_y_el_grafico_acepta_otras_estrategias():
    at = _abrir(ui.PASOS[2])
    cinco_anios = _celdas(_html(at), ui.ROTULO_CARTERA)["Retorno/año %"]
    at.radio(key="fx_ventana_estrategia").set_value("1 año").run()
    assert not at.exception
    un_anio = _celdas(_html(at), ui.ROTULO_CARTERA)["Retorno/año %"]
    assert un_anio != cinco_anios
    at.multiselect(key="fx_estrategias_grafico").set_value(["EUR", "CLP"]).run()
    assert not at.exception
    at.multiselect(key="fx_estrategias_grafico").set_value([]).run()
    assert not at.exception and any("al menos una estrategia" in i.value for i in at.info)


# ---------------------------------------------------------------------------
# Paso 4: Chile
# ---------------------------------------------------------------------------
def _metrica(at: AppTest, etiqueta: str):
    for m in at.metric:
        if m.label == etiqueta:
            return m
    raise AssertionError(f"No hay una métrica «{etiqueta}». Hay: {[m.label for m in at.metric]}")


def test_chile_muestra_el_dolar_el_cobre_y_la_correlacion_con_numeros_reales():
    at = _abrir(ui.PASOS[3])
    assert 300 < _numero(_metrica(at, "Dólar observado (pesos)").value) < 3000
    assert 0.5 < _numero(_metrica(at, "Cobre (USD por libra)").value) < 20
    correlacion = _numero(_metrica(at, "Correlación dólar-cobre, último año").value)
    assert -1 <= correlacion <= 1
    assert len(at.get("plotly_chart")) == 3  # dólar y cobre, correlación móvil, dólar y diferencial de tasas


def test_la_frase_de_la_correlacion_describe_su_fuerza_y_sentido_segun_el_numero_mostrado():
    at = _abrir(ui.PASOS[3])
    correlacion = _numero(_metrica(at, "Correlación dólar-cobre, último año").value)
    frase = next(c.value for c in at.caption if c.value.startswith("La correlación del último año es"))
    mostrado = float(re.search(r"es \*\*(-?\d\.\d\d)\*\*", frase).group(1))
    assert mostrado == pytest.approx(correlacion, abs=0.006)
    fuerza = "débil" if abs(mostrado) < 0.2 else "moderada" if abs(mostrado) < 0.5 else "fuerte"
    assert f"una relación **{fuerza}**" in frase
    assert ("negativa" in frase) == (mostrado < 0)


def test_el_diferencial_de_tasas_de_chile_es_la_tpm_menos_la_fed_y_la_comprobacion_de_datos_se_muestra():
    at = _abrir(ui.PASOS[3])
    frase = next(c.value for c in at.caption if c.value.startswith("Hoy la TPM de Chile"))
    tpm, dif, fed = (float(x) for x in re.search(r"TPM de Chile \((\d+\.\d+)%\) está (\d+\.\d+) puntos .* Fed \((\d+\.\d+)%\)", frase).groups())
    assert abs(abs(tpm - fed) - dif) < 0.011
    assert ("sobre" in frase) == (tpm >= fed)
    comprobacion = next(c.value for c in at.caption if c.value.startswith("Comprobación de datos"))
    assert re.search(r"difieren [+-]\d+\.\d\d%", comprobacion) and "convención de fecha" in comprobacion


def test_chile_acepta_cambiar_el_periodo():
    at = _abrir(ui.PASOS[3])
    for periodo in ("1 año", "Todo el historial"):
        at.radio(key="fx_ventana_chile").set_value(periodo).run()
        assert not at.exception


# ---------------------------------------------------------------------------
# La tabla del carry muestra los números del motor, sin recalcularlos
# ---------------------------------------------------------------------------
def _una_moneda_con_tasa_enorme():
    """Datos sintéticos de una sola moneda con una tasa gigante: así la volatilidad del TIPO DE CAMBIO y la de la
    POSICIÓN COMPLETA se separan mucho (el interés de un fin de semana es el triple que el de un día).

    Hace falta construirlo así porque con tasas reales las dos volatilidades casi coinciden: usar una en vez de la
    otra cambiaría el número mostrado en menos de lo que se redondea, y el error pasaría inadvertido en pantalla.
    """
    import numpy as np
    import pandas as pd

    fechas = pd.bdate_range("2025-01-01", periods=400)
    ruido = np.random.default_rng(11).normal(0, 0.002, len(fechas)).cumsum()
    precios = pd.DataFrame({ui.MONEDAS_CARRY["EUR"]["par"]: 1.10 + ruido * 0.05}, index=fechas)
    filas = [
        {"nombre": nombre, "fecha": f, "valor": valor}
        for nombre, valor in ((ui.NOMBRE_TASA_EEUU, 0.0), (ui.MONEDAS_CARRY["EUR"]["serie_tasa"], 500.0))
        for f in fechas
    ]
    return pd.DataFrame(filas), precios


def test_la_columna_carry_sobre_riesgo_es_la_del_motor_y_no_se_recalcula_con_otra_volatilidad():
    import pandas as pd

    macro, precios = _una_moneda_con_tasa_enorme()
    tabla = ui._resumen_del_carry(macro, precios, precios.index[-1] + pd.Timedelta(days=1))
    esperado = ui.fx.resumen_del_carry(ui._retornos_de_las_monedas(macro, precios)["EUR"], ui.rf.DIAS_DEL_ANIO)
    assert tabla.loc["EUR", "Carry sobre riesgo"] == pytest.approx(esperado["carry_sobre_riesgo"])
    # el caso está bien elegido: con la volatilidad de la posición completa el número sería muy distinto
    assert abs(esperado["diferencial_actual"] / esperado["volatilidad_total"] - esperado["carry_sobre_riesgo"]) > 1.0


def test_las_columnas_de_spot_carry_y_total_tambien_son_las_del_motor():
    import pandas as pd

    macro, precios = _una_moneda_con_tasa_enorme()
    tabla = ui._resumen_del_carry(macro, precios, precios.index[-1] + pd.Timedelta(days=1))
    esperado = ui.fx.resumen_del_carry(ui._retornos_de_las_monedas(macro, precios)["EUR"], ui.rf.DIAS_DEL_ANIO)
    for columna, clave in (("Spot 1 año (%)", "spot"), ("Carry 1 año (%)", "carry"), ("Total 1 año (%)", "total"),
                           ("Diferencial (pp)", "diferencial_actual"), ("Volatilidad (%)", "volatilidad_spot"),
                           ("Caída máxima (%)", "caida_maxima")):
        assert tabla.loc["EUR", columna] == pytest.approx(esperado[clave]), columna
