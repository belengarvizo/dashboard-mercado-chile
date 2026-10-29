"""Pruebas del informe en PDF de renta fija: que las cuentas sean las que dice ser y que el documento no afirme de más.

Dos niveles, como en el resto del proyecto:
- `calcular()` con datos SINTÉTICOS, donde las identidades tienen que cumplirse exactas (explicado = −duración × cambio
  de tasa; resto = real − explicado). Un error de signo o de fecha no puede pasar inadvertido.
- El PDF con datos REALES: que se genere, que los números impresos sean los calculados, que no queden huecos («—»,
  «nan») donde debería haber cifras, y que estén los límites que el informe promete declarar.

Las piezas del PDF (informe_base) se prueban aparte al final: ahí vive un error que ya ocurrió y que no se ve leyendo
el código, solo contando páginas.
"""
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pytest
from dotenv import load_dotenv

import estructura_tasas as et
import informe_base as ib
import informe_renta_fija as inf
import renta_fija_ui as rfui
from catalogo_renta_fija import ETFS_RENTA_FIJA

load_dotenv()  # no pisa una DATABASE_URL ya presente en el entorno


# ---------------------------------------------------------------------------
# Datos sintéticos: las identidades de la atribución
# ---------------------------------------------------------------------------
DURACIONES_VERDADERAS = {"SHY": 2.0, "TLT": 15.0}


def _tasa_sintetica(fechas: pd.DatetimeIndex, inicial: float, final: float) -> np.ndarray:
    """Tasa que va de `inicial` a `final` con ruido diario.

    El ruido no es decorativo: una tasa que sube en línea recta tiene el mismo cambio todos los días, su varianza es
    cero y la regresión que mide la duración se indefine (da números del orden de 10¹²)."""
    rng = np.random.default_rng(11)
    return np.linspace(inicial, final, len(fechas)) + rng.normal(0, 0.04, len(fechas))


def _macro_sintetico(fechas: pd.DatetimeIndex, tasa: np.ndarray) -> pd.DataFrame:
    """Macro con la curva completa del Tesoro siguiendo esa tasa, más las series chilenas y el spread."""
    recta = tasa
    filas = []
    for etiqueta in et.PLAZOS_ANIOS:
        filas += [{"nombre": rfui.nombre_treasury(etiqueta), "fecha": f, "valor": v} for f, v in zip(fechas, recta)]
    for nombre, valor in (
        (rfui.NOMBRE_BAA10Y, 1.5), (rfui.NOMBRE_BCP10, 6.0), (rfui.NOMBRE_BCU10, 2.5),
        (rfui.NOMBRE_TPM_CHILE, 4.5), (rfui.NOMBRE_TPM_EEUU, 3.88), (rfui.NOMBRE_UST10, 4.5),
    ):
        filas += [{"nombre": nombre, "fecha": f, "valor": valor} for f in fechas]
    return pd.DataFrame(filas)


def _precios_sinteticos(fechas: pd.DatetimeIndex, tasa: np.ndarray) -> pd.DataFrame:
    """Precios que responden a la tasa con una duración CONOCIDA: retorno = −duración × cambio de tasa + ruido.

    Construirlos así permite comprobar que la regresión recupera esa duración y que los signos de la atribución son los
    correctos. Con precios independientes de la tasa, la duración medida sale cercana a cero y con signo al azar."""
    rng = np.random.default_rng(3)
    cambios = pd.Series(tasa, index=fechas).diff().fillna(0.0).to_numpy() / 100.0
    datos = {t: 100 * (1 + (-d * cambios + rng.normal(0, 0.0004, len(fechas)))).cumprod()
             for t, d in DURACIONES_VERDADERAS.items()}
    datos["^GSPC"] = 5000 * np.exp(rng.normal(0.0003, 0.008, len(fechas)).cumsum())
    return pd.DataFrame(datos, index=fechas)


