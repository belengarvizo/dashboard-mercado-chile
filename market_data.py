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


# ============================================================
# Atribución multi-factor del IPSA (proxy ECH)
# ============================================================

VENTANA_ATRIBUCION_IPSA = 120

# (nombre del factor, columna de retorno, tipo de tabla de origen, nombre/ticker en la fuente)
FACTORES_ATRIBUCION_IPSA = [
    ("Cobre", "cobre", "macro", "Precio del cobre (USD/oz troy)"),
    ("S&P 500", "sp500", "accion", "^GSPC"),
    ("USD/CLP", "usdclp", "macro", "Tipo de cambio observado"),
]


def _retornos_atribucion_ipsa(df_acciones: pd.DataFrame, df_macro: pd.DataFrame) -> pd.DataFrame:
    """Retornos diarios alineados de ECH (proxy del IPSA) y los 3 factores
    (complete-case: solo fechas donde los 4 tienen un retorno ese día).
    ECH y S&P 500 usan calcular_retornos_reales (precio + volumen, distingue
    empate real de corte de datos); cobre y USD/CLP son series del BCCh sin
    concepto de volumen, así que usan pct_change() directo — no tienen el
    mismo riesgo de "fuente que dejó de refrescar" que Yahoo Finance."""
    df_acciones = df_acciones.assign(fecha=pd.to_datetime(df_acciones["fecha"]))
    df_macro = df_macro.assign(fecha=pd.to_datetime(df_macro["fecha"]))

    ech = df_acciones[df_acciones["ticker"] == "ECH"].sort_values("fecha").set_index("fecha")
    sp500 = df_acciones[df_acciones["ticker"] == "^GSPC"].sort_values("fecha").set_index("fecha")
    cobre = (
        df_macro[df_macro["nombre"] == "Precio del cobre (USD/oz troy)"]
        .sort_values("fecha").set_index("fecha")["valor"]
    )
    usdclp = (
        df_macro[df_macro["nombre"] == "Tipo de cambio observado"]
        .sort_values("fecha").set_index("fecha")["valor"]
    )

    retornos = {
        "ech": calcular_retornos_reales(ech["precio_cierre"], ech["volumen"]),
        "cobre": cobre.pct_change(),
        "sp500": calcular_retornos_reales(sp500["precio_cierre"], sp500["volumen"]),
        "usdclp": usdclp.pct_change(),
    }
    return pd.DataFrame(retornos).dropna()


def _ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """OLS vía mínimos cuadrados (np.linalg.lstsq, no requiere invertir
    X'X a mano). X ya debe incluir la columna de unos para el intercepto.
    Devuelve [alfa, beta_1, beta_2, ...]."""
    coeficientes, *_ = np.linalg.lstsq(X, y, rcond=None)
    return coeficientes


def calcular_atribucion_ipsa(
    df_acciones: pd.DataFrame, df_macro: pd.DataFrame, ventana: int = VENTANA_ATRIBUCION_IPSA,
) -> pd.DataFrame:
    """Atribución del retorno diario de ECH (proxy del IPSA) a 3 factores
    globales (cobre, S&P 500, USD/CLP), vía regresión OLS de VENTANA
    móvil re-estimada cada día:

        R_ECH = α + β_cobre·R_cobre + β_SP500·R_SP500 + β_USDCLP·R_USDCLP + ε

    Para el día t, α y los β se estiman SOLO con los `ventana` días hábiles
    ANTERIORES a t (t-ventana .. t-1) — nunca con el día t mismo ni con
    datos futuros, así que el retorno predicho de t es walk-forward, no
    look-ahead. Ese α/β se aplica luego a los retornos REALES observados de
    los factores en t para obtener la contribución de cada uno; el residual
    es lo que sobra. Por construcción, para cada fila:

        α + contrib_cobre + contrib_sp500 + contrib_usdclp + residual == retorno_ech

    siempre, exactamente (no es una propiedad que haya que validar aparte,
    es cómo se define el residual).

    También agrega z-scores de cada retorno de factor y del residual,
    calculados contra la distribución de los `ventana` días hábiles
    anteriores a cada fecha (mismo criterio walk-forward que los β) — un
    |z_residual| > 2 es la señal de "movimiento local inusual, no explicado
    por estos 3 factores globales"."""
    df = _retornos_atribucion_ipsa(df_acciones, df_macro)
    fechas = df.index
    n = len(df)

    X_todo = np.column_stack([np.ones(n), df["cobre"].to_numpy(), df["sp500"].to_numpy(), df["usdclp"].to_numpy()])
    y_todo = df["ech"].to_numpy()

    filas = []
    for i in range(ventana, n):
        X_ventana = X_todo[i - ventana:i]
        y_ventana = y_todo[i - ventana:i]
        alfa, b_cobre, b_sp500, b_usdclp = _ols(X_ventana, y_ventana)

        _, r_cobre, r_sp500, r_usdclp = X_todo[i]
        contrib_cobre = b_cobre * r_cobre
        contrib_sp500 = b_sp500 * r_sp500
        contrib_usdclp = b_usdclp * r_usdclp
        predicho = alfa + contrib_cobre + contrib_sp500 + contrib_usdclp
        real = y_todo[i]

        filas.append({
            "fecha": fechas[i],
            "retorno_ech": real,
            "retorno_cobre": r_cobre,
            "retorno_sp500": r_sp500,
            "retorno_usdclp": r_usdclp,
            "alfa": alfa,
            "beta_cobre": b_cobre,
            "beta_sp500": b_sp500,
            "beta_usdclp": b_usdclp,
            "contrib_cobre": contrib_cobre,
            "contrib_sp500": contrib_sp500,
            "contrib_usdclp": contrib_usdclp,
            "retorno_predicho": predicho,
            "residual": real - predicho,
        })

    resultado = pd.DataFrame(filas).set_index("fecha")

    # Z-scores walk-forward: contra la media/desv. estándar de los `ventana`
    # valores anteriores a cada fecha (shift(1) antes del rolling, para que
    # el valor de hoy nunca entre en su propia distribución de referencia).
    for columna, z_columna in [
        ("retorno_cobre", "z_cobre"), ("retorno_sp500", "z_sp500"),
        ("retorno_usdclp", "z_usdclp"), ("residual", "z_residual"),
    ]:
        previos = resultado[columna].shift(1)
        media = previos.rolling(ventana).mean()
        desv = previos.rolling(ventana).std()
        resultado[z_columna] = (resultado[columna] - media) / desv

    return resultado


