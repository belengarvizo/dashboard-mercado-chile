"""
Lógica de "Laboratorio Financiero": frontera media-varianza (con varias
familias de restricciones), Línea de Mercado de Capitales y CAPM/alfa de
Jensen sobre un universo de hasta 50 acciones del S&P 500.

Vive fuera de app/dashboard.py (sin llamadas a Streamlit) para poder testear
la optimización y las estadísticas de forma aislada, y para no duplicar la
pestaña "Optimización de Portafolios" ya existente (que resuelve un problema
más simple, de 2 casos, sobre un universo Chile+EEUU distinto).
"""

import numpy as np
import pandas as pd
from scipy.optimize import linprog, minimize

from market_data import calcular_retornos_reales, calcular_capm_regresion, matriz_retornos_alineados

N_RUEDAS_ANIO = 252


# ============================================================
# Preparación de datos
# ============================================================


def preparar_datos_laboratorio(
    df_precios: pd.DataFrame, tickers: list, fecha_inicio, fecha_fin, min_obs: int = 60,
) -> dict:
    """Alinea retornos para los tickers pedidos dentro de la ventana, excluye
    los que no tienen historia suficiente (advertencia, no error) y devuelve
    la matriz de retornos lista para optimizar."""
    df_precios = df_precios.assign(fecha=pd.to_datetime(df_precios["fecha"]))
    fecha_inicio_ts = pd.Timestamp(fecha_inicio)
    fecha_fin_ts = pd.Timestamp(fecha_fin)

    tickers_validos, tickers_excluidos = [], []
    for ticker in tickers:
        datos = df_precios[df_precios["ticker"] == ticker].sort_values("fecha").set_index("fecha")
        datos = datos[(datos.index >= fecha_inicio_ts) & (datos.index <= fecha_fin_ts)]
        n_obs = len(calcular_retornos_reales(datos["precio_cierre"], datos["volumen"]).dropna())
        if n_obs >= min_obs:
            tickers_validos.append(ticker)
        else:
            tickers_excluidos.append((ticker, n_obs))

    df_retornos = matriz_retornos_alineados(df_precios, tickers_validos, fecha_inicio_ts, fecha_fin_ts)

    return {
        "df_retornos": df_retornos,
        "tickers_validos": list(df_retornos.columns),
        "tickers_excluidos": tickers_excluidos,
        "fecha_inicio": fecha_inicio_ts,
        "fecha_fin": fecha_fin_ts,
        "n_observaciones": len(df_retornos),
    }


def diagnosticar_cobertura(df_precios: pd.DataFrame, tickers: list, fecha_inicio, fecha_fin) -> dict:
    """Diagnóstico de transparencia para la UI: cuántas sesiones bursátiles
    "teóricas" hay en la ventana y cuántas se pierden por ticker antes de
    llegar a la matriz de retornos alineada. Puramente informativo — NO
    afecta el cálculo de la frontera/CAPM, solo lo explica.

    "Sesiones teóricas" se toma de los retornos reales de ^GSPC en la
    ventana (el S&P 500 no tiene precio congelado, y coincide con el
    calendario NYSE oficial), en vez de un calendario externo, para no
    agregar una dependencia nueva solo para este diagnóstico."""
    df_precios = df_precios.assign(fecha=pd.to_datetime(df_precios["fecha"]))
    fecha_inicio = pd.Timestamp(fecha_inicio)
    fecha_fin = pd.Timestamp(fecha_fin)

    sp500 = df_precios[df_precios["ticker"] == "^GSPC"].sort_values("fecha").set_index("fecha")
    sp500 = sp500[(sp500.index >= fecha_inicio) & (sp500.index <= fecha_fin)]
    sesiones_teoricas = set(calcular_retornos_reales(sp500["precio_cierre"], sp500["volumen"]).dropna().index)

    filas = []
    for ticker in tickers:
        datos = df_precios[df_precios["ticker"] == ticker].sort_values("fecha").set_index("fecha")
        datos = datos[(datos.index >= fecha_inicio) & (datos.index <= fecha_fin)]
        retornos_ticker = set(calcular_retornos_reales(datos["precio_cierre"], datos["volumen"]).dropna().index)
        faltantes = sesiones_teoricas - retornos_ticker
        if faltantes:
            filas.append({"Ticker": ticker, "Días perdidos": len(faltantes)})

    df_diag = (
        pd.DataFrame(filas).sort_values("Días perdidos", ascending=False).reset_index(drop=True)
        if filas else pd.DataFrame(columns=["Ticker", "Días perdidos"])
    )

    return {"sesiones_teoricas": len(sesiones_teoricas), "tabla": df_diag}


