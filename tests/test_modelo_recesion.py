"""Test de regresión (sin red, sin BD) para modelo_recesion.py: confirma que
el modelo original se reproduce exactamente igual al recesion.py del usuario
(sensibilidad 32.14% con corte 0.5, verificada a mano antes de construir esta
pestaña) y que la alineación trimestral de las series de FRED con
base_recesion_us.xlsx queda correcta pese al desfase de convención de fecha
(el Excel marca cada trimestre con el 1er día de su ÚLTIMO mes, FRED con
fechas de observación reales cualquier día del trimestre)."""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from modelo_recesion import (
    PREDICTORES_ORIGINAL,
    _agregar_series_fred_trimestral,
    _metricas_matriz_confusion,
    construir_dataset,
    estimar_modelo,
)


def test_metricas_matriz_confusion_calcula_bien():
    y_real = pd.Series([0, 0, 0, 1, 1, 1, 1])
    y_pred = pd.Series([0, 0, 1, 0, 1, 1, 1])  # 1 FP, 1 FN, 3 VP, 2 VN

    metricas = _metricas_matriz_confusion(y_real, y_pred)

    assert metricas["sensibilidad"] == 3 / 4
    assert metricas["especificidad"] == 2 / 3
    assert metricas["precision_global"] == 5 / 7


def test_agregar_series_fred_trimestral_alinea_por_periodo_no_por_fecha_exacta():
    # Observaciones de FRED en fechas cualquiera dentro de cada trimestre
    # (como realmente vienen: UNRATE es mensual, ICSA semanal, etc.) deben
    # promediarse dentro de su trimestre sin importar en qué día caigan.
    df_series_macro = pd.DataFrame([
        {"nombre": "Tasa de desempleo de EEUU (UNRATE)", "fecha": "1990-01-01", "valor": 5.0},
        {"nombre": "Tasa de desempleo de EEUU (UNRATE)", "fecha": "1990-02-01", "valor": 6.0},
        {"nombre": "Tasa de desempleo de EEUU (UNRATE)", "fecha": "1990-03-01", "valor": 7.0},
        {"nombre": "Tasa de desempleo de EEUU (UNRATE)", "fecha": "1990-04-01", "valor": 10.0},
    ])

    agregado = _agregar_series_fred_trimestral(df_series_macro)

    trimestre_q1 = pd.Period("1990Q1", freq="Q")
    assert agregado.loc[trimestre_q1, "unrate"] == 6.0  # promedio de 5, 6, 7
    trimestre_q2 = pd.Period("1990Q2", freq="Q")
    assert agregado.loc[trimestre_q2, "unrate"] == 10.0


def test_modelo_original_reproduce_la_sensibilidad_conocida():
    """Regresión: el modelo original (g_lag, p_lag) debe dar exactamente los
    mismos resultados que el recesion.py original del usuario -- sensibilidad
    32.14%, especificidad 98.25%, precisión global 91.05%, N=257 -- antes de
    agregar las variables de FRED. Si esto cambia, algo rompió la
    reproducción del modelo base."""
    df_series_macro_vacio = pd.DataFrame(columns=["nombre", "fecha", "valor"])
    df = construir_dataset(df_series_macro_vacio)

    modelo = estimar_modelo(df, PREDICTORES_ORIGINAL)

    assert modelo["n_obs"] == 257
    assert abs(modelo["sensibilidad"] - 9 / 28) < 1e-6
    assert abs(modelo["especificidad"] - 225 / 229) < 1e-6
    assert abs(modelo["precision_global"] - 234 / 257) < 1e-6


if __name__ == "__main__":
    test_metricas_matriz_confusion_calcula_bien()
    test_agregar_series_fred_trimestral_alinea_por_periodo_no_por_fecha_exacta()
    test_modelo_original_reproduce_la_sensibilidad_conocida()
    print("OK: las tres pruebas pasaron.")
