"""Estadísticas del proceso de trading: medir cómo se decide, no solo cuánto
se ganó.

LA IDEA DE FONDO. Un resultado bueno puede venir de una decisión mala y al
revés; con pocas operaciones, el resultado dice más sobre el azar que sobre
quien opera. Por eso acá todo se expresa en múltiplos de R (cuántas veces el
riesgo que se arriesgó) y todo viene acompañado de n, el número de
operaciones detrás de cada número.

Módulo PURO: no importa Streamlit ni toca la base. Todas las funciones
trabajan sobre listas de diccionarios y son testeables sin infraestructura.

CUANDO NO SE PUEDE CALCULAR, DEVUELVE None. Nunca 0, que se leería como "la
expectativa es cero" en vez de "no hay datos".
"""
from dataclasses import dataclass, field
from decimal import Decimal

# Debajo de este número de operaciones, cualquier estadística es una pista y
# no una conclusión: la dispersión domina sobre la señal.
N_MINIMO_CONFIABLE = 20
AVISO_POCAS = "pocas operaciones: es una pista, no una conclusión"

TENDENCIAS = ("a_favor", "contra", "neutral")
CALIDADES = ("buena", "mala")
CONVICCIONES = (1, 2, 3)


def _d(x):
    if x is None:
        return None
    if isinstance(x, Decimal):
        return x
    if x != x:  # NaN: los datos llegan de la base vía pandas
        return None
    return Decimal(str(x))


def r_multiplo(resultado_clp, riesgo_clp):
    """Resultado en múltiplos del riesgo inicial.

    None si falta el riesgo o si es cero: una operación sin riesgo registrado
    no tiene R, y poner 0 o el resultado crudo mezclaría peras con manzanas
    en todos los promedios de más abajo.
    """
    resultado = _d(resultado_clp)
    riesgo = _d(riesgo_clp)
    if resultado is None or riesgo is None or riesgo == 0:
        return None
    return resultado / abs(riesgo)


def r_multiplos_de(operaciones) -> list:
    """Los R que se pueden calcular de una lista de operaciones cerradas."""
    valores = []
    for op in operaciones:
        r = r_multiplo(op.get("resultado_clp"), op.get("riesgo_clp"))
        if r is not None:
            valores.append(r)
    return valores


def expectativa_r(r_multiplos):
    """Promedio de los R. Es lo que se espera ganar (o perder) por operación,
    medido en unidades de riesgo. None si no hay ninguno."""
    valores = [v for v in r_multiplos if v is not None]
    if not valores:
        return None
    return sum(valores, Decimal(0)) / Decimal(len(valores))


def peor_racha_perdidas(resultados) -> int:
    """La racha más larga de operaciones perdedoras seguidas.

    Los empates (resultado exactamente 0) NO cortan la racha ni la alargan:
    no son una pérdida, pero tampoco son una recuperación. Las operaciones
    sin resultado se ignoran.
    """
    peor = actual = 0
    for bruto in resultados:
        valor = _d(bruto)
        if valor is None:
            continue
        if valor < 0:
            actual += 1
            peor = max(peor, actual)
        elif valor > 0:
            actual = 0
    return peor


# --------------------------------------- el riesgo escrito contra los lotes
# Cuánto puede diferir el riesgo que se escribe a mano del que implican los
# lotes, el stop y el valor del pip, antes de avisar. Un 10% cubre el redondeo
# de lotes (0,12 en vez de 0,1236) y las diferencias de tasa entre el ticket y
# el último cierre guardado, que ya se midieron en 0,5%.
TOLERANCIA_RIESGO_CONTRA_LOTES = Decimal("0.10")


@dataclass
class RiesgoContraLotes:
    """Comparación entre el riesgo escrito y el que sale de los lotes.

    `cuadra` es None cuando faltan datos para comparar: eso NO es "está
    bien", es "no se pudo mirar".
    """
    cuadra: bool = None
    riesgo_escrito: Decimal = None
    riesgo_implicito: Decimal = None
    lotes_escritos: Decimal = None
    lotes_para_el_riesgo: Decimal = None
    texto: str = ""


