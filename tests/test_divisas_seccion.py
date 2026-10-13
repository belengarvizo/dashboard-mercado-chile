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


def _correr(**estado):
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=420)
    at.session_state["seccion_activa"] = SECCION
    for clave, valor in estado.items():
        at.session_state[clave] = valor
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


def test_el_limite_por_operacion_avisa_cuando_te_pasas():
    """Sin equity registrado la base es el capital inicial de 10.000.000. Al
    5% el riesgo son 500.000 contra un límite de 200.000: rojo."""
    at = _correr()
    at.number_input(key="trd_calc_pct").set_value(5.0).run(timeout=420)
    assert not at.exception, at.exception
    texto = _todo_el_texto(at)
    assert "Riesgo de esta operación" in texto
    assert "🔴" in texto, "debería estar en rojo"
    # En pesos y en porcentaje del capital, como se pidió.
    assert "500,000 CLP" in texto and "5.00%" in texto, texto[-1200:]
    assert "10,000,000" in texto
    # Y cuántas operaciones así llegan al piso: 5.000.000 / 500.000 = 10.
    assert "10 operaciones así seguidas" in texto, texto[-1200:]
    assert "5,000,000" in texto
    # No es una regla del torneo y tiene que decirlo.
    assert "no del reglamento del torneo" in texto


def test_el_limite_por_operacion_esta_en_verde_con_el_riesgo_por_defecto():
    """Al 1% son 100.000 contra un límite de 200.000."""
    texto = _todo_el_texto(_correr())
    assert "Riesgo de esta operación" in texto
    assert "100,000 CLP" in texto and "1.00%" in texto


def test_el_limite_por_operacion_es_editable():
    """Si fuera una constante del código, cambiarlo exigiría un deploy."""
    at = _correr()
    claves = {w.key for w in at.number_input}
    assert "trd_tope_operacion_pct" in claves, claves
    # El mismo 1% de riesgo, con el límite bajado a 0,5%: pasa a rojo.
    at.number_input(key="trd_tope_operacion_pct").set_value(0.5).run(timeout=420)
    assert not at.exception, at.exception
    texto = _todo_el_texto(at)
    assert "🔴" in texto, "con el límite en 0,5% debería avisar"
    assert "50,000" in texto, texto[-900:]


def test_avisa_si_la_operacion_que_registraste_supera_el_limite():
    """El formulario deja el aviso en session_state antes del rerun, porque
    el rerun borra todo lo que se dibuje ahí. Acá se inyecta ese mismo
    estado: la prueba NO escribe en la base."""
    from decimal import Decimal

    at = _correr(trd_aviso_riesgo_guardado=(Decimal("500000"), "EURUSD"))
    texto = _todo_el_texto(at)
    assert "acabas de registrar en EURUSD" in texto, texto[-1200:]
    assert "supera" in texto
    assert "500,000 CLP" in texto
    assert "10 operaciones así seguidas" in texto


def test_el_aviso_de_la_operacion_registrada_no_se_repite():
    """Se consume con pop: si quedara en la sesión, reaparecería en cada
    rerun aunque ya no corresponda."""
    from decimal import Decimal

    at = _correr(trd_aviso_riesgo_guardado=(Decimal("500000"), "EURUSD"))
    assert "acabas de registrar" in _todo_el_texto(at)
    at.number_input(key="trd_calc_stop").set_value(40.0).run(timeout=420)
    assert "acabas de registrar" not in _todo_el_texto(at)


def test_el_limite_por_operacion_no_bloquea_nada():
    """La lógica vive en trading_reglas.py, que es un módulo puro: ni
    siquiera importa Streamlit, así que no tiene forma de impedir nada."""
    ruta_reglas = os.path.join(os.path.dirname(__file__), "..", "trading_reglas.py")
    with open(ruta_reglas, encoding="utf-8") as f:
        reglas = f.read()
    assert "import streamlit" not in reglas
    bloque = reglas[reglas.index("def riesgo_por_operacion("):
                    reglas.index("\ndef stops_hasta_el_piso(")]
    for prohibido in ("st.stop()", "raise ", "return False", "disabled=True"):
        assert prohibido not in bloque, (
            f"el chequeo de riesgo por operación contiene {prohibido!r}: avisa, no bloquea")


