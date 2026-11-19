"""Guardia de base de datos para las pruebas: ninguna prueba puede llegar a producción.

QUÉ PROTEGE
===========
El dashboard y los scripts leen DATABASE_URL del .env, que apunta a Postgres de
producción en Railway. Antes de este guardia, cualquier prueba que importara
`models` (o levantara el dashboard con AppTest) se conectaba a producción, y
dos de ellas escribían y borraban filas allí.

CÓMO
====
Este módulo es lo PRIMERO que importa cada archivo de prueba y conftest.py
(una meta-prueba lo exige). Al importarse:

  1. Si el programa principal es un archivo de tests/ (python tests/x.py o
     python -m test_x), se detiene: las pruebas solo corren con pytest.
  2. En la memoria de ESTE proceso (no en Windows ni en el .env):
       - DATABASE_URL pasa a una URL que no lleva a ninguna parte, o a la base
         de pruebas local si está autorizada y validada (ver abajo). Como
         load_dotenv() no pisa variables ya definidas, el .env ya no entra.
       - Se borran las variables PG* que podrían redirigir la conexión.
  3. Reemplaza psycopg2._connect —la función por la que pasa TODA conexión de
     psycopg2, venga de SQLAlchemy, del dashboard, de un script importado o de
     psycopg2.connect directo— por una aduana que valida el destino final
     ANTES de abrir el socket. Si no pasa, lanza ConexionBloqueada y libpq
     nunca se llama.
  4. Cuenta las conexiones intentadas, permitidas y bloqueadas, y las imprime
     al terminar el proceso.

BASE DE PRUEBAS LOCAL (desactivada hasta una etapa posterior)
=============================================================
Solo se permite conectar si se cumplen TODAS estas condiciones:
  - FRI_PRUEBAS_POSTGRES=1 en el entorno, y TEST_DATABASE_URL en el entorno o
    en .env.test (ignorado por git).
  - El servidor es literalmente 127.0.0.1 o ::1 ("localhost" no: el archivo
    hosts puede redirigirlo).
  - El nombre de la base termina en _test, y hay usuario explícito.
  - Sin destinos ambiguos: ni service, ni hostaddr, ni varios servidores.
  - No coincide con producción: servidor, puerto, base, usuario y contraseña
    se comparan contra los de producción, en memoria; nunca se imprimen.
Y en cada conexión, el destino debe ser exactamente esa base autorizada.

Ningún mensaje de este módulo incluye URLs, servidores ni credenciales.
"""
import atexit
import hashlib
import os
import sys
from pathlib import Path

CARPETA_TESTS = Path(__file__).resolve().parent
RAIZ = CARPETA_TESTS.parent

URL_BLOQUEADA = "postgresql://bloqueado-por-pruebas.invalid:5432/sin_base_de_pruebas"

# Variables de libpq que pueden cambiar a dónde se conecta, o con qué
# credenciales, sin aparecer en la URL.
VARIABLES_LIBPQ = (
    "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD",
    "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS",
)

SERVIDORES_LOCALES = frozenset({"127.0.0.1", "::1"})
SUFIJO_BASE_DE_PRUEBAS = "_test"

ESTADISTICAS = {"intentadas": 0, "permitidas": 0, "bloqueadas": 0}


class ConexionBloqueada(Exception):
    """Una conexión que el guardia rechazó antes de abrirla.

    No hereda de los errores de psycopg2 a propósito: así SQLAlchemy no la
    envuelve y el reintento por corte de red de conftest.py no la reintenta.
    """


class ConfiguracionDePruebasInsegura(Exception):
    """La base de pruebas pedida no pasa la validación: la sesión no arranca."""


# ---------------------------------------------------------------------------
# 1. Ejecución directa
# ---------------------------------------------------------------------------

def es_ejecucion_directa_de_un_archivo_de_prueba(modulo_principal=None):
    """True si el programa principal es un archivo dentro de tests/."""
    if modulo_principal is None:
        modulo_principal = sys.modules.get("__main__")
    archivo = getattr(modulo_principal, "__file__", None)
    if not archivo:
        return False
    try:
        ruta = Path(archivo).resolve()
    except (OSError, ValueError):
        return False
    return ruta.parent == CARPETA_TESTS or CARPETA_TESTS in ruta.parents


# ---------------------------------------------------------------------------
# 2. Huellas: describir un destino sin guardar el secreto
# ---------------------------------------------------------------------------

def _hash(texto):
    if texto is None:
        return None
    return hashlib.sha256(str(texto).encode("utf-8")).hexdigest()


