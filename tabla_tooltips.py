"""
Tabla de instrumentos con color por celda y un tooltip al pasar el mouse sobre el nombre de cada fila.

Es el mismo recurso que usan los heatmaps de «Acciones IPSA» y «Acciones Dow Jones»
(app/dashboard.py: _renderizar_heatmap_con_tooltips): una tabla HTML propia, porque
st.dataframe no admite HTML dentro de las celdas, con el tooltip CSS puro de
glosario.tooltip_html. Se escribió aparte, con el mismo criterio de colores, para que las
secciones nuevas (renta fija, y las que vienen) lo reutilicen sin tocar las secciones de
acciones que ya funcionan. No depende de Streamlit: devuelve un string HTML.

Colores, igual que en las acciones:
- columnas de variación (1D, 1W, ...): escala divergente rojo-gris-verde, simétrica y compartida
  entre ellas (el mismo valor absoluto pinta la misma intensidad en todas);
- el resto de las columnas numéricas: escala secuencial blanca-azul, con su propio mínimo y máximo.
Una fila marcada como atrasada va en gris y sin color de fondo: su dato no es de fiar.

No se envuelve la tabla en un contenedor con scroll horizontal: eso recortaría el tooltip hacia
arriba (ver el comentario de glosario.TOOLTIP_CSS).
"""
from __future__ import annotations

import html
from typing import Callable

import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from glosario import TOOLTIP_CSS, tooltip_html

CMAP_DIVERGENTE = LinearSegmentedColormap.from_list("rojo_verde", ["#d03b3b", "#f0efec", "#0ca30c"])
CMAP_SECUENCIAL = LinearSegmentedColormap.from_list("azul_secuencial", ["#fcfcfb", "#2a78d6"])
COLUMNA_ATRASADO = "_atrasado_bool"


def color_de_gradiente(cmap, valor, minimo, maximo) -> tuple[str, str] | None:
    """(color de fondo, color de texto) para `valor` dentro de [minimo, maximo], o None si no se puede pintar.

    El texto pasa a oscuro o claro según la luminancia del fondo, para que se lea en todo el degradado
    (con texto claro fijo, los valores del centro de la escala, casi blancos, quedaban ilegibles)."""
    if pd.isna(valor) or maximo == minimo:
        return None
    fraccion = min(max((valor - minimo) / (maximo - minimo), 0.0), 1.0)
    r, g, b, _ = cmap(fraccion)
    r255, g255, b255 = int(r * 255), int(g * 255), int(b * 255)
    luminancia = 0.299 * r255 + 0.587 * g255 + 0.114 * b255
    return f"rgb({r255}, {g255}, {b255})", ("#1a1a1a" if luminancia > 150 else "#f5f5f5")


def tabla_con_tooltips(
    datos: pd.DataFrame,
    columnas_divergentes: list[str],
    columnas_secuenciales: list[str],
    formatos: dict[str, str],
    construir_tooltip: Callable[[str, pd.Series], str],
    titulo_primera_columna: str = "Ticker",
    relleno_horizontal: int = 7,
) -> str:
    """HTML de la tabla. `datos` tiene una fila por instrumento (el índice es el nombre que se ve) y puede
    traer la columna `_atrasado_bool`. `formatos` mapea columna -> plantilla («{:+.2f}%») o una función
    valor -> texto; un valor vacío se muestra como «—». Las columnas que no están en ninguna de las dos listas
    de colores se muestran sin pintar. `construir_tooltip(nombre, fila)` devuelve el HTML del tooltip de esa fila.
    `relleno_horizontal` (px) es el espacio a cada lado del texto de una celda: con tablas de más de ~10
    columnas, achicarlo es lo que decide si la tabla cabe en pantalla o se corta a la derecha."""
    atrasado = datos[COLUMNA_ATRASADO] if COLUMNA_ATRASADO in datos else pd.Series(False, index=datos.index)
    mostradas = [c for c in datos.columns if c != COLUMNA_ATRASADO]

    maximo_abs = datos[columnas_divergentes].abs().max().max() if columnas_divergentes else 1
    maximo_abs = maximo_abs if pd.notna(maximo_abs) and maximo_abs > 0 else 1
    rangos = {c: (datos[c].min(), datos[c].max()) for c in columnas_secuenciales}

    celda = f"padding:6px {relleno_horizontal}px;"
    filas = []
    for nombre, fila in datos.iterrows():
        gris = bool(atrasado[nombre])
        estilo_texto = "color:#898781;" if gris else ""
        contenido = construir_tooltip(nombre, fila)
        etiqueta = html.escape(str(nombre))
        celdas = [
            f"<td style='{celda} white-space:nowrap; {estilo_texto}'>"
            f"{tooltip_html(etiqueta, contenido) if contenido else etiqueta}</td>"
        ]
        for columna in mostradas:
            valor = fila[columna]
            fondo = ""
            if not gris:
                color = None
                if columna in columnas_divergentes:
                    color = color_de_gradiente(CMAP_DIVERGENTE, valor, -maximo_abs, maximo_abs)
                elif columna in columnas_secuenciales:
                    color = color_de_gradiente(CMAP_SECUENCIAL, valor, *rangos[columna])
                if color:
                    fondo = f"background-color:{color[0]}; color:{color[1]};"
            if columna in formatos and pd.notna(valor):
                formato = formatos[columna]
                texto = formato(valor) if callable(formato) else formato.format(valor)
            elif pd.isna(valor):
                texto = "—"
            else:
                texto = html.escape(str(valor))
            celdas.append(f"<td style='{celda} white-space:nowrap; {estilo_texto}{fondo}'>{texto}</td>")
        filas.append(f"<tr>{''.join(celdas)}</tr>")

    encabezado = "".join(
        f"<th style='text-align:left; {celda} border-bottom:1px solid #4a4a4a; white-space:nowrap;'>{html.escape(c)}</th>"
        for c in [titulo_primera_columna] + mostradas
    )
    return (
        TOOLTIP_CSS
        + "<table style='width:100%; border-collapse:collapse; font-size:0.88rem;'>"
        + f"<tr>{encabezado}</tr>" + "".join(filas) + "</table>"
    )
