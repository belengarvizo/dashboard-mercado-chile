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


# ================================ límite de riesgo por operación (Parte II.5)
# Es un límite PROPIO, no del reglamento del torneo. Avisa y nunca bloquea.
# Lo que se prueba son los bordes donde un veredicto plausible sería falso:
# sin capital, sin riesgo, justo en el límite y con el límite editado.
from trading_reglas import (  # noqa: E402
    AMARILLO,
    TOPE_RIESGO_ABIERTO_POR_DEFECTO,
    TOPE_RIESGO_POR_OPERACION_POR_DEFECTO,
    riesgo_por_operacion,
)

EQUITY = Decimal("10000000")
TOPE_2 = TOPE_RIESGO_POR_OPERACION_POR_DEFECTO       # 2% -> 200.000 sobre 10M


def test_el_tope_por_operacion_por_defecto_es_el_2_por_ciento():
    assert TOPE_RIESGO_POR_OPERACION_POR_DEFECTO == Decimal("0.02")
    # Y por debajo del presupuesto de riesgo de toda la cuenta: una sola
    # operación no debería agotarlo sola.
    assert TOPE_RIESGO_POR_OPERACION_POR_DEFECTO < TOPE_RIESGO_ABIERTO_POR_DEFECTO


def test_sin_riesgo_cargado_no_se_puede_evaluar():
    """Gris, no verde: verde afirmaría que está dentro del límite."""
    for vacio in (None, 0, Decimal(0), -5000, float("nan")):
        c = riesgo_por_operacion(vacio, EQUITY)
        assert c.estado == SIN_DATOS, f"{vacio!r} dio {c.estado}"


def test_sin_limite_tampoco():
    assert riesgo_por_operacion(100000, EQUITY, None).estado == SIN_DATOS
    assert riesgo_por_operacion(100000, EQUITY, Decimal(0)).estado == SIN_DATOS
    assert riesgo_por_operacion(100000, EQUITY, float("nan")).estado == SIN_DATOS


def test_sin_equity_usa_el_capital_inicial_y_lo_dice():
    """Antes de registrar el primer equity, el capital del torneo es el
    inicial. Apagar el control sería peor que calcularlo sobre ese número,
    pero hay que decir cuál se usó."""
    c = riesgo_por_operacion(Decimal("100000"), None)
    assert c.estado == VERDE
    assert "capital inicial" in c.detalle
    assert f"{CAPITAL_INICIAL_CLP:,.0f}" in c.detalle
    # con equity cargado no aparece esa aclaración
    con_equity = riesgo_por_operacion(Decimal("100000"), EQUITY)
    assert "capital inicial" not in con_equity.detalle


def test_justo_en_el_limite_queda_amarillo_y_no_rojo():
    """No lo superó, pero no queda margen. Para el rojo se exige
    estrictamente mayor."""
    en_el_limite = riesgo_por_operacion(Decimal("200000"), EQUITY, TOPE_2)
    assert en_el_limite.estado == AMARILLO

    un_peso_mas = riesgo_por_operacion(Decimal("200001"), EQUITY, TOPE_2)
    assert un_peso_mas.estado == ROJO


def test_el_amarillo_empieza_pasado_el_80_por_ciento_del_limite():
    justo_en_el_80 = riesgo_por_operacion(Decimal("160000"), EQUITY, TOPE_2)
    assert justo_en_el_80.estado == VERDE, "el 80% exacto todavía es verde"
    assert riesgo_por_operacion(Decimal("160001"), EQUITY, TOPE_2).estado == AMARILLO
    assert riesgo_por_operacion(Decimal("100000"), EQUITY, TOPE_2).estado == VERDE


def test_editar_el_limite_cambia_el_veredicto():
    """El mismo riesgo, dos límites distintos."""
    riesgo = Decimal("150000")
    assert riesgo_por_operacion(riesgo, EQUITY, Decimal("0.02")).estado == VERDE
    assert riesgo_por_operacion(riesgo, EQUITY, Decimal("0.01")).estado == ROJO
    assert riesgo_por_operacion(riesgo, EQUITY, Decimal("0.016")).estado == AMARILLO


def test_el_detalle_dice_los_pesos_y_el_porcentaje():
    c = riesgo_por_operacion(Decimal("250000"), EQUITY, TOPE_2)
    assert "250,000 CLP" in c.detalle
    assert "2.50%" in c.detalle, c.detalle
    assert "10,000,000" in c.detalle
    assert "200,000" in c.detalle and "2.0%" in c.detalle


def test_la_nota_dice_cuantas_operaciones_llevan_al_piso():
    """(10.000.000 - 5.000.000) / 100.000 = 50."""
    c = riesgo_por_operacion(Decimal("100000"), EQUITY, TOPE_2)
    assert "50 operaciones" in c.nota, c.nota
    assert f"{PISO_EQUITY_CLP:,.0f}" in c.nota
    # con el doble de riesgo, la mitad de operaciones
    doble = riesgo_por_operacion(Decimal("200000"), EQUITY, TOPE_2)
    assert "25 operaciones" in doble.nota, doble.nota


def test_si_ya_estas_en_el_piso_lo_dice_en_vez_de_contar():
    c = riesgo_por_operacion(Decimal("100000"), PISO_EQUITY_CLP, TOPE_2)
    assert "Ya estás en el piso" in c.nota, c.nota
    bajo_el_piso = riesgo_por_operacion(Decimal("100000"), Decimal("4000000"), TOPE_2)
    assert "Ya estás en el piso" in bajo_el_piso.nota


def test_siempre_dice_que_el_limite_es_propio():
    """No sale del reglamento del torneo, y confundirlo sería grave: XTB no
    descalifica por esto."""
    for riesgo in (Decimal("50000"), Decimal("250000"), None):
        c = riesgo_por_operacion(riesgo, EQUITY, TOPE_2)
        assert "no del reglamento del torneo" in c.nota, c.nota


def test_el_chequeo_describe_y_no_bloquea():
    """Devuelve un Chequeo igual que el resto del panel: no tiene forma de
    impedir nada."""
    c = riesgo_por_operacion(Decimal("500000"), EQUITY, TOPE_2)
    assert c.estado == ROJO
    assert c.valor == Decimal("500000")
    assert c.limite == Decimal("200000")
    assert c.nombre == "Riesgo de esta operación"
