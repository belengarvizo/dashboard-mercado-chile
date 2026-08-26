"""
Modelo Probit de recesión de EEUU: reproduce el modelo original del usuario
(recesion.py, predictores g_lag y p_lag sobre base_recesion_us.xlsx) y lo
extiende con 4 series de FRED (UNRATE, ICSA, BAA10Y, NFCI) para evaluar si
mejoran la sensibilidad del modelo original (32.14% con corte 0.5).

Las series de FRED se descargan por scripts/actualizar_bcch.py (cron diario,
sin API key) y se leen desde la tabla series_macro. Ninguna de las 4 series
tiene historia hasta 1962 en FRED (a diferencia de g y p del Excel original):
UNRATE arranca en 1948, ICSA en 1967, NFCI en 1971, BAA10Y recién en 1986 -
por eso el modelo extendido queda con una muestra más corta (limitada por
BAA10Y, la más reciente) que el modelo original.
"""

import os

import pandas as pd
import statsmodels.api as sm

BASE_RECESION_XLSX = os.path.join(os.path.dirname(__file__), "base_recesion_us.xlsx")

# columna interna -> nombre exacto tal como queda guardado en series_macro
# (ver SERIES_RECESION_FRED en scripts/actualizar_bcch.py).
SERIES_FRED_RECESION = {
    "unrate": "Tasa de desempleo de EEUU (UNRATE)",
    "icsa": "Solicitudes iniciales de seguro de desempleo de EEUU (ICSA)",
    "baa10y": "Spread bonos corporativos Baa vs Treasury 10 años (BAA10Y)",
    "nfci": "Índice de condiciones financieras nacionales de Chicago Fed (NFCI)",
}

PREDICTORES_ORIGINAL = ["g_lag", "p_lag"]
PREDICTORES_EXTENDIDO = PREDICTORES_ORIGINAL + [f"{col}_lag" for col in SERIES_FRED_RECESION]


def _cargar_base_original() -> pd.DataFrame:
    df = pd.read_excel(BASE_RECESION_XLSX)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def _agregar_series_fred_trimestral(df_series_macro: pd.DataFrame) -> pd.DataFrame:
    """Agrega las 4 series de FRED a frecuencia trimestral (promedio dentro
    de cada trimestre), indexado por período trimestral (no por una fecha
    exacta: base_recesion_us.xlsx marca cada trimestre con el 1er día de su
    ÚLTIMO mes -ej. 1962-03-01 para Q1-, mientras que to_period("Q") de
    pandas por defecto ancla al PRIMER mes -1962-01-01-; alinear por período
    evita ese desfase)."""
    df_series_macro = df_series_macro.copy()
    df_series_macro["fecha"] = pd.to_datetime(df_series_macro["fecha"])
    df_series_macro["valor"] = df_series_macro["valor"].astype(float)
    df_series_macro["trimestre"] = df_series_macro["fecha"].dt.to_period("Q")

    resultado = None
    for columna, nombre in SERIES_FRED_RECESION.items():
        serie = df_series_macro[df_series_macro["nombre"] == nombre]
        promedio_trimestral = serie.groupby("trimestre")["valor"].mean().rename(columna)
        resultado = promedio_trimestral.to_frame() if resultado is None else resultado.join(promedio_trimestral, how="outer")

    return resultado


def construir_dataset(df_series_macro: pd.DataFrame) -> pd.DataFrame:
    """Reproduce el dataset de recesion.py (g_lag, p_lag) y le agrega las
    versiones rezagadas (shift(1), mismo criterio que el original) de las
    4 series de FRED, alineadas por trimestre."""
    df = _cargar_base_original()
    df["trimestre"] = df["fecha"].dt.to_period("Q")
    fred = _agregar_series_fred_trimestral(df_series_macro)
    df = df.merge(fred, on="trimestre", how="left").drop(columns="trimestre")

    df["g_lag"] = df["g"].shift(1)
    df["p_lag"] = df["p"].shift(1)
    for columna in SERIES_FRED_RECESION:
        df[f"{columna}_lag"] = df[columna].shift(1)

    return df


def _metricas_matriz_confusion(y_real: pd.Series, y_pred: pd.Series) -> dict:
    matriz = pd.crosstab(y_real, y_pred, rownames=["Real"], colnames=["Predicho"])
    for valor in (0, 1):
        if valor not in matriz.index:
            matriz.loc[valor] = 0
        if valor not in matriz.columns:
            matriz[valor] = 0
    matriz = matriz.sort_index().sort_index(axis=1)

    vn, fp = matriz.loc[0, 0], matriz.loc[0, 1]
    fn, vp = matriz.loc[1, 0], matriz.loc[1, 1]

    return {
        "matriz": matriz,
        "precision_global": (vn + vp) / (vn + fp + fn + vp),
        "sensibilidad": vp / (vp + fn) if (vp + fn) > 0 else float("nan"),
        "especificidad": vn / (vn + fp) if (vn + fp) > 0 else float("nan"),
    }


