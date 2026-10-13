"""ATR de Wilder (14) para dimensionar el stop.

CUÁL ES LA CIFRA PRINCIPAL, Y POR QUÉ. La principal es el ATR del RANGO DEL
DÍA (máximo menos mínimo). La del rango verdadero queda como secundaria.

Se eligió así después de medir contra xStation el 12-10-2026, ATR(14)
diario, penúltima vela:

    par       xStation   rango del día   rango verdadero
    EURUSD     53,4 pips   55,6  (-4%)     65,5  (+23%)
    USDJPY     90,3 pips  100,0 (-10%)    117,9  (+31%)

El rango del día SE PARECE MÁS. No se afirma que coincida: son dos pares en
una fecha, y la diferencia que queda puede venir de que xStation incluya el
lunes y de cómo promedia.

Esto es consistente con lo que ya se había medido por otro lado: el término
de hueco aporta entre 14% y 39% del ATR en los pares =X y solo 1,4% en el
índice dólar, que es el único ticker del grupo que NO es una serie =X y el
único sin cierres fuera de rango. Las divisas operan casi 24 horas, así que
deberían tener huecos MÁS chicos que un instrumento que cierra y reabre: que
pase lo contrario apunta a que parte de ese hueco es desfase de la fuente.

Las dos cifras usan el mismo suavizado de Wilder, para que la comparación
mida la diferencia entre las dos definiciones de rango y no entre dos formas
de promediar.


PARA QUÉ SIRVE Y PARA QUÉ NO. Esto dimensiona el stop: dice cuánto se mueve
un par en una rueda típica, para no poner el stop dentro del ruido normal.
NO es una señal: no dice si comprar o vender, ni cuándo.

EL RANGO VERDADERO de una rueda, que es la cifra SECUNDARIA, es el mayor de
tres distancias:

    máximo - mínimo
    |máximo - cierre previo|
    |mínimo  - cierre previo|

Las dos últimas existen para que un hueco entre ruedas cuente como
movimiento. Sin ellas, un par que abre lejos del cierre anterior y después
se mueve poco parecería tranquilo.

EL PROMEDIO ES EL DE WILDER, no una media simple de los últimos 14. Wilder
suaviza:

    ATR_hoy = (ATR_ayer * 13 + rango_verdadero_hoy) / 14

sembrado con la media simple de los primeros 14 rangos. La diferencia con
la media simple no es cosmética: medida sobre un año real de datos, va de
+0,1% en EURJPY a +13,4% en AUDUSD. Se eligió Wilder porque es el suavizado
original del indicador y el más extendido. NO se afirma que coincida con el
número de ninguna plataforma en particular: para eso habría que comparar
contra ella, y eso no se hizo.

Módulo PURO: no importa Streamlit, no toca la base y no llama a la red.

CUANDO NO SE PUEDE CALCULAR DEVUELVE None, nunca un número de relleno. Un
ATR inventado haría poner un stop con una confianza que no existe.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

PERIODO_ATR = 14
# Un ATR necesita PERIODO_ATR rangos verdaderos, y el primer rango necesita
# un cierre previo: PERIODO_ATR + 1 ruedas como mínimo absoluto.
MINIMO_RUEDAS = PERIODO_ATR + 1

MULTIPLO_STOP_POR_DEFECTO = Decimal("1.5")

# Un día con rango mayor a este múltiplo de la MEDIANA del par se marca como
# sospechoso. Mediana y no promedio: el promedio ya estaría contaminado por
# los días que se quieren detectar.
FACTOR_DIA_SOSPECHOSO = 3

# Un par se marca solo cuando sus días raros mueven su ATR MÁS que esto, en
# porcentaje.
#
# POR QUÉ NO ALCANZA CON CONTARLOS. Con el factor en 3x, los 14 pares tienen
# al menos un día así en un año: es lo normal. Marcarlos a todos es no marcar
# a ninguno. Lo que importa no es que existan sino que muevan el número que
# se usa para dimensionar el stop. Medido sobre el año guardado, solo USDBRL
# pasa el 5%: sus 2 días lo inflan 11,7%, mientras que USDCLP, con 14 días,
# lo mueve 0,57% y EURUSD, con 2, no lo mueve nada.
UMBRAL_INFLACION_MATERIAL = Decimal("5")
# Por debajo del umbral material, todavia hay dos situaciones distintas: que
# los dias raros muevan el ATR un poco o que no lo muevan nada. Decir "no
# cambian" cuando mueven un 2% seria afirmar de mas.
UMBRAL_INFLACION_PERCEPTIBLE = Decimal("0.5")

# Más de esto sin un dato nuevo y el par se considera desactualizado.
#
# SE CUENTA EN RUEDAS HÁBILES, NO EN DÍAS CORRIDOS. Con días corridos, todos
# los lunes los 14 pares saldrían desactualizados: del cierre del viernes al
# lunes hay 3 días corridos pero 1 sola rueda. Un guardián que da la alarma
# todos los lunes se termina ignorando. Medido: viernes->lunes = 1 rueda;
# viernes->miércoles con el cron caído dos días = 3 ruedas, que sí avisa.
RUEDAS_PARA_DESACTUALIZADO = 2

# Un hueco mayor a esto entre dos ruedas guardadas rompe la continuidad del
# cierre previo. Cinco días corridos cubren un fin de semana largo.
DIAS_HUECO_MAXIMO = 5


# --------------------------------------------------------------- ruedas
def solo_ruedas_cerradas(historico: pd.DataFrame, hoy: date) -> pd.DataFrame:
    """Saca la vela del día en curso, que todavía se está formando.

    Yahoo entrega una fila para el día de hoy con el máximo y el mínimo de
    lo que va corrido de la sesión. Guardar eso sería guardar medio día como
    si fuera una rueda completa, y el ATR quedaría subestimado justo en el
    dato más reciente. Se descarta todo lo que tenga fecha de hoy o
    posterior.

    `hoy` entra como argumento, no se lee del reloj acá: así la función es
    comprobable y la fecha puede formar parte de la clave de una caché.
    """
    if historico is None or len(historico) == 0:
        return historico if historico is not None else pd.DataFrame()
    fechas = pd.to_datetime(historico.index)
    # El índice de Yahoo viene con zona horaria (+01:00 en los pares =X). Se
    # le quita para poder comparar contra una fecha sin zona. La comparación
    # se hace en la zona del propio índice, que es la de la rueda.
    if getattr(fechas, "tz", None) is not None:
        fechas = fechas.tz_localize(None)
    return historico[fechas.date < hoy]


def filas_validas(historico: pd.DataFrame) -> pd.DataFrame:
    """Deja solo las ruedas con máximo, mínimo y cierre utilizables.

    Descarta los NaN (Yahoo los devuelve para sesiones incompletas) y los
    máximos menores que el mínimo, que es un dato roto por definición.

    NO DESCARTA la rueda cuando el cierre cae fuera de [mínimo, máximo].
    Parece un dato roto y es tentador filtrarlo, pero descartar la sesión
    entera es peor que el defecto: se pierde una rueda real Y se abre un
    hueco, y el hueco infla el rango verdadero del día siguiente, porque el
    "cierre previo" pasa a ser el de hace dos o tres días.

    Medido sobre un año de los 14 pares: 128 de 3.605 ruedas (3,5%) tienen
    el cierre fuera de su propio rango. En casi todas la diferencia es
    minúscula —entre 0,005% y 0,04% del precio, que es 1% a 5% del rango del
    día— y corresponde a que Yahoo toma el cierre de los pares =X en un
    momento distinto del que usa para el máximo y el mínimo. Las
    excepciones grandes están concentradas en USDCLP, que ya es la serie de
    peor calidad del grupo.

    Para contar cuántas vienen así está cierres_fuera_de_rango().
    """
    if historico is None or len(historico) == 0:
        return pd.DataFrame()
    columnas = {"High", "Low", "Close"}
    if not columnas.issubset(historico.columns):
        return pd.DataFrame()
    df = historico.dropna(subset=["High", "Low", "Close"])
    return df[df["High"] >= df["Low"]]


def cierres_fuera_de_rango(historico: pd.DataFrame) -> int:
    """Cuántas ruedas traen el cierre fuera de [mínimo, máximo].

    No se descartan (ver filas_validas), pero se cuentan: es la medida de
    cuánta confianza merece la serie de ese par.
    """
    if historico is None or len(historico) == 0:
        return 0
    if not {"High", "Low", "Close"}.issubset(historico.columns):
        return 0
    df = historico.dropna(subset=["High", "Low", "Close"])
    fuera = (df["Close"] < df["Low"]) | (df["Close"] > df["High"])
    return int(fuera.sum())


# ------------------------------------------------------- rango verdadero
def rango_verdadero(maximos, minimos, cierres) -> pd.Series:
    """El rango verdadero de cada rueda. La primera queda en NaN: no tiene
    cierre previo contra el cual medir."""
    maximos = pd.Series(maximos, dtype="float64").reset_index(drop=True)
    minimos = pd.Series(minimos, dtype="float64").reset_index(drop=True)
    cierres = pd.Series(cierres, dtype="float64").reset_index(drop=True)
    cierre_previo = cierres.shift(1)
    return pd.concat([
        maximos - minimos,
        (maximos - cierre_previo).abs(),
        (minimos - cierre_previo).abs(),
    ], axis=1).max(axis=1).where(cierre_previo.notna())


def rango_del_dia(maximos, minimos) -> pd.Series:
    """Solo máximo menos mínimo, sin los términos de hueco.

    POR QUÉ EXISTE, además del rango verdadero. En los pares =X el término de
    hueco aporta entre 14% y 39% del ATR, mientras que en el índice dólar
    —el único ticker del grupo que NO es una serie =X y el único sin cierres
    fuera de rango— aporta 1,4%. Está al revés de lo que predice el mercado:
    las divisas operan casi 24 horas y deberían tener huecos MÁS chicos que
    un instrumento que cierra y reabre. Así que parte de ese hueco es el
    desfase entre el cierre y el máximo/mínimo de Yahoo, no movimiento.

    Esta cifra es inmune a ese desfase. Se muestra al lado de la principal
    para poder compararlas, no para reemplazarla.
    """
    maximos = pd.Series(maximos, dtype="float64").reset_index(drop=True)
    minimos = pd.Series(minimos, dtype="float64").reset_index(drop=True)
    return maximos - minimos


def dias_sospechosos(maximos, minimos, factor: int = FACTOR_DIA_SOSPECHOSO) -> int:
    """Cuántos días tienen un rango mayor a `factor` veces la mediana del par."""
    rango = rango_del_dia(maximos, minimos).dropna()
    if len(rango) == 0:
        return 0
    mediana = float(rango.median())
    if mediana <= 0:
        return 0
    return int((rango > mediana * factor).sum())


def inflacion_por_dias_sospechosos(maximos, minimos,
                                  factor: int = FACTOR_DIA_SOSPECHOSO,
                                  periodo: int = PERIODO_ATR):
    """Cuánto infla el ATR tener días de rango anormal, en porcentaje.

    Compara el ATR normal contra el que sale recortando esos días a `factor`
    veces la mediana. Se RECORTA en vez de sacarlos: sacarlos abriría huecos
    en la serie, y el hueco distorsiona por su cuenta.

    Se mide sobre el rango del día, que es la cifra principal: es la que se
    usa para dimensionar el stop y la que importa que no esté inflada.

    None si no se puede calcular.
    """
    rango = rango_del_dia(maximos, minimos).dropna()
    if len(rango) < periodo:
        return None
    mediana = float(rango.median())
    if mediana <= 0:
        return None
    normal = atr_wilder(rango, periodo)
    recortado = atr_wilder(rango.clip(upper=mediana * factor), periodo)
    if normal is None or recortado is None or recortado <= 0:
        return None
    return (normal / recortado - Decimal(1)) * 100


def atr_wilder(rangos, periodo: int = PERIODO_ATR):
    """El ATR de Wilder sobre una serie de rangos verdaderos ya calculados.

    None si no alcanzan los datos. La semilla es la media simple de los
    primeros `periodo` rangos; de ahí en adelante, el suavizado.
    """
    serie = pd.Series(rangos, dtype="float64").dropna()
    if periodo < 1 or len(serie) < periodo:
        return None
    valor = float(serie.iloc[:periodo].mean())
    for siguiente in serie.iloc[periodo:]:
        valor = (valor * (periodo - 1) + float(siguiente)) / periodo
    if valor != valor or valor < 0:
        return None
    return Decimal(str(round(valor, 10)))


# ------------------------------------------------------------- resultado
@dataclass
class ResultadoATR:
    """El ATR de un par y todo lo que hace falta para leerlo con criterio.

    `valor` es el ATR del RANGO DEL DÍA, que es la cifra principal, en
    unidades de precio; None cuando no se pudo calcular, y entonces `motivo`
    dice por qué. `valor_rango_verdadero` es la secundaria.

    `pips` es None cuando el catálogo no tiene el tamaño del pip de ese par:
    no se inventa un divisor.
    """
    ticker: str
    # PRINCIPAL: sobre el rango del día (máximo - mínimo).
    valor: Decimal = None
    pips: Decimal = None
    # SECUNDARIA: sobre el rango verdadero, con el mismo suavizado.
    valor_rango_verdadero: Decimal = None
    pips_rango_verdadero: Decimal = None
    sospechosos: int = 0
    inflacion_sospechosos: Decimal = None   # en %, sobre la cifra principal
    porcentaje: Decimal = None
    ultima_fecha: date = None
    ruedas: int = 0
    motivo: str = ""
    aviso_pips: str = ""
    dias_sin_actualizar: int = None      # corridos, para el texto
    ruedas_sin_actualizar: int = None    # hábiles, para decidir si avisa
    huecos: int = 0

    @property
    def hay_atr(self) -> bool:
        return self.valor is not None

    @property
    def sospechosos_materiales(self) -> bool:
        """True solo si los días raros mueven el ATR más que el umbral.

        Tenerlos no basta: casi todos los pares tienen alguno. Lo que se
        avisa es que cambien el número con el que se dimensiona el stop.
        """
        return (self.sospechosos > 0
                and self.inflacion_sospechosos is not None
                and self.inflacion_sospechosos > UMBRAL_INFLACION_MATERIAL)

    @property
    def texto_sospechosos(self) -> str:
        """La marca, diciendo cuánto inflan. Vacía si no es material."""
        if not self.sospechosos_materiales:
            return ""
        dias = (f"{self.sospechosos} día raro infla" if self.sospechosos == 1
                else f"{self.sospechosos} días raros inflan")
        return f"{dias} su ATR en {self.inflacion_sospechosos:.0f}%"

    @property
    def desactualizado(self) -> bool:
        return (self.ruedas_sin_actualizar is not None
                and self.ruedas_sin_actualizar > RUEDAS_PARA_DESACTUALIZADO)


MOTIVO_SIN_FILAS = "no hay ruedas guardadas de este par"
MOTIVO_POCAS = (f"hacen falta al menos {MINIMO_RUEDAS} ruedas cerradas y hay")
AVISO_SIN_PIP = "pips: falta tamaño del pip en el catálogo"


def _d(x):
    if x is None:
        return None
    try:
        d = x if isinstance(x, Decimal) else Decimal(str(x))
    except Exception:
        return None
    return None if d != d else d


def contar_huecos(fechas, dias_maximo: int = DIAS_HUECO_MAXIMO) -> int:
    """Cuántos saltos mayores a `dias_maximo` hay entre ruedas consecutivas.

    Importa porque el cierre previo sale de la fila anterior: si entre dos
    filas faltan ruedas, ese "cierre previo" es de hace varios días y el
    rango verdadero de esa rueda queda inflado.
    """
    ordenadas = sorted(f for f in fechas if f is not None)
    return sum(1 for a, b in zip(ordenadas, ordenadas[1:])
               if (b - a).days > dias_maximo)


def atr_de_rangos(ticker: str, filas, pip_tamano=None, hoy: date = None,
                  periodo: int = PERIODO_ATR) -> ResultadoATR:
    """Calcula el ATR de un par a partir de sus filas guardadas.

    `filas` es una lista de dicts con fecha, maximo, minimo y cierre, o un
    DataFrame con esas columnas. Se ordena por fecha acá: no se confía en
    que venga ordenado.
    """
    if isinstance(filas, pd.DataFrame):
        filas = filas.to_dict("records") if not filas.empty else []
    filas = [f for f in (filas or []) if f.get("fecha") is not None]
    if not filas:
        return ResultadoATR(ticker, motivo=MOTIVO_SIN_FILAS)

    filas = sorted(filas, key=lambda f: f["fecha"])
    fechas = [f["fecha"] for f in filas]
    ultima = fechas[-1]
    huecos = contar_huecos(fechas)
    dias = (hoy - ultima).days if hoy is not None else None
    ruedas_atras = (int(np.busday_count(ultima, hoy))
                    if hoy is not None and hoy >= ultima else
                    (0 if hoy is not None else None))

    if len(filas) < MINIMO_RUEDAS:
        return ResultadoATR(ticker, ultima_fecha=ultima, ruedas=len(filas),
                            motivo=f"{MOTIVO_POCAS} {len(filas)}",
                            dias_sin_actualizar=dias,
                            ruedas_sin_actualizar=ruedas_atras, huecos=huecos)

    maximos = [f["maximo"] for f in filas]
    minimos = [f["minimo"] for f in filas]
    cierres = [f["cierre"] for f in filas]
    # PRINCIPAL: el rango del día. SECUNDARIA: el rango verdadero. Las dos
    # con el mismo suavizado de Wilder, para que la comparación mida la
    # diferencia entre las dos definiciones de rango y no entre dos formas de
    # promediar.
    valor = atr_wilder(rango_del_dia(maximos, minimos), periodo)
    valor_tr = atr_wilder(rango_verdadero(maximos, minimos, cierres), periodo)
    sospechosos = dias_sospechosos(maximos, minimos)
    inflacion = inflacion_por_dias_sospechosos(maximos, minimos)
    if valor is None:
        return ResultadoATR(ticker, ultima_fecha=ultima, ruedas=len(filas),
                            motivo=f"{MOTIVO_POCAS} {len(filas)}",
                            dias_sin_actualizar=dias,
                            ruedas_sin_actualizar=ruedas_atras, huecos=huecos)

    pip = _d(pip_tamano)
    hay_pip = bool(pip and pip > 0)
    pips = valor / pip if hay_pip else None
    pips_tr = valor_tr / pip if hay_pip and valor_tr is not None else None
    aviso = "" if pips is not None else AVISO_SIN_PIP

    ultimo_cierre = _d(filas[-1]["cierre"])
    porcentaje = (valor / ultimo_cierre * 100
                  if ultimo_cierre and ultimo_cierre > 0 else None)

    return ResultadoATR(ticker, valor, pips, valor_tr, pips_tr, sospechosos,
                        inflacion, porcentaje, ultima, len(filas),
                        aviso_pips=aviso, dias_sin_actualizar=dias,
                        ruedas_sin_actualizar=ruedas_atras, huecos=huecos)


# ------------------------------------------------------------ el stop
def stop_sugerido(atr: ResultadoATR, multiplo=MULTIPLO_STOP_POR_DEFECTO):
    """(stop_en_precio, stop_en_pips) sobre la cifra PRINCIPAL. None donde no
    se pueda.

    Es una REFERENCIA de distancia, no un nivel: dice cuánto espacio dejarle
    al ruido normal del par, no dónde está el soporte.
    """
    if atr is None or not atr.hay_atr:
        return None, None
    m = _d(multiplo)
    if m is None or m <= 0:
        return None, None
    en_precio = atr.valor * m
    en_pips = atr.pips * m if atr.pips is not None else None
    return en_precio, en_pips


def stop_demasiado_cerca(precio_entrada, stop, atr: ResultadoATR):
    """(esta_cerca, distancia_en_atr) sobre la cifra PRINCIPAL. None cuando
    falta algo.

    Un stop a menos de 1 ATR de la entrada está dentro del movimiento normal
    de una rueda: lo más probable es que salte por ruido y no porque la
    tesis se haya roto.
    """
    entrada, nivel = _d(precio_entrada), _d(stop)
    if entrada is None or nivel is None or atr is None or not atr.hay_atr:
        return None, None
    if atr.valor <= 0:
        return None, None
    distancia = abs(entrada - nivel)
    if distancia <= 0:
        return None, None
    en_atr = distancia / atr.valor
    return en_atr < 1, en_atr
