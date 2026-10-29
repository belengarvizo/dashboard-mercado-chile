"""Pruebas del motor de «FX y Carry Trade» (fx_carry.py) con series sintéticas de respuesta conocida.

Cada prueba arma un caso donde la respuesta correcta se puede calcular a mano (un tipo de cambio quieto con tasas de 10 % y 4 %
da un retorno de tramo igual a 6 % × días / 365; una estrategia que invierte su lado cuando el diferencial cambia de signo),
de modo que un error de fórmula, de signo o de alineación de fechas no pueda pasar inadvertido. Los datos reales se prueban
aparte, en test_fx_carry_seccion.py.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pytest

import fx_carry as fx


def _fechas(n: int = 300, inicio: str = "2024-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(inicio, periods=n)


def _constante(valor: float, fechas: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(valor, index=fechas)


# ---------------------------------------------------------------------------
# valor_en_dolares
# ---------------------------------------------------------------------------
def test_un_par_cotizado_en_dolares_por_moneda_queda_igual_y_uno_cotizado_en_monedas_por_dolar_se_invierte():
    f = _fechas(3)
    eurusd = pd.Series([1.10, 1.20, 1.25], index=f)
    usdjpy = pd.Series([100.0, 125.0, 200.0], index=f)
    assert fx.valor_en_dolares(eurusd, base_es_dolar=False).tolist() == [1.10, 1.20, 1.25]
    assert fx.valor_en_dolares(usdjpy, base_es_dolar=True).tolist() == pytest.approx([0.01, 0.008, 0.005])


def test_un_precio_no_positivo_o_vacio_se_descarta_en_vez_de_dividir_por_cero():
    f = _fechas(4)
    serie = pd.Series([100.0, 0.0, np.nan, 50.0], index=f)
    resultado = fx.valor_en_dolares(serie, base_es_dolar=True)
    assert list(resultado.index) == [f[0], f[3]] and resultado.tolist() == pytest.approx([0.01, 0.02])


# ---------------------------------------------------------------------------
# tasa_en_cada_fecha
# ---------------------------------------------------------------------------
def test_la_tasa_se_mantiene_hasta_que_se_publica_otra_y_antes_del_primer_dato_esta_vacia():
    fechas = pd.to_datetime(["2024-01-01", "2024-01-15", "2024-02-01", "2024-02-20"])
    tasa = pd.Series([5.0, 6.0], index=pd.to_datetime(["2024-01-10", "2024-02-01"]))
    r = fx.tasa_en_cada_fecha(tasa, fechas)
    assert np.isnan(r.iloc[0])  # antes del primer dato
    assert r.iloc[1] == 5.0 and r.iloc[2] == 6.0 and r.iloc[3] == 6.0


def test_una_tasa_publicada_hace_demasiado_se_considera_vencida():
    fechas = pd.to_datetime(["2024-01-12", "2024-02-20", "2024-06-01"])
    tasa = pd.Series([5.0], index=pd.to_datetime(["2024-01-10"]))
    r = fx.tasa_en_cada_fecha(tasa, fechas, antiguedad_maxima_dias=75)
    assert r.iloc[0] == 5.0  # 2 días
    assert r.iloc[1] == 5.0 or np.isnan(r.iloc[1])
    assert (fechas[1] - tasa.index[0]).days == 41 and r.iloc[1] == 5.0  # 41 días: vigente
    assert np.isnan(r.iloc[2])  # 143 días: vencida
    # sin tope, sigue vigente para siempre
    assert fx.tasa_en_cada_fecha(tasa, fechas).iloc[2] == 5.0


def test_una_serie_de_tasas_vacia_da_todo_vacio():
    fechas = _fechas(5)
    assert fx.tasa_en_cada_fecha(pd.Series(dtype=float), fechas).isna().all()


# ---------------------------------------------------------------------------
# retornos_del_carry
# ---------------------------------------------------------------------------
def test_con_el_tipo_de_cambio_quieto_cada_tramo_rinde_el_diferencial_por_los_dias_transcurridos():
    f = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-09"])  # viernes, lunes (3 días), martes (1 día)
    r = fx.retornos_del_carry(_constante(1.0, f), pd.Series([10.0], index=[f[0]]), pd.Series([4.0], index=[f[0]]))
    assert len(r) == 2
    assert r["spot"].tolist() == [0.0, 0.0]
    assert r["total"].tolist() == pytest.approx([0.06 * 3 / 365, 0.06 * 1 / 365])
    assert r["diferencial"].tolist() == pytest.approx([6.0, 6.0])


def test_el_total_es_exactamente_spot_mas_carry_y_se_calcula_con_la_formula_de_la_posicion_financiada():
    f = pd.to_datetime(["2024-01-05", "2024-01-08"])
    valor = pd.Series([1.00, 1.02], index=f)  # la moneda sube 2 %
    r = fx.retornos_del_carry(valor, pd.Series([10.0], index=[f[0]]), pd.Series([4.0], index=[f[0]]))
    factor = 3 / 365
    esperado = (1 + 0.02) * (1 + 0.10 * factor) - (1 + 0.04 * factor)
    assert r["total"].iloc[0] == pytest.approx(esperado)
    assert r["spot"].iloc[0] == pytest.approx(0.02)
    assert r["carry"].iloc[0] == pytest.approx(esperado - 0.02)
    assert (r["spot"] + r["carry"]).iloc[0] == pytest.approx(r["total"].iloc[0])


def test_sin_diferencial_de_tasas_el_total_es_el_movimiento_del_tipo_de_cambio_mas_su_interes_sobre_la_ganancia():
    """Con las dos tasas iguales no hay carry de verdad: queda solo el término cruzado spot × tasa × días (minúsculo, de ~4 diezmilésimas)."""
    f = _fechas(50)
    valor = pd.Series(np.linspace(1.0, 1.3, 50), index=f)
    r = fx.retornos_del_carry(valor, _constante(5.0, f), _constante(5.0, f))
    dias = pd.Series(f, index=f).diff().dt.days.loc[r.index]
    assert r["total"].tolist() == pytest.approx((r["spot"] * (1 + 0.05 * dias / 365)).tolist())
    assert (r["carry"] - r["spot"] * 0.05 * dias / 365).abs().max() == pytest.approx(0.0, abs=1e-15)
    assert r["carry"].abs().max() < 1e-4


def test_el_tramo_usa_la_tasa_vigente_al_inicio_y_no_la_del_final():
    """La tasa de la moneda pasa de 10 % a 20 % el día 3: el tramo que TERMINA ese día todavía rinde la del 10 %."""
    f = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    tasa = pd.Series([10.0, 20.0], index=[f[0], f[2]])
    r = fx.retornos_del_carry(_constante(1.0, f), tasa, pd.Series([0.0], index=[f[0]]))
    assert r["diferencial"].tolist() == pytest.approx([10.0, 10.0, 20.0])
    assert r["total"].tolist() == pytest.approx([0.10 / 365, 0.10 / 365, 0.20 / 365])


def test_el_tramo_tambien_usa_la_tasa_de_eeuu_vigente_al_inicio():
    """La tasa de EEUU sube de 4 % a 8 % el día 3: el tramo que termina ese día todavía paga la del 4 %."""
    f = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    tasa_usd = pd.Series([4.0, 8.0], index=[f[0], f[2]])
    r = fx.retornos_del_carry(_constante(1.0, f), pd.Series([10.0], index=[f[0]]), tasa_usd)
    assert r["diferencial"].tolist() == pytest.approx([6.0, 6.0, 2.0])
    assert r["total"].tolist() == pytest.approx([0.06 / 365, 0.06 / 365, 0.02 / 365])


def test_en_un_ano_con_diferencial_constante_el_total_acumulado_es_el_diferencial_compuesto():
    f = pd.bdate_range("2024-01-01", "2025-01-01")
    r = fx.retornos_del_carry(_constante(1.0, f), pd.Series([10.0], index=[f[0]]), pd.Series([4.0], index=[f[0]]))
    dias = (f[-1] - f[0]).days
    assert (1 + r["total"]).prod() - 1 == pytest.approx(np.exp(0.06 * dias / 365) - 1, rel=2e-3)


def test_una_tasa_vencida_deja_ese_tramo_sin_retorno_en_vez_de_inventar_una_tasa():
    f = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"])
    tasa = pd.Series([10.0], index=[f[0]])  # publicada el 2 de enero y nunca más
    r = fx.retornos_del_carry(_constante(1.0, f), tasa, pd.Series([4.0], index=[f[0]]), antiguedad_maxima_moneda=2)
    # el tramo que termina el 4 usa la tasa del 3 (1 día: vigente); el que termina el 5 usa la del 4 (2 días: vigente);
    # el que termina el 8 usaría la del 5 (3 días > 2): vencida, así que ese tramo no tiene retorno
    assert list(r.index) == [f[1], f[2], f[3]]


def test_un_hueco_en_los_precios_no_se_convierte_en_meses_de_interes_supuesto():
    """Si faltan cinco meses de precios, el tramo que los une se descarta: no se le devengan 152 días con la tasa del primer día."""
    f = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-06-03", "2024-06-04"])
    r = fx.retornos_del_carry(_constante(1.0, f), pd.Series([10.0], index=[f[0]]), pd.Series([4.0], index=[f[0]]))
    assert list(r.index) == [f[1], f[3]]  # los dos tramos de un día; el de 152 días, no
    assert r["total"].max() < 0.001
    # con un tope más holgado el tramo largo vuelve a entrar y devenga lo que dice la fórmula
    largo = fx.retornos_del_carry(_constante(1.0, f), pd.Series([10.0], index=[f[0]]), pd.Series([4.0], index=[f[0]]), dias_maximos_por_tramo=400)
    assert largo.loc[f[2], "total"] == pytest.approx(0.06 * 152 / 365)


# ---------------------------------------------------------------------------
# estrategia_de_carry y cartera
# ---------------------------------------------------------------------------
def test_la_estrategia_compra_la_moneda_si_su_tasa_es_mayor_y_la_vende_si_es_menor():
    retornos = pd.DataFrame({"total": [0.01, 0.01, -0.02, 0.0], "diferencial": [5.0, -3.0, -3.0, 0.0]}, index=_fechas(4))
    e = fx.estrategia_de_carry(retornos)
    assert e["lado"].tolist() == [1.0, -1.0, -1.0, 0.0]
    assert e["retorno"].tolist() == pytest.approx([0.01, -0.01, 0.02, 0.0])  # la posición corta gana lo que pierde la larga


def test_una_estrategia_de_carry_con_el_diferencial_de_hoy_aplicado_al_pasado_seria_distinta_a_la_que_no_mira_el_futuro():
    """El lado de cada tramo es el del diferencial de ESE tramo (conocido al inicio), no el último del período."""
    f = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    tasa_m = pd.Series([10.0, 2.0], index=[f[0], f[2]])  # la tasa baja bajo la de EEUU a partir del día 3
    valor = pd.Series([1.0, 1.01, 1.02, 1.0], index=f)
    r = fx.retornos_del_carry(valor, tasa_m, pd.Series([4.0], index=[f[0]]))
    e = fx.estrategia_de_carry(r)
    assert e["lado"].tolist() == [1.0, 1.0, -1.0]  # larga mientras la tasa era mayor y corta cuando pasó a ser menor


def test_la_cartera_es_el_promedio_de_las_estrategias_con_dato_ese_dia():
    f = _fechas(3)
    df = pd.DataFrame({"A": [0.02, 0.02, np.nan], "B": [0.04, np.nan, np.nan], "C": [0.0, 0.01, 0.03]}, index=f)
    c = fx.cartera_de_igual_peso(df)
    assert c.tolist() == pytest.approx([0.02, 0.015, 0.03])


# ---------------------------------------------------------------------------
# estadisticas_de_retornos
# ---------------------------------------------------------------------------
def test_un_retorno_diario_constante_da_la_volatilidad_cero_y_el_acumulado_compuesto():
    f = pd.bdate_range("2024-01-01", periods=253)
    s = pd.Series(0.001, index=f)
    e = fx.estadisticas_de_retornos(s)
    assert e["retorno_total"] == pytest.approx((1.001**253 - 1) * 100)
    assert e["volatilidad"] == pytest.approx(0.0, abs=1e-9)
    assert e["caida_maxima"] == pytest.approx(0.0)
    assert e["meses_ganadores"] == 100.0
    assert e["peor_mes"] == pytest.approx((1.001**21 - 1) * 100)


def test_la_caida_maxima_se_mide_desde_el_maximo_previo():
    f = _fechas(40)
    r = pd.Series(0.0, index=f)
    r.iloc[9], r.iloc[14] = 0.10, -0.20  # sube 10 %, luego cae 20 %
    e = fx.estadisticas_de_retornos(r)
    assert e["caida_maxima"] == pytest.approx(-20.0)


def test_el_peor_mes_dice_cuanto_y_en_que_fecha_termina():
    f = pd.bdate_range("2024-01-01", periods=200)
    r = pd.Series(0.0005, index=f)
    r.iloc[100:121] = -0.01  # 21 ruedas seguidas de -1 %
    e = fx.estadisticas_de_retornos(r)
    assert e["peor_mes"] == pytest.approx((0.99**21 - 1) * 100)
    assert e["fecha_peor_mes"] == f[120]


def test_los_meses_ganadores_cuentan_meses_calendario_con_retorno_compuesto_positivo():
    f = pd.bdate_range("2024-01-01", "2024-04-30")
    r = pd.Series(0.001, index=f)
    r[(r.index.month == 2)] = -0.001  # febrero pierde; enero, marzo y abril ganan
    e = fx.estadisticas_de_retornos(r)
    assert e["meses_ganadores"] == pytest.approx(75.0)


def test_un_mes_sin_ganancia_ni_perdida_no_cuenta_como_mes_ganador():
    f = pd.bdate_range("2024-01-01", "2024-03-29")
    r = pd.Series(0.001, index=f)
    r[(r.index.month == 2)] = 0.0  # febrero queda plano
    e = fx.estadisticas_de_retornos(r)
    assert e["meses_ganadores"] == pytest.approx(200 / 3)  # enero y marzo ganan, febrero no


def test_la_ventana_de_dias_recorta_la_serie_y_con_pocos_datos_no_hay_estadisticas():
    f = pd.bdate_range("2022-01-01", periods=800)
    s = pd.Series(0.0005, index=f)
    corta, larga = fx.estadisticas_de_retornos(s, dias=365), fx.estadisticas_de_retornos(s)
    assert corta["dias"] < larga["dias"] and corta["desde"] >= f[-1] - pd.Timedelta(days=365)
    assert fx.estadisticas_de_retornos(s.head(10)) is None


def test_el_retorno_anualizado_es_geometrico_sobre_el_periodo_transcurrido():
    f = pd.bdate_range("2024-01-01", "2025-01-01")
    r = pd.Series((1.10 ** (1 / len(f))) - 1, index=f)  # 10 % compuesto en total
    e = fx.estadisticas_de_retornos(r)
    assert e["retorno_total"] == pytest.approx(10.0, abs=1e-9)
    # n retornos fechados al final de su tramo cubren n tramos: el lapso entre la primera y la última fecha, escalado por n/(n-1)
    transcurrido = (f[-1] - f[0]).days * len(f) / (len(f) - 1)
    assert e["anualizado"] == pytest.approx((1.10 ** (365.0 / transcurrido) - 1) * 100, rel=1e-9)
    # y es parecido al 10 % de un año (el período dura ~366 días)
    assert 9.9 < e["anualizado"] < 10.1


# ---------------------------------------------------------------------------
# resumen_del_carry
# ---------------------------------------------------------------------------
def test_el_resumen_separa_spot_y_carry_y_su_suma_es_el_total():
    f = pd.bdate_range("2024-01-01", periods=260)
    valor = pd.Series(np.linspace(1.0, 1.1, 260), index=f)
    r = fx.retornos_del_carry(valor, _constante(9.0, f), _constante(4.0, f))
    s = fx.resumen_del_carry(r, dias=10_000)
    assert s["spot"] == pytest.approx((valor.iloc[-1] / valor.iloc[0] - 1) * 100)
    assert s["spot"] + s["carry"] == pytest.approx(s["total"])
    assert s["carry"] > 0 and s["diferencial_actual"] == pytest.approx(5.0) and s["diferencial_promedio"] == pytest.approx(5.0)


def test_el_carry_sobre_riesgo_es_el_diferencial_actual_dividido_por_la_volatilidad_del_spot():
    f = pd.bdate_range("2024-01-01", periods=260)
    valor = pd.Series(1.0 + np.random.default_rng(1).normal(0, 0.003, 260).cumsum() * 0.1 + 1.0, index=f)
    r = fx.retornos_del_carry(valor, _constante(10.0, f), _constante(4.0, f))
    s = fx.resumen_del_carry(r, dias=10_000)
    assert s["carry_sobre_riesgo"] == pytest.approx(6.0 / s["volatilidad_spot"])
    assert s["volatilidad_spot"] == pytest.approx(r["spot"].std() * np.sqrt(252) * 100)


def test_el_carry_sobre_riesgo_usa_el_diferencial_de_hoy_y_no_el_promedio_cuando_estos_difieren():
    f = pd.bdate_range("2024-01-01", periods=260)
    valor = pd.Series(1.0 + np.random.default_rng(4).normal(0, 0.004, 260).cumsum() * 0.1 + 1.0, index=f)
    tasa = pd.Series([12.0, 6.0], index=[f[0], f[200]])  # el diferencial baja de 8 a 2 puntos a mitad de camino
    r = fx.retornos_del_carry(valor, tasa, _constante(4.0, f))
    s = fx.resumen_del_carry(r, dias=10_000)
    assert s["diferencial_actual"] == pytest.approx(2.0) and s["diferencial_promedio"] > 4.0
    assert s["carry_sobre_riesgo"] == pytest.approx(2.0 / s["volatilidad_spot"])


def test_el_resumen_usa_el_ultimo_diferencial_como_actual_y_el_promedio_del_periodo():
    f = pd.bdate_range("2024-01-01", periods=100)
    tasa = pd.Series([10.0, 2.0], index=[f[0], f[60]])  # 10 % los primeros 60 días y 2 % después
    r = fx.retornos_del_carry(_constante(1.0, f), tasa, _constante(4.0, f))
    s = fx.resumen_del_carry(r, dias=10_000)
    assert s["diferencial_actual"] == pytest.approx(-2.0)
    assert 0 < s["diferencial_promedio"] < 6.0


def test_el_resumen_del_carry_sin_datos_suficientes_es_none():
    f = _fechas(10)
    r = fx.retornos_del_carry(_constante(1.0, f), _constante(5.0, f), _constante(1.0, f))
    assert fx.resumen_del_carry(r) is None


# ---------------------------------------------------------------------------
# resumen_de_par y correlacion_movil
# ---------------------------------------------------------------------------
def test_el_resumen_de_un_par_trae_cambios_volatilidad_y_rango_del_ultimo_anio():
    f = pd.bdate_range("2023-01-02", periods=500)
    precios = pd.Series(np.concatenate([np.linspace(100, 200, 250), np.linspace(200, 150, 250)]), index=f)
    r = fx.resumen_de_par(precios, precios)
    ultimo_anio = precios[precios.index >= precios.index[-1] - pd.Timedelta(days=365)]
    assert r["Rango 1 año (%)"] == pytest.approx((ultimo_anio.max() / ultimo_anio.min() - 1) * 100)
    assert r["1D %"] == pytest.approx((precios.iloc[-1] / precios.iloc[-2] - 1) * 100)
    assert r["ultima_fecha"] == f[-1] and r["Volatilidad (%)"] > 0
    assert r["Correlación vs referencia"] == pytest.approx(1.0)


def test_el_rango_no_depende_de_la_direccion_de_la_cotizacion():
    """Si se invierte el par (USD/JPY a JPY/USD), el rango % cambia de signo en el retorno pero el movimiento es el mismo orden de magnitud."""
    f = pd.bdate_range("2024-01-01", periods=300)
    precios = pd.Series(100 + np.sin(np.arange(300) / 20) * 10, index=f)
    directo, invertido = fx.resumen_de_par(precios, precios)["Rango 1 año (%)"], fx.resumen_de_par(1 / precios, 1 / precios)["Rango 1 año (%)"]
    assert directo == pytest.approx(invertido)  # (max/min - 1) es el mismo número al invertir el precio


def test_la_correlacion_con_la_referencia_es_negativa_para_un_par_invertido_y_none_sin_referencia():
    f = pd.bdate_range("2024-01-01", periods=300)
    precios = pd.Series(100 * np.exp(np.random.default_rng(2).normal(0, 0.005, 300).cumsum()), index=f)
    assert fx.resumen_de_par(1 / precios, precios)["Correlación vs referencia"] < -0.95
    assert fx.resumen_de_par(precios, pd.Series(dtype=float))["Correlación vs referencia"] is None


def test_un_par_con_menos_de_dos_precios_no_tiene_resumen():
    assert fx.resumen_de_par(pd.Series([1.0], index=pd.to_datetime(["2024-01-02"])), pd.Series(dtype=float)) is None


def test_la_correlacion_movil_ve_el_cambio_de_relacion_entre_dos_series():
    f = pd.bdate_range("2023-01-02", periods=600)
    a = pd.Series(100 * np.exp(np.random.default_rng(5).normal(0, 0.01, 600).cumsum()), index=f)
    retornos = a.pct_change().fillna(0)
    # b copia a durante los primeros 300 días y es su opuesto después
    retornos_b = pd.Series(np.concatenate([retornos.values[:300], -retornos.values[300:]]), index=f)
    b = 100 * (1 + retornos_b).cumprod()
    m = fx.correlacion_movil(a, b, ventana=100)
    assert m.loc[f[250]] == pytest.approx(1.0, abs=0.01)
    assert m.loc[f[500]] == pytest.approx(-1.0, abs=0.01)
    assert len(m) == len(f) - 1 - 99  # una ventana de 100 retornos necesita 100 datos


def test_el_motor_no_depende_de_streamlit_ni_calcula_correlaciones_con_la_bolsa():
    codigo = open(os.path.join(os.path.dirname(__file__), "..", "fx_carry.py"), encoding="utf-8").read()
    assert "import streamlit" not in codigo
    # por diseño (ver el docstring del módulo) ninguna función recibe la bolsa ni el índice dólar
    assert "precios_dxy" not in codigo and "precios_mercado" not in codigo and "retornos_mercado" not in codigo
