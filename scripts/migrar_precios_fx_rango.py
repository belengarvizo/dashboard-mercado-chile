"""Migración aditiva: tabla precios_fx_rango, el máximo y el mínimo diarios
de los pares de divisas.

PARA QUÉ. El ATR necesita el rango verdadero de cada rueda, y el rango
necesita máximo y mínimo. Yahoo los entrega, pero el cron de precios guarda
solo el cierre y el volumen: los descarta en el bucle de guardar_historico.
Esta tabla los conserva.

POR QUÉ UNA TABLA NUEVA Y NO COLUMNAS EN precios_acciones. Esa tabla tiene
~216.000 filas de 166 tickers, de los cuales solo 14 son divisas. Agregarle
dos columnas que quedarían nulas en el 92% de las filas, y tocar el camino
de escritura que usan todos los tickers, es mucho más riesgo que una tabla
aparte de ~3.600 filas. precios_acciones NO se toca.

POR QUÉ SE GUARDA `cierre` Y NO `cierre_previo`. El cierre previo es la fila
anterior del mismo par, así que guardarlo sería duplicar un dato que se
puede derivar. Duplicado puede quedar inconsistente: si un día falta, o si
el backfill entra desordenado, el rango verdadero se calcularía contra un
cierre que no corresponde. Derivándolo al leer, además, se pueden detectar
los huecos.

ADITIVA: solo crea una tabla nueva. No borra, no reescribe y no cambia el
tipo de nada existente.

IDEMPOTENTE: CREATE TABLE IF NOT EXISTS y las restricciones dentro de un
bloque DO que primero consulta pg_constraint (ADD CONSTRAINT no tiene
IF NOT EXISTS). Se puede correr dos veces sin romper nada.

Todo va en UNA transacción.

Uso (con el .env apuntando a Railway):
    python scripts/migrar_precios_fx_rango.py
    python scripts/migrar_precios_fx_rango.py --solo-verificar
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from sqlalchemy import text

from models import get_engine

TABLA = "precios_fx_rango"

DDL = """
-- Máximo, mínimo y cierre de cada rueda CERRADA de los pares de divisas.
-- Una fila por (ticker, fecha). El cierre previo se deriva de la fila
-- anterior al leer, no se guarda.
CREATE TABLE IF NOT EXISTS precios_fx_rango (
    id              SERIAL PRIMARY KEY,
    ticker          VARCHAR(20) NOT NULL,
    fecha           DATE        NOT NULL,
    maximo          NUMERIC(18,8) NOT NULL,
    minimo          NUMERIC(18,8) NOT NULL,
    cierre          NUMERIC(18,8) NOT NULL,
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# ADD CONSTRAINT no admite IF NOT EXISTS, así que cada una se agrega solo si
# no está ya en pg_constraint.
RESTRICCIONES = {
    "precios_fx_rango_unico":
        "ALTER TABLE precios_fx_rango ADD CONSTRAINT precios_fx_rango_unico "
        "UNIQUE (ticker, fecha)",
    # Invariante por definición: si Yahoo alguna vez devolviera un máximo
    # menor que el mínimo, el dato está roto y es mejor enterarse.
    "precios_fx_rango_max_mayor_min":
        "ALTER TABLE precios_fx_rango ADD CONSTRAINT precios_fx_rango_max_mayor_min "
        "CHECK (maximo >= minimo)",
}

# El cierre fuera de [minimo, maximo] NO va como restricción de la base a
# propósito: sería una restricción que puede fallar en producción y cortar el
# cron por un dato raro de la fuente. Se filtra al guardar, con aviso.


def _verificar_destino(engine) -> None:
    """Confirma que se apunta a Railway SIN imprimir la cadena de conexión."""
    url = str(engine.url)
    if "railway" not in url and "rlwy.net" not in url:
        print("AVISO: DATABASE_URL no parece de Railway. Abortando por seguridad.")
        sys.exit(1)
    print(f"Destino verificado: base de producción en Railway "
          f"(base '{engine.url.database}').")


def _informe(engine) -> None:
    with engine.connect() as conn:
        existe = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:t)"),
            {"t": TABLA}).scalar()
        print(f"\n=== TABLA {TABLA} ===")
        if not existe:
            print("  [FALTA] la tabla no existe")
            return

        columnas = conn.execute(text(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name=:t ORDER BY ordinal_position"), {"t": TABLA}).fetchall()
        for nombre, tipo, nulable in columnas:
            print(f"  [OK ] {nombre:16s} {tipo:28s} nullable={nulable}")

        print("\n=== RESTRICCIONES ===")
        presentes = {c for (c,) in conn.execute(text(
            "SELECT conname FROM pg_constraint WHERE conname LIKE 'precios_fx_rango%'"
        )).fetchall()}
        for nombre in RESTRICCIONES:
            print(f"  [{'OK ' if nombre in presentes else 'FALTA'}] {nombre}")

        n, tickers, desde, hasta = conn.execute(text(
            f"SELECT count(*), count(DISTINCT ticker), min(fecha), max(fecha) "
            f"FROM {TABLA}")).fetchone()
        print(f"\n=== CONTENIDO ===")
        print(f"  filas={n}  tickers={tickers}  rango={desde} -> {hasta}")

        print("\n=== precios_acciones (NO debe haber cambiado) ===")
        n_acc = conn.execute(text("SELECT count(*) FROM precios_acciones")).scalar()
        cols_acc = conn.execute(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='precios_acciones'")).scalar()
        print(f"  filas={n_acc}  columnas={cols_acc}")


def migrar(engine) -> None:
    with engine.begin() as conn:
        print("\n--- creando la tabla ---")
        conn.execute(text(DDL))
        print(f"  CREATE TABLE IF NOT EXISTS {TABLA}")

        print("--- restricciones ---")
        for nombre, sentencia in RESTRICCIONES.items():
            conn.execute(text(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = '{nombre}'
                    ) THEN
                        {sentencia};
                    END IF;
                END $$;
            """))
            print(f"  {nombre}")
    print("\nMigración aplicada en una sola transacción.")


def main() -> None:
    engine = get_engine()
    _verificar_destino(engine)
    if "--solo-verificar" in sys.argv:
        print("\n(modo solo verificar: no se escribe nada)")
        _informe(engine)
        return
    migrar(engine)
    _informe(engine)


if __name__ == "__main__":
    main()
