"""
asset_processor.py - utilitario de normalizacion de assets para el CanvasEngine.

Intenta convertir el vectorial 'Referentes Invitaciones.ai' (los .ai de Adobe
Illustrator llevan estructura PDF embebida) a PNG de alta resolucion usando
inkscape o pdf2image si estan instalados en el sistema. Si ninguna herramienta
esta disponible (o el archivo no existe/falla al parsear), activa un fallback
que genera placeholders transparentes con Pillow para no bloquear el pipeline.

Tambien reorganiza imagenes sueltas de FONDOS/ hacia assets/backgrounds/ con
nombres limpios en minusculas.
"""

import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent  # invitaciones/
ASSETS_DIR = BASE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
BACKGROUNDS_DIR = ASSETS_DIR / "backgrounds"
SPEAKERS_DIR = ASSETS_DIR / "speakers"
FONDOS_DIR = BASE_DIR / "FONDOS"
AI_SOURCE_FILE = BASE_DIR / "Referentes Invitaciones.ai"
AI_EXPORT_DIR = ASSETS_DIR / "_ai_export"
FONT_PATH = ASSETS_DIR / "fonts" / "Arial-Bold.ttf"

LOGO_COLOR_MAP = {
    "logo_contegral.png": (183, 28, 28),
    "logo_finca.png": (27, 94, 32),
    "logo_grupo_bios.png": (55, 71, 79),
}
MAESTRIA_COLOR_MAP = {
    "maestria_ganadera.png": (110, 78, 43),
    "maestria_porcicola.png": (194, 24, 91),
    "maestria_avicola.png": (245, 127, 23),
}
SPEAKER_PLACEHOLDER_NAME = "speaker_default.png"
FONDOS_EXTENSIONES_VALIDAS = {".jpg", ".jpeg", ".png", ".webp"}


# ---------------------------------------------------------------------------
# Deteccion e intento de conversion del .ai (estructura PDF)
# ---------------------------------------------------------------------------

def _inkscape_disponible() -> bool:
    return shutil.which("inkscape") is not None


def _pdf2image_disponible() -> bool:
    try:
        import pdf2image  # noqa: F401
        return True
    except ImportError:
        return False


def intentar_conversion_ai(output_dir: Path = AI_EXPORT_DIR) -> bool:
    """
    Intenta convertir AI_SOURCE_FILE a PNG de alta resolucion via inkscape o
    pdf2image. No lanza excepcion si el archivo no existe o la conversion
    falla: devuelve False para que el llamador active el fallback.
    """
    if not AI_SOURCE_FILE.is_file():
        print(f"[AVISO] No se encontro '{AI_SOURCE_FILE.name}' en la raiz del proyecto; se omite conversion vectorial.")
        return False

    if _inkscape_disponible():
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            destino = output_dir / f"{AI_SOURCE_FILE.stem}.png"
            subprocess.run(
                [
                    "inkscape", str(AI_SOURCE_FILE),
                    "--export-type=png",
                    f"--export-filename={destino}",
                    "--export-dpi=300",
                ],
                check=True, capture_output=True,
            )
            print(f"[OK] '{AI_SOURCE_FILE.name}' convertido via inkscape -> {destino}")
            return True
        except (subprocess.SubprocessError, OSError) as e:
            print(f"[AVISO] inkscape esta instalado pero fallo la conversion: {e}")

    if _pdf2image_disponible():
        try:
            from pdf2image import convert_from_path
            output_dir.mkdir(parents=True, exist_ok=True)
            paginas = convert_from_path(str(AI_SOURCE_FILE), dpi=300)
            for i, pagina in enumerate(paginas, start=1):
                destino = output_dir / f"{AI_SOURCE_FILE.stem}_{i}.png"
                pagina.save(destino)
                print(f"[OK] '{AI_SOURCE_FILE.name}' (pagina {i}) convertido via pdf2image -> {destino}")
            return True
        except Exception as e:
            print(f"[AVISO] pdf2image esta instalado pero fallo la conversion: {e}")

    print("[AVISO] Ni inkscape ni pdf2image estan disponibles; se activa el fallback de placeholders.")
    return False


# ---------------------------------------------------------------------------
# Fallback: placeholders transparentes generados con Pillow
# ---------------------------------------------------------------------------

def _texto_centrado(draw: ImageDraw.ImageDraw, texto: str, font, size: Tuple[int, int], color: Tuple[int, int, int, int]):
    bbox = draw.textbbox((0, 0), texto, font=font)
    ancho, alto = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size[0] - ancho) / 2 - bbox[0]
    y = (size[1] - alto) / 2 - bbox[1]
    draw.text((x, y), texto, font=font, fill=color)


def _cargar_fuente(size: int) -> ImageFont.ImageFont:
    if FONT_PATH.is_file():
        return ImageFont.truetype(str(FONT_PATH), size)
    print(f"[AVISO] Fuente '{FONT_PATH}' no encontrada; usando fuente por defecto de Pillow.")
    return ImageFont.load_default()


