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
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import feedparser
from models import get_session, Noticia, MetadataActualizacion

HORAS_VENTANA = 48

FUENTES_RSS = {
    "Diario Financiero": "https://www.df.cl/noticias/site/list/port/rss.xml",
    "La Tercera Pulso": "https://news.google.com/rss/search?q=site:latercera.com+econom%C3%ADa+when:2d&hl=es-419&gl=CL&ceid=CL:es-419",
    "Emol Economía": "https://news.google.com/rss/search?q=site:emol.com+econom%C3%ADa+when:2d&hl=es-419&gl=CL&ceid=CL:es-419",
}


def descargar_titulares(url: str) -> list[dict]:
    """Descarga un feed RSS y devuelve los titulares de las últimas HORAS_VENTANA horas."""
    feed = feedparser.parse(url)
    limite = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=HORAS_VENTANA)

    resultado = []
    for entrada in feed.entries:
        if not entrada.get("published_parsed") or not entrada.get("link") or not entrada.get("title"):
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
        for fuente, url in FUENTES_RSS.items():
            print(f"Descargando titulares de {fuente}...")
            titulares = descargar_titulares(url)

            links_existentes = {
                link for (link,) in session.query(Noticia.link).filter_by(fuente=fuente)
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
            ]

            if nuevas:
                session.bulk_save_objects(nuevas)
            session.commit()
            print(f"  -> {len(titulares)} titulares en ventana de {HORAS_VENTANA}h, {len(nuevas)} nuevos")

        meta = session.query(MetadataActualizacion).filter_by(fuente="noticias").first()
        if meta:
            meta.ultima_actualizacion = datetime.now()
        else:
            session.add(MetadataActualizacion(fuente="noticias", ultima_actualizacion=datetime.now()))

        session.commit()
        print("Actualización de noticias completada.")

    except Exception as e:
        session.rollback()
        print(f"Error actualizando noticias: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    actualizar_todas_las_noticias()
