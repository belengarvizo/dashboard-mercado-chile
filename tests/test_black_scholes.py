"""Pruebas del motor de Black-Scholes (black_scholes.py) con casos de respuesta conocida.

Son los casos estándar de cualquier curso de derivados: el ejemplo de libro (S=K=100, T=1, r=5%, sigma=20% ->
call ≈10,45, put ≈5,57), la paridad put-call, la volatilidad implícita recuperando exactamente la sigma con la que
se generó el precio, y el límite T→0 convergiendo al valor intrínseco. Así un error de signo o de fórmula no puede
pasar inadvertido.
"""
import math
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pytest

import black_scholes as bs


# ---------------------------------------------------------------------------
# Casos de libro
# ---------------------------------------------------------------------------
def test_el_caso_clasico_de_libro_da_los_precios_conocidos():
    """Hull, "Options, Futures and Other Derivatives": S=100, K=100, T=1, r=5%, sigma=20% -> call 10,4506, put 5,5735."""
    call = bs.precio(100, 100, 1, 0.05, 0.20, "call")
    put = bs.precio(100, 100, 1, 0.05, 0.20, "put")
    assert call == pytest.approx(10.4506, abs=0.001)
    assert put == pytest.approx(5.5735, abs=0.001)


def test_la_paridad_put_call_se_cumple_siempre():
    """C - P = S - K·e^(-rT), para cualquier combinación de parámetros razonable."""
    for S, K, T, r, sigma in [(100, 100, 1, 0.05, 0.2), (50, 60, 0.25, 0.03, 0.4), (200, 180, 2, 0.08, 0.15)]:
        call = bs.precio(S, K, T, r, sigma, "call")
        put = bs.precio(S, K, T, r, sigma, "put")
        assert call - put == pytest.approx(S - K * math.exp(-r * T), abs=1e-9)


def test_un_call_muy_dentro_de_dinero_vale_casi_su_valor_intrinseco():
    """Si S >> K, el call casi no tiene valor de tiempo: su precio se acerca a S - K·e^(-rT)."""
    call = bs.precio(1000, 10, 0.1, 0.05, 0.2, "call")
    intrinseco_descontado = 1000 - 10 * math.exp(-0.05 * 0.1)
    assert call == pytest.approx(intrinseco_descontado, abs=0.5)


def test_un_call_muy_fuera_de_dinero_vale_casi_cero():
    call = bs.precio(10, 1000, 0.1, 0.05, 0.2, "call")
    assert call == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# El límite T → 0: Black-Scholes converge al valor intrínseco
# ---------------------------------------------------------------------------
def test_con_tiempo_cero_el_precio_es_exactamente_el_valor_intrinseco():
    assert bs.precio(110, 100, 0, 0.05, 0.2, "call") == bs.valor_intrinseco(110, 100, "call") == 10.0
    assert bs.precio(90, 100, 0, 0.05, 0.2, "call") == bs.valor_intrinseco(90, 100, "call") == 0.0
    assert bs.precio(90, 100, 0, 0.05, 0.2, "put") == bs.valor_intrinseco(90, 100, "put") == 10.0


def test_con_volatilidad_cero_el_precio_tambien_es_el_valor_intrinseco_pero_sin_descontar():
    """Sin incertidumbre, el precio hoy de lo que se sabe que va a pasar al vencimiento es su valor presente —
    pero acá, por simplicidad, se trata igual que T=0 (ver docstring de precio()): es una aproximación declarada."""
    assert bs.precio(110, 100, 1, 0.05, 0, "call") == 10.0


def test_el_valor_intrinseco_nunca_es_negativo():
    assert bs.valor_intrinseco(50, 100, "call") == 0.0
    assert bs.valor_intrinseco(150, 100, "put") == 0.0


def test_tipo_invalido_lanza_un_error_claro():
    with pytest.raises(ValueError):
        bs.precio(100, 100, 1, 0.05, 0.2, "swap")
    with pytest.raises(ValueError):
        bs.valor_intrinseco(100, 100, "swap")


