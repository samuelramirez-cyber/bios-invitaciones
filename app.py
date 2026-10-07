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
    "Día del pollito": ("Día", "del Pollito"),
    "Día del ganadero": ("Día", "del Ganadero"),
    "Día del acuicultor": ("Día", "del Acuicultor"),
    "Día del caballo (Cinta Azul)": ("Día del Caballo", "Cinta Azul"),
    "Día del caballo (Rodeo)": ("Día del Caballo", "Rodeo"),
    "Día de lechón": ("Día de", "Lechón"),
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
    col_form, col_resultado = st.columns([1, 2], gap="large")

    with col_form:
        st.subheader("Datos del evento")

        marca_lider = st.selectbox("Marca líder que convoca", MARCA_LIDER_OPCIONES, key="marca_lider")
        marca_lider_otro = ""
        if marca_lider == "Otro":
            marca_lider_otro = st.text_input("Especifique la marca/programa", key="marca_lider_otro")
        if marca_lider in MARCA_LIDER_ASUNCION:
            st.caption("⚠️ Tipografía/logo asumidos para este programa — pendiente de confirmar con el cliente.")
        marca = MARCA_LIDER_A_MARCA.get(marca_lider, [])

        categoria = st.multiselect(
            "Línea de negocio (elige varias si el evento cubre mas de una)",
            CATEGORIAS, default=[CATEGORIAS[0]], key="categoria",
        )
        if len(categoria) > 1:
            st.caption("Evento multi-linea: se usa un color neutro y la insignia lista todas las categorias elegidas.")

        sub_linea = None
        if len(categoria) == 1 and categoria[0] in SUB_LINEAS_POR_CATEGORIA:
            opciones_sub = SUB_LINEAS_POR_CATEGORIA[categoria[0]]
            sub_linea = st.radio(f"Sub-línea de {categoria[0]}", opciones_sub, key="sub_linea", horizontal=True)

        tipo_evento = st.radio("Tipo de evento", TIPOS_EVENTO, key="tipo_evento")
        st.caption("Los eventos tipo Encuentro o Jornada no se gestionan por este formulario: van directo con los jefes de mercadeo.")

        titulo_evento = fecha = hora = lugar = ""
        tipo_activacion = None
        descripcion_promocion = ""
        fecha_inicio_promo = fecha_fin_promo = None
        unidades_disponibles = ""

        if tipo_evento in TIPOS_CON_CHARLAS:
            titulo_evento = st.text_input("Título del evento", key="titulo", placeholder="Ej. Manejo Reproductivo Bovino")
            fecha = st.text_input("Fecha", key="fecha", placeholder="Ej. 24 de Septiembre de 2026")
            hora = st.text_input("Hora", key="hora", placeholder="Ej. 3:00 p.m.")
            lugar = st.text_input("Lugar", key="lugar", placeholder="Ej. Auditorio Central")
        else:
            tipo_activacion = st.selectbox("Tipo de activación", TIPOS_ACTIVACION, key="tipo_activacion")
            descripcion_promocion = st.text_area(
                "Describa en qué consiste la promoción", key="descripcion_promocion",
                placeholder=(
                    'Ej. "Por la compra de X unidades, lleva Y gratis" o "Nuestros expertos estarán '
                    'con nosotros, visítanos para asesorarte. Tendremos regalos y sorpresas por tu '
                    'compra en la marca."'
                ),
            )
            st.caption("Este texto queda sujeto a validación humana antes de publicarse.")
            col_fi, col_ff = st.columns(2)
            fecha_inicio_promo = col_fi.date_input("Fecha inicial de la promoción", key="fecha_inicio_promo")
            fecha_fin_promo = col_ff.date_input("Fecha final de la promoción", key="fecha_fin_promo")
            unidades_disponibles = st.text_area(
                "Unidades disponibles de cada referencia involucrada", key="unidades_disponibles",
                placeholder="Ej. Ref. 1234 - 500 unidades; Ref. 5678 - 300 unidades",
            )
            st.caption("Dato administrativo — no se imprime en la pieza.")

        st.markdown("**Imagen de fondo**")
        archivo_fondo_propio = st.file_uploader(
            "Subir mi propia imagen de fondo (opcional, tiene prioridad sobre la galería)",
            type=["png", "jpg", "jpeg", "webp"], key="fondo_propio",
        )
        fondos_disponibles = _listar_fondos()
        fondo_elegido = st.session_state.get("fondo_elegido")
        if fondo_elegido and not (BACKGROUNDS_DIR / fondo_elegido).is_file():
            fondo_elegido = None
        if archivo_fondo_propio is not None:
            st.caption("Se usará la imagen que subiste.")
        elif fondo_elegido:
            miniatura_actual = _miniatura_fondo(BACKGROUNDS_DIR / fondo_elegido)
            if miniatura_actual:
                st.image(miniatura_actual, width=140)
            st.caption(f"Fondo elegido: {fondo_elegido}")
        else:
            st.caption("Automático: se elige al azar uno acorde a la línea de negocio. Revisa la vista previa o elige uno de la galería.")
        palabras_linea = [p for linea in categoria for p in PALABRAS_FONDO_POR_LINEA.get(linea, [])]
        fondos_de_la_linea = [f for f in fondos_disponibles if any(p in f.stem.lower() for p in palabras_linea)]
        mostrar_todos = st.checkbox("Mostrar fondos de todas las líneas", key="fondos_todos")
        if mostrar_todos or not fondos_de_la_linea:
            fondos_galeria = fondos_disponibles
            if not mostrar_todos:
                st.caption("No hay fondos específicos para la línea elegida; se muestran todos.")
        else:
            fondos_galeria = fondos_de_la_linea
        if fondo_elegido and archivo_fondo_propio is None and (BACKGROUNDS_DIR / fondo_elegido) not in fondos_galeria:
            st.warning("El fondo elegido no corresponde a la línea de negocio seleccionada.")
        with st.expander(f"Elegir de la galería ({len(fondos_galeria)} fondos)"):
            st.button("Automático (según línea de negocio)", key="fondo_auto", on_click=_elegir_fondo, args=(None,))
            columnas_fondos = st.columns(2)
            for i, ruta_fondo in enumerate(fondos_galeria):
                with columnas_fondos[i % 2]:
                    miniatura = _miniatura_fondo(ruta_fondo)
                    if miniatura:
                        st.image(miniatura, width="stretch")
                    st.caption(ruta_fondo.stem.replace("_", " "))
                    st.button("Usar este", key=f"fondo_{ruta_fondo.name}", on_click=_elegir_fondo, args=(ruta_fondo.name,))

        apoyos_texto = st.text_input(
            "Pata / Sponsors (texto de apoyo, si no subes logos abajo)",
            key="apoyos_texto", placeholder="Ej. Con el apoyo de Contegral",
        )
        st.caption("Pata: sube los logos de las marcas aliadas (tienen prioridad sobre el texto de arriba).")
        archivos_apoyan = st.file_uploader(
            "Logos que APOYAN", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="logos_apoyan",
        )
        archivos_invitan = st.file_uploader(
            "Logos que INVITAN", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="logos_invitan",
        )

        ponentes: List[Dict[str, Any]] = []
        if tipo_evento in TIPOS_CON_CHARLAS:
            st.divider()
            st.subheader("Charlas")
            num_charlas = st.radio(
                "¿Cuántas charlas tendrá el evento?", list(range(1, MAX_CHARLAS + 1)),
                key="num_charlas", horizontal=True,
            )
            for i in range(int(num_charlas)):
                with st.expander(f"Charla {i + 1}", expanded=True):
                    titulo_charla = st.text_input("Título de la charla", key=f"charla_{i}_titulo")
                    expositor = st.text_input("Nombre del expositor", key=f"charla_{i}_expositor")
                    empresa_expositor = st.text_input("Empresa del expositor", key=f"charla_{i}_empresa")
                    foto_subida = st.file_uploader(
                        "Foto del expositor (opcional)", type=["png", "jpg", "jpeg"], key=f"charla_{i}_foto",
                    )
                    if expositor.strip():
                        ponentes.append({
                            "name": expositor, "role": "", "empresa": empresa_expositor, "tema": titulo_charla,
                            "_foto_subida": foto_subida,
                        })

        st.divider()
        st.subheader("Información administrativa")
        centro_operativo = st.text_input("Centro Operativo", key="centro_operativo")
        observaciones = st.text_area("Observaciones adicionales", key="observaciones")

        st.divider()
        generar = st.button("🎨 Generar Invitación", type="primary", width="stretch")

    with col_resultado:
        st.subheader("Resultado")

        if generar:
            if tipo_evento in TIPOS_CON_CHARLAS:
                campo_obligatorio_ok = bool(titulo_evento.strip())
                mensaje_falta = "El campo 'Título del evento' es obligatorio."
            else:
                campo_obligatorio_ok = bool(descripcion_promocion.strip())
                mensaje_falta = "El campo 'Describa en qué consiste la promoción' es obligatorio."

            if not campo_obligatorio_ok:
                st.error(mensaje_falta)
            elif not categoria:
                st.error("Selecciona al menos una Línea de negocio.")
            else:
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

                patas = []
                for tipo_pata, archivos_pata in (("Apoya", archivos_apoyan), ("Invita", archivos_invitan)):
                    if not archivos_pata:
                        continue
                    carpeta_aliados = UPLOADS_DIR / "aliados"
                    carpeta_aliados.mkdir(parents=True, exist_ok=True)
                    rutas = []
                    for subido in archivos_pata:
                        ruta_logo = carpeta_aliados / f"{tipo_pata.lower()}_{subido.name}"
                        ruta_logo.write_bytes(subido.getvalue())
                        rutas.append(str(ruta_logo))
                    patas.append({"tipo": tipo_pata, "logos": rutas})

                # Resolver la foto subida de cada ponente (si hay) a una ruta real en disco.
                carpeta_fotos_ponentes = UPLOADS_DIR / "ponentes"
                ponentes_resueltos = []
                for p in ponentes:
                    p = dict(p)
                    foto_subida = p.pop("_foto_subida", None)
                    if foto_subida is not None:
                        carpeta_fotos_ponentes.mkdir(parents=True, exist_ok=True)
                        ruta_foto = carpeta_fotos_ponentes / f"{int(time.time() * 1000)}_{foto_subida.name}"
                        ruta_foto.write_bytes(foto_subida.getvalue())
                        p["photo"] = str(ruta_foto)
                    else:
                        p["photo"] = ""
                    ponentes_resueltos.append(p)

                if tipo_evento in TIPOS_CON_CHARLAS:
                    palabra_categoria, palabra_titulo = HEADLINE_POR_TIPO_EVENTO[tipo_evento]
                    tema_evento = titulo_evento
                    fecha_texto = [v for v in (fecha, hora, lugar) if v]
                else:
                    palabra_categoria, palabra_titulo = HEADLINE_POR_ACTIVACION.get(
                        tipo_activacion, ("Actividad", "Promocional"),
                    )
                    tema_evento = descripcion_promocion
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
                    "fecha_texto": fecha_texto,
                    "ponentes": ponentes_resueltos,
                    "apoyos_texto": apoyos_texto,
                    # Metadata administrativa del formulario - no se dibuja en la pieza.
                    "marca_lider": marca_lider_otro if marca_lider == "Otro" else marca_lider,
                    "centro_operativo": centro_operativo,
                    "observaciones": observaciones,
                }
                if archivo_fondo_propio is not None:
                    carpeta_fondos = UPLOADS_DIR / "fondos"
                    carpeta_fondos.mkdir(parents=True, exist_ok=True)
                    ruta_fondo_propio = carpeta_fondos / f"{int(time.time() * 1000)}_{archivo_fondo_propio.name}"
                    ruta_fondo_propio.write_bytes(archivo_fondo_propio.getvalue())
                    payload["background_file"] = str(ruta_fondo_propio)
                elif fondo_elegido:
                    payload["background_file"] = fondo_elegido
                if sub_linea:
                    payload["sub_linea"] = sub_linea
                if patas:
                    payload["patas"] = patas
                if tipo_evento == "Actividad Promocional":
                    payload["tipo_activacion"] = tipo_activacion
                    payload["unidades_disponibles"] = unidades_disponibles

                nombre_archivo = f"invitacion_{int(time.time() * 1000)}.png"
                destino = OUTPUT_DIR / nombre_archivo

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
            st.metric("Tiempo de renderizado", f"{resultado['duracion_ms']:.1f} ms")
            _mostrar_mensajes_capturados(resultado["mensajes"])

            with open(resultado["ruta"], "rb") as f:
                st.download_button(
                    "⬇️ Descargar PNG",
                    data=f.read(),
                    file_name=Path(resultado["ruta"]).name,
                    mime="image/png",
                    width="stretch",
                )
        else:
            st.info("Completa el formulario y presiona 'Generar Invitación' para ver la vista previa aquí.")


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
