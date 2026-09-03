"""Migración puntual de datos: renombra la serie del cobre en las filas ya
guardadas de ``series_macro``.

Contexto: la etiqueta de la serie ``F019.PPB.PRE.100.D`` decía
"Precio del cobre (USD/oz troy)", pero el valor guardado (~6,5 en 2026) está en
US$/libra (confirmado contra cobre LME en US$/tonelada y COMEX en centavos/libra,
ambos convergiendo en ~6,5-6,6). El código del repo ya se corrigió a
"Precio del cobre (USD/lb)"; este script alinea las filas históricas para que
coincidan con la nueva etiqueta y no queden dos nombres para la misma serie.

Es idempotente: si ya no hay filas con el nombre viejo, no hace nada.

Uso:
    python scripts/migrar_label_cobre.py

Requiere ``DATABASE_URL`` en ``.env`` (la conexión a PostgreSQL de Railway/Neon).
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from models import get_engine

CODIGO_SERIE = "F019.PPB.PRE.100.D"
NOMBRE_VIEJO = "Precio del cobre (USD/oz troy)"
NOMBRE_NUEVO = "Precio del cobre (USD/lb)"


def _conteo_por_nombre(conn):
    filas = conn.execute(
        text(
            "SELECT nombre, COUNT(*) AS n FROM series_macro "
            "WHERE codigo_serie = :codigo GROUP BY nombre ORDER BY nombre"
        ),
        {"codigo": CODIGO_SERIE},
    ).fetchall()
    return [(nombre, n) for nombre, n in filas]


def main():
    engine = get_engine()

    with engine.connect() as conn:
        antes = _conteo_por_nombre(conn)
    print("Antes de la migración:")
    for nombre, n in antes:
        print(f"  {nombre!r}: {n} filas")

    with engine.begin() as conn:
        resultado = conn.execute(
            text(
                "UPDATE series_macro SET nombre = :nuevo "
                "WHERE codigo_serie = :codigo AND nombre = :viejo"
            ),
            {"nuevo": NOMBRE_NUEVO, "codigo": CODIGO_SERIE, "viejo": NOMBRE_VIEJO},
        )
    print(f"\nFilas actualizadas: {resultado.rowcount}")

    with engine.connect() as conn:
        despues = _conteo_por_nombre(conn)
    print("\nDespués de la migración:")
    for nombre, n in despues:
        print(f"  {nombre!r}: {n} filas")

    nombres_finales = {nombre for nombre, _ in despues}
    if NOMBRE_VIEJO in nombres_finales:
        print(
            f"\nADVERTENCIA: todavía quedan filas con {NOMBRE_VIEJO!r}. "
            "La migración no se completó."
        )
    else:
        print("\nOK: no quedan filas con la etiqueta vieja.")


if __name__ == "__main__":
    main()
