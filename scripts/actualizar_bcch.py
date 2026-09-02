"""
Descarga las series macro del Banco Central de Chile y las guarda en la BD.
Este script lo corre el cron job de Railway una vez al día.

Requiere las variables de entorno:
  BCCH_TOKEN   -> API key/token gratuito de la API del BCCh (autenticación REST)
  DATABASE_URL -> conexión a PostgreSQL (la da Railway)
"""

import os
import sys
from datetime import datetime, date

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import requests
import yfinance as yf
from models import get_session, SerieMacro, MetadataActualizacion
from retry_utils import con_reintentos_db

# El codigo_serie es el identificador que usa el BCCh para cada serie.
# Todos los códigos fueron verificados contra SearchSeries de la propia API.
SERIES_A_DESCARGAR = {
    "F073.TCO.PRE.Z.D": {"nombre": "Tipo de cambio observado", "frecuencia": "diaria"},
    # Unidad de Fomento: encontrada vía SearchSeries (function=SearchSeries
    # no filtra por texto del lado del servidor pese al parámetro "series" --
    # hay que traer el catálogo completo de la frecuencia y filtrar client-
    # side por título) -- verificada con GetSeries antes de agregarla, con
    # el valor del día devuelto coincidiendo con el orden de magnitud real
    # de la UF (~40.870 CLP en 2026).
    "F073.UFF.PRE.Z.D": {"nombre": "Unidad de fomento (UF)", "frecuencia": "diaria"},
    "F022.TPM.TIN.D001.NO.Z.D": {"nombre": "Tasa de política monetaria (TPM)", "frecuencia": "diaria"},
    # El BCCh discontinuó la serie base 2018=100 (G073.IPC.IND.2018.M) en
    # diciembre de 2023 al cambiar de año base; esta es la serie "empalmada"
    # (spliced) que la reemplaza, con historia completa desde 2015 y datos
    # vigentes - encontrada vía SearchSeries al notar que el IPC no se
    # actualizaba en el dashboard.
    "G073.IPC.IND.2023.M": {"nombre": "IPC (índice, empalme base 2023=100)", "frecuencia": "mensual"},
    # Variación a 12 meses del IPC: la cifra de "inflación anual" que
    # normalmente se reporta (distinta del nivel del índice o de su
    # variación mensual, que pueden confundirse con "la inflación").
    "G073.IPC.V12.2023.M": {"nombre": "IPC variación 12 meses (inflación anual, empalme base 2023=100)", "frecuencia": "mensual"},
    "F032.IMC.IND.Z.Z.EP18.Z.Z.0.M": {"nombre": "IMACEC", "frecuencia": "mensual"},
    # Variación a 12 meses del Imacec (mismo problema que el IPC arriba: el
    # nivel del índice por sí solo no sirve para mostrar "cuánto subió/bajó
    # la actividad económica" -- calcular un % entre dos observaciones
    # mensuales consecutivas del índice da un cambio mes a mes sin
    # desestacionalizar, que no es la cifra que se reporta como "el Imacec
    # cayó/subió X%". Encontrada vía SearchSeries; verificada contra el
    # comunicado de prensa del Banco Central: julio 2026 da -1.49% acá vs.
    # -1,5% publicado — descubierta porque el dashboard mostraba -3,29% para
    # julio 2026 (el cambio mes a mes del índice bruto) mientras la prensa
    # reportaba -1,5% interanual.
    "F032.IMC.V12.Z.Z.2018.Z.Z.0.M": {"nombre": "IMACEC variación 12 meses", "frecuencia": "mensual"},
    "F019.PPB.PRE.100.D": {"nombre": "Precio del cobre (USD/oz troy)", "frecuencia": "diaria"},
    "F022.SPC.TPR.D090.NO.Z.D": {"nombre": "Swap Promedio Cámara nominal (90 días)", "frecuencia": "diaria"},
    "F022.PDBC.TIN.D014.NO.Z.D": {"nombre": "Tasa libre de riesgo CLP (PDBC 14 días)", "frecuencia": "diaria"},
    "F022.BCLP.TIS.AN10.NO.Z.D": {"nombre": "Bono BCCh en pesos (BCP) a 10 años - tasa mercado secundario", "frecuencia": "diaria"},
    # Tasa real (bonos en UF, indexados a inflación): BCP - BCU al mismo plazo
    # es la inflación breakeven implícita en el mercado (ver
    # calcular_inflacion_breakeven en app/dashboard.py).
    "F022.BUF.TIS.AN10.UF.Z.D": {"nombre": "Bono BCCh en UF (BCU) a 10 años - tasa mercado secundario", "frecuencia": "diaria"},
    "F049.DES.TAS.INE.10.M": {"nombre": "Tasa de desocupación nacional (INE, desestacionalizada)", "frecuencia": "mensual"},
}

