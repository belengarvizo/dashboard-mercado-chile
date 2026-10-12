"""Estadísticas del proceso: funciones puras, sin tocar la base.

Se prueban sobre todo los casos borde, que es donde este tipo de cálculo
miente: sin operaciones, con una sola, con el riesgo en cero o vacío, y con
las probabilidades de los escenarios justo en el límite. En todos, la
respuesta correcta es None o un aviso, nunca un cero que se lea como "la
expectativa es cero".
"""
import os
import sys
from decimal import Decimal

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from trading_proceso import (
    AVISO_POCAS,
    N_MINIMO_CONFIABLE,
    PREGUNTAS_CHECKLIST,
    cuadro_decision_resultado,
    estadisticas,
    estadisticas_por,
    evaluar_checklist,
    expectativa_r,
    peor_racha_perdidas,
    r_multiplo,
    valor_esperado_pips,
    validar_probabilidades,
)


def op(resultado=None, riesgo=None, **extra):
    base = {"resultado_clp": resultado, "riesgo_clp": riesgo}
    base.update(extra)
    return base


# --------------------------------------------------------------- r_multiplo
def test_r_multiplo_basico():
    assert r_multiplo(200000, 100000) == Decimal(2)
    assert r_multiplo(-100000, 100000) == Decimal(-1)
    assert r_multiplo(50000, 100000) == Decimal("0.5")


def test_r_multiplo_usa_el_valor_absoluto_del_riesgo():
    """El riesgo es una magnitud: si quedó guardado en negativo, una
    operación ganadora no puede dar un R negativo."""
    assert r_multiplo(200000, -100000) == Decimal(2)


def test_r_multiplo_sin_riesgo_no_se_inventa():
    """Sin riesgo inicial no hay R. Devolver 0 lo metería en los promedios
    como si fuera una operación en el punto de equilibrio."""
    assert r_multiplo(200000, None) is None
    assert r_multiplo(200000, 0) is None
    assert r_multiplo(200000, float("nan")) is None
    assert r_multiplo(None, 100000) is None


# ------------------------------------------------------------- expectativa
def test_expectativa_sin_datos_es_none_no_cero():
    assert expectativa_r([]) is None
    assert expectativa_r([None, None]) is None


def test_expectativa_con_una_sola_operacion():
    assert expectativa_r([Decimal(3)]) == Decimal(3)


def test_expectativa_promedia_los_r():
    # +2R, -1R, -1R  ->  0
    assert expectativa_r([Decimal(2), Decimal(-1), Decimal(-1)]) == Decimal(0)
    # +3R, -1R  ->  +1R
    assert expectativa_r([Decimal(3), Decimal(-1)]) == Decimal(1)


# ------------------------------------------------------------- peor racha
def test_peor_racha_de_perdidas():
    assert peor_racha_perdidas([]) == 0
    assert peor_racha_perdidas([100, 200]) == 0
    assert peor_racha_perdidas([-1, -1, -1]) == 3
    # la racha se corta con una ganadora
    assert peor_racha_perdidas([-1, -1, 5, -1]) == 2
    # y la peor no es necesariamente la última
    assert peor_racha_perdidas([-1, -1, -1, 5, -1]) == 3


def test_un_empate_no_corta_ni_alarga_la_racha():
    """Un resultado exactamente 0 no es una pérdida ni una recuperación."""
    assert peor_racha_perdidas([-1, 0, -1]) == 2
    assert peor_racha_perdidas([0, 0]) == 0


def test_las_operaciones_sin_resultado_se_ignoran_en_la_racha():
    assert peor_racha_perdidas([-1, None, -1]) == 2


# ----------------------------------------------------------- estadisticas
def test_estadisticas_sin_operaciones():
    e = estadisticas([])
    assert e.n == 0 and e.expectativa_r is None and e.aciertos_pct is None
    assert "sin operaciones" in e.aviso


def test_estadisticas_avisan_cuando_hay_pocas():
    pocas = estadisticas([op(100000, 100000)] * 3)
    assert pocas.n == 3 and pocas.aviso == AVISO_POCAS and not pocas.es_confiable

    muchas = estadisticas([op(100000, 100000)] * N_MINIMO_CONFIABLE)
    assert muchas.es_confiable and muchas.aviso == ""


def test_estadisticas_completas():
    ops = [op(200000, 100000), op(-100000, 100000), op(-100000, 100000), op(400000, 100000)]
    e = estadisticas(ops)
    assert e.n == 4 and e.n_con_r == 4
    assert e.expectativa_r == Decimal("1.0")          # (2 - 1 - 1 + 4) / 4
    assert e.aciertos_pct == Decimal(50)
    assert e.r_medio_ganadoras == Decimal(3)          # (2 + 4) / 2
    assert e.r_medio_perdedoras == Decimal(-1)
    assert e.peor_racha == 2


def test_las_operaciones_sin_riesgo_no_se_cuelan_en_los_promedios():
    """Pero sí se cuentan en n y se avisa, para que el hueco se vea."""
    ops = [op(200000, 100000), op(500000, None)]
    e = estadisticas(ops)
    assert e.n == 2 and e.n_con_r == 1
    assert e.expectativa_r == Decimal(2), "la operación sin riesgo distorsionó la expectativa"
    assert any("no tienen riesgo inicial" in d for d in e.desglose), e.desglose


def test_estadisticas_abiertas_por_campo():
    ops = [
        op(200000, 100000, tendencia_diario="a_favor"),
        op(-100000, 100000, tendencia_diario="a_favor"),
        op(-100000, 100000, tendencia_diario="contra"),
        op(100000, 100000),  # sin tendencia anotada
    ]
    por = estadisticas_por(ops, "tendencia_diario")
    assert por["a_favor"].n == 2
    assert por["contra"].n == 1
    assert por["sin dato"].n == 1, "las operaciones sin el campo deben verse, no desaparecer"
    assert por["a_favor"].expectativa_r == Decimal("0.5")