def test_parametros_invalidos_lanzan_un_error_claro():
    with pytest.raises(ValueError):
        bs.precio(-100, 100, 1, 0.05, 0.2, "call")
    with pytest.raises(ValueError):
        bs.precio(100, 0, 1, 0.05, 0.2, "call")
    with pytest.raises(ValueError):
        bs.precio(100, 100, -1, 0.05, 0.2, "call")
    with pytest.raises(ValueError):
        bs.precio(100, 100, 1, 0.05, -0.2, "call")


# ---------------------------------------------------------------------------
# Volatilidad implícita: recupera exactamente la sigma con la que se generó el precio
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("S,K,T,r,sigma,tipo", [
    (100, 100, 1, 0.05, 0.20, "call"), (100, 100, 1, 0.05, 0.20, "put"),
    (50, 55, 0.5, 0.03, 0.27, "put"), (200, 180, 0.1, 0.08, 0.60, "call"),
    (80, 120, 2, 0.02, 0.35, "call"), (768, 769, 1 / 365, 0.041, 0.12, "call"),  # un contrato a 1 día, como en pantalla
])
def test_la_volatilidad_implicita_recupera_exactamente_la_sigma_usada(S, K, T, r, sigma, tipo):
    precio_generado = bs.precio(S, K, T, r, sigma, tipo)
    iv = bs.volatilidad_implicita(precio_generado, S, K, T, r, tipo)
    assert iv == pytest.approx(sigma, abs=1e-4)


def test_un_precio_bajo_el_valor_intrinseco_no_tiene_volatilidad_implicita():
    """Ninguna volatilidad (ni siquiera cero) explica un precio por debajo de lo que vale ejercer ya mismo."""
    intrinseco = bs.valor_intrinseco(150, 100, "call")  # 50
    assert bs.volatilidad_implicita(intrinseco - 5, 150, 100, 1, 0.05, "call") is None


def test_sin_tiempo_al_vencimiento_no_se_puede_despejar_una_volatilidad():
    assert bs.volatilidad_implicita(10.0, 110, 100, 0, 0.05, "call") is None


def test_un_precio_absurdamente_alto_no_tiene_volatilidad_implicita_dentro_del_rango():
    """Ni con 500% de volatilidad se explica un precio mayor al propio subyacente."""
    assert bs.volatilidad_implicita(10_000, 100, 100, 1, 0.05, "call") is None


# ---------------------------------------------------------------------------
# Griegas
# ---------------------------------------------------------------------------
def test_el_delta_de_un_call_esta_entre_0_y_1_y_el_de_un_put_entre_menos_1_y_0():
    g_call = bs.griegas(100, 100, 1, 0.05, 0.2, "call")
    g_put = bs.griegas(100, 100, 1, 0.05, 0.2, "put")
    assert 0 < g_call.delta < 1
    assert -1 < g_put.delta < 0


def test_el_delta_de_un_call_muy_dentro_de_dinero_es_cercano_a_1():
    g = bs.griegas(1000, 10, 0.5, 0.05, 0.2, "call")
    assert g.delta == pytest.approx(1.0, abs=0.01)


def test_el_delta_de_un_call_muy_fuera_de_dinero_es_cercano_a_0():
    g = bs.griegas(10, 1000, 0.5, 0.05, 0.2, "call")
    assert g.delta == pytest.approx(0.0, abs=0.01)


def test_gamma_es_la_misma_para_el_call_y_el_put_del_mismo_contrato():
    """Es una identidad de Black-Scholes: la convexidad del precio no depende de si es call o put."""
    g_call = bs.griegas(100, 105, 0.5, 0.04, 0.25, "call")
    g_put = bs.griegas(100, 105, 0.5, 0.04, 0.25, "put")
    assert g_call.gamma == pytest.approx(g_put.gamma, rel=1e-9)
    assert g_call.gamma > 0  # el precio de una opción siempre es convexo en el subyacente


