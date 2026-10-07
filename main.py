"""
main.py - orquestador principal del generador de invitaciones.

Pipeline: payload JSON -> LayoutDecisionEngine (plantilla + coordenadas + color
                          de categoria) -> CanvasEngine (Fondo -> Overlay degradado
                          -> Titulo/Fecha -> Subtitulo enmarcado -> Tarjetas de
                          ponentes -> Insignia de Maestria -> Patrocinador) -> PNG final.

El layout replica el sistema visual real de las piezas en assets/Templates/:
bloque de titulo arriba-izquierda (palabra de categoria en color de acento +
palabra grande en blanco) separado por una linea vertical del bloque de
fecha/lugar arriba-derecha; subtitulo/tema con marco de esquinas sobre la foto;
tarjetas de ponentes con borde de acento; insignia "Maestria <Categoria>".
"""

import json
import time
from pathlib import Path
from typing import List, Optional, Union

from assets_manager import get_brand_font_name
from canvas_engine import InvitationCanvasBuilder
from layout_engine import CATEGORY_COLORS, LayoutConfigError, LayoutDecisionEngine

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PAYLOAD_PATH = BASE_DIR / "payload.json"
DEFAULT_OUTPUT_PATH = BASE_DIR / "output" / "invitacion_render.png"
BACKGROUNDS_DIR = BASE_DIR / "assets" / "backgrounds"

TEXT_PRIMARY = (255, 255, 255)
TEXT_MUTED = (210, 210, 210)


class PipelineError(Exception):
    """Error de alto nivel del pipeline de generacion de invitaciones."""


