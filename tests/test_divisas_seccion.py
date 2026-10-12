"""AppTest de la sección "Divisas" (apoyo al Alpha Trading Challenge).

Lo que se fija acá no es el aspecto, son las propiedades de seguridad: que el
panel se presente como un espejo y no como un guardián, que el calculador se
niegue a calcular cuando le falta el tamaño del pip, y que el diario se
dibuje con UNA sola llamada en vez de una por fila.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

load_dotenv()

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
SECCION = "Divisas"


def _correr():
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = SECCION
    at.run(timeout=420)
    assert not at.exception, f"la sección lanzó una excepción: {at.exception}"
    return at


def _todo_el_texto(at):
    partes = []
    for attr in ("title", "subheader", "markdown", "caption", "info", "warning", "error"):
        for el in getattr(at, attr, []):
            partes.append(str(getattr(el, "value", "")))
    return " || ".join(partes)


def test_la_seccion_existe_entre_riesgo_y_benchmark():
    """El orden lo pidió la usuaria explícitamente."""
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        codigo = f.read()
    inicio = codigo.index("SECCIONES = [")
    bloque = codigo[inicio:codigo.index("]", inicio)]
    assert '"Riesgo", "Divisas", "Benchmark"' in bloque, bloque


def test_la_seccion_renderiza_sin_excepcion():
    at = _correr()
    assert any("Alpha Trading Challenge" in s.value for s in at.subheader)


def test_se_presenta_como_espejo_y_no_como_guardian():
    """La propiedad de seguridad más importante de toda la sección.

    El panel solo refleja lo que la usuaria cargó a mano. Si se leyera como
    una garantía de cumplimiento, daría una falsa tranquilidad justo en las
    reglas que descalifican — y el piso de 5.000.000 CLP lo aplica XTB en
    tiempo real, sin esperar a que nadie registre nada."""
    at = _correr()
    avisos = " ".join(str(w.value) for w in at.warning)
    assert "espejo" in avisos and "guardián" in avisos, avisos
    assert "XTB" in avisos and "tiempo real" in avisos, (
        "el aviso debe decir de quién es la regla del piso de equity")


def test_declara_que_no_opera_ni_recomienda():
    """El torneo prohíbe el software que opere solo, y la usuaria pidió que
    no hubiera recomendaciones de inversión."""
    texto = _todo_el_texto(_correr())
    assert "no se conecta a XTB" in texto.lower() or "no opera" in texto.lower(), texto[:400]
    assert "recomendaciones de inversión" in texto.lower()


def test_el_calculador_se_niega_cuando_el_pip_esta_pendiente():
    """USDCLP cotiza cerca de 975: un pip de 0,0001 sería absurdo, y errarlo
    por un factor de 100 erraría el tamaño de la posición por 100. Mientras
    el dato no esté cargado desde el ticket, no se calcula."""
    at = _correr()
    # Se cambia el widget y se vuelve a correr: fijar session_state antes del
    # primer run no alcanza, porque el selectbox trae su propio `index`.
    at.selectbox(key="trd_calc_par").set_value("USDCLP").run(timeout=420)
    assert not at.exception, at.exception

    errores = " ".join(str(e.value) for e in at.error)
    assert "No se puede calcular" in errores, errores
    assert "PENDIENTE" in errores, errores
    # y NO debe haber salido un número de lotes
    etiquetas = [m.label for m in at.metric]
    assert "Lotes" not in etiquetas, f"calculó lotes sin tener el pip: {etiquetas}"


def test_el_calculador_si_funciona_donde_el_pip_esta_cargado():
    at = _correr()
    at.selectbox(key="trd_calc_par").set_value("EURUSD").run(timeout=420)
    assert not at.exception, at.exception
    etiquetas = {m.label: m.value for m in at.metric}
    assert "Lotes" in etiquetas, etiquetas
    assert "Valor del pip (1 lote)" in etiquetas, etiquetas


def test_el_diario_no_dibuja_una_llamada_por_fila():
    """El incidente de los titulares: cada st.* es un mensaje por el
    WebSocket y la cola tiene un tope FIJO de 500. Una tabla dibujada fila
    por fila volvería a desbordarla a medida que el diario crezca."""
    at = _correr()
    # Con el diario vacío o con pocas filas, el total de bloques tiene que
    # mantenerse chico: la tabla va en un st.dataframe, no en un bucle.
    assert len(at.markdown) < 40, (
        f"{len(at.markdown)} bloques markdown: la sección parece estar dibujando "
        f"elemento por elemento en vez de usar una tabla")


def test_el_panel_muestra_los_controles_del_reglamento():
    texto = _todo_el_texto(_correr())
    for control in ["Operaciones cerradas", "menos de 2 minutos", "piso de descalificación",
                    "Margen por subyacente", "Concentración por categoría"]:
        assert control in texto, f"falta el control {control!r} en el panel"


if __name__ == "__main__":
    test_la_seccion_existe_entre_riesgo_y_benchmark()
    test_la_seccion_renderiza_sin_excepcion()
    test_se_presenta_como_espejo_y_no_como_guardian()
    test_declara_que_no_opera_ni_recomienda()
    test_el_calculador_se_niega_cuando_el_pip_esta_pendiente()
    test_el_calculador_si_funciona_donde_el_pip_esta_cargado()
    test_el_diario_no_dibuja_una_llamada_por_fila()
    test_el_panel_muestra_los_controles_del_reglamento()
    print("OK: las ocho pruebas pasaron.")
