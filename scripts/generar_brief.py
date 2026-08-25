"""
Genera el resumen diario del Brief Premercado (secciones "Global Overview",
"Financial Highlights", "Political & Geopolitical Events" — con Chile y
Global como subgrupos separados — y "Possible Effects for Chile", en inglés
— es la única pestaña del dashboard que queda en ese idioma) usando Gemini,
a partir de los titulares recientes y los indicadores de mercado del día.
Se corre una vez al día como parte del cron job de Railway — el dashboard
nunca llama a Gemini directamente, solo lee el resultado ya guardado en la
tabla brief_diario.

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
from market_data import calcular_resumen_mercado, calcular_atribucion_ipsa, VENTANA_ATRIBUCION_IPSA
from scripts.actualizar_noticias import FUENTES_RSS

MODELO_GEMINI = "gemini-3.6-flash"
HORAS_VENTANA_TITULARES = 48
# Cupo por FUENTE, no un corte único por fecha sobre todas juntas: con un
# solo corte global, una fuente de mucho volumen (ej. Emol vía Google
# Noticias, ~100 titulares en 48h) desplaza por completo a una de menor
# volumen (ej. Yahoo Finance, ~20) — se verificó en la práctica que esto
# dejaba a Yahoo en cero titulares dentro del prompt real. Con un cupo
# parejo por fuente, cada una llega con al menos algo (o con menos si ese
# día no tiene tanto contenido — no se rellena con más de otra fuente para
# no forzar contenido menos relevante solo por completar un número fijo).
# Cuál de esos titulares termina realmente usado en cada sección del
# resumen lo decide Gemini al redactar según relevancia, no este corte.
TITULARES_POR_FUENTE = 15

PROMPT_TEMPLATE = """You are a financial analyst preparing a morning brief for \
investors in Chile, before the Santiago Stock Exchange opens.

International market indicators (latest available session):
{indicadores}

Recent headlines from Chilean and international financial press (titles may be \
in Spanish — read them in Spanish, but write your summary in English):
{titulares}

Write a summary in English, in Markdown format, with exactly these four sections \
(use these exact titles, as level-2 headings):

## Global Overview
3 to 5 bullet points synthesizing the day's most relevant macro themes (equity \
indices, rates, commodities, growth outlook) based on the indicators and headlines \
above. Use measured, non-sensationalist language.

## Financial Highlights
3 to 5 bullet points on notable COMPANY- and STOCK-specific financial news from \
the headlines above — earnings, M&A, guidance changes, dividends, major individual \
stock moves and why. This is distinct from Global Overview: skip broad macro \
themes here and focus on specific companies/tickers. If the headlines don't have \
enough genuinely notable company-level news, it's fine to include fewer than 3 \
points, or note briefly that there wasn't much company-specific news today —  \
never pad this section with macro content or invented details just to fill it.

## Political & Geopolitical Events
Two separate sub-lists (use these as level-3 headings inside this section):

### Chile
1 to 3 bullet points on Chilean political/policy developments from the headlines \
above (government, congress, regulation, elections) — economic policy only, not \
market data (that belongs in the other sections).

### Global
1 to 3 bullet points on international geopolitical developments from the \
headlines above (conflicts, trade tensions, diplomatic disputes, elections \
abroad) that are relevant to markets.

Keep the two sub-lists clearly separate — don't mix Chilean and international \
items together. If either sub-list has no genuinely relevant headlines that day, \
say so briefly instead of inventing or padding.

## Possible Effects for Chile
How the themes above (from any of the previous sections) could connect to \
copper, the exchange rate (USD/CLP), or the local market (IPSA). Always use \
cautious language ("could", "it's possible that", "eventually") — never \
categorical causal claims or guarantees about future price movements."""

# Se agrega al prompt SOLO cuando el residual de la atribución multi-factor
# de hoy (ver market_data.calcular_atribucion_ipsa) tiene |z| > 2 — un
# movimiento del IPSA que copper/S&P 500/USDCLP no explican, y que podría
# tener una causa local específica visible en los titulares del día.
INSTRUCCION_RESIDUAL_INUSUAL = """

