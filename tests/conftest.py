"""Aislamiento entre tests: base de datos y red protegidas, y cachés de Streamlit vacías.

La protección contra la base de producción vive en _guardia_bd.py y la de servicios externos en _guardia_red.py
(_guardia_bd la instala; se importa primero, aquí y en cada archivo de prueba). Este archivo agrega el registro de
pruebas de integración, la omisión de las pruebas externas, la contabilidad de red por prueba (más abajo) y la
limpieza de cachés.

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
import _guardia_bd  # noqa: F401  (debe ir primero: protege la base de producción)

import contextlib
import sys
import time
from pathlib import Path

import pytest
import streamlit as st
from _pytest.runner import runtestprotocol

_guardia_red = sys.modules["_guardia_red"]  # lo instaló _guardia_bd, en la línea de arriba de todo

# ---------------------------------------------------------------------------
# Pruebas de integración: se saltan mientras no haya base de pruebas local
# ---------------------------------------------------------------------------
#
# Estas pruebas necesitan una base de datos (leen o escriben, directamente o
# levantando el dashboard con AppTest). Antes corrían contra producción; ahora
# se saltan hasta que exista una base PostgreSQL local con datos sintéticos
# autorizada por el guardia. Si alguien las fuerza igual (por ejemplo con
# --noconftest), el guardia bloquea la conexión antes de abrirla y fallan.
#
# Para cada archivo: el motivo, y las pruebas de ese archivo que NO necesitan
# base y por lo tanto siguen corriendo. Una prueba nueva en estos archivos se
# salta por defecto; en cualquier otro archivo corre, y si intentara
# conectarse, el guardia la haría fallar a la vista.

TODAS_NECESITAN_BASE = frozenset()

ARCHIVOS_DE_INTEGRACION = {
    "test_atribucion_ipsa.py": ("lee precios reales de la base", TODAS_NECESITAN_BASE),
    "test_glosario_tooltips.py": ("levanta el dashboard con AppTest", TODAS_NECESITAN_BASE),
    "test_guardar_historico_tolerancia.py": ("escribe y borra filas en precios_acciones", TODAS_NECESITAN_BASE),
    "test_heatmap_atraso.py": ("levanta el dashboard y lee precios de la base", TODAS_NECESITAN_BASE),
    "test_labfin_view.py": ("levanta el dashboard con AppTest", TODAS_NECESITAN_BASE),
    "test_divisas_formulario_hora.py": ("levanta el dashboard y lee el diario de trading", TODAS_NECESITAN_BASE),
    "test_banner_apagon.py": ("levanta el dashboard con AppTest", frozenset({
        "test_banner_apagon_se_dispara_con_datos_simulados_de_apagon",
        "test_banner_no_se_dispara_con_datos_frescos_simulados",
    })),
    "test_commodities_seccion.py": ("levanta el dashboard con datos de la base", frozenset({
        "test_sin_una_divergencia_grande_no_hay_mensaje",
        "test_justo_en_el_umbral_no_hay_mensaje_y_un_poco_mas_arriba_si",
        "test_una_divergencia_grande_dentro_de_la_ventana_del_arancel_cita_esa_causa",
        "test_una_divergencia_grande_fuera_de_la_ventana_del_arancel_no_inventa_una_causa",
        "test_justo_en_los_bordes_de_la_ventana_del_arancel",
        "test_una_fila_con_precio_viejo_se_marca_como_atrasada_y_una_fresca_no",
        "test_el_tramo_del_grafico_solo_mira_las_columnas_elegidas_y_no_las_demas",
    })),
    "test_defensa_topdown.py": ("levanta el dashboard y escribe predicciones", frozenset({
        "test_prediccion_pendiente",
        "test_acierto_dentro_de_tolerancia",
        "test_mal_calibrado_direccion_ok_magnitud_lejos",
        "test_fallo_solo_si_la_direccion_es_la_contraria",
        "test_prediccion_sin_datos",
        "test_16_preguntas_exactas_del_pdf",
        "test_sliders_defensa_sin_porcentaje_suelto_en_format",
    })),
    "test_derivados_seccion.py": ("levanta el dashboard y lee precios de la base", frozenset({
        "test_dias_al_vencimiento_nunca_es_negativo_para_una_fecha_pasada",
        "test_el_precio_de_mercado_es_el_punto_medio_entre_bid_y_ask_cuando_los_hay",
        "test_el_precio_de_mercado_usa_el_ultimo_transado_si_no_hay_bid_ni_ask",
    })),
    "test_divisas_seccion.py": ("levanta el dashboard y lee el diario de trading", frozenset({
        "test_la_seccion_conserva_su_lugar_entre_riesgo_y_benchmark",
        "test_el_limite_por_operacion_no_bloquea_nada",
        "test_el_aviso_de_stop_cerca_no_bloquea_nada",
        "test_la_tabla_de_atr_no_da_senales_ni_se_puede_editar",
        "test_el_bloque_del_atr_no_da_senales_ni_bloquea",
        "test_el_aviso_de_antimartingala_no_bloquea_nada",
        "test_la_comprobacion_de_lotes_no_bloquea_el_guardado",
        "test_el_aviso_del_stop_no_bloquea_ni_da_senales",
        "test_el_atr_se_guarda_con_la_operacion",
        "test_el_sql_filtra_las_eliminadas_en_la_consulta_y_no_en_pandas",
        "test_editar_avisa_del_desajuste_de_lotes_igual_que_al_crear",
        "test_editar_eliminar_y_restaurar_exigen_una_sola_fila",
        "test_las_sentencias_del_diario_usan_parametros_y_no_texto_armado",
        "test_el_bloque_de_correlacion_avisa_y_no_bloquea",
        "test_el_bloque_de_correlacion_va_despues_de_la_puerta",
    })),
    "test_fx_carry_seccion.py": ("levanta el dashboard con datos de la base", frozenset({
        "test_la_columna_carry_sobre_riesgo_es_la_del_motor_y_no_se_recalcula_con_otra_volatilidad",
        "test_las_columnas_de_spot_carry_y_total_tambien_son_las_del_motor",
    })),
    "test_generar_brief_errores.py": ("escribe y borra filas en errores_actualizacion", frozenset({
        "test_clasificacion_por_tipo_de_error",
        "test_texto_de_respuesta_bloqueada_lanza_briefbloqueado",
        "test_reintenta_solo_transitorios",
        "test_prueba_modelos_de_respaldo_si_el_principal_agota_reintentos",
        "test_espera_sugerida_solo_cuando_la_api_la_indica",
        "test_limite_por_minuto_espera_lo_que_pide_la_api_y_reintenta_igual_modelo",
        "test_cuota_diaria_sigue_sin_reintentarse",
        "test_si_el_modelo_sigue_limitado_pasa_al_siguiente",
        "test_el_tiempo_total_dormido_nunca_supera_el_presupuesto",
        "test_el_watchdog_del_paso_brief_deja_lugar_a_las_esperas",
    })),
    "test_informe_renta_fija.py": ("algunas pruebas generan el informe con datos de la base", frozenset({
        "test_la_duracion_medida_recupera_la_que_se_uso_para_construir_los_precios",
        "test_lo_explicado_por_la_duracion_es_exactamente_menos_duracion_por_el_cambio_de_tasa",
        "test_el_resto_es_exactamente_el_retorno_real_menos_lo_explicado",
        "test_el_retorno_del_periodo_se_mide_entre_las_puntas_del_periodo",
        "test_el_cambio_de_tasa_es_el_de_la_tasa_de_referencia_de_cada_etf",
        "test_con_la_curva_al_alza_lo_explicado_es_negativo_y_mas_para_el_plazo_largo",
        "test_con_la_curva_a_la_baja_se_invierte_el_signo",
        "test_la_curva_del_informe_son_las_dos_puntas_del_periodo",
        "test_sin_historia_suficiente_no_se_inventa_un_periodo",
        "test_la_frase_del_cupon_solo_aparece_cuando_los_datos_la_sostienen",
        "test_sin_datos_el_informe_lo_dice_en_vez_de_mostrar_cifras_de_ejemplo",
        "test_el_markdown_del_pdf_convierte_negrita_cursiva_y_escapa_el_html",
        "test_los_numeros_sin_dato_salen_como_guion_y_nunca_como_cero",
        "test_una_nota_no_se_parte_entre_paginas_pero_no_se_anida_dentro_de_otro_bloque",
    })),
    "test_key_indicators_frescura.py": ("dos pruebas levantan el dashboard con AppTest", frozenset({
        "test_diaria_fresca_muestra_badge_y_diaria_atrasada_lo_oculta",
        "test_umbral_de_un_dia_habil",
        "test_mensuales_siempre_muestran_badge_aunque_tengan_meses_de_atraso",
        "test_delta_sin_direccion_cuando_el_cambio_mostrado_es_0",
    })),
    "test_renta_fija_seccion.py": ("levanta el dashboard con datos de la base", frozenset({
        "test_los_nombres_de_series_coinciden_con_los_del_script_de_descarga",
        "test_un_hueco_corta_la_linea_en_vez_de_unir_los_bordes",
        "test_fines_de_semana_y_feriados_no_son_huecos",
        "test_el_umbral_del_hueco_es_estricto",
    })),
    "test_renta_variable_seccion.py": ("levanta el dashboard con datos de la base", frozenset({
        "test_dos_puntos_casi_iguales_ponen_su_etiqueta_uno_arriba_y_el_otro_abajo",
        "test_un_punto_en_el_borde_no_pone_su_etiqueta_hacia_afuera_del_grafico",
        "test_cada_punto_recibe_una_posicion_valida_y_los_casos_degenerados_no_rompen",
        "test_los_puntos_sin_etiqueta_no_reciben_posicion_pero_siguen_siendo_obstaculos",
    })),
    "test_trading_acceso.py": ("levanta el dashboard con AppTest", frozenset({
        "test_sin_variable_configurada_no_entra_ni_con_cadena_vacia",
        "test_una_variable_vacia_cuenta_como_no_configurada",
        "test_la_contrasena_correcta_entra_y_la_incorrecta_no",
        "test_el_motivo_nunca_revela_la_contrasena",
        "test_el_limite_de_intentos_es_del_servidor_y_no_de_la_sesion",
        "test_el_bloqueo_se_levanta_solo_al_pasar_el_tiempo",
        "test_un_acierto_reinicia_el_contador",
        "test_el_titulo_de_defensa_no_tiene_emoji",
    })),
    "test_trading_fx.py": ("una prueba levanta el dashboard con AppTest", frozenset({
        "test_separa_las_divisas_del_par",
        "test_el_ticket_de_eurusd_implica_una_tasa_coherente_con_el_banco_central",
        "test_valor_de_posicion_usa_la_divisa_base",
        "test_pip_de_un_par_que_cotiza_en_usd",
        "test_pip_encadenado_cuando_la_cotizacion_no_es_usd",
        "test_se_niega_cuando_el_pip_esta_pendiente",
        "test_se_niega_cuando_falta_la_tasa_de_conversion",
        "test_la_tasa_manual_pisa_la_de_la_base",
        "test_avisa_cuando_la_tasa_de_la_base_esta_vieja",
        "test_marca_como_supuesto_el_contrato_de_los_pares_no_verificados",
        "test_lotes_para_un_riesgo_dado",
        "test_lotes_rechaza_un_stop_invalido",
        "test_la_cadena_a_clp_queda_documentada_paso_a_paso",
    })),
    "test_trading_zona_horaria.py": ("inserta filas en trading_operaciones", frozenset({
        "test_el_desfase_nueva_york_chile_cambia_el_1_de_noviembre",
    })),
}

# Archivos que mencionan la base pero verificadamente no se conectan.
ARCHIVOS_SIN_CONEXION_VERIFICADOS = {
    "test_models_get_engine.py": "crea motores con create_engine, que no conecta hasta la primera consulta",
}


def pytest_collection_modifyitems(config, items):
    _omitir_externas_sin_autorizacion(items)
    if _guardia_bd.base_de_pruebas_autorizada() is not None:
        return
    for item in items:
        archivo = Path(str(item.fspath)).name
        registro = ARCHIVOS_DE_INTEGRACION.get(archivo)
        if registro is None:
            continue
        motivo, pueden_correr = registro
        nombre = getattr(item, "originalname", None) or item.name
        if nombre not in pueden_correr:
            item.add_marker(pytest.mark.skip(
                reason=f"Integración ({motivo}): requiere la base PostgreSQL local de pruebas, aún no configurada."
            ))


# ---------------------------------------------------------------------------
# Pruebas con servicios externos (P-1): offline por defecto
# ---------------------------------------------------------------------------
#
# Las marcas están declaradas en pytest.ini (con --strict-markers, una marca mal escrita falla):
#   externa                    necesita servicios externos reales; se omite salvo FRI_PRUEBAS_EXTERNAS=1, una
#                              autorización SEPARADA de FRI_PRUEBAS_POSTGRES.
#   simulada                   usa conexiones o servicios simulados (mocks, destinos ficticios).
#   integracion_bd             necesita la base local de pruebas (quien decide si corre es el registro de arriba).
#   intentos_de_red_esperados  provoca a propósito intentos de red bloqueados: solo las pruebas del guardia de red.
# Sin marca, una prueba es offline. La protección NO depende de las marcas: el guardia de red bloquea igual, y
# _guardia_de_red_por_prueba deja en rojo a la prueba que intente salir sin estar marcada 'externa'.

def _omitir_externas_sin_autorizacion(items):
    if _guardia_red.externas_autorizadas():
        return
    for item in items:
        if item.get_closest_marker("externa") is not None:
            item.add_marker(pytest.mark.skip(
                reason="Externa: necesita servicios externos reales; se ejecuta solo con FRI_PRUEBAS_EXTERNAS=1."
            ))


def motivo_de_falla_por_red(intentos, marcada_externa, intentos_esperados):
    """None si la prueba está en regla; si no, el motivo para dejarla en rojo. Un intento cuenta aunque el código lo
    haya capturado: el dashboard degrada a «sin datos» ante cualquier excepción, y eso escondería la conexión."""
    if not intentos or marcada_externa or intentos_esperados:
        return None
    detalle = ", ".join(sorted({f"{i['capa']} -> {i['destino']}" for i in intentos}))
    return (
        f"La prueba intentó {len(intentos)} conexión(es) a servicios externos sin estar marcada 'externa' ({detalle}). "
        "El guardia de red las bloqueó; aunque el código haya capturado la excepción, la prueba queda en rojo. "
        "Usa datos simulados, o márcala 'externa' (se ejecutará solo con FRI_PRUEBAS_EXTERNAS=1)."
    )


@pytest.fixture(autouse=True)
def _guardia_de_red_por_prueba(request):
    externa = request.node.get_closest_marker("externa") is not None
    esperados = request.node.get_closest_marker("intentos_de_red_esperados") is not None
    marca = _guardia_red.instantanea()
    with (_guardia_red.prueba_externa() if externa else contextlib.nullcontext()):
        yield
    motivo = motivo_de_falla_por_red(_guardia_red.intentos_desde(marca), externa, esperados)
    if motivo:
        pytest.fail(motivo, pytrace=False)

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
