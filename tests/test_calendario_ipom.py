"""Valida que el IPoM (Informe de Política Monetaria del Banco Central) se
derive correctamente de las fechas de RPM, sin hardcodear las 4 fechas.

El BCCh publica el IPoM cuatro veces al año, la mañana siguiente a una RPM
"ampliada". calendario_economico.py lo deriva de las listas de RPM para que
no se desincronice al cargar un año nuevo.

POR QUÉ ESTE TEST CONTRASTA CONTRA FECHAS OFICIALES. La regla original
identificaba la RPM ampliada por su MES ({3, 6, 9, 12}). Funcionaba para
2026 y se rompe en 2027: ese año la reunión previa al IPoM de septiembre es
el 31 de AGOSTO, así que la regla por mes perdía ese IPoM por completo y el
calendario se habría quedado con 3 en vez de 4, en silencio. La regla
correcta es posicional (una de cada dos reuniones). Para que un año futuro
que rompa también ese patrón se note, acá se comparan las fechas DERIVADAS
contra las que el propio Banco Central publica.
"""
import os
import sys
from datetime import date, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import calendario_economico as cal

# Fechas de "Monetary Policy Reports" tal como las publica el BCCh en
# bcentral.cl/en/news-and-publications/press/monetary-and-financial-policy-calendar
# (leídas de la fuente el 01-10-2026). Al agregar un año nuevo al módulo hay
# que agregarlo también acá, con las fechas de la fuente.
IPOM_OFICIAL_POR_ANIO = {
    2026: [date(2026, 3, 25), date(2026, 6, 17), date(2026, 9, 9), date(2026, 12, 16)],
    2027: [date(2027, 3, 31), date(2027, 6, 16), date(2027, 9, 1), date(2027, 12, 15)],
}


def _ipom_de(anio):
    return sorted(
        e.fecha_inicio for e in cal.EVENTOS
        if e.tipo == "IPoM" and e.fecha_inicio.year == anio
    )


def test_el_ipom_derivado_coincide_con_el_que_publica_el_banco_central():
    """El contraste que atrapa un cambio de patrón en el calendario del BCCh."""
    for anio, oficiales in IPOM_OFICIAL_POR_ANIO.items():
        derivadas = _ipom_de(anio)
        assert derivadas == sorted(oficiales), (
            f"{anio}: el IPoM derivado de las RPM no coincide con el publicado por el "
            f"Banco Central.\n  derivado: {[str(d) for d in derivadas]}\n"
            f"  oficial:  {[str(d) for d in sorted(oficiales)]}"
        )


def test_todos_los_anios_cargados_tienen_su_ipom_contrastado():
    """Si alguien carga un año de RPM pero se olvida de traer las fechas
    oficiales de IPoM, el contraste de arriba no lo cubriría y el error
    pasaría callado."""
    faltantes = set(cal.ANIOS_CARGADOS) - set(IPOM_OFICIAL_POR_ANIO)
    assert not faltantes, (
        f"estos años están cargados en calendario_economico pero no tienen fechas "
        f"oficiales de IPoM con las que contrastar: {sorted(faltantes)}"
    )


def test_hay_cuatro_ipom_por_anio():
    for anio in cal.ANIOS_CARGADOS:
        ipom = _ipom_de(anio)
        assert len(ipom) == 4, f"{anio} deberia tener 4 IPoM, tiene {len(ipom)}: {ipom}"


def test_cada_ipom_es_el_dia_siguiente_a_una_rpm():
    fines_de_rpm = {fin for rpm in cal._RPM_POR_ANIO.values() for _, fin in rpm}
    for e in cal.EVENTOS:
        if e.tipo != "IPoM":
            continue
        assert e.fecha_inicio - timedelta(days=1) in fines_de_rpm, (
            f"el IPoM del {e.fecha_inicio} no sigue a ninguna RPM"
        )
        assert e.fecha_inicio == e.fecha_fin, "el IPoM es un evento de un solo día"
        assert e.hora == "09:00", f"el IPoM es a las 09:00 hora de Chile, no {e.hora!r}"
        assert e.confirmado is True


def test_ipom_de_septiembre_2027_viene_de_la_rpm_de_agosto():
    """El caso concreto que rompía la regla vieja: en 2027 no hay RPM en
    septiembre, y el IPoM del 1 de septiembre sale de la RPM del 31 de
    agosto."""
    assert date(2027, 9, 1) in _ipom_de(2027), (
        "falta el IPoM del 01-09-2027, que es el que la regla por mes perdía"
    )
    assert not any(
        fin.month == 9 for _, fin in cal._RPM_POR_ANIO[2027]
    ), "si el BCCh agregó una RPM en septiembre 2027, revisar este test"


def test_ipom_de_septiembre_2026_es_el_9():
    # Verificado contra bcentral.cl: RPM el martes 08-09-2026, IPoM el
    # miércoles 09-09-2026 a las 09:00.
    assert date(2026, 9, 9) in _ipom_de(2026)
    prox = cal.proximos_eventos(date(2026, 9, 9), dias=7)
    assert any(e.tipo == "IPoM" and e.fecha_inicio == date(2026, 9, 9) for e in prox)


def test_ipom_tiene_indicador_visual_propio():
    ind = cal.INDICADOR_POR_TIPO.get("IPoM")
    assert ind is not None, "IPoM necesita entrada en INDICADOR_POR_TIPO (color/etiqueta)"
    assert ind["etiqueta"] == "IPoM"
    assert ind["organismo"] == "Banco Central de Chile"
    otros = {v["color"] for k, v in cal.INDICADOR_POR_TIPO.items() if k != "IPoM"}
    assert ind["color"] not in otros, "el IPoM no debería reusar el color de otro tipo"


if __name__ == "__main__":
    test_el_ipom_derivado_coincide_con_el_que_publica_el_banco_central()
    test_todos_los_anios_cargados_tienen_su_ipom_contrastado()
    test_hay_cuatro_ipom_por_anio()
    test_cada_ipom_es_el_dia_siguiente_a_una_rpm()
    test_ipom_de_septiembre_2027_viene_de_la_rpm_de_agosto()
    test_ipom_de_septiembre_2026_es_el_9()
    test_ipom_tiene_indicador_visual_propio()
    print("OK: las siete pruebas pasaron.")
