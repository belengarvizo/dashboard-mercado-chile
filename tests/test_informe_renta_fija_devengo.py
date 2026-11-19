"""I-3: devengo aproximado y atribución de retornos de renta fija (offline, datos sintéticos).

QUÉ SE PRUEBA
    - En los fondos del Tesoro nominal (SHY, IEI, IEF, TLT) se descuenta un DEVENGO APROXIMADO = tasa de referencia al
      inicio × días / 365, y lo anticipado por la sensibilidad se contrasta con el retorno neto de ese devengo.
    - En crédito, agregados y emergentes no se estima devengo: la tasa del Tesoro no representa su carry.
    - TIP queda fuera del devengo (su tasa relevante es real; la corrección de fondo es I-4a).
    - Identidad contable: retorno = explicado + resto, y en el Tesoro resto = devengo aproximado + no explicado.
    - Ningún residuo se atribuye a una causa ni se presenta el devengo como exacto o como el carry del fondo.

CÓMO
    Los precios se construyen con un modelo conocido: retorno diario = devengo de la tasa (tasa / 252 por rueda) −
    duración × cambio de la tasa (y − duración × cambio del spread, en crédito). Las cifras esperadas se calculan aparte
    con ese modelo, no llamando al informe.
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

FECHAS = pd.bdate_range("2025-01-06", periods=420)
N = len(FECHAS)
TESORO = {"SHY": 1.9, "IEI": 4.4, "IEF": 6.5, "TLT": 16.0}


def _cambios(tasa_pct):
    return np.diff(tasa_pct, prepend=tasa_pct[0]) / 100.0


def _devengo_diario(tasa_pct):
    return np.concatenate([[0.0], np.asarray(tasa_pct)[:-1] / 100 / 252])


def _precio(retornos):
    r = np.asarray(retornos, dtype=float).copy()
    r[0] = 0.0
    return 100.0 * np.cumprod(1.0 + r)


def _macro(tasa, extras=None, quitar=None):
    """Curva del Tesoro (todos los plazos con la misma tasa), más series sueltas. `quitar`: {(nombre, fecha)} ausentes."""
    filas = []
    for etiqueta in et.PLAZOS_ANIOS:
        nombre = rfui.nombre_treasury(etiqueta)
        filas += [{"nombre": nombre, "fecha": f, "valor": float(v)} for f, v in zip(FECHAS, tasa)
                  if not quitar or (nombre, f) not in quitar]
    for nombre, valores in (extras or {}).items():
        filas += [{"nombre": nombre, "fecha": f, "valor": float(v)} for f, v in zip(FECHAS, np.broadcast_to(valores, N))]
    return pd.DataFrame(filas)


def _paseo(semilla, inicio=4.0, desvio=0.02):
    rng = np.random.default_rng(semilla)
    return inicio + np.concatenate([[0.0], rng.normal(0, desvio, N - 1)]).cumsum()


def _mundo_tesoro(tasa, duraciones=TESORO):
    """Fondos del Tesoro que devengan la tasa y responden a −D × Δy. Nada de crédito."""
    return pd.DataFrame({t: _precio(_devengo_diario(tasa) - d * _cambios(tasa)) for t, d in duraciones.items()}, index=FECHAS)


def _ventana(datos):
    return datos["fechas"]["inicio"], datos["fechas"]["fin"]


def _tasa_en(tasa, fecha):
    return float(tasa[FECHAS.get_loc(fecha)])


def _texto_pdf(pdf: bytes) -> str:
    pymupdf = pytest.importorskip("pymupdf", reason="pymupdf no está instalado: no se puede leer el PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return " ".join(" ".join(p.get_text().split()) for p in doc)


def _nota_cuadro_2(texto: str) -> str:
    return texto[texto.find("Cuadro 2."):texto.find("Gráfico 3")]


# ---------------------------------------------------------------------------
# 1, 5, 9, 10. Tesoro sin crédito: devengo aproximado, identidad y ventanas de distinto largo
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("periodo", list(inf.PERIODOS))
def test_en_el_tesoro_el_devengo_es_la_tasa_al_inicio_por_dias_sobre_365_y_la_identidad_se_conserva(periodo):
    tasa = _paseo(11)
    datos = inf.calcular(_macro(tasa), _mundo_tesoro(tasa), inf.PERIODOS[periodo], periodo)
    inicio, fin = _ventana(datos)
    dias = (fin - inicio).days
    precios = _mundo_tesoro(tasa)
    for ticker, fila in datos["etfs"].iterrows():
        esperado = _tasa_en(tasa, inicio) * dias / 365          # cuenta aparte
        assert fila["Devengo aproximado (%)"] == pytest.approx(esperado, abs=1e-12), ticker
        R, X = fila["Retorno del período (%)"], fila["Explicado por la duración (%)"]
        # El retorno observado sale solo de los precios: el devengo no se le suma ni lo modifica.
        assert R == pytest.approx((precios.loc[fin, ticker] / precios.loc[inicio, ticker] - 1) * 100, abs=1e-10), ticker
        assert R == pytest.approx(X + fila["Resto (%)"], abs=1e-12)
        assert fila["Resto (%)"] == pytest.approx(fila["Devengo aproximado (%)"] + fila["No explicado (%)"], abs=1e-12)


def test_en_un_mundo_sin_mas_factores_que_el_devengo_lo_no_explicado_es_pequeno_y_el_resto_no():
    """Con la tasa casi quieta, el resto de un año es ~4 pp (el devengo) y lo no explicado, la diferencia de convención
    entre el devengo del mundo (tasa/252 por rueda) y la aproximación (tasa/365 por día) más el efecto compuesto."""
    tasa = _paseo(12, desvio=0.005)
    datos = inf.calcular(_macro(tasa), _mundo_tesoro(tasa), 365, "Último año")
    inicio, fin = _ventana(datos)
    i0, i1 = FECHAS.get_loc(inicio), FECHAS.get_loc(fin)
    devengo_real = (np.prod(1 + _devengo_diario(tasa)[i0 + 1:i1 + 1]) - 1) * 100
    for ticker, fila in datos["etfs"].iterrows():
        assert fila["Resto (%)"] > 3.5, ticker
        diferencia_de_convencion = devengo_real - fila["Devengo aproximado (%)"]
        assert fila["No explicado (%)"] == pytest.approx(diferencia_de_convencion, abs=0.15), ticker
        assert abs(fila["No explicado (%)"]) < 0.5, ticker


@pytest.mark.parametrize("periodo,advierte", [("Último mes", False), ("Últimos 3 meses", False), ("Último año", True)])
def test_solo_en_ventanas_largas_se_advierte_que_la_aproximacion_es_menos_precisa(periodo, advierte):
    tasa = _paseo(16)
    datos = inf.calcular(_macro(tasa), _mundo_tesoro(tasa), inf.PERIODOS[periodo], periodo)
    texto = next(a for a in datos["afirmaciones"] if a.clave == "atribucion").texto
    assert ("la aproximación es menos precisa" in texto) is advierte


def test_la_nota_del_cuadro_2_con_solo_fondos_del_tesoro_no_nombra_el_credito_y_dice_que_es_una_aproximacion():
    tasa = _paseo(13)
    texto = _texto_pdf(inf.generar(_macro(tasa), _mundo_tesoro(tasa), "Último año"))
    nota = _nota_cuadro_2(texto)
    assert "crédito" not in nota and "spread" not in nota
    assert "Devengo aprox." in nota and "no el rendimiento ni el carry del fondo" in nota
    assert "No es una medida de riesgo" in nota
    assert not re.search(r"devengo exacto|carry exacto|carry estimado|carry real", texto, re.I)


# ---------------------------------------------------------------------------
# 3. Retorno positivo con tasas al alza: deja de leerse como «contrario» a lo anticipado
# ---------------------------------------------------------------------------
def _rampa(inicio, total, dias):
    r = np.full(N, inicio)
    r[N - dias:] = inicio + np.linspace(total / dias, total, dias)
    return r


def test_un_fondo_del_tesoro_que_rinde_positivo_con_tasas_al_alza_es_consistente_neto_del_devengo():
    """IEF (β 6,5) con tasa de 4% que sube 50 pb en el año: lo anticipado es ≈ −3,25 pp y el retorno ≈ +1 pp. Hasta I-2
    se leía como «contrario» (signos opuestos). Neto del devengo aproximado (≈ 4 pp) el retorno es ≈ −3 pp."""
    tasa = _rampa(4.0, 0.5, 250) + np.random.default_rng(14).normal(0, 0.01, N)
    datos = inf.calcular(_macro(tasa), _mundo_tesoro(tasa, {"IEF": 6.5}), 365, "Último año")
    ev = next(e for e in datos["evaluaciones"] if e["ETF"] == "IEF")
    inicio, fin = _ventana(datos)
    devengo = _tasa_en(tasa, inicio) * (fin - inicio).days / 365
    assert ev["retorno"] > 0 > ev["anticipado"]
    assert ev["retorno_comparado"] == pytest.approx(ev["retorno"] - devengo, abs=1e-12)
    assert ev["clase"] == "consistente", ev
    frase = inf._frase_de_evaluacion(ev)
    assert "devengo aproximado" in frase and "pese a que" not in frase


def test_la_limitacion_de_usar_la_tasa_del_inicio_queda_en_lo_no_explicado_y_tiene_el_signo_esperado():
    """LIMITACIÓN cuantificada: con la tasa subiendo 1 pp a lo largo del año, el devengo efectivo sigue a la tasa del
    camino (promedio ≈ inicio + 0,5 pp), pero la aproximación usa la del inicio: lo no explicado queda ≈ +0,5 pp."""
    tasa = _rampa(4.0, 1.0, 260) + np.random.default_rng(15).normal(0, 0.01, N)   # ruido: la regresión necesita variación
    datos = inf.calcular(_macro(tasa), _mundo_tesoro(tasa, {"SHY": 1.9}), 365, "Último año")
    inicio, fin = _ventana(datos)
    i0, i1 = FECHAS.get_loc(inicio), FECHAS.get_loc(fin)
    sesgo = (tasa[i0:i1].mean() - tasa[i0]) * (i1 - i0) / 252     # devengo extra del camino, aparte
    no_explicado = datos["etfs"].loc["SHY", "No explicado (%)"]
    assert no_explicado > 0.3 and no_explicado == pytest.approx(sesgo, abs=0.25)


# ---------------------------------------------------------------------------
# 2, 4, 11. Crédito: sin devengo estimado, spread no observado, y conclusiones que se abstienen
# ---------------------------------------------------------------------------
def _mundo_credito(semilla=21, ensanche_pb=0.0, baa=False):
    """LQD (D 7,3) y HYG (D 3,9): devengan tasa + spread y responden a −D × (Δy + Δs). El spread no está en los datos
    salvo que `baa` lo publique (y el Baa no representa al high yield: aquí es el mismo spread solo por construcción)."""
    tasa = _paseo(semilla)
    spread = 1.5 + np.concatenate([[0.0], np.random.default_rng(semilla + 1).normal(0, 0.01, N - 1)]).cumsum()
    if ensanche_pb:
        spread = spread + np.concatenate([np.zeros(N - 20), np.linspace(0, ensanche_pb / 100, 20)])
    precios = pd.DataFrame({
        t: _precio(_devengo_diario(tasa + spread) - d * (_cambios(tasa) + _cambios(spread)))
        for t, d in {"LQD": 7.3, "HYG": 3.9}.items()
    }, index=FECHAS)
    precios["IEF"] = _precio(_devengo_diario(tasa) - 6.5 * _cambios(tasa))
    extras = {rfui.NOMBRE_BAA10Y: spread} if baa else None
    return tasa, spread, _macro(tasa, extras), precios


def test_en_credito_no_se_estima_devengo_y_el_resto_queda_sin_separar():
    tasa, spread, macro, precios = _mundo_credito()
    datos = inf.calcular(macro, precios, 365, "Último año")
    etfs = datos["etfs"]
    for ticker in ("LQD", "HYG"):
        assert pd.isna(etfs.loc[ticker, "Devengo aproximado (%)"]) and pd.isna(etfs.loc[ticker, "No explicado (%)"])
        assert etfs.loc[ticker, "Resto (%)"] == pytest.approx(
            etfs.loc[ticker, "Retorno del período (%)"] - etfs.loc[ticker, "Explicado por la duración (%)"], abs=1e-12)
        ev = next(e for e in datos["evaluaciones"] if e["ETF"] == ticker)
        assert ev["devengo"] is None and ev["retorno_comparado"] == ev["retorno"]
    # El Tesoro del mismo mundo sí tiene su devengo aproximado.
    assert pd.notna(etfs.loc["IEF", "Devengo aproximado (%)"])
    nota = _nota_cuadro_2(_texto_pdf(inf.generar(macro, precios, "Último año")))
    assert "no se estima su devengo (n. e.: no estimado)" in nota and "sin separarlos" in nota
    tabla = inf._tabla_atribucion(etfs)
    assert set(tabla.loc[tabla["ETF"].isin(["LQD", "HYG"]), "Devengo aprox."]) == {inf.NO_ESTIMADO}


def test_con_el_spread_ensanchandose_un_retorno_negativo_con_tasas_a_la_baja_no_se_atribuye_a_una_causa():
    """HYG cae aunque la tasa del Tesoro baje, porque el spread se amplía 150 pb: el retorno negativo va contra lo
    anticipado por la sensibilidad a tasas. El informe no debe decir que el resto «corresponde» a crédito."""
    tasa, spread, macro, precios = _mundo_credito(semilla=22, ensanche_pb=150, baa=True)
    tasa_baja = tasa.copy()
    tasa_baja[N - 20:] -= np.linspace(0, 0.3, 20)          # la tasa del Tesoro baja 30 pb en el último mes
    precios["HYG"] = _precio(_devengo_diario(tasa_baja + spread) - 3.9 * (_cambios(tasa_baja) + _cambios(spread)))
    macro = _macro(tasa_baja, {rfui.NOMBRE_BAA10Y: spread})
    datos = inf.calcular(macro, precios, 30, "Último mes")
    ev = next(e for e in datos["evaluaciones"] if e["ETF"] == "HYG")
    assert ev["retorno"] < 0 and ev["devengo"] is None
    textos = [a.texto for a in datos["afirmaciones"]] + [inf._frase_de_evaluacion(e) for e in datos["evaluaciones"]]
    for texto in textos:
        assert not re.search(r"(resto|diferencia)[^.]*(corresponde|se debe|es atribuible|se explica por)", texto, re.I), texto
    assert ev["clase"] in ("credito", "contraria", "magnitud", "imprecisa", "efecto_pequeno", "precio_quieto"), ev


def test_la_mayor_diferencia_se_informa_sin_asignarla_a_un_factor():
    tasa, spread, macro, precios = _mundo_credito(semilla=23, ensanche_pb=80)
    datos = inf.calcular(macro, precios, 30, "Último mes")
    texto = next(a for a in datos["afirmaciones"] if a.clave == "atribucion").texto
    residuo = inf._residuo_comparado(datos["etfs"])
    mayor = residuo.abs().idxmax()
    assert f"se registró en {mayor}" in texto                      # en este escenario la diferencia es material
    assert "no es posible asignarla a un factor específico" in texto


# ---------------------------------------------------------------------------
# 6, 7. Datos faltantes: sin tasa al inicio, o sin sensibilidad
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tasa_inicio,dias", [(None, 90), (float("nan"), 90), (4.0, None), (4.0, 0)])
def test_sin_tasa_al_inicio_o_sin_dias_no_hay_devengo(tasa_inicio, dias):
    assert inf.devengo_aproximado(tasa_inicio, dias) is None


def test_si_falta_la_tasa_en_la_fecha_de_inicio_la_ventana_se_corre_y_el_devengo_usa_la_tasa_del_nuevo_inicio():
    """Por la ventana común de I-1, la atribución exige la curva completa en las dos fechas: si falta la tasa de 2 años en
    el inicio, la ventana se corre a una fecha con curva completa, y el devengo usa la tasa de ESA fecha (nunca rellena)."""
    tasa = _paseo(31)
    precios = _mundo_tesoro(tasa, {"SHY": 1.9, "IEF": 6.5})
    inicio_original, _ = _ventana(inf.calcular(_macro(tasa), precios, 90, "Últimos 3 meses"))
    quitar = {(rfui.nombre_treasury(e), inicio_original) for e, plazo in et.PLAZOS_ANIOS.items() if plazo == 2.0}
    datos = inf.calcular(_macro(tasa, quitar=quitar), precios, 90, "Últimos 3 meses")
    inicio, fin = _ventana(datos)
    assert inicio != inicio_original
    for ticker in ("SHY", "IEF"):
        esperado = _tasa_en(tasa, inicio) * (fin - inicio).days / 365
        assert datos["etfs"].loc[ticker, "Devengo aproximado (%)"] == pytest.approx(esperado, abs=1e-12), ticker


def test_sin_sensibilidad_estimada_no_hay_devengo_ni_no_explicado():
    tasa = _paseo(32)
    precios = _mundo_tesoro(tasa, {"SHY": 1.9})
    # 26 precios: alcanza para el retorno del último mes (~21 ruedas), no para estimar la sensibilidad (mínimo 30).
    precios.loc[precios.index[:-26], "SHY"] = np.nan
    datos = inf.calcular(_macro(tasa), precios, 30, "Último mes")
    fila = datos["etfs"].loc["SHY"]
    assert pd.notna(fila["Retorno del período (%)"])
    assert pd.isna(fila["Explicado por la duración (%)"])
    assert pd.isna(fila["Devengo aproximado (%)"]) and pd.isna(fila["No explicado (%)"])


# ---------------------------------------------------------------------------
# 8. TIP
# ---------------------------------------------------------------------------
def test_tip_no_recibe_devengo_nominal_y_su_fila_no_se_interpreta():
    tasa = _paseo(41)
    precios = _mundo_tesoro(tasa, {"IEF": 6.5})
    precios["TIP"] = _precio(_devengo_diario(tasa - 2.3) - 4.5 * _cambios(tasa) * 0.5)
    datos = inf.calcular(_macro(tasa), precios, 90, "Últimos 3 meses")
    assert pd.isna(datos["etfs"].loc["TIP", "Devengo aproximado (%)"])
    ev = next(e for e in datos["evaluaciones"] if e["ETF"] == "TIP")
    assert ev["clase"] == "sin_tasa_real" and ev["devengo"] is None   # clase renombrada en I-4a
    nota = _nota_cuadro_2(_texto_pdf(inf.generar(_macro(tasa), precios, "Últimos 3 meses")))
    assert "En TIP solo se informa el retorno" in nota and "n. e.: no estimado" in nota   # texto de I-4a


# ---------------------------------------------------------------------------
# 12. Compatibilidad con I-1 (ventana y fecha de corte), I-2 (comparación entre fondos) y D-1 (precios ajustados)
# ---------------------------------------------------------------------------
def test_el_devengo_usa_las_mismas_dos_fechas_que_el_retorno_y_se_reproduce_con_una_fecha_de_corte():
    tasa = _paseo(51)
    precios = _mundo_tesoro(tasa)
    corte = FECHAS[-40]
    completo = inf.calcular(_macro(tasa), precios, 90, "Últimos 3 meses", fecha_corte=corte)
    recortado = inf.calcular(_macro(tasa)[lambda m: m["fecha"] <= corte], precios.loc[:corte], 90, "Últimos 3 meses")
    columnas = ["Retorno del período (%)", "Devengo aproximado (%)", "No explicado (%)"]
    pd.testing.assert_frame_equal(completo["etfs"][columnas], recortado["etfs"][columnas])
    inicio, fin = _ventana(completo)
    assert completo["contexto"]["dias"] == (fin - inicio).days


def test_reescalar_toda_la_serie_ajustada_no_cambia_nada_de_la_atribucion():
    """D-1: con una sola base de ajuste, Yahoo puede reescalar toda la historia por una distribución sin cambiar ningún
    retorno. El devengo aproximado sale de la tasa, no del precio: no se suma a las distribuciones (sin doble conteo)."""
    tasa = _paseo(52)
    precios = _mundo_tesoro(tasa)
    a = inf.calcular(_macro(tasa), precios, 365, "Último año")["etfs"]
    b = inf.calcular(_macro(tasa), precios * 0.9963, 365, "Último año")["etfs"]
    columnas = ["Retorno del período (%)", "Explicado por la duración (%)", "Resto (%)", "Devengo aproximado (%)", "No explicado (%)"]
    pd.testing.assert_frame_equal(a[columnas], b[columnas], atol=1e-9)


def test_la_brecha_entre_dos_fondos_del_tesoro_incluye_la_diferencia_de_sus_devengos():
    """SHY y TLT con tasas de referencia distintas (2 y 20 años): la brecha anticipada es (X_TLT + c_TLT) − (X_SHY + c_SHY).
    Se construye una curva con pendiente para que los devengos difieran."""
    base = _paseo(53, desvio=0.01)
    pendiente = {p: 0.08 * p for p in et.PLAZOS_ANIOS.values()}
    filas = []
    for etiqueta, plazo in et.PLAZOS_ANIOS.items():
        filas += [{"nombre": rfui.nombre_treasury(etiqueta), "fecha": f, "valor": float(v + pendiente[plazo])}
                  for f, v in zip(FECHAS, base)]
    macro = pd.DataFrame(filas)
    precios = pd.DataFrame({
        "SHY": _precio(_devengo_diario(base + pendiente[2.0]) - 1.9 * _cambios(base)),
        "TLT": _precio(_devengo_diario(base + pendiente[20.0]) - 16.0 * _cambios(base)),
    }, index=FECHAS)
    datos = inf.calcular(macro, precios, 365, "Último año")
    etfs = datos["etfs"]
    c_shy, c_tlt = etfs.loc["SHY", "Devengo aproximado (%)"], etfs.loc["TLT", "Devengo aproximado (%)"]
    assert c_tlt - c_shy == pytest.approx(0.08 * 18 * (_ventana(datos)[1] - _ventana(datos)[0]).days / 365, abs=1e-9)
    comparacion = next(a for a in datos["afirmaciones"] if a.clave == "comparacion")
    anticipada = dict((c[0], c[2]) for c in comparacion.condiciones)["brecha anticipada consistente (pp)"]
    mejor = etfs["Retorno del período (%)"].idxmax()
    peor = etfs["Retorno del período (%)"].idxmin()
    esperado = (etfs.loc[mejor, "Explicado por la duración (%)"] + etfs.loc[mejor, "Devengo aproximado (%)"]
                - etfs.loc[peor, "Explicado por la duración (%)"] - etfs.loc[peor, "Devengo aproximado (%)"])
    assert anticipada == pytest.approx(esperado, abs=1e-3)
