"""Migración puntual: crea las tres tablas del módulo de trading y carga el
catálogo semilla de instrumentos de XTB.

El proyecto no usa Alembic. Esta migración va en SQL explícito (no con
create_all) porque usa cosas que el modelo ORM no expresa: una columna
generada, un índice parcial y varios CHECK. El SQL es el que se revisó y
aprobó, palabra por palabra.

Todo corre DENTRO DE UNA TRANSACCIÓN: o quedan las tres tablas y el catálogo,
o no queda nada a medias.

Idempotente: CREATE TABLE IF NOT EXISTS + un upsert del catálogo que NO pisa
lo que el usuario haya editado desde la UI (margen, valor por punto, pip y
notas se conservan si ya tenían valor).

Uso (con el .env apuntando a Railway):
    python scripts/crear_tablas_trading.py
    python scripts/crear_tablas_trading.py --solo-verificar
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from sqlalchemy import inspect, text

from catalogo_instrumentos import CATALOGO_SEMILLA
from models import get_engine

TABLAS = ("trading_instrumentos", "trading_operaciones", "trading_estado_cuenta")

DDL = """
CREATE TABLE IF NOT EXISTS trading_instrumentos (
    id               SERIAL PRIMARY KEY,
    nombre_xtb       TEXT        NOT NULL UNIQUE,
    categoria        TEXT        NOT NULL,
    elegible_torneo  BOOLEAN     NOT NULL DEFAULT TRUE,
    ticker_yahoo     TEXT,
    pip_tamano       NUMERIC(12, 8),
    margen_001_clp   NUMERIC(14, 2),
    valor_punto_clp  NUMERIC(14, 4),
    notas            TEXT,
    actualizado_en   TIMESTAMPTZ,
    CONSTRAINT trading_instrumentos_categoria_valida CHECK (
        categoria IN ('divisas', 'indices', 'indices_volatilidad',
                      'materias_primas', 'zona_gris', 'cripto')),
    CONSTRAINT trading_instrumentos_pip_positivo CHECK (
        pip_tamano IS NULL OR pip_tamano > 0),
    CONSTRAINT trading_instrumentos_margen_positivo CHECK (
        margen_001_clp IS NULL OR margen_001_clp > 0),
    CONSTRAINT trading_instrumentos_valor_punto_positivo CHECK (
        valor_punto_clp IS NULL OR valor_punto_clp > 0)
);

CREATE INDEX IF NOT EXISTS ix_trading_instrumentos_categoria
    ON trading_instrumentos (categoria, nombre_xtb);

