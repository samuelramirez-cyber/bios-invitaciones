"""
assets_manager.py - Gestor centralizado de recursos (AssetRepository).

Punto unico de resolucion de fuentes, fondos, logos de marca y avatares de
ponentes desde assets/. Reemplaza las rutas hardcodeadas que usaban
CanvasEngine y LayoutDecisionEngine: apenas se depositen archivos reales en
las carpetas de assets/, el pipeline los recoge automaticamente sin cambiar
codigo. Todos los fallbacks son transparentes: nunca lanzan excepciones que
detengan el renderizado.
"""

import random
from pathlib import Path
from typing import Any, List, Optional, Union

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
BACKGROUNDS_DIR = ASSETS_DIR / "backgrounds"
ICONS_DIR = ASSETS_DIR / "icons"
SPEAKERS_DIR = ASSETS_DIR / "speakers"
MAESTRIA_LOGOS_DIR = ASSETS_DIR / "Logos Maestria"

# ---------------------------------------------------------------------------
# Logos reales de marca: insignia "Maestria <Categoria>" e iconos de linea.
# Nota: por decision del cliente, Gatos/Perros (mascotas) NUNCA se resuelven
# aqui aunque existan archivos en icons/ - el negocio es alimentacion para
# animales de produccion, no mascotas.
# ---------------------------------------------------------------------------

# Categoria canonica (ver layout_engine.CATEGORY_COLORS) -> sufijo de archivo
# en "Logos Maestria/{Marca}_Maestria_{sufijo}.png". PDV queda fuera a
# proposito (no es una linea productiva - pendiente de definir su disparador).
MAESTRIA_LOGO_SUFFIX = {
    "ganadera": "Ganadera",
    "porcicola": "Porcicola",
    "avicola": "Avicola",
    "equina": "Equina",
    "acuicola": "Acuicola",
    "general": "Campo",
}

# (categoria, sub_linea) -> nombre base del icono en "icons/{Marca}/{Marca}_<nombre>.png".
# Ganaderia y Avicola son ambiguas sin sub_linea (Carne/Leche, Ponedoras/Engorde)
# y no se resuelven sin ella - ver AssetRepository.get_category_icon().
CATEGORY_ICON_NAME = {
    ("porcicola", None): "Porcicultura",
    ("equina", None): "Equinos",
    ("acuicola", None): "Acuacultura",
    ("ganadera", "carne"): "Ganaderia_Carne",
    ("ganadera", "leche"): "Ganaderia_Leche",
    ("avicola", "ponedoras"): "Ponedoras",
    ("avicola", "engorde"): "Engorde",
}

# ---------------------------------------------------------------------------
# Tipografia corporativa por marca (regla de negocio confirmada por el cliente):
#   evento co-marca (Contegral + Finca a la vez) -> Alexandria
#   evento solo Contegral                        -> Montserrat
#   evento solo Finca                            -> Akwe Pro
# Alexandria/Montserrat son fuentes variables (un solo archivo, todos los
# pesos via ejes de variacion); Akwe Pro es licenciada (ROHH) y viene como
# archivos estaticos por peso.
# ---------------------------------------------------------------------------

VARIABLE_FONT_FILES = {
    "montserrat": FONTS_DIR / "Montserrat" / "Montserrat-Variable.ttf",
    "alexandria": FONTS_DIR / "Alexandria" / "Alexandria-Variable.ttf",
}
STATIC_FONT_FAMILY_DIRS = {
    "akwepro": FONTS_DIR / "Akwe Pro",
}

FONT_FAMILY_BY_MARCA = {
    frozenset({"contegral", "finca"}): "montserrat",  # alias "alexandria" mas abajo, ver resolver
    frozenset({"contegral"}): "montserrat",
    frozenset({"finca"}): "akwepro",
}
# (se define aparte para dejar explicita la regla de co-marca sin duplicar 'alexandria' como string suelto)
FONT_FAMILY_BY_MARCA[frozenset({"contegral", "finca"})] = "alexandria"

# Peso con nombre por rol semantico, segun lo que ofrece cada familia:
# Akwe Pro no tiene "Black" real -> se usa su ExtraBold como equivalente.
ROLE_WEIGHT_BY_FAMILY = {
    "alexandria": {"regular": "Regular", "bold": "Bold", "black": "Black"},
    "montserrat": {"regular": "Regular", "bold": "Bold", "black": "Black"},
    "akwepro": {"regular": "Regular", "bold": "Bold", "black": "ExtraBold"},
}
DEFAULT_FONT_FAMILY = "montserrat"  # marca desconocida/vacia -> fallback neutro


