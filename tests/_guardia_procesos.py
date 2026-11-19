"""Guardia de procesos hijos para las pruebas (P-2): denegación por defecto.

POR QUÉ
=======
Un proceso hijo no hereda la aduana de PostgreSQL ni los parches del guardia de red: en el hijo, libpq y un socket
directo conectan sin control. Los proxies muertos frenan HTTP, pero no a libpq. Por eso, desde las pruebas, ningún
proceso hijo se crea salvo por las dos vías explícitas de abajo.

QUÉ SE BLOQUEA (antes de crear el proceso)
==========================================
subprocess.Popen (y todo lo que lo usa: run, call, check_output, os.popen, asyncio), _winapi.CreateProcess (por ahí
pasan subprocess y multiprocessing en Windows), os.system, os.popen, os.spawn*, os.exec*, os.startfile y, en
sistemas POSIX, fork, forkpty, posix_spawn y fork_exec. Cada intento queda en el registro compartido del guardia de
red (capa «proceso.*»): conftest.py deja en rojo a la prueba aunque el código capture la excepción, y la marca
'externa' NO exime de esto.

LAS DOS ÚNICAS EXCEPCIONES
==========================
  - ejecutar_archivo_de_prueba(nombre): corre `python tests/test_*.py` para verificar que el guardia de la base
    detiene la ejecución directa (prueba de la Etapa 0). Solo archivos test_*.py de esta carpeta.
  - ejecutar_python_con_guardias(codigo): corre código en un Python hijo que instala TODOS los guardias (base, red,
    procesos) antes de ejecutar nada.
Ambas usan un entorno mínimo armado desde cero (no se hereda: DATABASE_URL bloqueada, claves vacías, proxies muertos,
sin variables PYTHON*, sin el site del usuario) y una carpeta temporal sin .env como directorio de trabajo. Solo las
pueden usar las pruebas de los guardias (lo exige una meta-prueba).

LÍMITES
=======
Un proceso creado por código nativo (ctypes, una extensión en C) no pasa por estas funciones. Una meta-prueba marca
el uso de ctypes en las pruebas.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

CARPETA_TESTS = Path(__file__).resolve().parent
RAIZ = CARPETA_TESTS.parent

ORIGINALES: dict[str, tuple] = {}
FUNCIONES_PROTEGIDAS: list[str] = []
PERMITIDOS: list[dict] = []  # procesos creados por las dos vías permitidas (motivo y programa, nunca argumentos)
INSTALADO = False

_ESTADO = threading.local()

# Variables del sistema que un Python hijo necesita en Windows para arrancar; todo lo demás no se hereda.
VARIABLES_DEL_SISTEMA = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP")


class ProcesoBloqueado(Exception):
    """Un proceso hijo que el guardia rechazó antes de crearlo."""


def _red():
    return sys.modules["_guardia_red"]


def _bloquear(capa: str, programa) -> None:
    nombre = Path(str(programa)).name if programa else "?"
    _red()._registrar(capa, nombre, False)
    raise ProcesoBloqueado(
        f"Proceso hijo bloqueado por el guardia de pruebas (capa: {capa}; programa: {nombre}). Un proceso hijo no "
        "hereda los guardias de base de datos ni de red. No se creó ningún proceso."
    )


def _primer_elemento(valor):
    if isinstance(valor, (list, tuple)) and valor:
        return valor[0]
    if isinstance(valor, (str, bytes, os.PathLike)):
        texto = os.fsdecode(valor) if not isinstance(valor, str) else valor
        return texto.split()[0] if texto.split() else texto
    return None


def _envolver(original, capa, programa_de):
    def envoltura(*args, **kwargs):
        if getattr(_ESTADO, "permitido", False):
            return original(*args, **kwargs)
        _bloquear(capa, programa_de(args, kwargs))
    envoltura._guardia_procesos = True
    envoltura.__name__ = getattr(original, "__name__", capa)
    return envoltura


def _reemplazar(objeto, nombre, capa, programa_de):
    original = getattr(objeto, nombre, None)
    if original is None or getattr(original, "_guardia_procesos", False):
        return
    ORIGINALES[f"{getattr(objeto, '__name__', type(objeto).__name__)}.{nombre}"] = (objeto, nombre, original)
    setattr(objeto, nombre, _envolver(original, capa, programa_de))
    FUNCIONES_PROTEGIDAS.append(f"{getattr(objeto, '__name__', objeto)}.{nombre}")


def instalar() -> None:
    """Idempotente. La llama _guardia_red al final de su instalación."""
    global INSTALADO
    if INSTALADO:
        return
    # subprocess: Popen._execute_child(self, args, executable, ...) es el punto común de run/call/check_output/popen.
    _reemplazar(subprocess.Popen, "_execute_child", "proceso.subprocess.Popen",
                lambda a, k: _primer_elemento(a[1] if len(a) > 1 else k.get("args")))
    if sys.platform == "win32":
        import _winapi
        # CreateProcess(application_name, command_line, ...): lo usan subprocess y multiprocessing en Windows.
        _reemplazar(_winapi, "CreateProcess", "proceso._winapi.CreateProcess",
                    lambda a, k: a[0] or _primer_elemento(a[1] if len(a) > 1 else None))
    else:
        import _posixsubprocess
        _reemplazar(_posixsubprocess, "fork_exec", "proceso.fork_exec", lambda a, k: _primer_elemento(a[0] if a else None))
        if hasattr(subprocess, "_fork_exec"):
            _reemplazar(subprocess, "_fork_exec", "proceso.fork_exec", lambda a, k: _primer_elemento(a[0] if a else None))
    _reemplazar(os, "system", "proceso.os.system", lambda a, k: _primer_elemento(a[0] if a else None))
    _reemplazar(os, "popen", "proceso.os.popen", lambda a, k: _primer_elemento(a[0] if a else None))
    for nombre in ("spawnv", "spawnve", "spawnvp", "spawnvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe"):
        _reemplazar(os, nombre, f"proceso.os.{nombre}", lambda a, k: a[1] if len(a) > 1 else None)
    for nombre in ("execv", "execve", "execvp", "execvpe", "execl", "execle", "execlp", "execlpe"):
        _reemplazar(os, nombre, f"proceso.os.{nombre}", lambda a, k: a[0] if a else None)
    for nombre in ("startfile", "fork", "forkpty", "posix_spawn", "posix_spawnp"):
        _reemplazar(os, nombre, f"proceso.os.{nombre}", lambda a, k: a[0] if a else None)
    # pywin32 (instalado en esta máquina) crea procesos llamando a Windows directamente, sin pasar por lo de arriba.
    import importlib.util
    if importlib.util.find_spec("win32process"):
        import win32process
        for nombre in ("CreateProcess", "CreateProcessAsUser"):
            _reemplazar(win32process, nombre, f"proceso.win32process.{nombre}",
                        lambda a, k: a[0] or _primer_elemento(a[1] if len(a) > 1 else None))
    if importlib.util.find_spec("win32api"):
        import win32api
        _reemplazar(win32api, "ShellExecute", "proceso.win32api.ShellExecute", lambda a, k: a[2] if len(a) > 2 else None)
        _reemplazar(win32api, "WinExec", "proceso.win32api.WinExec", lambda a, k: _primer_elemento(a[0] if a else None))
    INSTALADO = True


# ---------------------------------------------------------------------------
# Las dos vías permitidas
# ---------------------------------------------------------------------------
def entorno_aislado() -> dict:
    """Entorno armado desde cero para un hijo: nada se hereda salvo lo que Windows necesita para arrancar Python."""
    entorno = {v: os.environ[v] for v in VARIABLES_DEL_SISTEMA if v in os.environ}
    entorno["PATH"] = os.pathsep.join([str(Path(sys.executable).parent),
                                       str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32")])
    entorno["DATABASE_URL"] = sys.modules["_guardia_bd"].URL_BLOQUEADA  # el hijo nunca usa una base, ni la local
    red = _red()
    for variable in red.VARIABLES_DE_PROXY:
        entorno[variable] = red.PROXY_MUERTO
    entorno["NO_PROXY"] = entorno["no_proxy"] = red.SIN_PROXY
    for clave in red.CLAVES_NEUTRALIZADAS:
        entorno[clave] = ""
    entorno["PYTHONIOENCODING"] = "utf-8"
    return entorno


def _ejecutar(argv: list[str], motivo: str, timeout: float) -> subprocess.CompletedProcess:
    carpeta = tempfile.mkdtemp(prefix="fri-hijo-")  # sin .env: el hijo no puede encontrarlo por cercanía
    _ESTADO.permitido = True
    try:
        resultado = subprocess.run(argv, cwd=carpeta, env=entorno_aislado(), capture_output=True, text=True,
                                   timeout=timeout, stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
    finally:
        _ESTADO.permitido = False
        shutil.rmtree(carpeta, ignore_errors=True)
    PERMITIDOS.append({"motivo": motivo, "programa": Path(argv[0]).name})
    return resultado


def ejecutar_archivo_de_prueba(nombre: str, motivo: str, timeout: float = 120) -> subprocess.CompletedProcess:
    """`python tests/<nombre>` con el entorno aislado. Solo archivos test_*.py que estén directamente en tests/."""
    ruta = (CARPETA_TESTS / nombre).resolve()
    if ruta.parent != CARPETA_TESTS or not ruta.name.startswith("test_") or ruta.suffix != ".py" or not ruta.is_file():
        raise ValueError("Solo se puede ejecutar un archivo test_*.py de la carpeta tests/.")
    return _ejecutar([sys.executable, "-E", "-s", str(ruta)], motivo, timeout)


ARRANQUE = (
    "import sys\n"
    f"sys.path.insert(0, {str(CARPETA_TESTS)!r})\n"
    "import _guardia_bd  # instala los guardias de base, red y procesos ANTES de ejecutar el código\n"
)


def ejecutar_python_con_guardias(codigo: str, motivo: str, timeout: float = 120) -> subprocess.CompletedProcess:
    """Un Python hijo que instala todos los guardias antes de ejecutar `codigo`, con el entorno aislado."""
    return _ejecutar([sys.executable, "-E", "-s", "-c", ARRANQUE + codigo], motivo, timeout)
