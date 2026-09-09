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
import time
from datetime import date, datetime, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from google import genai
from models import get_session, get_engine, Noticia, BriefDiario, ErrorActualizacion
from market_data import calcular_resumen_mercado, calcular_atribucion_ipsa, VENTANA_ATRIBUCION_IPSA
from retry_utils import ESPERAS_REINTENTO_SEGUNDOS
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

# Prompt de la traducción bilingüe + glosario dinámico para el PDF (paso NO
# crítico, ver generar_traduccion_y_glosario). Toma el brief en inglés YA
# generado y devuelve el mismo Markdown con la traducción al español pegada
# en la misma línea tras el token <<<ES>>>, más una sección "## Glossary" al
# final con solo los términos técnicos que aparecieron ese día.
PROMPT_TRADUCCION_TEMPLATE = """You are turning a finished English financial brief \
into a bilingual English-Spanish document, in the exact style of a Bloomberg \
class study guide.

Here is today's brief (Markdown):

---
{contenido}
---

Produce a NEW Markdown document following these rules EXACTLY:

1. Keep the SAME structure and the SAME Markdown markers as the original: `## ` \
for sections, `### ` for subsections, `- ` for bullets, blank lines between \
blocks. Keep the sections in the same order. Do NOT add, remove, merge, split \
or reorder any bullet or paragraph — one English item maps to exactly one \
output line.

2. For every heading, bullet and paragraph, keep the original English text and \
append its Spanish translation ON THE SAME LINE, separated by the literal token \
`<<<ES>>>` (three '<', the letters ES, three '>'). Examples:
`## Global Overview <<<ES>>> Panorama Global`
`- The IMF projects Chile's GDP to grow 1.9% in 2026, weighed down by a \
slowdown in mining investment. <<<ES>>> El FMI proyecta que el PIB de Chile \
(Producto Interno Bruto) crecerá 1,9% en 2026, presionado a la baja por una \
desaceleración en la inversión minera (mining investment).`

3. In the Spanish text, keep technical / financial / Bloomberg terms in English \
and put their Spanish rendering in parentheses right after, e.g. "spread \
(diferencial)", "guidance (proyección de resultados)", "earnings (resultados \
corporativos)". Use Chilean Spanish conventions: comma as decimal separator \
(1,9%), and keep tickers, proper nouns and figures unchanged.

4. After translating everything, add ONE final section, exactly:
`## Glossary <<<ES>>> Glosario`
Then one bullet per term, listing ONLY the financial / economic / Bloomberg \
terms that ACTUALLY appear in today's brief above (a dynamic glossary, not a \
fixed list). Each line in this EXACT format — three parts separated by ` — ` \
(space, em dash U+2014, space):
`- **Term (full English form)** — término en español — short definition in \
Spanish, max 20 words.`
Example:
`- **GDP (Gross Domestic Product)** — PIB — Valor total de bienes y servicios \
producidos en un país durante un período.`
Do NOT use Markdown table syntax (no `|`). Typically 5 to 15 terms.

Output ONLY the Markdown document, nothing before or after it."""


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


class BriefBloqueadoError(RuntimeError):
    """Gemini devolvió una respuesta sin texto utilizable (safety filter,
    recitation, etc.). Reintentar el mismo prompt no sirve."""


def _clasificar_error_gemini(exc: Exception) -> str:
    """Clasifica un fallo de la llamada a Gemini en una categoría accionable:
    "cuota" | "transitorio" | "bloqueo" | "otro". Ver ErrorActualizacion."""
    if isinstance(exc, BriefBloqueadoError):
        return "bloqueo"

    codigo = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    texto = str(exc).lower()

    if codigo == 429 or any(k in texto for k in ("resource_exhausted", "quota", "rate limit", "too many requests")):
        return "cuota"
    if codigo in (500, 502, 503, 504) or any(
        k in texto for k in ("timeout", "timed out", "deadline", "unavailable", "503", "502", "504", "internal error")
    ):
        return "transitorio"
    if any(k in texto for k in ("safety", "blocked", "block_reason", "recitation", "prohibited")):
        return "bloqueo"
    return "otro"


def _registrar_error_actualizacion(fuente: str, categoria: str, tipo: str, mensaje: str) -> None:
    """Best-effort: deja el detalle del error en la tabla errores_actualizacion
    para poder diagnosticar sin el log de Railway. Usa su propia sesión (la
    del paso puede estar en rollback) y NUNCA propaga: si esto falla, no debe
    tapar el error real."""
    try:
        s = get_session()
        try:
            s.add(ErrorActualizacion(
                fuente=fuente,
                ocurrido_en=datetime.now(),
                categoria=categoria,
                tipo_excepcion=tipo,
                mensaje=(mensaje or "")[:4000],
            ))
            s.commit()
        finally:
            s.close()
        print(f"  [errores_actualizacion] {fuente}: {categoria} / {tipo}")
    except Exception as e:
        print(f"  (no se pudo registrar el error en errores_actualizacion: {e})")