def test_el_atr_aparece_en_el_calculador():
    """EURUSD tiene un ano de ruedas guardadas, asi que sale con numero."""
    at = _correr()
    texto = _todo_el_texto(at)
    assert "ATR de Wilder (14)" in texto
    # La PRINCIPAL es la del rango del día; el rango verdadero va al lado.
    etiquetas = {m.label for m in at.metric}
    assert "ATR del rango del día (14)" in etiquetas, etiquetas
    assert "Rango verdadero:" in texto, texto[-1500:]
    assert "último dato del par" in texto, texto[-1500:]
    assert "Stop sugerido" in texto
    # La nota que pidió la usuaria, con esas palabras.
    assert ("rango verdadero incluye saltos entre cierres" in texto
            and "desfase de datos de Yahoo" in texto)
    assert "la cifra principal es la del rango del día" in texto
    # Es para dimensionar, no una señal.
    assert "No cambia el campo" in texto


def test_el_multiplo_del_stop_es_editable():
    at = _correr()
    claves = {w.key for w in at.number_input}
    assert "trd_atr_multiplo" in claves, claves
    at.number_input(key="trd_atr_multiplo").set_value(2.0).run(timeout=420)
    assert not at.exception, at.exception
    assert "2.0 × ATR" in _todo_el_texto(at)


def test_el_atr_no_sobrescribe_el_stop_que_escribo():
    """El campo 'Distancia al stop' tiene que seguir en lo que yo puse,
    aunque el stop sugerido sea otro número."""
    at = _correr()
    at.number_input(key="trd_calc_stop").set_value(17.0).run(timeout=420)
    assert not at.exception, at.exception
    assert at.number_input(key="trd_calc_stop").value == 17.0
    at.number_input(key="trd_atr_multiplo").set_value(3.0).run(timeout=420)
    assert at.number_input(key="trd_calc_stop").value == 17.0, (
        "el stop sugerido pisó el stop escrito a mano")


def test_un_par_sin_pip_muestra_precio_y_porcentaje_pero_no_pips():
    """USDCLP, USDBRL, USDIDX y USDMXN no tienen tamaño de pip en el
    catálogo. No se inventa el divisor."""
    at = _correr()
    at.selectbox(key="trd_calc_par").set_value("USDCLP").run(timeout=420)
    assert not at.exception, at.exception
    texto = _todo_el_texto(at)
    assert "ATR de Wilder (14)" in texto
    assert "falta tamaño del pip en el catálogo" in texto, texto[-1500:]
    # El precio y el porcentaje SÍ están: lo único que falta son los pips.
    assert "Sobre el precio" in texto, texto[-1500:]
    assert "En precio:" in texto
    valores = {m.label: m.value for m in at.metric}
    principal = valores.get("ATR del rango del día (14)", "")
    assert principal and "pips" not in principal, (
        f"mostró pips para un par sin tamaño de pip: {principal!r}")


def test_avisa_si_el_stop_de_una_posicion_abierta_esta_a_menos_de_un_ATR(monkeypatch):
    """Posiciones simuladas con ATR REAL de la base.

    EURUSD lleva el stop a 0,0030 de la entrada; con un ATR de ~0,0065 son
    ~0,46 ATR y avisa. GBPUSD lo lleva a 0,0350, que son ~5 ATR, y no avisa.
    La prueba no escribe en la base: solo intercepta las lecturas del diario.
    """
    import pandas as pd

    import datos_simulados_divisas as sim

    monkeypatch.setattr(pd, "read_sql", sim.interceptar(pd))
    texto = _todo_el_texto(_correr())
    assert "Stop dentro del movimiento normal del par" in texto, texto[-1800:]
    assert "EURUSD" in texto
    assert "ATR** (rango del día) de la entrada" in texto, texto[-1800:]
    # El de GBPUSD está lejos: no debe aparecer en ESE aviso.
    bloque = texto[texto.index("Stop dentro del movimiento normal"):]
    bloque = bloque[:bloque.index("||")] if "||" in bloque else bloque
    assert "GBPUSD" not in bloque, bloque
    # Y queda claro que no hace nada por su cuenta.
    assert "no cierra ni modifica nada" in texto


