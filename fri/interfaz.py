"""Interfaz FRI sobre el dashboard existente (etapas F0 y F1).

EL INTERRUPTOR
    FRI_INTERFAZ (variable de entorno). Por defecto «clasica»: el dashboard se ve y funciona exactamente como antes.
    Con FRI_INTERFAZ=fri se usa esta interfaz; en ese modo, ?ui=clasica en la URL permite volver a la clásica (y ?ui=fri
    regresar). Con «clasica» configurado, ?ui=fri NO activa FRI: producción no cambia hasta que se decida.
    La interfaz FRI requiere el tema oscuro de Streamlit (STREAMLIT_THEME_BASE=dark, por ejemplo).

CÓMO REUTILIZA LOS MOTORES
    navegar() dibuja el menú lateral, la barra superior, la cabecera y las pestañas, y devuelve el NOMBRE de la sección
    clásica que corresponde (p. ej. «Renta Fija»). app/dashboard.py usa ese nombre como su `_seccion` de siempre, así
    que ejecuta el mismo bloque de código, con las mismas funciones y consultas. Esta interfaz no calcula nada ni
    duplica motores. Si la pestaña elegida no tiene todavía una sección existente, devuelve None y muestra qué falta.

DATOS
    Esta interfaz no contiene datos. Solo rotula la base local sintética cuando el lanzador de desarrollo
    (app/fri_local.py) define FRI_DATOS_LOCALES_SINTETICOS=1."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from fri import componentes as c
from fri.estilos import CSS, T

SANTIAGO = ZoneInfo("America/Santiago")
MODOS = ("clasica", "fri")

# (clave, nombre en el menú, icono)
SECCIONES_FRI = [
    ("inicio", "Inicio", "inicio"), ("macro", "Macroeconomía", "macro"), ("mercados", "Mercados", "mercados"),
    ("riesgo", "Riesgo y derivados", "riesgo"), ("investigacion", "Investigación", "investigacion"), ("informes", "Informes", "informes"),
]
ENCABEZADOS = {
    "macro": ("Macroeconomía", "Panorama económico de Chile y su entorno relevante", "macro"),
    "mercados": ("Mercados", "Evolución de los principales mercados financieros y condiciones de inversión.", "barras"),
    "riesgo": ("Riesgo y derivados", "Medición, análisis y gestión de riesgos, diversificación y valorización de derivados.", "riesgo"),
    "investigacion": ("Investigación", "Asistente de análisis económico y financiero", "investigacion"),
    "informes": ("Informes", "Análisis semanal, perspectivas de mercados y archivo de informes.", "informes"),
}
# Pestañas de cada sección (estructura aprobada) -> secciones clásicas que se ejecutan en ellas (None: aún no hay).
PESTANAS: dict[str, list[tuple[str, list[str] | None]]] = {
    "macro": [
        ("Panorama general", ["Indicadores macro"]), ("Actividad", None), ("Inflación", None), ("Mercado laboral", None),
        ("Política monetaria", None), ("Sector externo", None), ("Condiciones financieras", None),
    ],
    "mercados": [
        ("Panorama general", None),
        ("Renta variable", ["Renta Variable y ETFs", "Acciones IPSA", "Atribución IPSA", "Acciones Dow Jones", "Benchmark"]),
        ("Renta fija", ["Renta Fija"]), ("Divisas", ["FX y Carry Trade"]), ("Materias primas", ["Commodities"]),
    ],
    "riesgo": [
        ("Panorama general", None), ("Análisis de riesgo", ["Riesgo"]), ("Correlaciones y diversificación", None), ("Derivados", ["Derivados"]),
    ],
    "investigacion": [("Investigador", None), ("Regulación financiera", None), ("Investigaciones guardadas", None)],
    "informes": [("Informes", None)],
}
# Rótulos FRI para las secciones clásicas dentro de una pestaña con varias.
ROTULOS = {"Renta Variable y ETFs": "ETF y mercados", "Acciones IPSA": "Acciones IPSA", "Atribución IPSA": "Atribución IPSA",
           "Acciones Dow Jones": "Acciones Dow Jones", "Benchmark": "Comparación internacional"}
# Secciones que siguen disponibles SOLO en la interfaz clásica (no se eliminan; su ubicación en FRI no está decidida
# o la especificación las deja fuera de la navegación principal).
SOLO_INTERFAZ_CLASICA = ("Brief Premercado", "Laboratorio Financiero", "Modelo de Recesión EEUU")
# Qué falta en cada pestaña sin sección existente (se muestra en pantalla; nunca se reemplaza con datos inventados).
PENDIENTES = {
    ("macro", "Actividad"): "PIB, Imacec, evolución sectorial y coyuntura.",
    ("macro", "Inflación"): "IPC, componentes, dinámica y expectativas con datos válidos.",
    ("macro", "Mercado laboral"): "Desempleo, ocupación y su evolución.",
    ("macro", "Política monetaria"): "TPM, transmisión, expectativas y comparación internacional (DFF como tasa efectiva).",
    ("macro", "Sector externo"): "Comercio, tipo de cambio y contexto internacional.",
    ("macro", "Condiciones financieras"): "Tasas, curvas, spreads y condiciones de financiamiento.",
    ("mercados", "Panorama general"): "Indicadores del IPSA, S&P 500, tasa a 10 años de Chile y USD/CLP, gráfico del IPSA y curva soberana (etapa F2). "
                                      "El IPSA necesita antes una fuente directa: ECH no se presenta como IPSA.",
    ("riesgo", "Panorama general"): "Volatilidad, VaR, drawdown y correlación del IPSA (requiere validar los motores sobre el índice, no sobre ECH).",
    ("riesgo", "Correlaciones y diversificación"): "Matrices, correlaciones móviles y carteras. Los motores existen en el Laboratorio Financiero, "
                                                   "que por ahora sigue disponible en la interfaz clásica.",
    ("investigacion", "Investigador"): "Conversación con fuentes verificables y cálculos deterministas de FRI.",
    ("investigacion", "Regulación financiera"): "Observatorio «Qué cambió y por qué importa» (Basilea III, CMF, NIIF).",
    ("investigacion", "Investigaciones guardadas"): "Biblioteca de investigaciones y expedientes, con versiones.",
    ("informes", "Informes"): "Informe semanal dominical (3–4 páginas) y su archivo. El PDF de renta fija existente está en Mercados → Renta fija.",
}


# ---------------------------------------------------------------------------
# Interruptor
# ---------------------------------------------------------------------------
def modo_configurado() -> str:
    """El modo de la variable de entorno FRI_INTERFAZ; cualquier valor desconocido es «clasica»."""
    modo = os.environ.get("FRI_INTERFAZ", "clasica").strip().lower()
    return modo if modo in MODOS else "clasica"


def modo_activo(query_params) -> bool:
    """True si esta carga usa la interfaz FRI. Solo es posible con FRI_INTERFAZ=fri; ?ui=clasica vuelve a la clásica."""
    return modo_configurado() == "fri" and str(query_params.get("ui", "fri")).lower() != "clasica"


def secciones_cubiertas() -> set[str]:
    return {s for pestañas in PESTANAS.values() for _, secciones in pestañas for s in (secciones or [])}


# ---------------------------------------------------------------------------
# Piezas comunes
# ---------------------------------------------------------------------------
def _fecha_larga(d) -> str:
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return f"{dias[d.weekday()].capitalize()}, {d.day} de {meses[d.month - 1]} de {d.year}"


def proxima_publicacion(ahora: datetime) -> datetime:
    """El próximo domingo a las 10:00 de Santiago (si hoy es domingo antes de las 10:00, hoy)."""
    objetivo = ahora.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=(6 - ahora.weekday()) % 7)
    return objetivo if objetivo > ahora else objetivo + timedelta(days=7)


def _menu(seccion: str, autora: str = "") -> None:
    enlaces = "".join(
        f'<a href="?s={clave}" target="_self" class="{"activo" if clave == seccion else ""}">'
        f'{c.icono(ic, 21, T["dorado"] if clave == seccion else T["texto_2"])}<span>{nombre}</span></a>'
        for clave, nombre, ic in SECCIONES_FRI
    )
    st.sidebar.markdown(
        f"""<div class="fri-marca"><div class="logo">{c.logo_barras(30)}FRI</div>
        <div class="nombre">Financial Research<br>Intelligence</div><div class="filete"></div>
        <div class="lema">Análisis económico<br>y financiero</div></div>
        <nav class="fri-nav">{enlaces}</nav>
        <div class="fri-enlace-clasica"><a href="?ui=clasica" target="_self">Interfaz clásica →</a></div>
        <div class="fri-pie-menu">FRI{f"<small>Creado por {autora}</small>" if autora else ""}</div>""",
        unsafe_allow_html=True,
    )


def _barra_superior() -> None:
    """La misma barra en todas las secciones interiores. Sin campana (FRI no tendrá alertas intradía); los controles
    que todavía no funcionan se ven inactivos."""
    st.markdown(
        f"""<div class="fri-barra"><div class="titulo">{c.logo_barras(24)}Financial Research Intelligence<span class="sep"></span>
        <span class="sub">Investigación económica y financiera de Chile y el mundo</span></div>
        <div class="acciones"><span class="fri-control-pendiente" title="Pendiente de implementación">{c.icono('buscar', 17, T['texto_3'])}Explorar gráficos<em>PENDIENTE</em></span></div></div>""",
        unsafe_allow_html=True,
    )


def _encabezado(seccion: str, actualizacion: str = "") -> None:
    titulo, bajada, ic = ENCABEZADOS[seccion]
    meta = f'<div class="meta">{c.icono("calendario", 20)}<div>{actualizacion}</div></div>' if actualizacion else ""
    st.markdown(f'<div class="fri-encabezado"><div class="texto">{c.icono(ic, 42, grosor=1.4)}<div><div class="h1">{titulo}</div>'
                f'<p>{bajada}</p></div></div>{meta}</div>', unsafe_allow_html=True)


def _aviso_base_local() -> None:
    if os.environ.get("FRI_DATOS_LOCALES_SINTETICOS") == "1":
        st.markdown(c.aviso_sintetico("Base local con cifras inventadas (FRI-local/crear_base_sintetica.py). "
                                      "Ninguna cifra de esta sesión es real."), unsafe_allow_html=True)


def _pendiente(texto: str, nota_clasica: str = "") -> None:
    st.markdown(f'<div class="fri-pendiente" style="grid-template-columns:1fr"><div class="caja"><p>{texto}</p>'
                f'<span class="estado estado-pendiente">PENDIENTE DE IMPLEMENTACIÓN</span>{nota_clasica}</div></div>', unsafe_allow_html=True)


def _texto_actualizacion(cargar_ultima_actualizacion) -> str:
    try:
        meta = cargar_ultima_actualizacion()
        nombres = {"bcch": "BCCh", "yfinance": "Yahoo Finance"}
        partes = [f"{nombres.get(f['fuente'], f['fuente'])}: {f['ultima_actualizacion'].strftime('%d-%m-%Y %H:%M')}" for _, f in meta.iterrows()]
        return "Última actualización<br>" + "<br>".join(partes) if partes else ""
    except Exception:
        return "Sin información de actualización"


# ---------------------------------------------------------------------------
# Inicio
# ---------------------------------------------------------------------------
def _inicio() -> None:
    ahora = datetime.now(SANTIAGO)
    prox = proxima_publicacion(ahora)
    st.markdown(
        f"""<div class="fri-portada"><div class="fecha">{c.icono('calendario', 20)} {_fecha_larga(ahora)}<span style="color:{T['borde_fuerte']}">|</span>
        {c.icono('lugar', 20)} Santiago de Chile</div>
        <div class="contenido"><div class="ruta">INICIO <span class="linea"></span></div>
        <div class="h1">Financial Research<br>Intelligence</div><div class="subtitulo">Análisis económico y financiero</div>
        <div class="bajada">Investigación, mercados, riesgo y valorización con un enfoque riguroso en la economía chilena y su contexto global.</div>
        </div></div>""",
        unsafe_allow_html=True,
    )
    tarjetas = [
        ("macro", "macro", "Macroeconomía", "Actividad, inflación, mercado laboral, política monetaria y sector externo."),
        ("mercados", "mercados", "Mercados", "Renta variable, renta fija, divisas y materias primas, con foco en el IPSA y el cobre."),
        ("riesgo", "riesgo", "Riesgo y derivados", "Medición y análisis de riesgos, correlaciones, diversificación y valorización de derivados."),
        ("investigacion", "investigacion", "Investigación", "Análisis asistido por IA, observatorio regulatorio y biblioteca personal."),
        ("informes", "informes", "Informes", "Informe semanal de mercados, con análisis de coyuntura, riesgos y perspectivas."),
    ]
    st.markdown('<div class="fri-tarjetas">' + "".join(
        f'<div class="fri-tarjeta-nav">{c.decoracion(s)}{c.icono(ic, 38, grosor=1.3)}<div class="h3">{t}</div><p>{d}</p>'
        f'<a href="?s={s}" target="_self">Ir a {t} {c.icono("flecha", 18)}</a></div>' for s, ic, t, d in tarjetas) + "</div>",
        unsafe_allow_html=True)
    st.markdown(
        f"""<div class="fri-foco"><div class="imagen"></div>
        <div><div class="etiqueta">EN FOCO</div><div class="h3">Espacio editorial</div>
        <p>Aquí aparecerá el análisis destacado de la semana, escrito con datos verificados. Todavía no está implementado.</p>
        <span class="boton-inactivo" title="Pendiente de implementación">Leer análisis {c.icono('flecha', 16, T['texto_3'])}</span>
        <span class="estado estado-pendiente" style="margin-left:10px">PENDIENTE</span></div>
        <div class="proximo"><div class="etiqueta">{c.icono('calendario', 20)} PRÓXIMO INFORME</div>
        <b>Informe semanal de mercados</b><span>{_fecha_larga(prox)} · 10:00 (Santiago)</span><br>
        <span style="font-size:13px;color:{T['texto_3']}">Publicación prevista; el motor del informe dominical aún no está implementado.</span></div></div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Navegación
