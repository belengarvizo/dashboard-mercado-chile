"""Pruebas de aceptación del guardia de red (P-1): ninguna prueba sale a internet sin autorización explícita.

SEGURIDAD DE ESTAS PRUEBAS
    Ninguna hace una solicitud real a un dominio público. Los destinos son ficticios: dominios .invalid (reservados,
    no existen), direcciones del rango de documentación 203.0.113.0/24 (no se enrutan) y puertos locales cerrados.
    Cuando una prueba quita una capa para verificar la siguiente en aislamiento, la capa de proxies muertos sigue
    puesta o se agrega una trampa explícita: si la capa probada fallara, la petición iría a un puerto local cerrado.

    Las pruebas que provocan intentos bloqueados a propósito llevan la marca intentos_de_red_esperados: sin ella, la
    contabilidad por prueba de conftest.py las dejaría en rojo (que es justamente lo que se quiere para el resto).
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import ast
import asyncio
import configparser
import os
import socket
import sys
from pathlib import Path

import pytest

G = sys.modules["_guardia_red"]
CARPETA_TESTS = Path(__file__).resolve().parent
RAIZ = CARPETA_TESTS.parent
sys.path.append(str(RAIZ))

FICTICIO = "servidor-ficticio.invalid"
IP_DOCUMENTACION = "203.0.113.7"  # TEST-NET-3: reservada para documentación, no se enruta
MODULOS_DE_RED = ("yfinance", "curl_cffi", "requests", "httpx", "aiohttp", "google.genai", "urllib3", "feedparser",
                  "derivados_ui")
esperados = pytest.mark.intentos_de_red_esperados


def _ultimo():
    return G.REGISTRO[-1]


# ---------------------------------------------------------------------------
# Instalación y orden de carga
# ---------------------------------------------------------------------------
def test_el_guardia_se_instala_antes_que_cualquier_modulo_que_pueda_conectarse():
    assert G.INSTALADO
    for modulo in MODULOS_DE_RED:
        assert modulo not in G.MODULOS_CARGADOS_ANTES, f"{modulo} se cargó antes que el guardia de red"
    for capa in ("proxies muertos y claves neutralizadas", "sockets y DNS de Python", "curl_cffi (yfinance)",
                 "google.genai", "requests", "httpx", "aiohttp"):
        assert capa in G.CAPAS_INSTALADAS, capa
    import curl_cffi
    import httpx
    import requests.adapters
    from curl_cffi import requests as curl_requests
    from google import genai
    reemplazados = [socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo, socket.gethostbyname,
                    socket.create_connection, curl_requests.Session.request, curl_requests.AsyncSession.request,
                    curl_cffi.Curl.perform, genai.Client.__init__, requests.adapters.HTTPAdapter.send,
                    httpx.HTTPTransport.handle_request, httpx.AsyncHTTPTransport.handle_async_request]
    assert all(getattr(f, "_guardia_red", False) for f in reemplazados)


def test_el_guardia_de_red_lo_instala_el_guardia_de_la_base():
    """Así hereda sus rutas protegidas (pytest desde cualquier carpeta y --noconftest): cada archivo de prueba
    importa _guardia_bd primero, y _guardia_bd instala _guardia_red al terminar."""
    fuente = (CARPETA_TESTS / "_guardia_bd.py").read_text(encoding="utf-8")
    assert "_instalar_guardia_de_red()" in fuente and "def _instalar_guardia_de_red" in fuente


# ---------------------------------------------------------------------------
# Capa 1: sockets y DNS
# ---------------------------------------------------------------------------
@esperados
def test_un_socket_a_una_direccion_externa_se_bloquea_antes_de_conectar():
    antes = G.ESTADISTICAS["bloqueadas"]
    with socket.socket() as s, pytest.raises(G.ConexionExternaBloqueada):
        s.connect((IP_DOCUMENTACION, 80))
    with socket.socket() as s, pytest.raises(G.ConexionExternaBloqueada):
        s.connect_ex((IP_DOCUMENTACION, 443))
    assert G.ESTADISTICAS["bloqueadas"] == antes + 2 and _ultimo()["destino"] == IP_DOCUMENTACION


@esperados
def test_la_resolucion_de_un_nombre_externo_se_bloquea_sin_consultar_al_dns():
    for resolver in (lambda: socket.getaddrinfo(FICTICIO, 443), lambda: socket.gethostbyname(FICTICIO),
                     lambda: socket.gethostbyname_ex(FICTICIO), lambda: socket.create_connection((FICTICIO, 443), 1)):
        with pytest.raises(G.ConexionExternaBloqueada):
            resolver()
        assert _ultimo()["destino"] == FICTICIO


def test_el_loopback_queda_permitido_para_la_futura_base_local():
    """Conectar a un puerto LOCAL cerrado da «conexión rechazada», no el bloqueo del guardia."""
    with socket.socket() as libre:
        libre.bind(("127.0.0.1", 0))
        puerto = libre.getsockname()[1]
    antes = len(G.REGISTRO)
    with socket.socket() as s:
        s.settimeout(3)
        with pytest.raises(OSError):
            s.connect(("127.0.0.1", puerto))
    assert socket.getaddrinfo("localhost", 5432)  # nombre local: permitido
    assert len(G.REGISTRO) == antes
    assert G.es_loopback_literal("127.0.0.1") and G.es_loopback_literal("::1")
    assert not G.es_loopback_literal("localhost") and not G.es_loopback_literal(IP_DOCUMENTACION)


# ---------------------------------------------------------------------------
# Capa 2: clientes HTTP
# ---------------------------------------------------------------------------
@esperados
def test_requests_se_bloquea_y_el_registro_no_guarda_la_url():
    import requests
    with pytest.raises(G.ConexionExternaBloqueada) as error:
        requests.get(f"http://{FICTICIO}/ruta?clave=valor-secreto", timeout=2)
    assert _ultimo() == {"capa": "requests.HTTPAdapter.send", "destino": FICTICIO, "permitido": False}
    assert "valor-secreto" not in str(error.value) and all("valor-secreto" not in str(r) for r in G.REGISTRO)


@esperados
def test_sin_la_capa_de_requests_bloquean_el_dns_o_los_proxies(monkeypatch):
    """Se quita SOLO la capa de requests: con proxies muertos, la petición va a 127.0.0.1:9 (cerrado); sin proxies,
    la bloquea la resolución de nombres. En ningún caso sale de la máquina."""
    import requests
    import requests.adapters
    _, _, original = G.ORIGINALES["requests.adapters.HTTPAdapter.send"]
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", original)
    with pytest.raises(requests.exceptions.ConnectionError) as error:  # proxy muerto: rechazo local
        requests.get(f"http://{IP_DOCUMENTACION}/", timeout=3)
    assert "127.0.0.1" in str(error.value) or "ProxyError" in type(error.value).__name__
    for variable in G.VARIABLES_DE_PROXY:
        monkeypatch.delenv(variable, raising=False)
    with pytest.raises(G.ConexionExternaBloqueada):
        requests.get(f"http://{FICTICIO}/", timeout=3)
    assert _ultimo()["capa"].startswith("dns.")


@esperados
def test_httpx_sincrono_y_asincrono_se_bloquean():
    import httpx
    with pytest.raises(G.ConexionExternaBloqueada):
        httpx.get(f"https://{FICTICIO}/")

    async def pedir():
        async with httpx.AsyncClient() as cliente:
            await cliente.get(f"https://{FICTICIO}/")
    with pytest.raises(G.ConexionExternaBloqueada):
        asyncio.run(pedir())
    assert _ultimo() == {"capa": "httpx.AsyncHTTPTransport", "destino": FICTICIO, "permitido": False}


@esperados
def test_aiohttp_se_bloquea():
    import aiohttp

    async def pedir():
        async with aiohttp.ClientSession() as sesion:
            await sesion.get(f"https://{FICTICIO}/")
    with pytest.raises(G.ConexionExternaBloqueada):
        asyncio.run(pedir())
    assert _ultimo()["capa"] == "aiohttp.ClientSession"


# ---------------------------------------------------------------------------
# curl_cffi / yfinance (libcurl: no pasa por los sockets de Python)
# ---------------------------------------------------------------------------
@esperados
def test_curl_cffi_se_bloquea_en_la_sesion_y_en_la_capa_mas_baja():
    import curl_cffi
    from curl_cffi import CurlOpt
    from curl_cffi import requests as curl_requests
    with pytest.raises(G.ConexionExternaBloqueada):
        curl_requests.get(f"https://{FICTICIO}/")
    assert _ultimo() == {"capa": "curl_cffi.Session.request", "destino": FICTICIO, "permitido": False}
    curl = curl_cffi.Curl()
    curl.setopt(CurlOpt.URL, f"https://{FICTICIO}/".encode())
    curl.setopt(CurlOpt.PROXY, b"http://127.0.0.1:9")  # trampa: si la capa fallara, iría a un puerto local cerrado
    with pytest.raises(G.ConexionExternaBloqueada):
        curl.perform()
    assert _ultimo()["capa"] == "curl_cffi.Curl.perform"


@esperados
def test_sin_la_capa_de_curl_cffi_libcurl_respeta_el_proxy_muerto(monkeypatch):
    """Se quitan las capas de curl_cffi: libcurl toma el proxy del entorno (127.0.0.1:9, cerrado) y falla ahí. El
    destino es una IP de documentación, así que ni siquiera hay consulta DNS."""
    import curl_cffi
    from curl_cffi import requests as curl_requests
    _, _, sesion = G.ORIGINALES["curl_cffi.requests.session.Session.request"]
    _, _, perform = G.ORIGINALES["curl_cffi.curl.Curl.perform"]
    monkeypatch.setattr(curl_requests.Session, "request", sesion)
    monkeypatch.setattr(curl_cffi.Curl, "perform", perform)
    with pytest.raises(Exception) as error:
        curl_requests.get(f"http://{IP_DOCUMENTACION}/", timeout=3)
    assert not isinstance(error.value, G.ConexionExternaBloqueada)
    assert "127.0.0.1" in str(error.value) and IP_DOCUMENTACION not in str(error.value).replace(f"http://{IP_DOCUMENTACION}/", "")


@esperados
def test_yfinance_no_llega_a_yahoo_y_el_intento_capturado_no_se_esconde(monkeypatch):
    """derivados_ui._vencimientos_disponibles envuelve a yfinance y captura CUALQUIER excepción (devuelve ()). El
    guardia bloquea en curl_cffi, la función degrada en silencio... y aun así el intento queda registrado, y la
    contabilidad de conftest.py dejaría en rojo a una prueba sin marca 'externa'."""
    import curl_cffi
    import conftest

    def trampa(*args, **kwargs):
        raise AssertionError("trampa: la petición llegó a libcurl, la capa de sesión no la detuvo")
    monkeypatch.setattr(curl_cffi.Curl, "perform", trampa)
    import derivados_ui as ui
    marca = G.instantanea()
    assert ui._vencimientos_disponibles("TICKER-FICTICIO-P1") == ()  # el dashboard se tragó la excepción
    intentos = G.intentos_desde(marca)
    assert intentos and all(not i["permitido"] for i in intentos)
    assert {i["capa"] for i in intentos} <= {"curl_cffi.Session.request", "requests.HTTPAdapter.send"}
    assert any("yahoo" in i["destino"] for i in intentos)
    motivo = conftest.motivo_de_falla_por_red(intentos, marcada_externa=False, intentos_esperados=False)
    assert motivo and "sin estar marcada 'externa'" in motivo


# ---------------------------------------------------------------------------
# Gemini y credenciales
# ---------------------------------------------------------------------------
@esperados
def test_gemini_no_llega_a_google():
    from google import genai
    with pytest.raises(G.ConexionExternaBloqueada):
        genai.Client(api_key="clave-ficticia")
    assert _ultimo() == {"capa": "google.genai.Client", "destino": "generativelanguage.googleapis.com", "permitido": False}


def test_las_claves_quedan_vacias_y_load_dotenv_no_las_restaura():
    """Solo se comparan con la cadena vacía: ningún valor se lee para mostrarlo ni se imprime."""
    from dotenv import dotenv_values, load_dotenv
    assert {"GEMINI_API_KEY", "GOOGLE_API_KEY", "BCCH_TOKEN"} <= set(G.CLAVES_NEUTRALIZADAS)
    assert "DATABASE_URL" not in G.CLAVES_NEUTRALIZADAS  # esa la maneja el guardia de la base
    assert all(os.environ.get(c) == "" for c in G.CLAVES_NEUTRALIZADAS)
    load_dotenv(RAIZ / ".env")  # como lo hacen models.py y varias pruebas: no pisa lo que ya está
    assert all(os.environ.get(c) == "" for c in G.CLAVES_NEUTRALIZADAS)
    if (RAIZ / ".env").is_file():
        valores = dotenv_values(RAIZ / ".env")  # leer el archivo tampoco devuelve los valores
        assert all(valores.get(c, "") == "" for c in G.CLAVES_NEUTRALIZADAS)


def test_despues_de_cualquier_load_dotenv_las_claves_vuelven_a_quedar_vacias(tmp_path, monkeypatch):
    """Aunque algo lograra escribir una clave (aquí se simula con un valor inventado), la siguiente llamada a
    load_dotenv la vuelve a vaciar: la neutralización se reaplica siempre, con o sin override. Se usa un .env
    FICTICIO y sin override=True: llamar a load_dotenv(override=True) sobre el .env real repondría la DATABASE_URL
    de producción en el proceso, que es justo lo que la Etapa 0 prohíbe en las pruebas."""
    from dotenv import load_dotenv
    falso = tmp_path / ".env"
    falso.write_text("OTRA_VARIABLE_FICTICIA=1\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "valor-inventado-para-la-prueba")
    load_dotenv(falso)
    assert os.environ.get("GEMINI_API_KEY") == ""


def test_un_subproceso_no_recupera_las_credenciales_y_choca_con_el_proxy_muerto(pytester):
    """Un proceso hijo de Python SIN guardia: hereda el entorno (claves vacías, proxies muertos). load_dotenv() no
    puede reponer las claves (no pisa variables existentes) y su conexión va a 127.0.0.1:9, cerrado. Solo imprime
    booleanos y el tipo de error: ningún valor."""
    codigo = (
        "import os, urllib.request\n"
        "from dotenv import load_dotenv\n"
        f"load_dotenv(r'{RAIZ / '.env'}')\n"
        "claves = ('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'BCCH_TOKEN')\n"
        "print('claves_vacias=' + str(all(os.environ.get(c) == '' for c in claves)))\n"
        "print('proxy_muerto=' + str(os.environ.get('HTTPS_PROXY') == 'http://127.0.0.1:9'))\n"
        "try:\n"
        f"    urllib.request.urlopen('http://{IP_DOCUMENTACION}/', timeout=3)\n"
        "    print('red=SALIO')\n"
        "except Exception as e:\n"
        "    print('red=' + type(e).__name__)\n"
    )
    resultado = pytester.run(sys.executable, "-c", codigo, timeout=60)
    salida = resultado.stdout.str()
    assert "claves_vacias=True" in salida and "proxy_muerto=True" in salida, salida
    assert "red=URLError" in salida and "red=SALIO" not in salida, salida


# ---------------------------------------------------------------------------
# Autorización de pruebas externas y contabilidad
# ---------------------------------------------------------------------------
class _ItemFalso:
    def __init__(self, marcas):
        self.marcas, self.agregadas = set(marcas), []

    def get_closest_marker(self, nombre):
        return object() if nombre in self.marcas else None

    def add_marker(self, marca):
        self.agregadas.append(marca)


def test_una_prueba_externa_sin_autorizacion_se_omite():
    import conftest
    assert os.environ.get("FRI_PRUEBAS_EXTERNAS") != "1" and not G.externas_autorizadas()
    externa, offline = _ItemFalso({"externa"}), _ItemFalso(set())
    conftest._omitir_externas_sin_autorizacion([externa, offline])
    assert len(externa.agregadas) == 1 and "FRI_PRUEBAS_EXTERNAS=1" in externa.agregadas[0].kwargs["reason"]
    assert offline.agregadas == []
    with G.prueba_externa() as abierto:
        assert abierto is False and not G.permitido()


def test_la_autorizacion_externa_solo_abre_durante_la_prueba_y_es_independiente_de_postgres(monkeypatch):
    """Sin conectar a nada: con la autorización simulada, el permiso existe solo dentro de prueba_externa(), quita
    los proxies mientras dura y los repone. Las claves siguen vacías. FRI_PRUEBAS_POSTGRES no la concede."""
    assert "FRI_PRUEBAS_POSTGRES" not in open(CARPETA_TESTS / "_guardia_red.py", encoding="utf-8").read()
    monkeypatch.setitem(G._PERMISO, "autorizadas", True)
    assert not G.permitido()
    with G.prueba_externa() as abierto:
        assert abierto and G.permitido() and "HTTPS_PROXY" not in os.environ
        assert os.environ.get("GEMINI_API_KEY") == ""
    assert not G.permitido() and os.environ.get("HTTPS_PROXY") == G.PROXY_MUERTO


@pytest.mark.parametrize("intentos, externa, esperados_, falla", [
    ([], False, False, False),
    ([{"capa": "curl_cffi.Session.request", "destino": "query2.finance.yahoo.com", "permitido": False}], False, False, True),
    ([{"capa": "curl_cffi.Session.request", "destino": "query2.finance.yahoo.com", "permitido": True}], True, False, False),
    ([{"capa": "dns.getaddrinfo", "destino": FICTICIO, "permitido": False}], False, True, False),
])
def test_la_contabilidad_por_prueba(intentos, externa, esperados_, falla):
    import conftest
    motivo = conftest.motivo_de_falla_por_red(intentos, externa, esperados_)
    assert bool(motivo) is falla
    if falla:
        assert "query2.finance.yahoo.com" in motivo and "curl_cffi.Session.request" in motivo


# ---------------------------------------------------------------------------
# Meta-pruebas: marcas declaradas y dependencias externas no declaradas
# ---------------------------------------------------------------------------
MARCAS = {"externa", "simulada", "integracion_bd", "intentos_de_red_esperados"}
# Puntos de entrada que, sin un mock, llegan a un servicio externo.
FUNCIONES_EXTERNAS = {"_vencimientos_disponibles", "_cadena_de_opciones", "_precio_en_vivo", "_precio_yf_serie",
                      "_precio_yf_en_fecha"}
CLIENTES = {("yf", "Ticker"), ("yf", "download"), ("yfinance", "Ticker"), ("yfinance", "download"),
            ("genai", "Client"), ("requests", "get"), ("requests", "post"), ("requests", "request"),
            ("requests", "Session"), ("httpx", "get"), ("httpx", "Client"), ("urllib.request", "urlopen")}


def test_pytest_ini_declara_las_marcas_y_las_exige():
    ini = configparser.ConfigParser()
    ini.read(RAIZ / "pytest.ini", encoding="utf-8")
    declaradas = {linea.split(":")[0].strip() for linea in ini["pytest"]["markers"].strip().splitlines()}
    assert declaradas == MARCAS
    assert "--strict-markers" in ini["pytest"]["addopts"]


def _marcas_de(funcion: ast.FunctionDef, modulo: ast.Module) -> set:
    marcas = set()
    for d in funcion.decorator_list:
        for n in ast.walk(d):
            if isinstance(n, ast.Attribute) and n.attr in MARCAS:
                marcas.add(n.attr)
    for n in modulo.body:  # pytestmark de módulo
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets):
            marcas |= {a.attr for a in ast.walk(n) if isinstance(a, ast.Attribute) and a.attr in MARCAS}
    return marcas


def _llamadas_externas(funcion: ast.FunctionDef) -> list[str]:
    encontradas = []
    for n in ast.walk(funcion):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute) and f.attr in FUNCIONES_EXTERNAS:
            encontradas.append(f.attr)
        elif isinstance(f, ast.Name) and f.id in FUNCIONES_EXTERNAS:
            encontradas.append(f.id)
        elif isinstance(f, ast.Attribute) and isinstance(f.value, (ast.Name, ast.Attribute)):
            base = ast.unparse(f.value)
            if (base, f.attr) in CLIENTES:
                encontradas.append(f"{base}.{f.attr}")
    return encontradas


def _consulta_la_marca_externa(funcion: ast.FunctionDef) -> bool:
    """True si la función llama a get_closest_marker("externa") (se busca en el árbol, no como texto)."""
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get_closest_marker"
               and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "externa"
               for n in ast.walk(funcion))


def test_ninguna_prueba_usa_un_servicio_externo_sin_declararlo():
    """Toda prueba que llame directamente a un punto de entrada externo debe estar marcada 'externa' (se omite sin
    autorización) o 'simulada' (reemplaza el servicio por uno falso). Un fixture o ayudante que lo llame debe
    consultar la marca 'externa' antes. Esto avisa temprano; la contabilidad por prueba es la red de seguridad."""
    hallazgos = []
    for ruta in sorted(CARPETA_TESTS.glob("test_*.py")):
        if ruta.name == Path(__file__).name:
            continue
        modulo = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(modulo):
            if not isinstance(nodo, ast.FunctionDef):
                continue
            llamadas = _llamadas_externas(nodo)
            if not llamadas:
                continue
            if nodo.name.startswith("test_"):
                if not (_marcas_de(nodo, modulo) & {"externa", "simulada"}):
                    hallazgos.append(f"{ruta.name}::{nodo.name} llama a {sorted(set(llamadas))} sin marca externa/simulada")
            elif not _consulta_la_marca_externa(nodo):
                hallazgos.append(f"{ruta.name}::{nodo.name} (ayudante o fixture) llama a {sorted(set(llamadas))} "
                                 "sin consultar la marca externa")
    assert hallazgos == []


def test_la_marca_de_intentos_esperados_solo_la_usan_las_pruebas_del_guardia():
    for ruta in CARPETA_TESTS.glob("test_*.py"):
        if ruta.name != Path(__file__).name:
            assert "intentos_de_red_esperados" not in ruta.read_text(encoding="utf-8"), ruta.name


def test_las_pruebas_de_derivados_que_no_usan_red_no_quedan_marcadas():
    """El fixture de Yahoo de test_derivados_seccion.py era de módulo y hacía que hasta sus pruebas puras salieran a
    internet. Ahora solo corre en las marcadas 'externa', y las dos pruebas puras quedan sin marca."""
    modulo = ast.parse((CARPETA_TESTS / "test_derivados_seccion.py").read_text(encoding="utf-8"))
    funciones = {n.name: n for n in modulo.body if isinstance(n, ast.FunctionDef)}
    for pura in ("test_dias_al_vencimiento_nunca_es_negativo_para_una_fecha_pasada",
                 "test_el_precio_de_mercado_usa_el_ultimo_transado_si_no_hay_bid_ni_ask"):
        assert not _marcas_de(funciones[pura], modulo), pura
    fixture = funciones["_requiere_yahoo_en_vivo"]
    assert _consulta_la_marca_externa(fixture)
    assert not any("scope" in ast.unparse(d) for d in fixture.decorator_list)
