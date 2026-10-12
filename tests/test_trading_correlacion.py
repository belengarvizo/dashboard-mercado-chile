"""Correlación entre pares y riesgo agrupado.

LO QUE SE PRUEBA DE VERDAD. No que la matriz "se calcule", sino los bordes
donde un número plausible sería una mentira: pocas observaciones, una serie
constante, el umbral exacto, y las posiciones que se compensan en vez de
sumarse. Un riesgo agrupado mal firmado es peor que no tenerlo: diría que
hay media apuesta donde hay dos.

Módulo puro: estas pruebas no tocan la base de datos ni la red.
"""
import math
import os
import sys

FLECHA2 = "\u2194"

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal

import pandas as pd
import pytest

from trading_correlacion import (
    COMPRA,
    riesgo_agrupado_de,
    MINIMO_OBSERVACIONES,
    UMBRAL_AGRUPACION,
    VENTANA_CORRELACION,
    VENTA,
    agrupar_por_correlacion,
    correlacion_entre,
    evaluar_limites,
    matriz_correlacion,
    posiciones_desde_diario,
    resumen,
    retornos_diarios,
    riesgo_por_direccion,
)


# --------------------------------------------------------------- utilidades
def _precios(series: dict, dias: int) -> pd.DataFrame:
    """DataFrame en el formato de la base: ticker, fecha, precio_cierre."""
    fechas = pd.bdate_range("2026-01-05", periods=dias)
    filas = []
    for ticker, precios in series.items():
        for fecha, precio in zip(fechas, precios):
            filas.append({"ticker": ticker, "fecha": fecha, "precio_cierre": precio})
    return pd.DataFrame(filas)


def _acumular(retornos, inicio=1.0):
    precios, p = [inicio], inicio
    for r in retornos:
        p *= (1 + r)
        precios.append(p)
    return precios


def _retornos_variados(n):
    # Deterministas y no constantes. Sin aleatoriedad: una prueba que falla
    # una vez de cada veinte no sirve de nada.
    return [0.01 * math.sin(i) for i in range(n)]


def _matriz(valores: dict, tickers):
    """Matriz armada a mano, para poder probar el umbral EXACTO. Derivarla de
    precios no permite fijar una correlación en 0,7 clavado."""
    m = pd.DataFrame(1.0, index=list(tickers), columns=list(tickers))
    for (a, b), v in valores.items():
        m.loc[a, b] = v
        m.loc[b, a] = v
    return m


# ------------------------------------------------- la matriz y sus negativas
def test_con_pocas_observaciones_no_hay_correlacion():
    """Dos series de 5 puntos dan correlaciones altísimas por casualidad. Con
    menos del mínimo, la respuesta correcta es "no se sabe", no un número."""
    r = _retornos_variados(5)
    df = _precios({"EURUSD=X": _acumular(r), "GBPUSD=X": _acumular(r)}, 6)
    matriz, _obs = matriz_correlacion(df)
    assert correlacion_entre(matriz, "EURUSD=X", "GBPUSD=X") is None


def test_justo_en_el_minimo_de_observaciones_si_hay_correlacion():
    r = _retornos_variados(MINIMO_OBSERVACIONES)
    df = _precios({"EURUSD=X": _acumular(r), "GBPUSD=X": _acumular(r)},
                  MINIMO_OBSERVACIONES + 1)
    matriz, obs = matriz_correlacion(df)
    assert obs.loc["EURUSD=X", "GBPUSD=X"] == MINIMO_OBSERVACIONES
    assert correlacion_entre(matriz, "EURUSD=X", "GBPUSD=X") == pytest.approx(1.0)


def test_una_serie_constante_no_da_correlacion_cero_sino_nada():
    """Precio plano = desviación cero = correlación indefinida. Devolver 0
    diría "no están correlacionados", que es una afirmación distinta."""
    r = _retornos_variados(40)
    df = _precios({"EURUSD=X": _acumular(r), "USDCLP=X": [950.0] * 41}, 41)
    matriz, _obs = matriz_correlacion(df)
    assert correlacion_entre(matriz, "EURUSD=X", "USDCLP=X") is None


