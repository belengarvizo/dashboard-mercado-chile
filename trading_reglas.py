"""Control de las reglas del Alpha Trading Challenge de XTB.

QUÉ ES ESTO Y QUÉ NO ES. Es un ESPEJO de lo que el usuario registró a mano, no
un guardián. XTB controla sus reglas en tiempo real sobre la cuenta real; acá
solo se refleja lo que se haya cargado en el diario, y con el retraso con que
se haya cargado. Un panel en verde significa "lo que registraste cumple", no
"estás cumpliendo". La regla del piso de 5.000.000 CLP, en particular, la
aplica XTB automáticamente y puede dispararse sin que el diario se entere.

Módulo puro: no importa Streamlit ni toca la base, así que es testeable.

Todas las funciones devuelven un Chequeo con el número, el límite y el estado,
para que la UI solo pinte y no calcule.
"""
from dataclasses import dataclass, field
from decimal import Decimal

CAPITAL_INICIAL_CLP = Decimal("10000000")
PISO_EQUITY_CLP = Decimal("5000000")
MINIMO_OPERACIONES_CERRADAS = 10
MAXIMO_OPERACIONES_CORTAS = 50
SEGUNDOS_OPERACION_CORTA = 120
TOPE_MARGEN_POR_SUBYACENTE = Decimal("0.30")
TOPE_TRADE_SOBRE_GANANCIA = Decimal("0.40")
TOPE_RIESGO_ABIERTO_POR_DEFECTO = Decimal("0.03")
# Límite PROPIO de cuánto puede arriesgar UNA operación, como fracción del
# capital. No sale del reglamento del torneo: XTB no lo exige. Por debajo del
# tope de riesgo total abierto (3%), porque una sola operación nunca debería
# agotar sola el presupuesto de riesgo de toda la cuenta.
TOPE_RIESGO_POR_OPERACION_POR_DEFECTO = Decimal("0.02")
# Umbral intermedio: avisar en amarillo antes de llegar al límite duro.
AVISO_MARGEN_POR_SUBYACENTE = Decimal("0.20")

VERDE, AMARILLO, ROJO, SIN_DATOS = "verde", "amarillo", "rojo", "sin_datos"


@dataclass
class Chequeo:
    nombre: str
    estado: str                 # VERDE | AMARILLO | ROJO | SIN_DATOS
    detalle: str                # frase corta, lista para mostrar
    valor: Decimal | int | None = None
    limite: Decimal | int | None = None
    nota: str = ""              # ambigüedades del reglamento, supuestos
    desglose: list[str] = field(default_factory=list)


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _d_o_nada(x):
    """Como _d, pero devuelve None en vez de reventar con los faltantes.

    pandas entrega NaN para los NULL de SQL, y NaN es el único valor distinto
    de sí mismo: un chequeo `is None` no lo ve.
    """
    if x is None:
        return None
    try:
        d = _d(x)
    except Exception:
        return None
    return None if d != d else d


def minimo_operaciones(cerradas: int) -> Chequeo:
    """Hay que cerrar al menos 10 operaciones para ser elegible."""
    faltan = max(0, MINIMO_OPERACIONES_CERRADAS - cerradas)
    if cerradas >= MINIMO_OPERACIONES_CERRADAS:
        return Chequeo("Operaciones cerradas", VERDE,
                       f"{cerradas} cerradas (mínimo {MINIMO_OPERACIONES_CERRADAS})",
                       cerradas, MINIMO_OPERACIONES_CERRADAS)
    estado = AMARILLO if cerradas >= MINIMO_OPERACIONES_CERRADAS // 2 else ROJO
    return Chequeo("Operaciones cerradas", estado,
                   f"{cerradas} de {MINIMO_OPERACIONES_CERRADAS}: faltan {faltan} para ser elegible",
                   cerradas, MINIMO_OPERACIONES_CERRADAS)


def operaciones_cortas(cantidad: int) -> Chequeo:
    """Tope de 50 operaciones de menos de 2 minutos."""
    if cantidad > MAXIMO_OPERACIONES_CORTAS:
        estado = ROJO
    elif cantidad >= MAXIMO_OPERACIONES_CORTAS * 0.8:
        estado = AMARILLO
    else:
        estado = VERDE
    return Chequeo("Operaciones de menos de 2 minutos", estado,
                   f"{cantidad} de {MAXIMO_OPERACIONES_CORTAS} permitidas",
                   cantidad, MAXIMO_OPERACIONES_CORTAS)