def huella_de_url(url):
    """(servidor, puerto, base, usuario, hash de la contraseña) de una URL, o None.

    Nunca lanza con el contenido de la URL en el mensaje.
    """
    if not url:
        return None
    try:
        from sqlalchemy.engine import make_url
        u = make_url(url)
    except Exception:
        return None
    return {
        "servidor": (u.host or "").lower(),
        "puerto": u.port or 5432,
        "base": u.database or "",
        "usuario": u.username or "",
        "clave": _hash(u.password),
        "consulta": dict(u.query),
    }


def huellas_de_produccion(urls_conocidas):
    """Huellas de las URLs de producción conocidas (sin duplicados ni vacías)."""
    huellas = []
    for url in urls_conocidas:
        h = huella_de_url(url)
        if h is not None and h not in huellas:
            huellas.append(h)
    return huellas


# ---------------------------------------------------------------------------
# 3. Validación de la URL de la base de pruebas (antes de cualquier conexión)
# ---------------------------------------------------------------------------

def motivo_de_rechazo_de_url_de_pruebas(url, produccion):
    """Devuelve None si la URL es aceptable como base de pruebas, o el motivo.

    El motivo nunca incluye la URL ni partes de ella.
    """
    h = huella_de_url(url)
    if h is None:
        return "la URL de pruebas no se puede interpretar"
    if not url.split("://", 1)[0].startswith("postgres"):
        return "la URL de pruebas no es de PostgreSQL"
    consulta = {k.lower() for k in h["consulta"]}
    for prohibida in ("service", "hostaddr", "host", "port", "dbname", "user", "options"):
        if prohibida in consulta:
            return f"la URL de pruebas trae '{prohibida}' en los parámetros: destino ambiguo"
    if "," in h["servidor"]:
        return "la URL de pruebas tiene varios servidores"
    if h["servidor"] not in SERVIDORES_LOCALES:
        return "el servidor de pruebas debe ser literalmente 127.0.0.1 o ::1"
    if not h["base"].endswith(SUFIJO_BASE_DE_PRUEBAS):
        return f"el nombre de la base de pruebas debe terminar en '{SUFIJO_BASE_DE_PRUEBAS}'"
    if not h["usuario"]:
        return "la URL de pruebas debe traer un usuario explícito"
    for p in produccion:
        if h["servidor"] == p["servidor"]:
            return "el servidor de pruebas coincide con el de producción"
        if h["base"] == p["base"]:
            return "el nombre de la base de pruebas coincide con el de producción"
        if h["usuario"] == p["usuario"]:
            return "el usuario de pruebas coincide con el de producción"
        if h["clave"] is not None and h["clave"] == p["clave"]:
            return "la contraseña de pruebas coincide con la de producción"
    return None


# ---------------------------------------------------------------------------
# 4. La aduana: validar el destino final que recibiría libpq
# ---------------------------------------------------------------------------

def motivo_de_rechazo_de_destino(parametros, autorizada, entorno=None):
    """Valida el destino FINAL (parámetros de libpq ya resueltos).

    `parametros`: dict como el que devuelve psycopg2.extensions.parse_dsn.
    `autorizada`: huella de la base de pruebas autorizada, o None.
    Devuelve None si se permite, o el motivo del rechazo.
    """
    if entorno is None:
        entorno = os.environ
    if autorizada is None:
        return "no hay base de pruebas autorizada: toda conexión está bloqueada"
    presentes = [v for v in VARIABLES_LIBPQ if v in entorno]
    if presentes:
        return "hay variables PG* en el entorno que podrían redirigir la conexión"
    for prohibida in ("service", "hostaddr"):
        if prohibida in parametros:
            return f"la conexión trae '{prohibida}': destino ambiguo"
    servidor = (parametros.get("host") or "").lower()
    if not servidor:
        return "la conexión no declara servidor"
    if "," in servidor:
        return "la conexión tiene varios servidores"
    if servidor not in SERVIDORES_LOCALES:
        return "el servidor no es local"
    try:
        puerto = int(parametros.get("port") or 5432)
    except ValueError:
        return "el puerto no es un número"
    if servidor != autorizada["servidor"] or puerto != autorizada["puerto"]:
        return "el destino no es la base de pruebas autorizada"
    if parametros.get("dbname") != autorizada["base"]:
        return "la base no es la base de pruebas autorizada"
    if parametros.get("user") != autorizada["usuario"]:
        return "el usuario no es el de la base de pruebas autorizada"
    return None