def estadisticas_activos(df_retornos: pd.DataFrame, sector_por_ticker: dict, empresa_por_ticker: dict) -> pd.DataFrame:
    """Retorno esperado, volatilidad y varianza anualizados de cada activo."""
    mu = df_retornos.mean() * N_RUEDAS_ANIO
    vol = df_retornos.std() * (N_RUEDAS_ANIO ** 0.5)
    return pd.DataFrame({
        "Empresa": [empresa_por_ticker.get(t, t) for t in df_retornos.columns],
        "Sector": [sector_por_ticker.get(t, "Otro") for t in df_retornos.columns],
        "Retorno esperado": mu,
        "Volatilidad": vol,
        "Varianza": vol ** 2,
        "Observaciones": df_retornos.count(),
    })


def matriz_covarianza_anual(df_retornos: pd.DataFrame) -> pd.DataFrame:
    return df_retornos.cov() * N_RUEDAS_ANIO


def matriz_covarianza_diagonal(cov: pd.DataFrame) -> pd.DataFrame:
    """Ω_diag: conserva solo las varianzas (diagonal); todas las covarianzas
    fuera de la diagonal quedan en cero — la frontera "ingenua" de la tarea."""
    diag = np.diag(np.diag(cov.to_numpy()))
    return pd.DataFrame(diag, index=cov.index, columns=cov.columns)


def contar_por_sector(tickers: list, sector_por_ticker: dict) -> dict:
    conteo = {}
    for t in tickers:
        s = sector_por_ticker.get(t, "Otro")
        conteo[s] = conteo.get(s, 0) + 1
    return conteo


def resumen_sectorial(pesos: pd.Series, sector_por_ticker: dict) -> pd.Series:
    df = pesos.rename("peso").to_frame()
    df["sector"] = [sector_por_ticker.get(t, "Otro") for t in df.index]
    return df.groupby("sector")["peso"].sum()


# ============================================================
# Optimización: solución cerrada (sin restricciones de signo/límite)
# ============================================================

def _resolver_cerrado(mu: np.ndarray, cov: np.ndarray, rf: float | None = None) -> dict | None:
    """Solución matricial cerrada de Markowitz (Merton, 1972) SIN
    restricciones de signo ni límite por activo — la única familia de casos
    donde existe una solución exacta en forma cerrada (con venta corta
    libre, sin cotas ±X% ni piso sectorial, la restricción de desigualdad
    desaparece y basta álgebra lineal). Si Ω no es invertible o está mal
    condicionada (activos casi colineales), se regulariza con un término de
    Tikhonov ínfimo antes de fallar — se documenta con la clave
    "regularizado" en vez de cambiar la metodología silenciosamente."""
    n = len(mu)
    ones = np.ones(n)
    regularizado = False

    cov_inv = None
    try:
        cov_inv = np.linalg.inv(cov)
        if np.linalg.cond(cov) > 1e12:
            cov_inv = None
    except np.linalg.LinAlgError:
        pass

    if cov_inv is None:
        eps = 1e-8 * float(np.trace(cov)) / n
        try:
            cov_inv = np.linalg.inv(cov + eps * np.eye(n))
            regularizado = True
        except np.linalg.LinAlgError:
            return None

    A = float(ones @ cov_inv @ ones)
    B = float(ones @ cov_inv @ mu)
    C = float(mu @ cov_inv @ mu)
    D = A * C - B ** 2
    if A <= 0 or D <= 0:
        return None

    resultado = {
        "w_minvar": cov_inv @ ones / A,
        "cov_inv": cov_inv, "A": A, "B": B, "C": C, "D": D,
        "regularizado": regularizado,
    }

    if rf is not None:
        excess = mu - rf * ones
        denom = float(ones @ cov_inv @ excess)
        if abs(denom) > 1e-12:
            resultado["w_tangencia"] = cov_inv @ excess / denom

    return resultado


