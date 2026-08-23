"""
Cálculo de los indicadores de mercado de la sección "Importante" del Brief
Premercado. Vive fuera de app/dashboard.py (que tiene llamadas a Streamlit a
nivel de módulo) para que scripts/generar_brief.py pueda reutilizar la misma
lógica sin depender de un contexto de Streamlit.
"""

import numpy as np
import pandas as pd
from scipy import stats

# (etiqueta, tipo de tabla de origen, nombre/ticker, unidad a mostrar)
INDICADORES_PREMERCADO = [
    ("S&P 500", "accion", "^GSPC", ""),
    ("Dow Jones", "accion", "^DJI", ""),
    ("Cobre", "macro", "Precio del cobre (USD/oz troy)", "US$/oz troy"),
    ("Petróleo WTI", "accion", "CL=F", "US$/barril"),
    ("Bono UST 10 años", "macro", "Bono del Tesoro de EEUU a 10 años (UST10Y)", "%"),
    ("TPM EEUU", "macro", "Tasa de política monetaria de EEUU (Effective Federal Funds Rate)", "%"),
    ("IPSA (proxy ECH)", "accion", "ECH", ""),
    ("TPM Chile", "macro", "Tasa de política monetaria (TPM)", "%"),
    ("IPC (inflación anual)", "macro", "IPC variación 12 meses (inflación anual, empalme base 2023=100)", "%"),
    ("Imacec", "macro", "IMACEC", ""),
    ("Tasa de desempleo", "macro", "Tasa de desocupación nacional (INE, desestacionalizada)", "%"),
]


def calcular_cambio_reciente(serie: pd.Series) -> tuple[float, float, object, float] | None:
    """(valor actual, % de cambio vs la sesión anterior, fecha, cambio
    absoluto) a partir de una serie ordenada por fecha. Descarta
    observaciones NaN (dato no disponible, ej. una sesión de mercado
    todavía incompleta) y usa el último valor VÁLIDO junto con su fecha
    real — nunca devuelve NaN, y nunca junta un dato viejo con la fecha de
    hoy.

    El cambio absoluto es necesario además del % porque para un indicador
    que YA es una tasa/porcentaje (ej. TPM, inflación anual), el "% de
    cambio" es el cambio porcentual de la tasa misma (ej. de 4,34% a 3,52%
    es -18,8%), no el cambio en puntos porcentuales (-0,82 pp) que es lo
    que normalmente se espera ver para ese tipo de indicador — quien llama
    decide cuál mostrar según la unidad."""
    serie = serie.dropna()
    if len(serie) < 2:
        return None
    valor_actual = serie.iloc[-1]
    valor_anterior = serie.iloc[-2]
    if not valor_anterior:
        return None
    cambio_pct = (valor_actual / valor_anterior - 1) * 100
    cambio_absoluto = valor_actual - valor_anterior
    return float(valor_actual), float(cambio_pct), serie.index[-1], float(cambio_absoluto)


def calcular_retornos_reales(serie_precio: pd.Series, serie_volumen: pd.Series) -> pd.Series:
    """Retornos diarios de una serie de precios, usando el volumen para
    distinguir un empate real de mercado (precio idéntico al día anterior,
    pero con volumen propio y distinto de cero — un movimiento real, no un
    error de datos) de un corte de la fuente (la fuente deja de refrescar y
    repite la misma fila día tras día, con volumen=0 o con el mismo volumen
    exacto del día anterior). Antes esta función excluía TODO precio
    repetido a ciegas; una auditoría cruzada contra Nasdaq.com (metodología
    de precio distinta) mostró que la mayoría de esos empates eran reales,
    pero excluir la comparación de volumen por completo (ver commit
    revertido) también dejaba pasar apagones reales de la fuente sin
    detectarlos — el caso de AGUAS-A.SN (37 ruedas seguidas con precio Y
    volumen idénticos) es justo lo que ese cambio dejaba de detectar.

    Un día con precio empatado se excluye (se trata como dato congelado, no
    como retorno real) si, además:
      - el volumen de ese día es 0, o
      - el volumen es idéntico al del día anterior (evidencia de que la
        fuente repitió la fila completa, no solo el precio).
    Si no hay volumen disponible para el ticker (NaN — algunos benchmarks
    internacionales no lo traen), no hay forma de distinguir un empate real
    de un corte de datos con este criterio, así que por seguridad se vuelve
    al criterio conservador anterior a la auditoría: el empate se excluye.

    Los días con precio genuinamente ausente (sin fila en la base para esa
    fecha) no aparecen en absoluto en `serie_precio` — no hay nada que
    filtrar para esos, pct_change() ya los salta solo. No confundir con la
    detección de "Atraso" del heatmap (dato más reciente posiblemente
    desactualizado): esa es una lógica separada, definida donde se usa, que
    sigue igual."""
    retornos = serie_precio.pct_change()
    precio_empatado = serie_precio.eq(serie_precio.shift(1))
    sin_evidencia_de_trading = (
        serie_volumen.isna() | serie_volumen.eq(0) | serie_volumen.eq(serie_volumen.shift(1))
    )
    congelado = precio_empatado & sin_evidencia_de_trading
    return retornos[~congelado]


