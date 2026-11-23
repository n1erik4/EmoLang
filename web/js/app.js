// Interfaz de EmoLang: inicio, sesión con cámara y resultados.
import { iniciarGaleria } from "./carrusel.js";
import { abrirCamara, cadaCuadro, cargarDetector, cerrarCamara, ErrorCamara } from "./camara.js";
import {
  callar, decir, desbloquear, estaHablando, mantenerPantalla, pitido, soltarPantalla, usarVoz, vocesEnEspanol, vozActual,
} from "./avisos.js";
import { crearSesion, cargarMotor, leerPrograma } from "./motor.js";
import * as cuenta from "./cuenta.js";
import { BOCA_H, BOCA_V, Calibrador, metricasDe, NEUTRAS, OJO_DER, OJO_IZQ } from "./rostro.js";

const $ = (sel) => document.querySelector(sel);
const pct = new Intl.NumberFormat("es-MX", { style: "percent", maximumFractionDigits: 0 });
const fechaLarga = new Intl.DateTimeFormat("es-MX", { dateStyle: "long", timeStyle: "short" });
const fechaCorta = new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeStyle: "short" });
const SIMETRIA_MINIMA = 0.8;

// ====================================================================== módulos
const MODULOS = {
  terapia: {
    programa: "terapia_facial.emo",
    titulo: "Terapia facial",
    inicio: "Relaje el rostro para comenzar",
    ejercicios: [
      { clave: "sonrisa", nombre: "Sonreír" },
      { clave: "cejas", nombre: "Levantar las cejas" },
      { clave: "ojos", nombre: "Cerrar los ojos" },
    ],
    medidores: (cfg) => [
      // cada barra: el movimiento respecto del máximo de la persona (emolang/perfil.py)
      { nombre: "Sonrisa", valor: (m, e) => e?.sonrisa_rel ?? 0, umbral: cfg.umbral_sonrisa ?? 0.6, gesto: "sonreir",
        texto: (m, e) => pct.format(e?.sonrisa_rel ?? 0) },
      { nombre: "Cejas levantadas", valor: (m, e) => e?.cejas_rel ?? 0, umbral: cfg.umbral_cejas ?? 0.6, gesto: "elevar_cejas",
        texto: (m, e) => pct.format(e?.cejas_rel ?? 0) },
      { nombre: "Ojos cerrados", valor: (m, e) => e?.ojos_rel ?? 0, umbral: cfg.umbral_ojos ?? 0.7, gesto: "cerrar_ojos",
        texto: (m, e) => pct.format(e?.ojos_rel ?? 0) },
    ],
  },
  conduccion: {
    programa: "conduccion.emo",
    titulo: "Conducción",
    inicio: "Todo bien. Mantenga la vista al frente.",
    estados: {
      normal: { texto: "Atento", instruccion: "Todo bien. Mantenga la vista al frente.", tono: "" },
      somnoliento: { texto: "Somnoliento", instruccion: "Hay señales de cansancio. Considere detenerse a descansar.", tono: "ambar" },
      distraido: { texto: "Distraído", instruccion: "Mire al frente.", tono: "ambar" },
      alerta: { texto: "¡Alerta!", instruccion: "¡Despierte! Riesgo de microsueño.", tono: "rojo" },
    },
    contadores: [
      ["parpadeo", "Parpadeos"], ["bostezo", "Bostezos"], ["microsueno", "Microsueños"],
      ["cabeceo", "Cabeceos"], ["distraccion", "Distracciones"], ["fatiga", "Patrón de fatiga"],
    ],
    medidores: (cfg) => [
      { nombre: "Apertura de los ojos", valor: (m) => m.ear / 0.4, umbral: (cfg.umbral_ojo ?? 0.2) / 0.4, texto: (m) => m.ear.toFixed(2),
        bajo: true, nota: "Ojos cerrados: antes de la marca." },
      { nombre: "Apertura de la boca", valor: (m) => m.mar, umbral: cfg.umbral_bostezo ?? 0.33, texto: (m) => pct.format(m.mar), alto: true },
      { nombre: "PERCLOS (último minuto)", valor: (m, e) => e.perclos, umbral: cfg.umbral_perclos ?? 0.15, texto: (m, e) => pct.format(e.perclos), alto: true },
    ],
  },
};

const NOMBRES_GESTO = {
  parpadeo: "Parpadeos", bostezo: "Bostezos", microsueno: "Microsueños", cabeceo: "Cabeceos",
  distraccion: "Distracciones", atento: "Vuelta a la atención", fatiga: "Patrón de fatiga (bostezo + cabeceo)",
};
const TIPOS = {
  gesto: "Gesto", secuencia: "Secuencia", transicion: "Cambio de estado", repeticion: "Repetición",
  registro: "Nota", alarma: "Alarma", alarma_detenida: "Alarma detenida",
};

// ====================================================================== pantallas
let pantallaActual = "inicio";

let usuario = null;

function mostrarPantalla(id, { historia = true } = {}) {
  if (!usuario && id !== "acceso") id = "acceso";
  for (const p of document.querySelectorAll(".pantalla")) p.hidden = p.id !== id;
  pantallaActual = id;
  if (historia && id !== "inicio" && id !== "acceso") history.pushState({ pantalla: id }, "", `#${id}`);
  if (id === "inicio" || id === "acceso") {
    if (location.hash) history.replaceState(null, "", location.pathname);
  }
  if (id === "inicio") pintarInicio();
  window.scrollTo({ top: 0 });
}