def _caso(inicial: float, final: float, periodos: int = 500):
    fechas = pd.bdate_range("2024-01-01", periods=periodos)
    tasa = _tasa_sintetica(fechas, inicial, final)
    return _macro_sintetico(fechas, tasa), _precios_sinteticos(fechas, tasa)


@pytest.fixture
def sintetico():
    """Caso base: la tasa sube de 4% a 5% a lo largo de 500 ruedas."""
    return _caso(4.0, 5.0)


def test_la_duracion_medida_recupera_la_que_se_uso_para_construir_los_precios(sintetico):
    """Si los precios se construyeron con una duración de 2 y de 15, la regresión del informe tiene que encontrarlas."""
    macro, precios = sintetico
    etfs = inf.calcular(macro, precios, 365, "Último año")["etfs"]
    for ticker, verdadera in DURACIONES_VERDADERAS.items():
        assert etfs.loc[ticker, "Duración medida (años)"] == pytest.approx(verdadera, abs=0.3), ticker
        assert etfs.loc[ticker, "R² con la tasa"] > 0.85, ticker  # los precios se construyeron casi solo con la tasa


def test_lo_explicado_por_la_duracion_es_exactamente_menos_duracion_por_el_cambio_de_tasa(sintetico):
    macro, precios = sintetico
    etfs = inf.calcular(macro, precios, 365, "Último año")["etfs"]
    assert len(etfs) == 2
    for ticker, fila in etfs.iterrows():
        esperado = -fila["Duración medida (años)"] * fila["Cambio de la tasa (pp)"]
        assert fila["Explicado por la duración (%)"] == pytest.approx(esperado), ticker


def test_el_resto_es_exactamente_el_retorno_real_menos_lo_explicado(sintetico):
    macro, precios = sintetico
    etfs = inf.calcular(macro, precios, 365, "Último año")["etfs"]
    for ticker, fila in etfs.iterrows():
        assert fila["Resto (%)"] == pytest.approx(fila["Retorno del período (%)"] - fila["Explicado por la duración (%)"]), ticker


def test_el_retorno_del_periodo_se_mide_entre_las_puntas_del_periodo(sintetico):
    macro, precios = sintetico
    dias = 90
    etfs = inf.calcular(macro, precios, dias, "Últimos 3 meses")["etfs"]
    for ticker in etfs.index:
        serie = precios[ticker].dropna()
        inicio = serie[serie.index <= serie.index[-1] - pd.Timedelta(days=dias)].iloc[-1]
        assert etfs.loc[ticker, "Retorno del período (%)"] == pytest.approx((serie.iloc[-1] / inicio - 1) * 100), ticker


def test_el_cambio_de_tasa_es_el_de_la_tasa_de_referencia_de_cada_etf(sintetico):
    macro, precios = sintetico
    dias = 365
    etfs = inf.calcular(macro, precios, dias, "Último año")["etfs"]
    for ticker, fila in etfs.iterrows():
        tasa = rfui._rendimiento_del_tesoro(macro, ETFS_RENTA_FIJA[ticker]["plazo_referencia"]) * 100
        inicio = tasa[tasa.index <= tasa.index[-1] - pd.Timedelta(days=dias)].iloc[-1]
        assert fila["Cambio de la tasa (pp)"] == pytest.approx(tasa.iloc[-1] - inicio), ticker
    # la curva de este caso sube un punto completo en 500 ruedas, así que en un año sube y menos que ese punto
    assert 0 < etfs["Cambio de la tasa (pp)"].iloc[0] < 1.2


def test_con_la_curva_al_alza_lo_explicado_es_negativo_y_mas_para_el_plazo_largo(sintetico):
    """Si las tasas suben, la duración anticipa una caída de precio, y más grande mientras mayor sea la duración."""
    macro, precios = sintetico
    etfs = inf.calcular(macro, precios, 365, "Último año")["etfs"]
    assert (etfs["Explicado por la duración (%)"] < 0).all()
    largo, corto = etfs["Duración medida (años)"].idxmax(), etfs["Duración medida (años)"].idxmin()
    assert etfs.loc[largo, "Explicado por la duración (%)"] < etfs.loc[corto, "Explicado por la duración (%)"]


