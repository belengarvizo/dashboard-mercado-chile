"""Correlación entre pares y riesgo agrupado de las posiciones abiertas.

LA IDEA. Dos posiciones muy correlacionadas no son dos apuestas: son la
misma apuesta puesta dos veces. Un riesgo del 1% en EURUSD y otro 1% en
GBPUSD, con correlación de 0,9, se comportan como casi un 2% en una sola
cosa. El panel de riesgo que suma por instrumento no ve eso.

CÓMO SE AGREGA EL RIESGO DE UN GRUPO. Con la forma cuadrática de siempre en
riesgo de cartera: raíz(r' C r), donde r es el vector de riesgos con signo
según la dirección (compra +, venta -) y C es la matriz de correlaciones
entre las posiciones del grupo.

NO es lo mismo que sumar y restar los montos. Restar supondría cobertura
perfecta, y eso solo ocurre con correlación de exactamente -1. Con 100.000
en EURUSD y 80.000 en USDCHF, las dos a la compra y con correlación real de
-0,706, la resta daría 20.000 y la fórmula da 71.442: la cobertura es
parcial y lo que queda expuesto es más de tres veces mayor. Con
correlaciones de +1 o -1 las dos cuentas coinciden, que es el caso límite.

ES UNA ESTIMACIÓN, no una medición. Usa la correlación de los últimos 60
días; si el mercado cambia de régimen, la cobertura puede ser menor que la
que este número supone. Por eso en pantalla se rotula "estimado".

POR QUÉ NO SE REUSA calcular_retornos_reales. Esa función excluye los días
de precio repetido usando el volumen, y Yahoo devuelve volumen 0 para todos
los pares de divisas (verificado: las 3.618 filas de FX están en cero). Con
ese criterio descartaría TODOS los días planos. Acá los retornos son un
pct_change simple y la desactualización se detecta por la fecha del último
dato, no por el volumen.

Módulo puro: no importa Streamlit ni toca la base.
"""
import math
from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np
import pandas as pd

VENTANA_CORRELACION = 60
UMBRAL_AGRUPACION = 0.7
# Mínimo de retornos en común para que una correlación signifique algo. Con
# menos, el número sale igual pero es ruido: dos series de 5 puntos dan
# correlaciones altísimas por casualidad.
MINIMO_OBSERVACIONES = 20

# POR QUÉ EL ÍNDICE DÓLAR QUEDA FUERA DE LA MATRIZ.
# Las series de Yahoo terminadas en "=X" y el índice DX-Y.NYB no comparten
# convención de fecha: la fila de un día no corresponde a la misma rueda. Se
# verificó con los datos ya guardados, sin recurrir a ninguna fuente externa:
#
#   1) Las identidades de cruce entre los pares =X calzan en desfase 0:
#      r(EURGBP) contra r(EURUSD)-r(GBPUSD) da +0,9954; r(EURJPY) contra
#      r(EURUSD)+r(USDJPY), +0,9995; r(GBPJPY), +0,9997. Los 13 pares son
#      consistentes entre sí.
#   2) Un DXY sintético reconstruido desde esos mismos pares con los pesos
#      públicos de la canasta (EUR 57,6% JPY 13,6% GBP 11,9% CAD 9,1%
#      CHF 3,6%) calza con el DX-Y.NYB guardado en desfase -1 con +0,9415,
#      y solo +0,0377 en desfase 0.
#
# Correlacionarlo en la misma fila mezcla dos días distintos: contra EURUSD
# daba -0,05, cuando la relación real es fuertemente negativa (el euro pesa
# más de la mitad del índice). Un -0,05 en pantalla se leería como "no
# tienen nada que ver", que es falso.
#
# NO se corrige desplazando la serie: alinear datos a partir de un ajuste de
# correlación es una suposición, y si Yahoo cambia la convención el arreglo
# se convierte en el error. La posición en USDIDX sigue contando en el
# riesgo total y por dirección; lo único que no se hace es agruparla.
TICKERS_SIN_CONVENCION_COMUN = frozenset({"DX-Y.NYB"})

COMPRA, VENTA = "compra", "venta"