window.addEventListener("popstate", () => {
  if (sesion) terminarSesion({ mostrar: false });
  mostrarPantalla("inicio", { historia: false });
});

document.addEventListener("click", (ev) => {
  const ir = ev.target.closest("[data-ir]");
  if (ir) {
    ev.preventDefault();
    if (sesion && !confirm("¿Terminar la sesión actual?")) return;
    if (sesion) terminarSesion({ mostrar: false });
    mostrarPantalla(ir.dataset.ir);
  }
  const iniciar = ev.target.closest("[data-iniciar]");
  if (iniciar) iniciarSesion(iniciar.dataset.iniciar);
  const ver = ev.target.closest("[data-ver-programa]");
  if (ver) verPrograma(ver.dataset.verPrograma);
  const cerrar = ev.target.closest("[data-cerrar]");
  if (cerrar) cerrar.closest("dialog").close();
});

function error(texto, titulo = "No se pudo iniciar") {
  $("#error-titulo").textContent = titulo;
  $("#error-texto").textContent = texto;
  $("#dialogo-error").showModal();
}

// ====================================================================== carga
// La carga se marca en <html data-motor data-detector> (la usan las pruebas de navegador).
function marcarCarga(nombre, promesa) {
  const raiz = document.documentElement;
  raiz.dataset[nombre] = "cargando";
  promesa.then(() => { raiz.dataset[nombre] = "listo"; }, () => { raiz.dataset[nombre] = "error"; });
}

function precargar() {
  precargarUnaVez();
}

// ====================================================================== voz
const voz = {
  get activa() { return $("#opcion-voz").checked; },
  set activa(v) {
    $("#opcion-voz").checked = v;
    $("#boton-voz").setAttribute("aria-pressed", String(v));
    try { localStorage.setItem("emolang.voz", v ? "1" : "0"); } catch { /* sin almacenamiento */ }
    if (!v) callar();
  },
};
try { if (localStorage.getItem("emolang.voz") === "0") voz.activa = false; } catch { /* sin almacenamiento */ }
$("#opcion-voz").addEventListener("change", (e) => { voz.activa = e.target.checked; });
$("#boton-voz").addEventListener("click", () => { voz.activa = !voz.activa; });

// Selector de voz: la lista llega tarde en Chrome (evento voiceschanged).
function llenarVoces() {
  const voces = vocesEnEspanol();
  const caja = $("#selector-voz");
  caja.hidden = voces.length < 2;
  const sel = $("#opcion-voz-nombre");
  const actual = vozActual();
  sel.replaceChildren(...voces.map((v, i) => {
    const op = document.createElement("option");
    op.value = v.name;
    op.textContent = `${v.name} (${v.lang})${i === 0 ? " · recomendada" : ""}`;
    op.selected = v.name === actual;
    return op;
  }));
}
if ("speechSynthesis" in window) {
  llenarVoces();
  speechSynthesis.addEventListener?.("voiceschanged", llenarVoces);
}
$("#opcion-voz-nombre").addEventListener("change", (e) => { usarVoz(e.target.value); probarVoz(); });
$("#probar-voz").addEventListener("click", probarVoz);
function probarVoz() {
  desbloquear({ hablar: false });
  decir("Hola. Repetición 3 de 8. Simetría 85 por ciento.", { urgente: true });
}

const esConteo = (texto) => /\d+ de \d+/.test(texto);

// Qué se dice en voz alta de cada mensaje del programa:
// - una instrucción solo cuando cambia: «Sonría y sostenga» vuelve a aparecer en
//   pantalla después de cada repetición, pero decirla cada vez solo atrasa la voz;
// - un conteo, corto: «Sonrisa 3 de 5 - simetría 85.3%» → «3 de 5. Simetría 85 por ciento»
//   (el nombre del ejercicio ya está en pantalla).
function decirMensaje(ses, texto) {
  if (esConteo(texto)) {
    hablar(texto.replace(/^\D*?(?=\d+ de \d+)/, ""), { conteo: true });
  } else if (texto !== ses.ultimaInstruccion) {
    ses.ultimaInstruccion = texto;
    hablar(texto);
  }
}

function hablar(texto, opciones) {
  if (voz.activa) decir(texto, opciones);
}

// ====================================================================== sesión
let sesion = null;
const video = $("#video");
const lienzo = $("#lienzo");
const ctx = lienzo.getContext("2d");

