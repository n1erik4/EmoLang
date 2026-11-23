// Landing: carrusel de gestos sin fin y cierre del menú del celular.

const carrusel = document.getElementById("carrusel");
const pista = carrusel?.querySelector(".carrusel__pista");
if (pista) {
  // Una copia seguida de la lista: al recorrer la mitad, la animación vuelve al
  // inicio sin que se note. La copia no la leen los lectores de pantalla.
  for (const li of [...pista.children]) {
    const copia = li.cloneNode(true);
    copia.setAttribute("aria-hidden", "true");
    pista.append(copia);
  }
  // Velocidad constante: más gestos, más tiempo por vuelta.
  pista.style.setProperty("--duracion", `${pista.children.length * 2.2}s`);
}

// El menú del celular se cierra al elegir una sección.
const menu = document.querySelector(".nav__menu");
menu?.addEventListener("click", (ev) => {
  if (ev.target.closest("a")) menu.open = false;
});
