"""
app.py - Interfaz visual (Streamlit) del generador de invitaciones.

Reusa el mismo pipeline que main.py / webhook_server.py / batch_processor.py
(LayoutDecisionEngine + CanvasEngine via main.generar_invitacion), para que
la interfaz nunca se desincronice del motor de renderizado. Cualquier
[AVISO]/[ERROR] que el pipeline ya imprime por consola (fallback de fondo,
foto de ponente, logo, config) se captura y se muestra como alerta visual.
"""

import contextlib
import io
import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

import main as pipeline
from batch_processor import generar_reporte_resumen, process_csv_file, process_json_folder

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output" / "streamlit"
BATCH_OUTPUT_DIR = OUTPUT_DIR / "batch"
UPLOADS_DIR = OUTPUT_DIR / "_uploads"

MARCAS = ["Contegral", "Finca"]
CATEGORIAS = ["Ganadería", "Porcicultura", "Avicultura", "Acuícola", "Cunicultura", "Equinos", "Campo"]
TIPOS_EVENTO = ["Charla", "Encuentro", "Día de Campo"]

# Categorias cuyo icono de linea real (assets/icons/{Marca}/) es ambiguo sin
# una sub-linea explicita - ver AssetRepository.get_category_icon().
SUB_LINEAS_POR_CATEGORIA = {
    "Ganadería": ["Carne", "Leche"],
    "Avicultura": ["Ponedoras", "Engorde"],
}

# Palabra grande (headline, blanca) derivada del tipo de evento - el usuario
# solo elige la palabra pequena (categoria de evento); ver main.py / assets/Templates/.
HEADLINE_POR_TIPO = {
    "Charla": "Maestra",
    "Encuentro": "Tecnico",
    "Día de Campo": "Ganadero",
}

MAX_PONENTES = 4

st.set_page_config(
    page_title="Generador Automatizado de Invitaciones - Grupo Bios",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _construir_payload_formulario(datos: Dict[str, Any], ponentes: List[Dict[str, str]]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "marca": datos["marca"],
        "categoria": datos["categoria"],
        "palabra_categoria": datos["tipo_evento"],
        "palabra_titulo": HEADLINE_POR_TIPO.get(datos["tipo_evento"], "Maestra"),
        "tema_evento": datos["titulo"],
        "fecha_texto": [v for v in (datos["fecha"], datos["hora"], datos["lugar"]) if v],
        "ponentes": ponentes,
        "apoyos_texto": datos["apoyos_texto"],
    }
    if datos.get("sub_linea"):
        payload["sub_linea"] = datos["sub_linea"]
    if datos.get("logos_aliados"):
        payload["logos_aliados"] = datos["logos_aliados"]
    return payload


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

        marca = st.multiselect(
            "Marca (elige ambas si el evento es co-marca)",
            MARCAS, default=[MARCAS[0]], key="marca",
        )
        if len(marca) > 1:
            st.caption("Evento co-marca: se usa la tipografia Alexandria (regla Contegral+Finca).")
        categoria = st.multiselect(
            "Categoría (elige varias si el evento cubre mas de una linea)",
            CATEGORIAS, default=[CATEGORIAS[0]], key="categoria",
        )
        if len(categoria) > 1:
            st.caption("Evento multi-linea: se usa un color neutro y la insignia lista todas las categorias elegidas.")

        # El icono real de linea (assets/icons/{Marca}/) es ambiguo para
        # Ganaderia/Avicultura sin esta sub-linea - solo aplica cuando hay
        # exactamente una categoria seleccionada y esa categoria la necesita.
        sub_linea = None
        if len(categoria) == 1 and categoria[0] in SUB_LINEAS_POR_CATEGORIA:
            opciones_sub = SUB_LINEAS_POR_CATEGORIA[categoria[0]]
            sub_linea = st.radio(f"Sub-línea de {categoria[0]}", opciones_sub, key="sub_linea", horizontal=True)

        tipo_evento = st.selectbox("Tipo de evento", TIPOS_EVENTO, key="tipo_evento")

        titulo = st.text_input("Título del evento", key="titulo", placeholder="Ej. Manejo Reproductivo Bovino")
        fecha = st.text_input("Fecha", key="fecha", placeholder="Ej. 24 de Septiembre de 2026")
        hora = st.text_input("Hora", key="hora", placeholder="Ej. 3:00 p.m.")
        lugar = st.text_input("Lugar", key="lugar", placeholder="Ej. Auditorio Central")
        apoyos_texto = st.text_input(
            "Pata / Sponsors (texto de apoyo, si no subes logos abajo)",
            key="apoyos_texto", placeholder="Ej. Con el apoyo de Contegral",
        )
        archivos_logos_aliados = st.file_uploader(
            "Logos de marcas aliadas (patrocinadores) para la pata - opcional, tiene prioridad sobre el texto de arriba",
            type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="logos_aliados",
        )

        st.divider()
        st.subheader("Ponentes")
        num_ponentes = st.number_input("Cantidad de ponentes", min_value=0, max_value=MAX_PONENTES, value=0, step=1, key="num_ponentes")

        ponentes: List[Dict[str, str]] = []
        for i in range(int(num_ponentes)):
            with st.expander(f"Ponente {i + 1}", expanded=True):
                nombre = st.text_input("Nombre", key=f"ponente_{i}_nombre")
                cargo = st.text_input("Cargo", key=f"ponente_{i}_cargo")
                empresa = st.text_input("Empresa", key=f"ponente_{i}_empresa")
                tema = st.text_input("Tema de la charla", key=f"ponente_{i}_tema")
                foto_subida = st.file_uploader(
                    "Foto (opcional)", type=["png", "jpg", "jpeg"], key=f"ponente_{i}_foto",
                )
                if nombre.strip():
                    ponentes.append({
                        "name": nombre, "role": cargo, "empresa": empresa, "tema": tema,
                        "_foto_subida": foto_subida,
                    })

        st.divider()
        generar = st.button("🎨 Generar Invitación", type="primary", width="stretch")

    with col_resultado:
        st.subheader("Resultado")

        if generar:
            if not titulo.strip():
                st.error("El campo 'Título del evento' es obligatorio.")
            elif not marca:
                st.error("Selecciona al menos una Marca.")
            else:
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

                rutas_logos_aliados = []
                if archivos_logos_aliados:
                    carpeta_aliados = UPLOADS_DIR / "aliados"
                    carpeta_aliados.mkdir(parents=True, exist_ok=True)
                    for subido in archivos_logos_aliados:
                        ruta_logo = carpeta_aliados / subido.name
                        ruta_logo.write_bytes(subido.getvalue())
                        rutas_logos_aliados.append(str(ruta_logo))

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
                ponentes = ponentes_resueltos

                datos_formulario = {
                    "marca": marca, "categoria": categoria, "tipo_evento": tipo_evento,
                    "titulo": titulo, "fecha": fecha, "hora": hora, "lugar": lugar,
                    "apoyos_texto": apoyos_texto, "sub_linea": sub_linea,
                    "logos_aliados": rutas_logos_aliados,
                }
                payload = _construir_payload_formulario(datos_formulario, ponentes)

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
