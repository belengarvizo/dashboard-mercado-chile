"""FRI — tokens del sistema de diseño y hoja de estilos de la interfaz FRI (FRI_INTERFAZ=fri).

Tokens de docs/FRI/FRI_DESIGN_SYSTEM.md (§2), ajustados a las capturas aprobadas: azul petróleo profundo con matices
teal, dorado apagado, serif para títulos y sans serif para datos. Fuentes del sistema (sin solicitudes a internet).
Las fotografías se sirven desde static/ (servidor local de Streamlit)."""

TOKENS = {
    "fondo": "#0B1F2A",
    "fondo_profundo": "#081821",
    "superficie": "#0E2833",
    "superficie_2": "#11303C",
    "superficie_destacada": "#16394A",
    "dorado": "#C9AB74",
    "dorado_suave": "#A88E5E",
    "texto": "#F3EFE6",
    "texto_2": "#C2D2DA",
    "texto_3": "#97AEB9",
    "borde": "#1C3D4B",
    "borde_fuerte": "#2A4E5D",
    "positivo": "#7FC09E",
    "negativo": "#E39A9A",
    "azul_dato": "#6FB3D2",
    "teal": "#3E8F95",
}

SERIF = "Georgia, Cambria, 'Times New Roman', serif"
SANS = "'Segoe UI', Calibri, system-ui, -apple-system, sans-serif"
T = TOKENS

FOTO_PORTADA = "app/static/cordillera_portada.jpg"
FOTO_CABECERA = "app/static/cordillera_cabecera.jpg"
FOTO_FOCO = "app/static/cordillera_foco.jpg"