def retornos_diarios(df_precios: pd.DataFrame, ventana: int = VENTANA_CORRELACION) -> pd.DataFrame:
    """Tabla de retornos diarios por ticker, con las últimas `ventana` ruedas.

    `df_precios` es el formato de la base: columnas ticker, fecha,
    precio_cierre.
    """
    if df_precios is None or df_precios.empty:
        return pd.DataFrame()
    df = df_precios.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    pivote = (df.pivot_table(index="fecha", columns="ticker", values="precio_cierre",
                             aggfunc="last")
                .sort_index())
    # +1 fila porque el primer retorno necesita un cierre previo.
    pivote = pivote.tail(ventana + 1)
    return pivote.pct_change().dropna(how="all")


def matriz_correlacion(df_precios: pd.DataFrame, ventana: int = VENTANA_CORRELACION,
                       excluir=TICKERS_SIN_CONVENCION_COMUN):
    """(matriz, observaciones_por_par). La matriz usa observaciones
    pairwise-completas: cada par se correlaciona con las fechas en que ambos
    tienen retorno, sin exigir que los 13 coincidan el mismo día.

    Una serie CONSTANTE (todos los retornos iguales, típicamente cero) tiene
    desviación cero y su correlación es indefinida: pandas devuelve NaN y
    acá se deja NaN en vez de convertirlo a 0, que se leería como "no están
    correlacionados" cuando en realidad no se sabe.

    `excluir` deja fuera las series que no comparten convención de fecha con
    el resto; ver TICKERS_SIN_CONVENCION_COMUN.
    """
    retornos = retornos_diarios(df_precios, ventana)
    if not retornos.empty and excluir:
        retornos = retornos.drop(columns=[c for c in retornos.columns if c in excluir])
    if retornos.empty or retornos.shape[1] < 2:
        return pd.DataFrame(), pd.DataFrame()
    matriz = retornos.corr(min_periods=MINIMO_OBSERVACIONES)
    observaciones = retornos.notna().astype(int).T.dot(retornos.notna().astype(int))
    return matriz, observaciones


def correlacion_entre(matriz: pd.DataFrame, a: str, b: str):
    """La correlación entre dos tickers, o None si no se puede saber."""
    if matriz is None or matriz.empty:
        return None
    if a not in matriz.index or b not in matriz.columns:
        return None
    valor = matriz.loc[a, b]
    if valor is None or pd.isna(valor):
        return None
    return float(valor)


@dataclass
class Grupo:
    """Posiciones que, por su correlación, son en los hechos una sola apuesta.

    `riesgo_agrupado` es la ESTIMACIÓN raíz(r' C r); `riesgo_bruto` es la
    suma sin compensar, que es lo que muestra el control de riesgo abierto.
    """
    posiciones: list = field(default_factory=list)
    riesgo_agrupado: Decimal = Decimal(0)
    riesgo_bruto: Decimal = Decimal(0)
    detalle: list = field(default_factory=list)

    @property
    def es_apuesta_unica(self) -> bool:
        return len(self.posiciones) > 1


def _signo(direccion: str) -> int:
    return 1 if direccion == COMPRA else -1


def _nombre(p) -> str:
    """El nombre del catálogo (EURUSD), no el ticker de Yahoo (EURUSD=X):
    esto se lee en pantalla."""
    return p.get("instrumento") or p["ticker"]


def _correlaciones_del_grupo(miembros, matriz):
    """(C, parejas_sin_dato) para las posiciones de un grupo.

    RELLENO PRUDENTE. Una pareja sin correlación conocida se completa con el
    valor que hace CRECER el riesgo: +1 si las dos van en el mismo sentido,
    -1 si van en sentidos contrarios. En los dos casos el término cruzado
    termina sumando. Rellenar con 0 diría "son independientes", que es una
    afirmación que no se tiene.
    """
    n = len(miembros)
    C = np.ones((n, n))
    sin_dato = set()
    for i in range(n):
        for j in range(i + 1, n):
            c = correlacion_entre(matriz, miembros[i]["ticker"], miembros[j]["ticker"])
            if c is None:
                sin_dato.add((i, j))
                mismo = (_signo(miembros[i]["direccion"])
                         == _signo(miembros[j]["direccion"]))
                c = 1.0 if mismo else -1.0
            C[i, j] = C[j, i] = c
    return C, sin_dato