def piso_de_equity(equity_clp) -> Chequeo:
    """Bajar de 5.000.000 CLP descalifica. Lo controla XTB en tiempo real."""
    if equity_clp is None:
        return Chequeo("Equity vs. piso de descalificación", SIN_DATOS,
                       "No registraste el equity todavía", None, PISO_EQUITY_CLP,
                       nota="XTB aplica esta regla en tiempo real sobre tu cuenta real.")
    equity = _d(equity_clp)
    margen = equity - PISO_EQUITY_CLP
    pct = margen / PISO_EQUITY_CLP * 100
    if equity <= PISO_EQUITY_CLP:
        estado, texto = ROJO, f"{equity:,.0f} CLP: está EN o BAJO el piso de descalificación"
    elif pct < 20:
        estado, texto = AMARILLO, f"{equity:,.0f} CLP: a {margen:,.0f} del piso ({pct:.0f}% de colchón)"
    else:
        estado, texto = VERDE, f"{equity:,.0f} CLP: a {margen:,.0f} del piso"
    return Chequeo("Equity vs. piso de descalificación", estado, texto, equity, PISO_EQUITY_CLP,
                   nota="XTB aplica esta regla en tiempo real; este panel solo refleja lo que registraste.")


def mayor_trade_sobre_ganancia(resultados: list) -> Chequeo:
    """Ningún trade puede ser más del 40% de la ganancia total acumulada.

    El reglamento no dice si "ganancia total acumulada" es la suma de los
    trades ganadores o el resultado neto. Se usa el NETO, que es la lectura
    más exigente cuando hay pérdidas, y se informa la otra en el desglose.
    """
    ganadores = [_d(r) for r in resultados if r is not None and _d(r) > 0]
    if not ganadores:
        return Chequeo("Mayor trade vs. ganancia total", SIN_DATOS,
                       "Todavía no hay operaciones ganadoras", None, TOPE_TRADE_SOBRE_GANANCIA)

    neto = sum((_d(r) for r in resultados if r is not None), Decimal(0))
    bruto = sum(ganadores, Decimal(0))
    mayor = max(ganadores)

    if neto <= 0:
        return Chequeo("Mayor trade vs. ganancia total", SIN_DATOS,
                       f"El resultado neto es {neto:,.0f} CLP: la regla no aplica mientras no haya ganancia",
                       None, TOPE_TRADE_SOBRE_GANANCIA,
                       nota="Regla ambigua en el reglamento: confirmar con XTB si 'ganancia total' es neta o bruta.",
                       desglose=[f"Mayor ganador: {mayor:,.0f} CLP",
                                 f"Suma de ganadores: {bruto:,.0f} CLP"])

    proporcion = mayor / neto
    if proporcion > TOPE_TRADE_SOBRE_GANANCIA:
        estado = ROJO
    elif proporcion > TOPE_TRADE_SOBRE_GANANCIA * Decimal("0.8"):
        estado = AMARILLO
    else:
        estado = VERDE
    return Chequeo(
        "Mayor trade vs. ganancia total", estado,
        f"El mayor ganador es el {proporcion * 100:.1f}% del neto (tope {TOPE_TRADE_SOBRE_GANANCIA * 100:.0f}%)",
        proporcion, TOPE_TRADE_SOBRE_GANANCIA,
        nota="Regla ambigua en el reglamento: confirmar con XTB si 'ganancia total' es neta o bruta.",
        desglose=[f"Mayor ganador: {mayor:,.0f} CLP",
                  f"Resultado neto: {neto:,.0f} CLP  ->  {proporcion * 100:.1f}%",
                  f"Suma de ganadores: {bruto:,.0f} CLP  ->  {mayor / bruto * 100:.1f}%"])


def limite_margen_por_subyacente(equity_clp) -> tuple[Decimal, list[str]]:
    """El 30% se calcula sobre el equity actual, pero se usa el MENOR entre
    ese valor y el 30% del capital inicial, que es la lectura conservadora
    mientras el reglamento no aclare cuál corresponde."""
    sobre_capital = CAPITAL_INICIAL_CLP * TOPE_MARGEN_POR_SUBYACENTE
    if equity_clp is None:
        return sobre_capital, [
            f"30% del capital inicial = {sobre_capital:,.0f} CLP",
            "No hay equity registrado: se usa solo el capital inicial.",
        ]
    sobre_equity = _d(equity_clp) * TOPE_MARGEN_POR_SUBYACENTE
    limite = min(sobre_equity, sobre_capital)
    return limite, [
        f"30% del equity actual ({_d(equity_clp):,.0f}) = {sobre_equity:,.0f} CLP",
        f"30% del capital inicial (10.000.000) = {sobre_capital:,.0f} CLP",
        f"Se usa el menor: {limite:,.0f} CLP",
    ]


