// Voz, pitido de alarma y pantalla encendida durante la sesión.

let audio = null;
let voz = null;
let candado = null;

// Los navegadores de celular solo permiten audio y voz después de un toque del usuario:
// se llama al presionar «Comenzar».
export function desbloquear() {
  try {
    audio ??= new (window.AudioContext || window.webkitAudioContext)();
    audio.resume();
  } catch { /* sin audio */ }
  if ("speechSynthesis" in window) {
    const voces = speechSynthesis.getVoices();
    voz = voces.find((v) => v.lang === "es-MX") || voces.find((v) => v.lang?.startsWith("es")) || null;
    const vacio = new SpeechSynthesisUtterance(" ");
    vacio.volume = 0;
    speechSynthesis.speak(vacio);
  }
}

if ("speechSynthesis" in window) {
  speechSynthesis.addEventListener?.("voiceschanged", () => {
    const voces = speechSynthesis.getVoices();
    voz = voces.find((v) => v.lang === "es-MX") || voces.find((v) => v.lang?.startsWith("es")) || voz;
  });
}

// Lee un texto en voz alta. Si se acumulan mensajes, se descartan los viejos.
export function decir(texto, { urgente = false } = {}) {
  if (!("speechSynthesis" in window) || !texto) return;
  if (urgente || speechSynthesis.pending) speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(paraVoz(texto));
  u.lang = voz?.lang || "es-MX";
  if (voz) u.voice = voz;
  u.rate = 1.0;
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
