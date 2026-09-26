"""Guarda contra la regresión que rompió el cron en producción el
2026-09-25: con DATABASE_URL="postgresql://..." (esquema ambiguo, sin
sufijo de driver), una versión más nueva de SQLAlchemy resolvió el
dialecto por default a psycopg (v3) -- no instalado, requirements.txt
solo trae psycopg2-binary -- y los 4 pasos de actualizar_todo.py
fallaron con "ModuleNotFoundError: No module named 'psycopg'" apenas
intentaban conectarse a la BD. get_engine() ahora fuerza el driver
psycopg2 explícito en la URL, sin importar qué esquema venga en
DATABASE_URL. create_engine() no conecta de forma ansiosa, así que este
test no necesita una BD real ni red.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from models import get_engine


def _con_database_url(url, func):
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        return func()
    finally:
        if original is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original


def test_esquema_postgresql_ambiguo_se_fuerza_a_psycopg2():
    engine = _con_database_url("postgresql://usuario:pass@host:5432/db", get_engine)
    assert engine.url.drivername == "postgresql+psycopg2", engine.url.drivername
    print("OK: postgresql:// -> postgresql+psycopg2")


def test_esquema_postgres_viejo_estilo_heroku_tambien_se_fuerza():
    engine = _con_database_url("postgres://usuario:pass@host:5432/db", get_engine)
    assert engine.url.drivername == "postgresql+psycopg2", engine.url.drivername
    print("OK: postgres:// (viejo estilo) -> postgresql+psycopg2")


def test_esquema_ya_explicito_no_se_toca():
    engine = _con_database_url("postgresql+psycopg2://usuario:pass@host:5432/db", get_engine)
    assert engine.url.drivername == "postgresql+psycopg2", engine.url.drivername
    print("OK: postgresql+psycopg2:// explícito queda igual")


def test_ninguna_consulta_puede_colgarse_para_siempre():
    """El servidor viene con statement_timeout=0 (sin límite): sin un tope
    del lado del cliente, una conexión del pool ya muerta dejaba al
    dashboard esperando para siempre (indicador "running" girando, CPU en
    0%). get_engine() debe fijar statement_timeout, keepalives de TCP para
    detectar la conexión muerta, y connect_timeout."""
    from models import CONNECT_ARGS_POSTGRES as args, SEGUNDOS_RECICLAR_CONEXION

    assert "statement_timeout" in args.get("options", ""), args.get("options")
    assert args.get("keepalives") == 1, args
    # detección de conexión muerta acotada: idle + interval * count
    deteccion = args["keepalives_idle"] + args["keepalives_interval"] * args["keepalives_count"]
    assert deteccion <= 60, f"detectar una conexión muerta tardaría {deteccion}s"
    assert args.get("connect_timeout"), args
    # y las conexiones viejas se reciclan antes de pudrirse en el pool
    assert 0 < SEGUNDOS_RECICLAR_CONEXION <= 600, SEGUNDOS_RECICLAR_CONEXION

    # que además lleguen de verdad al engine, no solo que existan las constantes
    engine = _con_database_url("postgresql://usuario:pass@host:5432/db", get_engine)
    assert engine.pool._recycle == SEGUNDOS_RECICLAR_CONEXION, engine.pool._recycle
    print("OK: statement_timeout + keepalives + connect_timeout + pool_recycle")


if __name__ == "__main__":
    test_esquema_postgresql_ambiguo_se_fuerza_a_psycopg2()
    test_esquema_postgres_viejo_estilo_heroku_tambien_se_fuerza()
    test_esquema_ya_explicito_no_se_toca()
    test_ninguna_consulta_puede_colgarse_para_siempre()
    print("OK: las cuatro pruebas pasaron.")
