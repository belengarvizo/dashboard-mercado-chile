"""Valida que el IPoM (Informe de Política Monetaria del Banco Central) se
derive correctamente de las fechas de RPM, sin hardcodear las 4 fechas.

El BCCh publica el IPoM cuatro veces al año, la mañana siguiente (día
calendario) a la RPM de marzo, junio, septiembre y diciembre — las RPM
"ampliadas". calendario_economico.py lo deriva de _RPM_2026 para que no se
desincronice cuando se publique el calendario de RPM del año siguiente.
"""
import os
import sys
from datetime import date, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import calendario_economico as cal


def test_hay_un_ipom_por_cada_rpm_ampliada():
    ipom = [e for e in cal.EVENTOS_2026 if e.tipo == "IPoM"]
    rpm_ampliadas = [fin for _, fin in cal._RPM_2026 if fin.month in cal._MESES_RPM_AMPLIADA]

    assert len(rpm_ampliadas) == 4, f"deberia haber 4 RPM ampliadas en 2026, hay {len(rpm_ampliadas)}"
    assert len(ipom) == len(rpm_ampliadas), (
        f"deberia haber un IPoM por RPM ampliada ({len(rpm_ampliadas)}), hay {len(ipom)}"
    )


def test_cada_ipom_es_el_dia_siguiente_a_su_rpm_a_las_9():
    ipom_fechas = sorted(e.fecha_inicio for e in cal.EVENTOS_2026 if e.tipo == "IPoM")
    esperadas = sorted(
        fin + timedelta(days=1)
        for _, fin in cal._RPM_2026
        if fin.month in cal._MESES_RPM_AMPLIADA
    )
    assert ipom_fechas == esperadas, f"{ipom_fechas} != {esperadas}"

    for e in cal.EVENTOS_2026:
        if e.tipo == "IPoM":
            assert e.fecha_inicio == e.fecha_fin, "el IPoM es un evento de un solo día"
            assert e.hora == "09:00", f"el IPoM es a las 09:00 hora de Chile, no {e.hora!r}"
            assert e.confirmado is True


def test_ipom_de_septiembre_2026_es_el_9():
    # Verificado contra bcentral.cl: RPM el martes 08-09-2026, IPoM el
    # miércoles 09-09-2026 a las 09:00.
    ipom_sep = [
        e for e in cal.EVENTOS_2026
        if e.tipo == "IPoM" and e.fecha_inicio == date(2026, 9, 9)
    ]
    assert len(ipom_sep) == 1, "falta el IPoM del 09-09-2026 (evento puntual verificado con la fuente)"

    # y aparece en el calendario de los próximos 7 días si hoy es el 09
    prox = cal.proximos_eventos(date(2026, 9, 9), dias=7)
    assert any(e.tipo == "IPoM" and e.fecha_inicio == date(2026, 9, 9) for e in prox)


def test_ipom_tiene_indicador_visual_propio():
    ind = cal.INDICADOR_POR_TIPO.get("IPoM")
    assert ind is not None, "IPoM necesita entrada en INDICADOR_POR_TIPO (color/etiqueta)"
    assert ind["etiqueta"] == "IPoM"
    assert ind["organismo"] == "Banco Central de Chile"
    # color distinto de los demás tipos
    otros = {v["color"] for k, v in cal.INDICADOR_POR_TIPO.items() if k != "IPoM"}
    assert ind["color"] not in otros, "el IPoM no debería reusar el color de otro tipo"


if __name__ == "__main__":
    test_hay_un_ipom_por_cada_rpm_ampliada()
    test_cada_ipom_es_el_dia_siguiente_a_su_rpm_a_las_9()
    test_ipom_de_septiembre_2026_es_el_9()
    test_ipom_tiene_indicador_visual_propio()
    print("OK: las cuatro pruebas pasaron.")
