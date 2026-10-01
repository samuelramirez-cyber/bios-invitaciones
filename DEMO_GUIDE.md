# Guía rápida — Demo del martes

## Interfaz visual (Streamlit)

`app.py` ya está construida — `start_demo.bat` la levanta automáticamente en
`http://localhost:8501` junto con el webhook. Tiene dos pestañas:

- **🖼️ Generar Invitación**: formulario (marca, categoría, tipo de evento,
  título, fecha/hora/lugar, ponentes) con vista previa en vivo, métricas de
  tiempo de render, alertas si se activa algún fallback, y descarga del PNG.
- **📦 Carga Masiva**: sube uno o varios `.csv`/`.json` y genera la galería de
  resultados usando el mismo `batch_processor.py` del CLI.

**Categorías multi-línea:** el selector de Categoría acepta elegir varias a
la vez (ej. un evento que cubre Ganadería y Porcicultura) — en ese caso la
insignia "Maestría" lista todas las líneas elegidas y usa un color neutro
(no hay una plantilla real de referencia para una mezcla de colores).

---

## 1. Arranque en un clic

Doble clic en **`start_demo.bat`** (raíz del proyecto). El script:

1. Verifica que Python 3.x esté instalado y en el PATH.
2. Instala/actualiza las dependencias de `requirements.txt`.
3. Lanza `tools/demo_launcher.py`, que a su vez:
   - Verifica que `assets/`, `output/`, `data/` y `config/` existan y sean escribibles.
   - Inicia el **webhook** (Flask, puerto `5000`).
   - Inicia la **interfaz visual** (Streamlit, puerto `8501`) — si `app.py` existe.
   - Intenta abrir un **túnel público con ngrok** para que Google Forms pueda
     alcanzar el webhook desde internet.
   - Imprime en consola todas las URLs activas.

Para detener todo: **Ctrl+C** en esa misma ventana. Apaga el webhook, la
interfaz y el túnel ngrok, y libera los puertos — no hace falta cerrar nada
manualmente.

### Arranque manual (si prefieres no usar el .bat)

```bash
python -m pip install -r requirements.txt
python tools\demo_launcher.py
```

---

## 2. Túnel público (ngrok) y Google Forms

`ngrok` desde 2024 exige una cuenta gratuita y un *authtoken* incluso para
túneles básicos. Si no configuras un token, el lanzador lo avisa claramente y
sigue funcionando solo en `localhost` (perfecto para probar en tu propia
máquina, pero Google Forms no podrá alcanzarlo).

**Para habilitar el túnel público antes del martes:**

1. Crea una cuenta gratis en <https://dashboard.ngrok.com/signup>.
2. Copia tu authtoken desde <https://dashboard.ngrok.com/get-started/your-authtoken>.
3. Configúralo como variable de entorno **antes** de correr `start_demo.bat`
   (nunca lo pegues dentro del código — por eso se lee de una variable de entorno):

   ```powershell
   # PowerShell, en la misma sesion donde vas a correr start_demo.bat
   $env:NGROK_AUTHTOKEN = "tu_token_aqui"
   ```

4. Corre `start_demo.bat`. La consola mostrará algo como:

   ```
   Webhook publico:    https://algo-random.ngrok-free.app/api/v1/invitaciones/webhook
   ```

5. Copia esa URL y pégala en `WEBHOOK_URL` dentro de
   `tools/google_apps_script.js`, luego pega ese código en
   Extensiones > Apps Script del formulario (instrucciones dentro del archivo).

**Nota:** el plan gratuito de ngrok genera una URL nueva cada vez que se
reinicia el túnel — si reinicias la demo, hay que actualizar `WEBHOOK_URL` en
Apps Script otra vez.

---

## 3. Solución de problemas de puertos ocupados

Si ves `[AVISO] El puerto 5000 ya esta en uso`, es casi siempre un proceso
huérfano de una corrida anterior que no se cerró con Ctrl+C (por ejemplo, se
cerró la ventana con la X en vez de Ctrl+C). Para diagnosticar y liberar el
puerto manualmente en PowerShell:

```powershell
# 1. Ver que proceso tiene el puerto 5000 (o 8501 para Streamlit)
Get-NetTCPConnection -LocalPort 5000 | Select-Object OwningProcess

# 2. Confirmar que es realmente el webhook (y no otra cosa) antes de matarlo
Get-Process -Id <PID_del_paso_anterior> | Select-Object Id, ProcessName, Path

# 3. Matar el proceso Y todo su arbol (importante: un simple Stop-Process
#    puede dejar hijos huerfanos sosteniendo el puerto)
taskkill /F /T /PID <PID_del_paso_1>
```

`demo_launcher.py` ya usa `taskkill /F /T` internamente al apagarse con
Ctrl+C, así que en el uso normal esto no debería pasar — esta sección es para
el caso en que algo lo interrumpió de forma anormal (crash, cierre forzado).

---

## 4. Flujo de prueba en vivo (para la reunión)

Con la demo corriendo (`start_demo.bat`), en **otra** terminal:

```bash
python tools\google_forms_emulator.py
```

Esto envía 3 formularios de prueba (charla de 1 ponente, encuentro de 4
ponentes, día de campo sin ponentes) al webhook y muestra en consola la ruta
del PNG generado para cada uno. Los archivos quedan en `output/webhook/`.

Para una prueba end-to-end automatizada (levanta el servidor, envía los 3
formularios, valida los PNGs en disco y apaga todo solo):

```bash
python test_webhook.py
```

### Prueba manual de un solo formulario (curl / PowerShell)

```powershell
$body = @{
    marca = "Finca"
    tipo_evento = "Ganaderia"
    titulo = "Prueba en vivo"
    fecha = "24 de Septiembre de 2026"
    hora = "3:00 p.m."
    lugar = "Auditorio"
    ponentes = @()
    apoyos_texto = ""
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:5000/api/v1/invitaciones/webhook" -Method Post -Body $body -ContentType "application/json"
```

La respuesta trae `output_path` (ruta del PNG generado) y `duracion_ms`
(tiempo de renderizado).

---

## 5. Checklist antes de la reunión

- [ ] `start_demo.bat` corre sin errores y muestra "DEMO LISTA".
- [ ] `python tools\google_forms_emulator.py` genera los 3 PNG en `output/webhook/`.
- [ ] Si se necesita acceso público: `NGROK_AUTHTOKEN` configurado y la URL
      pública copiada a `tools/google_apps_script.js`.
- [ ] La interfaz visual carga en `http://localhost:8501` y genera una invitación de prueba.
