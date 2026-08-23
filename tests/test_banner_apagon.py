"""Valida el banner de "apagón de mercado completo" (detectar_apagon_mercado
+ _mostrar_banner_apagon en app/dashboard.py), a nivel de pestaña, distinto
de la columna "Atraso" por fila del heatmap.

Dos pruebas:
1. Con AppTest de la app COMPLETA (datos reales de la BD): confirma que el
   banner st.error() aparece, con el % y la fecha correctos, dado el
   apagón de Yahoo Finance ya diagnosticado para las acciones .SN.
2. Con datos simulados "frescos" (sin apagón), a nivel de la función pura
   detectar_apagon_mercado: confirma que el banner NO se dispara. Esta
   prueba no pasa por AppTest ni toca la base de datos real a propósito —
   simular "datos frescos" solo es seguro fabricando un DataFrame en
   memoria; escribir filas ficticias en la base de producción para probar
   esto sería una acción destructiva innecesaria.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from constants import TICKERS_IPSA
from market_data import detectar_apagon_mercado
from models import get_session, PrecioAccion

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")


def _apagon_manual_ipsa() -> dict:
    """Mismo calculo que detectar_apagon_mercado pero hecho aparte, leyendo
    la BD directo, para comparar contra lo que la app realmente muestra."""
    session = get_session()
    rows = session.query(PrecioAccion.ticker, PrecioAccion.fecha, PrecioAccion.precio_cierre).filter(
        PrecioAccion.ticker.in_(TICKERS_IPSA)
    ).all()
    session.close()
    df = pd.DataFrame(rows, columns=["ticker", "fecha", "precio_cierre"])
    resultado = detectar_apagon_mercado(df, TICKERS_IPSA)
    assert resultado is not None, "Esta prueba asume que el apagon de Yahoo para el IPSA sigue activo"
    return resultado


def test_banner_apagon_aparece_en_la_app_con_datos_reales():
    esperado = _apagon_manual_ipsa()
    pct_esperado = round(esperado["pct_afectado"] * 100)
    fecha_esperada = esperado["fecha_apagon"].strftime("%Y-%m-%d")

    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=300).run(timeout=300)
    assert not at.exception, f"La app lanzo una excepcion al correr: {at.exception}"

    textos_error = [e.value for e in at.error]
    banners_apagon = [t for t in textos_error if "Apagón de datos detectado" in t]
    assert banners_apagon, (
        f"No aparecio ningun banner de apagon. Errores renderizados: {textos_error}"
    )
    # Debe aparecer en las 2 pestañas que agregan el universo del IPSA
    # (Acciones IPSA, Riesgo — Momentum IPSA y Optimización de Portafolios
    # se eliminaron) — la de Laboratorio Financiero usa un universo
    # distinto (US) y no debe dispararse hoy.
    assert len(banners_apagon) >= 2, f"Se esperaban >=2 banners, aparecieron {len(banners_apagon)}"

    banner = banners_apagon[0]
    print(f"Banner renderizado: {banner!r}")
    assert f"{pct_esperado}%" in banner
    assert fecha_esperada in banner


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
    test_banner_apagon_aparece_en_la_app_con_datos_reales()
    test_banner_no_se_dispara_con_datos_frescos_simulados()
    print("OK: ambas pruebas pasaron.")
