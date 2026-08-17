"""
Corre las dos actualizaciones diarias (series del BCCh y precios de
acciones del IPSA) en un solo paso. Pensado para usarse como único
comando del cron job de Railway.
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from scripts.actualizar_bcch import actualizar_todas_las_series
from scripts.actualizar_acciones import actualizar_todas_las_acciones


def actualizar_todo():
    print("== Actualizando series del BCCh ==")
    actualizar_todas_las_series()

    print("\n== Actualizando acciones del IPSA ==")
    actualizar_todas_las_acciones()


if __name__ == "__main__":
    actualizar_todo()