# ------------------------------------------------- cuadro decision/resultado
def test_cuadro_de_cuatro_casillas():
    ops = [
        op(100000, 100000, calidad_decision="buena"),    # buena / ganadora
        op(-100000, 100000, calidad_decision="buena"),   # buena / perdedora
        op(100000, 100000, calidad_decision="mala"),     # mala / ganadora
        op(-100000, 100000, calidad_decision="mala"),    # mala / perdedora
        op(-100000, 100000),                             # sin evaluar
        op(0, 100000, calidad_decision="buena"),         # resultado 0: no clasifica
    ]
    c = cuadro_decision_resultado(ops)
    assert c[("buena", "ganadora")] == 1
    assert c[("buena", "perdedora")] == 1
    assert c[("mala", "ganadora")] == 1
    assert c[("mala", "perdedora")] == 1
    assert c["sin_clasificar"] == 2


# --------------------------------------------------------------- escenarios
def test_las_probabilidades_tienen_que_sumar_cien():
    bien = [{"probabilidad": 50, "movimiento_pips": 100},
            {"probabilidad": 50, "movimiento_pips": -50}]
    ok, suma, msg = validar_probabilidades(bien)
    assert ok and suma == Decimal(100) and msg == ""

    mal = [{"probabilidad": 50, "movimiento_pips": 100},
           {"probabilidad": 30, "movimiento_pips": -50}]
    ok2, suma2, msg2 = validar_probabilidades(mal)
    assert not ok2 and suma2 == Decimal(80)
    assert "falta 20" in msg2, msg2

    pasado = [{"probabilidad": 70, "movimiento_pips": 10},
              {"probabilidad": 50, "movimiento_pips": 10}]
    ok3, _s3, msg3 = validar_probabilidades(pasado)
    assert not ok3 and "sobra 20" in msg3, msg3

    ok4, _s4, msg4 = validar_probabilidades([])
    assert not ok4 and "No hay escenarios" in msg4


def test_tolerancia_minima_por_redondeo():
    casi = [{"probabilidad": "33.33", "movimiento_pips": 10},
            {"probabilidad": "33.33", "movimiento_pips": 10},
            {"probabilidad": "33.34", "movimiento_pips": 10}]
    ok, suma, _ = validar_probabilidades(casi)
    assert ok, f"suma {suma}: debería aceptarse por tolerancia de redondeo"


def test_valor_esperado_en_pips():
    escenarios = [
        {"probabilidad": 60, "movimiento_pips": 100},   # +60
        {"probabilidad": 40, "movimiento_pips": -50},   # -20
    ]
    assert valor_esperado_pips(escenarios) == Decimal(40)


def test_el_valor_esperado_no_se_calcula_sobre_probabilidades_invalidas():
    """Un valor esperado sobre probabilidades que no suman 100% no significa
    nada, así que no se devuelve un número."""
    malos = [{"probabilidad": 50, "movimiento_pips": 100}]
    assert valor_esperado_pips(malos) is None

    sin_movimiento = [{"probabilidad": 100}]
    assert valor_esperado_pips(sin_movimiento) is None


# ---------------------------------------------------------------- checklist
def test_checklist_avisa_pero_no_bloquea():
    todas_si = [True] * len(PREGUNTAS_CHECKLIST)
    puede, noes = evaluar_checklist(todas_si)
    assert puede and noes == []

    con_un_no = [True] * len(PREGUNTAS_CHECKLIST)
    con_un_no[3] = False
    puede2, noes2 = evaluar_checklist(con_un_no)
    assert not puede2
    assert noes2 == [PREGUNTAS_CHECKLIST[3]]


if __name__ == "__main__":
    for nombre, funcion in sorted(list(globals().items())):
        if nombre.startswith("test_"):
            funcion()
            print("OK:", nombre)


def test_valor_esperado_con_el_movimiento_sin_completar():
    """Un escenario sin movimiento esperado NO vale cero.

    Las probabilidades pueden sumar 100% y aun así faltar el dato: completar
    con cero diría "ese escenario no mueve el precio", que es una afirmación
    y no un dato faltante. Antes el formulario guardaba 0 por defecto, así
    que el valor esperado salía calculado sobre un supuesto inventado.
    """
    falta_uno = [
        {"escenario": "sorpresa alcista", "probabilidad": 50, "movimiento_pips": 80},
        {"escenario": "en línea", "probabilidad": 50, "movimiento_pips": None},
    ]
    ok, suma, _ = validar_probabilidades(falta_uno)
    assert ok and suma == Decimal(100), "las probabilidades sí cierran"
    assert valor_esperado_pips(falta_uno) is None, (
        "calculó un valor esperado tratando el movimiento faltante como cero")

    # con el dato completo sí calcula
    completo = [
        {"escenario": "sorpresa alcista", "probabilidad": 50, "movimiento_pips": 80},
        {"escenario": "en línea", "probabilidad": 50, "movimiento_pips": 0},
    ]
    assert valor_esperado_pips(completo) == Decimal(40), (
        "un cero EXPLÍCITO sí es un dato y debe entrar en la cuenta")

    # y un NaN de la base cuenta como faltante, igual que None
    con_nan = [
        {"escenario": "a", "probabilidad": 50, "movimiento_pips": 80},
        {"escenario": "b", "probabilidad": 50, "movimiento_pips": float("nan")},
    ]
    assert valor_esperado_pips(con_nan) is None
