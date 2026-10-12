"""La asimetría entre perder y recuperar.

Las referencias que fijan la fórmula: perder 20% exige ganar 25%; perder
50% exige ganar 100%. Si una de esas dos se rompe, la cuenta está mal.

Los bordes que importan son el 0% (no hay nada que mostrar) y el 100% (no
se puede, y hay que decirlo sin dividir por cero).

Módulo puro: estas pruebas no tocan la base de datos ni la red.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal

import pytest

from trading_recuperacion import (
    MOTIVO_TODO_EL_CAPITAL,
    RACHAS,
    ganancia_para_recuperar,
    recuperacion,
    recuperacion_de_racha,
    tabla_de_rachas,
)

CAPITAL = Decimal("10000000")


def _pct(x):
    """Decimal en fracción -> porcentaje, para leer las aserciones."""
    return None if x is None else float(x * 100)


# ------------------------------------------------- las dos referencias fijas
def test_perder_20_por_ciento_exige_ganar_25():
    assert _pct(ganancia_para_recuperar(Decimal("0.20"))) == pytest.approx(25.0)


def test_perder_50_por_ciento_exige_ganar_100():
    assert _pct(ganancia_para_recuperar(Decimal("0.50"))) == pytest.approx(100.0)


def test_la_asimetria_crece_y_nunca_es_menor_que_la_perdida():
    """Recuperar siempre exige ganar MÁS de lo que se perdió, en porcentaje,
    y la brecha se abre a medida que la pérdida crece."""
    anterior = Decimal(0)
    for p in ("0.01", "0.05", "0.10", "0.20", "0.33", "0.50", "0.75", "0.90"):
        perdida = Decimal(p)
        ganancia = ganancia_para_recuperar(perdida)
        assert ganancia > perdida, f"con {p} la ganancia no supera la pérdida"
        brecha = ganancia - perdida
        assert brecha > anterior, f"la brecha no creció en {p}"
        anterior = brecha


def test_perdidas_chicas_son_casi_simetricas():
    """Con 1% la diferencia es de centésimas: es justamente el argumento a
    favor de arriesgar poco."""
    assert _pct(ganancia_para_recuperar(Decimal("0.01"))) == pytest.approx(
        1.010101, abs=0.000001)


# ------------------------------------------------------------- los dos bordes
def test_sin_perdida_no_hay_nada_que_mostrar():
    assert ganancia_para_recuperar(Decimal(0)) is None
    assert ganancia_para_recuperar(Decimal("-0.1")) is None
    assert recuperacion(0, CAPITAL) is None
    assert recuperacion(Decimal("-5000"), CAPITAL) is None


def test_perder_todo_el_capital_no_se_recupera_y_no_divide_por_cero():
    """1 - 1 = 0 en el denominador. Tiene que decirlo, no reventar."""
    assert ganancia_para_recuperar(Decimal("1.0")) is None
    assert ganancia_para_recuperar(Decimal("1.5")) is None

    r = recuperacion(CAPITAL, CAPITAL)
    assert r is not None, "no es lo mismo que no haya nada que mostrar"
    assert not r.se_puede
    assert r.ganancia_fraccion is None
    assert r.motivo == MOTIVO_TODO_EL_CAPITAL
    assert "una sola operación" in r.motivo
    assert r.capital_restante_clp == 0


def test_perder_mas_que_el_capital_tampoco_rompe():
    r = recuperacion(CAPITAL * 2, CAPITAL)
    assert r is not None and not r.se_puede
    assert r.capital_restante_clp == 0, "el capital restante no puede ser negativo"


def test_sin_capital_no_se_calcula_nada():
    assert recuperacion(100000, 0) is None
    assert recuperacion(100000, None) is None
    assert recuperacion(100000, Decimal("-1")) is None
    assert recuperacion(None, CAPITAL) is None


def test_un_nulo_de_la_base_llega_como_nan_y_no_como_none():
    """pandas convierte el NULL de SQL en NaN, que es un float: un chequeo
    `is None` no lo ve. Ya pasó antes en este proyecto."""
    assert recuperacion(float("nan"), CAPITAL) is None
    assert recuperacion(100000, float("nan")) is None
    assert ganancia_para_recuperar(float("nan")) is None


# --------------------------------------------------------- la cuenta en pesos
def test_en_pesos_hay_que_ganar_exactamente_lo_perdido():
    """Lo que cambia es el PORCENTAJE, no el monto. Es el punto de toda la
    tabla: los mismos pesos pesan más sobre un capital más chico."""
    r = recuperacion(Decimal("200000"), CAPITAL)
    assert r.ganancia_clp == pytest.approx(Decimal("200000"))
    assert r.perdida_clp == Decimal("200000")
    assert r.capital_restante_clp == Decimal("9800000")
    assert _pct(r.perdida_fraccion) == pytest.approx(2.0)
    assert _pct(r.ganancia_fraccion) == pytest.approx(2.040816, abs=0.000001)


def test_el_capital_restante_mas_la_ganancia_vuelve_al_de_partida():
    for monto in ("50000", "1000000", "4999999"):
        r = recuperacion(Decimal(monto), CAPITAL)
        assert r.capital_restante_clp + r.ganancia_clp == pytest.approx(CAPITAL)


# -------------------------------------------------------------- las rachas
def test_una_racha_de_una_es_la_operacion_sola():
    uno = recuperacion_de_racha(Decimal("0.01"), CAPITAL, 1)
    sola = recuperacion(CAPITAL * Decimal("0.01"), CAPITAL)
    assert uno.perdida_clp == pytest.approx(sola.perdida_clp)
    assert uno.ganancia_fraccion == pytest.approx(sola.ganancia_fraccion)


def test_tres_y_cinco_perdidas_seguidas_al_uno_por_ciento():
    """Componen: 0,99^3 deja 2,9701% abajo, no 3%. El supuesto es que
    recalculas el tamaño sobre el capital que queda, que es lo que hace el
    calculador de esta misma pantalla."""
    tres = recuperacion_de_racha(Decimal("0.01"), CAPITAL, 3)
    assert _pct(tres.perdida_fraccion) == pytest.approx(2.970100, abs=0.000001)
    assert _pct(tres.ganancia_fraccion) == pytest.approx(3.061015, abs=0.000001)

    cinco = recuperacion_de_racha(Decimal("0.01"), CAPITAL, 5)
    assert _pct(cinco.perdida_fraccion) == pytest.approx(4.900995, abs=0.000001)
    assert _pct(cinco.ganancia_fraccion) == pytest.approx(5.153571, abs=0.000001)


def test_cinco_perdidas_al_dos_por_ciento():
    cinco = recuperacion_de_racha(Decimal("0.02"), CAPITAL, 5)
    assert _pct(cinco.perdida_fraccion) == pytest.approx(9.607920, abs=0.000001)
    assert _pct(cinco.ganancia_fraccion) == pytest.approx(10.629162, abs=0.000001)


def test_la_racha_compuesta_pierde_menos_que_la_suma_simple():
    """Comprobación de que de verdad compone y no suma: cinco veces 2% no
    son 10%."""
    cinco = recuperacion_de_racha(Decimal("0.02"), CAPITAL, 5)
    assert cinco.perdida_fraccion < Decimal("0.10")
    assert cinco.perdida_fraccion > Decimal("0.09")


def test_una_racha_al_cien_por_ciento_de_riesgo_no_se_recupera():
    r = recuperacion_de_racha(Decimal("1.0"), CAPITAL, 3)
    assert r is not None and not r.se_puede
    assert r.motivo == MOTIVO_TODO_EL_CAPITAL


def test_rachas_sin_sentido_no_devuelven_nada():
    assert recuperacion_de_racha(Decimal("0.01"), CAPITAL, 0) is None
    assert recuperacion_de_racha(Decimal("0.01"), CAPITAL, -2) is None
    assert recuperacion_de_racha(Decimal(0), CAPITAL, 3) is None
    assert recuperacion_de_racha(Decimal("0.01"), 0, 3) is None


def test_la_tabla_trae_las_dos_rachas_y_en_orden():
    tabla = tabla_de_rachas(Decimal("0.01"), CAPITAL)
    assert [n for n, _r in tabla] == list(RACHAS) == [3, 5]
    assert tabla[0][1].perdida_fraccion < tabla[1][1].perdida_fraccion


def test_la_tabla_queda_vacia_si_no_hay_nada_que_calcular():
    assert tabla_de_rachas(Decimal(0), CAPITAL) == []
    assert tabla_de_rachas(Decimal("0.01"), None) == []


if __name__ == "__main__":
    print("Correr con pytest: python -m pytest tests/test_trading_recuperacion.py")
