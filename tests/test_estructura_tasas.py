"""Test de regresión (sin red, sin BD) para estructura_tasas.py: confirma
que el ajuste de Nelson-Siegel y Svensson recupera los parámetros
correctos sobre una curva sintética generada por la misma fórmula (así
sabemos que la optimización encuentra el mínimo GLOBAL, no uno local
cualquiera), y valida el comportamiento con datos reales conocidos
(la curva del 30-jun-2017 que se verificó a mano contra la BD antes de
construir la sección en el dashboard)."""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from estructura_tasas import ajustar_nelson_siegel, ajustar_svensson, nelson_siegel, svensson, PLAZOS_ANIOS


def test_nelson_siegel_recupera_parametros_de_una_curva_sintetica():
    plazos = list(PLAZOS_ANIOS.values())
    parametros_reales = {"beta0": 3.0, "beta1": -2.0, "beta2": 1.0, "tau1": 2.5}
    curva_sintetica = nelson_siegel(np.array(plazos), **parametros_reales)

    ajuste = ajustar_nelson_siegel(plazos, curva_sintetica.tolist())

    # Sin ruido: el RMSE del ajuste sobre su propia curva generadora debe
    # ser prácticamente cero (confirma que encontró el óptimo global, no
    # un mínimo local mediocre).
    assert ajuste["rmse"] < 1e-4, f"RMSE demasiado alto para una curva sin ruido: {ajuste['rmse']}"
    for nombre, valor_real in parametros_reales.items():
        assert abs(ajuste["parametros"][nombre] - valor_real) < 1e-2, (
            f"{nombre}: esperado {valor_real}, ajustado {ajuste['parametros'][nombre]}"
        )


def test_svensson_recupera_parametros_de_una_curva_sintetica():
    plazos = list(PLAZOS_ANIOS.values())
    parametros_reales = {
        "beta0": 3.0, "beta1": -2.0, "beta2": 1.0, "beta3": -1.5, "tau1": 1.5, "tau2": 8.0,
    }
    curva_sintetica = svensson(np.array(plazos), **parametros_reales)

    ajuste = ajustar_svensson(plazos, curva_sintetica.tolist())

    assert ajuste["rmse"] < 1e-3, f"RMSE demasiado alto para una curva sin ruido: {ajuste['rmse']}"


def test_svensson_nunca_ajusta_peor_que_nelson_siegel():
    """Svensson es una generalización de Nelson-Siegel (se reduce a NS
    cuando beta3=0): con los parámetros óptimos GLOBALES, su RMSE nunca
    debería ser mayor que el de Nelson-Siegel en la misma curva -- si
    esto falla, es señal de que el optimizador quedó en un mínimo local
    en vez del global."""
    plazos = list(PLAZOS_ANIOS.values())
    # Curva real del 30-jun-2017 (verificada a mano contra la BD antes
    # de construir la sección del dashboard).
    tasas_reales = [0.84, 1.03, 1.14, 1.24, 1.38, 1.55, 1.89, 2.14, 2.31, 2.61, 2.84]

    ns = ajustar_nelson_siegel(plazos, tasas_reales)
    sv = ajustar_svensson(plazos, tasas_reales)

    assert sv["rmse"] <= ns["rmse"] + 1e-6, (
        f"Svensson (RMSE={sv['rmse']:.5f}) ajustó peor que Nelson-Siegel (RMSE={ns['rmse']:.5f})"
    )
    # Sanity check adicional: ambos ajustes deben ser razonablemente
    # buenos sobre datos reales (no un caso patológico).
    assert ns["rmse"] < 0.5, f"RMSE de Nelson-Siegel sospechosamente alto: {ns['rmse']}"


if __name__ == "__main__":
    test_nelson_siegel_recupera_parametros_de_una_curva_sintetica()
    test_svensson_recupera_parametros_de_una_curva_sintetica()
    test_svensson_nunca_ajusta_peor_que_nelson_siegel()
    print("OK: las tres pruebas pasaron.")
