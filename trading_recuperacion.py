"""Cuánto hay que ganar para volver al punto de partida después de perder.

LA IDEA. Perder y recuperar no son simétricos, y la asimetría crece rápido.
Perder un 20% exige ganar un 25% para volver; perder un 50% exige ganar un
100%. La razón es que la ganancia se calcula sobre un capital más chico:

    ganancia necesaria = pérdida / (1 - pérdida)

EN PESOS ES EL MISMO MONTO. Si perdiste 200.000 CLP, necesitas ganar
200.000 CLP: eso no cambia. Lo que cambia es que esos 200.000 son un
porcentaje mayor del capital que te queda. Por eso el número que importa no
es el monto sino el esfuerzo que representa.

Módulo puro: no importa Streamlit ni toca la base. Es una referencia para
dimensionar, no una señal ni un bloqueo.
"""
from dataclasses import dataclass
from decimal import Decimal

# Las dos rachas que se muestran. Tres pérdidas seguidas le pasan a
# cualquiera; cinco ya es la racha que ordena el tamaño de la posición.
RACHAS = (3, 5)

MOTIVO_SIN_PERDIDA = "sin pérdida que recuperar"
MOTIVO_TODO_EL_CAPITAL = (
    "con una pérdida del 100% del capital no queda nada sobre lo que ganar: "
    "no se recupera con una sola operación"
)
MOTIVO_SIN_CAPITAL = "falta el capital para calcular sobre qué"


@dataclass
class Recuperacion:
    """Qué hace falta para volver al capital de partida.

    `ganancia_fraccion` es sobre el capital QUE QUEDA, no sobre el inicial.
    Es None cuando no se puede, y entonces `motivo` dice por qué.
    """
    perdida_fraccion: Decimal
    perdida_clp: Decimal
    capital_restante_clp: Decimal
    ganancia_fraccion: Decimal | None = None
    ganancia_clp: Decimal | None = None
    motivo: str = ""

    @property
    def se_puede(self) -> bool:
        return self.ganancia_fraccion is not None


def _a_decimal(x) -> Decimal | None:
    if x is None:
        return None
    try:
        d = Decimal(str(x))
    except Exception:
        return None
    # pandas entrega NaN para los NULL de SQL, y NaN es el único valor
    # distinto de sí mismo.
    return None if d != d else d


def ganancia_para_recuperar(perdida_fraccion) -> Decimal | None:
    """perdida / (1 - perdida), con la pérdida como FRACCIÓN del capital.

    None si no hay pérdida (no hay nada que recuperar) o si la pérdida se
    lleva todo el capital o más. Nunca divide por cero.
    """
    p = _a_decimal(perdida_fraccion)
    if p is None or p <= 0 or p >= 1:
        return None
    return p / (Decimal(1) - p)


def recuperacion(perdida_clp, capital_clp) -> Recuperacion | None:
    """La cuenta completa para una pérdida en pesos sobre un capital dado.

    Devuelve None cuando no hay nada que mostrar: sin capital, o sin
    pérdida. Con una pérdida igual o mayor al capital devuelve el objeto con
    `se_puede` en False y el motivo, que es distinto de no mostrar nada.
    """
    perdida = _a_decimal(perdida_clp)
    capital = _a_decimal(capital_clp)
    if capital is None or capital <= 0:
        return None
    if perdida is None or perdida <= 0:
        return None

    fraccion = perdida / capital
    restante = capital - perdida
    ganancia = ganancia_para_recuperar(fraccion)
    if ganancia is None:
        return Recuperacion(fraccion, perdida, max(restante, Decimal(0)),
                            None, None, MOTIVO_TODO_EL_CAPITAL)
    # En pesos hay que ganar exactamente lo perdido: ganancia x restante
    # = (p/(1-p)) x C(1-p) = pC. Se calcula igual, no se asume.
    return Recuperacion(fraccion, perdida, restante, ganancia, ganancia * restante)


def recuperacion_de_racha(riesgo_fraccion, capital_clp, perdidas: int):
    """Lo mismo, pero después de `perdidas` operaciones seguidas en contra.

    SUPUESTO QUE IMPORTA: se asume que vuelves a calcular el tamaño sobre el
    capital que te queda, que es lo que hace el calculador de esta misma
    pantalla. Por eso las pérdidas COMPONEN y no se suman: perder 1% tres
    veces deja 0,99^3, es decir 2,9701% abajo y no 3%. Si en cambio
    mantuvieras el tamaño fijo en pesos, la pérdida sería algo mayor.
    """
    riesgo = _a_decimal(riesgo_fraccion)
    capital = _a_decimal(capital_clp)
    if capital is None or capital <= 0 or riesgo is None or riesgo <= 0:
        return None
    if perdidas is None or perdidas < 1:
        return None
    if riesgo >= 1:
        # Una sola operación se lleva todo: no hay racha que calcular.
        return Recuperacion(Decimal(1), capital, Decimal(0), None, None,
                            MOTIVO_TODO_EL_CAPITAL)
    queda = (Decimal(1) - riesgo) ** int(perdidas)
    return recuperacion(capital * (Decimal(1) - queda), capital)


def tabla_de_rachas(riesgo_fraccion, capital_clp, rachas=RACHAS) -> list:
    """[(n, Recuperacion), ...] para las rachas pedidas, sin las que no
    aplican."""
    salida = []
    for n in rachas:
        r = recuperacion_de_racha(riesgo_fraccion, capital_clp, n)
        if r is not None:
            salida.append((n, r))
    return salida
