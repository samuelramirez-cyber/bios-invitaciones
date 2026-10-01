"""
demo_launcher.py - Orquestador de la demo.

Verifica el entorno, lanza el webhook (Flask, puerto 5000) y la interfaz
visual (Streamlit, puerto 8501) en subprocesos gestionados, intenta exponer
el webhook publicamente via ngrok, y apaga todo de forma limpia ante Ctrl+C
sin dejar puertos bloqueados en Windows.

El webhook y la interfaz son independientes entre si: si uno falta o falla
al iniciar, el otro sigue funcionando (se avisa en consola, no se aborta
toda la demo).
"""

import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent  # invitaciones/
REQUIRED_DIRS = ["assets", "output", "data", "config"]
WEBHOOK_SCRIPT = BASE_DIR / "webhook_server.py"
APP_SCRIPT = BASE_DIR / "app.py"
WEBHOOK_PORT = 5000
STREAMLIT_PORT = 8501

# (nombre_legible, subprocess.Popen) - se apagan en orden inverso al iniciar
procesos: List[Tuple[str, subprocess.Popen]] = []


# ---------------------------------------------------------------------------
# Verificacion de entorno
# ---------------------------------------------------------------------------

def verificar_entorno() -> bool:
    """Asegura que assets/, output/, data/ y config/ existan y sean escribibles."""
    print("Verificando estructura de carpetas...")
    ok = True
    for nombre in REQUIRED_DIRS:
        carpeta = BASE_DIR / nombre
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            prueba = carpeta / ".demo_launcher_write_test"
            prueba.write_text("ok", encoding="utf-8")
            prueba.unlink()
            print(f"  [OK] {nombre}/ existe y es escribible.")
        except OSError as e:
            print(f"  [ERROR] {nombre}/ no se pudo crear o escribir: {e}")
            ok = False
    return ok


# ---------------------------------------------------------------------------
# Lanzamiento de subprocesos
# ---------------------------------------------------------------------------

