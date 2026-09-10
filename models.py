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
    # Versión bilingüe EN/ES + glosario para el PDF (ver
    # generar_traduccion_y_glosario en scripts/generar_brief.py). Nullable:
    # es un paso NO crítico que puede fallar sin tumbar el brief en inglés;
    # cuando falta, el PDF sale solo en inglés desde `contenido`.
    contenido_bilingue = Column(Text, nullable=True)
    generado_en = Column(DateTime, nullable=False)


class ErrorActualizacion(Base):
    """Registro del último error de cada paso del cron (actualizar_todo.py),
    para diagnosticar sin depender del log de Railway. Se escribe best-effort:
    si esta tabla no existe o el insert falla, el paso igual reporta su error
    por el camino normal.

    `categoria` es la clasificación accionable del fallo:
      - "cuota"       -> límite/cuota del proveedor agotado (no reintentar hoy)
      - "transitorio" -> timeout / 5xx (se reintenta con backoff)
      - "bloqueo"     -> respuesta filtrada por safety (no reintentar el prompt)
      - "otro"        -> no clasificado (se relanza para que quede visible)
    """
    __tablename__ = "errores_actualizacion"

    id = Column(Integer, primary_key=True)
    fuente = Column(String, nullable=False)          # "brief", "bcch", "noticias", ...
    ocurrido_en = Column(DateTime, nullable=False)
    categoria = Column(String, nullable=False)
    tipo_excepcion = Column(String, nullable=False)  # type(exc).__name__
    mensaje = Column(Text, nullable=False)


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


class DefensaTopdownRespuesta(Base):
    """Borrador de las respuestas del módulo "Defensa Top-Down" del dashboard
    (Simulación Mesa de Dinero): las 16 preguntas de sensibilidad de mercado
    de la Tarea de Inversiones de la FEN + el calendario de catalizadores.
    No es un dato de mercado: es el trabajo del propio usuario, guardado para
    poder retomarlo y volcarlo al informe real que hay que entregar.

    `pregunta_id` es "q1".."q16" para las preguntas y "cat_1".."cat_4" para
    los campos del calendario de catalizadores (que usan solo `nota`).
    Cada "Guardar decisiones" inserta un snapshot completo con la misma
    `fecha`; el más reciente es el que se recupera al volver.

    Rediseño: en vez de 3 campos de texto largo (respuesta_i/ii/iii, ahora
    en desuso) cada pregunta guarda `decision_valor` — el valor del widget
    de decisión (string para radio/selectbox/número simple, JSON para las
    que tienen 2 widgets: q7, q9, q13, q16) — y `nota`, una nota corta
    opcional de 1-2 líneas."""
    __tablename__ = "defensa_topdown_respuestas"

    id = Column(Integer, primary_key=True)
    pregunta_id = Column(String, nullable=False)
    ticker = Column(String)
    respuesta_i = Column(Text)    # en desuso (rediseño a widgets de decisión)
    respuesta_ii = Column(Text)   # en desuso
    respuesta_iii = Column(Text)  # en desuso
    decision_valor = Column(Text)
    nota = Column(Text)
    fecha = Column(DateTime, nullable=False)


class DefensaTopdownPrediccion(Base):
    """Predicciones verificables que el usuario deja en el campo "(iii)
    impacto en la estrategia" de una pregunta de la Defensa Top-Down (ej.
    "+5% en 3 semanas" o un target price). Al cumplirse el plazo, el
    dashboard compara `precio_base` contra el precio real del ticker (Yahoo
    Finance) y muestra acierto/fallo, sin que nadie lo juzgue a mano.

    `tipo`: "pct" (valor_objetivo es un % de variación, ej. +5.0) o "target"
    (valor_objetivo es un precio objetivo absoluto). `precio_base` es el
    precio del ticker en el momento de registrar la predicción (None si
    Yahoo Finance no lo devolvió)."""
    __tablename__ = "defensa_topdown_predicciones"

    id = Column(Integer, primary_key=True)
    pregunta_id = Column(String, nullable=False)
    ticker = Column(String, nullable=False)
    texto = Column(Text)
    tipo = Column(String, nullable=False)
    valor_objetivo = Column(Numeric, nullable=False)
    horizonte_dias = Column(Integer, nullable=False)
    precio_base = Column(Numeric)
    fecha_hecha = Column(DateTime, nullable=False)

    # Resolución CONGELADA: se calcula UNA sola vez, cuando el plazo vence,
    # contra el precio histórico de la fecha objetivo (no el precio en vivo de
    # hoy). Una vez escrito `estado_resuelto`, no se vuelve a recalcular.
    precio_verificacion = Column(Numeric)   # cierre del ticker en la fecha objetivo (o día hábil previo más cercano)
    fecha_verificacion = Column(DateTime)   # la fecha efectiva a la que corresponde ese precio
    estado_resuelto = Column(String)        # "acierto" | "mal_calibrado" | "fallo" | "sin_datos"
    detalle_resuelto = Column(Text)
    error_pp = Column(Numeric)              # (variación real − variación predicha), en puntos porcentuales
    verificado_en = Column(DateTime)        # cuándo se congeló la resolución


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