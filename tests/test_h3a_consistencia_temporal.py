"""H3-A: consistencia de fuentes, fechas y cifras (offline, datos sintéticos).

QUÉ SE PRUEBA
    H3-01  El spread 2s10s del Resumen y del Brief PDF sale de la curva H.15 (10 y 2 años en la MISMA fecha), no del
           ^TNX de Yahoo ni del proxy de futuros 2YY=F; si no hay fecha común, se dice que no está disponible. La Defensa
           Top-Down sigue con su cálculo anterior (cambiarlo altera su calculadora de costo de capital: fuera de alcance).
    H3-06  En la tabla de carry, la tasa local y la de EEUU mostradas son exactamente las del diferencial mostrado, con
           su fecha de referencia; el tooltip es aritméticamente coherente considerando el redondeo.
    H3-07  El diferencial TPM − fondos federales usa las dos tasas vigentes en una misma fecha de referencia, igual en la
           pantalla y en el PDF; sin datos posteriores a esa fecha ni arrastres indefinidos.
    H3-08  En el PDF, el spread Baa se mide en las mismas fechas que la ventana de los ETFs (con una tolerancia explícita
           de una rueda); si no hay datos comparables, se dice y no se compara.
    H3-11  La tarjeta «Tesoro de EEUU a 10 años» de Renta Fija usa el DGS10 del H.15, la serie de la curva.

Las pruebas son sintéticas: verifican la lógica, no validan datos reales de producción.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import pickle
import re
import sys
import textwrap

import numpy as np
import pandas as pd
import pymupdf
import pytest
from streamlit.testing.v1 import AppTest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(RAIZ)

import fx_carry as fx  # noqa: E402
import fx_carry_ui as fxui  # noqa: E402
import glosario_fx as gl  # noqa: E402
import informe_renta_fija as inf  # noqa: E402
import renta_fija_ui as rfui  # noqa: E402
import test_diferencial_bcp_bcu_dashboard as tdash  # noqa: E402
import test_informe_renta_fija as tinf  # noqa: E402
from catalogo_fx import MONEDAS_CARRY, NOMBRE_TASA_CHILE, NOMBRE_TASA_EEUU  # noqa: E402

FIN = pd.Timestamp("2026-11-18")   # miércoles
DIEZ, DOS = rfui.nombre_treasury("10 años"), rfui.nombre_treasury("2 años")
UST10_YAHOO = "Bono del Tesoro de EEUU a 10 años (UST10Y)"
UST2_PROXY = "Bono del Tesoro de EEUU a 2 años (UST2Y, proxy 2YY=F)"


def _s(fechas, valores) -> pd.Series:
    return pd.Series(np.asarray(valores, dtype=float), index=pd.DatetimeIndex(fechas))


def _filas(nombre, serie: pd.Series) -> list[dict]:
    return [{"nombre": nombre, "fecha": f, "valor": v} for f, v in serie.items()]


# ---------------------------------------------------------------------------
# H3-07: fx_carry.diferencial_vigente
# ---------------------------------------------------------------------------
def test_el_diferencial_se_fecha_en_la_mas_antigua_de_las_dos_ultimas_observaciones():
    habiles = pd.bdate_range(end=FIN, periods=30)
    tpm = _s(habiles, [4.75] * 29 + [4.50])                       # baja el último día (18-11)
    dff = _s(pd.date_range(habiles[0], FIN - pd.Timedelta(days=1)), 3.88)   # 7 días, hasta el 17-11
    d = fx.diferencial_vigente(tpm, dff)
    assert d["fecha_referencia"] == pd.Timestamp("2026-11-17")
    assert (d["tasa_a"], d["fecha_a"]) == (4.75, pd.Timestamp("2026-11-17"))   # no la TPM del 18-11, posterior
    assert (d["tasa_b"], d["fecha_b"]) == (3.88, pd.Timestamp("2026-11-17"))
    assert d["diferencial"] == pytest.approx(0.87) and d["vigente"]


def test_el_diferencial_no_usa_datos_posteriores_a_la_fecha_de_referencia():
    habiles = pd.bdate_range(end=FIN, periods=30)
    dff = _s(habiles[:-2], 3.88)                                   # termina el 16-11
    tpm = _s(habiles, np.linspace(4.0, 5.0, 30))
    base = fx.diferencial_vigente(tpm, dff)
    alterada = tpm.copy()
    alterada[alterada.index > base["fecha_referencia"]] = 99.0     # lo posterior a la referencia no debe pesar
    assert fx.diferencial_vigente(alterada, dff) == base


def test_ignora_valores_vacios_y_con_fechas_repetidas_vale_la_ultima_fila():
    habiles = pd.bdate_range(end=FIN, periods=10)
    tpm = _s(habiles, 4.0)
    tpm.iloc[-1] = np.nan                                          # el último dato viene vacío
    dff = pd.concat([_s(habiles, 3.0), _s([habiles[-2]], [3.5])])  # fecha repetida: vale la última fila
    d = fx.diferencial_vigente(tpm, dff)
    assert d["fecha_referencia"] == habiles[-2]
    assert d["tasa_b"] == 3.5 and d["diferencial"] == pytest.approx(0.5)


def test_sin_fecha_en_comun_no_hay_diferencial():
    a = _s(pd.bdate_range("2026-01-01", periods=5), 4.0)
    b = _s(pd.bdate_range("2026-03-01", periods=5), 3.0)           # empieza cuando la otra ya terminó
    assert fx.diferencial_vigente(a, b) is None
    assert fx.diferencial_vigente(a, pd.Series(dtype=float)) is None


@pytest.mark.parametrize("dias, vigente", [(10, True), (11, False), (30, False)])
def test_una_tasa_atrasada_no_se_arrastra_indefinidamente(dias, vigente):
    habiles = pd.date_range(end=FIN, periods=60)
    tpm = _s(habiles, 4.5)
    dff = _s(habiles[habiles <= FIN - pd.Timedelta(days=dias)], 3.88)
    d = fx.diferencial_vigente(tpm, dff)
    assert d["vigente"] is vigente
    assert d["fecha_referencia"] == FIN - pd.Timedelta(days=dias)


@pytest.mark.parametrize("tpm, fed, esperado", [(4.0, 4.0, 0.0), (3.0, 4.33, -1.33)])
def test_tasas_iguales_y_diferencial_negativo(tpm, fed, esperado):
    fechas = pd.bdate_range(end=FIN, periods=5)
    d = fx.diferencial_vigente(_s(fechas, tpm), _s(fechas, fed))
    assert d["diferencial"] == pytest.approx(esperado)


# ---------------------------------------------------------------------------
# H3-01: rfui.pendiente_2s10s
# ---------------------------------------------------------------------------
def _macro_curva(diez: pd.Series, dos: pd.Series, extra: bool = True) -> pd.DataFrame:
    filas = _filas(DIEZ, diez) + _filas(DOS, dos)
    if extra:   # Yahoo y el proxy de futuros, con otros valores y hasta otra fecha: no deben influir
        ultimo = pd.bdate_range(end=FIN + pd.Timedelta(days=1), periods=5)
        filas += _filas(UST10_YAHOO, _s(ultimo, 9.0)) + _filas(UST2_PROXY, _s(ultimo, 1.0))
    return pd.DataFrame(filas)


def test_el_2s10s_usa_la_ultima_fecha_comun_del_h15_y_no_yahoo():
    fechas = pd.bdate_range(end=FIN, periods=10)
    p = rfui.pendiente_2s10s(_macro_curva(_s(fechas, np.linspace(4.0, 4.4, 10)), _s(fechas[:-2], 3.5)))
    assert p["fecha"] == fechas[-3]
    assert p["ust10"] == pytest.approx(np.linspace(4.0, 4.4, 10)[-3]) and p["ust2"] == 3.5


def test_el_2s10s_con_valores_vacios_y_fechas_repetidas():
    fechas = pd.bdate_range(end=FIN, periods=10)
    diez = _s(fechas, 4.0)
    diez.iloc[-1] = np.nan
    dos = pd.concat([_s(fechas, 3.0), _s([fechas[-2]], [3.2])])
    p = rfui.pendiente_2s10s(_macro_curva(diez, dos))
    assert p["fecha"] == fechas[-2] and p["ust2"] == 3.2 and p["spread"] == pytest.approx(0.8)


def test_sin_fecha_comun_el_2s10s_no_esta_disponible():
    habiles = pd.bdate_range(end=FIN, periods=10)
    fines = pd.date_range(end=FIN, periods=20)
    fines = fines[fines.dayofweek >= 5]
    assert rfui.pendiente_2s10s(_macro_curva(_s(habiles, 4.0), _s(fines, 3.0))) is None
    assert rfui.pendiente_2s10s(_macro_curva(_s(habiles, 4.0), pd.Series(dtype=float))) is None


@pytest.mark.parametrize("dos, invertida", [(4.004, True), (4.006, True), (4.0, False), (3.996, False), (3.0, False), (5.0, True)])
def test_la_curva_invertida_sigue_al_signo_sin_redondear(dos, invertida):
    fechas = pd.bdate_range(end=FIN, periods=3)
    assert rfui.pendiente_2s10s(_macro_curva(_s(fechas, 4.0), _s(fechas, dos)))["invertida"] is invertida


@pytest.mark.parametrize("spread, esperado", [
    (-0.004, "0.00 pp (slightly negative: the 10-year yield is just below the 2-year)"),
    (0.004, "0.00 pp (slightly positive: the 10-year yield is just above the 2-year)"),
    (0.0, "0.00 pp"), (-0.006, "-0.01 pp"), (1.85, "+1.85 pp"),
])
def test_un_spread_que_se_lee_cero_aclara_su_signo(spread, esperado):
    assert tdash._definiciones_del_dashboard()["_texto_cifra_2s10s"](spread) == esperado


# ---------------------------------------------------------------------------
# H3-06: tasas de la tabla de carry
# ---------------------------------------------------------------------------
def _carry_sintetico(mensual: bool, seed: int = 5):
    rng = np.random.default_rng(seed)
    fechas = pd.bdate_range(end=FIN, periods=400)
    valor = pd.Series(np.exp(rng.normal(0, 0.006, len(fechas)).cumsum()), index=fechas)
    if mensual:
        f_m = pd.date_range(fechas[0], FIN, freq="MS")
        tasa_m = _s(f_m, rng.uniform(0.1, 11.0, len(f_m)).round(4))
    else:
        tasa_m = _s(fechas[:-1], rng.uniform(0.1, 11.0, len(fechas) - 1).round(4))
    tasa_u = _s(pd.date_range(fechas[0], FIN - pd.Timedelta(days=1)), 3.88)
    return valor, tasa_m, tasa_u


@pytest.mark.parametrize("mensual", [False, True])
def test_las_tasas_mostradas_son_las_del_diferencial_del_motor(mensual):
    valor, tasa_m, tasa_u = _carry_sintetico(mensual)
    edad_m = fxui.ANTIGUEDAD_MAXIMA_DE_TASA["mensual" if mensual else "diaria"]
    edad_u = fxui.ANTIGUEDAD_MAXIMA_DE_TASA["diaria"]
    r = fx.retornos_del_carry(valor, tasa_m, tasa_u, edad_m, edad_u)
    resumen = fx.resumen_del_carry(r)
    t = fx.tasas_del_ultimo_tramo(valor, r, tasa_m, tasa_u, edad_m, edad_u)
    assert t["diferencial"] == resumen["diferencial_actual"]        # idéntico, no aproximado
    assert t["fecha_referencia"] == valor.index[-2] and t["hasta"] == resumen["hasta"]
    # cálculo aparte: la última observación en o antes de la fecha de referencia
    assert t["tasa_moneda"] == pytest.approx(float(tasa_m[tasa_m.index <= t["fecha_referencia"]].iloc[-1]))
    assert t["fecha_tasa_moneda"] == tasa_m[tasa_m.index <= t["fecha_referencia"]].index[-1]
    assert t["tasa_usd"] == pytest.approx(3.88) and t["fecha_tasa_usd"] <= t["fecha_referencia"]
    assert t["tasa_moneda"] - t["tasa_usd"] == pytest.approx(t["diferencial"], abs=1e-12)


def test_la_tabla_de_carry_muestra_las_tasas_usadas_y_no_las_ultimas_de_cada_serie():
    fechas = pd.bdate_range(end=FIN, periods=400)
    rng = np.random.default_rng(2)
    filas = []
    for codigo, datos in MONEDAS_CARRY.items():
        if datos["serie_tasa"] == NOMBRE_TASA_CHILE:
            continue
        f = pd.date_range(fechas[0], FIN, freq="MS") if datos["frecuencia"] == "mensual" else fechas
        filas += _filas(datos["serie_tasa"], _s(f, rng.uniform(0.5, 10, len(f)).round(3)))
    tpm = _s(fechas, 4.75)
    tpm.iloc[-1] = 4.50                                             # la TPM del último día no es la del diferencial
    filas += _filas(NOMBRE_TASA_CHILE, tpm)
    filas += _filas(NOMBRE_TASA_EEUU, _s(pd.date_range(fechas[0], FIN - pd.Timedelta(days=1)), 3.88))
    macro = pd.DataFrame(filas)
    precios = pd.DataFrame({d["par"]: 100 * np.exp(rng.normal(0, 0.005, len(fechas)).cumsum()) for d in MONEDAS_CARRY.values()},
                           index=fechas)
    tabla = fxui._resumen_del_carry(macro, precios, FIN)
    clp = tabla.loc["CLP"]
    assert clp["Tasa local (%)"] == pytest.approx(4.75) and clp["fecha_referencia"] == fechas[-2]
    for _codigo, fila in tabla.iterrows():
        assert fila["Tasa local (%)"] - fila["tasa_usd"] == pytest.approx(fila["Diferencial (pp)"], abs=1e-9)
    html = fxui._tabla_de_carry_html(tabla, macro)
    assert "4.75% para el peso chileno" in html and "4.50%" not in html
    assert f"vigentes al {rfui._fecha(fechas[-2])}" in html


def test_el_tooltip_del_diferencial_es_coherente_con_el_redondeo():
    rng = np.random.default_rng(9)
    for _ in range(3000):
        m, u = rng.uniform(-1, 15, 2).round(rng.integers(2, 6))
        d = m - u
        texto = gl.explicacion_diferencial("el yen", float(m), float(u), float(d))
        mostrado_m, mostrado_u = (float(x) for x in re.findall(r"(-?\d+\.\d{2})% para", texto + "% para")[:1] +
                                  re.findall(r"y (-?\d+\.\d{2})% para el dólar", texto))
        cabecera = float(re.search(r"= ([+-]?\d+\.\d{2}) pp", texto).group(1))
        resta = round(mostrado_m - mostrado_u, 2)
        assert abs(resta - cabecera) <= 0.0100001
        assert ("difiere en 0.01 por redondeo" in texto) == (abs(resta - cabecera) > 1e-9)


def test_el_tooltip_solo_aclara_la_fecha_de_una_tasa_si_es_de_otro_dia():
    texto = gl.explicacion_diferencial("el yen", 0.75, 3.88, -3.13, "17-11-2026", "01-11-2026", "17-11-2026")
    assert "vigentes al 17-11-2026" in texto and "0.75% para el yen (dato del 01-11-2026)" in texto
    assert "3.88% para el dólar;" in texto
    assert "Diferencial de tasas = 0.00 pp" in gl.explicacion_diferencial("el yen", 4.0, 4.0, 0.0)


# ---------------------------------------------------------------------------
# H3-07 y H3-11 en la pantalla de Renta Fija, y la misma cifra en el PDF
# ---------------------------------------------------------------------------
def _macro_tasas(dff_hasta=FIN - pd.Timedelta(days=1)) -> pd.DataFrame:
    habiles = pd.bdate_range(end=FIN, periods=40)
    tpm = _s(habiles, 4.75)
    tpm.iloc[-1] = 4.50
    filas = _filas(rfui.NOMBRE_TPM_CHILE, tpm)
    filas += _filas(rfui.NOMBRE_TPM_EEUU, _s(pd.date_range(habiles[0], dff_hasta), 3.88))
    filas += _filas(DIEZ, _s(habiles[:-1], 4.10)) + _filas(UST10_YAHOO, _s(habiles, 4.17))
    filas += _filas(rfui.NOMBRE_BCP10, _s(habiles, 5.5)) + _filas(rfui.NOMBRE_BCU10, _s(habiles, 2.4))
    return pd.DataFrame(filas)


def _app_banco_central(macro):
    import renta_fija_ui
    renta_fija_ui._paso_banco_central(macro)


def _app_mercado(macro):
    import pandas
    import renta_fija_ui
    renta_fija_ui._paso_mercado(macro, pandas.DataFrame())


def test_la_pantalla_y_el_pdf_muestran_el_mismo_diferencial_tpm_fed_con_su_fecha():
    macro = _macro_tasas()
    at = AppTest.from_function(_app_banco_central, args=(macro,), default_timeout=60)
    at.run()
    assert not at.exception
    metrica = next(m for m in at.metric if m.label.startswith("Diferencial TPM"))
    assert metrica.value == "0.87 pp"                               # 4.75 − 3.88 al 17-11, no 4.50 − 3.88
    assert any(c.value.startswith("Al 17-11-2026: TPM 4.75% − tasa efectiva de fondos federales 3.88%") for c in at.caption)
    chile = inf._chile(macro)
    assert chile["diferencial"] == pytest.approx(0.87) and chile["fecha_diferencial"] == pd.Timestamp("2026-11-17")
    assert (chile["tpm"], chile["fed"]) == (4.75, 3.88)


def test_si_la_fed_quedo_atrasada_ni_la_pantalla_ni_el_pdf_calculan_el_diferencial():
    macro = _macro_tasas(dff_hasta=FIN - pd.Timedelta(days=31))
    at = AppTest.from_function(_app_banco_central, args=(macro,), default_timeout=60)
    at.run()
    metrica = next(m for m in at.metric if m.label.startswith("Diferencial TPM"))
    assert metrica.value == "—"
    assert any("No hay una fecha reciente con las dos tasas" in c.value for c in at.caption)
    assert inf._chile(macro)["diferencial"] is None


def test_la_tarjeta_del_tesoro_a_10_anios_usa_el_h15():
    at = AppTest.from_function(_app_mercado, args=(_macro_tasas(),), default_timeout=60)
    at.run()
    assert not at.exception
    metrica = next(m for m in at.metric if m.label == "Tesoro de EEUU a 10 años")
    assert metrica.value == "4.10%"                                 # DGS10, no el 4.17% de Yahoo
    assert "Al 17-11-2026 · Reserva Federal (H.15, vía FRED)" in [c.value for c in at.caption]


# ---------------------------------------------------------------------------
# H3-08: el spread Baa en la ventana de los ETFs (PDF)
# ---------------------------------------------------------------------------
def _caso_credito(recorte_baa: int | None):
    macro, precios = tinf._caso(4.0, 5.0)
    if recorte_baa is not None:
        baa = macro["nombre"] == rfui.NOMBRE_BAA10Y
        fechas_baa = sorted(macro.loc[baa, "fecha"].unique())
        macro = macro[~baa | (macro["fecha"] <= fechas_baa[recorte_baa])]
    macro = macro.copy()
    m = macro["nombre"] == rfui.NOMBRE_BAA10Y
    macro.loc[m, "valor"] = np.linspace(1.5, 2.1, int(m.sum()))
    return macro, precios


@pytest.mark.parametrize("periodo", list(inf.PERIODOS))
def test_el_spread_baa_se_mide_en_las_fechas_de_la_ventana_de_los_etfs(periodo):
    macro, precios = _caso_credito(None)
    d = inf.calcular(macro, precios, inf.PERIODOS[periodo], periodo)
    c = d["credito"]
    assert (c["fecha_inicio"], c["fecha_fin"]) == (d["fechas"]["inicio"], d["fechas"]["fin"])
    assert not c["ventana_propia"] and d["credito_motivo"] is None
    assert c["fecha_inicio"] <= c["fecha_maximo"] <= c["fecha_fin"]


def test_un_baa_una_rueda_atrasado_se_acepta_con_sus_fechas_efectivas():
    macro, precios = _caso_credito(-2)                              # sin el último dato
    d = inf.calcular(macro, precios, 30, "Último mes")
    c, fin = d["credito"], d["fechas"]["fin"]
    assert c is not None and c["fecha_fin"] < fin and c["fin_etf"] == fin
    texto = " ".join(p.get_text() for p in pymupdf.open(stream=inf.generar(macro, precios, "Último mes"), filetype="pdf"))
    assert "a lo más 1 rueda antes" in " ".join(texto.split())


def test_un_baa_muy_atrasado_no_se_compara_y_el_pdf_lo_dice():
    macro, precios = _caso_credito(-10)
    d = inf.calcular(macro, precios, 30, "Último mes")
    assert d["credito"] is None and "no tiene datos comparables" in d["credito_motivo"]
    credito = next(a for a in d["afirmaciones"] if a.clave == "credito")
    assert credito.nivel == inf.NIVEL_INSUFICIENTE and "no tiene datos comparables" in credito.texto
    texto = " ".join(" ".join(p.get_text() for p in pymupdf.open(stream=inf.generar(macro, precios, "Último mes"),
                                                                 filetype="pdf")).split())
    assert "No se describe el spread de bonos corporativos Baa" in texto


# ---------------------------------------------------------------------------
# H3-01 en el Resumen y el Brief PDF del dashboard (definiciones del dashboard con datos sintéticos)
# ---------------------------------------------------------------------------
def _bloque_2s10s() -> str:
    lineas = tdash.FUENTE.splitlines(keepends=True)
    i = next(k for k, linea in enumerate(lineas) if 'st.caption("not enough data")' in linea) + 1
    j = next(k for k in range(i, len(lineas)) if "given false signals in the past" in lineas[k])
    while lineas[j].strip() != ")":
        j += 1
    return textwrap.dedent("".join(lineas[i:j + 1]))


def _macro_dashboard(dos_desde_fines: bool = False) -> pd.DataFrame:
    base = tdash._macro()
    fechas = pd.bdate_range(end=FIN, periods=40)
    dos = _s(fechas[:-2], 3.6)
    if dos_desde_fines:
        fines = pd.date_range(end=FIN, periods=60)
        dos = _s(fines[fines.dayofweek >= 5], 3.6)
    extra = _filas(DIEZ, _s(fechas[:-1], np.linspace(4.0, 4.3, 39))) + _filas(DOS, dos)
    extra += _filas(UST10_YAHOO, _s(fechas, 9.0)) + _filas(UST2_PROXY, _s(fechas, 1.0))
    df = pd.concat([base[~base["nombre"].isin([UST10_YAHOO, UST2_PROXY])], pd.DataFrame(extra)], ignore_index=True)
    return df.assign(fecha=pd.to_datetime(df["fecha"]).dt.date)


@pytest.mark.parametrize("sin_comun", [False, True])
def test_el_resumen_y_el_brief_usan_el_2s10s_del_h15(tmp_path, sin_comun):
    df = _macro_dashboard(dos_desde_fines=sin_comun)
    at = tdash._correr(tmp_path, df, [_bloque_2s10s()])
    ns = tdash._definiciones_del_dashboard({"cargar_series_macro": lambda: df, "cargar_precios_acciones": tdash._acciones,
                                             "cargar_brief_diario": lambda: pd.DataFrame()})
    with pymupdf.open(stream=ns["generar_pdf_brief_premercado"](), filetype="pdf") as doc:
        brief = " ".join(" ".join(p.get_text() for p in doc).split())
    if sin_comun:
        assert [x.value for x in at.info] == [ns["TEXTO_2S10S_NO_DISPONIBLE"]] and not at.success and not at.error
        assert ns["TEXTO_2S10S_NO_DISPONIBLE"] in brief
    else:
        diez = np.linspace(4.0, 4.3, 39)[-2]                         # la última fecha común es la del 2 años (16-11)
        esperado = f"{diez - 3.6:+.2f}"
        texto = (at.success or at.error)[0].value
        assert f"2s10s spread (10-year − 2-year Treasury, H.15): {esperado} pp" in texto and "as of 2026-11-16" in texto
        assert f"(10Y {diez:.2f}% − 2Y 3.60%)" in texto and "9.00" not in texto
        assert f"2s10s spread (10-year − 2-year Treasury, H.15): {esperado} pp as of 2026-11-16" in brief
    assert any("Yahoo Finance (^TNX" in c.value for c in at.caption)


def test_la_defensa_top_down_conserva_su_calculo_anterior():
    """Fuera de alcance de H3-A: su calculadora de costo de capital precarga el «ust10» de calcular_spread_2s10s."""
    ns = tdash._definiciones_del_dashboard()
    df = _macro_dashboard()
    anterior = ns["calcular_spread_2s10s"](df)
    assert anterior["ust10"] == 9.0 and anterior["ust2"] == 1.0      # sigue leyendo ^TNX y el proxy 2YY=F
    fuente = tdash.FUENTE
    inicio = fuente.index("def _defensa_topdown_datos_reales")
    assert "calcular_spread_2s10s(df_macro)" in fuente[inicio:fuente.index("\ndef ", inicio + 10)]


# ---------------------------------------------------------------------------
# Cierre H3-A: antigüedad absoluta del diferencial TPM − Fed (distinta del desfase entre las dos observaciones)
# ---------------------------------------------------------------------------
def test_un_diferencial_completo_pero_viejo_se_presenta_como_historico():
    fechas = pd.bdate_range(end="2026-06-30", periods=30)              # las dos terminan el mismo día, hace meses
    dif = fx.diferencial_vigente(_s(fechas, 5.0), _s(fechas, 4.33))
    assert dif["vigente"]                                              # el desfase entre ellas es cero
    texto = rfui.texto_diferencial_tpm_fed(dif, FIN)
    assert "Dato atrasado:" in texto and "diferencial histórico, no el de hoy" in texto
    assert "Dato atrasado" not in rfui.texto_diferencial_tpm_fed(dif, pd.Timestamp("2026-07-03"))   # 3 días hábiles


def test_el_pdf_avisa_si_el_diferencial_quedo_atras_respecto_de_la_fecha_de_corte():
    fechas = pd.bdate_range(end="2026-06-30", periods=30)
    macro = pd.DataFrame(_filas(rfui.NOMBRE_TPM_CHILE, _s(fechas, 5.0)) + _filas(rfui.NOMBRE_TPM_EEUU, _s(fechas, 4.33)))
    chile = inf._chile(macro, FIN)
    assert chile["diferencial"] == pytest.approx(0.67)
    assert "Dato atrasado" in rfui.texto_atraso_diferencial(chile["diferencial_tpm_fed"], chile["corte"])
    assert rfui.texto_atraso_diferencial(chile["diferencial_tpm_fed"], pd.Timestamp("2026-07-01")) == ""
