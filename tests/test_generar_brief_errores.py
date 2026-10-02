"""Valida el manejo diferenciado de errores al generar el brief diario
(scripts/generar_brief.py): clasificación por tipo, reintento solo de fallos
transitorios, y persistencia del detalle en la tabla errores_actualizacion
para poder diagnosticar sin el log de Railway.

No llama a Gemini de verdad: usa clientes/excepciones simuladas.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from models import get_session, ErrorActualizacion
from scripts import generar_brief as gb
from scripts.generar_brief import (
    BriefBloqueadoError,
    _clasificar_error_gemini,
    _generar_contenido_brief,
    _registrar_error_actualizacion,
    _texto_de_respuesta_gemini,
)


class _ErrorApiFalso(Exception):
    """Imita google.genai.errors.APIError: trae .code (status HTTP)."""
    def __init__(self, code, message=""):
        super().__init__(message or f"api error {code}")
        self.code = code


def test_clasificacion_por_tipo_de_error():
    assert _clasificar_error_gemini(_ErrorApiFalso(429)) == "cuota"
    assert _clasificar_error_gemini(Exception("429 RESOURCE_EXHAUSTED: quota")) == "cuota"
    assert _clasificar_error_gemini(Exception("You exceeded your current quota")) == "cuota"

    assert _clasificar_error_gemini(_ErrorApiFalso(503)) == "transitorio"
    assert _clasificar_error_gemini(_ErrorApiFalso(500, "internal error")) == "transitorio"
    assert _clasificar_error_gemini(TimeoutError("read timed out")) == "transitorio"
    assert _clasificar_error_gemini(Exception("504 Deadline Exceeded")) == "transitorio"

    assert _clasificar_error_gemini(BriefBloqueadoError("finish_reason=SAFETY")) == "bloqueo"
    assert _clasificar_error_gemini(Exception("response blocked by safety settings")) == "bloqueo"

    assert _clasificar_error_gemini(ValueError("algo raro")) == "otro"
    print("OK: clasificacion por tipo de error")


def test_texto_de_respuesta_bloqueada_lanza_briefbloqueado():
    class _RespOK:
        text = "  Brief válido con contenido.  "

    class _Cand:
        finish_reason = "SAFETY"

    class _RespVacia:
        text = None
        candidates = [_Cand()]
        prompt_feedback = None

    assert _texto_de_respuesta_gemini(_RespOK()).strip().startswith("Brief válido")

    try:
        _texto_de_respuesta_gemini(_RespVacia())
        assert False, "deberia haber lanzado BriefBloqueadoError"
    except BriefBloqueadoError as e:
        assert "SAFETY" in str(e), str(e)
    print("OK: respuesta vacia/bloqueada -> BriefBloqueadoError")


def test_reintenta_solo_transitorios(monkeypatch=None):
    """Un fallo transitorio se reintenta y termina bien; uno de cuota se
    relanza de inmediato sin gastar reintentos."""
    dormidas = []
    import scripts.generar_brief as _gb
    orig_sleep = _gb.time.sleep
    _gb.time.sleep = lambda s: dormidas.append(s)
    try:
        # (a) transitorio 2 veces y despues OK
        class _Cli:
            def __init__(self):
                self.n = 0
                self.models = self

            def generate_content(self, model, contents):
                self.n += 1
                if self.n <= 2:
                    raise _ErrorApiFalso(503, "service unavailable")
                return type("R", (), {"text": "brief tras 2 reintentos"})()

        cli = _Cli()
        out = _generar_contenido_brief(cli, "prompt")
        assert out == "brief tras 2 reintentos", out
        assert cli.n == 3 and len(dormidas) == 2, (cli.n, dormidas)

        # (b) cuota -> se relanza en el primer intento, sin dormir
        dormidas.clear()

        class _CliCuota:
            models = property(lambda self: self)

            def generate_content(self, model, contents):
                raise _ErrorApiFalso(429, "RESOURCE_EXHAUSTED")

        try:
            _generar_contenido_brief(_CliCuota(), "prompt")
            assert False, "cuota deberia relanzarse, no reintentar"
        except _ErrorApiFalso as e:
            assert e.code == 429
        assert dormidas == [], "no deberia haber reintentado una cuota"
    finally:
        _gb.time.sleep = orig_sleep
    print("OK: reintenta transitorios, no reintenta cuota")


def test_prueba_modelos_de_respaldo_si_el_principal_agota_reintentos():
    """Si gemini-3.6-flash agota sus 3 reintentos por demanda alta (503), se
    prueba una vez con cada modelo de MODELOS_GEMINI_FALLBACK antes de darse
    por vencido -- verificado en vivo el 2026-09-23 (ver comentario en
    generar_brief.py): con el principal caído, gemini-3.5-flash sí respondió."""
    import scripts.generar_brief as _gb
    orig_sleep = _gb.time.sleep
    _gb.time.sleep = lambda s: None
    try:
        class _CliPrincipalCaidoPrimerRespaldoOk:
            def __init__(self):
                self.llamadas = []
                self.models = self

            def generate_content(self, model, contents):
                self.llamadas.append(model)
                if model == _gb.MODELO_GEMINI:
                    raise _ErrorApiFalso(503, "high demand")
                if model == _gb.MODELOS_GEMINI_FALLBACK[0]:
                    return type("R", (), {"text": "brief del modelo de respaldo"})()
                raise AssertionError(f"no debería haber llegado a {model}")

        cli = _CliPrincipalCaidoPrimerRespaldoOk()
        out = _generar_contenido_brief(cli, "prompt")
        assert out == "brief del modelo de respaldo", out
        # 4 intentos con el principal (1 inicial + 3 reintentos) + 1 con el
        # primer respaldo, y nunca llega al segundo
        assert cli.llamadas == [_gb.MODELO_GEMINI] * 4 + [_gb.MODELOS_GEMINI_FALLBACK[0]], cli.llamadas

        # si TODOS los modelos (principal + los 2 de respaldo) fallan
        # transitoriamente, se relanza el último error, no un genérico
        class _CliTodosCaidos:
            def __init__(self):
                self.models = self

            def generate_content(self, model, contents):
                raise _ErrorApiFalso(503, f"high demand ({model})")

        try:
            _generar_contenido_brief(_CliTodosCaidos(), "prompt")
            assert False, "debería haber relanzado el error tras agotar todos los modelos"
        except _ErrorApiFalso as e:
            assert _gb.MODELOS_GEMINI_FALLBACK[-1] in str(e), str(e)
    finally:
        _gb.time.sleep = orig_sleep
    print("OK: prueba modelos de respaldo cuando el principal agota reintentos")


def test_registrar_error_persiste_fila_en_la_bd():
    marca = f"__TEST_BRIEF_ERR_{os.getpid()}"
    _registrar_error_actualizacion(marca, "transitorio", "TimeoutError", "read timed out (prueba)")

    s = get_session()
    try:
        fila = (
            s.query(ErrorActualizacion)
            .filter_by(fuente=marca)
            .order_by(ErrorActualizacion.ocurrido_en.desc())
            .first()
        )
        assert fila is not None, "no se guardo la fila en errores_actualizacion"
        assert fila.categoria == "transitorio"
        assert fila.tipo_excepcion == "TimeoutError"
        assert "read timed out" in fila.mensaje
        s.query(ErrorActualizacion).filter_by(fuente=marca).delete()
        s.commit()
    finally:
        s.close()
    print("OK: _registrar_error_actualizacion persiste y es consultable")


MENSAJE_LIMITE_POR_MINUTO = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your "
    "current quota. * Quota exceeded for metric: "
    "generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 5, "
    "model: gemini-3.6-flash\\nPlease retry in 40.389909296s.', "
    "'status': 'RESOURCE_EXHAUSTED'}}"
)
MENSAJE_CUOTA_DIARIA = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your "
    "current quota, please check your plan and billing details.', "
    "'status': 'RESOURCE_EXHAUSTED'}}"
)


def _sin_dormir_de_verdad():
    """Reemplaza time.sleep y devuelve (lista_de_esperas, restaurar)."""
    dormidas = []
    original = gb.time.sleep
    gb.time.sleep = lambda s: dormidas.append(s)
    return dormidas, (lambda: setattr(gb.time, "sleep", original))


def test_espera_sugerida_solo_cuando_la_api_la_indica():
    """Es la señal que separa el límite por minuto (se despeja en segundos)
    de la cuota diaria agotada (no se despeja hoy)."""
    assert gb._espera_sugerida_por_gemini(Exception(MENSAJE_LIMITE_POR_MINUTO)) == 40.389909296
    assert gb._espera_sugerida_por_gemini(Exception("retryDelay: '30s'")) == 30.0
    assert gb._espera_sugerida_por_gemini(Exception('"retryDelay": "7s"')) == 7.0

    # cuota diaria: sin espera sugerida
    assert gb._espera_sugerida_por_gemini(Exception(MENSAJE_CUOTA_DIARIA)) is None
    assert gb._espera_sugerida_por_gemini(_ErrorApiFalso(429, "RESOURCE_EXHAUSTED")) is None

    # una espera absurda se trata como "no hay": esperar tanto se comería el
    # watchdog del paso en actualizar_todo.py
    excesiva = gb.TOPE_ESPERA_SUGERIDA_SEGUNDOS + 1
    assert gb._espera_sugerida_por_gemini(Exception(f"Please retry in {excesiva}s")) is None
    print("OK: la espera sugerida distingue limite por minuto de cuota diaria")


def test_limite_por_minuto_espera_lo_que_pide_la_api_y_reintenta_igual_modelo():
    """ESTE es el bug que se arregló: antes un 429 con espera sugerida se
    abandonaba al instante y se perdía la traducción bilingüe del día
    (observado en errores_actualizacion el 2026-09-29 y 09-30, con
    contenido_bilingue vacío)."""
    dormidas, restaurar = _sin_dormir_de_verdad()
    try:
        class _Cli:
            def __init__(self):
                self.modelos_usados = []
                self.models = self

            def generate_content(self, model, contents):
                self.modelos_usados.append(model)
                if len(self.modelos_usados) == 1:
                    raise _ErrorApiFalso(429, MENSAJE_LIMITE_POR_MINUTO)
                return type("R", (), {"text": "traducción que antes se perdía"})()

        cli = _Cli()
        salida = _generar_contenido_brief(cli, "prompt")
        assert salida == "traducción que antes se perdía", salida
        # esperó lo que pidió la API (40.39s) más el margen de 1s
        assert len(dormidas) == 1 and 41 <= dormidas[0] <= 42, dormidas
        # y reintentó con el MISMO modelo, sin saltar al de respaldo
        assert cli.modelos_usados == [gb.MODELO_GEMINI, gb.MODELO_GEMINI], cli.modelos_usados
    finally:
        restaurar()
    print("OK: el limite por minuto se espera y se reintenta con el mismo modelo")


def test_cuota_diaria_sigue_sin_reintentarse():
    """El arreglo no debe volver reintentable la cuota diaria: ahí esperar
    solo quema el tiempo del cron, porque no se despeja hoy."""
    dormidas, restaurar = _sin_dormir_de_verdad()
    try:
        class _Cli:
            models = property(lambda self: self)

            def generate_content(self, model, contents):
                raise _ErrorApiFalso(429, MENSAJE_CUOTA_DIARIA)

        try:
            _generar_contenido_brief(_Cli(), "prompt")
            assert False, "la cuota diaria deberia relanzarse"
        except _ErrorApiFalso as e:
            assert e.code == 429
        assert dormidas == [], f"no deberia haber dormido por cuota diaria: {dormidas}"
    finally:
        restaurar()
    print("OK: la cuota diaria se relanza sin esperar")


def test_si_el_modelo_sigue_limitado_pasa_al_siguiente():
    """El cupo por minuto es POR MODELO (el propio error dice
    "limit: 5, model: gemini-3.6-flash"), así que agotadas las esperas
    conviene probar el siguiente, que trae su propio cupo."""
    dormidas, restaurar = _sin_dormir_de_verdad()
    try:
        class _Cli:
            def __init__(self):
                self.modelos_usados = []
                self.models = self

            def generate_content(self, model, contents):
                self.modelos_usados.append(model)
                if model == gb.MODELO_GEMINI:
                    raise _ErrorApiFalso(429, MENSAJE_LIMITE_POR_MINUTO)
                return type("R", (), {"text": "respondió el modelo de respaldo"})()

        cli = _Cli()
        salida = _generar_contenido_brief(cli, "prompt")
        assert salida == "respondió el modelo de respaldo", salida
        # el principal se intentó 1 + MAX_ESPERAS veces y después se cambió
        esperados_principal = 1 + gb.MAX_ESPERAS_POR_LIMITE_DE_TASA
        assert cli.modelos_usados[:esperados_principal] == [gb.MODELO_GEMINI] * esperados_principal
        assert cli.modelos_usados[esperados_principal] == gb.MODELOS_GEMINI_FALLBACK[0]
        assert len(dormidas) == gb.MAX_ESPERAS_POR_LIMITE_DE_TASA, dormidas
    finally:
        restaurar()
    print("OK: agotadas las esperas, pasa al siguiente modelo")


def test_el_tiempo_total_dormido_nunca_supera_el_presupuesto():
    """Techo duro: el paso "brief" tiene un watchdog de pared, así que honrar
    la espera de la API no puede volverse ilimitado aunque los tres modelos
    estén limitados a la vez."""
    dormidas, restaurar = _sin_dormir_de_verdad()
    try:
        class _Cli:
            models = property(lambda self: self)

            def generate_content(self, model, contents):
                # el tope de espera, para forzar el peor caso
                raise _ErrorApiFalso(
                    429, f"Please retry in {gb.TOPE_ESPERA_SUGERIDA_SEGUNDOS}s"
                )

        try:
            _generar_contenido_brief(_Cli(), "prompt")
            assert False, "deberia terminar relanzando"
        except _ErrorApiFalso:
            pass
        total = sum(dormidas)
        margen = len(dormidas)  # el +1s de margen por espera
        assert total - margen <= gb.PRESUPUESTO_TOTAL_ESPERAS_SEGUNDOS, (
            f"durmió {total - margen}s, por encima del presupuesto de "
            f"{gb.PRESUPUESTO_TOTAL_ESPERAS_SEGUNDOS}s"
        )
    finally:
        restaurar()
    print(f"OK: el total dormido respeta el presupuesto ({sum(dormidas):.0f}s)")


def test_el_watchdog_del_paso_brief_deja_lugar_a_las_esperas():
    """Si alguien baja el límite del paso sin mirar esto, el watchdog mataría
    el brief justo cuando estaba por tener éxito tras esperar lo que pidió la
    API. El paso hace 2 llamadas (brief + traducción)."""
    from scripts.actualizar_todo import LIMITE_SEGUNDOS_POR_FUENTE

    limite = LIMITE_SEGUNDOS_POR_FUENTE["brief"]
    peor_caso_esperando = 2 * gb.PRESUPUESTO_TOTAL_ESPERAS_SEGUNDOS
    assert limite > peor_caso_esperando, (
        f"el watchdog del paso 'brief' es {limite}s pero solo esperando por límite de "
        f"tasa se pueden ir {peor_caso_esperando}s, sin contar el trabajo real"
    )
    print(f"OK: watchdog {limite}s > peor caso de espera {peor_caso_esperando}s")


if __name__ == "__main__":
    test_clasificacion_por_tipo_de_error()
    test_texto_de_respuesta_bloqueada_lanza_briefbloqueado()
    test_reintenta_solo_transitorios()
    test_prueba_modelos_de_respaldo_si_el_principal_agota_reintentos()
    test_registrar_error_persiste_fila_en_la_bd()
    test_espera_sugerida_solo_cuando_la_api_la_indica()
    test_limite_por_minuto_espera_lo_que_pide_la_api_y_reintenta_igual_modelo()
    test_cuota_diaria_sigue_sin_reintentarse()
    test_si_el_modelo_sigue_limitado_pasa_al_siguiente()
    test_el_tiempo_total_dormido_nunca_supera_el_presupuesto()
    test_el_watchdog_del_paso_brief_deja_lugar_a_las_esperas()
    print("OK: las once pruebas pasaron.")