def validar_atribucion_out_of_sample(
    df_acciones: pd.DataFrame, df_macro: pd.DataFrame, frac_in_sample: float = 0.7,
) -> dict:
    """Validación out-of-sample del modelo de 3 factores: separa el
    histórico disponible en el primer `frac_in_sample` (in-sample) y el
    resto (out-of-sample) EN ORDEN CRONOLÓGICO (no al azar, para no filtrar
    información futura al in-sample). Estima α/β UNA SOLA VEZ con los datos
    in-sample, los aplica a los retornos de los factores en el período
    out-of-sample, y compara el retorno predicho contra el real de ese
    período — reporta R² y correlación de Pearson tal cual salgan, sin
    ocultar un resultado bajo (que sería, en sí mismo, información válida
    sobre qué tan bien generaliza el modelo)."""
    df = _retornos_atribucion_ipsa(df_acciones, df_macro)
    n = len(df)
    corte = int(n * frac_in_sample)

    in_sample = df.iloc[:corte]
    out_of_sample = df.iloc[corte:]
    if len(in_sample) < 30 or len(out_of_sample) < 30:
        return {"suficientes_datos": False}

    X_in = np.column_stack([
        np.ones(len(in_sample)), in_sample["cobre"].to_numpy(),
        in_sample["sp500"].to_numpy(), in_sample["usdclp"].to_numpy(),
    ])
    y_in = in_sample["ech"].to_numpy()
    alfa, b_cobre, b_sp500, b_usdclp = _ols(X_in, y_in)

    y_real_oos = out_of_sample["ech"].to_numpy()
    y_pred_oos = (
        alfa
        + b_cobre * out_of_sample["cobre"].to_numpy()
        + b_sp500 * out_of_sample["sp500"].to_numpy()
        + b_usdclp * out_of_sample["usdclp"].to_numpy()
    )

    residuos_oos = y_real_oos - y_pred_oos
    ss_res = float(np.sum(residuos_oos ** 2))
    ss_tot = float(np.sum((y_real_oos - y_real_oos.mean()) ** 2))
    r2_oos = 1 - ss_res / ss_tot if ss_tot > 0 else None
    correlacion_oos = float(np.corrcoef(y_pred_oos, y_real_oos)[0, 1]) if np.std(y_pred_oos) > 0 else None

    return {
        "suficientes_datos": True,
        "n_in_sample": len(in_sample),
        "n_out_of_sample": len(out_of_sample),
        "fecha_inicio_oos": out_of_sample.index[0].date(),
        "fecha_fin_oos": out_of_sample.index[-1].date(),
        "coeficientes_in_sample": {
            "alfa": float(alfa), "beta_cobre": float(b_cobre),
            "beta_sp500": float(b_sp500), "beta_usdclp": float(b_usdclp),
        },
        "r2_oos": r2_oos,
        "correlacion_oos": correlacion_oos,
    }
