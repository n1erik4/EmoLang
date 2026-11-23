"""Captura de métricas reales con etiquetas manuales (verdad de terreno).

Mientras se graba, la persona marca el inicio y el fin de cada gesto con una
tecla (alternar). Cada cuadro se guarda en un CSV con las métricas y una
columna `etiquetas` con los gestos marcados como activos en ese cuadro. El CSV
se reproduce después con `--sensor csv` o se evalúa con `evaluar --csv`.
"""

import csv
import os

from .metricas import METRICAS

TECLAS = {
    "b": "bostezo",
    "m": "microsueno",
    "c": "cabeceo",
    "d": "distraccion",
    "s": "sonrisa",
    "e": "cejas",
    "o": "ojos",
}
COLUMNAS = [n for n in METRICAS if n != "perclos"]   # perclos lo calcula el motor


def capturar(destino, indice=0, fps=30, duracion=None, salida=print):
    from .camara import SensorCamara

    sensor = SensorCamara(indice=indice, fps=fps, duracion=duracion, mostrar_video=True)
    activas = {}       # tipo -> t de inicio
    intervalos = []    # (tipo, inicio, fin)
    t_actual = [0.0]

    def alternar(tecla):
        tipo = TECLAS.get(tecla)
        if tipo is None:
            return
        if tipo in activas:
            intervalos.append((tipo, activas.pop(tipo), t_actual[0]))
            salida(f"  [{t_actual[0] / 1000:7.2f} s] fin de {tipo}")
        else:
            activas[tipo] = t_actual[0]
            salida(f"  [{t_actual[0] / 1000:7.2f} s] inicio de {tipo}")

    sensor.al_tecla = alternar
    sensor.lineas_extra = lambda: [
        "Marcar inicio/fin:  " + "  ".join(f"[{k}] {v}" for k, v in TECLAS.items()) + "   [q] salir",
        "Grabando  " + (f"| ACTIVO: {', '.join(activas)}" if activas else "| sin etiqueta activa"),
    ]

    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    cuadros = 0
    with open(destino, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_ms"] + COLUMNAS + ["etiquetas"])
        for t, m in sensor:
            t_actual[0] = t
            w.writerow([f"{t:.1f}"] + [int(m[n]) if isinstance(m[n], bool) else f"{m[n]:.4f}"
                                       for n in COLUMNAS] + [";".join(sorted(activas))])
            cuadros += 1
    for tipo, ini in activas.items():
        intervalos.append((tipo, ini, t_actual[0]))
    return cuadros, intervalos
