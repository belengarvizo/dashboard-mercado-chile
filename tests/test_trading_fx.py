"""Valida el cálculo del valor del pip y del tamaño de posición en CLP.

Un error acá se traduce uno a uno en un error de tamaño de posición, y pasarse
del 30% del margen por subyacente descalifica del torneo. Por eso se prueban
los bordes y, sobre todo, que el módulo SE NIEGUE a calcular cuando le falta
un dato en vez de asumirlo.
"""
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from trading_fx import (
    DIAS_TASA_VIEJA,
    es_nulo,
    divisas_del_par,
    lotes_para_riesgo,
    tasa_a_clp,
    valor_pip_clp,
    valor_posicion_clp,
)

HOY = date(2026, 10, 11)
# Cotizaciones de referencia, fijas, para que los tests no dependan de la red.
COT = {
    "USDCLP=X": (Decimal("975.06"), HOY),
    "EURUSD=X": (Decimal("1.1217"), HOY),
    "GBPUSD=X": (Decimal("1.3247"), HOY),
    "USDJPY=X": (Decimal("158.11"), HOY),
    "USDCAD=X": (Decimal("1.3700"), HOY),
}


def test_separa_las_divisas_del_par():
    assert divisas_del_par("EURUSD") == ("EUR", "USD")
    assert divisas_del_par("GBPJPY") == ("GBP", "JPY")
    # USDIDX es un índice, no un par: no tiene divisa de cotización ni pip.
    assert divisas_del_par("USDIDX") is None
    assert divisas_del_par("US500") is None
    assert divisas_del_par("") is None


def test_el_ticket_de_eurusd_implica_una_tasa_coherente_con_el_banco_central():
    """ESTA PRUEBA NO CONFIRMA LA FÓRMULA, y vale decir por qué.

    Del ticket real (0,01 lotes de EURUSD a 1,11995 = 1.099.995 CLP) se puede
    despejar el USD/CLP implícito. Reproducir el valor de posición CON esa
    tasa sería circular, porque la tasa salió de ese mismo valor.

    Lo que sí es evidencia: la tasa implícita cae a 0,06% del dólar observado
    del Banco Central del 09-10-2026 (981,61), que es una fuente
    independiente; y por descarte, ningún otro tamaño de contrato da una tasa
    creíble (con 10.000 unidades saldría 9.822, con 1.000.000 saldría 98).
    """
    valor_posicion_ticket = Decimal("1099995")
    precio_ticket = Decimal("1.11995")
    implicita = valor_posicion_ticket / (Decimal("0.01") * Decimal("100000") * precio_ticket)

    observado_bcch = Decimal("981.61")
    diferencia = abs(implicita - observado_bcch) / observado_bcch
    assert diferencia < Decimal("0.01"), (
        f"la tasa implícita del ticket ({implicita:.2f}) se despegó del dólar "
        f"observado del BCCh ({observado_bcch}): {diferencia * 100:.2f}%")

    # El argumento por descarte: solo 100.000 unidades da una tasa creíble.
    for tamano, creible in [(10_000, False), (100_000, True), (1_000_000, False)]:
        tasa = valor_posicion_ticket / (Decimal("0.01") * Decimal(tamano) * precio_ticket)
        assert (Decimal(900) < tasa < Decimal(1100)) == creible, (
            f"con contrato de {tamano} la tasa implícita sería {tasa:.0f}")


def test_valor_de_posicion_usa_la_divisa_base():
    r = valor_posicion_clp("EURUSD", "0.01",
                           Decimal("1.11995"),
                           {"EURUSD=X": (Decimal("1.11995"), HOY),
                            "USDCLP=X": (Decimal("982.18"), HOY)}, HOY)
    # 1.000 EUR x (1,11995 x 982,18) = 1.099.992
    assert abs(r.valor - Decimal("1099992")) < Decimal("2"), r.valor
    assert any("EUR/CLP" in p for p in r.pasos), "falta el paso de conversión en el desglose"


def test_pip_de_un_par_que_cotiza_en_usd():
    r = valor_pip_clp("EURUSD", "0.01", "0.0001", COT, HOY)
    # 1.000 EUR x 0,0001 = 0,1 USD -> x 975,06 = 97,51 CLP
    assert abs(r.valor - Decimal("97.51")) < Decimal("0.05"), r.valor


def test_pip_encadenado_cuando_la_cotizacion_no_es_usd():
    """USDJPY cotiza en JPY: hay que pasar por USD para llegar a CLP."""
    r = valor_pip_clp("USDJPY", "0.01", "0.01", COT, HOY)
    # 1.000 USD x 0,01 = 10 JPY ; JPY/CLP = 975,06/158,11 = 6,167 -> 61,67 CLP
    assert abs(r.valor - Decimal("61.67")) < Decimal("0.1"), r.valor
    assert any("JPY/USD" in p for p in r.pasos), "el desglose debe mostrar la cadena"

    r2 = valor_pip_clp("EURGBP", "0.01", "0.0001", COT, HOY)
    # 1.000 EUR x 0,0001 = 0,1 GBP ; GBP/CLP = 1,3247 x 975,06 = 1291,7 -> 129,17
    assert abs(r2.valor - Decimal("129.17")) < Decimal("0.1"), r2.valor


