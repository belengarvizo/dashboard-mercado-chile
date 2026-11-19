"""Pruebas de aceptación de P-2: credenciales y procesos hijos.

SEGURIDAD DE ESTAS PRUEBAS
    - Credenciales: los casos con override=True usan un .env FICTICIO (valores inventados y un servidor .invalid). Con
      el .env real solo se usan las vías de python-dotenv, y sus resultados se comparan con «» o con la URL bloqueada:
      ningún valor se imprime ni se guarda.
    - Procesos: cada intento usa un comando que, de ejecutarse, crearía un archivo testigo en una carpeta temporal; la
      prueba verifica que el archivo NO aparezca. Antes de llamar a funciones que serían peligrosas si el guardia
      fallara (os.execv reemplazaría al propio pytest; os.startfile abriría un programa), se comprueba que estén
      reemplazadas.
    - Este archivo está en ARCHIVOS_DEL_GUARDIA de test_guardia_bd.py: importa subprocess y usa override=True a
      propósito, que es justo lo que las meta-pruebas prohíben en las demás pruebas.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import ast
import asyncio
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path

import pytest

GB = sys.modules["_guardia_bd"]
GR = sys.modules["_guardia_red"]
GP = sys.modules["_guardia_procesos"]
CARPETA_TESTS = Path(__file__).resolve().parent
RAIZ = CARPETA_TESTS.parent
sys.path.append(str(RAIZ))
esperados = pytest.mark.intentos_de_red_esperados

URL_PRODUCCION_FICTICIA = "postgresql://usuario_prod:clave-ficticia@servidor-produccion-ficticio.invalid:5432/railway"


def _requisito(condicion, mensaje):
    if not condicion:
        pytest.fail(f"Requisito de seguridad de la prueba: {mensaje}")


@pytest.fixture
def env_ficticio(tmp_path):
    archivo = tmp_path / ".env"
    archivo.write_text(f"DATABASE_URL={URL_PRODUCCION_FICTICIA}\nGEMINI_API_KEY=clave-ficticia-gemini\n"
                       "OTRO_SERVICIO_TOKEN=token-ficticio\nCONFIG_NO_SENSIBLE=1\n", encoding="utf-8")
    return archivo


# ---------------------------------------------------------------------------
# 1 y 2. Credenciales vía python-dotenv
# ---------------------------------------------------------------------------
def test_load_dotenv_con_override_no_repone_una_url_de_produccion_ni_las_claves(env_ficticio):
    from dotenv import load_dotenv
    load_dotenv(env_ficticio, override=True)
    assert os.environ["DATABASE_URL"] == GB.URL_BLOQUEADA
    assert os.environ["GEMINI_API_KEY"] == ""
    assert os.environ.get("OTRO_SERVICIO_TOKEN", "") == ""


def test_las_vias_de_python_dotenv_entregan_valores_enmascarados(env_ficticio):
    from dotenv import dotenv_values, get_key
    from dotenv.main import DotEnv
    for valores in (dotenv_values(env_ficticio), DotEnv(env_ficticio).dict(), dict(DotEnv(env_ficticio).parse())):
        assert valores["DATABASE_URL"] == GB.URL_BLOQUEADA
        assert valores["GEMINI_API_KEY"] == "" and valores["OTRO_SERVICIO_TOKEN"] == ""
        assert valores["CONFIG_NO_SENSIBLE"] == "1"  # lo que no es credencial pasa igual
    assert get_key(env_ficticio, "GEMINI_API_KEY") == ""


def test_el_env_real_por_python_dotenv_tampoco_revela_credenciales():
    """Solo comparaciones con «» y con la URL bloqueada: ningún valor se muestra."""
    from dotenv import dotenv_values
    from dotenv.main import DotEnv
    archivo = RAIZ / ".env"
    if not archivo.is_file():
        pytest.skip("No hay .env en esta máquina.")
    for valores in (dotenv_values(archivo), DotEnv(archivo).dict()):
        assert valores.get("DATABASE_URL", GB.URL_BLOQUEADA) == GB.URL_BLOQUEADA
        assert all(valores.get(c, "") == "" for c in GR.CLAVES_NEUTRALIZADAS)


def test_las_variables_heredadas_con_nombre_de_credencial_quedan_vacias():
    assert GR.es_nombre_sensible("OTRO_SERVICIO_API_KEY") and GR.es_nombre_sensible("github_token")
    assert GR.es_nombre_sensible("AWS_SECRET_ACCESS_KEY") and GR.es_nombre_sensible("SMTP_PASSWORD")
    assert not GR.es_nombre_sensible("PATH") and not GR.es_nombre_sensible("DATABASE_URL")
    instaladas = [n for n in GR.CLAVES_NEUTRALIZADAS if n in os.environ]
    assert instaladas and all(os.environ[n] == "" for n in instaladas)


# ---------------------------------------------------------------------------
# Lectura directa del .env: bloqueada (python-dotenv sí, enmascarado)
# ---------------------------------------------------------------------------
@esperados
def test_leer_el_env_directamente_se_bloquea_por_todas_las_vias_de_python(monkeypatch):
    archivo = RAIZ / ".env"
    import io
    for leer in (lambda: open(archivo).read(), lambda: io.open(archivo).read(), lambda: archivo.read_text(),
                 lambda: archivo.read_bytes(), lambda: os.open(archivo, os.O_RDONLY)):
        with pytest.raises(GR.ArchivoProtegido):
            leer()
    monkeypatch.chdir(RAIZ)
    with pytest.raises(GR.ArchivoProtegido):
        open(".env")  # ruta relativa
    assert GR.REGISTRO[-1]["capa"].startswith("archivo.") and GR.REGISTRO[-1]["destino"] == ".env"


@esperados
def test_tambien_se_bloquean_las_vias_que_no_pasan_por_open():
    """_io.open (en C) y la referencia propia que tokenize guardó al importarse (de ella dependen tokenize.open y
    linecache). La sonda de P-2 encontró estas vías abiertas; io.FileIO sigue abierta (ver el informe)."""
    import _io
    import linecache
    import tokenize
    archivo = RAIZ / ".env"
    for leer in (lambda: _io.open(archivo).read(), lambda: tokenize.open(archivo).read()):
        with pytest.raises(GR.ArchivoProtegido):
            leer()
    linecache.clearcache()
    with pytest.raises(GR.ArchivoProtegido):  # linecache solo captura errores de sistema: el bloqueo se ve
        linecache.getline(str(archivo), 1)
    assert GR.REGISTRO[-1]["capa"] == "archivo.tokenize"


def test_los_demas_archivos_se_abren_normalmente(tmp_path):
    otro = tmp_path / "datos.env.ejemplo"
    otro.write_text("x", encoding="utf-8")
    assert open(otro).read() == "x" and (RAIZ / "README.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 3. Procesos hijos no autorizados: bloqueados antes de crearse
# ---------------------------------------------------------------------------
def _testigo(tmp_path):
    return tmp_path / "el_proceso_se_ejecuto.txt"


def _codigo_que_crea(testigo):
    return f"open(r'{testigo}', 'w').write('x')"


@esperados
@pytest.mark.parametrize("via", ["run", "Popen", "check_output", "call", "os.system", "os.popen", "os.spawnv", "asyncio"])
def test_los_procesos_hijos_se_bloquean_antes_de_crearse(via, tmp_path):
    testigo = _testigo(tmp_path)
    argv = [sys.executable, "-c", _codigo_que_crea(testigo)]
    linea = subprocess.list2cmdline(argv)
    acciones = {
        "run": lambda: subprocess.run(argv),
        "Popen": lambda: subprocess.Popen(argv),
        "check_output": lambda: subprocess.check_output(argv),
        "call": lambda: subprocess.call(argv),
        "os.system": lambda: os.system(linea),
        "os.popen": lambda: os.popen(linea).read(),
        "os.spawnv": lambda: os.spawnv(os.P_WAIT, sys.executable, argv),
        "asyncio": lambda: asyncio.run(asyncio.create_subprocess_exec(*argv)),
    }
    with pytest.raises(GP.ProcesoBloqueado):
        acciones[via]()
    assert not testigo.exists()
    assert GR.REGISTRO[-1]["capa"].startswith("proceso.") and not GR.REGISTRO[-1]["permitido"]


def _funcion_del_hijo(ruta):  # nivel de módulo: multiprocessing necesita poder importarla
    Path(ruta).write_text("x")


@esperados
def test_multiprocessing_se_bloquea(tmp_path):
    testigo = _testigo(tmp_path)
    proceso = multiprocessing.get_context("spawn").Process(target=_funcion_del_hijo, args=(str(testigo),))
    with pytest.raises(GP.ProcesoBloqueado):
        proceso.start()
    assert not testigo.exists()


@esperados
def test_la_capa_mas_baja_de_windows_y_las_funciones_peligrosas_se_bloquean(tmp_path):
    testigo = _testigo(tmp_path)
    if sys.platform == "win32":
        import _winapi
        _requisito(getattr(_winapi.CreateProcess, "_guardia_procesos", False), "_winapi.CreateProcess reemplazado")
        with pytest.raises(GP.ProcesoBloqueado):
            _winapi.CreateProcess(None, subprocess.list2cmdline([sys.executable, "-c", _codigo_que_crea(testigo)]),
                                  None, None, False, 0, None, None, None)
        _requisito(getattr(os.startfile, "_guardia_procesos", False), "os.startfile reemplazado")
        with pytest.raises(GP.ProcesoBloqueado):
            os.startfile(str(tmp_path / "no_existe.txt"))
    try:
        import win32api
        import win32process
    except ImportError:
        win32process = None
    if win32process is not None:  # pywin32 llama a Windows directo, sin pasar por subprocess ni _winapi
        _requisito(getattr(win32process.CreateProcess, "_guardia_procesos", False), "win32process.CreateProcess reemplazado")
        with pytest.raises(GP.ProcesoBloqueado):
            win32process.CreateProcess(None, subprocess.list2cmdline([sys.executable, "-c", _codigo_que_crea(testigo)]),
                                       None, None, 0, 0, None, None, win32process.STARTUPINFO())
        _requisito(getattr(win32api.WinExec, "_guardia_procesos", False), "win32api.WinExec reemplazado")
        with pytest.raises(GP.ProcesoBloqueado):
            win32api.WinExec(subprocess.list2cmdline([sys.executable, "-c", _codigo_que_crea(testigo)]))
    _requisito(getattr(os.execv, "_guardia_procesos", False), "os.execv reemplazado (si no, reemplazaría a pytest)")
    with pytest.raises(GP.ProcesoBloqueado):
        os.execv(sys.executable, [sys.executable, "-c", _codigo_que_crea(testigo)])
    assert not testigo.exists()


# ---------------------------------------------------------------------------
# 4. Las dos vías permitidas: entorno aislado
# ---------------------------------------------------------------------------
def test_el_entorno_de_un_hijo_permitido_se_arma_desde_cero(monkeypatch):
    monkeypatch.setenv("VARIABLE_HEREDADA_FICTICIA", "no-debe-pasar")
    entorno = GP.entorno_aislado()
    assert "VARIABLE_HEREDADA_FICTICIA" not in entorno
    assert entorno["DATABASE_URL"] == GB.URL_BLOQUEADA
    assert all(entorno[c] == "" for c in GR.CLAVES_NEUTRALIZADAS)
    assert entorno["HTTPS_PROXY"] == GR.PROXY_MUERTO
    assert not {"USERPROFILE", "APPDATA", "HOME", "PYTHONPATH", "FRI_PRUEBAS_POSTGRES", "TEST_DATABASE_URL",
                "FRI_PRUEBAS_EXTERNAS"} & set(entorno)


def test_un_hijo_permitido_no_hereda_variables_y_corre_con_los_guardias(monkeypatch):
    monkeypatch.setenv("VARIABLE_HEREDADA_FICTICIA", "no-debe-pasar")
    codigo = ("import os, sys\n"
              "print('heredada=' + str(os.environ.get('VARIABLE_HEREDADA_FICTICIA')))\n"
              "print('guardias=' + str(all(m in sys.modules for m in ('_guardia_bd', '_guardia_red', '_guardia_procesos'))))\n"
              "print('cwd_sin_env=' + str(not os.path.exists('.env')))\n")
    r = GP.ejecutar_python_con_guardias(codigo, motivo="prueba de aislamiento")
    assert "heredada=None" in r.stdout and "guardias=True" in r.stdout and "cwd_sin_env=True" in r.stdout, r.stderr[-400:]
    assert GP.PERMITIDOS[-1] == {"motivo": "prueba de aislamiento", "programa": Path(sys.executable).name}


@pytest.mark.parametrize("nombre", ["../app/dashboard.py", "_guardia_bd.py", "conftest.py", "test_no_existe.py",
                                    "../tests/../verificar_final.py"])
def test_la_via_de_archivo_de_prueba_solo_acepta_test_py_de_la_carpeta_tests(nombre):
    with pytest.raises(ValueError):
        GP.ejecutar_archivo_de_prueba(nombre, motivo="no debería ejecutarse")


# ---------------------------------------------------------------------------
# 5. Una prueba que intenta evadir el guardia queda en rojo
# ---------------------------------------------------------------------------
@esperados
def test_un_intento_capturado_igual_deja_la_prueba_en_rojo_y_externa_no_lo_exime(tmp_path):
    import conftest
    marca = GR.instantanea()
    try:
        subprocess.run([sys.executable, "-c", "pass"])
    except Exception:
        pass  # el código «se defiende» tragándose el error
    try:
        open(RAIZ / ".env")
    except Exception:
        pass
    intentos = GR.intentos_desde(marca)
    assert {i["capa"] for i in intentos} == {"proceso.subprocess.Popen", "archivo.open"}
    for externa in (False, True):
        motivo = conftest.motivo_de_falla_por_red(intentos, marcada_externa=externa, intentos_esperados=False)
        assert motivo and "La marca 'externa' no autoriza esto" in motivo


# ---------------------------------------------------------------------------
# Meta-pruebas: las vías nuevas no se pueden abrir en silencio
# ---------------------------------------------------------------------------
ARCHIVOS_DEL_GUARDIA = {"_guardia_bd.py", "_guardia_red.py", "_guardia_procesos.py", "test_guardia_bd.py",
                        "test_guardia_red.py", "test_guardia_procesos.py"}
LLAMADAS_A_OS = {"system", "popen", "spawnv", "spawnve", "spawnvp", "spawnvpe", "spawnl", "spawnle", "spawnlp",
                 "spawnlpe", "execv", "execve", "execvp", "execvpe", "execl", "execle", "execlp", "execlpe", "startfile",
                 "fork", "forkpty", "posix_spawn", "posix_spawnp"}
MODULOS_NATIVOS = {"ctypes", "pty", "_winapi", "_posixsubprocess", "cffi", "win32process", "win32api", "win32com",
                   "_io", "tokenize", "linecache"}
VIAS_PERMITIDAS = {"ejecutar_python_con_guardias", "ejecutar_archivo_de_prueba"}


def _hallazgos(ruta):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    hallazgos = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            base = ast.unparse(n.func.value)
            if base == "os" and n.func.attr in LLAMADAS_A_OS:
                hallazgos.append(f"os.{n.func.attr}")
            if n.func.attr in VIAS_PERMITIDAS:
                hallazgos.append(f"vía permitida {n.func.attr} fuera de las pruebas del guardia")
            if n.func.attr == "ProcessPoolExecutor":
                hallazgos.append("ProcessPoolExecutor")
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            nombres = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""]
            for nombre in nombres:
                if nombre.split(".")[0] in MODULOS_NATIVOS:
                    hallazgos.append(f"importa {nombre}")
        if isinstance(n, ast.FunctionDef) and {a.arg for a in n.args.args} & {"pytester", "testdir"}:
            hallazgos.append(f"{n.name} usa el fixture pytester")
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.strip() in (".env", ".streamlit/secrets.toml"):
            hallazgos.append(f"menciona el archivo {n.value!r}")
    return [f"{ruta.name}: {h}" for h in hallazgos]


def test_ninguna_prueba_abre_vias_de_procesos_o_de_credenciales_sin_el_guardia():
    hallazgos = []
    for ruta in sorted(CARPETA_TESTS.glob("*.py")):
        if ruta.name not in ARCHIVOS_DEL_GUARDIA:
            hallazgos += _hallazgos(ruta)
    assert hallazgos == []


def test_pytester_ya_no_se_carga():
    assert "pytester" not in (RAIZ / "pytest.ini").read_text(encoding="utf-8").split("addopts", 1)[1].split("\n", 1)[0]


def test_los_guardias_solo_viven_en_las_pruebas():
    """Fuera de tests/ nada importa los guardias: la aplicación, los scripts y el dashboard no cambian."""
    hallazgos = []
    for ruta in RAIZ.rglob("*.py"):
        if CARPETA_TESTS in ruta.parents or ".git" in ruta.parts:
            continue
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        if any(m in texto for m in ("_guardia_bd", "_guardia_red", "_guardia_procesos")):
            hallazgos.append(str(ruta.relative_to(RAIZ)))
    assert hallazgos == []


def test_el_guardia_de_procesos_se_instala_con_los_demas():
    assert GP.INSTALADO and "procesos hijos" in GR.CAPAS_INSTALADAS
    assert "lectura directa del .env bloqueada" in GR.CAPAS_INSTALADAS
    for f in (subprocess.Popen._execute_child, os.system, os.popen, os.spawnv, os.execv):
        assert getattr(f, "_guardia_procesos", False), f