def estimar_modelo(df: pd.DataFrame, predictores: list[str]) -> dict:
    """Estima un Probit con los predictores dados (mismo criterio que
    recesion.py: dropna sobre las columnas usadas, corte 0.5 para la
    matriz de confusión)."""
    datos = df.dropna(subset=predictores + ["R"]).reset_index(drop=True)
    X = sm.add_constant(datos[predictores])
    y = datos["R"]
    resultado = sm.Probit(y, X).fit(disp=0)

    prob_predicha = resultado.predict(X)
    y_pred = (prob_predicha >= 0.5).astype(int)
    metricas = _metricas_matriz_confusion(y, y_pred)

    return {
        "resultado": resultado,
        "n_obs": len(datos),
        "fecha_min": datos["fecha"].min(),
        "fecha_max": datos["fecha"].max(),
        "fechas": datos["fecha"],
        "prob_predicha": prob_predicha,
        "y_real": y,
        **metricas,
    }


def desglose_por_episodio(modelo: dict) -> pd.DataFrame:
    """Agrupa los trimestres con R=1 de un modelo ya estimado en episodios
    de recesión consecutivos (ej. los 6 trimestres de 2008-09 son un solo
    episodio, no 6 episodios sueltos) y devuelve, por episodio, la
    probabilidad máxima que el modelo le asignó a alguno de sus trimestres
    -- que es exactamente el corte más alto con el que ese episodio
    todavía se detectaría (cualquier corte más exigente lo pierde por
    completo)."""
    fechas = modelo["fechas"].reset_index(drop=True)
    y_real = modelo["y_real"].reset_index(drop=True)
    prob = modelo["prob_predicha"].reset_index(drop=True)

    en_recesion = y_real == 1
    grupo = (en_recesion != en_recesion.shift()).cumsum()

    filas = []
    for _, sub in pd.DataFrame({"fecha": fechas, "real": y_real, "prob": prob, "grupo": grupo}).groupby("grupo"):
        if sub["real"].iloc[0] != 1:
            continue
        inicio, fin = sub["fecha"].min(), sub["fecha"].max()
        etiqueta = str(inicio.year) if inicio.year == fin.year else f"{inicio.year}-{str(fin.year)[-2:]}"
        prob_maxima = sub["prob"].max()
        filas.append({
            "Episodio": etiqueta,
            "Probabilidad máxima alcanzada": prob_maxima,
            "Corte mínimo para detectarlo": f"≤{prob_maxima:.2%}",
        })

    return pd.DataFrame(filas).set_index("Episodio")


def corte_optimo_por_precision(modelo: dict) -> dict:
    """Barre cortes de 0.01 a 0.99 (mismo criterio que recesion.py) y
    devuelve el que maximiza la precisión global, junto con la sensibilidad
    que ese corte produce -- para chequear si el corte "objetivamente
    óptimo" por este criterio es o no un corte razonable para detectar
    recesiones (con una base rate baja de recesiones, maximizar precisión
    global puede terminar eligiendo un corte tan alto que la sensibilidad
    resultante sea 0%)."""
    y_real = modelo["y_real"].reset_index(drop=True)
    prob = modelo["prob_predicha"].reset_index(drop=True)

    mejor_corte, mejor_precision, mejor_sensibilidad = None, -1.0, None
    for paso in range(1, 100):
        corte = paso / 100
        y_pred = (prob >= corte).astype(int)
        metricas = _metricas_matriz_confusion(y_real, y_pred)
        if metricas["precision_global"] > mejor_precision:
            mejor_corte = corte
            mejor_precision = metricas["precision_global"]
            mejor_sensibilidad = metricas["sensibilidad"]

    return {"corte": mejor_corte, "precision_global": mejor_precision, "sensibilidad": mejor_sensibilidad}


def comparar_modelos(df_series_macro: pd.DataFrame) -> dict:
    """Compara tres versiones del modelo:
    - "original": g_lag y p_lag, muestra completa (1962 en adelante).
    - "extendido": los 6 predictores (agrega las 4 series de FRED), acotado
      a 1986+ porque BAA10Y no existe antes.
    - "original_restringido": g_lag y p_lag otra vez, pero restringido a
      EXACTAMENTE las mismas observaciones (mismas fechas) que "extendido".
      Sin este tercer modelo, comparar "original" vs "extendido" confunde
      dos efectos distintos: la mejora podría venir de las variables nuevas,
      o simplemente de que el subperíodo 1986-2026 tenga recesiones más
      fáciles de predecir en general. "original_restringido" aísla el efecto
      de las variables nuevas, manteniendo fijo el período."""
    df = construir_dataset(df_series_macro)

    modelo_extendido = estimar_modelo(df, PREDICTORES_EXTENDIDO)
    df_mismo_periodo = df[df["fecha"].isin(modelo_extendido["fechas"])]

    return {
        "dataset": df,
        "original": estimar_modelo(df, PREDICTORES_ORIGINAL),
        "original_restringido": estimar_modelo(df_mismo_periodo, PREDICTORES_ORIGINAL),
        "extendido": modelo_extendido,
    }
