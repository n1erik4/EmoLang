"""Diagramas en blanco y negro para el reporte (arquitectura y autómatas)."""

import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from emolang import automatas as A  # noqa: E402
from emolang.compilador import compilar_archivo  # noqa: E402

SALIDA = os.path.join(AQUI, "figuras")
plt.rcParams.update({"font.family": "Arial", "font.size": 9, "text.color": "black"})
R = 0.32  # radio de los estados


def _guardar(fig, nombre):
    fig.savefig(os.path.join(SALIDA, nombre), dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ----------------------------------------------------------------- arquitectura
def arquitectura():
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    ax.set_xlim(0, 14.4)
    ax.set_ylim(0, 5.2)
    ax.axis("off")

    def caja(x, y, texto, w=1.9, h=0.9):
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="square,pad=0",
                                    fill=False, lw=0.8, color="black"))
        ax.text(x, y, texto, ha="center", va="center", fontsize=8)

    def flecha(a, b, texto=None, dy=0.18):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=9, lw=0.7, color="black"))
        if texto:
            ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + dy, texto, ha="center", va="bottom", fontsize=7)

    y1, y2 = 4.0, 1.3
    xs = [1.0, 3.3, 5.6, 7.9, 10.2, 12.9]
    nombres = ["Programa\n.emo", "Analizador\nléxico", "Analizador\nsintáctico", "Analizador\nsemántico",
               "Validaciones\nde dominio", "Generador de\nautómatas"]
    for x, n in zip(xs, nombres):
        caja(x, y1, n, w=1.8 if x < 12 else 2.0)
    etiquetas = ["texto", "tokens", "AST", "AST + tabla\nde símbolos", "AST validado"]
    for i in range(5):
        flecha((xs[i] + 0.9, y1), (xs[i + 1] - (0.9 if i < 4 else 1.0), y1), etiquetas[i], dy=0.5)

    caja(1.6, y2, "Cámara RGB\n(MediaPipe)", w=2.2)
    caja(5.0, y2, "Sensor\n(métricas)", w=1.8)
    caja(8.4, y2, "Motor de\nejecución", w=1.8)
    caja(12.0, y2, "Módulo de dominio\n(alarma, conteo)", w=2.6)
    flecha((2.7, y2), (4.1, y2), "cuadros")
    flecha((5.9, y2), (7.5, y2), "métricas")
    flecha((9.3, y2), (10.7, y2), "eventos")
    flecha((12.9, y1 - 0.45), (8.9, y2 + 0.45))
    ax.text(11.35, 2.75, "tablas de transición", fontsize=7, ha="left")
    ax.text(0.1, 5.05, "Compilación", fontsize=8, style="italic")
    ax.text(0.1, 2.35, "Ejecución (cada cuadro)", fontsize=8, style="italic")
    _guardar(fig, "fig_arquitectura.png")


# ----------------------------------------------------------------- autómatas
def _bezier(p1, c, p2, t):
    return tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * b + t ** 2 * d for a, b, d in zip(p1, c, p2))


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def _dibujar(ax, pos, trans, opciones=None, lazos=None, inicial=None, aceptacion=(), radio=0.32,
             tam_et=7.5, tam_estado=8):
    """opciones[(o, d)] = dict(rad=curvatura, t=posición de la etiqueta en la curva 0..1,
    dx/dy=desplazamiento extra de la etiqueta). lazos[q] = ángulo del lazo propio."""
    opciones = opciones or {}
    lazos = lazos or {}
    for q, (x, y) in pos.items():
        ax.add_patch(Circle((x, y), radio, fill=False, lw=0.9, color="black"))
        if q in aceptacion:
            ax.add_patch(Circle((x, y), radio * 0.82, fill=False, lw=0.7, color="black"))
        ax.text(x, y, q, ha="center", va="center", fontsize=tam_estado)
    if inicial:
        x, y = pos[inicial]
        ax.add_patch(FancyArrowPatch((x - radio - 0.7, y), (x - radio, y), arrowstyle="-|>",
                                     mutation_scale=9, lw=0.8, color="black"))

    etiquetas = {}
    for t in trans:
        et = t.simbolo + (f" [{t.guarda}]" if t.guarda else "") + (f" / {t.salida}" if t.salida else "")
        etiquetas.setdefault((t.origen, t.destino), []).append(et)

    caja = dict(boxstyle="square,pad=0.08", fc="white", ec="none")
    for (o, d), ets in etiquetas.items():
        if o not in pos or d not in pos:
            continue
        texto = "\n".join(ets)
        p1, p2 = pos[o], pos[d]
        if o == d:
            ang = math.radians(lazos.get(o, 90))
            ux, uy = math.cos(ang), math.sin(ang)
            px, py = -uy, ux
            a1 = (p1[0] + radio * (ux * 0.7 + px * 0.7), p1[1] + radio * (uy * 0.7 + py * 0.7))
            a2 = (p1[0] + radio * (ux * 0.7 - px * 0.7), p1[1] + radio * (uy * 0.7 - py * 0.7))
            ax.add_patch(FancyArrowPatch(a1, a2, connectionstyle="arc3,rad=-2.0", arrowstyle="-|>",
                                         mutation_scale=8, lw=0.7, color="black"))
            dist = radio * 1.9 + 0.3 + 0.055 * len(texto) * abs(ux)
            ax.text(p1[0] + ux * dist, p1[1] + uy * (radio * 1.9 + 0.3), texto, ha="center", va="center",
                    fontsize=tam_et, bbox=caja)
            continue
        op = opciones.get((o, d), {})
        rad = op.get("rad", 0.0)
        m = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        c = (m[0] + rad * (p2[1] - p1[1]), m[1] - rad * (p2[0] - p1[0]))
        u1, u2 = _unit(p1, c), _unit(p2, c)
        s1 = (p1[0] + radio * u1[0], p1[1] + radio * u1[1])
        s2 = (p2[0] + radio * u2[0], p2[1] + radio * u2[1])
        ax.add_patch(FancyArrowPatch(s1, s2, connectionstyle=f"arc3,rad={rad}", arrowstyle="-|>",
                                     mutation_scale=9, lw=0.7, color="black", shrinkA=0, shrinkB=0))
        lx, ly = _bezier(p1, c, p2, op.get("t", 0.5))
        ax.text(lx + op.get("dx", 0), ly + op.get("dy", 0), texto, ha="center", va="center",
                fontsize=tam_et, bbox=caja)