async function iniciarSesion(clave) {
  if (sesion || !usuario) return;
  if (clave !== cuenta.MODULO_DE_ROL[usuario.rol]) return;    // cada rol usa solo su módulo
  const mod = MODULOS[clave];
  desbloquear({ hablar: voz.activa });
  for (const b of document.querySelectorAll("[data-iniciar]")) b.disabled = true;

  prepararPanel(clave, mod);
  mostrarPantalla("sesion");
  capa("Abriendo la cámara…");
  instruccion("Preparando…");

  let flujo = null;
  try {
    const camara = abrirCamara(video).then((f) => { flujo = f; capa("Cargando el compilador y el detector facial…"); return f; });
    const perfil = clave === "terapia" ? await cuenta.perfil().catch(() => null) : null;
    const [s, detector] = await Promise.all([crearSesion(mod.programa, perfil), cargarDetector(), camara]);
    lienzo.width = video.videoWidth;
    lienzo.height = video.videoHeight;
    sesion = {
      clave, mod, s, detector, flujo,
      cfg: s.info.configuracion,
      calibrador: new Calibrador(2.0),
      previas: { ...NEUTRAS },
      t0: null, pausa: 0, ocultoEn: null, recalibrandoDesde: null,
      ultimoTs: -1, ultimaDeteccion: -1e9, sinRostroDesde: null,
      ultimoPitido: 0, estado: null, contadores: {}, notas: 0, terminadoEn: null,
      inicio: new Date(),
    };
    sesion.medidores = mod.medidores(sesion.cfg);
    pintarMedidores();
    capa("Mire al frente y no se mueva", 0);
    hablar("Mire al frente y no se mueva. Vamos a calibrar.");
    mantenerPantalla();
    sesion.detener = cadaCuadro(video, alCuadro);
  } catch (e) {
    console.error(e);
    cerrarCamara(flujo, video);
    sesion = null;
    mostrarPantalla("inicio", { historia: false });
    error(e instanceof ErrorCamara ? e.message
      : `No se pudo cargar EmoLang. Revise su conexión a internet y vuelva a intentar. (${e.message || e})`);
  } finally {
    for (const b of document.querySelectorAll("[data-iniciar]")) b.disabled = false;
  }
}

function alCuadro(ahora) {
  const ses = sesion;
  if (!ses || video.readyState < 2) return;
  if (ahora - ses.ultimaDeteccion < 28) return;          // hasta ~35 cuadros por segundo
  ses.ultimaDeteccion = ahora;
  const ts = Math.max(Math.round(ahora), ses.ultimoTs + 1); // MediaPipe exige marcas crecientes
  ses.ultimoTs = ts;
  let res;
  try {
    res = ses.detector.detectForVideo(video, ts);
  } catch (e) {
    console.error(e);
    return;
  }
  dibujar(res);

  // Terapia: el ejercicio espera a que la voz termine (la indicación de calibrar, la
  // instrucción de cada ejercicio y el resultado de cada repetición). El tiempo en
  // espera no cuenta, igual que con la pestaña oculta. Conducción nunca se pausa.
  if (esperaVoz(ses, ahora)) return;

  if (!ses.calibrador.listo) {
    const c = ses.calibrador.agregar(res, ahora);
    if (c.listo) {
      if (ses.t0 === null) {
        ses.t0 = ahora;
        instruccion(ses.mod.inicio);
      } else {
        ses.pausa += ahora - ses.recalibrandoDesde;
      }
      capa(null);
    } else if (c.sinRostro) {
      capa("No se ve el rostro. Colóquese frente a la cámara.", 0);
    } else {
      capa("Mire al frente y no se mueva", 1 - c.faltan_s / ses.calibrador.segundos);
    }
    return;
  }

  const m = metricasDe(res, video.videoWidth, video.videoHeight, ses.previas, ses.calibrador.base);
  ses.previas = m;
  if (!m.rostro) {
    ses.sinRostroDesde ??= ahora;
    if (ahora - ses.sinRostroDesde > 800) capa("No se ve el rostro", null, true);
  } else if (ses.sinRostroDesde !== null) {
    ses.sinRostroDesde = null;
    capa(null);
  }

  const t = ahora - ses.t0 - ses.pausa;
  let e;
  try {
    e = ses.s.paso(t, m);
  } catch (err) {
    console.error(err);
    terminarSesion();
    error(`Error en tiempo de ejecución: ${err.message || err}`, "La sesión se detuvo");
    return;
  }
  ses.estado = e;
  actualizar(e, m, t, ahora);
}

document.addEventListener("visibilitychange", () => {
  const ses = sesion;
  if (!ses || ses.t0 === null) return;
  const ahora = performance.now();
  if (document.visibilityState === "hidden") ses.ocultoEn = ahora;
  else if (ses.ocultoEn !== null) {
    ses.pausa += ahora - ses.ocultoEn;          // el tiempo con la pestaña oculta no cuenta
    ses.ocultoEn = null;
  }
});

$("#boton-recalibrar").addEventListener("click", () => {
  if (!sesion || !sesion.calibrador.listo) return;
  sesion.calibrador.reiniciar();
  sesion.recalibrandoDesde = performance.now();
  capa("Mire al frente y no se mueva", 0);
});

$("#boton-terminar").addEventListener("click", () => terminarSesion());

function terminarSesion({ mostrar = true } = {}) {
  const ses = sesion;
  if (!ses) return;
  sesion = null;
  ses.detener?.();
  cerrarCamara(ses.flujo, video);
  soltarPantalla();
  callar();
  $("#alarma").hidden = true;
  let r, perfil = null;
  try {
    if (ses.clave === "terapia") perfil = ses.s.perfil();
    r = ses.s.terminar();
  } catch (e) {
    console.error(e);
    mostrarPantalla("inicio", { historia: false });
    return;
  }
  const registro = { id: Date.now(), fecha: ses.inicio.toISOString(), modulo: ses.clave, simetria_minima: ses.cfg.simetria_minima ?? SIMETRIA_MINIMA, r };
  if (ses.t0 !== null && r.duracion_s >= 3) {
    guardarEnHistorial(registro);
    // el esfuerzo máximo de hoy, para medir la próxima sesión contra él
    if (perfil && usuario) cuenta.guardarPerfil(perfil).catch((e) => console.error(e));
  } else registro.noGuardada = true;
  if (mostrar) {
    pintarResultados(registro);
    history.replaceState({ pantalla: "resultados" }, "", "#resultados");
    mostrarPantalla("resultados", { historia: false });
  }
}

