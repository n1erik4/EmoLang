"""Sensor de cámara RGB con MediaPipe Face Landmarker (API de Tasks).

Requiere: mediapipe y opencv-python (usar Python 3.9-3.12) y el modelo
modelos/face_landmarker.task, que se descarga automáticamente la primera vez.

Métricas calculadas por cuadro:
  ear, ear_izq, ear_der   razón de aspecto del ojo (Soukupová y Čech, 2016)
  mar                     razón de aspecto de la boca (labios internos)
  sonrisa_izq/der, cejas  blendshapes de MediaPipe (mouthSmile*, brow*)
  pitch, yaw, roll        pose de la cabeza (grados) desde la matriz de transformación,
                          relativa a la postura neutra medida en la calibración
  simetria                comparación izquierda/derecha de sonrisa y apertura ocular
  simetria_sonrisa/cejas/ojos  comparación izquierda/derecha de un solo ejercicio
"""

import math
import os
import time
import urllib.request

from .metricas import metricas_neutras
from .sensores import simetria, simetria_par

URL_MODELO = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
              "face_landmarker/float16/latest/face_landmarker.task")
RUTA_MODELO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "modelos", "face_landmarker.task")

# Índices de la malla de 478 puntos. Orden EAR: p1, p2, p3, p4, p5, p6
OJO_DER = [33, 160, 158, 133, 153, 144]     # ojo derecho de la persona
OJO_IZQ = [362, 385, 387, 263, 373, 380]    # ojo izquierdo de la persona
BOCA_V = [(81, 178), (13, 14), (311, 402)]  # pares verticales de labios internos
BOCA_H = (78, 308)                          # comisuras internas


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _ear(p, idx):
    p1, p2, p3, p4, p5, p6 = (p[i] for i in idx)
    return (_dist(p2, p6) + _dist(p3, p5)) / (2.0 * _dist(p1, p4) + 1e-9)


def _mar(p):
    vertical = sum(_dist(p[a], p[b]) for a, b in BOCA_V) / len(BOCA_V)
    return vertical / (_dist(p[BOCA_H[0]], p[BOCA_H[1]]) + 1e-9)


def _euler(m):
    """pitch, yaw, roll (grados) de una matriz 4x4; pitch positivo = cabeza hacia abajo."""
    pitch = math.degrees(math.atan2(m[2][1], m[2][2]))
    yaw = math.degrees(math.atan2(-m[2][0], math.hypot(m[2][1], m[2][2])))
    roll = math.degrees(math.atan2(m[1][0], m[0][0]))
    return pitch, yaw, roll


_FUENTES = {}


