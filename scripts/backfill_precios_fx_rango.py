"""Backfill del último año de máximos y mínimos de los pares de divisas.

QUÉ HACE. Baja un año de cada uno de los 14 tickers FX desde la MISMA
fuente y con la MISMA llamada que usa el cron (yfinance, `Ticker.history`),
y los guarda en precios_fx_rango con la misma función que usará el cron de
ahora en adelante. Así el histórico y lo que se agregue cada día salen del
mismo camino: si hubiera una diferencia, estaría en los dos lados.

QUÉ NO HACE. No toca precios_acciones. Ni la lee para escribir, ni le
agrega columnas, ni le cambia una fila.

IDEMPOTENTE: cada fila entra con ON CONFLICT (ticker, fecha) DO UPDATE, así
que correrlo dos veces deja el mismo resultado. Se puede repetir sin miedo.

LA VELA DEL DÍA EN CURSO SE DESCARTA. Yahoo entrega una fila para hoy con
el máximo y el mínimo de lo que va corrido de la sesión; guardarla sería
contar medio día como una rueda completa y subestimar el ATR justo en el
dato más reciente.

Uso (con el .env apuntando a Railway):
    python scripts/backfill_precios_fx_rango.py --solo-verificar
    python scripts/backfill_precios_fx_rango.py
    python scripts/backfill_precios_fx_rango.py --periodo 2y
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from datetime import date

from sqlalchemy import text

from catalogo_instrumentos import TICKERS_YAHOO_FASE_1
from models import get_session
from scripts.actualizar_acciones import descargar_ticker, guardar_rango_fx

PERIODO_POR_DEFECTO = "1y"


def _verificar_destino(session) -> None:
    """Confirma Railway SIN imprimir la cadena de conexión."""
    url = str(session.get_bind().url)
    if "railway" not in url and "rlwy.net" not in url:
        print("AVISO: DATABASE_URL no parece de Railway. Abortando por seguridad.")
        sys.exit(1)
    print("Destino verificado: base de producción en Railway.")


def _huella_precios_acciones(session):
    """Conteo y columnas de precios_acciones, para probar que no se tocó."""
    n = session.execute(text("SELECT count(*) FROM precios_acciones")).scalar()
    c = session.execute(text(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name='precios_acciones'")).scalar()
    return n, c


def _informe(session) -> None:
    filas = session.execute(text(
        "SELECT ticker, count(*) n, min(fecha), max(fecha) "
        "FROM precios_fx_rango GROUP BY ticker ORDER BY ticker")).fetchall()
    print("\n=== CONTENIDO DE precios_fx_rango ===")
    if not filas:
        print("  (vacía)")
        return
    print(f"  {'ticker':<10} {'ruedas':>7}  {'desde':<12} {'hasta':<12}")
    for ticker, n, desde, hasta in filas:
        print(f"  {ticker:<10} {n:>7}  {str(desde):<12} {str(hasta):<12}")
    total = sum(f[1] for f in filas)
    print(f"  {len(filas)} tickers, {total} filas")


def correr(periodo: str = PERIODO_POR_DEFECTO, solo_verificar: bool = False) -> None:
    session = get_session()
    _verificar_destino(session)
    antes = _huella_precios_acciones(session)
    print(f"precios_acciones ANTES: {antes[0]} filas, {antes[1]} columnas")

    if solo_verificar:
        print("\n(modo solo verificar: no se escribe nada)")
        _informe(session)
        session.close()
        return

    hoy = date.today()
    print(f"\nBajando {periodo} de {len(TICKERS_YAHOO_FASE_1)} pares "
          f"(hoy = {hoy}, la vela de hoy se descarta)...\n")
    total_guardadas = total_incompletas = total_fuera = 0
    fallidos = []

    for ticker in TICKERS_YAHOO_FASE_1:
        try:
            historico = descargar_ticker(ticker, periodo)
            guardadas, incompletas, fuera = guardar_rango_fx(
                session, ticker, historico, hoy)
            session.commit()
            total_guardadas += guardadas
            total_incompletas += incompletas
            total_fuera += fuera
            extra = ""
            if incompletas:
                extra += f"  ({incompletas} sin cerrar descartada/s)"
            if fuera:
                extra += f"  ({fuera} con el cierre fuera del rango)"
            print(f"  {ticker:<10} {guardadas:>4} ruedas{extra}")
        except Exception as e:
            session.rollback()
            fallidos.append((ticker, str(e)[:120]))
            print(f"  {ticker:<10} [!] falló: {str(e)[:100]}")

    print(f"\nTotal: {total_guardadas} ruedas guardadas, "
          f"{total_incompletas} sin cerrar descartadas, "
          f"{total_fuera} guardadas con el cierre fuera de su rango.")
    if fallidos:
        print("Tickers que fallaron:")
        for t, e in fallidos:
            print(f"  {t}: {e}")

    _informe(session)

    despues = _huella_precios_acciones(session)
    print(f"\nprecios_acciones DESPUÉS: {despues[0]} filas, {despues[1]} columnas")
    print("  " + ("SIN CAMBIOS" if despues == antes else "*** CAMBIÓ: REVISAR ***"))
    session.close()


def main() -> None:
    periodo = PERIODO_POR_DEFECTO
    if "--periodo" in sys.argv:
        periodo = sys.argv[sys.argv.index("--periodo") + 1]
    correr(periodo, solo_verificar="--solo-verificar" in sys.argv)


if __name__ == "__main__":
    main()
