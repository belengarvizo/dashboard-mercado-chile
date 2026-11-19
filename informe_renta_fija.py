"""
Informe en PDF de la sección «Renta Fija»: qué pasó con los bonos en un período, por qué, y qué lectura equivocada evitar.

PARA QUÉ EXISTE
    La pantalla muestra los números; el informe explica el mecanismo detrás y se puede mandar a alguien que no abrió el
    dashboard. Está pensado para un comité de inversiones o un área que necesita entender renta fija, no solo mirarla.

EL MOLDE DE CADA HALLAZGO
    Tres partes, siempre:
      1. Qué pasó, con el número real y su fecha.
      2. Por qué, con la cuenta hecha: casi todo el movimiento de un bono se explica por su duración y el cambio de la tasa.
      3. Qué error evitar, nombrando la confusión típica. Esa tercera parte es la que enseña.

DE DÓNDE SALEN LOS NÚMEROS
    De las mismas funciones que usa la pantalla (renta_fija.py y renta_fija_ui.py), no de un cálculo paralelo: si la
    pantalla y el informe difirieran, uno de los dos estaría mal. `calcular()` deja todo en un diccionario, y `generar()`
    solo lo escribe. Así las pruebas pueden comprobar los números sin abrir el PDF.

LÍMITES QUE EL INFORME DECLARA
    - La duración se mide con el último año de datos diarios y se aplica a períodos más cortos: es una aproximación de
      primer orden, no una identidad contable.
    - La base no tiene el rendimiento ni el cupón devengado de cada ETF, así que lo que no explica la duración se informa
      junto («cupones, crédito y lo no explicado») en vez de inventar una descomposición más fina.
    - No hay recomendaciones de compra ni de venta: el informe no conoce el horizonte, el perfil ni las restricciones de
      quien lo lee.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import estructura_tasas as et
import informe_base as ib
import renta_fija as rf
import renta_fija_ui as rfui
from catalogo_renta_fija import ETFS_RENTA_FIJA

PERIODOS = {"Último mes": 30, "Últimos 3 meses": 90, "Último año": 365}
# Los ETFs que se grafican: el tramo corto, el medio, el largo y el de crédito, que es donde se ve la diferencia.
ETFS_DEL_GRAFICO = ["SHY", "IEF", "TLT", "HYG"]
CAMBIOS_DE_SENSIBILIDAD = (-1.0, -0.5, 0.5, 1.0)  # puntos porcentuales

# ---------------------------------------------------------------------------
# Comparabilidad: fecha de corte y ventana común
# ---------------------------------------------------------------------------
# Todos los ETFs del catálogo cotizan en la misma bolsa y los baja el mismo proceso, así que con datos sanos comparten
# su último precio. Una rueda de diferencia se tolera (una descarga que falló un día) y mueve la ventana de todos a lo
# más un día; más que eso es una serie rota, y se excluye de la comparación en vez de arrastrar a las demás.
TOLERANCIA_RUEDAS = 1
# FRED publica la curva H.15 el día hábil siguiente: 1 a 2 ruedas detrás de los precios es lo normal. Más de 5 (el mismo
# umbral de atraso que usa la pantalla) y la atribución se omite, en vez de llevar la comparación semanas atrás.
MAX_RUEDAS_ATRASO_CURVA = rfui.DIAS_HABILES_DE_ATRASO
# Desde cuántos días hábiles entre el último precio y la fecha de corte se advierte en la portada.
DIAS_HABILES_SIN_ADVERTENCIA = 1

ESTADO_CALCULABLE = "calculable"


def _a_fecha(valor) -> pd.Timestamp:
    return pd.Timestamp(valor).normalize()


def _resolver_corte(precios: pd.DataFrame, fecha_corte) -> tuple[pd.Timestamp | None, bool]:
    """(fecha de corte, si fue pedida). Sin pedirla, es la última fecha con precio de algún ETF del catálogo: nunca el
    reloj del computador, para que las cifras dependan solo de los datos."""
    if fecha_corte is not None:
        return _a_fecha(fecha_corte), True
    ultimas = [precios[t].last_valid_index() for t in ETFS_RENTA_FIJA if t in precios]
    ultimas = [u for u in ultimas if u is not None]
    return (_a_fecha(max(ultimas)) if ultimas else None), False


def _recortar_al_corte(macro: pd.DataFrame, precios: pd.DataFrame, corte: pd.Timestamp | None):
    """Nada posterior a la fecha de corte entra al cálculo."""
    if corte is None:
        return macro, precios
    macro = macro[pd.to_datetime(macro["fecha"]) <= corte] if len(macro) else macro
    precios = precios[precios.index <= corte] if len(precios) else precios
    return macro, precios


def _calendario_de_ruedas(precios: pd.DataFrame) -> pd.DatetimeIndex:
    """Las ruedas bursátiles, sacadas de los propios datos: días hábiles en que cotizó algún ETF del catálogo.

    Así los feriados de la bolsa quedan fuera sin una lista escrita a mano (que vencería cada año). Su límite: después
    del último precio no hay datos, y ahí los feriados no se pueden ver."""
    tickers = [t for t in ETFS_RENTA_FIJA if t in precios]
    if not tickers or precios.empty:
        return pd.DatetimeIndex([])
    con_precio = precios[tickers].notna().any(axis=1)
    habiles = pd.Series(precios.index.dayofweek < 5, index=precios.index)
    return pd.DatetimeIndex(precios.index[con_precio & habiles])


def _ruedas_entre(ruedas: pd.DatetimeIndex, desde, hasta) -> int:
    """Ruedas r con desde < r ≤ hasta."""
    return int(((ruedas > desde) & (ruedas <= hasta)).sum())


def _comparabilidad(macro: pd.DataFrame, precios: pd.DataFrame, dias: int) -> dict:
    """Qué ETFs se comparan, entre qué fechas exactas y cuáles quedan fuera, en pasos que no dependen unos de otros en
    círculo:

      1. Frescura: cada ETF contra el último precio de todos (U*), en ruedas. Pasa la tolerancia o se excluye.
      2. Tasas: cada plazo de referencia contra el más reciente de la curva. Un plazo atrasado deja sin atribución solo
         a los ETFs que lo usan; la curva entera atrasada respecto de los precios deja sin atribución a todos.
      3. Fin E: la última fecha con precio de TODOS los ETFs vigentes y dato de TODAS las tasas vigentes que se usan.
      4. Historia: un ETF sin precio antes de E − período se excluye (si ninguno lo tiene, el período no es calculable).
      5. Inicio S: la última fecha con esos mismos datos en E − período o antes.

    Retornos y cambios de tasa se miden entre S y E, las mismas dos fechas para todos. No se interpola ni se rellena."""
    ruedas = _calendario_de_ruedas(precios)
    ultimas = {t: precios[t].last_valid_index() for t in ETFS_RENTA_FIJA if t in precios}
    excluidos = []
    for t, u in ultimas.items():
        if u is None:
            excluidos.append({"ETF": t, "ultima_fecha": None, "ruedas": None, "motivo": "sin precios hasta la fecha de corte"})
    con_datos = {t: u for t, u in ultimas.items() if u is not None}
    resultado = {"ruedas": ruedas, "vigentes": [], "excluidos": excluidos, "ultimo_precio": None, "inicio": None,
                 "fin": None, "estado": {}, "atribucion": False, "ultima_curva": None, "motivo_sin_ventana": None}
    if not con_datos:
        resultado["motivo_sin_ventana"] = "no hay precios de ETFs hasta la fecha de corte"
        return resultado
    ultimo = max(con_datos.values())
    resultado["ultimo_precio"] = ultimo

    # 1. Frescura de cada ETF.
    vigentes = []
    for t, u in con_datos.items():
        atraso = _ruedas_entre(ruedas, u, ultimo)
        if atraso <= TOLERANCIA_RUEDAS:
            vigentes.append(t)
        else:
            excluidos.append({"ETF": t, "ultima_fecha": u, "ruedas": atraso,
                              "motivo": f"último precio el {ib.fecha(u)}, {atraso} ruedas antes que el resto"})

    # 2. Tasas de referencia de los vigentes.
    plazos = sorted({float(ETFS_RENTA_FIJA[t]["plazo_referencia"]) for t in vigentes})
    tasas = {}
    for p in plazos:
        serie = rfui._rendimiento_del_tesoro(macro, p).dropna()
        tasas[p] = serie[~serie.index.duplicated(keep="last")]
    ultimas_tasas = {p: s.index[-1] for p, s in tasas.items() if len(s)}
    estado = {}
    plazos_vigentes = []
    if ultimas_tasas:
        ultima_curva = max(ultimas_tasas.values())
        resultado["ultima_curva"] = ultima_curva
        atraso_curva = _ruedas_entre(ruedas, ultima_curva, ultimo)
        if atraso_curva > MAX_RUEDAS_ATRASO_CURVA:
            motivo_curva = (f"no calculable: la curva del Tesoro llega hasta el {ib.fecha(ultima_curva)}, "
                            f"{atraso_curva} ruedas antes que los precios")
        else:
            motivo_curva = None
            for p in plazos:
                u = ultimas_tasas.get(p)
                if u is not None and _ruedas_entre(ruedas, u, ultima_curva) <= TOLERANCIA_RUEDAS:
                    plazos_vigentes.append(p)
    else:
        motivo_curva = "no calculable: no hay datos de la curva del Tesoro hasta la fecha de corte"
    for t in vigentes:
        p = float(ETFS_RENTA_FIJA[t]["plazo_referencia"])
        if motivo_curva:
            estado[t] = motivo_curva
        elif p in plazos_vigentes:
            estado[t] = ESTADO_CALCULABLE
        else:
            u = ultimas_tasas.get(p)
            estado[t] = (f"no calculable: la tasa a {int(p)} años no tiene datos desde el {ib.fecha(u)}" if u is not None
                         else f"no calculable: no hay datos de la tasa a {int(p)} años")
    resultado["atribucion"] = bool(plazos_vigentes)

    # 3. Fin común E.
    def fechas_con_datos(tickers):
        if not tickers:
            return pd.DatetimeIndex([])
        disponible = precios[tickers].notna().all(axis=1)
        for p in plazos_vigentes:
            disponible &= tasas[p].reindex(precios.index).notna()
        return precios.index[disponible]

    comunes = fechas_con_datos(vigentes)
    if len(comunes) == 0:
        resultado.update(vigentes=vigentes, estado=estado,
                         motivo_sin_ventana="no hay ninguna fecha con precio de todos los ETFs vigentes y sus tasas")
        return resultado
    fin = comunes[-1]
    objetivo = fin - pd.Timedelta(days=dias)

    # 4. Historia suficiente para el período.
    con_historia = [t for t in vigentes if precios[t].first_valid_index() <= objetivo]
    if not con_historia:
        resultado.update(vigentes=vigentes, estado=estado, fin=fin,
                         motivo_sin_ventana=f"ningún ETF tiene precios desde antes del {ib.fecha(objetivo)}")
        return resultado
    for t in vigentes:
        if t not in con_historia:
            excluidos.append({"ETF": t, "ultima_fecha": con_datos[t], "ruedas": 0,
                              "motivo": f"sin precios antes del {ib.fecha(objetivo)}, el inicio del período"})
            estado.pop(t, None)

    # 5. Inicio común S.
    candidatos = fechas_con_datos(con_historia)
    candidatos = candidatos[candidatos <= objetivo]
    if len(candidatos) == 0:
        resultado.update(vigentes=con_historia, estado=estado, fin=fin,
                         motivo_sin_ventana=f"no hay una fecha común con todos los datos en o antes del {ib.fecha(objetivo)}")
        return resultado
    resultado.update(vigentes=con_historia, estado=estado, fin=fin, inicio=candidatos[-1])
    return resultado


# ---------------------------------------------------------------------------
# Cálculo (sin PDF): todo lo que el informe va a decir
# ---------------------------------------------------------------------------
def _en_o_antes(serie: pd.Series, fecha):
    """Último valor de la serie en esa fecha o antes, con su fecha. None si no hay ninguno."""
    previos = serie[serie.index <= fecha]
    return (float(previos.iloc[-1]), previos.index[-1]) if len(previos) else None


def _tramo(serie: pd.Series, dias: int):
    """(valor al inicio, valor al final, fecha de inicio, fecha de fin) del período, o None si falta historia."""
    serie = serie.dropna().sort_index()
    if len(serie) < 2:
        return None
    fin, fecha_fin = float(serie.iloc[-1]), serie.index[-1]
    inicio = _en_o_antes(serie, fecha_fin - pd.Timedelta(days=dias))
    if inicio is None:
        return None
    return inicio[0], fin, inicio[1], fecha_fin


def _valor_en(serie: pd.Series, fecha) -> float | None:
    """El valor EXACTO de esa fecha, o None. No toma el día anterior ni interpola: la ventana ya eligió fechas con dato."""
    if fecha is None:
        return None
    serie = serie.dropna()
    serie = serie[~serie.index.duplicated(keep="last")]
    return float(serie.loc[fecha]) if fecha in serie.index else None


def _tabla_de_etfs(macro: pd.DataFrame, precios: pd.DataFrame, ventana: dict) -> pd.DataFrame:
    """Una fila por ETF que se compara: lo que rindió entre S y E y la parte que explica su duración.

    `esperado` = −duración × cambio de la tasa de referencia (en puntos porcentuales) ENTRE LAS MISMAS DOS FECHAS que el
    retorno. `resto` es lo que queda: todo lo que el modelo de duración no incluye. Las métricas que no dependen del
    período (duración medida, volatilidad, caída máxima) usan los datos hasta E, para que toda la fila quede fechada ahí."""
    vigentes, inicio, fin = ventana["vigentes"], ventana["inicio"], ventana["fin"]
    if not vigentes:
        return pd.DataFrame()
    hasta = fin if fin is not None else ventana["ultimo_precio"]
    macro_e, precios_e = _recortar_al_corte(macro, precios, hasta)
    resumen = rfui._resumen_de_etfs(precios_e, macro_e, hasta)  # la fecha solo marca el atraso de la pantalla
    filas = []
    for ticker in vigentes:
        if resumen is None or ticker not in resumen.index:
            continue
        datos, fila = ETFS_RENTA_FIJA[ticker], resumen.loc[ticker]
        p_inicio, p_fin = _valor_en(precios[ticker], inicio), _valor_en(precios[ticker], fin)
        retorno = (p_fin / p_inicio - 1) * 100 if inicio is not None and p_inicio and p_fin is not None else None
        if inicio is None:
            estado = f"no calculable: {ventana['motivo_sin_ventana']}"
        else:
            estado = ventana["estado"].get(ticker, ESTADO_CALCULABLE)
        cambio = None
        if estado == ESTADO_CALCULABLE:
            tasa = rfui._rendimiento_del_tesoro(macro, datos["plazo_referencia"]) * 100  # a puntos porcentuales
            y_inicio, y_fin = _valor_en(tasa, inicio), _valor_en(tasa, fin)
            cambio = y_fin - y_inicio if y_inicio is not None and y_fin is not None else None
        duracion = fila["Duración medida (años)"]
        esperado = None if cambio is None or pd.isna(duracion) else -duracion * cambio
        filas.append({
            "ETF": ticker, "Grupo": datos["grupo"], "Plazo de referencia": datos["plazo_referencia"],
            "Retorno del período (%)": retorno,
            "Duración medida (años)": duracion, "Error de la duración": fila["Error de la duración"],
            "R² con la tasa": fila["R² con la tasa"],
            "Cambio de la tasa (pp)": cambio,
            "Explicado por la duración (%)": esperado,
            "Resto (%)": None if esperado is None or retorno is None else retorno - esperado,
            "Volatilidad (%)": fila["Volatilidad (%)"], "Caída máxima 1 año (%)": fila["Caída máxima 1 año (%)"],
            "ultima_fecha": fila["ultima_fecha"],
            "Estado de la atribución": estado,
        })
    tabla = pd.DataFrame(filas).set_index("ETF") if filas else pd.DataFrame()
    if len(tabla):
        numericas = ["Retorno del período (%)", "Cambio de la tasa (pp)", "Explicado por la duración (%)", "Resto (%)"]
        tabla[numericas] = tabla[numericas].apply(pd.to_numeric, errors="coerce")
    return tabla


def _curva(macro: pd.DataFrame, ventana: dict) -> dict | None:
    """Curva del Tesoro completa en el inicio y en el fin de la ventana común, en %, por plazo en años.

    Si en alguna de las dos fechas falta un plazo, no hay gráfico: usar la curva de otro día volvería a desalinear las
    fechas del informe."""
    inicio, fin = ventana["inicio"], ventana["fin"]
    if inicio is None or fin is None or not ventana["atribucion"]:
        return None
    pivote = rfui._pivote_curva(macro)
    pivote = pivote[~pivote.index.duplicated(keep="last")]
    if inicio not in pivote.index or fin not in pivote.index:
        return None
    curva_inicio, curva_fin = pivote.loc[inicio], pivote.loc[fin]
    if curva_inicio.isna().any() or curva_fin.isna().any():
        return None
    return {"inicio": curva_inicio, "fin": curva_fin, "fecha_inicio": inicio, "fecha_fin": fin,
            "cambio": curva_fin - curva_inicio}


def _chile(macro: pd.DataFrame) -> dict:
    """Tasas chilenas de hoy y la inflación implícita a 10 años (BCP menos BCU, las dos en la misma fecha)."""
    bcp = rfui._serie(macro, rfui.NOMBRE_BCP10).dropna()
    bcu = rfui._serie(macro, rfui.NOMBRE_BCU10).dropna()
    tpm = rfui._ultimo(macro, rfui.NOMBRE_TPM_CHILE)
    fed = rfui._ultimo(macro, rfui.NOMBRE_TASA_EEUU) if hasattr(rfui, "NOMBRE_TASA_EEUU") else rfui._ultimo(macro, rfui.NOMBRE_TPM_EEUU)
    par = rfui._ultimo_comun(bcp, bcu)
    return {
        "bcp10": par[0] if par else None, "bcu10": par[1] if par else None,
        "fecha_curva_chile": par[2] if par else None,
        "inflacion_implicita": (par[0] - par[1]) if par else None,
        "tpm": tpm[0] if tpm else None, "fecha_tpm": tpm[1] if tpm else None,
        "fed": fed[0] if fed else None, "fecha_fed": fed[1] if fed else None,
        "diferencial": (tpm[0] - fed[0]) if tpm and fed else None,
    }


def _credito(macro: pd.DataFrame, dias: int) -> dict | None:
    baa = rfui._serie(macro, rfui.NOMBRE_BAA10Y).dropna()
    t = _tramo(baa, dias)
    if t is None:
        return None
    recorte = baa[baa.index >= t[3] - pd.Timedelta(days=dias)]
    return {
        "inicio": t[0], "fin": t[1], "cambio": t[1] - t[0], "fecha_inicio": t[2], "fecha_fin": t[3],
        "maximo": float(recorte.max()), "fecha_maximo": recorte.idxmax(),
    }


def _ultima(serie: pd.Series):
    serie = serie.dropna()
    return serie.index[-1] if len(serie) else None


def calcular(macro: pd.DataFrame, precios: pd.DataFrame, dias: int, nombre_periodo: str, fecha_corte=None) -> dict:
    """Todo lo que el informe va a decir, ya calculado. No arma PDF: así las pruebas pueden comprobar los números.

    `fecha_corte`: nada posterior entra al cálculo. Sin ella, es la última fecha con precio de un ETF. Con los mismos
    datos, el mismo período y la misma fecha de corte, el resultado es siempre el mismo (no depende del reloj)."""
    precios = precios if precios is not None else pd.DataFrame()
    corte, solicitada = _resolver_corte(precios, fecha_corte)
    macro, precios = _recortar_al_corte(macro, precios, corte)
    ventana = _comparabilidad(macro, precios, dias)
    etfs = _tabla_de_etfs(macro, precios, ventana)
    pivote = rfui._pivote_curva(macro)
    fechas = {
        "corte": corte, "corte_solicitado": solicitada,
        "inicio": ventana["inicio"], "fin": ventana["fin"],
        "ruedas": _ruedas_entre(ventana["ruedas"], ventana["inicio"], ventana["fin"]) if ventana["inicio"] is not None else None,
        "motivo_sin_ventana": ventana["motivo_sin_ventana"],
        "ultima_por_fuente": {
            "ETFs (Yahoo Finance)": ventana["ultimo_precio"],
            "Curva del Tesoro (FRED)": _ultima(pivote.max(axis=1)) if len(pivote.columns) else None,
            "Spread Baa (FRED)": _ultima(rfui._serie(macro, rfui.NOMBRE_BAA10Y)),
            "Banco Central de Chile": max(
                [u for u in (_ultima(rfui._serie(macro, n)) for n in (rfui.NOMBRE_BCP10, rfui.NOMBRE_BCU10, rfui.NOMBRE_TPM_CHILE))
                 if u is not None], default=None),
        },
        "dias_habiles_de_atraso": (int(np.busday_count(ventana["ultimo_precio"].date(), corte.date()))
                                   if corte is not None and ventana["ultimo_precio"] is not None else None),
    }
    credito = _credito(macro, dias)
    datos = {
        "periodo": nombre_periodo, "dias": dias,
        "etfs": etfs,
        "excluidos": ventana["excluidos"],
        "fechas": fechas,
        "curva": _curva(macro, ventana),
        "credito": credito,
        "chile": _chile(macro),
        "hasta": ventana["fin"] if ventana["fin"] is not None else ventana["ultimo_precio"],
        "precios": precios,
        "contexto": _contexto(macro, precios, ventana, credito, etfs),
    }
    # Para auditar: cada conclusión con su nivel de evidencia y las condiciones que se evaluaron.
    datos["evaluaciones"] = _evaluaciones(datos)
    datos["afirmaciones"] = _afirmaciones(datos)
    return datos


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
def _grafico_retornos(precios: pd.DataFrame, tickers: list[str], inicio, fin):
    """Base 100 en el inicio S de la ventana común, hasta su fin E: las mismas fechas que el Cuadro 1."""
    def dibujar(ax):
        for ticker in [t for t in ETFS_DEL_GRAFICO if t in tickers and t in precios]:
            serie = precios[ticker].dropna()
            serie = serie[(serie.index >= inicio) & (serie.index <= fin)]
            if len(serie) < 2 or serie.index[0] != inicio:
                continue
            ax.plot(serie.index, serie / serie.iloc[0] * 100, linewidth=1.3, label=ticker)
        ax.set_ylabel("Base 100 al inicio", fontsize=7.5, color=ib.INK)
        ax.legend(fontsize=7, frameon=False, ncol=4)
        ax.tick_params(axis="x", labelrotation=0)

    return ib.grafico(dibujar, alto_cm=5.6)


def _grafico_curva(curva: dict):
    def dibujar(ax):
        plazos = list(curva["fin"].index)
        ax.plot(plazos, curva["inicio"].values, linewidth=1.3, linestyle="--", color=ib.MUTED,
                label=f"Al {ib.fecha(curva['fecha_inicio'])}")
        ax.plot(plazos, curva["fin"].values, linewidth=1.7, color=ib.NAVY, label=f"Al {ib.fecha(curva['fecha_fin'])}")
        ax.set_xlabel("Plazo (años)", fontsize=7.5, color=ib.INK)
        ax.set_ylabel("Tasa (%)", fontsize=7.5, color=ib.INK)
        ax.legend(fontsize=7, frameon=False)

    return ib.grafico(dibujar, alto_cm=5.4)


def _grafico_atribucion(etfs: pd.DataFrame):
    datos = etfs.dropna(subset=["Retorno del período (%)", "Explicado por la duración (%)"])

    def dibujar(ax):
        posiciones = range(len(datos))
        ancho = 0.38
        ax.bar([p - ancho / 2 for p in posiciones], datos["Explicado por la duración (%)"], ancho,
               color=ib.NAVY, label="Explicado por la duración")
        ax.bar([p + ancho / 2 for p in posiciones], datos["Retorno del período (%)"], ancho,
               color=ib.GOLD, label="Retorno real")
        ax.axhline(0, color=ib.RULE, linewidth=0.8)
        ax.set_xticks(list(posiciones))
        ax.set_xticklabels(list(datos.index), fontsize=7)
        ax.set_ylabel("% en el período", fontsize=7.5, color=ib.INK)
        ax.legend(fontsize=7, frameon=False, ncol=2)

    return ib.grafico(dibujar, alto_cm=5.4)


# ---------------------------------------------------------------------------
# El informe
# ---------------------------------------------------------------------------
def _frase_del_resto(etfs: pd.DataFrame, dias: int) -> str | None:
    """Observación sobre el «resto» de la atribución, solo si los datos la sostienen.

    Cuando el resto es positivo en todos los ETFs y su tamaño anualizado se parece al rendimiento de un bono, lo que
    está capturando es el cupón devengado: la duración mide el efecto del cambio de tasa y no el paso del tiempo."""
    resto = etfs["Resto (%)"].dropna()
    if len(resto) < 5 or not (resto > 0).all():
        return None
    anualizado = resto.mean() * 365.0 / dias
    if not 1.0 <= anualizado <= 12.0:
        return None
    return (
        f"El «resto» es positivo en los {len(resto)} ETFs y promedia {ib.pct(resto.mean(), 2)} en el período, equivalente a "
        f"{ib.pct(anualizado, 1)} anual: del orden de lo que rinden estos bonos. Eso apunta a que es sobre todo el **cupón "
        "devengado**, que la duración no puede capturar porque solo mide el efecto del cambio de tasa, no el paso del tiempo. "
        "Dicho de otro modo: aunque las tasas no se movieran, un bono igual rinde."
    )


# ---------------------------------------------------------------------------
# Conclusiones condicionadas a los datos
# ---------------------------------------------------------------------------
# Cada frase interpretativa del informe sale de una función que primero evalúa sus condiciones con las cifras del
# período; si no se cumplen, la frase no se escribe o se reemplaza por una que dice qué no se puede concluir. Cada
# afirmación guarda su nivel de evidencia y las condiciones evaluadas (para auditarla), pero el PDF no muestra
# etiquetas: el grado de certeza va en los verbos.
#
# Tres distinciones que estas reglas respetan:
#   - Un cambio OBSERVADO (la tasa subió 6 pb) es un hecho, no una estimación: no tiene «significancia». Lo que se
#     evalúa es si es material y qué tan grande es frente a la variabilidad habitual de un período de ese largo.
#   - La sensibilidad a tasas (β) SÍ es una estimación, con error estándar y un R² que describe el AJUSTE HISTÓRICO
#     diario del último año. El R² no mide qué parte del retorno del período explican las tasas ni prueba causalidad.
#   - Que lo anticipado por la sensibilidad coincida con el retorno es COMPATIBILIDAD con el modelo, no identificación
#     de una causa. Ningún texto dice que las tasas «causaron» un resultado.
#
# UMBRALES. Son hipótesis de trabajo, no estándares estadísticos ni regulatorios. Un movimiento es material si supera
# un PISO ECONÓMICO fijo y, además, una fracción κ de su variabilidad típica para el largo de la ventana:
#     umbral = max(piso, κ · σ_diaria · √ruedas)
# Con κ = 0,25 y cambios aproximadamente de paseo aleatorio, cerca de una quinta parte de los períodos de ese largo
# tendría un cambio menor: esos se informan como «prácticamente sin cambio». Así el mismo piso de 5 pb sirve en un mes
# (donde suele mandar el piso) y no convierte en «alza» un cambio de 6 pb en un año (donde manda la variabilidad).
UMBRALES = {
    "pb_sin_cambio": 0.5,             # presentación: bajo esto el cambio redondea a 0 pb
    "pb_tasa": 5.0,                   # económico: 5 pb en una duración de 6,5 años ≈ 0,33% de precio
    "pb_spread": 5.0,                 # económico: 5 pb en una duración de spread de ~7 años ≈ 0,35% de precio
    "kappa": 0.25,                    # estadístico descriptivo: fracción del desvío típico del horizonte
    "pp_retorno": 0.10,               # económico: piso de un retorno o una brecha material (puntos porcentuales)
    "anios_sensibilidad": 1.0,        # económico: 1 año de diferencia ante 25 pb ≈ 0,25 pp de retorno
    "errores_estandar": 2.0,          # estadístico: separación mínima de una estimación respecto de cero o de otra
    "r2_minimo": 0.5,                 # ajuste histórico mínimo para tomar la sensibilidad como precisa
    "error_relativo_maximo": 0.10,    # error estándar / sensibilidad: con 10%, ±2 errores son ±20% del efecto
    "tolerancia_consistente": 0.5,    # |retorno − anticipado| ≤ 0,5·|retorno| (con piso): «consistente»
    "tolerancia_parcial": 1.0,        # |retorno − anticipado| ≤ 1,0·|retorno| (con piso): «da cuenta de una parte»
}

NIVEL_HALLAZGO = "hallazgo observado"
NIVEL_INTERPRETACION = "interpretación consistente"
NIVEL_INSUFICIENTE = "evidencia insuficiente"

SIN_CAMBIO, ESTABLE, SUBE, BAJA = "sin cambio", "prácticamente sin cambio", "sube", "baja"

# Exposición económica de cada grupo del catálogo. Solo dos fondos del Tesoro nominal son comparables POR PLAZO:
# el mismo grupo no basta (dos fondos de empresas pueden diferir en calidad de crédito).
EXPOSICION_POR_GRUPO = {
    "Tesoro EEUU": "bonos nominales del Tesoro de EEUU",
    "Mercado total": "una mezcla de bonos del Tesoro, hipotecarios de agencias y de empresas",
    "Empresas": "bonos de empresas con grado de inversión, con riesgo de crédito",
    "High yield": "bonos de empresas bajo grado de inversión, con riesgo de crédito alto",
    "Emergentes": "deuda en dólares de países emergentes, con riesgo soberano y de crédito",
    "Inflación": "bonos del Tesoro ligados a la inflación, que responden a tasas reales",
}
GRUPOS_COMPARABLES_POR_PLAZO = {"Tesoro EEUU"}
GRUPOS_CON_CREDITO = {"Mercado total", "Empresas", "High yield", "Emergentes"}


@dataclass(frozen=True)
class Afirmacion:
    clave: str
    nivel: str
    texto: str
    condiciones: tuple = ()


def _umbral(piso: float, sigma_diaria: float | None, ruedas: int | None) -> float:
    """max(piso, κ · σ_diaria · √ruedas); sin datos de variabilidad, el piso."""
    if sigma_diaria is None or not ruedas or not np.isfinite(sigma_diaria):
        return piso
    return max(piso, UMBRALES["kappa"] * sigma_diaria * float(np.sqrt(ruedas)))


def _clasificar_cambio(valor: float, umbral: float) -> str:
    if abs(valor) < UMBRALES["pb_sin_cambio"]:
        return SIN_CAMBIO
    if abs(valor) < umbral:
        return ESTABLE
    return SUBE if valor > 0 else BAJA


def _verbo_tasa(clase: str, pb: float) -> str:
    """La variación de una tasa en pb, con su equivalente en pp, y con dirección solo si es material."""
    if clase == SUBE:
        return f"subió {ib.num(abs(pb), 0)} pb ({ib.num(abs(pb) / 100, 2)} pp)"
    if clase == BAJA:
        return f"bajó {ib.num(abs(pb), 0)} pb ({ib.num(abs(pb) / 100, 2)} pp)"
    if clase == ESTABLE:
        return f"prácticamente no cambió ({ib.num(pb, 1, True)} pb)"
    return "no cambió (menos de 1 pb)"


def _desvio_de_cambios(serie: pd.Series, hasta, escala: float = 1.0) -> float | None:
    """Desvío estándar de los cambios diarios del último año hasta `hasta` (inclusive), en la unidad × escala."""
    s = serie.dropna()
    s = s[~s.index.duplicated(keep="last")]
    if hasta is not None:
        s = s[s.index <= hasta]
    cambios = s.diff().dropna().tail(rf.DIAS_HABILES_ANIO) * escala
    return float(cambios.std()) if len(cambios) >= rf.MINIMO_DE_OBSERVACIONES else None


def _lista(nombres: list[str]) -> str:
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _contexto(macro: pd.DataFrame, precios: pd.DataFrame, ventana: dict, credito: dict | None, etfs: pd.DataFrame) -> dict:
    """Lo que las reglas necesitan además de la tabla: variabilidades del último año (hasta el fin de la ventana),
    ruedas de la ventana y tasas de referencia al inicio."""
    inicio, fin = ventana["inicio"], ventana["fin"]
    ruedas = _ruedas_entre(ventana["ruedas"], inicio, fin) if inicio is not None and fin is not None else None
    pivote = rfui._pivote_curva(macro)
    pivote = pivote[~pivote.index.duplicated(keep="last")]
    sigma_plazo = {float(p): _desvio_de_cambios(pivote[p], fin, 100.0) for p in pivote.columns}
    sigma_pendiente = (_desvio_de_cambios(pivote[10.0] - pivote[2.0], fin, 100.0)
                       if 10.0 in pivote.columns and 2.0 in pivote.columns else None)
    sigma_spread = ruedas_spread = None
    if credito:
        baa = rfui._serie(macro, rfui.NOMBRE_BAA10Y).dropna()
        sigma_spread = _desvio_de_cambios(baa, credito["fecha_fin"], 100.0)
        ruedas_spread = int(((baa.index > credito["fecha_inicio"]) & (baa.index <= credito["fecha_fin"])).sum())
    tickers = [t for t in etfs.index if t in precios] if len(etfs) else []
    retornos = pd.DataFrame()
    tasa_inicio = {}
    if tickers and fin is not None:
        retornos = (precios.loc[precios.index <= fin, tickers].pct_change(fill_method=None) * 100).tail(rf.DIAS_HABILES_ANIO)
        for t in tickers:
            tasa = rfui._rendimiento_del_tesoro(macro, ETFS_RENTA_FIJA[t]["plazo_referencia"]) * 100
            tasa_inicio[t] = _valor_en(tasa, inicio)
    sigma_retorno = {t: float(retornos[t].dropna().std()) for t in retornos.columns if retornos[t].notna().sum() >= 30}
    return {"ruedas": ruedas, "dias": (fin - inicio).days if inicio is not None else None,
            "sigma_plazo": sigma_plazo, "sigma_pendiente": sigma_pendiente,
            "sigma_spread": sigma_spread, "ruedas_spread": ruedas_spread,
            "retornos": retornos, "sigma_retorno": sigma_retorno, "tasa_inicio": tasa_inicio}


# ---- Curva del Tesoro ------------------------------------------------------
def _afirmacion_curva(curva: dict | None, ctx: dict) -> Afirmacion:
    """Dirección de cada tramo (2, 5 y 10 años) y forma del movimiento: estable, paralelo, empinamiento, aplanamiento,
    torsión, con cambio de curvatura si el tramo medio se aparta de los extremos."""
    if curva is None:
        return Afirmacion("curva", NIVEL_INSUFICIENTE,
                          "**Tasas del Tesoro.** No es posible describir el movimiento de la curva del Tesoro en la ventana: la "
                          "curva completa no está disponible en sus dos fechas.")
    n, sp = ctx.get("ruedas"), ctx.get("sigma_plazo", {})
    d2, d5, d10 = (float(curva["cambio"][p]) * 100 for p in (2.0, 5.0, 10.0))
    t2, t5, t10 = (_umbral(UMBRALES["pb_tasa"], sp.get(p), n) for p in (2.0, 5.0, 10.0))
    pendiente = d10 - d2
    t_pend = _umbral(UMBRALES["pb_tasa"], ctx.get("sigma_pendiente"), n)
    c2, c10 = _clasificar_cambio(d2, t2), _clasificar_cambio(d10, t10)
    m2, m10 = c2 in (SUBE, BAJA), c10 in (SUBE, BAJA)
    nivel_medio = (d2 + d10) / 2
    detalle = f"la tasa a 2 años {_verbo_tasa(c2, d2)} y la de 10 años {_verbo_tasa(c10, d10)}"
    if abs(pendiente) >= t_pend:
        detalle_pendiente = (f"la pendiente entre ambos plazos {'aumentó' if pendiente > 0 else 'disminuyó'} "
                             f"{ib.num(abs(pendiente), 0)} pb")
    else:
        detalle_pendiente = "la pendiente entre ambos plazos prácticamente no cambió"

    if not m2 and not m10 and abs(pendiente) < t_pend:
        forma, texto = "estable", f"La curva del Tesoro prácticamente no se movió en la ventana: {detalle}."
    elif m2 and m10 and (d2 > 0) != (d10 > 0):
        forma = "torsión"
        texto = (f"La curva del Tesoro registró una torsión: {detalle}, de modo que {detalle_pendiente} "
                 f"({'empinamiento' if pendiente > 0 else 'aplanamiento'}).")
    elif abs(pendiente) < t_pend:
        forma = "paralelo"
        texto = (f"La curva del Tesoro se desplazó {'al alza' if nivel_medio > 0 else 'a la baja'} de forma aproximadamente "
                 f"paralela: {detalle}.")
    elif (m2 or m10) and abs(nivel_medio) >= min(t2, t10) and abs(pendiente) < 0.5 * abs(nivel_medio):
        # El nivel domina: describirlo como «se aplanó» escondería que toda la curva se movió en la misma dirección.
        cambio_forma = "empinamiento" if pendiente > 0 else "aplanamiento"
        forma = f"desplazamiento {'al alza' if nivel_medio > 0 else 'a la baja'} con {cambio_forma}"
        texto = (f"La curva del Tesoro se desplazó {'al alza' if nivel_medio > 0 else 'a la baja'}, con un leve {cambio_forma}: "
                 f"{detalle}, y {detalle_pendiente}.")
    else:
        forma = "empinamiento" if pendiente > 0 else "aplanamiento"
        if m2 and m10:  # los dos tramos se movieron en la misma dirección (la dirección opuesta es torsión)
            lider = "el tramo largo" if abs(d10) >= abs(d2) else "el tramo corto"
            contexto_nivel = f"en un contexto de {'alza' if d10 > 0 else 'baja'} de tasas, más intensa en {lider}"
        elif m2:
            contexto_nivel = f"por {'el alza' if d2 > 0 else 'la baja'} del tramo corto"
        elif m10:
            contexto_nivel = f"por {'el alza' if d10 > 0 else 'la baja'} del tramo largo"
        else:
            contexto_nivel = "sin que ninguno de los dos tramos se moviera de forma material por sí solo"
        texto = f"La curva del Tesoro se {'empinó' if pendiente > 0 else 'aplanó'} {contexto_nivel}: {detalle}, y {detalle_pendiente}."
    desvio_medio = d5 - (d2 + d10) / 2
    if abs(desvio_medio) >= t5:
        texto += (f" El tramo de 5 años no acompañó a los extremos ({ib.num(desvio_medio, 0, True)} pb respecto del promedio "
                  "de 2 y 10 años), lo que indica además un cambio de curvatura.")
    sigma10 = sp.get(10.0)
    if sigma10 and n and abs(d10) >= 2 * sigma10 * np.sqrt(n) and m10:
        texto += " El movimiento a 10 años fue amplio en relación con su variabilidad del último año."
    texto += f" Al {ib.fecha(curva['fecha_fin'])}, la tasa a 10 años se ubicaba en {ib.pct(float(curva['fin'][10.0]))}."
    condiciones = (("cambio 2 años (pb)", m2, round(d2, 2), round(t2, 2)), ("cambio 10 años (pb)", m10, round(d10, 2), round(t10, 2)),
                   ("cambio de pendiente (pb)", abs(pendiente) >= t_pend, round(pendiente, 2), round(t_pend, 2)), ("forma", True, forma, None))
    return Afirmacion("curva", NIVEL_HALLAZGO, "**Tasas del Tesoro.** " + texto, condiciones)


# ---- Crédito ---------------------------------------------------------------
def _clase_spread(credito: dict | None, ctx: dict) -> tuple[str | None, float | None, float | None]:
    if not credito:
        return None, None, None
    pb = float(credito["cambio"]) * 100
    umbral = _umbral(UMBRALES["pb_spread"], ctx.get("sigma_spread"), ctx.get("ruedas_spread"))
    return _clasificar_cambio(pb, umbral), pb, umbral


def _texto_spread(credito: dict, clase: str, pb: float) -> str:
    desde, hasta = ib.pct(float(credito["inicio"])), ib.pct(float(credito["fin"]))
    fechas = f"entre el {ib.fecha(credito['fecha_inicio'])} y el {ib.fecha(credito['fecha_fin'])}"
    if clase == SUBE:
        return (f"se amplió {ib.num(abs(pb), 0)} pb {fechas}, de {desde} a {hasta}. Un spread mayor indica que el mercado exige "
                "una compensación más alta por el riesgo de crédito y de liquidez de esos bonos.")
    if clase == BAJA:
        return (f"se comprimió {ib.num(abs(pb), 0)} pb {fechas}, de {desde} a {hasta}. Un spread menor indica que el mercado "
                "exige una compensación más baja por el riesgo de crédito y de liquidez de esos bonos.")
    if clase == ESTABLE:
        return f"prácticamente no cambió {fechas} ({ib.num(pb, 1, True)} pb, de {desde} a {hasta})."
    return f"no cambió {fechas} (se mantuvo en {hasta})."


def _afirmacion_credito(credito: dict | None, ctx: dict) -> Afirmacion:
    if not credito:
        return Afirmacion("credito", NIVEL_INSUFICIENTE,
                          "**Crédito.** No hay datos del spread de los bonos corporativos Baa para describir el riesgo de crédito.")
    clase, pb, umbral = _clase_spread(credito, ctx)
    texto = ("**Crédito.** El premio por riesgo de crédito (spread de los bonos corporativos Baa sobre el Tesoro a 10 años) "
             + _texto_spread(credito, clase, pb))
    return Afirmacion("credito", NIVEL_HALLAZGO, texto, (("cambio del spread (pb)", clase in (SUBE, BAJA), round(pb, 2), round(umbral, 2)),))


# ---- Atribución de cada ETF ------------------------------------------------
def _evaluar_atribucion(ticker: str, fila: pd.Series, ctx: dict, credito: dict | None) -> dict:
    """Compara el retorno del período (R) con lo que anticipaba la sensibilidad estimada (X = −β·Δy) y clasifica.

    No usa el cociente X/R (inestable con R cercano a cero): exige primero que R y X sean materiales, luego el mismo
    signo, y mide la diferencia en puntos porcentuales. La precisión de β (R² y error estándar) es una condición
    adicional, nunca la única."""
    u = UMBRALES
    n = ctx.get("ruedas")
    grupo = ETFS_RENTA_FIJA[ticker]["grupo"]
    R, X = fila["Retorno del período (%)"], fila["Explicado por la duración (%)"]
    beta, se, r2 = fila["Duración medida (años)"], fila["Error de la duración"], fila["R² con la tasa"]
    cambio = fila["Cambio de la tasa (pp)"]
    plazo = float(fila["Plazo de referencia"])
    estado = fila.get("Estado de la atribución", ESTADO_CALCULABLE)
    ev = {"ETF": ticker, "grupo": grupo, "retorno": R, "anticipado": X, "plazo": plazo, "r2": r2, "estado": estado,
          "cambio_pb": None if pd.isna(cambio) else float(cambio) * 100, "spread_pb": None, "condiciones": []}

    def cerrar(clase: str) -> dict:
        ev["clase"] = clase
        ev["nivel"] = {"consistente": NIVEL_INTERPRETACION, "parcial": NIVEL_INTERPRETACION,
                       "contraria": NIVEL_HALLAZGO, "sin_movimiento": NIVEL_HALLAZGO}.get(clase, NIVEL_INSUFICIENTE)
        ev["condiciones"] = tuple(ev["condiciones"])
        return ev

    if estado != ESTADO_CALCULABLE or pd.isna(R) or pd.isna(X) or pd.isna(beta) or pd.isna(cambio):
        return cerrar("no_calculable")
    if grupo == "Inflación":
        return cerrar("tasa_nominal")
    tau_y = _umbral(u["pb_tasa"], ctx.get("sigma_plazo", {}).get(plazo), n)
    tau_r = _umbral(u["pp_retorno"], ctx.get("sigma_retorno", {}).get(ticker), n)
    tau_x = max(tau_r, u["errores_estandar"] * (se if pd.notna(se) else 0.0) * abs(float(cambio)))
    ev.update(umbral_tasa_pb=tau_y, umbral_retorno=tau_r, diferencia=R - X)
    ev["condiciones"] += [("cambio de tasa material (pb)", abs(ev["cambio_pb"]) >= tau_y, round(ev["cambio_pb"], 2), round(tau_y, 2)),
                          ("retorno material (pp)", abs(R) >= tau_r, round(R, 4), round(tau_r, 4)),
                          ("efecto anticipado material (pp)", abs(X) >= tau_x, round(X, 4), round(tau_x, 4))]
    if abs(ev["cambio_pb"]) < tau_y:
        return cerrar("sin_movimiento" if abs(R) < tau_r else "tasa_quieta")
    if abs(X) < tau_x:
        return cerrar("efecto_pequeno")
    if abs(R) < tau_r:
        return cerrar("precio_quieto")
    ev["condiciones"].append(("mismo signo", (R > 0) == (X > 0), None, None))
    if (R > 0) != (X > 0):
        return cerrar("contraria")
    error = abs(R - X)
    ev["condiciones"].append(("|R − X| (pp)", error <= max(u["tolerancia_consistente"] * abs(R), tau_r), round(error, 4),
                              round(max(u["tolerancia_consistente"] * abs(R), tau_r), 4)))
    if error <= max(u["tolerancia_consistente"] * abs(R), tau_r):
        clase = "consistente"
    elif error <= max(u["tolerancia_parcial"] * abs(R), tau_r):
        clase = "parcial"
    else:
        return cerrar("magnitud")
    precisa = pd.notna(r2) and r2 >= u["r2_minimo"] and pd.notna(se) and beta and se / abs(beta) <= u["error_relativo_maximo"]
    ev["condiciones"].append(("sensibilidad precisa (R², error relativo)", bool(precisa), round(float(r2), 3) if pd.notna(r2) else None,
                              (u["r2_minimo"], u["error_relativo_maximo"])))
    if not precisa:
        return cerrar("imprecisa")
    if grupo in GRUPOS_CON_CREDITO:
        clase_s, pb_s, _ = _clase_spread(credito, ctx)
        ev["spread_pb"] = pb_s
        ev["condiciones"].append(("spread sin cambio material", clase_s not in (SUBE, BAJA), pb_s, None))
        if clase_s in (SUBE, BAJA):
            return cerrar("credito")
    return cerrar(clase)


def _frase_de_evaluacion(ev: dict) -> str:
    """Una frase por ETF para la lectura de la atribución (sección 2)."""
    t, clase = ev["ETF"], ev["clase"]
    R = ib.pct(ev["retorno"], 2, True) if pd.notna(ev["retorno"]) else None
    X = ib.pct(ev["anticipado"], 2, True) if pd.notna(ev["anticipado"]) else None
    tasa = f"su tasa de referencia a {int(ev['plazo'])} años"
    pb = f"{ib.num(ev['cambio_pb'], 0, True)} pb" if ev.get("cambio_pb") is not None else None
    dif = ib.num(abs(ev.get("diferencia", 0.0)), 2)
    if clase == "consistente":
        extra = " El modelo no incluye su riesgo de crédito." if ev["grupo"] in GRUPOS_CON_CREDITO else ""
        return f"{t} rindió {R}, en línea con el {X} que anticipaba su sensibilidad estimada ante el cambio de {pb} de {tasa}.{extra}"
    if clase == "parcial":
        return (f"{t} rindió {R}; su sensibilidad anticipaba {X}, en la misma dirección pero con una diferencia de {dif} pp, de modo "
                "que el movimiento de tasas da cuenta solo de una parte del resultado.")
    if clase == "magnitud":
        return (f"En {t}, el retorno ({R}) y lo anticipado ({X}) van en la misma dirección, pero difieren en {dif} pp, más de lo que "
                "permite considerarlos consistentes.")
    if clase == "contraria":
        return f"{t} rindió {R} pese a que su sensibilidad a tasas anticipaba {X}: el movimiento de tasas no da cuenta de su resultado."
    if clase == "sin_movimiento":
        return f"En {t}, ni {tasa} ({pb}) ni su precio ({R}) se movieron de forma material."
    if clase == "tasa_quieta":
        return (f"{t} rindió {R} con {tasa} prácticamente sin cambio ({pb}); su resultado no puede asociarse al movimiento de "
                "tasas.")
    if clase == "efecto_pequeno":
        return f"En {t}, el efecto anticipado por su sensibilidad ({X}) es demasiado pequeño para contrastarlo con su retorno ({R})."
    if clase == "precio_quieto":
        return f"La sensibilidad de {t} anticipaba {X}, pero su precio prácticamente no se movió ({R})."
    if clase == "imprecisa":
        return (f"{t} rindió {R} y su sensibilidad anticipaba {X}; la coincidencia no es concluyente porque la relación diaria con "
                f"{tasa} es débil o imprecisa (R² {ib.num(ev['r2'], 2)}).")
    if clase == "credito":
        return (f"{t} rindió {R} y su sensibilidad a tasas anticipaba {X}, pero el spread de crédito también se movió "
                f"({ib.num(ev['spread_pb'], 0, True)} pb): la coincidencia puede reflejar efectos que se compensan y no permite "
                "separarlos.")
    if clase == "tasa_nominal":
        return (f"La sensibilidad de {t} se mide contra la tasa nominal del Tesoro, mientras su precio responde a tasas reales; "
                "su atribución no se interpreta.")
    return f"{t}: atribución {ev['estado']}."


def _evaluaciones(datos: dict) -> list[dict]:
    etfs, ctx = datos["etfs"], datos.get("contexto") or {}
    return [_evaluar_atribucion(t, fila, ctx, datos.get("credito")) for t, fila in etfs.iterrows()] if len(etfs) else []


def _afirmacion_atribucion(datos: dict, evaluaciones: list[dict]) -> Afirmacion:
    etfs, ctx = datos["etfs"], datos.get("contexto") or {}
    por_clase: dict[str, list[str]] = {}
    for ev in evaluaciones:
        por_clase.setdefault(ev["clase"], []).append(ev["ETF"])
    calculables = [ev for ev in evaluaciones if ev["clase"] != "no_calculable"]
    if not calculables:
        motivo = datos["fechas"].get("motivo_sin_ventana") or "no hay ETFs con retorno y tasa de referencia en la ventana"
        return Afirmacion("atribucion", NIVEL_INSUFICIENTE,
                          f"**Sensibilidad a tasas.** No es posible contrastar los retornos con su sensibilidad a tasas en este período: {motivo}.")
    partes = []
    if por_clase.get("consistente"):
        partes.append(f"El retorno de {_lista(por_clase['consistente'])} es consistente en signo y magnitud con lo que anticipaba su "
                      "sensibilidad estimada a tasas.")
    if por_clase.get("parcial"):
        partes.append(f"En {_lista(por_clase['parcial'])}, el movimiento de tasas da cuenta solo de una parte del resultado.")
    if por_clase.get("contraria"):
        partes.append(f"En {_lista(por_clase['contraria'])}, el retorno fue en sentido contrario al anticipado, por lo que el movimiento "
                      "de tasas no da cuenta de su resultado.")
    if por_clase.get("sin_movimiento"):
        partes.append(f"En {_lista(por_clase['sin_movimiento'])}, ni la tasa de referencia ni el precio se movieron de forma material.")
    otros = [ev["ETF"] for ev in evaluaciones if ev["clase"] not in ("consistente", "parcial", "contraria", "sin_movimiento")]
    if otros:
        partes.append(f"Para {_lista(otros)}, la evidencia no permite una conclusión sobre el papel de las tasas (ver sección 2).")
    con_resto = etfs["Resto (%)"].dropna() if "Resto (%)" in etfs else pd.Series(dtype=float)
    if len(con_resto):
        mayor = con_resto.abs().idxmax()
        umbral_mayor = next((ev.get("umbral_retorno") for ev in evaluaciones if ev["ETF"] == mayor and ev.get("umbral_retorno")),
                            UMBRALES["pp_retorno"])
        if abs(con_resto[mayor]) >= umbral_mayor:  # una diferencia inmaterial no merece una frase
            partes.append(f"La mayor diferencia entre lo anticipado y lo observado se registró en {mayor} "
                          f"({ib.num(con_resto[mayor], 2, True)} pp); con estos datos no es posible asignarla a un factor específico.")
    devengo = _orden_del_devengo(ctx)
    if devengo is not None and devengo >= UMBRALES["pp_retorno"]:
        partes.append(f"La comparación es parcial: el modelo de sensibilidad no incluye el devengo de cupones, que en una ventana de "
                      f"{ctx['dias']} días y con tasas de referencia cercanas a {ib.pct(_mediana_tasa_inicio(ctx), 1)} puede ser del orden de "
                      f"{ib.num(devengo, 2)} pp, ni el riesgo de crédito ni la convexidad.")
    nivel = NIVEL_INTERPRETACION if por_clase.get("consistente") else NIVEL_HALLAZGO
    return Afirmacion("atribucion", nivel, "**Sensibilidad a tasas.** " + " ".join(partes),
                      tuple((ev["ETF"], ev["clase"]) for ev in evaluaciones))


def _mediana_tasa_inicio(ctx: dict) -> float | None:
    tasas = [v for v in (ctx.get("tasa_inicio") or {}).values() if v is not None]
    return float(np.median(tasas)) if tasas else None


def _orden_del_devengo(ctx: dict) -> float | None:
    """Orden de magnitud del devengo omitido (tasa mediana al inicio × días / 365), en pp. Solo dimensiona la
    limitación del modelo: no es una estimación del carry de ningún ETF ni entra en ninguna clasificación."""
    tasa = _mediana_tasa_inicio(ctx)
    return tasa * ctx["dias"] / 365.0 if tasa is not None and ctx.get("dias") else None


# ---- Comparación entre fondos --------------------------------------------
def _afirmacion_comparacion(datos: dict) -> Afirmacion | None:
    """El mejor y el peor ETF del período: ¿su diferencia de retorno es consistente con sus distintas sensibilidades?

    Cada uno se evalúa contra SU tasa de referencia (X_i = −β_i·Δy_i): la brecha anticipada es X_mejor − X_peor, no
    una diferencia de duraciones multiplicada por un único cambio de tasa. Solo dos fondos del Tesoro nominal se
    consideran comparables por plazo."""
    etfs, ctx, u = datos["etfs"], datos.get("contexto") or {}, UMBRALES
    if not len(etfs):
        return None
    retornos = etfs["Retorno del período (%)"].dropna()
    if len(retornos) < 2:
        return None
    mejor, peor = retornos.idxmax(), retornos.idxmin()
    r_m, r_p = float(retornos[mejor]), float(retornos[peor])
    brecha = r_m - r_p
    n = ctx.get("ruedas")
    diarios = ctx.get("retornos")
    sigma_brecha = None
    if isinstance(diarios, pd.DataFrame) and mejor in diarios and peor in diarios:
        dif = (diarios[mejor] - diarios[peor]).dropna()
        sigma_brecha = float(dif.std()) if len(dif) >= 30 else None
    tau = _umbral(u["pp_retorno"], sigma_brecha, n)
    b_m, b_p = etfs.loc[mejor, "Duración medida (años)"], etfs.loc[peor, "Duración medida (años)"]
    se_m, se_p = etfs.loc[mejor, "Error de la duración"], etfs.loc[peor, "Error de la duración"]
    g_m, g_p = ETFS_RENTA_FIJA[mejor]["grupo"], ETFS_RENTA_FIJA[peor]["grupo"]
    cifras = f"{mejor} rindió {ib.pct(r_m, 2, True)} y {peor}, {ib.pct(r_p, 2, True)}"
    condiciones = [("brecha material (pp)", brecha >= tau, round(brecha, 4), round(tau, 4))]
    if brecha < tau:
        texto = (f"Los retornos de los fondos fueron similares: {cifras}, una diferencia de {ib.num(brecha, 2)} pp, menor que la "
                 "variabilidad habitual de esa brecha en un período de este largo.")
        quietas = all(ev["clase"] in ("sin_movimiento", "tasa_quieta") for ev in _evaluaciones(datos) if ev["ETF"] in (mejor, peor))
        if quietas and pd.notna(b_m) and pd.notna(b_p) and abs(b_m - b_p) >= u["anios_sensibilidad"]:
            texto += (" Es lo esperable aun con sensibilidades a tasas distintas, porque sus tasas de referencia prácticamente no se "
                      "movieron.")
        return Afirmacion("comparacion", NIVEL_HALLAZGO, "**Comparación entre fondos.** " + texto, tuple(condiciones))
    distintas = (pd.notna(b_m) and pd.notna(b_p)
                 and abs(b_m - b_p) >= max(u["anios_sensibilidad"],
                                           u["errores_estandar"] * float(np.hypot(se_m if pd.notna(se_m) else 0, se_p if pd.notna(se_p) else 0))))
    condiciones.append(("sensibilidades distinguibles", bool(distintas), None, None))
    sens = (f"sus sensibilidades estimadas a tasas son de {ib.num(b_m, 1)} y {ib.num(b_p, 1)} años"
            if pd.notna(b_m) and pd.notna(b_p) else "")
    comparables = g_m == g_p and g_m in GRUPOS_COMPARABLES_POR_PLAZO
    condiciones.append(("comparables por plazo", comparables, (g_m, g_p), None))
    if not comparables:
        texto = f"{cifras}: una diferencia de {ib.num(brecha, 2)} pp."
        if sens and not distintas:
            texto += f" Como {sens}, la diferencia no proviene del plazo."
        texto += (f" {mejor} invierte en {EXPOSICION_POR_GRUPO[g_m]}, y {peor}, en {EXPOSICION_POR_GRUPO[g_p]}: los datos disponibles "
                  "no permiten atribuir la diferencia de rentabilidad exclusivamente al plazo.")
        return Afirmacion("comparacion", NIVEL_INSUFICIENTE, "**Comparación entre fondos.** " + texto, tuple(condiciones))
    x_m, x_p = etfs.loc[mejor, "Explicado por la duración (%)"], etfs.loc[peor, "Explicado por la duración (%)"]
    if not distintas or pd.isna(x_m) or pd.isna(x_p):
        motivo = (f"{sens}, demasiado parecidas para atribuir la diferencia al plazo" if not distintas and sens
                  else "no es posible contrastarla con su sensibilidad a tasas")
        return Afirmacion("comparacion", NIVEL_INSUFICIENTE,
                          f"**Comparación entre fondos.** {cifras}: una diferencia de {ib.num(brecha, 2)} pp; {motivo}.", tuple(condiciones))
    anticipada = float(x_m - x_p)
    coincide = (anticipada > 0) == (brecha > 0) and abs(brecha - anticipada) <= max(u["tolerancia_consistente"] * abs(brecha), tau)
    condiciones.append(("brecha anticipada consistente (pp)", coincide, round(anticipada, 4), None))
    if coincide:
        texto = (f"La diferencia de {ib.num(brecha, 2)} pp entre {mejor} ({ib.pct(r_m, 2, True)}) y {peor} ({ib.pct(r_p, 2, True)}) es "
                 f"consistente con sus distintas sensibilidades a tasas: medidas contra sus propias tasas de referencia, anticipaban una "
                 f"brecha de {ib.num(anticipada, 2)} pp. Ambos fondos invierten en bonos del Tesoro de EEUU, sin diferencias de riesgo de "
                 "crédito, por lo que el plazo es la diferencia económica más directa entre ellos, aunque no la única: el devengo y la "
                 "convexidad, no modelados aquí, también pueden contribuir.")
        # Un factor común a ambos se cancela en la diferencia: la brecha puede ser consistente aunque el nivel de cada
        # retorno no lo sea. Si es así, se dice, para que una frase no parezca contradecir a la otra.
        clases = {ev["ETF"]: ev["clase"] for ev in _evaluaciones(datos)}
        if any(clases.get(t) not in ("consistente", "sin_movimiento") for t in (mejor, peor)):
            texto += (" La conclusión se refiere solo a la diferencia entre ambos: el nivel de sus retornos no se explica por el "
                      "movimiento de tasas, lo que sugiere un componente común a los dos que el modelo no identifica.")
        return Afirmacion("comparacion", NIVEL_INTERPRETACION, "**Comparación entre fondos.** " + texto, tuple(condiciones))
    texto = (f"{cifras}: una diferencia de {ib.num(brecha, 2)} pp que no coincide con la brecha de {ib.num(anticipada, 2, True)} pp que "
             "anticipaban sus sensibilidades a tasas; los datos no permiten atribuirla al plazo.")
    return Afirmacion("comparacion", NIVEL_INSUFICIENTE, "**Comparación entre fondos.** " + texto, tuple(condiciones))


def _afirmaciones(datos: dict) -> list[Afirmacion]:
    """Las afirmaciones del resumen, en orden, cada una con su nivel y condiciones."""
    ctx = datos.get("contexto") or {}
    afirmaciones = [_afirmacion_curva(datos["curva"], ctx)]
    afirmaciones.append(_afirmacion_atribucion(datos, _evaluaciones(datos)))
    comparacion = _afirmacion_comparacion(datos)
    if comparacion is not None:
        afirmaciones.append(comparacion)
    afirmaciones.append(_afirmacion_credito(datos["credito"], ctx))
    chile = datos["chile"]
    if chile["inflacion_implicita"] is not None:
        afirmaciones.append(Afirmacion(
            "chile", NIVEL_HALLAZGO,
            f"**En Chile, el mercado descuenta una inflación de {ib.pct(chile['inflacion_implicita'])} a diez años.** Es la diferencia "
            f"entre el bono en pesos ({ib.pct(chile['bcp10'])}) y el bono en UF ({ib.pct(chile['bcu10'])}), al "
            f"{ib.fecha(chile['fecha_curva_chile'])}.",
        ))
    return afirmaciones


def _resumen(datos: dict) -> list[str]:
    """Los textos del resumen (ver _afirmaciones para su nivel de evidencia y las condiciones evaluadas)."""
    return [a.texto for a in _afirmaciones(datos)]


def _tramo_de_r2(r2: float) -> str:
    """Descripción del ajuste histórico diario. Describe, no prueba: un R² alto no demuestra causalidad."""
    if r2 >= 0.8:
        return "estrecha"
    if r2 >= UMBRALES["r2_minimo"]:
        return "moderada"
    if r2 >= 0.2:
        return "parcial"
    return "débil"


def _nota_metodologica(datos: dict) -> str:
    """Los criterios con que se redactaron las interpretaciones, con los umbrales efectivos de esta ventana."""
    u, ctx = UMBRALES, datos.get("contexto") or {}
    umbral_10 = _umbral(u["pb_tasa"], (ctx.get("sigma_plazo") or {}).get(10.0), ctx.get("ruedas"))
    return (
        "Criterios de interpretación. Un cambio de tasa o de spread se describe como alza o baja solo si supera "
        f"{ib.num(u['pb_tasa'], 0)} pb y, además, una cuarta parte de su variabilidad habitual para un período de este largo (en esta "
        f"ventana, {ib.num(umbral_10, 1)} pb para la tasa a 10 años); por debajo se informa como prácticamente sin cambio. Un retorno se "
        "considera consistente con la sensibilidad estimada a tasas cuando ambos son materiales, tienen el mismo signo, su diferencia no "
        f"supera la mitad del retorno observado (con un piso de {ib.num(u['pp_retorno'], 2)} pp) y la sensibilidad es precisa (R² de al "
        f"menos {ib.num(u['r2_minimo'], 1)} y error estándar de hasta {ib.num(u['error_relativo_maximo'] * 100, 0)}% de la estimación). "
        "El R² describe la relación diaria del último año: no mide qué parte del retorno del período explican las tasas ni establece "
        "causalidad. Dos fondos solo se comparan por plazo si ambos son bonos nominales del Tesoro. Estas reglas indican compatibilidad "
        "con un modelo de sensibilidad a tasas que omite el devengo de cupones, el riesgo de crédito y la convexidad; no identifican causas, "
        "y sus umbrales son hipótesis de trabajo, no estándares estadísticos ni regulatorios."
    )


def _tabla_desempeno(etfs: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "ETF": etfs.index,
        "Qué contiene": [ETFS_RENTA_FIJA[t]["grupo"] for t in etfs.index],
        "Retorno del período": [ib.pct(v, 2, True) for v in etfs["Retorno del período (%)"]],
        "Duración medida": [ib.num(v, 2) for v in etfs["Duración medida (años)"]],
        "Volatilidad (1 año)": [ib.pct(v) for v in etfs["Volatilidad (%)"]],
        "Peor caída (1 año)": [ib.pct(v) for v in etfs["Caída máxima 1 año (%)"]],
    })


def _tabla_atribucion(etfs: pd.DataFrame) -> pd.DataFrame:
    datos = etfs.dropna(subset=["Explicado por la duración (%)"])
    return pd.DataFrame({
        "ETF": datos.index,
        "Tasa de ref.": [f"{int(p)} años" for p in datos["Plazo de referencia"]],
        "Cambio de la tasa": [f"{ib.num(v, 2, True)} pp" for v in datos["Cambio de la tasa (pp)"]],
        "Duración": [ib.num(v, 2) for v in datos["Duración medida (años)"]],
        "Explicado": [ib.pct(v, 2, True) for v in datos["Explicado por la duración (%)"]],
        "Real": [ib.pct(v, 2, True) for v in datos["Retorno del período (%)"]],
        "Resto": [ib.pct(v, 2, True) for v in datos["Resto (%)"]],
        "R²": [ib.num(v, 2) for v in datos["R² con la tasa"]],
    })


def _tabla_sensibilidad(etfs: pd.DataFrame) -> pd.DataFrame:
    datos = etfs.dropna(subset=["Duración medida (años)"])
    tabla = {"ETF": datos.index, "Duración": [ib.num(v, 2) for v in datos["Duración medida (años)"]]}
    for cambio in CAMBIOS_DE_SENSIBILIDAD:
        tabla[f"{cambio:+.1f} pp"] = [ib.pct(-d * cambio, 1, True) for d in datos["Duración medida (años)"]]
    tabla["Margen"] = [f"±{ib.num(2 * e, 2)}" if pd.notna(e) else "—" for e in datos["Error de la duración"]]
    return pd.DataFrame(tabla)


def _lineas_de_fechas(datos: dict) -> list[str]:
    """La portada separa tres cosas distintas: la fecha de corte pedida, lo último que trae cada fuente y la ventana que
    de verdad se compara. (Sin «—»: en este PDF ese signo solo va en el pie de página.)"""
    f = datos["fechas"]
    if f["corte"] is None:
        return ["Sin datos de mercado."]
    lineas = [
        f"Datos de mercado al {ib.fecha(datos['hasta'])}." if datos["hasta"] is not None else "Sin datos de mercado.",
        f"Fecha de corte: {ib.fecha(f['corte'])} "
        + ("(solicitada)." if f["corte_solicitado"] else "(la última fecha con precios en la base)."),
    ]
    if f["inicio"] is not None:
        lineas.append(
            f"Ventana comparada: del {ib.fecha(f['inicio'])} al {ib.fecha(f['fin'])} ({f['ruedas']} ruedas). Retornos, "
            "cambios de tasa y atribución se miden entre esas dos mismas fechas."
        )
    else:
        lineas.append(f"Sin ventana comparable para el período: {f['motivo_sin_ventana']}.")
    ultimas = "; ".join(f"{fuente}, {ib.fecha(u)}" for fuente, u in f["ultima_por_fuente"].items() if u is not None)
    if ultimas:
        lineas.append(f"Último dato disponible al corte: {ultimas}.")
    ultimo_precio = f["ultima_por_fuente"]["ETFs (Yahoo Finance)"]
    if f["fin"] is not None and ultimo_precio is not None and f["fin"] < ultimo_precio:
        lineas.append(
            f"La ventana termina antes del último precio ({ib.fecha(ultimo_precio)}) porque la curva del Tesoro se publica con "
            "rezago y la atribución exige precio y tasa en la misma fecha. Por eso estos retornos pueden diferir por unos días "
            "de los que muestra el dashboard, que usa el último precio."
        )
    if f["dias_habiles_de_atraso"] is not None and f["dias_habiles_de_atraso"] > DIAS_HABILES_SIN_ADVERTENCIA:
        lineas.append(
            f"Advertencia: el último precio de la base es del {ib.fecha(ultimo_precio)}, unos {f['dias_habiles_de_atraso']} días "
            "hábiles antes de la fecha de corte (estimado sin feriados, que después del último dato no se pueden ver)."
        )
    return lineas


def _nota_de_excluidos(excluidos: list[dict]) -> str | None:
    if not excluidos:
        return None
    detalle = "; ".join(f"{e['ETF']} ({e['motivo']})" for e in excluidos)
    return (f"No se comparan, para no medir retornos en fechas distintas: {detalle}. Ningún precio se rellenó ni se "
            "estimó.")


def _nota_de_no_calculables(etfs: pd.DataFrame) -> str | None:
    if "Estado de la atribución" not in etfs:
        return None
    sin = etfs[etfs["Estado de la atribución"] != ESTADO_CALCULABLE]
    if sin.empty:
        return None
    detalle = "; ".join(f"{t} ({estado})" for t, estado in sin["Estado de la atribución"].items())
    return f"Sin atribución en este período: {detalle}. Su retorno, si se pudo medir, sí aparece en el Cuadro 1."


def generar(macro: pd.DataFrame, precios: pd.DataFrame, nombre_periodo: str, fecha_corte=None) -> bytes:
    """El informe completo en PDF, en bytes. `macro` y `precios` vienen como los usa la pantalla; `fecha_corte` (opcional)
    regenera el informe con los datos hasta esa fecha."""
    dias = PERIODOS[nombre_periodo]
    datos = calcular(macro, precios, dias, nombre_periodo, fecha_corte=fecha_corte)
    etfs, curva, chile, credito = datos["etfs"], datos["curva"], datos["chile"], datos["credito"]
    fechas = datos["fechas"]

    piezas = ib.portada(
        "Renta fija: qué pasó y por qué",
        f"Bonos del Tesoro, crédito y curva chilena · {nombre_periodo.lower()}",
        _lineas_de_fechas(datos) + [
            "Fuentes: Yahoo Finance (ETFs), Reserva Federal vía FRED (curva del Tesoro y spread Baa), Banco Central de Chile (BCP, BCU y TPM).",
        ],
    )

    if etfs.empty:
        piezas.append(ib.parrafo(
            "No hay datos de los ETFs de bonos en la base en este momento, así que este informe no puede calcular nada. "
            "No se muestran cifras de ejemplo."
        ))
        nota = _nota_de_excluidos(datos["excluidos"])
        if nota:
            piezas.append(ib.nota(nota))
        return ib.construir_pdf(piezas, "Renta fija", "Informe de renta fija")

    # ---- Resumen
    piezas += ib.titulo_seccion("Resumen")
    piezas += [ib.conclusion(f) for f in _resumen(datos)]

    # ---- 1. Qué pasó
    piezas += ib.titulo_seccion("1. Qué pasó")
    piezas.append(ib.parrafo(
        "Un **bono** es un préstamo que se compra y se vende. Quien lo emite paga **cupones** y devuelve el **capital** al "
        "vencimiento: por eso se llama renta fija. Lo que no es fijo es su **precio**, que sube y baja todos los días. "
        "Los instrumentos de abajo son ETFs: canastas de bonos que cotizan en bolsa como una acción."
    ))
    piezas.append(ib.tabla(_tabla_desempeno(etfs)))
    piezas.append(ib.nota(
        "Cuadro 1. Retornos totales del período: los precios vienen ajustados por distribuciones, así que ya incluyen los cupones que el "
        "fondo repartió. La volatilidad y la peor caída se miden sobre el último año de retornos diarios, no sobre el período del informe. "
        + (f"Todos los retornos van del {ib.fecha(fechas['inicio'])} al {ib.fecha(fechas['fin'])}, las mismas fechas para cada ETF. "
           if fechas["inicio"] is not None else f"Sin retornos del período: {fechas['motivo_sin_ventana']}. ")
        + f"Fuente: Yahoo Finance, datos al {ib.fecha(datos['hasta'])}."
    ))
    nota_excluidos = _nota_de_excluidos(datos["excluidos"])
    if nota_excluidos:
        piezas.append(ib.nota(nota_excluidos))
    if fechas["inicio"] is not None:
        piezas.append(ib.con_su_nota(
            _grafico_retornos(datos["precios"], list(etfs.index), fechas["inicio"], fechas["fin"]),
            f"Gráfico 1. Retorno acumulado de ETFs representativos, base 100 el {ib.fecha(fechas['inicio'])} y hasta el "
            f"{ib.fecha(fechas['fin'])} ({nombre_periodo.lower()}). "
            "SHY son bonos del Tesoro de 1 a 3 años; IEF, de 7 a 10; TLT, de 20 o más; HYG, bonos de empresas de alto rendimiento.",
        ))

    # ---- 2. Por qué
    piezas += ib.titulo_seccion("2. Sensibilidad a tasas y atribución de retornos")
    piezas.append(ib.parrafo(
        "Si las tasas suben, el precio de un bono ya emitido **baja**: nadie paga lo mismo por un cupón de 5% cuando puede comprar "
        "uno nuevo que paga 6%. Cuánto baja depende de la **duración**. Multiplicando la sensibilidad estimada de cada ETF por lo que "
        "se movió su tasa de referencia se obtiene cuánto **anticipaba** el modelo que se moviera su precio; contrastarlo con lo que "
        "pasó de verdad muestra si el resultado es compatible con el movimiento de tasas y qué parte queda sin explicar."
    ))
    if curva is not None:
        piezas.append(ib.con_su_nota(
            _grafico_curva(curva),
            f"Gráfico 2. Curva de rendimientos del Tesoro de EEUU el {ib.fecha(curva['fecha_inicio'])} y el "
            f"{ib.fecha(curva['fecha_fin'])}, el inicio y el fin de la ventana comparada. Fuente: Reserva Federal (H.15) vía FRED.",
        ))
    elif fechas["inicio"] is not None:
        piezas.append(ib.nota(
            "Sin Gráfico 2: la curva completa del Tesoro no está disponible en las dos fechas de la ventana, y usar la de otro "
            "día volvería a mezclar fechas."
        ))
    con_atribucion = etfs["Explicado por la duración (%)"].notna().any()
    if con_atribucion:
        piezas.append(ib.tabla(_tabla_atribucion(etfs)))
        piezas.append(ib.nota(
            "Cuadro 2. «Explicado» = −duración × cambio de la tasa. «Resto» = retorno real menos explicado: cupones devengados, riesgo de "
            "crédito y lo que el modelo no captura. **R²** indica qué parte del movimiento diario del precio explican las tasas: bajo el 0,5 "
            "la duración de ese instrumento es poco confiable. Retorno y cambio de tasa se miden entre las mismas dos fechas "
            f"({ib.fecha(fechas['inicio'])} y {ib.fecha(fechas['fin'])})."
        ))
    nota_sin = _nota_de_no_calculables(etfs)
    if nota_sin:
        piezas.append(ib.nota(nota_sin))
    if con_atribucion:
        piezas.append(ib.con_su_nota(
            _grafico_atribucion(etfs),
            "Gráfico 3. Lo que anticipaba la duración frente al retorno real de cada ETF en el período.",
        ))
    lectura = [_frase_de_evaluacion(ev) for ev in datos["evaluaciones"] if ev["clase"] != "no_calculable"]
    if lectura:
        piezas.append(ib.parrafo("**Lectura de la atribución.** " + " ".join(lectura)))
    dias_de_la_ventana = (fechas["fin"] - fechas["inicio"]).days if fechas["inicio"] is not None else dias
    frase_cupon = _frase_del_resto(etfs, dias_de_la_ventana or dias)
    if frase_cupon:
        piezas.append(ib.parrafo(frase_cupon))
    piezas.append(ib.recuadro_concepto(
        "Recuadro 1. Por qué la duración se mide y no se calcula",
        [
            "La duración de un bono suelto sale de una fórmula: es el promedio de sus pagos, ponderado por cuánto vale hoy cada uno. "
            "Pero un ETF es una canasta que cambia de composición, con bonos de distintos plazos y cupones, así que esa fórmula no aplica directamente.",
            "Acá la duración se **mide**: se compara, día a día durante un año, cuánto se movió el precio del ETF con cuánto se movió la tasa "
            "del Tesoro de su plazo. La pendiente de esa relación es la duración, y viene con un margen de error y con un R² que dice cuán "
            "confiable es. Un número medido con datos reales es preferible a uno sacado de una ficha que puede estar desactualizada.",
        ],
    ))
    # Solo fondos del Tesoro nominal: así «mismo emisor y mismo riesgo de impago» es cierto para los dos que se comparan.
    tesoro = etfs.loc[etfs["Grupo"] == "Tesoro EEUU", "Duración medida (años)"].dropna()
    tesoro = tesoro[tesoro > 0]
    if len(tesoro) >= 2:
        largo, corto = tesoro.idxmax(), tesoro.idxmin()
        dur_largo, dur_corto = float(tesoro[largo]), float(tesoro[corto])
        piezas.append(ib.recuadro_error(
            "Error frecuente: creer que «los bonos son seguros»",
            [
                f"{largo} y {corto} invierten en bonos del mismo emisor, el Tesoro de EEUU, con el mismo riesgo de impago. Sin embargo, la "
                f"sensibilidad estimada de {largo} es de {ib.num(dur_largo, 1)} años y la de {corto}, de {ib.num(dur_corto, 1)}: ante un "
                f"alza de un punto en sus respectivas tasas de referencia, el precio de {largo} tendería a caer unas "
                f"{ib.num(dur_largo / dur_corto, 0)} veces más que el de {corto}.",
                "La seguridad de un bono del Tesoro es de **crédito**: te pagan. No es de **precio**: un bono largo puede caer más que una "
                "acción defensiva. Confundir las dos cosas es lo que lleva a poner «renta fija» en la parte conservadora de una cartera sin "
                "mirar el plazo.",
            ],
        ))

    # ---- 3. Crédito
    piezas += ib.titulo_seccion("3. El otro motor: el riesgo de crédito")
    piezas.append(ib.parrafo(
        "El **riesgo de crédito** es que quien emitió el bono no pague. El mercado lo cobra como un **spread**: la tasa extra que exige "
        "por sobre un bono del Tesoro del mismo plazo. Cuando el spread se amplía, el precio de los bonos de empresas cae aunque las tasas "
        "del Tesoro no se muevan."
    ))
    if credito:
        clase_spread, pb_spread, _ = _clase_spread(credito, datos["contexto"])
        piezas.append(ib.parrafo(
            f"El spread Baa {_texto_spread(credito, clase_spread, pb_spread)} Su máximo en esas fechas fue "
            f"{ib.pct(float(credito['maximo']))}, el {ib.fecha(credito['fecha_maximo'])}. Es un indicador de **EEUU**, no de empresas "
            "chilenas, y corresponde a bonos de grado de inversión: no describe por sí solo el riesgo de los bonos de alto rendimiento. "
            "Se mide con sus propias fechas de publicación, que pueden no coincidir con la ventana de los ETFs."
        ))
    else:
        piezas.append(ib.parrafo("No hay datos del spread de bonos corporativos Baa en la base para este período."))
    alto_rendimiento = etfs.loc["HYG"] if "HYG" in etfs.index else None
    tesoro_medio = etfs.loc["IEF"] if "IEF" in etfs.index else None
    r2_hyg = alto_rendimiento["R² con la tasa"] if alto_rendimiento is not None else None
    r2_ief = tesoro_medio["R² con la tasa"] if tesoro_medio is not None else None
    if r2_hyg is not None and r2_ief is not None and pd.notna(r2_hyg) and pd.notna(r2_ief):
        segundo = (
            "En los bonos de alto rendimiento pesa además el **riesgo de crédito**: su precio puede caer aunque las tasas del Tesoro "
            "bajen, si el mercado exige más compensación por el riesgo de impago. Con una relación diaria "
            f"{_tramo_de_r2(r2_hyg)} con las tasas, su sensibilidad estimada debe leerse con cautela y no como una medida completa de su riesgo."
            if r2_hyg < UMBRALES["r2_minimo"] else
            f"En el último año, la relación diaria de HYG con las tasas fue {_tramo_de_r2(r2_hyg)}; aun así, su riesgo incluye el de "
            "**crédito**, que la sensibilidad a tasas no mide."
        )
        piezas.append(ib.recuadro_error(
            "Error frecuente: medir un bono de empresa solo por su duración",
            [
                f"En el último año, la relación diaria con la tasa del Tesoro de su plazo describe cerca de un {ib.num(r2_ief * 100, 0)}% "
                f"de la variación de IEF (R² {ib.num(r2_ief, 2)}) y un {ib.num(r2_hyg * 100, 0)}% de la de HYG (R² {ib.num(r2_hyg, 2)}). "
                "El R² describe ese ajuste histórico; no dice qué parte del retorno de un período explican las tasas.",
                segundo,
            ],
        ))

    # ---- 4. Chile
    piezas += ib.titulo_seccion("4. Chile: pesos, UF y política monetaria")
    if chile["bcp10"] is not None:
        piezas.append(ib.parrafo(
            f"El Banco Central de Chile emite bonos en **pesos** (BCP) y en **UF** (BCU). Al {ib.fecha(chile['fecha_curva_chile'])}, el BCP a "
            f"10 años rinde {ib.pct(chile['bcp10'])} y el BCU a 10 años, {ib.pct(chile['bcu10'])}. La diferencia, "
            f"{ib.pct(chile['inflacion_implicita'])}, es la **inflación implícita**: la que el mercado necesita que ocurra para quedar "
            "indiferente entre los dos."
        ))
    if chile["diferencial"] is not None:
        piezas.append(ib.parrafo(
            f"La **TPM** está en {ib.pct(chile['tpm'])} (al {ib.fecha(chile['fecha_tpm'])}) y la tasa de política de EEUU en "
            f"{ib.pct(chile['fed'])} (al {ib.fecha(chile['fecha_fed'])}): un diferencial de {ib.num(chile['diferencial'], 2, True)} puntos. "
            "Ese diferencial es lo que gana, antes del tipo de cambio, quien se financia en dólares para invertir en pesos."
        ))
    piezas.append(ib.recuadro_error(
        "Error frecuente: comparar una tasa en UF con una en pesos",
        [
            "Un BCU que rinde 2,6% no rinde menos que un BCP que rinde 6,0%. El BCU paga esa tasa **sobre un capital que se reajusta con la "
            "inflación**, así que su rendimiento ya viene limpio de inflación; el del BCP la incluye.",
            "Compararlas directamente lleva a concluir que el instrumento en UF es malo cuando en realidad están midiendo cosas distintas. "
            "La comparación correcta es entre la tasa real del BCU y la del BCP menos la inflación esperada, que es justamente la implícita.",
        ],
    ))

    # ---- 5. Sensibilidad
    piezas += ib.titulo_seccion("5. Qué pasaría si las tasas se mueven")
    piezas.append(ib.parrafo(
        "Con la duración medida se puede estimar el efecto de un movimiento de tasas. **No es una proyección**: no dice qué van a hacer las "
        "tasas, solo qué pasaría con el precio si se movieran esa cantidad."
    ))
    piezas.append(ib.tabla(_tabla_sensibilidad(etfs)))
    piezas.append(ib.nota(
        "Cuadro 3. Cambio estimado del precio ante movimientos paralelos de la tasa de referencia de cada ETF, calculado como "
        "−duración × cambio. «Margen» son dos errores estándar de la duración medida: el rango dentro del cual es razonable que esté el "
        "valor verdadero. La estimación ignora la convexidad, así que para movimientos grandes subestima las alzas de precio y sobreestima las caídas."
    ))

    # ---- 6. Límites
    piezas += ib.titulo_seccion("6. Qué no dice este informe")
    piezas.append(ib.parrafo(
        "**No hay recomendaciones de compra ni de venta.** El informe no conoce el horizonte, el perfil de riesgo ni las restricciones de "
        "quien lo lee, y sin eso una recomendación no tiene sustento."
    ))
    piezas.append(ib.parrafo(
        "**No hay proyecciones de tasas ni de inflación.** Todo lo que aparece ya ocurrió y está medido; las sensibilidades del cuadro 3 son "
        "condicionales, no pronósticos."
    ))
    piezas.append(ib.parrafo(
        "**No hay causas macroeconómicas.** El informe explica el movimiento de los precios por su mecánica (duración, spread, tasas), no por "
        "qué hizo la Reserva Federal o qué pasó en la economía: eso no se puede medir con estos datos y afirmarlo sería inventar."
    ))
    piezas.append(ib.parrafo(
        "**No hay precios de bonos individuales, probabilidades de default ni rendimientos publicados de cada ETF.** La base no los tiene, "
        "y por eso el «resto» del cuadro 2 va junto en vez de descompuesto."
    ))
    piezas.append(ib.nota(_nota_metodologica(datos)))
    piezas.append(ib.nota(
        "La duración se mide con el último año de retornos diarios y se aplica a este período como aproximación de primer orden. "
        "Este documento se genera automáticamente desde la base de datos del dashboard y no constituye asesoría de inversión."
    ))

    return ib.construir_pdf(piezas, "Renta fija", f"Informe de renta fija — {nombre_periodo.lower()}")
