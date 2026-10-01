"""
Genera 4 invitaciones de prueba cubriendo los casos de uso principales del
LayoutDecisionEngine, con el layout real (titulo arriba-izquierda, fecha
arriba-derecha, tarjetas de ponentes con color por categoria). Cada caso se
ejecuta de forma aislada: si uno falla, se registra el error y se continua.
"""

import time
from pathlib import Path

import main as pipeline

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

CASOS = {
    1: {  # 0 ponentes - solo texto (dia de campo)
        "marca": "Finca",
        "categoria": "ganadera",
        "palabra_categoria": "Dia de Campo",
        "palabra_titulo": "Ganadero",
        "background_file": "paisaje_colinas_atardecer_finca.jpg",
        "fecha_texto": ["10 de Octubre", "de 2026", "8:00 a.m.", "Finca Buenos Aires"],
        "tema_evento": "Buenas practicas de manejo en epoca de lluvias",
        "ponentes": [],
        "apoyos_texto": "",
    },
    2: {  # 1 ponente con foto
        "marca": "Finca",
        "categoria": "ganadera",
        "palabra_categoria": "Charla",
        "palabra_titulo": "Maestra",
        "background_file": "vaca_potrero_dorado_atardecer.jpeg",
        "fecha_texto": ["15 de Octubre", "de 2026", "4:00 p.m.", "Auditorio Central"],
        "tema_evento": "Manejo Reproductivo Bovino",
        "ponentes": [
            {
                "name": "Dr. Andres Vega",
                "role": "Medico Veterinario Zootecnista",
                "empresa": "Grupo Bios",
                "tema": "Sincronizacion y fertilidad en hatos lecheros",
                "photo": "andres_vega.jpg",
            },
        ],
        "apoyos_texto": "",
    },
    3: {  # 3 ponentes con foto, linea Contegral, categoria porcicola
        "marca": "Contegral",
        "categoria": "porcicola",
        "palabra_categoria": "Charla",
        "palabra_titulo": "Maestra",
        "background_file": "lechones_destetados_pasillo.jpg",
        "fecha_texto": ["22 de Octubre", "de 2026", "3:30 p.m.", "Hotel Sochagota"],
        "tema_evento": "Actualizacion en Nutricion Porcicola",
        "ponentes": [
            {
                "name": "Ing. Paola Rios",
                "role": "Nutricionista Porcicola",
                "empresa": "Contegral",
                "tema": "Formulacion de dietas por fase productiva",
                "photo": "paola_rios.jpg",
            },
            {
                "name": "Dr. Felipe Cano",
                "role": "Medico Veterinario",
                "empresa": "Grupo Bios",
                "tema": "Bioseguridad en granjas porcicolas",
                "photo": "felipe_cano.jpg",
            },
            {
                "name": "Ing. Sara Nino",
                "role": "Ingeniera de Produccion",
                "empresa": "Contegral",
                "tema": "Eficiencia y costo de produccion",
                "photo": "",
            },
        ],
        "apoyo_logo": "",
        "apoyos_texto": "Linea Contegral",
    },
    4: {  # 4 ponentes, linea Finca, fallback de patrocinador por texto
        "marca": "Finca",
        "categoria": "general",
        "palabra_categoria": "Encuentro",
        "palabra_titulo": "Tecnico",
        "background_file": "potrero_extenso_aereo_dron.jpg",
        "fecha_texto": ["30 de Octubre", "de 2026", "9:00 a.m.", "Centro de Eventos Bios"],
        "tema_evento": "Nutricion Animal Integral",
        "ponentes": [
            {"name": "Dr. Juan Perez", "role": "Medico Veterinario", "empresa": "Grupo Bios", "tema": "Nutricion de precision", "photo": ""},
            {"name": "Ing. Maria Gomez", "role": "Zootecnista", "empresa": "Finca", "tema": "Suplementacion estrategica", "photo": ""},
            {"name": "Dr. Carlos Ruiz", "role": "Nutricionista Animal", "empresa": "Grupo Bios", "tema": "Manejo de praderas", "photo": ""},
            {"name": "Ing. Laura Diaz", "role": "Ingeniera Agropecuaria", "empresa": "Finca", "tema": "Costos de produccion", "photo": ""},
        ],
        "apoyo_logo": "",
        "apoyos_texto": "Con el apoyo de Contegral",
    },
    5: {  # co-marca (Contegral+Finca -> fuente Alexandria) + multi-categoria (color general + etiqueta combinada)
        "marca": ["Contegral", "Finca"],
        "categoria": ["ganadera", "porcicola"],
        "palabra_categoria": "Día",
        "palabra_titulo": "Contegral",
        "background_file": "ganado_cebu_pastizal.jpg",
        "fecha_texto": ["Vigente del 01/11/2026", "al 30/11/2026"],
        "tema_evento": "Por la compra de 2 bultos, lleva un suplemento mineral gratis",
        "ponentes": [],
        "apoyos_texto": "",
    },
    6: {  # fila de logos aliados reales (render_sponsor_logos_row) en vez de texto/logo unico
        "marca": "Contegral",
        "categoria": "porcicola",
        "palabra_categoria": "Charla",
        "palabra_titulo": "Maestra",
        "background_file": "lechones_destetados_pasillo.jpg",
        "fecha_texto": ["5 de Noviembre", "de 2026", "2:00 p.m.", "Centro de Convenciones"],
        "tema_evento": "Bioseguridad y Produccion Porcicola",
        "ponentes": [],
        "logos_aliados": [
            str(BASE_DIR / "assets" / "icons" / "Contegral" / "Contegral_Porcicultura.png"),
            str(BASE_DIR / "assets" / "icons" / "Finca" / "Finca_Porcicultura.png"),
        ],
    },
    7: {  # avicola con sub_linea (icono de linea real, Engorde) - no probado antes
        "marca": "Finca",
        "categoria": "avicola",
        "sub_linea": "engorde",
        "palabra_categoria": "Charla",
        "palabra_titulo": "Maestra",
        "background_file": "potrero_extenso_aereo_dron.jpg",
        "fecha_texto": ["12 de Noviembre", "de 2026", "10:00 a.m.", "Granja Avicola El Roble"],
        "tema_evento": "Manejo Sanitario en Pollo de Engorde",
        "ponentes": [
            {"name": "Ing. Diana Lopez", "role": "Zootecnista Avicola", "empresa": "Finca", "tema": "Bioseguridad en galpones", "photo": ""},
        ],
        "apoyos_texto": "",
    },
    8: {  # 2 ponentes - sin config dedicada, ejercita el FALLBACK_CASE (case_d_grid_4)
        "marca": "Contegral",
        "categoria": "ganadera",
        "palabra_categoria": "Día de",
        "palabra_titulo": "Campo",
        "background_file": "vaca_lechera_pastizal_verde.jpg",
        "fecha_texto": ["20 de Noviembre", "de 2026", "8:00 a.m.", "Finca La Esperanza"],
        "tema_evento": "Jornada de Campo - Manejo de Praderas",
        "ponentes": [
            {"name": "Dr. Oscar Martinez", "role": "Medico Veterinario", "empresa": "Contegral", "tema": "Manejo de praderas", "photo": ""},
            {"name": "Ing. Camila Torres", "role": "Zootecnista", "empresa": "Contegral", "tema": "Rotacion de potreros", "photo": ""},
        ],
        "apoyos_texto": "",
    },
}