def riesgo_contra_lotes(riesgo_escrito, lotes, pips, valor_pip_un_lote,
                        tolerancia=TOLERANCIA_RIESGO_CONTRA_LOTES) -> RiesgoContraLotes:
    """Avisa si el riesgo escrito a mano no concuerda con los lotes.

    POR QUÉ EXISTE. En el formulario, lotes, riesgo y margen son tres campos
    independientes y nadie comprobaba que hablaran de la misma operación. Pasó
    de verdad: una fila quedó con lotes 0,01 y un riesgo de 100.000 CLP, que
    corresponde a 0,12 lotes. El riesgo escrito se guarda tal cual, así que el
    panel de riesgo sumaba 100.000 por una posición que arriesgaba 8.093.

    AVISA, NO BLOQUEA: devuelve la comparación y el texto; quien llama decide
    qué hacer, y en la pantalla no impide guardar.
    """
    escrito = _d(riesgo_escrito)
    n_lotes = _d(lotes)
    n_pips = _d(pips)
    por_lote = _d(valor_pip_un_lote)

    if (escrito is None or escrito <= 0 or n_lotes is None or n_lotes <= 0
            or n_pips is None or n_pips <= 0 or por_lote is None or por_lote <= 0):
        return RiesgoContraLotes()

    implicito = n_pips * por_lote * n_lotes
    lotes_para_el_riesgo = escrito / (n_pips * por_lote)
    diferencia = abs(escrito - implicito) / implicito
    if diferencia <= _d(tolerancia):
        return RiesgoContraLotes(True, escrito, implicito, n_lotes,
                                 lotes_para_el_riesgo)

    return RiesgoContraLotes(
        False, escrito, implicito, n_lotes, lotes_para_el_riesgo,
        f"Escribiste **{escrito:,.0f} CLP** de riesgo, pero con **{n_lotes} lotes** "
        f"y {n_pips:.1f} pips al stop el riesgo es **{implicito:,.0f} CLP**. "
        f"Para arriesgar {escrito:,.0f} necesitas **{lotes_para_el_riesgo:.2f} "
        f"lotes**.")


# ----------------------------------------------------- antimartingala
SIN_AVISO, AVISO_SUBIO, SIN_DATO = "ninguno", "aviso", "sin_dato"

TEXTO_ANTIMARTINGALA = (
    "Subir el tamaño después de perder es el patrón que más rápido destruye una "
    "cuenta: convierte una racha de pérdidas normal en una racha de pérdidas "
    "crecientes, y el pozo se hace más hondo justo cuando menos capital queda "
    "para salir."
)


def ultima_cerrada(operaciones):
    """La operación CERRADA más reciente, por fecha de cierre.

    Las abiertas no sirven de comparación: todavía no tienen resultado, así
    que no se sabe si fueron pérdida.
    """
    cerradas = [op for op in (operaciones or [])
                if op.get("fecha_cierre") is not None
                and op.get("fecha_cierre") == op.get("fecha_cierre")]  # descarta NaT
    if not cerradas:
        return None
    try:
        return max(cerradas, key=lambda op: op["fecha_cierre"])
    except TypeError:
        # Fechas de tipos mezclados: queda la última tal como vino.
        return cerradas[-1]


@dataclass
class Antimartingala:
    """El resultado del chequeo. `nivel` es SIN_AVISO, AVISO_SUBIO o SIN_DATO.

    SIN_DATO no es lo mismo que SIN_AVISO: quiere decir que la operación
    anterior no tiene cargado el riesgo o el resultado, así que no se puede
    comparar. Callarlo sería dar por buena una comparación que no se hizo.
    """
    nivel: str = SIN_AVISO
    texto: str = ""
    riesgo_anterior: Decimal = None
    resultado_anterior: Decimal = None
    riesgo_nuevo: Decimal = None

    @property
    def avisa(self) -> bool:
        return self.nivel == AVISO_SUBIO