def test_el_aviso_de_stop_cerca_no_bloquea_nada():
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        codigo = f.read()
    inicio = codigo.index("def _trd_stops_cerca_del_atr(")
    bloque = codigo[inicio:codigo.index("\ndef _trd_aviso_antimartingala(")]
    for prohibido in ("st.stop()", "raise ", "return False", "disabled=True",
                      "UPDATE", "DELETE"):
        assert prohibido not in bloque, (
            f"el aviso de stop cerca contiene {prohibido!r}: avisa, no actúa")


def test_el_bloque_del_atr_no_da_senales_ni_bloquea():
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        codigo = f.read()
    inicio = codigo.index("def _trd_bloque_atr(")
    bloque = codigo[inicio:codigo.index("\ndef _trd_stops_cerca_del_atr(")]
    for prohibido in ("st.stop()", "raise ", "return False", "disabled=True"):
        assert prohibido not in bloque, f"el bloque del ATR contiene {prohibido!r}"
    # Buscar las palabras "comprar" o "vender" no sirve: el propio descargo
    # del bloque dice que NO dice si comprar o vender. Lo que se comprueba es
    # que ese descargo esté, y que el texto no recomiende una dirección.
    assert "no dice si comprar o vender" in bloque
    assert "dimensionar el stop" in bloque.lower()
    for recomendacion in ("deberías comprar", "deberías vender", "conviene comprar",
                          "conviene vender", "señal de compra", "señal de venta"):
        assert recomendacion not in bloque.lower(), (
            f"el bloque del ATR recomienda una dirección: {recomendacion!r}")


def test_la_tabla_de_recuperacion_aparece_en_el_calculador():
    """Sin equity registrado la base es el capital inicial de 10.000.000, y
    el riesgo por defecto es 1%: 100.000 CLP, que exigen ganar 1,01%."""
    texto = _todo_el_texto(_correr())
    assert "Si esta operación sale mal" in texto
    assert "100,000 CLP" in texto and "1.01%" in texto, texto[-1500:]
    assert "9,900,000" in texto, "falta el capital que queda"
    # Las dos rachas, con sus porcentajes compuestos.
    assert "3 pérdidas seguidas" in texto and "3.06%" in texto
    assert "5 pérdidas seguidas" in texto and "5.15%" in texto
    # Las dos referencias que fijan la fórmula.
    assert "20% exige ganar un 25%" in texto
    assert "50% exige ganar un 100%" in texto


def test_la_tabla_de_recuperacion_sigue_al_riesgo_que_elijas():
    """Si no se moviera con el porcentaje, sería un adorno."""
    at = _correr()
    at.number_input(key="trd_calc_pct").set_value(2.0).run(timeout=420)
    assert not at.exception, at.exception
    texto = _todo_el_texto(at)
    assert "200,000 CLP" in texto and "2.04%" in texto, texto[-1500:]
    # 5 pérdidas seguidas al 2% componen a 9,61%, no a 10%.
    assert "9.61%" in texto and "10.63%" in texto