def test_con_la_curva_a_la_baja_se_invierte_el_signo():
    macro, precios = _caso(5.0, 4.0)  # ahora las tasas bajan
    etfs = inf.calcular(macro, precios, 365, "Último año")["etfs"]
    assert (etfs["Cambio de la tasa (pp)"] < 0).all()
    assert (etfs["Explicado por la duración (%)"] > 0).all()


def test_la_curva_del_informe_son_las_dos_puntas_del_periodo(sintetico):
    macro, precios = sintetico
    curva = inf.calcular(macro, precios, 365, "Último año")["curva"]
    assert curva["fecha_fin"] - curva["fecha_inicio"] >= pd.Timedelta(days=360)
    assert np.allclose(curva["cambio"].to_numpy(), (curva["fin"] - curva["inicio"]).to_numpy())
    assert (curva["cambio"] > 0).all()  # en este caso toda la curva sube


def test_sin_historia_suficiente_no_se_inventa_un_periodo(sintetico):
    """Con un período más largo que los datos, las cifras que dependen de él quedan vacías en vez de usar otra fecha."""
    macro, precios = sintetico
    datos = inf.calcular(macro, precios, 10_000, "Último año")
    assert datos["curva"] is None and datos["credito"] is None
    assert datos["etfs"]["Cambio de la tasa (pp)"].isna().all()
    assert datos["etfs"]["Explicado por la duración (%)"].isna().all()
    assert datos["etfs"]["Duración medida (años)"].notna().all()  # lo que no depende del período sí se calcula


def test_la_frase_del_cupon_solo_aparece_cuando_los_datos_la_sostienen():
    """La afirmación «el resto es el cupón» solo se escribe si el resto es positivo en todos y su tamaño es creíble."""
    etfs = pd.DataFrame({"Resto (%)": [4.0] * 10}, index=[f"E{i}" for i in range(10)])
    # un resto negativo en alguno basta para que la afirmación no se haga
    con_negativo = etfs.copy()
    con_negativo.loc[con_negativo.index[0], "Resto (%)"] = -1.0
    assert inf._frase_del_resto(con_negativo, 365) is None
    # ni con pocos instrumentos para sostenerla
    assert inf._frase_del_resto(etfs.head(3), 365) is None
    # y tampoco se hace si el tamaño anualizado no se parece al rendimiento de un bono
    absurdo = etfs.copy()
    absurdo["Resto (%)"] = 90.0
    assert inf._frase_del_resto(absurdo, 365) is None
    creible = etfs.copy()
    creible["Resto (%)"] = 4.0
    frase = inf._frase_del_resto(creible, 365)
    assert frase is not None and "4.00%" in frase and "cupón" in frase


# ---------------------------------------------------------------------------
# El PDF, con datos reales
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def datos_reales():
    from constants import TICKERS_RENTA_FIJA
    from models import get_engine

    motor = get_engine()
    macro = pd.read_sql("SELECT nombre, fecha, valor FROM series_macro", motor)
    tickers = tuple(TICKERS_RENTA_FIJA) + ("^GSPC",)
    precios = pd.read_sql(
        "SELECT ticker, fecha, precio_cierre FROM precios_acciones WHERE ticker IN %(t)s", motor, params={"t": tickers}
    )
    return rfui._recortar(macro), rfui._precios_en_columnas(precios)