def gestos():
    # gesto de 3 cuadros sin tolerancia (100 ms a 30 fps)
    a = A.afd_gesto("g", 100, None, fps=30)
    pos = {f"q{i}": (i * 1.7, 0) for i in range(4)}
    op = {(f"q{i}", "q0"): {"rad": -(0.32 + 0.06 * i)} for i in range(1, 4)}
    fig, ax = plt.subplots(figsize=(6.0, 2.4))
    _dibujar(ax, pos, a.transiciones, op, lazos={"q0": 90, "q3": 90}, inicial="q0",
             aceptacion=set(a.aceptacion))
    ax.set_xlim(-1.3, 5.8)
    ax.set_ylim(-2.4, 1.3)
    ax.set_aspect("equal")
    ax.axis("off")
    _guardar(fig, "fig_afd_gesto.png")

    # mismo gesto con tolerancia de 1 cuadro
    a = A.afd_gesto("g", 100, None, fps=30, tolerancia_ms=34)
    pos = {"q0": (0, 0)}
    for i in range(1, 4):
        pos[f"q{i}"] = (i * 2.2, 0)
        pos[f"q{i}~1"] = (i * 2.2, -2.0)
    op = {}
    for i in range(1, 4):
        op[(f"q{i}~1", "q0")] = {"rad": [0, -0.08, -0.62, -0.48][i], "t": 0.5}
        op[(f"q{i}", f"q{i}~1")] = {"rad": 0.2}
        op[(f"q{i}~1", f"q{min(i + 1, 3)}")] = {"rad": 0.2 if i == 3 else 0.0, "t": 0.35}
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    _dibujar(ax, pos, a.transiciones, op, lazos={"q0": 90, "q3": 90}, inicial="q0",
             aceptacion=set(a.aceptacion))
    ax.set_xlim(-1.3, 7.4)
    ax.set_ylim(-4.4, 1.3)
    ax.set_aspect("equal")
    ax.axis("off")
    _guardar(fig, "fig_afd_tolerancia.png")


def maquina():
    r = compilar_archivo(os.path.join(os.path.dirname(AQUI), "ejemplos", "conduccion.emo"))
    m = next(a for a in r.automatas["conduccion"] if a.nombre == "monitor")
    trans = []
    for t in m.transiciones:
        g = t.guarda
        if g and "tiempo_en_estado" in g:
            g = "t > 15 s y perclos < umbral"
        elif g and "perclos" in g:
            g = "perclos > umbral"
        trans.append(A.Transicion(t.origen, t.simbolo, t.destino, t.salida, g))
    pos = {"normal": (0, 0), "somnoliento": (5.2, 3.2), "distraido": (5.2, -3.2), "alerta": (10.4, 0)}
    op = {
        ("normal", "somnoliento"): {"rad": -0.18, "t": 0.45},
        ("somnoliento", "normal"): {"rad": -0.18, "t": 0.5},
        ("normal", "distraido"): {"rad": 0.18, "t": 0.5},
        ("distraido", "normal"): {"rad": 0.18, "t": 0.5},
        ("normal", "alerta"): {"rad": -0.08, "t": 0.25},
        ("alerta", "normal"): {"rad": -0.08, "t": 0.25},
        ("somnoliento", "alerta"): {"rad": -0.12, "t": 0.5},
        ("distraido", "alerta"): {"rad": 0.12, "t": 0.5},
        ("somnoliento", "distraido"): {"rad": -0.18, "t": 0.74},
    }
    fig, ax = plt.subplots(figsize=(7.0, 4.8))
    _dibujar(ax, pos, trans, op, lazos={"normal": 180, "somnoliento": 90}, radio=0.8,
             tam_et=7, tam_estado=7.8)
    x, y = pos["normal"]
    ax.add_patch(FancyArrowPatch((x - 0.9, y + 1.6), (x - 0.4, y + 0.66), arrowstyle="-|>",
                                 mutation_scale=9, lw=0.8, color="black"))
    ax.set_xlim(-3.6, 11.4)
    ax.set_ylim(-4.3, 5.0)
    ax.set_aspect("equal")
    ax.axis("off")
    _guardar(fig, "fig_maquina_monitor.png")


if __name__ == "__main__":
    os.makedirs(SALIDA, exist_ok=True)
    arquitectura()
    gestos()
    maquina()
    print("figuras generadas", file=sys.stderr)