def crear_aduana(conectar_original, obtener_autorizada, interpretar_dsn, estadisticas):
    """Envuelve la función de conexión de bajo nivel con la validación previa."""

    def _connect_con_aduana(dsn, *args, **kwargs):
        estadisticas["intentadas"] += 1
        try:
            parametros = interpretar_dsn(dsn)
        except Exception:
            estadisticas["bloqueadas"] += 1
            raise ConexionBloqueada(
                "Conexión bloqueada por el guardia de pruebas: el destino no se puede interpretar."
            ) from None
        motivo = motivo_de_rechazo_de_destino(parametros, obtener_autorizada())
        if motivo is not None:
            estadisticas["bloqueadas"] += 1
            raise ConexionBloqueada(
                f"Conexión bloqueada por el guardia de pruebas ({motivo}). "
                "No se abrió ninguna conexión."
            )
        estadisticas["permitidas"] += 1
        return conectar_original(dsn, *args, **kwargs)

    _connect_con_aduana._aduana_fri = True
    return _connect_con_aduana


# ---------------------------------------------------------------------------
# 5. Instalación
# ---------------------------------------------------------------------------

_BASE_AUTORIZADA = None  # huella de la base de pruebas local, si se autoriza


def base_de_pruebas_autorizada():
    return _BASE_AUTORIZADA


def _leer_url_de_pruebas():
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    archivo = RAIZ / ".env.test"
    if archivo.is_file():
        from dotenv import dotenv_values
        return dotenv_values(archivo).get("TEST_DATABASE_URL")
    return None


def _urls_de_produccion_conocidas(database_url_heredada):
    urls = [database_url_heredada]
    archivo = RAIZ / ".env"
    if archivo.is_file():
        from dotenv import dotenv_values
        urls.append(dotenv_values(archivo).get("DATABASE_URL"))
    return urls


def _instalar():
    global _BASE_AUTORIZADA

    if es_ejecucion_directa_de_un_archivo_de_prueba():
        raise SystemExit(
            "Las pruebas no se ejecutan directamente con python: usa pytest "
            "(por ejemplo: python -m pytest tests/). Así siempre pasan por el "
            "guardia de base de datos."
        )

    # Lo que haya en el entorno o en .env se considera producción.
    produccion = huellas_de_produccion(
        _urls_de_produccion_conocidas(os.environ.get("DATABASE_URL"))
    )

    for variable in VARIABLES_LIBPQ:
        os.environ.pop(variable, None)

    os.environ["DATABASE_URL"] = URL_BLOQUEADA
    if os.environ.get("FRI_PRUEBAS_POSTGRES") == "1":
        url = _leer_url_de_pruebas()
        if not url:
            raise ConfiguracionDePruebasInsegura(
                "FRI_PRUEBAS_POSTGRES=1 pero no hay TEST_DATABASE_URL."
            )
        motivo = motivo_de_rechazo_de_url_de_pruebas(url, produccion)
        if motivo is not None:
            raise ConfiguracionDePruebasInsegura(f"Base de pruebas rechazada: {motivo}.")
        _BASE_AUTORIZADA = huella_de_url(url)
        os.environ["DATABASE_URL"] = url

    import psycopg2
    from psycopg2.extensions import parse_dsn

    if not getattr(psycopg2._connect, "_aduana_fri", False):
        psycopg2._connect = crear_aduana(
            psycopg2._connect, base_de_pruebas_autorizada, parse_dsn, ESTADISTICAS
        )

    atexit.register(_imprimir_resumen)
    _instalar_guardia_de_red()


def _instalar_guardia_de_red():
    """P-1: el guardia de red (servicios externos) se instala junto a este, así hereda sus mismas rutas protegidas.
    Se carga por su ruta, sin tocar sys.path, y queda registrado como `_guardia_red` para que todos lo compartan."""
    if "_guardia_red" not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_guardia_red", CARPETA_TESTS / "_guardia_red.py")
        modulo = importlib.util.module_from_spec(spec)
        sys.modules["_guardia_red"] = modulo
        spec.loader.exec_module(modulo)
    sys.modules["_guardia_red"].instalar()


def _imprimir_resumen():
    e = ESTADISTICAS
    estado = "base local autorizada" if _BASE_AUTORIZADA else "sin base de pruebas: todo bloqueado"
    try:
        print(
            f"\n[guardia BD] {estado} | conexiones intentadas={e['intentadas']} "
            f"permitidas={e['permitidas']} bloqueadas={e['bloqueadas']}",
            file=sys.__stderr__, flush=True,
        )
    except Exception:
        pass


_instalar()
