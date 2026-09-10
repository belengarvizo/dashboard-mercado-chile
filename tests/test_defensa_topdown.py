"""Verificación del módulo "Defensa Top-Down" (Simulación Mesa de Dinero):

  - verificar_prediccion (defensa_topdown.py): función pura. Se prueba con el
    precio SIMULADO de la fecha objetivo (no un precio "en vivo") y el
    veredicto de CALIBRACIÓN: acierto (±3 pp) / mal_calibrado (dirección ok,
    magnitud lejos) / fallo (dirección equivocada) / pendiente / sin_datos.
  - Las 16 preguntas renderizadas coinciden EXACTO con el enunciado de la
    Tarea de Inversiones (AppTest sobre app/dashboard.py, datos reales).
  - El comparador de decisión muestra 2 tickers de prueba sin mezclar datos.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from defensa_topdown import verificar_prediccion, TOLERANCIA_PP

HOY = pd.Timestamp("2026-09-09")


def _pred(**kw):
    base = {"fecha_hecha": "2026-08-01", "horizonte_dias": 21, "tipo": "pct",
            "valor_objetivo": 5.0, "precio_base": 100.0}
    base.update(kw)
    return base


def test_prediccion_pendiente():
    r = verificar_prediccion(_pred(fecha_hecha="2026-09-05"), 130.0, hoy=HOY)
    assert r["estado"] == "pendiente"


def test_acierto_dentro_de_tolerancia():
    # predijo +5 %, real +6 % -> dif +1 pp, dentro de ±3 pp
    r = verificar_prediccion(_pred(), 106.0, hoy=HOY)
    assert r["estado"] == "acierto"
    assert abs(r["error_pp"] - 1.0) < 1e-6
    assert "dif +1.0 pp" in r["detalle"]
    # también cuenta si se quedó corto (real +3 % vs +5 %)
    assert verificar_prediccion(_pred(), 103.0, hoy=HOY)["estado"] == "acierto"
    # predicción a la baja bien calibrada
    assert verificar_prediccion(_pred(valor_objetivo=-5.0), 94.0, hoy=HOY)["estado"] == "acierto"


def test_mal_calibrado_direccion_ok_magnitud_lejos():
    # el caso que el usuario marcó: predijo +2 %, resultado real +40 % -> NO es
    # un check verde limpio, es "dirección correcta, mal calibrado" (amarillo)
    r = verificar_prediccion(_pred(valor_objetivo=2.0), 140.0, hoy=HOY)
    assert r["estado"] == "mal_calibrado"
    assert abs(r["error_pp"] - 38.0) < 1e-6
    assert "mal calibrada" in r["detalle"]
    # target price con la misma característica
    r2 = verificar_prediccion(_pred(tipo="target", valor_objetivo=120.0), 150.0, hoy=HOY)
    assert r2["estado"] == "mal_calibrado"  # implícito +20 %, real +50 %


def test_fallo_solo_si_la_direccion_es_la_contraria():
    assert verificar_prediccion(_pred(), 97.0, hoy=HOY)["estado"] == "fallo"          # predijo +5 %, cayó
    assert verificar_prediccion(_pred(valor_objetivo=-5.0), 102.0, hoy=HOY)["estado"] == "fallo"  # predijo baja, subió


def test_prediccion_sin_datos():
    assert verificar_prediccion(_pred(), None, hoy=HOY)["estado"] == "sin_datos"
    assert verificar_prediccion(_pred(precio_base=None), 110.0, hoy=HOY)["estado"] == "sin_datos"
    assert verificar_prediccion(_pred(tipo="target", precio_base=None), 130.0, hoy=HOY)["estado"] == "sin_datos"


# Texto EXACTO de las 16 preguntas, tal como aparecen en
# Tarea_Inversiones_TopDown (FEN U. de Chile). Si el PDF cambia, este test
# debe fallar hasta que se re-transcriba.
ESCENARIOS_PDF = {
    1: "Desde IFMO y el calendario ECO se constata que el output gap mundial ha pasado de −0,5 % a +1,5 % en solo dos trimestres.",
    2: "La curva de rendimientos del mercado donde opera tu empresa (consulta BTMM para la moneda relevante) se invierte −40 pb en el tramo 2–10 años.",
    3: "Los pronósticos ECFC muestran un alza de +80 pb en la inflación 12 m para EE.UU. y la Eurozona.",
    4: "El mercado de futuros de Fed Funds (FF1 Comdty) y la función WIRP descuentan +75 pb de subidas en los próximos 6 meses.",
    5: "El indicador líder de actividad relevante para tu sector (PMI manufacturero, servicios, u otro según IMAP) sube 7 puntos, alcanzando máximos de 3 años.",
    6: "Identificas que el sector de tu empresa muestra salidas netas significativas (USD 2 bn en la última semana), mientras sectores defensivos reciben entradas.",
    7: "El índice de condiciones financieras (BFCIUS Index o buscar “Financial Conditions” en tu región) se deteriora a niveles típicos previos a compresión de múltiplos.",
    8: "El spread de crédito de bonos comparables al rating de tu empresa (consulta CRPR para el rating y BI CREDIT para spreads del sector) se amplía +120 pb en solo una semana.",
    9: "Tu empresa cotiza a P/E 14× vs. 11× su sector (ver RV); los analistas (ANR) revisan EPS +12 %.",
    10: "La función SPLC de tu empresa muestra que el 30 % del coste de insumos proviene de un país en tensión geopolítica.",
    11: "Moody’s coloca la deuda de tu empresa en review for downgrade.",
    12: "Un alza de 50 pb en la tasa libre de riesgo eleva el WACC de tu empresa al 10 %.",
    13: "El precio rompe la media móvil de 200 días y sube +8 %.",
    14: "Las Bandas de Bollinger se estrechan al mínimo de 12 meses.",
    15: "La volatilidad implícita ATM a 3 meses de tu empresa (consulta OMON — Option Monitor) sube de 22 % a 35 % en 48 h.",
    16: "El interés corto (SI) de tu empresa está en máximo de 3 años, con un short interest ratio elevado.",
}


def test_16_preguntas_exactas_del_pdf():
    from market_data import INDICADORES_PREMERCADO  # noqa: F401 (fuerza sys.path del repo)
    import importlib.util
    ruta = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
    spec = importlib.util.spec_from_file_location("_dash_defensa", ruta)
    # No ejecutamos dashboard.py entero (levanta Streamlit); leemos el AST del
    # constante en su lugar.
    fuente = open(ruta, encoding="utf-8").read()
    ns: dict = {}
    inicio = fuente.index("PREGUNTAS_DEFENSA_TOPDOWN = [")
    fin = fuente.index("\n]\n", inicio) + 3
    exec(fuente[inicio:fin], ns)
    preguntas = {p["n"]: p for p in ns["PREGUNTAS_DEFENSA_TOPDOWN"]}

    assert len(preguntas) == 16, f"esperaba 16 preguntas, hay {len(preguntas)}"
    capas = {1: "MACRO", 5: "SECTORIAL", 9: "FUNDAMENTAL", 13: "TÉCNICO"}
    for n, p in sorted(preguntas.items()):
        esperado_capa = capas[((n - 1) // 4) * 4 + 1]
        assert p["capa"] == esperado_capa, f"pregunta {n}: capa {p['capa']} != {esperado_capa}"
        assert p["escenario"] == ESCENARIOS_PDF[n], (
            f"pregunta {n}: el escenario NO coincide con el PDF.\n"
            f"  módulo: {p['escenario']!r}\n  PDF:    {ESCENARIOS_PDF[n]!r}"
        )
        assert len(p["partes"]) == 2 and p["partes"][0].startswith("(a)") and p["partes"][1].startswith("(b)")

    # Chequeo adicional contra el PDF real del repo (docs/Tarea_Inversiones_
    # TopDown.pdf), si hay una librería para leerlo. No es una dependencia dura
    # del proyecto: si falta, este cross-check se salta y el resto del test
    # (constante del módulo vs. ESCENARIOS_PDF) igual corre.
    pdf_path = os.path.join(os.path.dirname(__file__), "..", "docs", "Tarea_Inversiones_TopDown.pdf")
    try:
        import pymupdf  # type: ignore
    except Exception:
        print("  (cross-check con el PDF: se salta, no hay pymupdf)")
        return
    if not os.path.exists(pdf_path):
        print("  (cross-check con el PDF: se salta, falta docs/Tarea_Inversiones_TopDown.pdf)")
        return
    import unicodedata

    def _norm(s: str) -> str:
        # El PDF es LaTeX: al extraer texto, "ñ" sale como "n" + tilde
        # (modificador U+02DC), "í" como i-sin-punto, y a veces dos palabras
        # quedan pegadas o partidas en un salto de línea ("El índice" ->
        # "elindice"). Para el cross-check de PROVENIENCIA se comparan las
        # cadenas sin acentos y SIN espacios, así esos artefactos de
        # extracción no disparan un falso negativo. La comparación ESTRICTA
        # byte-a-byte ya la hace el assert de arriba (constante del módulo
        # vs. ESCENARIOS_PDF).
        for mod in "˜´`ˆˇ¨":
            s = s.replace(mod, "")
        s = s.replace("ı", "i").replace("İ", "i")
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c) and not c.isspace())
        return s.lower()

    doc = pymupdf.open(pdf_path)
    texto_pdf = _norm(" ".join(page.get_text() for page in doc))
    for n, esc in ESCENARIOS_PDF.items():
        assert _norm(esc) in texto_pdf, f"pregunta {n}: el escenario NO aparece en el PDF del repo"


def test_render_y_comparador_apptest():
    from streamlit.testing.v1 import AppTest

    dash = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
    at = AppTest.from_file(dash, default_timeout=600)
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]

    textos = "\n".join(str(m.value) for m in at.markdown)
    for n, esc in ESCENARIOS_PDF.items():
        assert esc in textos, f"falta el escenario EXACTO de la pregunta {n} en el render"

    subs = [s.value for s in at.subheader]
    assert any("Defensa Top-Down" in s for s in subs)
    assert any("Comparador de decisión" in s for s in subs)

    # comparador: dos tickers de prueba, sus columnas no deben mezclar datos
    cmp_inputs = [w for w in at.text_input if (w.label or "").startswith("Candidato")]
    assert len(cmp_inputs) == 3
    cmp_inputs[0].set_value("AAPL")
    cmp_inputs[1].set_value("MSFT")
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]
    render2 = "\n".join(str(m.value) for m in at.markdown)
    assert "### AAPL" in render2 and "### MSFT" in render2


if __name__ == "__main__":
    test_prediccion_pendiente()
    test_acierto_dentro_de_tolerancia()
    test_mal_calibrado_direccion_ok_magnitud_lejos()
    test_fallo_solo_si_la_direccion_es_la_contraria()
    test_prediccion_sin_datos()
    test_16_preguntas_exactas_del_pdf()
    test_render_y_comparador_apptest()
    print("OK: defensa top-down — todas las pruebas pasaron.")