def test_se_niega_cuando_el_pip_esta_pendiente():
    """El caso que motivó todo: USDCLP cotiza a 975, así que un pip de 0,0001
    sería absurdo. Antes que adivinar, no calcula."""
    for par in ("USDCLP", "USDBRL", "USDMXN"):
        r = valor_pip_clp(par, "0.01", None, COT, HOY)
        assert r.valor is None, f"{par} calculó un valor sin tener el pip"
        assert "PENDIENTE" in r.motivo, r.motivo


def test_se_niega_cuando_falta_la_tasa_de_conversion():
    sin_usdclp = {"EURUSD=X": (Decimal("1.1217"), HOY)}
    r = valor_pip_clp("EURUSD", "0.01", "0.0001", sin_usdclp, HOY)
    assert r.valor is None
    assert "a mano" in r.motivo, r.motivo


def test_la_tasa_manual_pisa_la_de_la_base():
    r = valor_pip_clp("EURUSD", "0.01", "0.0001", COT, HOY, tasa_manual=Decimal("1000"))
    assert abs(r.valor - Decimal("100")) < Decimal("0.01"), r.valor
    assert any("a mano" in p for p in r.pasos)


def test_avisa_cuando_la_tasa_de_la_base_esta_vieja():
    vieja = HOY - timedelta(days=DIAS_TASA_VIEJA + 1)
    cot = dict(COT, **{"USDCLP=X": (Decimal("975.06"), vieja)})
    r = valor_pip_clp("EURUSD", "0.01", "0.0001", cot, HOY)
    assert r.valor is not None, "una tasa vieja avisa, no bloquea"
    assert any("revisala contra XTB" in a for a in r.avisos), r.avisos

    # Y en el borde exacto NO avisa, para no gritar todos los lunes.
    justo = HOY - timedelta(days=DIAS_TASA_VIEJA)
    r2 = valor_pip_clp("EURUSD", "0.01", "0.0001",
                       dict(COT, **{"USDCLP=X": (Decimal("975.06"), justo)}), HOY)
    assert not any("revisala" in a for a in r2.avisos), r2.avisos


def test_marca_como_supuesto_el_contrato_de_los_pares_no_verificados():
    solo_eurusd = valor_pip_clp("EURUSD", "0.01", "0.0001", COT, HOY)
    assert not any("SUPUESTO" in a for a in solo_eurusd.avisos), (
        "EURUSD es el único con el contrato contrastado contra un ticket")

    otro = valor_pip_clp("GBPUSD", "0.01", "0.0001", COT, HOY)
    assert any("SUPUESTO" in a for a in otro.avisos), otro.avisos


def test_lotes_para_un_riesgo_dado():
    # 1 lote de EURUSD = 9.750,6 CLP/pip ; con stop de 30 pips = 292.518 CLP
    # Para arriesgar 100.000 CLP -> 0,3419 lotes
    r = lotes_para_riesgo("EURUSD", 100000, 30, "0.0001", COT, HOY)
    assert abs(r.valor - Decimal("0.3419")) < Decimal("0.001"), r.valor

    # el doble de stop, la mitad de lotes
    r2 = lotes_para_riesgo("EURUSD", 100000, 60, "0.0001", COT, HOY)
    assert abs(r2.valor - r.valor / 2) < Decimal("0.001")


def test_lotes_rechaza_un_stop_invalido():
    for distancia in (0, -10):
        r = lotes_para_riesgo("EURUSD", 100000, distancia, "0.0001", COT, HOY)
        assert r.valor is None, f"aceptó una distancia de {distancia} pips"


def test_la_cadena_a_clp_queda_documentada_paso_a_paso():
    """El desglose es el producto, no un extra: es lo que permite auditar la
    cuenta contra el ticket de XTB."""
    tasa = tasa_a_clp("JPY", COT)
    assert tasa is not None
    assert len(tasa.pasos) >= 3, tasa.pasos
    assert any("158.11" in p for p in tasa.pasos), "falta la cotización usada"
    assert any("975.06" in p for p in tasa.pasos), "falta el USD/CLP usado"


if __name__ == "__main__":
    for nombre, funcion in sorted(list(globals().items())):
        if nombre.startswith("test_"):
            funcion()
            print("OK:", nombre)


def test_un_nan_de_la_base_cuenta_como_dato_faltante():
    """Los datos llegan de PostgreSQL vía pandas, y un NULL de SQL se vuelve
    NaN (un float), no None. Con un chequeo `is None` a secas, el pip sin
    cargar pasaba el filtro y el cálculo devolvía NaN: mostraba "nan lotes"
    en vez de negarse. Lo encontró un AppTest, no la revisión."""
    nan = float("nan")
    assert es_nulo(nan) and es_nulo(None)
    assert not es_nulo(0.0001) and not es_nulo(Decimal("0.0001"))

    r = valor_pip_clp("USDCLP", "0.01", nan, COT, HOY)
    assert r.valor is None, f"calculó {r.valor} con un pip NaN"
    assert "PENDIENTE" in r.motivo

    # y lo mismo en el camino de los lotes, que es el que se usa para operar
    r2 = lotes_para_riesgo("USDCLP", 100000, 30, nan, COT, HOY)
    assert r2.valor is None, f"calculó {r2.valor} lotes con un pip NaN"
