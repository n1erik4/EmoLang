// Compilador y EmoVM de EmoLang dentro del navegador (Pyodide).
// Es el mismo paquete de Python del repositorio, empacado en emolang.zip por web/construir.py.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
const VERSION = document.querySelector('meta[name="version"]')?.content || "local";

let carga = null;

export function cargarMotor() {
  carga ??= (async () => {
    const { loadPyodide } = await import(`${PYODIDE}pyodide.mjs`);
    const py = await loadPyodide({ indexURL: PYODIDE });
    const respuesta = await fetch(`emolang.zip?v=${VERSION}`);
    if (!respuesta.ok) throw new Error("no se encontró emolang.zip");
    py.unpackArchive(await respuesta.arrayBuffer(), "zip", { extractDir: "/home/pyodide" });
    return py.pyimport("emolang.web");
  })();
  return carga;
}

const fuentes = {};

export async function leerPrograma(nombre) {
  fuentes[nombre] ??= fetch(`programas/${nombre}?v=${VERSION}`).then((r) => {
    if (!r.ok) throw new Error(`no se encontró el programa ${nombre}`);
    return r.text();
  });
  return fuentes[nombre];
}

// Una sesión: compila el programa y lo ejecuta cuadro por cuadro.
export async function crearSesion(nombrePrograma) {
  const [web, fuente] = await Promise.all([cargarMotor(), leerPrograma(nombrePrograma)]);
  const s = web.nueva_sesion(fuente);
  const info = JSON.parse(s.info());
  return {
    info,
    paso: (tMs, metricas) => JSON.parse(s.paso(tMs, JSON.stringify(metricas))),
    terminar: () => {
      const r = JSON.parse(s.terminar());
      s.destroy();
      return r;
    },
  };
}
