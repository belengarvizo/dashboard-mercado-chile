"""Guarda estática: ninguna función cacheada debe leer el reloj adentro.

EL BUG QUE ESTO PREVIENE. Varias funciones de app/dashboard.py están
decoradas con @st.cache_data(ttl=3600). Si una de ellas calcula
pd.Timestamp.now() (o datetime.now() / date.today()) DENTRO de su cuerpo, esa
fecha queda congelada en la entrada del caché durante toda la vida de la
entrada. El resultado es que el dashboard sigue usando el "hoy" de ayer
durante la primera hora después de medianoche.

Se detectó en calcular_resumen_ipsa y calcular_resumen_dow_jones, donde el
efecto era visible: la columna "Atraso" mostraba "Precio congelado — N días
hábiles" con el N del día anterior. También estaba en calcular_var,
calcular_cuartiles_liquidez, calcular_distribucion_retornos y
_defensa_topdown_series_12m, donde corría la fecha de corte de la ventana.

El arreglo es pasar la fecha como argumento (ver _hoy_normalizado en
app/dashboard.py): así forma parte de la clave del caché y el cambio de día
invalida la entrada sola, sin perder el cacheo dentro del mismo día.

Este test es ESTÁTICO (analiza el AST, no corre la app) a propósito: es el
tipo de bug que no falla nunca en una corrida normal de tests, porque solo se
manifiesta si el reloj cruza la medianoche mientras la entrada sigue viva.
Un test de comportamiento no lo agarraría por accidente.

Limitación conocida: solo detecta la llamada DIRECTA al reloj dentro del
cuerpo. Si una función cacheada llama a otra función que lee el reloj, esto
no lo ve.
"""
import ast
import os

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")

# Llamadas que devuelven "ahora". Se comparan por el final del nombre punteado,
# así que cubre pd.Timestamp.now, datetime.datetime.now, date.today, etc.
LLAMADAS_DE_RELOJ = ("Timestamp.now", "datetime.now", "date.today", "time.time")

# EXCEPCIÓN CORRECTA, no un pendiente: generar_pdf_brief_premercado.
#
# Acá el reloj congelado es el comportamiento que se quiere, y conviene
# entender por qué, porque la diferencia con el resto es sutil.
#
# En las funciones que sí se arreglaron, el reloj se usa para CALCULAR un
# valor que responde una pregunta sobre AHORA: cuántos días hábiles hace que
# un precio no cambia. Esa respuesta crece sola con el paso del tiempo, así
# que servirla congelada da un número falso.
#
# El PDF hace lo contrario: es una FOTO. Reusa las mismas cachés de datos que
# la pestaña, así que su contenido es el de un instante concreto, y el
# "Generated <hora>" del pie y el "As of <fecha>" de la portada estampan
# precisamente ese instante. Un PDF generado a las 23:50 que dice "Generated
# 23:50" es correcto aunque se descargue a las 00:10: esa ES la hora en que
# se produjo. Pasarle la fecha por argumento no lo arreglaría; lo rompería,
# porque el sello dejaría de coincidir con los datos que el documento trae.
#
# Si alguna vez se agrega algo nuevo a esta lista, tiene que ser con una razón
# escrita como esta, no para hacer pasar el test.
EXCEPCIONES_ACEPTADAS = {"generar_pdf_brief_premercado"}


def _nombre_punteado(nodo: ast.AST) -> str:
    """Reconstruye "pd.Timestamp.now" a partir del árbol de atributos."""
    partes = []
    actual = nodo
    while isinstance(actual, ast.Attribute):
        partes.append(actual.attr)
        actual = actual.value
    if isinstance(actual, ast.Name):
        partes.append(actual.id)
    return ".".join(reversed(partes))


def _esta_cacheada(func: ast.FunctionDef) -> bool:
    for dec in func.decorator_list:
        objetivo = dec.func if isinstance(dec, ast.Call) else dec
        if _nombre_punteado(objetivo).endswith("cache_data"):
            return True
    return False


def _relojes_en(func: ast.FunctionDef) -> list[str]:
    encontrados = []
    for nodo in ast.walk(func):
        if isinstance(nodo, ast.Call):
            nombre = _nombre_punteado(nodo.func)
            if any(nombre.endswith(reloj) for reloj in LLAMADAS_DE_RELOJ):
                encontrados.append(f"{nombre}() en la línea {nodo.lineno}")
    return encontrados


def _funciones_cacheadas_con_reloj() -> dict[str, list[str]]:
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        arbol = ast.parse(f.read())
    culpables = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and _esta_cacheada(nodo):
            relojes = _relojes_en(nodo)
            if relojes:
                culpables[nodo.name] = relojes
    return culpables


def test_ninguna_funcion_cacheada_lee_el_reloj_adentro():
    culpables = _funciones_cacheadas_con_reloj()
    nuevos = {n: r for n, r in culpables.items() if n not in EXCEPCIONES_ACEPTADAS}
    assert not nuevos, (
        "Estas funciones están cacheadas y leen el reloj adentro, así que la fecha "
        "queda congelada en el caché y el dashboard usará el 'hoy' de ayer durante "
        "la primera hora después de medianoche:\n"
        + "\n".join(f"  - {n}: {', '.join(r)}" for n, r in sorted(nuevos.items()))
        + "\n\nArreglo: sacá el reloj de la función y pasá la fecha como argumento "
          "(ver _hoy_normalizado en app/dashboard.py), para que forme parte de la "
          "clave del caché."
    )


def test_las_excepciones_aceptadas_siguen_existiendo():
    """Si una excepción ya se arregló, hay que sacarla de la lista en vez de
    dejarla ahí tapando una futura regresión de esa misma función."""
    culpables = _funciones_cacheadas_con_reloj()
    obsoletas = EXCEPCIONES_ACEPTADAS - set(culpables)
    assert not obsoletas, (
        f"Estas funciones ya no leen el reloj adentro: {sorted(obsoletas)}. "
        "Sacalas de EXCEPCIONES_ACEPTADAS para que la guarda vuelva a cubrirlas."
    )


def test_las_funciones_arregladas_reciben_la_fecha_como_argumento():
    """Las seis que se arreglaron deben seguir recibiendo `hoy`. Si alguien
    vuelve a sacarles el parámetro, el test de arriba lo agarraría solo si
    además reintrodujo la llamada al reloj; esto lo agarra antes."""
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        arbol = ast.parse(f.read())
    esperadas = {
        "calcular_resumen_ipsa", "calcular_resumen_dow_jones", "calcular_var",
        "calcular_cuartiles_liquidez", "calcular_distribucion_retornos",
        "_defensa_topdown_series_12m",
    }
    vistas = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and nodo.name in esperadas:
            vistas[nodo.name] = [a.arg for a in nodo.args.args]

    faltantes = esperadas - set(vistas)
    assert not faltantes, f"No se encontraron en el dashboard: {sorted(faltantes)}"

    sin_hoy = {n: args for n, args in vistas.items() if "hoy" not in args}
    assert not sin_hoy, (
        "Estas funciones perdieron el parámetro `hoy`, así que volvieron a depender "
        f"de un reloj que no es parte de la clave del caché: {sin_hoy}"
    )


if __name__ == "__main__":
    test_ninguna_funcion_cacheada_lee_el_reloj_adentro()
    test_las_excepciones_aceptadas_siguen_existiendo()
    test_las_funciones_arregladas_reciben_la_fecha_como_argumento()
    print("OK: las tres guardas pasaron.")
