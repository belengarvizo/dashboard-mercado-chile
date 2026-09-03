"""
Descarga precios históricos de acciones vía Yahoo Finance y los guarda
en la base de datos: las 30 acciones del IPSA, las 30 del Dow Jones, el
ETF ECH (proxy del IPSA, que no tiene ticker propio en Yahoo Finance),
benchmarks internacionales y las "7 Magníficas". Corre junto al script
del BCCh en el cron job diario de Railway.

Estrategia de descarga (para que una corrida diaria no vuelva a durar
>30 min y ser matada por el límite del contenedor, como pasó el
2026-09-02):

  Fase 1 — incremental: para TODOS los tickers se baja solo una ventana
  reciente (VENTANA_INCREMENTAL). Es rápido y el solapamiento con lo ya
  guardado permite re-chequear la historia reciente cada día.

  Detector de reajuste histórico: Yahoo devuelve precios ajustados por
  splits/dividendos y recalcula ese ajuste de forma continua. El
  re-ajuste por dividendos en efectivo mueve los cierres ~0.001% (ruido,
  ver TOLERANCIA_RELATIVA_PRECIO). Un split o una corrección grande de
  datos mueve un cierre YA guardado por un factor grande: si en la
  ventana incremental una fecha ya existente difiere >UMBRAL_REAJUSTE_
  HISTORICO del valor guardado, ese ticker se marca para re-sync completo
  inmediato en la fase 2 — así un split se auto-corrige el mismo día en
  vez de dejar un escalón en la serie.

  Fase 2 — re-sync de historia completa: baja PERIODO_COMPLETO, pero solo
  para (a) los tickers marcados por el detector y (b) una porción del
  universo por corrida (MAX_TICKERS_REFRESH_POR_CORRIDA), empezando en un
  offset rotativo por fecha e iterando de forma circular hasta agotar
  PRESUPUESTO_REFRESH_SEG. Así cada ticker se re-sincroniza por completo
  cada ~10 días sin que ninguna corrida haga el pull de los ~166 tickers
  de una (que es justo lo que causó el timeout del 2026-09-02). Un corte
  por presupuesto o un SIGKILL no pierde nada (commit por ticker); la
  rotación del día siguiente sigue avanzando.

  --full fuerza el re-sync completo de todos los tickers, sin presupuesto
  (para una resincronización manual).
"""

import math
import os
import sys
import time
from datetime import date, datetime

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# El cron corre en Linux (stdout UTF-8), pero en un dev local en Windows la
# consola es cp1252 y un print con un carácter no-latino (ej. una flecha o
# un emoji en un mensaje de log) aborta el script entero. Con errors=
# "replace" ese print degrada a "?" en vez de tirar UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

import pandas as pd
import yfinance as yf
from models import get_session, PrecioAccion, MetadataActualizacion
from constants import (
    TICKERS_IPSA,
    TICKER_PROXY_IPSA,
    TICKERS_BENCHMARK,
    TICKERS_MAGNIFICAS,
    TICKER_PETROLEO_WTI,
    TICKER_DOW_JONES,
    TICKER_NASDAQ,
    TICKER_VIX,
    TICKERS_DOW_JONES,
    TICKERS_CHILE_ADICIONALES,
    TICKERS_EEUU_ADICIONALES,
    TICKERS_LABORATORIO_ADICIONALES,
    TICKERS_LABORATORIO_ADICIONAL_DESCARGA,
)
from retry_utils import con_reintentos_db

# dict.fromkeys en vez de una lista simple: varias de las "7 Magníficas"
# (AAPL, MSFT, GOOGL, AMZN, NVDA) también son parte del Dow Jones — se
# descargan una sola vez, preservando el orden de la primera aparición.
TICKERS_A_DESCARGAR = list(dict.fromkeys(
    TICKERS_IPSA
    + TICKERS_CHILE_ADICIONALES
    + [TICKER_PROXY_IPSA]
    + [t for t in TICKERS_BENCHMARK if t != TICKER_PROXY_IPSA]
    + TICKERS_MAGNIFICAS
    + TICKERS_DOW_JONES
    + TICKERS_EEUU_ADICIONALES
    + TICKERS_LABORATORIO_ADICIONALES
    + TICKERS_LABORATORIO_ADICIONAL_DESCARGA
    + [TICKER_PETROLEO_WTI, TICKER_DOW_JONES, TICKER_NASDAQ, TICKER_VIX]
))


