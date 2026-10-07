"""
LayoutDecisionEngine - capa de inteligencia de negocio.
Analiza un payload y decide que caso visual (config JSON de coordenadas) usar.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from assets_manager import AssetRepository

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_DIR = BASE_DIR / "config" / "layouts"
DEFAULT_SPEAKERS_DIR = BASE_DIR / "assets" / "speakers"

REQUIRED_CONFIG_KEYS = ("safe_area", "bounding_boxes", "colors")

# Colores de acento por categoria/linea de negocio. ganadera/porcicola/avicola
# se extrajeron por muestreo de pixeles directamente de assets/Templates/
# (piezas reales aprobadas), no inventados:
#   ganadera  -> #D41117 (rojo,  ej. "Charla Maestra" - Union / Duitama)
#   porcicola -> #53AD32 (verde, ej. "Charla Maestra" - Neiva / Ricaurte)
#   avicola   -> #DE5F10 (naranja, ej. "Charla Maestra" - Gallinas Ponedoras)
# cunicola/equina/acuicola son PLACEHOLDER de color (no hay pieza de referencia
# en assets/Templates/ todavia para esas lineas) - ajustar cuando llegue una
# plantilla real aprobada. Nota: el cliente confirmo que Cunicultura no es una
# linea real del negocio (alimentacion para animales de produccion, no
# mascotas) - se deja el soporte tecnico por si acaso, pero no se expone/usa.
CATEGORY_COLORS = {
    "ganadera": (212, 17, 23),
    "porcicola": (83, 173, 50),
    "avicola": (222, 95, 16),
    "cunicola": (142, 68, 173),   # placeholder - sin plantilla de referencia aun
    "equina": (183, 121, 31),     # placeholder - sin plantilla de referencia aun
    "acuicola": (25, 118, 158),   # placeholder - sin plantilla de referencia aun
    "general": (158, 158, 158),
}
CATEGORY_MAESTRIA_LABEL = {
    "ganadera": "Ganadera",
    "porcicola": "Porcícola",
    "avicola": "Avícola",
    "cunicola": "Cunícola",
    "equina": "Equina",
    "acuicola": "Acuícola",
    "general": "en el Campo Colombiano",
}

# Sinonimos aceptados en payload/CSV -> clave canonica de CATEGORY_COLORS.
# Cubre tanto los alias cortos usados en payloads existentes (ganadera,
# porcicola, general) como las formas "largas" pedidas para el CSV en lote
# (Ganaderia, Porcicultura, Avicola, Campo) y las lineas de Equinos/Acuicultura.
CATEGORY_SYNONYMS = {
    "ganadera": "ganadera", "ganaderia": "ganadera", "ganado": "ganadera",
    "porcicola": "porcicola", "porcicultura": "porcicola", "porcicultor": "porcicola",
    "avicola": "avicola", "avicultura": "avicola", "aves": "avicola",
    "cunicola": "cunicola", "cunicultura": "cunicola", "conejos": "cunicola", "conejo": "cunicola",
    "equina": "equina", "equino": "equina", "equinos": "equina", "caballos": "equina", "caballo": "equina", "hipica": "equina",
    "acuicola": "acuicola", "acuicultura": "acuicola", "acuacultura": "acuicola", "piscicultura": "acuicola", "peces": "acuicola",
    "general": "general", "campo": "general", "mixto": "general",
}


def _quitar_tildes(texto: str) -> str:
    for original, reemplazo in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        texto = texto.replace(original, reemplazo)
    return texto


def normalizar_categoria(valor: str) -> str:
    """Acepta variantes de mayusculas/tildes/forma larga o corta y devuelve la clave canonica."""
    if not valor:
        return "general"
    clave = _quitar_tildes(str(valor).strip().lower())
    return CATEGORY_SYNONYMS.get(clave, "general")


def resolver_categoria(valor: Any) -> Dict[str, Any]:
    """
    Resuelve `valor` (un string de categoria, o una LISTA de varias - un evento
    puede cubrir mas de una linea de negocio a la vez, ej. "Ganaderia y
    Porcicultura") a color de acento + etiqueta de la insignia "Maestria".

    - Un solo valor (string, o lista de un elemento): color y etiqueta propios
      de esa categoria (comportamiento de siempre).
    - Varios valores: no existe un color "mezclado" con respaldo en plantillas
      reales, asi que se usa el gris neutro de 'general'; la etiqueta de la
      insignia si lista las categorias reales combinadas (ej. "Ganadera,
      Porcicola y Avicola") en vez del generico "en el Campo Colombiano".
    """
    valores = valor if isinstance(valor, list) else [valor]
    valores = [v for v in valores if v]

    claves: List[str] = []
    for v in valores:
        clave = normalizar_categoria(v)
        if clave not in claves:
            claves.append(clave)

    if len(claves) <= 1:
        clave_unica = claves[0] if claves else "general"
        return {
            "categoria": clave_unica,
            "accent_color": CATEGORY_COLORS[clave_unica],
            "maestria_label": CATEGORY_MAESTRIA_LABEL[clave_unica],
        }

    etiquetas = [CATEGORY_MAESTRIA_LABEL[c] for c in claves if c != "general"]
    if len(etiquetas) <= 1:
        etiqueta_combinada = CATEGORY_MAESTRIA_LABEL["general"]
    elif len(etiquetas) == 2:
        etiqueta_combinada = f"{etiquetas[0]} y {etiquetas[1]}"
    else:
        etiqueta_combinada = ", ".join(etiquetas[:-1]) + f" y {etiquetas[-1]}"

    return {
        "categoria": "general",
        "accent_color": CATEGORY_COLORS["general"],
        "maestria_label": etiqueta_combinada,
    }


class LayoutConfigError(Exception):
    """Se lanza cuando un JSON de configuracion de layout no existe o esta malformado."""


class LayoutDecisionEngine:
    """
    Determina, a partir de un payload (marca, ponentes, fotos disponibles),
    que caso visual aplica y devuelve la configuracion de coordenadas/fuentes
    correspondiente para que el CanvasEngine renderice la pieza.
    """

    # Mapa de casos con configuracion dedicada (dummy, provistos en esta mision)
    CASE_MAP = {
        0: "case_a_text_only",
        1: "case_b_single_speaker",
        4: "case_d_grid_4",
    }
    # Cantidades de ponentes sin config dedicada (2, 3, 5) usan esta aproximacion
    FALLBACK_CASE = "case_d_grid_4"

    def __init__(
        self,
        config_dir: Optional[str] = None,
        speakers_dir: Optional[str] = None,
        asset_repo: Optional[AssetRepository] = None,
    ):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.speakers_dir = Path(speakers_dir) if speakers_dir else DEFAULT_SPEAKERS_DIR
        self.asset_repo = asset_repo or AssetRepository(speakers_dir=self.speakers_dir)

    # ------------------------------------------------------------------
    # Evaluacion del payload
    # ------------------------------------------------------------------

    def _evaluar_ponente(self, ponente: Any) -> Dict[str, Any]:
        """
        Normaliza un ponente (str o dict) y resuelve su foto via
        AssetRepository.get_speaker_avatar() - que siempre devuelve una ruta
        valida (la foto pedida o el avatar neutro por defecto, sin excepciones).
        """
        if isinstance(ponente, dict):
            datos = dict(ponente)
        else:
            datos = {"name": str(ponente), "role": ""}

        photo_file = datos.get("photo")
        avatar_path = self.asset_repo.get_speaker_avatar(photo_file)
        candidata_solicitada = (self.speakers_dir / photo_file) if photo_file else None

        datos["photo_path"] = str(avatar_path)
        datos["has_fallback_avatar"] = candidata_solicitada is None or avatar_path != candidata_solicitada
        return datos

    def evaluate_payload(self, payload_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Lee marca y ponentes del payload, verifica fotos, y decide el caso visual.
        Retorna: marca, case_id, config_path, num_ponentes, ponentes (normalizados).
        """
        marca = payload_dict.get("marca", "")
        ponentes_raw: List[Any] = payload_dict.get("ponentes", [])
        ponentes = [self._evaluar_ponente(p) for p in ponentes_raw]
        num_ponentes = len(ponentes)

        case_id = self.CASE_MAP.get(num_ponentes)
        if case_id is None:
            print(
                f"[AVISO] No hay configuracion dedicada para {num_ponentes} ponentes; "
                f"usando '{self.FALLBACK_CASE}' como aproximacion."
            )
            case_id = self.FALLBACK_CASE

        config_path = self.config_dir / f"{case_id}.json"

        categoria_original = payload_dict.get("categoria", "general")
        valores_categoria = categoria_original if isinstance(categoria_original, list) else [categoria_original]
        for valor in valores_categoria:
            if not valor:
                continue
            clave_normalizada = _quitar_tildes(str(valor).strip().lower())
            if clave_normalizada not in CATEGORY_SYNONYMS:
                print(f"[AVISO] Categoria '{valor}' no reconocida; se ignora en el calculo de color/etiqueta.")

        resuelto = resolver_categoria(categoria_original)

        return {
            "marca": marca,
            "case_id": case_id,
            "config_path": str(config_path),
            "num_ponentes": num_ponentes,
            "ponentes": ponentes,
            "categoria": resuelto["categoria"],
            "accent_color": resuelto["accent_color"],
            "maestria_label": resuelto["maestria_label"],
        }

    # ------------------------------------------------------------------
    # Carga y validacion de configuracion
    # ------------------------------------------------------------------

    def load_layout_config(self, case_id_or_path: str) -> Dict[str, Any]:
        """
        Parsea el JSON de coordenadas para `case_id_or_path` (nombre de caso o
        ruta directa) y valida que contenga las claves requeridas:
        safe_area, bounding_boxes, colors.
        """
        path = Path(case_id_or_path)
        if path.suffix.lower() != ".json":
            path = self.config_dir / f"{case_id_or_path}.json"

        if not path.is_file():
            raise LayoutConfigError(f"No se encontro el archivo de configuracion de layout: {path}")

        try:
            with path.open("r", encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            raise LayoutConfigError(f"El archivo de configuracion '{path}' esta malformado: {e}")

        if not isinstance(config, dict):
            raise LayoutConfigError(f"El archivo de configuracion '{path}' debe ser un objeto JSON.")

        faltantes = [clave for clave in REQUIRED_CONFIG_KEYS if clave not in config]
        if faltantes:
            raise LayoutConfigError(
                f"El archivo '{path}' no contiene las claves requeridas: {faltantes}"
            )

        return config
