"""H3-D2 (Derivados): tiempo al vencimiento continuo en años ACT/365F (offline; instantes fijados, sin Yahoo).

QUÉ SE PRUEBA
    - Mismo día de vencimiento, antes y después del cierre de negociación (4:15 p.m. ET para SPY, QQQ, IWM, DIA y TLT).
    - Sesión reducida (27-nov-2026), feriado, calendario no verificado y cambio de horario de verano (1-nov-2026).
    - El instante de valoración es el del precio del subyacente y nunca posterior a «ahora».
    - T = 0: valor intrínseco, sin volatilidad implícita ni griegas inválidas, sin divisiones por cero.
    - Comparación reproducible entre el cálculo anterior (días completos / 365) y el nuevo.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import math
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import black_scholes as bs  # noqa: E402
import reloj  # noqa: E402
import tiempo_al_vencimiento as tv  # noqa: E402

NY = reloj.ZONA_NUEVA_YORK
ANIO = 365 * 86400


def _ny(*args):
    return datetime(*args, tzinfo=NY)


@pytest.mark.parametrize("ticker", ["SPY", "QQQ", "IWM", "DIA", "TLT"])
def test_las_cinco_clases_cierran_a_las_4_15_segun_la_fuente(ticker):
    h = tv.horizonte(ticker, "2026-11-20")
    assert h.cierre_de_negociacion == _ny(2026, 11, 20, 16, 15)
    assert h.plazo_de_ejercicio == _ny(2026, 11, 20, 17, 30)                 # informativo: el modelo no lo usa
    assert tv.APROX_HORIZONTE in h.aproximaciones                          # el horizonte se declara como aproximación


def test_una_clase_sin_horario_verificado_usa_4_00_y_lo_dice():
    h = tv.horizonte("XYZ", "2026-11-20")
    assert h.cierre_de_negociacion.time().hour == 16 and h.cierre_de_negociacion.minute == 0
    assert any("no verificado" in a for a in h.aproximaciones)


def test_mismo_dia_antes_del_cierre_t_positivo():
    h = tv.horizonte("SPY", "2026-11-20")
    T = tv.anios(h, _ny(2026, 11, 20, 10, 0))
    assert T == pytest.approx(6.25 * 3600 / ANIO) and not tv.terminado(h, _ny(2026, 11, 20, 10, 0))
    assert tv.texto_de_tiempo(T) == "6 h 15 min"


def test_mismo_dia_despues_del_cierre_horizonte_terminado():
    h = tv.horizonte("SPY", "2026-11-20")
    for despues in (_ny(2026, 11, 20, 16, 15), _ny(2026, 11, 20, 16, 30), _ny(2026, 11, 21, 9, 0)):
        assert tv.anios(h, despues) == 0.0 and tv.terminado(h, despues)
    assert tv.texto_de_tiempo(0.0) == "terminado"


def test_sesion_reducida_usa_1_15_y_lo_declara():
    h = tv.horizonte("SPY", "2026-11-27")                                    # NYSE cierra 1:00 p.m. ET ese día
    assert h.cierre_de_negociacion == _ny(2026, 11, 27, 13, 15)
    assert any("Sesión reducida" in a for a in h.aproximaciones)


def test_feriado_y_calendario_no_verificado_se_declaran():
    assert any("no es una sesión de la NYSE" in a for a in tv.horizonte("SPY", "2026-11-26").aproximaciones)
    assert any("no está verificado" in a for a in tv.horizonte("SPY", "2025-06-20").aproximaciones)


def test_cambio_de_horario_de_verano_cuenta_horas_reales():
    """EE. UU. vuelve al horario estándar el domingo 1-nov-2026: ese día dura 25 horas."""
    h = tv.horizonte("SPY", "2026-11-02")
    T = tv.anios(h, _ny(2026, 10, 30, 16, 15))
    assert T * ANIO == pytest.approx((3 * 24 + 1) * 3600)


def test_la_zona_del_instante_no_cambia_t():
    h = tv.horizonte("SPY", "2026-11-20")
    instante = _ny(2026, 11, 18, 12, 0)
    en_santiago = instante.astimezone(reloj.ZONA_SANTIAGO)
    assert tv.anios(h, instante) == tv.anios(h, en_santiago) == tv.anios(h, instante.astimezone(timezone.utc))


def test_el_instante_de_valoracion_es_el_del_precio_y_nunca_posterior_a_ahora():
    with reloj.fijar(_ny(2026, 11, 20, 11, 0)):
        valoracion, del_precio = tv.instante_de_valoracion(_ny(2026, 11, 20, 10, 58))
        assert del_precio and valoracion == _ny(2026, 11, 20, 10, 58)
        futuro, _ = tv.instante_de_valoracion(_ny(2026, 11, 20, 12, 0))      # un precio «del futuro» se recorta a ahora
        assert futuro == _ny(2026, 11, 20, 11, 0)
        sin_hora, del_precio = tv.instante_de_valoracion(None)
        assert not del_precio and sin_hora == _ny(2026, 11, 20, 11, 0)
    with pytest.raises(ValueError):
        tv.instante_de_valoracion(datetime(2026, 11, 20, 10, 58))


def test_t_cero_no_divide_por_cero_ni_da_volatilidades_invalidas():
    T = tv.anios(tv.horizonte("SPY", "2026-11-20"), _ny(2026, 11, 20, 17, 0))
    assert T == 0.0
    assert bs.precio(600.0, 590.0, T, 0.04, 0.2, "call") == pytest.approx(10.0)       # valor intrínseco
    assert bs.volatilidad_implicita(10.5, 600.0, 590.0, T, 0.04, "call") is None
    g = bs.griegas(600.0, 590.0, T, 0.04, 0.2, "call")
    assert all(math.isnan(x) for x in (g.delta, g.gamma, g.theta, g.vega, g.rho))


# ---------------------------------------------------------------------------
# Comparación reproducible: antes (días completos con la fecha de hoy) frente a ahora (T continuo hasta 4:15 p.m. ET)
# ---------------------------------------------------------------------------
def _t_anterior(vencimiento: str, ahora_servidor: datetime) -> float:
    """El cálculo anterior: (fecha de vencimiento − fecha de hoy del servidor).days, recortado a 0, / 365."""
    return max((date.fromisoformat(vencimiento) - ahora_servidor.date()).days, 0) / 365.0


CASOS = [
    # (descripción, vencimiento, instante de valoración en Nueva York, servidor en UTC)
    ("vence hoy, 10:00 ET", "2026-11-20", _ny(2026, 11, 20, 10, 0)),
    ("vence mañana, 15:00 ET", "2026-11-20", _ny(2026, 11, 19, 15, 0)),
    ("vence mañana, 22:30 ET (en UTC ya es el día del vencimiento)", "2026-11-20", _ny(2026, 11, 19, 22, 30)),
    ("vence en 30 días, 12:00 ET", "2026-12-18", _ny(2026, 11, 18, 12, 0)),
]


@pytest.mark.parametrize("descripcion, vencimiento, instante", CASOS)
def test_comparacion_reproducible_anterior_frente_a_nuevo(descripcion, vencimiento, instante):
    S, K, r, sigma = 600.0, 600.0, 0.04, 0.15
    t_antes = _t_anterior(vencimiento, instante.astimezone(timezone.utc))           # servidor en UTC
    t_ahora = tv.anios(tv.horizonte("SPY", vencimiento), instante)
    p_antes, p_ahora = bs.precio(S, K, t_antes, r, sigma, "call"), bs.precio(S, K, t_ahora, r, sigma, "call")
    if descripcion.startswith("vence hoy"):
        assert t_antes == 0 and p_antes == 0.0 and t_ahora > 0 and p_ahora > 0.5       # antes: solo intrínseco (0)
    if "22:30" in descripcion:
        assert t_antes == 0 and t_ahora == pytest.approx((17 * 3600 + 45 * 60) / ANIO)  # antes perdía el día entero
    assert t_ahora >= 0 and p_ahora >= 0


# ---------------------------------------------------------------------------
# Cierre de H3-D2b: coherencia temporal y calidad de cotizaciones
# ---------------------------------------------------------------------------
def test_la_barra_de_un_minuto_se_fecha_con_su_inicio_y_el_precio_es_del_final():
    with reloj.fijar(_ny(2026, 11, 20, 15, 0)):
        assert tv.instante_del_cierre_de_barra(_ny(2026, 11, 20, 14, 30)) == _ny(2026, 11, 20, 14, 31)
        # El minuto en curso todavía no termina: el instante se recorta a la consulta.
        assert tv.instante_del_cierre_de_barra(_ny(2026, 11, 20, 14, 59, 30)) == _ny(2026, 11, 20, 15, 0)
    with pytest.raises(ValueError):
        tv.instante_del_cierre_de_barra(datetime(2026, 11, 20, 14, 30))


def test_ultimo_precio_antes_del_cierre_y_consulta_despues_del_vencimiento():
    """El contrato ya venció al consultar, pero se valora al instante del precio (antes del cierre): T > 0 y la pantalla
    debe presentarlo como valorización HISTÓRICA, no vigente."""
    h = tv.horizonte("SPY", "2026-11-20")
    with reloj.fijar(_ny(2026, 11, 21, 10, 0)):                               # sábado: consulta tras el vencimiento
        valoracion, del_precio = tv.instante_de_valoracion(_ny(2026, 11, 20, 15, 59))
        assert del_precio and tv.vencido_al_consultar(h)
        assert tv.anios(h, valoracion) == pytest.approx(16 * 60 / ANIO) and not tv.terminado(h, valoracion)
    fuente = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "derivados_ui.py"), encoding="utf-8").read()
    assert "valorización histórica" in fuente and "no una valorización vigente" in fuente
    assert "NO es la liquidación contractual" in fuente


def test_los_textos_no_afirman_contemporaneidad_ni_un_plazo_de_ejercicio_universal():
    fuente = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "derivados_ui.py"), encoding="utf-8").read()
    assert "se puede afirmar que sea contemporánea del precio del subyacente" in fuente
    assert "se toma como la del momento de la consulta" not in fuente
    assert "UMBRAL OPERATIVO DE ADVERTENCIA, no una garantía" in fuente
    assert "los intermediarios pueden fijar uno anterior" in fuente
    assert "intermediarios pueden fijar un plazo anterior" in tv.FUENTE_EJERCICIO


class _YahooSimulado:
    """Sustituto de yfinance sin red: cuenta las llamadas a history()."""
    llamadas = []

    def __init__(self, vacio_primero=False, sin_zona=False):
        self.vacio_primero, self.sin_zona = vacio_primero, sin_zona

    def Ticker(self, ticker):
        modulo = self

        class _T:
            def history(self, period, interval, timeout):
                import pandas as pd
                _YahooSimulado.llamadas.append((ticker, period, interval))
                if modulo.vacio_primero and period == "1d":
                    return pd.DataFrame(columns=["Close"])
                indice = pd.DatetimeIndex(["2026-11-20 15:58", "2026-11-20 15:59"])
                if not modulo.sin_zona:
                    indice = indice.tz_localize("America/New_York")
                return pd.DataFrame({"Close": [600.0, 601.0]}, index=indice)
        return _T()


@pytest.fixture
def yahoo(monkeypatch):
    import derivados_ui as ui
    _YahooSimulado.llamadas = []
    ui._precio_en_vivo_con_hora.clear()

    def poner(**kw):
        monkeypatch.setitem(sys.modules, "yfinance", _YahooSimulado(**kw))
        ui._precio_en_vivo_con_hora.clear()
        _YahooSimulado.llamadas = []
        return ui
    yield poner
    ui._precio_en_vivo_con_hora.clear()


@pytest.mark.simulada  # Yahoo Finance simulado (_YahooSimulado), sin red
def test_una_sola_consulta_liviana_por_subyacente_y_sin_redundancia(yahoo):
    ui = yahoo()
    with reloj.fijar(_ny(2026, 11, 20, 16, 30)):
        for _ in range(3):
            assert ui._precio_en_vivo("SPY") == 601.0
            precio, instante = ui._precio_en_vivo_con_hora("SPY")
    assert _YahooSimulado.llamadas == [("SPY", "1d", "1m")]                     # una sola llamada, de 1 día
    assert instante == _ny(2026, 11, 20, 16, 0)                                  # barra de las 15:59 → precio de las 16:00


@pytest.mark.simulada  # Yahoo Finance simulado (_YahooSimulado), sin red
def test_cinco_dias_solo_si_el_dia_viene_vacio(yahoo):
    ui = yahoo(vacio_primero=True)
    with reloj.fijar(_ny(2026, 11, 23, 8, 0)):
        ui._precio_en_vivo_con_hora("SPY")
    assert _YahooSimulado.llamadas == [("SPY", "1d", "1m"), ("SPY", "5d", "1m")]


@pytest.mark.simulada  # Yahoo Finance simulado (_YahooSimulado), sin red
def test_sin_zona_horaria_no_se_inventa_la_hora(yahoo):
    ui = yahoo(sin_zona=True)
    precio, instante = ui._precio_en_vivo_con_hora("SPY")
    assert precio == 601.0 and instante is None
    valoracion, del_precio = tv.instante_de_valoracion(instante)
    assert not del_precio                                                        # se usa la consulta y se dice