def main():
    reporte = []  # (numero, tema, status, ms, detalle)

    for numero, payload in CASOS.items():
        output_path = OUTPUT_DIR / f"test_case_{numero}.png"
        print(f"\n--- Caso {numero}: {payload['tema_evento']} ({len(payload['ponentes'])} ponentes) ---")
        inicio = time.perf_counter()
        try:
            resultado = pipeline.generar_invitacion(payload, output_path)
            duracion_ms = (time.perf_counter() - inicio) * 1000
            print(f"[OK] Caso {numero} generado: {resultado} ({duracion_ms:.1f} ms)")
            reporte.append((numero, payload["tema_evento"], "OK", duracion_ms, str(resultado)))
        except Exception as e:
            duracion_ms = (time.perf_counter() - inicio) * 1000
            print(f"[ERROR] Caso {numero} fallo: {type(e).__name__}: {e}")
            reporte.append((numero, payload["tema_evento"], "FAIL", duracion_ms, f"{type(e).__name__}: {e}"))

    exitos = sum(1 for r in reporte if r[2] == "OK")
    tiempo_total = sum(r[3] for r in reporte)

    print("\n=== Reporte final ===")
    for numero, tema, status, duracion_ms, detalle in reporte:
        print(f"  Caso {numero} [{status}] {duracion_ms:7.1f} ms - {tema}")
        if status == "FAIL":
            print(f"           -> {detalle}")
    print(f"----------------------")
    print(f"  Total: {exitos}/{len(CASOS)} OK  |  Tiempo acumulado: {tiempo_total:.1f} ms")
    print("======================")


if __name__ == "__main__":
    main()
