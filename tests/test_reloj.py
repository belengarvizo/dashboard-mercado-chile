"""H3-D2: reloj centralizado y fechas de Santiago (offline; instantes fijados con reloj.fijar, sin tocar el reloj del sistema).

QUÉ SE PRUEBA
    - El resultado no depende de la zona del servidor: «ahora» se obtiene en UTC y se convierte con zoneinfo.
    - Horario de verano e invierno calculados por zoneinfo (no escritos a mano).
    - Desfases de fecha: 22:30 en Santiago ya es el día siguiente en UTC; 23:30 en Nueva York ya es el día siguiente en
      Santiago, pero la fecha de SESIÓN sigue siendo la de Nueva York.
    - Usar la fecha de Santiago como «hoy» no adelanta atrasos de los mercados de EE. UU.
    - La hora del pie de los PDF lleva su zona.
    - Los componentes de H3-D2 ya no leen el reloj del servidor.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(RAIZ)

import calendarios_financieros as calf  # noqa: E402
import reloj  # noqa: E402

UTC = timezone.utc


def test_hoy_es_la_fecha_de_santiago_y_no_la_del_servidor():
    # 02:30 UTC del 27-nov-2026 = 23:30 del 26-nov en Santiago (verano, UTC−3).
    with reloj.fijar(datetime(2026, 11, 27, 2, 30, tzinfo=UTC)):
        assert reloj.hoy_santiago() == date(2026, 11, 26)
        assert reloj.ahora_utc().date() == date(2026, 11, 27)                    # en UTC ya es el día siguiente
    # El mismo instante expresado con otra zona da exactamente lo mismo (el servidor podría estar en cualquiera).
    instante_chile = datetime(2026, 11, 26, 23, 30, tzinfo=reloj.ZONA_SANTIAGO)
    with reloj.fijar(instante_chile):
        assert reloj.hoy_santiago() == date(2026, 11, 26)
        assert reloj.ahora_utc() == datetime(2026, 11, 27, 2, 30, tzinfo=UTC)


def test_horario_de_verano_e_invierno_vienen_de_zoneinfo():
    with reloj.fijar(datetime(2026, 7, 15, 12, 0, tzinfo=UTC)):
        invierno = reloj.ahora_santiago().utcoffset()
    with reloj.fijar(datetime(2026, 12, 15, 12, 0, tzinfo=UTC)):
        verano = reloj.ahora_santiago().utcoffset()
    assert invierno == timedelta(hours=-4) and verano == timedelta(hours=-3)


def test_22_30_en_santiago_es_el_dia_siguiente_en_utc():
    instante = datetime(2026, 7, 15, 22, 30, tzinfo=reloj.ZONA_SANTIAGO)        # invierno: UTC−4
    assert instante.astimezone(UTC).date() == date(2026, 7, 16)
    with reloj.fijar(instante):
        assert reloj.hoy_santiago() == date(2026, 7, 15)


def test_23_30_en_nueva_york_es_el_dia_siguiente_en_santiago_pero_la_sesion_es_la_de_nueva_york():
    instante = datetime(2026, 11, 23, 23, 30, tzinfo=reloj.ZONA_NUEVA_YORK)     # lunes 23:30 en Nueva York
    assert reloj.fecha_de_sesion(instante, reloj.ZONA_NUEVA_YORK) == date(2026, 11, 23)
    with reloj.fijar(instante):
        assert reloj.hoy_santiago() == date(2026, 11, 24)                       # martes 01:30 en Santiago


def test_la_fecha_de_santiago_no_adelanta_atrasos_de_eeuu():
    """Entre las 22:00 y las 24:00 de Nueva York, Santiago ya cambió de fecha; la sesión de Nueva York de ese día ya cerró
    (16:00). Último precio del lunes: con «hoy» = martes en Santiago, la antigüedad es 1 y no falta ninguna sesión."""
    with reloj.fijar(datetime(2026, 11, 23, 23, 30, tzinfo=reloj.ZONA_NUEVA_YORK)):
        conteo = calf.sesiones_entre("nyse", date(2026, 11, 23), reloj.hoy_santiago())
    assert conteo.sesiones == 1 and conteo.faltantes == 0 and not conteo.atrasado()


def test_la_hora_del_pie_de_los_pdf_lleva_su_zona():
    with reloj.fijar(datetime(2026, 11, 27, 13, 5, tzinfo=UTC)):
        assert reloj.marca_de_generacion() == "27-11-2026 10:05 (hora de Santiago)"
    fuente = open(os.path.join(RAIZ, "informe_base.py"), encoding="utf-8").read()
    assert "reloj.marca_de_generacion()" in fuente and "datetime.now()" not in fuente
    dashboard = open(os.path.join(RAIZ, "app", "dashboard.py"), encoding="utf-8").read()
    assert "(Santiago time)" in dashboard


def test_fijar_exige_un_instante_con_zona():
    with pytest.raises(ValueError):
        with reloj.fijar(datetime(2026, 11, 27, 12, 0)):
            pass
    with pytest.raises(ValueError):
        reloj.fecha_de_sesion(datetime(2026, 11, 27, 12, 0), reloj.ZONA_NUEVA_YORK)


# Componentes de H3-D2: ya no leen el reloj del servidor. Quedan FUERA a propósito (y se listan en el informe):
# derivados_ui (alimenta la valorización: metodología pendiente de aprobación), Defensa Top-Down, Mesa de Dinero y el
# diario FX (secciones privadas que guardan en la base), y el cron (scripts/).
EN_ALCANCE = ("market_data.py", "renta_fija_ui.py", "renta_variable_ui.py", "commodities_ui.py", "fx_carry_ui.py",
              "informe_base.py", "fri/informes.py", "fri/interfaz.py")
RELOJ_DEL_SERVIDOR = re.compile(r"date\.today\(\)|datetime\.now\(|Timestamp\.now\(|Timestamp\.today\(")


@pytest.mark.parametrize("archivo", EN_ALCANCE)
def test_los_componentes_en_alcance_no_leen_el_reloj_del_servidor(archivo):
    codigo = [l for l in open(os.path.join(RAIZ, archivo), encoding="utf-8") if not l.lstrip().startswith("#")]
    assert not RELOJ_DEL_SERVIDOR.search("".join(codigo)), archivo


def test_en_el_dashboard_solo_quedan_relojes_fuera_de_alcance():
    lineas = open(os.path.join(RAIZ, "app", "dashboard.py"), encoding="utf-8").read().splitlines()
    con_reloj = [i for i, l in enumerate(lineas, 1) if RELOJ_DEL_SERVIDOR.search(l) and not l.lstrip().startswith("#")]
    # Todas están en el diario FX, Defensa Top-Down o la Mesa de Dinero (después de la definición de TZ_CHILE).
    inicio_privadas = next(i for i, l in enumerate(lineas, 1) if l.startswith("TZ_CHILE = "))
    assert con_reloj and all(i > inicio_privadas for i in con_reloj), con_reloj


# ---------------------------------------------------------------------------
# Comprobaciones de cierre de H3-D2
# ---------------------------------------------------------------------------
from zoneinfo import ZoneInfo  # noqa: E402

TOKIO = ZoneInfo("Asia/Tokyo")


def test_cambio_de_dia_entre_santiago_nueva_york_y_tokio():
    # 13:00 del martes 24-nov-2026 en Santiago (UTC−3) = 16:00 UTC = 11:00 en Nueva York = 01:00 del MIÉRCOLES en Tokio.
    with reloj.fijar(datetime(2026, 11, 24, 13, 0, tzinfo=reloj.ZONA_SANTIAGO)):
        assert reloj.hoy_santiago() == date(2026, 11, 24)
        assert reloj.hoy_en(reloj.ZONA_NUEVA_YORK) == date(2026, 11, 24)
        assert reloj.hoy_en(TOKIO) == date(2026, 11, 25)            # Tokio ya cambió de día: Santiago va ATRÁS
    # 23:30 del lunes en Nueva York = martes en Santiago y en Tokio.
    with reloj.fijar(datetime(2026, 11, 23, 23, 30, tzinfo=reloj.ZONA_NUEVA_YORK)):
        assert reloj.hoy_en(reloj.ZONA_NUEVA_YORK) == date(2026, 11, 23)
        assert reloj.hoy_santiago() == date(2026, 11, 24) and reloj.hoy_en(TOKIO) == date(2026, 11, 24)


def test_para_un_mercado_al_este_la_fecha_de_santiago_contaria_una_sesion_menos():
    """Por eso un mercado asiático debe usar hoy_en(su zona) y no la fecha de Santiago (documentado en reloj.py)."""
    instante = datetime(2026, 11, 24, 13, 0, tzinfo=reloj.ZONA_SANTIAGO)    # la sesión del martes en Tokio ya cerró
    with reloj.fijar(instante):
        con_santiago = calf.sesiones_entre("fx_24_5", date(2026, 11, 23), reloj.hoy_santiago())
        con_tokio = calf.sesiones_entre("fx_24_5", date(2026, 11, 23), reloj.hoy_en(TOKIO))
    assert (con_santiago.sesiones, con_tokio.sesiones) == (1, 2)


def test_la_referencia_de_santiago_no_cambia_las_fechas_de_los_datos():
    """La fecha económica de un dato (por ejemplo, la observación de la DFF de un sábado) se conserva; la frescura se mide
    con el calendario de PUBLICACIÓN, separado del de observaciones."""
    import market_data as md
    item = {"etiqueta": "TPM EEUU", "cadencia": "diaria", "resultado": (3.88, 0.0, pd.Timestamp("2026-11-28"), 0.0),
            "calendario": md.CALENDARIO_DE_INDICADOR["TPM EEUU"]}
    assert md._badge_visible(item, date(2026, 11, 30)) is True
    assert item["resultado"][2] == pd.Timestamp("2026-11-28")                 # la fecha del dato no se tocó
    assert item["frescura"].calendarios == ("fed_nueva_york",) and item["frescura"].faltantes == 0


def test_la_hora_de_generacion_del_pdf_no_cambia_su_fecha_de_corte_ni_sus_resultados():
    import informe_renta_fija as inf
    import test_informe_renta_fija_ventana as v
    tasa = v._tasa()
    macro, precios = v._macro(tasa), v._precios(tasa)
    resultados, textos = [], []
    for instante in (datetime(2026, 11, 17, 3, 30, tzinfo=UTC), datetime(2027, 3, 1, 23, 59, tzinfo=reloj.ZONA_SANTIAGO)):
        with reloj.fijar(instante):
            datos = inf.calcular(macro, precios, v.DIAS, v.MES, fecha_corte="2026-11-11")
            resultados.append((repr(datos["fechas"]), repr(datos["etfs"]), inf._lineas_de_fechas(datos)))
            texto, _ = v._texto_pdf(inf.generar(macro, precios, v.MES, fecha_corte="2026-11-11"))
            textos.append(re.sub(r"generado el [^\n]*", "", texto))
    assert resultados[0] == resultados[1]
    assert textos[0] == textos[1]                                              # solo cambia la línea «generado el …»
