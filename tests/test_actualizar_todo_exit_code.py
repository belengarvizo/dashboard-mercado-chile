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

import time

from scripts.actualizar_todo import (
    Paso,
    Resultado,
    _decidir_exit_code,
    _correr_con_limite,
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


def test_correr_con_limite_devuelve_el_resultado_si_termina_a_tiempo():
    assert _correr_con_limite(lambda: 42, segundos=5) == 42


def test_correr_con_limite_relanza_la_excepcion_real():
    def _falla():
        raise ValueError("boom")

    try:
        _correr_con_limite(_falla, segundos=5)
        assert False, "debería haber relanzado ValueError"
    except ValueError as e:
        assert "boom" in str(e)


def test_correr_con_limite_corta_un_paso_colgado_sin_bloquear_el_proceso():
    """El caso real: una llamada que nunca retorna (como el fetch RSS sin
    timeout que dejó el cron 'Running' 7+ horas en producción). Debe lanzar
    TimeoutError apenas se cumple el límite -- y el propio test, que termina
    acá, es la prueba de que el hilo colgado (daemon) no bloquea la salida."""
    t0 = time.time()
    try:
        _correr_con_limite(lambda: time.sleep(3600), segundos=1)
        assert False, "debería haber lanzado TimeoutError"
    except TimeoutError as e:
        transcurrido = time.time() - t0
        assert transcurrido < 5, f"el timeout debería cortar cerca de 1s, tardó {transcurrido:.1f}s"
        assert "no terminó" in str(e)


if __name__ == "__main__":
    test_todo_ok_exit_0()
    test_falla_critica_exit_1()
    test_falla_no_critica_racha_corta_exit_0()
    test_falla_no_critica_racha_larga_escala_a_exit_1()
    test_critica_manda_aunque_no_critica_tambien_falle()
    test_correr_con_limite_devuelve_el_resultado_si_termina_a_tiempo()
    test_correr_con_limite_relanza_la_excepcion_real()
    test_correr_con_limite_corta_un_paso_colgado_sin_bloquear_el_proceso()
    print("OK: las ocho pruebas pasaron.")
