"""
Piezas comunes de los informes en PDF del dashboard (renta fija y, después, renta variable y FX).

PARA QUÉ EXISTE
    Los informes salen de la misma base de datos que las pantallas, pero se leen fuera del dashboard: alguien los
    descarga, los imprime o los manda. Por eso tienen su propio formato, pensado para papel, y su propia exigencia:
    cada cifra tiene que poder rastrearse hasta su fuente y su fecha.

QUÉ NO HACE
    No calcula nada. Los números los traen los módulos de cada sección (renta_fija.py y compañía), que ya están
    probados. Acá solo se arma el documento: estilos, encabezados, tablas, recuadros y gráficos.

EL FORMATO
    Es el del PDF del Brief Premercado (app/dashboard.py: generar_pdf_brief_premercado): tipografía serif para los
    títulos, sans para el texto, paleta navy y dorado, tablas con líneas horizontales en vez de grilla. Un informe
    descargado se juzga con los códigos de una nota de research, no con los de una pantalla. La paleta vive acá y
    el Brief la importa, para que los dos documentos no se separen con el tiempo.

LOS RECUADROS
    Hay dos, y la diferencia importa:
    - `recuadro_concepto`: explica un concepto (qué es la duración, qué es un spread). Fondo gris, al estilo de los
      recuadros del IPoM.
    - `recuadro_error`: nombra una lectura equivocada frecuente y la corrige. Barra roja a la izquierda. Es la parte
      que convierte el informe en algo que enseña: un dato sin la confusión típica al lado se entiende mal.
"""
from __future__ import annotations

import io
import re
from datetime import datetime

import matplotlib

matplotlib.use("Agg", force=False)  # sin ventanas: el PDF se arma en el servidor
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Paleta: navy + dorado apagado (look «nota de research institucional»), separada del resto del dashboard.
NAVY = "#1c2b45"
GOLD = "#a8823c"
INK = "#2b2b2b"
MUTED = "#6d6d6d"
RULE = "#d9d5cb"
ROW_ALT = "#f7f6f2"
POSITIVO = "#2f6f4f"
NEGATIVO = "#a13c3c"
FONDO_CONCEPTO = "#f2f1ec"

MARGEN = 1.8 * cm
ANCHO_UTIL = letter[0] - 2 * MARGEN

_C = {n: colors.HexColor(v) for n, v in (
    ("navy", NAVY), ("gold", GOLD), ("ink", INK), ("muted", MUTED), ("rule", RULE),
    ("row_alt", ROW_ALT), ("positivo", POSITIVO), ("negativo", NEGATIVO), ("concepto", FONDO_CONCEPTO),
)}

_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"\*(.+?)\*")


def md(texto: str) -> str:
    """Escapa el texto y convierte **negrita** y *cursiva* a las etiquetas que entiende Paragraph.

    La negrita va primero: si no, los dos asteriscos de **x** se tomarían como una cursiva vacía."""
    texto = texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _MD_ITALIC.sub(r"<i>\1</i>", _MD_BOLD.sub(r"<b>\1</b>", texto))


ESTILOS = {
    "titulo": ParagraphStyle("titulo", fontName="Times-Bold", fontSize=22, leading=26, textColor=_C["navy"], spaceAfter=2),
    "subtitulo": ParagraphStyle("subtitulo", fontName="Times-Italic", fontSize=12.5, leading=16, textColor=_C["muted"], spaceAfter=2),
    "fecha": ParagraphStyle("fecha", fontName="Helvetica", fontSize=9.5, leading=12, textColor=_C["muted"]),
    "seccion": ParagraphStyle("seccion", fontName="Times-Bold", fontSize=14, leading=17, textColor=_C["navy"], spaceBefore=15, spaceAfter=2),
    "subseccion": ParagraphStyle("subseccion", fontName="Times-Bold", fontSize=11, leading=14, textColor=_C["navy"], spaceBefore=9, spaceAfter=3),
    "texto": ParagraphStyle("texto", fontName="Helvetica", fontSize=9.2, leading=13, textColor=_C["ink"], spaceAfter=6, alignment=4),
    "conclusion": ParagraphStyle("conclusion", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=_C["ink"], spaceAfter=7,
                                 leftIndent=10, bulletIndent=1, alignment=4),
    "nota": ParagraphStyle("nota", fontName="Helvetica-Oblique", fontSize=7.8, leading=10.5, textColor=_C["muted"], spaceAfter=8),
    "recuadro_titulo": ParagraphStyle("recuadro_titulo", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=_C["navy"], spaceAfter=3),
    "recuadro_texto": ParagraphStyle("recuadro_texto", fontName="Helvetica", fontSize=8.6, leading=12, textColor=_C["ink"], spaceAfter=4, alignment=4),
    "error_titulo": ParagraphStyle("error_titulo", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=_C["negativo"], spaceAfter=3),
    "celda": ParagraphStyle("celda", fontName="Helvetica", fontSize=8, leading=10.5, textColor=_C["ink"]),
    "celda_encabezado": ParagraphStyle("celda_encabezado", fontName="Helvetica-Bold", fontSize=8, leading=10.5, textColor=_C["navy"]),
}