// ---------------------------------------------------------------------- panel
function prepararPanel(clave, mod) {
  $("#panel-terapia").hidden = clave !== "terapia";
  $("#panel-conduccion").hidden = clave !== "conduccion";
  $("#notas").replaceChildren();
  $("#bloque-notas").hidden = true;
  $("#reloj").textContent = "0:00";
  $("#alarma").hidden = true;
  if (clave === "terapia") {
    $("#ejercicios").replaceChildren(...mod.ejercicios.map((ej) => {
      const li = document.createElement("li");
      li.className = "ejercicio";
      li.dataset.clave = ej.clave;
      li.innerHTML = `<span class="ejercicio__nombre"></span><span class="ejercicio__sim"></span><span class="puntos"></span>`;
      li.querySelector(".ejercicio__nombre").textContent = ej.nombre;
      return li;
    }));
  } else {
    $("#contadores").replaceChildren(...mod.contadores.map(([k, nombre]) => {
      const d = document.createElement("div");
      d.innerHTML = `<dt></dt><dd data-contador="${k}">0</dd>`;
      d.querySelector("dt").textContent = nombre;
      return d;
    }));
    pintarEstadoConductor("normal");
  }
}

function pintarMedidores() {
  $("#medidores").replaceChildren(...sesion.medidores.map((md, i) => {
    const d = document.createElement("div");
    d.className = "medidor";
    d.dataset.i = i;
    d.innerHTML = `<span class="medidor__nombre"></span><span class="medidor__valor">–</span>
      <span class="medidor__pista"><span class="medidor__barra"></span><span class="medidor__umbral"></span></span>
      ${md.nota ? '<span class="medidor__nota"></span>' : ""}`;
    d.querySelector(".medidor__nombre").textContent = md.nombre;
    d.querySelector(".medidor__umbral").style.left = `calc(${Math.min(1, md.umbral) * 100}% - 1px)`;
    if (md.nota) d.querySelector(".medidor__nota").textContent = md.nota;
    return d;
  }));
}

function instruccion(texto, tono = "") {
  const el = $("#instruccion");
  if (el.textContent !== texto) el.textContent = texto;
  el.dataset.tono = tono;
}

function esperaVoz(ses, ahora) {
  const esperar = ses.clave === "terapia" && voz.activa && estaHablando();
  if (esperar) {
    if (ses.esperandoVozDesde == null) {
      ses.esperandoVozDesde = ahora;
      if (!ses.calibrador.listo) capa("Escuche la indicación…", 0);
    }
    return true;
  }
  if (ses.esperandoVozDesde != null) {
    if (ses.t0 !== null && ses.calibrador.listo) ses.pausa += ahora - ses.esperandoVozDesde;
    ses.esperandoVozDesde = null;
    if (!ses.calibrador.listo) capa("Mire al frente y no se mueva", 0);
  }
  return false;
}

function capa(texto, avance = null, sinAnillo = false) {
  const el = $("#capa");
  if (texto === null) { el.hidden = true; return; }
  el.hidden = false;
  $("#capa-texto").textContent = texto;
  const anillo = $("#anillo");
  anillo.hidden = sinAnillo || avance === null;
  if (avance !== null) anillo.style.setProperty("--avance", Math.max(0, Math.min(1, avance)).toFixed(3));
}

function nota(t, texto) {
  const li = document.createElement("li");
  li.innerHTML = "<time></time><span></span>";
  li.querySelector("time").textContent = reloj(t);
  li.querySelector("span").textContent = texto;
  $("#notas").prepend(li);
  $("#bloque-notas").hidden = false;
}

