"""Etapa 1, intervención I-1: ventana común, fecha de corte y ETFs atrasados en el informe de renta fija.

QUÉ SE COMPRUEBA
    Que cada ETF que se compara mida su retorno y el cambio de su tasa de referencia entre las MISMAS dos fechas (S y
    E), que un ETF atrasado se excluya y se informe en vez de arrastrar la ventana de los demás, que nada posterior a la
    fecha de corte entre al cálculo y que lo que no se puede calcular quede dicho, sin rellenar datos.

CÓMO
    Offline y con datos sintéticos sobre el calendario real de 2026 (feriados de la bolsa y del mercado de bonos
    incluidos). Los precios responden EXACTAMENTE a −duración × cambio de tasa, así que en una ventana alineada el resto
    es ≈ 0 por construcción. Los valores esperados (fechas, retornos, cambios de tasa) se leen de los arreglos que se
    construyeron, no del informe.

POR QUÉ ES UN ARCHIVO APARTE
    tests/conftest.py omitiría sin base de pruebas cualquier prueba nueva dentro de test_informe_renta_fija.py.
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
import renta_fija as rf  # noqa: E402
import renta_fija_ui as rfui  # noqa: E402

MES = "Último mes"
DIAS = inf.PERIODOS[MES]
D = pd.Timestamp
FERIADO_BOLSA = D("2026-09-07")       # Labor Day: cierran la bolsa y el mercado de bonos
FERIADOS_BONOS = [D("2026-10-12"), D("2026-11-11")]  # Columbus y Veterans Day: la bolsa abre, H.15 no publica
FECHAS = pd.bdate_range("2025-06-02", "2026-11-16").drop(FERIADO_BOLSA)  # termina el lunes 16-11-2026
DURACIONES = {"SHY": 1.9, "IEF": 6.5, "TLT": 16.0}


# ---------------------------------------------------------------------------
# Constructores
# ---------------------------------------------------------------------------
def _requisito(condicion: bool, mensaje: str) -> None:
    if not condicion:
        pytest.fail(f"Escenario mal construido: {mensaje}")


def _tasa(semilla: int = 1) -> pd.Series:
    rng = np.random.default_rng(semilla)
    valores = 4.0 + np.concatenate([[0.0], rng.normal(0, 0.03, len(FECHAS) - 1)]).cumsum()
    return pd.Series(valores, index=FECHAS)


def _precios(tasa: pd.Series, duraciones: dict = DURACIONES) -> pd.DataFrame:
    cambios = tasa.diff().fillna(0.0).to_numpy() / 100.0
    return pd.DataFrame({t: 100.0 * np.cumprod(1.0 - d * cambios) for t, d in duraciones.items()}, index=FECHAS)


def _macro(tasa: pd.Series, hasta=None, sin_dato=(), hasta_por_plazo: dict | None = None, extras: dict | None = None):
    """Curva paralela (todos los plazos = `tasa`). `hasta`: fin de toda la curva; `hasta_por_plazo`: fin de un plazo;
    `sin_dato`: fechas sin publicación (feriados del mercado de bonos)."""
    filas = []
    for etiqueta, plazo in et.PLAZOS_ANIOS.items():
        limite = (hasta_por_plazo or {}).get(plazo, hasta)
        for f, v in tasa.items():
            if f in sin_dato or (limite is not None and f > limite):
                continue
            filas.append({"nombre": rfui.nombre_treasury(etiqueta), "fecha": f, "valor": float(v)})
    for nombre, valor in (extras or {}).items():
        filas += [{"nombre": nombre, "fecha": f, "valor": valor} for f in FECHAS]
    return pd.DataFrame(filas)


def _inicio_esperado(fechas_validas, fin, dias=DIAS):
    return max(f for f in fechas_validas if f <= fin - pd.Timedelta(days=dias))


def _texto_pdf(pdf: bytes) -> tuple[str, int]:
    pymupdf = pytest.importorskip("pymupdf", reason="pymupdf no está instalado: no se puede leer el PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return " ".join(" ".join(p.get_text().split()) for p in doc), doc.page_count


def _verificar_fila(fila, precios, tasa, ticker, inicio, fin):
    """Retorno, cambio de tasa, explicado y resto de una fila, contra cuentas hechas aquí con los datos construidos."""
    assert fila["Retorno del período (%)"] == pytest.approx((precios.loc[fin, ticker] / precios.loc[inicio, ticker] - 1) * 100)
    cambio = tasa[fin] - tasa[inicio]
    assert fila["Cambio de la tasa (pp)"] == pytest.approx(cambio)
    assert fila["Explicado por la duración (%)"] == pytest.approx(-fila["Duración medida (años)"] * cambio)
    assert fila["Resto (%)"] == pytest.approx(fila["Retorno del período (%)"] - fila["Explicado por la duración (%)"])


# ---------------------------------------------------------------------------
# Calendarios desfasados
# ---------------------------------------------------------------------------
def test_con_la_curva_atrasada_retorno_y_tasa_se_miden_entre_las_mismas_fechas():
    """Precios hasta el lunes 16-11, H.15 hasta el viernes 13-11 (y sin Columbus ni Veterans Day). La ventana termina
    en la última fecha con precio Y tasa (13-11) y empieza en la última fecha común en 13-11 − 30 días = 14-10 o antes:
    el mismo 14-10 (miércoles, con precio y tasa)."""
    tasa = _tasa(1)
    precios = _precios(tasa)
    macro = _macro(tasa, hasta=D("2026-11-13"), sin_dato=FERIADOS_BONOS)
    datos = inf.calcular(macro, precios, DIAS, MES)
    f = datos["fechas"]
    _requisito(D("2026-11-13") - pd.Timedelta(days=DIAS) == D("2026-10-14"), "13-11 menos 30 días es el 14-10")
    assert (f["corte"], f["fin"], f["inicio"]) == (D("2026-11-16"), D("2026-11-13"), D("2026-10-14"))
    assert f["ultima_por_fuente"]["ETFs (Yahoo Finance)"] == D("2026-11-16")
    assert f["ultima_por_fuente"]["Curva del Tesoro (FRED)"] == D("2026-11-13")
    assert datos["hasta"] == D("2026-11-13")
    for ticker, fila in datos["etfs"].iterrows():
        _verificar_fila(fila, precios, tasa, ticker, f["inicio"], f["fin"])
        assert abs(fila["Resto (%)"]) < 0.10, ticker  # mundo lineal, ventana alineada: no queda nada sin explicar
        assert fila["Estado de la atribución"] == inf.ESTADO_CALCULABLE
    assert datos["curva"]["fecha_inicio"] == f["inicio"] and datos["curva"]["fecha_fin"] == f["fin"]


def test_un_dia_sin_publicacion_de_tasas_no_puede_ser_inicio_ni_fin():
    """El 14-10 (el inicio que tocaría) no hay tasa publicada, aunque sí precio: el inicio pasa al día común anterior
    (13-10) para TODOS, y el retorno se mide desde ahí, no desde el precio del 14-10."""
    tasa = _tasa(2)
    precios = _precios(tasa)
    datos = inf.calcular(_macro(tasa, hasta=D("2026-11-13"), sin_dato=[D("2026-10-14"), *FERIADOS_BONOS]), precios, DIAS, MES)
    f = datos["fechas"]
    assert (f["inicio"], f["fin"]) == (D("2026-10-13"), D("2026-11-13"))
    for ticker, fila in datos["etfs"].iterrows():
        _verificar_fila(fila, precios, tasa, ticker, D("2026-10-13"), D("2026-11-13"))


def test_feriado_del_mercado_de_bonos_como_fin_de_la_ventana():
    """Con corte el miércoles 11-11 (Veterans Day: hay precio, no hay H.15), el fin es el martes 10-11."""
    tasa = _tasa(3)
    datos = inf.calcular(_macro(tasa, sin_dato=FERIADOS_BONOS), _precios(tasa), DIAS, MES, fecha_corte="2026-11-11")
    assert datos["fechas"]["fin"] == D("2026-11-10")
    assert datos["fechas"]["inicio"] == _inicio_esperado([x for x in FECHAS if x not in FERIADOS_BONOS], D("2026-11-10"))


# ---------------------------------------------------------------------------
# ETFs atrasados
# ---------------------------------------------------------------------------
def test_un_etf_con_una_rueda_de_atraso_mueve_la_ventana_de_todos_un_dia_y_no_se_excluye():
    tasa = _tasa(4)
    precios = _precios(tasa)
    precios.loc[D("2026-11-16"), "TLT"] = np.nan
    datos = inf.calcular(_macro(tasa), precios, DIAS, MES)
    assert datos["excluidos"] == []
    assert set(datos["etfs"].index) == set(DURACIONES)
    assert datos["fechas"]["fin"] == D("2026-11-13")
    for ticker, fila in datos["etfs"].iterrows():
        _verificar_fila(fila, precios, tasa, ticker, datos["fechas"]["inicio"], D("2026-11-13"))


def test_las_ruedas_de_atraso_se_cuentan_en_dias_de_bolsa_y_no_en_dias_habiles():
    """TLT tiene su último precio el viernes 04-09 y los demás el martes 08-09; el lunes 07-09 es feriado de la bolsa.
    En ruedas el atraso es 1 (se tolera); en días hábiles serían 2 (se habría excluido sin razón)."""
    tasa = _tasa(5)
    precios = _precios(tasa)
    precios.loc[D("2026-09-08"), "TLT"] = np.nan
    datos = inf.calcular(_macro(tasa), precios, DIAS, MES, fecha_corte="2026-09-08")
    _requisito(np.busday_count(D("2026-09-04").date(), D("2026-09-08").date()) == 2, "son dos días hábiles")
    assert datos["excluidos"] == []
    assert datos["fechas"]["fin"] == D("2026-09-04")


def test_un_etf_con_dos_o_mas_ruedas_de_atraso_se_excluye_se_informa_y_no_mueve_a_los_demas():
    tasa = _tasa(6)
    precios = _precios(tasa)
    precios.loc[precios.index > D("2026-11-11"), "TLT"] = np.nan  # último precio el 11-11: 3 ruedas de atraso
    datos = inf.calcular(_macro(tasa), precios, DIAS, MES)
    assert "TLT" not in datos["etfs"].index
    assert datos["fechas"]["fin"] == D("2026-11-16")  # los demás no retroceden
    (excluido,) = datos["excluidos"]
    assert excluido["ETF"] == "TLT" and excluido["ruedas"] == 3 and excluido["ultima_fecha"] == D("2026-11-11")
    texto, _ = _texto_pdf(inf.generar(_macro(tasa), precios, MES))
    assert "No se comparan" in texto and "TLT (último precio el 11-11-2026, 3 ruedas antes que el resto)" in texto


def test_un_etf_sin_historia_para_el_periodo_se_excluye_y_los_demas_si_se_comparan():
    tasa = _tasa(7)
    precios = _precios(tasa)
    precios.loc[precios.index < D("2026-11-01"), "TLT"] = np.nan  # recién empezó a cotizar
    datos = inf.calcular(_macro(tasa), precios, DIAS, MES)
    assert "TLT" not in datos["etfs"].index and datos["fechas"]["inicio"] is not None
    assert [e["ETF"] for e in datos["excluidos"]] == ["TLT"]
    assert "inicio del período" in datos["excluidos"][0]["motivo"]


def test_si_todos_estan_atrasados_respecto_del_corte_se_comparan_igual_y_se_advierte():
    tasa = _tasa(8)
    datos = inf.calcular(_macro(tasa), _precios(tasa), DIAS, MES, fecha_corte="2026-11-30")
    assert datos["excluidos"] == [] and datos["fechas"]["fin"] == D("2026-11-16")
    assert datos["fechas"]["dias_habiles_de_atraso"] == 10
    texto, _ = _texto_pdf(inf.generar(_macro(tasa), _precios(tasa), MES, fecha_corte="2026-11-30"))
    assert "Advertencia: el último precio de la base es del 16-11-2026, unos 10 días hábiles antes de la fecha de corte" in texto


# ---------------------------------------------------------------------------
# Tasas de referencia faltantes
# ---------------------------------------------------------------------------
def test_un_plazo_atrasado_deja_sin_atribucion_solo_al_etf_que_lo_usa():
    """La tasa a 20 años se corta el 30-10 y el resto de la curva sigue. TLT conserva su retorno pero no su
    atribución; SHY e IEF se atribuyen normalmente y la ventana no retrocede por la tasa a 20 años."""
    tasa = _tasa(9)
    precios = _precios(tasa)
    datos = inf.calcular(_macro(tasa, hasta_por_plazo={20.0: D("2026-10-30")}), precios, DIAS, MES)
    f, etfs = datos["fechas"], datos["etfs"]
    assert f["fin"] == D("2026-11-16")
    assert pd.notna(etfs.loc["TLT", "Retorno del período (%)"])
    assert pd.isna(etfs.loc["TLT", "Explicado por la duración (%)"]) and pd.isna(etfs.loc["TLT", "Cambio de la tasa (pp)"])
    assert "tasa a 20 años no tiene datos desde el 30-10-2026" in etfs.loc["TLT", "Estado de la atribución"]
    for ticker in ("SHY", "IEF"):
        _verificar_fila(etfs.loc[ticker], precios, tasa, ticker, f["inicio"], f["fin"])
    assert datos["curva"] is None  # la curva COMPLETA no existe en el fin: no se grafica la de otro día


def test_con_la_curva_entera_atrasada_no_hay_atribucion_y_los_retornos_usan_el_ultimo_precio():
    tasa = _tasa(10)
    precios = _precios(tasa)
    macro = _macro(tasa, hasta=D("2026-11-02"))  # 10 ruedas antes que los precios
    datos = inf.calcular(macro, precios, DIAS, MES)
    f, etfs = datos["fechas"], datos["etfs"]
    assert f["fin"] == D("2026-11-16") and datos["curva"] is None
    assert etfs["Explicado por la duración (%)"].isna().all()
    assert etfs["Retorno del período (%)"].notna().all()
    assert etfs["Estado de la atribución"].str.contains("curva del Tesoro llega hasta el 02-11-2026").all()
    texto, _ = _texto_pdf(inf.generar(macro, precios, MES))
    assert "Sin atribución en este período" in texto and "Cuadro 2." not in texto


# ---------------------------------------------------------------------------
# Fecha de corte y reproducibilidad
# ---------------------------------------------------------------------------
def test_corte_en_fin_de_semana_termina_el_viernes_y_no_usa_el_lunes():
    tasa = _tasa(11)
    precios = _precios(tasa)
    precios.loc[D("2026-11-16")] *= 0.9  # un lunes que, si se usara, se notaría
    datos = inf.calcular(_macro(tasa), precios, DIAS, MES, fecha_corte="2026-11-15")
    assert datos["fechas"]["corte"] == D("2026-11-15") and datos["fechas"]["corte_solicitado"]
    assert datos["fechas"]["fin"] == D("2026-11-13")
    assert datos["precios"].index.max() <= D("2026-11-15")


def test_un_corte_historico_da_lo_mismo_que_la_base_de_ese_dia_y_es_determinista():
    tasa = _tasa(12)
    precios, macro = _precios(tasa), _macro(tasa)
    corte = D("2026-08-14")
    al_dia = inf.calcular(macro[pd.to_datetime(macro["fecha"]) <= corte], precios[precios.index <= corte], DIAS, MES)
    con_corte = inf.calcular(macro, precios, DIAS, MES, fecha_corte=corte)
    otra_vez = inf.calcular(macro, precios, DIAS, MES, fecha_corte=corte)
    pd.testing.assert_frame_equal(al_dia["etfs"], con_corte["etfs"])
    pd.testing.assert_frame_equal(con_corte["etfs"], otra_vez["etfs"])
    for clave in ("inicio", "fin", "ruedas"):
        assert al_dia["fechas"][clave] == con_corte["fechas"][clave]
    assert con_corte["fechas"]["fin"] <= corte


def test_el_calculo_no_lee_el_reloj_del_computador():
    fuente = inspect.getsource(inf)
    assert not re.search(r"Timestamp\.now|Timestamp\.today|datetime\.now|date\.today", fuente)


# ---------------------------------------------------------------------------
# Sin ventana común
# ---------------------------------------------------------------------------
def test_sin_ventana_comun_no_se_calcula_nada_del_periodo_y_se_explica():
    tasa = _tasa(13)
    precios = _precios(tasa)
    datos = inf.calcular(_macro(tasa), precios, 10_000, "Último año")
    assert datos["fechas"]["inicio"] is None and datos["fechas"]["motivo_sin_ventana"]
    assert datos["etfs"]["Retorno del período (%)"].isna().all()
    assert datos["etfs"]["Explicado por la duración (%)"].isna().all()
    assert datos["etfs"]["Duración medida (años)"].notna().all()


def test_sin_ventana_el_pdf_lo_dice_y_no_imprime_una_atribucion():
    tasa = _tasa(14)
    precios = _precios(tasa)
    precios.loc[precios.index < D("2026-10-30")] = np.nan  # ningún ETF tiene un mes de historia
    texto, _ = _texto_pdf(inf.generar(_macro(tasa), precios, MES))
    assert "Sin ventana comparable para el período" in texto
    assert "Cuadro 2." not in texto and "Gráfico 1." not in texto


# ---------------------------------------------------------------------------
# PDF y compatibilidad
# ---------------------------------------------------------------------------
def test_la_portada_distingue_corte_ventana_y_ultimo_dato_de_cada_fuente():
    tasa = _tasa(15)
    precios = _precios(tasa)
    texto, paginas = _texto_pdf(inf.generar(_macro(tasa, hasta=D("2026-11-13"), sin_dato=FERIADOS_BONOS), precios, MES))
    assert "Fecha de corte: 16-11-2026 (la última fecha con precios en la base)" in texto
    assert "Ventana comparada: del 14-10-2026 al 13-11-2026" in texto
    assert "ETFs (Yahoo Finance), 16-11-2026" in texto and "Curva del Tesoro (FRED), 13-11-2026" in texto
    assert "pueden diferir por unos días de los que muestra el dashboard" in texto
    assert "Datos de mercado al 13-11-2026" in texto
    # El único «—» del PDF es el del pie de página (lo exige también la prueba de integración con datos reales).
    assert texto.count("—") == paginas


def test_la_llamada_del_dashboard_sigue_funcionando_sin_fecha_de_corte():
    """renta_fija_ui llama generar(macro, precios, periodo): el parámetro nuevo es opcional."""
    assert inspect.signature(inf.generar).parameters["fecha_corte"].default is None
    assert inspect.signature(inf.calcular).parameters["fecha_corte"].default is None
    llamada = inspect.getsource(rfui._descarga_del_informe)
    assert "informe.generar(macro, precios, periodo)" in llamada
    tasa = _tasa(16)
    for periodo in inf.PERIODOS:
        assert inf.generar(_macro(tasa), _precios(tasa), periodo).startswith(b"%PDF")


def test_la_duracion_del_informe_es_la_de_renta_fija_con_los_datos_hasta_el_fin_de_la_ventana():
    """I-1 no cambia la fórmula: la duración de la tabla es rf.duracion_empirica sobre los datos hasta E."""
    tasa = _tasa(17)
    precios = _precios(tasa)
    macro = _macro(tasa, hasta=D("2026-11-13"))
    datos = inf.calcular(macro, precios, DIAS, MES)
    fin = datos["fechas"]["fin"]
    for ticker in DURACIONES:
        directa = rf.duracion_empirica(precios.loc[:fin, ticker], (tasa.loc[:fin] / 100.0))
        assert datos["etfs"].loc[ticker, "Duración medida (años)"] == pytest.approx(directa["duracion"])
        assert datos["etfs"].loc[ticker, "Error de la duración"] == pytest.approx(directa["error_estandar"])
