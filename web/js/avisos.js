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

// Cada navegador trae voces distintas. Las «naturales» (Microsoft Edge, Google, Siri,
// voces mejoradas de Apple) suenan mucho mejor que las básicas (eSpeak en Linux,
// las «compactas» de Apple), así que se califican y se elige la mejor en español.
let vozPreferida = "";   // nombre elegido por el usuario; vacío = automática
try { vozPreferida = localStorage.getItem("emolang.vozNombre") || ""; } catch { /* sin almacenamiento */ }

const BUENAS = /natural|neural|online|premium|enhanced|mejorada|siri|google|paulina|m[oó]nica|dalia|jorge|elvira|sabina|helena|lupe|marisol/i;
const MALAS = /espeak|compact|eloquence|novelty|whisper|grandma|grandpa|bad news|bubbles|jester|organ|zarvox|trinoids|bells|boing/i;

function calificar(v) {
  const lang = (v.lang || "").toLowerCase().replace("_", "-");
  let p = lang === "es-mx" ? 3 : lang === "es-us" || lang === "es-419" ? 2 : 1;
  if (BUENAS.test(v.name)) p += 5;
  if (MALAS.test(v.name)) p -= 10;
  return p;
}

export function vocesEnEspanol() {
  if (!("speechSynthesis" in window)) return [];
  return speechSynthesis.getVoices()
    .filter((v) => (v.lang || "").toLowerCase().startsWith("es"))
    .sort((a, b) => calificar(b) - calificar(a) || a.name.localeCompare(b.name));
}

function elegirVoz() {
  const voces = vocesEnEspanol();
  voz = voces.find((v) => v.name === vozPreferida) || voces[0] || voz;
}

export function usarVoz(nombre) {
  vozPreferida = nombre || "";
  try { localStorage.setItem("emolang.vozNombre", vozPreferida); } catch { /* sin almacenamiento */ }
  elegirVoz();
}

export function vozActual() {
  return voz?.name || "";
}

if ("speechSynthesis" in window) {
  speechSynthesis.addEventListener?.("voiceschanged", elegirVoz);
  elegirVoz();
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

// Lee un texto en voz alta sin quedarse atrás de la pantalla.
//
// El navegador forma en fila todo lo que se le pide decir y lo lee completo; si la
// persona hace los ejercicios más rápido de lo que tarda la voz, la fila crece y la
// voz va narrando cosas que ya pasaron. Por eso aquí nunca hay más de dos mensajes
// esperando: la instrucción más reciente y el conteo más reciente. Lo que se está
// diciendo NUNCA se corta (salvo una alarma): cortar a media frase suena trabado y,
// además, hablar justo después de cancel() deja muda la voz en Chrome para Android.
//
//   { conteo: true }   «3 de 5…»: reemplaza al conteo que esperaba
//   (instrucción)      «Eleve las cejas»: va antes que cualquier conteo pendiente
//   { urgente: true }  alarma: corta lo que se esté diciendo
let actual = null;        // frase que se está diciendo
let instruccionPendiente = null;
let conteoPendiente = null;
let ocupado = false;
let vigilante = null;

export function decir(texto, { urgente = false, conteo = false } = {}) {
  if (!("speechSynthesis" in window) || !texto) return;
  if (urgente) {
    instruccionPendiente = conteoPendiente = null;
    actual = null;          // los avisos de fin de la frase cortada se ignoran
    ocupado = true;
    speechSynthesis.cancel();
    setTimeout(() => emitir(texto), 250);   // pausa para que Android no se quede mudo
    return;
  }
  if (conteo) conteoPendiente = texto;
  else {
    instruccionPendiente = texto;
    conteoPendiente = null;  // el conteo del ejercicio anterior ya no importa
  }
  if (!ocupado) siguiente();
}

function siguiente() {
  const texto = instruccionPendiente ?? conteoPendiente;
  if (instruccionPendiente !== null) instruccionPendiente = null;
  else conteoPendiente = null;
  if (texto) emitir(texto);
}

function emitir(texto) {
  if (speechSynthesis.paused) speechSynthesis.resume();     // Android a veces la deja en pausa
  const u = new SpeechSynthesisUtterance(paraVoz(texto));
  u.lang = voz?.lang || "es-MX";
  if (voz) u.voice = voz;
  u.rate = 1;
  u.pitch = 1;
  u.volume = 1;
  const fin = () => {
    if (u !== actual) return;
    clearTimeout(vigilante);
    actual = null;
    ocupado = false;
    siguiente();
  };
  u.onend = fin;
  u.onerror = fin;
  actual = u;
  ocupado = true;
  // Algunos navegadores a veces no avisan que terminaron: sin esto la voz se quedaría
  // callada para siempre. Si se dispara antes de tiempo, la siguiente frase solo espera
  // en la fila del navegador (no corta nada).
  clearTimeout(vigilante);
  vigilante = setTimeout(fin, 2000 + u.text.length * 100);
  speechSynthesis.speak(u);
}

// true mientras la voz dice algo o tiene algo por decir. La terapia la usa para no
// avanzar el ejercicio mientras se da una indicación o el resultado de una repetición.
export function estaHablando() {
  return ocupado || instruccionPendiente !== null || conteoPendiente !== null;
}

export function callar() {
  instruccionPendiente = conteoPendiente = null;
  actual = null;
  ocupado = false;
  clearTimeout(vigilante);
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
