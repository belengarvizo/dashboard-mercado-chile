"""
Ajuste de modelos de estructura temporal de tasas de interés — Nelson-Siegel
(1987) y Svensson (1994) — sobre la curva de Treasury Constant Maturity del
H.15 de la Reserva Federal (vía FRED, ver scripts/actualizar_bcch.py).

Construido para "Laboratorio Financiero" (Pregunta 2: Modelos de Estructura
de Tasas), siguiendo las mismas fórmulas del material del curso
(diapositivas 82-83 de Finanzas I — ENFIN415).
"""

import numpy as np
from scipy.optimize import minimize

# Plazos en años para cada nombre de serie tal como se guarda en series_macro.
PLAZOS_ANIOS: dict[str, float] = {
    "1 mes": 1 / 12,
    "3 meses": 3 / 12,
    "6 meses": 6 / 12,
    "1 año": 1.0,
    "2 años": 2.0,
    "3 años": 3.0,
    "5 años": 5.0,
    "7 años": 7.0,
    "10 años": 10.0,
    "20 años": 20.0,
    "30 años": 30.0,
}


def nelson_siegel(t, beta0: float, beta1: float, beta2: float, tau1: float):
    """R(t) = β0 + β1·[(1-e^(-t/τ1))/(t/τ1)] + β2·[(1-e^(-t/τ1))/(t/τ1) - e^(-t/τ1)]

    β0 = nivel de largo plazo, β1 = pendiente (corto - largo), β2 = curvatura
    (ver diapositiva 82: "Chilean Term structure of Interest Rates")."""
    t = np.asarray(t, dtype=float)
    x = t / tau1
    factor = (1 - np.exp(-x)) / x
    return beta0 + beta1 * factor + beta2 * (factor - np.exp(-x))


def svensson(t, beta0: float, beta1: float, beta2: float, beta3: float, tau1: float, tau2: float):
    """Nelson-Siegel + un segundo término de curvatura con su propio τ2
    (diapositiva 83), para capturar formas de curva con dos jorobas que
    Nelson-Siegel no puede representar."""
    t = np.asarray(t, dtype=float)
    x1 = t / tau1
    x2 = t / tau2
    factor1 = (1 - np.exp(-x1)) / x1
    factor2 = (1 - np.exp(-x2)) / x2
    return (
        beta0
        + beta1 * factor1
        + beta2 * (factor1 - np.exp(-x1))
        + beta3 * (factor2 - np.exp(-x2))
    )


def _rmse(pred: np.ndarray, obs: np.ndarray) -> float:
    return float(np.sqrt(np.mean((pred - obs) ** 2)))


def ajustar_nelson_siegel(plazos: list[float], tasas: list[float]) -> dict:
    """Mínimos cuadrados no lineales con MÚLTIPLES puntos de partida para
    τ1 (el parámetro más propenso a mínimos locales en este modelo) — el
    enunciado pide explícitamente encontrar los parámetros óptimos
    GLOBALES, no solo el primer mínimo que encuentre el optimizador."""
    t = np.asarray(plazos, dtype=float)
    y = np.asarray(tasas, dtype=float)

    mejor = None
    for tau1_0 in (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0):
        x0 = [y[-1], y[0] - y[-1], 0.0, tau1_0]
        resultado = minimize(
            lambda p: _rmse(nelson_siegel(t, *p), y) ** 2,
            x0,
            bounds=[(-20, 20), (-20, 20), (-20, 20), (0.05, 30)],
            method="L-BFGS-B",
        )
        if resultado.success and (mejor is None or resultado.fun < mejor.fun):
            mejor = resultado

    beta0, beta1, beta2, tau1 = mejor.x
    ajustado = nelson_siegel(t, beta0, beta1, beta2, tau1)
    return {
        "modelo": "Nelson-Siegel",
        "parametros": {"beta0": beta0, "beta1": beta1, "beta2": beta2, "tau1": tau1},
        "rmse": _rmse(ajustado, y),
        "ajustado": ajustado,
    }


def ajustar_svensson(plazos: list[float], tasas: list[float]) -> dict:
    """Igual que ajustar_nelson_siegel, pero con una grilla 2D de puntos
    de partida para τ1 y τ2 (dos parámetros propensos a mínimos locales
    acá, no solo uno)."""
    t = np.asarray(plazos, dtype=float)
    y = np.asarray(tasas, dtype=float)

    mejor = None
    for tau1_0 in (0.25, 0.5, 1.0, 2.0):
        for tau2_0 in (3.0, 7.0, 12.0, 20.0):
            if tau2_0 <= tau1_0:
                continue
            x0 = [y[-1], y[0] - y[-1], 0.0, 0.0, tau1_0, tau2_0]
            resultado = minimize(
                lambda p: _rmse(svensson(t, *p), y) ** 2,
                x0,
                bounds=[(-50, 50), (-50, 50), (-50, 50), (-50, 50), (0.05, 30), (0.05, 30)],
                method="L-BFGS-B",
            )
            if resultado.success and (mejor is None or resultado.fun < mejor.fun):
                mejor = resultado

    beta0, beta1, beta2, beta3, tau1, tau2 = mejor.x
    ajustado = svensson(t, beta0, beta1, beta2, beta3, tau1, tau2)
    return {
        "modelo": "Svensson",
        "parametros": {
            "beta0": beta0, "beta1": beta1, "beta2": beta2, "beta3": beta3,
            "tau1": tau1, "tau2": tau2,
        },
        "rmse": _rmse(ajustado, y),
        "ajustado": ajustado,
    }
