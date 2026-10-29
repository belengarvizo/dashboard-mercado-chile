"""
Explicaciones en lenguaje simple para los tooltips (al pasar el mouse) de las tablas de «FX y Carry Trade».

Mismo criterio que glosario.py, glosario_renta_fija.py y glosario_renta_variable.py: cada texto se rellena con el
número REAL de la fila sobre la que está el mouse, nunca con un ejemplo genérico, y el nivel es el de alguien que está
aprendiendo el concepto por primera vez. Los umbrales de «alta/baja» son una referencia cualitativa simple, no una
clasificación estadística formal.

Las funciones devuelven HTML corto (<b>, <br>); glosario.tooltip_html los pone dentro del tooltip. Si falta el dato, el
texto lo dice en vez de inventar.
"""
from catalogo_fx import MONEDAS_CARRY, PARES_FX


def explicacion_par(ticker: str) -> str:
    datos = PARES_FX.get(ticker)
    if not datos:
        return f"<b>{ticker}</b>"
    return f"<b>{datos['nombre']}</b><br>{datos['descripcion']}<br><i>El precio es: {datos['cotiza']}.</i>"


def explicacion_movimiento(ticker: str, cambio_1m: float | None, ytd: float | None) -> str:
    datos = PARES_FX.get(ticker, {})
    if cambio_1m is None and ytd is None:
        return "Movimiento reciente no disponible todavía."
    partes = []
    if cambio_1m is not None:
        partes.append(f"en el último mes {cambio_1m:+.1f}%")
    if ytd is not None:
        partes.append(f"en lo que va del año {ytd:+.1f}%")
    texto = f"<b>Movimiento:</b> {' y '.join(partes)}."
    if cambio_1m is not None and datos:
        if cambio_1m > 0.05:
            texto += f"<br>En el último mes el par subió: {datos['sube']}."
        elif cambio_1m < -0.05:
            texto += f"<br>En el último mes el par bajó: {datos['baja']}."
        else:
            texto += "<br>En el último mes el par prácticamente no se movió."
    return texto + "<br>Verde o rojo solo indica si el número subió o bajó, no si fue bueno o malo para ti."


def explicacion_volatilidad(volatilidad: float | None) -> str:
    if volatilidad is None:
        return "Volatilidad no disponible todavía."
    if volatilidad > 12:
        nivel = "alta para una divisa"
    elif volatilidad > 7:
        nivel = "moderada"
    else:
        nivel = "baja"
    return (
        f"<b>Volatilidad = {volatilidad:.1f}%</b><br>"
        f"Cuánto saltó el tipo de cambio en el último año (anualizado): aquí es {nivel}. No dice si va a subir o bajar, "
        "solo cuánto puede moverse."
    )


def explicacion_rango(rango: float | None) -> str:
    if rango is None:
        return "Rango del año no disponible todavía."
    return (
        f"<b>Rango del año = {rango:.1f}%</b><br>"
        f"Entre el precio más bajo y el más alto del último año hubo una diferencia de {rango:.1f}%. "
        "Sirve para ver cuánto se ha movido el tipo de cambio sin importar hacia qué lado."
    )


def explicacion_correlacion_referencia(correlacion: float | None, etiqueta: str, etiqueta_referencia: str,
                                       sin_convencion_comun: bool = False) -> str:
    if sin_convencion_comun:
        return (
            f"<b>Correlación con {etiqueta_referencia}</b><br>No se calcula para {etiqueta}: es un índice y usa otra convención de fecha "
            "que los pares de divisas, así que el número saldría cerca de cero aunque la relación real sea fuerte."
        )
    if correlacion is None:
        return "Correlación no disponible todavía."
    if etiqueta == etiqueta_referencia:
        return f"<b>Correlación = {correlacion:.2f}</b><br>Es el par contra sí mismo: por definición vale 1."
    if correlacion >= 0.5:
        lectura = f"tiende a subir cuando {etiqueta_referencia} sube (y a bajar cuando baja)"
    elif correlacion <= -0.5:
        lectura = f"tiende a bajar cuando {etiqueta_referencia} sube (y a subir cuando baja)"
    else:
        lectura = f"se mueve bastante por su cuenta respecto de {etiqueta_referencia}"
    return (
        f"<b>Correlación con {etiqueta_referencia} = {correlacion:.2f}</b><br>"
        f"Va de -1 (siempre al revés) a +1 (siempre igual), con los retornos diarios del último año. {etiqueta} {lectura}. "
        "Ojo con el signo: los pares que empiezan con USD y los que terminan en USD se mueven en sentido contrario cuando es el dólar el que cambia."
    )


