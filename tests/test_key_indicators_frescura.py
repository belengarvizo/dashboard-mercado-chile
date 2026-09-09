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


def test_delta_sin_direccion_cuando_el_cambio_mostrado_es_0():
    """Un indicador fresco cuyo cambio, redondeado a 2 decimales, es 0.00 se
    marca delta_sin_direccion=True (para que quien renderiza no le ponga
    color/flecha/"+"). Un cambio real -aunque sea chico- se marca False."""
    # TPM Chile: valor plano (0.00 pp exacto) -> sin dirección
    # UF: se mueve +0.003% -> muestra "0.00%" -> sin dirección
    # USD/CLP: se mueve -0.74% -> con dirección
    df = pd.concat([
        _serie_diaria(NOMBRE["TPM Chile"], REF, valor=4.5),  # todos iguales
        pd.DataFrame([
            {"nombre": NOMBRE["UF"], "fecha": date(2026, 9, 7), "valor": 40884.32},
            {"nombre": NOMBRE["UF"], "fecha": REF, "valor": 40885.63},  # +0.0032%
        ]),
        pd.DataFrame([
            {"nombre": NOMBRE["USD/CLP"], "fecha": date(2026, 9, 7), "valor": 940.0},
            {"nombre": NOMBRE["USD/CLP"], "fecha": REF, "valor": 933.06},  # -0.74%
        ]),
    ], ignore_index=True)
    r = _correr(df)

    assert r["TPM Chile"]["delta_sin_direccion"] is True, "TPM Chile plana -> sin dirección"
    assert r["UF"]["delta_sin_direccion"] is True, "UF +0.003% se muestra 0.00% -> sin dirección"
    assert r["USD/CLP"]["delta_sin_direccion"] is False, "un cambio real de -0.74% SÍ tiene dirección"

    # el cambio real no se rompe: sigue teniendo su badge_visible normal
    assert r["USD/CLP"]["badge_visible"] is True


def test_render_sin_argumento_delta_cuando_no_hay_cambio():
    """En la pestaña (AppTest): un indicador fresco cuyo cambio se muestra
    0.00 se renderiza SIN argumento delta en st.metric — el proto no trae
    delta, así que no hay flecha ni color — y el caption lleva "· no change".
    Un cambio real conserva su delta. Usa datos reales de la BD; la TPM Chile
    está plana entre reuniones, así que es el caso estable a chequear."""
    from streamlit.testing.v1 import AppTest

    dash = os.path.join(os.path.dirname(__file__), "..", "app", "dashboard.py")
    at = AppTest.from_file(dash, default_timeout=420)
    at.run(timeout=420)
    assert not at.exception, [str(e) for e in at.exception]

    por_label = {m.label: m for m in at.get("metric")}

    tpm = por_label.get("Chile Policy Rate")
    assert tpm is not None, "falta la métrica 'Chile Policy Rate'"
    assert tpm.proto.delta == "", (
        f"TPM Chile (plana entre RPM) no debería pasar delta a st.metric, tiene {tpm.proto.delta!r}"
    )

    con_delta = [m for m in at.get("metric") if m.proto.delta]
    assert con_delta, "debería haber al menos un indicador con cambio real (delta no vacío)"
    for m in con_delta:
        # un delta no vacío nunca debería ser un "0.00" sin signo (ese caso
        # va sin delta); siempre trae signo + o -
        assert m.proto.delta.lstrip()[0] in "+-", (
            f"{m.label}: un delta mostrado debe llevar signo, tiene {m.proto.delta!r}"
        )

    caps = [c.value for c in at.caption]
    assert any(c.startswith("as of ") and "· no change" in c for c in caps), (
        "el caption del caso sin cambio debe anotar '· no change'"
    )


if __name__ == "__main__":
    test_diaria_fresca_muestra_badge_y_diaria_atrasada_lo_oculta()
    test_umbral_de_un_dia_habil()
    test_mensuales_siempre_muestran_badge_aunque_tengan_meses_de_atraso()
    test_delta_sin_direccion_cuando_el_cambio_mostrado_es_0()
    test_render_sin_argumento_delta_cuando_no_hay_cambio()
    print("OK: las cinco pruebas pasaron.")
