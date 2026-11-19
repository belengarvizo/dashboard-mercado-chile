"""Guardia de red para las pruebas: ninguna prueba sale a internet sin autorización explícita.

QUÉ PROTEGE
===========
Además de la base de producción (de eso se ocupa _guardia_bd), las pruebas pueden llegar a servicios externos:
Yahoo Finance (yfinance, que descarga con curl_cffi: libcurl, en C), Gemini (google-genai, una API de pago),
y cualquier cliente HTTP del repositorio (requests, httpx, aiohttp, urllib). Este módulo lo instala _guardia_bd, que
es lo PRIMERO que importa cada archivo de prueba y conftest.py: hereda las mismas rutas protegidas (pytest desde
cualquier carpeta, --noconftest; la ejecución directa ya la detiene _guardia_bd).

CAPAS (independientes: si una falla, las otras siguen)
=======================================================
  1. Sockets y DNS de Python: socket.connect/connect_ex/create_connection y la resolución de nombres
     (getaddrinfo, gethostbyname) se rechazan ANTES de conectar o de consultar al DNS, salvo direcciones de loopback
     escritas literalmente (127.0.0.0/8 y ::1), que necesitará la futura base de pruebas local.
  2. Clientes que no pasan por esos sockets o que conviene cortar antes: curl_cffi (Session.request,
     AsyncSession.request y Curl.perform; cubre yfinance), google.genai.Client, requests (HTTPAdapter.send),
     httpx (transportes síncrono y asíncrono) y aiohttp (ClientSession._request).
  3. Proxies muertos en el entorno de ESTE proceso (y de sus subprocesos): HTTP(S)_PROXY y ALL_PROXY apuntan a
     127.0.0.1:9, un puerto cerrado. libcurl, requests y httpx los respetan: lo que se escape de las capas 1 y 2, o
     un subproceso, termina contra un puerto local cerrado. NO_PROXY deja pasar solo lo local.
  4. Claves neutralizadas: las variables de credenciales (las del .env, salvo DATABASE_URL, que maneja _guardia_bd,
     y GEMINI_API_KEY, GOOGLE_API_KEY y BCCH_TOKEN aunque no estén) quedan VACÍAS en el entorno de este proceso. Como
     load_dotenv() no pisa variables existentes, el .env ya no entra; y load_dotenv/dotenv_values se envuelven para
     que tampoco con override=True ni leyendo el archivo devuelvan los valores. El .env no se lee para guardar
     valores, no se modifica y nada se imprime: solo se usan los NOMBRES de sus variables.

AUTORIZACIÓN
============
Las pruebas que necesitan servicios externos llevan la marca `externa` y conftest.py las omite salvo que
FRI_PRUEBAS_EXTERNAS=1. Aun así, esta guardia solo deja pasar conexiones DURANTE una prueba marcada `externa` y con
esa autorización (conftest.py abre y cierra el permiso por prueba). Las claves siguen neutralizadas incluso entonces.

CONTABILIDAD
============
Cada intento bloqueado o permitido queda registrado con su capa y su servidor (nunca la URL completa: puede llevar
credenciales en la consulta). conftest.py hace fallar la prueba que intentó salir sin estar marcada `externa`, aunque
el código haya capturado la excepción. Al terminar el proceso se imprime el resumen.
"""
import atexit
import contextlib
import ipaddress
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

CARPETA_TESTS = Path(__file__).resolve().parent
RAIZ = CARPETA_TESTS.parent

PROXY_MUERTO = "http://127.0.0.1:9"
VARIABLES_DE_PROXY = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
SIN_PROXY = "127.0.0.1,::1,localhost"
CLAVES_SIEMPRE_NEUTRALIZADAS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "BCCH_TOKEN")
MANEJADAS_POR_GUARDIA_BD = ("DATABASE_URL", "TEST_DATABASE_URL")
NOMBRES_LOCALES = frozenset({"localhost"})

ESTADISTICAS = {"intentadas": 0, "permitidas": 0, "bloqueadas": 0}
REGISTRO: list[dict] = []          # un dict por intento: capa, destino (servidor), permitido
ORIGINALES: dict[str, object] = {}  # lo reemplazado, para restaurarlo en pruebas de una capa sola
CAPAS_INSTALADAS: list[str] = []
MODULOS_CARGADOS_ANTES: frozenset = frozenset()
CLAVES_NEUTRALIZADAS: tuple = ()
INSTALADO = False

