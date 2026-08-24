"""Utilidad compartida entre tests: parsea la tabla HTML del heatmap
(con tooltips :hover integrados) a un DataFrame limpio.

pd.read_html() NO sirve para esto: concatena el texto visible del ticker
con el texto oculto del tooltip (visibility:hidden no es lo mismo que
"no está en el HTML" — un parser de texto plano no distingue eso),
verificado con una prueba mínima antes de escribir esto:

    >>> import pandas as pd
    >>> html = '<table><tr><th>Ticker</th></tr><tr><td>'\\
    ...   '<span class="glosario-tooltip">FALABELLA'\\
    ...   '<span class="glosario-tooltip-texto">oculto</span></span>'\\
    ...   '</td></tr></table>'
    >>> pd.read_html(html)[0]["Ticker"][0]
    'FALABELLAoculto'

Por eso se usa BeautifulSoup y se extrae el span oculto (.glosario-
tooltip-texto) ANTES de leer el texto de la celda del ticker.
"""
import pandas as pd
from bs4 import BeautifulSoup


def parsear_tabla_heatmap(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    tabla = soup.find("table")
    filas_tr = tabla.find_all("tr")
    encabezados = [th.get_text(strip=True) for th in filas_tr[0].find_all("th")]

    filas = []
    for tr in filas_tr[1:]:
        valores = []
        for td in tr.find_all("td"):
            tooltip_span = td.find("span", class_="glosario-tooltip")
            if tooltip_span is not None:
                interior = tooltip_span.find("span", class_="glosario-tooltip-texto")
                if interior is not None:
                    interior.extract()
                valores.append(tooltip_span.get_text(strip=True))
            else:
                valores.append(td.get_text(strip=True))
        filas.append(valores)

    return pd.DataFrame(filas, columns=encabezados).set_index(encabezados[0])


def tooltip_html_de_ticker(html: str, ticker: str) -> str | None:
    """Devuelve el HTML interno (con las etiquetas <b>/<hr> intactas) del
    tooltip oculto de un ticker específico, para poder revisar su
    contenido con detalle (ej. comprobar que un número real aparece)."""
    soup = BeautifulSoup(html, "lxml")
    for span in soup.find_all("span", class_="glosario-tooltip"):
        interior = span.find("span", class_="glosario-tooltip-texto")
        if interior is None:
            continue
        contenido_interior = interior.decode_contents()
        interior.extract()
        if span.get_text(strip=True) == ticker:
            return contenido_interior
    return None
