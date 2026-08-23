"""AppTest de integracion: valida que la columna "Atraso" del heatmap de
"Resumen de desempeño" (Acciones IPSA y Dow Jones) muestre el texto
correcto ("Precio congelado — N días hábiles" o "Al día"), y que el
numero de dias coincida con un calculo independiente hecho directo contra
la base de datos (no reutiliza ninguna funcion de app/dashboard.py, para
que la comparacion sea real y no circular).

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

from models import get_session, PrecioAccion

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


def test_columna_atraso_ipsa_falabella_coincide_con_calculo_manual():
    texto_esperado, dias_esperados, atrasado_esperado = _atraso_manual("FALABELLA.SN")
    assert atrasado_esperado, "Esta prueba asume que FALABELLA sigue con el apagon de Yahoo activo"

    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=300).run(timeout=300)
    assert not at.exception, f"La app lanzo una excepcion al correr: {at.exception}"

    df_heatmap = None
    for elem in at.dataframe:
        valor = elem.value
        datos = valor.data if hasattr(valor, "data") else valor
        if isinstance(datos, pd.DataFrame) and "Atraso" in datos.columns and "FALABELLA" in datos.index:
            df_heatmap = datos
            break
    assert df_heatmap is not None, "No se encontro el heatmap de Acciones IPSA con columna 'Atraso' en la app"

    texto_app = df_heatmap.loc["FALABELLA", "Atraso"]
    print(f"FALABELLA -> app: {texto_app!r} | manual (BD directa): {texto_esperado!r}")
    assert texto_app == texto_esperado
    assert f"{dias_esperados} días hábiles" in texto_app


def test_columna_atraso_no_usa_cero_dias_confuso():
    """Un ticker sin atraso debe decir "Al día", nunca "0 días"."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=300).run(timeout=300)
    assert not at.exception, f"La app lanzo una excepcion al correr: {at.exception}"

    for elem in at.dataframe:
        valor = elem.value
        datos = valor.data if hasattr(valor, "data") else valor
        if isinstance(datos, pd.DataFrame) and "Atraso" in datos.columns:
            assert not datos["Atraso"].astype(str).str.contains("0 días").any()


if __name__ == "__main__":
    test_columna_atraso_ipsa_falabella_coincide_con_calculo_manual()
    test_columna_atraso_no_usa_cero_dias_confuso()
    print("OK: ambas pruebas pasaron.")
