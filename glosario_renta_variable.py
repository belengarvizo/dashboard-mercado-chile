"""
Explicaciones en lenguaje simple para los tooltips (al pasar el mouse) de las tablas de ETFs de acciones.

Mismo criterio que glosario.py (acciones) y glosario_renta_fija.py (bonos): cada texto se rellena con el
número REAL de la fila sobre la que está el mouse, nunca con un ejemplo genérico, y el nivel es el de
alguien que está aprendiendo el concepto por primera vez. Los umbrales de «alta/baja» son una referencia
cualitativa simple, no una clasificación estadística formal.

Las funciones devuelven HTML corto (<b>, <br>); glosario.tooltip_html los pone dentro del tooltip. Si
falta el dato, el texto lo dice en vez de inventar.
"""
from catalogo_etfs_acciones import ETFS_ACCIONES, nombre_de


def explicacion_instrumento(ticker: str) -> str:
    datos = ETFS_ACCIONES.get(ticker)
    if not datos:
        return f"<b>{ticker}</b>"
    return f"<b>{nombre_de(ticker)}</b><br>{datos['descripcion']}"


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
        "Incluye los dividendos que el fondo repartió: el precio de esta tabla ya los suma."
    )


def explicacion_volatilidad(volatilidad: float | None) -> str:
    if volatilidad is None:
        return "Volatilidad no disponible todavía."
    if volatilidad > 30:
        nivel = "alta"
    elif volatilidad > 18:
        nivel = "moderada"
    else:
        nivel = "baja para un ETF de acciones"
    return (
        f"<b>Volatilidad = {volatilidad:.1f}%</b><br>"
        f"Cuánto saltó el precio en el último año (anualizado): aquí es {nivel}. No dice si va a subir o bajar, "
        "solo cuánto puede moverse."
    )


def explicacion_caida_maxima(caida: float | None) -> str:
    if caida is None:
        return "Caída máxima no disponible todavía."
    return (
        f"<b>Caída máxima = {caida:.1f}%</b><br>"
        f"La peor baja desde un máximo previo dentro del último año: quien hubiera comprado en el punto más alto "
        f"y visto el punto más bajo habría tenido una pérdida de {abs(caida):.1f}%."
    )


def explicacion_beta(beta: float | None) -> str:
    if beta is None:
        return "Beta no disponible todavía: falta historia de precios."
    if beta > 1.1:
        lectura = "amplifica los movimientos de la bolsa: sube más cuando ella sube y cae más cuando ella cae"
    elif beta >= 0.9:
        lectura = "se mueve casi igual que la bolsa"
    elif beta >= 0.5:
        lectura = "amortigua los movimientos de la bolsa: sube y cae menos que ella"
    else:
        lectura = "casi no depende de lo que haga la bolsa de EEUU"
    return (
        f"<b>Beta vs S&amp;P 500 = {beta:.2f}</b><br>"
        f"Si el S&amp;P 500 sube o baja 1%, este ETF tiende a moverse {beta:.2f}%: {lectura}. "
        "Se mide con SPY, el ETF del S&amp;P 500, en el último año."
    )


def explicacion_correlacion(correlacion: float | None) -> str:
    if correlacion is None:
        return "Correlación no disponible todavía: falta historia de precios."
    if correlacion >= 0.85:
        lectura = "casi siempre sube y baja el mismo día que la bolsa, así que diversifica poco"
    elif correlacion >= 0.5:
        lectura = "en general se mueve en la misma dirección que la bolsa, pero con días propios"
    elif correlacion >= 0.2:
        lectura = "se mueve solo en parte con la bolsa: aporta diversificación"
    elif correlacion > -0.2:
        lectura = "prácticamente se mueve por su cuenta respecto de la bolsa"
    else:
        lectura = "tiende a moverse al revés de la bolsa"
    return (
        f"<b>Correlación = {correlacion:.2f}</b><br>"
        f"Va de -1 (siempre al revés) a +1 (siempre igual). Aquí {lectura}. "
        "El beta dice cuánto se mueve; la correlación, cuán parecidos son los días."
    )


def explicacion_relativo(diferencia_pp: float | None, retorno_1a: float | None) -> str:
    if diferencia_pp is None:
        return "Comparación con el S&P 500 no disponible todavía."
    if abs(diferencia_pp) < 0.05:
        lectura = "rindió prácticamente lo mismo que el S&amp;P 500"
    elif diferencia_pp > 0:
        lectura = f"rindió {diferencia_pp:.1f} puntos porcentuales MÁS que el S&amp;P 500"
    else:
        lectura = f"rindió {abs(diferencia_pp):.1f} puntos porcentuales MENOS que el S&amp;P 500"
    propio = f" ({retorno_1a:+.1f}% propio)" if retorno_1a is not None else ""
    return (
        f"<b>Contra el S&amp;P 500 = {diferencia_pp:+.1f} pp</b><br>"
        f"En el último año este ETF {lectura}{propio}. Es solo un año: no basta para decir que un sector o un "
        "país \"es mejor\"; los líderes cambian de un año a otro."
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
        f"Retorno extra del último año sobre la tasa libre de riesgo{base}, por cada unidad de volatilidad. "
        f"Aquí la relación es {lectura}."
    )