function reloj(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function actualizar(e, m, t, ahora) {
  const ses = sesion;
  $("#reloj").textContent = reloj(t);

  for (const texto of e.mensajes) {
    const final = /rutina completa/i.test(texto);
    instruccion(texto, final ? "exito" : "");
  }
  for (const texto of e.mensajes) decirMensaje(ses, texto);
  for (const texto of e.registros) nota(t, texto);

  // alarma
  const alarma = $("#alarma");
  if (e.alarma) {
    alarma.hidden = false;
    $("#alarma-texto").textContent = e.alarma_mensaje;
    if (e.nuevas_alarmas > 0) hablar(e.alarma_mensaje, { urgente: true });
    if (ahora - ses.ultimoPitido > 1200) {
      pitido();
      ses.ultimoPitido = ahora;
    }
  } else if (!alarma.hidden) {
    alarma.hidden = true;
  }

  // medidores
  const activos = new Set(e.gestos_activos);
  for (const el of document.querySelectorAll(".medidor")) {
    const md = ses.medidores[el.dataset.i];
    const v = Math.max(0, Math.min(1, md.valor(m, e)));
    el.querySelector(".medidor__barra").style.width = `${(v * 100).toFixed(1)}%`;
    el.querySelector(".medidor__valor").textContent = md.texto(m, e);
    el.dataset.activo = md.gesto && activos.has(md.gesto) ? "si" : "no";
    el.dataset.alto = (md.alto && v > md.umbral) || (md.bajo && v < md.umbral) ? "si" : "no";
  }

  if (ses.clave === "terapia") actualizarTerapia(e, ahora);
  else actualizarConduccion(e);
}

function actualizarTerapia(e, ahora) {
  const ses = sesion;
  const estado = e.estados.rutina || "";
  const actual = estado.split("_")[0];
  const meta = ses.cfg.meta ?? 5;
  const minima = ses.cfg.simetria_minima ?? SIMETRIA_MINIMA;
  for (const li of document.querySelectorAll(".ejercicio")) {
    const sims = e.ejercicios[li.dataset.clave] || [];
    li.dataset.actual = li.dataset.clave === actual ? "si" : "no";
    li.dataset.hecho = sims.length >= meta ? "si" : "no";
    const puntos = li.querySelector(".puntos");
    if (puntos.children.length !== meta) {
      puntos.replaceChildren(...Array.from({ length: meta }, () => Object.assign(document.createElement("span"), { className: "punto" })));
    }
    [...puntos.children].forEach((p, i) => {
      p.dataset.lleno = i < sims.length ? "si" : "no";
      p.dataset.asimetrico = i < sims.length && sims[i] < minima ? "si" : "no";
    });
    li.querySelector(".ejercicio__sim").textContent = sims.length
      ? `${sims.length} de ${meta} · simetría ${pct.format(sims[sims.length - 1])}` : `0 de ${meta}`;
  }
  if (estado === "terminado") {
    ses.terminadoEn ??= ahora;
    if (ahora - ses.terminadoEn > 3500) terminarSesion();   // sin tocar la pantalla
  }
}

function actualizarConduccion(e) {
  const ses = sesion;
  for (const ev of e.eventos) ses.contadores[ev] = (ses.contadores[ev] || 0) + 1;
  for (const dd of document.querySelectorAll("[data-contador]")) dd.textContent = ses.contadores[dd.dataset.contador] || 0;
  const estado = e.estados.monitor || "normal";
  if (estado !== ses.estadoConductor) {
    ses.estadoConductor = estado;
    pintarEstadoConductor(estado);
    if (estado === "somnoliento") hablar(ses.mod.estados.somnoliento.instruccion);
  }
}

function pintarEstadoConductor(estado) {
  const info = MODULOS.conduccion.estados[estado] || { texto: estado, instruccion: "", tono: "" };
  $("#estado-conductor").dataset.estado = estado;
  $("#estado-conductor-texto").textContent = info.texto;
  if (sesion?.t0 !== null && sesion?.t0 !== undefined) instruccion(info.instruccion, info.tono);
}

// ---------------------------------------------------------------------- dibujo
const PUNTOS = [...OJO_DER, ...OJO_IZQ, ...BOCA_H, ...BOCA_V.flat()];

function dibujar(res) {
  ctx.clearRect(0, 0, lienzo.width, lienzo.height);
  const lm = res.faceLandmarks?.[0];
  if (!lm) return;
  ctx.fillStyle = "rgba(94, 234, 212, 0.95)";
  const r = Math.max(2, lienzo.width / 220);
  for (const i of PUNTOS) {
    const q = lm[i];
    ctx.beginPath();
    ctx.arc(q.x * lienzo.width, q.y * lienzo.height, r, 0, Math.PI * 2);
    ctx.fill();
  }
}

// ====================================================================== resultados
let ultimoRegistro = null;

function pintarResultados(reg) {
  ultimoRegistro = reg;
  const { r } = reg;
  const mod = MODULOS[reg.modulo];
  $("#res-fecha").textContent = fechaLarga.format(new Date(reg.fecha));
  $("#res-titulo").textContent = `${mod.titulo}: resultados`;
  const tarjetas = [["Duración", reloj(r.duracion_s * 1000)]];
  const detalle = $("#res-detalle");
  detalle.replaceChildren();

  if (reg.modulo === "terapia") {
    const todas = Object.values(r.ejercicios).flat();
    const asim = todas.filter((s) => s < reg.simetria_minima).length;
    tarjetas.push(["Repeticiones", String(todas.length)]);
    tarjetas.push(["Simetría promedio", todas.length ? pct.format(todas.reduce((a, b) => a + b, 0) / todas.length) : "–"]);
    tarjetas.push([`Repeticiones con simetría < ${pct.format(reg.simetria_minima)}`, String(asim)]);
    const cont = document.createElement("div");
    cont.className = "resumen-ejercicios";
    for (const ej of mod.ejercicios) {
      const sims = r.ejercicios[ej.clave] || [];
      const tarjeta = document.createElement("section");
      tarjeta.className = "resumen-ej";
      const prom = sims.length ? sims.reduce((a, b) => a + b, 0) / sims.length : null;
      tarjeta.innerHTML = `<h3></h3><div class="barras" role="img"></div><p class="leyenda"></p><dl>
        <dt>Repeticiones</dt><dd>${sims.length}</dd>
        <dt>Simetría promedio</dt><dd>${prom === null ? "–" : pct.format(prom)}</dd>
        <dt>Simetría mínima</dt><dd>${sims.length ? pct.format(Math.min(...sims)) : "–"}</dd></dl>`;
      tarjeta.querySelector("h3").textContent = ej.nombre;
      const barras = tarjeta.querySelector(".barras");
      barras.setAttribute("aria-label", sims.length
        ? `Simetría de cada repetición: ${sims.map((s) => pct.format(s)).join(", ")}` : "Sin repeticiones");
      const linea = document.createElement("span");
      linea.className = "barras__linea";
      linea.style.bottom = `${reg.simetria_minima * 100}%`;
      barras.append(linea, ...sims.map((s) => {
        const b = document.createElement("span");
        b.className = "barras__b";
        b.style.height = `${Math.max(3, s * 100)}%`;
        b.dataset.asimetrico = s < reg.simetria_minima ? "si" : "no";
        b.title = pct.format(s);
        return b;
      }));
      tarjeta.querySelector(".leyenda").textContent = sims.length
        ? `Cada barra es una repetición; la línea marca ${pct.format(reg.simetria_minima)}.` : "No se completaron repeticiones.";
      cont.append(tarjeta);
    }
    detalle.append(cont);
  } else {
    const res = r.resumen;
    const gestos = res.gestos_detectados || {};
    tarjetas.push(["Alarmas", String(res.alarmas_emitidas ?? 0)]);
    tarjetas.push(["Tiempo en alarma", `${(res.tiempo_en_alarma_s ?? 0).toFixed(1)} s`]);
    tarjetas.push(["Microsueños", String(gestos.microsueno ?? 0)]);
    const tabla = document.createElement("table");
    tabla.className = "tabla-simple";
    tabla.innerHTML = `<thead><tr><th scope="col">Señal detectada</th><th scope="col">Veces</th></tr></thead><tbody></tbody>`;
    const filas = Object.entries(gestos).sort((a, b) => b[1] - a[1]);
    tabla.tBodies[0].append(...(filas.length ? filas : [["–", 0]]).map(([g, n]) => {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td></td><td></td>";
      tr.cells[0].textContent = NOMBRES_GESTO[g] || g;
      tr.cells[1].textContent = n;
      return tr;
    }));
    detalle.append(tabla);
  }

  $("#res-tarjetas").replaceChildren(...tarjetas.map(([nombre, dato]) => {
    const d = document.createElement("div");
    d.className = "tarjeta";
    d.innerHTML = '<div class="tarjeta__dato"></div><div class="tarjeta__nombre"></div>';
    d.querySelector(".tarjeta__dato").textContent = dato;
    d.querySelector(".tarjeta__nombre").textContent = nombre;
    return d;
  }));

  $("#res-n-eventos").textContent = r.bitacora.length;
  $("#res-bitacora").replaceChildren(...r.bitacora.map(([t, tipo, det]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td></td><td></td><td></td>";
    tr.cells[0].textContent = `${reloj(t * 1000)}.${String(Math.floor((t % 1) * 10))}`;
    tr.cells[1].textContent = TIPOS[tipo] || tipo;
    tr.cells[2].textContent = det;
    return tr;
  }));
}

$("#boton-csv").addEventListener("click", () => {
  if (!ultimoRegistro) return;
  const q = (v) => `"${String(v).replaceAll('"', '""')}"`;
  const filas = [["t_s", "tipo", "detalle"], ...ultimoRegistro.r.bitacora].map((f) => f.map(q).join(","));
  const blob = new Blob(["﻿" + filas.join("\r\n") + "\r\n"], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  const fecha = ultimoRegistro.fecha.slice(0, 16).replace(/[T:]/g, "-");
  a.download = `emolang-${ultimoRegistro.modulo}-${fecha}.csv`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});

$("#boton-otra").addEventListener("click", () => {
  const clave = usuario ? cuenta.MODULO_DE_ROL[usuario.rol] : ultimoRegistro?.modulo;
  mostrarPantalla("inicio", { historia: false });
  iniciarSesion(clave);
});

// ====================================================================== cuenta e historial
let historial = [];

async function guardarEnHistorial(reg) {
  historial = [reg, ...historial];
  try {
    const { id } = await cuenta.guardarSesion(reg);
    reg.id = id;
  } catch (e) {
    console.error(e);
    reg.noGuardada = true;
    error(e.estado === 401
      ? "Tu sesión de la cuenta expiró, así que este resultado no se guardó. Descarga la bitácora en CSV antes de salir y vuelve a iniciar sesión."
      : `La sesión no se pudo guardar en tu cuenta: ${e.message} Puedes descargar la bitácora en CSV.`, "Sin guardar");
  }
}

async function cargarHistorial() {
  try {
    historial = await cuenta.sesiones();
  } catch (e) {
    console.error(e);
    historial = [];
  }
  if (pantallaActual === "inicio") pintarInicio();
}

const TEXTOS_ROL = {
  terapia: {
    titulo: "Tu rutina de terapia facial",
    texto: "Haz la rutina con la cámara de tu celular, tablet o computadora. Aquí ves tu avance sesión por sesión.",
    historial: "Tus sesiones de terapia",
  },
  conductor: {
    titulo: "Tu monitoreo de conducción",
    texto: "Coloca el dispositivo frente a ti antes de manejar. EmoLang te avisa si detecta señales de cansancio.",
    historial: "Tus viajes monitoreados",
  },
};

function pintarInicio() {
  if (!usuario) return;
  const modulo = cuenta.MODULO_DE_ROL[usuario.rol];
  const textos = TEXTOS_ROL[usuario.rol];
  $("#saludo").textContent = `Hola, ${usuario.nombre.split(" ")[0]}`;
  $("#inicio-titulo").textContent = textos.titulo;
  $("#inicio-texto").textContent = textos.texto;
  $("#historial-titulo").textContent = textos.historial;
  for (const art of document.querySelectorAll(".modulo")) art.hidden = art.dataset.modulo !== modulo;
  $(".modulos").classList.add("modulos--uno");
  pintarEstadisticas(modulo);
  pintarHistorial();
}

function pintarEstadisticas(modulo) {
  const propias = historial.filter((h) => h.modulo === modulo);
  const cont = $("#estadisticas");
  cont.hidden = propias.length === 0;
  if (!propias.length) return;
  const datos = [["Sesiones", String(propias.length)]];
  if (modulo === "terapia") {
    const promedio = (v) => v.reduce((a, b) => a + b, 0) / v.length;
    const sims = propias.map((h) => Object.values(h.r.ejercicios || {}).flat()).filter((v) => v.length);
    datos.push(["Repeticiones en total", String(sims.reduce((a, v) => a + v.length, 0))]);
    if (sims.length) {
      datos.push(["Simetría de la última sesión", pct.format(promedio(sims[0]))]);
      datos.push(["Simetría promedio histórica", pct.format(promedio(sims.flat()))]);
    }
  } else {
    const alarmas = propias.reduce((a, h) => a + (h.r.resumen?.alarmas_emitidas ?? 0), 0);
    const micro = propias.reduce((a, h) => a + (h.r.resumen?.gestos_detectados?.microsueno ?? 0), 0);
    const minutos = propias.reduce((a, h) => a + (h.r.duracion_s ?? 0), 0) / 60;
    datos.push(["Tiempo monitoreado", `${minutos.toFixed(0)} min`]);
    datos.push(["Alarmas en total", String(alarmas)]);
    datos.push(["Microsueños", String(micro)]);
  }
  cont.replaceChildren(...datos.map(([nombre, dato]) => {
    const d = document.createElement("div");
    d.className = "tarjeta";
    d.innerHTML = '<div class="tarjeta__dato"></div><div class="tarjeta__nombre"></div>';
    d.querySelector(".tarjeta__dato").textContent = dato;
    d.querySelector(".tarjeta__nombre").textContent = nombre;
    return d;
  }));
}

function pintarHistorial() {
  const modulo = usuario ? cuenta.MODULO_DE_ROL[usuario.rol] : null;
  const h = historial.filter((reg) => reg.modulo === modulo);
  $("#borrar-historial").hidden = h.length === 0;
  $("#historial-lista").replaceChildren(...h.map((reg) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    let valor;
    if (reg.modulo === "terapia") {
      const sims = Object.values(reg.r.ejercicios || {}).flat();
      valor = `${sims.length} rep.${sims.length ? ` · ${pct.format(sims.reduce((a, x) => a + x, 0) / sims.length)}` : ""}`;
    } else {
      const n = reg.r.resumen?.alarmas_emitidas ?? 0;
      valor = `${n} alarma${n === 1 ? "" : "s"}`;
    }
    b.innerHTML = '<span><strong></strong><small></small></span><span class="valor"></span>';
    b.querySelector("strong").textContent = MODULOS[reg.modulo]?.titulo || reg.modulo;
    b.querySelector("small").textContent = `${fechaCorta.format(new Date(reg.fecha))} · ${reloj(reg.r.duracion_s * 1000)}`;
    b.querySelector(".valor").textContent = valor;
    b.addEventListener("click", () => {
      pintarResultados(reg);
      mostrarPantalla("resultados");
    });
    li.append(b);
    return li;
  }));
}

$("#borrar-historial").addEventListener("click", async () => {
  if (!confirm("¿Borrar todas tus sesiones guardadas? No se puede deshacer.")) return;
  try {
    await cuenta.borrarSesiones();
    historial = [];
    pintarInicio();
  } catch (e) {
    if (e.estado !== 401) error(e.message, "No se pudo borrar");   // 401: ya avisa el acceso
  }
});

$("#borrar-cuenta").addEventListener("click", async () => {
  if (!confirm("¿Borrar tu cuenta y todos tus datos? No se puede deshacer.")) return;
  try {
    await cuenta.borrarCuenta();
    alSalir();
  } catch (e) {
    if (e.estado !== 401) error(e.message, "No se pudo borrar");   // 401: ya avisa el acceso
  }
});

// ---------------------------------------------------------------------- acceso
function alEntrar(u) {
  usuario = u;
  $("#cuenta").hidden = false;
  $("#cuenta-nombre").textContent = u.nombre;
  historial = [];
  mostrarPantalla("inicio", { historia: false });
  cargarHistorial();
  precargar();
}

// Cualquier llamada a la API que responda 401 (sesión vencida o cerrada en otro
// dispositivo) regresa al acceso con un aviso. Si hay un resultado en pantalla,
// se deja ahí para que se pueda descargar; el aviso de «Sin guardar» lo explica.
window.addEventListener("sesion-expirada", () => {
  if (!usuario || pantallaActual === "resultados") return;
  alSalir();
  cambiarPestana("entrar");
  errorFormulario($("#form-entrar"), "Tu sesión expiró o se cerró. Vuelve a iniciar sesión.");
});

function alSalir() {
  if (sesion) terminarSesion({ mostrar: false });
  usuario = null;
  historial = [];
  $("#cuenta").hidden = true;
  for (const f of document.querySelectorAll(".formulario")) f.reset();
  mostrarPantalla("acceso", { historia: false });
}

$("#boton-salir").addEventListener("click", async () => {
  if (sesion && !confirm("¿Terminar la sesión actual y salir?")) return;
  try { await cuenta.salir(); } catch { /* la cookie expira sola */ }
  alSalir();
});

function cambiarPestana(cual) {
  const entrar = cual === "entrar";
  $("#tab-entrar").setAttribute("aria-selected", String(entrar));
  $("#tab-registro").setAttribute("aria-selected", String(!entrar));
  $("#form-entrar").hidden = !entrar;
  $("#form-registro").hidden = entrar;
  (entrar ? $("#form-entrar") : $("#form-registro")).querySelector("input").focus();
}
$("#tab-entrar").addEventListener("click", () => cambiarPestana("entrar"));
$("#tab-registro").addEventListener("click", () => cambiarPestana("registro"));

function errorFormulario(form, texto) {
  const p = form.querySelector(".formulario__error");
  p.textContent = texto || "";
  p.hidden = !texto;
}

async function enviar(form, accion) {
  const boton = form.querySelector('[type="submit"]');
  errorFormulario(form, "");
  boton.disabled = true;
  try {
    alEntrar(await accion());
  } catch (e) {
    errorFormulario(form, e.message);
  } finally {
    boton.disabled = false;
  }
}

$("#form-entrar").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const f = ev.target;
  if (!f.correo.value || !f.contrasena.value) return errorFormulario(f, "Escriba su correo y su contraseña.");
  enviar(f, () => cuenta.entrar(f.correo.value, f.contrasena.value));
});