IMPORTANT — unusual unexplained local move detected: today's IPSA (ECH) return \
has a residual not explained by copper, the S&P 500, or the USD/CLP exchange \
rate — the three global factors that normally drive most of its daily movement \
— with a z-score of {z:+.2f} against the last {ventana} trading days of \
residuals (|z| > 2 is considered unusual). In the "Possible Effects for Chile" \
section, actively look through the headlines above for a Chile-specific news \
item (company-level news, local political event, regulatory decision, etc.) \
that could plausibly explain this unusual local move, and mention it if you \
find a plausible candidate. If nothing in the headlines explains it, say \
explicitly that the cause is unclear from the available headlines — don't \
speculate or invent a cause."""


def construir_prompt(titulares: list[dict], indicadores: list[dict], instruccion_extra: str = "") -> str:
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

    prompt = PROMPT_TEMPLATE.format(
        indicadores="\n".join(lineas_indicadores) if lineas_indicadores else "(sin datos disponibles)",
        titulares="\n".join(lineas_titulares) if lineas_titulares else "(sin titulares disponibles)",
    )
    return prompt + instruccion_extra


def obtener_titulares_recientes(session) -> list[dict]:
    """Trae los titulares recientes para el prompt, con un cupo parejo por
    fuente (TITULARES_POR_FUENTE) en vez de un solo corte por fecha sobre
    todas juntas — así ninguna fuente de bajo volumen (ej. Yahoo Finance)
    queda invisible para Gemini solo porque otra tiene mucho más volumen
    ese día. Qué titulares terminan efectivamente reflejados en cada
    sección del resumen lo decide Gemini por relevancia al redactar, no
    esta selección — si una fuente no trae nada útil ese día, el prompt
    simplemente le deja usar otra en su lugar."""
    limite = datetime.now() - timedelta(hours=HORAS_VENTANA_TITULARES)

    noticias = []
    for fuente in FUENTES_RSS:
        noticias.extend(
            session.query(Noticia)
            .filter(Noticia.fecha_publicacion >= limite, Noticia.fuente == fuente)
            .order_by(Noticia.fecha_publicacion.desc())
            .limit(TITULARES_POR_FUENTE)
            .all()
        )

    noticias.sort(key=lambda n: n.fecha_publicacion, reverse=True)
    return [{"fuente": n.fuente, "titulo": n.titulo} for n in noticias]


def generar_brief_diario():
    session = get_session()

    try:
        api_key = os.environ["GEMINI_API_KEY"]

        titulares = obtener_titulares_recientes(session)

        engine = get_engine()
        # Sin ORDER BY en el SQL: con estas tablas ya grandes (precios_acciones
        # ronda las 200k filas), Postgres derramaba el sort a disco y esto
        # tardaba mas de un minuto (medido en produccion) -- se ordena en
        # pandas despues de traer los datos, ~20x mas rapido. Mismo fix que
        # app/dashboard.py (cargar_precios_acciones/cargar_series_macro).
        df_macro = pd.read_sql("SELECT nombre, fecha, valor FROM series_macro", engine).sort_values("fecha")
        df_acciones = pd.read_sql(
            "SELECT ticker, fecha, precio_cierre, volumen FROM precios_acciones", engine
        ).sort_values("fecha")
        indicadores = calcular_resumen_mercado(df_macro, df_acciones)

        # Si el residual de HOY de la atribución multi-factor del IPSA (ver
        # market_data.calcular_atribucion_ipsa) es inusual (|z| > 2), se le
        # pide a Gemini que busque una causa local específica en los
        # titulares — un solo intento con try/except: si la atribución falla
        # por lo que sea (historia insuficiente, etc.), el brief se genera
        # igual sin esa instrucción extra, en vez de no generarse.
        instruccion_extra = ""
        try:
            df_atribucion = calcular_atribucion_ipsa(df_acciones, df_macro)
            if not df_atribucion.empty:
                z_residual_hoy = df_atribucion["z_residual"].iloc[-1]
                if pd.notna(z_residual_hoy) and abs(z_residual_hoy) > 2:
                    instruccion_extra = INSTRUCCION_RESIDUAL_INUSUAL.format(
                        z=z_residual_hoy, ventana=VENTANA_ATRIBUCION_IPSA,
                    )
        except Exception as e:
            print(f"No se pudo calcular la atribución del IPSA para el prompt (se sigue sin ella): {e}")

        prompt = construir_prompt(titulares, indicadores, instruccion_extra)

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
