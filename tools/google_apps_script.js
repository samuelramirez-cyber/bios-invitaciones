/**
 * google_apps_script.js
 *
 * Codigo listo para pegar en el editor de Apps Script (Extensiones > Apps
 * Script) del Google Form (o de la Hoja de calculo de respuestas vinculada).
 * Captura cada envio del formulario y lo reenvia como POST JSON al webhook
 * de invitaciones (ver webhook_server.py).
 *
 * CONFIGURACION:
 * 1. Reemplaza WEBHOOK_URL por la URL publica del servidor (con ngrok/Cloud
 *    Run/etc; "http://localhost:5000/..." NO es alcanzable desde Google).
 * 2. En el editor de Apps Script: Activadores (reloj, barra lateral) >
 *    Agregar activador > funcion "onFormSubmit" > Origen del evento
 *    "Desde el formulario" > Tipo de evento "Al enviarse el formulario".
 * 3. Ajusta MAPA_PREGUNTAS con el texto EXACTO de cada pregunta del formulario
 *    (Google entrega las respuestas indexadas por titulo de pregunta).
 */

var WEBHOOK_URL = "http://localhost:5000/api/v1/invitaciones/webhook";

// Texto exacto de cada pregunta del formulario -> campo interno esperado por
// el webhook (marca, tipo_evento, maestria, titulo, fecha, hora, lugar, apoyos_texto).
// El campo "ponentes" se arma aparte (ver PREGUNTAS_PONENTES mas abajo),
// porque suele venir de varias preguntas repetidas (Nombre 1, Cargo 1, ...).
var MAPA_PREGUNTAS = {
  "Marca": "marca",
  "Tipo de evento": "tipo_evento",
  "Maestria (opcional)": "maestria",
  "Titulo / tema de la charla": "titulo",
  "Fecha": "fecha",
  "Hora": "hora",
  "Lugar": "lugar",
  "Texto de apoyos/patrocinadores": "apoyos_texto",
};

// Hasta 4 ponentes, cada uno con 4 preguntas en el formulario (ajustar los
// titulos exactos a como esten redactados en tu Google Form).
var PREGUNTAS_PONENTES = [
  { nombre: "Ponente 1 - Nombre", cargo: "Ponente 1 - Cargo", empresa: "Ponente 1 - Empresa", tema: "Ponente 1 - Tema" },
  { nombre: "Ponente 2 - Nombre", cargo: "Ponente 2 - Cargo", empresa: "Ponente 2 - Empresa", tema: "Ponente 2 - Tema" },
  { nombre: "Ponente 3 - Nombre", cargo: "Ponente 3 - Cargo", empresa: "Ponente 3 - Empresa", tema: "Ponente 3 - Tema" },
  { nombre: "Ponente 4 - Nombre", cargo: "Ponente 4 - Cargo", empresa: "Ponente 4 - Empresa", tema: "Ponente 4 - Tema" },
];

/**
 * Trigger instalable de Google Forms: se ejecuta automaticamente en cada
 * envio del formulario. `e.namedValues` trae { "Titulo de la pregunta": [respuesta] }.
 */
function onFormSubmit(e) {
  try {
    var respuestas = e && e.namedValues ? e.namedValues : {};
    var payload = construirPayload(respuestas);
    enviarWebhook(payload);
  } catch (error) {
    Logger.log("Error procesando el envio del formulario: " + error);
  }
}

function primeraRespuesta(respuestas, tituloPregunta) {
  var valores = respuestas[tituloPregunta];
  if (valores && valores.length > 0) {
    return String(valores[0]).trim();
  }
  return "";
}

function construirPayload(respuestas) {
  var payload = {};

  for (var pregunta in MAPA_PREGUNTAS) {
    if (MAPA_PREGUNTAS.hasOwnProperty(pregunta)) {
      payload[MAPA_PREGUNTAS[pregunta]] = primeraRespuesta(respuestas, pregunta);
    }
  }

  payload.ponentes = [];
  for (var i = 0; i < PREGUNTAS_PONENTES.length; i++) {
    var preguntasPonente = PREGUNTAS_PONENTES[i];
    var nombre = primeraRespuesta(respuestas, preguntasPonente.nombre);
    if (!nombre) {
      continue; // ponente vacio/no usado en este formulario -> se omite
    }
    payload.ponentes.push({
      nombre: nombre,
      cargo: primeraRespuesta(respuestas, preguntasPonente.cargo),
      empresa: primeraRespuesta(respuestas, preguntasPonente.empresa),
      tema: primeraRespuesta(respuestas, preguntasPonente.tema),
    });
  }

  return payload;
}

function enviarWebhook(payload) {
  var opciones = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true, // para poder inspeccionar errores 4xx/5xx en el log, en vez de que Apps Script lance una excepcion
  };

  var respuesta = UrlFetchApp.fetch(WEBHOOK_URL, opciones);
  var codigo = respuesta.getResponseCode();
  var cuerpo = respuesta.getContentText();

  if (codigo === 200 || codigo === 201) {
    Logger.log("Invitacion generada correctamente: " + cuerpo);
  } else {
    Logger.log("El webhook respondio con error (HTTP " + codigo + "): " + cuerpo);
  }
}
