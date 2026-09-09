"""Valida las horas de los eventos del calendario económico:

  - IPC (INE): 08:00 hrs. — verificado contra la fuente oficial del INE.
  - RPM (Banco Central): 18:00 hrs. — "el comunicado se publica a partir de
    las 18:00" (nota de prensa del Banco Central).
  - IPoM (Banco Central): 09:00 hrs.
  - IMACEC y OPEP+: sin hora oficial publicada -> campo `hora` vacío
    (no se inventa un valor).
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import calendario_economico as cal


def _por_tipo(tipo):
    return [e for e in cal.EVENTOS_2026 if e.tipo == tipo]


def test_ipc_todos_a_las_08_00():
    ipc = _por_tipo("IPC")
    assert ipc, "no hay eventos IPC"
    assert all(e.hora == "08:00" for e in ipc), [(str(e.fecha_inicio), e.hora) for e in ipc]


def test_rpm_todos_a_las_18_00():
    rpm = _por_tipo("RPM")
    assert rpm, "no hay eventos RPM"
    assert all(e.hora == "18:00" for e in rpm), [(str(e.fecha_inicio), e.hora) for e in rpm]


def test_ipom_todos_a_las_09_00():
    ipom = _por_tipo("IPoM")
    assert ipom
    assert all(e.hora == "09:00" for e in ipom)


def test_imacec_y_opep_sin_hora():
    for tipo in ("IMACEC", "OPEP+"):
        eventos = _por_tipo(tipo)
        assert eventos, f"no hay eventos {tipo}"
        assert all(e.hora == "" for e in eventos), (
            f"{tipo} no debería tener hora inventada: "
            + str([(str(e.fecha_inicio), e.hora) for e in eventos])
        )


if __name__ == "__main__":
    test_ipc_todos_a_las_08_00()
    test_rpm_todos_a_las_18_00()
    test_ipom_todos_a_las_09_00()
    test_imacec_y_opep_sin_hora()
    print("OK: las cuatro pruebas pasaron.")