BCCH_URL = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"

# El BCCh no publica la tasa de la Fed ni el bono del Tesoro de EEUU como
# series propias (no existen en su catálogo SearchSeries), así que los bonos
# de EEUU se descargan aparte desde Yahoo Finance.
CODIGO_UST10 = "YF.^TNX"
NOMBRE_UST10 = "Bono del Tesoro de EEUU a 10 años (UST10Y)"

# Yahoo Finance no tiene un índice "^" para el UST 2 años (solo 13 semanas,
# 5, 10 y 30 años). El sustituto verificado es 2YY=F (2-Year Yield Futures,
# CME), que cotiza directamente en rendimiento (no en precio) y tiene ~5
# años de historia con valores económicamente coherentes (0.2% en 2021,
# subiendo con el ciclo de alzas de la Fed hasta ~4% hoy).
CODIGO_UST2 = "YF.2YY=F"
NOMBRE_UST2 = "Bono del Tesoro de EEUU a 2 años (UST2Y, proxy 2YY=F)"

# El BCCh tampoco publica la tasa de política monetaria de EEUU. Se usa la
# Effective Federal Funds Rate (serie "DFF") de FRED (Federal Reserve
# Economic Data), vía su endpoint CSV público que no requiere autenticación.
CODIGO_TPM_EEUU = "FRED.DFF"
NOMBRE_TPM_EEUU = "Tasa de política monetaria de EEUU (Effective Federal Funds Rate)"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# Treasury Constant Maturity a 1 año (serie "DGS1" del H.15 de la Reserva
# Federal, publicada en FRED) — la tasa libre de riesgo que pide
# específicamente "Laboratorio Financiero" (distinta de la Effective Federal
# Funds Rate de arriba, que es la tasa de política monetaria, no un
# rendimiento de bonos del Tesoro). Mismo endpoint CSV público sin API key.
CODIGO_TREASURY_1Y = "FRED.DGS1"
NOMBRE_TREASURY_1Y = "Bono del Tesoro de EEUU a 1 año (Treasury Constant Maturity, H.15)"

# Resto de la curva de Treasury Constant Maturity (H.15), para ajustar
# Nelson-Siegel y Svensson en "Laboratorio Financiero" (Pregunta 2:
# Modelos de Estructura de Tasas). DGS1 (1 año) ya se descarga arriba con
# su propio nombre porque además se usa como Rf en otras partes del
# laboratorio; estos 10 plazos son exclusivos de la curva completa.
# Incluye DGS10 aunque ya existe un "UST10Y" (vía Yahoo Finance, ^TNX,
# usado en otras partes del dashboard) a propósito: para ajustar una
# curva bien necesitas que TODOS los puntos vengan de la misma fuente
# (acá, el H.15 real vía FRED) — mezclar un punto de Yahoo con el resto
# de FRED introduciría una inconsistencia metodológica en el ajuste.
SERIES_TREASURY_FRED = {
    "DGS1MO": "1 mes",
    "DGS3MO": "3 meses",
    "DGS6MO": "6 meses",
    "DGS2": "2 años",
    "DGS3": "3 años",
    "DGS5": "5 años",
    "DGS7": "7 años",
    "DGS10": "10 años",
    "DGS20": "20 años",
    "DGS30": "30 años",
}

# Predictores adicionales para el modelo Probit de recesión de EEUU
# ("Modelo de Recesión EEUU" en el dashboard, que extiende recesion.py con
# variables de FRED buscando mejorar la sensibilidad del modelo original,
# que solo usaba g_lag y p_lag). Mismo endpoint CSV público sin API key.
# Ninguna de estas 4 series tiene historia hasta 1962 en FRED (a diferencia
# de g y p del Excel original): UNRATE arranca en 1948, ICSA en 1967,
# BAA10Y en 1986, NFCI en 1971 -- por eso se piden desde 1948 acá (lo más
# atrás que existe cualquiera de ellas) y el merge posterior con el Excel
# recorta cada modelo a la ventana que sus propias variables permiten.
SERIES_RECESION_FRED = {
    "UNRATE": {"nombre": "Tasa de desempleo de EEUU (UNRATE)", "frecuencia": "mensual"},
    "ICSA": {"nombre": "Solicitudes iniciales de seguro de desempleo de EEUU (ICSA)", "frecuencia": "semanal"},
    "BAA10Y": {"nombre": "Spread bonos corporativos Baa vs Treasury 10 años (BAA10Y)", "frecuencia": "diaria"},
    "NFCI": {"nombre": "Índice de condiciones financieras nacionales de Chicago Fed (NFCI)", "frecuencia": "semanal"},
}


