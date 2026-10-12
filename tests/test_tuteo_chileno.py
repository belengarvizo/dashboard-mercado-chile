"""Los textos de la interfaz van en tuteo chileno, nunca en voseo.

POR QUÉ ESTA PRUEBA EXISTE. El voseo ("ingresá", "apretá", "tenés") se
coló varias veces en textos que ve la usuaria, incluso después de una
pasada de corrección: quedaron cinco cadenas vivas que solo aparecieron al
mirar la pantalla en el navegador. Una prueba lo detecta antes.

LAS PALABRAS PROHIBIDAS SE CONSTRUYEN AL VUELO, a partir de los
infinitivos. Si estuvieran escritas tal cual, este archivo contendría
justamente lo que prohíbe y la prueba se encontraría a sí misma.
"""
import io
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

RAIZ = os.path.join(os.path.dirname(__file__), "..")
CARPETAS_IGNORADAS = {".git", "__pycache__", "node_modules", ".venv", "venv",
                      ".pytest_cache", "build", "dist"}

# Verbos frecuentes en textos de interfaz. Quedan fuera los que al conjugarse
# en voseo coinciden con una palabra legítima, porque un guardián que da
# falsas alarmas se termina ignorando:
#
#   - "estar" daría "está" y "ser" daría "sé": los dos son correctos en tuteo.
#   - TODOS los verbos en -ir quedan fuera. Su imperativo de voseo es idéntico
#     al pretérito de primera persona: "seguí" es voseo en "seguí el plan",
#     pero es correcto en "¿seguí mi plan?", que es justo lo que pregunta el
#     diario. Lo mismo con "abrí", "escribí" y "elegí". Los verbos en -ar y
#     en -er no tienen esa colisión ("cambié", "hice").
INFINITIVOS_IMPERATIVO = [
    "ingresar", "apretar", "cambiar", "sacar", "pasar", "revisar", "mirar",
    "cargar", "anotar", "hacer", "poner", "dejar", "verificar",
    "consultar", "usar", "cerrar", "guardar", "calcular", "comparar",
    "agregar", "buscar", "copiar", "esperar", "fijar", "probar",
    "recordar", "tomar", "volver", "empezar", "contar", "llenar",
]
# Presente de indicativo en voseo: "tenés", "podés", ... Mismo criterio: sin
# verbos en -ir, cuya forma de voseo ("preferís") coincide con la de vosotros.
INFINITIVOS_PRESENTE = [
    "tener", "poder", "querer", "saber", "deber", "necesitar",
    "entender", "pensar", "esperar", "mirar", "usar",
]

ACENTUADA = {"a": "á", "e": "é", "i": "í"}


def _imperativo_voseo(infinitivo: str) -> str:
    """ingresar -> ingres + á. Se quita la r y se acentúa la vocal final."""
    sin_r = infinitivo[:-1]
    return sin_r[:-1] + ACENTUADA[sin_r[-1]]


def _presente_voseo(infinitivo: str) -> str:
    """tener -> ten + és;  necesitar -> necesit + ás."""
    raiz, terminacion = infinitivo[:-2], infinitivo[-2:]
    return raiz + (ACENTUADA["a"] + "s" if terminacion == "ar"
                   else ACENTUADA["e"] + "s")


# Pronombres enclíticos frecuentes en textos de interfaz.
PRONOMBRES = ("lo", "la", "los", "las", "me")

# Verbos que al pegarles un enclítico producen una palabra real del español y
# no sirven para detectar nada: "tomar" + "te" da "tomate".
SIN_ENCLITICO = {"tomar", "contar", "pasar"}


def _enclitico_voseo(infinitivo: str, pronombre: str) -> str:
    """cargar + lo -> cargalo (voseo). El tuteo sería "cárgalo", CON tilde.

    POR QUÉ HACE FALTA ESTA FAMILIA APARTE. El voseo con pronombre pegado
    pierde la tilde escrita, así que un detector que busca vocales acentuadas
    no lo ve. Se coló así en dos textos vivos: "Cargalo desde el ticket de
    XTB" y "revisala contra XTB o ingresala a mano". La marca de que es
    voseo no es el acento sino su AUSENCIA: la forma de tuteo siempre lleva
    tilde (cárgalo, revísala, ingrésala).
    """
    return infinitivo[:-1] + pronombre


def formas_de_voseo() -> set:
    formas = {_imperativo_voseo(v) for v in INFINITIVOS_IMPERATIVO}
    formas |= {_presente_voseo(v) for v in INFINITIVOS_PRESENTE}
    formas |= {
        _enclitico_voseo(v, p)
        for v in INFINITIVOS_IMPERATIVO if v not in SIN_ENCLITICO
        for p in PRONOMBRES
    }
    return formas


def _archivos_python():
    for carpeta, subcarpetas, archivos in os.walk(RAIZ):
        subcarpetas[:] = [d for d in subcarpetas if d not in CARPETAS_IGNORADAS]
        for nombre in archivos:
            if nombre.endswith(".py"):
                yield os.path.join(carpeta, nombre)


def test_las_formas_se_construyen_bien():
    """Si la construcción estuviera mal, la prueba de abajo pasaría siempre
    sin revisar nada."""
    assert _imperativo_voseo("ingresar") == "ingres" + ACENTUADA["a"]
    assert _imperativo_voseo("hacer") == "hac" + ACENTUADA["e"]
    assert _imperativo_voseo("poner") == "pon" + ACENTUADA["e"]
    assert _presente_voseo("tener") == "ten" + ACENTUADA["e"] + "s"
    assert _presente_voseo("necesitar") == "necesit" + ACENTUADA["a"] + "s"
    # El enclítico NO lleva tilde: esa es justamente su marca.
    assert _enclitico_voseo("cargar", "lo") == "carga" + "lo"
    assert _enclitico_voseo("revisar", "la") == "revisa" + "la"
    assert all(ACENTUADA[v] not in _enclitico_voseo("cargar", "lo")
               for v in ACENTUADA)
    assert len(formas_de_voseo()) > 100


def test_no_hay_voseo_en_el_codigo():
    """Busca cada forma como palabra completa, con mayúscula o minúscula."""
    formas = formas_de_voseo()
    patrones = {f: re.compile(r"\b" + f + r"\b", re.IGNORECASE) for f in formas}
    hallazgos = []
    for ruta in _archivos_python():
        if os.path.abspath(ruta) == os.path.abspath(__file__):
            continue  # este archivo construye las formas, no las contiene
        texto = io.open(ruta, encoding="utf-8").read()
        for numero, linea in enumerate(texto.splitlines(), 1):
            for forma, patron in patrones.items():
                if patron.search(linea):
                    relativa = os.path.relpath(ruta, RAIZ)
                    hallazgos.append(f"{relativa}:{numero}  [{forma}]  "
                                     f"{linea.strip()[:90]}")
    assert not hallazgos, (
        "Hay voseo en el código. Los textos van en tuteo chileno "
        "(\"revisa\", \"puedes\", \"tienes\"):\n" + "\n".join(hallazgos))


if __name__ == "__main__":
    print("Correr con pytest: python -m pytest tests/test_tuteo_chileno.py")
