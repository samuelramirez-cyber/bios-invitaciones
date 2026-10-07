"""
spellcheck.py - revision ortografica (espanol) de los textos que van impresos en la pieza.

Usa el diccionario Hunspell es (assets/dictionaries/es/) via spylls, 100% offline,
mas un diccionario propio del negocio (config/diccionario_propio.txt: marcas,
terminos tecnicos y municipios) para no marcar como error palabras validas.
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set, Tuple

from spylls.hunspell import Dictionary

BASE_DIR = Path(__file__).resolve().parent
DICT_BASE = BASE_DIR / "assets" / "dictionaries" / "es" / "index"
CUSTOM_WORDS_FILE = BASE_DIR / "config" / "diccionario_propio.txt"

WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
MIN_LEN = 3


@lru_cache(maxsize=1)
def _cargar() -> Tuple[Dictionary, Set[str]]:
    propias: Set[str] = set()
    if CUSTOM_WORDS_FILE.is_file():
        for linea in CUSTOM_WORDS_FILE.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#"):
                propias.add(linea.lower())
    return Dictionary.from_files(str(DICT_BASE)), propias


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def revisar_texto(texto: str) -> List[Dict]:
    """Palabras mal escritas en `texto`, sin repetir: [{"palabra", "sugerencias"}]."""
    if not texto or not texto.strip():
        return []
    diccionario, propias = _cargar()
    vistas, errores = set(), []
    for palabra in WORD_RE.findall(texto):
        clave = palabra.lower()
        if len(palabra) < MIN_LEN or clave in vistas or clave in propias:
            continue
        vistas.add(clave)
        if not diccionario.lookup(palabra):
            # Una palabra propia del negocio escrita sin tilde (porcicola -> porcícola) va de primera.
            propias_parecidas = [
                w.capitalize() if palabra[0].isupper() else w
                for w in propias if _sin_tildes(w) == _sin_tildes(clave)
            ]
            sugerencias = propias_parecidas + [x for x in diccionario.suggest(palabra) if x.lower() not in propias_parecidas]
            errores.append({"palabra": palabra, "sugerencias": sugerencias[:3]})
    return errores


def formatear_errores(errores: List[Dict]) -> str:
    """'nutricion → nutrición, nutricio'  (una entrada por palabra, separadas por ' · ')."""
    return " · ".join(
        f"**{e['palabra']}**" + (f" → {', '.join(e['sugerencias'])}" if e["sugerencias"] else "")
        for e in errores
    )
