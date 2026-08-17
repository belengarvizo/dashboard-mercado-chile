"""
Define las tablas de la base de datos.
Usamos SQLAlchemy para no escribir SQL a mano.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Date, Numeric, BigInteger, DateTime
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


def get_engine():
    database_url = os.environ["DATABASE_URL"]
    return create_engine(database_url)


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