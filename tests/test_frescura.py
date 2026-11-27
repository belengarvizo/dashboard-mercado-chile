"""H3-D3: estados de frescura por frecuencia, calendario y plazo de publicación (offline, fechas fijas).

QUÉ SE PRUEBA
    - Los cinco estados: vigente, posiblemente atrasado, atrasado, no disponible y cobertura desconocida.
    - Diarias (con rezago esperado por publicación y cron), semanales, mensuales y trimestrales.
    - Una serie mensual o trimestral nunca queda «atrasada» por no tener datos diarios, ni con plazos no verificados.
    - Un calendario no verificado nunca produce «atrasado».
    - Coherencia con los motores: «atrasado» usa el mismo umbral (más de 5 sesiones); todo lo que el motor marca atrasado
      no aparece como vigente en FRI.
    - Un informe histórico se evalúa contra su fecha de corte, no contra el reloj.
    - Los panoramas de FRI muestran el estado.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import sys
from datetime import date, datetime, timezone

import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import calendarios_financieros as calf  # noqa: E402
import frescura as f  # noqa: E402
import reloj  # noqa: E402

DFF = f.PERFILES_DE_SERIE["Tasa de política monetaria de EEUU (Effective Federal Funds Rate)"]
IPC = f.PERFILES_DE_SERIE["IPC variación 12 meses (inflación anual, empalme base 2023=100)"]
ICSA = f.PERFILES_DE_SERIE["Solicitudes iniciales de seguro de desempleo de EEUU (ICSA)"]


def test_no_disponible():
    assert f.evaluar(pd.Series(dtype=float), DFF, "2026-11-20").estado == f.NO_DISPONIBLE
    assert f.evaluar(None, IPC, "2026-11-20").estado == f.NO_DISPONIBLE


@pytest.mark.parametrize("ultima, estado", [
    ("2026-11-19", f.VIGENTE),                 # ref viernes 20-nov: falta el jueves → dentro del rezago (2)
    ("2026-11-18", f.VIGENTE),                 # faltan 19 y... → faltantes 1 (19) con [18, 20) → vigente
    ("2026-11-16", f.POSIBLEMENTE_ATRASADO),   # faltan 17, 18, 19 → 3 > 2, antigüedad 4 ≤ 5
    ("2026-11-12", f.ATRASADO),                # antigüedad 6 > 5 (11-nov es feriado de la Fed de Nueva York)
])
def test_diaria_con_calendario_verificado(ultima, estado):
    assert f.evaluar(ultima, DFF, "2026-11-20").estado == estado


def test_diaria_con_calendario_no_verificado_nunca_es_atrasado():
    spx = f.perfil_de_instrumento("^GSPC")
    assert f.evaluar("2026-11-19", spx, "2026-11-20").estado == f.COBERTURA_DESCONOCIDA
    lejos = f.evaluar("2026-10-01", spx, "2026-11-20")
    assert lejos.estado == f.POSIBLEMENTE_ATRASADO and "aproximación" in lejos.texto


def test_mensual_vigente_aunque_tenga_meses_y_nunca_atrasada():
    # IPC de septiembre (fechado 1-sep). El de octubre se espera hacia el 8-nov (+7 de tolerancia).
    assert f.evaluar("2026-09-01", IPC, "2026-11-10").estado == f.VIGENTE
    tarde = f.evaluar("2026-09-01", IPC, "2026-11-20")
    assert tarde.estado == f.POSIBLEMENTE_ATRASADO and "10-2026" in tarde.texto
    assert f.evaluar("2025-09-01", IPC, "2026-11-20").estado == f.POSIBLEMENTE_ATRASADO     # nunca «atrasado» (supuesto)


def test_trimestral():
    trimestral = f.Perfil("trimestral", plazo_publicacion_dias=60, nota="sintético")
    assert f.evaluar("2026-04-01", trimestral, "2026-11-01").estado == f.VIGENTE   # T3 se espera hacia fines de nov
    assert f.evaluar("2026-04-01", trimestral, "2026-12-15").estado == f.POSIBLEMENTE_ATRASADO


def test_semanal():
    assert f.evaluar("2026-11-14", ICSA, "2026-11-27").estado == f.VIGENTE          # 7 + 5 + 7 días de margen
    assert f.evaluar("2026-11-01", ICSA, "2026-11-27").estado == f.POSIBLEMENTE_ATRASADO


def test_un_informe_historico_se_evalua_contra_su_corte_y_no_contra_el_reloj():
    for instante in (datetime(2026, 11, 21, 12, tzinfo=timezone.utc), datetime(2027, 6, 1, 12, tzinfo=timezone.utc)):
        with reloj.fijar(instante):
            assert f.evaluar("2026-11-12", DFF, referencia="2026-11-13").estado == f.VIGENTE


def test_sin_referencia_usa_la_fecha_de_santiago():
    with reloj.fijar(datetime(2026, 11, 21, 2, 30, tzinfo=timezone.utc)):     # 23:30 del 20-nov en Santiago
        assert f.evaluar("2026-11-19", DFF).referencia == date(2026, 11, 20)


DIARIAS = {n: pf for n, pf in f.PERFILES_DE_SERIE.items() if pf.frecuencia == "diaria"}


@pytest.mark.parametrize("nombre", sorted(DIARIAS))
def test_coherencia_con_los_motores(nombre):
    """El motor marca atrasado con antigüedad > 5 sesiones; FRI nunca muestra ese dato como vigente, y solo dice
    «atrasado» (categórico) si el motor también lo hace. Para todos los perfiles diarios y ocho semanas de fechas."""
    perfil = DIARIAS[nombre]
    ref = date(2026, 11, 20)
    for ultima in pd.bdate_range("2026-09-25", "2026-11-19").date:
        motor_atrasado = calf.sesiones_entre(perfil.calendario, ultima, ref).atrasado()
        estado = f.evaluar(ultima, perfil, ref).estado
        if motor_atrasado:
            assert estado in (f.ATRASADO, f.POSIBLEMENTE_ATRASADO), (nombre, ultima)
        if estado == f.ATRASADO:
            assert motor_atrasado, (nombre, ultima)


def test_el_rezago_esperado_no_choca_con_el_umbral_de_atraso():
    """Descontar el rezago nunca vuelve «vigente» un dato que el motor ya considera atrasado."""
    for nombre, perfil in DIARIAS.items():
        assert perfil.rezago_sesiones < calf.UMBRAL_SESIONES_DE_ATRASO, nombre


def test_fechas_oficiales_del_ine():
    # IPC de octubre (fechado 1-oct): el de noviembre tiene fecha oficial 07-12-2026 (INE) → no estimado.
    e = f.evaluar("2026-10-01", IPC, "2026-12-10")
    assert e.estado == f.VIGENTE and not e.estimado and "07-12-2026" in e.texto and "INE" in e.texto
    tarde = f.evaluar("2026-10-01", IPC, "2026-12-15")              # 07-12 + 7 días de margen del proveedor
    assert tarde.estado == f.POSIBLEMENTE_ATRASADO and not tarde.estimado
    # Desocupación: trimestre móvil ago-oct fechado 01-10; sep-nov (fechado 01-11) se publica el 30-12-2026.
    des = f.PERFILES_DE_SERIE["Tasa de desocupación nacional (INE, sin ajuste estacional)"]
    assert f.evaluar("2026-10-01", des, "2026-12-29").estado == f.VIGENTE
    assert f.evaluar("2026-10-01", des, "2027-01-07").estado == f.POSIBLEMENTE_ATRASADO


def test_fechas_oficiales_del_bls():
    unrate = f.PERFILES_DE_SERIE["Tasa de desempleo de EEUU (UNRATE)"]
    e = f.evaluar("2026-09-01", unrate, "2026-11-20")              # octubre se publicó el 06-11-2026
    assert e.estado == f.POSIBLEMENTE_ATRASADO and not e.estimado and "06-11-2026" in e.texto
    assert f.evaluar("2026-10-01", unrate, "2026-12-05").estado == f.VIGENTE          # noviembre: 04-12-2026


def test_sin_fecha_oficial_el_estado_es_estimado():
    imacec = f.PERFILES_DE_SERIE["IMACEC variación 12 meses"]
    e = f.evaluar("2026-09-01", imacec, "2026-11-20")
    assert e.estimado and "supuesta" in e.texto and "Estado estimado" in e.texto
    tpm = f.PERFILES_DE_SERIE["Tasa de política monetaria (TPM)"]
    assert f.evaluar("2026-11-18", tpm, "2026-11-20").estimado                       # rezago BCCh supuesto
    assert not f.evaluar("2026-11-19", DFF, "2026-11-20").estimado                    # publicación EFFR verificada


def test_la_carga_programada_no_se_presenta_como_actualizacion():
    e = f.evaluar("2026-11-19", DFF, "2026-11-20")
    assert "no registra cuándo se cargó" in e.texto


def test_tpm_constante_se_evalua_por_fecha_y_no_por_valor():
    tpm = f.PERFILES_DE_SERIE["Tasa de política monetaria (TPM)"]
    fechas = pd.bdate_range("2026-06-01", "2026-11-19")
    constante = pd.Series(4.5, index=fechas)                                        # meses sin cambio de la TPM
    assert f.evaluar(constante, tpm, "2026-11-20").estado == f.VIGENTE


def test_nan_al_final_no_cuenta_como_dato():
    s = pd.Series([1.0, 2.0, float("nan")], index=pd.DatetimeIndex(["2026-11-11", "2026-11-12", "2026-11-19"]))
    e = f.evaluar(s, DFF, "2026-11-20")
    assert e.ultima == date(2026, 11, 12) and e.estado == f.ATRASADO


def test_fechas_posteriores_a_la_referencia_se_ignoran():
    s = pd.Series([1.0, 2.0], index=pd.DatetimeIndex(["2026-11-12", "2026-12-01"]))
    e = f.evaluar(s, DFF, "2026-11-13")                              # informe con corte 13-11: el dato de diciembre no existía
    assert e.estado == f.VIGENTE and e.ultima == date(2026, 11, 12) and "Se ignoraron 1" in e.texto
    solo_futuro = f.evaluar("2026-12-01", DFF, "2026-11-13")
    assert solo_futuro.estado == f.NO_DISPONIBLE and "hasta el 13-11-2026" in solo_futuro.texto


def test_todos_los_perfiles_usan_calendarios_existentes():
    for nombre, perfil in f.PERFILES_DE_SERIE.items():
        assert perfil.frecuencia in ("diaria", "semanal", "mensual", "trimestral"), nombre
        if perfil.frecuencia == "diaria":
            assert perfil.calendario in calf.disponibles(), nombre
        assert perfil.nota, nombre                                   # todo plazo o rezago está documentado


def test_los_panoramas_muestran_el_estado():
    import fri.panoramas as p
    s = pd.Series([1.0, 2.0], index=pd.DatetimeIndex(["2026-11-11", "2026-11-12"]))
    with reloj.fijar(datetime(2026, 11, 20, 15, tzinfo=timezone.utc)):
        html = p.tarjeta("Prueba", s, "FRED", perfil=DFF)
        assert "fri-frescura-atrasado" in html and "Atrasado" in html
        assert p.estado_html(s, None) == ""                                          # sin perfil, sin rótulo
        assert p.estado_html(pd.Series([1.0], index=pd.DatetimeIndex(["2026-11-19"])), DFF, solo_si_no_vigente=True) == ""
        bcch = f.PERFILES_DE_SERIE["Tipo de cambio observado"]
        rotulo = p.estado_html(pd.Series([1.0], index=pd.DatetimeIndex(["2026-11-19"])), bcch)
        assert "Vigente (estimado)" in rotulo and '"' not in rotulo.split('title="')[1].split('">')[0]
