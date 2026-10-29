"""Pruebas del catálogo de subyacentes de «Derivados»."""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from catalogo_derivados import SUBYACENTES, nombre_de


def test_cada_subyacente_tiene_nombre_y_descripcion():
    for ticker, d in SUBYACENTES.items():
        assert d["nombre"].strip(), ticker
        assert d["descripcion"].strip(), ticker


def test_nombre_de_nunca_inventa_un_nombre():
    assert nombre_de("SPY") == "State Street SPDR S&P 500 ETF Trust"
    assert nombre_de("XXXX") == "XXXX"


def test_los_subyacentes_ya_tienen_historial_de_precios_en_otras_secciones():
    """Derivados no baja nada nuevo: sus 5 subyacentes deben estar ya en los universos de otras secciones, así el
    cron diario ya los mantiene al día sin que esta sección tenga que agregar nada a la descarga."""
    from constants import TICKERS_ETFS_ACCIONES, TICKERS_RENTA_FIJA

    ya_cubiertos = set(TICKERS_ETFS_ACCIONES) | set(TICKERS_RENTA_FIJA)
    faltantes = set(SUBYACENTES) - ya_cubiertos
    assert not faltantes, f"estos subyacentes no los baja ningún script diario: {faltantes}"