# ---------------------------------------------------------------------------
# Carry trade
# ---------------------------------------------------------------------------
def explicacion_moneda(codigo: str, tasa: float | None, fecha: str | None) -> str:
    datos = MONEDAS_CARRY.get(codigo)
    if not datos:
        return f"<b>{codigo}</b>"
    if tasa is None:
        return f"<b>{datos['nombre']}</b><br>No hay una tasa vigente en la base para esta moneda."
    return (
        f"<b>{datos['nombre']} ({codigo})</b><br>"
        f"La tasa que se usa es la {datos['tasa']}: {tasa:.2f}%" + (f" (dato de {fecha})" if fecha else "") + "."
    )


def explicacion_diferencial(nombre: str, tasa_moneda: float | None, tasa_usd: float | None, diferencial: float | None) -> str:
    if diferencial is None or tasa_moneda is None or tasa_usd is None:
        return "Diferencial de tasas no disponible todavía."
    if diferencial >= 0:
        lectura = (
            f"Quien compra {nombre} con dólares prestados cobra {tasa_moneda:.2f}% y paga {tasa_usd:.2f}%: gana {diferencial:.2f} puntos al año "
            "por mantener la posición, siempre que el tipo de cambio no se mueva en contra."
        )
    else:
        lectura = (
            f"Quien compra {nombre} con dólares prestados cobra {tasa_moneda:.2f}% y paga {tasa_usd:.2f}%: pierde {abs(diferencial):.2f} puntos al año. "
            f"El carry está al revés: lo gana quien compra dólares y se financia en {nombre}."
        )
    return f"<b>Diferencial de tasas = {diferencial:+.2f} puntos</b><br>{lectura}"


def explicacion_spot_y_total(nombre: str, spot: float | None, carry: float | None, total: float | None) -> str:
    if spot is None or carry is None or total is None:
        return "Resultado del último año no disponible todavía."
    if spot * carry >= 0:
        pelea = " El tipo de cambio y el diferencial de tasas jugaron en el mismo sentido."
    elif abs(spot) > abs(carry):
        pelea = " El tipo de cambio se movió en sentido contrario al diferencial y decidió el resultado."
    else:
        pelea = " El tipo de cambio se movió en sentido contrario al diferencial, pero el carry pesó más."
    return (
        f"<b>Resultado del último año = {total:+.1f}%</b><br>"
        f"De ese total, {spot:+.1f}% fue lo que se movió {nombre} frente al dólar y {carry:+.1f}% fue el carry (el diferencial de tasas)."
        f"{pelea}"
    )


def explicacion_riesgo_carry(volatilidad_spot: float | None, caida_maxima: float | None, carry_sobre_riesgo: float | None) -> str:
    if volatilidad_spot is None or caida_maxima is None:
        return "Riesgo del carry no disponible todavía."
    texto = (
        f"<b>Riesgo</b><br>El tipo de cambio de esta moneda tuvo una volatilidad de {volatilidad_spot:.1f}% en el último año. "
        f"La peor caída de la posición desde un máximo previo fue de {abs(caida_maxima):.1f}%."
    )
    if carry_sobre_riesgo is not None:
        lectura = "se cobra poco por el riesgo que se corre" if abs(carry_sobre_riesgo) < 0.5 else "el diferencial paga razonablemente el riesgo cambiario"
        texto += (
            f"<br><b>Carry sobre riesgo = {carry_sobre_riesgo:.2f}</b>: el diferencial de tasas dividido por la volatilidad del tipo de cambio; "
            f"{lectura}."
        )
    return texto


def explicacion_estrategia(nombre: str, lado_hoy: str | None, estadisticas: dict | None) -> str:
    """Tooltip de una fila del paso «La estrategia y su riesgo». `lado_hoy` es «larga», «corta» o None (la cartera no tiene un solo lado)."""
    if not estadisticas:
        return f"<b>{nombre}</b><br>No hay datos suficientes en este período."
    texto = f"<b>{nombre}</b><br>"
    if lado_hoy == "larga":
        texto += "Hoy la estrategia está larga en esta moneda: su tasa supera a la de EEUU, así que compra la moneda y se financia en dólares.<br>"
    elif lado_hoy == "corta":
        texto += "Hoy la estrategia está corta en esta moneda: su tasa es menor que la de EEUU, así que se financia en ella y compra dólares.<br>"
    texto += (
        f"En el período ({estadisticas['dias']} ruedas) ganó {estadisticas['anualizado']:+.1f}% al año con una volatilidad de "
        f"{estadisticas['volatilidad']:.1f}%. Su peor caída desde un máximo fue de {abs(estadisticas['caida_maxima']):.1f}%."
    )
    if estadisticas.get("peor_mes") is not None and estadisticas.get("fecha_peor_mes") is not None:
        texto += (
            f"<br><b>Peor mes:</b> {estadisticas['peor_mes']:+.1f}% (21 ruedas terminadas el {estadisticas['fecha_peor_mes']:%d-%m-%Y}). "
            f"En {estadisticas['meses_ganadores']:.0f}% de los meses calendario ganó."
        )
    return texto
