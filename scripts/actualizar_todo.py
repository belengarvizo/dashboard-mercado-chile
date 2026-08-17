"""
Corre las cuatro actualizaciones diarias (series del BCCh, precios de
acciones del IPSA, titulares de noticias, y el resumen diario generado
por IA) en un solo paso. Pensado para usarse como único comando del cron
job de Railway.
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from scripts.actualizar_bcch import actualizar_todas_las_series
from scripts.actualizar_acciones import actualizar_todas_las_acciones
from scripts.actualizar_noticias import actualizar_todas_las_noticias
from scripts.generar_brief import generar_brief_diario


def actualizar_todo():
    print("== Actualizando series del BCCh ==")
    actualizar_todas_las_series()

    print("\n== Actualizando acciones del IPSA ==")
    actualizar_todas_las_acciones()

    print("\n== Actualizando titulares de noticias ==")
    actualizar_todas_las_noticias()

    print("\n== Generando resumen diario (IA) ==")
    generar_brief_diario()


if __name__ == "__main__":
    actualizar_todo()
