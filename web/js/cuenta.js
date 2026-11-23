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
  if (!r.ok) {
    const e = new ErrorApi(r.status, cuerpo?.error || MENSAJES[r.status] || `Error ${r.status} del servidor.`);
    // 401 fuera del inicio de sesión = la sesión expiró o se cerró en otro lado.
    if (r.status === 401 && ruta !== "entrar") window.dispatchEvent(new CustomEvent("sesion-expirada"));
    throw e;
  }
  return cuerpo;
}

const MENSAJES = {
  400: "Los datos enviados no son válidos.",
  401: "Tu sesión expiró o se cerró. Vuelve a iniciar sesión.",
  403: "Tu tipo de usuario no tiene permiso para esto.",
  404: "No se encontró lo que se pidió al servidor.",
  500: "El servidor tuvo un error. Intenta de nuevo en un momento.",
};

// El rol decide qué módulo puede usar la persona.
export const MODULO_DE_ROL = { terapia: "terapia", conductor: "conduccion" };

// Devuelve null si no hay sesión iniciada.
export const yo = () => api("GET", "yo");
export const entrar = (correo, contrasena) => api("POST", "entrar", { correo, contrasena });
export const registrar = (datos) => api("POST", "registro", datos);
export const salir = () => api("POST", "salir", {});
export const sesiones = () => api("GET", "sesiones");
export const guardarSesion = (reg) => api("POST", "sesiones", {
  modulo: reg.modulo, fecha: reg.fecha, simetria_minima: reg.simetria_minima, resultado: reg.r,
});
export const borrarSesiones = () => api("DELETE", "sesiones");
// Esfuerzo máximo de la persona en cada ejercicio (terapia): se mide contra él.
export const perfil = () => api("GET", "perfil");
export const guardarPerfil = (datos) => api("PUT", "perfil", datos);
export const borrarCuenta = () => api("DELETE", "cuenta");
