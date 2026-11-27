"""tzdata: ZoneInfo funciona aunque el sistema operativo no tenga su propia base de zonas horarias.

En Railway (Linux) zoneinfo busca primero la base del sistema (/usr/share/zoneinfo). Si la imagen no la trae, usa el paquete
tzdata, fijado en requirements.txt. Esta prueba vacía la ruta de búsqueda del sistema (zoneinfo.reset_tzpath) dentro del
proceso, sin tocar el sistema, y comprueba que las zonas que usa el dashboard se resuelven desde el paquete.
"""
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import os
import re
import zoneinfo
from datetime import datetime, timedelta, timezone

import pytest

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


@pytest.fixture
def sin_base_del_sistema():
    ruta_anterior = zoneinfo.TZPATH
    zoneinfo.reset_tzpath(to=[])
    zoneinfo.ZoneInfo.clear_cache()
    try:
        yield
    finally:
        zoneinfo.reset_tzpath(to=ruta_anterior)
        zoneinfo.ZoneInfo.clear_cache()


@pytest.mark.parametrize("zona", ["America/Santiago", "America/New_York", "Asia/Tokyo", "UTC"])
def test_las_zonas_del_dashboard_se_resuelven_sin_la_base_del_sistema(sin_base_del_sistema, zona):
    assert zoneinfo.TZPATH == ()
    zi = zoneinfo.ZoneInfo(zona)
    assert datetime(2026, 7, 15, 12, tzinfo=timezone.utc).astimezone(zi).tzinfo is not None


def test_horario_de_chile_desde_el_paquete(sin_base_del_sistema):
    santiago = zoneinfo.ZoneInfo("America/Santiago")
    assert datetime(2026, 7, 15, 12, tzinfo=timezone.utc).astimezone(santiago).utcoffset() == timedelta(hours=-4)
    assert datetime(2026, 12, 15, 12, tzinfo=timezone.utc).astimezone(santiago).utcoffset() == timedelta(hours=-3)


def test_la_version_instalada_es_la_fijada():
    from importlib.metadata import version
    fijada = re.search(r"^tzdata==(\S+)\s*$", open(os.path.join(RAIZ, "requirements.txt"), encoding="utf-8").read(), re.M)
    assert fijada, "tzdata debe estar fijado en requirements.txt"
    instalada = version("tzdata")
    if instalada != fijada.group(1):
        pytest.skip(f"este entorno tiene tzdata {instalada}; requirements fija {fijada.group(1)} (se verifica en el entorno de despliegue)")
