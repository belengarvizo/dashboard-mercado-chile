"""Sección Informes de FRI (etapa F3).

Qué hay y qué no:
    - Informe semanal (dominical, 3–4 páginas): NO está implementado. La pantalla muestra su estado real (sin ediciones,
      publicación deshabilitada) y la próxima fecha prevista. No hay tarea programada ni generación con IA.
    - Archivo de informes: estructura preparada; no hay almacenamiento persistente de ediciones (decisión pendiente,
      ver la especificación: GitHub no es base de datos y el disco del servicio no es persistente). Se muestra vacío.
    - Informes especializados: el PDF de renta fija EXISTENTE (informe_renta_fija.generar), con el mismo botón que en
      Mercados → Renta fija (renta_fija_ui._descarga_del_informe). Se rotula como especializado: no es el dominical.
    - El Brief Premercado diario sigue solo en la interfaz clásica y no se presenta como informe dominical.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import reloj  # H3-D2: reloj centralizado (America/Santiago)

from fri import componentes as c
from fri.estilos import T

SANTIAGO = ZoneInfo("America/Santiago")
ESTADO_INFORME_SEMANAL = "No implementado"           # estado real: no existe motor, almacenamiento ni tarea programada
PUBLICACION_HABILITADA = False                        # cualquier publicación queda deshabilitada hasta que exista el motor


def _titulo(texto: str, nota: str = "") -> None:
    st.markdown(f'<div class="fri-panel-titulo"><div class="t">{texto}</div><span>{nota}</span></div>', unsafe_allow_html=True)


def informe_semanal(fecha_larga, proxima_publicacion) -> None:
    prox = proxima_publicacion(reloj.ahora_santiago())
    izq, der = st.columns([1.6, 1], gap="medium")
    with izq, st.container(border=True):
        _titulo("Informe semanal de mercados", "Domingos 10:00 (Santiago)")
        st.markdown(
            f'<p style="color:{T["texto_2"]};font-size:15px">Estado: <b style="color:{T["texto"]}">{ESTADO_INFORME_SEMANAL}</b>. '
            f'Todavía no hay ediciones publicadas: el motor del informe dominical (3–4 páginas, blanco, negro y acentos rojos), su '
            f'almacenamiento y su programación no están implementados. No se generan informes de prueba ni textos ficticios.</p>'
            f'<span class="boton-inactivo" title="Deshabilitado: sin ediciones">Leer informe (PDF)</span> '
            f'<span class="boton-inactivo" title="Deshabilitado: sin ediciones" style="margin-left:8px">Descargar PDF</span>',
            unsafe_allow_html=True)
    with der, st.container(border=True):
        _titulo("Fecha prevista", "No programada")
        st.markdown(f'<p style="font-family:Georgia,serif;font-size:24px;color:{T["texto"]};margin:6px 0">{fecha_larga(prox)} · 10:00</p>'
                    f'<p style="color:{T["texto_2"]};font-size:14.5px">Es la fecha que corresponde por calendario (domingo 10:00 de '
                    f'Santiago), <b>no una publicación programada</b>: no existe ninguna tarea que publique y la publicación automática está '
                    f'deshabilitada. Una edición semanal; sin informes diarios, alertas intradía ni correos.</p>', unsafe_allow_html=True)


def archivo() -> None:
    with st.container(border=True):
        _titulo("Archivo de informes", "Ediciones semanales y reportes especiales")
        st.markdown(f'<div class="fri-control-pendiente" style="padding:9px 14px;margin:6px 0 10px 0;width:fit-content">'
                    f'{c.icono("buscar", 18, T["texto_3"])}Buscar en el archivo<em>DESHABILITADO</em></div>', unsafe_allow_html=True)
        st.markdown(c.tabla(["Informe", "Tipo", "Fecha de publicación", "Tamaño"], [["Sin ediciones publicadas", "—", "—", "—"]]),
                    unsafe_allow_html=True)
        st.markdown('<div class="fri-nota">El archivo será permanente e inmutable: una edición publicada no se sobrescribe. El '
                    'almacenamiento persistente está pendiente de decisión (sin costo adicional). No se muestran ediciones ficticias.</div>',
                    unsafe_allow_html=True)


def especializados(cargadores: dict | None) -> None:
    import renta_fija_ui as rfui
    from constants import TICKERS_RENTA_FIJA
    with st.container(border=True):
        _titulo("Informe especializado de renta fija (PDF)", "Especializado · no es el informe semanal")
        st.markdown('<span class="estado estado-existente">INFORME ESPECIALIZADO EXISTENTE · SE ARMA A PEDIDO</span>', unsafe_allow_html=True)
        st.markdown(f'<p style="color:{T["texto_2"]};font-size:14.5px">Es el mismo informe de Mercados → Renta fija: '
                    f'<b>no es el informe dominical</b> de FRI. Explica qué pasó con los bonos del Tesoro y el crédito en el período y '
                    f'qué parte es compatible con la sensibilidad a tasas.</p>', unsafe_allow_html=True)
        if not cargadores:
            st.markdown(f'<p style="color:{T["texto_3"]}">No disponible: sin acceso a los datos del dashboard.</p>', unsafe_allow_html=True)
            return
        try:
            macro = cargadores["macro"]()
            precios = cargadores["precios"](tickers=tuple(TICKERS_RENTA_FIJA) + ("^GSPC",))
        except Exception as e:  # noqa: BLE001  se dice qué falló; no se arma un informe con datos incompletos
            st.warning(f"No se pudieron cargar los datos del informe: {e}")
            return
        ancho = rfui._precios_en_columnas(precios)
        if ancho.empty:
            st.markdown(f'<p style="color:{T["texto_3"]}">No disponible: la base no tiene precios de los ETF de bonos.</p>', unsafe_allow_html=True)
            return
        rfui._descarga_del_informe(rfui._recortar(macro), ancho)
    with st.container(border=True):
        _titulo("Brief Premercado (diario)", "Interfaz clásica")
        st.markdown(f'<p style="color:{T["texto_2"]};font-size:14.5px">El brief diario sigue disponible en la interfaz clásica y '
                    f'dejará de ejecutarse cuando exista el informe dominical (decisión aprobada). No se presenta como informe semanal.</p>',
                    unsafe_allow_html=True)
