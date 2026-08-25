"""
Glosario de tickers y plantillas de explicación educativa para los
tooltips (hover) integrados en los heatmaps de "Acciones IPSA" y
"Acciones Dow Jones". Vive fuera de app/dashboard.py para no mezclar
datos/plantillas con lógica de Streamlit, mismo criterio que
market_data.py.

Los nombres completos son datos verificados (no inventados): los 30 del
IPSA se cruzaron contra topforeignstocks.com/indices/components-of-the-
chile-ipsa-index/ y una búsqueda específica para el caso ambiguo
(ITAUCL: "Itaú Corpbanca" hasta 2023, renombrado a "Banco Itaú Chile" en
marzo 2023 — se usa el nombre vigente). Los 30 del Dow Jones son
empresas globales sin ambigüedad de nombre.

Deliberadamente NO incluye (fuera de alcance, a pedido explícito):
- Expectativas de mercado / consenso de analistas: no hay una fuente
  confiable de eso para acciones chilenas en este proyecto.
- Atribución de shocks de noticias específica por acción individual:
  requeriría una regresión por acción (30 modelos), no una frase.
  explicacion_atribucion() conecta con el modelo ya construido
  (market_data.calcular_atribucion_ipsa) solo a través de la Beta de la
  fila — la relación general "Beta alta → se mueve más que el promedio
  del mercado ante shocks globales", nunca una atribución inventada
  para ESA acción puntual.
"""

NOMBRE_COMPLETO_POR_TICKER: dict[str, str] = {
    # --- IPSA (30) ---
    "AGUAS-A.SN": "Aguas Andinas S.A.",
    "ANDINA-B.SN": "Embotelladora Andina S.A. (Serie B)",
    "BCI.SN": "Banco de Crédito e Inversiones (BCI)",
    "BSANTANDER.SN": "Banco Santander Chile",
    "CAP.SN": "CAP S.A.",
    "CCU.SN": "Compañía Cervecerías Unidas S.A. (CCU)",
    "CENCOMALLS.SN": "Cencosud Shopping Centers S.A.",
    "CENCOSUD.SN": "Cencosud S.A.",
    "CHILE.SN": "Banco de Chile",
    "CMPC.SN": "Empresas CMPC S.A.",
    "COLBUN.SN": "Colbún S.A.",
    "CONCHATORO.SN": "Viña Concha y Toro S.A.",
    "COPEC.SN": "Empresas Copec S.A.",
    "ECL.SN": "Engie Energía Chile S.A.",
    "ENELAM.SN": "Enel Américas S.A.",
    "ENELCHILE.SN": "Enel Chile S.A.",
    "ENTEL.SN": "Empresa Nacional de Telecomunicaciones S.A. (Entel)",
    "FALABELLA.SN": "S.A.C.I. Falabella",
    "IAM.SN": "IAM S.A. (Inversiones Aguas Metropolitanas)",
    "ILC.SN": "Inversiones La Construcción S.A.",
    "ITAUCL.SN": "Banco Itaú Chile",
    "LTM.SN": "LATAM Airlines Group S.A.",
    "MALLPLAZA.SN": "Plaza S.A. (Mallplaza)",
    "PARAUCO.SN": "Parque Arauco S.A.",
    "QUINENCO.SN": "Quiñenco S.A.",
    "RIPLEY.SN": "Ripley Corp S.A.",
    "SALFACORP.SN": "SalfaCorp S.A.",
    "SMU.SN": "SMU S.A.",
    "SQM-B.SN": "Sociedad Química y Minera de Chile S.A. (SQM), Serie B",
    "VAPORES.SN": "Compañía Sud Americana de Vapores S.A. (CSAV)",
    # --- Dow Jones (30) ---
    "AAPL": "Apple Inc.",
    "AMGN": "Amgen Inc.",
    "AMZN": "Amazon.com, Inc.",
    "AXP": "American Express Company",
    "BA": "The Boeing Company",
    "CAT": "Caterpillar Inc.",
    "CRM": "Salesforce, Inc.",
    "CSCO": "Cisco Systems, Inc.",
    "CVX": "Chevron Corporation",
    "DIS": "The Walt Disney Company",
    "GOOGL": "Alphabet Inc. (Google)",
    "GS": "The Goldman Sachs Group, Inc.",
    "HD": "The Home Depot, Inc.",
    "HON": "Honeywell International Inc.",
    "IBM": "International Business Machines Corporation",
    "JNJ": "Johnson & Johnson",
    "JPM": "JPMorgan Chase & Co.",
    "KO": "The Coca-Cola Company",
    "MCD": "McDonald's Corporation",
    "MMM": "3M Company",
    "MRK": "Merck & Co., Inc.",
    "MSFT": "Microsoft Corporation",
    "NKE": "NIKE, Inc.",
    "NVDA": "NVIDIA Corporation",
    "PG": "The Procter & Gamble Company",
    "SHW": "The Sherwin-Williams Company",
    "TRV": "The Travelers Companies, Inc.",
    "UNH": "UnitedHealth Group Incorporated",
    "V": "Visa Inc.",
    "WMT": "Walmart Inc.",
}


