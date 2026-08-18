"""
Corre las cuatro actualizaciones diarias (series del BCCh, precios de
acciones del IPSA, titulares de noticias, y el resumen diario generado
por IA) en un solo paso. Pensado para usarse como único comando del cron
job de Railway.

Cada paso corre en su propio try/except: si uno falla, los siguientes
igual se intentan (ej. si noticias falla, el brief se genera igual con
los titulares que ya había en la base, en vez de no generarse). Al final
se imprime un resumen con el estado de cada paso, y el script termina con
código de salida distinto de cero si alguno falló — para que una falla
parcial quede visible en el log de esa corrida, no se descubra recién al
otro día por un dato atrasado.
"""

import os
import sys
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from scripts.actualizar_bcch import actualizar_todas_las_series
from scripts.actualizar_acciones import actualizar_todas_las_acciones
from scripts.actualizar_noticias import actualizar_todas_las_noticias
from scripts.generar_brief import generar_brief_diario

PASOS = [
    ("Series del BCCh", actualizar_todas_las_series),
    ("Acciones del IPSA", actualizar_todas_las_acciones),
    ("Titulares de noticias", actualizar_todas_las_noticias),
    ("Resumen diario (IA)", generar_brief_diario),
]


def actualizar_todo():
    resultados = []

    for nombre, funcion in PASOS:
        print(f"\n== Actualizando {nombre.lower()} ==")
        try:
            funcion()
            resultados.append((nombre, True, None))
        except Exception as e:
            print(f"ERROR en '{nombre}': {e}")
            traceback.print_exc()
            resultados.append((nombre, False, str(e)))

    print("\n== Resumen de la corrida ==")
    hubo_error = False
    for nombre, ok, error in resultados:
        if ok:
            print(f"  OK   {nombre}")
        else:
            print(f"  FALLO {nombre}: {error}")
            hubo_error = True

    if hubo_error:
        print("\nAl menos un paso falló - revisa el detalle de arriba.")
        sys.exit(1)

    print("\nTodos los pasos se completaron correctamente.")


if __name__ == "__main__":
    actualizar_todo()
