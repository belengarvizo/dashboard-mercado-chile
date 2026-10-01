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


def test_el_engine_se_reusa_en_vez_de_crear_un_pool_nuevo_por_llamada():
    """Antes, get_engine() llamaba a create_engine() CADA vez, así que cada
    llamador se llevaba su propio pool y ninguno se cerraba. get_session()
    crea un engine por sesión, y hay bucles que la llaman una vez por ticker
    (test_heatmap_atraso abre 30 seguidas, una por acción del IPSA): 30
    handshakes contra Postgres donde debería haber uno reusado, lo que
    multiplica por 30 la chance de caer en una ventana mala de la red y
    además desperdicia pool_pre_ping y pool_recycle, que solo sirven si las
    conexiones se reusan de verdad."""
    url = "postgresql://usuario:pass@host:5432/db_reuso"
    primero = _con_database_url(url, get_engine)
    segundo = _con_database_url(url, get_engine)
    assert primero is segundo, (
        "get_engine() devolvió dos engines distintos para la misma URL: "
        "cada llamada estaría armando un pool de conexiones nuevo"
    )


def test_urls_distintas_no_comparten_engine():
    """La memorización es por URL: apuntar a otra base no debe devolver el
    engine de la anterior (los tests de arriba dependen de esto, y una
    migración apuntada a la base equivocada sería un desastre silencioso)."""
    uno = _con_database_url("postgresql://u:p@host:5432/base_a", get_engine)
    otro = _con_database_url("postgresql://u:p@host:5432/base_b", get_engine)
    assert uno is not otro, "dos URLs distintas devolvieron el mismo engine"
    assert uno.url.database == "base_a", uno.url.database
    assert otro.url.database == "base_b", otro.url.database


def test_get_session_usa_el_engine_compartido():
    """get_session() no debe esquivar la memorización: si vuelve a construir
    un engine propio, el bucle de 30 tickers sigue abriendo 30 pools."""
    from models import get_session

    url = "postgresql://usuario:pass@host:5432/db_sesion"
    engine_directo = _con_database_url(url, get_engine)
    sesion = _con_database_url(url, get_session)
    try:
        assert sesion.get_bind() is engine_directo, (
            "get_session() usó un engine distinto al que devuelve get_engine()"
        )
    finally:
        sesion.close()


if __name__ == "__main__":
    test_esquema_postgresql_ambiguo_se_fuerza_a_psycopg2()
    test_esquema_postgres_viejo_estilo_heroku_tambien_se_fuerza()
    test_esquema_ya_explicito_no_se_toca()
    test_ninguna_consulta_puede_colgarse_para_siempre()
    test_el_engine_se_reusa_en_vez_de_crear_un_pool_nuevo_por_llamada()
    test_urls_distintas_no_comparten_engine()
    test_get_session_usa_el_engine_compartido()
    print("OK: las siete pruebas pasaron.")
