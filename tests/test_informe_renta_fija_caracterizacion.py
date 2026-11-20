"""Etapa 1, intervención I-0: pruebas de caracterización del informe de renta fija.

PARA QUÉ EXISTE
    Antes de tocar los cálculos o los textos de informe_renta_fija.py, estas pruebas fijan qué hace hoy el informe y
    reproducen, con datos sintéticos, cada defecto metodológico identificado en el diagnóstico. Todo es offline: ninguna
    prueba lee la base de datos.

CÓMO SE LEEN
    - Prueba normal (pasa): describe un comportamiento que hoy es correcto, o cuantifica una LIMITACIÓN declarada.
    - `@defecto(...)`: xfail(strict=True) que reproduce un defecto pendiente. Indica el error y la intervención que
      debería corregirlo. Si alguien lo corrige, la prueba pasa, el xfail estricto la marca en rojo y hay que quitar
      la marca: así ninguna corrección pasa inadvertida.
    - `raises=AssertionError`: solo cuenta como «falla esperada» una aserción que falla. Una excepción de otro tipo
      (un escenario roto, un cambio de interfaz) sale en rojo en vez de esconderse detrás del xfail.
    - `_requisito(...)`: condiciones previas del escenario. Usan pytest.fail, que NO es AssertionError: si el escenario
      no es el que se pretendía, la prueba sale en rojo en vez de contar como el defecto.

RIGOR
    Los resultados esperados se calculan aparte (fórmulas en la prueba, no llamando al informe). Un «resto» solo se
    exige cercano a cero en un mundo construido sin ningún factor omitido; nunca se supone que el resto «es» carry,
    crédito o cupón salvo en un escenario donde, por construcción, es lo único que falta en el modelo.

POR QUÉ ES UN ARCHIVO APARTE
    tests/conftest.py registra test_informe_renta_fija.py como de integración, con una lista de las pruebas que pueden
    correr sin base. Una prueba nueva en ese archivo quedaría omitida sin base de pruebas, y conftest.py está fuera del
    alcance de I-0.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import inspect
import os
import re
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import estructura_tasas as et  # noqa: E402
import informe_base as ib  # noqa: E402
import informe_renta_fija as inf  # noqa: E402
import renta_fija_ui as rfui  # noqa: E402
from catalogo_renta_fija import ETFS_RENTA_FIJA  # noqa: E402

FECHAS = pd.bdate_range("2025-01-06", periods=420)
N = len(FECHAS)
MES = "Último mes"
DIAS_MES = inf.PERIODOS[MES]


# ---------------------------------------------------------------------------
# Constructores de escenarios
# ---------------------------------------------------------------------------
def defecto(intervencion: str, que: str):
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"Defecto pendiente, corrige {intervencion}: {que}")


def _requisito(condicion: bool, mensaje: str) -> None:
    if not condicion:
        pytest.fail(f"Escenario mal construido: {mensaje}")


def _paseo(semilla: int, inicio: float, desvio: float) -> np.ndarray:
    """Paseo aleatorio en % (la unidad en que la base guarda las tasas)."""
    rng = np.random.default_rng(semilla)
    return inicio + np.concatenate([[0.0], rng.normal(0, desvio, N - 1)]).cumsum()


def _rampa(total: float, dias: int) -> np.ndarray:
    """Cero hasta los últimos `dias` puntos, y de ahí sube en línea recta hasta `total`."""
    r = np.zeros(N)
    r[N - dias:] = np.linspace(total / dias, total, dias)
    return r


def _cambios(tasa_pct: np.ndarray) -> np.ndarray:
    """Cambio diario de una tasa, en decimales (0,01 pp = 0.0001)."""
    return np.diff(tasa_pct, prepend=tasa_pct[0]) / 100.0


def _precio(retornos: np.ndarray) -> np.ndarray:
    r = np.asarray(retornos, dtype=float).copy()
    r[0] = 0.0
    return 100.0 * np.cumprod(1.0 + r)


def _macro(tasa_de, extras: dict | None = None, tasas_hasta=None) -> pd.DataFrame:
    """Curva del Tesoro completa (todos los plazos), opcionalmente cortada en `tasas_hasta`, más series sueltas."""
    filas = []
    for etiqueta, plazo in et.PLAZOS_ANIOS.items():
        for f, v in zip(FECHAS, tasa_de(plazo)):
            if tasas_hasta is None or f <= tasas_hasta:
                filas.append({"nombre": rfui.nombre_treasury(etiqueta), "fecha": f, "valor": float(v)})
    for nombre, valores in (extras or {}).items():
        filas += [{"nombre": nombre, "fecha": f, "valor": float(v)}
                  for f, v in zip(FECHAS, np.broadcast_to(valores, N))]
    return pd.DataFrame(filas)


def _inicio(fin: pd.Timestamp, dias: int) -> pd.Timestamp:
    """La convención del informe, reescrita aquí: el último dato en `fin − dias` o antes."""
    return FECHAS[FECHAS <= fin - pd.Timedelta(days=dias)][-1]


def _delta(tasa_pct: np.ndarray, dias: int, fin_idx: int = -1) -> float:
    """Cambio de una tasa (pp) en la ventana que termina en FECHAS[fin_idx], calculado aparte del informe."""
    fin = FECHAS[fin_idx]
    i0 = FECHAS.get_loc(_inicio(fin, dias))
    return float(tasa_pct[FECHAS.get_loc(fin)] - tasa_pct[i0])


def _frase(frases: list[str], clave: str) -> str | None:
    return next((f for f in frases if clave in f), None)


def _mundo_lineal(semilla: int, duraciones: dict, salto: float = 0.0):
    """Curva paralela y precios que responden EXACTAMENTE a −duración × cambio de tasa: el modelo del informe no omite
    nada, así que en ventanas alineadas lo explicado tiene que coincidir con lo real (salvo el efecto compuesto)."""
    y = _paseo(semilla, 4.0, 0.03)
    if salto:
        y[N - 10:] += salto
    precios = pd.DataFrame({t: _precio(-d * _cambios(y)) for t, d in duraciones.items()}, index=FECHAS)
    return y, precios


def _texto_pdf(pdf: bytes) -> str:
    pymupdf = pytest.importorskip("pymupdf", reason="pymupdf no está instalado: no se puede leer el PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return " ".join(" ".join(p.get_text().split()) for p in doc)


DURACIONES_LINEALES = {"SHY": 1.9, "IEF": 6.5, "TLT": 16.0}


# ---------------------------------------------------------------------------
# 1. Ventanas temporales (I-1)
# ---------------------------------------------------------------------------
def test_control_con_calendarios_iguales_lo_explicado_coincide_con_lo_real():
    """Control del escenario: sin desfase y sin factores omitidos, la atribución actual cierra (resto ≈ 0) y la
    duración medida es la usada para construir los precios. Si esto falla, el generador de escenarios está mal."""
    y, precios = _mundo_lineal(1, DURACIONES_LINEALES)
    etfs = inf.calcular(_macro(lambda p: y), precios, DIAS_MES, MES)["etfs"]
    for ticker, d in DURACIONES_LINEALES.items():
        assert etfs.loc[ticker, "Duración medida (años)"] == pytest.approx(d, abs=1e-6), ticker
        assert abs(etfs.loc[ticker, "Resto (%)"]) < 0.10, ticker
    # en este mundo la frase «la duración explica la mayor parte» está justificada
    # Desde I-2 la afirmación está condicionada a los datos (y redactada como compatibilidad, no causa): en este mundo
    # se cumplen sus condiciones, así que tiene que aparecer.
    frase = _frase(inf._resumen(inf.calcular(_macro(lambda p: y), precios, DIAS_MES, MES)), "Sensibilidad a tasas")
    assert frase is not None and "es consistente en signo y magnitud" in frase, frase


def test_precio_y_tasa_con_fechas_de_actualizacion_distintas_se_atribuyen_en_la_misma_ventana():
    # Fue xfail en I-0 (defecto); corregido en I-1 con la ventana común.
    """Las tasas (FRED) llegan 3 ruedas atrasadas respecto de los precios (Yahoo), como en el informe real del 18-11.
    En esas 3 ruedas los ETFs caen 2% por un movimiento de tasas que todavía no está en la base.

    Esperado: con la ventana común (la que termina en la última fecha con precio Y tasa) el mundo es lineal y el resto
    es ≈ 0. Hoy el retorno llega hasta la última fecha con precio y el cambio de tasa hasta la última con tasa, y la
    caída sin su tasa queda como «resto» (≈ −2%), presentada como cupones, crédito o lo no explicado."""
    y, precios = _mundo_lineal(1, DURACIONES_LINEALES)
    caida = np.ones(N)
    caida[N - 3] = 0.99            # −1% en la antepenúltima rueda
    caida[N - 2:] = 0.99 * 0.99    # y otro −1% en la penúltima, que se mantiene hasta el final
    precios = precios.mul(caida, axis=0)
    tasas_hasta = FECHAS[-4]
    macro = _macro(lambda p: y, tasas_hasta=tasas_hasta)
    _requisito(pd.to_datetime(macro["fecha"]).max() < precios.index.max(), "las tasas deberían terminar antes que los precios")
    etfs = inf.calcular(macro, precios, DIAS_MES, MES)["etfs"]
    for ticker in DURACIONES_LINEALES:
        assert abs(etfs.loc[ticker, "Resto (%)"]) < 0.10, f"{ticker}: resto {etfs.loc[ticker, 'Resto (%)']:.2f}% por ventanas distintas"


# ---------------------------------------------------------------------------
# 2. Dirección de las tasas y forma de la curva (I-2)
# ---------------------------------------------------------------------------
def _curva_con_tramos(y2: np.ndarray, y10: np.ndarray):
    def tasa_de(plazo: float) -> np.ndarray:
        if plazo <= 2:
            return y2
        if plazo >= 10:
            return y10
        w = (plazo - 2) / 8
        return (1 - w) * y2 + w * y10
    return tasa_de


def _escenario_curva(subida_2: float, subida_10: float, semilla: int):
    y2 = _paseo(semilla, 4.0, 0.005) + _rampa(subida_2, 21)
    y10 = _paseo(semilla + 100, 4.5, 0.005) + _rampa(subida_10, 21)
    tasa_de = _curva_con_tramos(y2, y10)
    precios = pd.DataFrame({
        "SHY": _precio(-1.9 * _cambios(tasa_de(2.0))),
        "IEF": _precio(-6.5 * _cambios(tasa_de(7.0))),
    }, index=FECHAS)
    return y2, y10, inf.calcular(_macro(tasa_de), precios, DIAS_MES, MES)


def test_con_un_movimiento_paralelo_a_la_baja_el_texto_dice_a_la_baja_con_las_cifras_correctas():
    y2, y10, datos = _escenario_curva(-0.30, -0.30, semilla=21)
    d2, d10 = _delta(y2, DIAS_MES), _delta(y10, DIAS_MES)
    _requisito(d2 < -0.2 and d10 < -0.2, "las dos tasas deberían bajar")
    assert datos["curva"]["cambio"][2.0] == pytest.approx(d2)
    assert datos["curva"]["cambio"][10.0] == pytest.approx(d10)
    frase = _frase(inf._resumen(datos), "curva del Tesoro")
    assert "a la baja" in frase and "bajó" in frase
    assert ib.num(abs(d10), 2) in frase and ib.num(abs(d2), 2) in frase


def test_si_el_tramo_corto_sube_y_el_largo_baja_el_texto_no_lo_presenta_como_una_baja_general():
    # Fue xfail en I-0; corregido en I-2. Desde I-2 además se exige que el movimiento se nombre como torsión.
    """Aplanamiento: la tasa a 2 años sube 0,30 pp y la de 10 años baja 0,30 pp (como el 18-11, en menor escala).
    Hoy el resumen dice «La curva del Tesoro se movió a la baja. La tasa a 10 años bajó 0.30 ... y la de 2 años, 0.30»:
    el lector entiende que la de 2 años también bajó. El Gráfico 2 muestra lo contrario."""
    y2, y10, datos = _escenario_curva(+0.30, -0.30, semilla=22)
    _requisito(_delta(y2, DIAS_MES) > 0.2 and _delta(y10, DIAS_MES) < -0.2, "2 años debería subir y 10 años bajar")
    _requisito(datos["curva"]["cambio"][2.0] > 0 > datos["curva"]["cambio"][10.0], "los números del informe deberían tener esos signos")
    frase = _frase(inf._resumen(datos), "curva del Tesoro")
    assert "se movió a la baja" not in frase and "se movió al alza" not in frase, frase
    assert re.search(r"subió|al alza|aument", frase), f"no dice que algún tramo subió: {frase}"
    assert "torsión" in frase and "subió" in frase and "bajó" in frase, frase


def test_si_la_curva_no_se_mueve_el_texto_no_inventa_una_direccion():
    # Fue xfail en I-0; corregido en I-2.
    y = _paseo(23, 4.0, 0.03)
    y[N - 25:] = y[N - 26]  # la curva queda congelada durante todo el último mes
    precios = pd.DataFrame({"SHY": _precio(-1.9 * _cambios(y)), "IEF": _precio(-6.5 * _cambios(y))}, index=FECHAS)
    datos = inf.calcular(_macro(lambda p: y), precios, DIAS_MES, MES)
    _requisito(datos["curva"]["cambio"][10.0] == 0 and datos["curva"]["cambio"][2.0] == 0, "la curva no debería moverse")
    frase = _frase(inf._resumen(datos), "curva del Tesoro")
    assert frase is None or not re.search(r"a la baja|al alza|bajó|subió", frase), frase
    assert frase is not None and "prácticamente no se movió" in frase, frase


def test_si_el_spread_no_cambia_el_texto_no_dice_que_se_comprimio():
    # Fue xfail en I-0; corregido en I-2.
    y, precios = _mundo_lineal(24, {"SHY": 1.9, "IEF": 6.5})
    datos = inf.calcular(_macro(lambda p: y, extras={rfui.NOMBRE_BAA10Y: 1.5}), precios, DIAS_MES, MES)
    _requisito(datos["credito"] is not None and datos["credito"]["cambio"] == 0, "el spread debería estar constante")
    frase = _frase(inf._resumen(datos), "premio por riesgo de crédito")
    assert frase is None or ("se comprimió" not in frase and "se amplió" not in frase), frase
    assert frase is not None and "no cambió" in frase, frase


# ---------------------------------------------------------------------------
# 3. Conclusiones que la duración no sostiene (I-2)
# ---------------------------------------------------------------------------
def test_si_lo_explicado_y_lo_real_tienen_signo_opuesto_no_se_afirma_que_la_duracion_explica_la_mayor_parte():
    # Fue xfail en I-0; corregido en I-2. Desde I-2 además se exige que no aparezca ninguna afirmación de
    # consistencia (con cualquier redacción) y que se diga que el retorno fue en sentido contrario.
    """Las tasas suben 0,20 pp en un día y los precios, además del efecto de la duración, suben 2,5% por un factor que
    no es la tasa. En los tres ETFs lo explicado es negativo y lo real positivo: |real − explicado| > |real|, así que
    la duración no puede explicar «la mayor parte». Pasó en 5 de 10 ETFs el 18-11 y el informe lo afirmó igual."""
    y = _paseo(31, 4.0, 0.03)
    y[N - 10:] += 0.20
    extra = np.zeros(N)
    extra[N - 21:] = 0.025 / 20
    extra[N - 10] = 0.0  # el día del salto de tasa no hay otro factor
    duraciones = {"SHY": 1.9, "IEI": 4.0, "IEF": 6.5}
    precios = pd.DataFrame({t: _precio(-d * _cambios(y) + extra) for t, d in duraciones.items()}, index=FECHAS)
    datos = inf.calcular(_macro(lambda p: y), precios, DIAS_MES, MES)
    etfs = datos["etfs"]
    _requisito(((etfs["Explicado por la duración (%)"] < 0) & (etfs["Retorno del período (%)"] > 0)).all(),
               "lo explicado debería ser negativo y lo real positivo en todos")
    assert _frase(inf._resumen(datos), "La duración explica la mayor parte") is None
    frase = _frase(inf._resumen(datos), "Sensibilidad a tasas")
    assert "consistente" not in frase and "sentido contrario" in frase, frase


# ---------------------------------------------------------------------------
# 4. ETFs con duración parecida y riesgos distintos (I-2)
# ---------------------------------------------------------------------------
def _ratio_de_la_brecha_explicada(etfs: pd.DataFrame, mejor: str, peor: str) -> float:
    explicado = etfs["Explicado por la duración (%)"]
    real = etfs["Retorno del período (%)"]
    return abs(explicado[mejor] - explicado[peor]) / abs(real[mejor] - real[peor])


def test_control_si_la_brecha_la_explica_la_duracion_se_puede_decir_que_el_plazo_decidio():
    """Tasas +1 pp en un día, sin otro factor: la diferencia entre SHY y TLT es casi toda −ΔD × Δy."""
    y, precios = _mundo_lineal(41, {"SHY": 1.9, "TLT": 16.0}, salto=1.0)
    datos = inf.calcular(_macro(lambda p: y), precios, DIAS_MES, MES)
    etfs = datos["etfs"]
    _requisito(etfs["Retorno del período (%)"].idxmax() == "SHY" and etfs["Retorno del período (%)"].idxmin() == "TLT",
               "SHY debería ser el mejor y TLT el peor")
    _requisito(_ratio_de_la_brecha_explicada(etfs, "SHY", "TLT") > 0.9, "la duración debería explicar la brecha")
    # Desde I-2 la afirmación se condiciona y se redacta como compatibilidad; en este mundo se cumplen sus condiciones.
    assert _frase(inf._resumen(datos), "es consistente con sus distintas sensibilidades a tasas")


def test_con_duraciones_parecidas_la_diferencia_de_retorno_no_se_atribuye_al_plazo():
    # Fue xfail en I-0; corregido en I-2. Desde I-2 además se exige que no aparezca la afirmación nueva de
    # consistencia por plazo y que se diga explícitamente que no se puede atribuir al plazo.
    """IEI, HYG y LQD con duraciones 4,0 / 3,9 / 4,1 y tasas casi quietas. HYG gana 1,5% y LQD pierde 1,5% por un
    factor ajeno a la tasa (crédito, en la realidad). La parte de la brecha HYG−LQD que explica la duración es
    |ΔD·Δy| / |ΔR| < 10%: decir que «lo que los separa es cuánto duran sus flujos» es falso. El 18-11 el informe lo dijo
    de HYG (2,99) y TIP (3,78)."""
    y = _paseo(42, 4.0, 0.02) + _rampa(0.05, 21)
    factor = np.zeros(N)
    factor[N - 20:] = 0.015 / 20
    precios = pd.DataFrame({
        "IEI": _precio(-4.0 * _cambios(y)),
        "HYG": _precio(-3.9 * _cambios(y) + factor),
        "LQD": _precio(-4.1 * _cambios(y) - factor),
    }, index=FECHAS)
    datos = inf.calcular(_macro(lambda p: y), precios, DIAS_MES, MES)
    etfs = datos["etfs"]
    _requisito(etfs["Retorno del período (%)"].idxmax() == "HYG" and etfs["Retorno del período (%)"].idxmin() == "LQD",
               "HYG debería ser el mejor y LQD el peor")
    _requisito(_ratio_de_la_brecha_explicada(etfs, "HYG", "LQD") < 0.10, "la duración no debería explicar la brecha")
    assert _frase(inf._resumen(datos), "El plazo decidió el resultado") is None
    assert _frase(inf._resumen(datos), "es consistente con sus distintas sensibilidades") is None
    frase = _frase(inf._resumen(datos), "Comparación entre fondos")
    assert frase is not None and "no permiten atribuir la diferencia de rentabilidad exclusivamente al plazo" in frase, frase


# ---------------------------------------------------------------------------
# 5. TIP y la tasa real (I-4a)
# ---------------------------------------------------------------------------
def _escenario_tip():
    """Tasa nominal = real + inflación de equilibrio. TIP responde SOLO a la real (duración 4,5). En el último mes la
    inflación de equilibrio sube 0,40 pp y la real casi no se mueve."""
    real = _paseo(51, 1.8, 0.03)
    equilibrio = _paseo(151, 2.3, 0.01) + _rampa(0.40, 21)
    nominal = real + equilibrio
    precios = pd.DataFrame({"TIP": _precio(-4.5 * _cambios(real))}, index=FECHAS)
    return real, nominal, inf.calcular(_macro(lambda p: nominal), precios, DIAS_MES, MES)["etfs"]


def test_tip_ya_no_se_mide_contra_la_tasa_nominal_del_tesoro():
    """Caracterización. Hasta I-4a el informe medía TIP contra la tasa NOMINAL a 5 años (esta prueba lo fijaba como
    «cambio de la tasa = Δ nominal»). Desde I-4a, sin serie de tasa real en la base, TIP no tiene cambio de tasa, duración,
    explicado ni resto; su retorno se sigue midiendo. El catálogo no cambia (plazo 5, solo como dato del fondo)."""
    _, nominal, etfs = _escenario_tip()
    assert ETFS_RENTA_FIJA["TIP"]["plazo_referencia"] == 5
    for columna in ("Cambio de la tasa (pp)", "Duración medida (años)", "Explicado por la duración (%)", "Resto (%)"):
        assert pd.isna(etfs.loc["TIP", columna]), columna
    assert pd.notna(etfs.loc["TIP", "Retorno del período (%)"])


def test_tip_no_se_atribuye_con_una_tasa_nominal():
    # Fue xfail en I-0 (asignado a I-4a); corregido en I-4a: TIP queda fuera de la atribución (NaN), sin tasa real en la base.
    """Lo correcto, si se atribuye, es −4,5 × Δ tasa real (≈ 0 aquí). Hoy se usa −duración medida × Δ nominal, que
    arrastra los 0,40 pp de inflación de equilibrio: «explica» una caída que no ocurrió y deja un «resto» positivo
    que el informe llama cupones o riesgo de crédito (TIP no tiene riesgo de crédito). Vale también excluir a TIP de
    la atribución (NaN)."""
    real, nominal, etfs = _escenario_tip()
    esperado = -4.5 * _delta(real, DIAS_MES)
    _requisito(abs(-4.5 * _delta(nominal, DIAS_MES) - esperado) > 1.0, "nominal y real deberían diferir lo suficiente")
    explicado = etfs.loc["TIP", "Explicado por la duración (%)"]
    assert pd.isna(explicado) or abs(explicado - esperado) < 0.25, f"explicado {explicado:.2f}% vs {esperado:.2f}% con la tasa real"


# ---------------------------------------------------------------------------
# 6. Carry y convexidad
# ---------------------------------------------------------------------------
def _entradas_carry():
    """Tasas en torno a 5% sin tendencia. Los precios devengan la tasa cada día (carry) y responden a −D × Δy."""
    y = _paseo(61, 5.0, 0.02)
    carry = np.concatenate([[0.0], y[:-1] / 100 / 252])
    duraciones = {"SHY": 1.9, "IEF": 6.5}
    precios = pd.DataFrame({t: _precio(carry - d * _cambios(y)) for t, d in duraciones.items()}, index=FECHAS)
    return carry, _macro(lambda p: y), precios


def _escenario_carry():
    carry, macro, precios = _entradas_carry()
    return carry, inf.calcular(macro, precios, 365, "Último año")


def test_limitacion_sin_termino_de_carry_el_devengo_de_un_anio_queda_entero_en_el_resto():
    """LIMITACIÓN cuantificada (no un error de cálculo): el modelo del informe es retorno = −D·Δy + resto. En un mundo
    donde lo único que falta en ese modelo es el devengo, el resto es el devengo: ≈ 5% en un año, de igual tamaño
    que un movimiento de tasas de 1 pp en IEF. Fuera de este escenario el resto NO se puede leer como carry."""
    carry, datos = _escenario_carry()
    fin = FECHAS[-1]
    inicio = FECHAS.get_loc(_inicio(fin, 365))
    devengo = (np.prod(1 + carry[inicio + 1:]) - 1) * 100
    for ticker in ("SHY", "IEF"):
        resto = datos["etfs"].loc[ticker, "Resto (%)"]
        assert resto == pytest.approx(devengo, abs=0.3), ticker
        assert resto > 4.0, ticker  # materialmente distinto de cero


def test_el_resto_de_un_etf_del_tesoro_no_se_atribuye_a_riesgo_de_credito():
    # Fue xfail en I-0 (asignado a I-3); corregido en I-3: la nota del Cuadro 2 se arma según los grupos presentes.
    """Solo hay ETFs del Tesoro de EEUU, cuyo riesgo de impago se trata como nulo en este análisis (es la referencia
    libre de riesgo del propio informe). Nombrar el crédito como causa de su resto es un error objetivo.

    Hasta I-2 el defecto estaba en el resumen («…atribuible a cupones, riesgo de crédito…»). I-2 reemplazó esa frase
    fija, pero el defecto sigue en la nota del Cuadro 2, que rotula el resto igual para todos los ETFs: la prueba se
    extendió a esa nota para no perder la evidencia. Se corrige en I-3, con el resto rotulado según el activo."""
    _, macro, precios = _entradas_carry()
    datos = inf.calcular(macro, precios, 365, "Último año")
    _requisito((datos["etfs"]["Grupo"] == "Tesoro EEUU").all(), "solo deberían entrar ETFs del Tesoro")
    frase = _frase(inf._resumen(datos), "La duración explica")
    assert frase is None or "riesgo de crédito" not in frase, frase
    texto = _texto_pdf(inf.generar(macro, precios, "Último año"))
    _requisito("Cuadro 2." in texto, "el PDF debería traer el Cuadro 2")
    nota = texto[texto.find("Cuadro 2."):texto.find("Gráfico 3")]
    assert "riesgo de crédito" not in nota, nota


def _precio_bono(tasa: float, cupon: float = 0.05, anios: int = 20, m: int = 2) -> float:
    k = np.arange(1, anios * m + 1)
    flujos = np.full(len(k), cupon / m * 100.0)
    flujos[-1] += 100.0
    return float(np.sum(flujos / (1 + tasa / m) ** k))


def test_limitacion_la_tabla_de_sensibilidad_es_lineal_y_la_convexidad_es_material_en_plazos_largos():
    """LIMITACIÓN declarada en la nota del Cuadro 3. Un bono a la par a 20 años con 5%: la aproximación lineal con su
    duración modificada se equivoca en más de 0,5 pp ante ±1 pp, subestima las alzas y sobreestima las caídas
    (justo lo que dice la nota). La tabla del informe es simétrica por construcción."""
    y, h = 0.05, 1e-6
    p0 = _precio_bono(y)
    modificada = -(_precio_bono(y + h) - _precio_bono(y - h)) / (2 * h) / p0
    for dy in (+0.01, -0.01):
        exacto = (_precio_bono(y + dy) / p0 - 1) * 100
        lineal = -modificada * dy * 100
        assert exacto - lineal > 0.5, dy  # la convexidad siempre suma: el lineal se queda corto al subir y exagera al caer
    tabla = inf._tabla_sensibilidad(pd.DataFrame(
        {"Duración medida (años)": [round(modificada, 2)], "Error de la duración": [0.2]}, index=["TLT"]))
    assert tabla["+1.0 pp"].iloc[0] == ib.pct(-round(modificada, 2), 1, True)
    assert tabla["-1.0 pp"].iloc[0] == ib.pct(round(modificada, 2), 1, True)
    assert "ignora la convexidad" in inspect.getsource(inf.generar)


# ---------------------------------------------------------------------------
# 7. Sensibilidad empírica frente a duración (I-5)
# ---------------------------------------------------------------------------
def _escenario_spread():
    """LQD con duración efectiva 8. Su tasa = Tesoro + spread, y el spread se mueve la mitad y en contra del Tesoro
    (Δs = −0,5·Δy + ruido), algo habitual en bonos de empresas. El precio responde a −8 × (Δy + Δs)."""
    y = _paseo(71, 4.0, 0.03)
    dy = _cambios(y)
    ds = -0.5 * dy + np.random.default_rng(171).normal(0, 0.005, N) / 100
    precios = pd.DataFrame({"LQD": _precio(-8.0 * (dy + ds))}, index=FECHAS)
    return _macro(lambda p: y), precios


def test_la_regresion_mide_la_sensibilidad_a_la_tasa_de_referencia_y_no_la_duracion_efectiva():
    """Comportamiento correcto del cálculo (la regresión hace lo que dice), cuya lectura hay que acotar: la pendiente
    esperada es 8 × (1 − 0,5) = 4, la mitad de la duración efectiva."""
    macro, precios = _escenario_spread()
    medida = inf.calcular(macro, precios, DIAS_MES, MES)["etfs"].loc["LQD", "Duración medida (años)"]
    assert medida == pytest.approx(4.0, abs=0.3)
    assert medida < 6.0  # lejos de la duración efectiva (8)


def test_el_informe_no_afirma_que_la_pendiente_sea_la_duracion():
    # Fue xfail en I-0 (asignado a I-5); corregido en I-5a (lenguaje). Los errores HAC quedan para I-5b.
    """En el escenario anterior la pendiente es 4 y la duración efectiva 8: la frase general es falsa. Lo defendible es
    «sensibilidad empírica frente a la tasa de X años», que coincide con la duración solo bajo supuestos."""
    macro, precios = _escenario_spread()
    texto = _texto_pdf(inf.generar(macro, precios, MES))
    assert "La pendiente de esa relación es la duración" not in texto


# ---------------------------------------------------------------------------
# 8. Datos atrasados (I-7)
# ---------------------------------------------------------------------------
def test_un_etf_atrasado_no_se_compara_con_los_demas_bajo_una_fecha_general():
    # Fue xfail en I-0 (asignado a I-7); se adelantó a I-1 porque la ventana común no es correcta sin excluir atrasados.
    """La portada dice «Datos de mercado al <la fecha MÁS reciente>» y TLT entra con su retorno hasta 20 ruedas antes,
    comparado en la misma tabla con ETFs al día. La pantalla ya marca el atraso (más de 5 días hábiles); el informe
    no lo usa. Esperado: TLT fuera de la comparación o sin retorno del período."""
    y, precios = _mundo_lineal(81, DURACIONES_LINEALES)
    precios.loc[precios.index[N - 20:], "TLT"] = np.nan
    _requisito(np.busday_count(precios["TLT"].last_valid_index().date(), precios.index[-1].date())
               > rfui.DIAS_HABILES_DE_ATRASO, "TLT debería estar atrasado")
    datos = inf.calcular(_macro(lambda p: y), precios, DIAS_MES, MES)
    _requisito(datos["hasta"] == FECHAS[-1], "la fecha general es la más reciente")
    etfs = datos["etfs"]
    assert "TLT" not in etfs.index or pd.isna(etfs.loc["TLT", "Retorno del período (%)"])


# ---------------------------------------------------------------------------
# 9. Cifras y textos (I-6, I-7)
# ---------------------------------------------------------------------------
EXTRAS_CHILE = {
    rfui.NOMBRE_BCP10: 8.40, rfui.NOMBRE_BCU10: 1.20, rfui.NOMBRE_TPM_CHILE: 4.50, rfui.NOMBRE_TPM_EEUU: 3.88,
}


def test_las_cifras_de_chile_del_resumen_son_las_calculadas():
    y, precios = _mundo_lineal(91, {"SHY": 1.9, "IEF": 6.5})
    datos = inf.calcular(_macro(lambda p: y, extras=EXTRAS_CHILE), precios, DIAS_MES, MES)
    chile = datos["chile"]
    assert chile["inflacion_implicita"] == pytest.approx(8.40 - 1.20)
    assert chile["diferencial"] == pytest.approx(4.50 - 3.88)
    frase = _frase(inf._resumen(datos), "En Chile")
    # I-6c: la diferencia de dos tasas va en puntos porcentuales («7.20 pp»), no como tasa («7.20%»).
    assert "7.20 pp" in frase and ib.pct(7.20) not in frase and ib.pct(8.40) in frase and ib.pct(1.20) in frase


def test_el_recuadro_de_la_uf_usa_las_tasas_de_los_datos_y_no_cifras_fijas():
    # Fue xfail en I-0 (asignado a I-6); corregido en I-6: el recuadro usa BCP y BCU de su fecha, o ninguna cifra.
    y, precios = _mundo_lineal(92, {"SHY": 1.9, "IEF": 6.5})
    texto = _texto_pdf(inf.generar(_macro(lambda p: y, extras=EXTRAS_CHILE), precios, MES))
    _requisito(ib.pct(8.40) in texto, "el PDF debería traer el BCP de los datos")
    assert "2,6%" not in texto and "6,0%" not in texto


def test_un_valor_que_redondea_a_cero_no_se_imprime_con_signo_negativo():
    # Fue xfail en I-0 (asignado a I-7); corregido en I-7: informe_base.num imprime sin signo lo que se lee como cero.
    etfs = pd.DataFrame({
        "Plazo de referencia": [3], "Cambio de la tasa (pp)": [0.0004], "Duración medida (años)": [2.43],
        "Explicado por la duración (%)": [-0.0009], "Retorno del período (%)": [0.13], "Resto (%)": [0.1309],
        "R² con la tasa": [0.76],
    }, index=["VCSH"])
    tabla = inf._tabla_atribucion(etfs)
    assert not tabla.astype(str).apply(lambda c: c.str.contains(r"-0\.00\b")).any().any(), tabla.to_dict("records")


# ---------------------------------------------------------------------------
# 10. Reproducibilidad (I-1)
# ---------------------------------------------------------------------------
def _numeros(etfs: pd.DataFrame) -> pd.DataFrame:
    return etfs.drop(columns=["ultima_fecha"]).select_dtypes("number")


def test_las_cifras_no_dependen_del_dia_en_que_se_genera(monkeypatch):
    """Con la misma base, las cifras no cambian con el día de generación. (Antes de I-1 `calcular` llamaba a
    pd.Timestamp.now() solo para la marca de atraso de la pantalla; desde I-1 le pasa el fin de la ventana.)"""
    y, precios = _mundo_lineal(101, DURACIONES_LINEALES)
    macro = _macro(lambda p: y)
    hoy = _numeros(inf.calcular(macro, precios, DIAS_MES, MES)["etfs"])
    original = rfui._resumen_de_etfs
    monkeypatch.setattr(inf.rfui, "_resumen_de_etfs", lambda p, m, _hoy: original(p, m, pd.Timestamp("2099-12-31")))
    otro_dia = _numeros(inf.calcular(macro, precios, DIAS_MES, MES)["etfs"])
    pd.testing.assert_frame_equal(hoy, otro_dia)


def test_con_una_fecha_de_corte_explicita_el_informe_de_un_dia_pasado_se_reproduce():
    # Fue xfail en I-0 (defecto); corregido en I-1 con `fecha_corte`.
    """Con datos que siguieron llegando después de T, pedir el informe «al T» debe dar lo mismo que se habría obtenido
    el día T. Hoy calcular() y generar() no aceptan una fecha de corte."""
    y, precios = _mundo_lineal(102, DURACIONES_LINEALES)
    macro = _macro(lambda p: y)
    corte = FECHAS[-30]
    for funcion in (inf.calcular, inf.generar):
        nombres = [p for p in inspect.signature(funcion).parameters if re.search(r"corte|hasta|as_of", p)]
        assert nombres, f"{funcion.__name__} no acepta una fecha de corte"
    parametro = next(p for p in inspect.signature(inf.calcular).parameters if re.search(r"corte|hasta|as_of", p))
    al_dia_t = inf.calcular(macro[pd.to_datetime(macro["fecha"]) <= corte], precios[precios.index <= corte], DIAS_MES, MES)
    con_corte = inf.calcular(macro, precios, DIAS_MES, MES, **{parametro: corte})
    pd.testing.assert_frame_equal(_numeros(al_dia_t["etfs"]), _numeros(con_corte["etfs"]))