def test_la_tabla_de_recuperacion_es_una_referencia_y_no_un_bloqueo():
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        codigo = f.read()
    inicio = codigo.index("def _trd_tabla_recuperacion(")
    bloque = codigo[inicio:codigo.index("\ndef ", inicio + 10)]
    for prohibido in ("st.stop()", "raise ", "return False", "disabled=True"):
        assert prohibido not in bloque, (
            f"la tabla de recuperación contiene {prohibido!r}: es una referencia, "
            f"no un bloqueo")
    texto = _todo_el_texto(_correr())
    assert "es una referencia para dimensionar, no una señal" in texto.lower()


def test_avisa_si_subes_el_tamano_despues_de_perder(monkeypatch):
    """El diario real está en cero, así que el escenario va simulado: UNA
    operación cerrada con pérdida que arriesgó 50.000, contra el 1% por
    defecto del calculador sobre el capital inicial, que son 100.000."""
    import pandas as pd

    import datos_simulados_divisas as sim

    monkeypatch.setattr(pd, "read_sql", sim.interceptar_una_cerrada(pd, -50000.0))
    at = _correr()
    avisos = " || ".join(str(w.value) for w in at.warning)
    assert "subiendo el tamaño después de perder" in avisos, avisos[:600]
    assert "50,000" in avisos and "100,000" in avisos
    assert "100% más" in avisos, avisos[:600]
    # El texto dice POR QUÉ importa, no solo que pasó.
    assert "destruye una cuenta" in avisos
    # Y deja claro que no bloquea.
    assert "Es un aviso, no un bloqueo" in avisos


def test_no_avisa_si_la_operacion_anterior_gano(monkeypatch):
    """Subir el tamaño después de ganar es lo contrario del patrón."""
    import pandas as pd

    import datos_simulados_divisas as sim

    monkeypatch.setattr(pd, "read_sql", sim.interceptar_una_cerrada(pd, 40000.0))
    at = _correr()
    avisos = " || ".join(str(w.value) for w in at.warning)
    assert "subiendo el tamaño" not in avisos, avisos[:600]


def test_el_aviso_de_antimartingala_no_bloquea_nada():
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        codigo = f.read()
    inicio = codigo.index("def _trd_aviso_antimartingala(")
    bloque = codigo[inicio:codigo.index("\ndef ", inicio + 10)]
    for prohibido in ("st.stop()", "raise ", "return False", "disabled=True"):
        assert prohibido not in bloque, (
            f"el aviso de antimartingala contiene {prohibido!r}: avisa, no bloquea")


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
    # Se mira SOLO el bloque del grupo: buscar la palabra en toda la página
    # la confunde con otros textos que la usan en su sentido corriente, como
    # la tabla de recuperación ("es una referencia para dimensionar").
    bloque = next(str(m.value) for m in at.markdown
                  if "se comportan como una sola apuesta" in str(m.value))
    assert "referencia" not in bloque, bloque
    assert "EURUSD ↔ GBPUSD" in bloque and "suman" in bloque
    assert "EURUSD ↔ USDCHF" in bloque and "se compensan" in bloque
    # Y queda dicho que es una estimación, no una medición.
    assert "Estimado con la correlación de los últimos 60 días" in texto
    assert "la compensación es PARCIAL" in texto
    # El que no se parece a ninguno no entra al grupo. También acotado al
    # bloque: el nombre del par aparece en otras partes de la pantalla.
    assert "USDJPY" not in bloque, bloque

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

    # El tope por dirección es el 2,5% de 9.500.000 = 237.500, y las compras
    # van en 310.000: rojo. Con el 4% que tenía antes (380.000) este aviso no
    # podía gatillar nunca, porque el control de riesgo total abierto, que va
    # al 3%, se ponía rojo primero.
    assert "Riesgo en compras: 310,000 CLP, sobre el tope de 237,500" in rojos, rojos
    assert "apuesta direccional" in rojos
    # Las ventas, en 90.000, están bajo el 80% del tope: no dicen nada.
    assert "Riesgo en ventas" not in rojos
    amarillos = " || ".join(str(e.value) for e in at.warning)
    assert "Riesgo en ventas" not in amarillos, amarillos


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