def test_vega_es_la_misma_para_el_call_y_el_put_y_siempre_positiva():
    g_call = bs.griegas(100, 105, 0.5, 0.04, 0.25, "call")
    g_put = bs.griegas(100, 105, 0.5, 0.04, 0.25, "put")
    assert g_call.vega == pytest.approx(g_put.vega, rel=1e-9)
    assert g_call.vega > 0  # más volatilidad siempre vale más, para cualquiera de los dos


def test_el_delta_calculado_coincide_con_el_cambio_de_precio_por_diferencias_finitas():
    """Verificación cruzada: el delta analítico debe ser (precio(S+h) - precio(S-h)) / (2h), para h chico."""
    S, K, T, r, sigma = 100, 95, 0.75, 0.04, 0.3
    h = 0.01
    delta_numerico = (bs.precio(S + h, K, T, r, sigma, "call") - bs.precio(S - h, K, T, r, sigma, "call")) / (2 * h)
    g = bs.griegas(S, K, T, r, sigma, "call")
    assert g.delta == pytest.approx(delta_numerico, abs=1e-4)


def test_theta_de_un_call_normalmente_es_negativo_pierde_valor_con_el_tiempo():
    g = bs.griegas(100, 100, 1, 0.05, 0.2, "call")
    assert g.theta < 0


def test_gamma_coincide_con_el_cambio_del_delta_por_diferencias_finitas():
    """gamma = d(delta)/dS: no alcanza con que gamma(call) == gamma(put) y sea positiva (un error de escala, como
    olvidar dividir por sigma, pasa esa prueba igual); se verifica contra la definición misma."""
    S, K, T, r, sigma = 100, 95, 0.75, 0.04, 0.3
    h = 0.01
    gamma_numerico = (bs.griegas(S + h, K, T, r, sigma, "call").delta - bs.griegas(S - h, K, T, r, sigma, "call").delta) / (2 * h)
    g = bs.griegas(S, K, T, r, sigma, "call")
    assert g.gamma == pytest.approx(gamma_numerico, abs=1e-4)


def test_vega_coincide_con_el_cambio_de_precio_por_un_punto_de_volatilidad():
    """vega está definida «por 1 punto porcentual de sigma» (ver Griegas.__doc__): se verifica contra una diferencia
    central con paso chico (y no un salto de 0,01 completo, que recoge curvatura y no solo la pendiente), para que
    un error de escala (como olvidar dividir por 100) no pase inadvertido."""
    S, K, T, r, sigma = 100, 95, 0.75, 0.04, 0.3
    h = 1e-5
    vega_numerico = (bs.precio(S, K, T, r, sigma + h, "call") - bs.precio(S, K, T, r, sigma - h, "call")) / (2 * h) * 0.01
    g = bs.griegas(S, K, T, r, sigma, "call")
    assert g.vega == pytest.approx(vega_numerico, abs=1e-5)


def test_theta_coincide_con_el_cambio_de_precio_al_pasar_un_dia():
    """theta está definida «por el paso de un día» (ver Griegas.__doc__): se compara con precio(T) menos
    precio(T - 1 día), directamente, sin pasar por una fórmula analítica que podría tener el mismo error que
    la que se está probando."""
    S, K, T, r, sigma = 100, 95, 0.75, 0.04, 0.3
    un_dia = 1 / bs.DIAS_DEL_ANIO
    theta_numerico = bs.precio(S, K, T - un_dia, r, sigma, "call") - bs.precio(S, K, T, r, sigma, "call")
    g = bs.griegas(S, K, T, r, sigma, "call")
    assert g.theta == pytest.approx(theta_numerico, abs=1e-4)


def test_sin_tiempo_o_sin_volatilidad_las_griegas_no_se_inventan():
    g = bs.griegas(100, 100, 0, 0.05, 0.2, "call")
    assert math.isnan(g.delta) and math.isnan(g.gamma) and math.isnan(g.theta) and math.isnan(g.vega) and math.isnan(g.rho)
