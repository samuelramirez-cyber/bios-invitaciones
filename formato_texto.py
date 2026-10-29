"""
formato_texto.py - mayusculas iniciales de los textos que se imprimen en la pieza.

- nombre_propio(): lugares, direcciones, municipios -> "Carrera 36 # 4A-59", "Casa de la Justicia".
- parrafo(): frases y descripciones -> mayuscula al empezar cada oracion y en las marcas conocidas.

Si el texto llega TODO EN MAYUSCULAS o todo en minusculas se normaliza; si ya viene mezclado
(ej. "Casa GREA") se respeta lo que escribio la persona y solo se corrige la letra inicial.
"""

import re
from pathlib import Path
from typing import List

CONECTORES = frozenset("a al con de del e el en la las lo los o para por sin su sus y".split())
_MARCAS = ("Contegral", "Finca", "Bios", "Grupo Bios", "Fedegán", "Agasurbol")
_TERMINADOR = re.compile(r"([.!?]\s+|[.!?]$)")


def _es_uniforme(texto: str) -> bool:
    """True si las palabras (sin contar las que llevan numeros, como '4a-59') van todas en mayusculas o todas en minusculas."""
    letras = "".join(c for w in texto.split() if not re.search(r"\d", w) for c in w if c.isalpha())
    return bool(letras) and (letras == letras.upper() or letras == letras.lower())


def _mayus_tras_numero(palabra: str) -> str:
    """'4a-59' -> '4A-59' (letra pegada a un numero va en mayuscula)."""
    if not re.search(r"\d", palabra):
        return palabra
    return re.sub(r"(?<=\d)([a-záéíóúñ])", lambda m: m.group(1).upper(), palabra)


def _inicial(palabra: str) -> str:
    for i, c in enumerate(palabra):
        if c.isalpha():
            return palabra[:i] + c.upper() + palabra[i + 1:]
    return palabra


def nombre_propio(texto: str) -> str:
    """Una linea de lugar/direccion/municipio con la inicial de cada palabra en mayuscula."""
    t = " ".join((texto or "").split())
    if not t:
        return ""
    if _es_uniforme(t):
        t = t.lower()
    salida: List[str] = []
    for i, palabra in enumerate(t.split()):
        limpia = palabra.lower().strip(".,;:()")
        if i > 0 and limpia in CONECTORES:
            salida.append(palabra)
        else:
            salida.append(_mayus_tras_numero(_inicial(palabra)))
    return " ".join(salida)


def parrafo(texto: str) -> str:
    """Mayuscula al inicio de cada oracion y en las marcas del negocio; respeta el resto."""
    t = " ".join((texto or "").split())
    if not t:
        return ""
    if _es_uniforme(t):
        t = t.lower()
    partes = _TERMINADOR.split(t)
    rehecho = []
    for fragmento in partes:
        rehecho.append(fragmento if _TERMINADOR.fullmatch(fragmento) else _inicial(fragmento))
    t = "".join(rehecho)
    for marca in _MARCAS:
        t = re.sub(rf"\b{re.escape(marca)}\b", marca, t, flags=re.IGNORECASE)
    return t
