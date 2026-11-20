"""
Regla única para escribir una cifra en pantalla, en los tooltips y en los PDF (I-7, H2).

Un valor que, a la precisión mostrada, se lee como cero se escribe sin signo: «0.00», no «-0.00» ni «+0.00». El signo
de algo que se lee como cero no informa nada y sugiere una dirección que la cifra mostrada no tiene. Cualquier otro
valor se escribe exactamente como con el formato de Python de siempre.

Solo es presentación: devuelve texto y nunca cambia el valor que se calcula, se compara o se guarda. No decide qué
hacer con un dato faltante (None o NaN): eso lo resuelve quien llama, como antes (informe_base.num escribe «—»).
Sin dependencias, para que la puedan usar los glosarios y las pantallas sin cargar nada más.
"""
from __future__ import annotations


def cifra(valor: float, decimales: int = 2, con_signo: bool = False, miles: bool = True) -> str:
    """`valor` con `decimales` decimales; con `con_signo`, los positivos llevan «+»; con `miles`, coma de miles.

    Equivale a f"{valor:{'+' if con_signo else ''}{',' if miles else ''}.{decimales}f}", salvo que lo que se lee como
    cero va sin signo. Un NaN o un infinito se escriben como lo haría ese mismo formato («nan», «inf»)."""
    separador = "," if miles else ""
    if float(f"{abs(valor):.{decimales}f}") == 0:
        return f"{0.0:{separador}.{decimales}f}"
    return f"{valor:{'+' if con_signo else ''}{separador}.{decimales}f}"
