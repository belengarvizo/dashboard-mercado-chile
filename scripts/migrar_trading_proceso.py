"""Migración aditiva: campos de proceso en el diario, planes de evento,
checklist y revisión semanal.

ADITIVA Y REVERSIBLE DE HECHO: solo agrega columnas NULLABLE y tablas nuevas.
No borra, no reescribe y no cambia el tipo de nada existente.

IDEMPOTENTE: ADD COLUMN IF NOT EXISTS, CREATE TABLE IF NOT EXISTS y los CHECK
dentro de un bloque DO que primero consulta pg_constraint (ADD CONSTRAINT no
tiene IF NOT EXISTS). Se puede correr dos veces sin romper nada.

Todo va en UNA transacción: o queda el esquema completo, o no queda nada a
medias.

Uso (con el .env apuntando a Railway):
    python scripts/migrar_trading_proceso.py
    python scripts/migrar_trading_proceso.py --solo-verificar
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from sqlalchemy import text

from models import get_engine

COLUMNAS_NUEVAS = {
    "conviccion": "INTEGER",
    "tendencia_diario": "TEXT",
    "evento_dia": "TEXT",
    "calidad_decision": "TEXT",
    "nota_post": "TEXT",
    # Apunta a evento_checklist.id, que tiene UNA fila por evento (no a
    # evento_planes, que tiene una por escenario). Sin FOREIGN KEY, igual que
    # el resto del diario: una foránea bloquearía registrar una operación real
    # si el checklist de ese evento todavía no existe.
    "evento_plan_id": "INTEGER",
}

TABLAS_NUEVAS = ("evento_planes", "evento_checklist", "trading_revision_semanal")

RESTRICCIONES = {
    "trading_operaciones_conviccion_valida":
        "CHECK (conviccion IS NULL OR conviccion BETWEEN 1 AND 3)",
    "trading_operaciones_tendencia_valida":
        "CHECK (tendencia_diario IS NULL OR tendencia_diario IN "
        "('a_favor','contra','neutral'))",
    "trading_operaciones_calidad_valida":
        "CHECK (calidad_decision IS NULL OR calidad_decision IN ('buena','mala'))",
}

DDL_TABLAS = """
-- `fecha` es TIMESTAMPTZ, o sea un instante absoluto. El formulario lo
-- CONSTRUYE interpretando lo que se escribe como hora de America/New_York
-- (es como publican BLS y la Fed) y la pantalla lo MUESTRA en hora de Chile.
-- El desfase no es constante: +1h hasta el 1-nov y +2h después.
CREATE TABLE IF NOT EXISTS evento_planes (
    id                SERIAL PRIMARY KEY,
    evento            TEXT        NOT NULL,
    fecha             TIMESTAMPTZ NOT NULL,
    escenario         TEXT        NOT NULL,
    probabilidad      NUMERIC(5,2),
    movimiento_pips   NUMERIC(10,2),
    peor_caso_pips    NUMERIC(10,2),
    tamano_max_lotes  NUMERIC(12,4),
    nota              TEXT,
    registrado_en     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evento_planes_probabilidad_valida CHECK (
        probabilidad IS NULL OR (probabilidad >= 0 AND probabilidad <= 100)),
    CONSTRAINT evento_planes_lotes_positivos CHECK (
        tamano_max_lotes IS NULL OR tamano_max_lotes > 0)
);

CREATE INDEX IF NOT EXISTS ix_evento_planes_evento ON evento_planes (evento, fecha);

-- UNA fila por evento: el par (evento, fecha) sale de EVENTOS_TORNEO en
-- trading_proceso.py, para que las dos tablas hablen del mismo evento.
-- Responder de nuevo ACTUALIZA la fila (upsert sobre el UNIQUE).
CREATE TABLE IF NOT EXISTS evento_checklist (
    id             SERIAL PRIMARY KEY,
    evento         TEXT        NOT NULL,
    fecha          TIMESTAMPTZ NOT NULL,
    respuestas     BOOLEAN[]   NOT NULL,
    respondido_en  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evento_checklist_seis_respuestas CHECK (
        array_length(respuestas, 1) = 6),
    CONSTRAINT evento_checklist_unico UNIQUE (evento, fecha)
);

