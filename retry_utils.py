"""
Reintentos con backoff exponencial para operaciones propensas a cortes
transitorios de red o de conexión: la conexión serverless a Neon Postgres
(que puede cerrarse sola si estuvo inactiva un rato) y los feeds RSS
externos que usa actualizar_noticias.py. El objetivo es que un corte
transitorio no se cuente como un fallo real del paso completo — solo se
reporta error después de agotar todos los reintentos.
"""

import time

ESPERAS_REINTENTO_SEGUNDOS = (2, 4, 8)  # backoff exponencial: hasta 3 reintentos


def con_reintentos(func, *args, **kwargs):
    """Reintenta `func(*args, **kwargs)` hasta 3 veces más (esperas de 2, 4
    y 8 segundos entre intentos) si lanza una excepción. Relanza el error
    real solo después de agotar todos los reintentos. Para operaciones sin
    estado (ej. un fetch RSS) — para escrituras de BD usar con_reintentos_db."""
    ultimo_error = None
    for intento in range(len(ESPERAS_REINTENTO_SEGUNDOS) + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            ultimo_error = e
            if intento == len(ESPERAS_REINTENTO_SEGUNDOS):
                raise
            espera = ESPERAS_REINTENTO_SEGUNDOS[intento]
            print(f"  Fallo transitorio ({e}) - reintento {intento + 1}/{len(ESPERAS_REINTENTO_SEGUNDOS)} en {espera}s...")
            time.sleep(espera)
    raise ultimo_error  # inalcanzable (el loop siempre retorna o relanza), solo para el linter


def con_reintentos_db(session, func, *args, **kwargs):
    """Igual que con_reintentos, pero pensado para operaciones de
    SQLAlchemy: hace session.rollback() entre intentos. Tras un error de
    conexión, SQLAlchemy invalida automáticamente la conexión caída, pero
    la sesión queda en un estado que no admite más queries hasta hacer
    rollback() — sin eso, el siguiente intento fallaría de inmediato con
    el mismo error en vez de tomar una conexión nueva del pool."""
    ultimo_error = None
    for intento in range(len(ESPERAS_REINTENTO_SEGUNDOS) + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            ultimo_error = e
            session.rollback()
            if intento == len(ESPERAS_REINTENTO_SEGUNDOS):
                raise
            espera = ESPERAS_REINTENTO_SEGUNDOS[intento]
            print(f"  Fallo transitorio de BD ({e}) - reintento {intento + 1}/{len(ESPERAS_REINTENTO_SEGUNDOS)} en {espera}s...")
            time.sleep(espera)
    raise ultimo_error  # inalcanzable, solo para el linter