def _generar_placeholder_logo(nombre_archivo: str, color: Tuple[int, int, int], destino: Path):
    size = (400, 400)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radio = 180
    cx, cy = size[0] / 2, size[1] / 2
    draw.ellipse((cx - radio, cy - radio, cx + radio, cy + radio), fill=color + (255,))

    marca = nombre_archivo.replace("logo_", "").replace(".png", "").replace("_", " ")
    iniciales = "".join(palabra[0] for palabra in marca.split()[:2]).upper()
    font = _cargar_fuente(96)
    _texto_centrado(draw, iniciales, font, size, (255, 255, 255, 255))

    img.save(destino)


def _generar_placeholder_icono(nombre_archivo: str, color: Tuple[int, int, int], destino: Path):
    size = (320, 320)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margen = 20
    draw.rounded_rectangle(
        (margen, margen, size[0] - margen, size[1] - margen), radius=48, fill=color + (255,)
    )

    etiqueta = nombre_archivo.replace("maestria_", "").replace(".png", "").upper()[:3]
    font = _cargar_fuente(72)
    _texto_centrado(draw, etiqueta, font, size, (255, 255, 255, 255))

    img.save(destino)


def _generar_placeholder_avatar(destino: Path):
    size = (400, 400)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.ellipse((0, 0, size[0], size[1]), fill=(158, 158, 158, 255))
    draw.ellipse((130, 90, 270, 230), fill=(207, 207, 207, 255))
    draw.pieslice((70, 220, 330, 480), start=180, end=360, fill=(207, 207, 207, 255))

    img.save(destino)


def generate_placeholder_assets() -> List[Path]:
    """Genera logos, iconos de maestria y avatar neutro con fondo transparente."""
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    SPEAKERS_DIR.mkdir(parents=True, exist_ok=True)

    generados: List[Path] = []

    for nombre_archivo, color in LOGO_COLOR_MAP.items():
        destino = ICONS_DIR / nombre_archivo
        _generar_placeholder_logo(nombre_archivo, color, destino)
        generados.append(destino)

    for nombre_archivo, color in MAESTRIA_COLOR_MAP.items():
        destino = ICONS_DIR / nombre_archivo
        _generar_placeholder_icono(nombre_archivo, color, destino)
        generados.append(destino)

    destino_avatar = SPEAKERS_DIR / SPEAKER_PLACEHOLDER_NAME
    _generar_placeholder_avatar(destino_avatar)
    generados.append(destino_avatar)

    return generados


# ---------------------------------------------------------------------------
# Reorganizacion de FONDOS/ -> assets/backgrounds/
# ---------------------------------------------------------------------------

def _slug_limpio(nombre_original: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", nombre_original.lower()).strip("_")
    if not slug:
        slug = "fondo"
    if not slug.startswith("fondo"):
        slug = f"fondo_{slug}"
    return slug


def reorganizar_fondos() -> int:
    """Mueve imagenes de FONDOS/ a assets/backgrounds/ con nombres limpios y numerados."""
    if not FONDOS_DIR.is_dir():
        print(f"[AVISO] No se encontro la carpeta '{FONDOS_DIR.name}' en la raiz del proyecto; se omite reorganizacion.")
        return 0

    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    contador_por_slug = {}
    movidos = 0

    for archivo in sorted(FONDOS_DIR.iterdir()):
        if not archivo.is_file() or archivo.suffix.lower() not in FONDOS_EXTENSIONES_VALIDAS:
            continue

        slug = _slug_limpio(archivo.stem)
        contador_por_slug[slug] = contador_por_slug.get(slug, 0) + 1
        nuevo_nombre = f"{slug}_{contador_por_slug[slug]:02d}{archivo.suffix.lower()}"
        destino = BACKGROUNDS_DIR / nuevo_nombre

        shutil.move(str(archivo), str(destino))
        print(f"[OK] Movido: {archivo.name} -> assets/backgrounds/{nuevo_nombre}")
        movidos += 1

    return movidos


# ---------------------------------------------------------------------------
# Reporte y orquestacion
# ---------------------------------------------------------------------------

def generar_reporte(conversion_lograda: bool, placeholders: List[Path], fondos_movidos: int):
    total = len(placeholders) + fondos_movidos
    print("\n=== Reporte de normalizacion de assets ===")
    print(f"Conversion vectorial (.ai): {'lograda via herramienta externa' if conversion_lograda else 'no disponible -> fallback de placeholders usado'}")
    print(f"Placeholders generados: {len(placeholders)}")
    for p in placeholders:
        print(f"  - {p.relative_to(BASE_DIR)}")
    print(f"Fondos reorganizados desde FONDOS/: {fondos_movidos}")
    print(f"Total de assets normalizados y listos para el CanvasEngine: {total}")
    print("===========================================\n")


def main():
    conversion_lograda = intentar_conversion_ai()

    placeholders: List[Path] = []
    if not conversion_lograda:
        placeholders = generate_placeholder_assets()

    fondos_movidos = reorganizar_fondos()

    generar_reporte(conversion_lograda, placeholders, fondos_movidos)


if __name__ == "__main__":
    main()