def _puerto_ocupado(port: int, host: str = "127.0.0.1") -> bool:
    """
    True si algo ya esta escuchando en `port` (ej. un proceso huerfano de una
    corrida anterior que no se cerro limpiamente). Se usa solo para avisar
    antes de lanzar - no bloquea el intento, por si es un falso positivo.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _lanzar_proceso(nombre: str, comando: List[str]) -> subprocess.Popen:
    print(f"Iniciando {nombre}...")
    proceso = subprocess.Popen(
        comando, cwd=str(BASE_DIR),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    procesos.append((nombre, proceso))
    return proceso


def lanzar_webhook() -> Optional[subprocess.Popen]:
    if not WEBHOOK_SCRIPT.is_file():
        print(f"[ERROR] No se encontro {WEBHOOK_SCRIPT.name}; no se puede iniciar el webhook.")
        return None
    if _puerto_ocupado(WEBHOOK_PORT):
        print(f"[AVISO] El puerto {WEBHOOK_PORT} ya esta en uso (posible proceso de una corrida anterior).")
        print("        Ver DEMO_GUIDE.md - 'Puertos ocupados' para liberarlo. Se intenta iniciar de todas formas...")
    return _lanzar_proceso(f"webhook (Flask, puerto {WEBHOOK_PORT})", [sys.executable, str(WEBHOOK_SCRIPT)])


def lanzar_streamlit() -> Optional[subprocess.Popen]:
    if not APP_SCRIPT.is_file():
        print(f"[AVISO] No se encontro app.py en la raiz del proyecto; se omite la interfaz visual.")
        print("        El webhook sigue disponible normalmente sin ella.")
        return None
    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("[AVISO] El paquete 'streamlit' no esta instalado; se omite la interfaz visual.")
        print("        Instalalo con: pip install streamlit")
        return None
    if _puerto_ocupado(STREAMLIT_PORT):
        print(f"[AVISO] El puerto {STREAMLIT_PORT} ya esta en uso (posible proceso de una corrida anterior).")
        print("        Ver DEMO_GUIDE.md - 'Puertos ocupados' para liberarlo. Se intenta iniciar de todas formas...")
    return _lanzar_proceso(
        f"interfaz (Streamlit, puerto {STREAMLIT_PORT})",
        [sys.executable, "-m", "streamlit", "run", str(APP_SCRIPT),
         "--server.port", str(STREAMLIT_PORT), "--server.headless", "true"],
    )


# ---------------------------------------------------------------------------
# Tunel publico (ngrok)
# ---------------------------------------------------------------------------

def exponer_webhook_ngrok() -> Optional[str]:
    """
    Intenta exponer WEBHOOK_PORT con pyngrok. El authtoken (si ngrok lo exige
    para tu cuenta) se lee UNICAMENTE de la variable de entorno
    NGROK_AUTHTOKEN - nunca se hardcodea aqui. Sin pyngrok instalado, sin
    token cuando se requiere, o sin conexion a internet, se degrada de forma
    transparente devolviendo None (la demo sigue funcionando en localhost).
    """
    try:
        from pyngrok import ngrok
    except ImportError:
        print("[AVISO] 'pyngrok' no esta instalado; se omite el tunel publico.")
        print("        Instalalo con: pip install pyngrok")
        return None

    import os
    token = os.environ.get("NGROK_AUTHTOKEN")
    if token:
        ngrok.set_auth_token(token)

    try:
        tunel = ngrok.connect(WEBHOOK_PORT, "http")
        return tunel.public_url
    except Exception as e:
        print(f"[AVISO] No se pudo abrir el tunel ngrok: {e}")
        print("        Verifica tu conexion a internet, o define NGROK_AUTHTOKEN si tu cuenta lo exige.")
        return None


# ---------------------------------------------------------------------------
# Apagado limpio
# ---------------------------------------------------------------------------

def _matar_arbol_de_proceso(pid: int) -> None:
    """
    Termina `pid` y TODOS sus procesos hijos. Necesario en Windows: un
    servidor puede quedar huerfano sosteniendo el puerto si solo se mata el
    proceso directamente rastreado (ej. si algo mato al lanzador sin pasar
    por apagar_todo() - cierre de consola, crash, Task Manager). taskkill /T
    mata el arbol completo sin importar como se genero.
    """
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, check=False,
        )
    else:
        import signal as _signal
        try:
            os_pgid_kill = __import__("os").kill
            os_pgid_kill(pid, _signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def apagar_todo() -> None:
    if not procesos:
        return
    print("\nDeteniendo servicios de la demo...")
    for nombre, proceso in reversed(procesos):
        if proceso.poll() is not None:
            continue  # ya se habia detenido por su cuenta
        print(f"  Deteniendo {nombre} (PID {proceso.pid}, arbol completo)...")
        proceso.terminate()
        try:
            proceso.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"  {nombre} no respondio a terminate(); forzando kill()...")
            proceso.kill()
            proceso.wait()
        finally:
            # Por si el proceso (ej. el reloader de Flask) genero hijos propios
            # que terminate()/kill() no alcanzan a limpiar en Windows.
            _matar_arbol_de_proceso(proceso.pid)

    try:
        from pyngrok import ngrok
        ngrok.kill()  # cierra el proceso ngrok local y libera el tunel, si estaba activo
    except Exception:
        pass

    procesos.clear()
    print("Todos los procesos detenidos. Puertos liberados.")


# ---------------------------------------------------------------------------
# Orquestacion principal
# ---------------------------------------------------------------------------

def main() -> int:
    print("=== Lanzador de demo - Generador de Invitaciones ===\n")

    if not verificar_entorno():
        print("\n[ERROR] El entorno tiene problemas de permisos; corrige eso antes de continuar.")
        return 1

    try:
        lanzar_webhook()
        time.sleep(1.5)  # margen para que Flask termine de bindear el puerto
        lanzar_streamlit()

        print("\nExponiendo el webhook publicamente (ngrok)...")
        url_publica = exponer_webhook_ngrok()

        print("\n" + "=" * 60)
        print("DEMO LISTA")
        print("=" * 60)
        print(f"  Webhook local:      http://localhost:{WEBHOOK_PORT}/api/v1/invitaciones/webhook")
        if APP_SCRIPT.is_file():
            print(f"  Interfaz visual:    http://localhost:{STREAMLIT_PORT}")
        if url_publica:
            print(f"  Webhook publico:    {url_publica}/api/v1/invitaciones/webhook")
            print("\n  Para conectar Google Forms:")
            print("    1. Abre tools/google_apps_script.js")
            print(f"    2. Reemplaza WEBHOOK_URL por: {url_publica}/api/v1/invitaciones/webhook")
            print("    3. Pega el codigo en Extensiones > Apps Script del formulario")
            print("    4. Configura el activador onFormSubmit (instrucciones en ese archivo)")
        else:
            print("\n  Sin tunel publico activo: Google Forms no podra alcanzar este servidor")
            print("  directamente. Revisa los avisos de arriba, o usa el webhook solo en local.")
        print("=" * 60)
        print("\nPresiona Ctrl+C para detener todos los servicios.\n")

        while True:
            time.sleep(1)
            for nombre, proceso in list(procesos):
                if proceso.poll() is not None:
                    print(f"[AVISO] {nombre} se detuvo inesperadamente (codigo {proceso.returncode}).")
                    procesos.remove((nombre, proceso))

    except KeyboardInterrupt:
        print("\n\nCtrl+C recibido.")
        return 0
    finally:
        apagar_todo()


if __name__ == "__main__":
    sys.exit(main())