def nombre_completo(ticker_sn_o_plano: str) -> str:
    """Busca el nombre completo probando primero el ticker tal cual (Dow
    Jones, sin sufijo) y luego con sufijo ".SN" (IPSA, cuyo índice de
    fila ya viene sin el sufijo). Si no está en el diccionario, devuelve
    el ticker mismo — nunca inventa un nombre."""
    if ticker_sn_o_plano in NOMBRE_COMPLETO_POR_TICKER:
        return NOMBRE_COMPLETO_POR_TICKER[ticker_sn_o_plano]
    return NOMBRE_COMPLETO_POR_TICKER.get(f"{ticker_sn_o_plano}.SN", ticker_sn_o_plano)


def explicacion_rendimiento(cambio_1m: float | None) -> str:
    """Rendimiento reciente en texto simple (requisito 2): una sola
    línea, sin jerga — "esta acción subió/bajó X% en el último mes"."""
    if cambio_1m is None:
        return "Rendimiento del último mes no disponible todavía."
    if cambio_1m > 0.05:
        verbo = "subió"
    elif cambio_1m < -0.05:
        verbo = "bajó"
    else:
        verbo = "se mantuvo prácticamente igual"
    return f"<b>Último mes:</b> esta acción {verbo} {abs(cambio_1m):.1f}% en el último mes."


def explicacion_beta(beta: float | None, beta_ajustada: float | None = None) -> str:
    """Explicación de Beta en 2-3 líneas, rellenada con el número REAL de
    una fila específica del heatmap — no un ejemplo genérico. Nivel:
    alguien que está aprendiendo el concepto por primera vez.

    Deliberadamente corta: la primera versión de este tooltip incluía
    también Beta ajustada como párrafo aparte y el texto terminaba
    ocupando ~650px de alto, saliéndose de la pantalla hacia arriba en
    filas cercanas al borde superior del viewport — confirmado con un
    screenshot real dentro de Streamlit, no algo que se dedujo leyendo el
    CSS. `beta_ajustada` se acepta por compatibilidad de la firma pero ya
    no se usa en el texto, para mantener el tooltip corto."""
    if beta is None:
        return "Beta no disponible todavía: falta historia de precios para calcularla."
    if beta > 1.05:
        comparacion = "más volátil que el mercado"
    elif beta < 0.95:
        comparacion = "menos volátil que el mercado"
    else:
        comparacion = "casi tan volátil como el mercado"
    return (
        f"<b>Beta = {beta:.2f}</b><br>"
        f"Si el mercado sube o baja 1%, esta acción tiende a moverse {beta:.2f}% — es "
        f"{comparacion}. Mide el riesgo que no se elimina diversificando."
    )


def explicacion_capm(capm_local: float | None, capm_crp: float | None = None) -> str:
    """Explicación de CAPM en 2-3 líneas, con el número REAL de esa fila.
    Igual de corta que explicacion_beta y por el mismo motivo — ver su
    docstring. `capm_crp` se acepta por compatibilidad pero no se usa acá."""
    if capm_local is None:
        return "CAPM no disponible todavía: falta algún dato (Beta o tasas) para calcularlo."
    return (
        f"<b>CAPM = {capm_local:.2f}%</b><br>"
        f"Retorno anual mínimo que, según este modelo, debería exigir un inversionista "
        f"por el riesgo de esta acción. Si no rinde al menos {capm_local:.2f}% al año en "
        "el largo plazo, no compensa ese riesgo."
    )


