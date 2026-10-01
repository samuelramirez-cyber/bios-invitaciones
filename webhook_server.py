"""
webhook_server.py - Microservidor Flask que recibe respuestas de un Google
Form (via webhook de Apps Script) y genera automaticamente la invitacion
correspondiente con el pipeline existente (LayoutDecisionEngine + CanvasEngine).

Endpoint: POST /api/v1/invitaciones/webhook
Cuerpo esperado (JSON, mismos campos que las columnas del CSV en lote - ver
batch_processor.py): marca, tipo_evento, maestria, titulo, fecha, hora, lugar,
ponentes, apoyos_texto.
  - ponentes acepta DOS formatos: una lista de objetos
    [{"nombre":.., "cargo":.., "empresa":.., "tema":.., "foto":..}, ...]
    (recomendado para JSON), o el mismo texto delimitado del CSV en lote
    ("Nombre|Cargo|Empresa|Tema; Nombre2|...") para reusar una respuesta de
    formulario de texto libre.
  - tipo_evento acepta un string simple (Ganaderia/Porcicultura/Avicola/
    Cunicultura/Equinos/Campo), un string con '+' para varias lineas a la
    vez ("Ganaderia+Porcicultura"), o directamente una lista JSON.
"""

import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, request

import main as pipeline
from batch_processor import parsear_ponentes_delimitados, validar_payload_minimo

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output" / "webhook"

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Mapeo de respuestas de formulario -> payload interno
# ---------------------------------------------------------------------------

def _mapear_ponentes(valor: Any) -> List[Dict[str, str]]:
    if isinstance(valor, list):
        ponentes = []
        for p in valor:
            if not isinstance(p, dict):
                continue
            nombre = str(p.get("nombre") or p.get("name") or "").strip()
            if not nombre:
                continue
            ponentes.append({
                "name": nombre,
                "role": str(p.get("cargo") or p.get("role") or "").strip(),
                "empresa": str(p.get("empresa") or p.get("company") or "").strip(),
                "tema": str(p.get("tema") or p.get("topic") or "").strip(),
                "photo": str(p.get("foto") or p.get("photo") or "").strip(),
            })
        return ponentes
    if isinstance(valor, str) and valor.strip():
        return parsear_ponentes_delimitados(valor)
    return []


def _mapear_categoria(valor: Any) -> Any:
    """
    Acepta 'tipo_evento' como string simple, string con '+' para varias
    lineas ("Ganaderia+Porcicultura") o directamente una lista JSON
    (["Ganaderia", "Porcicultura"]) - ver layout_engine.resolver_categoria.
    """
    if isinstance(valor, list):
        return [str(v).strip() for v in valor if str(v).strip()]
    texto = str(valor or "").strip()
    partes = [p.strip() for p in texto.split("+") if p.strip()]
    if len(partes) <= 1:
        return partes[0] if partes else ""
    return partes


def mapear_payload_formulario(datos: Dict[str, Any]) -> Dict[str, Any]:
    """Traduce las respuestas planas de un Google Form al payload interno del CanvasEngine."""

    def limpio(clave: str) -> str:
        return str(datos.get(clave) or "").strip()

    payload: Dict[str, Any] = {
        "marca": limpio("marca"),
        "categoria": _mapear_categoria(datos.get("tipo_evento")),
        "palabra_categoria": "Charla",
        "palabra_titulo": "Maestra",
        "tema_evento": limpio("titulo"),
        "fecha_texto": [v for v in (limpio("fecha"), limpio("hora"), limpio("lugar")) if v],
        "ponentes": _mapear_ponentes(datos.get("ponentes")),
        "apoyos_texto": limpio("apoyos_texto"),
    }
    if limpio("maestria"):
        payload["maestria_label"] = limpio("maestria")
    return payload


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/v1/invitaciones/webhook")
def recibir_webhook():
    """Recibe la respuesta del formulario, genera el PNG y devuelve su ruta + tiempo de proceso."""
    inicio = time.perf_counter()

    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"status": "error", "error": "El cuerpo de la peticion debe ser un objeto JSON valido."}), 400

    try:
        payload = mapear_payload_formulario(datos)
        validar_payload_minimo(payload)
    except ValueError as e:
        return jsonify({"status": "error", "error": f"Datos de formulario invalidos: {e}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "error": f"No se pudo interpretar el formulario: {type(e).__name__}: {e}"}), 400

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    nombre_archivo = f"invitacion_{int(time.time() * 1000)}.png"
    destino = OUTPUT_DIR / nombre_archivo

    try:
        resultado = pipeline.generar_invitacion(payload, destino)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": f"Fallo al generar la invitacion: {type(e).__name__}: {e}"}), 500

    duracion_ms = (time.perf_counter() - inicio) * 1000
    return jsonify({
        "status": "ok",
        "output_path": str(resultado),
        "duracion_ms": round(duracion_ms, 1),
    }), 201


@app.get("/api/v1/invitaciones/health")
def health():
    """Endpoint simple de salud, usado por test_webhook.py para esperar a que el servidor arranque."""
    return jsonify({"status": "ok"}), 200


@app.errorhandler(404)
def _no_encontrado(_e):
    return jsonify({"status": "error", "error": "Ruta no encontrada."}), 404


@app.errorhandler(500)
def _error_interno(_e):
    return jsonify({"status": "error", "error": "Error interno del servidor."}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
