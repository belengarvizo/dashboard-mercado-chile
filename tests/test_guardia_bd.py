"""Pruebas del guardia de base de datos (_guardia_bd.py), sin red y sin base real.

Toda conexión que aparece aquí apunta a servidores con el dominio reservado
.invalid (que no existe en internet) o pasa por una función de conexión falsa
que solo registra la llamada. Si el guardia fallara, ninguna de ellas podría
llegar a una base real. Ningún mensaje ni aserción expone la URL de producción.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import ast
import os
import re
import sys
from pathlib import Path

import pytest

import _guardia_bd as g

CARPETA_TESTS = Path(__file__).resolve().parent
RAIZ = CARPETA_TESTS.parent
sys.path.append(str(RAIZ))  # como los demás archivos: para importar models desde cualquier carpeta

URL_FALSA_REMOTA = "postgresql://u:clave@produccion-falsa.invalid:5432/railway"

PRODUCCION_SINTETICA = g.huellas_de_produccion([
    "postgresql://postgres:secreto-prod@servidor-prod.invalid:41234/railway",
])

LOCAL_OK = "postgresql://fri_prueba:otra-clave@127.0.0.1:5432/mercado_test"


# ---------------------------------------------------------------------------
# Entorno del proceso
# ---------------------------------------------------------------------------

def test_database_url_del_proceso_es_la_bloqueada():
    assert os.environ["DATABASE_URL"] == g.URL_BLOQUEADA


def test_el_env_de_produccion_no_pisa_la_url_bloqueada():
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")  # mismo llamado que hacen models.py y varias pruebas
    assert os.environ["DATABASE_URL"] == g.URL_BLOQUEADA


def test_no_quedan_variables_pg_que_redirijan_la_conexion():
    assert [v for v in g.VARIABLES_LIBPQ if v in os.environ] == []


def test_sin_base_autorizada_por_defecto():
    assert g.base_de_pruebas_autorizada() is None


def test_la_aduana_esta_instalada_en_psycopg2():
    import psycopg2
    assert getattr(psycopg2._connect, "_aduana_fri", False) is True


# ---------------------------------------------------------------------------
# Rutas reales de conexión: se bloquean antes de abrir el socket
# ---------------------------------------------------------------------------

def test_psycopg2_connect_directo_se_bloquea():
    import psycopg2
    antes = dict(g.ESTADISTICAS)
    with pytest.raises(g.ConexionBloqueada):
        psycopg2.connect(host="produccion-falsa.invalid", dbname="railway", user="u", password="p")
    assert g.ESTADISTICAS["bloqueadas"] == antes["bloqueadas"] + 1
    assert g.ESTADISTICAS["permitidas"] == antes["permitidas"]


def test_un_import_temprano_de_connect_tambien_pasa_por_la_aduana():
    # Quien hizo `from psycopg2 import connect` antes igual cae en la aduana,
    # porque connect llama a psycopg2._connect al momento de conectar.
    from psycopg2 import connect
    with pytest.raises(g.ConexionBloqueada):
        connect("host=produccion-falsa.invalid dbname=railway user=u")


def test_sqlalchemy_se_bloquea_sin_envolver_el_error():
    from sqlalchemy import create_engine
    engine = create_engine(URL_FALSA_REMOTA.replace("postgresql://", "postgresql+psycopg2://"))
    with pytest.raises(g.ConexionBloqueada):
        engine.connect()
    engine.dispose()


def test_models_get_engine_se_bloquea():
    import models
    with pytest.raises(g.ConexionBloqueada):
        models.get_engine().connect()


def test_incluso_una_url_local_se_bloquea_sin_base_autorizada():
    import psycopg2
    with pytest.raises(g.ConexionBloqueada):
        psycopg2.connect(LOCAL_OK)


def test_el_mensaje_de_bloqueo_no_revela_el_destino():
    import psycopg2
    with pytest.raises(g.ConexionBloqueada) as exc:
        psycopg2.connect(URL_FALSA_REMOTA)
    texto = str(exc.value)
    assert "produccion-falsa" not in texto and "clave" not in texto and "railway" not in texto


def test_el_bloqueo_no_coincide_con_las_firmas_de_reintento_por_red():
    import conftest
    assert not issubclass(g.ConexionBloqueada, __import__("psycopg2").Error)
    with pytest.raises(g.ConexionBloqueada) as exc:
        __import__("psycopg2").connect(URL_FALSA_REMOTA)
    assert not any(f in str(exc.value) for f in conftest.FIRMAS_DE_ERROR_DE_CONEXION)


# ---------------------------------------------------------------------------
# La aduana con una conexión falsa: lo bloqueado nunca llega a conectar
# ---------------------------------------------------------------------------

class _ConexionFalsa:
    def __init__(self):
        self.llamadas = []

    def __call__(self, dsn, *args, **kwargs):
        self.llamadas.append(dsn)
        return "conexion-falsa"


def _aduana(autorizada):
    from psycopg2.extensions import parse_dsn
    falsa = _ConexionFalsa()
    stats = {"intentadas": 0, "permitidas": 0, "bloqueadas": 0}
    return g.crear_aduana(falsa, lambda: autorizada, parse_dsn, stats), falsa, stats


AUTORIZADA = g.huella_de_url(LOCAL_OK)

DESTINOS_BLOQUEADOS = {
    "servidor remoto": "host=produccion-falsa.invalid port=5432 dbname=mercado_test user=fri_prueba",
    "localhost por nombre": "host=localhost port=5432 dbname=mercado_test user=fri_prueba",
    "otra base": "host=127.0.0.1 port=5432 dbname=railway user=fri_prueba",
    "otro puerto": "host=127.0.0.1 port=41234 dbname=mercado_test user=fri_prueba",
    "otro usuario": "host=127.0.0.1 port=5432 dbname=mercado_test user=postgres",
    "sin servidor": "dbname=mercado_test user=fri_prueba",
    "varios servidores": "host=127.0.0.1,produccion-falsa.invalid dbname=mercado_test user=fri_prueba",
    "service": "service=prod host=127.0.0.1 dbname=mercado_test user=fri_prueba",
    "hostaddr": "host=127.0.0.1 hostaddr=10.0.0.1 dbname=mercado_test user=fri_prueba",
}


@pytest.mark.parametrize("caso", sorted(DESTINOS_BLOQUEADOS))
def test_destinos_no_autorizados_nunca_llegan_a_conectar(caso):
    aduana, falsa, stats = _aduana(AUTORIZADA)
    with pytest.raises(g.ConexionBloqueada):
        aduana(DESTINOS_BLOQUEADOS[caso])
    assert falsa.llamadas == []
    assert stats == {"intentadas": 1, "permitidas": 0, "bloqueadas": 1}


def test_sin_base_autorizada_todo_se_bloquea():
    aduana, falsa, stats = _aduana(None)
    with pytest.raises(g.ConexionBloqueada):
        aduana("host=127.0.0.1 port=5432 dbname=mercado_test user=fri_prueba")
    assert falsa.llamadas == []


def test_un_dsn_ilegible_se_bloquea():
    aduana, falsa, _ = _aduana(AUTORIZADA)
    with pytest.raises(g.ConexionBloqueada):
        aduana("esto no es un dsn ===")
    assert falsa.llamadas == []


def test_solo_la_base_autorizada_exacta_pasa():
    aduana, falsa, stats = _aduana(AUTORIZADA)
    assert aduana("host=127.0.0.1 port=5432 dbname=mercado_test user=fri_prueba") == "conexion-falsa"
    assert len(falsa.llamadas) == 1
    assert stats["permitidas"] == 1


def test_variables_pg_en_el_entorno_bloquean_aunque_el_destino_sea_correcto():
    params = {"host": "127.0.0.1", "port": "5432", "dbname": "mercado_test", "user": "fri_prueba"}
    assert g.motivo_de_rechazo_de_destino(params, AUTORIZADA, entorno={}) is None
    assert g.motivo_de_rechazo_de_destino(params, AUTORIZADA, entorno={"PGHOST": "x"}) is not None


# ---------------------------------------------------------------------------
# Validación de la URL de pruebas (antes de cualquier conexión)
# ---------------------------------------------------------------------------

URLS_RECHAZADAS = {
    "servidor de producción": "postgresql://fri:x@servidor-prod.invalid:41234/mercado_test",
    "servidor remoto": "postgresql://fri:x@otro.invalid:5432/mercado_test",
    "localhost por nombre": "postgresql://fri:x@localhost:5432/mercado_test",
    "sin sufijo _test": "postgresql://fri:x@127.0.0.1:5432/mercado",
    "misma base que producción": "postgresql://fri:x@127.0.0.1:5432/railway",
    "mismo usuario que producción": "postgresql://postgres:x@127.0.0.1:5432/mercado_test",
    "misma contraseña que producción": "postgresql://fri:secreto-prod@127.0.0.1:5432/mercado_test",
    "sin usuario": "postgresql://127.0.0.1:5432/mercado_test",
    "host escondido en parámetros": "postgresql://fri:x@127.0.0.1:5432/mercado_test?host=servidor-prod.invalid",
    "service": "postgresql://fri:x@127.0.0.1:5432/mercado_test?service=prod",
    "no es postgres": "mysql://fri:x@127.0.0.1:3306/mercado_test",
    "ilegible": "esto no es una url",
}


@pytest.mark.parametrize("caso", sorted(URLS_RECHAZADAS))
def test_urls_de_pruebas_inseguras_se_rechazan(caso):
    assert g.motivo_de_rechazo_de_url_de_pruebas(URLS_RECHAZADAS[caso], PRODUCCION_SINTETICA) is not None


def test_una_url_local_bien_formada_se_acepta():
    assert g.motivo_de_rechazo_de_url_de_pruebas(LOCAL_OK, PRODUCCION_SINTETICA) is None


def test_los_motivos_de_rechazo_no_revelan_la_url():
    for url in URLS_RECHAZADAS.values():
        motivo = g.motivo_de_rechazo_de_url_de_pruebas(url, PRODUCCION_SINTETICA)
        assert "invalid" not in motivo and "secreto" not in motivo


def test_la_url_real_de_produccion_no_sirve_como_base_de_pruebas():
    # P-2: el guardia lo calcula una vez al instalarse, con la URL en memoria, y guarda solo el booleano. Antes esta
    # prueba volvía a leer el .env; ahora ninguna prueba lo necesita (y la lectura directa está bloqueada).
    resultado = g.LA_URL_DE_PRODUCCION_SE_RECHAZA
    if resultado is None:
        pytest.skip("No hay .env con DATABASE_URL en esta máquina.")
    assert resultado is True


# ---------------------------------------------------------------------------
# Ejecución directa de archivos de prueba
# ---------------------------------------------------------------------------

class _Modulo:
    def __init__(self, archivo):
        self.__file__ = archivo


def test_detecta_un_archivo_de_tests_como_programa_principal():
    assert g.es_ejecucion_directa_de_un_archivo_de_prueba(_Modulo(str(CARPETA_TESTS / "test_x.py")))
    assert not g.es_ejecucion_directa_de_un_archivo_de_prueba(_Modulo(str(RAIZ / "app" / "dashboard.py")))
    assert not g.es_ejecucion_directa_de_un_archivo_de_prueba(object())


def test_ejecutar_un_archivo_de_prueba_con_python_se_detiene():
    # P-2: el proceso hijo se crea por la única vía permitida para esto, con un entorno armado desde cero
    # (DATABASE_URL bloqueada, sin claves, sin proxies útiles) y en una carpeta temporal sin .env.
    r = sys.modules["_guardia_procesos"].ejecutar_archivo_de_prueba(
        "test_black_scholes.py", motivo="verificar que el guardia detiene la ejecución directa"
    )
    assert r.returncode != 0
    assert "usa pytest" in r.stderr


# ---------------------------------------------------------------------------
# Meta-pruebas: la protección no se puede olvidar en silencio
# ---------------------------------------------------------------------------

ARCHIVOS_DE_PRUEBA = sorted(CARPETA_TESTS.glob("test_*.py"))
# _guardia_procesos.py importa subprocess para crear los únicos procesos permitidos; test_guardia_procesos.py
# provoca a propósito lo que estas reglas prohíben (con un .env ficticio), para verificar que el guardia lo frena.
ARCHIVOS_DEL_GUARDIA = {"_guardia_bd.py", "test_guardia_bd.py", "_guardia_procesos.py", "test_guardia_procesos.py"}


def _primera_sentencia_despues_del_docstring(ruta):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    cuerpo = list(arbol.body)
    if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(getattr(cuerpo[0], "value", None), ast.Constant) \
            and isinstance(cuerpo[0].value.value, str):
        cuerpo = cuerpo[1:]
    return cuerpo[0] if cuerpo else None


def _es_import_del_guardia(nodo):
    return isinstance(nodo, ast.Import) and [a.name for a in nodo.names] == ["_guardia_bd"]


@pytest.mark.parametrize("ruta", ARCHIVOS_DE_PRUEBA + [CARPETA_TESTS / "conftest.py"], ids=lambda r: r.name)
def test_cada_archivo_importa_el_guardia_antes_que_nada(ruta):
    assert _es_import_del_guardia(_primera_sentencia_despues_del_docstring(ruta))


def test_ningun_archivo_de_tests_se_puede_ejecutar_como_programa():
    con_main = [r.name for r in CARPETA_TESTS.glob("*.py")
                if re.search(r"__name__\s*==\s*['\"]__main__['\"]", r.read_text(encoding="utf-8"))]
    assert con_main == []


def test_nada_fuera_de_tests_importa_el_guardia():
    excluidas = {".git", ".venv", "venv", "tests", "__pycache__", "node_modules"}
    culpables = []
    for ruta in RAIZ.rglob("*.py"):
        if excluidas & set(ruta.relative_to(RAIZ).parts):
            continue
        if "_guardia_bd" in ruta.read_text(encoding="utf-8", errors="ignore"):
            culpables.append(str(ruta.relative_to(RAIZ)))
    assert culpables == []


MODULOS_QUE_ESQUIVAN_AL_GUARDIA = {
    "subprocess",        # un proceso hijo no hereda la aduana
    "multiprocessing",   # idem
    "psycopg",           # otros drivers no pasan por psycopg2._connect
    "pg8000",
    "asyncpg",
    "psycopg2._psycopg", # la función interna, sin la aduana
}


def _hallazgos_en(ruta):
    hallazgos = []
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        modulos = []
        if isinstance(nodo, ast.Import):
            modulos = [a.name for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            modulos = [nodo.module] + [f"{nodo.module}.{a.name}" for a in nodo.names]
        for m in modulos:
            if m in MODULOS_QUE_ESQUIVAN_AL_GUARDIA or m.split(".")[0] in MODULOS_QUE_ESQUIVAN_AL_GUARDIA - {"psycopg2._psycopg"}:
                hallazgos.append(f"{ruta.name}: importa {m}")
        if isinstance(nodo, ast.keyword) and nodo.arg == "override" \
                and isinstance(nodo.value, ast.Constant) and nodo.value.value is True:
            hallazgos.append(f"{ruta.name}: load_dotenv con override=True")
    return hallazgos


def test_las_pruebas_no_usan_vias_que_esquiven_al_guardia():
    hallazgos = []
    for ruta in CARPETA_TESTS.glob("*.py"):
        if ruta.name not in ARCHIVOS_DEL_GUARDIA:
            hallazgos += _hallazgos_en(ruta)
    assert hallazgos == []


USA_LA_BASE = re.compile(r"AppTest|get_session|get_engine|read_sql|create_engine|^\s*(from|import) models\b", re.M)


def test_todo_archivo_que_usa_la_base_esta_registrado():
    import conftest
    registrados = set(conftest.ARCHIVOS_DE_INTEGRACION) | set(conftest.ARCHIVOS_SIN_CONEXION_VERIFICADOS)
    sin_registro = [r.name for r in ARCHIVOS_DE_PRUEBA
                    if r.name not in ARCHIVOS_DEL_GUARDIA
                    and USA_LA_BASE.search(r.read_text(encoding="utf-8"))
                    and r.name not in registrados]
    assert sin_registro == []


def test_el_registro_no_nombra_pruebas_que_no_existen():
    import conftest
    inexistentes = []
    for archivo, (_, pueden_correr) in conftest.ARCHIVOS_DE_INTEGRACION.items():
        ruta = CARPETA_TESTS / archivo
        assert ruta.is_file(), archivo
        nombres = {n.name for n in ast.parse(ruta.read_text(encoding="utf-8")).body
                   if isinstance(n, ast.FunctionDef)}
        inexistentes += [f"{archivo}::{p}" for p in pueden_correr if p not in nombres]
    assert inexistentes == []