def margen_por_subyacente(margenes: dict, equity_clp, sin_dato: int = 0) -> Chequeo:
    """`margenes` es {instrumento: margen_clp} de las posiciones ABIERTAS.

    `sin_dato` es cuántas posiciones abiertas NO tienen margen cargado. Si hay
    alguna, el chequeo NO puede pintar verde: no sabría lo que no se le
    contó. Un verde por falta de datos es peor que no mostrar nada.
    """
    limite, pasos = limite_margen_por_subyacente(equity_clp)
    nota_regla = ("Regla ambigua en el reglamento: confirmar con XTB si el 30% va sobre "
                  "el equity o sobre el margen disponible.")
    if sin_dato:
        return Chequeo(
            "Margen por subyacente", SIN_DATOS,
            f"Falta cargar el margen en {sin_dato} posición(es) abierta(s): "
            f"no se puede evaluar la regla del 30%",
            None, limite, nota=nota_regla, desglose=pasos)
    if not margenes:
        return Chequeo("Margen por subyacente", VERDE, "No hay posiciones abiertas",
                       Decimal(0), limite, desglose=pasos, nota=nota_regla)

    peor_inst, peor_margen = max(margenes.items(), key=lambda kv: _d(kv[1]))
    peor_margen = _d(peor_margen)
    proporcion = peor_margen / limite if limite > 0 else Decimal(0)
    if proporcion >= 1:
        estado = ROJO
    elif proporcion >= AVISO_MARGEN_POR_SUBYACENTE / TOPE_MARGEN_POR_SUBYACENTE:
        estado = AMARILLO
    else:
        estado = VERDE
    desglose = pasos + [f"{inst}: {_d(m):,.0f} CLP" for inst, m in
                        sorted(margenes.items(), key=lambda kv: -_d(kv[1]))]
    return Chequeo(
        "Margen por subyacente", estado,
        f"El mayor es {peor_inst} con {peor_margen:,.0f} CLP ({proporcion * 100:.0f}% del límite)",
        peor_margen, limite, desglose=desglose,
        nota="Regla ambigua en el reglamento: confirmar con XTB si el 30% va sobre el equity o sobre el margen disponible.")


def riesgo_total_abierto(riesgos: list, equity_clp,
                         tope_pct: Decimal = TOPE_RIESGO_ABIERTO_POR_DEFECTO,
                         sin_dato: int = 0) -> Chequeo:
    """Suma de lo que se perdería si TODAS las posiciones abiertas tocan su
    stop. No es una regla del torneo: es un límite propio.

    `sin_dato` es cuántas posiciones abiertas no tienen el riesgo cargado.
    Con una sola que falte, la suma está incompleta y el chequeo pasa a
    SIN_DATOS: pintar verde sumando solo lo que sí se cargó sería afirmar
    que el riesgo está acotado cuando no se sabe.
    """
    base = _d(equity_clp) if equity_clp is not None else CAPITAL_INICIAL_CLP
    tope = base * _d(tope_pct)
    total = sum((_d(r) for r in riesgos if r is not None), Decimal(0))
    if sin_dato:
        return Chequeo(
            "Riesgo total si todos los stops saltan", SIN_DATOS,
            f"Falta cargar el riesgo en {sin_dato} posición(es) abierta(s): "
            f"los {total:,.0f} CLP contados son solo una parte",
            None, tope, nota="Límite propio, no del reglamento del torneo.")
    if total > tope:
        estado = ROJO
    elif total > tope * Decimal("0.8"):
        estado = AMARILLO
    else:
        estado = VERDE
    return Chequeo(
        "Riesgo total si todos los stops saltan", estado,
        f"{total:,.0f} CLP de {tope:,.0f} permitidos ({_d(tope_pct) * 100:.1f}% de {base:,.0f})",
        total, tope,
        nota="Límite propio, no del reglamento del torneo.")


