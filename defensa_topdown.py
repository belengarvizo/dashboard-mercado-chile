"""Lógica pura del módulo "Defensa Top-Down" del dashboard (Simulación Mesa
de Dinero) que conviene poder testear sin levantar Streamlit ni tocar la BD.

La UI, los gráficos, las llamadas a Yahoo Finance y a Gemini viven en
app/dashboard.py; acá solo va la verificación de las predicciones, que es
una función pura: recibe el precio YA obtenido (el cierre histórico de la
fecha objetivo, o uno simulado en los tests) y decide el veredicto de
calibración.

Regla de resolución (ver app/dashboard.py):
  - una predicción se evalúa UNA sola vez, cuando vence el plazo, contra el
    precio de su fecha objetivo — NO contra el precio en vivo de hoy;
  - el resultado se congela en la BD y no se vuelve a recalcular.

Veredicto de calibración (el objetivo es entrenar calibración, no solo
adivinar la dirección):
  - "acierto"        -> el error de magnitud está dentro de ±TOLERANCIA_PP
                        del valor predicho (verde);
  - "mal_calibrado"  -> la dirección es correcta pero el error de magnitud
                        supera la tolerancia (amarillo) — p. ej. predijo +2 %
                        y el resultado real fue +40 %;
  - "fallo"          -> la dirección real es la contraria a la predicha (rojo);
  - "pendiente"      -> todavía no vence el plazo;
  - "sin_datos"      -> venció pero falta el precio de verificación o el
                        precio base.
"""

import pandas as pd

TOLERANCIA_PP = 3.0  # ±3 puntos porcentuales de error de magnitud = "acierto"


def _variacion_predicha_pct(pred: dict) -> float | None:
    """El % de variación que implica la predicción, para poder compararlo en
    la misma unidad (pp) con la variación real. Necesita precio_base."""
    base = pred.get("precio_base")
    objetivo = float(pred["valor_objetivo"])
    if pred["tipo"] == "pct":
        return objetivo
    if base in (None, 0):
        return None
    return (objetivo / float(base) - 1) * 100  # target price -> % implícito vs. base


def verificar_prediccion(pred: dict, precio_en_fecha_objetivo, hoy=None) -> dict:
    """Compara una predicción contra el precio del ticker EN SU FECHA OBJETIVO.

    `pred` trae al menos: fecha_hecha, horizonte_dias, tipo ("pct" | "target"),
    valor_objetivo y (para medir calibración) precio_base.
    `precio_en_fecha_objetivo` es el cierre histórico de la fecha objetivo
    (fecha_hecha + horizonte_dias), o del día hábil previo más cercano — NO el
    precio de hoy. En los tests se pasa un valor simulado.

    Devuelve {estado, detalle, error_pp} con estado ∈
    {"pendiente", "sin_datos", "acierto", "mal_calibrado", "fallo"}.
    """
    hoy = pd.Timestamp(hoy) if hoy is not None else pd.Timestamp.now()
    hecha = pd.Timestamp(pred["fecha_hecha"])
    vence = hecha + pd.Timedelta(days=int(pred["horizonte_dias"]))
    if hoy < vence:
        dias = (vence - hoy).days
        return {"estado": "pendiente", "error_pp": None,
                "detalle": f"vence el {vence.strftime('%Y-%m-%d')} (faltan {dias} día(s))"}

    if precio_en_fecha_objetivo is None:
        return {"estado": "sin_datos", "error_pp": None,
                "detalle": "Yahoo Finance no devolvió el precio de la fecha objetivo para este ticker"}

    base = pred.get("precio_base")
    if base in (None, 0):
        return {"estado": "sin_datos", "error_pp": None,
                "detalle": "sin precio base al registrar la predicción no se puede medir la calibración"}

    predicho_pct = _variacion_predicha_pct(pred)
    if predicho_pct is None:
        return {"estado": "sin_datos", "error_pp": None,
                "detalle": "no se pudo derivar la variación predicha"}

    real_pct = (float(precio_en_fecha_objetivo) / float(base) - 1) * 100
    error_pp = real_pct - predicho_pct
    detalle = (f"predijo {predicho_pct:+.1f} %, real {real_pct:+.1f} % "
               f"(dif {error_pp:+.1f} pp; de {float(base):.2f} a {float(precio_en_fecha_objetivo):.2f})")

    if abs(error_pp) <= TOLERANCIA_PP:
        return {"estado": "acierto", "error_pp": error_pp, "detalle": detalle}

    # Fuera de tolerancia: ¿al menos acertó la dirección?
    # (si la predicción era ~plana, cualquier magnitud real cuenta como mal calibrado, no como fallo)
    if abs(predicho_pct) < 1e-9:
        direccion_ok = True
    else:
        direccion_ok = (real_pct > 0) == (predicho_pct > 0) and real_pct != 0
    if direccion_ok:
        return {"estado": "mal_calibrado", "error_pp": error_pp,
                "detalle": detalle + " — dirección correcta, magnitud mal calibrada"}
    return {"estado": "fallo", "error_pp": error_pp,
            "detalle": detalle + " — dirección equivocada"}
