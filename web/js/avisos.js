// Voz, pitido de alarma y pantalla encendida durante la sesión.

let audio = null;
let voz = null;
let candado = null;

// Los navegadores de celular solo permiten audio y voz si empiezan dentro de un toque
// del usuario: se llama al presionar «Comenzar», antes de cualquier await.
export function desbloquear({ hablar = true } = {}) {
  // iPhone (iOS 17+): que la página suene aunque esté activado el interruptor de silencio.
  try { if (navigator.audioSession) navigator.audioSession.type = "playback"; } catch { /* no disponible */ }
  // iPhone anterior: reproducir un <audio> mudo cambia la sesión de audio a «reproducción».
  try {
    const mudo = new Audio(wavMudo());
    mudo.setAttribute("playsinline", "");
    mudo.play().catch(() => {});
  } catch { /* sin audio */ }
  try {
    audio ??= new (window.AudioContext || window.webkitAudioContext)();
    audio.resume();
    // Un sonido real (casi inaudible) termina de activar el audio en Safari.
    const t = audio.currentTime;
    const osc = audio.createOscillator();
    const gan = audio.createGain();
    gan.gain.value = 0.001;
    osc.connect(gan).connect(audio.destination);
    osc.start(t);
    osc.stop(t + 0.05);
  } catch { /* sin audio */ }
  if ("speechSynthesis" in window) {
    elegirVoz();
    speechSynthesis.cancel();
    speechSynthesis.resume();
    // Una frase con volumen real: varios navegadores de teléfono no activan la voz con una muda.
    const u = new SpeechSynthesisUtterance(hablar ? "Iniciando" : " ");
    u.lang = voz?.lang || "es-MX";
    if (voz) u.voice = voz;
    u.volume = hablar ? 1 : 0;
    speechSynthesis.speak(u);
  }
}

function elegirVoz() {
  const voces = speechSynthesis.getVoices();
  voz = voces.find((v) => v.lang === "es-MX") || voces.find((v) => v.lang === "es-US")
    || voces.find((v) => v.lang?.toLowerCase().startsWith("es")) || voz;
}

if ("speechSynthesis" in window) {
  speechSynthesis.addEventListener?.("voiceschanged", elegirVoz);
}

// Medio segundo de silencio en WAV (8 kHz, 8 bits), sin descargar nada.
function wavMudo() {
  const n = 4000;
  const b = new Uint8Array(44 + n);
  const v = new DataView(b.buffer);
  const txt = (o, t) => [...t].forEach((c, i) => { b[o + i] = c.charCodeAt(0); });
  txt(0, "RIFF"); v.setUint32(4, 36 + n, true); txt(8, "WAVEfmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, 8000, true); v.setUint32(28, 8000, true); v.setUint16(32, 1, true); v.setUint16(34, 8, true);
  txt(36, "data"); v.setUint32(40, n, true);
  b.fill(128, 44);
  let bin = "";
  for (const x of b) bin += String.fromCharCode(x);
  return `data:audio/wav;base64,${btoa(bin)}`;
}

// Lee un texto en voz alta. Una alarma interrumpe lo que se esté diciendo; los demás
// mensajes se forman en la cola (cancelar justo antes de hablar hace que Chrome en
// Android a veces no diga nada).
export function decir(texto, { urgente = false } = {}) {
  if (!("speechSynthesis" in window) || !texto) return;
  if (urgente) speechSynthesis.cancel();
  if (speechSynthesis.paused) speechSynthesis.resume();     // Android a veces la deja en pausa
  const u = new SpeechSynthesisUtterance(paraVoz(texto));
  u.lang = voz?.lang || "es-MX";
  if (voz) u.voice = voz;
  u.rate = 1.0;
  u.volume = 1;
  speechSynthesis.speak(u);
}

export function callar() {
  if ("speechSynthesis" in window) speechSynthesis.cancel();
}

// «Sonrisa 3 de 5 - simetría 85.3%» se lee mejor como «Sonrisa 3 de 5. Simetría 85 por ciento».
function paraVoz(texto) {
  return texto
    .replace(/(\d+)\.\d+%/g, "$1%")
    .replace(/ - /g, ". ")
    .replace(/%/g, " por ciento");
}

export function pitido(frecuencia = 880, duracion = 0.35) {
  if (!audio) return;
  const t = audio.currentTime;
  const osc = audio.createOscillator();
  const gan = audio.createGain();
  osc.type = "square";
  osc.frequency.value = frecuencia;
  gan.gain.setValueAtTime(0.0001, t);
  gan.gain.exponentialRampToValueAtTime(0.25, t + 0.02);
  gan.gain.exponentialRampToValueAtTime(0.0001, t + duracion);
  osc.connect(gan).connect(audio.destination);
  osc.start(t);
  osc.stop(t + duracion + 0.05);
}

export async function mantenerPantalla() {
  try {
    candado = await navigator.wakeLock?.request("screen");
  } catch { /* no disponible */ }
}

export function soltarPantalla() {
  candado?.release?.();
  candado = null;
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && candado?.released) mantenerPantalla();
});
