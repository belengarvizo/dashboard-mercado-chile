"""Valida el panel de cumplimiento del torneo de XTB.

Las reglas con umbral fallan en los bordes, así que acá se prueban los bordes:
el valor justo en el límite, uno abajo y uno arriba. Y se prueba que cuando
falta un dato el chequeo diga SIN_DATOS en vez de pintar verde, porque un
verde falso en un panel de riesgo es peor que no tener panel.
"""
import os
import sys
from decimal import Decimal

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from trading_reglas import (
    CAPITAL_INICIAL_CLP,
    MAXIMO_OPERACIONES_CORTAS,
    MINIMO_OPERACIONES_CERRADAS,
    PISO_EQUITY_CLP,
    ROJO,
    SIN_DATOS,
    VERDE,
    concentracion_por_categoria,
    limite_margen_por_subyacente,
    margen_por_subyacente,
    mayor_trade_sobre_ganancia,
    minimo_operaciones,
    operaciones_cortas,
    piso_de_equity,
    riesgo_total_abierto,
    stops_hasta_el_piso,
)


def test_minimo_de_operaciones_en_el_borde():
    assert minimo_operaciones(MINIMO_OPERACIONES_CERRADAS).estado == VERDE
    assert minimo_operaciones(MINIMO_OPERACIONES_CERRADAS - 1).estado != VERDE
    assert minimo_operaciones(0).estado == ROJO
    assert "faltan 10" in minimo_operaciones(0).detalle


def test_tope_de_operaciones_cortas_en_el_borde():
    assert operaciones_cortas(MAXIMO_OPERACIONES_CORTAS).estado != ROJO
    assert operaciones_cortas(MAXIMO_OPERACIONES_CORTAS + 1).estado == ROJO
    assert operaciones_cortas(0).estado == VERDE


def test_piso_de_equity():
    assert piso_de_equity(None).estado == SIN_DATOS
    assert piso_de_equity(PISO_EQUITY_CLP).estado == ROJO, "estar justo EN el piso descalifica"
    assert piso_de_equity(PISO_EQUITY_CLP - 1).estado == ROJO
    assert piso_de_equity(CAPITAL_INICIAL_CLP).estado == VERDE
    # colchón chico -> amarillo
    assert piso_de_equity(Decimal("5500000")).estado == "amarillo"
    # y siempre recuerda de quién es la regla
    assert "XTB" in piso_de_equity(CAPITAL_INICIAL_CLP).nota


def test_mayor_trade_sobre_la_ganancia():
    # neto 100.000, mayor ganador 30.000 -> 30%, por debajo del 40%
    assert mayor_trade_sobre_ganancia([30000, 30000, 20000, 20000]).estado == VERDE
    # JUSTO en el 40%: el reglamento prohíbe pasarse, así que todavía no es
    # rojo, pero estar clavado en el límite merece aviso.
    en_el_borde = mayor_trade_sobre_ganancia([40000, 30000, 30000])
    assert en_el_borde.estado == "amarillo", en_el_borde.estado
    assert en_el_borde.valor == Decimal("0.4")
    # mayor ganador 60.000 sobre neto 100.000 -> 60%, pasado
    assert mayor_trade_sobre_ganancia([60000, 20000, 20000]).estado == ROJO
    # sin ganadores
    assert mayor_trade_sobre_ganancia([-100, -200]).estado == SIN_DATOS
    # con ganadores pero neto negativo: la regla no aplica, no inventa un %
    c = mayor_trade_sobre_ganancia([50000, -80000])
    assert c.estado == SIN_DATOS
    assert "no aplica" in c.detalle
    # la ambigüedad del reglamento queda dicha, y se muestran las dos lecturas
    c2 = mayor_trade_sobre_ganancia([60000, 20000, 20000])
    assert "ambigua" in c2.nota
    assert any("Suma de ganadores" in d for d in c2.desglose)


def test_el_limite_de_margen_usa_el_menor_de_los_dos():
    sobre_capital = CAPITAL_INICIAL_CLP * Decimal("0.30")  # 3.000.000

    # equity por encima del capital -> manda el capital inicial
    limite, _ = limite_margen_por_subyacente(Decimal("12000000"))
    assert limite == sobre_capital

    # equity por debajo -> manda el equity, que es más exigente
    limite2, pasos = limite_margen_por_subyacente(Decimal("6000000"))
    assert limite2 == Decimal("1800000")
    assert any("Se usa el menor" in p for p in pasos)

    # sin equity registrado, cae al capital inicial y lo dice
    limite3, pasos3 = limite_margen_por_subyacente(None)
    assert limite3 == sobre_capital
    assert any("No hay equity" in p for p in pasos3)


