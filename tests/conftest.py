"""Aislamiento entre tests: cada uno arranca con las cachés de Streamlit vacías.

POR QUÉ EXISTE ESTE ARCHIVO
===========================
st.cache_data NO guarda sus entradas en el Runtime, sino en un global de
módulo: `_data_caches = DataCaches()` en
streamlit/runtime/caching/cache_data_api.py. Con el scope "global" que trae
por defecto, todas las entradas caen en el mismo diccionario de proceso.

AppTest.run() crea un Runtime simulado y un MemoryCacheStorageManager nuevos
en cada corrida, y al terminar deja Runtime._instance = None — pero nunca
toca `_data_caches`. Es decir: el storage manager nuevo ni se consulta, y
TODAS las instancias de AppTest de un mismo proceso de pytest comparten la
misma caché. Lo que cachea un test lo heredan los que corren después.

QUÉ ROMPÍA
==========
Fallos intermitentes que desaparecían al correr el test aislado (donde el
proceso arranca con la caché vacía). Dos observados y reproducidos:

  - test_defensa_topdown.py::test_yahoo_timeout_no_cuelga_la_pestana
    Verifica que el botón "Resolver predicciones vencidas" dispare una
    llamada nueva a Yahoo Finance: `assert len(llamadas) > n_antes`. Falló
    con `assert 1 > 1` — la llamada se sirvió de la caché de un test
    anterior en vez de ejecutarse, así que el contador no se movió.

  - test_heatmap_atraso.py::test_columna_atraso_ipsa_coincide_con_calculo_manual
    Compara la columna "Atraso" que renderiza el dashboard contra un cálculo
    hecho leyendo la base en vivo. Si un test anterior dejó cacheado
    cargar_precios_acciones() y entremedio el cron insertó los precios del
    día, el dashboard sirve la tabla vieja mientras el cálculo manual lee la
    nueva. Medido contra la base: ese salto mueve el texto de 28 de los 30
    tickers del IPSA a la vez (de "Precio congelado — N días hábiles" a
    "Al día"), porque Yahoo Finance refresca los .SN en un solo lote.

COSTO
=====
La suite se vuelve algo más lenta: al no compartir caché entre tests, varios
vuelven a leer la base. Es el precio correcto — una suite rápida que miente
no sirve de nada, y este tipo de fallo cuesta horas de diagnóstico cada vez
que aparece.
"""
import time

import pytest
import streamlit as st
from _pytest.runner import runtestprotocol

# ---------------------------------------------------------------------------
# Reintento de un test que ni siquiera llegó a correr por un corte de red
# ---------------------------------------------------------------------------
#
# Esta suite es de integración: casi todos los tests levantan el dashboard
# entero contra la base de Postgres en Railway, a la que se llega por un TCP
# proxy desde la máquina de desarrollo. Cuando la conexión de casa hipa un
# segundo, el test no "falla": nunca llega a probar nada, y aun así aparece en
# rojo con el nombre de la funcionalidad que iba a verificar.
#
# Eso no es teórico ni menor: durante la cacería de un test intermitente, un
# corte de red se confundió con evidencia y llevó a descartar la causa real
# (la caché heredada entre tests, ver arriba). Costó horas.
#
# QUÉ HACE Y QUÉ NO HACE. Reintenta UNA sola vez, y solo si el traceback trae
# una firma de error de conexión. Un assert que falla sigue siendo rojo a la
# primera: nunca se reintenta un fallo de lógica. Y como el reintento es uno
# solo y se anuncia en la salida, un problema de conexión sistemático (no un
# hipo) falla igual, en los dos intentos, y queda a la vista.

ESPERA_ANTES_DEL_REINTENTO_SEGUNDOS = 5

FIRMAS_DE_ERROR_DE_CONEXION = (
    "OperationalError",
    "server closed the connection",
    "connection to server at",
    "timeout expired",
    "could not connect to server",
    "SSL connection has been closed",
    "could not receive data from server",
)


def _firma_de_corte_de_red(reportes):
    """Devuelve la firma encontrada, o None si el fallo no es de conexión."""
    for reporte in reportes:
        if not reporte.failed or reporte.longrepr is None:
            continue
        texto = str(reporte.longrepr)
        for firma in FIRMAS_DE_ERROR_DE_CONEXION:
            if firma in texto:
                return firma
    return None


def pytest_runtest_protocol(item, nextitem):
    # Al reemplazar el protocolo por defecto hay que emitir logstart/logfinish
    # a mano: pytest los usa para abrir y cerrar el reporte de cada test.
    item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
    for intento in (1, 2):
        if intento > 1:
            # Reconstruye el request de fixtures para que el reintento arranque
            # limpio en vez de reusar las de la corrida que se cayó.
            if hasattr(item, "_initrequest"):
                item._initrequest()

        # Siempre se pasa el nextitem real. Pasar nextitem=item para "ahorrar"
        # el desarmado entre intentos parece una optimización, pero difiere el
        # teardown de TODOS los tests (no solo de los que se reintentan) y el
        # siguiente revienta con "previous item was not torn down properly".
        # Verificado: así fallaba la primera versión de este enganche.
        reportes = runtestprotocol(item, nextitem=nextitem, log=False)

        firma = _firma_de_corte_de_red(reportes)
        if firma is None or intento == 2:
            for reporte in reportes:
                item.ihook.pytest_runtest_logreport(report=reporte)
            break

        print(
            f"\n  [conexión] {item.nodeid}\n"
            f"             falló por red ({firma!r}), no por una aserción.\n"
            f"             Reintento único en {ESPERA_ANTES_DEL_REINTENTO_SEGUNDOS}s.",
            flush=True,
        )
        time.sleep(ESPERA_ANTES_DEL_REINTENTO_SEGUNDOS)
    item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
    return True


@pytest.fixture(autouse=True)
def cache_de_streamlit_limpia():
    """Vacía las cachés de Streamlit antes y después de CADA test.

    Antes, para que el test no herede lo que dejó el anterior. Después, para
    no dejar entradas vivas apuntando a datos que ya cambiaron.
    """
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()