def explicacion_volatilidad(volatilidad_anualizada: float | None) -> str:
    """Volatilidad explicada como "propensión a sorpresas" (requisito
    4), con el número real de la fila. Los umbrales alta/moderada/baja
    son una referencia cualitativa simple para el nivel "recién
    aprendiendo el concepto", no una clasificación estadística formal."""
    if volatilidad_anualizada is None:
        return "Volatilidad no disponible todavía."
    if volatilidad_anualizada > 35:
        nivel = "alta"
    elif volatilidad_anualizada > 20:
        nivel = "moderada"
    else:
        nivel = "baja"
    return (
        f"<b>Volatilidad = {volatilidad_anualizada:.1f}%</b><br>"
        f"Qué tan propensa es esta acción a movimientos inesperados o sorpresivos en el "
        f"precio — acá es {nivel}. No dice si va a subir o bajar, solo cuánto puede saltar."
    )


def explicacion_alfa(alpha: float | None, retorno_real_1y: float | None = None, capm: float | None = None) -> str:
    """Alpha de Jensen simplificado (r_i - r_f = alpha + beta*(r_m - r_f)):
    compara el retorno REALIZADO del último año contra el mínimo que el
    CAPM exigía dado el riesgo (Beta) de esa fila — ver Parte 4 de
    "Detrás del Dashboard". No es la versión académica completa (le
    falta la segunda etapa cross-sectional que estima el precio de
    riesgo de cada factor): acá se usa para DESCRIBIR lo que ya pasó,
    no para predecir lo que debería pasar. Un alpha alto en un solo año
    puede ser suerte, no habilidad — un año de datos no alcanza para
    distinguir una cosa de la otra."""
    if alpha is None:
        return "Alpha no disponible todavía: falta Beta o CAPM para calcularlo."
    if alpha > 2:
        lectura = "rindió MÁS de lo que su riesgo exigía"
    elif alpha < -2:
        lectura = "rindió MENOS de lo que su riesgo exigía"
    else:
        lectura = "rindió aproximadamente lo que su riesgo exigía"
    detalle = ""
    if retorno_real_1y is not None and capm is not None:
        detalle = f" ({retorno_real_1y:+.1f}% real vs. {capm:.1f}% exigido por CAPM)"
    return (
        f"<b>Alpha = {alpha:+.2f}%</b><br>"
        f"En el último año, esta acción {lectura}{detalle}. Un alpha positivo suena bien, "
        "pero en un solo año puede ser suerte tanto como habilidad — no alcanza para probar nada."
    )


def explicacion_sharpe(sharpe: float | None) -> str:
    """Ratio de Sharpe = (retorno realizado del último año - Rf) /
    volatilidad anualizada — ver Parte 2 de "Detrás del Dashboard".
    Compara retorno extra contra RIESGO TOTAL (no solo el sistemático
    que mide Beta), así que dos acciones con el mismo Beta pueden tener
    Sharpe muy distinto si una es más volátil por razones propias de la
    empresa."""
    if sharpe is None:
        return "Sharpe no disponible todavía: falta el retorno realizado o la volatilidad."
    if sharpe > 1:
        lectura = "buena — ganó bastante más de lo que arriesgó"
    elif sharpe > 0:
        lectura = "moderada — ganó algo más de lo que arriesgó"
    else:
        lectura = "mala — no compensó el riesgo total que tuvo"
    return (
        f"<b>Sharpe = {sharpe:.2f}</b><br>"
        f"Cuánto retorno extra (por sobre la tasa libre de riesgo) ganó esta acción por cada "
        f"unidad de volatilidad total que tuvo en el último año. Acá la relación es {lectura}. "
        "Es el número que aparece en cualquier ficha técnica de un fondo mutuo."
    )