_PERMISO = {"autorizadas": False, "prueba_externa": False}


class ConexionExternaBloqueada(Exception):
    """Una conexión a un servicio externo que el guardia rechazó antes de abrirla.

    No hereda de OSError a propósito: así los clientes no la confunden con una falla de red recuperable, y el
    reintento por corte de red de conftest.py no la reintenta (su mensaje tampoco trae esas firmas)."""


# ---------------------------------------------------------------------------
# Permiso y registro
# ---------------------------------------------------------------------------
def externas_autorizadas() -> bool:
    return _PERMISO["autorizadas"]


def permitido() -> bool:
    return _PERMISO["autorizadas"] and _PERMISO["prueba_externa"]


@contextlib.contextmanager
def prueba_externa():
    """Abre el permiso de red durante una prueba marcada `externa`, SOLO si hay autorización. Mientras dura, saca
    los proxies muertos (si no, las llamadas permitidas también chocarían con ellos); al terminar los repone."""
    if not externas_autorizadas():
        yield False
        return
    guardados = {v: os.environ.pop(v) for v in VARIABLES_DE_PROXY if v in os.environ}
    _PERMISO["prueba_externa"] = True
    try:
        yield True
    finally:
        _PERMISO["prueba_externa"] = False
        os.environ.update(guardados)


def instantanea() -> int:
    return len(REGISTRO)


def intentos_desde(marca: int) -> list[dict]:
    return REGISTRO[marca:]


def _registrar(capa: str, destino: str | None, permitida: bool) -> None:
    ESTADISTICAS["intentadas"] += 1
    ESTADISTICAS["permitidas" if permitida else "bloqueadas"] += 1
    REGISTRO.append({"capa": capa, "destino": destino or "?", "permitido": permitida})


def _bloquear(capa: str, destino: str | None):
    _registrar(capa, destino, False)
    raise ConexionExternaBloqueada(
        f"Conexión externa bloqueada por el guardia de pruebas (capa: {capa}; servidor: {destino or '?'}). "
        "Las pruebas no salen a internet: usa datos simulados, o marca la prueba como 'externa' y autoriza con "
        "FRI_PRUEBAS_EXTERNAS=1. No se abrió ninguna conexión."
    )