def _normalizar_marca_set(marca: Union[str, List[str], None]) -> frozenset:
    valores = marca if isinstance(marca, (list, tuple, set, frozenset)) else [marca]
    return frozenset(str(v).strip().lower() for v in valores if v)


def get_brand_font_name(marca: Union[str, List[str], None], role: str = "regular") -> str:
    """
    Nombre de fuente "virtual" (ej. 'alexandria-Bold') para pasar como
    font_path a los metodos de CanvasEngine. AssetRepository.get_font() lo
    reconoce y resuelve al archivo real (variable o estatico) + peso.
    `marca` acepta un string ('Finca') o una lista para eventos co-marca
    (['Contegral', 'Finca']).
    """
    claves = _normalizar_marca_set(marca)
    familia = FONT_FAMILY_BY_MARCA.get(claves, DEFAULT_FONT_FAMILY)
    peso = ROLE_WEIGHT_BY_FAMILY[familia].get(role, "Regular")
    return f"{familia}-{peso}"

DEFAULT_CANVAS_SIZE = (1080, 1920)
DEFAULT_BG_COLOR = (33, 33, 33)
SPEAKER_DEFAULT_NAME = "speaker_default.png"
FONT_EXTENSIONS = (".ttf", ".otf")
BACKGROUND_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}

# Palabras clave (sobre el nombre de archivo, en minusculas) para emparejar
# un fondo con una categoria/linea de negocio.
CATEGORY_KEYWORDS = {
    "ganaderia": ["vaca", "vacas", "ganado", "cebu", "potrero", "pastizal", "colinas", "finca_aerea"],
    "porcicultura": ["lechon", "lechones", "cerda", "cerdo", "porcicola"],
    "avicola": ["pollit", "gallina", "avicola", "pollo"],
    "campo": ["paisaje", "granja", "estanque", "campo"],
}
# Alias de categoria usados en el payload (ver layout_engine.CATEGORY_COLORS)
# hacia la categoria canonica de busqueda de fondos.
CATEGORY_ALIASES = {
    "ganadera": "ganaderia",
    "porcicola": "porcicultura",
    "avicola": "avicola",
    "general": "campo",
}