def matriz_retornos_alineados(
    df_precios: pd.DataFrame,
    tickers: list,
    fecha_inicio=None,
    fecha_fin=None,
    quitar_sufijo_sn: bool = False,
) -> pd.DataFrame:
    """Retornos diarios reales (ver calcular_retornos_reales) de cada ticker
    dado, opcionalmente recortados a [fecha_inicio, fecha_fin], alineados
    por fecha (complete-case: solo se conservan los días donde TODOS los
    tickers pedidos tienen un retorno real ese día, requisito para que la
    matriz de covarianza resultante sea válida).

    Punto único para esta operación: antes existían dos copias casi
    idénticas (una en portfolio_lab.py, otra en app/dashboard.py como
    _matriz_retornos_alineados) que armaban la misma matriz por separado."""
    df_precios = df_precios.assign(fecha=pd.to_datetime(df_precios["fecha"]))
    fecha_inicio = pd.Timestamp(fecha_inicio) if fecha_inicio is not None else None
    fecha_fin = pd.Timestamp(fecha_fin) if fecha_fin is not None else None

    retornos = {}
    for ticker in tickers:
        datos = df_precios[df_precios["ticker"] == ticker].sort_values("fecha").set_index("fecha")
        if fecha_inicio is not None:
            datos = datos[datos.index >= fecha_inicio]
        if fecha_fin is not None:
            datos = datos[datos.index <= fecha_fin]
        nombre_columna = ticker.replace(".SN", "") if quitar_sufijo_sn else ticker
        retornos[nombre_columna] = calcular_retornos_reales(datos["precio_cierre"], datos["volumen"])
    return pd.DataFrame(retornos).dropna()


