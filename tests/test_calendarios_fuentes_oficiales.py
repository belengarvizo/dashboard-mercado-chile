"""H3-D1: FECHAS REALES de los calendarios versionados, tal como las publican las fuentes oficiales consultadas el 25-11-2026
(NYSE, SIFMA, Reserva Federal, Reserva Federal de Nueva York, ICE Futures U.S., gob.cl y CMF). Ver calendarios/*.json.

QUÉ SE PRUEBA
    - Feriados exclusivos de Chile (8-dic-2026) y de EE. UU. (Thanksgiving, 26-nov-2026).
    - Diferencia entre la NYSE y la renta fija de EE. UU. (Columbus y Veterans Day: NYSE abierta; SIFMA recomienda cerrar).
    - Transición de diciembre de 2026 a enero de 2027.
    - Sesiones reducidas verificadas (NYSE 27-nov-2026; SIFMA, Viernes Santo 2026 con cierre anticipado y no total).
    - Calendarios sin cobertura (Bolsa de Santiago, CME, Nasdaq) o vencidos, que nunca se toman como cerrados.
    - El badge de frescura y el aviso de atraso usan el calendario de cada serie.
    - Contraste con bibliotecas locales (solo si están instaladas; no son la fuente).
No hay cierres extraordinarios verificados en 2025–2027 en las fuentes consultadas: la lógica de cierres extraordinarios se
prueba con datos sintéticos en test_calendarios_logica.py.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import sys
from datetime import date

import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import calendarios_financieros as calf  # noqa: E402

D = date


def test_todos_los_calendarios_registran_su_trazabilidad():
    for id_calendario in calf.disponibles():
        c = calf.cargar(id_calendario)
        assert c.nombre and c.mercado_o_fuente and c.fuente_oficial and c.limitaciones, id_calendario
        assert c.fecha_verificacion == D(2026, 11, 25), id_calendario
        for fecha in c.feriados:                                  # ningún feriado cae fuera de un año razonable
            assert D(2025, 1, 1) <= fecha <= D(2028, 12, 31), (id_calendario, fecha)
    assert calf.cargar("sifma_renta_fija_eeuu").es_recomendacion is True
    assert calf.cargar("bcch_series").supuesto                     # el supuesto queda escrito, no implícito


def test_feriado_exclusivo_de_chile_y_de_eeuu():
    inmaculada, thanksgiving = D(2026, 12, 8), D(2026, 11, 26)
    assert calf.es_sesion("chile_bancario", inmaculada) is False and calf.es_sesion("fed_nueva_york", inmaculada) is True
    assert calf.es_sesion("nyse", inmaculada) is True
    assert calf.es_sesion("chile_bancario", thanksgiving) is True and calf.es_sesion("nyse", thanksgiving) is False
    assert calf.es_sesion("fed_nueva_york", thanksgiving) is False and calf.es_sesion("ice_futures_us_blandos", thanksgiving) is False


@pytest.mark.parametrize("fecha", [D(2026, 10, 12), D(2026, 11, 11)])
def test_nyse_abierta_y_renta_fija_cerrada_en_columbus_y_veterans_day(fecha):
    assert calf.es_sesion("nyse", fecha) is True
    assert calf.es_sesion("sifma_renta_fija_eeuu", fecha) is False
    assert calf.es_sesion("fed_nueva_york", fecha) is False
    assert calf.es_sesion("ice_futures_us_blandos", fecha) is True          # el café abre esos días (aviso de ICE)


def test_independence_day_2026_la_junta_cierra_y_la_fed_de_nueva_york_abre():
    viernes = D(2026, 7, 3)
    assert calf.es_sesion("fed_junta", viernes) is False and calf.es_sesion("fed_nueva_york", viernes) is True
    assert calf.es_sesion("nyse", viernes) is False


def test_sesiones_reducidas_cuentan_como_sesion():
    assert calf.es_sesion("nyse", D(2026, 11, 27)) is True and D(2026, 11, 27) in calf.cargar("nyse").sesiones_reducidas
    viernes_santo = D(2026, 4, 3)
    assert calf.es_sesion("sifma_renta_fija_eeuu", viernes_santo) is True        # cierre anticipado, no total
    assert "12:00" in calf.cargar("sifma_renta_fija_eeuu").sesiones_reducidas[viernes_santo]
    assert calf.es_sesion("nyse", viernes_santo) is False


def test_transicion_de_diciembre_2026_a_enero_2027():
    # Fed de Nueva York (cubierta 2026–2027): 31-dic jueves sesión, 1-ene feriado → del 30-dic al 4-ene: 30 y 31.
    nyfed = calf.sesiones_entre("fed_nueva_york", D(2026, 12, 30), D(2027, 1, 4))
    assert nyfed.verificado and nyfed.sesiones == 2
    # Banca chilena (cubierta solo 2026): el 31-dic es feriado bancario y 2027 no está verificado → aproximación rotulada.
    chile = calf.sesiones_entre("chile_bancario", D(2026, 12, 30), D(2027, 1, 4))
    assert not chile.verificado and chile.sesiones == 2                           # 30-dic y 1-ene (no verificado)
    assert calf.es_sesion("chile_bancario", D(2027, 1, 1)) is None               # nunca «cerrado» por falta de calendario
    # NYSE (cubierta 2026–2028): 1-ene-2027 feriado.
    assert calf.sesiones_entre("nyse", D(2026, 12, 30), D(2027, 1, 4)).sesiones == 2


def test_lo_que_antes_fallaba_desde_el_4_de_enero_de_2027():
    """Con la lista manual de 2026, desde el 4-ene-2027 la DFF contaba el 1-ene-2027 como hábil. Ahora no."""
    conteo = calf.sesiones_entre("fed_nueva_york", D(2026, 12, 31), D(2027, 1, 4))
    assert conteo.verificado and conteo.sesiones == 1                           # solo el 31-dic


@pytest.mark.parametrize("calendario", ["bolsa_santiago", "cme_group", "nasdaq", "eeuu_bolsa_no_registrada", "ice_futures_us_divisas"])
def test_calendarios_sin_cobertura_nunca_se_toman_como_cerrados(calendario):
    assert calf.es_sesion(calendario, D(2026, 12, 25)) is None
    assert not calf.sesiones_entre(calendario, D(2026, 12, 21), D(2026, 12, 28)).verificado


def test_badge_de_frescura_con_el_calendario_de_cada_serie():
    import market_data as md
    def item(etiqueta, fecha):
        return {"etiqueta": etiqueta, "cadencia": "diaria", "resultado": (1.0, 0.0, pd.Timestamp(fecha), 0.0),
                "calendario": md.CALENDARIO_DE_INDICADOR[etiqueta]}
    # Referencia: miércoles 9-dic-2026. USD/CLP del lunes 7: el martes 8 es feriado en Chile → 1 sesión: badge visible.
    assert md._badge_visible(item("USD/CLP", "2026-12-07"), D(2026, 12, 9)) is True
    # La DFF del mismo lunes sí queda 2 sesiones atrás (el 8 es hábil en la Fed de Nueva York): badge oculto.
    assert md._badge_visible(item("TPM EEUU", "2026-12-07"), D(2026, 12, 9)) is False


def test_aviso_de_atraso_del_diferencial_tpm_fed():
    import renta_fija_ui as rfui
    dif = {"fecha_referencia": pd.Timestamp("2026-11-13")}
    texto = rfui.texto_atraso_diferencial(dif, pd.Timestamp("2026-11-24"))
    # Días abiertos en las dos plazas del 13 al 23-nov: 13, 16, 17, 18, 19, 20, 23 = 7 (ningún feriado común).
    assert "7 días hábiles" in texto and "unos" not in texto
    fuera = rfui.texto_atraso_diferencial({"fecha_referencia": pd.Timestamp("2026-12-21")}, pd.Timestamp("2027-01-11"))
    assert "unos" in fuera and "no verificado" in fuera                          # 2027 de Chile no verificado: aproximación


def test_contraste_con_bibliotecas_locales_si_existen():
    """Solo contraste: las bibliotecas no son la fuente. Se omite si no están instaladas (no están en requirements)."""
    xcals = pytest.importorskip("exchange_calendars")
    xnys = xcals.get_calendar("XNYS", start="2025-12-01", end="2027-12-31")
    nyse = calf.cargar("nyse")
    sesiones_bib = {d.date() for d in xnys.sessions_in_range("2026-01-01", "2027-12-31")}
    for anio in (2026, 2027):
        dias = pd.bdate_range(f"{anio}-01-01", f"{anio}-12-31")
        cerrados_bib = {d.date() for d in dias if d.date() not in sesiones_bib}
        cerrados_json = {d.date() for d in dias if calf.es_sesion(nyse, d) is False}
        assert cerrados_bib == cerrados_json, (anio, sorted(cerrados_bib ^ cerrados_json))


def test_dff_calendario_de_observaciones_distinto_del_de_publicacion():
    nyfed = calf.cargar("fed_nueva_york")
    assert "OBSERVACIONES" in open(os.path.join(calf.CARPETA, "fed_nueva_york.json"), encoding="utf-8").read()
    # Una observación de la DFF fechada un sábado (FRED repite la tasa) no es una publicación: del sábado al lunes no
    # falta ninguna sesión de publicación.
    conteo = calf.sesiones_entre(nyfed, D(2026, 11, 28), D(2026, 11, 30))
    assert conteo.sesiones == 0 and conteo.faltantes == 0
    # En días corridos (calendario de observaciones) sí son 2 días.
    assert calf.sesiones_entre("dias_corridos", D(2026, 11, 28), D(2026, 11, 30)).sesiones == 2


def test_el_calendario_del_bcch_se_declara_como_aproximacion():
    texto = calf.cargar("bcch_series").supuesto
    assert "APROXIMACIÓN" in texto and "No es una verificación individual de cada serie" in texto


INVENTARIO = {"nyse", "nasdaq", "sifma_renta_fija_eeuu", "fed_junta", "fed_nueva_york", "chile_bancario", "bcch_series",
              "bolsa_santiago", "ice_futures_us_blandos", "ice_futures_us_divisas", "cme_group", "eeuu_bolsa_no_registrada",
              "fx_24_5", "dias_corridos"}


def test_las_14_fichas_coinciden_con_el_inventario_y_con_su_nombre_de_archivo():
    import json
    assert set(calf.disponibles()) == INVENTARIO and len(INVENTARIO) == 14
    for id_calendario in INVENTARIO:
        with open(os.path.join(calf.CARPETA, f"{id_calendario}.json"), encoding="utf-8") as f:
            datos = json.load(f)
        assert datos["id"] == id_calendario
        assert datos.get("base") is None or datos["base"] in INVENTARIO


def test_todo_calendario_usado_por_el_dashboard_existe():
    import market_data as md
    import renta_fija_ui as rfui
    usados = set(md.CALENDARIO_DE_INDICADOR.values()) | set(rfui.CALENDARIOS_DIFERENCIAL_TPM_FED) | {"fx_24_5", "eeuu_bolsa_no_registrada"}
    usados |= {calf.calendario_de_instrumento(t) for t in ("X.SN", "EURUSD=X", "KC=F", "CL=F", "DX-Y.NYB", "SPY")}
    assert usados <= INVENTARIO
