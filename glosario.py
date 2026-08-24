"""
Glosario de tickers y plantillas de explicación educativa para los
tooltips (hover) de los heatmaps de "Acciones IPSA" y "Acciones Dow
Jones". Vive fuera de app/dashboard.py para no mezclar datos/plantillas
con lógica de Streamlit, mismo criterio que market_data.py.

FASE 1 (prueba de concepto): solo 5 tickers del IPSA (incluye LTM, a
pedido explícito). Antes de escalar a los 63 restantes (25 del IPSA +
30 del Dow Jones + Momentum/otros) hay que confirmar visualmente que el
tooltip CSS puro (sin JavaScript) se ve bien dentro del render real de
Streamlit — no todos los trucos de CSS (position: absolute, overflow)
funcionan igual dentro de los contenedores propios de Streamlit.

Los nombres completos son datos verificables de empresas públicas
chilenas, no inventados: LATAM Airlines, SQM, Banco de Chile, Falabella
y Empresas Copec son emisores del IPSA ampliamente conocidos. Para los
25 tickers restantes del IPSA (varios menos obvios, ej. ENELAM = Enel
Américas, IAM = Inversiones Aguas Metropolitanas) habrá que verificar
cada nombre antes de escalar — no se completan acá todavía.
"""

NOMBRE_COMPLETO_POR_TICKER: dict[str, str] = {
    "LTM.SN": "LATAM Airlines Group S.A.",
    "SQM-B.SN": "Sociedad Química y Minera de Chile S.A. (SQM), Serie B",
    "CHILE.SN": "Banco de Chile",
    "FALABELLA.SN": "S.A.C.I. Falabella",
    "COPEC.SN": "Empresas Copec S.A.",
}


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
        f"Si el IPSA sube o baja 1%, esta acción tiende a moverse {beta:.2f}% — es "
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
# arriba en filas cercanas al borde superior (visto en la primera versión,
# con Beta+Beta ajustada+CAPM+CRP juntos: ~650px de alto). max-height +
# overflow-y:auto acá es el resguardo para eso; el contenido real (nombre +
# Beta + CAPM, ya acortados) mide ~286px con este ancho de 260px, medido
# con Playwright (scrollHeight) contra la app corriendo — max-height:300px
# le da margen sin necesitar scroll dentro del tooltip (que sería
# inutilizable: el tooltip desaparece apenas el mouse deja de estar
# encima, así que pedirle al usuario que además haga scroll ahí adentro
# no funciona en la práctica).
#
# Anclado a la DERECHA del ticker (no centrado arriba): la columna de
# Ticker es la más a la izquierda de la tabla, pegada al sidebar — un
# tooltip centrado (left:50% + translateX(-50%)) se corta contra el borde
# del sidebar y deja el principio del texto ilegible (confirmado con
# screenshot real: "LATAM Airlines..." se veía cortado como "AM
# Airlines..."). Abrir hacia la derecha usa el espacio ancho de la propia
# tabla en vez de chocar con el sidebar.
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
    width: 260px;
    max-height: 320px;
    overflow-y: auto;
    background-color: #262730;
    color: #fafafa;
    text-align: left;
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
    line-height: 1.45;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
}
.glosario-tooltip:hover .glosario-tooltip-texto {
    visibility: visible;
    opacity: 1;
}
</style>
"""