def cargar_payload(path: Path) -> dict:
    if not path.is_file():
        raise PipelineError(f"No se encontro el archivo de payload: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as e:
        raise PipelineError(f"El payload '{path}' esta malformado: {e}")

    requeridos = ["marca", "palabra_categoria", "palabra_titulo", "tema_evento", "fecha_texto"]
    faltantes = [campo for campo in requeridos if campo not in payload]
    if faltantes:
        raise PipelineError(f"El payload '{path}' no tiene los campos requeridos: {faltantes}")

    return payload


def _normalizar_fecha(fecha_texto: Union[str, List[str]]) -> List[str]:
    """El bloque de fecha/lugar admite un string (una linea) o una lista de lineas apiladas."""
    if isinstance(fecha_texto, list):
        return [str(l) for l in fecha_texto]
    return [str(fecha_texto)]


def generar_invitacion(payload: dict, output_path: Path) -> Path:
    """
    Ejecuta el pipeline completo para un payload ya cargado:
    LayoutDecisionEngine decide caso/color de categoria, CanvasEngine renderiza
    por capas replicando el sistema visual de assets/Templates/.
    Devuelve la ruta del PNG generado.
    """
    decision_engine = LayoutDecisionEngine()
    decision = decision_engine.evaluate_payload(payload)

    try:
        config = decision_engine.load_layout_config(decision["case_id"])
    except LayoutConfigError as e:
        raise PipelineError(str(e))

    boxes = config["bounding_boxes"]
    accent = decision["accent_color"]

    # --- Tipografia de marca: Contegral+Finca -> Alexandria, solo Contegral ->
    # Montserrat, solo Finca -> Akwe Pro (regla de negocio confirmada por el cliente) ---
    marca_payload = payload.get("marca")
    font_black = get_brand_font_name(marca_payload, "black")
    font_bold = get_brand_font_name(marca_payload, "bold")
    font_regular = get_brand_font_name(marca_payload, "regular")

    builder = InvitationCanvasBuilder(
        safe_top=config["safe_area"]["top"],
        safe_bottom=config["safe_area"]["bottom"],
    )

    # --- Fondo + overlay degradado (oscuro arriba/abajo, foto visible al centro) ---
    # Prioridad: archivo explicito del payload -> seleccion dinamica por
    # categoria via AssetRepository -> color solido (ver CanvasEngine.load_background).
    background_file = payload.get("background_file")
    bg_path = (BACKGROUNDS_DIR / background_file) if background_file else None
    builder.load_background(str(bg_path) if bg_path else None, category=decision["categoria"])
    builder.apply_gradient_overlay()

    # --- Bloque de titulo centrado (como en las piezas reales): palabra de
    # categoria (acento) sobre palabra grande (blanca), alineadas a la derecha
    # contra un divisor del color de acento; fecha/direccion/lugar a la
    # izquierda del otro lado y los iconos de linea bajo el titular. Icono:
    # ambiguo sin sub_linea para Ganaderia/Avicola y sin definir para
    # co-marca/multi-categoria (ver AssetRepository.get_category_icon). Con
    # varias sub-lineas (ej. carne + leche) salen varios iconos. ---
    lockup = boxes["title_lockup"]
    sub_lineas = payload.get("sub_linea") or [None]
    if not isinstance(sub_lineas, list):
        sub_lineas = [sub_lineas]
    iconos = []
    for sub_linea in sub_lineas:
        icono = builder.asset_repo.get_category_icon(decision["marca"], decision["categoria"], sub_linea)
        if icono and str(icono) not in iconos:
            iconos.append(str(icono))
    lockup_bottom = builder.draw_title_lockup(
        payload["palabra_categoria"], payload["palabra_titulo"], _normalizar_fecha(payload["fecha_texto"]),
        category_font=get_brand_font_name(marca_payload, "medium"),
        headline_font=font_bold,
        date_strong_font=get_brand_font_name(marca_payload, "semibold"),
        date_font=font_regular,
        accent=accent, top_y=lockup["top_y"],
        category_size=lockup["category_size"], headline_size=lockup["headline_size"],
        date_size=lockup["date_size"], icon_paths=iconos, icon_size=lockup["icon_size"],
    )

    # --- Marco blanco abierto: el titulo del evento (antetitulo opcional en
    # color de linea + titulo) va sobre el borde superior; las ponencias,
    # ancladas abajo, tapan el borde inferior. Todo queda "envuelto" por las lineas. ---
    marco = boxes["frame"]
    fx0, fx1 = marco["side_margin"], builder.width - marco["side_margin"]
    titulo = builder.draw_event_title(
        payload.get("antetitulo", ""), payload["tema_evento"],
        kicker_font=font_black, title_font=font_bold, accent=accent,
        top_y=lockup_bottom + marco["gap_after_lockup"],
        kicker_size=marco["kicker_size"], title_size=marco["title_size"], max_width=fx1 - fx0 - 120,
    )
    gap_top = (titulo["gap_x0"], titulo["gap_x1"])

    y = titulo["bottom"]
    if decision["num_ponentes"] > 0 and "speaker_cards" in boxes:
        cards_box = boxes["speaker_cards"]
        args = dict(
            accent_color=accent, columns=cards_box.get("columns", 2), margin=fx0 + marco["cards_inset"], gap=marco["cards_gap"],
            name_font_path=font_bold, role_font_path=font_regular, topic_font_path=font_bold,
        )
        medida = builder.render_speaker_cards(decision["ponentes"], start_y=0, measure_only=True, **args)
        cards_top = max(titulo["bottom"] + 50, marco["cards_bottom"] - medida["bottom"])
        fila_top = cards_top + medida["last_row_top"]
        fila_alto = medida["last_row_bottom"] - medida["last_row_top"]
        builder.draw_content_frame(
            fx0, titulo["frame_y"], fx1, fila_top + int(fila_alto * 0.62),
            gap_top=gap_top, gap_bottom=(medida["last_row_x0"], medida["last_row_x1"]), color=TEXT_PRIMARY,
        )
        y = builder.render_speaker_cards(decision["ponentes"], start_y=cards_top, **args)["bottom"]
    else:
        builder.draw_content_frame(
            fx0, titulo["frame_y"], fx1, marco["empty_bottom"],
            gap_top=gap_top, gap_bottom=(fx0 + 150, fx1 - 150), color=TEXT_PRIMARY,
        )
        y = marco["empty_bottom"]

    # --- Insignia Maestria: el logo real (assets/Logos Maestria/) va grande y
    # reemplaza al texto, como en las piezas reales. Sin logo para esta
    # marca+categoria (co-marca, categoria sin logo) se dibuja la insignia de
    # texto; el payload puede sobreescribir su etiqueta. ---
    maestria_box = boxes["maestria_badge"]
    badge_y = max(y + 30, maestria_box["y"])
    logo_maestria = builder.asset_repo.get_maestria_logo(decision["marca"], decision["categoria"])
    resultado_logo = None
    if logo_maestria:
        resultado_logo = builder.paste_image(
            logo_maestria, x=builder.width / 2, y=badge_y, max_size=(780, 170), center_x=True,
        )
    if resultado_logo:
        y = resultado_logo[1] + resultado_logo[3]
    else:
        maestria_label = payload.get("maestria_label") or decision["maestria_label"]
        y = builder.draw_maestria_badge(
            maestria_label, badge_y, accent,
            title_font_path=font_black, category_font_path=font_bold, tagline_font_path=font_regular,
        )

    # --- Pata de patrocinadores ---
    # Prioridad: `patas` (grupos "Apoya"/"Invita" con sus logos) -> apoyo_logo /
    # apoyos_texto explicitos (fallback de texto, validado por el Caso 4 de
    # test_all_cases.py). Sin ninguno de los anteriores no se dibuja pata.
    sponsor_box = boxes["sponsor"]
    grupos_pata = [
        {"label": g.get("tipo", "Apoya"), "logos": g.get("logos", [])} for g in payload.get("patas", [])
    ]

    if any(g["logos"] for g in grupos_pata):
        es_gris = tuple(accent) == CATEGORY_COLORS["general"]
        builder.render_sponsor_pata(
            grupos_pata, y_position=max(y + 30, sponsor_box["y"]),
            frame_color=(255, 255, 255) if es_gris else accent,
            label_color=CATEGORY_COLORS["porcicola"] if es_gris else accent,
            header_logo=builder.asset_repo.get_logo("grupo_bios"),
            label_font_path=font_bold,
        )
    else:
        apoyo_sponsor = payload.get("apoyo_logo") or payload.get("apoyos_texto")
        if apoyo_sponsor:
            builder.render_sponsor_fallback(apoyo_sponsor, y_position=sponsor_box["y"], font_path=font_regular)

    return Path(builder.save(str(output_path)))


def main(payload_path: Optional[Path] = None, output_path: Optional[Path] = None) -> Optional[Path]:
    payload_path = Path(payload_path) if payload_path else DEFAULT_PAYLOAD_PATH
    output_path = Path(output_path) if output_path else DEFAULT_OUTPUT_PATH

    inicio = time.perf_counter()
    try:
        payload = cargar_payload(payload_path)
        resultado = generar_invitacion(payload, output_path)
    except PipelineError as e:
        print(f"[ERROR] {e}")
        return None

    duracion_ms = (time.perf_counter() - inicio) * 1000
    print(f"Invitacion generada: {resultado} ({duracion_ms:.1f} ms)")
    return resultado


if __name__ == "__main__":
    main()
