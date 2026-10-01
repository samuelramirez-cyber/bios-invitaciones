"""
google_forms_emulator.py - Emula el envio de respuestas de Google Forms hacia
webhook_server.py, para probar el endpoint sin depender de un formulario real.

Uso standalone: python tools/google_forms_emulator.py
Uso como modulo: from tools.google_forms_emulator import enviar_formularios
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

import requests

DEFAULT_WEBHOOK_URL = "http://localhost:5000/api/v1/invitaciones/webhook"

FORMULARIOS_PRUEBA: List[Dict[str, Any]] = [
    {
        # Caso 1: Charla Maestra de 1 ponente
        "marca": "Finca",
        "tipo_evento": "Ganaderia",
        "maestria": "Ganadera",
        "titulo": "Manejo Reproductivo Bovino",
        "fecha": "15 de Octubre de 2026",
        "hora": "4:00 p.m.",
        "lugar": "Auditorio Central",
        "ponentes": [
            {
                "nombre": "Dr. Andres Vega",
                "cargo": "Medico Veterinario Zootecnista",
                "empresa": "Grupo Bios",
                "tema": "Sincronizacion y fertilidad en hatos lecheros",
            }
        ],
        "apoyos_texto": "",
    },
    {
        # Caso 2: Encuentro de 4 ponentes
        "marca": "Finca",
        "tipo_evento": "Campo",
        "maestria": "",
        "titulo": "Encuentro Tecnico de Nutricion Animal",
        "fecha": "30 de Octubre de 2026",
        "hora": "9:00 a.m.",
        "lugar": "Centro de Eventos Bios",
        "ponentes": [
            {"nombre": "Dr. Juan Perez", "cargo": "Medico Veterinario", "empresa": "Grupo Bios", "tema": "Nutricion de precision"},
            {"nombre": "Ing. Maria Gomez", "cargo": "Zootecnista", "empresa": "Finca", "tema": "Suplementacion estrategica"},
            {"nombre": "Dr. Carlos Ruiz", "cargo": "Nutricionista Animal", "empresa": "Grupo Bios", "tema": "Manejo de praderas"},
            {"nombre": "Ing. Laura Diaz", "cargo": "Ingeniera Agropecuaria", "empresa": "Finca", "tema": "Costos de produccion"},
        ],
        "apoyos_texto": "Con el apoyo de Contegral",
    },
    {
        # Caso 3: Dia de Campo sin ponentes
        "marca": "Finca",
        "tipo_evento": "Ganaderia",
        "maestria": "",
        "titulo": "Dia de Campo Ganadero",
        "fecha": "10 de Octubre de 2026",
        "hora": "8:00 a.m.",
        "lugar": "Finca Buenos Aires",
        "ponentes": [],
        "apoyos_texto": "",
    },
]


def enviar_formularios(webhook_url: str = DEFAULT_WEBHOOK_URL, formularios=None) -> List[Dict[str, Any]]:
    """
    Envia cada formulario de prueba como POST JSON a `webhook_url`. Un fallo
    de red o una respuesta de error en un formulario no detiene el envio de
    los demas. Devuelve la lista de resultados (uno por formulario).
    """
    formularios = formularios if formularios is not None else FORMULARIOS_PRUEBA
    resultados = []

    for i, formulario in enumerate(formularios, start=1):
        etiqueta = f"Formulario {i}: {formulario.get('titulo', '(sin titulo)')}"
        try:
            resp = requests.post(webhook_url, json=formulario, timeout=30)
            cuerpo = resp.json() if resp.content else {}
            ok = resp.status_code in (200, 201)
            print(f"[{'OK' if ok else 'ERROR'}] {etiqueta} -> HTTP {resp.status_code} {cuerpo}")
            resultados.append({"formulario": etiqueta, "http_status": resp.status_code, "ok": ok, "body": cuerpo})
        except requests.RequestException as e:
            print(f"[ERROR] {etiqueta}: fallo de conexion: {e}")
            resultados.append({"formulario": etiqueta, "http_status": None, "ok": False, "body": {"error": str(e)}})

    return resultados


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WEBHOOK_URL
    print(f"Enviando {len(FORMULARIOS_PRUEBA)} formularios de prueba a {url}\n")
    resultados = enviar_formularios(url)
    exitos = sum(1 for r in resultados if r["ok"])
    print(f"\nResumen: {exitos}/{len(resultados)} formularios procesados correctamente.")
