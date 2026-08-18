"""
Descarga precios históricos de acciones vía Yahoo Finance y los guarda
en la base de datos: las 30 acciones del IPSA, las 30 del Dow Jones, el
ETF ECH (proxy del IPSA, que no tiene ticker propio en Yahoo Finance),
benchmarks internacionales y las "7 Magníficas". Corre junto al script
del BCCh en el cron job diario de Railway.
"""

import os
import sys
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import yfinance as yf
from models import get_session, PrecioAccion, MetadataActualizacion
from constants import (
    TICKERS_IPSA,
    TICKER_PROXY_IPSA,
    TICKERS_BENCHMARK,
    TICKERS_MAGNIFICAS,
    TICKER_PETROLEO_WTI,
    TICKER_DOW_JONES,
    TICKERS_DOW_JONES,
)
from retry_utils import con_reintentos_db

# dict.fromkeys en vez de una lista simple: varias de las "7 Magníficas"
# (AAPL, MSFT, GOOGL, AMZN, NVDA) también son parte del Dow Jones — se
# descargan una sola vez, preservando el orden de la primera aparición.
TICKERS_A_DESCARGAR = list(dict.fromkeys(
    TICKERS_IPSA
    + [TICKER_PROXY_IPSA]
    + [t for t in TICKERS_BENCHMARK if t != TICKER_PROXY_IPSA]
    + TICKERS_MAGNIFICAS
    + TICKERS_DOW_JONES
    + [TICKER_PETROLEO_WTI, TICKER_DOW_JONES]
))


def descargar_ticker(ticker: str, periodo: str = "5y"):
    """Descarga el histórico de un ticker usando yfinance."""
    accion = yf.Ticker(ticker)
    historico = accion.history(period=periodo)
    return historico


def guardar_historico(session, ticker: str, historico):
    """Inserta o actualiza (por ticker+fecha) el histórico de un ticker en la BD.

    Trae fecha+precio+volumen ya guardados para ese ticker en una sola consulta
    (en vez de una consulta por día), inserta en bloque las fechas nuevas, y
    solo emite un UPDATE cuando el precio o el volumen realmente cambiaron (los
    precios de cierre históricos casi nunca se revisan, así que en una
    re-corrida normal esto evita miles de idas y vueltas innecesarias a la BD).
    """
    existentes = {
        fecha: (float(precio), volumen)
        for fecha, precio, volumen in session.query(
            PrecioAccion.fecha, PrecioAccion.precio_cierre, PrecioAccion.volumen
        ).filter_by(ticker=ticker)
    }

    nuevas = []
    contador = 0
    for fecha_idx, fila in historico.iterrows():
        fecha = fecha_idx.date()
        precio = float(fila["Close"])
        # Yahoo Finance a veces devuelve NaN para el día más reciente (ej.
        # sesión de mercado todavía incompleta) - no se guarda un "precio" que
        # en realidad no existe (causaba que el dashboard mostrara "nan").
        if precio != precio:  # NaN nunca es igual a sí mismo
            continue
        # Algunos índices/ETFs (ej. benchmarks internacionales) no traen volumen.
        volumen = int(fila["Volume"]) if pd.notna(fila["Volume"]) else None

        if fecha not in existentes:
            nuevas.append(PrecioAccion(ticker=ticker, fecha=fecha, precio_cierre=precio, volumen=volumen))
        elif existentes[fecha] != (precio, volumen):
            session.query(PrecioAccion).filter_by(ticker=ticker, fecha=fecha).update({
                "precio_cierre": precio,
                "volumen": volumen,
            })
        contador += 1

    if nuevas:
        session.bulk_save_objects(nuevas)

    return contador


def actualizar_todas_las_acciones():
    session = get_session()

    try:
        for ticker in TICKERS_A_DESCARGAR:
            print(f"Descargando {ticker}...")
            historico = descargar_ticker(ticker)

            def _guardar_y_commitear(ticker=ticker, historico=historico):
                contador_local = guardar_historico(session, ticker, historico)
                session.commit()
                return contador_local

            # La descarga vía yfinance no se reintenta acá (no es el problema
            # observado); solo la escritura a la BD, propensa a cortes
            # transitorios de la conexión serverless de Neon. guardar_historico
            # es idempotente (compara contra lo ya guardado), así que reintentar
            # la función completa -no solo el commit- es seguro.
            contador = con_reintentos_db(session, _guardar_y_commitear)
            print(f"  -> {contador} días procesados")

        def _guardar_metadata():
            meta = session.query(MetadataActualizacion).filter_by(fuente="yfinance").first()
            if meta:
                meta.ultima_actualizacion = datetime.now()
            else:
                session.add(MetadataActualizacion(fuente="yfinance", ultima_actualizacion=datetime.now()))
            session.commit()

        con_reintentos_db(session, _guardar_metadata)
        print("Actualización de acciones completada.")

    except Exception as e:
        session.rollback()
        print(f"Error actualizando precios de acciones: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    actualizar_todas_las_acciones()
