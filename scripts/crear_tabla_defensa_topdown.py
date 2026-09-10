"""Migración puntual: crea la tabla `defensa_topdown_respuestas` en la BD de
producción (Railway). El proyecto no usa Alembic; una tabla nueva se crea con
create_all (aditivo — no toca las tablas existentes). Idempotente: si la
tabla ya existe, no hace nada (checkfirst=True).

Uso (con el .env apuntando a Railway):
    python scripts/crear_tabla_defensa_topdown.py
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from sqlalchemy import inspect, text
from models import get_engine, DefensaTopdownRespuesta, DefensaTopdownPrediccion

# Columnas de resolución CONGELADA añadidas después de la creación inicial de
# defensa_topdown_predicciones. `__table__.create(checkfirst=True)` no altera
# una tabla existente, así que estas se agregan con ADD COLUMN IF NOT EXISTS
# (idempotente, no destructivo).
COLUMNAS_RESOLUCION = {
    "precio_verificacion": "NUMERIC",
    "fecha_verificacion": "TIMESTAMP",
    "estado_resuelto": "VARCHAR",
    "detalle_resuelto": "TEXT",
    "error_pp": "NUMERIC",
    "verificado_en": "TIMESTAMP",
}

# Rediseño: cada pregunta guarda un widget de decisión estructurado
# (decision_valor) + una nota corta (nota), en vez de los 3 textos largos.
COLUMNAS_DECISION = {
    "decision_valor": "TEXT",
    "nota": "TEXT",
}


def main() -> None:
    engine = get_engine()
    url = str(engine.url)
    if "altaria.proxy.rlwy.net" not in url and "railway" not in url:
        print(f"AVISO: DATABASE_URL no parece de Railway ({url!r}). Abortando por seguridad.")
        sys.exit(1)

    DefensaTopdownRespuesta.__table__.create(engine, checkfirst=True)
    DefensaTopdownPrediccion.__table__.create(engine, checkfirst=True)
    with engine.begin() as conn:
        for col, tipo in COLUMNAS_RESOLUCION.items():
            conn.execute(text(f"ALTER TABLE defensa_topdown_predicciones ADD COLUMN IF NOT EXISTS {col} {tipo}"))
        for col, tipo in COLUMNAS_DECISION.items():
            conn.execute(text(f"ALTER TABLE defensa_topdown_respuestas ADD COLUMN IF NOT EXISTS {col} {tipo}"))

    insp = inspect(engine)
    esperado = {
        "defensa_topdown_respuestas": {
            "id", "pregunta_id", "ticker", "respuesta_i", "respuesta_ii", "respuesta_iii",
            "decision_valor", "nota", "fecha",
        },
        "defensa_topdown_predicciones": {
            "id", "pregunta_id", "ticker", "texto", "tipo", "valor_objetivo",
            "horizonte_dias", "precio_base", "fecha_hecha",
            "precio_verificacion", "fecha_verificacion", "estado_resuelto",
            "detalle_resuelto", "error_pp", "verificado_en",
        },
    }
    ok = True
    for tabla, cols_esperadas in esperado.items():
        cols = insp.get_columns(tabla)
        print(f"Columnas de {tabla}:")
        for c in cols:
            print(f"  - {c['name']}: {c['type']} (nullable={c['nullable']})")
        if not cols_esperadas.issubset({c["name"] for c in cols}):
            print(f"ERROR: faltan columnas en {tabla} tras el create.")
            ok = False
    if ok:
        print("OK: las tablas de Defensa Top-Down están listas.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
