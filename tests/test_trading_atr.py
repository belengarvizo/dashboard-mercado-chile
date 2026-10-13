"""ATR de Wilder (14) sobre el rango verdadero.

Lo que se prueba son los bordes donde un número plausible sería falso: la
vela del día en curso contándose como rueda cerrada, menos datos de los que
hace falta, un par sin tamaño de pip, y huecos entre ruedas que inflan el
rango verdadero sin que se note.

Módulo puro: estas pruebas no tocan la base de datos ni la red.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from trading_atr import (
    AVISO_SIN_PIP,
    UMBRAL_INFLACION_MATERIAL,
    inflacion_por_dias_sospechosos,
    FACTOR_DIA_SOSPECHOSO,
    dias_sospechosos,
    rango_del_dia,
    cierres_fuera_de_rango,
    RUEDAS_PARA_DESACTUALIZADO,
    MINIMO_RUEDAS,
    MULTIPLO_STOP_POR_DEFECTO,
    PERIODO_ATR,
    atr_de_rangos,
    atr_wilder,
    contar_huecos,
    filas_validas,
    rango_verdadero,
    solo_ruedas_cerradas,
    stop_demasiado_cerca,
    stop_sugerido,
)

HOY = date(2026, 10, 12)


def _velas(n, maximo=1.1050, minimo=1.1000, cierre=1.1025, desde=None):
    """n ruedas consecutivas, todas con el mismo rango."""
    inicio = desde or (HOY - timedelta(days=n))
    return [{"fecha": inicio + timedelta(days=i), "maximo": maximo,
             "minimo": minimo, "cierre": cierre} for i in range(n)]


def _historico(fechas, tz="Europe/London"):
    idx = pd.to_datetime(fechas)
    if tz:
        idx = idx.tz_localize(tz)
    return pd.DataFrame(
        {"High": [1.11] * len(idx), "Low": [1.10] * len(idx),
         "Close": [1.105] * len(idx)}, index=idx)


# ------------------------------------------- la vela del día en curso
def test_la_vela_de_hoy_no_cuenta_como_rueda_cerrada():
    """Yahoo entrega una fila de hoy con lo que va corrido de la sesión.
    Guardarla sería contar medio día como rueda completa y el ATR quedaría
    subestimado justo en el dato más reciente."""
    h = _historico(["2026-10-08", "2026-10-09", "2026-10-12"])
    cerradas = solo_ruedas_cerradas(h, HOY)
    assert len(cerradas) == 2
    assert pd.to_datetime(cerradas.index).tz_localize(None).date.max() == date(2026, 10, 9)


def test_una_vela_futura_tampoco():
    h = _historico(["2026-10-09", "2026-10-13"])
    assert len(solo_ruedas_cerradas(h, HOY)) == 1


def test_sin_vela_de_hoy_no_descarta_nada():
    h = _historico(["2026-10-08", "2026-10-09"])
    assert len(solo_ruedas_cerradas(h, HOY)) == 2


def test_funciona_con_indice_sin_zona_horaria():
    h = _historico(["2026-10-09", "2026-10-12"], tz=None)
    assert len(solo_ruedas_cerradas(h, HOY)) == 1


def test_sin_datos_no_explota():
    assert len(solo_ruedas_cerradas(pd.DataFrame(), HOY)) == 0
    assert len(solo_ruedas_cerradas(None, HOY)) == 0


# ----------------------------------------------------- filas utilizables
def test_se_descartan_los_NaN_y_los_maximos_menores_que_el_minimo():
    df = pd.DataFrame({
        "High":  [1.11, float("nan"), 1.09, 1.11],
        "Low":   [1.10, 1.10, 1.10, 1.10],
        "Close": [1.105, 1.105, 1.105, 1.105],
    })
    #            ok     NaN         max<min   ok
    assert len(filas_validas(df)) == 2


def test_el_cierre_fuera_de_su_rango_NO_descarta_la_rueda():
    """Descartar la sesión entera pierde una rueda real Y abre un hueco, y
    el hueco infla el rango verdadero del día siguiente porque el "cierre
    previo" pasa a ser el de hace varios días. El remedio sería peor.

    Medido sobre un año de los 14 pares: 128 de 3.605 ruedas vienen así, casi
    todas por diferencias de 0,005% a 0,04% del precio, porque Yahoo toma el
    cierre de los pares =X en un momento distinto que el máximo y el mínimo.
    """
    df = pd.DataFrame({
        "High":  [1.1100, 1.1100, 1.1100],
        "Low":   [1.1000, 1.1000, 1.1000],
        "Close": [1.1050, 1.0999, 1.1101],   # dentro, apenas abajo, apenas arriba
    })
    assert len(filas_validas(df)) == 3, "no debe tirar ninguna"
    assert cierres_fuera_de_rango(df) == 2


def test_contar_cierres_fuera_de_rango_en_los_casos_vacios():
    assert cierres_fuera_de_rango(pd.DataFrame()) == 0
    assert cierres_fuera_de_rango(None) == 0
    assert cierres_fuera_de_rango(pd.DataFrame({"Close": [1.1]})) == 0


def test_sin_las_columnas_necesarias_devuelve_vacio():
    assert filas_validas(pd.DataFrame({"Close": [1.1]})).empty
    assert filas_validas(pd.DataFrame()).empty
    assert filas_validas(None).empty


# ------------------------------------------------------ rango verdadero
def test_la_primera_rueda_no_tiene_rango_verdadero():
    """Sin cierre previo no hay contra qué medir el hueco."""
    tr = rango_verdadero([10, 11], [8, 9], [9, 10])
    assert pd.isna(tr.iloc[0])
    assert tr.iloc[1] == pytest.approx(2.0)


def test_el_hueco_entre_ruedas_manda_sobre_el_rango_del_dia():
    """Un par que abre lejos del cierre anterior y después se mueve poco NO
    es un par tranquilo: el rango verdadero lo captura."""
    #  rueda 1: cierre 10
    #  rueda 2: máx 20, mín 19 -> rango del día 1, pero |20-10| = 10
    tr = rango_verdadero([10, 20], [8, 19], [10, 19.5])
    assert tr.iloc[1] == pytest.approx(10.0)


def test_el_hueco_hacia_abajo_tambien():
    tr = rango_verdadero([10, 4], [8, 3], [10, 3.5])
    assert tr.iloc[1] == pytest.approx(7.0)  # |3 - 10|


# --------------------------------------------------------- ATR de Wilder
def test_con_menos_de_catorce_rangos_no_hay_atr():
    assert atr_wilder([1.0] * (PERIODO_ATR - 1)) is None
    assert atr_wilder([]) is None
    assert atr_wilder([float("nan")] * 20) is None


def test_con_exactamente_catorce_el_atr_es_la_media_simple():
    """La semilla de Wilder es la media simple de los primeros 14."""
    assert atr_wilder([2.0] * PERIODO_ATR) == Decimal("2")
    rangos = list(range(1, PERIODO_ATR + 1))  # 1..14, media 7,5
    assert float(atr_wilder(rangos)) == pytest.approx(7.5)


def test_el_suavizado_de_wilder_pondera_13_a_1():
    """ATR = (ATR_previo * 13 + rango_nuevo) / 14. Con semilla 1 y un rango
    de 15: (1*13 + 15) / 14 = 2."""
    rangos = [1.0] * PERIODO_ATR + [15.0]
    assert float(atr_wilder(rangos)) == pytest.approx(2.0)


def test_el_atr_de_una_serie_constante_es_esa_constante():
    assert float(atr_wilder([3.0] * 60)) == pytest.approx(3.0)


def test_wilder_reacciona_menos_que_la_media_simple_a_un_salto():
    """Es la razón de ser del suavizado: un día extremo no arrastra el
    indicador de golpe."""
    rangos = [1.0] * 30 + [100.0]
    wilder = float(atr_wilder(rangos))
    simple = sum(rangos[-PERIODO_ATR:]) / PERIODO_ATR
    assert wilder < simple


# ------------------------------------------------ el ATR de un par entero
def test_sin_ruedas_guardadas_no_hay_atr():
    r = atr_de_rangos("EURUSD=X", [], hoy=HOY)
    assert not r.hay_atr and r.valor is None
    assert "no hay ruedas" in r.motivo


def test_con_menos_ruedas_que_el_minimo_no_hay_atr():
    """Hacen falta 15: catorce rangos y un cierre previo para el primero."""
    r = atr_de_rangos("EURUSD=X", _velas(MINIMO_RUEDAS - 1), hoy=HOY)
    assert not r.hay_atr
    assert str(MINIMO_RUEDAS - 1) in r.motivo
    assert r.ruedas == MINIMO_RUEDAS - 1


def test_con_el_minimo_justo_ya_hay_atr():
    r = atr_de_rangos("EURUSD=X", _velas(MINIMO_RUEDAS), hoy=HOY)
    assert r.hay_atr
    assert r.ruedas == MINIMO_RUEDAS


def test_el_atr_en_precio_porcentaje_y_pips():
    """Rango constante de 0,0050 sobre un cierre de 1,1025, con pip 0,0001."""
    r = atr_de_rangos("EURUSD=X", _velas(30), pip_tamano=Decimal("0.0001"), hoy=HOY)
    assert float(r.valor) == pytest.approx(0.0050)
    assert float(r.pips) == pytest.approx(50.0)
    assert float(r.porcentaje) == pytest.approx(0.0050 / 1.1025 * 100)
    assert r.aviso_pips == ""


def test_sin_tamano_de_pip_hay_precio_y_porcentaje_pero_no_pips():
    """Decisión explícita: no se inventa un divisor. USDBRL, USDCLP, USDIDX
    y USDMXN están en este caso."""
    r = atr_de_rangos("USDBRL=X", _velas(30), pip_tamano=None, hoy=HOY)
    assert r.hay_atr
    assert r.valor is not None and r.porcentaje is not None
    assert r.pips is None
    assert r.aviso_pips == AVISO_SIN_PIP
    assert "falta tamaño del pip" in r.aviso_pips

    # un pip en cero o NaN cuenta igual que ausente
    assert atr_de_rangos("X", _velas(30), pip_tamano=0, hoy=HOY).pips is None
    assert atr_de_rangos("X", _velas(30), pip_tamano=float("nan"), hoy=HOY).pips is None


def test_las_filas_se_ordenan_por_fecha_antes_de_calcular():
    """Si llegaran desordenadas, el cierre previo sería el equivocado."""
    velas = _velas(30)
    r_ordenado = atr_de_rangos("EURUSD=X", velas, hoy=HOY)
    r_revuelto = atr_de_rangos("EURUSD=X", list(reversed(velas)), hoy=HOY)
    assert r_ordenado.valor == r_revuelto.valor
    assert r_ordenado.ultima_fecha == r_revuelto.ultima_fecha


def test_informa_la_fecha_del_ultimo_dato_y_cuanto_lleva():
    velas = _velas(30, desde=date(2026, 9, 1))
    r = atr_de_rangos("EURUSD=X", velas, hoy=HOY)
    assert r.ultima_fecha == date(2026, 9, 30)
    assert r.dias_sin_actualizar == (HOY - date(2026, 9, 30)).days
    assert r.ruedas_sin_actualizar > RUEDAS_PARA_DESACTUALIZADO
    assert r.desactualizado


def test_el_lunes_no_marca_desactualizados_a_todos_los_pares():
    """Del cierre del viernes al lunes hay 3 días corridos pero UNA sola
    rueda. Contando días corridos, los 14 pares saldrían en alerta todos los
    lunes, y un guardián que grita cada lunes se termina ignorando."""
    viernes, lunes = date(2026, 10, 9), date(2026, 10, 12)
    velas = _velas(30, desde=viernes - timedelta(days=29))
    assert velas[-1]["fecha"] == viernes
    r = atr_de_rangos("EURUSD=X", velas, hoy=lunes)
    assert r.dias_sin_actualizar == 3, "son 3 días corridos"
    assert r.ruedas_sin_actualizar == 1, "pero una sola rueda"
    assert not r.desactualizado


def test_dos_ruedas_perdidas_si_avisan():
    """Viernes a miércoles con el cron caído: 3 ruedas, eso sí es un
    problema."""
    viernes, miercoles = date(2026, 10, 9), date(2026, 10, 14)
    velas = _velas(30, desde=viernes - timedelta(days=29))
    r = atr_de_rangos("EURUSD=X", velas, hoy=miercoles)
    assert r.ruedas_sin_actualizar == 3
    assert r.desactualizado


def test_un_par_al_dia_no_sale_como_desactualizado():
    velas = _velas(30, desde=HOY - timedelta(days=30))
    r = atr_de_rangos("EURUSD=X", velas, hoy=HOY)
    assert r.ruedas_sin_actualizar <= RUEDAS_PARA_DESACTUALIZADO
    assert not r.desactualizado


def test_los_huecos_entre_ruedas_se_cuentan():
    """Entre dos filas separadas por más de 5 días, el 'cierre previo' es de
    hace mucho y el rango verdadero de esa rueda queda inflado."""
    velas = _velas(20)
    velas[10]["fecha"] = velas[10]["fecha"] + timedelta(days=20)
    r = atr_de_rangos("EURUSD=X", velas, hoy=HOY)
    assert r.huecos >= 1

    assert contar_huecos([date(2026, 10, 1), date(2026, 10, 2)]) == 0
    assert contar_huecos([date(2026, 10, 1), date(2026, 10, 3)]) == 0   # fin de semana
    assert contar_huecos([date(2026, 10, 1), date(2026, 10, 20)]) == 1
    assert contar_huecos([]) == 0


# --------------------- cuál cifra es la principal y cuál la secundaria
def test_el_rango_del_dia_ignora_el_hueco():
    """Es la diferencia con el rango verdadero: acá un salto entre cierres no
    cuenta."""
    assert list(rango_del_dia([10, 20], [8, 19])) == [2, 1]


def _velas_con_salto():
    """30 velas con un salto de nivel a mitad, que SOLO ve el rango verdadero."""
    velas = _velas(30)
    for v in velas[15:]:
        v["maximo"] += 0.05
        v["minimo"] += 0.05
        v["cierre"] += 0.05
    return velas


def test_la_cifra_principal_es_la_del_rango_del_dia():
    """Se cambió tras medir contra xStation el 12-10-2026: su ATR(14) queda
    mucho más cerca del rango del día (EURUSD -4%, USDJPY -10%) que del rango
    verdadero (+23% y +31%). `valor` y `pips` son la principal."""
    r = atr_de_rangos("EURUSD=X", _velas_con_salto(), pip_tamano=Decimal("0.0001"),
                      hoy=HOY)
    assert r.valor < r.valor_rango_verdadero, (
        "la principal tiene que ser la del rango del día, que es la menor")
    assert r.pips < r.pips_rango_verdadero
    # Y la principal no se mueve con el salto: es solo máximo menos mínimo.
    sin_salto = atr_de_rangos("EURUSD=X", _velas(30), pip_tamano=Decimal("0.0001"),
                              hoy=HOY)
    assert r.valor == sin_salto.valor


def test_las_dos_cifras_usan_el_MISMO_suavizado():
    """Para que la comparación mida la diferencia entre las dos definiciones
    de rango, no entre dos formas de promediar. Sin huecos coinciden."""
    r = atr_de_rangos("EURUSD=X", _velas(30), pip_tamano=Decimal("0.0001"), hoy=HOY)
    assert r.valor == r.valor_rango_verdadero
    assert r.pips == r.pips_rango_verdadero


def test_el_rango_verdadero_nunca_es_menor_que_el_del_dia():
    """Toma el mayor de tres y uno de ellos ES el rango del día."""
    r = atr_de_rangos("EURUSD=X", _velas_con_salto(), pip_tamano=Decimal("0.0001"),
                      hoy=HOY)
    assert r.valor_rango_verdadero > r.valor


def test_sin_tamano_de_pip_las_dos_cifras_quedan_sin_pips():
    r = atr_de_rangos("USDBRL=X", _velas(30), pip_tamano=None, hoy=HOY)
    assert r.valor is not None and r.valor_rango_verdadero is not None
    assert r.pips is None and r.pips_rango_verdadero is None


def test_el_stop_sugerido_usa_la_principal_y_no_el_rango_verdadero():
    """Con el rango verdadero el stop saldría más ancho de lo pedido."""
    r = atr_de_rangos("EURUSD=X", _velas_con_salto(), pip_tamano=Decimal("0.0001"),
                      hoy=HOY)
    precio, _pips = stop_sugerido(r, Decimal("1.5"))
    assert precio == r.valor * Decimal("1.5")
    assert precio < r.valor_rango_verdadero * Decimal("1.5")


def test_el_aviso_de_stop_cerca_usa_la_principal():
    """Una distancia entre las dos cifras: lejos según la principal, cerca
    según el rango verdadero. Tiene que mandar la principal."""
    r = atr_de_rangos("EURUSD=X", _velas_con_salto(), pip_tamano=Decimal("0.0001"),
                      hoy=HOY)
    distancia = (r.valor + r.valor_rango_verdadero) / 2
    cerca, en_atr = stop_demasiado_cerca(Decimal("1.1000"),
                                         Decimal("1.1000") - distancia, r)
    assert cerca is False, "con la principal esa distancia supera 1 ATR"
    assert en_atr == distancia / r.valor


# ----------------------------------------------------- días sospechosos
def test_se_cuentan_los_dias_de_rango_anormal():
    """Rango mayor a 3 veces la MEDIANA del par. Mediana y no promedio: el
    promedio ya estaría contaminado por los días que se buscan."""
    maximos = [1.1050] * 20 + [1.1500]
    minimos = [1.1000] * 20 + [1.1000]
    #          rango 0,0050 x20        rango 0,0500 = 10x la mediana
    assert dias_sospechosos(maximos, minimos) == 1
    assert dias_sospechosos([1.1050] * 20, [1.1000] * 20) == 0


def test_justo_en_el_factor_no_es_sospechoso():
    """Estrictamente mayor, igual que los demás umbrales del proyecto.

    Los precios van en potencias de dos (1,0 / 1,25 / 1,75) a propósito: con
    valores como 1,1050 la resta da 0,004999999999999893 y la prueba
    terminaría midiendo la aritmética de punto flotante en vez del umbral.
    """
    minimos = [1.0] * 21
    normales = [1.25] * 20                     # rango 0,25 exacto
    justo = normales + [1.0 + 0.25 * FACTOR_DIA_SOSPECHOSO]   # rango 0,75 exacto
    assert dias_sospechosos(justo, minimos) == 0

    un_pelo_mas = normales + [1.0 + 0.25 * FACTOR_DIA_SOSPECHOSO + 0.125]
    assert dias_sospechosos(un_pelo_mas, minimos) == 1


def test_el_conteo_de_sospechosos_llega_al_resultado():
    velas = _velas(30)
    velas[20]["maximo"] = velas[20]["minimo"] + 0.05   # rango 10x
    r = atr_de_rangos("EURUSD=X", velas, hoy=HOY)
    assert r.sospechosos == 1
    assert atr_de_rangos("EURUSD=X", _velas(30), hoy=HOY).sospechosos == 0


def test_sin_datos_no_hay_sospechosos():
    assert dias_sospechosos([], []) == 0
    assert dias_sospechosos([1.1], [1.1]) == 0   # mediana cero


# ------------------------- cuando los dias raros IMPORTAN de verdad
def test_tener_dias_raros_no_basta_para_marcar():
    """Con el factor en 3x, los 14 pares reales tienen al menos un día así en
    un año: es lo normal. Marcarlos a todos es no marcar a ninguno. Lo que se
    avisa es que MUEVAN el número con el que se dimensiona el stop."""
    velas = _velas(60)
    # un solo día raro, pero diluido en 60 ruedas: casi no mueve el ATR
    velas[5]["maximo"] = velas[5]["minimo"] + 0.02
    r = atr_de_rangos("EURUSD=X", velas, hoy=HOY)
    assert r.sospechosos == 1, "el día raro tiene que contarse igual"
    assert r.inflacion_sospechosos < UMBRAL_INFLACION_MATERIAL
    assert not r.sospechosos_materiales
    assert r.texto_sospechosos == ""


def test_un_dia_raro_reciente_y_grande_si_marca():
    """Wilder pondera más lo reciente, así que un día enorme cerca del final
    sí mueve el ATR."""
    velas = _velas(30)
    velas[-1]["maximo"] = velas[-1]["minimo"] + 0.20   # 40x la mediana
    r = atr_de_rangos("EURUSD=X", velas, hoy=HOY)
    assert r.sospechosos == 1
    assert r.inflacion_sospechosos > UMBRAL_INFLACION_MATERIAL
    assert r.sospechosos_materiales
    assert "1 día raro infla su ATR en" in r.texto_sospechosos


def test_el_texto_de_la_marca_dice_cuanto_y_concuerda_en_numero():
    velas = _velas(30)
    velas[-1]["maximo"] = velas[-1]["minimo"] + 0.20
    velas[-2]["maximo"] = velas[-2]["minimo"] + 0.20
    r = atr_de_rangos("EURUSD=X", velas, hoy=HOY)
    assert r.sospechosos == 2
    assert r.texto_sospechosos.startswith("2 días raros inflan su ATR en")
    assert "%" in r.texto_sospechosos


def test_sin_dias_raros_no_hay_marca_ni_inflacion():
    r = atr_de_rangos("EURUSD=X", _velas(30), hoy=HOY)
    assert r.sospechosos == 0
    assert not r.sospechosos_materiales
    assert r.texto_sospechosos == ""
    # la inflación se calcula igual, y da cero
    assert r.inflacion_sospechosos == pytest.approx(Decimal(0), abs=1e-9)


def test_la_inflacion_se_mide_recortando_y_no_sacando_los_dias():
    """Sacarlos abriría huecos en la serie, y el hueco distorsiona por su
    cuenta. Recortar a 3x la mediana deja la serie completa."""
    rango_normal = [0.0050] * 29
    maximos = [1.0 + r for r in rango_normal] + [1.0 + 0.0500]
    minimos = [1.0] * 30
    infl = inflacion_por_dias_sospechosos(maximos, minimos)
    assert infl is not None and infl > 0
    # el recorte deja el día en 3x la mediana, no en cero ni fuera
    sin_el_dia = inflacion_por_dias_sospechosos(maximos[:-1], minimos[:-1])
    assert sin_el_dia == pytest.approx(Decimal(0), abs=1e-9)


def test_sin_datos_suficientes_no_hay_inflacion():
    assert inflacion_por_dias_sospechosos([1.1] * 5, [1.0] * 5) is None
    assert inflacion_por_dias_sospechosos([], []) is None
    # mediana cero
    assert inflacion_por_dias_sospechosos([1.0] * 30, [1.0] * 30) is None


# ------------------------------------------------------------- el stop
def test_el_stop_sugerido_es_el_multiplo_del_atr():
    r = atr_de_rangos("EURUSD=X", _velas(30), pip_tamano=Decimal("0.0001"), hoy=HOY)
    precio, pips = stop_sugerido(r)
    assert float(precio) == pytest.approx(0.0050 * float(MULTIPLO_STOP_POR_DEFECTO))
    assert float(pips) == pytest.approx(75.0)

    precio2, pips2 = stop_sugerido(r, Decimal("2"))
    assert float(pips2) == pytest.approx(100.0)


def test_sin_atr_no_hay_stop_sugerido():
    sin_atr = atr_de_rangos("EURUSD=X", [], hoy=HOY)
    assert stop_sugerido(sin_atr) == (None, None)
    assert stop_sugerido(None) == (None, None)


def test_un_multiplo_invalido_no_sugiere_nada():
    r = atr_de_rangos("EURUSD=X", _velas(30), pip_tamano=Decimal("0.0001"), hoy=HOY)
    assert stop_sugerido(r, 0) == (None, None)
    assert stop_sugerido(r, -1) == (None, None)
    assert stop_sugerido(r, None) == (None, None)


def test_sin_pips_el_stop_sale_solo_en_precio():
    r = atr_de_rangos("USDBRL=X", _velas(30), pip_tamano=None, hoy=HOY)
    precio, pips = stop_sugerido(r)
    assert precio is not None and pips is None


# ------------------------------------------- el stop de una posición abierta
def test_avisa_si_el_stop_esta_a_menos_de_un_atr():
    """Dentro del movimiento normal de una rueda: lo más probable es que
    salte por ruido y no porque la tesis se haya roto. Se mide contra la
    cifra PRINCIPAL, la del rango del día."""
    r = atr_de_rangos("EURUSD=X", _velas(30), pip_tamano=Decimal("0.0001"), hoy=HOY)
    cerca, en_atr = stop_demasiado_cerca(Decimal("1.1000"), Decimal("1.0975"), r)
    assert cerca is True
    assert float(en_atr) == pytest.approx(0.5)


def test_no_avisa_si_el_stop_esta_mas_lejos_de_un_atr():
    r = atr_de_rangos("EURUSD=X", _velas(30), pip_tamano=Decimal("0.0001"), hoy=HOY)
    cerca, en_atr = stop_demasiado_cerca(Decimal("1.1000"), Decimal("1.0900"), r)
    assert cerca is False
    assert float(en_atr) == pytest.approx(2.0)


def test_justo_en_un_atr_no_avisa():
    """Estrictamente menor, igual que el resto de los umbrales del módulo."""
    r = atr_de_rangos("EURUSD=X", _velas(30), pip_tamano=Decimal("0.0001"), hoy=HOY)
    cerca, en_atr = stop_demasiado_cerca(Decimal("1.1000"), Decimal("1.0950"), r)
    assert float(en_atr) == pytest.approx(1.0)
    assert cerca is False


def test_sin_los_datos_necesarios_no_se_afirma_nada():
    r = atr_de_rangos("EURUSD=X", _velas(30), pip_tamano=Decimal("0.0001"), hoy=HOY)
    assert stop_demasiado_cerca(None, Decimal("1.09"), r) == (None, None)
    assert stop_demasiado_cerca(Decimal("1.10"), None, r) == (None, None)
    assert stop_demasiado_cerca(float("nan"), Decimal("1.09"), r) == (None, None)
    # sin ATR tampoco
    sin_atr = atr_de_rangos("EURUSD=X", [], hoy=HOY)
    assert stop_demasiado_cerca(Decimal("1.10"), Decimal("1.09"), sin_atr) == (None, None)
    # y un stop en el mismo precio de entrada no es "cerca": es un dato malo
    assert stop_demasiado_cerca(Decimal("1.10"), Decimal("1.10"), r) == (None, None)


if __name__ == "__main__":
    print("Correr con pytest: python -m pytest tests/test_trading_atr.py")


# ================== el stop contra el ruido del día (tramos)
from trading_atr import (  # noqa: E402
    DENTRO,
    ERROR,
    FUERA,
    JUSTO,
    SIN_ATR,
    TEXTO_SIN_ATR,
    stop_sugerido_para,
    tramo_del_stop,
)

ATR_EURUSD = Decimal("0.0055")       # 55 pips, el real de hoy redondeado
ENTRADA = Decimal("1.1200")


def test_los_tres_tramos_en_una_compra():
    """ratio = |entrada - stop| / ATR. Los cortes van en 1 y en 1,5."""
    # 30 pips = 0,55 ATR -> dentro del ruido
    dentro = tramo_del_stop(ENTRADA, Decimal("1.1170"), ATR_EURUSD, "compra")
    assert dentro.tramo == DENTRO and dentro.avisa
    assert float(dentro.ratio) == pytest.approx(0.5454, abs=0.001)
    assert "dentro del ruido del día" in dentro.texto
    assert "saque antes de tiempo" in dentro.texto

    # 70 pips = 1,27 ATR -> justo
    justo = tramo_del_stop(ENTRADA, Decimal("1.1130"), ATR_EURUSD, "compra")
    assert justo.tramo == JUSTO and not justo.avisa
    assert "detrás de un nivel del gráfico" in justo.texto

    # 100 pips = 1,82 ATR -> fuera
    fuera = tramo_del_stop(ENTRADA, Decimal("1.1100"), ATR_EURUSD, "compra")
    assert fuera.tramo == FUERA and not fuera.avisa
    assert fuera.texto == "Stop fuera del ruido del día"


def test_los_cortes_son_estrictos_igual_que_el_resto_del_proyecto():
    """Justo en 1 ATR ya NO es "dentro"; justo en 1,5 ya es "fuera"."""
    en_uno = tramo_del_stop(ENTRADA, ENTRADA - ATR_EURUSD, ATR_EURUSD, "compra")
    assert en_uno.tramo == JUSTO, f"ratio {en_uno.ratio}"

    en_uno_y_medio = tramo_del_stop(
        ENTRADA, ENTRADA - ATR_EURUSD * Decimal("1.5"), ATR_EURUSD, "compra")
    assert en_uno_y_medio.tramo == FUERA


def test_los_mismos_tramos_en_una_venta():
    """En venta el stop va ARRIBA, y la distancia se mide igual."""
    dentro = tramo_del_stop(ENTRADA, Decimal("1.1230"), ATR_EURUSD, "venta")
    assert dentro.tramo == DENTRO
    fuera = tramo_del_stop(ENTRADA, Decimal("1.1300"), ATR_EURUSD, "venta")
    assert fuera.tramo == FUERA


def test_el_stop_sugerido_va_del_lado_que_corresponde():
    """Debajo en compra, encima en venta. Ponerlo al revés sería un stop que
    se ejecuta al instante."""
    compra = stop_sugerido_para(ENTRADA, "compra", ATR_EURUSD)
    venta = stop_sugerido_para(ENTRADA, "venta", ATR_EURUSD)
    assert compra < ENTRADA < venta
    assert compra == ENTRADA - ATR_EURUSD * Decimal("1.5")
    assert venta == ENTRADA + ATR_EURUSD * Decimal("1.5")
    # y el sugerido cae justo en el borde de "fuera"
    assert tramo_del_stop(ENTRADA, compra, ATR_EURUSD, "compra").tramo == FUERA


def test_el_multiplo_del_stop_sugerido_es_configurable():
    doble = stop_sugerido_para(ENTRADA, "compra", ATR_EURUSD, Decimal("2"))
    assert doble == ENTRADA - ATR_EURUSD * 2


def test_sin_atr_no_avisa_nada():
    """Sin el dato no se opina: ni aviso ni número."""
    for atr in (None, Decimal("0"), Decimal("-0.001"), float("nan")):
        r = tramo_del_stop(ENTRADA, Decimal("1.1170"), atr, "compra")
        assert r.tramo == SIN_ATR, atr
        assert r.ratio is None
        assert r.texto == TEXTO_SIN_ATR
        assert not r.avisa
        assert stop_sugerido_para(ENTRADA, "compra", atr) is None


def test_un_atr_en_cero_no_divide_por_cero():
    r = tramo_del_stop(ENTRADA, Decimal("1.1170"), Decimal("0"), "compra")
    assert r.tramo == SIN_ATR and r.ratio is None


def test_el_stop_del_lado_equivocado_es_un_error_y_lo_dice():
    """No es un stop apretado: es un error. Devolver un ratio lo haría pasar
    por válido."""
    compra_al_reves = tramo_del_stop(ENTRADA, Decimal("1.1250"), ATR_EURUSD, "compra")
    assert compra_al_reves.tramo == ERROR
    assert "DEBAJO" in compra_al_reves.texto
    assert compra_al_reves.ratio is None

    venta_al_reves = tramo_del_stop(ENTRADA, Decimal("1.1150"), ATR_EURUSD, "venta")
    assert venta_al_reves.tramo == ERROR
    assert "ENCIMA" in venta_al_reves.texto

    # aun así sugiere dónde ponerlo bien
    assert compra_al_reves.stop_sugerido is not None


def test_el_stop_igual_a_la_entrada_tambien_es_error():
    r = tramo_del_stop(ENTRADA, ENTRADA, ATR_EURUSD, "compra")
    assert r.tramo == ERROR


def test_sin_entrada_o_sin_stop_no_se_opina():
    assert tramo_del_stop(None, Decimal("1.11"), ATR_EURUSD, "compra").tramo == SIN_ATR
    assert tramo_del_stop(ENTRADA, None, ATR_EURUSD, "compra").tramo == SIN_ATR
    assert tramo_del_stop(Decimal("0"), Decimal("1.11"), ATR_EURUSD, "compra").tramo == SIN_ATR


def test_una_direccion_desconocida_no_sugiere_un_lado_al_azar():
    assert stop_sugerido_para(ENTRADA, "lo que sea", ATR_EURUSD) is None


def test_guarda_la_distancia_para_poder_mostrarla():
    r = tramo_del_stop(ENTRADA, Decimal("1.1170"), ATR_EURUSD, "compra")
    assert float(r.distancia) == pytest.approx(0.0030, abs=1e-9)


# ============ el stop sugerido redondeado hacia afuera de la entrada
from trading_atr import (  # noqa: E402
    TRAMO_FUERA_DEL_RUIDO,
    decimales_del_precio,
    stop_sugerido_redondeado,
)


def test_los_decimales_salen_del_pip_del_catalogo():
    """0,0001 da 5 decimales y 0,01 da 3: el pip más la pipeta, como cotiza
    XTB."""
    assert decimales_del_precio(Decimal("0.0001")) == 5
    assert decimales_del_precio(Decimal("0.01")) == 3


def test_sin_pip_los_decimales_salen_del_precio_escrito():
    """Cripto, índices, materias primas y 41 pares no tienen pip en el
    catálogo. Inventar 5 decimales para un índice que cotiza en enteros
    daría un stop con cuatro ceros al final."""
    assert decimales_del_precio(None, Decimal("4000.25")) == 2
    assert decimales_del_precio(None, Decimal("18500")) == 0
    assert decimales_del_precio(None, Decimal("0.123456")) == 6
    # sin nada de donde sacarlo, un valor por defecto razonable
    assert decimales_del_precio(None, None) == 5


def test_en_compra_redondea_ALEJANDO_el_stop_de_la_entrada():
    """Redondear al más cercano lo acercaría la mitad de las veces, y el
    stop cargado quedaría a menos de 1,5 ATR."""
    entrada, atr = Decimal("1.1200"), Decimal("0.005555")
    exacto = entrada - atr * Decimal("1.5")        # 1,1116675
    redondeado = stop_sugerido_redondeado(entrada, "compra", atr, Decimal("0.0001"))
    assert redondeado < exacto, f"{redondeado} deberia estar MAS abajo que {exacto}"
    assert redondeado == Decimal("1.11166")


def test_en_venta_redondea_para_el_otro_lado():
    entrada, atr = Decimal("1.1200"), Decimal("0.005555")
    exacto = entrada + atr * Decimal("1.5")        # 1,1283325
    redondeado = stop_sugerido_redondeado(entrada, "venta", atr, Decimal("0.0001"))
    assert redondeado > exacto
    assert redondeado == Decimal("1.12834")


def test_un_par_de_yenes_usa_tres_decimales():
    entrada, atr = Decimal("158.628"), Decimal("1.1789")
    compra = stop_sugerido_redondeado(entrada, "compra", atr, Decimal("0.01"))
    venta = stop_sugerido_redondeado(entrada, "venta", atr, Decimal("0.01"))
    assert -compra.as_tuple().exponent == 3, compra
    assert -venta.as_tuple().exponent == 3, venta
    assert compra == Decimal("156.859") and venta == Decimal("160.397")


def test_un_instrumento_de_dos_decimales():
    entrada, atr = Decimal("4000.25"), Decimal("35.5")
    stop = stop_sugerido_redondeado(entrada, "compra", atr)
    assert -stop.as_tuple().exponent == 2, stop
    assert stop == Decimal("3947.00")


def test_PROPIEDAD_el_stop_redondeado_nunca_queda_mas_cerca_de_1_5_ATR():
    """La propiedad que motivó todo el cambio: con la sugerencia ya
    redondeada, el ratio es siempre >= 1,5 y el tramo es "fuera del ruido".

    Se barre a mano una grilla amplia en vez de usar azar: una prueba que
    falla una vez de cada veinte no sirve para fijar una propiedad.
    """
    casos = 0
    for pip, entrada in (
        (Decimal("0.0001"), Decimal("1.1200")),
        (Decimal("0.0001"), Decimal("0.65432")),
        (Decimal("0.0001"), Decimal("1.33333")),
        (Decimal("0.01"), Decimal("158.628")),
        (Decimal("0.01"), Decimal("195.507")),
        (None, Decimal("4000.25")),
        (None, Decimal("18500")),
        (None, Decimal("0.123456")),
    ):
        for atr_txt in ("0.0001", "0.000777", "0.005555", "0.0123",
                        "1.1789", "7.5075", "35.5", "123.456"):
            atr = Decimal(atr_txt)
            for direccion in ("compra", "venta"):
                stop = stop_sugerido_redondeado(entrada, direccion, atr, pip)
                if stop is None or stop <= 0:
                    continue   # un ATR enorme puede dejar el stop en negativo
                r = tramo_del_stop(entrada, stop, atr, direccion)
                if r.tramo == ERROR:
                    continue   # el stop cruzó la entrada: otro caso, ya probado
                casos += 1
                assert r.ratio >= TRAMO_FUERA_DEL_RUIDO, (
                    f"{direccion} entrada={entrada} atr={atr} pip={pip} "
                    f"stop={stop} ratio={r.ratio}")
                assert r.tramo == FUERA, (
                    f"{direccion} entrada={entrada} atr={atr} stop={stop} "
                    f"dio {r.tramo}")
    assert casos > 100, f"solo se probaron {casos} combinaciones"


def test_el_redondeo_usa_Decimal_y_no_coma_flotante():
    """Con round() de Python, 1,1116675 a 5 decimales da 1,11167, que deja
    el ratio en 1,49955 y cae al tramo de abajo. Ese era el defecto."""
    entrada, atr = Decimal("1.1200"), Decimal("0.005555")
    con_round = Decimal(str(round(float(entrada - atr * Decimal("1.5")), 5)))
    assert tramo_del_stop(entrada, con_round, atr, "compra").tramo == JUSTO, (
        "si esto deja de ser cierto, el defecto original ya no se reproduce")
    bien = stop_sugerido_redondeado(entrada, "compra", atr, Decimal("0.0001"))
    assert tramo_del_stop(entrada, bien, atr, "compra").tramo == FUERA


def test_sin_atr_no_hay_stop_redondeado():
    for atr in (None, Decimal("0"), Decimal("-1"), float("nan")):
        assert stop_sugerido_redondeado(Decimal("1.12"), "compra", atr) is None
    assert stop_sugerido_redondeado(Decimal("1.12"), "lo que sea",
                                    Decimal("0.005")) is None