def test_margen_por_subyacente_en_el_borde():
    equity = CAPITAL_INICIAL_CLP  # límite = 3.000.000
    assert margen_por_subyacente({}, equity).estado == VERDE
    assert margen_por_subyacente({"EURUSD": 500000}, equity).estado == VERDE
    assert margen_por_subyacente({"EURUSD": 2100000}, equity).estado == "amarillo"
    assert margen_por_subyacente({"EURUSD": 3000000}, equity).estado == ROJO
    # toma el PEOR instrumento, no la suma
    c = margen_por_subyacente({"EURUSD": 500000, "US100": 2900000}, equity)
    assert "US100" in c.detalle


def test_riesgo_total_abierto():
    equity = CAPITAL_INICIAL_CLP  # 3% = 300.000
    assert riesgo_total_abierto([100000], equity).estado == VERDE
    assert riesgo_total_abierto([150000, 160000], equity).estado == ROJO
    assert riesgo_total_abierto([], equity).estado == VERDE
    # el tope es configurable
    assert riesgo_total_abierto([400000], equity, tope_pct=Decimal("0.05")).estado == VERDE
    # y se deja claro que es un límite propio, no del torneo
    assert "no del reglamento" in riesgo_total_abierto([100000], equity).nota


def test_cuantos_stops_faltan_para_la_descalificacion():
    # equity 10M, piso 5M, riesgo 100.000 -> 50 stops
    c = stops_hasta_el_piso(CAPITAL_INICIAL_CLP, 100000)
    assert c.valor == 50 and c.estado == VERDE
    # riesgo grande -> pocos stops -> rojo
    c2 = stops_hasta_el_piso(CAPITAL_INICIAL_CLP, 1000000)
    assert c2.valor == 5 and c2.estado == ROJO
    # ya en el piso
    assert stops_hasta_el_piso(PISO_EQUITY_CLP, 100000).estado == ROJO
    # datos faltantes -> SIN_DATOS, nunca verde
    assert stops_hasta_el_piso(None, 100000).estado == SIN_DATOS
    assert stops_hasta_el_piso(CAPITAL_INICIAL_CLP, 0).estado == SIN_DATOS
    assert stops_hasta_el_piso(CAPITAL_INICIAL_CLP, -5).estado == SIN_DATOS


def test_concentracion_por_categoria():
    assert concentracion_por_categoria({}).estado == VERDE
    equilibrado = concentracion_por_categoria({"divisas": 100, "indices": 100})
    assert equilibrado.estado == VERDE
    concentrado = concentracion_por_categoria({"divisas": 900, "indices": 100})
    assert concentrado.estado == "amarillo"
    # el aviso específico de cripto: varias posiciones ahí son una sola apuesta
    cripto = concentracion_por_categoria({"cripto": 500, "divisas": 500})
    assert "se mueven juntas" in cripto.nota


def test_ningun_chequeo_pinta_verde_cuando_le_falta_el_dato():
    """Un verde falso en un panel de riesgo es peor que no tener panel."""
    sin_datos = [
        piso_de_equity(None),
        stops_hasta_el_piso(None, 100000),
        mayor_trade_sobre_ganancia([]),
    ]
    for c in sin_datos:
        assert c.estado == SIN_DATOS, f"{c.nombre} pintó {c.estado} sin tener el dato"


if __name__ == "__main__":
    for nombre, funcion in sorted(list(globals().items())):
        if nombre.startswith("test_"):
            funcion()
            print("OK:", nombre)


def test_una_posicion_abierta_sin_dato_no_puede_pintar_verde():
    """El fallo que motivó este test: el formulario no guardaba riesgo_clp,
    así que el control de "riesgo total" sumaba una lista vacía, daba 0 y
    pintaba VERDE. Un verde por falta de datos en un panel de riesgo es peor
    que no tener panel: afirma que la regla se cumple sin haber mirado."""
    equity = CAPITAL_INICIAL_CLP

    # riesgo: con una sola posición sin cargar, no se puede concluir
    con_todo = riesgo_total_abierto([100000], equity, sin_dato=0)
    assert con_todo.estado == VERDE
    falta_una = riesgo_total_abierto([100000], equity, sin_dato=1)
    assert falta_una.estado == SIN_DATOS, falta_una.estado
    assert "Falta cargar el riesgo en 1" in falta_una.detalle

    # el caso exacto que se escapaba: NADA cargado y ninguna suma
    vacio = riesgo_total_abierto([], equity, sin_dato=2)
    assert vacio.estado == SIN_DATOS, "una lista vacía con posiciones abiertas no es 'sin riesgo'"

    # margen: mismo criterio
    assert margen_por_subyacente({"EURUSD": 100000}, equity, sin_dato=0).estado == VERDE
    sin_m = margen_por_subyacente({"EURUSD": 100000}, equity, sin_dato=1)
    assert sin_m.estado == SIN_DATOS, sin_m.estado
    assert "Falta cargar el margen en 1" in sin_m.detalle
    assert margen_por_subyacente({}, equity, sin_dato=3).estado == SIN_DATOS
