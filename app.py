"""
app.py - Interfaz visual (Streamlit) del generador de invitaciones.

Reusa el mismo pipeline que main.py / webhook_server.py / batch_processor.py
(LayoutDecisionEngine + CanvasEngine via main.generar_invitacion), para que
la interfaz nunca se desincronice del motor de renderizado. Cualquier
[AVISO]/[ERROR] que el pipeline ya imprime por consola (fallback de fondo,
foto de ponente, logo, config) se captura y se muestra como alerta visual.

El formulario replica los campos reales del formulario Microsoft Forms que
ya usaba el cliente (marca lider, tipo de evento con 3 ramas, informacion
administrativa) - ver notas de asuncion marcadas con [ASUNCION] mas abajo,
pendientes de confirmar con el cliente.
"""

import contextlib
import io
import json
import shutil
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from PIL import Image

import main as pipeline
from assets_manager import CATEGORY_KEYWORDS
from batch_processor import generar_reporte_resumen, process_csv_file, process_json_folder
from spellcheck import formatear_errores, revisar_texto

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output" / "streamlit"
BATCH_OUTPUT_DIR = OUTPUT_DIR / "batch"
UPLOADS_DIR = OUTPUT_DIR / "_uploads"
BACKGROUNDS_DIR = BASE_DIR / "assets" / "backgrounds"
THUMBS_DIR = OUTPUT_DIR / "_thumbs"
BACKGROUND_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}

# ---------------------------------------------------------------------------
# Marca lider que convoca (Q1 del formulario real del cliente). Las 4
# opciones de programa/sinergia no son simplemente "Contegral" o "Finca" -
# [ASUNCION] se mapean a la combinacion de marca mas probable para efectos
# de tipografia/logo (ver assets_manager.FONT_FAMILY_BY_MARCA); confirmar la
# regla real con el cliente cuando se defina.
# ---------------------------------------------------------------------------
MARCA_LIDER_OPCIONES = [
    "Contegral", "Finca", "Contegral + Finca", "Cinta Azul",
    "Equinos Bios", "Sinergia Ganadería", "Sinergia Porcicultura", "Otro",
]
MARCA_LIDER_A_MARCA = {
    "Contegral": ["Contegral"],
    "Finca": ["Finca"],
    "Contegral + Finca": ["Contegral", "Finca"],
    "Cinta Azul": ["Contegral"],              # [ASUNCION] linea equina de Contegral
    "Equinos Bios": ["Contegral", "Finca"],   # [ASUNCION] programa conjunto
    "Sinergia Ganadería": ["Contegral", "Finca"],
    "Sinergia Porcicultura": ["Contegral", "Finca"],
}
MARCA_LIDER_ASUNCION = {"Cinta Azul", "Equinos Bios", "Sinergia Ganadería", "Sinergia Porcicultura"}

CATEGORIAS = ["Ganadería", "Porcicultura", "Avicultura", "Acuícola", "Cunicultura", "Equinos", "Campo"]

# Palabras clave (sobre el nombre de archivo) para filtrar la galeria de fondos
# por linea de negocio. Equinos/Cunicultura aun no tienen fondos propios.
PALABRAS_FONDO_POR_LINEA = {
    "Ganadería": CATEGORY_KEYWORDS["ganaderia"],
    "Porcicultura": CATEGORY_KEYWORDS["porcicultura"],
    "Avicultura": CATEGORY_KEYWORDS["avicola"],
    "Acuícola": CATEGORY_KEYWORDS["campo"] + ["pez"],
    "Campo": CATEGORY_KEYWORDS["campo"],
    "Equinos": [],
    "Cunicultura": [],
}

# Categorias cuyo icono de linea real (assets/icons/{Marca}/) es ambiguo sin
# una sub-linea explicita - ver AssetRepository.get_category_icon().
SUB_LINEAS_POR_CATEGORIA = {
    "Ganadería": ["Carne", "Leche"],
    "Avicultura": ["Ponedoras", "Engorde"],
}

# Tipo de evento (Q2 del formulario real): Charla Maestra y Dia de Campo
# comparten exactamente las mismas preguntas (hasta 3 charlas con
# expositor/empresa); Actividad Promocional tiene su propio set de campos.
TIPOS_EVENTO = ["Charla Maestra", "Día de Campo", "Actividad Promocional"]
TIPOS_CON_CHARLAS = ("Charla Maestra", "Día de Campo")
MAX_CHARLAS = 3