def riesgo_agrupado_de(miembros, matriz) -> Decimal:
    """raíz(r' C r), con el vector de riesgos firmado por la dirección.

    Se acota en cero antes de la raíz. La matriz se estima pareja por pareja,
    con distinta cantidad de ruedas en cada una, así que NO está garantizado
    que sea semidefinida positiva: la forma cuadrática puede dar un número
    levemente negativo por el método de estimación, no porque el riesgo lo
    sea.
    """
    if not miembros:
        return Decimal(0)
    C, _sin_dato = _correlaciones_del_grupo(miembros, matriz)
    r = np.array([_signo(p["direccion"]) * float(abs(Decimal(str(p["riesgo_clp"]))))
                  for p in miembros])
    varianza = float(r @ C @ r)
    return Decimal(str(round(math.sqrt(max(varianza, 0.0)), 2)))


def agrupar_por_correlacion(posiciones, matriz, umbral: float = UMBRAL_AGRUPACION) -> list:
    """Agrupa posiciones abiertas cuya correlación en valor absoluto SUPERE el
    umbral.

    Estrictamente mayor: en el umbral exacto NO se agrupa. Es una decisión
    deliberada — el umbral es el límite de lo tolerado, así que 0,7 con
    umbral 0,7 todavía está dentro.

    `posiciones` es una lista de dicts con ticker, direccion y riesgo_clp.

    El riesgo del grupo sale de riesgo_agrupado_de(): raíz(r' C r), sin
    ninguna posición de referencia. Cada pareja aporta según el signo de
    signo(dirección i) x signo(dirección j) x correlación(i, j): comprar dos
    pares correlacionados positivamente SUMA; comprar uno y vender el otro
    COMPENSA; y comprar dos pares de correlación negativa también compensa,
    porque cuando uno sube el otro baja.
    """
    posiciones = [p for p in posiciones if p.get("riesgo_clp") is not None]
    if not posiciones:
        return []

    # Componentes conexas: si A se parece a B y B a C, los tres van juntos
    # aunque A y C no lleguen al umbral entre sí.
    n = len(posiciones)
    padre = list(range(n))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            c = correlacion_entre(matriz, posiciones[i]["ticker"], posiciones[j]["ticker"])
            if c is not None and abs(c) > umbral:
                padre[raiz(i)] = raiz(j)

    por_raiz = {}
    for i, p in enumerate(posiciones):
        por_raiz.setdefault(raiz(i), []).append(p)

    grupos = []
    for miembros in por_raiz.values():
        bruto = sum((abs(Decimal(str(p["riesgo_clp"]))) for p in miembros), Decimal(0))
        agrupado = riesgo_agrupado_de(miembros, matriz)

        detalle = [
            f"{_nombre(p)} {p['direccion']} "
            f"{abs(Decimal(str(p['riesgo_clp']))):,.0f} CLP"
            for p in miembros
        ]
        if len(miembros) > 1:
            C, sin_dato = _correlaciones_del_grupo(miembros, matriz)
            for i in range(len(miembros)):
                for j in range(i + 1, len(miembros)):
                    # El signo del término cruzado de r' C r para esta pareja
                    # dice si suma o si compensa, sin depender de ninguna
                    # posición de referencia.
                    cruce = (_signo(miembros[i]["direccion"])
                             * _signo(miembros[j]["direccion"]) * C[i, j])
                    efecto = ("suman" if cruce > 0
                              else "se compensan" if cruce < 0 else "no se afectan")
                    medida = ("correlación sin dato, se asume la peor"
                              if (i, j) in sin_dato
                              else f"correlación {C[i, j]:+.2f}")
                    detalle.append(
                        f"{_nombre(miembros[i])} ↔ {_nombre(miembros[j])} "
                        f"· {medida} → {efecto}")
        grupos.append(Grupo(miembros, agrupado, bruto, detalle))
    return sorted(grupos, key=lambda g: -g.riesgo_agrupado)