def _peso_frontera_cerrado(cerrado: dict, mu: np.ndarray, r: float) -> np.ndarray:
    A, B, C, D = cerrado["A"], cerrado["B"], cerrado["C"], cerrado["D"]
    ones = np.ones(len(mu))
    return cerrado["cov_inv"] @ (((C - B * r) / D) * ones + ((A * r - B) / D) * mu)


# ============================================================
# Optimización: restringida (SLSQP) — límite ±X%, sin venta corta y/o piso sectorial
# ============================================================

def _bounds(n: int, permitir_short: bool, limite_abs: float | None) -> list[tuple]:
    if limite_abs is not None:
        lo = -limite_abs if permitir_short else 0.0
        return [(lo, limite_abs)] * n
    if permitir_short:
        return [(-1.0, 1.0)] * n
    return [(0.0, 1.0)] * n


def _retorno_maximo_alcanzable(
    mu: np.ndarray, bounds: list[tuple], restriccion_sector: tuple[np.ndarray, float] | None = None,
) -> float:
    """max w@mu sujeto a sum(w)=1, lo_i <= w_i <= hi_i, y (si se pasa) un
    piso sectorial sum(w[idx]) >= peso_min -- una LP simple, resuelta
    exacto con linprog en vez de con SLSQP (mucho más barato: linprog en
    ~127 variables tarda milisegundos).

    Sirve para acotar el extremo superior de la curva de la frontera: sin
    esto, _frontera_slsqp le pide a SLSQP retornos objetivo por encima de
    lo que las restricciones realmente permiten (ej. mu.max() de un solo
    activo, cuando hay un tope por activo y/o un piso sectorial que lo
    hacen inalcanzable) -- SLSQP no falla rápido en esos casos, agota
    cientos de iteraciones buscando un punto que no existe (medido: ~93%
    del tiempo de una frontera restrictiva se iba en objetivos infactibles
    antes de este recorte -- tanto con tope por activo como, aparte, con
    piso sectorial sin tope por activo, que es un caso distinto y hay que
    acotar aparte porque no lo cubre un simple tope por activo)."""
    n = len(mu)
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)

    A_ub, b_ub = None, None
    if restriccion_sector is not None:
        idx, peso_min = restriccion_sector
        fila = np.zeros(n)
        fila[idx] = -1.0  # -sum(w[idx]) <= -peso_min  <=>  sum(w[idx]) >= peso_min
        A_ub, b_ub = [fila], [-peso_min]

    res = linprog(
        -mu, A_ub=A_ub, b_ub=b_ub, A_eq=[np.ones(n)], b_eq=[1.0],
        bounds=list(zip(lo, hi)), method="highs",
    )
    if not res.success:
        # No debería pasar si w_minvar ya fue factible con estos mismos
        # bounds/restricciones -- de todos modos, mu.max() (el
        # comportamiento anterior) es un fallback seguro, nunca más
        # restrictivo que la realidad.
        return float(mu.max())
    return float(-res.fun)


def _restriccion_suma_uno(n: int) -> dict:
    """sum(w) = 1, con su jacobiano exacto (vector de unos) -- se arma una
    vez por llamada y se reutiliza en las 3 funciones SLSQP de abajo."""
    return {"type": "eq", "fun": lambda w: np.sum(w) - 1.0, "jac": lambda w: np.ones(n)}


def _resolver_slsqp(mu, cov, bounds, restricciones_extra, w0, ftol: float = 1e-9) -> np.ndarray | None:
    n = len(w0)
    restr = [_restriccion_suma_uno(n)] + list(restricciones_extra)
    # Objetivo = varianza del portafolio, w^T @ Cov @ w -> gradiente exacto
    # 2 @ Cov @ w (Cov es simétrica). Pasarlo via jac= evita que SLSQP lo
    # estime por diferencias finitas (n evaluaciones extra del objetivo
    # por cada iteración, solo para aproximar el gradiente).
    res = minimize(
        lambda w: w @ cov @ w, w0, jac=lambda w: 2 * cov @ w,
        method="SLSQP", bounds=bounds, constraints=restr,
        options={"maxiter": 500, "ftol": ftol},
    )
    return res.x if res.success else None