PASOS_BASE = ["marca", "tipo", "datos", "charlas", "fondo", "pata", "admin", "final"]
PASOS_TITULOS = {
    "marca": "Marca y línea de negocio", "tipo": "Tipo de evento", "datos": "Datos del evento",
    "charlas": "Charlas", "fondo": "Imagen de fondo", "pata": "Patrocinadores (pata)",
    "admin": "Información administrativa", "final": "Revisión y vista previa",
}

def _hora_12h(minutos: int) -> str:
    h, m = divmod(minutos, 60)
    return f"{(h % 12) or 12}:{m:02d} {'a.m.' if h < 12 else 'p.m.'}"


HORAS_12H = [_hora_12h(m) for m in range(5 * 60, 22 * 60 + 1, 15)]

CENTROS_OPERATIVOS = [
    "Envigado", "Itagüí", "Bogotá", "Mosquera", "Cartago",
    "Buga", "Neiva", "Bucaramanga", "Ciénaga de Oro",
]

TIPOS_ACTIVACION = [
    "Día del pollito", "Día del ganadero", "Día del acuicultor",
    "Día del caballo (Cinta Azul)", "Día del caballo (Rodeo)",
    "Día de lechón", "Día del cerdo", "Día Contegral", "Día Finca",
]

# Palabra pequena (acento) + palabra grande (blanca) del bloque de titulo -
# ver main.py. Charla Maestra/Dia de Campo son fijas; Actividad Promocional
# depende del tipo de activacion elegido.
HEADLINE_POR_TIPO_EVENTO = {
    "Charla Maestra": ("Charla", "Maestra"),
    "Día de Campo": ("Día de", "Campo"),
}
HEADLINE_POR_ACTIVACION = {
    "Día del pollito": ("Día del", "Pollito"),
    "Día del ganadero": ("Día del", "Ganadero"),
    "Día del acuicultor": ("Día del", "Acuicultor"),
    "Día del caballo (Cinta Azul)": ("Día del Caballo", "Cinta Azul"),
    "Día del caballo (Rodeo)": ("Día del Caballo", "Rodeo"),
    "Día de lechón": ("Día del", "Lechón"),
    "Día del cerdo": ("Día del", "Cerdo"),
    "Día Contegral": ("Día", "Contegral"),
    "Día Finca": ("Día", "Finca"),
}

