// Cámara del dispositivo y MediaPipe Face Landmarker (corre en el navegador, con GPU si hay).

const VISION = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
const MODELO = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

let carga = null;

export function cargarDetector() {
  carga ??= (async () => {
    const { FaceLandmarker, FilesetResolver } = await import(`${VISION}/vision_bundle.mjs`);
    const archivos = await FilesetResolver.forVisionTasks(`${VISION}/wasm`);
    const opciones = (delegate) => ({
      baseOptions: { modelAssetPath: MODELO, delegate },
      runningMode: "VIDEO",
      numFaces: 1,
      outputFaceBlendshapes: true,
      outputFacialTransformationMatrixes: true,
    });
    try {
      return await FaceLandmarker.createFromOptions(archivos, opciones("GPU"));
    } catch {
      return await FaceLandmarker.createFromOptions(archivos, opciones("CPU"));
    }
  })();
  return carga;
}

export class ErrorCamara extends Error {}

export async function abrirCamara(video) {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    throw new ErrorCamara("La cámara solo funciona en una página segura (https). Abra la versión publicada del sitio.");
  }
  let flujo;
  try {
    flujo = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } },
    });
  } catch (e) {
    const mensajes = {
      NotAllowedError: "No se dio permiso para usar la cámara. Permítalo en la configuración del navegador (el candado junto a la dirección) y vuelva a intentar.",
      NotFoundError: "No se encontró ninguna cámara en este dispositivo.",
      NotReadableError: "La cámara está en uso por otra aplicación. Ciérrela y vuelva a intentar.",
      OverconstrainedError: "La cámara no admite la configuración solicitada.",
    };
    throw new ErrorCamara(mensajes[e.name] || `No se pudo abrir la cámara (${e.name || e.message}).`);
  }
  video.srcObject = flujo;
  await video.play();
  return flujo;
}

export function cerrarCamara(flujo, video) {
  flujo?.getTracks().forEach((t) => t.stop());
  if (video) video.srcObject = null;
}

// Llama a alCuadro(ahoraMs) con cada cuadro nuevo del video.
export function cadaCuadro(video, alCuadro) {
  let activo = true;
  const usarRVFC = "requestVideoFrameCallback" in HTMLVideoElement.prototype;
  const siguiente = () => {
    if (!activo) return;
    if (usarRVFC) video.requestVideoFrameCallback(paso);
    else requestAnimationFrame(paso);
  };
  const paso = () => {
    if (!activo) return;
    try {
      alCuadro(performance.now());
    } finally {
      siguiente();
    }
  };
  siguiente();
  return () => { activo = false; };
}