def _servidor_de_url(url) -> str | None:
    try:
        return urlsplit(str(url)).hostname
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Capa 1: sockets y DNS
# ---------------------------------------------------------------------------
def es_loopback_literal(servidor) -> bool:
    """True solo para direcciones de loopback escritas como IP (127.0.0.0/8, ::1). Un nombre no: el archivo hosts o
    un DNS podrían redirigirlo."""
    if not isinstance(servidor, str):
        return False
    try:
        return ipaddress.ip_address(servidor.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _destino_de_direccion(direccion):
    if isinstance(direccion, tuple) and direccion:
        return direccion[0]
    return None  # AF_UNIX u otras familias locales: str/bytes, sin servidor de red


def _envolver_conexion_de_socket(original, capa):
    def conectar(self, direccion, *args, **kwargs):
        destino = _destino_de_direccion(direccion)
        if destino is None or es_loopback_literal(destino):
            return original(self, direccion, *args, **kwargs)
        if permitido():
            _registrar(capa, str(destino), True)
            return original(self, direccion, *args, **kwargs)
        _bloquear(capa, str(destino))
    conectar._guardia_red = True
    return conectar


def _envolver_resolucion(original, capa):
    def resolver(servidor, *args, **kwargs):
        nombre = servidor.decode() if isinstance(servidor, bytes) else servidor
        if nombre in (None, "") or es_loopback_literal(nombre) or (isinstance(nombre, str) and nombre.lower() in NOMBRES_LOCALES):
            return original(servidor, *args, **kwargs)
        if permitido():
            _registrar(capa, str(nombre), True)
            return original(servidor, *args, **kwargs)
        _bloquear(capa, str(nombre))
    resolver._guardia_red = True
    return resolver


def _envolver_create_connection(original):
    def create_connection(direccion, *args, **kwargs):
        destino = _destino_de_direccion(direccion)
        if destino is not None and not es_loopback_literal(destino) and not (
                isinstance(destino, str) and destino.lower() in NOMBRES_LOCALES):
            if not permitido():
                _bloquear("socket.create_connection", str(destino))
            _registrar("socket.create_connection", str(destino), True)
        return original(direccion, *args, **kwargs)
    create_connection._guardia_red = True
    return create_connection


def _instalar_sockets():
    for nombre in ("connect", "connect_ex"):
        original = getattr(socket.socket, nombre)
        if not getattr(original, "_guardia_red", False):
            ORIGINALES[f"socket.socket.{nombre}"] = original
            setattr(socket.socket, nombre, _envolver_conexion_de_socket(original, f"socket.{nombre}"))
    for nombre in ("getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        original = getattr(socket, nombre)
        if not getattr(original, "_guardia_red", False):
            ORIGINALES[f"socket.{nombre}"] = original
            setattr(socket, nombre, _envolver_resolucion(original, f"dns.{nombre}"))
    if not getattr(socket.create_connection, "_guardia_red", False):
        ORIGINALES["socket.create_connection"] = socket.create_connection
        socket.create_connection = _envolver_create_connection(socket.create_connection)
    CAPAS_INSTALADAS.append("sockets y DNS de Python")


# ---------------------------------------------------------------------------
# Capa 2: clientes que no pasan por los sockets de Python (o que conviene cortar antes)
# ---------------------------------------------------------------------------
def _reemplazar(clase, metodo: str, capa: str, destino_de, asincrono: bool = False):
    original = getattr(clase, metodo)
    if getattr(original, "_guardia_red", False):
        return
    clave = f"{clase.__module__}.{clase.__qualname__}.{metodo}"
    ORIGINALES[clave] = (clase, metodo, original)

    if asincrono:
        async def envoltura(*args, **kwargs):
            destino = destino_de(args, kwargs)
            if permitido():
                _registrar(capa, destino, True)
                return await original(*args, **kwargs)
            _bloquear(capa, destino)
    else:
        def envoltura(*args, **kwargs):
            destino = destino_de(args, kwargs)
            if permitido():
                _registrar(capa, destino, True)
                return original(*args, **kwargs)
            _bloquear(capa, destino)
    envoltura._guardia_red = True
    envoltura.__name__ = getattr(original, "__name__", metodo)
    setattr(clase, metodo, envoltura)


def restaurar(clave: str) -> None:
    """Restaura una pieza reemplazada (solo para pruebas que verifican la capa siguiente en aislamiento)."""
    guardado = ORIGINALES[clave]
    if isinstance(guardado, tuple):
        clase, metodo, original = guardado
        setattr(clase, metodo, original)
    elif clave.startswith("socket.socket."):
        setattr(socket.socket, clave.rsplit(".", 1)[1], guardado)
    else:
        setattr(socket, clave.split(".", 1)[1], guardado)


def _url_de_requests(args, kwargs):  # Session.request(self, method, url, ...)
    url = kwargs.get("url", args[2] if len(args) > 2 else None)
    return _servidor_de_url(url)


def _instalar_clientes():
    try:
        import curl_cffi
        from curl_cffi import requests as curl_requests
        _reemplazar(curl_requests.Session, "request", "curl_cffi.Session.request", _url_de_requests)
        _reemplazar(curl_requests.AsyncSession, "request", "curl_cffi.AsyncSession.request", _url_de_requests, asincrono=True)
        _reemplazar(curl_cffi.Curl, "perform", "curl_cffi.Curl.perform", lambda a, k: None)
        CAPAS_INSTALADAS.append("curl_cffi (yfinance)")
    except ImportError:
        pass
    try:
        from google import genai
        _reemplazar(genai.Client, "__init__", "google.genai.Client", lambda a, k: "generativelanguage.googleapis.com")
        CAPAS_INSTALADAS.append("google.genai")
    except ImportError:
        pass
    try:
        import requests.adapters
        _reemplazar(requests.adapters.HTTPAdapter, "send", "requests.HTTPAdapter.send",
                    lambda a, k: _servidor_de_url(getattr(a[1] if len(a) > 1 else k.get("request"), "url", None)))
        CAPAS_INSTALADAS.append("requests")
    except ImportError:
        pass
    try:
        import httpx

        def _servidor_httpx(args, kwargs):
            pedido = args[1] if len(args) > 1 else kwargs.get("request")
            return getattr(getattr(pedido, "url", None), "host", None)
        _reemplazar(httpx.HTTPTransport, "handle_request", "httpx.HTTPTransport", _servidor_httpx)
        _reemplazar(httpx.AsyncHTTPTransport, "handle_async_request", "httpx.AsyncHTTPTransport", _servidor_httpx,
                    asincrono=True)
        CAPAS_INSTALADAS.append("httpx")
    except ImportError:
        pass
    try:
        import aiohttp
        _reemplazar(aiohttp.ClientSession, "_request", "aiohttp.ClientSession",
                    lambda a, k: _servidor_de_url(k.get("str_or_url", a[2] if len(a) > 2 else None)), asincrono=True)
        CAPAS_INSTALADAS.append("aiohttp")
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Capas 3 y 4: proxies muertos y claves neutralizadas
# ---------------------------------------------------------------------------
def _nombres_en_dotenv() -> set[str]:
    """Solo los NOMBRES de las variables del .env; los valores no se guardan."""
    archivo = RAIZ / ".env"
    if not archivo.is_file():
        return set()
    from dotenv import dotenv_values
    return set(dotenv_values(archivo).keys())


def _reaplicar_neutralizacion() -> None:
    for nombre in CLAVES_NEUTRALIZADAS:
        os.environ[nombre] = ""


def _instalar_entorno() -> None:
    global CLAVES_NEUTRALIZADAS
    for variable in VARIABLES_DE_PROXY:
        os.environ[variable] = PROXY_MUERTO
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = SIN_PROXY
    nombres = (_nombres_en_dotenv() | set(CLAVES_SIEMPRE_NEUTRALIZADAS)) - set(MANEJADAS_POR_GUARDIA_BD)
    CLAVES_NEUTRALIZADAS = tuple(sorted(nombres))
    _reaplicar_neutralizacion()

    import dotenv
    import dotenv.main
    for modulo in (dotenv, dotenv.main):
        cargar = getattr(modulo, "load_dotenv")
        if not getattr(cargar, "_guardia_red", False):
            def load_dotenv(*args, _original=cargar, **kwargs):
                resultado = _original(*args, **kwargs)
                _reaplicar_neutralizacion()  # ni con override=True vuelven las claves
                return resultado
            load_dotenv._guardia_red = True
            modulo.load_dotenv = load_dotenv
        leer = getattr(modulo, "dotenv_values")
        if not getattr(leer, "_guardia_red", False):
            def dotenv_values(*args, _original=leer, **kwargs):
                valores = _original(*args, **kwargs)
                return {k: ("" if k in CLAVES_NEUTRALIZADAS else v) for k, v in valores.items()}
            dotenv_values._guardia_red = True
            modulo.dotenv_values = dotenv_values
    CAPAS_INSTALADAS.append("proxies muertos y claves neutralizadas")


# ---------------------------------------------------------------------------
# Instalación y resumen
# ---------------------------------------------------------------------------
def instalar() -> None:
    """Idempotente. La llama _guardia_bd al final de su propia instalación."""
    global INSTALADO, MODULOS_CARGADOS_ANTES
    if INSTALADO:
        return
    MODULOS_CARGADOS_ANTES = frozenset(sys.modules)
    _PERMISO["autorizadas"] = os.environ.get("FRI_PRUEBAS_EXTERNAS") == "1"
    _instalar_entorno()
    _instalar_sockets()
    _instalar_clientes()
    INSTALADO = True
    atexit.register(_imprimir_resumen)


def _imprimir_resumen() -> None:
    e = ESTADISTICAS
    estado = "externas autorizadas solo en pruebas 'externa'" if externas_autorizadas() else "sin red externa"
    try:
        print(f"[guardia red] {estado} | conexiones intentadas={e['intentadas']} permitidas={e['permitidas']} "
              f"bloqueadas={e['bloqueadas']}", file=sys.__stderr__, flush=True)
    except Exception:
        pass
