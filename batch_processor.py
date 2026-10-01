"""
batch_processor.py - Procesador en lote de invitaciones.

Lee un directorio de payloads JSON (uno por pieza) o un CSV con multiples
solicitudes, renderiza cada una via main.generar_invitacion() y produce un
reporte de trazabilidad. Cada fila/archivo se procesa de forma aislada: un
fallo individual (JSON malformado, fila con datos invalidos, error de render)
se registra y el resto del lote continua.

Convenciones del CSV (columnas): marca, tipo_evento, maestria, titulo, fecha,
hora, lugar, ponentes, apoyos_texto.
  - tipo_evento: Ganaderia | Porcicultura | Avicola | Cunicultura | Equinos |
    Campo (o alias cortos como Ganadera/Porcicola/General) -> determina el
    color de categoria (ver layout_engine.normalizar_categoria). Un evento
    que cubre varias lineas a la vez se escribe separando con '+', ej.
    "Ganaderia+Porcicultura+Avicola" (ver layout_engine.resolver_categoria).
  - maestria: texto libre para la insignia "Maestria <texto>"; vacio = se
    deriva automaticamente de tipo_evento.
  - ponentes: ponentes separados por ';', campos separados por '|':
    "Nombre|Cargo|Empresa|Tema; Nombre2|Cargo2|Empresa2|Tema2" (vacio = 0 ponentes).
"""

import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import main as pipeline

BASE_DIR = Path(__file__).resolve().parent
CSV_COLUMNS = ("marca", "tipo_evento", "maestria", "titulo", "fecha", "hora", "lugar", "ponentes", "apoyos_texto")


class BatchResult:
    """Registro de trazabilidad de una pieza procesada en el lote."""

    __slots__ = ("origen", "status", "output_path", "duracion_ms", "error")

    def __init__(self, origen: str, status: str, output_path: Optional[str], duracion_ms: float, error: Optional[str] = None):
        self.origen = origen
        self.status = status
        self.output_path = output_path
        self.duracion_ms = duracion_ms
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origen": self.origen,
            "status": self.status,
            "output_path": self.output_path,
            "duracion_ms": round(self.duracion_ms, 1),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Traduccion de fila CSV -> payload interno
# ---------------------------------------------------------------------------

def parsear_ponentes_delimitados(texto: str) -> List[Dict[str, str]]:
    ponentes = []
    for bloque in texto.split(";"):
        bloque = bloque.strip()
        if not bloque:
            continue
        campos = [c.strip() for c in bloque.split("|")]
        campos += [""] * (4 - len(campos))
        nombre, cargo, empresa, tema = campos[:4]
        if nombre:
            ponentes.append({"name": nombre, "role": cargo, "empresa": empresa, "tema": tema, "photo": ""})
    return ponentes


def _parsear_categoria_csv(texto: str):
    """'Ganaderia+Porcicultura' -> ['Ganaderia', 'Porcicultura']; una sola -> string simple."""
    partes = [p.strip() for p in texto.split("+") if p.strip()]
    if len(partes) <= 1:
        return partes[0] if partes else ""
    return partes


def construir_payload_desde_fila_csv(fila: Dict[str, str]) -> Dict[str, Any]:
    """Traduce una fila de CSV (ver columnas en CSV_COLUMNS) al payload interno del CanvasEngine."""

    def limpio(clave: str) -> str:
        return (fila.get(clave) or "").strip()

    payload: Dict[str, Any] = {
        "marca": limpio("marca"),
        "categoria": _parsear_categoria_csv(limpio("tipo_evento")),
        "palabra_categoria": "Charla",
        "palabra_titulo": "Maestra",
        "tema_evento": limpio("titulo"),
        "fecha_texto": [v for v in (limpio("fecha"), limpio("hora"), limpio("lugar")) if v],
        "ponentes": parsear_ponentes_delimitados(limpio("ponentes")),
        "apoyos_texto": limpio("apoyos_texto"),
    }
    if limpio("maestria"):
        payload["maestria_label"] = limpio("maestria")
    return payload


CAMPOS_OBLIGATORIOS = ("marca", "tema_evento")