# Ventana que se baja para TODOS los tickers en cada corrida. 3 meses da
# solape de sobra con lo ya guardado para que el detector de reajuste
# funcione aunque el ticker haya estado fuera del pipeline varias semanas.
VENTANA_INCREMENTAL = "3mo"
# Historia completa que se baja en el re-sync (fase 2).
PERIODO_COMPLETO = "5y"
# Presupuesto de tiempo (segundos) para la fase 2 en una corrida normal.
# Al agotarse, la fase corta limpia y los tickers que faltan quedan para
# la próxima rotación. Medido contra prod: fase 1 (~166 tickers, ventana
# 3mo, una request de Yahoo por ticker) ~4-6 min; cada re-sync completo
# ~7-10s. Con este presupuesto la corrida entera de acciones queda en
# ~6-9 min y el cron completo (noticias+brief+bcch+acciones) en ~13 min,
# bien bajo el umbral de ~30 min que mató la corrida del 2026-09-02.
PRESUPUESTO_REFRESH_SEG = 210
# Cuántos tickers, como máximo, intenta re-sincronizar la fase 2 por
# corrida (además del presupuesto de tiempo). Con ~166 tickers, 18 por
# corrida = universo completo re-sincronizado cada ~9-10 días. El detector
# de reajuste corre para los 166 TODOS los días, así que un split se
# atrapa mucho antes que eso; la rotación es solo la red de fondo.
MAX_TICKERS_REFRESH_POR_CORRIDA = 18


def descargar_ticker(ticker: str, periodo: str = VENTANA_INCREMENTAL):
    """Descarga el histórico de un ticker usando yfinance.

    timeout=30: sin esto, una llamada de red que se cuelga (Yahoo Finance
    no responde) deja el script esperando indefinidamente sin lanzar
    ninguna excepción — pasó en producción (el cron quedó "Running" más
    de una hora). Con timeout, esa acción específica falla con una
    excepción normal en vez de colgar el proceso completo."""
    accion = yf.Ticker(ticker)
    historico = accion.history(period=periodo, timeout=30)
    return historico


TOLERANCIA_RELATIVA_PRECIO = 1e-4  # 0.01%: ver docstring de guardar_historico
# Un cierre YA guardado que cambia más que esto entre corridas no es
# re-ajuste por dividendo en efectivo (ruido <~0.1%): es un split o una
# corrección grande de datos de Yahoo. 2% deja margen holgado en ambos
# lados — hasta un dividendo EN ACCIONES del 5% mueve ~4.76%, y aun así
# lo captura; un split real (2:1 = -50%) lo cruza de sobra.
UMBRAL_REAJUSTE_HISTORICO = 0.02


def guardar_historico(session, ticker: str, historico):
    """Inserta o actualiza (por ticker+fecha) el histórico de un ticker en la BD.

    Devuelve (contador, reajuste_historico): `contador` = filas procesadas;
    `reajuste_historico` = True si alguna fecha YA guardada difiere del valor
    entrante en más de UMBRAL_REAJUSTE_HISTORICO (señal de split o corrección
    grande de Yahoo — el llamador debe re-sincronizar la historia completa de
    ese ticker).

    Trae fecha+precio+volumen ya guardados para ese ticker en una sola consulta
    (en vez de una consulta por día), inserta en bloque las fechas nuevas, y
    solo emite un UPDATE cuando el precio cambió MÁS que un ruido de punto
    flotante (ver TOLERANCIA_RELATIVA_PRECIO) o cambió el volumen.

    Antes comparaba el precio con IGUALDAD EXACTA, asumiendo que "los precios
    de cierre históricos casi nunca se revisan". Eso resultó falso: yfinance
    devuelve precios ajustados por dividendos/splits (auto_adjust), y ese
    ajuste se recalcula de forma continua — cada recálculo mueve TODOS los
    cierres históricos por una fracción minúscula (ej. 269.1323 -> 269.1324,
    diferencia relativa ~0.00004%). Con igualdad exacta, eso se contaba como
    "cambió" y disparaba un UPDATE individual (una ida y vuelta a la BD) por
    cada fila así — medido en producción: 644 de 1249 filas de un solo
    ticker (AGUAS-A.SN), NINGUNA con una diferencia real (todas <0.1%,
    la inmensa mayoría <0.001%). Eso multiplicado por ~164 tickers es la
    causa real de que la actualización diaria tardara horas en vez de
    minutos — confirmado con un benchmark real antes/después de este fix,
    no asumido (ver el historial de commits)."""
    existentes = {
        fecha: (float(precio), volumen)
        for fecha, precio, volumen in session.query(
            PrecioAccion.fecha, PrecioAccion.precio_cierre, PrecioAccion.volumen
        ).filter_by(ticker=ticker)
    }

    nuevas = []
    contador = 0
    reajuste_historico = False
    for fecha_idx, fila in historico.iterrows():
        fecha = fecha_idx.date()
        precio = float(fila["Close"])
        # Yahoo Finance a veces devuelve NaN para el día más reciente (ej.
        # sesión de mercado todavía incompleta) - no se guarda un "precio" que
        # en realidad no existe (causaba que el dashboard mostrara "nan").
        if precio != precio:  # NaN nunca es igual a sí mismo
            continue
        # Algunos índices/ETFs (ej. benchmarks internacionales) no traen volumen.
        volumen = int(fila["Volume"]) if pd.notna(fila["Volume"]) else None

        if fecha not in existentes:
            nuevas.append(PrecioAccion(ticker=ticker, fecha=fecha, precio_cierre=precio, volumen=volumen))
        else:
            precio_guardado, volumen_guardado = existentes[fecha]
            if precio_guardado and not math.isclose(
                precio_guardado, precio, rel_tol=UMBRAL_REAJUSTE_HISTORICO
            ):
                reajuste_historico = True
            precio_cambio = not math.isclose(precio_guardado, precio, rel_tol=TOLERANCIA_RELATIVA_PRECIO)
            if precio_cambio or volumen_guardado != volumen:
                session.query(PrecioAccion).filter_by(ticker=ticker, fecha=fecha).update({
                    "precio_cierre": precio,
                    "volumen": volumen,
                })
        contador += 1

    if nuevas:
        session.bulk_save_objects(nuevas)

    return contador, reajuste_historico


