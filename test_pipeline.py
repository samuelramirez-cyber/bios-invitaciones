"""
Script de integracion: payload -> LayoutDecisionEngine -> CanvasEngine.
Delega el renderizado en main.generar_invitacion() (fuente unica de verdad del
pipeline) e imprime el diagnostico de la decision de layout antes de renderizar.
"""

import json
from pathlib import Path

from layout_engine import LayoutDecisionEngine
import main as pipeline

BASE_DIR = Path(__file__).resolve().parent
PAYLOAD_PATH = BASE_DIR / "payload_pipeline_test.json"


def main():
    with PAYLOAD_PATH.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    decision = LayoutDecisionEngine().evaluate_payload(payload)
    print(
        f"Caso visual seleccionado: {decision['case_id']} "
        f"(categoria={decision['categoria']}, {decision['num_ponentes']} ponentes)"
    )
    for ponente in decision["ponentes"]:
        print(f"  - {ponente['name']}: has_fallback_avatar={ponente['has_fallback_avatar']}")

    output_path = BASE_DIR / "output" / "invitacion_integrada.png"
    pipeline.generar_invitacion(payload, output_path)
    print(f"Invitacion integrada generada: {output_path}")


if __name__ == "__main__":
    main()
