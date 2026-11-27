# Interfaz FRI (etapas F0 y F1)

Capa de presentación sobre el dashboard existente: **no calcula nada ni duplica motores**. `fri.interfaz.navegar()`
devuelve el nombre de la sección clásica que corresponde a la pestaña elegida, y `app/dashboard.py` ejecuta ese mismo
bloque de siempre.

## Interruptor

| Variable | Valor | Resultado |
|---|---|---|
| `FRI_INTERFAZ` | sin definir o `clasica` (predeterminado) | Interfaz clásica, sin ningún cambio. `?ui=fri` no la activa. |
| `FRI_INTERFAZ` | `fri` | Interfaz FRI. `?ui=clasica` muestra la clásica y `?ui=fri` vuelve a FRI. |

La interfaz FRI necesita el tema oscuro de Streamlit, por ejemplo con `STREAMLIT_THEME_BASE=dark`. Las fotografías se
sirven desde `app/static/` (`.streamlit/config.toml`: `server.enableStaticServing = true`); su origen y licencia
(dominio público) están en `app/static/CREDITOS.md`.

## Dónde está cada sección existente

| FRI | Secciones clásicas |
|---|---|
| Macroeconomía → Panorama general | Indicadores macro |
| Mercados → Renta variable | Renta Variable y ETFs, Acciones IPSA, Atribución IPSA, Acciones Dow Jones, Benchmark |
| Mercados → Renta fija · Divisas · Materias primas | Renta Fija · FX y Carry Trade · Commodities |
| Riesgo y derivados → Análisis de riesgo · Derivados | Riesgo · Derivados |
| Solo en la interfaz clásica | Brief Premercado, Laboratorio Financiero, Modelo de Recesión EEUU |

Las demás pestañas muestran qué falta («PENDIENTE DE IMPLEMENTACIÓN»); nunca muestran cifras de relleno.

## Probar en local, sin producción

Las herramientas viven fuera del repositorio, en `%USERPROFILE%\FRI-local\`:
- `crear_base_sintetica.py`: crea una base SQLite con cifras inventadas.
- `fri_local.py`: lanzador con los guardias del proyecto activos (sin PostgreSQL ni red).
- `iniciar_fri.bat`: abre la interfaz FRI en http://127.0.0.1:8620.
- `iniciar_clasica.bat`: abre la interfaz clásica en http://127.0.0.1:8621.

## Panoramas e Informes (F2 y F3)

- Panoramas de Macroeconomía, Mercados y Riesgo: `fri/panoramas.py`. Usan los cargadores del dashboard
  (`cargar_series_macro`, `cargar_precios_acciones`) y funciones existentes (`calcular_cambio_reciente`,
  `retorno_ultimo_anio`, `curva_en_fecha`). Sin datos: «No disponible», nunca una cifra de relleno.
- Informes: `fri/informes.py`. Muestra el estado real del informe semanal (no implementado, fecha prevista no
  programada), el archivo vacío y el PDF especializado EXISTENTE de renta fija (no es el informe semanal).

## Limitaciones aceptadas de la primera versión (se muestran en pantalla)

| Pendiente | Cómo se ve hoy |
|---|---|
| IPSA diario y su volumen | «No disponible». No hay fuente diaria gratuita verificada: el BCCh publica solo la serie mensual (promedio de cierres); `^IPSA` no existe en Yahoo. ECH no se presenta como IPSA. Sin gráfico de volumen. |
| Actividad económica de China | «Sin fuente». |
| Investigador y Observatorio regulatorio | «Pendiente de implementación». |
| Informe dominical | «No implementado»; la fecha prevista no es una publicación programada. |
| Nuevos modelos de derivados | «Pendiente de implementación»; se usan los motores existentes. |
| Antigüedad de los datos | Cada cifra muestra su fecha real. Los panoramas no marcan datos atrasados (H3-D3 pendiente); las tablas de cada sección sí, con el calendario de su mercado (H3-D1) o una aproximación rotulada si no está verificado. |

## Pendiente de revisión (sin ampliar el uso actual)

- **Condiciones de uso de Yahoo Finance.** Sus términos (sección 2) restringen la recolección automatizada y el uso
  comercial sin permiso. El cron ya descarga precios de Yahoo: hay que revisar esas condiciones para el uso actual y
  no ampliar el uso de esa fuente mientras tanto (FRI no agrega tickers nuevos de Yahoo).

## Escala adaptable (F4-b)

El diseño aprobado se trazó para un ancho útil de unos 1672 px. Con el escalado de pantalla de Windows (125–150 %), una
pantalla de 1920×1080 se ve como 1536 o 1280 px de ancho útil aunque el zoom del navegador esté al 100 %. Además,
Streamlit recuerda en el navegador si alguna vez se cerró el menú lateral (`localStorage`, clave `stSidebarCollapsed-`).

El bloque «ESCALA ADAPTABLE» de `fri/estilos.py` hace cuatro cosas:
- **Menú lateral:** lo mantiene siempre visible.
- **Tamaños:** reduce en proporción tipografías, portada y tarjetas con `clamp()`. El máximo es el valor aprobado, así que a
  1672 px o más la interfaz queda idéntica a la maqueta.
- **Títulos e ilustraciones:** los títulos no se cortan en mitad de una palabra, y la ilustración de cada tarjeta ocupa su
  propio espacio.
- **Grillas:** las reorganiza solo cuando ya no caben. Las tarjetas de Inicio pasan a 3 columnas bajo 1200 px y a 2 bajo
  900 px; los indicadores se reparten en dos filas parejas.

Se verificó en 1366×768, 1920×1080, 2560×1440, 1536×864 (escala 1,25) y 1280×720 (escala 1,5), en las seis secciones, con
Streamlit 1.67.0 (la versión que instala Railway).
