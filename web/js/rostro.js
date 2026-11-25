// Métricas faciales a partir del resultado de MediaPipe Face Landmarker.
// Es la misma cuenta que emolang/camara.py (metricas_de): las pruebas comparan ambas.
// No depende del navegador, así que se puede probar con Node.

export const OJO_DER = [33, 160, 158, 133, 153, 144];   // ojo derecho de la persona
export const OJO_IZQ = [362, 385, 387, 263, 373, 380];  // ojo izquierdo de la persona
export const BOCA_V = [[81, 178], [13, 14], [311, 402]];
export const BOCA_H = [78, 308];

export const NEUTRAS = Object.freeze({
  ear: 0.30, ear_izq: 0.30, ear_der: 0.30, mar: 0.05,
  sonrisa: 0.05, sonrisa_izq: 0.05, sonrisa_der: 0.05, cejas: 0.2,
  cejas_izq: 0.2, cejas_der: 0.2, simetria_sonrisa: 1.0, simetria_cejas: 1.0, simetria_ojos: 1.0, cierre_ojos: 0.0,
  simetria: 0.97, perclos: 0.0, pitch: 0.0, yaw: 0.0, roll: 0.0, rostro: true,
});

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const limitar = (v, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
const grados = (r) => (r * 180) / Math.PI;

function ear(p, idx) {
  const [p1, p2, p3, p4, p5, p6] = idx.map((i) => p[i]);
  return (dist(p2, p6) + dist(p3, p5)) / (2.0 * dist(p1, p4) + 1e-9);
}

function mar(p) {
  const vertical = BOCA_V.reduce((s, [a, b]) => s + dist(p[a], p[b]), 0) / BOCA_V.length;
  return vertical / (dist(p[BOCA_H[0]], p[BOCA_H[1]]) + 1e-9);
}

// La matriz llega como lista plana en orden por columnas: m[fila][col] = data[col * 4 + fila].
export function euler(matriz) {
  const d = matriz.data;
  const m = (f, c) => d[c * 4 + f];
  const pitch = grados(Math.atan2(m(2, 1), m(2, 2)));
  const yaw = grados(Math.atan2(-m(2, 0), Math.hypot(m(2, 1), m(2, 2))));
  const roll = grados(Math.atan2(m(1, 0), m(0, 0)));
  return [pitch, yaw, roll];
}

export function simetriaPar(izq, der, minimo = 0.15) {
  const mx = Math.max(izq, der);
  return mx > minimo ? limitar(1 - Math.abs(izq - der) / mx) : 1.0;
}

export function simetria(sonrisaIzq, sonrisaDer, earIzq, earDer) {
  const rel = (a, b) => {
    const mx = Math.max(a, b);
    return mx > 0.05 ? Math.abs(a - b) / mx : 0.0;
  };
  return limitar(1 - (2 * rel(sonrisaIzq, sonrisaDer) + rel(earIzq, earDer)) / 3);
}

export function metricasDe(resultado, ancho, alto, previas, basePose = [0, 0, 0]) {
  const m = { ...previas };
  if (!resultado.faceLandmarks || !resultado.faceLandmarks.length) {
    m.rostro = false;
    return m;
  }
  const p = resultado.faceLandmarks[0].map((q) => [q.x * ancho, q.y * alto]);
  m.rostro = true;
  m.ear_der = Math.min(1.0, ear(p, OJO_DER));
  m.ear_izq = Math.min(1.0, ear(p, OJO_IZQ));
  m.ear = (m.ear_izq + m.ear_der) / 2;
  m.mar = Math.min(1.0, mar(p));
  if (resultado.faceBlendshapes && resultado.faceBlendshapes.length) {
    const bs = {};
    for (const c of resultado.faceBlendshapes[0].categories) bs[c.categoryName] = c.score;
    const g = (n) => bs[n] ?? 0.0;
    m.sonrisa_izq = g("mouthSmileLeft");
    m.sonrisa_der = g("mouthSmileRight");
    m.sonrisa = (m.sonrisa_izq + m.sonrisa_der) / 2;
    m.cejas = Math.min(1.0, ((g("browInnerUp") + g("browOuterUpLeft") + g("browOuterUpRight")) / 3) * 1.5);
    m.cejas_izq = g("browOuterUpLeft");
    m.cejas_der = g("browOuterUpRight");
    m.simetria_sonrisa = simetriaPar(m.sonrisa_izq, m.sonrisa_der);
    m.simetria_cejas = simetriaPar(m.cejas_izq, m.cejas_der);
    m.simetria_ojos = simetriaPar(g("eyeBlinkLeft"), g("eyeBlinkRight"));
    m.cierre_ojos = (g("eyeBlinkLeft") + g("eyeBlinkRight")) / 2;
  }
  if (resultado.facialTransformationMatrixes && resultado.facialTransformationMatrixes.length) {
    const pose = euler(resultado.facialTransformationMatrixes[0]);
    [m.pitch, m.yaw, m.roll] = pose.map((v, i) => Math.max(-90.0, Math.min(90.0, v - basePose[i])));
  }
  m.simetria = simetria(m.sonrisa_izq, m.sonrisa_der, m.ear_izq, m.ear_der);
  return m;
}

// Calibración de la postura neutra (como SensorCamara._calibrar): acumula la pose mientras
// la cabeza esté quieta; si se mueve más de 4° respecto de la mediana, empieza de nuevo.
export class Calibrador {
  constructor(segundos = 2.0) {
    this.segundos = segundos;
    this.poses = [];
    this.base = [0, 0, 0];
    this.listo = false;
  }

  reiniciar() {
    this.poses = [];
    this.listo = false;
  }

  // Devuelve {listo, faltan_s} o {listo: false, sinRostro: true}.
  agregar(resultado, ahoraMs) {
    if (!resultado.facialTransformationMatrixes || !resultado.facialTransformationMatrixes.length) {
      this.poses = [];
      return { listo: false, sinRostro: true };
    }
    this.poses.push([ahoraMs, ...euler(resultado.facialTransformationMatrixes[0])]);
    const medianas = [1, 2, 3].map((i) => {
      const v = this.poses.map((p) => p[i]).sort((a, b) => a - b);
      return v[Math.floor(v.length / 2)];
    });
    const ultima = this.poses[this.poses.length - 1];
    if (medianas.some((med, i) => Math.abs(ultima[i + 1] - med) > 4)) this.poses = [ultima];
    const transcurrido = this.poses[this.poses.length - 1][0] - this.poses[0][0];
    if (transcurrido >= this.segundos * 1000 && this.poses.length >= 5) {
      this.base = medianas;
      this.listo = true;
      return { listo: true };
    }
    return { listo: false, faltan_s: Math.max(0, this.segundos - transcurrido / 1000) };
  }
}