def _texto_de_respuesta_gemini(respuesta) -> str:
    """Extrae el texto de la respuesta de Gemini; si viene vacía o bloqueada,
    lanza BriefBloqueadoError con el motivo (no se reintenta el mismo prompt)."""
    texto = getattr(respuesta, "text", None)
    if texto and texto.strip():
        return texto

    motivo = "respuesta sin texto"
    try:
        candidatos = getattr(respuesta, "candidates", None) or []
        if candidatos:
            fr = getattr(candidatos[0], "finish_reason", None)
            motivo = f"finish_reason={getattr(fr, 'name', fr)}"
        feedback = getattr(respuesta, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            motivo = f"block_reason={getattr(feedback.block_reason, 'name', feedback.block_reason)}"
    except Exception:
        pass
    raise BriefBloqueadoError(f"Gemini no devolvió texto ({motivo})")


def _generar_contenido_brief(cliente, prompt: str) -> str:
    """Llama a Gemini. Reintenta con backoff SOLO los fallos transitorios
    (timeout / 5xx); cuota agotada y respuestas bloqueadas se relanzan de
    inmediato porque reintentar no sirve."""
    ultimo_error = None
    for intento in range(len(ESPERAS_REINTENTO_SEGUNDOS) + 1):
        try:
            respuesta = cliente.models.generate_content(model=MODELO_GEMINI, contents=prompt)
            return _texto_de_respuesta_gemini(respuesta)
        except BriefBloqueadoError:
            raise  # el prompt no va a pasar por reintentar
        except Exception as e:
            if _clasificar_error_gemini(e) != "transitorio" or intento == len(ESPERAS_REINTENTO_SEGUNDOS):
                raise
            ultimo_error = e
            espera = ESPERAS_REINTENTO_SEGUNDOS[intento]
            print(f"  Gemini falló transitoriamente ({type(e).__name__}: {e}) — "
                  f"reintento {intento + 1}/{len(ESPERAS_REINTENTO_SEGUNDOS)} en {espera}s...")
            time.sleep(espera)
    raise ultimo_error  # inalcanzable (el loop retorna o relanza), solo para el linter


def generar_traduccion_y_glosario(cliente, contenido_en: str) -> str:
    """Devuelve el brief en inglés YA generado, con la traducción al español
    intercalada línea por línea (token <<<ES>>>) y una sección "## Glossary"
    dinámica al final. Reutiliza _generar_contenido_brief (mismo retry y misma
    clasificación de errores que el brief). Paso NO crítico: quien lo llama
    debe atrapar la excepción y seguir -- el PDF sabe caer al inglés solo."""
    prompt = PROMPT_TRADUCCION_TEMPLATE.format(contenido=contenido_en)
    return _generar_contenido_brief(cliente, prompt)


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
        try:
            contenido = _generar_contenido_brief(cliente, prompt)
        except Exception as e:
            categoria = _clasificar_error_gemini(e)
            if categoria == "cuota":
                print("Brief NO generado hoy: cuota de Gemini agotada "
                      f"({type(e).__name__}: {e}). No se reintenta hoy; brief_diario "
                      "queda sin fila para hoy.")
            elif categoria == "bloqueo":
                print("Brief NO generado hoy: Gemini bloqueó la respuesta "
                      f"({type(e).__name__}: {e}). No se reintenta el mismo prompt.")
            elif categoria == "transitorio":
                print("Brief NO generado hoy: Gemini falló de forma transitoria y "
                      f"agotó los reintentos ({type(e).__name__}: {e}).")
            raise

        hoy = date.today()
        existente = session.query(BriefDiario).filter_by(fecha=hoy).first()
        if existente:
            existente.contenido = contenido
            existente.generado_en = datetime.now()
        else:
            session.add(BriefDiario(fecha=hoy, contenido=contenido, generado_en=datetime.now()))

        session.commit()
        print("Brief diario generado y guardado.")

        # --- Traducción bilingüe + glosario (paso NO crítico) ---
        # El brief en inglés ya está commiteado arriba. Si la traducción falla
        # (cuota de Gemini, error transitorio agotado, respuesta bloqueada),
        # se registra en errores_actualizacion y se sigue: contenido_bilingue
        # queda NULL y el PDF sale solo en inglés desde `contenido`. Nunca
        # re-lanza -- un fallo acá no debe tumbar el paso "brief".
        try:
            print("Generando traducción bilingüe + glosario...")
            contenido_bilingue = generar_traduccion_y_glosario(cliente, contenido)
            fila = session.query(BriefDiario).filter_by(fecha=hoy).first()
            if fila is not None:
                fila.contenido_bilingue = contenido_bilingue
                session.commit()
                print("Traducción bilingüe + glosario guardados.")
        except Exception as e:
            session.rollback()
            categoria = _clasificar_error_gemini(e)
            _registrar_error_actualizacion(
                "brief_traduccion", categoria, type(e).__name__, str(e)
            )
            print(f"Traducción bilingüe NO generada hoy ({categoria}: "
                  f"{type(e).__name__}: {e}). El brief en inglés queda igual; "
                  "el PDF saldrá solo en inglés.")

    except Exception as e:
        session.rollback()
        # Deja el detalle en la BD para diagnosticar sin el log de Railway.
        _registrar_error_actualizacion("brief", _clasificar_error_gemini(e), type(e).__name__, str(e))
        print(f"Error generando el brief diario: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    generar_brief_diario()
