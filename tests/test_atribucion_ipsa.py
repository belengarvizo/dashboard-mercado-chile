"""AppTest de integración para la pestaña "Atribución IPSA": corre la app
completa con datos reales y confirma que los números que renderiza la UI
(retorno real, retorno predicho, residual, R²/correlación out-of-sample)
coinciden con un cálculo hecho por separado, directo contra market_data.py
(sin pasar por app/dashboard.py), para que la comparación no sea circular.

También confirma, contra datos reales de la base, que ECH (el proxy del
IPSA que no es un ticker `.SN`) no está afectado por el apagón de Yahoo
Finance para el mercado chileno documentado en sesiones anteriores.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from streamlit.testing.v1 import AppTest

from market_data import calcular_atribucion_ipsa, validar_atribucion_out_of_sample
from models import get_engine

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")


def _cargar_datos_reales():
    engine = get_engine()
    df_acciones = pd.read_sql(
        "SELECT ticker, fecha, precio_cierre, volumen FROM precios_acciones ORDER BY fecha", engine,
    )
    df_macro = pd.read_sql("SELECT nombre, fecha, valor FROM series_macro ORDER BY fecha", engine)
    return df_acciones, df_macro


def test_ech_no_esta_afectado_por_el_apagon_de_yahoo():
    """Confirma con datos reales (no una suposición) que ECH sigue
    recibiendo precio Y volumen frescos y distintos cada rueda -- a
    diferencia de los tickers .SN, que llevan semanas con precio/volumen
    congelados (ver diagnóstico previo, AGUAS-A.SN, FALABELLA.SN, etc.)."""
    df_acciones, _ = _cargar_datos_reales()
    ech = df_acciones[df_acciones["ticker"] == "ECH"].sort_values("fecha").tail(10)
    assert len(ech) >= 10, "No hay suficiente historia reciente de ECH para verificar"

    precios_distintos = ech["precio_cierre"].nunique()
    volumenes_distintos = ech["volumen"].nunique()
    volumen_nunca_cero = (ech["volumen"] > 0).all()

    print(f"ECH ultimas 10 ruedas: {precios_distintos} precios distintos, {volumenes_distintos} volumenes distintos")
    assert precios_distintos >= 8, "El precio de ECH deberia cambiar casi todos los dias, como cualquier ETF liquido"
    assert volumenes_distintos >= 8, "El volumen de ECH deberia ser distinto cada dia (evidencia de trading real)"
    assert volumen_nunca_cero, "ECH nunca deberia tener volumen 0 (eso indicaria un corte de datos)"


def test_atribucion_ipsa_en_la_app_coincide_con_calculo_independiente():
    df_acciones, df_macro = _cargar_datos_reales()
    df_atrib_esperado = calcular_atribucion_ipsa(df_acciones, df_macro)
    assert len(df_atrib_esperado) > 0, "El modelo de atribucion no produjo ninguna fila con datos reales"

    fila_esperada = df_atrib_esperado.iloc[-1]
    validacion_esperada = validar_atribucion_out_of_sample(df_acciones, df_macro)
    assert validacion_esperada["suficientes_datos"]

    # La suma de los componentes debe coincidir EXACTAMENTE con el retorno
    # real (requisito explícito del feature) -- no solo "aproximadamente".
    suma_componentes = (
        fila_esperada["alfa"] + fila_esperada["contrib_cobre"] + fila_esperada["contrib_sp500"]
        + fila_esperada["contrib_usdclp"] + fila_esperada["residual"]
    )
    assert abs(suma_componentes - fila_esperada["retorno_ech"]) < 1e-9

    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=300).run(timeout=300)
    assert not at.exception, f"La app lanzo una excepcion al correr: {at.exception}"

    metricas = {m.label: m.value for m in at.metric}
    print("Metricas renderizadas en la pestaña Atribución IPSA:", {
        k: v for k, v in metricas.items()
        if k in ("Retorno real de ECH", "Retorno predicho (3 factores)", "Residual",
                  "R² (out-of-sample)", "Correlación predicho vs. real")
    })

    assert "Retorno real de ECH" in metricas
    assert metricas["Retorno real de ECH"] == f"{fila_esperada['retorno_ech']:+.2%}"
    assert metricas["Retorno predicho (3 factores)"] == f"{fila_esperada['retorno_predicho']:+.2%}"
    assert metricas["Residual"] == f"{fila_esperada['residual']:+.2%}"

    assert metricas["R² (out-of-sample)"] == f"{validacion_esperada['r2_oos']:.3f}"
    assert metricas["Correlación predicho vs. real"] == f"{validacion_esperada['correlacion_oos']:.3f}"
    assert metricas["Días in-sample"] == f"{validacion_esperada['n_in_sample']:,}"
    assert metricas["Días out-of-sample"] == f"{validacion_esperada['n_out_of_sample']:,}"

    # El grafico de barras apiladas y el de historial del residual deben
    # existir (st.plotly_chart) dentro de la pestaña.
    assert len(at.get("plotly_chart")) >= 2


if __name__ == "__main__":
    test_ech_no_esta_afectado_por_el_apagon_de_yahoo()
    test_atribucion_ipsa_en_la_app_coincide_con_calculo_independiente()
    print("OK: todas las pruebas pasaron.")
