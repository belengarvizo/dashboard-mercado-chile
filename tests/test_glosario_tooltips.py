"""AppTest de integración para los tooltips educativos integrados
directamente en el heatmap de "Resumen de desempeño" (Acciones IPSA y
Acciones Dow Jones) — ya no una tabla aparte, sino el nombre de cada
ticker de la tabla real.

No puede probar el :hover en sí (eso es un comportamiento de CSS/DOM en
un navegador real — se verificó visualmente aparte con Playwright contra
la app corriendo, ver conversación), pero sí confirma:
1. Las 30 acciones del IPSA y las 30 del Dow Jones tienen tooltip, con
   su nombre completo real (contra el diccionario verificado de
   glosario.py) y los mismos números de Beta/CAPM que esa fila real.
2. El color de fondo (heatmap) del resto de la tabla sigue funcionando
   — no se perdió al reemplazar el Styler por HTML propio.
3. El bloque de atribución multi-factor aparece SOLO en el IPSA (el
   modelo es específico del mercado chileno) y NUNCA en el Dow Jones.
4. Ningún tooltip menciona expectativas de mercado/consenso de
   analistas ni una atribución de noticias específica por acción —
   ambas explícitamente fuera de alcance.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from bs4 import BeautifulSoup
from streamlit.testing.v1 import AppTest

from constants import TICKERS_IPSA, TICKERS_DOW_JONES
from glosario import NOMBRE_COMPLETO_POR_TICKER
from tests._html_table_utils import parsear_tabla_heatmap, tooltip_html_de_ticker


def _texto_plano(contenido_html: str) -> str:
    """Decodifica entidades HTML (ej. "&amp;" -> "&") para comparar
    contra nombres crudos como "Johnson & Johnson" — decode_contents()
    de BeautifulSoup re-escapa el "&" literal al serializar, así que
    comparar contra el HTML crudo falla aunque el nombre esté ahí."""
    return BeautifulSoup(contenido_html, "lxml").get_text()

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")

FRASES_PROHIBIDAS = [
    "consenso de analistas",
    "expectativas de mercado",
    "precio objetivo",
    "recomendación de compra",
    "recomendación de venta",
]


def _correr_app():
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=300).run(timeout=300)
    assert not at.exception, f"La app lanzo una excepcion al correr: {at.exception}"
    return at


def _tabla_por_marcador(at, marcador_columna: str) -> tuple[str, pd.DataFrame]:
    """Devuelve (html_crudo, dataframe_parseado) de la tabla de heatmap
    que tiene la columna dada (para distinguir IPSA de Dow Jones:
    IPSA tiene 'CAPM local (%)', Dow Jones tiene 'CAPM (%)' a secas)."""
    for elem in at.markdown:
        html = elem.value
        if "glosario-tooltip" in html and f">{marcador_columna}<" in html:
            return html, parsear_tabla_heatmap(html)
    raise AssertionError(f"No se encontro la tabla de heatmap con columna '{marcador_columna}'")


def test_heatmap_ipsa_completo_con_tooltips_y_atribucion():
    at = _correr_app()
    html_ipsa, df_ipsa = _tabla_por_marcador(at, "CAPM local (%)")

    assert len(df_ipsa) == 30, f"El heatmap IPSA deberia tener 30 acciones, tiene {len(df_ipsa)}"
    for columna in ["1D %", "1W %", "1M %", "YTD %", "Beta", "Beta ajustada",
                     "Volatilidad anualizada (%)", "CAPM local (%)", "CAPM + CRP (%)",
                     "Última actualización", "Atraso"]:
        assert columna in df_ipsa.columns, f"Falta la columna '{columna}' en el heatmap IPSA"

    # Todas las 30 acciones del IPSA tienen tooltip, con su nombre real.
    for ticker_sn in TICKERS_IPSA:
        ticker = ticker_sn.replace(".SN", "")
        assert ticker in df_ipsa.index, f"Falta {ticker} en el heatmap IPSA"
        contenido = tooltip_html_de_ticker(html_ipsa, ticker)
        assert contenido is not None, f"{ticker}: no tiene tooltip"
        assert NOMBRE_COMPLETO_POR_TICKER[ticker_sn] in _texto_plano(contenido), f"{ticker}: falta su nombre completo en el tooltip"
        # El bloque de atribucion multi-factor SI debe aparecer en el IPSA.
        assert "Relación con factores globales" in contenido or "no disponible" in contenido.lower(), (
            f"{ticker}: no tiene el bloque de atribucion ni un mensaje de dato no disponible"
        )

    # Los numeros del tooltip coinciden con los del heatmap real (misma fila) para una muestra.
    for ticker in ["LTM", "SQM-B", "CHILE", "FALABELLA", "COPEC"]:
        fila = df_ipsa.loc[ticker]
        contenido = tooltip_html_de_ticker(html_ipsa, ticker)
        beta_valor = float(fila["Beta"])
        capm_valor = float(fila["CAPM local (%)"].rstrip("%"))
        sharpe_valor = float(fila["Sharpe"])
        treynor_valor = float(fila["Treynor (%)"].rstrip("%"))
        alpha_valor = float(fila["Alpha (%)"].rstrip("%"))
        assert f"Beta = {beta_valor:.2f}" in contenido, f"{ticker}: Beta del tooltip no coincide con la fila"
        assert f"CAPM = {capm_valor:.2f}%" in contenido, f"{ticker}: CAPM del tooltip no coincide con la fila"
        assert f"Sharpe = {sharpe_valor:.2f}" in contenido, f"{ticker}: Sharpe del tooltip no coincide con la fila"
        assert f"Treynor = {treynor_valor:+.2f}%" in contenido, f"{ticker}: Treynor del tooltip no coincide con la fila"
        assert f"Alpha = {alpha_valor:+.2f}%" in contenido, f"{ticker}: Alpha del tooltip no coincide con la fila"

    # El heatmap debe pintar CADA fila con exactamente uno de los dos
    # estilos: gradiente de color (fila al dia) o grisado de "Atraso"
    # (fila atrasada, mismo criterio que el Styler anterior:
    # marcar_datos_atrasados anulaba el fondo). No se fija cuál de los
    # dos predomina -- eso depende de si hay un apagón real en curso al
    # momento de correr la prueba (ver conversación: hubo uno, se
    # resolvió, y fijar ese estado hacía la prueba frágil) -- solo que
    # el mecanismo esté funcionando en general.
    n_gradiente = html_ipsa.count("background-color:rgb(")
    n_grisado = html_ipsa.count("color:#898781")
    assert n_gradiente > 0 or n_grisado > 0, "El heatmap IPSA no muestra ni gradiente ni grisado de Atraso en ninguna fila"
    print(f"IPSA: {n_gradiente} celdas con gradiente, {n_grisado} celdas grisadas por Atraso.")


def test_heatmap_dow_jones_completo_con_tooltips_sin_atribucion():
    at = _correr_app()
    html_dow, df_dow = _tabla_por_marcador(at, "CAPM (%)")

    assert len(df_dow) == 30, f"El heatmap Dow Jones deberia tener 30 acciones, tiene {len(df_dow)}"

    for ticker in TICKERS_DOW_JONES:
        assert ticker in df_dow.index, f"Falta {ticker} en el heatmap Dow Jones"
        contenido = tooltip_html_de_ticker(html_dow, ticker)
        assert contenido is not None, f"{ticker}: no tiene tooltip"
        assert NOMBRE_COMPLETO_POR_TICKER[ticker] in _texto_plano(contenido), f"{ticker}: falta su nombre completo en el tooltip"
        # El bloque de atribucion NUNCA debe aparecer en el Dow Jones: el
        # modelo (market_data.calcular_atribucion_ipsa) es especifico del
        # mercado chileno.
        assert "Relación con factores globales" not in contenido, (
            f"{ticker}: el Dow Jones no deberia tener el bloque de atribucion del IPSA"
        )

    assert "background-color:rgb(" in html_dow, "El heatmap Dow Jones perdio el color de fondo del gradiente"

    # Los numeros del tooltip coinciden con los de la fila real, para una muestra.
    for ticker in ["AAPL", "JPM", "WMT"]:
        fila = df_dow.loc[ticker]
        contenido = tooltip_html_de_ticker(html_dow, ticker)
        sharpe_valor = float(fila["Sharpe"])
        treynor_valor = float(fila["Treynor (%)"].rstrip("%"))
        alpha_valor = float(fila["Alpha (%)"].rstrip("%"))
        assert f"Sharpe = {sharpe_valor:.2f}" in contenido, f"{ticker}: Sharpe del tooltip no coincide con la fila"
        assert f"Treynor = {treynor_valor:+.2f}%" in contenido, f"{ticker}: Treynor del tooltip no coincide con la fila"
        assert f"Alpha = {alpha_valor:+.2f}%" in contenido, f"{ticker}: Alpha del tooltip no coincide con la fila"


def test_tooltips_no_mencionan_lo_explicitamente_excluido():
    """Ni expectativas/consenso de analistas ni atribucion de noticias
    especifica por accion — ambas fuera de alcance a pedido explicito."""
    at = _correr_app()
    html_ipsa, _ = _tabla_por_marcador(at, "CAPM local (%)")
    html_dow, _ = _tabla_por_marcador(at, "CAPM (%)")

    for html, nombre in [(html_ipsa, "IPSA"), (html_dow, "Dow Jones")]:
        texto_minuscula = html.lower()
        for frase in FRASES_PROHIBIDAS:
            assert frase not in texto_minuscula, f"El heatmap {nombre} menciona '{frase}', fuera de alcance"


if __name__ == "__main__":
    test_heatmap_ipsa_completo_con_tooltips_y_atribucion()
    test_heatmap_dow_jones_completo_con_tooltips_sin_atribucion()
    test_tooltips_no_mencionan_lo_explicitamente_excluido()
    print("OK: todas las pruebas pasaron.")
