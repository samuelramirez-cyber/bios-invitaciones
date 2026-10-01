"""
test_webhook.py - Runner de integracion para webhook_server.py.

Levanta el servidor Flask en un subproceso, envia los 3 formularios de
prueba via tools/google_forms_emulator.py, valida que los 3 PNGs se hayan
generado realmente en output/webhook/ y detiene el servidor de forma
ordenada (incluso si algo falla en el camino).
"""

import subprocess
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "tools"))
from google_forms_emulator import DEFAULT_WEBHOOK_URL, enviar_formularios  # noqa: E402

OUTPUT_DIR = BASE_DIR / "output" / "webhook"
HEALTH_URL = "http://localhost:5000/api/v1/invitaciones/health"
TIMEOUT_ARRANQUE_S = 15


def _esperar_servidor(timeout_s: float = TIMEOUT_ARRANQUE_S) -> bool:
    """Sondea /health hasta que el servidor responda o se agote el timeout."""
    inicio = time.time()
    while time.time() - inicio < timeout_s:
        try:
            resp = requests.get(HEALTH_URL, timeout=1)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.3)
    return False


def main() -> int:
    print("Iniciando webhook_server.py en un subproceso...")
    proceso = subprocess.Popen(
        [sys.executable, str(BASE_DIR / "webhook_server.py")],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        if not _esperar_servidor():
            salida = proceso.stdout.read() if proceso.stdout else ""
            print(f"[ERROR] El servidor no respondio a tiempo en {HEALTH_URL}.\n{salida}")
            return 1

        print("Servidor listo. Enviando los 3 formularios de prueba...\n")
        resultados = enviar_formularios(DEFAULT_WEBHOOK_URL)

        print("\nValidando que los PNGs se hayan generado en output/webhook/...")
        exitos = 0
        for r in resultados:
            ruta = (r.get("body") or {}).get("output_path")
            if r["ok"] and ruta and Path(ruta).is_file():
                print(f"  [OK] {r['formulario']} -> {ruta}")
                exitos += 1
            else:
                print(f"  [FAIL] {r['formulario']} -> {r.get('body')}")

        total = len(resultados)
        print(f"\nResumen: {exitos}/{total} invitaciones generadas y verificadas en disco.")
        return 0 if exitos == total else 1

    finally:
        print("\nDeteniendo el servidor de pruebas...")
        proceso.terminate()
        try:
            proceso.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proceso.kill()
            proceso.wait()
        print("Servidor detenido.")


if __name__ == "__main__":
    sys.exit(main())
