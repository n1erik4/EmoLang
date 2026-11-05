"""Sensores: fuentes de métricas faciales cuadro por cuadro.

  SensorSimulado  genera métricas sintéticas a partir de un guion de eventos
                  con verdad de terreno (para pruebas y evaluación).
  SensorCSV       reproduce métricas grabadas en un archivo CSV.
  SensorCamara    cámara RGB + MediaPipe Face Mesh (requiere mediapipe y opencv).

Todos producen tuplas (t_ms, metricas) mediante iteración.
"""

import csv
import math
import random

from .metricas import METRICAS, metricas_neutras

# ---------------------------------------------------------------------------
# Escenarios simulados: lista de (tipo, inicio_s, duracion_s, parametros)
# ---------------------------------------------------------------------------
ESCENARIOS = {
    "conduccion": {
        "duracion": 40.0,
        "eventos": [
            ("bostezo", 5.0, 3.0, {}),
            ("microsueno", 11.0, 1.6, {}),
            ("bostezo", 17.0, 3.0, {}),
            ("cabeceo", 21.5, 0.9, {}),
            ("microsueno", 29.0, 2.2, {}),
            ("distraccion", 34.0, 2.5, {}),
        ],
    },
    "normal": {
        "duracion": 60.0,
        "eventos": [],
    },
    "rehabilitacion": {
        "duracion": 45.0,
        "eventos": [("sonrisa", 2.0 + 4.0 * i, 1.6, {"asimetria": a})
                    for i, a in enumerate([0.05, 0.10, 0.30, 0.08, 0.15, 0.40, 0.05, 0.12, 0.20, 0.06])],
    },
    "terapia": {
        "duracion": 70.0,
        "eventos": ([("sonrisa", 2.0 + 4.0 * i, 1.6, {"asimetria": a})
                     for i, a in enumerate([0.05, 0.10, 0.35, 0.08, 0.12])]
                    + [("cejas", 24.0 + 4.0 * i, 1.6, {"asimetria": a})
                       for i, a in enumerate([0.06, 0.40, 0.10, 0.05, 0.09])]
                    + [("ojos", 46.0 + 4.0 * i, 2.0, {"asimetria": a})
                       for i, a in enumerate([0.04, 0.08, 0.05, 0.45, 0.07])]),
    },
}


class SensorSimulado:
    def __init__(self, escenario="conduccion", fps=30, semilla=7, ruido=0.012,
                 parpadeos=True, duracion=None):
        if escenario not in ESCENARIOS:
            raise ValueError(f"escenario desconocido '{escenario}'. Opciones: {', '.join(ESCENARIOS)}")
        esc = ESCENARIOS[escenario]
        self.fps = fps
        self.duracion = duracion or esc["duracion"]
        self.rng = random.Random(semilla)
        self.rng_lados = random.Random(semilla + 1)
        self.ruido = ruido
        self.eventos = [e for e in esc["eventos"] if e[1] < self.duracion]
        self.verdad = [(tipo, ini * 1000, (ini + dur) * 1000) for tipo, ini, dur, _ in self.eventos]
        self._parpadeos = self._programar_parpadeos() if parpadeos else []
        self.verdad += [("parpadeo", a, b) for a, b in self._parpadeos]
        self.verdad.sort(key=lambda v: v[1])

    def _programar_parpadeos(self):
        res, t = [], 1.5
        ocupado = [(ini - 0.5, ini + dur + 0.5) for tipo, ini, dur, _ in self.eventos
                   if tipo in ("microsueno", "bostezo", "cabeceo", "ojos")]
        while t < self.duracion - 1:
            dur = self.rng.uniform(0.10, 0.25)
            if not any(a <= t <= b for a, b in ocupado):
                res.append((t * 1000, (t + dur) * 1000))
            t += self.rng.uniform(2.5, 5.0)
        return res

    def __iter__(self):
        periodo = 1000.0 / self.fps
        n = int(self.duracion * self.fps)
        for i in range(n):
            t = i * periodo
            yield t, self._metricas(t)

    def _metricas(self, t_ms):
        m = metricas_neutras()
        ts = t_ms / 1000
        rn = lambda s=1.0: self.rng.gauss(0, self.ruido * s)
        cejas_izq = cejas_der = None
        cierre_izq = cierre_der = 0.0

        for a, b in self._parpadeos:
            if a <= t_ms < b:
                m["ear"] = 0.08
        for tipo, ini, dur, p in self.eventos:
            if not (ini <= ts < ini + dur):
                continue
            x = (ts - ini) / dur                     # progreso 0..1
            campana = math.sin(math.pi * x)          # sube y baja suavemente
            if tipo == "bostezo":
                m["mar"] = 0.03 + 0.42 * min(1.0, 1.6 * campana)   # medido: ~0.38-0.45
                m["ear"] = 0.30 - 0.15 * campana   # se entrecierran los ojos (medido: ~0.15)
                m["pitch"] = -8 * campana
            elif tipo == "microsueno":
                m["ear"] = 0.07
                m["pitch"] = 8 * min(1.0, 3 * x)
            elif tipo == "cabeceo":
                m["pitch"] = 16 * campana                           # medido: ~8-12° (+ margen)
                m["ear"] = 0.24
            elif tipo == "distraccion":
                m["yaw"] = 28 * min(1.0, 3 * campana)               # medido: 23-33°
            elif tipo == "sonrisa":
                nivel = 0.75 * min(1.0, 1.8 * campana)
                asim = p.get("asimetria", 0.0)
                m["sonrisa_izq"] = nivel
                m["sonrisa_der"] = nivel * (1 - asim)
                m["sonrisa"] = (m["sonrisa_izq"] + m["sonrisa_der"]) / 2
                m["ear"] = 0.30 - 0.12 * campana   # medido: ~0.18 al sonreir
            elif tipo == "cejas":
                nivel = 0.2 + 0.55 * min(1.0, 1.8 * campana)
                cejas_izq, cejas_der = nivel, nivel * (1 - p.get("asimetria", 0.0))
                m["cejas"] = (cejas_izq + cejas_der) / 2
            elif tipo == "ojos":
                m["ear"] = 0.06
                cierre_izq, cierre_der = 0.9, 0.9 * (1 - p.get("asimetria", 0.0))

        # ruido de medición
        for k in ("ear", "mar", "sonrisa_izq", "sonrisa_der", "cejas"):
            m[k] = _limitar(m[k] + rn())
        m["sonrisa"] = _limitar((m["sonrisa_izq"] + m["sonrisa_der"]) / 2 + rn(0.3))
        m["pitch"] += rn(60)
        m["yaw"] += rn(60)
        m["roll"] += rn(40)
        m["ear_izq"] = _limitar(m["ear"] + rn(0.5))
        m["ear_der"] = _limitar(m["ear"] + rn(0.5))
        m["simetria"] = simetria(m["sonrisa_izq"], m["sonrisa_der"], m["ear_izq"], m["ear_der"])
        lado = lambda: self.rng_lados.gauss(0, self.ruido)
        m["cejas_izq"] = _limitar((m["cejas"] if cejas_izq is None else cejas_izq) + lado())
        m["cejas_der"] = _limitar((m["cejas"] if cejas_der is None else cejas_der) + lado())
        m["simetria_sonrisa"] = simetria_par(m["sonrisa_izq"], m["sonrisa_der"])
        m["simetria_cejas"] = simetria_par(m["cejas_izq"], m["cejas_der"])
        m["simetria_ojos"] = simetria_par(_limitar(cierre_izq + lado()), _limitar(cierre_der + lado()))
        return m


