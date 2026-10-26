"""Módulos de dominio (objetivo específico 7).

Implementan las funciones predefinidas con efectos (alarma, registrar,
contar_repeticion...) y el reporte final de cada dominio.
"""

import csv
import threading


class ModuloBase:
    nombre = "general"

    def __init__(self, sonido=False, salida=print):
        self.sonido = sonido
        self.salida = salida
        self.bitacora = []          # (t_ms, tipo, detalle)
        self.alarma_activa = False
        self.alarma_mensaje = ""
        self._t_alarma = None
        self.tiempo_alarma_ms = 0.0
        self.alarmas = 0
        self.reps = []              # (t_ms, simetria)
        self.t = 0.0
        self.metricas = {}

    # llamado por el motor antes de cada cuadro
    def cuadro(self, t_ms, metricas):
        self.t = t_ms
        self.metricas = metricas

    def _linea(self, etiqueta, texto):
        self.salida(f"  [{self.t / 1000:7.2f} s] {etiqueta:<10} {texto}")

    def evento(self, tipo, detalle):
        self.bitacora.append((self.t, tipo, detalle))
        if tipo in ("gesto", "secuencia"):
            self._linea(tipo, detalle)
        elif tipo == "transicion":
            self._linea("estado", detalle)

    # --- funciones predefinidas ------------------------------------------
    def alarma(self, mensaje):
        if not self.alarma_activa:
            self.alarmas += 1
            self._t_alarma = self.t
        self.alarma_activa = True
        self.alarma_mensaje = mensaje
        self.evento("alarma", mensaje)
        self._linea("ALARMA", mensaje)
        if self.sonido:
            _pitido()

    def detener_alarma(self):
        if self.alarma_activa:
            self.tiempo_alarma_ms += self.t - self._t_alarma
            self.evento("alarma_detenida", self.alarma_mensaje)
        self.alarma_activa = False
        self.alarma_mensaje = ""

    def registrar(self, mensaje):
        self.evento("registro", mensaje)
        self._linea("registro", mensaje)

    def mostrar(self, texto):
        self._linea("mensaje", texto)

    def contar_repeticion(self):
        sim = float(self.metricas.get("simetria", 0.0))
        self.reps.append((self.t, sim))
        self.evento("repeticion", f"#{len(self.reps)} simetria={sim:.2f}")

    def repeticiones(self):
        return len(self.reps)

    # --- cierre -----------------------------------------------------------
    def finalizar(self):
        if self.alarma_activa:
            self.tiempo_alarma_ms += self.t - self._t_alarma

    def resumen(self):
        return {"eventos_registrados": len(self.bitacora)}

    def exportar_bitacora(self, ruta):
        with open(ruta, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["t_s", "tipo", "detalle"])
            for t, tipo, det in self.bitacora:
                w.writerow([f"{t / 1000:.3f}", tipo, det])


class ModuloConduccion(ModuloBase):
    nombre = "conduccion"

    def resumen(self):
        gestos = {}
        for _, tipo, det in self.bitacora:
            if tipo == "gesto":
                gestos[det] = gestos.get(det, 0) + 1
        return {
            "alarmas_emitidas": self.alarmas,
            "tiempo_en_alarma_s": round(self.tiempo_alarma_ms / 1000, 2),
            "gestos_detectados": gestos,
            "eventos_registrados": sum(1 for _, t, _ in self.bitacora if t == "registro"),
        }


class ModuloRehabilitacion(ModuloBase):
    nombre = "rehabilitacion"

    def resumen(self):
        sims = [s for _, s in self.reps]
        r = {"repeticiones": len(self.reps)}
        if sims:
            r["simetria_promedio_%"] = round(100 * sum(sims) / len(sims), 1)
            r["simetria_minima_%"] = round(100 * min(sims), 1)
            r["simetria_maxima_%"] = round(100 * max(sims), 1)
        if len(self.reps) >= 2:
            ts = [t for t, _ in self.reps]
            r["ritmo_promedio_s"] = round((ts[-1] - ts[0]) / 1000 / (len(ts) - 1), 2)
        return r


def modulo_para(dominio, **kw):
    n = dominio.lower()
    if any(p in n for p in ("conduc", "transporte", "fatiga", "manejo")):
        return ModuloConduccion(**kw)
    if any(p in n for p in ("rehab", "salud", "terapia")):
        return ModuloRehabilitacion(**kw)
    return ModuloBase(**kw)


def _pitido():
    try:
        import winsound
        threading.Thread(target=winsound.Beep, args=(1200, 300), daemon=True).start()
    except Exception:
        print("\a", end="", flush=True)