def calcular_capm_regresion(exceso_portafolio: pd.Series, exceso_mercado: pd.Series) -> dict | None:
    """Regresión CAPM por mínimos cuadrados ordinarios sobre retornos DIARIOS
    en exceso: Rp,t - Rf,t = α + β(Rm,t - Rf,t) + εt. Devuelve α, β, R², sus
    errores estándar clásicos de OLS, el estadístico t de α (test bilateral
    H0: α=0), su p-value exacto vía la distribución t con n-2 grados de
    libertad (no la aproximación normal), y el intervalo de confianza 95%
    de α. t y p-value son invariantes a la frecuencia de anualización
    (anualizar α y SE(α) por el mismo factor no cambia t=α/SE(α))."""
    x = exceso_mercado.to_numpy()
    y = exceso_portafolio.to_numpy()
    n = len(x)
    if n < 3:
        return None

    x_media = x.mean()
    sxx = float(np.sum((x - x_media) ** 2))
    if sxx <= 0:
        return None

    beta = float(np.sum((x - x_media) * (y - y.mean())) / sxx)
    alfa = float(y.mean() - beta * x_media)

    residuos = y - (alfa + beta * x)
    gl = n - 2
    sigma2 = float(np.sum(residuos ** 2) / gl)
    se_alfa = (sigma2 * (1 / n + x_media ** 2 / sxx)) ** 0.5
    se_beta = (sigma2 / sxx) ** 0.5

    t_alfa = alfa / se_alfa if se_alfa > 0 else float("inf")
    p_valor = float(2 * stats.t.sf(abs(t_alfa), df=gl))
    t_critico = float(stats.t.ppf(0.975, df=gl))
    ic_95 = (alfa - t_critico * se_alfa, alfa + t_critico * se_alfa)

    ss_res = float(np.sum(residuos ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None

    return {
        "alfa": alfa, "beta": beta, "r2": r2, "se_alfa": se_alfa, "se_beta": se_beta,
        "t_alfa": t_alfa, "p_valor": p_valor, "ic_95": ic_95, "n": n, "gl": gl,
    }


def calcular_resumen_mercado(df_macro: pd.DataFrame, df_acciones: pd.DataFrame) -> list[dict]:
    """Para cada indicador de INDICADORES_PREMERCADO, devuelve
    {etiqueta, unidad, resultado} donde resultado es lo que devuelve
    calcular_cambio_reciente (o None si no hay datos suficientes)."""
    resultados = []
    for etiqueta, tipo, clave, unidad in INDICADORES_PREMERCADO:
        if tipo == "accion":
            serie = (
                df_acciones[df_acciones["ticker"] == clave]
                .sort_values("fecha")
                .set_index("fecha")["precio_cierre"]
            )
        else:
            serie = (
                df_macro[df_macro["nombre"] == clave]
                .sort_values("fecha")
                .set_index("fecha")["valor"]
            )
        resultados.append({
            "etiqueta": etiqueta,
            "unidad": unidad,
            "resultado": calcular_cambio_reciente(serie),
        })
    return resultados


def detectar_apagon_mercado(
    df_precios: pd.DataFrame,
    tickers: list,
    umbral_pct: float = 0.8,
    ventana_dias: int = 3,
    dias_habiles_min_atraso: int = 5,
) -> dict | None:
    """Detecta un corte de la fuente de datos a nivel de mercado completo
    (ej. Yahoo Finance dejó de refrescar toda la Bolsa de Santiago), a
    diferencia del "Atraso" por fila que ya existe en el heatmap para cada
    ticker individual.

    El criterio NO es simplemente "muchos tickers comparten la misma
    última fecha con cambio real" — en un mercado sano eso es lo normal
    (casi todas las acciones cambian de precio todos los días, así que casi
    todas comparten "hoy" como última fecha real). La señal real de apagón
    es que una fracción amplia de los tickers está, además, ATRASADA (más
    de `dias_habiles_min_atraso` días hábiles sin cambio real — mismo
    umbral que ya usa el heatmap) Y esas fechas de atraso se agrupan dentro
    de una ventana de `ventana_dias` entre sí: eso es lo que distingue "la
    fuente cortó el mercado completo el mismo día" de "varias acciones no
    relacionadas tienen atrasos idiosincráticos en fechas distintas".

    Se recalcula cada vez contra `pd.Timestamp.now()` — nunca hardcodea una
    fecha de apagón — así que se activa solo mientras el apagón esté
    vigente y se apaga solo cuando la fuente vuelva a refrescar datos, o
    detecta un apagón nuevo en el futuro sin cambios de código.

    Devuelve None si no se detecta apagón, o un dict con
    {pct_afectado, n_afectados, n_total, fecha_apagon} si sí — fecha_apagon
    es la fecha más antigua entre los tickers atrasados agrupados (el día
    en que la fuente dejó de refrescar)."""
    df_precios = df_precios.assign(fecha=pd.to_datetime(df_precios["fecha"]))
    hoy = pd.Timestamp.now().normalize()

    fechas_atraso = []
    for ticker in tickers:
        serie = df_precios[df_precios["ticker"] == ticker].sort_values("fecha").set_index("fecha")["precio_cierre"]
        if len(serie) < 2:
            continue
        cambia = serie.ne(serie.shift(1))
        cambia.iloc[0] = True
        ultima_fecha_real = serie.index[cambia][-1]
        dias_atraso = int(np.busday_count(ultima_fecha_real.date(), hoy.date()))
        if dias_atraso > dias_habiles_min_atraso:
            fechas_atraso.append(ultima_fecha_real)

    n_total = len(tickers)
    if not fechas_atraso or n_total == 0:
        return None

    fecha_min = min(fechas_atraso)
    agrupadas = [f for f in fechas_atraso if (f - fecha_min).days <= ventana_dias]
    pct_afectado = len(agrupadas) / n_total

    if pct_afectado < umbral_pct:
        return None

    return {
        "pct_afectado": pct_afectado,
        "n_afectados": len(agrupadas),
        "n_total": n_total,
        "fecha_apagon": fecha_min.date(),
    }
