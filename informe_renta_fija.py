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


def _retorno(serie: pd.Series, dias: int) -> float | None:
    t = _tramo(serie, dias)
    return None if t is None or t[0] == 0 else (t[1] / t[0] - 1) * 100


def _tabla_de_etfs(macro: pd.DataFrame, precios: pd.DataFrame, dias: int) -> pd.DataFrame:
    """Una fila por ETF: lo que rindió en el período y la parte que explica su duración.

    `esperado` = −duración × cambio de la tasa de referencia (en puntos porcentuales). `resto` es lo que queda:
    cupones devengados, riesgo de crédito y lo que el modelo no explica."""
    resumen = rfui._resumen_de_etfs(precios, macro, pd.Timestamp.now().normalize())
    filas = []
    for ticker, datos in ETFS_RENTA_FIJA.items():
        if resumen is None or ticker not in resumen.index or ticker not in precios:
            continue
        fila = resumen.loc[ticker]
        retorno = _retorno(precios[ticker], dias)
        tasa = rfui._rendimiento_del_tesoro(macro, datos["plazo_referencia"]) * 100  # a puntos porcentuales
        tramo_tasa = _tramo(tasa, dias)
        cambio = (tramo_tasa[1] - tramo_tasa[0]) if tramo_tasa else None
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
        })
    return pd.DataFrame(filas).set_index("ETF") if filas else pd.DataFrame()


def _curva(macro: pd.DataFrame, dias: int) -> dict | None:
    """Curva del Tesoro al inicio y al final del período, en %, por plazo en años."""
    pivote = rfui._pivote_curva(macro).dropna(how="all")
    if pivote.empty:
        return None
    completas = pivote.dropna(how="any")
    if len(completas) < 2:
        return None
    fecha_fin = completas.index[-1]
    objetivo = fecha_fin - pd.Timedelta(days=dias)
    anteriores = completas[completas.index <= objetivo]
    if anteriores.empty:
        return None
    fecha_inicio = anteriores.index[-1]
    inicio, fin = completas.loc[fecha_inicio], completas.loc[fecha_fin]
    return {"inicio": inicio, "fin": fin, "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin, "cambio": fin - inicio}


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


def calcular(macro: pd.DataFrame, precios: pd.DataFrame, dias: int, nombre_periodo: str) -> dict:
    """Todo lo que el informe va a decir, ya calculado. No arma PDF: así las pruebas pueden comprobar los números."""
    etfs = _tabla_de_etfs(macro, precios, dias)
    return {
        "periodo": nombre_periodo, "dias": dias,
        "etfs": etfs,
        "curva": _curva(macro, dias),
        "credito": _credito(macro, dias),
        "chile": _chile(macro),
        "hasta": etfs["ultima_fecha"].max() if len(etfs) else None,
        "precios": precios,
    }


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
def _grafico_retornos(precios: pd.DataFrame, dias: int):
    def dibujar(ax):
        for ticker in ETFS_DEL_GRAFICO:
            if ticker not in precios:
                continue
            serie = precios[ticker].dropna()
            serie = serie[serie.index >= serie.index[-1] - pd.Timedelta(days=dias)]
            if len(serie) < 2:
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


def generar(macro: pd.DataFrame, precios: pd.DataFrame, nombre_periodo: str) -> bytes:
    """El informe completo en PDF, en bytes. `macro` y `precios` vienen como los usa la pantalla."""
    dias = PERIODOS[nombre_periodo]
    datos = calcular(macro, precios, dias, nombre_periodo)
    etfs, curva, chile, credito = datos["etfs"], datos["curva"], datos["chile"], datos["credito"]

    piezas = ib.portada(
        "Renta fija: qué pasó y por qué",
        f"Bonos del Tesoro, crédito y curva chilena · {nombre_periodo.lower()}",
        [
            f"Datos de mercado al {ib.fecha(datos['hasta'])}." if datos["hasta"] is not None else "Sin datos de mercado.",
            "Fuentes: Yahoo Finance (ETFs), Reserva Federal vía FRED (curva del Tesoro y spread Baa), Banco Central de Chile (BCP, BCU y TPM).",
        ],
    )

    if etfs.empty:
        piezas.append(ib.parrafo(
            "No hay datos de los ETFs de bonos en la base en este momento, así que este informe no puede calcular nada. "
            "No se muestran cifras de ejemplo."
        ))
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
        f"Fuente: Yahoo Finance, datos al {ib.fecha(datos['hasta'])}."
    ))
    piezas.append(ib.con_su_nota(
        _grafico_retornos(datos["precios"], dias),
        f"Gráfico 1. Retorno acumulado de cuatro ETFs representativos, base 100 al inicio del período ({nombre_periodo.lower()}). "
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
            "Gráfico 2. Curva de rendimientos del Tesoro de EEUU al inicio y al final del período. "
            f"Fuente: Reserva Federal (H.15) vía FRED, al {ib.fecha(curva['fecha_fin'])}.",
        ))
    piezas.append(ib.tabla(_tabla_atribucion(etfs)))
    piezas.append(ib.nota(
        "Cuadro 2. «Explicado» = −duración × cambio de la tasa. «Resto» = retorno real menos explicado: cupones devengados, riesgo de "
        "crédito y lo que el modelo no captura. **R²** indica qué parte del movimiento diario del precio explican las tasas: bajo el 0,5 "
        "la duración de ese instrumento es poco confiable."
    ))
    piezas.append(ib.con_su_nota(
        _grafico_atribucion(etfs),
        "Gráfico 3. Lo que anticipaba la duración frente al retorno real de cada ETF en el período.",
    ))
    frase_cupon = _frase_del_resto(etfs, dias)
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
            f"En el período el spread Baa {verbo} de {ib.num(credito['inicio'])} a {ib.num(credito['fin'])} puntos porcentuales "
            f"({ib.num(credito['cambio'], 2, True)} pp). Su máximo del período fue {ib.num(credito['maximo'])} pp, el "
            f"{ib.fecha(credito['fecha_maximo'])}. Es un indicador de **EEUU**, no de empresas chilenas."
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
