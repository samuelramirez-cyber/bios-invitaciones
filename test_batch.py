"""
Runner: procesa data/batch_sample.csv con batch_processor.py, exporta los
PNGs a output/batch/ y guarda el reporte de trazabilidad en output/batch/summary.json.
"""

import json
from pathlib import Path

from batch_processor import generar_reporte_resumen, process_csv_file

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "batch_sample.csv"
OUTPUT_DIR = BASE_DIR / "output" / "batch"


def main():
    print(f"Procesando lote: {CSV_PATH}\n")
    resultados = process_csv_file(str(CSV_PATH), str(OUTPUT_DIR))
    resumen = generar_reporte_resumen(resultados)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = OUTPUT_DIR / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)

    print("\n=== Resumen del lote ===")
    print(f"  Total piezas: {resumen['total_piezas']}")
    print(f"  Exitosas: {resumen['exitosas']}  |  Fallidas: {resumen['fallidas']}")
    print(f"  Tiempo total: {resumen['tiempo_total_ms']} ms")
    print(f"  Promedio por imagen: {resumen['promedio_ms_por_imagen']} ms")
    print(f"  Resumen guardado en: {summary_path}")
    print("=========================")


if __name__ == "__main__":
    main()