def aviso_antimartingala(riesgo_nuevo, operaciones) -> Antimartingala:
    """Avisa si el riesgo que se va a tomar SUPERA el de la operación
    anterior Y esa anterior fue una pérdida.

    Estrictamente mayor: repetir el mismo tamaño después de perder no es
    antimartingala, es mantener el plan.

    Es un AVISO, nunca un bloqueo: la función solo describe, no decide.
    """
    nuevo = _d(riesgo_nuevo)
    if nuevo is None or nuevo <= 0:
        return Antimartingala(SIN_AVISO)

    anterior = ultima_cerrada(operaciones)
    if anterior is None:
        # Sin operaciones cerradas no hay con qué comparar, y eso no es una
        # falta de datos: es el primer trade.
        return Antimartingala(SIN_AVISO, riesgo_nuevo=nuevo)

    resultado = _d(anterior.get("resultado_clp"))
    riesgo_anterior = _d(anterior.get("riesgo_clp"))
    instrumento = anterior.get("instrumento") or "la anterior"

    if resultado is None or riesgo_anterior is None or riesgo_anterior <= 0:
        falta = "el resultado" if resultado is None else "el riesgo"
        return Antimartingala(
            SIN_DATO,
            f"No se puede comparar con la operación anterior ({instrumento}): le "
            f"falta {falta}. Cárgalo en el diario si quieres que este aviso "
            f"funcione.",
            riesgo_anterior, resultado, nuevo)

    if resultado >= 0:
        return Antimartingala(SIN_AVISO, riesgo_nuevo=nuevo,
                              riesgo_anterior=riesgo_anterior,
                              resultado_anterior=resultado)

    if nuevo <= riesgo_anterior:
        return Antimartingala(SIN_AVISO, riesgo_nuevo=nuevo,
                              riesgo_anterior=riesgo_anterior,
                              resultado_anterior=resultado)

    subida = (nuevo - riesgo_anterior) / riesgo_anterior * 100
    return Antimartingala(
        AVISO_SUBIO,
        f"**Estás subiendo el tamaño después de perder.** La operación anterior "
        f"({instrumento}) cerró con una pérdida de {abs(resultado):,.0f} CLP "
        f"arriesgando {riesgo_anterior:,.0f}, y esta la estás dimensionando en "
        f"{nuevo:,.0f}, un {subida:.0f}% más. {TEXTO_ANTIMARTINGALA}",
        riesgo_anterior, resultado, nuevo)


def veces_que_subio_despues_de_perder(operaciones) -> tuple:
    """(veces, comparaciones_posibles) sobre el diario ya registrado.

    Recorre las operaciones cerradas en orden cronológico y cuenta los pares
    consecutivos donde la anterior perdió y la siguiente arriesgó más. El
    segundo número dice sobre cuántos pares se pudo mirar: sin él, un 0 no
    distingue "nunca pasó" de "no se pudo revisar".
    """
    cerradas = [op for op in (operaciones or [])
                if op.get("fecha_cierre") is not None
                and op.get("fecha_cierre") == op.get("fecha_cierre")]
    try:
        cerradas = sorted(cerradas, key=lambda op: op["fecha_cierre"])
    except TypeError:
        pass
    veces = comparables = 0
    for previa, siguiente in zip(cerradas, cerradas[1:]):
        resultado = _d(previa.get("resultado_clp"))
        riesgo_previo = _d(previa.get("riesgo_clp"))
        riesgo_siguiente = _d(siguiente.get("riesgo_clp"))
        if resultado is None or riesgo_previo is None or riesgo_siguiente is None:
            continue
        if riesgo_previo <= 0:
            continue
        comparables += 1
        if resultado < 0 and riesgo_siguiente > riesgo_previo:
            veces += 1
    return veces, comparables


@dataclass
class Estadisticas:
    n: int
    n_con_r: int
    expectativa_r: Decimal | None = None
    aciertos_pct: Decimal | None = None
    r_medio_ganadoras: Decimal | None = None
    r_medio_perdedoras: Decimal | None = None
    peor_racha: int = 0
    aviso: str = ""
    desglose: list = field(default_factory=list)

    @property
    def es_confiable(self) -> bool:
        return self.n >= N_MINIMO_CONFIABLE


