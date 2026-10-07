"""
CanvasEngine - motor visual parametrico para invitaciones (WhatsApp).
Composicion por capas con Pillow. Sin dependencias externas pesadas.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from assets_manager import AssetRepository

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_FONT_BOLD = BASE_DIR / "assets" / "fonts" / "Arial-Bold.ttf"
DEFAULT_FONT_REGULAR = BASE_DIR / "assets" / "fonts" / "Arial-Regular.ttf"
DEFAULT_FONT_BLACK = BASE_DIR / "assets" / "fonts" / "Arial-Black.ttf"

DEFAULT_BG_COLOR = (33, 33, 33)
MIN_FONT_SIZE = 18


class InvitationCanvasBuilder:
    """Construye una invitacion por capas: fondo -> overlay -> texto -> ponentes -> patrocinador."""

    WIDTH = 1080
    HEIGHT = 1920
    SAFE_TOP = 250
    SAFE_BOTTOM = 1670

    def __init__(
        self,
        width: int = WIDTH,
        height: int = HEIGHT,
        safe_top: int = SAFE_TOP,
        safe_bottom: int = SAFE_BOTTOM,
        background_color: Tuple[int, int, int] = DEFAULT_BG_COLOR,
        asset_repo: Optional[AssetRepository] = None,
    ):
        self.width = width
        self.height = height
        self.safe_top = safe_top
        self.safe_bottom = safe_bottom
        self.background_color = background_color
        self.asset_repo = asset_repo or AssetRepository()

        self.image = Image.new("RGB", (self.width, self.height), background_color)
        self.draw = ImageDraw.Draw(self.image)

    # ------------------------------------------------------------------
    # Capa de fondo
    # ------------------------------------------------------------------

    def load_background(
        self, bg_path: Optional[str] = None, category: Optional[str] = None,
    ) -> "InvitationCanvasBuilder":
        """
        Carga el fondo. Prioridad: `bg_path` explicito (si existe y abre bien)
        -> seleccion dinamica por `category` via AssetRepository.get_background()
        -> color solido por defecto. Nunca lanza excepcion: cada nivel cae al
        siguiente de forma transparente.
        """
        if bg_path:
            try:
                fondo = Image.open(bg_path).convert("RGB")
                self.image = ImageOps.fit(fondo, (self.width, self.height), method=Image.LANCZOS)
                self.draw = ImageDraw.Draw(self.image)
                return self
            except (FileNotFoundError, OSError):
                print(f"[AVISO] Fondo no encontrado o invalido en '{bg_path}'; se intenta resolver por categoria.")

        if category:
            fondo = self.asset_repo.get_background(category, canvas_size=(self.width, self.height))
            self.image = ImageOps.fit(fondo, (self.width, self.height), method=Image.LANCZOS)
            self.draw = ImageDraw.Draw(self.image)
            return self

        print("[AVISO] Sin fondo ni categoria especificados; usando color solido por defecto.")
        return self

    def apply_dark_overlay(self, opacity: float = 0.4) -> "InvitationCanvasBuilder":
        """Superpone una capa negra semitransparente para garantizar contraste del texto blanco."""
        opacity = max(0.0, min(1.0, opacity))
        overlay = Image.new("RGBA", self.image.size, (0, 0, 0, int(255 * opacity)))
        merged = Image.alpha_composite(self.image.convert("RGBA"), overlay)
        self.image = merged.convert("RGB")
        self.draw = ImageDraw.Draw(self.image)
        return self

    def apply_gradient_overlay(
        self,
        top_opacity: float = 0.6,
        mid_opacity: float = 0.18,
        bottom_opacity: float = 0.68,
        mid_stop: float = 0.42,
    ) -> "InvitationCanvasBuilder":
        """
        Superpone un degradado vertical negro: oscuro arriba (legibilidad del
        titulo), mas transparente en el medio (se ve la foto) y oscuro abajo
        (legibilidad de tarjetas de ponentes/patrocinador). Replica el look
        de las plantillas de referencia (mejor que un negro plano uniforme).
        """
        h = self.height
        mid_y = int(h * mid_stop)
        alphas = []
        for y in range(h):
            if y <= mid_y:
                t = y / max(mid_y, 1)
                a = top_opacity + (mid_opacity - top_opacity) * t
            else:
                t = (y - mid_y) / max(h - mid_y, 1)
                a = mid_opacity + (bottom_opacity - mid_opacity) * t
            alphas.append(int(255 * max(0.0, min(1.0, a))))

        gradient_row = Image.new("L", (1, h))
        gradient_row.putdata(alphas)
        alpha_mask = gradient_row.resize((self.width, h))

        overlay = Image.new("RGBA", self.image.size, (0, 0, 0, 255))
        overlay.putalpha(alpha_mask)
        merged = Image.alpha_composite(self.image.convert("RGBA"), overlay)
        self.image = merged.convert("RGB")
        self.draw = ImageDraw.Draw(self.image)
        return self

    def apply_grain_texture(self, intensity: float = 0.05, opacity: float = 0.5) -> "InvitationCanvasBuilder":
        """
        Superpone un grano/textura sutil sobre toda la pieza - las plantillas
        de referencia reales (assets/Templates/Invitaciones/) no tienen un
        fondo oscuro completamente liso, tienen una textura tipo tela que le
        da riqueza tactil. `intensity` controla la variacion del ruido (en
        fraccion de 255); `opacity` cuanto se mezcla sobre la imagen final.
        """
        arr = np.array(self.image).astype(np.float32)
        ruido = np.random.normal(0, 255 * intensity, arr.shape[:2]).astype(np.float32)
        ruido = np.repeat(ruido[:, :, None], 3, axis=2)
        resultado = np.clip(arr + ruido * opacity, 0, 255).astype(np.uint8)
        self.image = Image.fromarray(resultado, mode="RGB")
        self.draw = ImageDraw.Draw(self.image)
        return self

    # ------------------------------------------------------------------
    # Fuentes
    # ------------------------------------------------------------------

    def _load_font(self, font_path: str, size: int) -> ImageFont.ImageFont:
        """
        Resuelve la fuente via AssetRepository (acepta ruta completa o solo
        nombre de archivo - se usa el basename para buscar en assets/fonts/).
        Nunca lanza excepcion: sin coincidencia, AssetRepository.get_font()
        cae de forma transparente a la fuente por defecto de Pillow.
        """
        nombre = Path(font_path).name if font_path else font_path
        return self.asset_repo.get_font(nombre, size)

    # ------------------------------------------------------------------
    # Texto adaptativo
    # ------------------------------------------------------------------

    def _wrap_lines(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
        palabras = text.split()
        if not palabras:
            return [""]
        lineas = []
        actual = palabras[0]
        for palabra in palabras[1:]:
            candidata = f"{actual} {palabra}"
            ancho = self.draw.textbbox((0, 0), candidata, font=font)[2]
            if ancho <= max_width:
                actual = candidata
            else:
                lineas.append(actual)
                actual = palabra
        lineas.append(actual)
        return lineas

    def _block_height(self, lineas: List[str], font: ImageFont.FreeTypeFont, spacing: int) -> int:
        alturas = [self.draw.textbbox((0, 0), l, font=font)[3] for l in lineas]
        return sum(alturas) + spacing * (len(lineas) - 1)

    def draw_wrapped_text(
        self,
        text: str,
        font_path: str,
        max_width: int,
        start_y: int,
        font_size: int,
        color: Tuple[int, int, int] = (255, 255, 255),
        spacing: int = 10,
    ) -> int:
        """
        Ajusta el texto a max_width en multiples lineas, centradas horizontalmente.
        Si el bloque total excede la zona segura vertical, reduce el tamano de
        fuente progresivamente hasta que quepa (o hasta MIN_FONT_SIZE).
        Devuelve la coordenada Y inmediatamente despues del bloque dibujado.
        """
        size = font_size
        font = self._load_font(font_path, size)
        lineas = self._wrap_lines(text, font, max_width)
        altura = self._block_height(lineas, font, spacing)

        while start_y + altura > self.safe_bottom and size > MIN_FONT_SIZE:
            size -= 2
            font = self._load_font(font_path, size)
            lineas = self._wrap_lines(text, font, max_width)
            altura = self._block_height(lineas, font, spacing)

        y = start_y
        for linea in lineas:
            bbox = self.draw.textbbox((0, 0), linea, font=font)
            ancho_linea = bbox[2] - bbox[0]
            alto_linea = bbox[3] - bbox[1]
            x = (self.width - ancho_linea) / 2
            self.draw.text((x, y), linea, font=font, fill=color)
            y += alto_linea + spacing

        return y

    def draw_text_block(
        self,
        lines: List[str],
        font_path: str,
        font_size: int,
        x: int,
        start_y: int,
        color: Tuple[int, int, int] = (255, 255, 255),
        align: str = "left",
        spacing: int = 6,
        measure_only: bool = False,
    ) -> int:
        """
        Dibuja lineas de texto ya preparadas (sin word-wrap automatico) ancladas
        en `x` segun `align` ('left', 'right' o 'center'). Util para bloques de
        titulo/fecha que no van centrados en el lienzo completo.
        Con `measure_only=True` calcula la Y resultante sin pintar pixeles
        (para medir la altura de un bloque antes de dibujar un fondo debajo).
        Devuelve la coordenada Y siguiente al bloque.
        """
        font = self._load_font(font_path, font_size)
        y = start_y
        for linea in lines:
            bbox = self.draw.textbbox((0, 0), linea, font=font)
            ancho_linea = bbox[2] - bbox[0]
            alto_linea = bbox[3] - bbox[1]
            if not measure_only:
                if align == "right":
                    pos_x = x - ancho_linea
                elif align == "center":
                    pos_x = x - ancho_linea / 2
                else:
                    pos_x = x
                self.draw.text((pos_x, y), linea, font=font, fill=color)
            y += alto_linea + spacing
        return y

    def measure_wrapped_text(
        self, text: str, font_path: str, font_size: int, max_width: int, spacing: int = 10,
    ) -> Tuple[int, int, List[str]]:
        """Ancho maximo de linea, alto total y lineas resultantes de envolver `text` a `max_width`."""
        font = self._load_font(font_path, font_size)
        lineas = self._wrap_lines(text, font, max_width)
        altura = self._block_height(lineas, font, spacing)
        ancho = max(self.draw.textbbox((0, 0), l, font=font)[2] for l in lineas)
        return ancho, altura, lineas

    def measure_text_width(self, text: str, font_path: str, font_size: int) -> int:
        """Ancho en pixeles de `text` con la fuente/tamano dados (sin dibujar nada)."""
        font = self._load_font(font_path, font_size)
        bbox = self.draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    def paste_image(
        self, image_path: str, x: int, y: int,
        max_size: Optional[Tuple[int, int]] = None, center_x: bool = False,
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Pega un PNG transparente arbitrario (logo/icono) en (x, y). Si
        `max_size` se da, lo reduce manteniendo proporcion. Si `center_x` es
        True, `x` se interpreta como el centro horizontal deseado. No lanza
        excepcion si el archivo no se puede abrir - lo omite y avisa.
        Devuelve (x, y, ancho, alto) reales usados, o None si se omitio.
        """
        try:
            img = Image.open(image_path).convert("RGBA")
        except (FileNotFoundError, OSError) as e:
            print(f"[AVISO] No se pudo abrir la imagen '{image_path}' ({e}); se omite.")
            return None

        if max_size:
            img.thumbnail(max_size)

        pos_x = int(x - img.width / 2) if center_x else int(x)
        pos_y = int(y)
        self.image.paste(img, (pos_x, pos_y), img)
        return (pos_x, pos_y, img.width, img.height)

    def draw_vertical_divider(
        self, x: int, y_top: int, y_bottom: int,
        color: Tuple[int, int, int] = (255, 255, 255), width: int = 3,
    ) -> "InvitationCanvasBuilder":
        """Linea vertical delgada, usada para separar el bloque de titulo del de fecha/lugar."""
        self.draw.line([(x, y_top), (x, y_bottom)], fill=color, width=width)
        return self

    def draw_title_lockup(
        self,
        category_word: str,
        headline_word: str,
        date_lines: List[str],
        category_font: str,
        headline_font: str,
        date_strong_font: str,
        date_font: str,
        accent: Tuple[int, int, int],
        top_y: int,
        category_size: int = 78,
        headline_size: int = 116,
        date_size: int = 38,
        icon_path: Optional[str] = None,
        icon_size: int = 105,
        gap_title: int = 38,
        gap_date: int = 22,
        max_width: int = 960,
        date_max_width: int = 420,
        strong_items: int = 1,
        text_color: Tuple[int, int, int] = (255, 255, 255),
        muted_color: Tuple[int, int, int] = (214, 214, 214),
    ) -> int:
        """
        Bloque de titulo como en las piezas reales: palabra de categoria (acento)
        sobre palabra grande (blanca), ambas alineadas a la DERECHA contra un
        divisor vertical del color de acento; la fecha/lugar queda a la
        IZQUIERDA del otro lado. Icono de linea bajo el titular, alineado a la
        derecha. Todo el conjunto se centra horizontalmente en el lienzo (si no
        cabe en `max_width`, se reducen los tamanos proporcionalmente).
        Devuelve la Y inferior del bloque (para ubicar el subtitulo debajo).
        """
        divider_w = 3
        escala = 1.0
        while True:
            cat_sz, head_sz, date_sz = (int(v * escala) for v in (category_size, headline_size, date_size))
            f_cat = self._load_font(category_font, cat_sz)
            f_head = self._load_font(headline_font, head_sz)
            f_strong = self._load_font(date_strong_font, date_sz)
            f_date = self._load_font(date_font, date_sz)

            lineas_fecha: List[Tuple[str, ImageFont.ImageFont]] = []
            for i, item in enumerate(date_lines):
                fuente = f_strong if i < strong_items else f_date
                for sub in self._wrap_lines(str(item), fuente, date_max_width):
                    lineas_fecha.append((sub, fuente))

            def ancho(txt, fnt):
                b = self.draw.textbbox((0, 0), txt, font=fnt)
                return b[2] - b[0]

            title_w = max(ancho(category_word, f_cat), ancho(headline_word, f_head))
            date_w = max((ancho(t, f) for t, f in lineas_fecha), default=0)
            total = title_w + gap_title + divider_w + gap_date + date_w
            if total <= max_width or escala <= 0.6:
                break
            escala -= 0.04

        left = (self.width - total) / 2
        title_right = left + title_w
        divider_x = title_right + gap_title
        date_x = divider_x + divider_w + gap_date

        def cap_box(fnt):
            return self.draw.textbbox((0, 0), "H", font=fnt)

        # Titulo: se ancla por altura de mayuscula (no por tinta) para que la
        # posicion vertical no cambie segun las letras de cada palabra.
        cb = cap_box(f_cat)
        cap_cat = cb[3] - cb[1]
        hb = cap_box(f_head)
        cap_head = hb[3] - hb[1]

        y_cat = top_y
        b = self.draw.textbbox((0, 0), category_word, font=f_cat)
        self.draw.text((title_right - b[2], y_cat - cb[1]), category_word, font=f_cat, fill=accent)

        gap_cat_head = max(int(cat_sz * 0.16), 8)
        y_head = y_cat + cap_cat + gap_cat_head
        b = self.draw.textbbox((0, 0), headline_word, font=f_head)
        self.draw.text((title_right - b[2], y_head - hb[1]), headline_word, font=f_head, fill=text_color)
        head_baseline = y_head + cap_head
        tiene_descendente = any(c in "gjpqyç" for c in headline_word.lower())
        title_bottom = head_baseline

        if icon_path:
            try:
                with Image.open(icon_path) as ic:
                    iw, ih = ic.size
                lado = int(icon_size * escala)
                factor = min(lado / iw, lado / ih)
                w_icono = int(iw * factor)
                y_icono = head_baseline + int(head_sz * (0.30 if tiene_descendente else 0.20))
                res = self.paste_image(icon_path, x=title_right - w_icono / 2, y=y_icono,
                                       max_size=(lado, lado), center_x=True)
                if res:
                    title_bottom = res[1] + res[3]
            except (FileNotFoundError, OSError) as e:
                print(f"[AVISO] No se pudo abrir el icono '{icon_path}' ({e}); se omite.")

        # Fecha/lugar: alineada a la izquierda, primera linea a la altura de la palabra de categoria.
        pitch = int(date_sz * 1.22)
        y = top_y
        for texto, fuente in lineas_fecha:
            fb = cap_box(fuente)
            color = text_color if fuente is f_strong else muted_color
            self.draw.text((date_x, y - fb[1]), texto, font=fuente, fill=color)
            y += pitch
        fdb = cap_box(f_date)
        date_bottom = top_y + pitch * (len(lineas_fecha) - 1) + (fdb[3] - fdb[1]) if lineas_fecha else top_y

        bottom = int(max(title_bottom, date_bottom))
        self.draw_vertical_divider(int(divider_x), top_y - 6, bottom + 6, accent, divider_w)
        return bottom + 6

    def draw_bracket_frame(
        self, x0: int, y0: int, x1: int, y1: int,
        color: Tuple[int, int, int] = (255, 255, 255),
        corner_len: int = 32, thickness: int = 3,
    ) -> "InvitationCanvasBuilder":
        """
        Marco decorativo de solo-esquinas (corchetes en L), como el motivo
        recurrente de las plantillas de referencia, en vez de un rectangulo completo.
        """
        corners = [
            ((x0, y0), (1, 0), (0, 1)),
            ((x1, y0), (-1, 0), (0, 1)),
            ((x0, y1), (1, 0), (0, -1)),
            ((x1, y1), (-1, 0), (0, -1)),
        ]
        for (cx, cy), (hx, hy), (vx, vy) in corners:
            self.draw.line([(cx, cy), (cx + hx * corner_len, cy + hy * corner_len)], fill=color, width=thickness)
            self.draw.line([(cx, cy), (cx + vx * corner_len, cy + vy * corner_len)], fill=color, width=thickness)
        return self

    # ------------------------------------------------------------------
    # Grid de ponentes
    # ------------------------------------------------------------------

    def _circular_photo(self, photo_path: str, diameter: int) -> Optional[Image.Image]:
        try:
            foto = Image.open(photo_path).convert("RGB")
        except (FileNotFoundError, OSError):
            print(f"[AVISO] Foto de ponente no encontrada en '{photo_path}'; se omite.")
            return None

        foto = ImageOps.fit(foto, (diameter, diameter), method=Image.LANCZOS)
        mask = Image.new("L", (diameter, diameter), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
        foto.putalpha(mask)
        return foto

    def render_speakers_grid(
        self,
        speakers_list: List[Dict],
        start_y: int,
        name_font_path: str = str(DEFAULT_FONT_BOLD),
        role_font_path: str = str(DEFAULT_FONT_REGULAR),
        photo_diameter: int = 180,
    ) -> int:
        """
        Dibuja de 1 a 5 ponentes en filas de hasta 2 columnas.
        Cada elemento: {"name": str, "role": str, "photo_path": Optional[str]}.
        Con foto: se recorta en circulo. Sin foto: solo texto (nombre en negrita, cargo regular).
        Devuelve la coordenada Y siguiente al grid completo.
        """
        speakers = speakers_list[:5]
        if not speakers:
            return start_y

        columnas = 1 if len(speakers) == 1 else 2
        filas = [speakers[i:i + columnas] for i in range(0, len(speakers), columnas)]

        name_font = self._load_font(name_font_path, 32)
        role_font = self._load_font(role_font_path, 26)

        y = start_y

        for fila in filas:
            columnas_fila = len(fila)
            col_width = self.width / columnas_fila
            fila_top = y
            fila_alturas = []

            for idx, ponente in enumerate(fila):
                col_center_x = col_width * idx + col_width / 2
                cursor_y = fila_top

                photo_path = ponente.get("photo_path")
                foto = self._circular_photo(photo_path, photo_diameter) if photo_path else None
                if foto:
                    pos_x = int(col_center_x - photo_diameter / 2)
                    self.image.paste(foto, (pos_x, int(cursor_y)), foto)
                    cursor_y += photo_diameter + 16

                nombre = ponente.get("name", "")
                cargo = ponente.get("role", "")

                bbox = self.draw.textbbox((0, 0), nombre, font=name_font)
                self.draw.text(
                    (col_center_x - (bbox[2] - bbox[0]) / 2, cursor_y),
                    nombre, font=name_font, fill=(255, 255, 255),
                )
                cursor_y += (bbox[3] - bbox[1]) + 8

                bbox2 = self.draw.textbbox((0, 0), cargo, font=role_font)
                self.draw.text(
                    (col_center_x - (bbox2[2] - bbox2[0]) / 2, cursor_y),
                    cargo, font=role_font, fill=(220, 220, 220),
                )
                cursor_y += (bbox2[3] - bbox2[1])

                fila_alturas.append(cursor_y - fila_top)

            y = fila_top + max(fila_alturas) + 40

        return y

    # ------------------------------------------------------------------
    # Tarjetas de ponentes (nombre, cargo, empresa, tema - con borde de acento)
    # ------------------------------------------------------------------

    def draw_speaker_card(
        self,
        ponente: Dict,
        x: int,
        y: int,
        width: int,
        accent_color: Tuple[int, int, int],
        name_font_path: str = str(DEFAULT_FONT_BOLD),
        role_font_path: str = str(DEFAULT_FONT_REGULAR),
        topic_font_path: str = str(DEFAULT_FONT_BOLD),
        bg_color: Tuple[int, int, int] = (18, 18, 18),
        bg_opacity: float = 0.55,
        padding: int = 16,
        corner_radius: int = 14,
        photo_size: int = 64,
    ) -> int:
        """
        Tarjeta con fondo oscuro semitransparente y borde de color de acento:
        [Foto opcional] Nombre (negrita) -> Cargo, Empresa (regular) -> linea
        divisoria -> Tema (negrita, color de acento). La foto solo se dibuja
        si `ponente["photo_path"]` es una foto real (has_fallback_avatar es
        False) - con avatar por defecto, la tarjeta queda solo texto, igual
        que en las plantillas de referencia que no traen foto.
        Devuelve el Y inferior de la tarjeta.
        """
        name_font = self._load_font(name_font_path, 28)
        role_font = self._load_font(role_font_path, 21)
        topic_font = self._load_font(topic_font_path, 22)

        photo_path = ponente.get("photo_path")
        mostrar_foto = bool(photo_path) and not ponente.get("has_fallback_avatar", True)
        texto_x = x + padding + (photo_size + 14 if mostrar_foto else 0)
        content_width = width - 2 * padding - (photo_size + 14 if mostrar_foto else 0)

        nombre_lineas = self._wrap_lines(ponente.get("name", ""), name_font, content_width)

        rol_texto = ponente.get("role", "")
        empresa_texto = ponente.get("empresa") or ponente.get("company") or ""
        rol_lineas = self._wrap_lines(rol_texto, role_font, content_width) if rol_texto else []
        empresa_lineas = self._wrap_lines(empresa_texto, role_font, content_width) if empresa_texto else []

        tema_texto = ponente.get("tema") or ponente.get("topic") or ""
        tema_lineas = self._wrap_lines(tema_texto.upper(), topic_font, content_width) if tema_texto else []

        # --- Pasada de medicion (no pinta pixeles): calcula la altura total de la tarjeta ---
        cursor_y = y + padding
        cursor_y = self.draw_text_block(nombre_lineas, name_font_path, 28, texto_x, cursor_y, (255, 255, 255), "left", 4, measure_only=True)
        if rol_lineas:
            cursor_y = self.draw_text_block(rol_lineas, role_font_path, 21, texto_x, cursor_y + 2, (215, 215, 215), "left", 3, measure_only=True)
        if empresa_lineas:
            cursor_y = self.draw_text_block(empresa_lineas, role_font_path, 21, texto_x, cursor_y, (255, 255, 255), "left", 3, measure_only=True)
        if tema_lineas:
            divider_y = cursor_y + 8
            cursor_y = self.draw_text_block(tema_lineas, topic_font_path, 22, texto_x, divider_y + 10, accent_color, "left", 4, measure_only=True)

        contenido_bottom = cursor_y + padding
        card_bottom = max(contenido_bottom, y + padding + photo_size + padding) if mostrar_foto else contenido_bottom

        # Fondo translucido + borde, dibujados DESPUES de medir el contenido (altura ya conocida)
        overlay = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(
            [x, y, x + width, card_bottom],
            radius=corner_radius,
            fill=bg_color + (int(255 * bg_opacity),),
        )
        self.image = Image.alpha_composite(self.image.convert("RGBA"), overlay).convert("RGB")
        self.draw = ImageDraw.Draw(self.image)
        self.draw.rounded_rectangle([x, y, x + width, card_bottom], radius=corner_radius, outline=accent_color, width=2)

        if mostrar_foto:
            try:
                foto = Image.open(photo_path).convert("RGB")
                foto = ImageOps.fit(foto, (photo_size, photo_size), method=Image.LANCZOS)
                # Blanco y negro, sin borde - asi se ven las fotos de ponente en
                # las plantillas de referencia reales (ver assets/Templates/Invitaciones/).
                foto = ImageOps.grayscale(foto).convert("RGB")
                self.image.paste(foto, (x + padding, y + padding))
            except (FileNotFoundError, OSError) as e:
                print(f"[AVISO] Foto de ponente '{photo_path}' no se pudo abrir ({e}); tarjeta sin foto.")

        # --- Pasada real: ahora si se pinta el texto, encima del fondo ya compuesto ---
        cursor_y = y + padding
        cursor_y = self.draw_text_block(nombre_lineas, name_font_path, 28, texto_x, cursor_y, (255, 255, 255), "left", 4)
        if rol_lineas:
            cursor_y = self.draw_text_block(rol_lineas, role_font_path, 21, texto_x, cursor_y + 2, (215, 215, 215), "left", 3)
        if empresa_lineas:
            cursor_y = self.draw_text_block(empresa_lineas, role_font_path, 21, texto_x, cursor_y, (255, 255, 255), "left", 3)
        if tema_lineas:
            divider_y = cursor_y + 8
            self.draw.line(
                [(texto_x, divider_y), (texto_x + min(180, content_width), divider_y)],
                fill=accent_color, width=2,
            )
            self.draw_text_block(tema_lineas, topic_font_path, 22, texto_x, divider_y + 10, accent_color, "left", 4)

        return card_bottom

    def render_speaker_cards(
        self,
        speakers_list: List[Dict],
        start_y: int,
        accent_color: Tuple[int, int, int],
        columns: int = 2,
        margin: int = 40,
        gap: int = 16,
        name_font_path: str = str(DEFAULT_FONT_BOLD),
        role_font_path: str = str(DEFAULT_FONT_REGULAR),
        topic_font_path: str = str(DEFAULT_FONT_BOLD),
    ) -> int:
        """
        Dispone hasta 5 ponentes en tarjetas con borde de acento (ver draw_speaker_card),
        en filas de hasta `columns` columnas. Devuelve el Y siguiente al bloque completo.
        """
        speakers = speakers_list[:5]
        if not speakers:
            return start_y

        cols = 1 if len(speakers) == 1 else columns
        card_width = (self.width - 2 * margin - gap * (cols - 1)) / cols

        y = start_y
        for i in range(0, len(speakers), cols):
            fila = speakers[i:i + cols]
            fila_bottom = y
            for idx, ponente in enumerate(fila):
                x = int(margin + idx * (card_width + gap))
                bottom = self.draw_speaker_card(
                    ponente, x, int(y), int(card_width), accent_color,
                    name_font_path=name_font_path, role_font_path=role_font_path, topic_font_path=topic_font_path,
                )
                fila_bottom = max(fila_bottom, bottom)
            y = fila_bottom + gap

        return y

    # ------------------------------------------------------------------
    # Insignia "Maestria [Categoria]"
    # ------------------------------------------------------------------

    def draw_maestria_badge(
        self,
        categoria_label: str,
        y_position: int,
        accent_color: Tuple[int, int, int] = (255, 255, 255),
        tagline: str = "que transforma",
        title_font_path: str = str(DEFAULT_FONT_BLACK),
        category_font_path: str = str(DEFAULT_FONT_BOLD),
        tagline_font_path: str = str(DEFAULT_FONT_BOLD),
    ) -> int:
        """Insignia de marca centrada: 'Maestria' + categoria + tagline en color de acento."""
        y = self.draw_wrapped_text("Maestria", title_font_path, self.width - 100, y_position, 44, (255, 255, 255), 4)
        y = self.draw_wrapped_text(categoria_label.upper(), category_font_path, self.width - 100, y + 22, 24, accent_color, 4)
        y = self.draw_wrapped_text(tagline, tagline_font_path, self.width - 100, y + 16, 20, (235, 235, 235), 4)
        return y

    # ------------------------------------------------------------------
    # Fila de logos de marcas aliadas (patrocinadores multiples)
    # ------------------------------------------------------------------

    def render_sponsor_logos_row(
        self,
        logo_paths: List[str],
        y_position: int,
        max_logo_height: int = 76,
        gap: int = 22,
        box_fill: Tuple[int, int, int] = (245, 245, 245),
        box_padding: int = 26,
        corner_radius: int = 16,
        label: Optional[str] = "Apoyan",
        label_color: Tuple[int, int, int] = (60, 60, 60),
        label_font_path: str = str(DEFAULT_FONT_BLACK),
        label_font_size: int = 30,
    ) -> int:
        """
        Pega varios logos de marcas aliadas dentro de una caja solida clara
        con esquinas redondeadas - la caja "Apoyan: <logos>" real de
        assets/Templates/Invitaciones/ (no un marco transparente). Con
        `label` (por defecto "Apoyan") lo dibuja a la izquierda, dentro de
        la misma caja. Un logo individual que no se pueda abrir se omite (no
        detiene el resto). Devuelve la Y siguiente al bloque. Si `logo_paths`
        esta vacio (tras omitir invalidos), no dibuja nada y devuelve
        `y_position` sin cambios.
        """
        logos = []
        for ruta in logo_paths:
            try:
                img = Image.open(ruta).convert("RGBA")
            except (FileNotFoundError, OSError):
                print(f"[AVISO] Logo aliado no encontrado o invalido en '{ruta}'; se omite.")
                continue
            escala = max_logo_height / img.height
            img = img.resize((max(1, int(img.width * escala)), max_logo_height))
            logos.append(img)

        if not logos:
            return y_position

        label_font = self._load_font(label_font_path, label_font_size) if label else None
        label_ancho = 0
        if label and label_font:
            bbox_label = self.draw.textbbox((0, 0), label, font=label_font)
            label_ancho = (bbox_label[2] - bbox_label[0]) + 22

        ancho_logos = sum(l.width for l in logos) + gap * (len(logos) - 1)
        ancho_contenido = label_ancho + ancho_logos
        box_w = ancho_contenido + 2 * box_padding
        box_h = max_logo_height + 2 * box_padding
        box_x0 = int((self.width - box_w) / 2)
        box_y0 = int(y_position)
        box_x1 = box_x0 + box_w
        box_y1 = box_y0 + box_h

        self.draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=corner_radius, fill=box_fill)

        cursor_x = box_x0 + box_padding
        if label and label_font:
            bbox_label = self.draw.textbbox((0, 0), label, font=label_font)
            alto_label = bbox_label[3] - bbox_label[1]
            y_label = box_y0 + box_h / 2 - alto_label / 2 - bbox_label[1]
            self.draw.text((cursor_x, y_label), label, font=label_font, fill=label_color)
            cursor_x += label_ancho

        for logo in logos:
            self.image.paste(logo, (int(cursor_x), int(box_y0 + box_padding)), logo)
            cursor_x += logo.width + gap

        return int(box_y1)

    # ------------------------------------------------------------------
    # Fallback de patrocinador
    # ------------------------------------------------------------------

    def render_sponsor_fallback(
        self,
        sponsor_text_or_logo_path: Optional[str],
        y_position: int,
        font_path: str = str(DEFAULT_FONT_REGULAR),
        font_size: int = 28,
        max_logo_size: Tuple[int, int] = (260, 110),
    ) -> int:
        """
        Intenta cargar un logo desde `sponsor_text_or_logo_path` (si parece ruta de imagen).
        Si la ruta es nula, no existe o falla la carga, dibuja el mismo valor como
        texto de respaldo con tipografia corporativa. Devuelve la Y siguiente al bloque.
        """
        if sponsor_text_or_logo_path:
            path = Path(sponsor_text_or_logo_path)
            if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                try:
                    logo = Image.open(path).convert("RGBA")
                    logo.thumbnail(max_logo_size)
                    pos_x = int((self.width - logo.width) / 2)
                    self.image.paste(logo, (pos_x, y_position), logo)
                    return y_position + logo.height
                except (FileNotFoundError, OSError):
                    print(
                        f"[AVISO] Logo de patrocinador no encontrado en "
                        f"'{sponsor_text_or_logo_path}'; usando texto de respaldo."
                    )

        texto = sponsor_text_or_logo_path or ""
        if not texto:
            return y_position

        font = self._load_font(font_path, font_size)
        bbox = self.draw.textbbox((0, 0), texto, font=font)
        ancho_texto = bbox[2] - bbox[0]
        alto_texto = bbox[3] - bbox[1]
        self.draw.text(((self.width - ancho_texto) / 2, y_position), texto, font=font, fill=(255, 255, 255))
        return y_position + alto_texto

    # ------------------------------------------------------------------
    # Exportacion
    # ------------------------------------------------------------------

    def save(self, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        self.image.save(output_path)
        return output_path
