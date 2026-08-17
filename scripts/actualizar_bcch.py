"""
Descarga las series macro del Banco Central de Chile y las guarda en la BD.
Este script lo corre el cron job de Railway una vez al día.

Requiere las variables de entorno:
  BCCH_TOKEN   -> API key/token gratuito de la API del BCCh (autenticación REST)
  DATABASE_URL -> conexión a PostgreSQL (la da Railway)
"""

import os
import sys
from datetime import datetime, date

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import requests
from models import get_session, SerieMacro, MetadataActualizacion

# Las 4 series que acordamos para el v1.
# El codigo_serie es el identificador que usa el BCCh para cada serie.
SERIES_A_DESCARGAR = {
    "F073.TCO.PRE.Z.D": {"nombre": "Tipo de cambio observado", "frecuencia": "diaria"},
    "F022.TPM.TIN.D001.NO.Z.D": {"nombre": "Tasa de política monetaria (TPM)", "frecuencia": "diaria"},
   "G073.IPC.IND.2018.M": {"nombre": "IPC (índice)", "frecuencia": "mensual"},
    "F032.IMC.IND.Z.Z.EP18.Z.Z.0.M": {"nombre": "IMACEC", "frecuencia": "mensual"},
}

BCCH_URL = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"


def descargar_serie(codigo_serie: str, first_date: str = "2015-01-01") -> list[dict]:
    """Pide una serie a la API del BCCh y devuelve una lista de {fecha, valor}."""
    token = os.environ["BCCH_TOKEN"]

    params = {
        "token": token,
        "firstdate": first_date,
        "lastdate": date.today().isoformat(),
        "timeseries": codigo_serie,
        "function": "GetSeries",
    }

    response = requests.get(BCCH_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

 # La API devuelve la serie en Series.Obs -> lista de {indexDateString, value}
    series = data.get("Series") or {}
    observaciones = series.get("Obs") or []

    if not observaciones:
        print(f"  Respuesta completa de la API para {codigo_serie}:")
        print(f"  {data}")

    resultado = []
    for obs in observaciones:
        try:
            fecha = datetime.strptime(obs["indexDateString"], "%d-%m-%Y").date()
            valor = float(obs["value"])
            resultado.append({"fecha": fecha, "valor": valor})
        except (ValueError, KeyError, TypeError):
            # Algunos valores vienen vacíos ("NaN" o similar) - los saltamos
            continue

    return resultado


def actualizar_todas_las_series():
    session = get_session()

    try:
        for codigo, info in SERIES_A_DESCARGAR.items():
            print(f"Descargando {info['nombre']} ({codigo})...")
            observaciones = descargar_serie(codigo)

            for obs in observaciones:
                # Evita duplicados: si ya existe esa fecha+serie, la actualiza; si no, la crea.
                existente = (
                    session.query(SerieMacro)
                    .filter_by(codigo_serie=codigo, fecha=obs["fecha"])
                    .first()
                )
                if existente:
                    existente.valor = obs["valor"]
                else:
                    session.add(
                        SerieMacro(
                            codigo_serie=codigo,
                            nombre=info["nombre"],
                            fecha=obs["fecha"],
                            valor=obs["valor"],
                            frecuencia=info["frecuencia"],
                        )
                    )

            print(f"  -> {len(observaciones)} observaciones procesadas")

        # Registra que esta fuente se actualizó ahora
        meta = session.query(MetadataActualizacion).filter_by(fuente="bcch").first()
        if meta:
            meta.ultima_actualizacion = datetime.now()
        else:
            session.add(MetadataActualizacion(fuente="bcch", ultima_actualizacion=datetime.now()))

        session.commit()
        print("Actualización del BCCh completada.")

    except Exception as e:
        session.rollback()
        print(f"Error actualizando datos del BCCh: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    actualizar_todas_las_series()