def _fuente(tam):
    """Fuente TrueType con acentos y ñ (cv2.putText solo dibuja ASCII)."""
    if tam not in _FUENTES:
        from PIL import ImageFont
        for ruta in (r"C:\Windows\Fonts\arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            if os.path.exists(ruta):
                _FUENTES[tam] = ImageFont.truetype(ruta, tam)
                break
        else:
            _FUENTES[tam] = ImageFont.load_default(tam)
    return _FUENTES[tam]


def _escribir(vista_bgr, textos):
    """Dibuja (texto, (x, y_superior), tamaño, color RGB) con contorno negro sobre el cuadro."""
    if not textos:
        return vista_bgr
    import numpy as np
    from PIL import Image, ImageDraw
    img = Image.fromarray(vista_bgr[:, :, ::-1])
    d = ImageDraw.Draw(img)
    for texto, pos, tam, color in textos:
        d.text(pos, texto, font=_fuente(tam), fill=color, stroke_width=2, stroke_fill=(0, 0, 0))
    return np.ascontiguousarray(np.asarray(img)[:, :, ::-1])


def asegurar_modelo(ruta=RUTA_MODELO):
    if not os.path.exists(ruta):
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        print(f"Descargando modelo de MediaPipe a {ruta} ...")
        urllib.request.urlretrieve(URL_MODELO, ruta)
    return ruta


class SensorCamara:
    def __init__(self, indice=0, fps=30, duracion=None, mostrar_video=True, calibracion_s=2.0):
        try:
            import cv2  # noqa: F401
            import mediapipe  # noqa: F401
        except ImportError as e:
            raise SystemExit(
                "El sensor de cámara requiere mediapipe y opencv-python.\n"
                "Use el entorno del proyecto:  .venv\\Scripts\\python -m emolang ejecutar ... --sensor camara\n"
                f"(detalle: {e})")
        self.indice = indice
        self.fps = fps
        self.duracion = duracion
        self.mostrar_video = mostrar_video
        self.calibracion_s = calibracion_s
        self.motor = None       # lo asigna ejecucion.ejecutar para dibujar el estado
        self.tasa_variable = True  # la cámara entrega cuadros a ritmo irregular
        self._recalibrar = False
        self._aviso = None
        self.cuadros_leidos = 0
        self.segundos = 0.0
        self.al_tecla = None    # callback(tecla: str) para etiquetar durante la captura
        self.lineas_extra = None  # callable -> list[str] con texto adicional del overlay
        self._base_pose = (0.0, 0.0, 0.0)

    def _crear_detector(self):
        from mediapipe.tasks.python import BaseOptions, vision
        opciones = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=asegurar_modelo()),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        return vision.FaceLandmarker.create_from_options(opciones)

    def _metricas(self, resultado, ancho, alto, previas):
        m = dict(previas)
        if not resultado.face_landmarks:
            m["rostro"] = False
            return m
        lm = resultado.face_landmarks[0]
        p = [(q.x * ancho, q.y * alto) for q in lm]
        m["rostro"] = True
        m["ear_der"] = min(1.0, _ear(p, OJO_DER))
        m["ear_izq"] = min(1.0, _ear(p, OJO_IZQ))
        m["ear"] = (m["ear_izq"] + m["ear_der"]) / 2
        m["mar"] = min(1.0, _mar(p))
        if resultado.face_blendshapes:
            bs = {c.category_name: c.score for c in resultado.face_blendshapes[0]}
            m["sonrisa_izq"] = bs.get("mouthSmileLeft", 0.0)
            m["sonrisa_der"] = bs.get("mouthSmileRight", 0.0)
            m["sonrisa"] = (m["sonrisa_izq"] + m["sonrisa_der"]) / 2
            m["cejas"] = min(1.0, (bs.get("browInnerUp", 0.0) + bs.get("browOuterUpLeft", 0.0)
                                   + bs.get("browOuterUpRight", 0.0)) / 3 * 1.5)
            m["cejas_izq"] = bs.get("browOuterUpLeft", 0.0)
            m["cejas_der"] = bs.get("browOuterUpRight", 0.0)
            m["simetria_sonrisa"] = simetria_par(m["sonrisa_izq"], m["sonrisa_der"])
            m["simetria_cejas"] = simetria_par(m["cejas_izq"], m["cejas_der"])
            m["simetria_ojos"] = simetria_par(bs.get("eyeBlinkLeft", 0.0), bs.get("eyeBlinkRight", 0.0))
        if resultado.facial_transformation_matrixes:
            pose = _euler(resultado.facial_transformation_matrixes[0])
            m["pitch"], m["yaw"], m["roll"] = (max(-90.0, min(90.0, v - b))
                                               for v, b in zip(pose, self._base_pose))
        m["simetria"] = simetria(m["sonrisa_izq"], m["sonrisa_der"], m["ear_izq"], m["ear_der"])
        return m

    def __iter__(self):
        import cv2
        import mediapipe as mp

        cap = cv2.VideoCapture(self.indice, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(self.indice)
        if not cap.isOpened():
            raise SystemExit(f"No se pudo abrir la cámara {self.indice}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        detector = self._crear_detector()
        inicio = time.perf_counter()
        ultimo_ts = -1
        previas = metricas_neutras()
        poses = []              # (ms, pitch, yaw, roll) de la calibración en curso
        calibrado = False
        t0 = None               # instante en que terminó la primera calibración
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                ahora = (time.perf_counter() - inicio) * 1000
                ts = max(int(ahora), ultimo_ts + 1)   # MediaPipe exige marcas crecientes
                ultimo_ts = ts
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
                alto, ancho = frame.shape[:2]

                if self._recalibrar:
                    self._recalibrar, calibrado, poses = False, False, []
                if not calibrado:
                    calibrado, mensaje = self._calibrar(res, ahora, poses)
                    if calibrado and t0 is None:
                        t0 = ahora
                    if t0 is None:   # primera calibración: todavía no se entregan cuadros
                        if self.mostrar_video and self._mostrar(frame, None, calibrando=mensaje):
                            break
                        continue
                    self._aviso = None if calibrado else mensaje

                t = ahora - t0
                if self.duracion and t > self.duracion * 1000:
                    break
                previas = self._metricas(res, ancho, alto, previas)
                self.cuadros_leidos += 1
                self.segundos = t / 1000
                yield t, previas
                # al reanudar, el motor ya procesó este cuadro: se dibuja su estado
                if self.mostrar_video and self._mostrar(frame, previas, lm=res.face_landmarks):
                    break
        finally:
            cap.release()
            detector.close()
            if self.mostrar_video:
                cv2.destroyAllWindows()

    def _calibrar(self, res, ahora, poses):
        """Acumula la pose mientras la cabeza esté quieta y de frente. Si la persona
        se mueve (más de 4° respecto de la mediana) la cuenta vuelve a empezar.
        Devuelve (terminado, mensaje para mostrar)."""
        if not res.facial_transformation_matrixes:
            poses.clear()
            return False, "Calibrando: no se detecta el rostro"
        poses.append((ahora,) + _euler(res.facial_transformation_matrixes[0]))
        medianas = [sorted(v)[len(v) // 2] for v in list(zip(*poses))[1:]]
        if any(abs(p - med) > 4 for p, med in zip(poses[-1][1:], medianas)):
            del poses[:-1]
        transcurrido = poses[-1][0] - poses[0][0]
        if transcurrido >= self.calibracion_s * 1000 and len(poses) >= 5:
            self._base_pose = tuple(medianas)
            return True, ""
        faltan = self.calibracion_s - transcurrido / 1000
        return False, f"Calibrando: mire al frente y no se mueva... {faltan:.1f} s"

    def _mostrar(self, frame, m, calibrando=False, lm=None):
        """Dibuja el overlay. Devuelve True si el usuario pidió salir (q / ESC)."""
        import cv2
        alto, ancho = frame.shape[:2]
        if lm:
            for idx in OJO_DER + OJO_IZQ + [BOCA_H[0], BOCA_H[1], 13, 14]:
                q = lm[0][idx]
                cv2.circle(frame, (int(q.x * ancho), int(q.y * alto)), 1, (0, 255, 0), -1)
        vista = cv2.flip(frame, 1)
        textos = []   # (texto, (x, y_superior), tamaño, color RGB)
        if calibrando:
            textos.append((str(calibrando), (20, 20), 22, (255, 255, 0)))
        else:
            fps = self.cuadros_leidos / self.segundos if self.segundos > 0 else 0
            lineas = [f"EAR {m['ear']:.2f}  MAR {m['mar']:.2f}  sonrisa {m['sonrisa']:.2f}  "
                      f"({fps:.0f} fps cámara)",
                      f"pitch {m['pitch']:+.0f}  yaw {m['yaw']:+.0f}  roll {m['roll']:+.0f}  "
                      f"simetría {m['simetria'] * 100:.0f}%  PERCLOS {m.get('perclos', 0) * 100:.0f}%"]
            if not m["rostro"]:
                lineas.append("SIN ROSTRO")
            lineas.append(self._aviso or "[r] recalibrar postura")
            if self.motor:
                for maq, est in self.motor.estado_actual().items():
                    lineas.append(f"{maq}: {est}")
                activos = self.motor.gestos_activos()
                lineas.append("condiciones: " + (", ".join(activos) or "-"))
                if self.motor.modulo.reps:
                    lineas.append(f"repeticiones: {len(self.motor.modulo.reps)}")
            for i, txt in enumerate(lineas):
                textos.append((txt, (12, 10 + 24 * i), 17, (255, 255, 255)))
            if self.lineas_extra:
                for i, txt in enumerate(self.lineas_extra()):
                    textos.append((txt, (12, alto - 34 - 24 * i), 17, (255, 255, 0)))
            if self.motor and self.motor.modulo.alarma_activa:
                cv2.rectangle(vista, (0, alto - 60), (ancho, alto), (0, 0, 255), -1)
                textos.append((self.motor.modulo.alarma_mensaje, (16, alto - 46), 28, (255, 255, 255)))
        vista = _escribir(vista, textos)
        cv2.imshow("EmoLang", vista)
        tecla = cv2.waitKey(1) & 0xFF
        if tecla in (ord("q"), 27):
            return True
        if tecla == ord("r") and not calibrando:
            self._recalibrar = True
            return False
        # cerrar con la X: imshow volvería a abrir la ventana en el siguiente cuadro
        if cv2.getWindowProperty("EmoLang", cv2.WND_PROP_VISIBLE) < 1:
            return True
        if tecla != 255 and self.al_tecla and not calibrando:
            self.al_tecla(chr(tecla).lower())
        return False
