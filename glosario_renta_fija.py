"""
Explicaciones en lenguaje simple para los tooltips (al pasar el mouse) de la tabla de ETFs de bonos.

Mismo criterio que glosario.py (acciones): cada texto se rellena con el número REAL de
la fila sobre la que está el mouse, nunca con un ejemplo genérico, y el nivel es el de
alguien que está aprendiendo el concepto por primera vez. Los umbrales de «alta/baja»
son una referencia cualitativa simple, no una clasificación estadística formal.

Las funciones devuelven HTML corto (<b>, <br>); glosario.tooltip_html los pone dentro del
tooltip. Si falta el dato, el texto lo dice en vez de inventar.
"""
from catalogo_renta_fija import ETFS_RENTA_FIJA, nombre_de
from formato_numerico import cifra


def explicacion_instrumento(ticker: str) -> str:
    datos = ETFS_RENTA_FIJA.get(ticker)
    if not datos:
        return f"<b>{ticker}</b>"
    return f"<b>{nombre_de(ticker)}</b><br>{datos['descripcion']}"


def explicacion_retorno(cambio_1m: float | None, ytd: float | None) -> str:
    if cambio_1m is None and ytd is None:
        return "Retorno reciente no disponible todavía."
    partes = []
    if cambio_1m is not None:
        partes.append(f"en el último mes {cifra(cambio_1m, 1, True, False)}%")
    if ytd is not None:
        partes.append(f"en lo que va del año {cifra(ytd, 1, True, False)}%")
    return (
        f"<b>Retorno:</b> {' y '.join(partes)}.<br>"
        "Incluye lo que el fondo repartió (los intereses de sus bonos): un ETF de bonos entrega buena parte de su "
        "retorno como cupones, y el precio de esta tabla ya los suma."
    )


def explicacion_duracion_medida(duracion: float | None, error: float | None, r2: float | None, plazo_referencia: int | None) -> str:
    """Tooltip de la sensibilidad empírica (I-5a: se conserva el nombre de la función por compatibilidad). La cifra es la
    pendiente de una regresión de retornos diarios contra cambios diarios de una tasa: no es la duración efectiva."""
    if duracion is None:
        return "Sensibilidad empírica no disponible todavía: falta historia de precios y tasas."
    texto = (
        f"<b>Sensibilidad empírica = {duracion:.1f} años</b>"
        + (f" (±{2 * error:.1f}, dos errores estándar)" if error is not None else "")
        + "<br>"
    )
    referencia = f" a {plazo_referencia} años" if plazo_referencia else ""
    texto += (
        f"En el último año, cuando la tasa del Tesoro{referencia} subió 1 punto porcentual, el precio de este ETF tendió a "
        f"caer cerca de {duracion:.1f}%. Es una estimación con datos históricos, no la duración efectiva del fondo: se le "
        "puede parecer en fondos del Tesoro, pero difiere si la tasa de referencia no representa su cartera, si hay riesgo "
        "de crédito o si precios y tasas no se registran a la misma hora."
    )
    if r2 is not None:
        if r2 >= 0.8:
            lectura = "la relación lineal diaria con esa tasa se ajustó muy bien en el último año"
        elif r2 >= 0.5:
            lectura = "la relación lineal diaria con esa tasa se ajustó de forma moderada: otros factores también movieron el precio"
        else:
            lectura = ("la relación lineal diaria con esa tasa se ajustó poco: el precio respondió también a factores que la "
                       "regresión no incluye (por ejemplo, spreads de crédito o ruido), sin que se pueda saber cuánto pesa cada uno")
        texto += f"<br><b>R² = {r2:.2f}:</b> {lectura}. El R² mide ajuste dentro de la muestra, no precisión ni causalidad."
    return texto


def explicacion_volatilidad(volatilidad: float | None) -> str:
    if volatilidad is None:
        return "Volatilidad no disponible todavía."
    if volatilidad > 8:
        nivel = "alta para un bono"
    elif volatilidad > 3:
        nivel = "moderada"
    else:
        nivel = "baja"
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
    if beta >= 0.2:
        lectura = "se mueve en parte junto con la bolsa, algo típico de los bonos con riesgo de crédito"
    elif beta > 0.05:
        lectura = "se mueve muy poco con la bolsa"
    elif beta >= -0.05:
        lectura = "tiene una sensibilidad estimada a la bolsa cercana a cero"
    else:
        lectura = "tiende a moverse en dirección contraria a la bolsa"
    return (
        f"<b>Beta vs S&amp;P 500 = {cifra(beta, 2, miles=False)}</b><br>"
        f"{lectura_de_beta(beta, 'este ETF')} Este ETF {lectura}. "
        "Una beta baja o negativa puede ayudar a diversificar una cartera de acciones, pero no lo garantiza: también importan la "
        "correlación, las volatilidades, el peso en la cartera y el período analizado."
    )


def lectura_de_beta(beta: float, sujeto: str) -> str:
    """H4: beta es una sensibilidad histórica estimada con una relación lineal (sin unidades): un rendimiento del índice
    1 pp mayor se asocia con un rendimiento β pp mayor del activo (menor si β es negativa). Si a dos decimales es 0.00,
    se dice que es cercana a cero, sin sugerir bajo riesgo ni independencia. Misma frase en glosario_renta_fija,
    glosario_renta_variable y glosario_commodities. Solo texto: no cambia la beta ni sus tramos."""
    magnitud = cifra(abs(beta), 2, miles=False)
    base = "Beta es una sensibilidad histórica estimada con una relación lineal; no tiene unidades."
    if magnitud == "0.00":
        return (f"{base} Aquí es cercana a cero: el rendimiento de {sujeto} casi no se asoció linealmente con el del S&amp;P 500, "
                "lo que no implica bajo riesgo ni independencia. No garantiza movimientos futuros.")
    mismo, contrario = ("mayor", "menor") if beta > 0 else ("menor", "mayor")
    return (f"{base} Según esa relación, un rendimiento del S&amp;P 500 1 punto porcentual (pp) mayor se asocia con un rendimiento "
            f"de {sujeto} unos {magnitud} pp {mismo}; uno 1 pp menor, con un rendimiento unos {magnitud} pp {contrario}. "
            "No garantiza movimientos futuros.")


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
