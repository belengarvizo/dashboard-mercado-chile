"""¿Está una sección en el selector del dashboard?

PARA QUÉ EXISTE. Divisas, Simulación Mesa de Dinero y Defensa Top-Down
salieron del selector el 20-10-2026, pero su código y sus pruebas siguen
enteros en el repo a propósito: la idea es poder devolverlas sacando un
nombre de una tupla.

Eso dejaría en rojo a las ~100 pruebas que RENDERIZAN esas secciones, que
pasarían a mirar la primera sección del selector y no encontrarían nada de lo
que buscan. Un rojo así no informa: no es una regresión, es una sección
apagada. Así que esas pruebas se saltan solas mientras la sección esté
oculta, y vuelven a correr sin tocar ni una línea el día que se devuelva.

Las pruebas de los módulos puros (trading_atr, trading_correlacion,
trading_fx, trading_proceso, trading_reglas, trading_recuperacion,
defensa_topdown) NO usan esto y siguen corriendo siempre: ese código no
depende del selector y tiene que seguir cuidado.

POR QUÉ SE LEE EL FUENTE Y NO SE IMPORTA EL MÓDULO. Importar
app/dashboard.py ejecutaría la app entera fuera de Streamlit. Otras pruebas
del repo ya leen ese archivo como texto por el mismo motivo.
"""
import os
import re

import pytest

DASHBOARD = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
MARCA = "SECCIONES_FUERA_DEL_SELECTOR = ("


def secciones_ocultas() -> frozenset:
    """Los nombres que hoy están fuera del selector.

    Si la marca no aparece, devuelve el conjunto vacío: así, si alguien borra
    el interruptor y deja las secciones visibles de nuevo, nada se salta.
    """
    with open(DASHBOARD, encoding="utf-8") as f:
        codigo = f.read()
    inicio = codigo.find(MARCA)
    if inicio == -1:
        return frozenset()
    bloque = codigo[inicio + len(MARCA):codigo.index(")", inicio)]
    return frozenset(re.findall(r'"([^"]+)"', bloque))


def exigir_seccion(nombre: str) -> None:
    """Salta la prueba si esa sección no está en el selector."""
    if nombre in secciones_ocultas():
        pytest.skip(
            f"La sección {nombre!r} está fuera del selector del dashboard "
            f"({MARCA[:-4]}), así que no hay nada que renderizar. El código y "
            f"esta prueba siguen en el repo: saca el nombre de esa tupla y "
            f"vuelve a correr."
        )
