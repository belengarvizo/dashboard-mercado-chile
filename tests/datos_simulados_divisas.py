"""Posiciones abiertas INVENTADAS para ver el bloque de riesgo agrupado.

POR QUÉ EXISTE. El diario real está en cero, así que el camino con
posiciones abiertas no se puede mirar en pantalla con datos de verdad. Este
módulo arma un diario simulado y lo entrega interceptando `pandas.read_sql`:
nunca escribe en la base, nunca la consulta para estas tres tablas.

LOS PRECIOS TAMBIÉN SON SIMULADOS, a propósito. Si la prueba usara los
precios reales, la agrupación dependería de correlaciones que se mueven
todos los días: EURUSD contra USDCHF está hoy en -0,706, a seis milésimas
del umbral. Una prueba que se cae sola el martes no sirve de nada.
"""
import numpy as np
import pandas as pd

# Cuatro posiciones elegidas para que se vea cada caso del signo a la vez:
#   EURUSD compra  150.000  <- referencia del grupo
#   GBPUSD compra  120.000  <- correlación +1 y mismo sentido -> SUMA
#   USDCHF compra   40.000  <- correlación -1 y mismo sentido -> COMPENSA
#   USDJPY venta    90.000  <- sin correlación -> queda sola
#
# Riesgo agrupado del grupo = 150.000 + 120.000 - 40.000 = 230.000
# Riesgo bruto del grupo    = 310.000
# Riesgo total abierto      = 400.000   (compras 310.000 / ventas 90.000)
POSICIONES = [
    ("EURUSD", "compra", 150000.0, 1.1180),
    ("GBPUSD", "compra", 120000.0, 1.3350),
    ("USDCHF", "compra", 40000.0, 0.7960),
    ("USDJPY", "venta", 90000.0, 152.400),
]
EQUITY = 9500000.0

# Con equity de 9.500.000: el tope por grupo (2%) son 190.000 y el grupo va
# en 230.000 -> ROJO. El tope por dirección (4%) son 380.000 y las compras
# van en 310.000, sobre el 80% (304.000) -> AMARILLO. Así se ven los dos
# avisos en la misma pantalla.
TOPE_GRUPO_ESPERADO = 190000.0
RIESGO_AGRUPADO_ESPERADO = 230000.0
RIESGO_TOTAL_ESPERADO = 400000.0

TICKERS = {"EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X",
           "USDCHF": "USDCHF=X", "USDJPY": "USDJPY=X"}

COLUMNAS_OPERACIONES = [
    "id", "instrumento", "categoria", "direccion", "fecha_apertura", "fecha_cierre",
    "precio_entrada", "precio_salida", "stop", "objetivo", "lotes", "margen_clp",
    "riesgo_clp", "resultado_clp", "duracion_segundos", "catalizador",
    "condicion_invalidacion", "tesis", "notas", "conviccion", "tendencia_diario",
    "evento_dia", "calidad_decision", "nota_post", "evento_plan_id",
]


def operaciones() -> pd.DataFrame:
    """Las cuatro posiciones, todas ABIERTAS (fecha_cierre nula)."""
    momento = pd.Timestamp("2026-10-12 09:30:00", tz="America/Santiago")
    filas = []
    for i, (instrumento, direccion, riesgo, precio) in enumerate(POSICIONES, start=1):
        fila = {c: None for c in COLUMNAS_OPERACIONES}
        fila.update({
            "id": i,
            "instrumento": instrumento,
            "categoria": "divisas",
            "direccion": direccion,
            "fecha_apertura": momento - pd.Timedelta(hours=i),
            "fecha_cierre": None,
            "precio_entrada": precio,
            "lotes": 0.10,
            "margen_clp": 180000.0,
            "riesgo_clp": riesgo,
            "tesis": "Posición simulada para revisar la pantalla.",
            "notas": "SIMULADA",
        })
        filas.append(fila)
    return pd.DataFrame(filas, columns=COLUMNAS_OPERACIONES)


def estado_cuenta() -> pd.DataFrame:
    return pd.DataFrame([{
        "momento": pd.Timestamp("2026-10-12 09:00:00", tz="America/Santiago"),
        "equity_clp": EQUITY,
        "margen_disponible_clp": 7200000.0,
        "nota": "SIMULADO",
    }])


def precios(dias: int = 70) -> pd.DataFrame:
    """Series con correlaciones FIJAS, para que la agrupación no dependa del
    mercado del día.

    EURUSD y GBPUSD comparten retornos (+1). USDCHF los lleva invertidos
    (-1). USDJPY es una serie aparte, deterministica por semilla fija, que
    no se parece a ninguna.
    """
    base = np.array([0.01 * np.sin(i) for i in range(dias)])
    aparte = np.random.RandomState(7).standard_normal(dias) * 0.01
    series = {
        "EURUSD=X": (base, 1.1000),
        "GBPUSD=X": (base, 1.3000),
        "USDCHF=X": (-base, 0.8000),
        "USDJPY=X": (aparte, 150.00),
    }
    # Terminan HOY para que la pantalla no muestre el aviso de datos viejos.
    # Las fechas no influyen en las correlaciones.
    fechas = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=dias + 1)
    filas = []
    for ticker, (retornos, inicio) in series.items():
        precio = inicio
        valores = [precio]
        for r in retornos:
            precio *= (1 + r)
            valores.append(precio)
        for fecha, valor in zip(fechas, valores):
            filas.append({"ticker": ticker, "fecha": fecha.date(),
                          "precio_cierre": valor, "volumen": 0})
    return pd.DataFrame(filas)


def interceptar(pd_modulo):
    """Devuelve un reemplazo de `pandas.read_sql` que responde las tres
    consultas del módulo con datos simulados y deja pasar todo lo demás.

    Lo que NO intercepta llega a la base de verdad, en modo lectura: el
    catálogo de instrumentos se sigue leyendo porque ahí está el mapa de
    nombre a ticker, y ese dato no cambia la demostración.
    """
    real = pd_modulo.read_sql

    def reemplazo(sql, *a, **kw):
        texto = str(sql)
        if "FROM trading_operaciones" in texto:
            return operaciones()
        if "FROM trading_estado_cuenta" in texto:
            return estado_cuenta()
        if "FROM precios_acciones" in texto:
            # Los tickers viajan como parametro, no en el texto del SQL.
            parametros = kw.get("params") or {}
            pedidos = parametros.get("tickers") or []
            if any(str(t).endswith("=X") for t in pedidos):
                return precios()
        return real(sql, *a, **kw)

    return reemplazo
