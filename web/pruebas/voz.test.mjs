// La voz no debe quedarse atrás de la pantalla cuando los ejercicios se hacen rápido.
// Uso: node web/pruebas/voz.test.mjs
// Simula un navegador cuya voz tarda 3 s por frase.
import assert from "node:assert/strict";

let reloj = 0;
const timers = [];
globalThis.setTimeout = (fn, ms) => { const t = { fn, en: reloj + ms, vivo: true }; timers.push(t); return t; };
globalThis.clearTimeout = (t) => { if (t) t.vivo = false; };

const dichas = [];
let fila = [];            // lo que el navegador tiene en fila
let hablando = null;
let cancelaciones = 0;
let sinAviso = false;     // simula el navegador que no dispara onend
const DURA = 3000;
function arrancar() {
  if (hablando || !fila.length) return;
  hablando = fila.shift();
  dichas.push({ t: reloj, texto: hablando.text });
  hablando.termina = reloj + DURA;
}
globalThis.window = globalThis;
globalThis.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
globalThis.speechSynthesis = {
  paused: false,
  getVoices: () => [],
  addEventListener() {},
  speak(u) { fila.push(u); arrancar(); },
  cancel() {
    cancelaciones++;
    const h = hablando; const f = fila;
    hablando = null; fila = [];
    if (h) h.onerror?.();
    for (const u of f) u.onerror?.();
  },
  resume() {},
};
globalThis.document = { addEventListener() {} };
globalThis.localStorage = { getItem: () => null, setItem() {} };

const { decir } = await import("../js/avisos.js");

function avanzar(ms) {
  const meta = reloj + ms;
  while (reloj < meta) {
    reloj += 10;
    if (hablando && reloj >= hablando.termina) { const h = hablando; hablando = null; if (!sinAviso) h.onend?.(); arrancar(); }
    for (const t of timers) if (t.vivo && t.en <= reloj) { t.vivo = false; t.fn(); }
  }
}

// Igual que decirMensaje() de app.js.
const esConteo = (x) => /\d+ de \d+/.test(x);
let ultimaInstruccion = null;
const mensaje = (x) => {
  if (esConteo(x)) decir(x.replace(/^\D*?(?=\d+ de \d+)/, ""), { conteo: true });
  else if (x !== ultimaInstruccion) { ultimaInstruccion = x; decir(x); }
};

// Rutina hecha rápido, con el patrón real del programa: al sostener el gesto sale el
// conteo y 0.3 s después, al relajar, la instrucción vuelve a aparecer.
function ejercicio(nombre, instruccion, cada = 1000) {
  mensaje(instruccion);
  for (let i = 1; i <= 5; i++) {
    avanzar(cada - 300);
    mensaje(`${nombre} ${i} de 5 - simetría 90.0%`);
    avanzar(300);
    if (i < 5) mensaje(instruccion);
  }
}
mensaje("Relaje el rostro para comenzar");
avanzar(1500);
ejercicio("Sonrisa", "Sonría y sostenga");
ejercicio("Cejas", "Eleve las cejas y sostenga");
ejercicio("Ojos", "Cierre los ojos y sostenga");
mensaje("¡Rutina completa!");
const tFinal = reloj;
avanzar(10000);

for (const d of dichas) console.log(`${(d.t / 1000).toFixed(1).padStart(5)} s  ${d.texto}`);
const textos = dichas.map((d) => d.texto);

assert.equal(cancelaciones, 0, "nunca debe cortar una frase a la mitad");
for (const [instr, anterior] of [["Eleve las cejas y sostenga", "Sonrisa"], ["Cierre los ojos y sostenga", "Cejas"]]) {
  const i = textos.indexOf(instr);
  assert.ok(i >= 0, `debe decir «${instr}»`);
  assert.equal(textos.filter((x) => x === instr).length, 1, `«${instr}» se dice una sola vez`);
}
assert.equal(textos.at(-1), "¡Rutina completa!", "lo último que dice es el final");
const atraso = dichas.at(-1).t - tFinal;
assert.ok(atraso <= 3000, `«Rutina completa» se atrasó ${atraso / 1000} s`);
assert.ok(textos.some((x) => /^\d+ de 5/.test(x)), "dice los conteos (cortos)");
console.log(`OK: sin cortes, atraso final ${atraso / 1000} s`);

// Android: a veces el navegador no avisa que terminó. La voz no debe quedarse muda.
const antes = dichas.length;
sinAviso = true;
mensaje("Prueba sin aviso 1 de 5");
avanzar(200);
mensaje("Instrucción nueva");
avanzar(8000);
sinAviso = false;
assert.equal(dichas.at(-1)?.texto, "Instrucción nueva", "debe seguir hablando aunque falte el aviso de fin");
assert.ok(dichas.length > antes + 1);
console.log("OK: se recupera si el navegador no avisa que terminó");