st.set_page_config(
    page_title="Generador Automatizado de Invitaciones - Grupo Bios",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _listar_fondos() -> List[Path]:
    if not BACKGROUNDS_DIR.is_dir():
        return []
    return sorted(
        p for p in BACKGROUNDS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in BACKGROUND_EXTENSIONS
    )


def _miniatura_fondo(ruta: Path) -> Optional[str]:
    """Miniatura JPG cacheada en disco (los fondos originales pesan hasta ~90MB)."""
    destino = THUMBS_DIR / f"{ruta.stem}.jpg"
    try:
        if not destino.is_file() or destino.stat().st_mtime < ruta.stat().st_mtime:
            THUMBS_DIR.mkdir(parents=True, exist_ok=True)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with Image.open(ruta) as im:
                    im.draft("RGB", (600, 1000))
                    miniatura = im.convert("RGB")
            miniatura.thumbnail((300, 520))
            miniatura.save(destino, quality=80)
        return str(destino)
    except Exception:
        return None


def _elegir_fondo(nombre: Optional[str]) -> None:
    st.session_state["fondo_elegido"] = nombre


def _revisar_ortografia(etiqueta: str, texto: str, acumulado: List[str]) -> None:
    """Muestra bajo el campo las palabras con error (con sugerencia) y las acumula para bloquear la generacion."""
    errores = revisar_texto(texto)
    if errores:
        st.warning(f"Ortografía en «{etiqueta}»: {formatear_errores(errores)}")
        acumulado.append(etiqueta)


def _cierre_ortografia(nombre: str, ort: Dict[str, List[str]], pendientes: Dict[str, List[str]]) -> None:
    """Si el paso tiene errores de ortografia: aviso + opcion de omitir; sin omitir, bloquea 'Siguiente'."""
    if not ort[nombre]:
        return
    st.error(f"Errores de ortografía en: {', '.join(ort[nombre])}.")
    omitir = st.checkbox("Omitir la revisión ortográfica en este paso (saldrá con esos errores)", key=f"omitir_ortografia_{nombre}")
    if not omitir:
        pendientes[nombre].append("corrige la ortografía de los campos marcados")


def _ir_a(paso: str) -> None:
    st.session_state["paso"] = paso
    if paso != "final":
        st.session_state["ultimo_resultado"] = None


def _reiniciar() -> None:
    for clave in list(st.session_state.keys()):
        del st.session_state[clave]


def _css_ocultar_pasos(actual: str) -> str:
    """Los pasos se renderizan todos (asi no se pierde lo escrito); aqui se ocultan los que no son el actual."""
    reglas = "".join(
        f'.st-key-paso_{n}, [data-testid="stLayoutWrapper"]:has(> .st-key-paso_{n}) {{display: none !important;}}'
        for n in PASOS_BASE if n != actual
    )
    return f"<style>{reglas}</style>"


def _mostrar_mensajes_capturados(texto: str) -> None:
    """Traduce los [AVISO]/[ERROR] que imprime el pipeline a alertas visuales de Streamlit."""
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        if linea.startswith("[AVISO]"):
            st.warning(linea.removeprefix("[AVISO]").strip())
        elif linea.startswith("[ERROR]"):
            st.error(linea.removeprefix("[ERROR]").strip())
        else:
            st.caption(linea)


def _renderizar_invitacion(payload: Dict[str, Any], output_path: Path):
    """
    Ejecuta main.generar_invitacion() capturando stdout (los [AVISO]/[ERROR]
    del pipeline) para mostrarlos como alertas. Devuelve (ruta, duracion_ms,
    mensajes_capturados) o lanza la excepcion original si algo falla.
    """
    buffer = io.StringIO()
    inicio = time.perf_counter()
    with contextlib.redirect_stdout(buffer):
        resultado = pipeline.generar_invitacion(payload, output_path)
    duracion_ms = (time.perf_counter() - inicio) * 1000
    return resultado, duracion_ms, buffer.getvalue()


# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------

st.title("📨 Generador Automatizado de Invitaciones - Grupo Bios")
st.caption("Motor: LayoutDecisionEngine + CanvasEngine (Pillow) — mismo pipeline que el webhook y el CLI.")

tab_generar, tab_lote = st.tabs(["🖼️ Generar Invitación", "📦 Carga Masiva"])


# ---------------------------------------------------------------------------
# Tab 1: Generar una invitacion individual
# ---------------------------------------------------------------------------

with tab_generar:
    _, centro, _ = st.columns([1, 4, 1])
    with centro:
        tipo_actual = st.session_state.get("tipo_evento", TIPOS_EVENTO[0])
        pasos = [p for p in PASOS_BASE if not (p == "charlas" and tipo_actual not in TIPOS_CON_CHARLAS)]
        paso = st.session_state.get("paso", "marca")
        if paso not in pasos:
            paso = "marca"
        idx = pasos.index(paso)

        st.markdown(_css_ocultar_pasos(paso), unsafe_allow_html=True)
        st.progress((idx + 1) / len(pasos), text=f"Paso {idx + 1} de {len(pasos)} · {PASOS_TITULOS[paso]}")

        pendientes: Dict[str, List[str]] = {n: [] for n in pasos}
        ort: Dict[str, List[str]] = {"datos": [], "charlas": []}

        # ---------------- Paso: marca y linea de negocio ----------------
        with st.container(key="paso_marca"):
            st.subheader(PASOS_TITULOS["marca"])
            marca_lider = st.selectbox("Marca líder que convoca", MARCA_LIDER_OPCIONES, key="marca_lider")
            marca_lider_otro = ""
            if marca_lider == "Otro":
                marca_lider_otro = st.text_input("Especifique la marca/programa", key="marca_lider_otro")
            if marca_lider in MARCA_LIDER_ASUNCION:
                st.caption("⚠️ Tipografía/logo asumidos para este programa — pendiente de confirmar con el cliente.")
            marca = MARCA_LIDER_A_MARCA.get(marca_lider, [])

            categoria = st.multiselect(
                "Línea de negocio (elige varias si el evento cubre más de una)",
                CATEGORIAS, default=[CATEGORIAS[0]], key="categoria",
            )
            if len(categoria) > 1:
                st.caption("Evento multi-línea: se usa un color neutro y la insignia lista todas las categorías elegidas.")
            if not categoria:
                pendientes["marca"].append("selecciona al menos una línea de negocio")

            sub_linea = None
            if len(categoria) == 1 and categoria[0] in SUB_LINEAS_POR_CATEGORIA:
                opciones_sub = SUB_LINEAS_POR_CATEGORIA[categoria[0]]
                sub_linea = st.multiselect(
                    f"Sub-línea de {categoria[0]} (elige las que apliquen; cada una muestra su icono)",
                    opciones_sub, default=opciones_sub[:1], key="sub_linea",
                )
                if not sub_linea:
                    pendientes["marca"].append("elige al menos una sub-línea")

        # ---------------- Paso: tipo de evento ----------------
        with st.container(key="paso_tipo"):
            st.subheader(PASOS_TITULOS["tipo"])
            tipo_evento = st.radio("Selecciona el tipo de evento para el que necesitas la pieza", TIPOS_EVENTO, key="tipo_evento")
            st.caption("Los eventos tipo Encuentro o Jornada no se gestionan por este formulario: van directo con los jefes de mercadeo.")

        # ---------------- Paso: datos del evento ----------------
        titulo_evento = subtitulo = fecha = hora = direccion = lugar = ""
        tipo_activacion = None
        descripcion_promocion = ""
        fecha_inicio_promo = fecha_fin_promo = None
        unidades_disponibles = ""

        with st.container(key="paso_datos"):
            st.subheader(PASOS_TITULOS["datos"])
            if tipo_evento in TIPOS_CON_CHARLAS:
                titulo_evento = st.text_input(
                    "Nombre o tema de la charla", key="titulo", placeholder="Ej. Suplementación en verano",
                    help="Es el título principal: sale en mayúsculas y en el color de la línea de negocio.",
                )
                subtitulo = st.text_input(
                    "Subtítulo (opcional)", key="subtitulo", placeholder="Ej. Formas de afrontar el fenómeno del Niño",
                    help="Complementa o amplía el tema. Sale debajo, en blanco.",
                )
                fecha = st.text_input("Fecha", key="fecha", placeholder="Ej. 24 de Septiembre de 2026")
                col_h1, col_h2 = st.columns(2)
                hora_inicio = col_h1.selectbox(
                    "Hora de inicio", HORAS_12H, index=None, placeholder="Ej. 7:00 a.m.", key="hora_inicio",
                )
                hora_fin = col_h2.selectbox(
                    "Hora de finalización (opcional)", HORAS_12H, index=None, placeholder="Ej. 9:00 a.m.", key="hora_fin",
                )
                hora = f"{hora_inicio} a {hora_fin}" if hora_inicio and hora_fin else (hora_inicio or "")
                if hora_inicio and hora_fin and HORAS_12H.index(hora_fin) <= HORAS_12H.index(hora_inicio):
                    pendientes["datos"].append("la hora de finalización debe ser posterior a la de inicio")
                direccion = st.text_input("Dirección", key="direccion", placeholder="Ej. Carrera 20 # 20-1 Barrio Boyacá")
                lugar = st.text_input("Lugar", key="lugar", placeholder="Ej. Comité de Ganaderos de Tame")
                for etiqueta_o, valor_o in (
                    ("Nombre o tema de la charla", titulo_evento), ("Subtítulo", subtitulo), ("Fecha", fecha),
                ):
                    _revisar_ortografia(etiqueta_o, valor_o, ort["datos"])
                if not titulo_evento.strip():
                    pendientes["datos"].append("escribe el nombre o tema de la charla")
            else:
                tipo_activacion = st.selectbox("Seleccione el tipo de activación", TIPOS_ACTIVACION, key="tipo_activacion")
                descripcion_promocion = st.text_area(
                    "Describa en qué consiste la promoción", key="descripcion_promocion",
                    placeholder=(
                        'Ej. "Por la compra de X unidades, lleva Y gratis" o "Nuestros expertos estarán '
                        'con nosotros, visítanos para asesorarte. Tendremos regalos y sorpresas por tu '
                        'compra en la marca."'
                    ),
                )
                st.caption("Este texto queda sujeto a validación humana antes de publicarse.")
                _revisar_ortografia("Descripción de la promoción", descripcion_promocion, ort["datos"])
                if not descripcion_promocion.strip():
                    pendientes["datos"].append("describe en qué consiste la promoción")
                col_fi, col_ff = st.columns(2)
                fecha_inicio_promo = col_fi.date_input("Fecha inicial de la promoción", key="fecha_inicio_promo")
                fecha_fin_promo = col_ff.date_input("Fecha final de la promoción", key="fecha_fin_promo")
                unidades_disponibles = st.text_area(
                    "Unidades disponibles de cada referencia involucrada", key="unidades_disponibles",
                    placeholder="Ej. Ref. 1234 - 500 unidades; Ref. 5678 - 300 unidades",
                )
                st.caption("Dato administrativo — no se imprime en la pieza.")
            _cierre_ortografia("datos", ort, pendientes)

        # ---------------- Paso: charlas (solo Charla Maestra / Dia de Campo) ----------------
        ponentes: List[Dict[str, Any]] = []
        if "charlas" in pasos:
            with st.container(key="paso_charlas"):
                st.subheader(PASOS_TITULOS["charlas"])
                num_charlas = st.radio(
                    "¿Cuántas charlas tendrá el evento?", list(range(1, MAX_CHARLAS + 1)),
                    key="num_charlas", horizontal=True,
                )
                st.caption("Si el evento tiene menos charlas, deja en blanco el nombre del expositor de las que no apliquen.")
                for i in range(int(num_charlas)):
                    with st.expander(f"Charla {i + 1}", expanded=True):
                        titulo_charla = st.text_input("Título de la charla", key=f"charla_{i}_titulo")
                        _revisar_ortografia(f"Título de la charla {i + 1}", titulo_charla, ort["charlas"])
                        expositor = st.text_input("Nombre del expositor", key=f"charla_{i}_expositor")
                        cargo_expositor = st.text_input("Cargo del expositor", key=f"charla_{i}_cargo", placeholder="Ej. Médico veterinario")
                        _revisar_ortografia(f"Cargo del expositor {i + 1}", cargo_expositor, ort["charlas"])
                        empresa_expositor = st.text_input("Empresa del expositor", key=f"charla_{i}_empresa")
                        if expositor.strip():
                            ponentes.append({
                                "name": expositor, "role": cargo_expositor, "empresa": empresa_expositor, "tema": titulo_charla,
                            })
                _cierre_ortografia("charlas", ort, pendientes)

        # ---------------- Paso: imagen de fondo ----------------
        with st.container(key="paso_fondo"):
            st.subheader(PASOS_TITULOS["fondo"])
            fondos_disponibles = _listar_fondos()
            fondo_elegido = st.session_state.get("fondo_elegido")
            if fondo_elegido and not (BACKGROUNDS_DIR / fondo_elegido).is_file():
                fondo_elegido = None
            if fondo_elegido:
                miniatura_actual = _miniatura_fondo(BACKGROUNDS_DIR / fondo_elegido)
                if miniatura_actual:
                    st.image(miniatura_actual, width=140)
                st.caption(f"Fondo elegido: {fondo_elegido}")
            else:
                st.caption("Automático: se elige al azar uno acorde a la línea de negocio. Elige uno de la galería para controlarlo.")
            palabras_linea = [p for linea in categoria for p in PALABRAS_FONDO_POR_LINEA.get(linea, [])]
            fondos_de_la_linea = [f for f in fondos_disponibles if any(p in f.stem.lower() for p in palabras_linea)]
            mostrar_todos = st.checkbox("Mostrar fondos de todas las líneas", key="fondos_todos")
            if mostrar_todos or not fondos_de_la_linea:
                fondos_galeria = fondos_disponibles
                if not mostrar_todos:
                    st.caption("No hay fondos específicos para la línea elegida; se muestran todos.")
            else:
                fondos_galeria = fondos_de_la_linea
            if fondo_elegido and (BACKGROUNDS_DIR / fondo_elegido) not in fondos_galeria:
                st.warning("El fondo elegido no corresponde a la línea de negocio seleccionada.")
            with st.expander(f"Elegir de la galería ({len(fondos_galeria)} fondos)"):
                st.button("Automático (según línea de negocio)", key="fondo_auto", on_click=_elegir_fondo, args=(None,))
                columnas_fondos = st.columns(3)
                for i, ruta_fondo in enumerate(fondos_galeria):
                    with columnas_fondos[i % 3]:
                        miniatura = _miniatura_fondo(ruta_fondo)
                        if miniatura:
                            st.image(miniatura, width="stretch")
                        st.caption(ruta_fondo.stem.replace("_", " "))
                        st.button("Usar este", key=f"fondo_{ruta_fondo.name}", on_click=_elegir_fondo, args=(ruta_fondo.name,))

        # ---------------- Paso: pata de patrocinadores ----------------
        with st.container(key="paso_pata"):
            st.subheader(PASOS_TITULOS["pata"])
            st.caption(
                "Obligatorio: al menos una marca que apoya o que invita. Cada grupo puede llevar logos, un nombre "
                "en texto o ambos; solo aparece el grupo que tenga contenido (si solo llenas «Invitan», sale solo «Invita»)."
            )
            archivos_apoyan = st.file_uploader(
                "Logos que APOYAN", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="logos_apoyan",
            )
            texto_apoyan = st.text_input("Nombre de quien APOYA (texto, opcional)", key="texto_apoyan", placeholder="Ej. Agro Insumos Donde Pollo")
            archivos_invitan = st.file_uploader(
                "Logos que INVITAN", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="logos_invitan",
            )
            texto_invitan = st.text_input("Nombre de quien INVITA (texto, opcional)", key="texto_invitan", placeholder="Ej. Veterinaria Agrollanos")
            if not (archivos_apoyan or archivos_invitan or texto_apoyan.strip() or texto_invitan.strip()):
                pendientes["pata"].append("agrega al menos una marca que apoya o invita (logo o nombre)")

        # ---------------- Paso: informacion administrativa ----------------
        with st.container(key="paso_admin"):
            st.subheader(PASOS_TITULOS["admin"])
            centro_operativo = st.selectbox(
                "Centro Operativo", CENTROS_OPERATIVOS, index=None, placeholder="Selecciona la respuesta", key="centro_operativo",
            )
            if not centro_operativo:
                pendientes["admin"].append("selecciona el Centro Operativo")
            observaciones = st.text_area("Observaciones adicionales", key="observaciones")

        # ---------------- Paso final: revision, generacion y vista previa ----------------
        pendientes_total = [
            f"{PASOS_TITULOS[n]}: {m}" for n in pasos if n != "final" for m in pendientes[n]
        ]
        with st.container(key="paso_final"):
            col_res, col_img = st.columns([1, 1], gap="large")
            with col_res:
                st.subheader(PASOS_TITULOS["final"])
                es_charla = tipo_evento in TIPOS_CON_CHARLAS
                resumen = [
                    f"**Marca líder:** {(marca_lider_otro or 'Otro') if marca_lider == 'Otro' else marca_lider}",
                    f"**Línea de negocio:** {', '.join(categoria) or '—'}",
                    f"**Tipo de evento:** {tipo_evento}" + (f" · {tipo_activacion}" if tipo_activacion else ""),
                    f"**{'Tema' if es_charla else 'Promoción'}:** {titulo_evento if es_charla else descripcion_promocion}{(' — ' + subtitulo) if es_charla and subtitulo.strip() else ''}",
                ]
                if es_charla:
                    resumen.append(f"**Fecha · hora · dirección · lugar:** {' · '.join(v for v in (fecha, hora, direccion, lugar) if v) or '—'}")
                    resumen.append(f"**Expositores:** {', '.join(p['name'] for p in ponentes) or 'ninguno'}")
                else:
                    resumen.append(
                        f"**Vigencia:** {fecha_inicio_promo.strftime('%d/%m/%Y')} al {fecha_fin_promo.strftime('%d/%m/%Y')}"
                    )
                def _resumen_grupo(archivos, texto):
                    partes = ([f"{len(archivos)} logo(s)"] if archivos else []) + ([f"«{texto.strip()}»"] if texto.strip() else [])
                    return " + ".join(partes) or "—"

                resumen += [
                    f"**Fondo:** {fondo_elegido or 'automático'}",
                    f"**Apoya:** {_resumen_grupo(archivos_apoyan, texto_apoyan)}",
                    f"**Invita:** {_resumen_grupo(archivos_invitan, texto_invitan)}",
                    f"**Centro Operativo:** {centro_operativo or '—'}",
                ]
                st.markdown("\n".join(f"- {linea}" for linea in resumen))

                if pendientes_total:
                    st.error("Faltan datos para generar:\n\n" + "\n".join(f"- {m}" for m in pendientes_total))
                generar = st.button(
                    "🎨 Generar invitación", type="primary", disabled=bool(pendientes_total), width="stretch",
                )
                st.button("↺ Crear otra invitación desde cero", key="nav_reiniciar", on_click=_reiniciar, width="stretch")

            with col_img:
                if generar:
                    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

                    patas = []
                    for tipo_pata, archivos_pata, texto_pata in (
                        ("Apoya", archivos_apoyan, texto_apoyan), ("Invita", archivos_invitan, texto_invitan),
                    ):
                        if not archivos_pata and not texto_pata.strip():
                            continue
                        carpeta_aliados = UPLOADS_DIR / "aliados"
                        carpeta_aliados.mkdir(parents=True, exist_ok=True)
                        rutas = []
                        for subido in archivos_pata:
                            ruta_logo = carpeta_aliados / f"{tipo_pata.lower()}_{subido.name}"
                            ruta_logo.write_bytes(subido.getvalue())
                            rutas.append(str(ruta_logo))
                        patas.append({"tipo": tipo_pata, "logos": rutas, "texto": texto_pata.strip()})

                    if es_charla:
                        palabra_categoria, palabra_titulo = HEADLINE_POR_TIPO_EVENTO[tipo_evento]
                        tema_evento, subtitulo_pieza = titulo_evento, subtitulo.strip()
                        fecha_texto = [v for v in (fecha, hora, direccion.upper(), lugar) if v]
                    else:
                        palabra_categoria, palabra_titulo = HEADLINE_POR_ACTIVACION.get(
                            tipo_activacion, ("Actividad", "Promocional"),
                        )
                        tema_evento, subtitulo_pieza = "", descripcion_promocion
                        fecha_texto = [
                            v for v in (
                                f"Vigente del {fecha_inicio_promo.strftime('%d/%m/%Y')}" if fecha_inicio_promo else "",
                                f"al {fecha_fin_promo.strftime('%d/%m/%Y')}" if fecha_fin_promo else "",
                            ) if v
                        ]

                    payload: Dict[str, Any] = {
                        "marca": marca,
                        "categoria": categoria,
                        "palabra_categoria": palabra_categoria,
                        "palabra_titulo": palabra_titulo,
                        "tema_evento": tema_evento,
                        "subtitulo": subtitulo_pieza,
                        "fecha_texto": fecha_texto,
                        "ponentes": ponentes,
                        # Metadata administrativa del formulario - no se dibuja en la pieza.
                        "marca_lider": marca_lider_otro if marca_lider == "Otro" else marca_lider,
                        "centro_operativo": centro_operativo,
                        "observaciones": observaciones,
                    }
                    if fondo_elegido:
                        payload["background_file"] = fondo_elegido
                    if sub_linea:
                        payload["sub_linea"] = [x.lower() for x in sub_linea]
                    if patas:
                        payload["patas"] = patas
                    if tipo_evento == "Actividad Promocional":
                        payload["tipo_activacion"] = tipo_activacion
                        payload["unidades_disponibles"] = unidades_disponibles

                    destino = OUTPUT_DIR / f"invitacion_{int(time.time() * 1000)}.png"
                    try:
                        ruta, duracion_ms, mensajes = _renderizar_invitacion(payload, destino)
                        st.session_state["ultimo_resultado"] = {
                            "ruta": str(ruta), "duracion_ms": duracion_ms, "mensajes": mensajes,
                        }
                    except Exception as e:
                        st.error(f"No se pudo generar la invitación: {type(e).__name__}: {e}")
                        st.session_state["ultimo_resultado"] = None

                resultado = st.session_state.get("ultimo_resultado")
                if resultado:
                    st.image(resultado["ruta"], width="stretch", caption="Vista previa (1080 x 1920 px)")
                    _mostrar_mensajes_capturados(resultado["mensajes"])
                    with open(resultado["ruta"], "rb") as f:
                        st.download_button(
                            "⬇️ Descargar PNG", data=f.read(), file_name=Path(resultado["ruta"]).name,
                            mime="image/png", width="stretch",
                        )
                else:
                    st.info("Aquí aparecerá la invitación cuando presiones «Generar invitación».")

        # ---------------- Navegacion ----------------
        st.divider()
        if paso != "final" and pendientes[paso]:
            st.caption("Para continuar: " + " · ".join(pendientes[paso]))
        nav_ant, nav_sig = st.columns(2)
        if idx > 0:
            nav_ant.button("← Anterior", key="nav_ant", on_click=_ir_a, args=(pasos[idx - 1],), width="stretch")
        if paso != "final":
            nav_sig.button(
                "Siguiente →" if pasos[idx + 1] != "final" else "Revisar y generar →", key="nav_sig", type="primary",
                disabled=bool(pendientes[paso]), on_click=_ir_a, args=(pasos[idx + 1],), width="stretch",
            )


# ---------------------------------------------------------------------------
# Tab 2: Carga masiva (CSV o JSON) via batch_processor.py
# ---------------------------------------------------------------------------

with tab_lote:
    st.subheader("Procesar un lote de invitaciones")
    st.caption(
        "Sube un .csv (columnas: marca, tipo_evento, maestria, titulo, fecha, hora, lugar, ponentes, apoyos_texto) "
        "o uno o varios .json (un payload completo por archivo)."
    )

    archivos = st.file_uploader(
        "Archivos .csv o .json", type=["csv", "json"], accept_multiple_files=True, key="archivos_lote",
    )
    procesar = st.button("⚙️ Procesar Lote", type="primary")

    if procesar:
        if not archivos:
            st.warning("Sube al menos un archivo .csv o .json antes de procesar.")
        else:
            shutil.rmtree(UPLOADS_DIR, ignore_errors=True)
            UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
            BATCH_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            resultados_totales = []
            archivos_csv = [a for a in archivos if a.name.lower().endswith(".csv")]
            archivos_json = [a for a in archivos if a.name.lower().endswith(".json")]

            with st.spinner("Procesando lote..."):
                for subido in archivos_csv:
                    ruta_csv = UPLOADS_DIR / subido.name
                    ruta_csv.write_bytes(subido.getvalue())
                    try:
                        resultados_totales.extend(process_csv_file(str(ruta_csv), str(BATCH_OUTPUT_DIR)))
                    except Exception as e:
                        st.error(f"Fallo procesando '{subido.name}': {type(e).__name__}: {e}")

                if archivos_json:
                    carpeta_json = UPLOADS_DIR / "json"
                    carpeta_json.mkdir(parents=True, exist_ok=True)
                    for subido in archivos_json:
                        (carpeta_json / subido.name).write_bytes(subido.getvalue())
                    try:
                        resultados_totales.extend(process_json_folder(str(carpeta_json), str(BATCH_OUTPUT_DIR)))
                    except Exception as e:
                        st.error(f"Fallo procesando los .json: {type(e).__name__}: {e}")

            st.session_state["ultimo_lote"] = generar_reporte_resumen(resultados_totales) if resultados_totales else None

    resumen_lote = st.session_state.get("ultimo_lote")
    if resumen_lote:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total piezas", resumen_lote["total_piezas"])
        col2.metric("Exitosas", resumen_lote["exitosas"])
        col3.metric("Fallidas", resumen_lote["fallidas"])
        col4.metric("Promedio ms/imagen", f"{resumen_lote['promedio_ms_por_imagen']:.1f}")

        fallidos = [r for r in resumen_lote["resultados"] if r["status"] == "FAIL"]
        for r in fallidos:
            st.warning(f"{r['origen']}: {r['error']}")

        st.subheader("Galería de resultados")
        exitosos = [r for r in resumen_lote["resultados"] if r["status"] == "OK" and r["output_path"]]
        if exitosos:
            columnas_galeria = st.columns(3)
            for i, r in enumerate(exitosos):
                with columnas_galeria[i % 3]:
                    st.image(r["output_path"], width="stretch", caption=r["origen"])
        else:
            st.info("Ninguna pieza se genero correctamente en este lote.")
    else:
        st.info("Sube un lote y presiona 'Procesar Lote' para ver los resultados aquí.")
