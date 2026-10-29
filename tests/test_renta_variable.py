"""Pruebas del motor de «Renta Variable y ETFs» (renta_variable.py) con series sintéticas de respuesta conocida.

Cada prueba arma precios cuya respuesta se sabe de antemano (un ETF que se mueve exactamente el doble que el
mercado tiene beta 2; uno que se mueve al revés, correlación -1), de modo que un error de fórmula no pueda pasar
inadvertido. Los datos reales se prueban aparte, en test_renta_variable_seccion.py.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pytest

import renta_fija as rf
import renta_variable as rv


def _precios(retornos: np.ndarray, inicio: str = "2024-01-01", base: float = 100.0) -> pd.Series:
    """Serie de precios que parte de `base` y sigue exactamente esos retornos diarios (días hábiles)."""
    fechas = pd.bdate_range(inicio, periods=len(retornos) + 1)
    return pd.Series(base * np.concatenate([[1.0], np.cumprod(1 + retornos)]), index=fechas)


@pytest.fixture
def retornos_mercado() -> np.ndarray:
    return np.random.default_rng(7).normal(0.0004, 0.01, 400)


# ---------------------------------------------------------------------------
# correlacion_contra
# ---------------------------------------------------------------------------
def test_la_correlacion_de_una_serie_consigo_misma_es_1_y_con_su_opuesta_es_menos_1(retornos_mercado):
    mercado = _precios(retornos_mercado).pct_change().dropna()
    assert rv.correlacion_contra(mercado, mercado) == pytest.approx(1.0)
    assert rv.correlacion_contra(-mercado, mercado) == pytest.approx(-1.0)


def test_la_correlacion_no_cambia_si_se_escala_la_serie(retornos_mercado):
    mercado = _precios(retornos_mercado).pct_change().dropna()
    assert rv.correlacion_contra(mercado * 3.0, mercado) == pytest.approx(1.0)


def test_la_correlacion_sin_datos_suficientes_o_sin_variacion_es_none(retornos_mercado):
    mercado = _precios(retornos_mercado).pct_change().dropna()
    assert rv.correlacion_contra(mercado.head(10), mercado.head(10)) is None
    constante = pd.Series(0.001, index=mercado.index)
    assert rv.correlacion_contra(constante, mercado) is None  # el ETF no se mueve
    assert rv.correlacion_contra(mercado, constante) is None  # el mercado no se mueve


def test_la_correlacion_solo_usa_las_fechas_en_comun(retornos_mercado):
    mercado = _precios(retornos_mercado).pct_change().dropna()
    otra = mercado.iloc[100:]  # mismos valores, pero solo desde el día 100
    assert rv.correlacion_contra(otra, mercado) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# resumen_de_etf
# ---------------------------------------------------------------------------
def test_un_etf_que_se_mueve_el_doble_que_el_mercado_tiene_beta_2_y_correlacion_1(retornos_mercado):
    mercado = _precios(retornos_mercado)
    etf = _precios(2 * retornos_mercado)
    r = rv.resumen_de_etf(etf, mercado, 4.0)
    assert r["Beta vs S&P 500"] == pytest.approx(2.0)
    assert r["Correlación vs S&P 500"] == pytest.approx(1.0)


def test_un_etf_que_se_mueve_al_reves_tiene_beta_y_correlacion_negativas(retornos_mercado):
    r = rv.resumen_de_etf(_precios(-retornos_mercado), _precios(retornos_mercado), 4.0)
    assert r["Beta vs S&P 500"] == pytest.approx(-1.0)
    assert r["Correlación vs S&P 500"] == pytest.approx(-1.0)


def test_el_retorno_relativo_es_el_del_etf_menos_el_del_mercado_en_puntos(retornos_mercado):
    mercado = _precios(retornos_mercado)
    etf = _precios(2 * retornos_mercado)
    r = rv.resumen_de_etf(etf, mercado, 4.0)
    esperado = rf.retorno_ultimo_anio(etf) - rf.retorno_ultimo_anio(mercado)
    assert r["Vs S&P 500 (pp)"] == pytest.approx(esperado)
    assert r["Retorno 1 año (%)"] == pytest.approx(rf.retorno_ultimo_anio(etf))
    # el mercado contra sí mismo no gana ni pierde
    assert rv.resumen_de_etf(mercado, mercado, 4.0)["Vs S&P 500 (pp)"] == pytest.approx(0.0)


def test_el_sharpe_es_el_retorno_menos_la_tasa_libre_dividido_por_la_volatilidad(retornos_mercado):
    etf = _precios(retornos_mercado)
    r = rv.resumen_de_etf(etf, etf, 4.0)
    esperado = (r["Retorno 1 año (%)"] - 4.0) / r["Volatilidad (%)"]
    assert r["Sharpe"] == pytest.approx(esperado)
    # sin tasa libre de riesgo no se inventa un Sharpe
    assert rv.resumen_de_etf(etf, etf, None)["Sharpe"] is None


def test_el_resumen_trae_los_cambios_por_periodo_la_ultima_fecha_y_no_trae_duracion(retornos_mercado):
    etf = _precios(retornos_mercado)
    r = rv.resumen_de_etf(etf, etf, 4.0)
    assert {"1D %", "1W %", "1M %", "YTD %"} <= set(r)
    assert r["1D %"] == pytest.approx((etf.iloc[-1] / etf.iloc[-2] - 1) * 100)
    assert r["ultima_fecha"] == etf.index[-1]
    assert not any("uración" in clave for clave in r)
    assert r["Caída máxima 1 año (%)"] <= 0


def test_sin_dos_precios_no_hay_resumen_y_sin_mercado_no_se_inventa_el_beta(retornos_mercado):
    assert rv.resumen_de_etf(pd.Series([100.0], index=pd.to_datetime(["2024-01-02"])), pd.Series(dtype=float), 4.0) is None
    r = rv.resumen_de_etf(_precios(retornos_mercado), pd.Series(dtype=float), 4.0)
    assert r["Beta vs S&P 500"] is None and r["Correlación vs S&P 500"] is None and r["Vs S&P 500 (pp)"] is None
    assert r["Volatilidad (%)"] is not None  # lo que no depende del mercado sí se calcula


def test_el_beta_y_la_correlacion_usan_solo_el_ultimo_anio(retornos_mercado):
    """Si hasta hace más de un año el ETF iba al revés y desde entonces va igual, el resumen mira solo lo último.

    «Último año» son 365 días corridos (unos 261 hábiles): el cambio de comportamiento se pone 300 días atrás, fuera de la ventana."""
    retornos_etf = np.concatenate([-retornos_mercado[:-300], retornos_mercado[-300:]])
    r = rv.resumen_de_etf(_precios(retornos_etf), _precios(retornos_mercado), 4.0)
    assert r["Beta vs S&P 500"] == pytest.approx(1.0)
    assert r["Correlación vs S&P 500"] == pytest.approx(1.0)
    # con toda la historia, en cambio, el tramo invertido arrastraría ambos números
    completo = pd.concat([_precios(retornos_etf).pct_change(), _precios(retornos_mercado).pct_change()], axis=1).dropna()
    assert completo.iloc[:, 0].corr(completo.iloc[:, 1]) < 0.7


# ---------------------------------------------------------------------------
# matriz_de_correlacion
# ---------------------------------------------------------------------------
def test_la_matriz_es_simetrica_con_unos_en_la_diagonal_y_refleja_pares_conocidos(retornos_mercado):
    precios = pd.DataFrame({
        "A": _precios(retornos_mercado), "B": _precios(retornos_mercado * 2), "C": _precios(-retornos_mercado),
    })
    m = rv.matriz_de_correlacion(precios)
    assert list(m.columns) == ["A", "B", "C"] and list(m.index) == ["A", "B", "C"]
    assert np.allclose(np.diag(m.values), 1.0)
    assert np.allclose(m.values, m.values.T)
    assert m.loc["A", "B"] == pytest.approx(1.0)
    assert m.loc["A", "C"] == pytest.approx(-1.0)


def test_la_ventana_de_dias_restringe_el_calculo_a_lo_reciente(retornos_mercado):
    """Primero B va igual que A y en los últimos ~100 días va al revés: la ventana corta tiene que ver el -1."""
    retornos_b = np.concatenate([retornos_mercado[:-100], -retornos_mercado[-100:]])
    precios = pd.DataFrame({"A": _precios(retornos_mercado), "B": _precios(retornos_b)})
    corta = rv.matriz_de_correlacion(precios, dias=100)
    completa = rv.matriz_de_correlacion(precios, dias=None)
    assert corta.loc["A", "B"] == pytest.approx(-1.0, abs=0.05)
    assert completa.loc["A", "B"] > 0.3  # con todo el historial pesan los 300 días en que iban juntos


def test_la_matriz_solo_cuenta_los_dias_en_que_todos_tienen_dato(retornos_mercado):
    a, b = _precios(retornos_mercado), _precios(retornos_mercado)
    b = b.iloc[150:]  # B arranca mucho después
    m = rv.matriz_de_correlacion(pd.DataFrame({"A": a, "B": b}))
    assert m.loc["A", "B"] == pytest.approx(1.0)


def test_cada_par_se_mide_en_los_mismos_dias_para_todos_los_etfs_de_la_matriz(retornos_mercado):
    """B va igual que A los primeros 200 días y al revés después; C solo existe en esos últimos días.
    En la matriz, A-B se mide solo donde C también tiene dato (-1); calculado por separado, mezclaría los dos tramos."""
    n = len(retornos_mercado)
    retornos_b = np.concatenate([retornos_mercado[:200], -retornos_mercado[200:]])
    a, b = _precios(retornos_mercado), _precios(retornos_b)
    c = _precios(retornos_mercado[200:], inicio=str(a.index[200].date()))
    precios = pd.DataFrame({"A": a, "B": b, "C": c})
    por_separado = rv.matriz_de_correlacion(precios[["A", "B"]])
    juntos = rv.matriz_de_correlacion(precios)
    assert juntos.loc["A", "B"] == pytest.approx(-1.0, abs=0.01)
    assert por_separado.loc["A", "B"] > -0.5  # sin C en la matriz, se mezclan el tramo +1 y el tramo -1


def test_con_pocos_dias_en_comun_la_matriz_esta_vacia(retornos_mercado):
    precios = pd.DataFrame({"A": _precios(retornos_mercado[:10]), "B": _precios(retornos_mercado[:10])})
    assert rv.matriz_de_correlacion(precios).empty


# ---------------------------------------------------------------------------
# comparar_con_indice
# ---------------------------------------------------------------------------
def test_un_etf_identico_al_indice_tiene_diferencia_cero_correlacion_1_y_error_cero(retornos_mercado):
    indice = _precios(retornos_mercado)
    c = rv.comparar_con_indice(indice, indice)
    assert c["diferencia"] == pytest.approx(0.0)
    assert c["correlacion"] == pytest.approx(1.0)
    assert c["error_de_seguimiento"] == pytest.approx(0.0, abs=1e-9)


def test_un_etf_que_suma_dividendos_gana_la_diferencia_y_el_error_de_seguimiento_mide_el_ruido(retornos_mercado):
    """El ETF rinde cada día lo del índice más ±0,05 % alternado: la diferencia diaria es ese ruido, de desviación conocida."""
    indice = _precios(retornos_mercado)
    ruido = np.where(np.arange(len(retornos_mercado)) % 2 == 0, 0.0005, -0.0005)
    etf = _precios(retornos_mercado + ruido)
    c = rv.comparar_con_indice(etf, indice, dias=10_000)  # toda la historia
    ventana = pd.concat([etf, indice], axis=1, keys=["e", "i"]).pct_change().dropna()
    esperado = (ventana["e"] - ventana["i"]).std() * np.sqrt(252) * 100
    assert c["error_de_seguimiento"] == pytest.approx(esperado)
    assert c["error_de_seguimiento"] == pytest.approx(0.0005 * np.sqrt(252) * 100, rel=0.01)
    assert c["retorno_etf"] == pytest.approx((etf.iloc[-1] / etf.iloc[0] - 1) * 100)
    assert c["retorno_indice"] == pytest.approx((indice.iloc[-1] / indice.iloc[0] - 1) * 100)
    assert c["diferencia"] == pytest.approx(c["retorno_etf"] - c["retorno_indice"])
    assert c["correlacion"] > 0.99


def test_la_correlacion_del_seguimiento_es_de_los_retornos_diarios_y_no_de_los_niveles_de_precio():
    """Dos series que solo suben juntas tienen niveles casi idénticos, pero sus días no se parecen: no replican nada."""
    rng = np.random.default_rng(3)
    indice = _precios(0.005 + rng.normal(0, 0.002, 300))
    otro = _precios(0.005 + rng.normal(0, 0.002, 300))
    assert indice.corr(otro) > 0.95  # los niveles se parecen porque ambos suben
    c = rv.comparar_con_indice(otro, indice, dias=10_000)
    assert abs(c["correlacion"]) < 0.3
    assert c["error_de_seguimiento"] > 2  # y el error de seguimiento lo dice


def test_la_comparacion_respeta_la_ventana_de_dias(retornos_mercado):
    indice = _precios(retornos_mercado)
    c = rv.comparar_con_indice(indice, indice, dias=365)
    assert c["hasta"] == indice.index[-1]
    assert c["desde"] >= indice.index[-1] - pd.Timedelta(days=365)
    assert c["desde"] < indice.index[-1] - pd.Timedelta(days=350)
    assert c["dias"] == len(indice[indice.index >= c["desde"]])
    # con la historia entera hay más días
    assert rv.comparar_con_indice(indice, indice, dias=10_000)["dias"] > c["dias"]


def test_la_comparacion_sin_historia_comun_suficiente_es_none(retornos_mercado):
    indice = _precios(retornos_mercado)
    assert rv.comparar_con_indice(indice.head(10), indice.head(10)) is None
    lejano = _precios(retornos_mercado[:60], inicio="2020-01-01")  # no coincide en fechas con el índice
    assert rv.comparar_con_indice(lejano, indice) is None


def test_el_motor_no_depende_de_streamlit():
    codigo = open(os.path.join(os.path.dirname(__file__), "..", "renta_variable.py"), encoding="utf-8").read()
    assert "import streamlit" not in codigo