def parrafo(texto: str, estilo: str = "texto") -> Paragraph:
    return Paragraph(md(texto), ESTILOS[estilo])


def conclusion(texto: str) -> Paragraph:
    """Una conclusión del resumen: viñeta, con la afirmación en negrita adelante y la evidencia atrás."""
    return Paragraph(md(texto), ESTILOS["conclusion"], bulletText="•")


def titulo_seccion(texto: str) -> list:
    """Encabezado de sección con su regla dorada debajo."""
    return [
        Paragraph(md(texto).upper(), ESTILOS["seccion"]),
        HRFlowable(width="100%", thickness=0.9, color=_C["gold"], spaceBefore=1, spaceAfter=7),
    ]


def _caja(titulo: str, parrafos: list[str], fondo, barra, estilo_titulo: str) -> KeepTogether:
    contenido = [Paragraph(md(titulo), ESTILOS[estilo_titulo])]
    contenido += [Paragraph(md(p), ESTILOS["recuadro_texto"]) for p in parrafos]
    tabla = Table([[contenido]], colWidths=[ANCHO_UTIL])
    estilo = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if fondo is not None:
        estilo.append(("BACKGROUND", (0, 0), (-1, -1), fondo))
    if barra is not None:
        estilo.append(("LINEBEFORE", (0, 0), (0, -1), 2.2, barra))
    tabla.setStyle(TableStyle(estilo))
    return KeepTogether([Spacer(1, 3), tabla, Spacer(1, 7)])


def recuadro_concepto(titulo: str, parrafos: list[str]) -> KeepTogether:
    """Recuadro que explica un concepto, al estilo de los del IPoM."""
    return _caja(titulo, parrafos, _C["concepto"], _C["gold"], "recuadro_titulo")


def recuadro_error(titulo: str, parrafos: list[str]) -> KeepTogether:
    """Recuadro que nombra una lectura equivocada frecuente y la corrige."""
    return _caja(titulo, parrafos, None, _C["negativo"], "error_titulo")


def tabla(datos: pd.DataFrame, anchos: list[float] | None = None, alinear_derecha_desde: int = 1) -> Table:
    """Tabla con el encabezado en navy, líneas horizontales y filas alternadas (sin grilla completa).

    `datos` ya viene con todo formateado como texto: esta función no redondea ni interpreta números."""
    encabezados = [Paragraph(md(str(c)), ESTILOS["celda_encabezado"]) for c in datos.columns]
    filas = [[Paragraph(md(str(v)), ESTILOS["celda"]) for v in fila] for fila in datos.itertuples(index=False)]
    if anchos is None:
        primera = ANCHO_UTIL * 0.16
        resto = (ANCHO_UTIL - primera) / max(len(datos.columns) - 1, 1)
        anchos = [primera] + [resto] * (len(datos.columns) - 1)
    t = Table([encabezados] + filas, colWidths=anchos, repeatRows=1)
    estilo = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (alinear_derecha_desde, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, _C["navy"]),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, _C["rule"]),
        ("LINEBELOW", (0, -1), (-1, -1), 0.7, _C["navy"]),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(filas) + 1):
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i), (-1, i), _C["row_alt"]))
    t.setStyle(TableStyle(estilo))
    return t


def nota(texto: str) -> KeepTogether:
    """Nota al pie de una tabla o gráfico: unidades, criterio y fuente.

    Va entera en una página: partida en dos, la frase se corta y la fuente de la cifra queda lejos del dato."""
    return KeepTogether([Paragraph(md(texto), ESTILOS["nota"])])


