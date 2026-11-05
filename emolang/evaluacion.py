"""Evaluación con pruebas controladas (objetivo específico 8).

Ejecuta el programa sobre escenarios simulados con verdad de terreno y mide,
por gesto: verdaderos positivos (VP), falsos positivos (FP), falsos negativos
(FN), precisión, exhaustividad (recall), F1, y la latencia de detección (desde
que inicia el gesto real hasta que el autómata emite el evento). También mide
la latencia de procesamiento del motor por cuadro.
"""

from dataclasses import dataclass, field

import os

from .captura import TECLAS
from .ejecucion import ejecutar
from .sensores import SensorCSV, SensorSimulado

# Tipos de evento que el simulador etiqueta con verdad de terreno
ETIQUETADOS = ["parpadeo", "bostezo", "microsueno", "cabeceo", "distraccion", "sonrisa", "cejas", "ojos"]

# Nombre del evento real en el simulador -> nombres de gesto aceptados en el programa
ALIAS = {
    "sonrisa": ["sonrisa", "sonreir", "sonrisa_ejercicio"],
    "microsueno": ["microsueno", "microsueño", "somnolencia"],
    "cejas": ["elevar_cejas"],
    "ojos": ["cerrar_ojos"],
}


@dataclass
class Conteo:
    vp: int = 0
    fp: int = 0
    fn: int = 0
    latencias: list = field(default_factory=list)

    @property
    def precision(self):
        return self.vp / (self.vp + self.fp) if self.vp + self.fp else None

    @property
    def recall(self):
        return self.vp / (self.vp + self.fn) if self.vp + self.fn else None

    @property
    def f1(self):
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)

    @property
    def exactitud(self):
        tot = self.vp + self.fp + self.fn
        return self.vp / tot if tot else None


def _emparejar(verdad, detecciones, tolerancia_ms, anticipo_ms=0):
    """Empareja cada evento real con la primera detección dentro de
    [inicio - anticipo, fin + tolerancia]. El anticipo absorbe el retraso de una
    persona al presionar la tecla de etiqueta."""
    c = Conteo()
    usadas = set()
    for ini, fin in verdad:
        match = next((i for i, t in enumerate(detecciones)
                      if i not in usadas and ini - anticipo_ms <= t <= fin + tolerancia_ms), None)
        if match is None:
            c.fn += 1
        else:
            usadas.add(match)
            c.vp += 1
            c.latencias.append(max(0.0, detecciones[match] - ini))
    c.fp = len(detecciones) - len(usadas)
    return c


def _mapa(gestos, etiquetables):
    """gesto del programa -> tipo de evento real etiquetado"""
    mapa = {}
    for tipo_real in etiquetables:
        nombres = [n for n in ALIAS.get(tipo_real, [tipo_real]) if n in gestos]
        if nombres:
            mapa[nombres[0]] = tipo_real
    return mapa


def fuentes_simuladas(escenarios, fps, semillas=range(5), ruido=1.0):
    for esc in escenarios:
        for semilla in semillas:
            yield f"simulado:{esc}#{semilla}", SensorSimulado(esc, fps=fps, semilla=semilla, ruido=0.012 * ruido), ETIQUETADOS


def fuentes_csv(rutas, fps):
    """Grabaciones reales hechas con `capturar`: se evalúan los tipos que se pueden
    etiquetar con teclado (el parpadeo es demasiado rápido para marcarlo a mano)."""
    for ruta in rutas:
        sensor = SensorCSV(ruta, fps=fps)
        if not sensor.etiquetado:
            raise ValueError(f"{ruta} no tiene columna 'etiquetas'; grábelo con 'emolang capturar'")
        yield f"real:{os.path.basename(ruta)}", sensor, list(TECLAS.values())


