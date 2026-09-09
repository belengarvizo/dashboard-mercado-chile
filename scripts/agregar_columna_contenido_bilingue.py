"""Migración puntual: agrega la columna `contenido_bilingue` (TEXT, nullable)
a la tabla `brief_diario` en la BD de producción (Railway).

El proyecto no usa Alembic; las tablas se crean con create_all (aditivo, no
altera columnas), así que una columna nueva sobre una tabla existente hay que
agregarla a mano una vez. Idempotente: si la columna ya existe, no hace nada.

Uso (con el .env apuntando a Railway):
    python scripts/agregar_columna_contenido_bilingue.py
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from sqlalchemy import text
from models import get_engine

DDL = "ALTER TABLE brief_diario ADD COLUMN IF NOT EXISTS contenido_bilingue TEXT"


def main() -> None:
    engine = get_engine()
    url = str(engine.url)
    if "altaria.proxy.rlwy.net" not in url and "railway" not in url:
        print(f"AVISO: DATABASE_URL no parece de Railway ({url!r}). Abortando por seguridad.")
        sys.exit(1)

    with engine.begin() as conn:
        conn.execute(text(DDL))
        cols = conn.execute(text(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'brief_diario' ORDER BY ordinal_position"
        )).fetchall()

    print("Columnas de brief_diario ahora:")
    for nombre, tipo, nullable in cols:
        print(f"  - {nombre}: {tipo} (nullable={nullable})")
    if any(c[0] == "contenido_bilingue" for c in cols):
        print("OK: la columna contenido_bilingue está presente.")
    else:
        print("ERROR: la columna contenido_bilingue NO aparece tras el ALTER.")
        sys.exit(1)


if __name__ == "__main__":
    main()
