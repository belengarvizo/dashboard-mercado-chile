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
    # La pestaña ahora pide contraseña. Estas pruebas son del CONTENIDO, no
    # de la puerta: se desbloquea por session_state para no depender de una
    # variable de entorno. La puerta tiene sus propias pruebas en
    # tests/test_trading_acceso.py.
    at.session_state["trd_desbloqueado"] = True
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


def test_el_riesgo_agrupado_aparece_junto_al_riesgo_total():
    """El control de arriba suma el riesgo por instrumento y no ve que dos
    posiciones correlacionadas son la misma apuesta. El bloque nuevo va
    pegado a ese control, no en otra pestaña."""
    texto = _todo_el_texto(_correr())
    assert "Correlación y riesgo agrupado" in texto
    assert "la misma apuesta puesta dos veces" in texto
    i_reglas = texto.index("Control de reglas del torneo")
    i_corr = texto.index("Correlación y riesgo agrupado")
    assert i_reglas < i_corr, "el riesgo agrupado quedó lejos del panel de riesgo"


def test_el_umbral_y_los_topes_son_editables():
    """La usuaria pidió poder moverlos. Si fueran constantes del código,
    cambiarlos exigiría un deploy."""
    at = _correr()
    claves = {w.key for w in list(at.slider) + list(at.number_input)}
    for clave in ("trd_corr_umbral", "trd_corr_tope_grupo", "trd_corr_tope_dir"):
        assert clave in claves, f"falta el control editable {clave!r}"


def test_el_bloque_de_correlacion_avisa_y_no_bloquea():
    """Igual que el resto de la pestaña: es un espejo. Ningún tope puede
    impedir registrar ni cerrar una operación."""
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        codigo = f.read()
    inicio = codigo.index("def _trd_riesgo_agrupado(")
    bloque = codigo[inicio:codigo.index("\ndef ", inicio + 10)]
    for prohibido in ("st.stop()", "raise ", "return False", "disabled=True"):
        assert prohibido not in bloque, (
            f"el bloque de correlación contiene {prohibido!r}: tiene que avisar, "
            f"no bloquear")


def test_la_matriz_declara_lo_que_no_sabe():
    """O dice por qué el índice dólar queda fuera, o dice que todavía no hay
    precios guardados. Lo que no puede hacer es mostrar un número sin
    advertencia."""
    texto = _todo_el_texto(_correr())
    assert ("USDIDX) no está en la matriz" in texto
            or "Todavía no hay precios de los pares" in texto
            or "no hay suficientes cierres guardados" in texto), texto[-1200:]


def test_el_riesgo_agrupado_con_posiciones_abiertas_simuladas(monkeypatch):
    """El camino que el diario real todavía no puede mostrar: está en cero.

    Cuatro posiciones inventadas, con precios inventados de correlación fija,
    entregadas interceptando pandas.read_sql. No se escribe ni se consulta la
    base para estas tablas.

    Lo que tiene que salir, y es todo aritmética verificable a mano:
      EURUSD compra 150.000
      GBPUSD compra 120.000  correlación +1 con EURUSD, mismo sentido -> SUMA
      USDCHF compra  40.000  correlación -1 con EURUSD, mismo sentido -> COMPENSA
      riesgo agrupado = raíz(r' C r) = 230.000

    Con correlaciones de exactamente +-1 la fórmula coincide con sumar y
    restar los montos, que es el caso límite: 150.000 + 120.000 - 40.000.
      USDJPY venta   90.000  sin correlación -> queda sola
      riesgo total abierto = 400.000
    """
    import pandas as pd

    import datos_simulados_divisas as sim

    monkeypatch.setattr(pd, "read_sql", sim.interceptar(pd))
    texto = _todo_el_texto(at := _correr())

    metricas = {m.label: m.value for m in at.metric}
    assert metricas.get("Riesgo total abierto") == "400,000 CLP", metricas
    assert metricas.get("Riesgo agrupado estimado") == "230,000 CLP", metricas
    assert metricas.get("Compras / ventas") == "310,000 / 90,000", metricas

    assert "Estas posiciones se comportan como una sola apuesta" in texto
    assert "EURUSD compra 150,000 CLP" in texto, texto[-1500:]
    assert "GBPUSD compra 120,000 CLP" in texto
    assert "USDCHF compra 40,000 CLP" in texto
    # Cada pareja explica su propio signo; no hay posición de referencia.
    assert "referencia" not in texto
    assert "EURUSD \u2194 GBPUSD" in texto and "suman" in texto
    assert "EURUSD \u2194 USDCHF" in texto and "se compensan" in texto
    # Y queda dicho que es una estimación, no una medición.
    assert "Estimado con la correlaci\u00f3n de los \u00faltimos 60 d\u00edas" in texto
    assert "la compensaci\u00f3n es PARCIAL" in texto
    # El que no se parece a ninguno no entra al grupo.
    assert "USDJPY venta" not in texto

    # El tope por grupo es el 2% de 9.500.000 = 190.000, y el grupo va en
    # 230.000: tiene que avisar en rojo, nombrando los tres instrumentos.
    rojos = " || ".join(str(e.value) for e in at.error)
    assert "230,000 CLP de riesgo agrupado estimado" in rojos, rojos
    assert "sobre el tope de 190,000" in rojos, rojos
    assert "una sola apuesta" in rojos
    # Con el nombre del catálogo, no con el ticker de Yahoo: "EURUSD=X" es
    # ruido para quien lee la pantalla.
    assert "EURUSD, GBPUSD, USDCHF" in rojos, rojos
    assert "=X" not in rojos and "=X" not in texto, "se filtró un ticker de Yahoo"

    # Las compras van en 310.000 contra un tope de 380.000: sobre el 80%,
    # así que amarillo y no rojo.
    amarillos = " || ".join(str(e.value) for e in at.warning)
    assert "compras" in amarillos and "310,000" in amarillos, amarillos
    assert "310,000" not in rojos, "pintó de rojo algo que está bajo el tope"


def test_el_bloque_de_correlacion_va_despues_de_la_puerta():
    """Si se dibujara antes del control de contraseña, la pestaña filtraría
    qué posiciones hay abiertas."""
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        codigo = f.read()
    inicio = codigo.index("def render_divisas():")
    cuerpo = codigo[inicio:]
    assert cuerpo.index("_trd_puerta_de_acceso()") < cuerpo.index("_trd_riesgo_agrupado(")


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
