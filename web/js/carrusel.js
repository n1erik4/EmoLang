// Galería del acceso: tres filas de fotos que se desplazan sin fin
// (la primera y la tercera hacia la derecha, la segunda hacia la izquierda).
// Las fotos son de dominio público (Openverse); la lista está en img/galeria/galeria.json.

const VERSION = document.querySelector('meta[name="version"]')?.content || "local";

export async function iniciarGaleria(seccion) {
  if (!seccion) return;
  let datos;
  try {
    const r = await fetch(`img/galeria/galeria.json?v=${VERSION}`);
    if (!r.ok) throw new Error(r.status);
    datos = await r.json();
  } catch {
    seccion.hidden = true;           // sin fotos, el acceso funciona igual
    return;
  }
  for (const fila of seccion.querySelectorAll(".galeria__fila")) {
    const fotos = datos.grupos[fila.dataset.grupo] || [];
    if (!fotos.length) { fila.hidden = true; continue; }
    const pista = document.createElement("div");
    pista.className = "galeria__pista";
    // Dos copias seguidas: al recorrer la mitad, la animación vuelve al inicio sin que se note.
    for (let copia = 0; copia < 2; copia++) {
      for (const f of fotos) {
        const img = document.createElement("img");
        img.src = `img/galeria/${f.archivo}`;
        img.alt = copia === 0 ? f.alt : "";
        if (copia) img.setAttribute("aria-hidden", "true");
        img.width = f.ancho;
        img.height = f.alto;
        img.decoding = "async";
        pista.append(img);
      }
    }
    // Velocidad constante: más fotos, más tiempo por vuelta.
    pista.style.animationDuration = `${fotos.length * 7}s`;
    fila.replaceChildren(pista);
  }
}
