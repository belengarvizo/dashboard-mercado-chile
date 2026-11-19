"""Etapa 1, intervención I-2: conclusiones del informe de renta fija condicionadas a los datos.

QUÉ SE COMPRUEBA
    Que cada frase interpretativa aparezca solo si sus condiciones se cumplen: dirección y forma de la curva con
    umbrales de materialidad ajustados al horizonte, spreads, consistencia entre el retorno y lo que anticipa la
    sensibilidad a tasas (sin usar R² como prueba ni cocientes con denominador cercano a cero), comparaciones entre
    fondos con su PROPIA tasa de referencia, y ausencia de lenguaje causal.

CÓMO
    Offline y con datos sintéticos. La mayoría de los casos llama a las funciones de evaluación con números elegidos,
    cuyo resultado esperado se calcula a mano en la propia prueba. Unos pocos escenarios completos verifican el PDF.

POR QUÉ ES UN ARCHIVO APARTE
    tests/conftest.py omitiría sin base de pruebas cualquier prueba nueva dentro de test_informe_renta_fija.py.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

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

U = inf.UMBRALES
CAUSAL = re.compile(r"\bcaus|se debe a|debido a|porque las tasas|provoc|gracias a|explican? la mayor parte|decidió", re.I)


# ---------------------------------------------------------------------------
# Constructores
# ---------------------------------------------------------------------------
def _curva(d2: float, d5: float, d10: float, nivel10: float = 4.0) -> dict:
    """Curva con cambios en pb para 2, 5 y 10 años (el resto de los plazos interpolado; no se usa)."""
    plazos = list(et.PLAZOS_ANIOS.values())
    cambios_pp = pd.Series(np.interp(plazos, [2.0, 5.0, 10.0], [d2, d5, d10]) / 100, index=plazos)
    fin = pd.Series(nivel10, index=plazos)
    return {"inicio": fin - cambios_pp, "fin": fin, "fecha_inicio": pd.Timestamp("2026-10-14"),
            "fecha_fin": pd.Timestamp("2026-11-13"), "cambio": cambios_pp}


CTX = {"ruedas": 21, "sigma_plazo": {}, "sigma_pendiente": None, "dias": 30}  # sin variabilidad: mandan los pisos


def _fila(R, beta, cambio_pp, se=0.1, r2=0.94, plazo=7, estado=inf.ESTADO_CALCULABLE):
    X = -beta * cambio_pp if cambio_pp is not None else np.nan
    return pd.Series({"Retorno del período (%)": R, "Explicado por la duración (%)": X, "Duración medida (años)": beta,
                      "Error de la duración": se, "R² con la tasa": r2, "Cambio de la tasa (pp)": cambio_pp,
                      "Plazo de referencia": plazo, "Estado de la atribución": estado})


def _credito(cambio_pp: float) -> dict:
    return {"inicio": 1.44, "fin": 1.44 + cambio_pp, "cambio": cambio_pp, "fecha_inicio": pd.Timestamp("2026-10-14"),
            "fecha_fin": pd.Timestamp("2026-11-13"), "maximo": 1.6, "fecha_maximo": pd.Timestamp("2026-11-05")}


def _tabla(filas: dict) -> pd.DataFrame:
    tabla = pd.DataFrame(filas).T
    for c in tabla.columns:
        if c != "Estado de la atribución":
            tabla[c] = pd.to_numeric(tabla[c])
    tabla["Grupo"] = [inf.ETFS_RENTA_FIJA[t]["grupo"] for t in tabla.index]
    tabla["Resto (%)"] = tabla["Retorno del período (%)"] - tabla["Explicado por la duración (%)"]
    return tabla


def _datos(etfs, ctx=None, credito=None):
    return {"etfs": etfs, "contexto": ctx or CTX, "credito": credito, "fechas": {"motivo_sin_ventana": None}}


# ---------------------------------------------------------------------------
# Umbrales: horizonte y bordes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sigma, ruedas, esperado", [
    (6.0, 21, 0.25 * 6.0 * 21 ** 0.5),    # un mes: 6,87 pb
    (6.0, 63, 0.25 * 6.0 * 63 ** 0.5),    # tres meses: 11,91 pb
    (6.0, 252, 0.25 * 6.0 * 252 ** 0.5),  # un año: 23,81 pb
    (1.0, 21, 5.0),                       # poca variabilidad: manda el piso
    (None, 21, 5.0),                      # sin datos de variabilidad: el piso
])
def test_el_umbral_de_materialidad_crece_con_el_horizonte_y_nunca_baja_del_piso(sigma, ruedas, esperado):
    """Un mismo cambio de 6 pb es material en un mes con poca variabilidad y no lo es en un año."""
    assert inf._umbral(U["pb_tasa"], sigma, ruedas) == pytest.approx(esperado)


@pytest.mark.parametrize("cambio, umbral, clase", [
    (0.4, 5.0, inf.SIN_CAMBIO), (-0.49, 5.0, inf.SIN_CAMBIO), (0.5, 5.0, inf.ESTABLE), (4.9, 5.0, inf.ESTABLE),
    (5.0, 5.0, inf.SUBE), (5.1, 5.0, inf.SUBE), (-5.1, 5.0, inf.BAJA), (6.0, 6.874, inf.ESTABLE), (-7.0, 6.874, inf.BAJA),
])
def test_clasificacion_de_un_cambio_en_los_bordes(cambio, umbral, clase):
    assert inf._clasificar_cambio(cambio, umbral) == clase


# ---------------------------------------------------------------------------
# Curva del Tesoro
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("d2, d5, d10, debe, no_debe", [
    (0.3, 0.0, -0.2, ["prácticamente no se movió", "no cambió (menos de 1 pb)"], ["subió", "bajó", "al alza", "a la baja"]),
    (3.0, 1.0, -1.0, ["prácticamente no se movió", "+3.0 pb", "-1.0 pb"], ["subió", "bajó"]),
    # la pendiente cambia exactamente 5 pb (el umbral): es un aplanamiento aunque ningún tramo sea material por sí solo
    (3.0, 1.0, -2.0, ["se aplanó sin que ninguno de los dos tramos se moviera de forma material", "disminuyó 5 pb"], ["subió", "bajó"]),
    (-30.0, -29.0, -28.0, ["a la baja de forma aproximadamente paralela", "bajó 30 pb (0.30 pp)", "bajó 28 pb (0.28 pp)"], ["torsión"]),
    (30.0, 0.0, -30.0, ["torsión", "subió 30 pb", "bajó 30 pb", "disminuyó 60 pb", "aplanamiento"], ["paralela"]),
    (10.0, 22.0, 35.0, ["se empinó en un contexto de alza de tasas, más intensa en el tramo largo", "aumentó 25 pb"], ["torsión"]),
    (-35.0, -22.0, -10.0, ["se empinó en un contexto de baja de tasas, más intensa en el tramo corto"], ["torsión"]),
    (35.0, 22.0, 10.0, ["se aplanó en un contexto de alza de tasas, más intensa en el tramo corto"], ["torsión"]),
    (-10.0, -22.0, -35.0, ["se aplanó en un contexto de baja de tasas, más intensa en el tramo largo"], ["torsión"]),
    (-27.0, -30.0, -33.0, ["se desplazó a la baja, con un leve aplanamiento", "disminuyó 6 pb"], ["torsión", "se aplanó"]),
    (20.0, 40.0, 20.0, ["al alza de forma aproximadamente paralela", "El tramo de 5 años no acompañó", "+20 pb"], ["torsión"]),
    (6.0, 1.0, -4.0, ["se aplanó por el alza del tramo corto", "subió 6 pb", "prácticamente no cambió (-4.0 pb)"],
     ["torsión", "contexto de alza"]),
])
def test_forma_de_la_curva(d2, d5, d10, debe, no_debe):
    afirmacion = inf._afirmacion_curva(_curva(d2, d5, d10), CTX)
    assert afirmacion.nivel == inf.NIVEL_HALLAZGO
    for texto in debe:
        assert texto in afirmacion.texto, (texto, afirmacion.texto)
    for texto in no_debe:
        assert texto not in afirmacion.texto, (texto, afirmacion.texto)


@pytest.mark.parametrize("piso, esperado", [
    (3.0, "torsión"),                                                   # los dos tramos materiales y opuestos
    (5.0, "se aplanó por el alza del tramo corto"),                     # solo 2 años material
    (10.0, "se aplanó sin que ninguno de los dos tramos se moviera"),   # solo la pendiente (−10 pb) llega al umbral
    (12.0, "prácticamente no se movió"),                                # nada llega al umbral
])
def test_sensibilidad_de_la_descripcion_de_la_curva_al_umbral(monkeypatch, piso, esperado):
    """El mismo movimiento (+6 / −4 pb, pendiente −10 pb) cambia de nombre según el umbral: por eso el umbral es
    explícito, central y documentado en el informe."""
    monkeypatch.setitem(inf.UMBRALES, "pb_tasa", piso)
    assert esperado in inf._afirmacion_curva(_curva(6.0, 1.0, -4.0), CTX).texto


def test_con_mucha_variabilidad_un_cambio_pequeno_en_un_anio_no_es_alza():
    """10 pb en un año, con un desvío diario de 6 pb: el umbral es 23,8 pb, así que no hay «alza»."""
    ctx = {"ruedas": 252, "sigma_plazo": {2.0: 6.0, 5.0: 6.0, 10.0: 6.0}, "sigma_pendiente": 4.0}
    texto = inf._afirmacion_curva(_curva(10.0, 10.0, 10.0), ctx).texto
    assert "prácticamente no se movió" in texto and "subió" not in texto


def test_sin_curva_completa_la_evidencia_es_insuficiente():
    afirmacion = inf._afirmacion_curva(None, CTX)
    assert afirmacion.nivel == inf.NIVEL_INSUFICIENTE and "No es posible describir" in afirmacion.texto


# ---------------------------------------------------------------------------
# Spread de crédito
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cambio_pp, debe, no_debe", [
    (0.0, ["no cambió"], ["se amplió", "se comprimió"]),
    (0.03, ["prácticamente no cambió", "+3.0 pb"], ["se amplió", "se comprimió"]),
    (0.12, ["se amplió 12 pb", "compensación más alta"], ["se comprimió"]),
    (-0.08, ["se comprimió 8 pb", "compensación más baja"], ["se amplió"]),
])
def test_spread_de_credito(cambio_pp, debe, no_debe):
    texto = inf._afirmacion_credito(_credito(cambio_pp), {"ruedas_spread": 21}).texto
    for t in debe:
        assert t in texto, (t, texto)
    for t in no_debe:
        assert t not in texto, (t, texto)


# ---------------------------------------------------------------------------
# Atribución de cada ETF
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ticker, fila, credito, clase", [
    # Δy −20 pb, β 6,5 → X = +1,30%; R = +1,45%: |R − X| = 0,15 ≤ 0,5·1,45
    ("IEF", _fila(1.45, 6.5, -0.20), None, "consistente"),
    # X = −4·0,20 = −0,80% y R = +1,70%: signos opuestos
    ("IEI", _fila(1.70, 4.0, 0.20, plazo=5), None, "contraria"),
    # X = +1,30%, R = +2,00%: |R − X| = 0,70 > 0,5·2 = 1,0? no, 0,70 ≤ 1,0 → consistente; con R = 3,0: 1,70 ≤ 3,0 → parcial
    ("IEF", _fila(3.00, 6.5, -0.20), None, "parcial"),
    # X = +1,30%, R = +0,50%: |R − X| = 0,80 > 1,0·0,50 → la magnitud no coincide
    ("IEF", _fila(0.50, 6.5, -0.20), None, "magnitud"),
    # R = +0,05%: el denominador es casi cero; no se calcula ningún cociente, se informa que el precio no se movió
    ("IEF", _fila(0.05, 6.5, -0.20), None, "precio_quieto"),
    # Δy = 3 pb (< 5): con retorno material, la tasa quieta no puede explicarlo; sin retorno material, nada se movió
    ("IEF", _fila(1.00, 6.5, 0.03), None, "tasa_quieta"),
    ("IEF", _fila(0.05, 6.5, 0.03), None, "sin_movimiento"),
    # β 1,9 y Δy 5 pb → X = −0,095%: menor que el piso de 0,10 pp
    ("SHY", _fila(-0.50, 1.9, 0.05, plazo=2), None, "efecto_pequeno"),
    # R² ALTO no rescata una atribución deficiente
    ("IEI", _fila(1.70, 4.0, 0.20, plazo=5, r2=0.97), None, "contraria"),
    ("IEF", _fila(0.50, 6.5, -0.20, r2=0.97), None, "magnitud"),
    # coincidencia con R² bajo o error estándar grande: no concluyente
    ("IEF", _fila(1.45, 6.5, -0.20, r2=0.34), None, "imprecisa"),
    ("IEF", _fila(1.45, 6.5, -0.20, se=1.3), None, "imprecisa"),
    # fondo de crédito con el spread moviéndose 25 pb: la coincidencia puede ser compensación de efectos
    ("LQD", _fila(1.45, 6.5, -0.20, plazo=10), _credito(0.25), "credito"),
    ("LQD", _fila(1.45, 6.5, -0.20, plazo=10), _credito(0.02), "consistente"),
    # TIP: aunque la fila traiga una sensibilidad contra la tasa nominal, no se contrasta (I-4a: responde a tasas reales)
    ("TIP", _fila(1.45, 6.5, -0.20, plazo=5), None, "sin_tasa_real"),
    ("TLT", _fila(1.45, 6.5, None, plazo=20, estado="no calculable: la tasa a 20 años no tiene datos desde el 30-10-2026"),
     None, "no_calculable"),
])
def test_clasificacion_de_la_atribucion(ticker, fila, credito, clase):
    ctx = {**CTX, "ruedas_spread": 21}
    assert inf._evaluar_atribucion(ticker, fila, ctx, credito)["clase"] == clase


def test_la_frase_de_cada_etf_usa_sus_cifras():
    ev = inf._evaluar_atribucion("IEF", _fila(1.45, 6.5, -0.20), CTX, None)
    frase = inf._frase_de_evaluacion(ev)
    assert ib.pct(1.45, 2, True) in frase and ib.pct(1.30, 2, True) in frase and "-20 pb" in frase and "7 años" in frase
    assert "en línea con" in frase


def test_errores_que_se_compensan_entre_fondos_no_producen_una_conclusion_favorable():
    """IEF: anticipaba +1,30% y rindió +3,60% (magnitud no coincide). IEI: anticipaba +0,80% y rindió −1,50% (contraria).
    En promedio lo anticipado (1,05%) coincide con lo observado (1,05%): agregado parecería un ajuste perfecto. Cada
    fondo se evalúa por separado y ninguno es consistente."""
    etfs = _tabla({"IEF": _fila(3.60, 6.5, -0.20), "IEI": _fila(-1.50, 4.0, -0.20, plazo=5)})
    _assert_promedio = np.isclose(etfs["Retorno del período (%)"].mean(), etfs["Explicado por la duración (%)"].mean())
    assert _assert_promedio
    texto = inf._afirmacion_atribucion({**_datos(etfs)}, inf._evaluaciones(_datos(etfs))).texto
    assert "consistente" not in texto and "sentido contrario" in texto


# ---------------------------------------------------------------------------
# Comparación entre fondos
# ---------------------------------------------------------------------------
def test_la_comparacion_usa_la_tasa_de_referencia_de_cada_fondo():
    """SHY (β 1,9, tasa a 2 años +110 pb) y TLT (β 16, tasa a 20 años +95 pb). Brecha anticipada con las tasas
    PROPIAS: −1,9·1,10 − (−16·0,95) = −2,09 + 15,20 = 13,11 pp. Con una sola tasa (+110 pb) daría 15,51 pp."""
    etfs = _tabla({"SHY": _fila(-2.00, 1.9, 1.10, plazo=2), "TLT": _fila(-15.00, 16.0, 0.95, plazo=20)})
    afirmacion = inf._afirmacion_comparacion(_datos(etfs))
    assert afirmacion.nivel == inf.NIVEL_INTERPRETACION
    assert "13.11 pp" in afirmacion.texto and "15.51" not in afirmacion.texto
    assert "es consistente con sus distintas sensibilidades a tasas" in afirmacion.texto
    assert "aunque no la única" in afirmacion.texto  # el plazo no se presenta como causa exclusiva


def test_si_el_nivel_no_es_consistente_la_brecha_consistente_se_acota_a_la_diferencia():
    """Tasas +20 pb y un factor común positivo en los dos fondos. SHY: X = −1,9·0,20 = −0,38%, R = +2,12%.
    IEF: X = −6,5·0,20 = −1,30%, R = +1,20%. Cada retorno va en sentido contrario a lo anticipado, pero la brecha
    observada (2,12 − 1,20 = 0,92 pp) es igual a la anticipada (−0,38 − (−1,30) = 0,92 pp): el factor común se cancela
    en la diferencia. El texto puede decir que la brecha es consistente, pero debe acotarlo a la diferencia."""
    etfs = _tabla({"SHY": _fila(2.12, 1.9, 0.20, plazo=2), "IEF": _fila(1.20, 6.5, 0.20)})
    afirmacion = inf._afirmacion_comparacion(_datos(etfs))
    assert "es consistente con sus distintas sensibilidades" in afirmacion.texto
    assert "se refiere solo a la diferencia entre ambos" in afirmacion.texto


def test_fondos_de_riesgos_distintos_no_se_comparan_por_plazo():
    etfs = _tabla({"HYG": _fila(1.57, 3.9, 0.05, plazo=5), "LQD": _fila(-1.42, 4.1, 0.05, plazo=10)})
    texto = inf._afirmacion_comparacion(_datos(etfs)).texto
    assert "la diferencia no proviene del plazo" in texto
    assert "no permiten atribuir la diferencia de rentabilidad exclusivamente al plazo" in texto
    assert "riesgo de crédito alto" in texto


def test_el_mismo_grupo_no_basta_para_comparar_por_plazo():
    """VCSH y LQD son ambos «Empresas», pero difieren también en la composición de su crédito."""
    etfs = _tabla({"LQD": _fila(1.30, 7.3, -0.18, plazo=10), "VCSH": _fila(0.20, 2.4, -0.10, plazo=3)})
    afirmacion = inf._afirmacion_comparacion(_datos(etfs))
    assert afirmacion.nivel == inf.NIVEL_INSUFICIENTE and "consistente" not in afirmacion.texto


def test_dos_fondos_del_tesoro_con_sensibilidades_parecidas_no_se_comparan_por_plazo():
    etfs = _tabla({"IEI": _fila(1.20, 4.0, -0.20, plazo=5), "IEF": _fila(0.60, 4.5, -0.20, plazo=7)})
    texto = inf._afirmacion_comparacion(_datos(etfs)).texto
    assert "demasiado parecidas para atribuir la diferencia al plazo" in texto


def test_sensibilidades_distintas_y_retornos_parecidos_con_tasas_quietas():
    etfs = _tabla({"SHY": _fila(0.30, 1.9, -0.02, plazo=2), "TLT": _fila(0.35, 16.0, -0.02, plazo=20)})
    afirmacion = inf._afirmacion_comparacion(_datos(etfs))
    assert afirmacion.nivel == inf.NIVEL_HALLAZGO
    assert "fueron similares" in afirmacion.texto and "prácticamente no se movieron" in afirmacion.texto


@pytest.mark.parametrize("brecha, material", [(0.20, False), (0.25, True)])
def test_la_brecha_material_depende_de_la_volatilidad_de_la_brecha(brecha, material):
    """Desvío diario de la brecha 0,20 pp y 21 ruedas: umbral = 0,25·0,20·√21 = 0,229 pp (sobre el piso de 0,10)."""
    rng = np.random.default_rng(5)
    diferencia = rng.normal(0, 1, 252)
    diferencia = (diferencia - diferencia.mean()) / diferencia.std(ddof=1) * 0.20
    retornos = pd.DataFrame({"SHY": np.zeros(252), "TLT": -diferencia})
    ctx = {**CTX, "retornos": retornos}
    etfs = _tabla({"SHY": _fila(0.10 + brecha, 1.9, -0.02, plazo=2), "TLT": _fila(0.10, 16.0, -0.02, plazo=20)})
    texto = inf._afirmacion_comparacion(_datos(etfs, ctx)).texto
    assert ("fueron similares" in texto) is (not material), texto


# ---------------------------------------------------------------------------
# Escenarios completos
# ---------------------------------------------------------------------------
FECHAS = pd.bdate_range("2025-06-02", "2026-11-16")


def _macro(y: np.ndarray, extras: dict | None = None) -> pd.DataFrame:
    filas = [{"nombre": rfui.nombre_treasury(e), "fecha": f, "valor": float(v)}
             for e in et.PLAZOS_ANIOS for f, v in zip(FECHAS, y)]
    for nombre, valores in (extras or {}).items():
        filas += [{"nombre": nombre, "fecha": f, "valor": float(v)} for f, v in zip(FECHAS, np.broadcast_to(valores, len(FECHAS)))]
    return pd.DataFrame(filas)


def _escenario(duraciones: dict, salto: float = 0.0, carry: bool = False, extras=None, semilla: int = 1):
    rng = np.random.default_rng(semilla)
    y = 4.0 + np.concatenate([[0.0], rng.normal(0, 0.03, len(FECHAS) - 1)]).cumsum()
    if salto:
        y[-10:] += salto
    cambios = np.diff(y, prepend=y[0]) / 100
    devengo = np.concatenate([[0.0], y[:-1] / 100 / 252]) if carry else 0.0
    precios = pd.DataFrame({t: 100 * np.cumprod(1 + devengo - d * cambios) for t, d in duraciones.items()}, index=FECHAS)
    return y, _macro(y, extras), precios


def test_sin_datos_suficientes_la_atribucion_lo_dice():
    _, macro, precios = _escenario({"SHY": 1.9, "IEF": 6.5})
    datos = inf.calcular(macro, precios, 10_000, "Último año")
    afirmacion = next(a for a in datos["afirmaciones"] if a.clave == "atribucion")
    assert afirmacion.nivel == inf.NIVEL_INSUFICIENTE and "No es posible contrastar" in afirmacion.texto
    assert next(a for a in datos["afirmaciones"] if a.clave == "curva").nivel == inf.NIVEL_INSUFICIENTE


def test_en_un_anio_sin_carry_modelado_el_informe_advierte_que_el_modelo_es_parcial():
    """Precios que devengan ~4% anual además de responder a las tasas.

    Hasta I-2 ningún fondo tenía devengo en el modelo, y esta prueba exigía que un fondo dominado por el devengo no
    quedara «consistente» (regla |R − X| ≤ 0,5·|R|). Desde I-3, en los fondos del Tesoro se descuenta un devengo
    aproximado y se compara R − c con X: esa protección sigue vigente para los fondos cuyo devengo NO se estima (aquí
    VCSH, de crédito y duración corta, donde el devengo pesa más que el efecto de tasas), y el texto la sigue
    advirtiendo, dimensionada con la tasa mediana al inicio × días / 365, sin presentarla como carry estimado.

    Tesoro (SHY, IEF): lo comparado es R − tasa al inicio × días / 365; la conclusión se presenta como compatibilidad
    con una aproximación (no como identificación de todas las causas) y, en un año, advierte su menor precisión.
    Crédito (VCSH): ningún texto atribuye su residuo al spread, al crédito o al cupón por separado."""
    y, macro, precios = _escenario({"SHY": 1.9, "IEF": 6.5, "VCSH": 1.5}, carry=True, semilla=7)
    datos = inf.calcular(macro, precios, 365, "Último año")
    texto = next(a for a in datos["afirmaciones"] if a.clave == "atribucion").texto
    inicio = FECHAS.get_loc(datos["fechas"]["inicio"])
    fin = FECHAS.get_loc(datos["fechas"]["fin"])
    devengo = (np.prod(1 + y[inicio:fin] / 100 / 252) - 1) * 100  # cuenta aparte, con los datos construidos
    orden = y[inicio] * datos["contexto"]["dias"] / 365
    evaluadas = 0
    for ev in datos["evaluaciones"]:
        if ev["ETF"] == "VCSH":
            assert ev["devengo"] is None
            if devengo > 0.5 * abs(ev["retorno"]) + 0.2:  # holgura por el efecto compuesto
                assert ev["clase"] != "consistente", ev
                evaluadas += 1
        else:
            assert ev["retorno_comparado"] == pytest.approx(ev["retorno"] - orden, abs=1e-9), ev
    assert evaluadas == 1, "VCSH debería quedar dominado por el devengo que no se estima"
    assert "VCSH la comparación es parcial" in texto and "no incluye el devengo de cupones" in texto
    assert f"del orden de {ib.num(orden, 2)} pp" in texto
    assert "carry estimado" not in texto
    # Tesoro: compatibilidad con una aproximación, no identificación de causas, y menor precisión en un año.
    assert "no el rendimiento ni el carry de cada fondo" in texto
    assert "no que se hayan identificado todos los componentes del retorno" in texto
    assert "la aproximación es menos precisa" in texto
    for ev in datos["evaluaciones"]:
        frase = inf._frase_de_evaluacion(ev)
        if ev["ETF"] in ("SHY", "IEF"):
            assert "devengo aproximado" in frase, frase
        else:  # crédito: ningún residuo se asigna a un factor
            assert not re.search(r"(spread|crédito|cup[oó]n)[^.]*(explica|corresponde|se debe|atribuible)", frase, re.I), frase
            assert not re.search(r"(resto|diferencia|residuo)[^.]*(spread|crédito|cup[oó]n)", frase, re.I), frase
    assert not re.search(r"(resto|diferencia|residuo)[^.]*(corresponde|se debe|es atribuible)", texto, re.I), texto


def test_ninguna_frase_generada_usa_lenguaje_causal():
    escenarios = [
        _escenario({"SHY": 1.9, "IEF": 6.5, "TLT": 16.0}),
        _escenario({"SHY": 1.9, "TLT": 16.0}, salto=1.0),
        _escenario({"SHY": 1.9, "IEF": 6.5}, carry=True, semilla=7),
        _escenario({"IEF": 6.5, "LQD": 7.3, "HYG": 3.9}, salto=0.3, extras={rfui.NOMBRE_BAA10Y: 1.5}),
    ]
    for _, macro, precios in escenarios:
        for periodo, dias in inf.PERIODOS.items():
            datos = inf.calcular(macro, precios, dias, periodo)
            textos = [a.texto for a in datos["afirmaciones"]] + [inf._frase_de_evaluacion(ev) for ev in datos["evaluaciones"]]
            for texto in textos:
                assert not CAUSAL.search(texto), texto
            for afirmacion in datos["afirmaciones"]:
                assert afirmacion.nivel in (inf.NIVEL_HALLAZGO, inf.NIVEL_INTERPRETACION, inf.NIVEL_INSUFICIENTE)


def _texto_pdf(pdf: bytes) -> tuple[str, int]:
    pymupdf = pytest.importorskip("pymupdf", reason="pymupdf no está instalado: no se puede leer el PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return " ".join(" ".join(p.get_text().split()) for p in doc), doc.page_count


def test_el_pdf_trae_la_lectura_la_nota_metodologica_y_los_recuadros_sin_cifras_inventadas():
    extras = {rfui.NOMBRE_BAA10Y: 1.5, rfui.NOMBRE_BCP10: 6.0, rfui.NOMBRE_BCU10: 2.6}
    _, macro, precios = _escenario({"VCSH": 1.5, "SHY": 1.9, "IEF": 6.5, "TLT": 16.0, "HYG": 3.9}, salto=0.3, extras=extras)
    texto, paginas = _texto_pdf(inf.generar(macro, precios, "Último mes"))
    assert "Lectura de la atribución." in texto and "Criterios de interpretación." in texto
    assert "no identifican causas" in texto
    # «los bonos son seguros» compara solo fondos del Tesoro (VCSH, de empresas, tiene la menor sensibilidad)
    assert "TLT y SHY invierten en bonos del mismo emisor" in texto
    assert "VCSH invierten en bonos del mismo emisor" not in texto and "TLT y VCSH" not in texto
    assert "describe cerca de un" in texto and "casi no existe" not in texto and "se parecen más a una acción" not in texto
    assert "El spread Baa no cambió" in texto  # spread constante: ni «se amplió» ni «se comprimió»
    assert texto.count("Error frecuente") >= 3
    assert texto.count("—") == paginas  # el único «—» del PDF es el del pie de página
    assert not CAUSAL.search(texto.split("6. QUÉ NO DICE ESTE INFORME")[0].replace("No hay causas macroeconómicas", ""))


def test_las_secciones_van_en_orden_y_el_titulo_de_la_seccion_2_es_neutral():
    """Versión sintética de la prueba de integración de secciones (que necesita la base). El título de la sección 2 ya
    no afirma que «la duración manda»: describe qué se analiza, sin adelantar una conclusión."""
    _, macro, precios = _escenario({"SHY": 1.9, "IEF": 6.5, "TLT": 16.0, "HYG": 3.9}, salto=0.3,
                                   extras={rfui.NOMBRE_BAA10Y: 1.5, rfui.NOMBRE_BCP10: 6.0, rfui.NOMBRE_BCU10: 2.6})
    texto, _ = _texto_pdf(inf.generar(macro, precios, "Último año"))
    secciones = ["RESUMEN", "1. QUÉ PASÓ", "2. SENSIBILIDAD A TASAS Y ATRIBUCIÓN DE RETORNOS",
                 "3. EL OTRO MOTOR: EL RIESGO DE CRÉDITO", "4. CHILE: PESOS, UF Y POLÍTICA MONETARIA",
                 "5. QUÉ PASARÍA SI LAS TASAS SE MUEVEN", "6. QUÉ NO DICE ESTE INFORME"]
    posiciones = [texto.find(s) for s in secciones]
    assert all(p >= 0 for p in posiciones), [s for s, p in zip(secciones, posiciones) if p < 0]
    assert posiciones == sorted(posiciones)
    assert "LA DURACIÓN MANDA" not in texto.upper()