# ---------------------------------------------------------------------------
def navegar(cargar_ultima_actualizacion, autora: str = "") -> str | None:
    """Dibuja la interfaz FRI y devuelve la sección clásica que el dashboard debe ejecutar (o None)."""
    st.markdown(CSS, unsafe_allow_html=True)
    seccion = str(st.query_params.get("s", "inicio"))
    if seccion not in {s for s, _, _ in SECCIONES_FRI}:
        seccion = "inicio"
    _menu(seccion, autora)
    if seccion == "inicio":   # la portada no lleva barra superior (diseño aprobado)
        _aviso_base_local()
        _inicio()
        return None
    _barra_superior()
    _encabezado(seccion, _texto_actualizacion(cargar_ultima_actualizacion))
    pestañas = PESTANAS[seccion]
    nombres = [n for n, _ in pestañas]
    elegida = st.segmented_control("Pestaña", nombres, default=nombres[0], key=f"fri_pestana_{seccion}",
                                   label_visibility="collapsed") or nombres[0] if len(nombres) > 1 else nombres[0]
    _aviso_base_local()
    secciones = dict(pestañas)[elegida]
    if not secciones:
        nota = (' <span class="estado estado-existente" style="margin-left:8px">EN LA INTERFAZ CLÁSICA</span>'
                if (seccion, elegida) == ("riesgo", "Correlaciones y diversificación") else "")
        _pendiente(PENDIENTES.get((seccion, elegida), "Pendiente de implementación."), nota)
        return None
    if len(secciones) == 1:
        return secciones[0]
    rotulos = [ROTULOS.get(s, s) for s in secciones]
    sub = st.segmented_control("Apartado", rotulos, default=rotulos[0], key=f"fri_apartado_{seccion}_{elegida}",
                               label_visibility="collapsed") or rotulos[0]
    return secciones[rotulos.index(sub)]
