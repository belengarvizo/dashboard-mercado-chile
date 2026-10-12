"""Las horas del diario tienen que ser las que la usuaria escribió.

EL BUG QUE ESTO PREVIENE. La sesión de PostgreSQL corre en Etc/UTC
(verificado con SHOW TimeZone contra la base de producción). Las columnas de
fecha del diario son TIMESTAMPTZ, así que un datetime INGENUO se guarda como
si fuera UTC: una operación abierta a las 10:00 de Chile quedaba registrada a
las 07:00 de Chile. Tres horas de error, y encima invisible al desarrollar en
una máquina que ya está en hora de Chile.

Además el torneo cruza el cambio de hora de Estados Unidos el 1 de noviembre,
así que se prueba una fecha de cada lado: con un desfase fijo en vez de zonas
horarias reales, la última semana del torneo saldría corrida.

ESTE TEST ESCRIBE EN LA BASE, dentro de una transacción que SIEMPRE se
revierte. No deja ninguna fila en el diario real.
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from models import get_engine

TZ_CHILE = ZoneInfo("America/Santiago")
TZ_NY = ZoneInfo("America/New_York")

INSERT = (
    "INSERT INTO trading_operaciones "
    "(instrumento, categoria, direccion, fecha_apertura, precio_entrada, lotes) "
    "VALUES ('EURUSD','divisas','compra',:fa,1.1,0.01) RETURNING id"
)


def _ida_y_vuelta(conn, momento_chile):
    """Guarda un instante y lo vuelve a leer convertido a hora de Chile."""
    id_op = conn.execute(text(INSERT), {"fa": momento_chile}).scalar()
    leido = conn.execute(
        text("SELECT fecha_apertura FROM trading_operaciones WHERE id=:i"), {"i": id_op}
    ).scalar()
    return leido.astimezone(TZ_CHILE)


def test_la_hora_guardada_es_la_que_se_escribio_antes_y_despues_del_1_de_noviembre():
    casos = [
        # (lo que la usuaria escribe en el formulario, descripción)
        (datetime(2026, 10, 14, 10, 30, tzinfo=TZ_CHILE), "antes del cambio de hora de EEUU"),
        (datetime(2026, 11, 4, 10, 30, tzinfo=TZ_CHILE), "después del cambio de hora de EEUU"),
    ]
    engine = get_engine()
    con = engine.connect()
    tx = con.begin()
    try:
        for escrito, descripcion in casos:
            vuelta = _ida_y_vuelta(con, escrito)
            assert vuelta == escrito, (
                f"{descripcion}: se escribió {escrito:%d-%m %H:%M %Z} y volvió "
                f"{vuelta:%d-%m %H:%M %Z}")
            assert vuelta.hour == 10 and vuelta.minute == 30, vuelta
    finally:
        tx.rollback()
        con.close()


def test_un_datetime_ingenuo_se_guardaria_mal_y_por_eso_hay_que_ponerle_zona():
    """Demuestra que el arreglo hace falta: el MISMO instante, guardado sin
    zona horaria, vuelve corrido. Si este test empieza a fallar es porque la
    base cambió de zona, y entonces hay que revisar el resto."""
    engine = get_engine()
    con = engine.connect()
    tx = con.begin()
    try:
        zona_sesion = con.execute(text("SHOW TimeZone")).scalar()
        if zona_sesion in ("America/Santiago", "localtime"):
            return  # en esa configuración no habría desfase; nada que demostrar

        con_zona = datetime(2026, 10, 14, 10, 30, tzinfo=TZ_CHILE)
        ingenuo = datetime(2026, 10, 14, 10, 30)

        hora_con_zona = _ida_y_vuelta(con, con_zona).hour
        hora_ingenua = _ida_y_vuelta(con, ingenuo).hour

        assert hora_con_zona == 10, hora_con_zona
        assert hora_ingenua != 10, (
            f"con TimeZone={zona_sesion} se esperaba que el datetime ingenuo quedara "
            f"corrido, pero volvió a las {hora_ingenua}")
    finally:
        tx.rollback()
        con.close()


def test_las_escrituras_de_prueba_nunca_se_confirman():
    """Red de seguridad de los dos tests de arriba.

    No se puede buscar "filas con fecha de prueba": una operación real puede
    caer en cualquier fecha. Lo que sí se puede comprobar es la propiedad que
    de verdad importa — que una escritura dentro de una transacción revertida
    no queda — y eso se verifica escribiendo una fila marcada y confirmando
    que, tras el rollback, no existe."""
    marca = "prueba-rollback-zona-horaria"
    engine = get_engine()
    con = engine.connect()
    tx = con.begin()
    try:
        con.execute(text(
            "INSERT INTO trading_operaciones (instrumento, categoria, direccion, "
            "fecha_apertura, precio_entrada, lotes, notas) VALUES "
            "('EURUSD','divisas','compra', now(), 1.1, 0.01, :m)"), {"m": marca})
        assert con.execute(text(
            "SELECT COUNT(*) FROM trading_operaciones WHERE notas = :m"),
            {"m": marca}).scalar() == 1, "la fila ni siquiera se insertó"
    finally:
        tx.rollback()
        con.close()

    with engine.connect() as con2:
        quedaron = con2.execute(text(
            "SELECT COUNT(*) FROM trading_operaciones WHERE notas = :m"),
            {"m": marca}).scalar()
    assert quedaron == 0, "el rollback no revirtió la escritura de prueba"


def test_el_desfase_nueva_york_chile_cambia_el_1_de_noviembre():
    """Los eventos del torneo (CPI 14-oct 8:30 NY, FOMC 28-oct 14:00 NY) se
    guardan en hora de Nueva York y se muestran en hora de Chile. El desfase
    NO es constante: son +1h hasta el 1-nov y +2h después, porque EEUU sale
    del horario de verano y Chile no. Un offset fijo rompería la última
    semana del torneo, que cierra el 6 de noviembre."""
    def diferencia(iso):
        en_ny = datetime.strptime(iso, "%Y-%m-%d %H:%M").replace(tzinfo=TZ_NY)
        en_cl = en_ny.astimezone(TZ_CHILE)
        return int((en_cl.utcoffset() - en_ny.utcoffset()).total_seconds() / 3600)

    assert diferencia("2026-10-14 08:30") == 1, "CPI de octubre: Chile debería ir +1h"
    assert diferencia("2026-10-28 14:00") == 1, "FOMC de octubre: Chile debería ir +1h"
    assert diferencia("2026-11-04 08:30") == 2, "después del 1-nov Chile va +2h"


if __name__ == "__main__":
    test_la_hora_guardada_es_la_que_se_escribio_antes_y_despues_del_1_de_noviembre()
    test_un_datetime_ingenuo_se_guardaria_mal_y_por_eso_hay_que_ponerle_zona()
    test_las_escrituras_de_prueba_nunca_se_confirman()
    test_el_desfase_nueva_york_chile_cambia_el_1_de_noviembre()
    print("OK: las cuatro pruebas pasaron.")
