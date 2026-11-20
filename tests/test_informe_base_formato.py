"""I-7: formato de cifras del PDF (informe_base.num / pct). Un valor que a la precisión mostrada es cero se imprime sin
signo; todo lo demás conserva su signo y su precisión. Es solo presentación: el valor no se modifica."""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import informe_base as ib  # noqa: E402


@pytest.mark.parametrize("valor,decimales,con_signo,esperado", [
    # ceros a la precisión mostrada: sin signo, nunca «-0.00» ni «+0.00»
    (-0.0009, 2, True, "0.00"), (-0.0009, 2, False, "0.00"), (0.0004, 2, True, "0.00"),
    (0.0, 2, True, "0.00"), (-0.0, 2, False, "0.00"), (-0.0, 2, True, "0.00"),
    (-0.004999, 2, True, "0.00"), (-0.4, 0, True, "0"), (0.04, 1, True, "0.0"), (-1e-12, 4, True, "0.0000"),
    # justo sobre la mitad del último dígito: sí se ve distinto de cero y conserva su signo
    (-0.006, 2, True, "-0.01"), (0.006, 2, True, "+0.01"), (-0.6, 0, False, "-1"),
    # valores normales: sin cambios
    (2.4315, 2, False, "2.43"), (-1.555, 1, True, "-1.6"), (12345.678, 2, True, "+12,345.68"), (-3.0, 2, False, "-3.00"),
])
def test_num(valor, decimales, con_signo, esperado):
    assert ib.num(valor, decimales, con_signo) == esperado


@pytest.mark.parametrize("valor", [None, float("nan"), np.nan, pd.NA])
def test_sin_dato_sigue_siendo_raya(valor):
    assert ib.num(valor) == "—" and ib.pct(valor, 2, True) == "—"


def test_pct_hereda_la_regla_y_agrega_el_simbolo():
    assert ib.pct(-0.0009, 2, True) == "0.00%" and ib.pct(-0.012, 2, True) == "-0.01%" and ib.pct(4.0, 1) == "4.0%"


@pytest.mark.parametrize("valor", np.linspace(-0.02, 0.02, 401))
def test_la_regla_coincide_con_lo_que_se_ve(valor):
    """Solo cambia el signo cuando la cifra mostrada es cero; si no, el texto es exactamente el formato de siempre."""
    sin_regla = f"{valor:+,.2f}"
    texto = ib.num(valor, 2, True)
    if float(sin_regla) == 0:
        assert texto == "0.00"
    else:
        assert texto == sin_regla


def test_el_valor_no_se_modifica():
    valor = -0.0009
    ib.num(valor, 2, True)
    assert valor == -0.0009 and math.copysign(1, valor) == -1