def _tangencia_slsqp(mu, cov, rf, bounds, restricciones_extra, w0, ftol: float = 1e-9) -> np.ndarray | None:
    n = len(w0)
    restr = [_restriccion_suma_uno(n)] + list(restricciones_extra)

    def _sharpe_negativo(w):
        ret = w @ mu
        var = w @ cov @ w
        vol = var ** 0.5 if var > 0 else 0.0
        return -(ret - rf) / vol if vol > 1e-12 else 1e6

    def _sharpe_negativo_jac(w):
        # f(w) = -(w@mu - rf) / sqrt(w@cov@w). Por regla del cociente,
        # con V = sqrt(w@cov@w) y dV/dw = (cov@w)/V:
        # df/dw = -mu/V + (w@mu - rf) * (cov@w) / V^3
        ret = w @ mu
        var = w @ cov @ w
        vol = var ** 0.5 if var > 0 else 0.0
        if vol <= 1e-12:
            return np.zeros(n)
        return -mu / vol + (ret - rf) * (cov @ w) / (vol ** 3)

    res = minimize(
        _sharpe_negativo, w0, jac=_sharpe_negativo_jac,
        method="SLSQP", bounds=bounds, constraints=restr,
        options={"maxiter": 500, "ftol": ftol},
    )
    return res.x if res.success else None


def _frontera_slsqp(mu, cov, bounds, restricciones_extra, retorno_minvar, retorno_max, n_puntos, w0) -> list[np.ndarray]:
    objetivos = [retorno_minvar] if retorno_max <= retorno_minvar else np.linspace(retorno_minvar, retorno_max, n_puntos)
    puntos = []
    # Warm start: cada punto de la curva parte de la solución del punto
    # anterior (no siempre de pesos iguales) -- puntos vecinos de una
    # frontera eficiente tienen soluciones parecidas, así que el
    # optimizador necesita muchas menos iteraciones para converger que
    # arrancando desde cero cada vez. Si un punto falla, el siguiente
    # sigue partiendo del último punto que sí convergió (no de w0 crudo).
    w_actual = w0
    for r in objetivos:
        restr_r = list(restricciones_extra) + [
            {"type": "eq", "fun": lambda w, r=r: w @ mu - r, "jac": lambda w: mu}
        ]
        w = _resolver_slsqp(mu, cov, bounds, restr_r, w_actual)
        if w is not None and np.all(np.isfinite(w)) and abs(np.sum(w) - 1.0) < 1e-4:
            puntos.append(w)
            w_actual = w
    return puntos


# ============================================================
# Frontera: función unificada usada por las 5 variantes de la tarea
# ============================================================