def estadisticas(operaciones) -> Estadisticas:
    """Resumen de proceso de un conjunto de operaciones CERRADAS.

    `operaciones` es una lista de diccionarios con al menos resultado_clp y
    riesgo_clp. El aviso de "pocas operaciones" se calcula sobre n, no sobre
    los que tienen R, porque el problema es de tamaño de muestra.
    """
    operaciones = list(operaciones)
    n = len(operaciones)
    if n == 0:
        return Estadisticas(0, 0, aviso="sin operaciones cerradas")

    erres = r_multiplos_de(operaciones)
    resultados = [_d(op.get("resultado_clp")) for op in operaciones]
    con_resultado = [r for r in resultados if r is not None]

    ganadoras = [r for r in erres if r > 0]
    perdedoras = [r for r in erres if r < 0]

    aciertos = None
    if con_resultado:
        gana = sum(1 for r in con_resultado if r > 0)
        aciertos = Decimal(gana) / Decimal(len(con_resultado)) * 100

    est = Estadisticas(
        n=n,
        n_con_r=len(erres),
        expectativa_r=expectativa_r(erres),
        aciertos_pct=aciertos,
        r_medio_ganadoras=(sum(ganadoras, Decimal(0)) / len(ganadoras)) if ganadoras else None,
        r_medio_perdedoras=(sum(perdedoras, Decimal(0)) / len(perdedoras)) if perdedoras else None,
        peor_racha=peor_racha_perdidas(resultados),
    )
    if n < N_MINIMO_CONFIABLE:
        est.aviso = AVISO_POCAS
    if est.n_con_r < n:
        est.desglose.append(
            f"{n - est.n_con_r} de {n} operaciones no tienen riesgo inicial cargado, "
            f"así que no entran en los números de R.")
    return est


def estadisticas_por(operaciones, campo: str, valores_posibles=None) -> dict:
    """Las mismas estadísticas, abiertas por el valor de un campo.

    Las operaciones sin ese campo cargado quedan bajo la clave "sin dato", en
    vez de desaparecer: si la mitad del diario no tiene la tendencia anotada,
    eso es justamente lo que hay que ver.
    """
    grupos = {}
    for op in operaciones:
        clave = op.get(campo)
        if clave is None or (isinstance(clave, float) and clave != clave) or clave == "":
            clave = "sin dato"
        grupos.setdefault(clave, []).append(op)

    if valores_posibles:
        for v in valores_posibles:
            grupos.setdefault(v, [])

    return {clave: estadisticas(ops) for clave, ops in grupos.items()}


# --------------------------------------------------------------------------
# Cuadro decisión x resultado
# --------------------------------------------------------------------------
# La idea que justifica todo el módulo: con pocas operaciones el resultado es
# mayormente azar, así que premiarse por un buen resultado de una decisión
# mala es la forma más rápida de aprender lo contrario de lo que conviene.
CUADRANTES = (
    ("buena", "ganadora", "Buena decisión, buen resultado"),
    ("buena", "perdedora", "Buena decisión, mal resultado"),
    ("mala", "ganadora", "Mala decisión, buen resultado"),
    ("mala", "perdedora", "Mala decisión, mal resultado"),
)


def cuadro_decision_resultado(operaciones) -> dict:
    """{(calidad, signo): cantidad} para las cuatro casillas, más las que no
    se pueden clasificar."""
    conteo = {(c, s): 0 for c, s, _ in CUADRANTES}
    sin_clasificar = 0
    for op in operaciones:
        calidad = op.get("calidad_decision")
        resultado = _d(op.get("resultado_clp"))
        if calidad not in CALIDADES or resultado is None or resultado == 0:
            sin_clasificar += 1
            continue
        conteo[(calidad, "ganadora" if resultado > 0 else "perdedora")] += 1
    conteo["sin_clasificar"] = sin_clasificar
    return conteo


# --------------------------------------------------------------------------
# Planes de evento
# --------------------------------------------------------------------------
TOLERANCIA_PROBABILIDAD = Decimal("0.01")

