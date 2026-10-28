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
        partes.append(f"en el último mes {cambio_1m:+.1f}%")
    if ytd is not None:
        partes.append(f"en lo que va del año {ytd:+.1f}%")
    return (
        f"<b>Retorno:</b> {' y '.join(partes)}.<br>"
        "Incluye lo que el fondo repartió (los intereses de sus bonos): un ETF de bonos entrega buena parte de su "
        "retorno como cupones, y el precio de esta tabla ya los suma."
    )


def explicacion_duracion_medida(duracion: float | None, error: float | None, r2: float | None, plazo_referencia: int | None) -> str:
    if duracion is None:
        return "Duración medida no disponible todavía: falta historia de precios y tasas."
    texto = (
        f"<b>Duración medida = {duracion:.1f} años</b>"
        + (f" (±{2 * error:.1f})" if error is not None else "")
        + "<br>"
    )
    referencia = f" a {plazo_referencia} años" if plazo_referencia else ""
    texto += (
        f"En el último año, cada vez que la tasa del Tesoro{referencia} subió 1 punto porcentual, el precio de este "
        f"ETF cayó cerca de {duracion:.1f}%. Es la sensibilidad a las tasas, medida con datos reales y no con la "
        "ficha del fondo."
    )
    if r2 is not None:
        if r2 >= 0.8:
            lectura = "casi todo lo que se mueve su precio lo explican las tasas"
        elif r2 >= 0.5:
            lectura = "las tasas explican buena parte de su movimiento, pero también pesa el riesgo de crédito"
        else:
            lectura = "lo mueve más el riesgo de crédito y el ánimo del mercado que las tasas, así que esta duración es poco confiable"
        texto += f"<br><b>R² = {r2:.2f}:</b> {lectura}."
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
        lectura = "prácticamente no depende de lo que haga la bolsa"
    else:
        lectura = "tiende a moverse al revés de la bolsa"
    return (
        f"<b>Beta vs S&amp;P 500 = {beta:.2f}</b><br>"
        f"Si el S&amp;P 500 sube o baja 1%, este ETF tiende a moverse {beta:+.2f}%: {lectura}. "
        "Mientras más baja, más sirve para diversificar una cartera de acciones."
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
