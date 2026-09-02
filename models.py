"""
Define las tablas de la base de datos.
Usamos SQLAlchemy para no escribir SQL a mano.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Date, Numeric, BigInteger, DateTime, Text, Index
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

Base = declarative_base()


class SerieMacro(Base):
    """Series del Banco Central de Chile (tipo de cambio, TPM, IPC, IMACEC)."""
    __tablename__ = "series_macro"

    id = Column(Integer, primary_key=True)
    codigo_serie = Column(String, nullable=False)
    nombre = Column(String, nullable=False)
    fecha = Column(Date, nullable=False)
    valor = Column(Numeric, nullable=False)
    frecuencia = Column(String, nullable=False)


class PrecioAccion(Base):
    """Precios históricos de acciones del IPSA vía Yahoo Finance."""
    __tablename__ = "precios_acciones"
    # Índice compuesto (ticker, fecha): es el filtro que usa CASI toda
    # consulta a esta tabla (dashboard.py, market_data.py,
    # guardar_historico en actualizar_acciones.py). Sin él, cada consulta
    # por ticker hace un Seq Scan sobre toda la tabla (ya 205.874 filas y
    # creciendo ~164 filas/día) — confirmado con EXPLAIN ANALYZE antes de
    # agregar esto, no asumido: filtraba 204.625 de 205.874 filas por
    # consulta. Es la causa más probable de que guardar_historico() tarde
    # segundos por ticker en vez de milisegundos durante la actualización
    # diaria de precios.
    __table_args__ = (Index("ix_precios_acciones_ticker_fecha", "ticker", "fecha"),)

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False)
    fecha = Column(Date, nullable=False)
    precio_cierre = Column(Numeric, nullable=False)
    volumen = Column(BigInteger)


class MetadataActualizacion(Base):
    """Controla cuándo se actualizó cada fuente por última vez."""
    __tablename__ = "metadata_actualizacion"

    fuente = Column(String, primary_key=True)
    ultima_actualizacion = Column(DateTime, nullable=False)


class Noticia(Base):
    """Titulares de noticias económicas chilenas, para el Brief Premercado."""
    __tablename__ = "noticias"

    id = Column(Integer, primary_key=True)
    fuente = Column(String, nullable=False)
    titulo = Column(String, nullable=False)
    link = Column(String, nullable=False)
    fecha_publicacion = Column(DateTime, nullable=False)
    fecha_descarga = Column(DateTime, nullable=False)


class BriefDiario(Base):
    """Resumen diario generado por IA (Gemini) para el Brief Premercado.
    Se regenera una vez al día en el cron, no en cada visita al dashboard."""
    __tablename__ = "brief_diario"

    fecha = Column(Date, primary_key=True)
    contenido = Column(Text, nullable=False)
    generado_en = Column(DateTime, nullable=False)


class CuadraturaMesaDinero(Base):
    """Historial de "snapshots" guardados manualmente desde la pestaña
    Simulación Mesa de Dinero del dashboard. No es un dato de mercado real
    ni de ningún banco: es un registro de práctica del propio usuario
    (cuadratura de liquidez + riesgo-retorno del día), para que pueda
    mostrar un track record de varios días al practicar."""
    __tablename__ = "cuadraturas_mesa_dinero"

    id = Column(Integer, primary_key=True)
    guardado_en = Column(DateTime, nullable=False)
    saldo_esperado = Column(Numeric, nullable=False)
    saldo_informado = Column(Numeric, nullable=False)
    diferencia = Column(Numeric, nullable=False)
    encaje_excedente = Column(Numeric)
    retorno_portafolio = Column(Numeric)
    vol_portafolio = Column(Numeric)
    sharpe_portafolio = Column(Numeric)
    usdclp = Column(Numeric)
    uf = Column(Numeric)
    tpm_chile = Column(Numeric)
    brief = Column(Text)


def get_engine():
    database_url = os.environ["DATABASE_URL"]
    # pool_pre_ping: antes de reusar una conexión del pool, hace un chequeo
    # liviano y la reemplaza si ya murió — evita la mayoría de los
    # "server closed the connection unexpectedly" típicos de Postgres
    # serverless (Neon), que puede cerrar conexiones inactivas sin avisar.
    return create_engine(database_url, pool_pre_ping=True)


def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("Tablas creadas correctamente.")


if __name__ == "__main__":
    init_db()