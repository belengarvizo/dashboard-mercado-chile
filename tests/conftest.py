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
import pytest
import streamlit as st


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
