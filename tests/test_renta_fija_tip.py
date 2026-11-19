"""I-4a: TIP (bonos del Tesoro ligados a la inflación) sin atribución contra la tasa NOMINAL (offline, datos sintéticos).

QUÉ SE PRUEBA
    El precio de TIP responde a la tasa real del Tesoro y al reajuste del capital por inflación. La base solo tiene la
    curva nominal (nominal = real + inflación de equilibrio), así que su sensibilidad contra la nominal no es una
    duración real. Desde I-4a, en el PDF y en la tabla del dashboard:
      - se conservan sus retornos y los indicadores que no dependen de esa tasa (volatilidad, caída, beta, Sharpe);
      - duración medida, su margen, R², cambio de tasa, explicado, resto y devengo quedan «n. e.» (no estimado);
      - TIP no entra en el Cuadro 3 ni en la mediana de tasas que usan otras frases;
      - los demás ETFs no cambian en nada.

CÓMO
    Mundo construido: tasa real con su camino, inflación de equilibrio que se mueve aparte, nominal = real + equilibrio.
    TIP responde a −4,5 × Δ real; los fondos nominales, a −D × Δ nominal. Las cifras esperadas salen de ese modelo.
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
import informe_renta_fija as inf  # noqa: E402
import renta_fija as rf  # noqa: E402
import renta_fija_ui as rfui  # noqa: E402

FECHAS = pd.bdate_range("2025-01-06", periods=420)
N = len(FECHAS)
NOMINALES = {"SHY": 1.9, "IEF": 6.5, "LQD": 7.3}
COLUMNAS_NOMINALES = ["Cambio de la tasa (pp)", "Duración medida (años)", "Explicado por la duración (%)", "Resto (%)",
                      "Devengo aproximado (%)", "No explicado (%)", "R² con la tasa"]


def _precio(retornos):
    r = np.asarray(retornos, dtype=float).copy()
    r[0] = 0.0
    return 100.0 * np.cumprod(1.0 + r)


def _cambios(tasa_pct):
    return np.diff(tasa_pct, prepend=tasa_pct[0]) / 100.0


def _mundo(semilla=1, con_tip=True):
    rng = np.random.default_rng(semilla)
    real = 1.8 + np.concatenate([[0.0], rng.normal(0, 0.03, N - 1)]).cumsum()
    equilibrio = 2.3 + np.concatenate([[0.0], rng.normal(0, 0.02, N - 1)]).cumsum()
    equilibrio[N - 25:] += np.linspace(0, 0.40, 25)            # la inflación esperada sube 40 pb en el último mes
    nominal = real + equilibrio
    filas = [{"nombre": rfui.nombre_treasury(e), "fecha": f, "valor": float(v)} for e in et.PLAZOS_ANIOS for f, v in zip(FECHAS, nominal)]
    filas += [{"nombre": rfui.NOMBRE_TPM_EEUU, "fecha": f, "valor": 4.0} for f in FECHAS]   # para el Sharpe
    precios = pd.DataFrame({t: _precio(-d * _cambios(nominal)) for t, d in NOMINALES.items()}, index=FECHAS)
    if con_tip:
        precios["TIP"] = _precio(-4.5 * _cambios(real))
    precios[rfui.TICKER_MERCADO] = _precio(rng.normal(0.0004, 0.01, N))
    return real, nominal, pd.DataFrame(filas), precios


def _texto_pdf(pdf: bytes) -> str:
    pymupdf = pytest.importorskip("pymupdf", reason="pymupdf no está instalado: no se puede leer el PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return " ".join(" ".join(p.get_text().split()) for p in doc)


def _entre(texto, desde, hasta):
    return texto[texto.find(desde):texto.find(hasta, texto.find(desde))]


# ---------------------------------------------------------------------------
# PDF: Cuadro 1, 2 y 3 y conclusiones
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("periodo", list(inf.PERIODOS))
def test_tip_conserva_su_retorno_observado_y_no_recibe_ninguna_cifra_basada_en_la_tasa_nominal(periodo):
    _, _, macro, precios = _mundo()
    datos = inf.calcular(macro, precios, inf.PERIODOS[periodo], periodo)
    fila = datos["etfs"].loc["TIP"]
    inicio, fin = datos["fechas"]["inicio"], datos["fechas"]["fin"]
    esperado = (precios.loc[fin, "TIP"] / precios.loc[inicio, "TIP"] - 1) * 100    # la misma ventana común de I-1
    assert fila["Retorno del período (%)"] == pytest.approx(esperado, abs=1e-10)
    for columna in COLUMNAS_NOMINALES:
        assert pd.isna(fila[columna]), columna
    for columna in ("Volatilidad (%)", "Caída máxima 1 año (%)"):
        assert pd.notna(fila[columna]), columna


def test_el_movimiento_de_la_inflacion_esperada_ya_no_se_atribuye_a_tip():
    """Con la nominal subiendo por la inflación esperada (no por la real), una atribución nominal «explicaría» una caída
    de TIP que no ocurrió. Ahora no hay explicado, y la evaluación es «sin tasa real»."""
    real, nominal, macro, precios = _mundo()
    datos = inf.calcular(macro, precios, 30, "Último mes")
    ev = next(e for e in datos["evaluaciones"] if e["ETF"] == "TIP")
    assert ev["clase"] == "sin_tasa_real" and ev["devengo"] is None and pd.isna(ev["anticipado"])
    frase = inf._frase_de_evaluacion(ev)
    assert "tasa real" in frase and "no se estima su sensibilidad" in frase


def test_en_el_cuadro_2_tip_aparece_con_su_retorno_y_n_e_en_todo_lo_demas():
    _, _, macro, precios = _mundo()
    datos = inf.calcular(macro, precios, 90, "Últimos 3 meses")
    tabla = inf._tabla_atribucion(datos["etfs"]).set_index("ETF")
    tip = tabla.loc["TIP"]
    assert tip["Real"] == inf.ib.pct(datos["etfs"].loc["TIP", "Retorno del período (%)"], 2, True)
    for columna in tabla.columns:
        if columna != "Real":
            assert tip[columna] == inf.NO_ESTIMADO, columna
    for ticker in NOMINALES:                                  # los demás conservan sus cifras
        assert tabla.loc[ticker, "Duración"] != inf.NO_ESTIMADO and tabla.loc[ticker, "Explicado"] != inf.NO_ESTIMADO


def test_tip_no_esta_en_el_cuadro_3_y_las_notas_lo_explican_sin_contradicciones():
    _, _, macro, precios = _mundo()
    datos = inf.calcular(macro, precios, 90, "Últimos 3 meses")
    assert "TIP" not in set(inf._tabla_sensibilidad(datos["etfs"])["ETF"])
    texto = _texto_pdf(inf.generar(macro, precios, "Últimos 3 meses"))
    nota2 = _entre(texto, "Cuadro 2.", "Gráfico 3")
    assert "En TIP solo se informa el retorno" in nota2 and "tasa real" in nota2
    nota3 = _entre(texto, "Cuadro 3.", "6. ")
    assert "TIP no se incluye" in nota3
    # Ninguna frase presenta una sensibilidad o duración de TIP contra la tasa nominal.
    assert not re.search(r"TIP[^.]*(duraci[oó]n medida|sensibilidad estimada)[^.]*\d", texto), "TIP con una sensibilidad numérica"
    resumen = next(a for a in datos["afirmaciones"] if a.clave == "atribucion").texto
    assert "TIP no se contrasta con las tasas" in resumen


def test_la_presencia_de_tip_no_cambia_nada_de_los_demas_etfs():
    """Mismo mundo, con y sin TIP: las cifras y las evaluaciones de los demás son idénticas (TIP ya no entra en la mediana
    de tasas al inicio que dimensiona el devengo omitido de los fondos de crédito)."""
    _, _, macro, con = _mundo()
    sin = con.drop(columns=["TIP"])
    a = inf.calcular(macro, con, 365, "Último año")
    b = inf.calcular(macro, sin, 365, "Último año")
    columnas = [c for c in a["etfs"].columns if c not in ("ultima_fecha",)]
    pd.testing.assert_frame_equal(a["etfs"].loc[list(NOMINALES), columnas], b["etfs"].loc[list(NOMINALES), columnas])
    clases_a = {e["ETF"]: (e["clase"], e.get("retorno_comparado")) for e in a["evaluaciones"] if e["ETF"] != "TIP"}
    clases_b = {e["ETF"]: (e["clase"], e.get("retorno_comparado")) for e in b["evaluaciones"]}
    assert clases_a == clases_b
    assert "TIP" not in a["contexto"]["tasa_inicio"]


def test_con_tip_atrasado_se_excluye_de_la_comparacion_como_cualquier_etf():
    _, _, macro, precios = _mundo()
    precios.loc[precios.index[N - 20:], "TIP"] = np.nan
    datos = inf.calcular(macro, precios, 30, "Último mes")
    assert "TIP" not in datos["etfs"].index or pd.isna(datos["etfs"].loc["TIP", "Retorno del período (%)"])
    assert any(e["ETF"] == "TIP" for e in datos["excluidos"])


# ---------------------------------------------------------------------------
# Dashboard: tabla de ETFs, tooltip y tabla de duración medida
# ---------------------------------------------------------------------------
def test_el_resumen_del_dashboard_deja_a_tip_sin_sensibilidad_nominal_y_conserva_lo_demas():
    _, nominal, macro, precios = _mundo()
    resumen = rfui._resumen_de_etfs(precios, macro, FECHAS[-1])
    for columna in rfui.COLUMNAS_DE_SENSIBILIDAD_NOMINAL:
        assert pd.isna(resumen.loc["TIP", columna]), columna
    directo = rf.resumen_de_instrumento(precios["TIP"], precios[rfui.TICKER_MERCADO], pd.Series(nominal / 100, index=FECHAS), None)
    for columna in ("1M %", "YTD %", "Retorno 1 año (%)", "Volatilidad (%)", "Caída máxima 1 año (%)", "Beta vs S&P 500"):
        assert resumen.loc["TIP", columna] == pytest.approx(directo[columna], nan_ok=True), columna
    for ticker in NOMINALES:                                  # los demás, idénticos al cálculo directo
        directo = rf.resumen_de_instrumento(precios[ticker], precios[rfui.TICKER_MERCADO],
                                            pd.Series(nominal / 100, index=FECHAS), None)
        for columna in rfui.COLUMNAS_DE_SENSIBILIDAD_NOMINAL:
            assert resumen.loc[ticker, columna] == pytest.approx(directo[columna]), (ticker, columna)


def _tabla_leida(resumen):
    """La tabla del dashboard leída por NOMBRE de encabezado y ticker (parser de BeautifulSoup ya usado en el proyecto)."""
    from _html_table_utils import parsear_tabla_heatmap
    return parsear_tabla_heatmap(rfui._tabla_de_etfs_html(resumen, 4.0))


def _verificar_tabla(tabla, resumen):
    assert tabla.loc["TIP", "Duración"] == "n. e." and tabla.loc["TIP", "R²"] == "n. e."
    for columna in ("1A %", "Vol. %", "Caída máx. %", "Beta", "Sharpe", "1M %"):
        assert tabla.loc["TIP", columna] not in ("n. e.", "—"), columna
    for ticker in NOMINALES:
        assert tabla.loc[ticker, "Duración"] == f"{resumen.loc[ticker, 'Duración medida (años)']:.2f}", ticker
        assert tabla.loc[ticker, "R²"] == f"{resumen.loc[ticker, 'R² con la tasa']:.2f}", ticker


def test_la_tabla_del_dashboard_muestra_n_e_solo_en_la_duracion_y_el_r2_de_tip():
    _, _, macro, precios = _mundo()
    resumen = rfui._resumen_de_etfs(precios, macro, FECHAS[-1])
    tabla = _tabla_leida(resumen)
    assert list(tabla.index) == list(resumen.index)          # TIP sigue en la tabla
    _verificar_tabla(tabla, resumen)
    assert (tabla == "n. e.").sum().sum() == 2               # solo esas dos celdas


@pytest.mark.parametrize("orden", ["invertido", "tip_primero"])
def test_el_n_e_sigue_al_ticker_si_cambia_el_orden_de_los_etfs(orden):
    _, _, macro, precios = _mundo()
    resumen = rfui._resumen_de_etfs(precios, macro, FECHAS[-1])
    nuevo = list(resumen.index)[::-1] if orden == "invertido" else ["TIP"] + [t for t in resumen.index if t != "TIP"]
    reordenado = resumen.loc[nuevo]
    tabla = _tabla_leida(reordenado)
    assert list(tabla.index) == nuevo
    _verificar_tabla(tabla, reordenado)
    assert (tabla == "n. e.").sum().sum() == 2


def test_el_n_e_sigue_a_la_columna_si_cambia_el_orden_de_las_columnas(monkeypatch):
    _, _, macro, precios = _mundo()
    resumen = rfui._resumen_de_etfs(precios, macro, FECHAS[-1])
    columnas = list(rfui.COLUMNAS_TABLA)
    monkeypatch.setattr(rfui, "COLUMNAS_TABLA", columnas[:1] + columnas[1:][::-1])   # «Grupo» primero, el resto al revés
    tabla = _tabla_leida(resumen)
    assert list(tabla.columns)[1:] == [rfui.ENCABEZADOS.get(c, c) for c in columnas[1:][::-1]]
    _verificar_tabla(tabla, resumen)
    assert (tabla == "n. e.").sum().sum() == 2


def test_el_n_e_nunca_pisa_un_numero_ni_marca_a_otro_etf_sin_dato():
    """Si TIP trajera un número en esas columnas, se muestra el número (no se tapa con «n. e.»); y un ETF nominal sin
    duración (por falta de historia) sigue mostrando «—», no «n. e.»."""
    _, _, macro, precios = _mundo()
    resumen = rfui._resumen_de_etfs(precios, macro, FECHAS[-1]).copy()
    resumen.loc["TIP", "Duración medida (años)"] = 4.5
    resumen.loc["SHY", "Duración medida (años)"] = np.nan
    tabla = _tabla_leida(resumen)
    assert tabla.loc["TIP", "Duración"] == "4.50" and tabla.loc["TIP", "R²"] == "n. e."
    assert tabla.loc["SHY", "Duración"] == "—"


def test_el_tooltip_de_tip_explica_por_que_no_hay_duracion_y_los_demas_conservan_el_suyo():
    _, _, macro, precios = _mundo()
    resumen = rfui._resumen_de_etfs(precios, macro, FECHAS[-1])
    html = rfui._tabla_de_etfs_html(resumen, 4.0)
    assert "Duración y R²: n. e. (no estimado)" in html and "tasa real" in html
    assert html.count("Duración medida =") == len(NOMINALES)


def test_la_tabla_de_duracion_medida_deja_a_tip_en_n_e_incluida_la_duracion_teorica_nominal():
    _, _, macro, precios = _mundo()
    resumen = rfui._resumen_de_etfs(precios, macro, FECHAS[-1])
    actual = rfui._curva_actual(macro)
    filas = {f["ETF"]: f for f in rfui._filas_de_duracion(resumen, actual[2] if actual else None)}
    for columna in ("Ref. Tesoro", "Duración medida", "Margen (±2 err.)", "R²", "Duración teórica"):
        assert filas["TIP"][columna] == rfui.NO_ESTIMADO, columna
    for ticker in NOMINALES:
        assert filas[ticker]["Duración medida"] != rfui.NO_ESTIMADO and filas[ticker]["Ref. Tesoro"].endswith("años")


def test_solo_tip_queda_fuera_de_la_tasa_nominal():
    assert [t for t in rfui.ETFS_RENTA_FIJA if not rfui.usa_tasa_nominal(t)] == ["TIP"]