def validar_payload_minimo(payload: Dict[str, Any]) -> None:
    """
    Valida que el payload interno traiga los campos minimos para renderizar
    (marca, tema_evento). Lanza ValueError con mensaje descriptivo si falta
    alguno - usado tanto por process_csv_file como por webhook_server.py.
    """
    faltantes = [c for c in CAMPOS_OBLIGATORIOS if not payload.get(c)]
    if faltantes:
        raise ValueError(f"faltan campos obligatorios: {faltantes}")


# ---------------------------------------------------------------------------
# Render individual con captura de errores
# ---------------------------------------------------------------------------

def _renderizar_uno(payload: Dict[str, Any], origen: str, output_path: Path) -> BatchResult:
    inicio = time.perf_counter()
    try:
        pipeline.generar_invitacion(payload, output_path)
        duracion_ms = (time.perf_counter() - inicio) * 1000
        print(f"[OK] {origen} -> {output_path.name} ({duracion_ms:.1f} ms)")
        return BatchResult(origen, "OK", str(output_path), duracion_ms)
    except Exception as e:
        duracion_ms = (time.perf_counter() - inicio) * 1000
        print(f"[ERROR] {origen}: {type(e).__name__}: {e}")
        return BatchResult(origen, "FAIL", None, duracion_ms, f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Procesadores de lote
# ---------------------------------------------------------------------------

def process_json_folder(input_dir: str, output_dir: str) -> List[BatchResult]:
    """
    Procesa cada archivo .json de `input_dir` (un payload completo por
    archivo) y guarda el PNG resultante en `output_dir` con el mismo nombre
    base. Un JSON malformado o un fallo de render no detiene el resto del lote.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    resultados: List[BatchResult] = []
    if not input_path.is_dir():
        print(f"[ERROR] Carpeta de entrada no encontrada: {input_path}")
        return resultados

    archivos = sorted(input_path.glob("*.json"))
    if not archivos:
        print(f"[AVISO] No se encontraron archivos .json en {input_path}")
        return resultados

    for archivo in archivos:
        origen = archivo.name
        try:
            with archivo.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[ERROR] {origen}: JSON malformado: {e}")
            resultados.append(BatchResult(origen, "FAIL", None, 0.0, f"JSONDecodeError: {e}"))
            continue

        destino = output_path / f"{archivo.stem}.png"
        resultados.append(_renderizar_uno(payload, origen, destino))

    return resultados


def process_csv_file(csv_path: str, output_dir: str) -> List[BatchResult]:
    """
    Procesa cada fila de `csv_path` (columnas: ver CSV_COLUMNS), la traduce a
    un payload interno y renderiza. Una fila con datos invalidos/incompletos
    no detiene el resto del lote.
    """
    csv_file = Path(csv_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    resultados: List[BatchResult] = []
    if not csv_file.is_file():
        print(f"[ERROR] Archivo CSV no encontrado: {csv_file}")
        return resultados

    with csv_file.open("r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        for numero, fila in enumerate(lector, start=1):
            origen = f"fila {numero}"
            try:
                payload = construir_payload_desde_fila_csv(fila)
                validar_payload_minimo(payload)
            except Exception as e:
                print(f"[ERROR] {origen}: fila invalida: {e}")
                resultados.append(BatchResult(origen, "FAIL", None, 0.0, str(e)))
                continue

            destino = output_path / f"batch_{numero:03d}.png"
            resultados.append(_renderizar_uno(payload, origen, destino))

    return resultados


# ---------------------------------------------------------------------------
# Reporte de trazabilidad
# ---------------------------------------------------------------------------

def generar_reporte_resumen(resultados: List[BatchResult]) -> Dict[str, Any]:
    """Agrega los resultados de un lote: total, exitos/fallos, tiempos y detalle por pieza."""
    total = len(resultados)
    exitos = sum(1 for r in resultados if r.status == "OK")
    tiempo_total_ms = sum(r.duracion_ms for r in resultados)
    promedio_ms = (tiempo_total_ms / total) if total else 0.0

    return {
        "total_piezas": total,
        "exitosas": exitos,
        "fallidas": total - exitos,
        "tiempo_total_ms": round(tiempo_total_ms, 1),
        "promedio_ms_por_imagen": round(promedio_ms, 1),
        "resultados": [r.to_dict() for r in resultados],
    }
