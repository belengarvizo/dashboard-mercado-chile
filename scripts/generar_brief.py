"""
Genera el resumen diario del Brief Premercado (secciones "Global Overview" y
"Possible Effects for Chile", en inglés — es la única pestaña del dashboard
que queda en ese idioma) usando Gemini, a partir de los titulares recientes y
los indicadores de mercado del día. Se corre una vez al día como parte del
cron job de Railway — el dashboard nunca llama a Gemini directamente, solo
lee el resultado ya guardado en la tabla brief_diario.

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

PROMPT_TEMPLATE = """You are a financial analyst preparing a morning brief for \
investors in Chile, before the Santiago Stock Exchange opens.

International market indicators (latest available session):
{indicadores}

Recent headlines from Chilean and international financial press (titles may be \
in Spanish — read them in Spanish, but write your summary in English):
{titulares}

Write a summary in English, in Markdown format, with exactly these two sections \
(use these exact titles, as level-2 headings):

## Global Overview
3 to 5 bullet points synthesizing the day's most relevant themes based on the \
indicators and headlines above. Use measured, non-sensationalist language.

## Possible Effects for Chile
How those themes could connect to copper, the exchange rate (USD/CLP), or the \
local market (IPSA). Always use cautious language ("could", "it's possible that", \
"eventually") — never categorical causal claims or guarantees about future price \
movements."""


def construir_prompt(titulares: list[dict], indicadores: list[dict]) -> str:
    lineas_indicadores = []
    for ind in indicadores:
        if ind["resultado"] is None:
            continue
        valor, cambio_pct, _fecha, cambio_absoluto = ind["resultado"]
        unidad = f" {ind['unidad']}" if ind["unidad"] else ""
        # Si el indicador ya es una tasa/porcentaje, el cambio se reporta en
        # puntos porcentuales (ver market_data.calcular_cambio_reciente) para
        # que Gemini no reciba, ej., "-18,8%" cuando en realidad la tasa bajó
        # 0,82 puntos porcentuales.
        if ind["unidad"] == "%":
            texto_cambio = f"{cambio_absoluto:+.2f} pp vs. sesión anterior"
        else:
            texto_cambio = f"{cambio_pct:+.2f}% vs. sesión anterior"
        lineas_indicadores.append(f"- {ind['etiqueta']}: {valor:,.2f}{unidad} ({texto_cambio})")

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
