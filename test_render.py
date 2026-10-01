"""Script de prueba: layout de 4 ponentes usando InvitationCanvasBuilder."""

from pathlib import Path

from canvas_engine import InvitationCanvasBuilder

BASE_DIR = Path(__file__).resolve().parent
FONT_BOLD = str(BASE_DIR / "assets" / "fonts" / "Arial-Bold.ttf")
FONT_REGULAR = str(BASE_DIR / "assets" / "fonts" / "Arial-Regular.ttf")


def main():
    builder = InvitationCanvasBuilder()

    builder.load_background(str(BASE_DIR / "assets" / "backgrounds" / "finca_fondo.png"))
    builder.apply_dark_overlay(0.4)

    y = builder.draw_wrapped_text(
        text="Jornada Tecnica de Nutricion Animal",
        font_path=FONT_BOLD,
        max_width=900,
        start_y=builder.SAFE_TOP,
        font_size=72,
    )

    y = builder.draw_wrapped_text(
        text="Miercoles 24 de Septiembre 2026 - 3:00 PM",
        font_path=FONT_REGULAR,
        max_width=900,
        start_y=y + 30,
        font_size=36,
        color=(255, 200, 60),
    )

    speakers = [
        {"name": "Dr. Juan Perez", "role": "Medico Veterinario", "photo_path": None},
        {"name": "Ing. Maria Gomez", "role": "Zootecnista", "photo_path": None},
        {"name": "Dr. Carlos Ruiz", "role": "Nutricionista Animal", "photo_path": None},
        {"name": "Ing. Laura Diaz", "role": "Ingeniera Agropecuaria", "photo_path": None},
    ]
    y = builder.render_speakers_grid(speakers, start_y=y + 60)

    builder.render_sponsor_fallback("Con el apoyo de Contegral", y_position=y + 40)

    output_path = BASE_DIR / "output" / "invitacion_test.png"
    builder.save(str(output_path))
    print(f"Invitacion de prueba generada: {output_path}")


if __name__ == "__main__":
    main()
