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


def test_modulo_gateado_por_boton():
    """El módulo pesado NO se renderiza hasta apretar "Cargar Defensa
    Top-Down" (mismo patrón lazy que el resto del dashboard): así abrir
    cualquier otra pestaña no espera a las consultas / Yahoo Finance de este
    módulo."""
    from streamlit.testing.v1 import AppTest

    dash = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
    at = AppTest.from_file(dash, default_timeout=600)
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]

    # sin apretar el botón: el subheader "7. Defensa Top-Down" y el botón de
    # carga están, pero NINGUNA de las 16 preguntas ni el comparador.
    textos0 = "\n".join(str(m.value) for m in at.markdown)
    assert not any(esc in textos0 for esc in ESCENARIOS_PDF.values()), \
        "el módulo se está renderizando sin apretar el botón (regresión de lazy-load)"
    assert not any("Comparador de decisión" in s.value for s in at.subheader)
    botones = [b for b in at.button if "Cargar Defensa Top-Down" in b.label]
    assert botones, "falta el botón 'Cargar Defensa Top-Down'"

    botones[0].click()
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]

    textos = "\n".join(str(m.value) for m in at.markdown)
    for n, esc in ESCENARIOS_PDF.items():
        assert esc in textos, f"falta el escenario EXACTO de la pregunta {n} tras cargar el módulo"
    assert any("Comparador de decisión" in s.value for s in at.subheader)

    # comparador: dos tickers de prueba, sus columnas no deben mezclar datos
    cmp_inputs = [w for w in at.text_input if (w.label or "").startswith("Candidato")]
    assert len(cmp_inputs) == 3
    cmp_inputs[0].set_value("AAPL")
    cmp_inputs[1].set_value("MSFT")
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]
    render2 = "\n".join(str(m.value) for m in at.markdown)
    assert "### AAPL" in render2 and "### MSFT" in render2

    # con el módulo cargado aparece el botón "Descargar" (punto 1): permite
    # apagarlo sin recargar la página. Al apretarlo, el módulo deja de
    # renderizarse (el costo por rerun desaparece hasta que se vuelva a cargar).
    descargar = [b for b in at.button if "Descargar Defensa Top-Down" in b.label]
    assert descargar, "falta el botón 'Descargar Defensa Top-Down' con el módulo cargado"
    descargar[0].click()
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]
    textos2 = "\n".join(str(m.value) for m in at.markdown)
    assert not any(esc in textos2 for esc in ESCENARIOS_PDF.values()), \
        "tras 'Descargar', el módulo no debería seguir renderizándose"


def _cargar_modulo(at):
    """AppTest con el módulo Defensa Top-Down ya cargado (apretando su botón)."""
    from streamlit.testing.v1 import AppTest  # noqa: F401
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]
    [b for b in at.button if "Cargar Defensa Top-Down" in b.label][0].click()
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]
    return at


def test_calculadoras_recalculan_en_vivo():
    """Las 3 calculadoras recalculan al mover un slider, sin botón de envío."""
    from streamlit.testing.v1 import AppTest

    dash = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
    at = _cargar_modulo(AppTest.from_file(dash, default_timeout=600))

    def metrica(label):
        return next(m for m in at.metric if m.label == label)

    def slider(frag):
        return next(s for s in at.slider if frag in (s.label or ""))

    # --- Calc 1: mover "Shock directo al WACC" +2 pp -> WACC sube ~2 pp ---
    wacc0 = float(metrica("WACC ponderado").value.split()[0])
    slider("Shock directo al WACC").set_value(2.0)
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]
    wacc1 = float(metrica("WACC ponderado").value.split()[0])
    assert abs((wacc1 - wacc0) - 2.0) < 0.05, f"WACC no reaccionó al slider: {wacc0} -> {wacc1}"

    # aviso cuando WACC <= g
    slider("Shock directo al WACC").set_value(-3.0)
    slider("Shock a Rf").set_value(-2.0)
    slider("Shock de ERP").set_value(-3.0)
    at.run(timeout=600)
    assert any("crecimiento perpetuo" in str(w.value) for w in at.warning), \
        "falta el aviso cuando WACC <= g"

    # --- Calc 2: PEG = P/E / crecimiento; mover el slider cambia el PEG ---
    peg0 = float(metrica("PEG resultante").value)
    slider("crecimiento de EPS").set_value(20.0)
    at.run(timeout=600)
    peg1 = float(metrica("PEG resultante").value)
    assert peg1 < peg0, f"PEG debería bajar al subir el crecimiento: {peg0} -> {peg1}"
    assert abs(peg1 - 14.0 / 20.0) < 0.02

    # --- Calc 3: sobrecosto 0 -> sin cambio; 15% -> margen baja ---
    slider("% de sobrecosto").set_value(0.0)
    at.run(timeout=600)
    m_base = float(metrica("Nuevo margen EBIT").value.split()[0])
    slider("% de sobrecosto").set_value(15.0)
    at.run(timeout=600)
    m_shock = float(metrica("Nuevo margen EBIT").value.split()[0])
    assert m_base > m_shock, f"el margen no bajó con el sobrecosto: {m_base} -> {m_shock}"
    # con margen 18, EBIT 100 -> ventas 555.6, costos 455.6, expuestos 30% = 136.7,
    # sobrecosto 15% = 20.5 -> nuevo EBIT 79.5 -> nuevo margen ~14.3%
    assert 13.5 < m_shock < 15.0, f"margen tras sobrecosto 15% fuera de rango: {m_shock}"