def posiciones_desde_diario(abiertas, instrumento_a_ticker: dict) -> list:
    """Convierte las filas abiertas del diario en la lista que esperan las
    funciones de arriba.

    Solo entran las posiciones que tienen ticker conocido Y riesgo cargado.
    Las demás se devuelven aparte para poder decir en pantalla cuántas
    quedaron fuera: callarlas haría que el riesgo agrupado se leyera como
    completo cuando no lo es.
    """
    adentro, afuera = [], []
    if abiertas is None or len(abiertas) == 0:
        return adentro, afuera
    for _, fila in abiertas.iterrows():
        nombre = fila.get("instrumento")
        ticker = instrumento_a_ticker.get(nombre)
        riesgo = fila.get("riesgo_clp")
        if ticker is None or riesgo is None or pd.isna(riesgo) or pd.isna(ticker):
            afuera.append(nombre)
            continue
        adentro.append({
            "ticker": str(ticker),
            "instrumento": str(nombre),
            "direccion": fila.get("direccion"),
            "riesgo_clp": Decimal(str(riesgo)),
        })
    return adentro, afuera


def resumen(grupos):
    """(riesgo_bruto_total, mayor_riesgo_agrupado, grupos_de_mas_de_uno).

    El número que importa al lado del riesgo total NO es la suma de los
    grupos: es el MAYOR, porque representa la apuesta más grande que está
    corriendo en los hechos.
    """
    bruto = sum((g.riesgo_bruto for g in grupos), Decimal(0))
    mayor = max((g.riesgo_agrupado for g in grupos), default=Decimal(0))
    racimos = [g for g in grupos if g.es_apuesta_unica]
    return bruto, mayor, racimos


def riesgo_por_direccion(posiciones) -> dict:
    """Riesgo total comprometido en compras y en ventas, por separado.

    Es el otro corte que importa: tener todo el riesgo del mismo lado del
    mercado es una apuesta direccional, aunque los instrumentos sean
    distintos.
    """
    totales = {COMPRA: Decimal(0), VENTA: Decimal(0)}
    for p in posiciones:
        if p.get("riesgo_clp") is None:
            continue
        direccion = p.get("direccion")
        if direccion in totales:
            totales[direccion] += abs(Decimal(str(p["riesgo_clp"])))
    return totales


@dataclass
class Alerta:
    nivel: str      # "verde" | "amarillo" | "rojo"
    texto: str


def evaluar_limites(grupos, posiciones, tope_grupo_clp, tope_direccion_clp) -> list:
    """Advertencias por grupo y por dirección. Nunca bloquea nada."""
    alertas = []
    tope_grupo = Decimal(str(tope_grupo_clp)) if tope_grupo_clp else None
    tope_direccion = Decimal(str(tope_direccion_clp)) if tope_direccion_clp else None

    for g in grupos:
        if not g.es_apuesta_unica:
            continue
        # El nombre del catálogo (EURUSD), no el de Yahoo (EURUSD=X).
        tickers = ", ".join(sorted({p.get("instrumento") or p["ticker"]
                                    for p in g.posiciones}))
        if tope_grupo and g.riesgo_agrupado > tope_grupo:
            alertas.append(Alerta("rojo",
                f"El grupo {tickers} tiene {g.riesgo_agrupado:,.0f} CLP de riesgo "
                f"agrupado estimado, sobre el tope de {tope_grupo:,.0f}. Estas "
                f"posiciones se comportan como una sola apuesta."))
        elif tope_grupo and g.riesgo_agrupado > tope_grupo * Decimal("0.8"):
            alertas.append(Alerta("amarillo",
                f"El grupo {tickers} va en {g.riesgo_agrupado:,.0f} CLP, cerca del tope de "
                f"{tope_grupo:,.0f}."))

    if tope_direccion:
        for direccion, total in riesgo_por_direccion(posiciones).items():
            if total > tope_direccion:
                alertas.append(Alerta("rojo",
                    f"Riesgo en {direccion}s: {total:,.0f} CLP, sobre el tope de "
                    f"{tope_direccion:,.0f}. Todo el riesgo del mismo lado del mercado es "
                    f"una apuesta direccional, aunque los instrumentos sean distintos."))
            elif total > tope_direccion * Decimal("0.8"):
                alertas.append(Alerta("amarillo",
                    f"Riesgo en {direccion}s: {total:,.0f} CLP, cerca del tope de "
                    f"{tope_direccion:,.0f}."))
    return alertas
