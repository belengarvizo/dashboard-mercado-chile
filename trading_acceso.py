"""Control de acceso de la pestaña Divisas.

POR QUÉ EXISTE. El dashboard es público, pero esa pestaña muestra el diario
de operaciones, el equity, los planes de evento y las tesis. Nada de eso debe
verlo quien abra el enlace.

QUÉ PROTEGE Y QUÉ NO. Esto evita que un visitante casual vea la estrategia.
NO es un sistema de autenticación: no hay usuarios, la contraseña es una sola
y viaja en el formulario de Streamlit. Sirve para lo que tiene que servir, y
conviene no confundirlo con más de lo que es.

LA CONTRASEÑA NUNCA ESTÁ EN EL CÓDIGO. Sale de la variable de entorno
DASHBOARD_PASSWORD. Si no está definida, la pestaña NO se abre: falla
cerrada. Y no se imprime, ni se registra, ni se devuelve en ningún error —
tampoco los intentos fallidos.

Módulo sin Streamlit: testeable sin levantar la app.
"""
import hmac
import os
import threading
import time

VARIABLE_ENTORNO = "DASHBOARD_PASSWORD"

# Tope de intentos fallidos SEGUIDOS antes de bloquear, y cuánto dura el
# bloqueo. El contador vive a nivel de módulo, no de sesión: si fuera por
# sesión, bastaría abrir una pestaña nueva para reiniciarlo y el límite no
# serviría de nada. Al ser de módulo, es compartido por todos los visitantes
# del mismo proceso.
MAX_INTENTOS = 5
SEGUNDOS_BLOQUEO = 60
# Pausa tras un intento fallido: encarece probar contraseñas de a una sin
# molestar a quien se equivocó al tipear.
PAUSA_TRAS_FALLO = 1.0

_candado = threading.Lock()
_fallidos = 0
_bloqueado_hasta = 0.0


def password_configurada() -> bool:
    """Si la variable de entorno existe y no está vacía. NO devuelve el valor."""
    return bool((os.environ.get(VARIABLE_ENTORNO) or "").strip())


def estado_bloqueo(ahora: float | None = None) -> tuple[bool, int]:
    """(está bloqueado, segundos que faltan)."""
    ahora = time.time() if ahora is None else ahora
    with _candado:
        restante = _bloqueado_hasta - ahora
    if restante > 0:
        return True, int(restante) + 1
    return False, 0


def intentos_fallidos() -> int:
    with _candado:
        return _fallidos


def reiniciar_estado() -> None:
    """Solo para las pruebas: vuelve el contador y el bloqueo a cero."""
    global _fallidos, _bloqueado_hasta
    with _candado:
        _fallidos = 0
        _bloqueado_hasta = 0.0


def verificar(intento: str, ahora: float | None = None) -> tuple[bool, str]:
    """Compara el intento con la contraseña configurada.

    Devuelve (acertó, motivo). El motivo NUNCA incluye el intento ni la
    contraseña: solo describe qué pasó.
    """
    global _fallidos, _bloqueado_hasta
    ahora = time.time() if ahora is None else ahora

    bloqueado, restante = estado_bloqueo(ahora)
    if bloqueado:
        return False, (
            f"Demasiados intentos fallidos. Espera {restante} segundos antes de "
            f"volver a probar.")

    esperada = (os.environ.get(VARIABLE_ENTORNO) or "").strip()
    if not esperada:
        # Falla cerrada: sin variable configurada no se entra, ni siquiera
        # acertando una cadena vacía.
        return False, (
            f"La pestaña no está configurada: falta la variable de entorno "
            f"{VARIABLE_ENTORNO}.")

    # compare_digest en vez de ==: el tiempo que tarda no depende de cuántos
    # caracteres coincidan, así que no se puede adivinar la contraseña
    # midiendo respuestas.
    if hmac.compare_digest(str(intento or ""), esperada):
        with _candado:
            _fallidos = 0
            _bloqueado_hasta = 0.0
        return True, ""

    with _candado:
        _fallidos += 1
        quedan = MAX_INTENTOS - _fallidos
        if _fallidos >= MAX_INTENTOS:
            _bloqueado_hasta = ahora + SEGUNDOS_BLOQUEO
            _fallidos = 0
            return False, (
                f"Contraseña incorrecta. Se alcanzó el límite de {MAX_INTENTOS} "
                f"intentos: bloqueado por {SEGUNDOS_BLOQUEO} segundos.")
    return False, f"Contraseña incorrecta. Quedan {quedan} intentos antes del bloqueo."


def instrucciones_variable() -> str:
    """Cómo crear la variable en Railway, sin mencionar ningún valor."""
    return (
        f"Railway → servicio **dashboard-mercado-chile** → pestaña **Variables** → "
        f"**New Variable** → nombre `{VARIABLE_ENTORNO}` → pega la contraseña en el "
        f"campo de valor → **Add**. El servicio se reinicia solo y la pestaña queda "
        f"habilitada. La contraseña no se escribe en el código ni en el repositorio."
    )