def test_series_identicas_y_opuestas():
    r = _retornos_variados(40)
    df = _precios({
        "EURUSD=X": _acumular(r),
        "GBPUSD=X": _acumular(r),
        "USDCHF=X": _acumular([-x for x in r]),
    }, 41)
    matriz, _obs = matriz_correlacion(df)
    assert correlacion_entre(matriz, "EURUSD=X", "GBPUSD=X") == pytest.approx(1.0)
    assert correlacion_entre(matriz, "EURUSD=X", "USDCHF=X") == pytest.approx(-1.0, abs=0.02)


def test_un_solo_ticker_no_da_matriz():
    df = _precios({"EURUSD=X": _acumular(_retornos_variados(40))}, 41)
    matriz, obs = matriz_correlacion(df)
    assert matriz.empty and obs.empty
    assert correlacion_entre(matriz, "EURUSD=X", "GBPUSD=X") is None


def test_sin_datos_no_explota():
    matriz, obs = matriz_correlacion(pd.DataFrame())
    assert matriz.empty and obs.empty
    assert retornos_diarios(None).empty


def test_la_ventana_recorta_a_las_ultimas_ruedas():
    r = _retornos_variados(VENTANA_CORRELACION + 30)
    df = _precios({"EURUSD=X": _acumular(r), "GBPUSD=X": _acumular(r)},
                  VENTANA_CORRELACION + 31)
    assert len(retornos_diarios(df)) == VENTANA_CORRELACION
    assert len(retornos_diarios(df, ventana=10)) == 10


def test_un_ticker_que_no_esta_en_la_matriz():
    r = _retornos_variados(40)
    df = _precios({"EURUSD=X": _acumular(r), "GBPUSD=X": _acumular(r)}, 41)
    matriz, _obs = matriz_correlacion(df)
    assert correlacion_entre(matriz, "EURUSD=X", "AUDNZD=X") is None