$("#form-registro").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const f = ev.target;
  if (!f.rol.value) return errorFormulario(f, "Elija si es usuario de terapia facial o conductor.");
  if (!f.nombre.value.trim()) return errorFormulario(f, "Escriba su nombre.");
  if (f.contrasena.value.length < 8) return errorFormulario(f, "La contraseña debe tener al menos 8 caracteres.");
  if (!f.consentimiento.checked) return errorFormulario(f, "Para crear la cuenta debe aceptar el aviso de privacidad.");
  enviar(f, () => cuenta.registrar({
    rol: f.rol.value, nombre: f.nombre.value.trim(), correo: f.correo.value.trim(),
    contrasena: f.contrasena.value, consentimiento: true,
  }));
});

// ====================================================================== programa
const PALABRAS = new Set(("dominio sensor usar var const gesto secuencia maquina inicial estado al_entrar cuando " +
  "ir_a tras mientras ignorar si sino durante hasta tolerando en repetir veces para retornar funcion estructura " +
  "y o no verdadero falso int decimal bool string duracion proporcion").split(" "));

function resaltar(fuente) {
  const esc = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  return fuente.split("\n").map((linea) => {
    const i = linea.indexOf("//");
    const codigo = i >= 0 ? linea.slice(0, i) : linea;
    const comentario = i >= 0 ? `<span class="c">${esc(linea.slice(i))}</span>` : "";
    const partes = codigo.split(/("[^"]*")/g).map((p, j) => {
      if (j % 2) return `<span class="s">${esc(p)}</span>`;
      return esc(p).replace(/[A-Za-z_áéíóúñ]+/g, (w) => (PALABRAS.has(w) ? `<span class="k">${w}</span>` : w));
    });
    return partes.join("") + comentario;
  }).join("\n");
}

async function verPrograma(clave) {
  const mod = MODULOS[clave];
  $("#dialogo-titulo").textContent = `${mod.titulo} · ${mod.programa}`;
  $("#dialogo-codigo").textContent = "Cargando…";
  $("#dialogo-programa").showModal();
  try {
    $("#dialogo-codigo").innerHTML = resaltar(await leerPrograma(mod.programa));
  } catch (e) {
    $("#dialogo-codigo").textContent = `No se pudo cargar el programa (${e.message}).`;
  }
}

// ====================================================================== arranque
iniciarGaleria(document.getElementById("galeria"));
if (location.hash) history.replaceState(null, "", location.pathname);
let precargado = false;
function precargarUnaVez() {
  if (precargado) return;
  precargado = true;
  // Se precarga en segundo plano mientras la persona lee la página.
  (window.requestIdleCallback || ((f) => setTimeout(f, 300)))(() => {
    marcarCarga("motor", cargarMotor());
    marcarCarga("detector", cargarDetector());
  });
}

(async () => {
  let u = null;
  try {
    u = await cuenta.yo();
  } catch (e) {
    console.error(e);
  }
  if (u) alEntrar(u);
  else mostrarPantalla("acceso", { historia: false });
})();
