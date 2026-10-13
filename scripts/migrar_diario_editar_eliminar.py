"""Migración aditiva: papelera y marca de edición en el diario.

QUÉ AGREGA, las dos NULLABLE y a trading_operaciones solamente:

    eliminado_en  TIMESTAMPTZ NULL   cuándo se mandó a la papelera
    editado_en    TIMESTAMPTZ NULL   cuándo se corrigió por última vez

POR QUÉ UNA MARCA Y NO UN DELETE. Un borrado físico no se puede deshacer, y
el diario es el registro de lo que pasó: si se borra una fila por error, se
pierde la operación y con ella la estadística. Con la marca, la fila sigue
ahí, deja de contar en todas las vistas, y se puede restaurar.

NULL significa "no eliminada" y "nunca editada". Las filas anteriores quedan
en NULL sin que haya que tocarlas.

ADITIVA: solo agrega columnas nullable. No borra, no reescribe y no cambia
el tipo de nada.

IDEMPOTENTE: ADD COLUMN IF NOT EXISTS. Correrla dos veces no rompe nada.

Todo va en UNA transacción.

Uso (con el .env apuntando a Railway):
    python scripts/migrar_diario_editar_eliminar.py --ensayo
    python scripts/migrar_diario_editar_eliminar.py --solo-verificar
    python scripts/migrar_diario_editar_eliminar.py
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from sqlalchemy import text

from models import get_engine

TABLA = "trading_operaciones"
COLUMNAS = {
    "eliminado_en": "TIMESTAMPTZ",
    "editado_en": "TIMESTAMPTZ",
}

DDL = [
    f"ALTER TABLE {TABLA} ADD COLUMN IF NOT EXISTS {col} {tipo} NULL"
    for col, tipo in COLUMNAS.items()
]


def _verificar_destino(engine) -> None:
    """Confirma Railway SIN imprimir la cadena de conexión."""
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
        print(f"\n=== COLUMNAS NUEVAS EN {TABLA} ===")
        for col in COLUMNAS:
            if col in presentes:
                tipo, nulable = presentes[col]
                marca = "OK " if nulable == "YES" else "OJO"
                print(f"  [{marca}] {col:14s} {tipo:28s} nullable={nulable}")
            else:
                print(f"  [FALTA] {col}")
        n = conn.execute(text(f"SELECT count(*) FROM {TABLA}")).scalar()
        print(f"\n  filas en {TABLA}: {n} (la migración no agrega ni quita filas)")
        print(f"  total de columnas: {len(presentes)}")


def ensayo(engine) -> None:
    """Corre el DDL en una transacción y la REVIERTE.

    Es la prueba previa: se ejecuta exactamente el mismo SQL contra el mismo
    motor y el mismo esquema, se comprueba que las columnas quedan, y se
    deshace. Más fiable que una base local distinta, que podría no reproducir
    el tipo TIMESTAMPTZ ni la versión de PostgreSQL.
    """
    print("\n--- ENSAYO: se aplica y se revierte ---")
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            antes = set(_columnas(conn))
            for sentencia in DDL:
                conn.execute(text(sentencia))
            despues = set(_columnas(conn))
            nuevas = despues - antes
            print(f"  columnas antes: {len(antes)}  despues: {len(despues)}")
            print(f"  agregadas en el ensayo: {sorted(nuevas) if nuevas else 'ninguna (ya existían)'}")
            # y otra vez, para probar que es idempotente
            for sentencia in DDL:
                conn.execute(text(sentencia))
            print(f"  segunda pasada sin error: idempotente")
            n = conn.execute(text(f"SELECT count(*) FROM {TABLA}")).scalar()
            print(f"  filas durante el ensayo: {n}")
        finally:
            trans.rollback()
            print("  ROLLBACK: la base quedó como estaba")
    with engine.connect() as conn:
        quedaron = set(_columnas(conn)) & set(COLUMNAS)
        print(f"  columnas nuevas tras el rollback: "
              f"{sorted(quedaron) if quedaron else 'ninguna, como corresponde'}")


def migrar(engine) -> None:
    with engine.begin() as conn:
        print("\n--- aplicando ---")
        for sentencia in DDL:
            conn.execute(text(sentencia))
            print(f"  {sentencia}")
    print("\nMigración aplicada en una sola transacción.")


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
    migrar(engine)
    _informe(engine)


if __name__ == "__main__":
    main()
