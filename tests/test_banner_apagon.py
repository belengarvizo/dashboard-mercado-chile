"""Valida el banner de "apagón de mercado completo" (detectar_apagon_mercado
+ _mostrar_banner_apagon en app/dashboard.py), a nivel de pestaña, distinto
de la columna "Atraso" por fila del heatmap.

La primera versión de este archivo asumía que el apagón real de Yahoo
Finance (ya diagnosticado en esta conversación) seguía activo, y usaba
datos reales de la BD para probar que el banner SÍ aparece. Esa suposición
dejó de ser cierta apenas se resolvió el apagón — dejar el test así lo
hacía frágil (iba a fallar apenas la fuente se pusiera al día, que es
justo el comportamiento correcto). Ahora ambos escenarios (apagón / sin
apagón) se prueban con datos simulados a nivel de la función pura
detectar_apagon_mercado, que no dependen de qué esté pasando ahora mismo
con Yahoo Finance — más un chequeo liviano con AppTest de que la app
corre sin excepciones y, si hay un apagón real en curso al momento de
correr la prueba, el banner que muestra tiene formato correcto (sin
exigirlo, porque no siempre va a haber uno)."""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from constants import TICKERS_IPSA
from market_data import detectar_apagon_mercado

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")


def test_banner_apagon_se_dispara_con_datos_simulados_de_apagon():
    """Simula 25 de las 30 acciones del IPSA congeladas por 10 días
    hábiles (>5, el umbral) agrupadas en la misma fecha -- el patrón
    real observado con Yahoo Finance -- y confirma que
    detectar_apagon_mercado lo detecta con el % y la fecha correctos.
    No depende de si hay un apagón real en curso ahora mismo."""
    hoy = pd.Timestamp.now().normalize()
    fecha_congelado = hoy - pd.Timedelta(days=14)  # ~10 dias habiles atras
    filas = []
    for i, ticker in enumerate(TICKERS_IPSA):
        atrasado = i < 25  # 25 de 30 = 83%, supera el umbral de 80%
        precio = 100.0
        for offset in range(40, -1, -1):
            fecha = hoy - pd.Timedelta(days=offset)
            if atrasado and fecha >= fecha_congelado:
                precio_fila = 50.0  # congelado desde fecha_congelado
            else:
                precio_fila = precio + offset * 0.01  # distinto cada dia
            filas.append({"ticker": ticker, "fecha": fecha, "precio_cierre": precio_fila})
    df_apagon = pd.DataFrame(filas)

    resultado = detectar_apagon_mercado(df_apagon, TICKERS_IPSA)
    assert resultado is not None, "Deberia detectar el apagon simulado (25/30 tickers congelados)"
    assert resultado["pct_afectado"] >= 0.8
    assert resultado["fecha_apagon"] == fecha_congelado.date()


def test_banner_apagon_app_corre_sin_excepciones_y_formato_es_correcto_si_hay_uno():
    """Chequeo liviano con AppTest: la app corre bien, y SI hay un apagón
    real en curso al momento de correr esta prueba (no se puede forzar
    ni se asume), el banner que muestra tiene el formato esperado."""
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=300).run(timeout=300)
    assert not at.exception, f"La app lanzo una excepcion al correr: {at.exception}"

    textos_error = [e.value for e in at.error]
    banners_apagon = [t for t in textos_error if "Apagón de datos detectado" in t]

    if not banners_apagon:
        print("No hay ningun apagon real en curso ahora mismo -- nada que validar en la UI (esperado).")
        return

    print(f"Apagon real en curso ({len(banners_apagon)} banners) -- validando formato.")
    banner = banners_apagon[0]
    assert "%" in banner
    assert any(str(y) in banner for y in range(2024, 2031))  # trae una fecha con año


def test_banner_no_se_dispara_con_datos_frescos_simulados():
    """Con datos simulados donde las 30 acciones del IPSA tienen precios
    reales y distintos hasta hoy (sin empates ni atraso), la deteccion NO
    debe disparar el apagon — confirma que el banner desaparece solo
    cuando la fuente se pone al dia, sin cambios de codigo."""
    hoy = pd.Timestamp.now().normalize()
    rng = np.random.default_rng(42)
    filas = []
    for ticker in TICKERS_IPSA:
        precio = 100.0
        for offset in range(30, -1, -1):
            precio *= 1 + rng.normal(0, 0.01)
            filas.append({"ticker": ticker, "fecha": hoy - pd.Timedelta(days=offset), "precio_cierre": precio})
    df_fresco = pd.DataFrame(filas)

    resultado = detectar_apagon_mercado(df_fresco, TICKERS_IPSA)
    assert resultado is None, f"No deberia detectar apagon con datos frescos, pero devolvio: {resultado}"


if __name__ == "__main__":
    test_banner_apagon_se_dispara_con_datos_simulados_de_apagon()
    test_banner_apagon_app_corre_sin_excepciones_y_formato_es_correcto_si_hay_uno()
    test_banner_no_se_dispara_con_datos_frescos_simulados()
    print("OK: las tres pruebas pasaron.")
