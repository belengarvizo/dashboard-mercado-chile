"""Pruebas del motor de renta fija (renta_fija.py).

Cada resultado se compara contra algo INDEPENDIENTE del código que se prueba:
una suma hecha a mano, una fórmula cerrada conocida (bono a la par, cero
cupón) o una derivada numérica por diferencias finitas. Así, si la fórmula del
motor tuviera un error, la prueba lo notaría en vez de repetirlo.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pytest

import renta_fija as rf

PLAZOS = [1 / 12, 3 / 12, 6 / 12, 1, 2, 3, 5, 7, 10, 20, 30]
CURVA_PLANA = pd.Series(0.04, index=PLAZOS)
CURVA_NORMAL = pd.Series([0.030, 0.032, 0.034, 0.036, 0.038, 0.040, 0.042, 0.044, 0.046, 0.050, 0.052], index=PLAZOS)
CURVA_INVERTIDA = pd.Series(list(reversed(CURVA_NORMAL.tolist())), index=PLAZOS)


# ---------------------------------------------------------------------------
# Flujos y precio
# ---------------------------------------------------------------------------
def test_los_flujos_son_cupones_mas_el_capital_al_final():
    f = rf.flujos_de_bono(100, 0.06, 2, 2)  # 2 años, semestral: 4 cupones de 3
    assert f["periodo"].tolist() == [1, 2, 3, 4]
    assert f["anios"].tolist() == [0.5, 1.0, 1.5, 2.0]
    assert f["flujo"].tolist() == [3.0, 3.0, 3.0, 103.0]


def test_el_precio_coincide_con_la_suma_hecha_a_mano():
    a_mano = 5 / 1.06 + 5 / 1.06**2 + 105 / 1.06**3
    assert rf.precio(100, 0.05, 3, 1, 0.06) == pytest.approx(a_mano, rel=1e-12)
    assert rf.precio(100, 0.05, 3, 1, 0.06) == pytest.approx(97.3269, abs=1e-3)  # valor conocido, a 4 decimales


def test_un_bono_con_cupon_igual_a_la_tasa_vale_su_nominal():
    for anios, frec in [(10, 2), (5, 1), (3, 4), (30, 2)]:
        assert rf.precio(100, 0.05, anios, frec, 0.05) == pytest.approx(100.0, abs=1e-9)
    assert rf.precio(1_000_000, 0.07, 8, 2, 0.07) == pytest.approx(1_000_000, abs=1e-5)


def test_premio_y_descuento():
    assert rf.precio(100, 0.06, 10, 2, 0.04) > 100  # cupón mayor que la tasa: sobre la par
    assert rf.precio(100, 0.03, 10, 2, 0.04) < 100  # cupón menor que la tasa: bajo la par


def test_el_precio_baja_cuando_sube_la_tasa():
    precios = [rf.precio(100, 0.05, 10, 2, y) for y in np.linspace(0.0, 0.2, 41)]
    assert all(a > b for a, b in zip(precios, precios[1:]))


def test_cero_cupon_tiene_formula_cerrada():
    # 100 / (1 + y/m)^(m·N)
    assert rf.precio(100, 0.0, 5, 2, 0.06) == pytest.approx(100 / 1.03**10, rel=1e-12)


def test_la_tabla_de_valorizacion_suma_el_precio():
    t = rf.tabla_de_valorizacion(100, 0.05, 10, 2, 0.045)
    assert t["valor_presente"].sum() == pytest.approx(rf.precio(100, 0.05, 10, 2, 0.045), rel=1e-12)
    assert len(t) == 20
    assert (t["factor_descuento"].diff().dropna() < 0).all()  # el futuro vale cada vez menos


def test_entradas_invalidas_se_rechazan():
    with pytest.raises(ValueError):
        rf.precio(100, 0.05, 10, 3, 0.05)       # frecuencia no soportada
    with pytest.raises(ValueError):
        rf.precio(100, 0.05, 10.3, 2, 0.05)     # 10,3 años no son semestres enteros
    with pytest.raises(ValueError):
        rf.precio(0, 0.05, 10, 2, 0.05)         # nominal cero
    with pytest.raises(ValueError):
        rf.precio(100, -0.01, 10, 2, 0.05)      # cupón negativo
    with pytest.raises(ValueError):
        rf.precio(100, 0.05, 10, 2, -2.5)       # tasa por período <= -100 %


# ---------------------------------------------------------------------------
# Tasa al vencimiento
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cupon,anios,frec,y", [
    (0.05, 10, 2, 0.04), (0.08, 3, 1, 0.12), (0.0, 7, 2, 0.05), (0.03, 30, 4, 0.002), (0.10, 2, 2, 0.35),
])
def test_ida_y_vuelta_precio_a_tasa(cupon, anios, frec, y):
    p = rf.precio(100, cupon, anios, frec, y)
    assert rf.tasa_al_vencimiento(p, 100, cupon, anios, frec) == pytest.approx(y, abs=1e-10)


def test_a_la_par_la_tasa_es_el_cupon():
    assert rf.tasa_al_vencimiento(100, 100, 0.055, 10, 2) == pytest.approx(0.055, abs=1e-10)


def test_un_precio_imposible_se_rechaza():
    with pytest.raises(ValueError):
        rf.tasa_al_vencimiento(-5, 100, 0.05, 10, 2)
    with pytest.raises(ValueError):
        rf.tasa_al_vencimiento(1e9, 100, 0.05, 10, 2)  # ni a tasa -50 % vale tanto


def test_rendimiento_corriente():
    assert rf.rendimiento_corriente(95, 100, 0.05) == pytest.approx(5 / 95)


# ---------------------------------------------------------------------------
# Duración y convexidad
# ---------------------------------------------------------------------------
def test_la_duracion_de_un_cero_cupon_es_su_plazo():
    m = rf.metricas_de_riesgo(100, 0.0, 7, 2, 0.05)
    assert m["macaulay"] == pytest.approx(7.0, abs=1e-12)


def test_duracion_de_un_bono_anual_a_la_par_tiene_formula_cerrada():
    # D_mac = (1 + y)/y · (1 − 1/(1 + y)^N)
    y, n = 0.05, 10
    esperado = (1 + y) / y * (1 - 1 / (1 + y) ** n)
    m = rf.metricas_de_riesgo(100, y, n, 1, y)
    assert m["macaulay"] == pytest.approx(esperado, rel=1e-12)
    assert m["modificada"] == pytest.approx(esperado / (1 + y), rel=1e-12)


def test_la_duracion_modificada_es_macaulay_sobre_uno_mas_tasa_por_periodo():
    m = rf.metricas_de_riesgo(100, 0.06, 5, 2, 0.04)
    assert m["modificada"] == pytest.approx(m["macaulay"] / (1 + 0.04 / 2), rel=1e-12)


def test_mas_cupon_menos_duracion_y_mas_plazo_mas_duracion():
    assert rf.metricas_de_riesgo(100, 0.08, 10, 2, 0.05)["macaulay"] < rf.metricas_de_riesgo(100, 0.02, 10, 2, 0.05)["macaulay"]
    assert rf.metricas_de_riesgo(100, 0.05, 20, 2, 0.05)["macaulay"] > rf.metricas_de_riesgo(100, 0.05, 5, 2, 0.05)["macaulay"]


def test_el_dv01_coincide_con_el_cambio_real_de_precio_por_un_punto_base():
    y, h = 0.045, rf.PUNTO_BASE
    m = rf.metricas_de_riesgo(100, 0.05, 10, 2, y)
    cambio_real = (rf.precio(100, 0.05, 10, 2, y + h) - rf.precio(100, 0.05, 10, 2, y - h)) / 2
    assert -cambio_real == pytest.approx(m["dv01"], rel=1e-5)


def test_la_convexidad_coincide_con_la_segunda_derivada_numerica():
    y, h = 0.045, 1e-3
    p0 = rf.precio(100, 0.05, 10, 2, y)
    segunda = (rf.precio(100, 0.05, 10, 2, y + h) + rf.precio(100, 0.05, 10, 2, y - h) - 2 * p0) / h**2
    assert rf.metricas_de_riesgo(100, 0.05, 10, 2, y)["convexidad"] == pytest.approx(segunda / p0, rel=1e-4)


def test_con_duracion_y_convexidad_el_error_es_menor_que_solo_con_duracion():
    y = 0.045
    m = rf.metricas_de_riesgo(100, 0.05, 10, 2, y)
    for dy in (-0.02, -0.01, 0.01, 0.02):
        real = rf.precio(100, 0.05, 10, 2, y + dy) - m["precio"]
        aprox = rf.aproximar_cambio_de_precio(m["precio"], m["modificada"], m["convexidad"], dy)
        assert abs(aprox["duracion_y_convexidad"] - real) < abs(aprox["solo_duracion"] - real)


def test_la_convexidad_hace_que_se_gane_mas_de_lo_que_se_pierde():
    """Con la misma magnitud de shock, la baja de tasas sube el precio más de lo que la alza lo baja."""
    y = 0.045
    p0 = rf.precio(100, 0.05, 10, 2, y)
    sube_tasa = rf.precio(100, 0.05, 10, 2, y + 0.02) - p0
    baja_tasa = rf.precio(100, 0.05, 10, 2, y - 0.02) - p0
    assert sube_tasa < 0 < baja_tasa
    assert baja_tasa > -sube_tasa


def test_un_shock_chico_es_casi_exacto():
    m = rf.metricas_de_riesgo(100, 0.05, 10, 2, 0.045)
    real = rf.precio(100, 0.05, 10, 2, 0.0451) - m["precio"]
    aprox = rf.aproximar_cambio_de_precio(m["precio"], m["modificada"], m["convexidad"], 0.0001)["duracion_y_convexidad"]
    assert aprox == pytest.approx(real, rel=1e-4)


def test_descomponer_retorno_suma_sus_partes_y_aproxima_el_cambio_real():
    m = rf.metricas_de_riesgo(100, 0.05, 10, 2, 0.045)
    d = rf.descomponer_retorno(0.045, 0.005, m["modificada"], m["convexidad"], horizonte=1.0)
    assert d["total"] == pytest.approx(d["carry"] + d["efecto_duracion"] + d["efecto_convexidad"], rel=1e-12)
    assert d["carry"] == pytest.approx(0.045)
    assert d["efecto_duracion"] < 0 < d["efecto_convexidad"]  # sube la tasa: pierdes por duración, ganas un poco por convexidad
    real_precio = rf.precio(100, 0.05, 10, 2, 0.045 + 0.005) / m["precio"] - 1
    assert d["efecto_duracion"] + d["efecto_convexidad"] == pytest.approx(real_precio, abs=2e-4)


# ---------------------------------------------------------------------------
# Curva de tasas
# ---------------------------------------------------------------------------
def test_la_interpolacion_es_exacta_en_los_nodos_y_lineal_entre_ellos():
    for plazo in PLAZOS:
        assert rf.interpolar_tasa(CURVA_NORMAL, plazo) == pytest.approx(CURVA_NORMAL[plazo])
    medio = rf.interpolar_tasa(CURVA_NORMAL, 4)  # entre 3 y 5 años
    assert medio == pytest.approx((CURVA_NORMAL[3] + CURVA_NORMAL[5]) / 2)


def test_interpolar_fuera_de_la_curva_se_rechaza():
    with pytest.raises(ValueError):
        rf.interpolar_tasa(CURVA_NORMAL, 31)
    with pytest.raises(ValueError):
        rf.interpolar_tasa(CURVA_NORMAL, 0.01)


def test_curva_en_fecha_usa_la_ultima_curva_completa_disponible():
    pivote = pd.DataFrame(
        {1: [1.0, 2.0, 3.0, np.nan], 2: [1.5, 2.5, np.nan, 4.5]},
        index=pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]),
    )
    fecha, curva = rf.curva_en_fecha(pivote, "2026-01-08")
    assert fecha == pd.Timestamp("2026-01-06")  # el 7 y el 8 están incompletos
    assert curva.tolist() == [2.0, 2.5]
    fecha, _ = rf.curva_en_fecha(pivote, "2026-01-05")
    assert fecha == pd.Timestamp("2026-01-05")
    with pytest.raises(ValueError):
        rf.curva_en_fecha(pivote, "2025-12-31")


def test_el_bono_a_la_par_vale_100():
    b = rf.bono_a_la_par(CURVA_NORMAL, 5)
    assert b["precio"] == pytest.approx(100.0, abs=1e-9)
    assert b["tasa"] == pytest.approx(0.042)


def test_rodar_en_una_curva_plana_solo_da_carry():
    r = rf.rodar_en_la_curva(CURVA_PLANA, 5, 1)
    assert r["precio_venta"] == pytest.approx(100.0, abs=1e-9)
    assert r["efecto_precio"] == pytest.approx(0.0, abs=1e-12)
    assert r["retorno_total"] == pytest.approx(0.04, abs=1e-12)


def test_rodar_gana_extra_con_pendiente_positiva_y_pierde_con_curva_invertida():
    normal = rf.rodar_en_la_curva(CURVA_NORMAL, 5, 1)
    assert normal["efecto_precio"] > 0
    assert normal["retorno_total"] > normal["carry"]
    invertida = rf.rodar_en_la_curva(CURVA_INVERTIDA, 5, 1)
    assert invertida["efecto_precio"] < 0
    assert invertida["retorno_total"] < invertida["carry"]


def test_rodar_calza_con_el_calculo_a_mano():
    # 5 años a 4,2 %, se vende a los 2 años con 3 años restantes a 4,0 % (curva normal)
    r = rf.rodar_en_la_curva(CURVA_NORMAL, 5, 2)
    p3 = rf.precio(100, 0.042, 3, 2, 0.040)
    assert r["precio_venta"] == pytest.approx(p3, rel=1e-12)
    assert r["retorno_total"] == pytest.approx((p3 + 100 * 0.042 * 2) / 100 - 1, rel=1e-12)
    assert r["retorno_anualizado"] == pytest.approx((1 + r["retorno_total"]) ** 0.5 - 1, rel=1e-12)


def test_rodar_rechaza_horizontes_imposibles():
    with pytest.raises(ValueError):
        rf.rodar_en_la_curva(CURVA_NORMAL, 5, 5)
    with pytest.raises(ValueError):
        rf.rodar_en_la_curva(CURVA_NORMAL, 5, 0.3)


# ---------------------------------------------------------------------------
# Curva de descuento: cuánto vale hoy 1 peso futuro, a partir de la curva
# ---------------------------------------------------------------------------
def test_con_curva_plana_los_factores_tienen_formula_cerrada():
    d = rf.curva_de_descuento(CURVA_PLANA, 10)
    n = np.arange(1, 21)
    assert d["anios"].tolist() == [k / 2 for k in n]
    assert d["factor"].to_numpy() == pytest.approx((1 + 0.04 / 2) ** -n, rel=1e-12)
    assert d["tasa_cero"].to_numpy() == pytest.approx(np.full(20, 0.04), abs=1e-12)


def test_los_factores_revaloran_a_100_cada_bono_a_la_par_de_una_curva_con_pendiente():
    """Prueba de consistencia: con los factores obtenidos, TODO bono a la par de la curva vale exactamente 100."""
    d = rf.curva_de_descuento(CURVA_NORMAL, 30)
    for n in (1, 2, 6, 10, 20, 40, 60):
        cupon = d["tasa_par"].iloc[n - 1] / 2 * 100
        valor = cupon * d["factor"].iloc[:n].sum() + 100 * d["factor"].iloc[n - 1]
        assert valor == pytest.approx(100.0, abs=1e-9), f"bono a la par de {n / 2} años"


def test_los_factores_bajan_con_el_plazo_y_la_tasa_cero_sigue_a_la_par_con_pendiente_positiva():
    d = rf.curva_de_descuento(CURVA_NORMAL, 30)
    assert (d["factor"].diff().dropna() < 0).all()
    assert 0 < d["factor"].iloc[-1] < d["factor"].iloc[0] < 1
    # con una curva que sube, la tasa cero queda por encima de la tasa par a los plazos largos
    assert d["tasa_cero"].iloc[-1] > d["tasa_par"].iloc[-1]


def test_la_curva_de_descuento_rechaza_plazos_fuera_de_la_curva():
    with pytest.raises(ValueError):
        rf.curva_de_descuento(CURVA_NORMAL, 31)


# ---------------------------------------------------------------------------
# Un bono comprado a la par con la tasa de ayer, valorizado con la tasa de hoy
# ---------------------------------------------------------------------------
def test_si_la_tasa_no_cambio_el_bono_vale_100_y_solo_hubo_cupones():
    r = rf.bono_a_la_par_hoy(0.04, 10, 1, 0.04)
    assert r["precio_hoy"] == pytest.approx(100.0, abs=1e-9)
    assert r["efecto_precio"] == pytest.approx(0.0, abs=1e-12)
    assert r["retorno_total"] == pytest.approx(0.04, abs=1e-12)


def test_si_la_tasa_subio_el_precio_cae_y_el_retorno_suma_los_cupones():
    r = rf.bono_a_la_par_hoy(0.04, 10, 1, 0.05)
    esperado = rf.precio(100, 0.04, 9, 2, 0.05)
    assert r["precio_hoy"] == pytest.approx(esperado, rel=1e-12) and r["precio_hoy"] < 100
    assert r["retorno_total"] == pytest.approx((esperado - 100) / 100 + 0.04, rel=1e-12)
    assert rf.bono_a_la_par_hoy(0.04, 10, 1, 0.03)["precio_hoy"] > 100  # si la tasa bajó, sube


def test_bono_a_la_par_hoy_rechaza_tiempos_imposibles():
    with pytest.raises(ValueError):
        rf.bono_a_la_par_hoy(0.04, 5, 5, 0.04)
    with pytest.raises(ValueError):
        rf.bono_a_la_par_hoy(0.04, 5, 0.3, 0.04)


# ---------------------------------------------------------------------------
# Métricas de un instrumento real a partir de su serie de precios
# ---------------------------------------------------------------------------
def _dias(inicio, n):
    return pd.bdate_range(inicio, periods=n)


def test_cambios_por_periodo_con_crecimiento_constante():
    # La serie parte en 2025 a propósito: así el YTD tiene que partir en el primer dato de 2026 y no en el primero que haya.
    dias = pd.bdate_range("2025-11-03", "2026-03-04")  # termina en miércoles
    precios = pd.Series(100 * 1.01 ** np.arange(len(dias)), index=dias)
    c = rf.cambios_por_periodo(precios)
    assert c["1D %"] == pytest.approx(1.0, abs=1e-9)
    # Cuántas ruedas hay entre dos fechas = días hábiles contando ambas puntas, menos 1
    def ruedas(desde):
        return len(pd.bdate_range(desde, "2026-03-04")) - 1

    assert ruedas("2026-02-25") == 5  # hace 7 días: el miércoles anterior
    assert c["1W %"] == pytest.approx((1.01 ** ruedas("2026-02-25") - 1) * 100, abs=1e-9)
    assert c["1M %"] == pytest.approx((1.01 ** ruedas("2026-02-02") - 1) * 100, abs=1e-9)  # hace 30 días: lunes 2-feb
    assert c["YTD %"] == pytest.approx((1.01 ** ruedas("2026-01-01") - 1) * 100, abs=1e-9)


def test_cambios_con_pocos_datos_son_none():
    assert rf.cambios_por_periodo(pd.Series([100.0], index=_dias("2026-01-01", 1))) == {"1D %": None, "1W %": None, "1M %": None, "YTD %": None}
    corta = pd.Series([100.0, 101.0, 102.0], index=_dias("2026-03-02", 3))
    c = rf.cambios_por_periodo(corta)
    assert c["1D %"] == pytest.approx(100 * (102 / 101 - 1)) and c["1M %"] is None  # no hay datos de hace un mes


def test_volatilidad_de_retornos_alternados():
    n = 300
    retornos = np.where(np.arange(n) % 2 == 0, 0.01, -0.01)
    precios = pd.Series(100 * np.cumprod(1 + retornos), index=_dias("2025-01-01", n))
    ventana = precios[precios.index >= precios.index[-1] - pd.Timedelta(days=365)]
    esperado = np.std(ventana.pct_change().dropna().to_numpy(), ddof=1) * np.sqrt(252) * 100
    assert rf.volatilidad_anualizada(precios) == pytest.approx(esperado, rel=1e-9)
    assert 15 < rf.volatilidad_anualizada(precios) < 17  # ≈ 1 % diario × √252


def test_volatilidad_de_una_serie_corta_es_none():
    assert rf.volatilidad_anualizada(pd.Series(np.linspace(100, 101, 10), index=_dias("2026-01-01", 10))) is None


def test_caida_maxima_es_la_peor_baja_desde_un_maximo():
    precios = pd.Series([100.0, 120.0, 90.0, 110.0, 100.0], index=_dias("2026-01-05", 5))
    assert rf.caida_maxima(precios) == pytest.approx(-25.0)  # de 120 a 90
    assert rf.caida_maxima(pd.Series([100.0, 101.0, 102.0], index=_dias("2026-01-05", 3))) == pytest.approx(0.0)


def test_beta_recupera_el_multiplo_y_el_signo():
    rng = np.random.default_rng(1)
    mercado = pd.Series(rng.normal(0, 0.01, 200), index=_dias("2025-06-02", 200))
    assert rf.beta_contra(2 * mercado, mercado) == pytest.approx(2.0, abs=1e-9)
    assert rf.beta_contra(-0.5 * mercado, mercado) == pytest.approx(-0.5, abs=1e-9)
    assert rf.beta_contra(mercado.head(10), mercado.head(10)) is None  # muy pocos datos


def test_sharpe():
    assert rf.razon_de_sharpe(5.0, 3.0, 4.0) == pytest.approx(0.5)
    assert rf.razon_de_sharpe(None, 3.0, 4.0) is None
    assert rf.razon_de_sharpe(5.0, None, 4.0) is None
    assert rf.razon_de_sharpe(5.0, 3.0, 0.0) is None


def _precio_con_duracion(duracion, cambios_de_tasa, ruido=None):
    """Serie de precios cuyo retorno diario es exactamente -duración × cambio de la tasa (más ruido opcional)."""
    retornos = -duracion * cambios_de_tasa.to_numpy() + (0 if ruido is None else ruido)
    return pd.Series(100 * np.cumprod(1 + retornos), index=cambios_de_tasa.index)


def test_la_duracion_medida_recupera_la_duracion_con_la_que_se_construyeron_los_datos():
    rng = np.random.default_rng(7)
    dias = _dias("2025-01-01", 400)
    cambios = pd.Series(rng.normal(0, 0.0005, 400), index=dias)  # ±5 pb diarios
    tasa = 0.04 + cambios.cumsum()
    precios = _precio_con_duracion(6.5, cambios)
    r = rf.duracion_empirica(precios, tasa)
    assert r["duracion"] == pytest.approx(6.5, rel=1e-6)
    assert r["r2"] == pytest.approx(1.0, abs=1e-9)
    assert r["error_estandar"] == pytest.approx(0.0, abs=1e-6)
    assert r["n"] == 252


def test_con_ruido_el_r2_baja_y_la_duracion_cae_dentro_de_dos_errores():
    rng = np.random.default_rng(11)
    dias = _dias("2025-01-01", 400)
    cambios = pd.Series(rng.normal(0, 0.0005, 400), index=dias)
    tasa = 0.04 + cambios.cumsum()
    precios = _precio_con_duracion(6.5, cambios, ruido=rng.normal(0, 0.004, 400))  # el ruido tapa buena parte de la señal
    r = rf.duracion_empirica(precios, tasa)
    assert 0 < r["r2"] < 0.9
    assert abs(r["duracion"] - 6.5) < 3 * r["error_estandar"]


def test_los_pares_de_la_duracion_alinean_fechas_y_calzan_con_la_regresion():
    rng = np.random.default_rng(21)
    dias = _dias("2025-01-01", 400)
    cambios = pd.Series(rng.normal(0, 0.0005, 400), index=dias)
    tasa = 0.04 + cambios.cumsum()
    precios = _precio_con_duracion(5.0, cambios)
    pares = rf.pares_para_duracion(precios, tasa.drop(tasa.index[[30, 31, 250]]))
    assert list(pares.columns) == ["cambio_de_tasa", "retorno"] and len(pares) == 252
    assert pares.index.is_monotonic_increasing and pares.notna().all().all()
    # la pendiente de esos mismos pares es la duración que entrega duracion_empirica (con el signo cambiado)
    pendiente = np.cov(pares["retorno"], pares["cambio_de_tasa"])[0, 1] / pares["cambio_de_tasa"].var()
    assert -pendiente == pytest.approx(rf.duracion_empirica(precios, tasa.drop(tasa.index[[30, 31, 250]]))["duracion"])
    assert len(rf.pares_para_duracion(precios, tasa, ventana=100)) == 100


def test_la_duracion_medida_es_none_con_pocos_datos_o_sin_movimiento():
    dias = _dias("2025-01-01", 20)
    assert rf.duracion_empirica(pd.Series(np.linspace(100, 101, 20), index=dias), pd.Series(0.04, index=dias)) is None
    dias = _dias("2025-01-01", 100)
    assert rf.duracion_empirica(pd.Series(np.linspace(100, 101, 100), index=dias), pd.Series(0.04, index=dias)) is None  # tasa sin cambios


def test_la_duracion_medida_alinea_por_fecha_aunque_falten_dias_en_la_tasa():
    rng = np.random.default_rng(3)
    dias = _dias("2025-01-01", 400)
    cambios = pd.Series(rng.normal(0, 0.0005, 400), index=dias)
    tasa = 0.04 + cambios.cumsum()
    precios = _precio_con_duracion(4.0, cambios)
    faltan = tasa.index[200::5]  # a la tasa le faltan 40 días repartidos entre los últimos 200
    r = rf.duracion_empirica(precios, tasa.drop(faltan))
    # Con la alineación correcta (solo fechas que tienen precio Y tasa) el retorno de un salto de 2 días calza con
    # el cambio de tasa de esos 2 días, y la duración se recupera casi exacta; rellenar la tasa con el valor del
    # día anterior descuadra esos días y la estimación se aleja.
    assert r is not None and r["duracion"] == pytest.approx(4.0, abs=0.02)


def test_resumen_de_instrumento_junta_todas_las_metricas():
    rng = np.random.default_rng(5)
    dias = _dias("2025-01-01", 400)
    cambios = pd.Series(rng.normal(0, 0.0005, 400), index=dias)
    tasa = 0.04 + cambios.cumsum()
    precios = _precio_con_duracion(6.5, cambios)
    mercado = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.01, 400)), index=dias)
    r = rf.resumen_de_instrumento(precios, mercado, tasa, tasa_libre_de_riesgo_pct=4.0)
    assert r["Duración medida (años)"] == pytest.approx(6.5, rel=1e-6)
    assert r["R² con la tasa"] == pytest.approx(1.0, abs=1e-9)
    assert r["ultima_fecha"] == dias[-1]
    assert r["Retorno 1 año (%)"] == pytest.approx(rf.retorno_ultimo_anio(precios))
    assert r["Volatilidad (%)"] == pytest.approx(rf.volatilidad_anualizada(precios))
    assert r["Sharpe"] == pytest.approx((r["Retorno 1 año (%)"] - 4.0) / r["Volatilidad (%)"])
    assert r["Caída máxima 1 año (%)"] <= 0
    assert abs(r["Beta vs S&P 500"]) < 1
    assert rf.resumen_de_instrumento(precios.head(1), mercado, tasa, 4.0) is None


# ---------------------------------------------------------------------------
# Carteras armadas con instrumentos reales
# ---------------------------------------------------------------------------
def test_retornos_de_cartera_es_la_combinacion_lineal_de_los_retornos():
    dias = _dias("2026-01-05", 4)
    r = pd.DataFrame({"A": [0.01, 0.02, -0.01, 0.0], "B": [0.03, 0.00, 0.01, -0.02]}, index=dias)
    cartera = rf.retornos_de_cartera(r, {"A": 0.6, "B": 0.4})
    assert cartera.tolist() == pytest.approx([0.6 * 0.01 + 0.4 * 0.03, 0.6 * 0.02, 0.6 * -0.01 + 0.4 * 0.01, 0.4 * -0.02])
    with pytest.raises(ValueError):
        rf.retornos_de_cartera(r, {"A": 0.6, "B": 0.5})


def test_estadisticas_de_retornos_constantes():
    r = pd.Series([0.01, 0.01, 0.01], index=_dias("2026-01-05", 3))
    e = rf.estadisticas_de_retornos(r)
    assert e["retorno_total"] == pytest.approx((1.01**3 - 1) * 100)
    assert e["volatilidad"] == pytest.approx(0.0, abs=1e-12)
    assert e["caida_maxima"] == pytest.approx(0.0)
    con_caida = rf.estadisticas_de_retornos(pd.Series([0.10, -0.20, 0.05], index=_dias("2026-01-05", 3)))
    assert con_caida["caida_maxima"] == pytest.approx(-20.0)  # de 1,10 a 0,88
    with pytest.raises(ValueError):
        rf.estadisticas_de_retornos(r.head(1))


def test_los_pesos_del_barbell_igualan_la_duracion_objetivo():
    corto, largo = rf.pesos_para_igualar_duracion(1.7, 14.2, 6.5)
    assert corto + largo == pytest.approx(1.0)
    assert corto * 1.7 + largo * 14.2 == pytest.approx(6.5)
    assert 0 < corto < 1 and 0 < largo < 1
    with pytest.raises(ValueError):
        rf.pesos_para_igualar_duracion(6.5, 14.2, 1.7)
    with pytest.raises(ValueError):
        rf.pesos_para_igualar_duracion(1.7, 14.2, 20.0)


def test_el_motor_no_importa_streamlit():
    codigo = open(os.path.join(os.path.dirname(__file__), "..", "renta_fija.py"), encoding="utf-8").read()
    assert "streamlit" not in codigo