CREATE TABLE IF NOT EXISTS trading_operaciones (
    id                      SERIAL PRIMARY KEY,
    instrumento             TEXT        NOT NULL,
    categoria               TEXT        NOT NULL,
    direccion               TEXT        NOT NULL,
    fecha_apertura          TIMESTAMPTZ NOT NULL,
    fecha_cierre            TIMESTAMPTZ,
    precio_entrada          NUMERIC(18, 8) NOT NULL,
    precio_salida           NUMERIC(18, 8),
    stop                    NUMERIC(18, 8),
    objetivo                NUMERIC(18, 8),
    lotes                   NUMERIC(12, 4) NOT NULL,
    margen_clp              NUMERIC(14, 2),
    riesgo_clp              NUMERIC(14, 2),
    resultado_clp           NUMERIC(14, 2),
    catalizador             TEXT,
    condicion_invalidacion  TEXT,
    tesis                   TEXT,
    notas                   TEXT,
    registrado_en           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duracion_segundos INTEGER GENERATED ALWAYS AS (
        CASE WHEN fecha_cierre IS NULL THEN NULL
             ELSE FLOOR(EXTRACT(EPOCH FROM (fecha_cierre - fecha_apertura)))::INTEGER
        END) STORED,
    CONSTRAINT trading_operaciones_direccion_valida CHECK (
        direccion IN ('compra', 'venta')),
    CONSTRAINT trading_operaciones_lotes_positivos CHECK (lotes > 0),
    CONSTRAINT trading_operaciones_cierre_posterior CHECK (
        fecha_cierre IS NULL OR fecha_cierre >= fecha_apertura),
    CONSTRAINT trading_operaciones_cierre_coherente CHECK (
        (fecha_cierre IS NULL AND precio_salida IS NULL)
        OR (fecha_cierre IS NOT NULL AND precio_salida IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ix_trading_operaciones_apertura
    ON trading_operaciones (fecha_apertura DESC);
CREATE INDEX IF NOT EXISTS ix_trading_operaciones_abiertas
    ON trading_operaciones (instrumento) WHERE fecha_cierre IS NULL;

CREATE TABLE IF NOT EXISTS trading_estado_cuenta (
    id                     SERIAL PRIMARY KEY,
    momento                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    equity_clp             NUMERIC(14, 2) NOT NULL,
    margen_disponible_clp  NUMERIC(14, 2),
    nota                   TEXT,
    CONSTRAINT trading_estado_cuenta_equity_positivo CHECK (equity_clp >= 0)
);

CREATE INDEX IF NOT EXISTS ix_trading_estado_cuenta_momento
    ON trading_estado_cuenta (momento DESC);
"""

# El upsert NO pisa lo que el usuario cargó desde la UI: margen, valor por
# punto, pip y notas solo se escriben si la fila todavía los tiene vacíos.
# Así se puede volver a correr la semilla (por ejemplo al agregar un
# instrumento nuevo) sin perder los datos de los tickets de XTB.
UPSERT = """
INSERT INTO trading_instrumentos
    (nombre_xtb, categoria, elegible_torneo, ticker_yahoo, pip_tamano,
     margen_001_clp, notas)
VALUES (:nombre, :categoria, :elegible, :ticker, :pip, :margen, :notas)
ON CONFLICT (nombre_xtb) DO UPDATE SET
    categoria       = EXCLUDED.categoria,
    elegible_torneo = EXCLUDED.elegible_torneo,
    ticker_yahoo    = COALESCE(trading_instrumentos.ticker_yahoo, EXCLUDED.ticker_yahoo),
    pip_tamano      = COALESCE(trading_instrumentos.pip_tamano, EXCLUDED.pip_tamano),
    margen_001_clp  = COALESCE(trading_instrumentos.margen_001_clp, EXCLUDED.margen_001_clp),
    notas           = COALESCE(NULLIF(trading_instrumentos.notas, ''), EXCLUDED.notas)
"""


def _verificar_destino(engine) -> None:
    url = str(engine.url)
    if "altaria.proxy.rlwy.net" not in url and "railway" not in url:
        print(f"AVISO: DATABASE_URL no parece de Railway ({url!r}). Abortando por seguridad.")
        sys.exit(1)
    print(f"Destino: {url.split('@')[-1]}")


def _informe(engine) -> None:
    insp = inspect(engine)
    presentes = set(insp.get_table_names())
    print("\n=== TABLAS ===")
    for tabla in TABLAS:
        existe = tabla in presentes
        marca = "OK " if existe else "FALTA"
        n_cols = len(insp.get_columns(tabla)) if existe else 0
        print(f"  [{marca}] {tabla:26s} columnas={n_cols}")

    with engine.connect() as conn:
        print("\n=== FILAS ===")
        for tabla in TABLAS:
            if tabla in presentes:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
                print(f"  {tabla:26s} {n:5d} filas")

        if "trading_instrumentos" in presentes:
            print("\n=== CATÁLOGO POR CATEGORÍA ===")
            filas = conn.execute(text(
                "SELECT categoria, COUNT(*), COUNT(ticker_yahoo), COUNT(pip_tamano) "
                "FROM trading_instrumentos GROUP BY categoria ORDER BY categoria"
            )).fetchall()
            for cat, total, con_ticker, con_pip in filas:
                print(f"  {cat:22s} {total:3d}   con ticker: {con_ticker:3d}   con pip: {con_pip:3d}")


def main() -> None:
    engine = get_engine()
    _verificar_destino(engine)

    if "--solo-verificar" in sys.argv:
        _informe(engine)
        return

    # Una sola transacción: o quedan las tres tablas con el catálogo cargado,
    # o no queda nada a medias.
    with engine.begin() as conn:
        conn.execute(text(DDL))
        insertados = 0
        for nombre, categoria, elegible, ticker, pip, margen, notas in CATALOGO_SEMILLA:
            conn.execute(text(UPSERT), {
                "nombre": nombre, "categoria": categoria, "elegible": elegible,
                "ticker": ticker, "pip": pip, "margen": margen, "notas": notas,
            })
            insertados += 1
        print(f"\nDDL aplicado y {insertados} instrumentos cargados (dentro de la transacción).")

    _informe(engine)


if __name__ == "__main__":
    main()
