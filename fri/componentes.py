"""FRI — piezas de interfaz en HTML/SVG (iconos, decoraciones, formato). Sin dependencias nuevas ni recursos externos."""
from __future__ import annotations

import math
import os
import sys

import numpy as np

from formato_numerico import cifra  # noqa: E402  regla única de cero sin signo (H2)
from fri.estilos import T  # noqa: E402

# ---------------------------------------------------------------------------
# Formato numérico: el MISMO del dashboard (formato_numerico.cifra, regla de cero sin signo de H2), para que una
# cifra se lea igual en FRI, en las secciones existentes y en la interfaz clásica.
# ---------------------------------------------------------------------------
def num(valor, decimales: int = 2, con_signo: bool = False) -> str:
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "—"
    return cifra(float(valor), decimales, con_signo, True)


def chip(valor: float, unidad: str = "%", decimales: int = 2, invertir_color: bool = False) -> str:
    """Variación con signo y flecha. El color no es el único código (flecha y signo) y, en tasas o desempleo, la
    variación positiva no se pinta como «buena» (ver FRI_DESIGN_SYSTEM §2)."""
    texto = num(valor, decimales, True)
    if texto.lstrip("+-") == num(0, decimales):
        return f'<span class="chip chip-neu">→ {texto} {unidad}</span>'
    sube = valor > 0
    clase = ("chip-neg" if sube else "chip-pos") if invertir_color else ("chip-pos" if sube else "chip-neg")
    return f'<span class="chip {clase}">{"▲" if sube else "▼"} {texto} {unidad}</span>'


# ---------------------------------------------------------------------------
# Iconos de línea (trazo dorado)
# ---------------------------------------------------------------------------
_TRAZOS = {
    "inicio": '<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/>',
    "macro": '<rect x="4" y="12" width="3" height="8"/><rect x="10.5" y="8" width="3" height="12"/><rect x="17" y="4" width="3" height="16"/>',
    "mercados": '<path d="M3 17l5-6 4 3 6-8 3 3"/>',
    "riesgo": '<path d="M12 3 20 6v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "investigacion": '<path d="M12 3 21 8l-9 5-9-5z"/><path d="M3 12.5l9 5 9-5"/><path d="M3 16.5l9 5 9-5"/>',
    "informes": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 15.5h6M9 9h3"/>',
    "calendario": '<rect x="4" y="5" width="16" height="15" rx="1.5"/><path d="M4 9.5h16M8 3v4M16 3v4"/>',
    "lugar": '<path d="M12 21s-6-6.2-6-11a6 6 0 0 1 12 0c0 4.8-6 11-6 11z"/><circle cx="12" cy="10" r="2.2"/>',
    "buscar": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    "ayuda": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.7"/><path d="M12 17h.01"/>',
    "campana": '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "ajustes": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
    "flecha": '<path d="M4 12h15M14 7l5 5-5 5"/>',
    "documento": '<path d="M6 3h8l4 4v14H6z"/><path d="M9 12h6M9 15.5h6"/>',
    "globo": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18"/>',
    "edificio": '<path d="M3 21h18M5 21V10M19 21V10M9 21v-8M15 21v-8M2.5 10 12 4l9.5 6z"/>',
    "barras": '<rect x="4" y="13" width="3.2" height="7"/><rect x="10.4" y="9" width="3.2" height="11"/><rect x="16.8" y="5" width="3.2" height="15"/>',
}


def icono(nombre: str, tam: int = 22, color: str | None = None, grosor: float = 1.6) -> str:
    return (f'<svg width="{tam}" height="{tam}" viewBox="0 0 24 24" fill="none" stroke="{color or T["dorado"]}" '
            f'stroke-width="{grosor}" stroke-linecap="round" stroke-linejoin="round">{_TRAZOS[nombre]}</svg>')


def logo_barras(tam: int = 30) -> str:
    return (f'<svg width="{tam}" height="{tam}" viewBox="0 0 24 24"><rect x="3" y="13" width="4.2" height="8" fill="{T["dorado"]}"/>'
            f'<rect x="9.9" y="8.5" width="4.2" height="12.5" fill="{T["dorado"]}"/>'
            f'<rect x="16.8" y="3" width="4.2" height="18" fill="{T["dorado"]}"/></svg>')


# ---------------------------------------------------------------------------
# Bandera y color de tendencia
# ---------------------------------------------------------------------------
def bandera_chile(ancho: int = 30) -> str:
    alto = ancho * 2 / 3
    return (f'<svg width="{ancho}" height="{alto:.0f}" viewBox="0 0 30 20" style="border-radius:3px;vertical-align:-3px">'
            '<rect width="30" height="20" fill="#d52b1e"/><rect width="30" height="10" fill="#ffffff"/><rect width="10" height="10" fill="#0039a6"/>'
            '<polygon points="5,2.2 5.9,4.6 8.4,4.6 6.4,6.1 7.2,8.5 5,7 2.8,8.5 3.6,6.1 1.6,4.6 4.1,4.6" fill="#ffffff"/></svg>')


def color_tendencia(serie) -> str:
    v = np.asarray(serie, dtype=float)
    return T["positivo"] if v[-1] >= v[0] else T["negativo"]