def _texto(pdf: bytes) -> str:
    pymupdf = pytest.importorskip("pymupdf", reason="pymupdf no está instalado: no se puede leer el PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return " ".join(" ".join(p.get_text().split()) for p in doc)


def _paginas(pdf: bytes) -> int:
    pymupdf = pytest.importorskip("pymupdf", reason="pymupdf no está instalado: no se puede leer el PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return doc.page_count


def test_el_informe_se_genera_con_datos_reales_en_los_tres_periodos(datos_reales):
    macro, precios = datos_reales
    for periodo in inf.PERIODOS:
        pdf = inf.generar(macro, precios, periodo)
        assert pdf.startswith(b"%PDF"), periodo
        assert len(pdf) > 50_000, periodo  # trae los tres gráficos
        assert 3 <= _paginas(pdf) <= 9, (periodo, _paginas(pdf))


def test_los_numeros_impresos_son_los_calculados(datos_reales):
    macro, precios = datos_reales
    periodo = "Último año"
    datos = inf.calcular(macro, precios, inf.PERIODOS[periodo], periodo)
    texto = _texto(inf.generar(macro, precios, periodo))
    for ticker, fila in datos["etfs"].iterrows():
        assert ticker in texto
        for columna, formato in (
            ("Retorno del período (%)", lambda v: ib.pct(v, 2, True)),
            ("Duración medida (años)", lambda v: ib.num(v, 2)),
            ("Explicado por la duración (%)", lambda v: ib.pct(v, 2, True)),
            ("Resto (%)", lambda v: ib.pct(v, 2, True)),
        ):
            if pd.notna(fila[columna]):
                assert formato(fila[columna]) in texto, f"{ticker}: falta {columna} ({formato(fila[columna])})"


def test_el_informe_no_deja_huecos_donde_deberia_haber_cifras(datos_reales):
    macro, precios = datos_reales
    texto = _texto(inf.generar(macro, precios, "Último año"))
    assert not re.search(r"\b[Nn]a[Nn]\b", texto), "quedó un «nan» impreso"
    assert "None" not in texto
    # el único «—» permitido es el del pie de página («Renta fija — generado el …»)
    guiones = [t for t in texto.split("Renta fija — generado") if False]  # el pie se repite por página
    assert texto.count("—") == _paginas(inf.generar(macro, precios, "Último año")), guiones


def test_el_informe_declara_sus_limites_y_no_se_presenta_como_asesoria(datos_reales):
    macro, precios = datos_reales
    texto = _texto(inf.generar(macro, precios, "Último año"))
    assert "No hay recomendaciones de compra ni de venta" in texto
    assert "no constituye asesoría de inversión" in texto
    assert "No hay proyecciones de tasas ni de inflación" in texto
    assert "No hay causas macroeconómicas" in texto


def test_el_informe_trae_sus_seis_secciones_y_la_explicacion_de_cada_una(datos_reales):
    macro, precios = datos_reales
    texto = _texto(inf.generar(macro, precios, "Último año"))
    secciones = ["RESUMEN", "1. QUÉ PASÓ", "2. POR QUÉ: LA DURACIÓN MANDA", "3. EL OTRO MOTOR: EL RIESGO DE CRÉDITO",
                 "4. CHILE: PESOS, UF Y POLÍTICA MONETARIA", "5. QUÉ PASARÍA SI LAS TASAS SE MUEVEN", "6. QUÉ NO DICE ESTE INFORME"]
    posiciones = [texto.find(s) for s in secciones]
    assert all(p >= 0 for p in posiciones), [s for s, p in zip(secciones, posiciones) if p < 0]
    assert posiciones == sorted(posiciones), "las secciones no van en orden"
    # el molde didáctico: cada error frecuente nombrado y corregido
    assert texto.count("Error frecuente") >= 3
    assert "Recuadro 1" in texto


def test_el_informe_cita_su_fecha_de_cierre_y_sus_fuentes(datos_reales):
    macro, precios = datos_reales
    datos = inf.calcular(macro, precios, 365, "Último año")
    texto = _texto(inf.generar(macro, precios, "Último año"))
    assert f"Datos de mercado al {ib.fecha(datos['hasta'])}" in texto
    for fuente in ("Yahoo Finance", "FRED", "Banco Central de Chile"):
        assert fuente in texto


def test_la_sensibilidad_es_simetrica_y_proporcional_a_la_duracion(datos_reales):
    """El cuadro 3 no es un pronóstico: es −duración × cambio, así que +1 pp y −1 pp tienen que dar lo mismo con signo opuesto."""
    macro, precios = datos_reales
    etfs = inf.calcular(macro, precios, 365, "Último año")["etfs"]
    tabla = inf._tabla_sensibilidad(etfs).set_index("ETF")
    for ticker in tabla.index:
        sube = float(tabla.loc[ticker, "+1.0 pp"].rstrip("%"))
        baja = float(tabla.loc[ticker, "-1.0 pp"].rstrip("%"))
        media = float(tabla.loc[ticker, "+0.5 pp"].rstrip("%"))
        assert sube == pytest.approx(-baja, abs=0.05), ticker
        assert sube == pytest.approx(2 * media, abs=0.16), ticker  # las cifras del cuadro van redondeadas a un decimal
        assert sube == pytest.approx(-float(tabla.loc[ticker, "Duración"]), abs=0.05), ticker


def test_sin_datos_el_informe_lo_dice_en_vez_de_mostrar_cifras_de_ejemplo():
    vacio_macro = pd.DataFrame(columns=["nombre", "fecha", "valor"])
    vacio_precios = pd.DataFrame()
    pdf = inf.generar(vacio_macro, vacio_precios, "Último año")
    assert pdf.startswith(b"%PDF")
    texto = _texto(pdf)
    assert "No se muestran cifras de ejemplo" in texto
    assert not re.search(r"\d+\.\d+%", texto), "apareció un porcentaje sin datos en la base"


# ---------------------------------------------------------------------------
# Las piezas del PDF
# ---------------------------------------------------------------------------
def test_el_markdown_del_pdf_convierte_negrita_cursiva_y_escapa_el_html():
    assert ib.md("hola **mundo**") == "hola <b>mundo</b>"
    assert ib.md("hola *mundo*") == "hola <i>mundo</i>"
    assert ib.md("**a** y *b*") == "<b>a</b> y <i>b</i>"
    assert ib.md("a < b & c") == "a &lt; b &amp; c"
    assert "<script>" not in ib.md("<script>alert(1)</script>")


def test_los_numeros_sin_dato_salen_como_guion_y_nunca_como_cero():
    for vacio in (None, np.nan, pd.NA):
        assert ib.num(vacio) == "—" and ib.pct(vacio) == "—" and ib.fecha(vacio) == "—"
    assert ib.num(0) == "0.00" and ib.pct(0) == "0.00%"
    assert ib.num(1234.5, 1) == "1,234.5" and ib.pct(-2.5, 1, True) == "-2.5%" and ib.pct(2.5, 1, True) == "+2.5%"


def test_una_nota_no_se_parte_entre_paginas_pero_no_se_anida_dentro_de_otro_bloque():
    """Anidar un KeepTogether dentro de otro mandaba el bloque entero a la página siguiente aunque cupiera:
    el informe pasó de 5 páginas a 7, con dos casi en blanco. La nota de `con_su_nota` va suelta."""
    from reportlab.platypus import KeepTogether, Paragraph, Spacer

    suelta = ib.nota("una nota")
    assert isinstance(suelta, KeepTogether)
    pegada = ib.con_su_nota(Spacer(1, 1), "otra nota")
    assert isinstance(pegada, KeepTogether)
    internos = pegada._content if hasattr(pegada, "_content") else pegada._flowables
    assert not any(isinstance(x, KeepTogether) for x in internos), "la nota quedó anidada dentro del bloque"
    assert any(isinstance(x, Paragraph) for x in internos)
