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


if __name__ == "__main__":
    test_clasificacion_por_tipo_de_error()
    test_texto_de_respuesta_bloqueada_lanza_briefbloqueado()
    test_reintenta_solo_transitorios()
    test_registrar_error_persiste_fila_en_la_bd()
    print("OK: las cuatro pruebas pasaron.")
