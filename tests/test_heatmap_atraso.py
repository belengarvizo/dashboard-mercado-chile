"""AppTest de integracion: valida que la columna "Atraso" del heatmap de
"Resumen de desempeño" (Acciones IPSA y Dow Jones) muestre el texto
correcto ("Precio congelado — N días hábiles" o "Al día"), y que el
numero de dias coincida con un calculo independiente hecho directo contra
la base de datos (no reutiliza ninguna funcion de app/dashboard.py, para
que la comparacion sea real y no circular).

El heatmap ahora se renderiza como una tabla HTML propia (st.markdown),
no un st.dataframe, para poder integrar los tooltips educativos en el
nombre de cada ticker -- este test parsea esa tabla con
tests._html_table_utils.parsear_tabla_heatmap (BeautifulSoup) en vez de
buscarla en at.dataframe o usar pd.read_html directo (que concatena el
texto oculto del tooltip con el del ticker, ver ese módulo).

Corre la app COMPLETA vía streamlit.testing.v1.AppTest porque el pedido
original fue validar lo que la UI realmente renderiza, no solo la funcion
de calculo por separado.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from constants import TICKERS_IPSA
from models import get_session, PrecioAccion
from tests._html_table_utils import parsear_tabla_heatmap

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")


def _atraso_manual(ticker: str) -> tuple[str, int, bool]:
    """Replica manual e independiente del criterio de atraso (misma logica
    que app/dashboard.py: ultimo dia con CAMBIO real de precio, no la
    ultima fila descargada), consultando la BD directamente sin pasar por
    ningun codigo de app/dashboard.py."""
    session = get_session()
    rows = (
        session.query(PrecioAccion.fecha, PrecioAccion.precio_cierre)
        .filter_by(ticker=ticker)
        .order_by(PrecioAccion.fecha)
        .all()
    )
    session.close()
    serie = pd.Series([float(p) for _, p in rows], index=[pd.Timestamp(f) for f, p in rows])
    cambia = serie.ne(serie.shift(1))
    cambia.iloc[0] = True
    ultima_fecha_real = serie.index[cambia][-1]
    hoy = pd.Timestamp.now().normalize()
    dias = int(np.busday_count(ultima_fecha_real.date(), hoy.date()))
    atrasado = dias > 5
    texto = f"Precio congelado — {dias} días hábiles" if atrasado else "Al día"
    return texto, dias, atrasado


def _tablas_heatmap_html():
    """Corre la app y devuelve todas las tablas HTML de heatmap (las que
    tienen tooltips + columna 'Atraso'), ya parseadas a DataFrame."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=300).run(timeout=300)
    assert not at.exception, f"La app lanzo una excepcion al correr: {at.exception}"

    tablas = []
    for elem in at.markdown:
        html = elem.value
        if "glosario-tooltip" in html and ">Atraso<" in html:
            tablas.append(parsear_tabla_heatmap(html))
    assert tablas, "No se encontro ningun heatmap con tooltips y columna 'Atraso' en la app"
    return tablas


def test_columna_atraso_ipsa_coincide_con_calculo_manual_para_todos_los_tickers():
    """Antes esta prueba asumía que FALABELLA específicamente estaba
    atrasada (cierto mientras duró el apagón de Yahoo Finance documentado
    en esta conversación). Esa suposición dejó de ser cierta apenas se
    resolvió el apagón — lo cual es exactamente el comportamiento
    correcto, no una falla — así que en vez de fijar un ticker
    específico, se compara CADA una de las 30 acciones del IPSA contra el
    cálculo manual: la prueba es válida sin importar cuántas (o ninguna)
    estén atrasadas en el momento de correrla."""
    df_heatmap = None
    for df in _tablas_heatmap_html():
        if all(t.replace(".SN", "") in df.index for t in TICKERS_IPSA):
            df_heatmap = df
            break
    assert df_heatmap is not None, "No se encontro el heatmap de Acciones IPSA (con las 30 acciones) en la app"

    n_atrasados = 0
    for ticker_sn in TICKERS_IPSA:
        ticker = ticker_sn.replace(".SN", "")
        texto_esperado, dias_esperados, atrasado_esperado = _atraso_manual(ticker_sn)
        texto_app = df_heatmap.loc[ticker, "Atraso"]
        assert texto_app == texto_esperado, f"{ticker}: app={texto_app!r} vs manual={texto_esperado!r}"
        if atrasado_esperado:
            n_atrasados += 1
            assert f"{dias_esperados} días hábiles" in texto_app

    print(f"Las 30 acciones del IPSA coinciden con el cálculo manual ({n_atrasados} atrasadas ahora mismo).")


def test_columna_atraso_no_usa_cero_dias_confuso():
    """Un ticker sin atraso debe decir "Al día", nunca "0 días".

    El patrón usa un negative lookbehind (?<!\\d) para exigir que el "0"
    sea un dígito solo, no parte de otro número -- sin esto, contains()
    hace match por substring y "3**0** días hábiles" (un atraso real de
    30 días, texto correcto) dispara un falso positivo. Confirmado en
    producción: con el apagón de datos de Yahoo Finance para el IPSA
    documentado en esta sesión, varios tickers llegaron a mostrar
    "30 días hábiles" (dato real y correcto), lo que rompía esta prueba
    con el patrón anterior sin que hubiera ningún "0 días" real."""
    for df in _tablas_heatmap_html():
        assert not df["Atraso"].astype(str).str.contains(r"(?<!\d)0 días", regex=True).any()


if __name__ == "__main__":
    test_columna_atraso_ipsa_coincide_con_calculo_manual_para_todos_los_tickers()
    test_columna_atraso_no_usa_cero_dias_confuso()
    print("OK: ambas pruebas pasaron.")