def evaluar(resultado, dominio, fuentes, tolerancia_ms=1500, anticipo_ms=0):
    gestos = set(resultado.analisis.dominios[dominio].gestos)
    por_gesto = {}
    latencias_proc = []
    nombres = []
    evaluados = set()
    programa = resultado.emoc_para_evaluar()
    for nombre, sensor, etiquetables in fuentes:
        mapa = _mapa(gestos, etiquetables)
        evaluados |= set(mapa)
        res = ejecutar(resultado, dominio, sensor, verbose=False, emoc=programa)
        nombres.append(nombre)
        latencias_proc.extend(res.latencias_ms)
        for g, tipo_real in mapa.items():
            verdad = [(a, b) for t, a, b in sensor.verdad if t == tipo_real]
            det = [t for t, ev in res.eventos if ev == g]
            c = _emparejar(verdad, det, tolerancia_ms, anticipo_ms)
            acc = por_gesto.setdefault(g, Conteo())
            acc.vp += c.vp
            acc.fp += c.fp
            acc.fn += c.fn
            acc.latencias += c.latencias
    latencias_proc.sort()
    return {
        "dominio": dominio, "fuentes": nombres, "corridas": len(nombres),
        "tolerancia_ms": tolerancia_ms, "anticipo_ms": anticipo_ms, "gestos": por_gesto,
        "no_evaluados": sorted(gestos - evaluados),
        "proc_media_ms": sum(latencias_proc) / len(latencias_proc) if latencias_proc else 0,
        "proc_p95_ms": latencias_proc[int(0.95 * (len(latencias_proc) - 1))] if latencias_proc else 0,
        "proc_max_ms": latencias_proc[-1] if latencias_proc else 0,
        "cuadros": len(latencias_proc),
    }


def _resumir_fuentes(nombres):
    reales = [n.split(":", 1)[1] for n in nombres if n.startswith("real:")]
    sim = {}
    for n in nombres:
        if n.startswith("simulado:"):
            esc = n.split(":", 1)[1].split("#")[0]
            sim[esc] = sim.get(esc, 0) + 1
    partes = []
    if reales:
        partes.append("grabaciones reales " + ", ".join(f"`{r}`" for r in reales))
    if sim:
        partes.append("escenarios simulados " + ", ".join(f"{e} (×{k})" for e, k in sim.items()))
    return "; ".join(partes)


def _pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def reporte_markdown(r, archivo):
    lineas = [
        f"# Evaluación de `{archivo}` — dominio `{r['dominio']}`", "",
        f"- Fuentes ({r['corridas']}): {_resumir_fuentes(r['fuentes'])}",
        f"- Emparejamiento: detección entre {r['anticipo_ms']:g} ms antes del inicio etiquetado y "
        f"{r['tolerancia_ms']:g} ms después del fin",
        "", "## Reconocimiento de gestos", "",
        "| Gesto | VP | FP | FN | Precisión | Recall | F1 | Exactitud | Latencia detección (media) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    total = Conteo()
    for g, c in sorted(r["gestos"].items()):
        lat = f"{sum(c.latencias) / len(c.latencias):.0f} ms" if c.latencias else "—"
        lineas.append(f"| {g} | {c.vp} | {c.fp} | {c.fn} | {_pct(c.precision)} | {_pct(c.recall)} | "
                      f"{_pct(c.f1)} | {_pct(c.exactitud)} | {lat} |")
        total.vp += c.vp; total.fp += c.fp; total.fn += c.fn; total.latencias += c.latencias
    lat = f"{sum(total.latencias) / len(total.latencias):.0f} ms" if total.latencias else "—"
    lineas.append(f"| **Total** | {total.vp} | {total.fp} | {total.fn} | {_pct(total.precision)} | "
                  f"{_pct(total.recall)} | {_pct(total.f1)} | {_pct(total.exactitud)} | {lat} |")
    if r["no_evaluados"]:
        lineas += ["", "Gestos sin verdad de terreno (no evaluados): "
                   + ", ".join(r["no_evaluados"])]
    lineas += [
        "", "Exactitud = VP / (VP + FP + FN). La latencia de detección incluye la duración mínima "
        "que el propio gesto exige (`durante`).", "",
        "## Latencia de procesamiento del motor", "",
        f"- Cuadros procesados: {r['cuadros']}",
        f"- Media: {r['proc_media_ms']:.3f} ms/cuadro · p95: {r['proc_p95_ms']:.3f} ms · "
        f"máximo: {r['proc_max_ms']:.3f} ms",
        f"- Presupuesto a 30 fps: 33.3 ms/cuadro (el motor usa {100 * r['proc_media_ms'] / 33.3:.2f}% "
        "en promedio, sin contar la extracción de puntos faciales de MediaPipe)",
    ]
    return "\n".join(lineas)