# ---------------------------------------------------------------------------
# Minigráfico y tarjeta KPI
# ---------------------------------------------------------------------------
def minigrafico(valores, color: str, ancho: int = 260, alto: int = 44) -> str:
    v = np.asarray(valores, dtype=float)
    v = v[~np.isnan(v)]
    if len(v) < 2:
        return ""
    lo, hi = v.min(), v.max()
    rango = hi - lo or 1.0
    xs = np.linspace(0, ancho, len(v))
    ys = alto - 4 - (v - lo) / rango * (alto - 8)
    linea = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area = f"0,{alto} {linea} {ancho},{alto}"
    gid = f"g{abs(hash((len(v), float(v[-1]), color))) % 10**8}"
    return (f'<svg width="100%" height="{alto}" viewBox="0 0 {ancho} {alto}" preserveAspectRatio="none">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{color}" stop-opacity=".28"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
            f'<polygon points="{area}" fill="url(#{gid})"/><polyline points="{linea}" fill="none" stroke="{color}" stroke-width="1.6"/></svg>')


def kpi(nombre: str, valor: str, variacion_html: str, etiqueta_var: str, serie, color: str, fecha: str = "", unidad: str = "") -> str:
    return (f'<div class="fri-kpi"><div class="fila"><div><div class="nombre">{nombre}</div>'
            f'<div class="valor">{valor}{f" <small>{unidad}</small>" if unidad else ""}</div></div>'
            f'<div class="var">{variacion_html}<br>{etiqueta_var}</div></div>{minigrafico(serie, color)}'
            f'{f"<div class=fecha>{fecha}</div>" if fecha else ""}</div>')


def tabla(encabezados: list[str], filas: list[list[str]], clases: list[list[str]] | None = None) -> str:
    th = "".join(f"<th>{h}</th>" for h in encabezados)
    cuerpo = []
    for i, fila in enumerate(filas):
        celdas = []
        for j, c in enumerate(fila):
            clase = clases[i][j] if clases else ""
            celdas.append(f'<td class="{clase}">{c}</td>')
        cuerpo.append("<tr>" + "".join(celdas) + "</tr>")
    return f'<table class="fri-tabla"><thead><tr>{th}</tr></thead><tbody>{"".join(cuerpo)}</tbody></table>'


def clase_signo(valor: float, decimales: int = 2) -> str:
    texto = num(valor, decimales)
    if texto.lstrip("-") == num(0, decimales):
        return ""
    return "pos" if valor > 0 else "neg"


def aviso_sintetico(texto: str = "Base local con cifras inventadas para probar la interfaz. No son datos de mercado.") -> str:
    return f'<div class="fri-aviso"><b>DATOS SINTÉTICOS</b> {texto}</div>'


# ---------------------------------------------------------------------------
# Decoraciones sutiles de las tarjetas de Inicio (dibujo de línea, como en las maquetas aprobadas)
# ---------------------------------------------------------------------------
def decoracion(tipo: str) -> str:
    oro, teal = T["dorado"], T["teal"]
    rng = np.random.default_rng({"macro": 1, "mercados": 2, "riesgo": 3, "investigacion": 4, "informes": 5}[tipo])
    w, h = 300, 96
    partes = []
    if tipo == "macro":      # cordones montañosos superpuestos
        for k, (base, amp, op) in enumerate([(70, 46, .55), (82, 34, .8), (92, 22, 1.0)]):
            xs = np.linspace(0, w, 40)
            ys = base - amp * np.abs(np.sin(xs / (38 + 9 * k) + k)) * rng.uniform(.6, 1, 40)
            partes.append(f'<polyline points="{" ".join(f"{x:.0f},{y:.0f}" for x, y in zip(xs, ys))}" fill="none" stroke="{teal if k < 2 else oro}" stroke-width="1" opacity="{op}"/>')
    elif tipo == "mercados":  # velas y barras al estilo de un gráfico de mercado
        x, nivel = 18, 60
        for _ in range(16):
            nivel += rng.normal(-1.2, 6)
            alto_v = rng.uniform(8, 22)
            partes.append(f'<line x1="{x}" y1="{nivel - alto_v:.0f}" x2="{x}" y2="{nivel + alto_v * .6:.0f}" stroke="{teal}" stroke-width="1"/>')
            partes.append(f'<rect x="{x - 3}" y="{nivel - alto_v * .5:.0f}" width="6" height="{alto_v * .7:.0f}" fill="none" stroke="{oro}" stroke-width="1" opacity=".8"/>')
            x += 17
    elif tipo == "riesgo":    # malla ondulada
        for i in range(9):
            xs = np.linspace(0, w, 60)
            ys = 70 - i * 5 + 14 * np.sin(xs / 45 + i * .35) * (1 - i / 14)
            partes.append(f'<polyline points="{" ".join(f"{x:.0f},{y:.0f}" for x, y in zip(xs, ys))}" fill="none" stroke="{teal}" stroke-width=".9" opacity="{.35 + i * .06:.2f}"/>')
    elif tipo == "investigacion":  # columnas de datos
        for i in range(22):
            alto_c = rng.uniform(20, 80)
            partes.append(f'<rect x="{10 + i * 13}" y="{h - alto_c:.0f}" width="6" height="{alto_c:.0f}" fill="{teal if i % 3 else oro}" opacity="{rng.uniform(.25, .6):.2f}"/>')
    else:                     # documento con un gráfico de barras
        partes.append(f'<rect x="120" y="14" width="150" height="80" rx="3" fill="none" stroke="{teal}" stroke-width="1" transform="skewX(-12)"/>')
        for i in range(9):
            alto_b = 10 + i * 4 + rng.uniform(0, 8)
            partes.append(f'<rect x="{130 + i * 13}" y="{82 - alto_b:.0f}" width="7" height="{alto_b:.0f}" fill="{oro}" opacity=".7" transform="skewX(-12)"/>')
    return (f'<svg class="decoracion" viewBox="0 0 {w} {h}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'
            f'<defs><linearGradient id="dv{tipo}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity="0"/></linearGradient></defs>'
            f'{"".join(partes)}</svg>')
