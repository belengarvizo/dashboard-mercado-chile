"""Cálculo del valor del pip y del tamaño de posición en CLP para el módulo
de trading. Módulo puro: no importa Streamlit, así que es testeable sin app.

POR QUÉ ESTE MÓDULO DEVUELVE UN DESGLOSE Y NO UN NÚMERO. Un error en el valor
del pip se traduce uno a uno en un error de tamaño de posición, y en el torneo
de XTB pasarse del 30% del margen por subyacente descalifica. Así que ninguna
función devuelve un número suelto: devuelven el resultado junto con las tasas
usadas, sus fechas, la cadena de conversión y los supuestos que quedaron en
pie, para que todo sea auditable contra el ticket de XTB.

Y CUANDO NO SE PUEDE, NO SE INVENTA. Si falta el tamaño del pip, o si no hay
forma de llegar a CLP con las cotizaciones disponibles, las funciones
devuelven `None` con el motivo. Nunca un valor por defecto.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# Un lote estándar = 100.000 unidades de la divisa BASE.
#
# QUÉ TAN SOSTENIDO ESTÁ ESTE NÚMERO, con precisión. Se contrastó contra un
# ticket real de XTB (0,01 lotes de EURUSD a 1,11995 = 1.099.995 CLP de valor
# de posición). Ese contraste NO confirma la fórmula completa: la tasa USD/CLP
# se dedujo del propio valor de posición, así que reproducirlo es circular.
#
# Lo que sí aporta evidencia es otra cosa. Primero, la tasa implícita que sale
# de ese ticket (982,18) cae a 0,06% del dólar observado del Banco Central
# para la misma fecha (981,61) — una fuente independiente. Y segundo, por
# descarte: con un contrato de 10.000 unidades el USD/CLP implícito sería
# 9.822, y con 1.000.000 sería 98; solo 100.000 da una tasa creíble. Eso
# sostiene el tamaño de contrato DE EURUSD con bastante fuerza.
#
# Para los demás instrumentos sigue siendo un supuesto de mercado sin
# verificar: cada uno necesita que se lea su propio ticket.
TAMANO_CONTRATO_ESTANDAR = Decimal("100000")
CONTRATO_CONFIRMADO = frozenset({"EURUSD"})

# A partir de cuántos días una cotización de la base se considera vieja. El
# cron corre una vez al día y los fines de semana no hay datos de FX, así que
# 3 días cubre un lunes sin alarmar de más.
DIAS_TASA_VIEJA = 3

# Cómo llegar de cada divisa a USD con los pares que el cron ya descarga.
# ("TICKER", "directo")  -> la divisa es la BASE del par: X/USD, se multiplica.
# ("TICKER", "inverso")  -> la divisa es la COTIZACIÓN: USD/X, se divide.
RUTA_A_USD = {
    "USD": None,  # ya está en USD
    "EUR": ("EURUSD=X", "directo"),
    "GBP": ("GBPUSD=X", "directo"),
    "AUD": ("AUDUSD=X", "directo"),
    "NZD": ("NZDUSD=X", "directo"),
    "JPY": ("USDJPY=X", "inverso"),
    "CAD": ("USDCAD=X", "inverso"),
    "CHF": ("USDCHF=X", "inverso"),
    "BRL": ("USDBRL=X", "inverso"),
    "MXN": ("USDMXN=X", "inverso"),
}
TICKER_USDCLP = "USDCLP=X"


@dataclass
class Tasa:
    """Una conversión a CLP, con la cuenta completa a la vista."""
    divisa: str
    valor: Decimal                      # cuántos CLP vale 1 unidad de `divisa`
    pasos: list[str] = field(default_factory=list)
    fecha_mas_vieja: date | None = None
    manual: bool = False

    def esta_vieja(self, hoy: date) -> bool:
        if self.manual or self.fecha_mas_vieja is None:
            return False
        return (hoy - self.fecha_mas_vieja).days > DIAS_TASA_VIEJA


@dataclass
class ResultadoCalculo:
    """Lo que se le muestra al usuario. `valor` es None cuando no se pudo
    calcular; `motivo` dice por qué, y nunca se sustituye por un default."""
    valor: Decimal | None
    motivo: str = ""
    pasos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


# Divisas que aparecen en los pares del catálogo de XTB. Se exige que AMBAS
# mitades del nombre estén acá: sin esta lista, "USDIDX" (el índice dólar, que
# también tiene 6 letras) se parseaba como el par USD/IDX y el error terminaba
# saliendo mucho después, como "no se puede convertir IDX a CLP", en vez del
# mensaje correcto de que no es un par.
DIVISAS_CONOCIDAS = frozenset({
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CLP", "BRL", "MXN",
    "COP", "CNH", "INR", "TRY", "ZAR", "SGD", "THB", "ILS", "NOK", "SEK", "PLN",
    "CZK", "HUF", "RON",
})


def es_nulo(x) -> bool:
    """True si el valor falta. Cubre None y NaN.

    El NaN importa: los datos llegan de la base vía pandas, y un NULL de SQL
    se convierte en NaN (un float), no en None. Con un chequeo `is None` a
    secas, un pip sin cargar pasaba el filtro y el cálculo seguía adelante
    devolviendo NaN — es decir, mostraba "nan lotes" en vez de negarse, que
    es exactamente lo contrario de lo que este módulo promete. Lo encontró
    tests/test_divisas_seccion.py, no la revisión.
    """
    if x is None:
        return True
    return x != x  # solo NaN es distinto de sí mismo


def divisas_del_par(nombre_xtb: str) -> tuple[str, str] | None:
    """('EUR', 'USD') para EURUSD. None si no es un par de divisas — por
    ejemplo USDIDX, que es el índice dólar y no tiene divisa de cotización."""
    nombre = (nombre_xtb or "").strip().upper()
    if len(nombre) != 6 or not nombre.isalpha():
        return None
    base, cotizacion = nombre[:3], nombre[3:]
    if base == cotizacion:
        return None
    if base not in DIVISAS_CONOCIDAS or cotizacion not in DIVISAS_CONOCIDAS:
        return None
    return base, cotizacion


def tasa_a_clp(divisa: str, cotizaciones: dict, manual: Decimal | None = None) -> Tasa | None:
    """Cuántos CLP vale una unidad de `divisa`, encadenando por USD.

    `cotizaciones` es {ticker: (precio, fecha)} con lo que hay en la base.
    `manual` permite pisar el resultado con la tasa que el usuario ve en XTB.
    Devuelve None si falta alguna pata de la cadena: no se inventa un valor.
    """
    divisa = (divisa or "").strip().upper()
    if not es_nulo(manual):
        return Tasa(divisa, Decimal(str(manual)), [f"{divisa}/CLP = {manual} (ingresada a mano)"], None, True)

    if divisa == "CLP":
        return Tasa(divisa, Decimal(1), ["CLP/CLP = 1"], None)

    if TICKER_USDCLP not in cotizaciones:
        return None
    usdclp, fecha_usdclp = cotizaciones[TICKER_USDCLP]
    usdclp = Decimal(str(usdclp))

    if divisa == "USD":
        return Tasa(divisa, usdclp, [f"USD/CLP = {usdclp} ({fecha_usdclp})"], fecha_usdclp)

    if divisa not in RUTA_A_USD:
        return None
    ticker, sentido = RUTA_A_USD[divisa]
    if ticker not in cotizaciones:
        return None
    precio, fecha = cotizaciones[ticker]
    precio = Decimal(str(precio))
    if precio <= 0:
        return None

    par = ticker.replace("=X", "")
    if sentido == "directo":
        en_usd = precio
        paso = f"{divisa}/USD = {precio} (de {par}, {fecha})"
    else:
        en_usd = Decimal(1) / precio
        paso = f"{divisa}/USD = 1 / {precio} = {en_usd:.8f} (de {par}, {fecha})"

    valor = en_usd * usdclp
    pasos = [paso, f"USD/CLP = {usdclp} ({fecha_usdclp})",
             f"{divisa}/CLP = {en_usd:.8f} x {usdclp} = {valor:.4f}"]
    fechas = [f for f in (fecha, fecha_usdclp) if f is not None]
    return Tasa(divisa, valor, pasos, min(fechas) if fechas else None)


def _avisos_de_tasa(tasa: Tasa, hoy: date, etiqueta: str) -> list[str]:
    if tasa.esta_vieja(hoy):
        dias = (hoy - tasa.fecha_mas_vieja).days
        return [f"La tasa de {etiqueta} es del {tasa.fecha_mas_vieja} ({dias} días): "
                f"revísala contra XTB o ingrésala a mano."]
    return []


def valor_pip_clp(nombre_xtb: str, lotes, pip_tamano, cotizaciones: dict,
                  hoy: date, tasa_manual: Decimal | None = None) -> ResultadoCalculo:
    """Cuántos CLP vale un pip para `lotes` lotes del par dado."""
    par = divisas_del_par(nombre_xtb)
    if par is None:
        return ResultadoCalculo(None, f"{nombre_xtb} no es un par de divisas: no tiene pip.")
    _base, cotizacion = par

    if es_nulo(pip_tamano):
        return ResultadoCalculo(
            None,
            f"El tamaño del pip de {nombre_xtb} está PENDIENTE. No se calcula con un "
            f"supuesto: en este par, errar el pip por un factor de 100 erraría el "
            f"tamaño de la posición por 100. Cárgalo desde el ticket de XTB.")

    tasa = tasa_a_clp(cotizacion, cotizaciones, tasa_manual)
    if tasa is None:
        return ResultadoCalculo(
            None, f"No hay forma de convertir {cotizacion} a CLP con las cotizaciones "
                  f"disponibles. Ingresa la tasa {cotizacion}/CLP a mano.")

    lotes = Decimal(str(lotes))
    pip_tamano = Decimal(str(pip_tamano))
    unidades = TAMANO_CONTRATO_ESTANDAR * lotes
    pip_en_cotizacion = unidades * pip_tamano
    valor = pip_en_cotizacion * tasa.valor

    pasos = [
        f"Unidades = {TAMANO_CONTRATO_ESTANDAR:,.0f} x {lotes} lotes = {unidades:,.2f} {par[0]}",
        f"1 pip = {pip_tamano} {cotizacion} por unidad",
        f"Pip en {cotizacion} = {unidades:,.2f} x {pip_tamano} = {pip_en_cotizacion:,.4f} {cotizacion}",
    ] + tasa.pasos + [
        f"Pip en CLP = {pip_en_cotizacion:,.4f} x {tasa.valor:.4f} = {valor:,.2f} CLP"
    ]

    avisos = _avisos_de_tasa(tasa, hoy, f"{cotizacion}/CLP")
    if nombre_xtb.upper() not in CONTRATO_CONFIRMADO:
        avisos.append(
            f"Tamaño de contrato de {TAMANO_CONTRATO_ESTANDAR:,.0f} unidades por lote: "
            f"SUPUESTO. Solo está confirmado para EURUSD. Confirmalo con el ticket.")
    return ResultadoCalculo(valor, "", pasos, avisos)


def valor_posicion_clp(nombre_xtb: str, lotes, precio, cotizaciones: dict,
                       hoy: date, tasa_manual: Decimal | None = None) -> ResultadoCalculo:
    """Valor nocional de la posición en CLP: lo que XTB muestra en el ticket."""
    par = divisas_del_par(nombre_xtb)
    if par is None:
        return ResultadoCalculo(None, f"{nombre_xtb} no es un par de divisas.")
    base, _cotizacion = par

    tasa = tasa_a_clp(base, cotizaciones, tasa_manual)
    if tasa is None:
        return ResultadoCalculo(
            None, f"No hay forma de convertir {base} a CLP con las cotizaciones "
                  f"disponibles. Ingresa la tasa {base}/CLP a mano.")

    lotes = Decimal(str(lotes))
    unidades = TAMANO_CONTRATO_ESTANDAR * lotes
    valor = unidades * tasa.valor

    pasos = [
        f"Unidades = {TAMANO_CONTRATO_ESTANDAR:,.0f} x {lotes} lotes = {unidades:,.2f} {base}",
    ] + tasa.pasos + [
        f"Valor de posición = {unidades:,.2f} {base} x {tasa.valor:.4f} = {valor:,.2f} CLP"
    ]
    avisos = _avisos_de_tasa(tasa, hoy, f"{base}/CLP")
    if nombre_xtb.upper() not in CONTRATO_CONFIRMADO:
        avisos.append(
            f"Tamaño de contrato de {TAMANO_CONTRATO_ESTANDAR:,.0f} unidades por lote: "
            f"SUPUESTO. Solo está confirmado para EURUSD.")
    if precio is not None:
        pasos.append(
            f"(precio de referencia del par: {precio} — el valor de posición se calcula "
            f"sobre la divisa BASE, así que el precio del par no entra en esta cuenta)")
    return ResultadoCalculo(valor, "", pasos, avisos)


def lotes_para_riesgo(nombre_xtb: str, riesgo_clp, distancia_pips, pip_tamano,
                      cotizaciones: dict, hoy: date,
                      tasa_manual: Decimal | None = None) -> ResultadoCalculo:
    """Cuántos lotes arriesgan exactamente `riesgo_clp` si el stop está a
    `distancia_pips` del precio de entrada."""
    distancia_pips = Decimal(str(distancia_pips))
    if distancia_pips <= 0:
        return ResultadoCalculo(None, "La distancia al stop tiene que ser mayor que cero.")

    por_lote = valor_pip_clp(nombre_xtb, 1, pip_tamano, cotizaciones, hoy, tasa_manual)
    if por_lote.valor is None:
        return ResultadoCalculo(None, por_lote.motivo, por_lote.pasos, por_lote.avisos)

    riesgo_clp = Decimal(str(riesgo_clp))
    riesgo_por_lote = por_lote.valor * distancia_pips
    lotes = riesgo_clp / riesgo_por_lote

    pasos = por_lote.pasos + [
        f"Riesgo de 1 lote = {por_lote.valor:,.2f} CLP/pip x {distancia_pips} pips "
        f"= {riesgo_por_lote:,.2f} CLP",
        f"Lotes = {riesgo_clp:,.0f} CLP / {riesgo_por_lote:,.2f} = {lotes:.4f}",
    ]
    return ResultadoCalculo(lotes, "", pasos, list(por_lote.avisos))
