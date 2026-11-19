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
    return {
        "periodo": nombre_periodo, "dias": dias,
        "etfs": etfs,
        "excluidos": ventana["excluidos"],
        "fechas": fechas,
        "curva": _curva(macro, ventana),
        "credito": _credito(macro, dias),
        "chile": _chile(macro),
        "hasta": ventana["fin"] if ventana["fin"] is not None else ventana["ultimo_precio"],
        "precios": precios,
    }


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
def _ordenar(etfs: pd.DataFrame, columna: str):
    datos = etfs[columna].dropna()
    return (datos.idxmax(), datos.max(), datos.idxmin(), datos.min()) if len(datos) >= 2 else None


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


def _resumen(datos: dict) -> list[str]:
    """Las conclusiones del informe: la afirmación adelante, en negrita, y la evidencia atrás."""
    etfs, curva, chile = datos["etfs"], datos["curva"], datos["chile"]
    frases = []
    extremos = _ordenar(etfs, "Retorno del período (%)")
    if extremos:
        mejor, valor_mejor, peor, valor_peor = extremos
        frases.append(
            f"**El plazo decidió el resultado del período.** {mejor} rindió {ib.pct(valor_mejor, 2, True)} y {peor}, "
            f"{ib.pct(valor_peor, 2, True)}. Los dos son canastas de bonos; lo que los separa es cuánto duran sus flujos."
        )
    if curva is not None:
        cambio10 = curva["cambio"].get(10.0)
        cambio2 = curva["cambio"].get(2.0)
        if cambio10 is not None and cambio2 is not None:
            direccion = "subió" if cambio10 > 0 else "bajó"
            frases.append(
                f"**La curva del Tesoro se movió {'al alza' if cambio10 > 0 else 'a la baja'}.** La tasa a 10 años {direccion} "
                f"{ib.num(abs(cambio10), 2)} puntos porcentuales y la de 2 años, {ib.num(abs(cambio2), 2)}. "
                f"Hoy la de 10 años está en {ib.pct(curva['fin'].get(10.0))}."
            )
    con_duracion = etfs.dropna(subset=["Explicado por la duración (%)", "Resto (%)"])
    if len(con_duracion):
        peor_ajuste = con_duracion["Resto (%)"].abs().idxmax()
        frases.append(
            f"**La duración explica la mayor parte del movimiento, pero no todo.** En {peor_ajuste} quedó la mayor diferencia "
            f"entre lo que anticipaba su duración y lo que pasó de verdad: {ib.pct(con_duracion.loc[peor_ajuste, 'Resto (%)'], 2, True)} "
            "atribuible a cupones, riesgo de crédito y a lo que el modelo no captura."
        )
    if datos["credito"]:
        c = datos["credito"]
        verbo = "se amplió" if c["cambio"] > 0 else "se comprimió"
        frases.append(
            f"**El premio por riesgo de crédito {verbo}.** El spread de los bonos corporativos Baa sobre el Tesoro a 10 años pasó de "
            f"{ib.num(c['inicio'])} a {ib.num(c['fin'])} puntos porcentuales. "
            + ("Un spread más alto significa que el mercado está cobrando más caro prestarle a las empresas."
               if c["cambio"] > 0 else "Un spread más bajo significa que el mercado está cobrando más barato prestarle a las empresas.")
        )
    if chile["inflacion_implicita"] is not None:
        frases.append(
            f"**En Chile, el mercado descuenta una inflación de {ib.pct(chile['inflacion_implicita'])} a diez años.** Es la diferencia "
            f"entre el bono en pesos ({ib.pct(chile['bcp10'])}) y el bono en UF ({ib.pct(chile['bcu10'])}), al {ib.fecha(chile['fecha_curva_chile'])}."
        )
    return frases


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
    piezas += ib.titulo_seccion("2. Por qué: la duración manda")
    piezas.append(ib.parrafo(
        "Si las tasas suben, el precio de un bono ya emitido **baja**: nadie paga lo mismo por un cupón de 5% cuando puede comprar "
        "uno nuevo que paga 6%. Cuánto baja depende de la **duración**. Multiplicando la duración de cada ETF por lo que se movió su "
        "tasa de referencia se obtiene cuánto **debería** haberse movido su precio; comparar eso con lo que pasó de verdad muestra qué "
        "parte del resultado explican las tasas y qué parte no."
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
    extremos = _ordenar(etfs, "Duración medida (años)")
    if extremos:
        largo, dur_largo, corto, dur_corto = extremos
        piezas.append(ib.recuadro_error(
            "Error frecuente: creer que «los bonos son seguros»",
            [
                f"{largo} y {corto} tienen el mismo emisor y el mismo riesgo de que no les paguen, pero la duración de {largo} es "
                f"{ib.num(dur_largo, 1)} años y la de {corto}, {ib.num(dur_corto, 1)}: por cada punto que suben las tasas, {largo} cae "
                f"cerca de {ib.num(dur_largo / dur_corto, 0) if dur_corto else '—'} veces más.",
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
        verbo = "se amplió" if credito["cambio"] > 0 else "se comprimió"
        piezas.append(ib.parrafo(
            f"Entre el {ib.fecha(credito['fecha_inicio'])} y el {ib.fecha(credito['fecha_fin'])} el spread Baa {verbo} de "
            f"{ib.num(credito['inicio'])} a {ib.num(credito['fin'])} puntos porcentuales "
            f"({ib.num(credito['cambio'], 2, True)} pp). Su máximo en esas fechas fue {ib.num(credito['maximo'])} pp, el "
            f"{ib.fecha(credito['fecha_maximo'])}. Es un indicador de **EEUU**, no de empresas chilenas. Se mide con sus propias "
            "fechas de publicación, que pueden no coincidir con la ventana de los ETFs."
        ))
    else:
        piezas.append(ib.parrafo("No hay datos del spread de bonos corporativos Baa en la base para este período."))
    alto_rendimiento = etfs.loc["HYG"] if "HYG" in etfs.index else None
    tesoro_medio = etfs.loc["IEF"] if "IEF" in etfs.index else None
    if alto_rendimiento is not None and tesoro_medio is not None:
        piezas.append(ib.recuadro_error(
            "Error frecuente: medir un bono de empresa solo por su duración",
            [
                f"El R² de HYG es {ib.num(alto_rendimiento['R² con la tasa'], 2)} y el de IEF, {ib.num(tesoro_medio['R² con la tasa'], 2)}. "
                "Eso significa que las tasas del Tesoro explican buena parte de lo que hace IEF y bastante poco de lo que hace HYG.",
                "A los bonos de alto rendimiento los mueve sobre todo el **crédito**: si el mercado cree que más empresas van a quebrar, caen "
                "aunque las tasas bajen. Por eso se parecen más a una acción que a un bono del Tesoro, y por eso su duración medida hay que "
                "tomarla con cuidado: está midiendo una relación que casi no existe.",
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
    piezas.append(ib.nota(
        "La duración se mide con el último año de retornos diarios y se aplica a este período como aproximación de primer orden. "
        "Este documento se genera automáticamente desde la base de datos del dashboard y no constituye asesoría de inversión."
    ))

    return ib.construir_pdf(piezas, "Renta fija", f"Informe de renta fija — {nombre_periodo.lower()}")
