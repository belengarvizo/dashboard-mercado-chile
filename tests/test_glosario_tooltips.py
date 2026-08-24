"""AppTest de integración para la prueba de concepto de tooltips
educativos (glosario.py) en el heatmap de "Acciones IPSA".

No puede probar el :hover en sí (eso es un comportamiento de CSS/DOM en
un navegador real — se verificó visualmente aparte con Playwright contra
la app corriendo, ver conversación), pero sí confirma:
1. La app corre sin excepciones con el bloque de tooltips agregado.
2. El heatmap original (30 acciones, columnas Beta/CAPM/Atraso/etc.) sigue
   intacto — el requisito explícito de "no romper nada del resto de la
   tabla".
3. El HTML de tooltips contiene los 5 tickers de la prueba de concepto
   (incluido LTM), sus nombres completos, y los mismos números de
   Beta/CAPM que ya muestra el heatmap real — no un número inventado o
   desalineado de la fila.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from streamlit.testing.v1 import AppTest

from glosario import NOMBRE_COMPLETO_POR_TICKER

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
TICKERS_POC = ["LTM", "SQM-B", "CHILE", "FALABELLA", "COPEC"]


def test_heatmap_ipsa_sigue_intacto_y_tooltips_muestran_numeros_reales():
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=300).run(timeout=300)
    assert not at.exception, f"La app lanzo una excepcion al correr: {at.exception}"

    # --- 1. El heatmap original de "Acciones IPSA" sigue intacto ---
    df_heatmap = None
    for elem in at.dataframe:
        valor = elem.value
        datos = valor.data if hasattr(valor, "data") else valor
        if isinstance(datos, pd.DataFrame) and "Atraso" in datos.columns and "Beta" in datos.columns:
            df_heatmap = datos
            break
    assert df_heatmap is not None, "No se encontro el heatmap de Acciones IPSA"
    assert len(df_heatmap) == 30, f"El heatmap deberia seguir teniendo las 30 acciones del IPSA, tiene {len(df_heatmap)}"
    for columna in ["1D %", "1W %", "1M %", "YTD %", "Beta", "Beta ajustada",
                     "CAPM local (%)", "CAPM + CRP (%)", "Última actualización", "Atraso"]:
        assert columna in df_heatmap.columns, f"Falta la columna '{columna}' del heatmap original"
    for ticker in TICKERS_POC:
        assert ticker in df_heatmap.index, f"Falta {ticker} en el heatmap"

    # --- 2. El bloque HTML de tooltips existe y tiene los 5 tickers ---
    html_tooltips = None
    for elem in at.markdown:
        if "glosario-tooltip" in elem.value:
            html_tooltips = elem.value
            break
    assert html_tooltips is not None, "No se encontro el bloque HTML de tooltips (clase glosario-tooltip)"

    for ticker in TICKERS_POC:
        assert f">{ticker}<" in html_tooltips, f"El ticker {ticker} no aparece en el HTML de tooltips"
    for ticker_sn, nombre in NOMBRE_COMPLETO_POR_TICKER.items():
        assert nombre in html_tooltips, f"Falta el nombre completo de {ticker_sn} ({nombre}) en el tooltip"

    # --- 3. Los numeros del tooltip coinciden con los del heatmap real (misma fila) ---
    for ticker in TICKERS_POC:
        fila = df_heatmap.loc[ticker]
        beta_esperada = f"Beta = {fila['Beta']:.2f}"
        capm_esperado = f"CAPM = {fila['CAPM local (%)']:.2f}%"
        assert beta_esperada in html_tooltips, f"{ticker}: no se encontro '{beta_esperada}' en el tooltip"
        assert capm_esperado in html_tooltips, f"{ticker}: no se encontro '{capm_esperado}' en el tooltip"

    print("Heatmap intacto (30 tickers, todas las columnas) y 5 tooltips con numeros reales confirmados.")


if __name__ == "__main__":
    test_heatmap_ipsa_sigue_intacto_y_tooltips_muestran_numeros_reales()
    print("OK: la prueba paso.")