def explicacion_treynor(treynor: float | None) -> str:
    """Ratio de Treynor = (retorno realizado del último año - Rf) / Beta
    — ver Parte 3 de "Detrás del Dashboard". A diferencia de Sharpe,
    divide solo por el riesgo SISTEMÁTICO (Beta), asumiendo que el
    riesgo propio de la empresa ya está diversificado en un
    portafolio -- útil para comparar acciones asumiendo que no las vas
    a tener solas."""
    if treynor is None:
        return "Treynor no disponible todavía: falta el retorno realizado o la Beta."
    return (
        f"<b>Treynor = {treynor:+.2f}%</b><br>"
        "Retorno extra ganado por cada unidad de riesgo NO diversificable (Beta), asumiendo "
        "que el riesgo propio de la empresa ya lo eliminaste teniendo otras acciones también."
    )


def explicacion_atribucion(beta: float | None) -> str:
    """Conecta con el modelo de atribución multi-factor del IPSA
    (market_data.calcular_atribucion_ipsa) SOLO a través de la relación
    general que da la Beta de esta fila — nunca una atribución
    específica para esta acción puntual (eso requeriría una regresión
    por acción, fuera de alcance). Pensada solo para el heatmap de
    Acciones IPSA: el modelo de atribución existente es específico del
    mercado chileno (cobre, S&P 500, USD/CLP explicando a ECH), así que
    no aplica de la misma forma a una acción del Dow Jones — el
    llamador simplemente no incluye este bloque para esa tabla."""
    if beta is None:
        return ""
    if beta > 1.05:
        relacion = "MÁS que el promedio del mercado"
    elif beta < 0.95:
        relacion = "MENOS que el promedio del mercado"
    else:
        relacion = "aproximadamente igual al promedio del mercado"
    return (
        "<b>Relación con factores globales</b><br>"
        "Cuando el mercado chileno se mueve por factores globales (cobre, S&P 500 — ver "
        f"pestaña \"Atribución IPSA\"), una acción con Beta {beta:.2f} como esta tiende a "
        f"moverse {relacion} en esos mismos movimientos."
    )


def tooltip_html(texto_visible: str, contenido_html: str) -> str:
    """HTML de un tooltip CSS puro (sin JavaScript): el contenido aparece
    al pasar el mouse sobre `texto_visible`, vía la pseudo-clase :hover
    (ver TOOLTIP_CSS). `contenido_html` ya viene formado con las etiquetas
    <b>/<br> que se quieran mostrar (no se escapa acá)."""
    return (
        '<span class="glosario-tooltip">'
        f'{texto_visible}'
        f'<span class="glosario-tooltip-texto">{contenido_html}</span>'
        '</span>'
    )


