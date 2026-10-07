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
from layout_engine import LayoutConfigError, LayoutDecisionEngine

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
    builder.apply_grain_texture()

    # --- Bloque de titulo centrado (como en las piezas reales): palabra de
    # categoria (acento) sobre palabra grande (blanca), alineadas a la derecha
    # contra un divisor del color de acento; fecha/lugar a la izquierda del
    # otro lado y el icono de linea bajo el titular. Icono: ambiguo sin
    # sub_linea para Ganaderia/Avicola y sin definir para co-marca/multi-categoria
    # (ver AssetRepository.get_category_icon) ---
    lockup = boxes["title_lockup"]
    icono_linea = builder.asset_repo.get_category_icon(decision["marca"], decision["categoria"], payload.get("sub_linea"))
    lockup_bottom = builder.draw_title_lockup(
        payload["palabra_categoria"], payload["palabra_titulo"], _normalizar_fecha(payload["fecha_texto"]),
        category_font=get_brand_font_name(marca_payload, "medium"),
        headline_font=font_bold,
        date_strong_font=get_brand_font_name(marca_payload, "semibold"),
        date_font=font_regular,
        accent=accent, top_y=lockup["top_y"],
        category_size=lockup["category_size"], headline_size=lockup["headline_size"],
        date_size=lockup["date_size"], icon_path=str(icono_linea) if icono_linea else None,
        icon_size=lockup["icon_size"],
    )

    # --- Subtitulo/tema, enmarcado con corchetes de esquina (siempre debajo del bloque de titulo) ---
    sub_box = dict(boxes["subtitle"])
    sub_box["y"] = max(sub_box["y"], lockup_bottom + sub_box["frame_margin"] + 40)
    ancho_sub, alto_sub, _ = builder.measure_wrapped_text(
        payload["tema_evento"], font_bold, sub_box["font_size"], sub_box["max_width"],
    )
    margin = sub_box["frame_margin"]
    frame_x0 = (builder.width - ancho_sub) / 2 - margin
    frame_x1 = (builder.width + ancho_sub) / 2 + margin
    frame_y0 = sub_box["y"] - margin
    frame_y1 = sub_box["y"] + alto_sub + margin
    builder.draw_bracket_frame(int(frame_x0), int(frame_y0), int(frame_x1), int(frame_y1), TEXT_PRIMARY)
    y = builder.draw_wrapped_text(
        payload["tema_evento"], font_bold, sub_box["max_width"], sub_box["y"], sub_box["font_size"], TEXT_PRIMARY,
    )

    # --- Tarjetas de ponentes (nombre, cargo, empresa, tema - borde color de categoria) ---
    if decision["num_ponentes"] > 0 and "speaker_cards" in boxes:
        cards_box = boxes["speaker_cards"]
        cards_start_y = max(y + 40, cards_box["start_y"])
        y = builder.draw_text_block(
            ["Ponencias"], font_black, 32, 40, cards_start_y, TEXT_PRIMARY, "left",
        )
        y = builder.render_speaker_cards(
            decision["ponentes"],
            start_y=y + 16,
            accent_color=accent,
            columns=cards_box.get("columns", 2),
            name_font_path=font_bold, role_font_path=font_regular, topic_font_path=font_bold,
        )

    # --- Insignia "Maestria <Categoria>" (el payload puede sobreescribir la etiqueta derivada) ---
    maestria_box = boxes["maestria_badge"]
    maestria_label = payload.get("maestria_label") or decision["maestria_label"]
    y = builder.draw_maestria_badge(
        maestria_label, max(y + 30, maestria_box["y"]), accent,
        title_font_path=font_black, category_font_path=font_bold, tagline_font_path=font_regular,
    )

    # --- Logo real de la insignia (assets/Logos Maestria/), si existe para esta
    # marca+categoria (marca co-marca o categoria sin logo definido -> None,
    # el texto de arriba ya cubre ese caso) ---
    logo_maestria = builder.asset_repo.get_maestria_logo(decision["marca"], decision["categoria"])
    if logo_maestria:
        resultado_logo = builder.paste_image(
            logo_maestria, x=builder.width / 2, y=y + 10, max_size=(220, 100), center_x=True,
        )
        if resultado_logo:
            y = resultado_logo[1] + resultado_logo[3]

    # --- Logos / fallback de patrocinador ---
    # Prioridad: logos_aliados (varios logos subidos, fila completa) ->
    # apoyo_logo explicito -> apoyos_texto explicito (asi el payload sigue
    # mandando, como en el Caso 4 de test_all_cases.py que valida a proposito
    # el fallback a texto) -> logo de marca via AssetRepository, solo si el
    # payload no especifico ninguno de los anteriores.
    sponsor_box = boxes["sponsor"]
    logos_aliados = payload.get("logos_aliados")
    if logos_aliados:
        builder.render_sponsor_logos_row(logos_aliados, y_position=max(y + 20, sponsor_box["y"]))
    else:
        apoyo_sponsor = payload.get("apoyo_logo") or payload.get("apoyos_texto")
        if not apoyo_sponsor:
            logo_marca = builder.asset_repo.get_logo(decision["marca"])
            apoyo_sponsor = str(logo_marca) if logo_marca else None
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
