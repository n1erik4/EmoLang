// Cuenta del usuario y sus sesiones guardadas (API de web/servidor.py).
// La sesión viaja en una cookie HttpOnly: el JavaScript nunca ve el token.

export class ErrorApi extends Error {
  constructor(estado, mensaje) {
    super(mensaje);
    this.estado = estado;
  }
}

async function api(metodo, ruta, datos) {
  let r;
  try {
    r = await fetch(`api/${ruta}`, {
      method: metodo,
      credentials: "same-origin",
      headers: datos ? { "Content-Type": "application/json" } : {},
      body: datos ? JSON.stringify(datos) : undefined,
    });
  } catch {
    throw new ErrorApi(0, "No hay conexión con el servidor.");
  }
  let cuerpo = null;
  try { cuerpo = await r.json(); } catch { /* sin cuerpo */ }
  if (!r.ok) throw new ErrorApi(r.status, cuerpo?.error || `Error ${r.status}`);
  return cuerpo;
}

// El rol decide qué módulo puede usar la persona.
export const MODULO_DE_ROL = { terapia: "terapia", conductor: "conduccion" };

export const yo = async () => {
  try {
    return await api("GET", "yo");
  } catch (e) {
    if (e.estado === 401) return null;
    throw e;
  }
};
export const entrar = (correo, contrasena) => api("POST", "entrar", { correo, contrasena });
export const registrar = (datos) => api("POST", "registro", datos);
export const salir = () => api("POST", "salir", {});
export const sesiones = () => api("GET", "sesiones");
export const guardarSesion = (reg) => api("POST", "sesiones", {
  modulo: reg.modulo, fecha: reg.fecha, simetria_minima: reg.simetria_minima, resultado: reg.r,
});
export const borrarSesiones = () => api("DELETE", "sesiones");
export const borrarCuenta = () => api("DELETE", "cuenta");
