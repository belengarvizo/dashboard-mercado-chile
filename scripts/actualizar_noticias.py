"""
Descarga titulares recientes (últimas 48 horas) de fuentes de noticias
económicas chilenas vía RSS y los guarda en la base de datos, evitando
duplicados. Alimenta la sección "Titulares relevantes" del Brief
Premercado. Corre junto a los demás scripts de actualización.

Nota sobre las fuentes: Diario Financiero tiene RSS propio. La Tercera
Pulso y Emol Economía NO tienen un feed RSS propio funcionando hoy (se
verificó: La Tercera marca "rss": null en toda su configuración de
sitio, y el sistema legado de Emol en rss.emol.com está caído), así que
para esas dos se usa una búsqueda de Google Noticias filtrada por sitio
como sustituto real y verificado (no es el feed oficial del medio).

Para La Tercera y Emol se hacen DOS búsquedas de Google Noticias: la de
"economía" (ventana 48h) y una segunda de agenda económica del gobierno
(FILTRO_REFORMA_ECONOMICA, ventana 120h) que rescata notas de reforma
previsional/tributaria, Hacienda, presupuesto y mercado de capitales que
no siempre llevan la palabra "economía" en el título. Las búsquedas
amplias de Google Noticias devuelven mezcladas páginas de etiqueta y
avisos clasificados ("MK4 - La Tercera", "Casa en Venta - Emol
Propiedades"): se filtran en _es_titular_no_editorial. Las notas que
aparecen en ambas búsquedas se deduplican por link y por título.

Yahoo Finance sí tiene RSS propio funcionando (requiere un User-Agent de
navegador o Yahoo devuelve "Too Many Requests"); se agrega como fuente
adicional de mercado internacional en inglés — el resumen diario en la
pestaña Brief Premercado la usa para la sección de panorama global, sin
reemplazar a las fuentes chilenas. Se usa el feed de titulares de
mercado atado al S&P 500 (`?s=^GSPC`), no el feed general de noticias
("news/rssindex"): el general mezcla contenido de finanzas personales
(tarjetas de crédito, seguros, tasas de depósito) que no aporta a un
brief de mercado; el de `^GSPC` trae solo movimientos de acciones,
índices y bonos — verificado en vivo antes de elegirlo.

MarketWatch se evaluó como fuente adicional (candidato: feed
"marketpulse") pero se descartó: aunque el RSS parsea sin error, sus
titulares más recientes tienen más de un año de antigüedad (probado en
vivo, igual que "realtimeheadlines") -- MarketWatch aparentemente
descontinuó la actualización en tiempo real de sus feeds públicos, así
que no sirve para un brief que necesita noticias del día.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import feedparser
from models import get_session, Noticia, MetadataActualizacion
from retry_utils import con_reintentos, con_reintentos_db

HORAS_VENTANA = 48

# Ventana más larga para la segunda búsqueda de La Tercera y Emol (ver
# FILTRO_REFORMA_ECONOMICA): las notas de agenda legislativa/regulatoria
# económica avanzan más lento que las de mercado, así que 48h se queda corto.
HORAS_VENTANA_REFORMA = 120

# Segunda búsqueda para La Tercera y Emol, además de la de "economía": agenda
# económica del gobierno que a menudo NO lleva la palabra "economía" en el
# título (proyectos de Hacienda, reforma previsional/tributaria, mercado de
# capitales, presupuesto, aranceles, salario mínimo). Se excluyen a propósito
# "reforma" y "Congreso" a secas -- arrastran todo el beat legislativo de
# seguridad, que no aporta a un brief de mercado. "fiscal" también se dejó
# fuera: Google Noticias lo matchea con "Fiscalía" y colaba notas de crimen;
# "gasto público" cubre el mismo terreno sin ese falso positivo (y "Consejo
# Fiscal Autónomo" igual entra por "Hacienda").
FILTRO_REFORMA_ECONOMICA = (
    '(Hacienda OR presupuesto OR "mercado de capitales" OR "proyecto de ley" '
    'OR previsional OR tributaria OR "Banco Central" OR arancel '
    'OR "salario mínimo" OR "gasto público")'
)


def _url_google_reforma(sitio: str) -> str:
    """Arma la URL de Google Noticias para la segunda búsqueda (agenda
    económica del gobierno) sobre un sitio, con ventana de 5 días."""
    consulta = f"site:{sitio} {FILTRO_REFORMA_ECONOMICA} when:5d"
    return (
        "https://news.google.com/rss/search?q="
        + quote(consulta, safe="")
        + "&hl=es-419&gl=CL&ceid=CL:es-419"
    )


# Cada fuente mapea a una lista de (url, horas_ventana). La Tercera y Emol
# tienen dos búsquedas: la de "economía" (48h) y la de agenda económica del
# gobierno (120h). Las notas repetidas entre ambas se deduplican por link y
# por título antes de guardar.
FUENTES_RSS = {
    "Diario Financiero": [
        ("https://www.df.cl/noticias/site/list/port/rss.xml", HORAS_VENTANA),
    ],
    "La Tercera Pulso": [
        ("https://news.google.com/rss/search?q=site:latercera.com+econom%C3%ADa+when:2d&hl=es-419&gl=CL&ceid=CL:es-419", HORAS_VENTANA),
        (_url_google_reforma("latercera.com"), HORAS_VENTANA_REFORMA),
    ],
    "Emol Economía": [
        ("https://news.google.com/rss/search?q=site:emol.com+econom%C3%ADa+when:2d&hl=es-419&gl=CL&ceid=CL:es-419", HORAS_VENTANA),
        (_url_google_reforma("emol.com"), HORAS_VENTANA_REFORMA),
    ],
    "Yahoo Finance": [
        ("https://finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US", HORAS_VENTANA),
    ],
}

# Sub-marcas no editoriales (avisos clasificados, guías) que Google Noticias
# mezcla con las notas cuando la búsqueda es amplia. Se detectan por el
# dominio real de la fuente (entry.source.href, que sí trae el sitio de
# destino aunque entry.link sea un redirect opaco de Google) y por el sufijo
# del título.
DOMINIOS_NO_EDITORIALES = (
    "emol.com/propiedades",
    "amarillas.com",
    "latercera.com/propiedades",
)
SUFIJOS_NO_EDITORIALES = (
    " - Emol Propiedades",
    " - La Tercera Propiedades",
    " - amarillas.com",
)
SUFIJOS_MEDIO = (" - La Tercera", " - Emol")


def _es_titular_no_editorial(titulo: str, source_href: str) -> bool:
    """True si el "titular" es en realidad una página de etiqueta/tema o un
    aviso clasificado, no una nota. Google Noticias los devuelve mezclados
    cuando la query es amplia (ej. "MK4 - La Tercera", "audio espacial",
    "Casa en Venta en Temuco - Emol Propiedades")."""
    href = (source_href or "").lower()
    if any(dominio in href for dominio in DOMINIOS_NO_EDITORIALES):
        return True

    base = titulo.strip()
    if any(base.endswith(sufijo) for sufijo in SUFIJOS_NO_EDITORIALES):
        return True
    for sufijo in SUFIJOS_MEDIO:
        if base.endswith(sufijo):
            base = base[: -len(sufijo)].strip()
            break
    # Fragmentos de 3 palabras o menos ("MK4", "Recaudación 7%",
    # "Negociaciones parlamentarias") son páginas de etiqueta.
    if len(base.split()) <= 3:
        return True
    # Un titular de verdad arranca con mayúscula (nombre propio o inicio de
    # oración); "audio espacial", "integración ChatGPT en Sonos" no.
    if base[:1].islower():
        return True
    return False


# Yahoo Finance bloquea con "Too Many Requests" sin un User-Agent de
# navegador (las otras fuentes no lo necesitan).
USER_AGENT_NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def descargar_titulares(url: str, horas_ventana: int = HORAS_VENTANA) -> list[dict]:
    """Descarga un feed RSS y devuelve los titulares de las últimas
    `horas_ventana` horas, descartando páginas de etiqueta y avisos
    clasificados (ver _es_titular_no_editorial)."""
    feed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT_NAVEGADOR})
    limite = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=horas_ventana)

    resultado = []
    for entrada in feed.entries:
        if not entrada.get("published_parsed") or not entrada.get("link") or not entrada.get("title"):
            continue
        source_href = ""
        if entrada.get("source"):
            source_href = entrada.source.get("href", "") or ""
        if _es_titular_no_editorial(entrada.title, source_href):
            continue
        # feedparser normaliza published_parsed a UTC.
        fecha_publicacion = datetime(*entrada.published_parsed[:6])
        if fecha_publicacion < limite:
            continue
        resultado.append({
            "titulo": entrada.title,
            "link": entrada.link,
            "fecha_publicacion": fecha_publicacion,
        })

    return resultado


def actualizar_todas_las_noticias():
    session = get_session()

    try:
        for fuente, busquedas in FUENTES_RSS.items():
            print(f"Descargando titulares de {fuente}...")
            # El fetch del feed RSS es propenso a cortes transitorios de red
            # (ej. Google Noticias resetea la conexión de a ratos).
            #
            # Dedup nivel 1 (dentro de la corrida): una fuente puede tener
            # varias búsquedas (economía + agenda económica del gobierno) y la
            # misma nota puede salir en ambas, con link idéntico o con un link
            # distinto pero el mismo título. Se descarta por cualquiera de los
            # dos antes de tocar la BD.
            titulares = []
            vistos_link = set()
            vistos_titulo = set()
            for url, horas in busquedas:
                for t in con_reintentos(descargar_titulares, url, horas):
                    titulo_norm = t["titulo"].strip().lower()
                    if t["link"] in vistos_link or titulo_norm in vistos_titulo:
                        continue
                    vistos_link.add(t["link"])
                    vistos_titulo.add(titulo_norm)
                    titulares.append(t)

            def _guardar_titulares(fuente=fuente, titulares=titulares):
                # Dedup nivel 2 (contra lo ya guardado): por link y por título
                # normalizado, para no reinsertar una nota que ya está bajo
                # esta fuente con otro link.
                links_existentes = {
                    link for (link,) in session.query(Noticia.link).filter_by(fuente=fuente)
                }
                titulos_existentes = {
                    titulo.strip().lower()
                    for (titulo,) in session.query(Noticia.titulo).filter_by(fuente=fuente)
                }

                nuevas = [
                    Noticia(
                        fuente=fuente,
                        titulo=t["titulo"],
                        link=t["link"],
                        fecha_publicacion=t["fecha_publicacion"],
                        fecha_descarga=datetime.now(),
                    )
                    for t in titulares
                    if t["link"] not in links_existentes
                    and t["titulo"].strip().lower() not in titulos_existentes
                ]

                if nuevas:
                    session.bulk_save_objects(nuevas)
                session.commit()
                return len(nuevas)

            # Se reintenta la lectura de lo ya guardado + la escritura como una
            # sola unidad: es idempotente (compara contra lo ya guardado), así
            # que reintentarla completa ante un corte de conexión es seguro.
            n_nuevas = con_reintentos_db(session, _guardar_titulares)
            print(f"  -> {len(titulares)} titulares únicos en ventana, {n_nuevas} nuevos")

        def _guardar_metadata():
            meta = session.query(MetadataActualizacion).filter_by(fuente="noticias").first()
            if meta:
                meta.ultima_actualizacion = datetime.now()
            else:
                session.add(MetadataActualizacion(fuente="noticias", ultima_actualizacion=datetime.now()))
            session.commit()

        con_reintentos_db(session, _guardar_metadata)
        print("Actualización de noticias completada.")

    except Exception as e:
        session.rollback()
        print(f"Error actualizando noticias: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    actualizar_todas_las_noticias()
