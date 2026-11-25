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
