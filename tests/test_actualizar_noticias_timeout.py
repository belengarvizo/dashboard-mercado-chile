"""Guarda contra la regresión que dejó el cron "Running" 7+ horas en
producción: descargar_titulares() debía ir directo a feedparser.parse(url),
que no tiene parámetro de timeout (se verificó en su firma instalada) y se
cuelga sin límite si el servidor acepta la conexión y no manda datos. Ahora
el fetch va por requests (que sí tiene timeout real y lanza una excepción
al vencer, algo que con_reintentos puede reintentar)."""
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import requests

from scripts.actualizar_noticias import descargar_titulares

_RSS_VALIDO = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>Un titular de prueba de verdad</title>
<link>https://example.com/nota</link>
<pubDate>Mon, 01 Sep 2026 12:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_descargar_titulares_pasa_timeout_explicito_a_requests():
    llamadas = []

    def _get_falso(url, headers=None, timeout=None):
        llamadas.append({"url": url, "headers": headers, "timeout": timeout})
        resp = MagicMock()
        resp.content = _RSS_VALIDO
        resp.raise_for_status = lambda: None
        return resp

    with patch("scripts.actualizar_noticias.requests.get", side_effect=_get_falso):
        titulares = descargar_titulares("https://example.com/rss.xml", horas_ventana=24 * 365 * 5)

    assert llamadas, "descargar_titulares no llamó a requests.get"
    assert llamadas[0]["timeout"] == 15, f"timeout debería ser 15, fue {llamadas[0]['timeout']}"
    assert any(t["titulo"] == "Un titular de prueba de verdad" for t in titulares)


def test_descargar_titulares_no_traga_el_timeout_de_requests():
    """Un timeout de requests debe propagarse como excepción real (para que
    con_reintentos, que solo reacciona a excepciones, pueda reintentar) -- no
    quedarse colgado ni devolver una lista vacía silenciosa."""
    def _get_falso(url, headers=None, timeout=None):
        raise requests.exceptions.Timeout("simulación: el servidor no respondió a tiempo")

    with patch("scripts.actualizar_noticias.requests.get", side_effect=_get_falso):
        try:
            descargar_titulares("https://example.com/rss.xml")
            assert False, "debería haber lanzado requests.exceptions.Timeout"
        except requests.exceptions.Timeout:
            pass


if __name__ == "__main__":
    test_descargar_titulares_pasa_timeout_explicito_a_requests()
    test_descargar_titulares_no_traga_el_timeout_de_requests()
    print("OK: las dos pruebas pasaron.")