def riesgo_por_operacion(riesgo_clp, equity_clp,
                         tope_pct=TOPE_RIESGO_POR_OPERACION_POR_DEFECTO) -> Chequeo:
    """Lo que arriesga UNA operación contra el límite propio.

    AVISA, NO BLOQUEA: devuelve un Chequeo, igual que el resto del panel.
    Amarillo desde el 80% del límite, rojo al pasarlo.

    Justo EN el límite queda amarillo, no rojo: no lo superó, pero no queda
    margen. Para el rojo se exige estrictamente mayor.

    Si no hay equity registrado se usa el capital inicial y se dice en el
    texto, en vez de devolver gris: antes de registrar el primer equity, el
    capital del torneo es el inicial, y dejar el control apagado sería peor
    que calcularlo sobre un número declarado.
    """
    nombre = "Riesgo de esta operación"
    nota = "Límite propio, no del reglamento del torneo."

    riesgo = _d_o_nada(riesgo_clp)
    if riesgo is None or riesgo <= 0:
        return Chequeo(nombre, SIN_DATOS,
                       "Falta el riesgo de la operación o quedó en cero", nota=nota)

    fraccion = _d_o_nada(tope_pct)
    if fraccion is None or fraccion <= 0:
        return Chequeo(nombre, SIN_DATOS, "Falta el límite por operación", nota=nota)

    base = _d_o_nada(equity_clp)
    sobre_el_inicial = base is None or base <= 0
    if sobre_el_inicial:
        base = CAPITAL_INICIAL_CLP

    tope = base * fraccion
    porcentaje = riesgo / base * 100

    if riesgo > tope:
        estado = ROJO
    elif riesgo > tope * Decimal("0.8"):
        estado = AMARILLO
    else:
        estado = VERDE

    de_donde = (f"capital inicial de {base:,.0f} (todavía no registras el equity)"
                if sobre_el_inicial else f"capital de {base:,.0f}")
    detalle = (f"{riesgo:,.0f} CLP, {porcentaje:.2f}% del {de_donde}. "
               f"Tu límite son {tope:,.0f} ({fraccion * 100:.1f}%)")

    if base <= PISO_EQUITY_CLP:
        nota = f"Ya estás en el piso de {PISO_EQUITY_CLP:,.0f} o por debajo. " + nota
    else:
        cuantas = int((base - PISO_EQUITY_CLP) / riesgo)
        nota = (f"{cuantas} operaciones así seguidas, todas perdedoras, te dejarían "
                f"en el piso de {PISO_EQUITY_CLP:,.0f}. ") + nota

    return Chequeo(nombre, estado, detalle, riesgo, tope, nota=nota)


def stops_hasta_el_piso(equity_clp, riesgo_por_operacion_clp) -> Chequeo:
    """Cuántos stops seguidos, al riesgo actual, llevan la cuenta al piso de
    descalificación. Es la pregunta que más rápido ordena el tamaño."""
    if equity_clp is None or riesgo_por_operacion_clp in (None, 0):
        return Chequeo("Stops seguidos hasta la descalificación", SIN_DATOS,
                       "Falta el equity o el riesgo por operación")
    equity = _d(equity_clp)
    riesgo = _d(riesgo_por_operacion_clp)
    if riesgo <= 0:
        return Chequeo("Stops seguidos hasta la descalificación", SIN_DATOS,
                       "El riesgo por operación tiene que ser mayor que cero")
    if equity <= PISO_EQUITY_CLP:
        return Chequeo("Stops seguidos hasta la descalificación", ROJO,
                       "Ya estás en el piso o por debajo", 0)
    cuantos = int((equity - PISO_EQUITY_CLP) / riesgo)
    if cuantos <= 5:
        estado = ROJO
    elif cuantos <= 15:
        estado = AMARILLO
    else:
        estado = VERDE
    return Chequeo(
        "Stops seguidos hasta la descalificación", estado,
        f"{cuantos} stops seguidos de {riesgo:,.0f} CLP te dejarían en el piso de 5.000.000",
        cuantos,
        desglose=[f"({equity:,.0f} - {PISO_EQUITY_CLP:,.0f}) / {riesgo:,.0f} = {cuantos}"])


def concentracion_por_categoria(margenes_por_categoria: dict) -> Chequeo:
    """Cuánto del margen comprometido está en cada categoría. No es una regla
    del torneo, pero varias cripto a la vez son en la práctica una sola
    apuesta: casi todas se mueven juntas."""
    total = sum((_d(v) for v in margenes_por_categoria.values()), Decimal(0))
    if total <= 0:
        return Chequeo("Concentración por categoría", VERDE, "No hay margen comprometido")
    partes = sorted(((cat, _d(v) / total) for cat, v in margenes_por_categoria.items()),
                    key=lambda kv: -kv[1])
    mayor_cat, mayor_pct = partes[0]
    estado = AMARILLO if mayor_pct > Decimal("0.6") else VERDE
    nota = ""
    if mayor_cat == "cripto" and mayor_pct > Decimal("0.4"):
        nota = ("Casi todas las cripto se mueven juntas: varias posiciones abiertas "
                "ahí son, en la práctica, una sola apuesta repetida.")
    return Chequeo(
        "Concentración por categoría", estado,
        f"{mayor_cat} concentra el {mayor_pct * 100:.0f}% del margen", mayor_pct, None,
        nota=nota,
        desglose=[f"{cat}: {pct * 100:.0f}%" for cat, pct in partes])
