"""Valida la regla de frescura del badge de cambio en "Key indicators"
(market_data.calcular_resumen_mercado / _badge_visible):

  - serie DIARIA con dato fresco (= fecha de referencia)  -> badge visible
  - serie DIARIA con dato > 1 día hábil detrás            -> badge OCULTO
  - serie DIARIA exactamente 1 día hábil detrás           -> badge visible
  - serie MENSUAL, aunque tenga meses de atraso           -> badge visible
  - feriado de EEUU entre medio no cuenta como día hábil  (caso Fed Funds)

Datos simulados (sin BD ni red).
"""
import os
import sys
from datetime import date

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from market_data import calcular_resumen_mercado, INDICADORES_PREMERCADO


def _macro(nombre, fechas_valores):
    return pd.DataFrame(
        [{"nombre": nombre, "fecha": f, "valor": v} for f, v in fechas_valores]
    )


def _serie_diaria(nombre, ultima_fecha, n=6, valor=3.63):
    fechas = pd.bdate_range(end=ultima_fecha, periods=n)
    return _macro(nombre, [(f.date(), valor) for f in fechas])


NOMBRE = {et: clave for et, tipo, clave, u, c in INDICADORES_PREMERCADO}
CAD = {et: c for et, tipo, clave, u, c in INDICADORES_PREMERCADO}

REF = date(2026, 9, 8)  # martes


def _correr(df_macro):
    # df_acciones vacío: las filas "accion" quedan sin resultado, no molestan
    df_acc = pd.DataFrame(columns=["ticker", "fecha", "precio_cierre", "volumen"])
    res = calcular_resumen_mercado(df_macro, df_acc)
    return {r["etiqueta"]: r for r in res}


def test_diaria_fresca_muestra_badge_y_diaria_atrasada_lo_oculta():
    df = pd.concat([
        # USD/CLP fresca al día de referencia
        _serie_diaria(NOMBRE["USD/CLP"], REF, valor=940.0),
        # TPM EEUU (Fed Funds) atrasada al 2026-09-03 (jueves); entre medio
        # está el Labor Day (lunes 07) -> 2 días hábiles detrás (03, 04) > 1
        _serie_diaria(NOMBRE["TPM EEUU"], date(2026, 9, 3), valor=3.63),
    ], ignore_index=True)
    r = _correr(df)

    assert r["USD/CLP"]["resultado"] is not None
    assert r["USD/CLP"]["badge_visible"] is True, "una serie diaria fresca debe mostrar el badge"

    assert r["TPM EEUU"]["resultado"] is not None
    assert r["TPM EEUU"]["badge_visible"] is False, "Fed Funds 2 días hábiles detrás debe ocultar el badge"


def test_umbral_de_un_dia_habil():
    # referencia = viernes 2026-09-11
    ref = date(2026, 9, 11)
    df_1dia = pd.concat([
        _serie_diaria(NOMBRE["USD/CLP"], ref, valor=940.0),
        _serie_diaria(NOMBRE["TPM Chile"], date(2026, 9, 10), valor=4.5),  # jueves: 1 día hábil detrás
    ], ignore_index=True)
    assert _correr(df_1dia)["TPM Chile"]["badge_visible"] is True, "1 día hábil detrás se tolera"

    df_2dias = pd.concat([
        _serie_diaria(NOMBRE["USD/CLP"], ref, valor=940.0),
        _serie_diaria(NOMBRE["TPM Chile"], date(2026, 9, 9), valor=4.5),   # miércoles: 2 días hábiles detrás
    ], ignore_index=True)
    assert _correr(df_2dias)["TPM Chile"]["badge_visible"] is False, "2 días hábiles detrás oculta el badge"

    # feriado EEUU entre medio no cuenta: dato del viernes 2026-09-04, ref
    # martes 2026-09-08, con Labor Day (lunes 07) -> solo 09-04 y 09-07(feriado, no)
    # -> 09-04 y ... busday_count('09-04','09-08', feriados=[09-07]) = 1 (solo 09-04)
    df_feriado = pd.concat([
        _serie_diaria(NOMBRE["USD/CLP"], REF, valor=940.0),
        _serie_diaria(NOMBRE["TPM EEUU"], date(2026, 9, 4), valor=3.63),
    ], ignore_index=True)
    assert _correr(df_feriado)["TPM EEUU"]["badge_visible"] is True, (
        "con Labor Day entre medio, un dato del viernes previo queda a 1 día hábil"
    )


def test_mensuales_siempre_muestran_badge_aunque_tengan_meses_de_atraso():
    df = pd.concat([
        _serie_diaria(NOMBRE["USD/CLP"], REF, valor=940.0),  # fija la referencia en 2026-09-08
        _macro(NOMBRE["IPC (inflación anual)"],
               [(date(2026, 6, 1), 3.9), (date(2026, 7, 1), 4.33), (date(2026, 8, 1), 3.52)]),
        _macro(NOMBRE["Imacec"],
               [(date(2026, 5, 1), 2.1), (date(2026, 6, 1), 2.01), (date(2026, 7, 1), -1.49)]),
        _macro(NOMBRE["Tasa de desempleo"],
               [(date(2026, 5, 1), 8.9), (date(2026, 6, 1), 8.94), (date(2026, 7, 1), 8.92)]),
    ], ignore_index=True)
    r = _correr(df)
    for et in ("IPC (inflación anual)", "Imacec", "Tasa de desempleo"):
        assert CAD[et] == "mensual"
        assert r[et]["resultado"] is not None
        assert r[et]["badge_visible"] is True, f"{et} (mensual) siempre muestra el badge"


if __name__ == "__main__":
    test_diaria_fresca_muestra_badge_y_diaria_atrasada_lo_oculta()
    test_umbral_de_un_dia_habil()
    test_mensuales_siempre_muestran_badge_aunque_tengan_meses_de_atraso()
    print("OK: las tres pruebas pasaron.")
