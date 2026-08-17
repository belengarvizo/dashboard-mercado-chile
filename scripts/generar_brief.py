"""
Genera el resumen diario del Brief Premercado (secciones "Panorama global" y
"Posibles efectos para Chile") usando Gemini, a partir de los titulares
recientes y los indicadores de mercado del día. Se corre una vez al día como
parte del cron job de Railway — el dashboard nunca llama a Gemini directamente,
solo lee el resultado ya guardado en la tabla brief_diario.

Requiere la variable de entorno:
  GEMINI_API_KEY -> API key de Google AI Studio para Gemini
"""

import os
import sys
from datetime import date, datetime, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from google import genai
from models import get_session, get_engine, Noticia, BriefDiario
from market_data import calcular_resumen_mercado

MODELO_GEMINI = "gemini-3.6-flash"
HORAS_VENTANA_TITULARES = 48
# Las fuentes vía Google Noticias (ver actualizar_noticias.py) traen algo de
# ruido no económico; se limita a los más recientes para que el prompt no se
# diluya ni crezca sin control.
MAX_TITULARES_PROMPT = 60

PROMPT_TEMPLATE = """Eres un analista financiero que prepara un brief matutino para \
inversionistas en Chile, antes de que abra la Bolsa de Santiago.

Indicadores de mercado internacional (última sesión disponible):
{indicadores}

Titulares recientes de prensa económica chilena e internacional:
{titulares}

Escribe un resumen en español, en formato Markdown, con exactamente estas dos \
secciones (usa esos títulos exactos, como encabezados de nivel 2):

## Panorama global
3 a 5 puntos (viñetas) sintetizando los temas más relevantes del día a partir de \
los indicadores y titulares de arriba. Usa un lenguaje moderado y no sensacionalista.

## Posibles efectos para Chile
Cómo esos temas podrían conectar con el cobre, el tipo de cambio (USD/CLP) o el \
mercado local (IPSA). Usa siempre lenguaje cauteloso ("podría", "es posible que", \
"eventualmente") — nunca afirmaciones causales categóricas ni garantías sobre \
movimientos futuros de precios."""


def construir_prompt(titulares: list[dict], indicadores: list[dict]) -> str:
    lineas_indicadores = []
    for ind in indicadores:
        if ind["resultado"] is None:
            continue
        valor, cambio_pct, _fecha = ind["resultado"]
        unidad = f" {ind['unidad']}" if ind["unidad"] else ""
        lineas_indicadores.append(f"- {ind['etiqueta']}: {valor:,.2f}{unidad} ({cambio_pct:+.2f}% vs. sesión anterior)")

    lineas_titulares = [f"- [{t['fuente']}] {t['titulo']}" for t in titulares]

    return PROMPT_TEMPLATE.format(
        indicadores="\n".join(lineas_indicadores) if lineas_indicadores else "(sin datos disponibles)",
        titulares="\n".join(lineas_titulares) if lineas_titulares else "(sin titulares disponibles)",
    )


def obtener_titulares_recientes(session) -> list[dict]:
    limite = datetime.now() - timedelta(hours=HORAS_VENTANA_TITULARES)
    noticias = (
        session.query(Noticia)
        .filter(Noticia.fecha_publicacion >= limite)
        .order_by(Noticia.fecha_publicacion.desc())
        .limit(MAX_TITULARES_PROMPT)
        .all()
    )
    return [{"fuente": n.fuente, "titulo": n.titulo} for n in noticias]


def generar_brief_diario():
    session = get_session()

    try:
        api_key = os.environ["GEMINI_API_KEY"]

        titulares = obtener_titulares_recientes(session)

        engine = get_engine()
        df_macro = pd.read_sql("SELECT nombre, fecha, valor FROM series_macro ORDER BY fecha", engine)
        df_acciones = pd.read_sql("SELECT ticker, fecha, precio_cierre FROM precios_acciones ORDER BY fecha", engine)
        indicadores = calcular_resumen_mercado(df_macro, df_acciones)

        prompt = construir_prompt(titulares, indicadores)

        print(f"Llamando a Gemini ({MODELO_GEMINI}) con {len(titulares)} titulares y {len(indicadores)} indicadores...")
        cliente = genai.Client(api_key=api_key)
        respuesta = cliente.models.generate_content(model=MODELO_GEMINI, contents=prompt)
        contenido = respuesta.text

        hoy = date.today()
        existente = session.query(BriefDiario).filter_by(fecha=hoy).first()
        if existente:
            existente.contenido = contenido
            existente.generado_en = datetime.now()
        else:
            session.add(BriefDiario(fecha=hoy, contenido=contenido, generado_en=datetime.now()))

        session.commit()
        print("Brief diario generado y guardado.")

    except Exception as e:
        session.rollback()
        print(f"Error generando el brief diario: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    generar_brief_diario()