def test_sectoriales_y_tecnicas_sin_calculo_inventado():
    """Las preguntas 5-7 (SECTORIAL) y 13-16 (TÉCNICO) NO enlazan a ninguna
    calculadora ni muestran un cálculo — se quedan narrativas."""
    from streamlit.testing.v1 import AppTest

    dash = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
    at = _cargar_modulo(AppTest.from_file(dash, default_timeout=600))

    caps = [str(c.value) for c in at.caption]
    # ninguna caption debe enlazar preguntas sectoriales 5-7 o técnicas a una calc
    for c in caps:
        if "🧮" in c:
            assert not any(t in c for t in (
                "Pulso de actividad", "Flujos sectoriales", "Condiciones financieras",
                "Break-out", "Bollinger", "Volatilidad implícita", "Interés corto",
            )), f"una pregunta sectorial/técnica está enlazada a una calculadora: {c!r}"

    # las 8 preguntas con fórmula (2,3,4,8,9,10,11,12) sí tienen enlace 🧮
    enlaces = [c for c in caps if c.startswith("🧮")]
    assert len(enlaces) >= 8, f"esperaba >=8 enlaces a calculadoras, hay {len(enlaces)}"


_PREP_LABELS = [
    "Tiene catalizador con fecha en los próximos 6 meses",
    "FA con historial limpio (verificado en Bloomberg)",
    "Cobertura de analistas suficiente (ANR)",
    "Opciones listadas (OMON)",
    "Dato de interés corto disponible (SI)",
    "Puedo argumentar una dirección clara (largo/corto)",
]


def test_comparador_checklist_preparacion():
    """El mini-checklist de preparación: 6 ítems por candidato, recálculo en
    vivo del puntaje al hacer click (sin botón), dos candidatos se puntúan
    independiente (puntajes distintos) y NO hay ranking automático."""
    from streamlit.testing.v1 import AppTest

    dash = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
    at = _cargar_modulo(AppTest.from_file(dash, default_timeout=600))

    cmp_inputs = [w for w in at.text_input if (w.label or "").startswith("Candidato")]
    cmp_inputs[0].set_value("AAPL")
    cmp_inputs[1].set_value("MSFT")
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]

    infos = " ".join(str(i.value) for i in at.info)
    assert "no decide por ustedes" in infos, "falta el aviso arriba del widget"
    assert "no hay ranking automático" in infos, "el aviso debe dejar claro que no hay ranking"

    prep = [c for c in at.checkbox if c.label in _PREP_LABELS]
    assert len(prep) == 12, f"esperaba 6 checkboxes x 2 candidatos, hay {len(prep)}"

    def puntajes():
        return sorted(m.value for m in at.metric if m.label == "Puntaje de preparación")

    p0 = puntajes()
    assert len(p0) == 2 and all(v.endswith("/6") for v in p0)

    # marcar 3 ítems del 1er candidato y 1 del 2º -> recalcula en vivo, distintos
    for c in prep[1:4]:   # fa/anr/omon del candidato 1 (evita 'cat', que puede venir premarcado)
        c.check()
    prep[7].check()       # fa del candidato 2
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]
    p1 = puntajes()
    assert p1 != p0, "el puntaje no recalculó al hacer click"
    assert p1[0] != p1[1], f"los dos candidatos deberían puntuar distinto: {p1}"

    # marcar el ítem de dirección (re-consultando los widgets tras el rerun)
    # abre el campo de texto "¿por qué?"
    dir_cbs = [c for c in at.checkbox
               if c.label == "Puedo argumentar una dirección clara (largo/corto)"]
    dir_cbs[0].check()
    at.run(timeout=600)
    assert not at.exception, [str(e) for e in at.exception]
    assert any((w.label or "").startswith("¿Por qué?") for w in at.text_input), \
        "marcar 'dirección clara' debe abrir el campo ¿por qué?"


if __name__ == "__main__":
    test_prediccion_pendiente()
    test_acierto_dentro_de_tolerancia()
    test_mal_calibrado_direccion_ok_magnitud_lejos()
    test_fallo_solo_si_la_direccion_es_la_contraria()
    test_prediccion_sin_datos()
    test_16_preguntas_exactas_del_pdf()
    test_modulo_gateado_por_boton()
    test_calculadoras_recalculan_en_vivo()
    test_sectoriales_y_tecnicas_sin_calculo_inventado()
    test_comparador_checklist_preparacion()
    print("OK: defensa top-down — todas las pruebas pasaron.")