-- semana_inicio = el LUNES DE LA SEMANA QUE SE REVISA, la que ya pasó.
-- `meta` es la meta para la semana SIGUIENTE a esa: al revisar la semana del
-- 12-oct se guarda semana_inicio = 2026-10-12 y la meta rige para la semana
-- del 19-oct. La pantalla lo dice con esas mismas palabras.
CREATE TABLE IF NOT EXISTS trading_revision_semanal (
    id             SERIAL PRIMARY KEY,
    semana_inicio  DATE NOT NULL UNIQUE,
    meta           TEXT,
    nota           TEXT,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _verificar_destino(engine) -> None:
    """Confirma que se apunta a Railway SIN imprimir la cadena de conexión."""
    url = str(engine.url)
    if "altaria.proxy.rlwy.net" not in url and "railway" not in url:
        print("AVISO: DATABASE_URL no parece de Railway. Abortando por seguridad.")
        sys.exit(1)
    print(f"Destino verificado: base de producción en Railway (base '{engine.url.database}').")


def _informe(engine) -> None:
    with engine.connect() as conn:
        print("\n=== COLUMNAS NUEVAS EN trading_operaciones ===")
        presentes = {
            n: (t, nul) for n, t, nul in conn.execute(text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'trading_operaciones'")).fetchall()
        }
        for col, tipo in COLUMNAS_NUEVAS.items():
            if col in presentes:
                dato, nulable = presentes[col]
                marca = "OK " if nulable == "YES" else "OJO"
                print(f"  [{marca}] {col:18s} {dato:10s} nullable={nulable}")
            else:
                print(f"  [FALTA] {col}")

        print("\n=== TABLAS NUEVAS ===")
        tablas = {t for (t,) in conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )).fetchall()}
        for tabla in TABLAS_NUEVAS:
            if tabla in tablas:
                n_col = conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = :t"
                ), {"t": tabla}).scalar()
                n_filas = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
                print(f"  [OK ] {tabla:26s} columnas={n_col}  filas={n_filas}")
            else:
                print(f"  [FALTA] {tabla}")

        print("\n=== RESTRICCIONES ===")
        existentes = {c for (c,) in conn.execute(text(
            "SELECT conname FROM pg_constraint WHERE conname LIKE 'trading_%' "
            "OR conname LIKE 'evento_%'")).fetchall()}
        esperadas = list(RESTRICCIONES) + [
            "evento_planes_probabilidad_valida", "evento_planes_lotes_positivos",
            "evento_checklist_seis_respuestas", "evento_checklist_unico",
        ]
        for nombre in esperadas:
            print(f"  [{'OK ' if nombre in existentes else 'FALTA'}] {nombre}")


def main() -> None:
    engine = get_engine()
    _verificar_destino(engine)

    if "--solo-verificar" in sys.argv:
        _informe(engine)
        return

    with engine.begin() as conn:
        for col, tipo in COLUMNAS_NUEVAS.items():
            conn.execute(text(
                f"ALTER TABLE trading_operaciones ADD COLUMN IF NOT EXISTS {col} {tipo}"))
        for nombre, definicion in RESTRICCIONES.items():
            conn.execute(text(
                "DO $$ BEGIN "
                f"IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{nombre}') THEN "
                f"ALTER TABLE trading_operaciones ADD CONSTRAINT {nombre} {definicion}; "
                "END IF; END $$;"))
        conn.execute(text(DDL_TABLAS))
        print("\nDDL aplicado dentro de una sola transacción.")

    _informe(engine)


if __name__ == "__main__":
    main()