def descargar_serie(codigo_serie: str, first_date: str = "2015-01-01") -> list[dict]:
    """Pide una serie a la API del BCCh y devuelve una lista de {fecha, valor}."""
    token = os.environ["BCCH_TOKEN"]

    params = {
        "token": token,
        "firstdate": first_date,
        "lastdate": date.today().isoformat(),
        "timeseries": codigo_serie,
        "function": "GetSeries",
    }

    response = requests.get(BCCH_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

 # La API devuelve la serie en Series.Obs -> lista de {indexDateString, value}
    series = data.get("Series") or {}
    observaciones = series.get("Obs") or []

    if not observaciones:
        print(f"  Respuesta completa de la API para {codigo_serie}:")
        print(f"  {data}")

    resultado = []
    for obs in observaciones:
        try:
            fecha = datetime.strptime(obs["indexDateString"], "%d-%m-%Y").date()
            valor = float(obs["value"])
            # float("NaN") no lanza excepción: el BCCh manda value="NaN" para
            # días sin observación (fines de semana en series diarias), así
            # que hay que descartarlo explícitamente en vez de confiar en el
            # try/except.
            if valor != valor:  # NaN nunca es igual a sí mismo
                continue
            resultado.append({"fecha": fecha, "valor": valor})
        except (ValueError, KeyError, TypeError):
            # Algunos valores vienen vacíos o con formato inválido - los saltamos
            continue

    return resultado


def descargar_serie_yfinance(ticker: str, first_date: str = "2015-01-01") -> list[dict]:
    """Descarga un rendimiento (ya expresado en %, no en precio) vía Yahoo Finance."""
    historico = yf.Ticker(ticker).history(start=first_date)
    resultado = []
    for fecha_idx, fila in historico.iterrows():
        valor = float(fila["Close"])
        # Yahoo Finance a veces devuelve NaN para el día más reciente (ej.
        # sesión de mercado todavía incompleta) - mismo criterio que
        # descargar_serie() para no guardar un "dato" que en realidad no existe.
        if valor != valor:  # NaN nunca es igual a sí mismo
            continue
        resultado.append({"fecha": fecha_idx.date(), "valor": valor})
    return resultado


def descargar_serie_fred(fred_id: str, first_date: str = "2015-01-01") -> list[dict]:
    """Descarga una serie pública de FRED vía su endpoint CSV (no requiere
    API key para series individuales)."""
    response = requests.get(FRED_URL, params={"id": fred_id}, timeout=30)
    response.raise_for_status()

    primera_fecha = datetime.strptime(first_date, "%Y-%m-%d").date()
    resultado = []
    lineas = response.text.splitlines()
    for linea in lineas[1:]:  # la primera línea es el encabezado "observation_date,<id>"
        partes = linea.split(",")
        if len(partes) != 2:
            continue
        fecha_str, valor_str = partes
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            valor = float(valor_str)  # FRED usa "." para datos faltantes -> ValueError, se salta
        except ValueError:
            continue
        if fecha < primera_fecha:
            continue
        resultado.append({"fecha": fecha, "valor": valor})

    return resultado


def guardar_observaciones(session, codigo: str, nombre: str, frecuencia: str, observaciones: list[dict]):
    """Inserta o actualiza (por fecha+serie) las observaciones de una serie en la BD.

    Trae fecha+valor ya guardados para esa serie en una sola consulta (en vez de
    una consulta por observación), inserta en bloque las fechas nuevas, y solo
    emite un UPDATE cuando el valor realmente cambió respecto a lo guardado
    (los datos históricos casi nunca se revisan, así que en una re-corrida
    normal esto evita miles de idas y vueltas innecesarias a la base de datos).
    """
    if not observaciones:
        return

    existentes = {
        fecha: float(valor)
        for fecha, valor in session.query(SerieMacro.fecha, SerieMacro.valor).filter_by(codigo_serie=codigo)
    }

    nuevas = []
    for obs in observaciones:
        if obs["fecha"] not in existentes:
            nuevas.append(
                SerieMacro(codigo_serie=codigo, nombre=nombre, fecha=obs["fecha"], valor=obs["valor"], frecuencia=frecuencia)
            )
        elif existentes[obs["fecha"]] != obs["valor"]:
            session.query(SerieMacro).filter_by(codigo_serie=codigo, fecha=obs["fecha"]).update({"valor": obs["valor"]})

    if nuevas:
        session.bulk_save_objects(nuevas)


def actualizar_todas_las_series():
    session = get_session()

    def _guardar_y_commitear(codigo, nombre, frecuencia, observaciones):
        def _hacerlo():
            guardar_observaciones(session, codigo, nombre, frecuencia, observaciones)
            session.commit()

        # La descarga vía API no se reintenta acá (no es el problema
        # observado); solo la escritura a la BD, propensa a cortes
        # transitorios de la conexión serverless de Neon. guardar_observaciones
        # es idempotente (compara contra lo ya guardado), así que reintentar
        # la función completa -no solo el commit- es seguro.
        con_reintentos_db(session, _hacerlo)

    try:
        for codigo, info in SERIES_A_DESCARGAR.items():
            print(f"Descargando {info['nombre']} ({codigo})...")
            observaciones = descargar_serie(codigo)
            _guardar_y_commitear(codigo, info["nombre"], info["frecuencia"], observaciones)
            print(f"  -> {len(observaciones)} observaciones procesadas")

        print(f"Descargando {NOMBRE_UST10} ({CODIGO_UST10})...")
        observaciones = descargar_serie_yfinance("^TNX")
        _guardar_y_commitear(CODIGO_UST10, NOMBRE_UST10, "diaria", observaciones)
        print(f"  -> {len(observaciones)} observaciones procesadas")

        print(f"Descargando {NOMBRE_UST2} ({CODIGO_UST2})...")
        observaciones = descargar_serie_yfinance("2YY=F", first_date="2021-08-13")
        _guardar_y_commitear(CODIGO_UST2, NOMBRE_UST2, "diaria", observaciones)
        print(f"  -> {len(observaciones)} observaciones procesadas")

        print(f"Descargando {NOMBRE_TPM_EEUU} ({CODIGO_TPM_EEUU})...")
        observaciones = descargar_serie_fred("DFF")
        _guardar_y_commitear(CODIGO_TPM_EEUU, NOMBRE_TPM_EEUU, "diaria", observaciones)
        print(f"  -> {len(observaciones)} observaciones procesadas")

        print(f"Descargando {NOMBRE_TREASURY_1Y} ({CODIGO_TREASURY_1Y})...")
        observaciones = descargar_serie_fred("DGS1")
        _guardar_y_commitear(CODIGO_TREASURY_1Y, NOMBRE_TREASURY_1Y, "diaria", observaciones)
        print(f"  -> {len(observaciones)} observaciones procesadas")

        for fred_id, plazo in SERIES_TREASURY_FRED.items():
            codigo = f"FRED.{fred_id}"
            nombre = f"Bono del Tesoro de EEUU a {plazo} (Treasury Constant Maturity, H.15)"
            print(f"Descargando {nombre} ({codigo})...")
            observaciones = descargar_serie_fred(fred_id)
            _guardar_y_commitear(codigo, nombre, "diaria", observaciones)
            print(f"  -> {len(observaciones)} observaciones procesadas")

        for fred_id, info in SERIES_RECESION_FRED.items():
            codigo = f"FRED.{fred_id}"
            print(f"Descargando {info['nombre']} ({codigo})...")
            observaciones = descargar_serie_fred(fred_id, first_date="1948-01-01")
            _guardar_y_commitear(codigo, info["nombre"], info["frecuencia"], observaciones)
            print(f"  -> {len(observaciones)} observaciones procesadas")

        def _guardar_metadata():
            # Registra que esta fuente se actualizó ahora
            meta = session.query(MetadataActualizacion).filter_by(fuente="bcch").first()
            if meta:
                meta.ultima_actualizacion = datetime.now()
            else:
                session.add(MetadataActualizacion(fuente="bcch", ultima_actualizacion=datetime.now()))
            session.commit()

        con_reintentos_db(session, _guardar_metadata)
        print("Actualización del BCCh completada.")

    except Exception as e:
        session.rollback()
        print(f"Error actualizando datos del BCCh: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    actualizar_todas_las_series()
