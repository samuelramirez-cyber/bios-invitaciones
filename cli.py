"""CLI para generar invitaciones desde consola, con soporte de payload mock."""

import argparse
import json
from pathlib import Path

import main as pipeline

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BASE_DIR / "output" / "invitacion_render.png"
MOCK_PAYLOAD_PATH = BASE_DIR / "payload_mock.json"

MOCK_PAYLOAD = {
    "marca": "Finca",
    "categoria": "ganadera",
    "palabra_categoria": "Encuentro",
    "palabra_titulo": "Tecnico",
    "background_file": "potrero_extenso_aereo_dron.jpg",
    "fecha_texto": ["24 de Septiembre", "de 2026", "3:00 p.m.", "Finca La Esperanza"],
    "tema_evento": "Jornada Tecnica de Nutricion Animal",
    "ponentes": [
        {"name": "Dr. Juan Perez", "role": "Medico Veterinario", "empresa": "Grupo Bios", "tema": "Nutricion de precision", "photo": ""},
        {"name": "Ing. Maria Gomez", "role": "Zootecnista", "empresa": "Finca", "tema": "Suplementacion estrategica", "photo": ""},
        {"name": "Dr. Carlos Ruiz", "role": "Nutricionista Animal", "empresa": "Grupo Bios", "tema": "Manejo de praderas", "photo": ""},
        {"name": "Ing. Laura Diaz", "role": "Ingeniera Agropecuaria", "empresa": "Finca", "tema": "Costos de produccion", "photo": ""},
    ],
    "apoyos_texto": "Con el apoyo de Contegral",
}


def generar_payload_mock(destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as f:
        json.dump(MOCK_PAYLOAD, f, ensure_ascii=False, indent=2)
    print(f"[MOCK] payload de prueba (4 ponentes) generado en: {destino}")
    return destino


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Genera una invitacion PNG a partir de un payload JSON."
    )
    parser.add_argument(
        "-i", "--input", type=str, default=None,
        help="Ruta al archivo JSON con los datos de la invitacion.",
    )
    parser.add_argument(
        "-o", "--output", type=str, default=str(DEFAULT_OUTPUT),
        help="Ruta y nombre del PNG de salida (por defecto output/invitacion_render.png).",
    )
    parser.add_argument(
        "-m", "--mock", action="store_true",
        help="Genera automaticamente un payload.json de prueba con 4 ponentes si no se especifica --input.",
    )
    return parser


def main():
    parser = construir_parser()
    args = parser.parse_args()

    if args.input:
        payload_path = Path(args.input)
    elif args.mock:
        payload_path = generar_payload_mock(MOCK_PAYLOAD_PATH)
    else:
        parser.error("Debes especificar --input <archivo.json> o usar --mock para generar uno de prueba.")
        return

    output_path = Path(args.output)
    pipeline.main(payload_path=payload_path, output_path=output_path)


if __name__ == "__main__":
    main()