# ------------------------------------------------------------ la agrupación
def test_en_el_umbral_exacto_no_se_agrupa():
    """Decisión deliberada: el umbral es el límite de lo TOLERADO, así que
    0,7 con umbral 0,7 todavía está dentro. Un pelo más arriba, agrupa."""
    posiciones = [
        {"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("100000")},
        {"ticker": "B", "direccion": COMPRA, "riesgo_clp": Decimal("100000")},
    ]
    en_el_umbral = _matriz({("A", "B"): UMBRAL_AGRUPACION}, ["A", "B"])
    grupos = agrupar_por_correlacion(posiciones, en_el_umbral)
    assert len(grupos) == 2, "agrupó estando justo en el umbral"
    assert all(not g.es_apuesta_unica for g in grupos)

    un_pelo_mas = _matriz({("A", "B"): UMBRAL_AGRUPACION + 0.0001}, ["A", "B"])
    grupos = agrupar_por_correlacion(posiciones, un_pelo_mas)
    assert len(grupos) == 1 and grupos[0].es_apuesta_unica


def test_el_umbral_tambien_aplica_a_la_correlacion_negativa():
    posiciones = [
        {"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("100000")},
        {"ticker": "B", "direccion": COMPRA, "riesgo_clp": Decimal("100000")},
    ]
    grupos = agrupar_por_correlacion(posiciones, _matriz({("A", "B"): -0.9}, ["A", "B"]))
    assert len(grupos) == 1, "ignoró una correlación negativa fuerte"


def _agrupado(riesgo_a, dir_a, riesgo_b, dir_b, correlacion):
    """El riesgo agrupado de dos posiciones, con la correlación dada."""
    posiciones = [
        {"ticker": "A", "direccion": dir_a, "riesgo_clp": Decimal(str(riesgo_a))},
        {"ticker": "B", "direccion": dir_b, "riesgo_clp": Decimal(str(riesgo_b))},
    ]
    grupos = agrupar_por_correlacion(posiciones, _matriz({("A", "B"): correlacion},
                                                         ["A", "B"]))
    assert len(grupos) == 1, "no agrupó"
    return float(grupos[0].riesgo_agrupado)


# --- los casos límite: con correlación de +-1 la fórmula tiene que coincidir
#     exactamente con sumar o restar los montos.
def test_con_correlacion_perfecta_positiva_y_mismo_sentido_los_montos_se_suman():
    assert _agrupado(100000, COMPRA, 80000, COMPRA, 1.0) == 180000.0


def test_con_correlacion_perfecta_y_sentidos_opuestos_se_cancelan_del_todo():
    """Cobertura perfecta: es el ÚNICO caso en que la resta es correcta."""
    assert _agrupado(100000, COMPRA, 100000, VENTA, 1.0) == 0.0
    assert _agrupado(100000, COMPRA, 80000, VENTA, 1.0) == 20000.0


def test_dos_compras_con_correlacion_perfecta_negativa_tambien_se_cancelan():
    assert _agrupado(100000, COMPRA, 80000, COMPRA, -1.0) == 20000.0


# --- los tres casos con las correlaciones REALES medidas el 12-10-2026. Los
#     números van fijos en la prueba a propósito: si se leyeran del mercado,
#     la prueba cambiaría de resultado todos los días.
def test_caso_real_eurusd_y_usdchf_ambas_compra():
    """Correlación -0,706. La resta daría 20.000 y supondría cobertura
    perfecta; la cobertura real es parcial y quedan 71.442."""
    agrupado = _agrupado(100000, COMPRA, 80000, COMPRA, -0.706)
    assert agrupado == pytest.approx(71442.28, abs=0.01)
    assert agrupado > 20000 * 3, "subestimó la exposición como si cubriera del todo"
    assert agrupado < 180000, "tampoco puede ser la suma: algo se compensa"


def test_caso_real_eurusd_y_gbpusd_ambas_compra():
    """Correlación +0,868: casi la suma, pero no la suma."""
    agrupado = _agrupado(100000, COMPRA, 80000, COMPRA, 0.868)
    assert agrupado == pytest.approx(174034.48, abs=0.01)
    assert agrupado < 180000


def test_caso_real_eurusd_compra_y_gbpusd_venta():
    """Correlación +0,868 en sentidos opuestos: compensa, pero no a cero."""
    agrupado = _agrupado(100000, COMPRA, 80000, VENTA, 0.868)
    assert agrupado == pytest.approx(50119.86, abs=0.01)
    assert agrupado > 20000, "la resta diría 20.000 y sería cobertura perfecta"


def test_una_sola_posicion_en_el_grupo_es_su_propio_riesgo():
    """raíz(r x 1 x r) = |r|. Sin vecinos no hay nada que compensar."""
    sola = [{"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("100000")}]
    assert riesgo_agrupado_de(sola, _matriz({}, ["A"])) == Decimal("100000")
    sola_venta = [{"ticker": "A", "direccion": VENTA, "riesgo_clp": Decimal("37500")}]
    assert riesgo_agrupado_de(sola_venta, _matriz({}, ["A"])) == Decimal("37500")


def test_el_riesgo_agrupado_nunca_es_negativo():
    """La matriz se estima pareja por pareja, con distinta cantidad de ruedas
    en cada una, así que puede no ser semidefinida positiva y la forma
    cuadrática daría un negativo. Se acota en cero antes de la raíz."""
    posiciones = [
        {"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("100000")},
        {"ticker": "B", "direccion": COMPRA, "riesgo_clp": Decimal("100000")},
        {"ticker": "C", "direccion": COMPRA, "riesgo_clp": Decimal("100000")},
    ]
    # Correlaciones imposibles a la vez (A~B y A~C casi perfectas, B~C opuesta):
    # ninguna matriz real es así, pero la estimación pareja a pareja puede
    # producirla.
    incoherente = _matriz({("A", "B"): 0.99, ("A", "C"): 0.99, ("B", "C"): -0.99},
                          ["A", "B", "C"])
    assert riesgo_agrupado_de(posiciones, incoherente) >= 0


def test_dos_ventas_de_pares_correlacionados_suman():
    assert _agrupado(70000, VENTA, 70000, VENTA, 0.9) == pytest.approx(136455.12,
                                                                       abs=0.01)
    assert _agrupado(70000, VENTA, 70000, VENTA, 1.0) == 140000.0


def test_el_grupo_es_transitivo():
    """Si A se parece a B y B a C, los tres son la misma apuesta aunque A y C
    no lleguen al umbral entre sí."""
    posiciones = [
        {"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("10000")},
        {"ticker": "B", "direccion": COMPRA, "riesgo_clp": Decimal("10000")},
        {"ticker": "C", "direccion": COMPRA, "riesgo_clp": Decimal("10000")},
    ]
    matriz = _matriz({("A", "B"): 0.85, ("B", "C"): 0.85, ("A", "C"): 0.10},
                     ["A", "B", "C"])
    grupos = agrupar_por_correlacion(posiciones, matriz)
    assert len(grupos) == 1
    assert len(grupos[0].posiciones) == 3


def test_una_pareja_sin_correlacion_se_rellena_con_la_peor():
    """El lado prudente es sobreestimar la apuesta, no subestimarla: una
    pareja sin dato se completa con el valor que hace crecer el riesgo
    (+1 si van en el mismo sentido). Rellenar con 0 diría "son
    independientes", que es una afirmación que no se tiene."""
    posiciones = [
        {"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("50000")},
        {"ticker": "B", "direccion": COMPRA, "riesgo_clp": Decimal("50000")},
        {"ticker": "C", "direccion": COMPRA, "riesgo_clp": Decimal("50000")},
    ]
    matriz = _matriz({("A", "B"): 0.9, ("B", "C"): 0.9}, ["A", "B", "C"])
    matriz.loc["A", "C"] = float("nan")
    matriz.loc["C", "A"] = float("nan")
    grupos = agrupar_por_correlacion(posiciones, matriz)
    assert grupos[0].riesgo_agrupado == pytest.approx(Decimal("146628.78"), abs=0.01)

    # Con el dato presente y bajo, el riesgo baja: el relleno no es neutro.
    matriz.loc["A", "C"] = matriz.loc["C", "A"] = 0.10
    con_dato = agrupar_por_correlacion(posiciones, matriz)[0].riesgo_agrupado
    assert con_dato < Decimal("146628.78")
    assert any("sin dato" in d for d in grupos[0].detalle)


def test_una_posicion_sola_es_su_propio_riesgo_y_no_es_apuesta_unica():
    posiciones = [{"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("40000")}]
    grupos = agrupar_por_correlacion(posiciones, _matriz({}, ["A"]))
    assert len(grupos) == 1
    assert grupos[0].riesgo_agrupado == Decimal("40000")
    assert not grupos[0].es_apuesta_unica


def test_sin_posiciones_no_hay_grupos():
    assert agrupar_por_correlacion([], _matriz({}, ["A"])) == []
    assert agrupar_por_correlacion(
        [{"ticker": "A", "direccion": COMPRA, "riesgo_clp": None}], _matriz({}, ["A"])) == []


def test_sin_matriz_cada_posicion_queda_sola():
    """Si todavía no hay precios cargados, el riesgo agrupado no puede
    inventar grupos."""
    posiciones = [
        {"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("10000")},
        {"ticker": "B", "direccion": COMPRA, "riesgo_clp": Decimal("10000")},
    ]
    grupos = agrupar_por_correlacion(posiciones, pd.DataFrame())
    assert len(grupos) == 2


def test_el_detalle_explica_cada_pareja_sin_posicion_de_referencia():
    """El signo de cada pareja sale de su propio término cruzado, así que no
    hay ninguna posición privilegiada."""
    posiciones = [
        {"ticker": "A", "instrumento": "EURUSD", "direccion": COMPRA,
         "riesgo_clp": Decimal("10000")},
        {"ticker": "B", "instrumento": "GBPUSD", "direccion": VENTA,
         "riesgo_clp": Decimal("10000")},
    ]
    grupos = agrupar_por_correlacion(posiciones, _matriz({("A", "B"): 0.9}, ["A", "B"]))
    detalle = " ".join(grupos[0].detalle)
    assert "referencia" not in detalle, "quedó el supuesto de la posición de referencia"
    assert "EURUSD compra 10,000 CLP" in detalle
    assert "GBPUSD venta 10,000 CLP" in detalle
    assert f"EURUSD {FLECHA2} GBPUSD" in detalle
    assert "+0.90" in detalle and "se compensan" in detalle


# ----------------------------------------------- dirección, resumen, límites
def test_riesgo_por_direccion_separa_los_lados():
    posiciones = [
        {"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("30000")},
        {"ticker": "B", "direccion": COMPRA, "riesgo_clp": Decimal("20000")},
        {"ticker": "C", "direccion": VENTA, "riesgo_clp": Decimal("15000")},
        {"ticker": "D", "direccion": VENTA, "riesgo_clp": None},
    ]
    totales = riesgo_por_direccion(posiciones)
    assert totales[COMPRA] == Decimal("50000")
    assert totales[VENTA] == Decimal("15000")


def test_el_resumen_toma_el_mayor_grupo_no_la_suma():
    """El número que importa es la apuesta más grande que está corriendo."""
    posiciones = [
        {"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("100000")},
        {"ticker": "B", "direccion": COMPRA, "riesgo_clp": Decimal("100000")},
        {"ticker": "C", "direccion": COMPRA, "riesgo_clp": Decimal("50000")},
    ]
    matriz = _matriz({("A", "B"): 0.9, ("A", "C"): 0.1, ("B", "C"): 0.1},
                     ["A", "B", "C"])
    bruto, mayor, racimos = resumen(agrupar_por_correlacion(posiciones, matriz))
    assert bruto == Decimal("250000")
    assert mayor == pytest.approx(Decimal("194935.89"), abs=0.01)
    assert len(racimos) == 1


def test_los_limites_avisan_y_nunca_bloquean():
    posiciones = [
        {"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("150000")},
        {"ticker": "B", "direccion": COMPRA, "riesgo_clp": Decimal("150000")},
    ]
    grupos = agrupar_por_correlacion(posiciones, _matriz({("A", "B"): 0.9}, ["A", "B"]))

    rojas = evaluar_limites(grupos, posiciones, 200000, 1000000)
    assert any(a.nivel == "rojo" for a in rojas)
    assert any("una sola apuesta" in a.texto for a in rojas)

    amarillas = evaluar_limites(grupos, posiciones, 350000, 1000000)
    assert [a.nivel for a in amarillas] == ["amarillo"]

    assert evaluar_limites(grupos, posiciones, 500000, 1000000) == []


def test_el_limite_por_direccion_mira_el_lado_del_mercado():
    posiciones = [
        {"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("100000")},
        {"ticker": "B", "direccion": COMPRA, "riesgo_clp": Decimal("100000")},
    ]
    grupos = agrupar_por_correlacion(posiciones, _matriz({("A", "B"): 0.1}, ["A", "B"]))
    alertas = evaluar_limites(grupos, posiciones, None, 150000)
    assert any(a.nivel == "rojo" and "compras" in a.texto for a in alertas)


def test_sin_topes_no_hay_alertas():
    posiciones = [{"ticker": "A", "direccion": COMPRA, "riesgo_clp": Decimal("999999")}]
    grupos = agrupar_por_correlacion(posiciones, _matriz({}, ["A"]))
    assert evaluar_limites(grupos, posiciones, None, None) == []


# ----------------------------------------------------- lectura del diario
def test_las_posiciones_sin_ticker_o_sin_riesgo_quedan_afuera_y_se_cuentan():
    """Callarlas haría que el riesgo agrupado se leyera como completo."""
    abiertas = pd.DataFrame([
        {"instrumento": "EURUSD", "direccion": COMPRA, "riesgo_clp": 100000},
        {"instrumento": "ORO", "direccion": COMPRA, "riesgo_clp": 50000},
        {"instrumento": "GBPUSD", "direccion": VENTA, "riesgo_clp": None},
    ])
    mapa = {"EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X"}
    adentro, afuera = posiciones_desde_diario(abiertas, mapa)
    assert [p["ticker"] for p in adentro] == ["EURUSD=X"]
    assert sorted(afuera) == ["GBPUSD", "ORO"]


def test_un_riesgo_nulo_de_la_base_llega_como_nan_y_no_como_none():
    """pandas convierte el NULL de SQL en NaN, que es un float: un chequeo
    `is None` no lo ve. Ya pasó antes en este módulo."""
    abiertas = pd.DataFrame([
        {"instrumento": "EURUSD", "direccion": COMPRA, "riesgo_clp": 100000.0},
        {"instrumento": "GBPUSD", "direccion": VENTA, "riesgo_clp": float("nan")},
    ])
    adentro, afuera = posiciones_desde_diario(abiertas, {"EURUSD": "EURUSD=X",
                                                        "GBPUSD": "GBPUSD=X"})
    assert len(adentro) == 1
    assert afuera == ["GBPUSD"]


def test_un_ticker_nulo_en_el_catalogo_queda_afuera():
    abiertas = pd.DataFrame([
        {"instrumento": "BITCOIN", "direccion": COMPRA, "riesgo_clp": 100000.0},
    ])
    adentro, afuera = posiciones_desde_diario(abiertas, {"BITCOIN": float("nan")})
    assert adentro == [] and afuera == ["BITCOIN"]


def test_diario_vacio():
    adentro, afuera = posiciones_desde_diario(pd.DataFrame(), {})
    assert adentro == [] and afuera == []


# ------------------------------------------- el índice dólar y su convención
def test_el_indice_dolar_queda_fuera_de_la_matriz():
    """Su serie no comparte convención de fecha con la de los pares =X.

    Verificado sobre los datos guardados: las identidades de cruce entre los
    pares calzan en desfase 0 (EURGBP contra EURUSD-GBPUSD, +0,9954), pero un
    DXY sintético armado con los pesos de la canasta desde esos mismos pares
    calza con el índice guardado en desfase de una rueda (+0,9415) y no en la
    misma fila (+0,0377). Correlacionarlo igual daba -0,05 contra EURUSD, que
    se leería como "no tienen relación" cuando el euro pesa más de la mitad
    del índice.
    """
    r = _retornos_variados(40)
    df = _precios({
        "EURUSD=X": _acumular(r),
        "GBPUSD=X": _acumular(r),
        "DX-Y.NYB": _acumular([-x for x in r], inicio=100.0),
    }, 41)
    matriz, obs = matriz_correlacion(df)
    assert "DX-Y.NYB" not in matriz.index
    assert "DX-Y.NYB" not in matriz.columns
    assert "DX-Y.NYB" not in obs.index
    assert "EURUSD=X" in matriz.index, "se llevó puestos los pares que sí sirven"
    assert correlacion_entre(matriz, "EURUSD=X", "DX-Y.NYB") is None


def test_la_exclusion_es_una_politica_y_no_un_hardcodeo():
    """Si alguna vez el cron guarda el índice con la convención de los pares,
    basta pasar `excluir` vacío: no hay que editar la función."""
    r = _retornos_variados(40)
    df = _precios({"EURUSD=X": _acumular(r),
                   "DX-Y.NYB": _acumular([-x for x in r], inicio=100.0)}, 41)
    matriz, _obs = matriz_correlacion(df, excluir=frozenset())
    assert correlacion_entre(matriz, "EURUSD=X", "DX-Y.NYB") == pytest.approx(-1.0, abs=0.02)


def test_una_posicion_en_el_indice_cuenta_en_el_riesgo_pero_no_se_agrupa():
    """No se la esconde: suma en el riesgo total y por dirección. Lo único que
    no se hace es afirmar con qué par se parece."""
    r = _retornos_variados(40)
    df = _precios({
        "EURUSD=X": _acumular(r),
        "DX-Y.NYB": _acumular([-x for x in r], inicio=100.0),
    }, 41)
    matriz, _obs = matriz_correlacion(df)
    posiciones = [
        {"ticker": "EURUSD=X", "instrumento": "EURUSD", "direccion": COMPRA,
         "riesgo_clp": Decimal("100000")},
        {"ticker": "DX-Y.NYB", "instrumento": "USDIDX", "direccion": COMPRA,
         "riesgo_clp": Decimal("60000")},
    ]
    grupos = agrupar_por_correlacion(posiciones, matriz)
    assert len(grupos) == 2, "agrupó el índice con un par sin poder saberlo"
    bruto, mayor, racimos = resumen(grupos)
    assert bruto == Decimal("160000"), "el riesgo del índice no se contó"
    assert racimos == []
    assert riesgo_por_direccion(posiciones)[COMPRA] == Decimal("160000")


if __name__ == "__main__":
    print("Correr con pytest: python -m pytest tests/test_trading_correlacion.py")