def _descargar_y_guardar(session, ticker, periodo, tickers_fallidos):
    """Baja `ticker` con la ventana `periodo`, lo guarda, y devuelve
    (contador, reajuste_historico) o None si el ticker falló (ya registrado
    en `tickers_fallidos`). Un ticker problemático no aborta la corrida."""
    try:
        historico = descargar_ticker(ticker, periodo)

        def _guardar_y_commitear(ticker=ticker, historico=historico):
            resultado_local = guardar_historico(session, ticker, historico)
            session.commit()
            return resultado_local

        # La descarga vía yfinance no se reintenta acá (ya tiene timeout=30,
        # y reintentar una falla de red repetida no aporta); solo la escritura
        # a la BD, propensa a cortes transitorios de la conexión serverless.
        # guardar_historico es idempotente, así que reintentar la función
        # completa -no solo el commit- es seguro.
        return con_reintentos_db(session, _guardar_y_commitear)
    except Exception as e:
        session.rollback()
        tickers_fallidos.append((ticker, str(e)))
        print(f"  [!] Fallo con {ticker}, se salta: {e}")
        return None


def actualizar_todas_las_acciones(refresh_completo=False):
    session = get_session()

    tickers_fallidos = []
    tickers_con_reajuste = []

    try:
        # --- Fase 1: ventana incremental para TODOS los tickers ---
        for ticker in TICKERS_A_DESCARGAR:
            print(f"Descargando {ticker} (ventana {VENTANA_INCREMENTAL})...")
            resultado = _descargar_y_guardar(
                session, ticker, VENTANA_INCREMENTAL, tickers_fallidos
            )
            if resultado is None:
                continue
            contador, reajuste = resultado
            if reajuste:
                tickers_con_reajuste.append(ticker)
                print(f"  -> {contador} días procesados  [!] reajuste histórico detectado (se re-sincroniza abajo)")
            else:
                print(f"  -> {contador} días procesados")

        # --- Fase 2: re-sync de historia completa ---
        # Primero los tickers con reajuste detectado (split / corrección
        # grande), luego una porción del universo por offset rotativo,
        # acotada por MAX_TICKERS_REFRESH_POR_CORRIDA y PRESUPUESTO_REFRESH_SEG.
        if refresh_completo:
            objetivo = list(TICKERS_A_DESCARGAR)
        else:
            n = len(TICKERS_A_DESCARGAR)
            offset = date.today().toordinal() % n
            rotacion = TICKERS_A_DESCARGAR[offset:] + TICKERS_A_DESCARGAR[:offset]
            objetivo = list(dict.fromkeys(
                tickers_con_reajuste + rotacion[:MAX_TICKERS_REFRESH_POR_CORRIDA]
            ))

        print(f"\n-- Re-sync historia completa ({PERIODO_COMPLETO}): {len(objetivo)} ticker(s) --")
        inicio = time.monotonic()
        resincronizados = 0
        for i, ticker in enumerate(objetivo):
            if not refresh_completo and time.monotonic() - inicio > PRESUPUESTO_REFRESH_SEG:
                print(f"  Presupuesto de re-sync agotado; {len(objetivo) - i} ticker(s) quedan para la próxima rotación.")
                break
            print(f"Re-sync completo {ticker}...")
            resultado = _descargar_y_guardar(
                session, ticker, PERIODO_COMPLETO, tickers_fallidos
            )
            if resultado is not None:
                contador, _ = resultado
                print(f"  -> {contador} días re-sincronizados")
                resincronizados += 1

        def _guardar_metadata():
            meta = session.query(MetadataActualizacion).filter_by(fuente="yfinance").first()
            if meta:
                meta.ultima_actualizacion = datetime.now()
            else:
                session.add(MetadataActualizacion(fuente="yfinance", ultima_actualizacion=datetime.now()))
            session.commit()

        con_reintentos_db(session, _guardar_metadata)

        print(
            f"Actualización de acciones completada "
            f"(re-sync completo de {resincronizados} ticker(s)"
            + (f", {len(tickers_con_reajuste)} por reajuste detectado" if tickers_con_reajuste else "")
            + ")."
        )
        if tickers_fallidos:
            print(f"  {len(tickers_fallidos)} ticker(s) fallido(s):")
            for ticker, error in tickers_fallidos:
                print(f"  - {ticker}: {error}")

    except Exception as e:
        session.rollback()
        print(f"Error actualizando precios de acciones: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    actualizar_todas_las_acciones(refresh_completo="--full" in sys.argv)