class AssetRepository:
    """
    Inspecciona assets/ en el momento de cada llamada (sin cache), por lo que
    un archivo depositado despues de iniciar el proceso se recoge de
    inmediato en la siguiente invocacion. Cada metodo tiene un fallback que
    mantiene la ejecucion sin lanzar excepciones bloqueantes.
    """

    def __init__(
        self,
        fonts_dir: Optional[Path] = None,
        backgrounds_dir: Optional[Path] = None,
        icons_dir: Optional[Path] = None,
        speakers_dir: Optional[Path] = None,
    ):
        self.fonts_dir = Path(fonts_dir) if fonts_dir else FONTS_DIR
        self.backgrounds_dir = Path(backgrounds_dir) if backgrounds_dir else BACKGROUNDS_DIR
        self.icons_dir = Path(icons_dir) if icons_dir else ICONS_DIR
        self.speakers_dir = Path(speakers_dir) if speakers_dir else SPEAKERS_DIR

    # ------------------------------------------------------------------
    # Fuentes
    # ------------------------------------------------------------------

    def get_font(self, font_name: str, size: int) -> ImageFont.ImageFont:
        """
        Busca `font_name` (con o sin extension, ej. 'Arial-Bold' o
        'Arial-Bold.ttf') en assets/fonts/. Si no es un archivo literal,
        intenta interpretarlo como fuente de marca "familia-Peso" (ej.
        'montserrat-Bold', ver get_brand_font_name) antes de rendirse. Si
        nada de eso funciona, cae de forma transparente a la fuente bitmap
        por defecto de Pillow - el render continua en vez de detenerse.
        """
        ruta = self._resolver_ruta_fuente(font_name)
        if ruta:
            try:
                return ImageFont.truetype(str(ruta), size)
            except OSError as e:
                print(f"[AVISO] La fuente '{ruta.name}' no se pudo abrir ({e}); usando fuente por defecto de Pillow.")
        else:
            fuente_marca = self._resolver_fuente_de_marca(font_name, size)
            if fuente_marca:
                return fuente_marca
            print(f"[AVISO] Fuente '{font_name}' no encontrada en assets/fonts/; usando fuente por defecto de Pillow.")

        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            # Pillow < 10.1 no acepta `size` en load_default()
            return ImageFont.load_default()

    def _resolver_fuente_de_marca(self, font_name: str, size: int) -> Optional[ImageFont.ImageFont]:
        """Interpreta 'familia-Peso' (ej. 'montserrat-ExtraBold') generado por get_brand_font_name()."""
        if not font_name or "-" not in font_name:
            return None
        familia, _, peso = font_name.rpartition("-")
        familia = familia.strip().lower().replace(" ", "")

        if familia in VARIABLE_FONT_FILES:
            ruta = VARIABLE_FONT_FILES[familia]
            if not ruta.is_file():
                return None
            try:
                font = ImageFont.truetype(str(ruta), size)
                font.set_variation_by_name(peso.encode("utf-8"))
                return font
            except Exception as e:
                print(f"[AVISO] No se pudo aplicar el peso '{peso}' a la fuente variable '{familia}': {e}")
                try:
                    return ImageFont.truetype(str(ruta), size)
                except OSError:
                    return None

        if familia in STATIC_FONT_FAMILY_DIRS:
            directorio = STATIC_FONT_FAMILY_DIRS[familia]
            for ext in FONT_EXTENSIONS:
                candidata = directorio / f"Akwe-Pro-{peso}{ext}"
                if candidata.is_file():
                    try:
                        return ImageFont.truetype(str(candidata), size)
                    except OSError:
                        return None
            return None

        return None

    def _resolver_ruta_fuente(self, font_name: str) -> Optional[Path]:
        if not font_name:
            return None
        directo = self.fonts_dir / font_name
        if directo.is_file():
            return directo
        for ext in FONT_EXTENSIONS:
            candidata = self.fonts_dir / f"{font_name}{ext}"
            if candidata.is_file():
                return candidata
        return None

    # ------------------------------------------------------------------
    # Fondos por categoria
    # ------------------------------------------------------------------

    def get_background(self, category: str, canvas_size=DEFAULT_CANVAS_SIZE) -> Image.Image:
        """
        Elige un fondo de assets/backgrounds/ cuyo nombre de archivo coincida
        con `category` (acepta tanto categorias canonicas como
        ganaderia/porcicultura/avicola/campo, y alias del payload como
        ganadera/porcicola/avicola/general). Sin coincidencias por palabra
        clave usa cualquier fondo disponible; sin fondos en absoluto, genera
        un lienzo de color solido.
        """
        categoria = CATEGORY_ALIASES.get(category, category)
        candidatos = self._listar_fondos_por_categoria(categoria)

        if not candidatos:
            candidatos = self._listar_todos_los_fondos()

        if candidatos:
            elegido = random.choice(candidatos)
            try:
                return Image.open(elegido).convert("RGB")
            except OSError as e:
                print(f"[AVISO] El fondo '{elegido.name}' no se pudo abrir ({e}); usando color solido por defecto.")

        print(f"[AVISO] Sin fondos disponibles para la categoria '{category}'; usando color solido por defecto.")
        return Image.new("RGB", canvas_size, DEFAULT_BG_COLOR)

    def _listar_todos_los_fondos(self) -> List[Path]:
        if not self.backgrounds_dir.is_dir():
            return []
        return [
            p for p in self.backgrounds_dir.iterdir()
            if p.is_file() and p.suffix.lower() in BACKGROUND_EXTENSIONS
        ]

    def _listar_fondos_por_categoria(self, categoria: str) -> List[Path]:
        palabras = CATEGORY_KEYWORDS.get(categoria, [])
        if not palabras:
            return []
        return [
            p for p in self._listar_todos_los_fondos()
            if any(palabra in p.stem.lower() for palabra in palabras)
        ]

    # ------------------------------------------------------------------
    # Logos de marca
    # ------------------------------------------------------------------

    def get_logo(self, brand_name: Union[str, List[str], None]) -> Optional[Path]:
        """
        Ruta del PNG transparente de `brand_name` ('contegral', 'finca',
        'grupo_bios', sin importar mayusculas/espacios) en assets/icons/.
        Devuelve None si no existe - quien llama decide el fallback
        (tipicamente texto, ver render_sponsor_fallback). Un evento co-marca
        (`brand_name` como lista con mas de un valor) tampoco tiene un logo
        unico definido - devuelve None de una vez, sin lanzar excepcion.
        """
        marca = self._una_sola_marca(brand_name)
        if not marca:
            return None
        slug = marca.strip().lower().replace(" ", "_")
        for candidata in (self.icons_dir / f"logo_{slug}.png", self.icons_dir / f"{slug}.png"):
            if candidata.is_file():
                return candidata
        print(f"[AVISO] Logo de marca '{marca}' no encontrado en assets/icons/.")
        return None

    @staticmethod
    def _una_sola_marca(marca: Union[str, List[str], None]) -> Optional[str]:
        """Colapsa `marca` (string o lista) a un unico nombre; None si es ambigua (0 o 2+ valores) o vacia."""
        if not marca:
            return None
        if isinstance(marca, (list, tuple, set, frozenset)):
            valores = [v for v in marca if v]
            if len(valores) != 1:
                return None
            return valores[0]
        return marca

    def get_maestria_logo(self, marca: Union[str, List[str], None], categoria: str) -> Optional[Path]:
        """
        PNG real de la insignia "Maestria <Categoria>" para `marca`, desde
        assets/Logos Maestria/{Marca}_Maestria_{Sufijo}.png. Devuelve None
        (sin excepcion) si la marca es ambigua (evento co-marca), la
        categoria no tiene logo definido (ej. PDV, pendiente) o el archivo no
        existe - quien llama sigue mostrando el badge de texto como fallback.
        """
        marca_unica = self._una_sola_marca(marca)
        if not marca_unica:
            return None
        sufijo = MAESTRIA_LOGO_SUFFIX.get(categoria)
        if not sufijo:
            return None
        candidata = MAESTRIA_LOGOS_DIR / f"{marca_unica.strip().capitalize()}_Maestria_{sufijo}.png"
        return candidata if candidata.is_file() else None

    def get_category_icon(
        self, marca: Union[str, List[str], None], categoria: str, sub_linea: Optional[str] = None,
    ) -> Optional[Path]:
        """
        PNG real del icono de linea para `marca`+`categoria` (+`sub_linea`
        cuando la categoria lo requiere: Ganaderia -> 'carne'/'leche',
        Avicola -> 'ponedoras'/'engorde'), desde assets/icons/{Marca}/.
        Devuelve None (sin excepcion) si la marca es ambigua, la combinacion
        categoria/sub_linea no esta definida (incluye Ganaderia/Avicola SIN
        sub_linea - son ambiguas de proposito) o el archivo no existe.
        Gatos/Perros nunca se resuelven aqui: no son lineas de este negocio.
        """
        marca_unica = self._una_sola_marca(marca)
        if not marca_unica:
            return None
        clave_sub = str(sub_linea).strip().lower() if sub_linea else None
        nombre_icono = CATEGORY_ICON_NAME.get((categoria, clave_sub))
        if not nombre_icono:
            return None

        slug_marca = marca_unica.strip().capitalize()
        directorio = self.icons_dir / slug_marca
        if not directorio.is_dir():
            return None

        candidatos = [f"{slug_marca}_{nombre_icono}.png"]
        if nombre_icono == "Ponedoras":
            candidatos.append(f"{slug_marca}_Ponedora.png")  # Finca usa singular
        if nombre_icono == "Acuacultura":
            candidatos.append(f"Contegra_{nombre_icono}.png")  # typo real en el archivo de Contegral

        for nombre_archivo in candidatos:
            candidata = directorio / nombre_archivo
            if candidata.is_file():
                return candidata
        return None

    # ------------------------------------------------------------------
    # Avatar de ponente
    # ------------------------------------------------------------------

    def get_speaker_avatar(self, photo_path: Optional[str]) -> Path:
        """
        Resuelve la foto del ponente dentro de assets/speakers/. Si
        `photo_path` es nulo/vacio o el archivo no existe, devuelve el avatar
        neutro por defecto (generandolo con Pillow si tampoco existe aun).
        """
        if photo_path:
            candidata = Path(photo_path)
            if not candidata.is_absolute():
                candidata = self.speakers_dir / photo_path
            if candidata.is_file():
                return candidata
            print(f"[AVISO] Foto de ponente no encontrada en assets/speakers/: '{photo_path}'; usando avatar por defecto.")

        return self._avatar_por_defecto()

    def _avatar_por_defecto(self) -> Path:
        destino = self.speakers_dir / SPEAKER_DEFAULT_NAME
        if not destino.is_file():
            self.speakers_dir.mkdir(parents=True, exist_ok=True)
            self._generar_avatar_placeholder(destino)
        return destino

    @staticmethod
    def _generar_avatar_placeholder(destino: Path):
        size = (400, 400)
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((0, 0, size[0], size[1]), fill=(158, 158, 158, 255))
        draw.ellipse((130, 90, 270, 230), fill=(207, 207, 207, 255))
        draw.pieslice((70, 220, 330, 480), start=180, end=360, fill=(207, 207, 207, 255))
        img.save(destino)