# CSS puro (sin JS): position:absolute (relativo al span padre, que tiene
# position:relative) + :hover para mostrar/ocultar. Se inyecta UNA vez por
# página vía st.markdown(unsafe_allow_html=True) antes de usar
# tooltip_html(). Confirmado con un screenshot real (Playwright headless
# contra la app corriendo) que streamlit renderiza st.markdown en el DOM
# principal, no en un iframe aislado — pero los contenedores propios de
# Streamlit (stMain, stAppViewContainer) SÍ tienen overflow: auto/hidden,
# así que un tooltip demasiado alto puede salirse del viewport hacia
# arriba en filas cercanas al borde superior (visto en la primera versión
# de la prueba de concepto, con Beta+Beta ajustada+CAPM+CRP juntos: ~650px
# de alto). max-height + overflow-y:auto acá es el resguardo para eso.
#
# La versión integrada en la tabla real (8-9 bloques: nombre, rendimiento,
# Beta, CAPM, volatilidad, Sharpe, Treynor, Alpha, y para IPSA también
# atribución) tiene mucho más contenido que la prueba de concepto de 5
# tickers. Se remidió con Playwright contra la app corriendo, LAS 60
# ACCIONES UNA POR UNA (30 IPSA + 30 Dow Jones, no una muestra) cada vez
# que se agregó contenido nuevo, comparando scrollHeight contra
# clientHeight: el máximo real observado, con Sharpe/Treynor/Alpha ya
# incluidos, fue 873px (BSANTANDER, IPSA — el máximo se da siempre en
# IPSA porque ahí se suma el bloque extra de atribución) con este ancho
# de 340px — max-height:920px le da margen sin necesitar scroll dentro
# del tooltip (que sería inutilizable: el tooltip desaparece apenas el
# mouse deja de estar encima). Se subió el ancho de 280 a 340px a
# propósito para achicar la altura total (menos líneas por bloque), no
# solo por estética.
#
# A este alto (~850-870px), el "límite conocido" de abajo (fila cerca
# del borde del viewport) se vuelve más frecuente, no solo un caso
# extremo — vale la pena tenerlo presente si se sigue agregando
# contenido al tooltip.
#
# Límite conocido, no resuelto (inherente a CSS puro sin JS): el tooltip
# se centra verticalmente sobre la fila (top:50% + translateY(-50%)), así
# que en una fila muy cerca del borde superior o inferior de la ventana
# visible, una porción del tooltip (hasta ~530px de alto) puede quedar
# fuera de esa ventana. No es lo mismo que los dos bugs de recorte de
# arriba (ese contenido SIGUE en el DOM, no lo tapa un overflow:hidden
# ajeno) — pero en la práctica el usuario no puede "scrollear para verlo"
# sin perder el :hover, porque mover la rueda del mouse mueve el
# contenido bajo un cursor que se queda fijo en pantalla (confirmado
# programáticamente: tras un scroll, el tooltip pasa a visibility:hidden
# porque el mouse deja de estar sobre el ticker). Arreglarlo bien
# (reposicionar el tooltip según el espacio disponible) requeriría
# JavaScript, explícitamente descartado. Mitigación aplicada: se acortó
# el contenido y se ensanchó el tooltip para reducir su alto lo más
# posible; el resto queda como limitación conocida y documentada, no
# como algo que se dio por resuelto sin serlo.
#
# Anclado a la DERECHA del ticker (no centrado arriba): la columna de
# Ticker es la más a la izquierda de la tabla, pegada al sidebar — un
# tooltip centrado (left:50% + translateX(-50%)) se corta contra el borde
# del sidebar y deja el principio del texto ilegible (confirmado con
# screenshot real en la prueba de concepto: "LATAM Airlines..." se veía
# cortado como "AM Airlines..."). Abrir hacia la derecha usa el espacio
# ancho de la propia tabla en vez de chocar con el sidebar.
#
# white-space: normal es obligatorio acá: las celdas <td> de la tabla
# (ver app/dashboard.py) usan white-space:nowrap para que el nombre del
# ticker nunca se corte a mitad de palabra, y white-space se HEREDA por
# defecto — sin este reset, el tooltip (que vive DENTRO de un <td>)
# heredaba nowrap y el texto de cada bloque salía como una sola línea
# larga cortada en el borde del box en vez de hacer word-wrap. Encontrado
# con un screenshot real después de escalar a 5-6 bloques de contenido
# (con el tooltip corto de la prueba de concepto no se notaba tanto,
# porque una sola línea de texto cabía igual sin wrap visible).
#
# Tampoco se envuelve la tabla en un <div overflow-x:auto> (ver
# _renderizar_heatmap_con_tooltips en app/dashboard.py) — esa combinación
# recortaba el tooltip verticalmente, otro bug real que solo apareció al
# escalar de 5 tickers en una mini-tabla a la tabla completa de 30.
TOOLTIP_CSS = """
<style>
.glosario-tooltip {
    border-bottom: 1px dotted #6a6a6a;
    cursor: help;
    position: relative;
}
.glosario-tooltip .glosario-tooltip-texto {
    visibility: hidden;
    opacity: 0;
    width: 340px;
    max-height: 920px;
    overflow-y: auto;
    background-color: #262730;
    color: #fafafa;
    text-align: left;
    white-space: normal;
    border-radius: 6px;
    padding: 10px 12px;
    position: absolute;
    z-index: 9999;
    top: 50%;
    left: 100%;
    margin-left: 10px;
    transform: translateY(-50%);
    transition: opacity 0.15s ease-in-out;
    font-size: 0.82rem;
    font-weight: 400;
    line-height: 1.4;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
}
.glosario-tooltip .glosario-tooltip-texto hr {
    border: none;
    border-top: 1px solid #3d3e47;
    margin: 8px 0;
}
.glosario-tooltip:hover .glosario-tooltip-texto {
    visibility: visible;
    opacity: 1;
}
</style>
"""