CSS = f"""
<style>
html, body, [data-testid="stAppViewContainer"], .stApp {{
  background: radial-gradient(120% 80% at 70% 0%, #0F2A36 0%, {T['fondo']} 45%, #091A23 100%) !important;
  background-color: {T['fondo']} !important; color: {T['texto']}; font-family: {SANS};
}}
[data-testid="stHeader"] {{ background: transparent; height: 0; }}
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {{ display: none !important; }}
.block-container {{ padding: 0 2.2rem 2.5rem 2.2rem !important; max-width: 1640px; }}

/* ---------- Menú lateral (idéntico en todas las secciones) ---------- */
[data-testid="stSidebar"] {{ background: linear-gradient(180deg, #0A1D27 0%, {T['fondo_profundo']} 100%) !important; border-right: 1px solid {T['borde']};
  min-width: 248px !important; max-width: 248px !important; }}
[data-testid="stSidebar"] > div:first-child {{ padding-top: 0; }}
[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarHeader"] {{ display: none !important; }}
.fri-marca {{ text-align: center; padding: 30px 12px 16px 12px; }}
.fri-marca .logo {{ font-family: {SERIF}; font-size: 40px; color: {T['texto']}; display: flex; align-items: center; justify-content: center; gap: 10px; }}
.fri-marca .nombre {{ font-family: {SERIF}; font-size: 17.5px; color: {T['texto']}; line-height: 1.25; margin-top: 6px; }}
.fri-marca .filete {{ width: 130px; height: 1px; margin: 14px auto; background: linear-gradient(90deg, transparent, {T['dorado']}, transparent); }}
.fri-marca .lema {{ font-family: {SERIF}; font-style: italic; font-size: 15px; color: {T['texto_2']}; line-height: 1.35; }}
.fri-nav {{ margin-top: 16px; display: flex; flex-direction: column; gap: 2px; }}
.fri-nav a {{ display: flex; align-items: center; gap: 14px; padding: 13px 22px; white-space: nowrap; color: {T['texto_2']} !important;
  text-decoration: none !important; font-size: 15.5px; border-left: 3px solid transparent; }}
.fri-nav a svg {{ flex: none; width: 21px; height: 21px; }}
.fri-nav a:hover {{ background: rgba(201,171,116,0.06); color: {T['texto']} !important; }}
.fri-nav a.activo {{ border-left-color: {T['dorado']}; color: {T['texto']} !important; background: linear-gradient(90deg, rgba(201,171,116,0.16), rgba(201,171,116,0.02)); }}
.fri-pie-menu {{ position: fixed; left: 0; bottom: 0; width: 247px; height: 130px; text-align: center; color: {T['texto_2']}; font-family: {SERIF}; font-size: 17px;
  padding-top: 64px; background: linear-gradient(180deg, rgba(8,24,33,1) 0%, rgba(8,24,33,.62) 45%, rgba(8,24,33,.92) 100%),
  url('{FOTO_FOCO}') center 30%/cover; }}
.fri-pie-menu small {{ display: block; font-family: {SANS}; font-size: 12.5px; color: {T['texto_3']}; }}

/* ---------- Barra superior (idéntica en las secciones interiores) ---------- */
.fri-barra {{ display: flex; align-items: center; justify-content: space-between; padding: 14px 0 12px 0; border-bottom: 1px solid {T['borde']}; }}
.fri-barra .titulo {{ display: flex; align-items: center; gap: 14px; font-family: {SERIF}; font-size: 22px; color: {T['texto']}; }}
.fri-barra .sep {{ width: 1px; height: 22px; background: {T['borde_fuerte']}; }}
.fri-barra .sub {{ font-family: {SANS}; font-size: 14.5px; color: {T['texto_2']}; }}
.fri-barra .acciones {{ display: flex; align-items: center; gap: 18px; }}
.fri-control-pendiente {{ border: 1px dashed {T['dorado_suave']}; color: {T['texto_3']}; border-radius: 6px; padding: 6px 14px; font-size: 14px;
  display: flex; gap: 8px; align-items: center; cursor: not-allowed; opacity: .8; }}
.fri-control-pendiente em {{ font-style: normal; font-size: 11px; letter-spacing: 1px; color: {T['dorado_suave']}; border-left: 1px solid {T['borde_fuerte']}; padding-left: 8px; }}
.fri-icono-inactivo {{ opacity: .45; cursor: not-allowed; display: inline-flex; }}

/* ---------- Cabecera de páginas interiores (más baja, con fotografía) ---------- */
.fri-encabezado {{ position: relative; height: 112px; margin: 0 -2.2rem 14px -2.2rem; overflow: hidden;
  background: linear-gradient(90deg, {T['fondo']} 0%, rgba(11,31,42,.92) 30%, rgba(11,31,42,.25) 62%, rgba(11,31,42,0) 80%),
              linear-gradient(0deg, {T['fondo']} 0%, rgba(11,31,42,0) 45%), url('{FOTO_CABECERA}') right 38%/cover no-repeat; }}
.fri-encabezado .texto {{ position: absolute; left: 2.2rem; top: 18px; display: flex; gap: 16px; align-items: flex-start; }}
.fri-encabezado .h1 {{ font-family: {SERIF}; font-size: 40px; font-weight: 600; color: {T['texto']}; line-height: 1.05; }}
.fri-encabezado p {{ color: {T['texto_2']}; margin: 6px 0 0 0; font-size: 16px; }}
.fri-encabezado .meta {{ position: absolute; right: 2.2rem; top: 22px; text-align: right; color: {T['texto']}; font-size: 13.5px; line-height: 1.5;
  display: flex; gap: 10px; align-items: flex-start; background: rgba(8,24,33,0.72); padding: 8px 12px; border-radius: 6px; }}

/* ---------- Portada ---------- */
.fri-portada {{ position: relative; height: 420px; margin: 0 -2.2rem 0 -2.2rem;
  background: linear-gradient(90deg, {T['fondo']} 0%, rgba(11,31,42,.94) 24%, rgba(11,31,42,.45) 50%, rgba(11,31,42,0) 72%),
              linear-gradient(0deg, {T['fondo']} 0%, rgba(11,31,42,0) 32%), url('{FOTO_PORTADA}') right 30%/cover no-repeat; }}
.fri-portada .contenido {{ position: absolute; left: 4.2rem; top: 36px; max-width: 660px; }}
.fri-portada .ruta {{ font-size: 13px; letter-spacing: 3px; color: {T['dorado']}; display: flex; align-items: center; gap: 14px; }}
.fri-portada .ruta span.linea {{ display: inline-block; width: 420px; height: 1px; background: linear-gradient(90deg, {T['dorado']}, transparent); }}
.fri-portada .h1 {{ font-family: {SERIF}; font-size: 64px; line-height: 1.04; color: {T['texto']}; margin: 26px 0 12px 0; font-weight: 600; }}
.fri-portada .subtitulo {{ font-family: {SERIF}; font-style: italic; font-size: 28px; color: {T['dorado']}; margin-bottom: 14px; }}
.fri-portada .bajada {{ font-size: 17.5px; color: {T['texto']}; line-height: 1.5; max-width: 540px; }}
.fri-portada .fecha {{ position: absolute; right: 2.2rem; top: 28px; color: {T['texto']}; font-size: 14.5px; display: flex; gap: 16px; align-items: center;
  background: rgba(8,24,33,0.55); padding: 8px 14px; border-radius: 6px; }}

.fri-tarjetas {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 18px; margin-top: -36px; position: relative; z-index: 2; }}
.fri-tarjeta-nav {{ position: relative; overflow: hidden; min-height: 300px; background: linear-gradient(180deg, rgba(17,48,60,0.96) 0%, rgba(13,38,49,0.96) 100%);
  border: 1px solid {T['borde']}; border-radius: 10px; padding: 24px 22px 20px 22px; min-height: 290px; display: flex; flex-direction: column; }}
.fri-tarjeta-nav .h3 {{ font-family: {SERIF}; font-size: 25px; color: {T['texto']}; margin: 14px 0 8px 0; font-weight: 500; }}
.fri-tarjeta-nav p {{ color: {T['texto_2']}; font-size: 15px; line-height: 1.45; margin: 0; position: relative; z-index: 1; }}
.fri-tarjeta-nav .decoracion {{ position: absolute; left: 0; right: 0; bottom: 40px; height: 64px; opacity: .5; pointer-events: none; }}
.fri-tarjeta-nav a {{ margin-top: auto; position: relative; z-index: 1; color: {T['dorado']} !important; text-decoration: none !important; font-size: 14.5px; display: flex; gap: 10px; align-items: center; }}

.fri-foco {{ margin-top: 20px; display: grid; grid-template-columns: 190px 1fr 340px; gap: 28px; align-items: center; background: {T['superficie']}; border: 1px solid {T['borde']}; border-radius: 10px; padding: 22px 26px; }}
.fri-foco .imagen {{ height: 124px; border-radius: 6px; background: url('{FOTO_FOCO}') center/cover; border: 1px solid {T['borde']}; }}
.fri-foco .etiqueta {{ color: {T['dorado']}; font-size: 13px; letter-spacing: 2px; font-weight: 600; }}
.fri-foco .h3 {{ font-family: {SERIF}; font-size: 25px; color: {T['texto']}; margin: 6px 0; font-weight: 500; }}
.fri-foco p {{ color: {T['texto_2']}; font-size: 15px; margin: 0 0 12px 0; line-height: 1.5; }}
.fri-foco .proximo {{ border-left: 1px solid {T['borde_fuerte']}; padding-left: 28px; }}
.fri-foco .proximo .etiqueta {{ display: flex; gap: 10px; align-items: center; }}
.fri-foco .proximo b {{ display: block; color: {T['texto']}; font-size: 16.5px; font-weight: 600; margin: 12px 0 4px 0; }}
.fri-foco .proximo span {{ color: {T['texto_2']}; font-size: 14.5px; }}

/* ---------- Pestañas (st.tabs) ---------- */
[role="tablist"] {{ gap: 0 !important; border: 1px solid {T['borde']}; border-radius: 8px; width: fit-content; padding: 3px; background: {T['superficie']}; }}
[data-testid="stTab"] {{ padding: 8px 26px !important; border-radius: 6px; margin: 0 !important; }}
[data-testid="stTab"] p {{ font-size: 15px !important; color: {T['texto_2']}; }}
[data-testid="stTab"][aria-selected="true"] {{ background: rgba(201,171,116,0.18); box-shadow: inset 0 0 0 1px {T['dorado']}; }}
[data-testid="stTab"][aria-selected="true"] p {{ color: {T['texto']} !important; }}
.react-aria-SelectionIndicator {{ display: none !important; }}

/* ---------- KPI ---------- */
.fri-kpis {{ display: grid; gap: 14px; margin: 14px 0 4px 0; }}
.fri-kpi {{ background: linear-gradient(180deg, {T['superficie_2']} 0%, {T['superficie']} 100%); border: 1px solid {T['borde']}; border-radius: 10px; padding: 15px 17px 8px 17px; }}
.fri-kpis > div {{ min-width: 0; }}
.fri-kpi .fila {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 6px; }}
.fri-kpi .nombre {{ color: {T['texto']}; font-size: 15.5px; font-weight: 600; line-height: 1.25; }}
.fri-kpi .valor {{ font-size: clamp(20px, 1.55vw, 28px); color: {T['texto']}; margin-top: 3px; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.fri-kpi .valor small {{ font-size: 15px; color: {T['texto_2']}; }}
.fri-kpi .var {{ text-align: right; font-size: 12px; color: {T['texto_2']}; flex: none; padding-left: 6px; max-width: 96px; line-height: 1.3; }}
.fri-kpi .chip {{ display: inline-block; white-space: nowrap; font-size: 13px; font-weight: 600; padding: 3px 9px; border-radius: 5px; margin-bottom: 4px; font-variant-numeric: tabular-nums; }}
.chip-pos {{ background: rgba(127,192,158,0.18); color: {T['positivo']}; }}
.chip-neg {{ background: rgba(227,154,154,0.18); color: {T['negativo']}; }}
.chip-neu {{ background: rgba(194,210,218,0.13); color: {T['texto_2']}; }}
.fri-kpi .fecha {{ font-size: 12.5px; color: {T['texto_3']}; margin-top: 2px; }}
.fri-grupo {{ display: flex; flex-direction: column; justify-content: center; gap: 6px; padding: 8px 10px; }}
.fri-grupo b {{ font-family: {SERIF}; font-size: 22px; font-weight: 500; color: {T['texto']}; display: flex; gap: 10px; align-items: center; }}
.fri-grupo span {{ color: {T['texto_2']}; font-size: 13.5px; line-height: 1.35; }}

/* ---------- Paneles ---------- */
.fri-panel-titulo {{ display: flex; justify-content: space-between; align-items: baseline; margin: 2px 0 0 0; gap: 12px; }}
.fri-panel-titulo .t {{ font-family: {SERIF}; font-size: 20px; color: {T['texto']}; border-left: 3px solid {T['dorado']}; padding-left: 10px; line-height: 1.2; }}
.fri-panel-titulo span {{ color: {T['texto_2']}; font-size: 13px; white-space: nowrap; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background: linear-gradient(180deg, {T['superficie_2']} 0%, {T['superficie']} 100%); border-color: {T['borde']} !important; border-radius: 10px !important; }}
.fri-tabla {{ width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; border: none !important; }}
.fri-tabla th {{ text-align: right; color: {T['texto_2']}; font-weight: 600; font-size: 12.5px; padding: 7px 6px; border-bottom: 1px solid {T['borde_fuerte']} !important; letter-spacing: .3px; }}
.fri-tabla th:first-child, .fri-tabla td:first-child {{ text-align: left; }}
.fri-tabla td {{ text-align: right; color: {T['texto']}; padding: 8px 6px; border-bottom: 1px solid rgba(28,61,75,0.75) !important; }}
.fri-tabla th, .fri-tabla td {{ border-left: none !important; border-right: none !important; border-top: none !important; background: transparent !important; white-space: nowrap; }}
.fri-tabla td:first-child {{ white-space: normal; }}
.fri-tabla td.pos {{ color: {T['positivo']}; }} .fri-tabla td.neg {{ color: {T['negativo']}; }}
.fri-nota, .fri-nota p {{ color: {T['texto_3']} !important; font-size: 12.5px !important; margin: 6px 0 0 0 !important; line-height: 1.4 !important; }}
.fri-comentario .h4 {{ font-family: {SERIF}; color: {T['texto']}; font-size: 21px; margin: 0 0 8px 0; font-weight: 500; display: flex; gap: 10px; align-items: center; }}
.fri-comentario p {{ color: {T['texto_2']}; font-size: 15px; line-height: 1.55; }}

.fri-aviso {{ display: flex; gap: 10px; align-items: center; border: 1px dashed {T['dorado_suave']}; color: {T['texto_2']}; border-radius: 8px; padding: 7px 14px; font-size: 13.5px; margin: 6px 0 0 0; }}
.fri-aviso b {{ color: {T['dorado']}; letter-spacing: 1px; font-size: 12px; }}

.fri-pendiente {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 12px; }}
.fri-pendiente .caja {{ background: {T['superficie']}; border: 1px dashed {T['borde_fuerte']}; border-radius: 10px; padding: 18px 20px; min-height: 150px; }}
.fri-pendiente .h4 {{ font-family: {SERIF}; font-size: 20px; color: {T['texto']}; margin: 0 0 8px 0; font-weight: 500; }}
.fri-pendiente p {{ color: {T['texto_2']}; font-size: 14.5px; line-height: 1.5; margin: 0 0 10px 0; }}
.estado {{ display: inline-block; font-size: 11.5px; letter-spacing: 1px; padding: 3px 8px; border-radius: 4px; }}
.estado-pendiente {{ color: {T['dorado']}; border: 1px solid {T['dorado_suave']}; }}
.estado-existente {{ color: {T['positivo']}; border: 1px solid rgba(127,192,158,0.5); }}
.boton-inactivo {{ display: inline-flex; gap: 10px; align-items: center; border: 1px dashed {T['dorado_suave']}; border-radius: 18px; padding: 6px 18px;
  color: {T['texto_3']}; font-size: 14px; cursor: not-allowed; opacity: .8; }}

.js-plotly-plot .plotly .modebar {{ display: none !important; }}

/* ---------- Contenido de las secciones existentes dentro de FRI ---------- */
[data-testid="stMain"] [data-testid="stHeading"] h1, [data-testid="stMain"] [data-testid="stHeading"] h2,
[data-testid="stMain"] [data-testid="stHeading"] h3 {{ font-family: {SERIF} !important; color: {T['texto']} !important; font-weight: 500 !important; }}
[data-testid="stMain"] [data-testid="stHeading"] h2 {{ font-size: 28px !important; }}
[data-testid="stMain"] [data-testid="stHeading"] h3 {{ font-size: 22px !important; border-left: 3px solid {T['dorado']}; padding-left: 10px !important; }}
[data-testid="stMain"] [data-testid="stMarkdownContainer"] p, [data-testid="stMain"] [data-testid="stMarkdownContainer"] li {{ color: {T['texto']}; }}
[data-testid="stMain"] [data-testid="stCaptionContainer"] {{ color: {T['texto_2']} !important; font-size: 13.5px; }}
[data-testid="stMetric"] {{ background: linear-gradient(180deg, {T['superficie_2']} 0%, {T['superficie']} 100%); border: 1px solid {T['borde']}; border-radius: 10px; padding: 12px 14px; }}
[data-testid="stAlert"] {{ border-radius: 8px; }}

/* Pestañas y apartados de FRI (st.segmented_control) con el mismo aspecto que las pestañas aprobadas */
[data-testid="stButtonGroup"] {{ margin: 0 0 6px 0; }}
[data-testid="stButtonGroup"] button {{ background: {T['superficie']} !important; border-color: {T['borde']} !important; color: {T['texto_2']} !important; padding: 7px 20px !important; }}
[data-testid="stButtonGroup"] button[kind$="Active"], [data-testid="stButtonGroup"] button[aria-checked="true"] {{
  background: rgba(201,171,116,0.18) !important; border-color: {T['dorado']} !important; color: {T['texto']} !important; }}
[data-testid="stButtonGroup"] button p {{ font-size: 15px !important; }}

.fri-enlace-clasica {{ padding: 18px 24px 0 24px; }}
.fri-enlace-clasica a {{ color: {T['texto_3']} !important; font-size: 13px; text-decoration: none !important; border-bottom: 1px dotted {T['texto_3']}; }}

/* =====================================================================================================================
   ESCALA ADAPTABLE (F4-b). El diseño aprobado se trazó para un ancho útil de ~1672 px. Las reglas de arriba quedan como
   están; las de abajo solo REDUCEN en proporción cuando la ventana es más angosta (clamp(mín, vw, máx), con máx = el valor
   aprobado, de modo que a ≥1672 px todo queda idéntico) y reorganizan las grillas cuando ya no caben. No cambian colores,
   fuentes ni componentes. Causa: con el escalado de Windows (125–150 %), una pantalla de 1920×1080 se ve como 1536 o
   1280 px de ancho útil aunque el zoom del navegador esté al 100 %.
   ===================================================================================================================== */

/* Menú lateral SIEMPRE visible. Streamlit recuerda en el navegador (localStorage «stSidebarCollapsed-») si alguna vez se
   cerró el menú, por ejemplo en la interfaz clásica; entonces lo desplaza fuera de la pantalla. FRI oculta el botón para
   abrirlo y reserva sus 248 px, así que quedaba el espacio vacío y sin forma de recuperarlo. */
[data-testid="stSidebar"] {{ transform: none !important; visibility: visible !important; left: 0 !important; }}
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {{ display: none !important; }}

/* Los títulos no se cortan en mitad de una palabra («Macroecono-mía»). */
.fri-portada .h1, .fri-portada .subtitulo, .fri-encabezado .h1, .fri-tarjeta-nav .h3, .fri-foco .h3, .fri-grupo b,
.fri-panel-titulo .t, .fri-pendiente .h4, .fri-kpi .nombre, .fri-barra .titulo {{
  overflow-wrap: normal !important; word-break: normal !important; hyphens: manual; }}

.block-container {{ max-width: 1880px; }}

/* Portada: misma composición, más baja y con títulos proporcionales en pantallas angostas. */
.fri-portada {{ height: clamp(300px, 25.1vw, 420px); }}
.fri-portada .contenido {{ top: clamp(22px, 2.15vw, 36px); left: clamp(2.2rem, 4vw, 4.2rem); max-width: min(660px, 58%); }}
.fri-portada .ruta span.linea {{ width: clamp(80px, 25.1vw, 420px); }}
.fri-portada .h1 {{ font-size: clamp(40px, 3.83vw, 64px); margin: clamp(14px, 1.55vw, 26px) 0 clamp(8px, .72vw, 12px) 0; }}
.fri-portada .subtitulo {{ font-size: clamp(20px, 1.67vw, 28px); margin-bottom: clamp(8px, .84vw, 14px); }}
.fri-portada .bajada {{ font-size: clamp(14.5px, 1.05vw, 17.5px); }}
.fri-portada .fecha {{ font-size: clamp(13px, .87vw, 14.5px); }}

/* Tarjetas de Inicio: la ilustración ocupa su propio espacio sobre el enlace y nunca tapa el texto. */
.fri-tarjetas {{ gap: clamp(12px, 1.08vw, 18px); margin-top: clamp(-36px, -2.15vw, -20px); }}
.fri-tarjeta-nav {{ --pad: clamp(16px, 1.32vw, 22px); padding: clamp(18px, 1.44vw, 24px) var(--pad) clamp(14px, 1.2vw, 20px) var(--pad);
  min-height: clamp(240px, 17.3vw, 290px); }}
.fri-tarjeta-nav .h3 {{ font-size: clamp(18px, 1.5vw, 25px); }}
.fri-tarjeta-nav p {{ font-size: clamp(13.5px, .9vw, 15px); }}
.fri-tarjeta-nav .decoracion {{ position: relative; left: auto; right: auto; bottom: auto; order: 1; flex: none;
  margin: auto calc(-1 * var(--pad)) 6px calc(-1 * var(--pad)); height: clamp(48px, 3.83vw, 64px); }}
.fri-tarjeta-nav .decoracion svg {{ width: 100%; height: 100%; }}
.fri-tarjeta-nav a {{ order: 2; margin-top: 0; font-size: clamp(13px, .87vw, 14.5px); white-space: nowrap; }}

/* Cabecera de las secciones */
.fri-encabezado .h1 {{ font-size: clamp(30px, 2.4vw, 40px); }}
.fri-encabezado p {{ font-size: clamp(14px, .96vw, 16px); }}
.fri-barra .titulo {{ font-size: clamp(18px, 1.32vw, 22px); }}
.fri-barra .sub {{ font-size: clamp(13px, .87vw, 14.5px); }}

/* Filas de indicadores: la variación puede bajar bajo el nombre en vez de salirse de la tarjeta. */
.fri-kpi .fila {{ flex-wrap: wrap; }}
.fri-kpi .nombre {{ font-size: clamp(14px, .93vw, 15.5px); }}

@media (max-width: 1600px) {{
  .fri-kpis {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)) !important; }}
  .fri-kpis.fri-kpis-grupo {{ grid-template-columns: minmax(0, .8fr) repeat(var(--mitad), minmax(0, 1fr)) !important; }}
  .fri-kpis.fri-kpis-grupo > :first-child {{ grid-row: span 2; }}
  .fri-foco {{ grid-template-columns: 150px 1fr 300px; gap: 22px; }}
}}
@media (max-width: 1360px) {{
  .fri-tarjeta-nav .h3 {{ font-size: clamp(17px, 1.36vw, 25px); }}
}}
@media (max-width: 1200px) {{
  .fri-tarjetas {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
  .fri-foco {{ grid-template-columns: 120px 1fr; }}
  .fri-foco .proximo {{ grid-column: 1 / -1; border-left: none; border-top: 1px solid {T['borde_fuerte']}; padding: 14px 0 0 0; }}
  .fri-encabezado .meta {{ display: none; }}
}}
@media (max-width: 900px) {{
  .fri-tarjetas {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .fri-portada .fecha {{ display: none; }}
}}

/* Pantallas bajas (p. ej. 1280×720 útiles): el pie con la fotografía no tapa «Interfaz clásica». */
@media (max-height: 860px) {{
  .fri-marca {{ padding: 18px 12px 10px 12px; }}
  .fri-marca .logo {{ font-size: 34px; }}
  .fri-marca .filete {{ margin: 10px auto; }}
  .fri-nav {{ margin-top: 8px; }}
  .fri-nav a {{ padding: 10px 22px; }}
  .fri-enlace-clasica {{ padding-top: 12px; }}
  .fri-pie-menu {{ height: 96px; padding-top: 42px; }}
}}
</style>
"""