PREGUNTAS_CHECKLIST = (
    "¿Entiendo las variables que fijan el precio hoy?",
    "¿Puedo leer rápido el efecto de la noticia?",
    "¿Puedo actuar rápido?",
    "¿Hay liquidez para salir si me equivoco?",
    "¿Tengo claro cuánto estoy dispuesta a perder?",
    "¿Puedo admitir un error y salir?",
)
AVISO_CHECKLIST = "Hoy conviene no operar este evento"


def validar_probabilidades(escenarios):
    """Las probabilidades de los escenarios tienen que sumar 100%.

    Devuelve (es_valido, suma, mensaje). Se admite una tolerancia mínima por
    el redondeo al escribirlas a mano.
    """
    valores = [_d(e.get("probabilidad")) for e in escenarios]
    valores = [v for v in valores if v is not None]
    if not valores:
        return False, Decimal(0), "No hay escenarios cargados."
    suma = sum(valores, Decimal(0))
    if abs(suma - Decimal(100)) <= TOLERANCIA_PROBABILIDAD:
        return True, suma, ""
    diferencia = suma - Decimal(100)
    sobra_falta = "sobra" if diferencia > 0 else "falta"
    return False, suma, (
        f"Las probabilidades suman {suma:.1f}% y tienen que sumar 100% "
        f"({sobra_falta} {abs(diferencia):.1f}).")


def valor_esperado_pips(escenarios):
    """Suma de probabilidad x movimiento esperado, en pips.

    None si los escenarios no son válidos: un valor esperado calculado sobre
    probabilidades que no suman 100% no significa nada.
    """
    valido, _suma, _msg = validar_probabilidades(escenarios)
    if not valido:
        return None
    total = Decimal(0)
    for e in escenarios:
        prob = _d(e.get("probabilidad"))
        mov = _d(e.get("movimiento_pips"))
        if prob is None or mov is None:
            return None
        total += prob / Decimal(100) * mov
    return total


def evaluar_checklist(respuestas) -> tuple:
    """`respuestas` es una lista de booleanos del largo de PREGUNTAS_CHECKLIST.
    Devuelve (puede_operar, preguntas_en_no). Es un aviso, nunca un bloqueo."""
    noes = [p for p, ok in zip(PREGUNTAS_CHECKLIST, respuestas) if not ok]
    return (not noes), noes


# --------------------------------------------------------------------------
# Eventos del torneo con plan previo
# --------------------------------------------------------------------------
# Constante VERSIONADA, no filas en la base: `evento_planes` tiene una fila
# por ESCENARIO y `escenario` es obligatorio, así que precargar un evento sin
# escenarios exigiría filas de relleno con un escenario inventado. Acá la
# constante alimenta el selector del formulario y también el par
# (evento, fecha) con el que `evento_checklist` hace su UNIQUE, para que las
# dos tablas hablen del mismo evento.
#
# Las horas son de NUEVA YORK, que es como las publican las fuentes. El
# formulario las construye con esa zona y la pantalla las muestra en hora de
# Chile: el desfase NO es constante, son +1h hasta el 1-nov y +2h después,
# porque EEUU sale del horario de verano y Chile no.
#
# NO se tocó el calendario compartido (calendario_economico.py) a propósito:
# ahí solo entran fechas publicadas por el organismo emisor, y estas tres
# están pendientes de verificar contra el Calendar de XTB.
EVENTOS_TORNEO = (
    ("IPC de EE.UU.", "2026-10-14 08:30",
     "fuente: calendario BLS; verificar antes de operar"),
    ("Decisión de la Fed", "2026-10-28 14:00",
     "fecha confirmada por la Fed (reunión del 27 y 28 de octubre); "
     "hora no confirmada: verificar en el Calendar de XTB"),
    ("Empleo de EE.UU.", "2026-11-06 08:30",
     "fuente: calendario BLS; verificar antes de operar"),
)


def eventos_torneo_con_fecha():
    """[(nombre, datetime en Nueva York, nota)], listo para el selector."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    return [
        (nombre, datetime.strptime(iso, "%Y-%m-%d %H:%M").replace(tzinfo=ny), nota)
        for nombre, iso, nota in EVENTOS_TORNEO
    ]
