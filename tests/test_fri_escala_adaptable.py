"""F4-b: escala adaptable de la interfaz FRI (solo presentación; offline, sin base ni red).

QUÉ SE PRUEBA
    - El menú lateral se fuerza visible aunque el navegador recuerde que se cerró (localStorage «stSidebarCollapsed-»).
    - Cada tamaño fluido clamp(mín, X vw, máx) del bloque adaptable vale exactamente el tamaño aprobado en un ancho de 1672 px:
      a ese ancho (el de las maquetas) la interfaz queda idéntica; solo se reduce en pantallas más angostas.
    - Los títulos no se cortan en mitad de una palabra y la ilustración de las tarjetas no se posiciona sobre el texto.
    - La fila de indicadores reparte sus tarjetas en dos filas parejas (--mitad = ⌈n/2⌉) en pantallas angostas.
La verificación visual (5 resoluciones × 6 secciones, con el menú «recordado como cerrado») se hace fuera del repositorio con
Playwright; ver fri/LEEME.md.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import re
import sys

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(RAIZ)

import fri.panoramas as p  # noqa: E402
from fri.estilos import CSS  # noqa: E402

ANCHO_MAQUETA = 1672
ADAPTABLE = CSS.split("ESCALA ADAPTABLE", 1)[1]
GENERAL = ADAPTABLE.split("@media", 1)[0]          # reglas que rigen en todos los anchos (sin consultas de medios)


def test_el_menu_lateral_se_fuerza_visible_y_no_queda_un_espacio_vacio():
    regla = re.search(r'\[data-testid="stSidebar"\] \{\{?([^}]*)\}', ADAPTABLE).group(1)
    assert "transform: none !important" in regla and "visibility: visible !important" in regla
    assert "stExpandSidebarButton" in ADAPTABLE                  # sin botón de expandir: el menú ya está siempre abierto


def test_los_tamanos_fluidos_valen_lo_aprobado_en_el_ancho_de_las_maquetas():
    encontrados = 0
    for minimo, vw, maximo in re.findall(r"clamp\((-?[\d.]+)px,\s*(-?[\d.]+)vw,\s*(-?[\d.]+)px\)", GENERAL):
        minimo, vw, maximo = float(minimo), float(vw), float(maximo)
        if maximo < 0:
            minimo, maximo = maximo, minimo                      # margen negativo: el «máximo» aprobado es el más negativo
        assert abs(vw * ANCHO_MAQUETA / 100 - maximo) <= 1.0, (minimo, vw, maximo)
        encontrados += 1
    assert encontrados >= 20


def test_los_titulos_no_se_cortan_en_mitad_de_palabra():
    regla = re.search(r"\.fri-portada \.h1, [^{]*\.fri-tarjeta-nav \.h3[^{]*\{([^}]*)\}", ADAPTABLE)
    assert regla and "word-break: normal !important" in regla.group(1) and "overflow-wrap: normal !important" in regla.group(1)


def test_la_ilustracion_ocupa_su_propio_espacio_y_no_tapa_el_texto():
    regla = re.search(r"\.fri-tarjeta-nav \.decoracion \{([^}]*)\}", GENERAL).group(1)
    assert "position: relative" in regla and "margin: auto" in regla


def test_la_fila_de_indicadores_se_reparte_en_dos_filas_parejas(monkeypatch):
    salida = []
    monkeypatch.setattr(p.st, "markdown", lambda html, **_: salida.append(html))
    for n, mitad in ((6, 3), (4, 2), (5, 3), (1, 1)):
        p._fila("<div>grupo</div>", ["<div>k</div>"] * n)
        assert f"--mitad:{mitad}" in salida[-1] and 'class="fri-kpis fri-kpis-grupo"' in salida[-1]
