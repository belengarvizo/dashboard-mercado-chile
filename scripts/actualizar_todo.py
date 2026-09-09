"""
Corre las cuatro actualizaciones diarias (series del BCCh, precios de
acciones del IPSA, titulares de noticias, y el resumen diario generado
por IA) en un solo paso. Pensado para usarse como único comando del cron
job de Railway.

Cada paso corre en su propio try/except: si uno falla, los siguientes
igual se intentan (ej. si noticias falla, el brief se genera igual con
los titulares que ya había en la base, en vez de no generarse). Al final
se imprime un resumen con el estado de cada paso.

Código de salida (lo que Railway pinta verde/rojo):
  - Falla un paso CRÍTICO (noticias, BCCh, acciones) -> exit 1. Datos
    desactualizados rompen el dashboard: hay que ir a mirar.
  - Falla solo un paso NO crítico (el brief): normalmente exit 0 (Railway
    verde) + línea "CORRIDA PARCIAL" + el detalle queda en la tabla
    errores_actualizacion. El dashboard muestra el brief del día anterior,
    que es cosmético. PERO si ese mismo paso (`fuente`) acumula fallas en
    más de MAX_FALLAS_NO_CRITICAS_TOLERADAS corridas dentro de
    HORAS_VENTANA_RACHA, se escala a exit 1 -> Railway se pone rojo cuando
    el problema deja de ser un bache puntual y se vuelve recurrente (para
    que no quede invisible detrás de un semáforo siempre verde).

Orden: noticias y brief van PRIMERO, antes de los pulls de series del BCCh
y precios de acciones. Esos dos pulls bajan la historia completa de cada
serie/ticker en cada corrida y pueden tardar >30 min y ser matados por el
límite de ejecución del contenedor (pasó el 2026-09-02) — poniéndolos al
final, un kill del pull de acciones ya no se lleva por delante los
titulares ni el resumen. El costo: el brief se arma con los indicadores de
la corrida anterior (~1 día de atraso) en vez de los del mismo día; para
un brief premercado de las 10:00 eso es aceptable (aún no hay cierre de
hoy) y los titulares sí quedan frescos. Revisar este orden cuando los
pulls pasen a ser incrementales y una corrida vuelva a durar pocos
minutos.
"""

import os
import sys
import traceback
from collections import namedtuple
from datetime import datetime, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from models import get_session, ErrorActualizacion
from scripts.actualizar_bcch import actualizar_todas_las_series
from scripts.actualizar_acciones import actualizar_todas_las_acciones
from scripts.actualizar_noticias import actualizar_todas_las_noticias
from scripts.generar_brief import generar_brief_diario

# `fuente` es la clave que el paso usa al registrar en errores_actualizacion
# (solo generar_brief lo hace hoy; si se agrega otro paso no crítico, debe
# registrar sus fallas ahí para que la racha lo cuente).
Paso = namedtuple("Paso", "nombre funcion critico fuente")
Resultado = namedtuple("Resultado", "paso ok error")

PASOS = [
    Paso("Titulares de noticias", actualizar_todas_las_noticias, True, "noticias"),
    Paso("Resumen diario (IA)", generar_brief_diario, False, "brief"),
    Paso("Series del BCCh", actualizar_todas_las_series, True, "bcch"),
    Paso("Acciones del IPSA", actualizar_todas_las_acciones, True, "yfinance"),
]

# Ventana para contar la racha de fallas de un paso no crítico. El cron
# corre 1 vez al día (14:00 UTC), así que ~40h cubre "hoy y ayer".
HORAS_VENTANA_RACHA = 40
# Cuántas fallas consecutivas de un paso no crítico se toleran como exit 0.
# 1 = un bache puntual pasa; a la 2ª falla dentro de la ventana, exit 1.
MAX_FALLAS_NO_CRITICAS_TOLERADAS = 1


def _racha_de_fallas(fuente: str) -> int:
    """Cuántas filas tiene `fuente` en errores_actualizacion en las últimas
    HORAS_VENTANA_RACHA horas — incluye la falla de esta corrida, que el paso
    ya registró antes de re-lanzar. Best-effort: si la consulta falla,
    devuelve 0 (no escala) para no poner rojo el semáforo por un problema de
    lectura."""
    try:
        s = get_session()
        try:
            corte = datetime.now() - timedelta(hours=HORAS_VENTANA_RACHA)
            return (
                s.query(ErrorActualizacion)
                .filter(
                    ErrorActualizacion.fuente == fuente,
                    ErrorActualizacion.ocurrido_en >= corte,
                )
                .count()
            )
        finally:
            s.close()
    except Exception as e:
        print(f"  (no se pudo consultar la racha de fallas de '{fuente}': {e})")
        return 0


def _decidir_exit_code(resultados, racha_por_fuente: dict) -> tuple[int, list[str]]:
    """Función pura (para poder testearla sin BD): dado el resultado de cada
    paso y la racha de fallas por fuente, devuelve (exit_code, mensajes)."""
    mensajes = []
    if any(not r.ok and r.paso.critico for r in resultados):
        mensajes.append("Al menos un paso CRÍTICO falló - la corrida se marca como fallida.")
        return 1, mensajes

    exit_code = 0
    for r in resultados:
        if r.ok or r.paso.critico:
            continue
        racha = racha_por_fuente.get(r.paso.fuente, 0)
        if racha > MAX_FALLAS_NO_CRITICAS_TOLERADAS:
            mensajes.append(
                f"'{r.paso.nombre}' (no crítico) lleva {racha} fallas en {HORAS_VENTANA_RACHA}h "
                "- ya no es un bache puntual, se escala a fallo."
            )
            exit_code = 1
        else:
            mensajes.append(
                f"CORRIDA PARCIAL: '{r.paso.nombre}' (no crítico) falló, pero es un bache "
                f"puntual ({racha} falla(s) en {HORAS_VENTANA_RACHA}h). Detalle en "
                f"errores_actualizacion (fuente='{r.paso.fuente}')."
            )
    return exit_code, mensajes


def actualizar_todo():
    resultados = []

    for paso in PASOS:
        print(f"\n== Actualizando {paso.nombre.lower()} ==")
        try:
            paso.funcion()
            resultados.append(Resultado(paso, True, None))
        except Exception as e:
            print(f"ERROR en '{paso.nombre}': {e}")
            traceback.print_exc()
            resultados.append(Resultado(paso, False, str(e)))

    print("\n== Resumen de la corrida ==")
    for r in resultados:
        print(f"  {'OK   ' if r.ok else 'FALLO'} {r.paso.nombre}" + ("" if r.ok else f": {r.error}"))

    racha_por_fuente = {
        r.paso.fuente: _racha_de_fallas(r.paso.fuente)
        for r in resultados if not r.ok and not r.paso.critico
    }
    exit_code, mensajes = _decidir_exit_code(resultados, racha_por_fuente)
    for m in mensajes:
        print(f"\n{m}")

    if exit_code != 0:
        sys.exit(exit_code)
    if not any(not r.ok for r in resultados):
        print("\nTodos los pasos se completaron correctamente.")


if __name__ == "__main__":
    actualizar_todo()