class SensorCSV:
    """Lee un CSV con columna t_ms (o t_s) y columnas con nombres de métricas."""

    tasa_variable = True   # las grabaciones reales no tienen periodo fijo

    def __init__(self, ruta, fps=30):
        self.ruta = ruta
        self.fps = fps
        self.verdad = self._leer_etiquetas()

    def _leer_etiquetas(self):
        """Convierte la columna `etiquetas` (gestos activos por cuadro) en intervalos
        (tipo, inicio_ms, fin_ms). Vacío si el CSV no tiene etiquetas."""
        verdad, abiertas, t = [], {}, 0.0
        for t, fila in self._filas():
            activas = {e for e in (fila.get("etiquetas") or "").split(";") if e}
            for tipo in activas - set(abiertas):
                abiertas[tipo] = t
            for tipo in set(abiertas) - activas:
                verdad.append((tipo, abiertas.pop(tipo), t))
        verdad += [(tipo, ini, t) for tipo, ini in abiertas.items()]
        return sorted(verdad, key=lambda v: v[1])

    @property
    def etiquetado(self):
        with open(self.ruta, newline="", encoding="utf-8") as f:
            return "etiquetas" in (csv.DictReader(f).fieldnames or [])

    def _filas(self):
        with open(self.ruta, newline="", encoding="utf-8") as f:
            for i, fila in enumerate(csv.DictReader(f)):
                if fila.get("t_ms"):
                    t = float(fila["t_ms"])
                elif fila.get("t_s"):
                    t = float(fila["t_s"]) * 1000
                else:
                    t = i * 1000.0 / self.fps
                yield t, fila

    def __iter__(self):
        for t, fila in self._filas():
            m = metricas_neutras()
            for k, v in fila.items():
                if k in METRICAS and v not in ("", None):
                    es_bool = METRICAS[k].tipo == "bool"
                    m[k] = v.strip().lower() in ("1", "true", "verdadero") if es_bool else float(v)
            yield t, m


def grabar_csv(sensor, ruta):
    """Guarda las métricas del sensor; la verdad de terreno (si existe) va en la
    columna `etiquetas`, con el mismo formato que produce `emolang capturar`."""
    verdad = getattr(sensor, "verdad", [])
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        nombres = [n for n in METRICAS if n != "perclos"]
        w.writerow(["t_ms"] + nombres + ["etiquetas"])
        for t, m in sensor:
            activas = sorted({tipo for tipo, a, b in verdad if a <= t < b})
            w.writerow([f"{t:.1f}"] + [(int(m[n]) if isinstance(m[n], bool) else f"{m[n]:.4f}")
                                       for n in nombres] + [";".join(activas)])


def simetria_par(izq, der, minimo=0.15):
    """1 = ambos lados iguales. Si apenas hay movimiento, no se puede medir y se reporta 1."""
    mx = max(izq, der)
    return _limitar(1 - abs(izq - der) / mx) if mx > minimo else 1.0


def simetria(sonrisa_izq, sonrisa_der, ear_izq, ear_der):
    """1 - diferencia relativa promedio entre lado izquierdo y derecho."""
    def rel(a, b):
        mx = max(a, b)
        return abs(a - b) / mx if mx > 0.05 else 0.0
    return _limitar(1 - (2 * rel(sonrisa_izq, sonrisa_der) + rel(ear_izq, ear_der)) / 3)


def _limitar(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))
