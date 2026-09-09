"""Valida la lógica de código de salida de actualizar_todo.py (Opción D):

  - falla un paso crítico            -> exit 1
  - falla solo un paso no crítico,
    racha corta                      -> exit 0 (CORRIDA PARCIAL)
  - falla un paso no crítico y la
    racha supera el umbral           -> exit 1 (se escala)

Tests de la función pura _decidir_exit_code, sin BD ni red.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from scripts.actualizar_todo import (
    Paso,
    Resultado,
    _decidir_exit_code,
    MAX_FALLAS_NO_CRITICAS_TOLERADAS,
)

_CRIT = Paso("Series del BCCh", None, True, "bcch")
_NOCRIT = Paso("Resumen diario (IA)", None, False, "brief")


def _r(paso, ok):
    return Resultado(paso, ok, None if ok else "boom")


def test_todo_ok_exit_0():
    code, msgs = _decidir_exit_code([_r(_CRIT, True), _r(_NOCRIT, True)], {})
    assert code == 0 and msgs == []


def test_falla_critica_exit_1():
    code, msgs = _decidir_exit_code([_r(_CRIT, False), _r(_NOCRIT, True)], {})
    assert code == 1
    assert any("CRÍTICO" in m for m in msgs)


def test_falla_no_critica_racha_corta_exit_0():
    # racha = 1 == tolerado -> NO escala
    code, msgs = _decidir_exit_code(
        [_r(_CRIT, True), _r(_NOCRIT, False)],
        {"brief": MAX_FALLAS_NO_CRITICAS_TOLERADAS},
    )
    assert code == 0
    assert any("CORRIDA PARCIAL" in m for m in msgs)


def test_falla_no_critica_racha_larga_escala_a_exit_1():
    # racha = tolerado + 1 -> escala
    code, msgs = _decidir_exit_code(
        [_r(_CRIT, True), _r(_NOCRIT, False)],
        {"brief": MAX_FALLAS_NO_CRITICAS_TOLERADAS + 1},
    )
    assert code == 1
    assert any("se escala a fallo" in m for m in msgs)


def test_critica_manda_aunque_no_critica_tambien_falle():
    code, msgs = _decidir_exit_code(
        [_r(_CRIT, False), _r(_NOCRIT, False)],
        {"brief": 5},
    )
    assert code == 1
    assert any("CRÍTICO" in m for m in msgs)
    # con falla crítica, ni siquiera evalúa la racha del no crítico
    assert not any("CORRIDA PARCIAL" in m for m in msgs)


if __name__ == "__main__":
    test_todo_ok_exit_0()
    test_falla_critica_exit_1()
    test_falla_no_critica_racha_corta_exit_0()
    test_falla_no_critica_racha_larga_escala_a_exit_1()
    test_critica_manda_aunque_no_critica_tambien_falle()
    print("OK: las cinco pruebas pasaron.")
