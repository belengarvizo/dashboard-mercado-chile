"""H3-D1: LÓGICA de los calendarios financieros, con calendarios SINTÉTICOS construidos aquí (no verifican fechas reales).

QUÉ SE PRUEBA
    - Límites exactos del contador: incluye la fecha del dato, excluye `hasta` (la sesión de hoy, que puede seguir abierta,
      nunca se cuenta), fines de semana y conteo negativo.
    - Una fecha fuera de la cobertura nunca se toma como cerrada: estado «calendario no verificado» y conteo aproximado.
    - Cierre extraordinario (sintético) y sesión de horario reducido (cuenta como sesión).
    - Varios calendarios a la vez: solo cuentan los días que son sesión en todos.
    - Umbral único de atraso en todo el dashboard, y sin cambios en las ventanas de H3-A ni en los límites del carry.
Las fechas reales de las fuentes oficiales se prueban aparte, en test_calendarios_fuentes_oficiales.py.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import re
import sys
from datetime import date

import pandas as pd
import pytest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(RAIZ)

import calendarios_financieros as calf  # noqa: E402

D = date


def _sintetico(feriados=(), cierres=(), reducidas=(), cobertura=((D(2030, 1, 1), D(2030, 12, 31)),), tipo=calf.TIPO_FERIADOS,
               id_="sintetico"):
    return calf.Calendario(
        id=id_, nombre=f"Calendario sintético {id_}", tipo=tipo, mercado_o_fuente="prueba", fuente_oficial="ninguna (sintético)",
        url="", fecha_verificacion=D(2030, 6, 1), cobertura=cobertura,
        feriados={f: "feriado sintético" for f in feriados}, cierres_extraordinarios={f: "cierre sintético" for f in cierres},
        sesiones_reducidas={f: "sesión reducida sintética" for f in reducidas}, limitaciones=("sintético",))


# 2030-01-07 es lunes.
LUN, MAR, MIE, JUE, VIE, SAB, DOM, LUN2 = (D(2030, 1, d) for d in (7, 8, 9, 10, 11, 12, 13, 14))


# ---------------------------------------------------------------------------
# Límites exactos del contador
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("desde, hasta, esperado", [
    (MIE, MIE, 0),     # dato de hoy: 0 (la sesión de hoy no se cuenta)
    (MAR, MIE, 1),     # dato de la sesión anterior: 1, aunque la de hoy siga abierta
    (VIE, LUN2, 1),    # viernes → lunes: el fin de semana no suma
    (SAB, LUN2, 0),    # dato de un sábado (por ejemplo, días corridos): ninguna sesión entre medio
    (LUN, LUN2, 5),    # una semana completa
    (MIE, MAR, -1),    # dato posterior a la fecha de comparación: negativo, nunca «atrasado»
])
def test_limites_del_contador(desde, hasta, esperado):
    conteo = calf.sesiones_entre(_sintetico(), desde, hasta)
    assert conteo.sesiones == esperado and conteo.verificado


def test_una_sesion_todavia_abierta_no_vuelve_atrasado_el_dato():
    # Dato del jueves de la semana anterior; hoy es el jueves siguiente: 5 sesiones (jue, vie, lun, mar, mié) = no atrasado.
    conteo = calf.sesiones_entre(_sintetico(), JUE, D(2030, 1, 17))
    assert conteo.sesiones == 5 and not conteo.atrasado()
    # Al día siguiente ya son 6: atrasado (umbral único, sin cambiar su valor 5).
    assert calf.sesiones_entre(_sintetico(), JUE, D(2030, 1, 18)).atrasado()
    assert calf.UMBRAL_SESIONES_DE_ATRASO == 5


def test_feriado_cierre_extraordinario_y_sesion_reducida():
    cal = _sintetico(feriados=[MIE], cierres=[JUE], reducidas=[MAR])
    assert calf.sesiones_entre(cal, LUN, LUN2).sesiones == 3          # lun, mar (reducida, cuenta), vie
    assert calf.es_sesion(cal, MAR) is True and calf.es_sesion(cal, MIE) is False and calf.es_sesion(cal, JUE) is False


# ---------------------------------------------------------------------------
# Cobertura desconocida o vencida
# ---------------------------------------------------------------------------
def test_fuera_de_cobertura_no_se_supone_cerrado_y_el_conteo_es_aproximado():
    vencido = _sintetico(cobertura=((D(2029, 1, 1), D(2029, 12, 31)),))
    assert calf.es_sesion(vencido, LUN) is None                           # nunca «cerrado» por falta de calendario
    assert calf.estado_de_fecha(vencido, LUN) == calf.ESTADO_NO_VERIFICADO
    conteo = calf.sesiones_entre(vencido, LUN, LUN2)
    assert conteo.sesiones == 5 and not conteo.verificado and "no verificado" in conteo.nota
    assert "unos 5 días hábiles" in calf.texto_de_conteo(conteo)


def test_tramo_que_cruza_el_fin_de_la_cobertura_es_aproximado_pero_usa_los_feriados_conocidos():
    cal = _sintetico(feriados=[D(2030, 12, 31)], cobertura=((D(2030, 1, 1), D(2030, 12, 31)),))
    conteo = calf.sesiones_entre(cal, D(2030, 12, 30), D(2031, 1, 3))   # 30-dic (lun) … 2-ene (jue)
    assert not conteo.verificado
    assert conteo.sesiones == 3                                          # 30-dic, 1-ene y 2-ene: el 31-dic conocido no cuenta


def test_sin_calendario_asignado_es_aproximacion():
    conteo = calf.sesiones_entre(None, LUN, LUN2)
    assert conteo.sesiones == 5 and not conteo.verificado


def test_dentro_de_la_cobertura_distingue_historico_de_programado():
    cal = _sintetico()
    assert calf.estado_de_fecha(cal, D(2030, 3, 1)) == calf.ESTADO_HISTORICO     # antes de la verificación (1-jun-2030)
    assert calf.estado_de_fecha(cal, D(2030, 9, 1)) == calf.ESTADO_PROGRAMADO


# ---------------------------------------------------------------------------
# Varios calendarios, días corridos y FX
# ---------------------------------------------------------------------------
def test_varios_calendarios_cuentan_solo_los_dias_abiertos_en_todos():
    a, b = _sintetico(feriados=[MAR], id_="a"), _sintetico(feriados=[JUE], id_="b")
    assert calf.sesiones_entre([a, b], LUN, LUN2).sesiones == 3          # lun, mié, vie
    sin_cobertura = _sintetico(cobertura=(), id_="c")
    assert not calf.sesiones_entre([a, sin_cobertura], LUN, LUN2).verificado


def test_dias_corridos_y_mercado_cambiario():
    assert calf.sesiones_entre("dias_corridos", VIE, LUN2).sesiones == 3
    fx = calf.sesiones_entre("fx_24_5", VIE, LUN2)
    assert fx.sesiones == 1 and fx.verificado                           # estructural: sin lista de feriados


def test_sin_fechas_no_hay_conteo():
    assert calf.sesiones_entre("fx_24_5", None, LUN) is None


# ---------------------------------------------------------------------------
# Asignación de calendarios a instrumentos: sin suponer NYSE ni un calendario común de futuros
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ticker, calendario", [
    ("SQM-B.SN", "bolsa_santiago"), ("USDCLP=X", "fx_24_5"), ("KC=F", "ice_futures_us_blandos"),
    ("CL=F", "cme_group"), ("GC=F", "cme_group"), ("DX-Y.NYB", "ice_futures_us_divisas"),
    ("SPY", "eeuu_bolsa_no_registrada"), ("TLT", "eeuu_bolsa_no_registrada"), ("^GSPC", "eeuu_bolsa_no_registrada"),
])
def test_calendario_de_cada_instrumento(ticker, calendario):
    assert calf.calendario_de_instrumento(ticker) == calendario


# ---------------------------------------------------------------------------
# Umbral único y modelos fuera del alcance sin cambios
# ---------------------------------------------------------------------------
def test_umbral_unico_en_todo_el_dashboard():
    import informe_renta_fija as irf
    import market_data as md
    import renta_fija_ui as rfui
    import inspect
    assert rfui.DIAS_HABILES_DE_ATRASO == calf.UMBRAL_SESIONES_DE_ATRASO
    assert irf.MAX_RUEDAS_ATRASO_CURVA == calf.UMBRAL_SESIONES_DE_ATRASO
    assert inspect.signature(md.detectar_apagon_mercado).parameters["dias_habiles_min_atraso"].default == calf.UMBRAL_SESIONES_DE_ATRASO
    for archivo in ("app/dashboard.py", "market_data.py", "renta_fija_ui.py", "renta_variable_ui.py", "commodities_ui.py",
                    "fx_carry_ui.py", "informe_renta_fija.py"):
        texto = open(os.path.join(RAIZ, archivo), encoding="utf-8").read()
        assert "busday_count" not in texto, archivo                       # todo conteo pasa por calendarios_financieros
        assert not re.search(r"atraso\s*>\s*5\b", texto), archivo         # sin umbrales sueltos
    assert not hasattr(md, "FERIADOS_EEUU_2026")


def test_sin_cambios_en_los_limites_del_carry_ni_en_la_regla_de_h3a():
    import fx_carry as fx
    import fx_carry_ui as fxui
    assert fx.ANTIGUEDAD_MAXIMA_TASA_DIARIA == 10                        # también el desfase máximo del diferencial (H3-A)
    assert fxui.ANTIGUEDAD_MAXIMA_DE_TASA == {"diaria": 10, "mensual": 75}
    assert fx.DIAS_MAXIMOS_POR_TRAMO == 10


# ---------------------------------------------------------------------------
# Cierre de H3-D1: antigüedad frente a sesiones faltantes, y extremos del intervalo
# ---------------------------------------------------------------------------
def test_antiguedad_y_sesiones_faltantes_son_medidas_distintas():
    conteo = calf.sesiones_entre(_sintetico(), MAR, VIE)          # dato del martes, consulta el viernes
    assert conteo.sesiones == 3 and conteo.faltantes == 2            # antigüedad: mar, mié, jue; faltan mié y jue


def test_viernes_consultado_el_lunes_antes_del_cierre():
    conteo = calf.sesiones_entre(_sintetico(), VIE, LUN2)
    assert conteo.sesiones == 1 and conteo.faltantes == 0 and not conteo.atrasado()


def test_el_umbral_de_cinco_equivale_a_cinco_sesiones_faltantes_ya_cerradas():
    cal = _sintetico()
    for hasta, atrasado in ((D(2030, 1, 14), False), (D(2030, 1, 15), True)):      # dato del lunes 7
        conteo = calf.sesiones_entre(cal, LUN, hasta)
        assert conteo.atrasado() is atrasado
        assert (conteo.faltantes >= 5) is atrasado                                  # misma decisión, medida en faltantes


def test_dato_en_dia_sin_sesion_no_resta_una_faltante():
    conteo = calf.sesiones_entre(_sintetico(), SAB, D(2030, 1, 16))  # dato de un sábado, consulta el miércoles
    assert conteo.sesiones == 2 and conteo.faltantes == 2


def test_un_calendario_no_verificado_no_produce_afirmaciones_categoricas():
    import market_data as md
    import renta_fija_ui as rfui
    # Aviso del diferencial: «Posible dato atrasado», no «Dato atrasado».
    texto = rfui.texto_atraso_diferencial({"fecha_referencia": pd.Timestamp("2030-01-07")}, pd.Timestamp("2030-01-21"))
    assert texto.strip().startswith("Posible dato atrasado") and "unos" in texto
    # Apagón con la Bolsa de Santiago (calendario no verificado): el resultado se marca como aproximado.
    fechas = pd.bdate_range("2030-01-01", periods=10)
    df = pd.DataFrame([{"ticker": t, "fecha": f, "precio_cierre": 1.0} for t in ("A.SN", "B.SN") for f in fechas])
    import reloj
    from datetime import datetime, timezone
    with reloj.fijar(datetime(2030, 2, 15, 15, 0, tzinfo=timezone.utc)):     # H3-D2: el detector lee el reloj central
        apagon = md.detectar_apagon_mercado(df, ["A.SN", "B.SN"])
    assert apagon is not None and apagon["aproximado"] is True
    fuente = open(os.path.join(RAIZ, "app", "dashboard.py"), encoding="utf-8").read()
    assert "Posible apagón de datos" in fuente
    # Ninguna fecha fuera de cobertura se declara cerrada.
    assert calf.es_sesion("bolsa_santiago", D(2030, 1, 1)) is None
