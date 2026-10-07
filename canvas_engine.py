"""
CanvasEngine - motor visual parametrico para invitaciones (WhatsApp).
Composicion por capas con Pillow. Sin dependencias externas pesadas.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

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
        icon_paths: Optional[List[str]] = None,
        icon_size: int = 105,
        gap_title: int = 38,
        gap_date: int = 22,
        max_width: int = 1000,
        date_max_width: int = 400,
        strong_max_width: int = 330,
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
                for sub in self._wrap_lines(str(item), fuente, strong_max_width if i < strong_items else date_max_width):
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

        if icon_paths:
            lado = int(icon_size * escala)
            y_icono = head_baseline + int(head_sz * (0.30 if tiene_descendente else 0.20))
            x_der = title_right
            for ruta_icono in reversed(icon_paths):
                try:
                    with Image.open(ruta_icono) as ic:
                        iw, ih = ic.size
                except (FileNotFoundError, OSError) as e:
                    print(f"[AVISO] No se pudo abrir el icono '{ruta_icono}' ({e}); se omite.")
                    continue
                w_icono = int(iw * min(lado / iw, lado / ih))
                res = self.paste_image(ruta_icono, x=x_der - w_icono, y=y_icono, max_size=(lado, lado))
                if res:
                    title_bottom = max(title_bottom, res[1] + res[3])
                    x_der -= w_icono + int(16 * escala)

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

    # ------------------------------------------------------------------
    # Marco blanco abierto + titulo del evento
    # ------------------------------------------------------------------

    def _componer_capa(self, capa: Image.Image, x: int, y: int) -> None:
        """Compone una capa RGBA sobre la imagen actual en (x, y) (recortando lo que se salga del lienzo)."""
        region = self.image.crop((x, y, x + capa.width, y + capa.height)).convert("RGBA")
        region.alpha_composite(capa)
        self.image.paste(region.convert("RGB"), (x, y))
        self.draw = ImageDraw.Draw(self.image)

    def draw_content_frame(
        self,
        x0: int, y_top: int, x1: int, y_bottom: int,
        gap_top: Optional[Tuple[int, int]] = None,
        gap_bottom: Optional[Tuple[int, int]] = None,
        color: Tuple[int, int, int] = (255, 255, 255),
        radius: int = 22,
        thickness: int = 3,
    ) -> None:
        """
        Marco de linea fina con esquinas redondeadas que envuelve titulo, foto y
        ponencias (motivo de las piezas reales). `gap_top` / `gap_bottom` son
        rangos X absolutos donde el borde superior/inferior queda abierto (el
        titulo arriba, las tarjetas abajo). Dibujado a 3x para bordes suaves.
        """
        w, h = int(x1 - x0), int(y_bottom - y_top)
        S = 3
        capa = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        dibujo = ImageDraw.Draw(capa)
        dibujo.rounded_rectangle(
            [0, 0, w * S - 1, h * S - 1], radius=radius * S, outline=tuple(color) + (255,), width=thickness * S,
        )
        alto_corte = (thickness + 3) * S
        if gap_top:
            dibujo.rectangle([(gap_top[0] - x0) * S, 0, (gap_top[1] - x0) * S, alto_corte], fill=(0, 0, 0, 0))
        if gap_bottom:
            dibujo.rectangle([(gap_bottom[0] - x0) * S, h * S - alto_corte, (gap_bottom[1] - x0) * S, h * S], fill=(0, 0, 0, 0))
        self._componer_capa(capa.resize((w, h), Image.LANCZOS), int(x0), int(y_top))

    def draw_event_title(
        self,
        kicker: str,
        title: str,
        kicker_font: str,
        title_font: str,
        accent: Tuple[int, int, int],
        top_y: int,
        kicker_size: int = 50,
        title_size: int = 52,
        max_width: int = 800,
        text_color: Tuple[int, int, int] = (255, 255, 255),
    ) -> Dict[str, int]:
        """
        Titulo centrado del evento: antetitulo opcional (mayusculas, color de
        acento) sobre el titulo en blanco (se ajusta a `max_width`). Devuelve
        {"bottom", "frame_y" (Y donde pasa el borde superior del marco),
        "gap_x0", "gap_x1" (rango X que el marco deja abierto)}.
        """
        cx = self.width / 2
        lineas: List[Tuple[str, ImageFont.ImageFont, Tuple[int, int, int]]] = []
        if kicker and kicker.strip():
            tam = kicker_size
            fuente = self._load_font(kicker_font, tam)
            texto = kicker.strip().upper()
            while self.draw.textbbox((0, 0), texto, font=fuente)[2] > max_width and tam > 24:
                tam -= 2
                fuente = self._load_font(kicker_font, tam)
            lineas.append((texto, fuente, accent))
        f_title = self._load_font(title_font, title_size)
        n_kicker = len(lineas)
        for sub in self._wrap_lines(title.strip(), f_title, max_width):
            lineas.append((sub, f_title, text_color))

        y = top_y
        ancho_max = 0
        frame_y = top_y
        for i, (texto, fuente, color) in enumerate(lineas):
            cap = self.draw.textbbox((0, 0), "H", font=fuente)
            cap_h = cap[3] - cap[1]
            b = self.draw.textbbox((0, 0), texto, font=fuente)
            ancho = b[2] - b[0]
            ancho_max = max(ancho_max, ancho)
            self.draw.text((cx - ancho / 2 - b[0], y - cap[1]), texto, font=fuente, fill=color)
            if i == n_kicker:
                frame_y = y + int(cap_h * 0.4)
            y += int(cap_h * 1.55)
            ultimo_cap = cap_h
        bottom = y - int(ultimo_cap * 0.55)
        return {
            "bottom": int(bottom), "frame_y": int(frame_y),
            "gap_x0": int(cx - ancho_max / 2 - 26), "gap_x1": int(cx + ancho_max / 2 + 26),
        }

    # ------------------------------------------------------------------
    # Tarjetas de ponentes (nombre, empresa, tema) - dos esquinas redondeadas
    # ------------------------------------------------------------------

    @staticmethod
    def _poligono_redondeado(x0, y0, x1, y1, r_tl, r_tr, r_br, r_bl, pasos: int = 24) -> List[Tuple[float, float]]:
        """Contorno de un rectangulo con radio propio por esquina (0 = esquina recta)."""
        import math
        pts: List[Tuple[float, float]] = []

        def arco(cx, cy, r, a0, a1):
            if r <= 0:
                pts.append((cx, cy))
                return
            for i in range(pasos + 1):
                a = math.radians(a0 + (a1 - a0) * i / pasos)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

        arco(x0 + r_tl, y0 + r_tl, r_tl, 180, 270)
        arco(x1 - r_tr, y0 + r_tr, r_tr, 270, 360)
        arco(x1 - r_br, y1 - r_br, r_br, 0, 90)
        arco(x0 + r_bl, y1 - r_bl, r_bl, 90, 180)
        return pts

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
        bg_opacity: float = 0.62,
        padding: int = 22,
        r_small: int = 14,
        r_big: int = 48,
        min_height: int = 0,
        measure_only: bool = False,
    ) -> int:
        """
        Tarjeta como en las piezas reales: fondo oscuro translucido, borde de
        acento y SOLO dos esquinas redondeadas en diagonal (superior izquierda
        pequena, inferior derecha grande). Contenido: NOMBRE en mayusculas
        (negrita), cargo/empresa (regular), linea de acento y TEMA en
        mayusculas (negrita, color de acento). Devuelve el Y inferior.
        """
        name_font = self._load_font(name_font_path, 25)
        role_font = self._load_font(role_font_path, 21)
        topic_font = self._load_font(topic_font_path, 21)
        content_width = width - 2 * padding

        nombre_lineas = self._wrap_lines(ponente.get("name", "").upper(), name_font, content_width)
        rol_texto = ponente.get("role", "")
        empresa_texto = ponente.get("empresa") or ponente.get("company") or ""
        rol_lineas = self._wrap_lines(rol_texto, role_font, content_width) if rol_texto else []
        empresa_lineas = self._wrap_lines(empresa_texto, role_font, content_width) if empresa_texto else []
        tema_texto = ponente.get("tema") or ponente.get("topic") or ""
        tema_lineas = self._wrap_lines(tema_texto.upper(), topic_font, content_width - 10) if tema_texto else []

        texto_x = x + padding
        cursor_y = y + padding - 4
        cursor_y = self.draw_text_block(nombre_lineas, name_font_path, 25, texto_x, cursor_y, (255, 255, 255), "left", 4, measure_only=True)
        if rol_lineas:
            cursor_y = self.draw_text_block(rol_lineas, role_font_path, 21, texto_x, cursor_y + 2, (215, 215, 215), "left", 3, measure_only=True)
        if empresa_lineas:
            cursor_y = self.draw_text_block(empresa_lineas, role_font_path, 21, texto_x, cursor_y + 4, (255, 255, 255), "left", 3, measure_only=True)
        if tema_lineas:
            cursor_y = self.draw_text_block(tema_lineas, topic_font_path, 21, texto_x, cursor_y + 8 + 12, accent_color, "left", 7, measure_only=True)
        card_bottom = max(cursor_y + padding + 6, y + min_height)
        if measure_only:
            return int(card_bottom)

        S = 3
        w, h = int(width), int(card_bottom - y)
        capa = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        poligono = self._poligono_redondeado(1, 1, w * S - 2, h * S - 2, r_small * S, 0, r_big * S, 0)
        d = ImageDraw.Draw(capa)
        d.polygon(poligono, fill=tuple(bg_color) + (int(255 * bg_opacity),))
        d.line(poligono + [poligono[0]], fill=tuple(accent_color) + (255,), width=2 * S, joint="curve")
        self._componer_capa(capa.resize((w, h), Image.LANCZOS), int(x), int(y))

        cursor_y = y + padding - 4
        cursor_y = self.draw_text_block(nombre_lineas, name_font_path, 25, texto_x, cursor_y, (255, 255, 255), "left", 4)
        if rol_lineas:
            cursor_y = self.draw_text_block(rol_lineas, role_font_path, 21, texto_x, cursor_y + 2, (215, 215, 215), "left", 3)
        if empresa_lineas:
            cursor_y = self.draw_text_block(empresa_lineas, role_font_path, 21, texto_x, cursor_y + 4, (255, 255, 255), "left", 3)
        if tema_lineas:
            linea_y = cursor_y + 8
            self.draw.line([(x + 1, linea_y), (x + width - 64, linea_y)], fill=tuple(accent_color), width=2)
            self.draw_text_block(tema_lineas, topic_font_path, 21, texto_x, linea_y + 12, accent_color, "left", 7)
        return int(card_bottom)

    def render_speaker_cards(
        self,
        speakers_list: List[Dict],
        start_y: int,
        accent_color: Tuple[int, int, int],
        columns: int = 2,
        margin: int = 40,
        gap: int = 26,
        name_font_path: str = str(DEFAULT_FONT_BOLD),
        role_font_path: str = str(DEFAULT_FONT_REGULAR),
        topic_font_path: str = str(DEFAULT_FONT_BOLD),
        measure_only: bool = False,
    ) -> Dict[str, int]:
        """
        Dispone hasta 5 ponentes en filas de hasta `columns` tarjetas del mismo
        alto por fila, dentro de [margin, ancho - margin]. Con `measure_only`
        solo calcula. Devuelve {"bottom", "last_row_top", "last_row_bottom",
        "last_row_x0", "last_row_x1"} (la ultima fila sirve para abrir el marco).
        """
        speakers = speakers_list[:5]
        if not speakers:
            return {"bottom": start_y, "last_row_top": start_y, "last_row_bottom": start_y,
                    "last_row_x0": margin, "last_row_x1": self.width - margin}

        cols = 1 if len(speakers) == 1 else columns
        card_width = (self.width - 2 * margin - gap * (cols - 1)) / cols
        if cols == 1:
            card_width = min(card_width, 440)
            margin = (self.width - card_width) / 2
        fuentes = dict(name_font_path=name_font_path, role_font_path=role_font_path, topic_font_path=topic_font_path)

        y = start_y
        info = {}
        for i in range(0, len(speakers), cols):
            fila = speakers[i:i + cols]
            alto_fila = max(
                self.draw_speaker_card(p, 0, int(y), int(card_width), accent_color, measure_only=True, **fuentes) - int(y)
                for p in fila
            )
            # Una fila incompleta (ej. el 3.er ponente solo) queda centrada.
            ancho_fila = len(fila) * card_width + (len(fila) - 1) * gap
            x_inicio = margin + ((self.width - 2 * margin) - ancho_fila) / 2
            if not measure_only:
                for idx, ponente in enumerate(fila):
                    self.draw_speaker_card(
                        ponente, int(x_inicio + idx * (card_width + gap)), int(y), int(card_width), accent_color,
                        min_height=alto_fila, **fuentes,
                    )
            info = {
                "last_row_top": int(y), "last_row_bottom": int(y + alto_fila),
                "last_row_x0": int(x_inicio), "last_row_x1": int(x_inicio + ancho_fila),
            }
            y += alto_fila + gap
        info["bottom"] = int(y - gap)
        return info

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
        y = self.draw_wrapped_text("Maestría", title_font_path, self.width - 100, y_position, 44, (255, 255, 255), 4)
        y = self.draw_wrapped_text(categoria_label.upper(), category_font_path, self.width - 100, y + 22, 24, accent_color, 4)
        y = self.draw_wrapped_text(tagline, tagline_font_path, self.width - 100, y + 16, 20, (235, 235, 235), 4)
        return y

    # ------------------------------------------------------------------
    # Fila de logos de marcas aliadas (patrocinadores multiples)
    # ------------------------------------------------------------------

    @staticmethod
    def _recortar_margenes(img: Image.Image, tolerancia: int = 14) -> Image.Image:
        """Quita el borde vacio de un logo (transparente, o blanco en JPG) para que el espaciado de la pata sea parejo."""
        rgba = img.convert("RGBA")
        caja = rgba.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
        if caja:
            rgba = rgba.crop(caja)
        if rgba.getchannel("A").getextrema()[0] > 250:
            fondo = Image.new("RGB", rgba.size, (255, 255, 255))
            dif = ImageChops.difference(rgba.convert("RGB"), fondo).convert("L").point(lambda v: 255 if v > tolerancia else 0)
            caja = dif.getbbox()
            if caja:
                rgba = rgba.crop(caja)
        return rgba

    def render_sponsor_pata(
        self,
        groups: List[Dict],
        y_position: int,
        frame_color: Tuple[int, int, int],
        label_color: Tuple[int, int, int],
        header_logo: Optional[str] = None,
        label_font_path: str = str(DEFAULT_FONT_BOLD),
        label_size: int = 52,
        max_logo_height: int = 104,
        text_size: int = 32,
        box_fill: Tuple[int, int, int] = (247, 247, 247),
        max_width: int = 940,
    ) -> int:
        """
        Pata de patrocinadores como en las piezas reales (assets/Templates/Patas/):
        logo de Grupo Bios arriba rompiendo un marco redondeado (color de la
        linea) y, debajo, una caja clara con uno o mas grupos "Etiqueta | contenido"
        (ej. "Apoya | logo", "Invita | AGRO INSUMOS DONDE POLLO"). `groups` =
        [{"label": "Invita", "logos": [rutas...], "texto": "..."}]: cada grupo
        lleva logos, texto o ambos, y la etiqueta se pluraliza sola ("Invitan")
        si trae mas de un elemento. Devuelve la Y inferior de la pata.
        """
        grupos = []
        for g in groups:
            logos = []
            for ruta in g.get("logos", []):
                try:
                    logos.append(self._recortar_margenes(Image.open(ruta)))
                except (FileNotFoundError, OSError) as e:
                    print(f"[AVISO] No se pudo abrir el logo '{ruta}' ({e}); se omite.")
            texto = str(g.get("texto") or "").strip()
            if logos or texto:
                etiqueta = str(g.get("label", "Apoya"))
                n_elementos = len(logos) + (1 if texto else 0)
                grupos.append((etiqueta + "n" if n_elementos > 1 and not etiqueta.endswith("n") else etiqueta, logos, texto))
        if not grupos:
            return y_position

        encabezado = None
        if header_logo:
            try:
                encabezado = Image.open(header_logo).convert("RGBA")
            except (FileNotFoundError, OSError) as e:
                print(f"[AVISO] No se pudo abrir el logo de encabezado '{header_logo}' ({e}); pata sin encabezado.")

        pad_x, gap_logo, gap_grupo, sep_gap = 36, 30, 46, 22
        f = 1.0
        while True:
            alto_logo = int(max_logo_height * f)
            font_label = self._load_font(label_font_path, int(label_size * f))
            font_texto = self._load_font(label_font_path, int(text_size * f))
            paso_texto = int(text_size * f * 1.25)
            escalados, textos, anchos_grupo, altos = [], [], [], [int(60 * f)]
            for etiqueta, logos, texto in grupos:
                fila = []
                for im in logos:
                    k = min(alto_logo / im.height, (alto_logo * 2.4) / im.width)
                    fila.append(im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS))
                lineas = self._wrap_lines(texto.upper(), font_texto, int(300 * f)) if texto else []
                ancho_texto = max((self.draw.textbbox((0, 0), l, font=font_texto)[2] for l in lineas), default=0)
                escalados.append(fila)
                textos.append(lineas)
                if fila:
                    altos.append(alto_logo)
                if lineas:
                    altos.append(paso_texto * len(lineas))
                bl = self.draw.textbbox((0, 0), etiqueta, font=font_label)
                elementos = len(fila) + (1 if lineas else 0)
                anchos_grupo.append(
                    (bl[2] - bl[0]) + sep_gap * 2 + 2 + sum(i.width for i in fila) + ancho_texto + gap_logo * (elementos - 1)
                )
            box_w = sum(anchos_grupo) + gap_grupo * (len(grupos) - 1) + 2 * pad_x
            if box_w <= max_width or f <= 0.55:
                break
            f -= 0.05

        alto_contenido = max(altos)
        pad_y = int(28 * f)
        box_h = alto_contenido + 2 * pad_y
        if encabezado:
            kh = (70 * f) / encabezado.height
            encabezado = encabezado.resize((int(encabezado.width * kh), int(encabezado.height * kh)), Image.LANCZOS)
        header_h = encabezado.height if encabezado else 0
        header_w = encabezado.width if encabezado else 0
        gap_header = 16 if encabezado else 0

        box_x0 = int((self.width - box_w) / 2)
        box_y0 = int(y_position + header_h + gap_header)
        box_cy = box_y0 + box_h / 2

        # Marco: rectangulo redondeado dibujado a 3x (bordes suaves). Arriba queda
        # abierto bajo el logo de encabezado; abajo lo tapa la caja de contenido.
        marco_w = int(min(max(box_w + 300, header_w + 280), self.width - 80))
        marco_x0 = int((self.width - marco_w) / 2)
        marco_top = int(y_position + header_h / 2) if encabezado else int(box_y0 - 20)
        marco_h = int(box_cy - marco_top)
        S3 = 3
        capa = Image.new("RGBA", (marco_w * S3, marco_h * S3), (0, 0, 0, 0))
        ImageDraw.Draw(capa).rounded_rectangle(
            [0, 0, marco_w * S3 - 1, marco_h * S3 - 1], radius=34 * S3,
            outline=tuple(frame_color) + (255,), width=3 * S3,
        )
        if encabezado:
            hueco = (header_w + 36) * S3
            ImageDraw.Draw(capa).rectangle(
                [(marco_w * S3 - hueco) // 2, 0, (marco_w * S3 + hueco) // 2, 6 * S3 + 2], fill=(0, 0, 0, 0),
            )
        capa = capa.resize((marco_w, marco_h), Image.LANCZOS)
        self.image.paste(capa, (marco_x0, marco_top), capa)

        if encabezado:
            self.image.paste(encabezado, (int((self.width - header_w) / 2), int(y_position)), encabezado)

        self.draw = ImageDraw.Draw(self.image)
        self.draw.rounded_rectangle(
            [box_x0, box_y0, box_x0 + box_w, box_y0 + box_h], radius=int(20 * f), fill=tuple(box_fill),
        )

        x = box_x0 + pad_x
        hb = self.draw.textbbox((0, 0), "H", font=font_label)
        hbt = self.draw.textbbox((0, 0), "H", font=font_texto)
        for (etiqueta, _, _), fila, lineas in zip(grupos, escalados, textos):
            bl = self.draw.textbbox((0, 0), etiqueta, font=font_label)
            y_texto = box_cy - (hb[3] - hb[1]) / 2 - hb[1]
            self.draw.text((x - bl[0], y_texto), etiqueta, font=font_label, fill=tuple(label_color))
            x += (bl[2] - bl[0]) + sep_gap
            self.draw.line([(x, box_cy - alto_contenido * 0.34), (x, box_cy + alto_contenido * 0.34)], fill=tuple(label_color), width=2)
            x += 2 + sep_gap
            for im in fila:
                self.image.paste(im, (int(x), int(box_cy - im.height / 2)), im)
                x += im.width + gap_logo
            if lineas:
                y_linea = box_cy - paso_texto * len(lineas) / 2 + (paso_texto - (hbt[3] - hbt[1])) / 2 - hbt[1]
                for linea in lineas:
                    b = self.draw.textbbox((0, 0), linea, font=font_texto)
                    self.draw.text((x - b[0], y_linea), linea, font=font_texto, fill=(45, 45, 45))
                    y_linea += paso_texto
                x += max(self.draw.textbbox((0, 0), l, font=font_texto)[2] for l in lineas) + gap_logo
            x += gap_grupo - gap_logo

        return int(box_y0 + box_h)

    def save(self, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        self.image.save(output_path)
        return output_path
