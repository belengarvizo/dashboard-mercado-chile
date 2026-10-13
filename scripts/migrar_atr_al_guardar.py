"""Migración aditiva: guarda el ATR que tenía el par al registrar la operación.

PARA QUÉ. El ATR de un par cambia todos los días. Si solo se guarda la
operación, después no se puede responder "¿qué parte de mis operaciones tuvo
el stop dentro del ruido y cómo les fue?", porque el ATR de hoy ya no es el
de aquel día. Guardándolo en la fila, la pregunta se puede contestar.

Una columna NUMERIC NULL: NULL en las filas anteriores, que no se tocan.

ADITIVA E IDEMPOTENTE: ADD COLUMN IF NOT EXISTS, en una transacción.

Uso (con el .env apuntando a Railway):
    python scripts/migrar_atr_al_guardar.py --ensayo
    python scripts/migrar_atr_al_guardar.py --solo-verificar
    python scripts/migrar_atr_al_guardar.py
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from sqlalchemy import text

from models import get_engine

TABLA = "trading_operaciones"
COLUMNA = "atr_al_guardar"
# NUMERIC sin precisión fija: el ATR de EURUSD vale 0,0055 y el de USDCLP
# vale 7,5. Una escala fija dejaría a uno de los dos sin dígitos útiles.
DDL = f"ALTER TABLE {TABLA} ADD COLUMN IF NOT EXISTS {COLUMNA} NUMERIC NULL"


def _verificar_destino(engine) -> None:
    url = str(engine.url)
    if "railway" not in url and "rlwy.net" not in url:
        print("AVISO: DATABASE_URL no parece de Railway. Abortando por seguridad.")
        sys.exit(1)
    print(f"Destino verificado: base de producción en Railway "
          f"(base '{engine.url.database}').")


def _columnas(conn) -> dict:
    return {
        n: (t, nul) for n, t, nul in conn.execute(text(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name = :t"), {"t": TABLA}).fetchall()
    }


def _informe(engine) -> None:
    with engine.connect() as conn:
        presentes = _columnas(conn)
        print(f"\n=== {COLUMNA} EN {TABLA} ===")
        if COLUMNA in presentes:
            tipo, nulable = presentes[COLUMNA]
            print(f"  [{'OK ' if nulable == 'YES' else 'OJO'}] {COLUMNA:16s} "
                  f"{tipo:12s} nullable={nulable}")
        else:
            print(f"  [FALTA] {COLUMNA}")
        n = conn.execute(text(f"SELECT count(*) FROM {TABLA}")).scalar()
        con_valor = conn.execute(text(
            f"SELECT count({COLUMNA}) FROM {TABLA}")).scalar() if COLUMNA in presentes else 0
        print(f"\n  filas: {n}  con ATR guardado: {con_valor}")
        print(f"  total de columnas: {len(presentes)}")


def ensayo(engine) -> None:
    """Aplica el DDL en una transacción y la revierte."""
    print("\n--- ENSAYO: se aplica y se revierte ---")
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            antes = set(_columnas(conn))
            conn.execute(text(DDL))
            despues = set(_columnas(conn))
            print(f"  columnas antes: {len(antes)}  despues: {len(despues)}")
            print(f"  agregada: {sorted(despues - antes) or 'ninguna (ya existía)'}")
            conn.execute(text(DDL))
            print("  segunda pasada sin error: idempotente")
            n = conn.execute(text(f"SELECT count(*) FROM {TABLA}")).scalar()
            nulos = conn.execute(text(
                f"SELECT count(*) FROM {TABLA} WHERE {COLUMNA} IS NOT NULL")).scalar()
            print(f"  filas: {n}  con valor distinto de NULL: {nulos} "
                  f"(debe ser 0: no toca filas existentes)")
        finally:
            trans.rollback()
            print("  ROLLBACK: la base quedó como estaba")
    with engine.connect() as conn:
        print(f"  {COLUMNA} tras el rollback: "
              f"{'sigue' if COLUMNA in _columnas(conn) else 'no está, como corresponde'}")


def main() -> None:
    engine = get_engine()
    _verificar_destino(engine)
    if "--ensayo" in sys.argv:
        ensayo(engine)
        return
    if "--solo-verificar" in sys.argv:
        print("\n(modo solo verificar: no se escribe nada)")
        _informe(engine)
        return
    with engine.begin() as conn:
        conn.execute(text(DDL))
        print(f"\n  {DDL}")
    print("\nMigración aplicada en una sola transacción.")
    _informe(engine)


if __name__ == "__main__":
    main()
