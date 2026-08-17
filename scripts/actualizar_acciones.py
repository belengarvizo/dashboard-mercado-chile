"""
Descarga precios históricos de acciones del IPSA vía Yahoo Finance
y los guarda en la base de datos. Corre junto al script del BCCh
en el cron job diario de Railway.
"""

import os
import sys
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import yfinance as yf
from models import get_session, PrecioAccion, MetadataActualizacion

# Las 5 acciones que acordamos para el v1.
# El sufijo .SN indica Bolsa de Santiago en Yahoo Finance.
TICKERS_A_DESCARGAR = [
    "SQM-B.SN",
    "CHILE.SN",       # Banco de Chile
    "FALABELLA.SN",
    "COPEC.SN",
    "CMPC.SN",
]


def descargar_ticker(ticker: str, periodo: str = "5y"):
    """Descarga el histórico de un ticker usando yfinance."""
    accion = yf.Ticker(ticker)
    historico = accion.history(period=periodo)
    return historico


def actualizar_todas_las_acciones():
    session = get_session()

    try:
        for ticker in TICKERS_A_DESCARGAR:
            print(f"Descargando {ticker}...")
            historico = descargar_ticker(ticker)

            contador = 0
            for fecha_idx, fila in historico.iterrows():
                fecha = fecha_idx.date()

                existente = (
                    session.query(PrecioAccion)
                    .filter_by(ticker=ticker, fecha=fecha)
                    .first()
                )
                if existente:
                    existente.precio_cierre = float(fila["Close"])
                    existente.volumen = int(fila["Volume"])
                else:
                    session.add(
                        PrecioAccion(
                            ticker=ticker,
                            fecha=fecha,
                            precio_cierre=float(fila["Close"]),
                            volumen=int(fila["Volume"]),
                        )
                    )
                contador += 1

            print(f"  -> {contador} días procesados")

        meta = session.query(MetadataActualizacion).filter_by(fuente="yfinance").first()
        if meta:
            meta.ultima_actualizacion = datetime.now()
        else:
            session.add(MetadataActualizacion(fuente="yfinance", ultima_actualizacion=datetime.now()))

        session.commit()
        print("Actualización de acciones completada.")

    except Exception as e:
        session.rollback()
        print(f"Error actualizando precios de acciones: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    actualizar_todas_las_acciones()
