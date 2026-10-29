"""
Explicaciones en lenguaje simple para los tooltips (al pasar el mouse) de la tabla de «Commodities».

Mismo criterio que los demás glosarios del dashboard: cada texto se rellena con el número REAL de la fila sobre la
que está el mouse, nunca con un ejemplo genérico. La diferencia con glosario_renta_variable.py: estos instrumentos
son futuros, no ETFs, así que no hay dividendos que sumar al retorno ni "composición de un fondo" que explicar.

Las funciones devuelven HTML corto (<b>, <br>); glosario.tooltip_html los pone dentro del tooltip. Si falta el dato,
el texto lo dice en vez de inventar.
"""
from catalogo_commodities import COMMODITIES, nombre_de


def explicacion_instrumento(ticker: str) -> str:
    datos = COMMODITIES.get(ticker)
    if not datos:
        return f"<b>{ticker}</b>"
    return f"<b>{nombre_de(ticker)}</b><br>{datos['descripcion']}<br><i>Se cotiza en {datos['unidad']}.</i>"


def explicacion_retorno(cambio_1m: float | None, ytd: float | None) -> str:
    if cambio_1m is None and ytd is None:
        return "Retorno reciente no disponible todavía."
    partes = []
    if cambio_1m is not None:
        partes.append(f"en el último mes {cambio_1m:+.1f}%")
    if ytd is not None:
        partes.append(f"en lo que va del año {ytd:+.1f}%")
    return (
        f"<b>Retorno:</b> {' y '.join(partes)}.<br>"
        "Es el precio del contrato de futuro más cercano a vencer (el que se usa como referencia del mercado real). "
        "No hay dividendos que sumar: todo el retorno es el movimiento del precio."
    )


def explicacion_volatilidad(volatilidad: float | None) -> str:
    if volatilidad is None:
        return "Volatilidad no disponible todavía."
    if volatilidad > 35:
        nivel = "alta"
    elif volatilidad > 18:
        nivel = "moderada"
    else:
        nivel = "baja"
    return (
        f"<b>Volatilidad = {volatilidad:.1f}%</b><br>"
        f"Cuánto saltó el precio en el último año (anualizado): aquí es {nivel}. Los agrícolas y el gas natural suelen moverse más que "
        "los metales preciosos, porque dependen del clima de una cosecha o de una temporada."
    )


def explicacion_caida_maxima(caida: float | None) -> str:
    if caida is None:
        return "Caída máxima no disponible todavía."
    return (
        f"<b>Caída máxima = {caida:.1f}%</b><br>"
        f"La peor baja desde un máximo previo dentro del último año: quien hubiera comprado en el punto más alto y visto el punto "
        f"más bajo habría tenido una pérdida de {abs(caida):.1f}%."
    )


def explicacion_beta(beta: float | None) -> str:
    if beta is None:
        return "Beta no disponible todavía: falta historia de precios."
    if beta > 0.3:
        lectura = "se mueve en parte junto con la bolsa: cuando el mercado está optimista, también sube"
    elif beta > -0.1:
        lectura = "casi no depende de lo que haga la bolsa de EEUU"
    else:
        lectura = "tiende a moverse al revés de la bolsa, lo que lo vuelve útil para diversificar"
    return (
        f"<b>Beta vs S&amp;P 500 = {beta:.2f}</b><br>"
        f"Si el S&amp;P 500 sube o baja 1%, este commodity tiende a moverse {beta:+.2f}%: {lectura}. "
        "Casi todos los commodities tienen un beta bajo: sus precios responden más a oferta y demanda física que al humor de la bolsa."
    )


def explicacion_correlacion(correlacion: float | None) -> str:
    if correlacion is None:
        return "Correlación no disponible todavía: falta historia de precios."
    if correlacion >= 0.5:
        lectura = "en general se mueve en la misma dirección que la bolsa"
    elif correlacion >= 0.2:
        lectura = "se mueve solo en parte con la bolsa: aporta diversificación"
    elif correlacion > -0.2:
        lectura = "prácticamente se mueve por su cuenta respecto de la bolsa"
    else:
        lectura = "tiende a moverse al revés de la bolsa"
    return (
        f"<b>Correlación con el S&amp;P 500 = {correlacion:.2f}</b><br>"
        f"Va de -1 (siempre al revés) a +1 (siempre igual). Aquí {lectura}."
    )


def explicacion_sharpe(sharpe: float | None, tasa_libre_de_riesgo: float | None) -> str:
    if sharpe is None:
        return "Sharpe no disponible todavía: falta el retorno del último año o la volatilidad."
    if sharpe > 1:
        lectura = "buena: ganó bastante más de lo que arriesgó"
    elif sharpe > 0:
        lectura = "moderada: ganó algo más de lo que arriesgó"
    else:
        lectura = "mala: no compensó el riesgo, rindió menos que la tasa libre de riesgo"
    base = f" (la tasa de política de EEUU, {tasa_libre_de_riesgo:.2f}%)" if tasa_libre_de_riesgo is not None else ""
    return (
        f"<b>Sharpe = {sharpe:.2f}</b><br>"
        f"Retorno extra del último año sobre la tasa libre de riesgo{base}, por cada unidad de volatilidad. Aquí la relación es {lectura}."
    )