def con_su_nota(pieza, texto: str) -> KeepTogether:
    """Une un gráfico (o una tabla corta) con su nota, para que el salto de página no los separe.

    La nota se arma acá y no con `nota()`: anidar un KeepTogether dentro de otro hace que reportlab mande el bloque
    entero a la página siguiente aunque quepa, y el informe se llena de páginas casi vacías (medido: 5 páginas pasaron a 7)."""
    return KeepTogether([pieza, Paragraph(md(texto), ESTILOS["nota"])])


def grafico(dibujar, alto_cm: float = 6.5, ancho_cm: float | None = None) -> Image:
    """Convierte un gráfico de matplotlib en una imagen para el PDF.

    `dibujar(ax)` recibe el eje y dibuja encima. La figura se cierra siempre, porque matplotlib las acumula en memoria
    y un informe con varios gráficos generado muchas veces terminaría llenándola."""
    ancho_cm = ancho_cm if ancho_cm is not None else ANCHO_UTIL / cm
    fig, ax = plt.subplots(figsize=(ancho_cm / 2.54, alto_cm / 2.54), dpi=200)
    try:
        dibujar(ax)
        ax.tick_params(labelsize=7, colors=INK)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color(RULE)
        ax.grid(axis="y", color=RULE, linewidth=0.5, alpha=0.8)
        ax.set_axisbelow(True)
        fig.tight_layout(pad=0.4)
        datos = io.BytesIO()
        fig.savefig(datos, format="png", bbox_inches="tight", facecolor="white")
    finally:
        plt.close(fig)
    # El alto va explícito: reportlab no lo deduce solo. Se saca de las proporciones reales del PNG, que `bbox_inches`
    # pudo haber recortado respecto del tamaño pedido.
    datos.seek(0)
    ancho_px, alto_px = ImageReader(datos).getSize()
    datos.seek(0)
    ancho_pt = ancho_cm * cm
    return Image(datos, width=ancho_pt, height=ancho_pt * alto_px / ancho_px)


def _pie_de_pagina(titulo_corto: str):
    def dibujar(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(_C["rule"])
        canvas.setLineWidth(0.5)
        canvas.line(MARGEN, 1.5 * cm, letter[0] - MARGEN, 1.5 * cm)
        canvas.setFont("Helvetica", 7.3)
        canvas.setFillColor(_C["muted"])
        canvas.drawString(MARGEN, 1.1 * cm, f"{titulo_corto} — generado el {datetime.now().strftime('%d-%m-%Y %H:%M')}")
        canvas.drawRightString(letter[0] - MARGEN, 1.1 * cm, f"Página {doc.page}")
        canvas.restoreState()

    return dibujar


def portada(titulo: str, subtitulo: str, lineas_de_fecha: list[str]) -> list:
    piezas = [
        HRFlowable(width="100%", thickness=2.2, color=_C["navy"], spaceAfter=9),
        Paragraph(md(titulo), ESTILOS["titulo"]),
        Paragraph(md(subtitulo), ESTILOS["subtitulo"]),
        Spacer(1, 5),
    ]
    piezas += [Paragraph(md(l), ESTILOS["fecha"]) for l in lineas_de_fecha]
    piezas.append(HRFlowable(width="100%", thickness=0.9, color=_C["gold"], spaceBefore=9, spaceAfter=4))
    return piezas


def construir_pdf(piezas: list, titulo_corto: str, titulo_documento: str) -> bytes:
    """Arma el PDF y devuelve sus bytes (para st.download_button, que necesita bytes y no un archivo)."""
    salida = io.BytesIO()
    doc = SimpleDocTemplate(
        salida, pagesize=letter,
        leftMargin=MARGEN, rightMargin=MARGEN, topMargin=1.7 * cm, bottomMargin=2.1 * cm,
        title=titulo_documento, author="Dashboard Mercado Económico Chileno",
    )
    pie = _pie_de_pagina(titulo_corto)
    doc.build(piezas, onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()


# ---------------------------------------------------------------------------
# Formato de números: el mismo de las tablas del dashboard (punto decimal)
# ---------------------------------------------------------------------------
def num(valor, decimales: int = 2, con_signo: bool = False) -> str:
    """Número formateado, o «—» si no hay dato (nunca un cero inventado)."""
    if valor is None or pd.isna(valor):
        return "—"
    return f"{valor:{'+' if con_signo else ''},.{decimales}f}"


def pct(valor, decimales: int = 2, con_signo: bool = False) -> str:
    return "—" if valor is None or pd.isna(valor) else f"{num(valor, decimales, con_signo)}%"


def fecha(valor) -> str:
    return "—" if valor is None or pd.isna(valor) else pd.Timestamp(valor).strftime("%d-%m-%Y")