def calcular_frontera(
    df_retornos: pd.DataFrame,
    rf: float,
    permitir_short: bool = True,
    limite_abs: float | None = None,
    restriccion_sectorial: tuple | None = None,
    cov_optimizacion: pd.DataFrame | None = None,
    n_puntos: int = 30,
) -> dict | None:
    """Frontera media-varianza (GMV + tangencia + curva eficiente) sobre
    df_retornos, con las restricciones dadas.

    - permitir_short=True, limite_abs=None, restriccion_sectorial=None →
      solución cerrada exacta (Merton), la "frontera base".
    - Cualquier otra combinación (límite ±X%, sin venta corta, piso
      sectorial) introduce restricciones de desigualdad → se resuelve con
      SLSQP (QP no lineal pero convexo).
    - Si se pasa cov_optimizacion (ej. la matriz diagonal "ingenua"), los
      PESOS se calculan con esa matriz, pero retorno/volatilidad de cada
      punto SIEMPRE se evalúan con la covarianza real de df_retornos — así
      se puede comparar "optimizar ignorando covarianzas" vs. el riesgo
      real resultante.

    restriccion_sectorial = (lista_de_tickers, peso_minimo_conjunto) — la
    suma de los pesos de esos tickers debe ser >= peso_minimo_conjunto.
    """
    tickers = list(df_retornos.columns)
    n = len(tickers)
    mu = df_retornos.mean().to_numpy() * N_RUEDAS_ANIO
    cov_real = df_retornos.cov().to_numpy() * N_RUEDAS_ANIO
    cov_opt = cov_optimizacion.to_numpy() if cov_optimizacion is not None else cov_real

    if not np.all(np.isfinite(mu)) or not np.all(np.isfinite(cov_real)) or not np.all(np.isfinite(cov_opt)):
        return None

    restricciones_extra = []
    restriccion_sector_lp = None
    if restriccion_sectorial is not None:
        tickers_grupo, peso_min = restriccion_sectorial
        idx_arr = np.array([tickers.index(t) for t in tickers_grupo if t in tickers])
        if len(idx_arr):
            jac_sector = np.zeros(n)
            jac_sector[idx_arr] = 1.0
            restricciones_extra.append({
                "type": "ineq",
                "fun": lambda w, idx=idx_arr, pm=peso_min: np.sum(w[idx]) - pm,
                "jac": lambda w, g=jac_sector: g,
            })
            restriccion_sector_lp = (idx_arr, peso_min)

    sin_restricciones = limite_abs is None and permitir_short and not restricciones_extra
    regularizado = False

    if sin_restricciones:
        cerrado = _resolver_cerrado(mu, cov_opt, rf)
        if cerrado is None:
            return None
        regularizado = cerrado["regularizado"]
        w_minvar = cerrado["w_minvar"]
        w_tangencia = cerrado.get("w_tangencia")
        ret_max = float(mu.max())
    else:
        bounds = _bounds(n, permitir_short, limite_abs)
        w0 = np.ones(n) / n
        w_minvar = _resolver_slsqp(mu, cov_opt, bounds, restricciones_extra, w0)
        if w_minvar is None:
            return None
        w_tangencia = _tangencia_slsqp(mu, cov_opt, rf, bounds, restricciones_extra, w0)
        # Acotado a lo que estos bounds realmente permiten alcanzar, no al
        # retorno de un solo activo sin restricciones (ver
        # _retorno_maximo_alcanzable) -- clave para que _frontera_slsqp no
        # pierda tiempo en objetivos infactibles.
        ret_max = _retorno_maximo_alcanzable(mu, bounds, restriccion_sector_lp)

    if w_tangencia is not None and (not np.all(np.isfinite(w_tangencia)) or abs(np.sum(w_tangencia) - 1.0) > 1e-3):
        w_tangencia = None

    ret_minvar_opt = float(w_minvar @ mu)
    # La curva de la frontera se dibuja hasta el mayor retorno alcanzable
    # entre los activos individuales — pero con venta corta, M (tangencia)
    # puede tener un retorno MAYOR que cualquier activo individual (apalanca
    # largos contra cortos), y en ese caso la curva quedaría cortada antes
    # de llegar a M aunque M sí sea parte de la misma frontera matemática.
    # Se extiende el rango (con margen del 15%) solo cuando eso ocurre, para
    # que M quede visiblemente sobre la curva dibujada — esto NO cambia
    # cómo se calcula ningún punto, solo hasta dónde se piden puntos.
    if w_tangencia is not None:
        ret_tangencia_bruto = float(w_tangencia @ mu)
        if np.isfinite(ret_tangencia_bruto) and ret_tangencia_bruto > ret_max:
            ret_max = ret_tangencia_bruto * 1.15

    if sin_restricciones:
        objetivos = [ret_minvar_opt] if ret_max <= ret_minvar_opt else np.linspace(ret_minvar_opt, ret_max, n_puntos)
        pesos_frontera = [_peso_frontera_cerrado(cerrado, mu, r) for r in objetivos]
        pesos_frontera = [w for w in pesos_frontera if np.all(np.isfinite(w)) and abs(np.sum(w) - 1.0) < 1e-4]
    else:
        pesos_frontera = _frontera_slsqp(mu, cov_opt, bounds, restricciones_extra, ret_minvar_opt, ret_max, n_puntos, w0)

    def _metricas(w):
        # Siempre con la covarianza REAL, incluso en el caso "ingenuo".
        ret = float(w @ mu)
        var = float(w @ cov_real @ w)
        vol = var ** 0.5 if var > 0 else 0.0
        return ret, vol

    ret_minvar, vol_minvar = _metricas(w_minvar)
    puntos_frontera = [_metricas(w) for w in pesos_frontera]

    resultado = {
        "tickers": tickers,
        "mu_anual": pd.Series(mu, index=tickers),
        "cov_anual": pd.DataFrame(cov_real, index=tickers, columns=tickers),
        "w_minvar": pd.Series(w_minvar, index=tickers),
        "ret_minvar": ret_minvar,
        "vol_minvar": vol_minvar,
        "frontera": [(vol, ret) for ret, vol in puntos_frontera],
        "pesos_frontera": [pd.Series(w, index=tickers) for w in pesos_frontera],
        "regularizado": regularizado,
        "permitir_short": permitir_short,
        "limite_abs": limite_abs,
    }
    if w_tangencia is not None:
        ret_t, vol_t = _metricas(w_tangencia)
        resultado["w_tangencia"] = pd.Series(w_tangencia, index=tickers)
        resultado["ret_tangencia"] = ret_t
        resultado["vol_tangencia"] = vol_t
        resultado["sharpe_tangencia"] = (ret_t - rf) / vol_t if vol_t > 0 else None

    return resultado


