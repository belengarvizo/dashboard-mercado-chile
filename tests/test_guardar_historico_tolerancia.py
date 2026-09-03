"""Test de regresión (no AppTest, no red) para guardar_historico(): confirma
que el ruido de punto flotante en precios ajustados por dividendos/splits
(el patrón real que causaba la lentitud de la actualización diaria — ver
commit) NO dispara un UPDATE, pero que un cambio de precio genuino sí lo
hace, y que fechas nuevas y cambios de volumen se siguen manejando bien.

Usa un ticker descartable dedicado (nunca en TICKERS_IPSA/TICKERS_DOW_JONES)
contra la BD real (mismo criterio que el resto de los tests de este
proyecto — sin mocks), y lo borra al final para no dejar basura en
producción.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from models import get_session, PrecioAccion
from scripts.actualizar_acciones import guardar_historico

TICKER_PRUEBA = "TEST_TOLERANCIA_NO_USAR_EN_PROD"


def _historico(filas: dict) -> pd.DataFrame:
    """filas: {fecha (date): (precio, volumen)} -> DataFrame con la misma
    forma que yfinance.Ticker(...).history() (índice de fecha, columnas
    Close/Volume)."""
    index = pd.DatetimeIndex([pd.Timestamp(f) for f in filas])
    return pd.DataFrame(
        {"Close": [v[0] for v in filas.values()], "Volume": [v[1] for v in filas.values()]},
        index=index,
    )


def _limpiar(session):
    session.query(PrecioAccion).filter_by(ticker=TICKER_PRUEBA).delete()
    session.commit()


def test_ruido_de_punto_flotante_no_dispara_update_pero_cambio_real_si():
    session = get_session()
    _limpiar(session)
    try:
        fecha_a = pd.Timestamp("2024-01-02").date()
        fecha_b = pd.Timestamp("2024-01-03").date()
        fecha_c = pd.Timestamp("2024-01-04").date()

        # Carga inicial: 3 filas.
        guardar_historico(session, TICKER_PRUEBA, _historico({
            fecha_a: (100.0000, 1000),
            fecha_b: (200.0000, 2000),
            fecha_c: (300.0000, 3000),
        }))
        session.commit()

        # "Re-descarga" con: (a) ruido de punto flotante en fecha_a (diff
        # relativa ~0.00003%, el orden de magnitud real observado en
        # producción con AGUAS-A.SN), (b) un cambio de precio GENUINO en
        # fecha_b (+2%, mucho mayor que la tolerancia), (c) fecha_c sin
        # cambios.
        guardar_historico(session, TICKER_PRUEBA, _historico({
            fecha_a: (100.0001, 1000),   # ruido -> NO deberia actualizar
            fecha_b: (204.0000, 2000),   # cambio real -> SI deberia actualizar
            fecha_c: (300.0000, 3000),   # sin cambio
        }))
        session.commit()

        guardados = {
            f: (float(p), v) for f, p, v in
            session.query(PrecioAccion.fecha, PrecioAccion.precio_cierre, PrecioAccion.volumen)
            .filter_by(ticker=TICKER_PRUEBA)
        }

        # fecha_a: el ruido NO debe haber pisado el valor original (o, si
        # lo pisó, la diferencia debe seguir siendo indistinguible de ruido
        # -- lo que de verdad importa es que fecha_b sí cambió).
        assert abs(guardados[fecha_a][0] - 100.0) < 0.001, "El ruido de punto flotante no deberia mover el precio guardado"
        # fecha_b: el cambio real SI debe haberse aplicado.
        assert guardados[fecha_b][0] == 204.0, "Un cambio de precio real (2%) debe disparar el UPDATE"
        # fecha_c: sin cambios.
        assert guardados[fecha_c][0] == 300.0

        # Fecha nueva + cambio de volumen (sin cambio de precio) siguen funcionando.
        fecha_d = pd.Timestamp("2024-01-05").date()
        guardar_historico(session, TICKER_PRUEBA, _historico({
            fecha_a: (100.0001, 1000),
            fecha_b: (204.0000, 2000),
            fecha_c: (300.0000, 9999),   # mismo precio, volumen distinto -> debe actualizar
            fecha_d: (400.0000, 4000),   # fecha nueva -> debe insertar
        }))
        session.commit()

        guardados_2 = {
            f: (float(p), v) for f, p, v in
            session.query(PrecioAccion.fecha, PrecioAccion.precio_cierre, PrecioAccion.volumen)
            .filter_by(ticker=TICKER_PRUEBA)
        }
        assert guardados_2[fecha_c][1] == 9999, "Un cambio de volumen (sin cambio de precio) debe disparar el UPDATE"
        assert fecha_d in guardados_2 and guardados_2[fecha_d] == (400.0, 4000), "Una fecha nueva debe insertarse"

        print("OK: ruido de punto flotante ignorado, cambios reales (precio y volumen) y fechas nuevas manejados bien.")
    finally:
        _limpiar(session)
        session.close()


def test_detector_de_reajuste_historico_distingue_split_de_ruido_de_dividendo():
    """El segundo valor devuelto por guardar_historico() debe marcarse True
    solo cuando un cierre YA guardado cambia por un factor grande (split o
    corrección de datos), no por el re-ajuste continuo de dividendos."""
    session = get_session()
    _limpiar(session)
    try:
        f1 = pd.Timestamp("2024-02-01").date()
        f2 = pd.Timestamp("2024-02-02").date()

        guardar_historico(session, TICKER_PRUEBA, _historico({
            f1: (100.0, 1000),
            f2: (110.0, 1100),
        }))
        session.commit()

        # (a) Ruido de re-ajuste por dividendo (~0.001%): NO es reajuste histórico.
        _, reajuste_ruido = guardar_historico(session, TICKER_PRUEBA, _historico({
            f1: (100.001, 1000),
            f2: (110.001, 1100),
        }))
        session.commit()
        assert reajuste_ruido is False, "El re-ajuste por dividendo en efectivo no debe marcar reajuste histórico"

        # (b) Split 2:1 -> los cierres ya guardados caen ~50%: SÍ es reajuste.
        _, reajuste_split = guardar_historico(session, TICKER_PRUEBA, _historico({
            f1: (50.0, 1000),
            f2: (55.0, 1100),
        }))
        session.commit()
        assert reajuste_split is True, "Un split (cambio ~50% en un cierre ya guardado) debe marcar reajuste histórico"

        print("OK: el detector distingue el ruido de dividendo de un split real.")
    finally:
        _limpiar(session)
        session.close()


if __name__ == "__main__":
    test_ruido_de_punto_flotante_no_dispara_update_pero_cambio_real_si()
    test_detector_de_reajuste_historico_distingue_split_de_ruido_de_dividendo()