# ============================================================
# CAPM, LMC y asignación óptima
# ============================================================

def retornos_portafolio(df_retornos: pd.DataFrame, pesos: pd.Series) -> pd.Series:
    """Serie diaria de retornos de un portafolio de pesos fijos."""
    pesos_alineados = pesos.reindex(df_retornos.columns).to_numpy()
    return pd.Series(df_retornos.to_numpy() @ pesos_alineados, index=df_retornos.index)


def preparar_regresion_capm(
    retornos_p: pd.Series, precio_mercado: pd.Series, volumen_mercado: pd.Series, rf_anual_serie: pd.Series,
) -> pd.DataFrame:
    """Alinea el portafolio, el mercado (ej. ^GSPC) y la Rf (reindexada por
    fecha con forward-fill, ya que la Rf no cambia todos los días) en un
    único DataFrame de retornos diarios, listo para la regresión CAPM."""
    retornos_mercado = calcular_retornos_reales(precio_mercado, volumen_mercado)
    conjunto = pd.concat(
        [retornos_p, retornos_mercado], axis=1, join="inner", keys=["portafolio", "mercado"],
    ).dropna()
    rf_diaria = rf_anual_serie.reindex(conjunto.index, method="ffill") / N_RUEDAS_ANIO
    return pd.concat([conjunto, rf_diaria.rename("rf")], axis=1).dropna()


def linea_mercado_capitales(rf: float, ret_tangencia: float, vol_tangencia: float, vol_max: float, n_puntos: int = 50):
    """(xs, ys, pendiente) de la LMC: E(Rc) = Rf + [(E(RM)-Rf)/σM] × σc."""
    pendiente = (ret_tangencia - rf) / vol_tangencia if vol_tangencia > 0 else 0.0
    xs = np.linspace(0, vol_max, n_puntos)
    ys = rf + pendiente * xs
    return xs, ys, pendiente


def sharpe_treynor(ret_anual: float, vol_anual: float, rf_anual: float, beta: float | None):
    sharpe = (ret_anual - rf_anual) / vol_anual if vol_anual > 0 else None
    treynor = (ret_anual - rf_anual) / beta if beta not in (None, 0) else None
    return sharpe, treynor


def asignacion_optima(ret_tangencia: float, rf: float, vol_tangencia: float, c: float) -> float | None:
    """x* = (E[RM] - Rf) / (c × σM²): fracción óptima del capital invertida
    en el portafolio de tangencia M según la aversión al riesgo c."""
    var_tangencia = vol_tangencia ** 2
    if var_tangencia <= 0 or c <= 0:
        return None
    return (ret_tangencia - rf) / (c * var_tangencia)
