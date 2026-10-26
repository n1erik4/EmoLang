"""Generador de autómatas finitos (objetivo específico 5).

Cada construcción de EmoLang se traduce a un autómata:

  gesto      AFD sobre el alfabeto {1, 0} (1 = la condición se cumple en el cuadro).
             El estado q_i significa "la condición lleva i cuadros consecutivos".
             La duración se discretiza en cuadros: N = ceil(durante / periodo).
             Es una máquina de Mealy: ciertas transiciones emiten el evento del gesto.
  secuencia  AFD de reconocimiento de patrón (construcción KMP) sobre el alfabeto
             de eventos de los gestos que la componen, con temporizador de ventana.
  maquina    Autómata cuyos estados son los estados declarados y cuyo alfabeto son
             los eventos de gestos/secuencias; λ marca transiciones espontáneas
             (desde al_entrar o mientras).

El motor de ejecución (runtime.py) evalúa directamente estas tablas.
"""

import json
import math
from dataclasses import dataclass, field

from . import nodos as N
from .errores import Reporte
from .semantico import evaluar_constante
from .validaciones import _buscador

LAMBDA = "λ"


@dataclass
class Transicion:
    origen: str
    simbolo: str
    destino: str
    salida: str = None      # evento emitido (máquina de Mealy)
    guarda: str = None      # condición textual (máquinas de estado)


@dataclass
class Automata:
    nombre: str
    clase: str              # gesto | secuencia | maquina
    estados: list
    alfabeto: list
    inicial: str
    aceptacion: list
    transiciones: list
    descripcion: dict = field(default_factory=dict)

    # tabla δ indexada para el motor
    def delta(self):
        return {(t.origen, t.simbolo): t for t in self.transiciones}

    def a_dict(self):
        return {
            "nombre": self.nombre, "clase": self.clase, "estados": self.estados,
            "alfabeto": self.alfabeto, "inicial": self.inicial, "aceptacion": self.aceptacion,
            "transiciones": [t.__dict__ for t in self.transiciones],
            "descripcion": self.descripcion,
        }


# ------------------------------------------------------------------ construcción
def afd_gesto(nombre, min_ms, max_ms, fps, condicion_txt="", tolerancia_ms=0.0):
    """Estados: q_i = la condición se ha cumplido en i cuadros; q_i~g = además lleva
    g cuadros seguidos sin cumplirse (interrupción tolerada, g <= K). Con K = 0 es
    la cadena simple de cuadros consecutivos."""
    periodo = 1000.0 / fps
    n = max(1, math.ceil(min_ms / periodo - 1e-9))
    m = None if max_ms is None else max(n, math.floor(max_ms / periodo + 1e-9))
    k = max(0, round((tolerancia_ms or 0.0) / periodo))
    tope = n if m is None else m
    hueco = lambda base, g: f"{base}~{g}"

    estados = ["q0"]
    for i in range(1, tope + 1):
        estados += [f"q{i}"] + [hueco(f"q{i}", g) for g in range(1, k + 1)]
    if m is not None:
        estados += ["qX"] + [hueco("qX", g) for g in range(1, k + 1)]

    def valido(i):
        return m is not None and n <= i <= m

    trans = [Transicion("q0", "0", "q0")]
    for i in range(0, tope + 1):
        origenes = [f"q{i}"] + ([hueco(f"q{i}", g) for g in range(1, k + 1)] if i > 0 else [])
        for q in origenes:
            # con 1: se acumula un cuadro más (la interrupción se perdona)
            if m is None:
                trans.append(Transicion(q, "1", f"q{min(i + 1, n)}", nombre if i == n - 1 else None))
            else:
                trans.append(Transicion(q, "1", f"q{i + 1}" if i < m else "qX"))
        if i == 0:
            continue
        # con 0: se abre o alarga la interrupción; al exceder K termina el gesto
        for g in range(0, k + 1):
            q = f"q{i}" if g == 0 else hueco(f"q{i}", g)
            if g < k:
                trans.append(Transicion(q, "0", hueco(f"q{i}", g + 1)))
            else:
                trans.append(Transicion(q, "0", "q0", nombre if valido(i) else None))
    if m is not None:
        for g in range(0, k + 1):
            q = "qX" if g == 0 else hueco("qX", g)
            trans.append(Transicion(q, "1", "qX"))
            trans.append(Transicion(q, "0", hueco("qX", g + 1) if g < k else "q0"))

    finales = [n] if m is None else range(n, m + 1)
    aceptacion = [q for i in finales for q in [f"q{i}"] + [hueco(f"q{i}", g) for g in range(1, k + 1)]]
    modo = ("al alcanzar la duración mínima" if m is None
            else "al liberarse dentro del intervalo [mínimo, máximo]")
    return Automata(nombre, "gesto", estados, ["1", "0"], "q0", aceptacion, trans, {
        "condicion": condicion_txt, "durante_ms": min_ms, "hasta_ms": max_ms, "fps": fps,
        "tolerancia_ms": tolerancia_ms or 0.0, "cuadros_tolerados": k,
        "cuadros_minimos": n, "cuadros_maximos": m, "emision": modo,
    })


def afd_secuencia(nombre, patron, ventana_ms):
    """AFD de Knuth-Morris-Pratt para reconocer `patron` en el flujo de eventos."""
    alfabeto = list(dict.fromkeys(patron))
    k = len(patron)
    estados = [f"s{i}" for i in range(k + 1)]
    trans = []
    # dfa[j][c] = siguiente estado
    dfa = [{c: 0 for c in alfabeto} for _ in range(k + 1)]
    dfa[0][patron[0]] = 1
    x = 0
    for j in range(1, k + 1):
        for c in alfabeto:
            dfa[j][c] = dfa[x][c]
        if j < k:
            dfa[j][patron[j]] = j + 1
            x = dfa[x][patron[j]]
    for j in range(k + 1):
        for c in alfabeto:
            d = dfa[j][c]
            trans.append(Transicion(f"s{j}", c, f"s{d}", nombre if d == k else None))
    return Automata(nombre, "secuencia", estados, alfabeto, "s0", [f"s{k}"], trans, {
        "patron": patron, "ventana_ms": ventana_ms,
        "nota": "si transcurre más que la ventana desde el primer evento, vuelve a s0",
    })


def afd_maquina(m: N.Maquina):
    trans = []
    for e in m.estados:
        for c in e.cuandos:
            if c.destino:
                trans.append(Transicion(e.nombre, c.evento, c.destino))
            if c.cuerpo is not None:
                saltos = list(_ir_a_con_guardas(c.cuerpo))
                for destino, guarda in saltos:
                    trans.append(Transicion(e.nombre, c.evento, destino, guarda=guarda))
                if not any(g is None for _, g in saltos) and c.cuerpo.sentencias:
                    # el evento ejecuta acciones y (al menos en algún caso) permanece en el estado
                    trans.append(Transicion(e.nombre, c.evento, e.nombre,
                                            guarda="otro caso" if saltos else None, salida="acciones"))
        for destino, guarda in _ir_a_con_guardas(e.al_entrar):
            trans.append(Transicion(e.nombre, LAMBDA, destino, guarda=guarda))
        for w in e.mientras:
            g = texto_expr(w.condicion)
            for destino, guarda in _ir_a_con_guardas(w.cuerpo):
                trans.append(Transicion(e.nombre, LAMBDA, destino,
                                        guarda=f"{g} y {guarda}" if guarda else g))
    alfabeto = list(dict.fromkeys(t.simbolo for t in trans))
    estados = [e.nombre for e in m.estados]
    sin_salida = [e for e in estados if not any(t.origen == e and t.destino != e for t in trans)]
    return Automata(m.nombre, "maquina", estados, alfabeto, m.inicial, sin_salida, trans, {
        "nota": "los estados de aceptación son los estados finales (sin transiciones de salida)",
    })


def _ir_a_con_guardas(nodo, guardas=()):
    if nodo is None:
        return
    if isinstance(nodo, N.Bloque):
        for s in nodo.sentencias:
            yield from _ir_a_con_guardas(s, guardas)
    elif isinstance(nodo, N.IrA):
        yield nodo.destino, " y ".join(guardas) or None
    elif isinstance(nodo, N.Si):
        c = texto_expr(nodo.condicion)
        yield from _ir_a_con_guardas(nodo.entonces, guardas + (c,))
        yield from _ir_a_con_guardas(nodo.sino, guardas + (f"no ({c})",))
    elif isinstance(nodo, N.Repetir):
        yield from _ir_a_con_guardas(nodo.cuerpo, guardas)


def generar(analisis, reporte: Reporte | None = None):
    """Devuelve {dominio: [Automata, ...]}."""
    reporte = reporte or Reporte()
    resultado = {}
    for info in analisis.dominios.values():
        buscar = _buscador(info.ambito)
        lista = []
        for g in info.gestos.values():
            dmin = evaluar_constante(g.minimo, buscar)
            dmax = evaluar_constante(g.maximo, buscar) if g.maximo else None
            tol = evaluar_constante(g.tolerancia, buscar) if g.tolerancia else 0.0
            if (not isinstance(dmin, (int, float)) or (g.maximo and not isinstance(dmax, (int, float)))
                    or not isinstance(tol, (int, float))):
                reporte.error("generacion", f"la duración del gesto '{g.nombre}' debe ser constante "
                              "para construir su autómata", g.linea, g.columna)
                continue
            lista.append(afd_gesto(g.nombre, float(dmin), None if dmax is None else float(dmax),
                                   info.fps, texto_expr(g.condicion), float(tol)))
        for s in info.secuencias.values():
            ventana = evaluar_constante(s.ventana, buscar) if s.ventana else None
            lista.append(afd_secuencia(s.nombre, [i.nombre for i in s.gestos], ventana))
        for m in info.maquinas.values():
            lista.append(afd_maquina(m))
        resultado[info.nombre] = lista
    return resultado, reporte


# ------------------------------------------------------------------ texto de expresiones
PRECEDENCIA = {"o": 1, "y": 2, "<": 4, "<=": 4, ">": 4, ">=": 4, "==": 4, "!=": 4,
               "+": 5, "-": 5, "*": 6, "/": 6}


def texto_expr(e, prec=0):
    if e is None:
        return ""
    if isinstance(e, N.Literal):
        if e.tipo_lit == "duracion":
            v = e.valor
            return f"{v / 1000:g} s" if v >= 1000 and v % 1000 == 0 else f"{v:g} ms"
        if e.tipo_lit == "proporcion":
            return f"{e.valor * 100:g}%"
        if e.tipo_lit == "bool":
            return "verdadero" if e.valor else "falso"
        if e.tipo_lit == "string":
            return json.dumps(e.valor, ensure_ascii=False)
        return str(e.valor)
    if isinstance(e, N.Identificador):
        return e.nombre
    if isinstance(e, N.Unaria):
        if e.op == "no":
            return f"no {texto_expr(e.operando, 3)}"
        return f"-{texto_expr(e.operando, 7)}"
    if isinstance(e, N.Binaria):
        p = PRECEDENCIA[e.op]
        t = f"{texto_expr(e.izq, p)} {e.op} {texto_expr(e.der, p + 1)}"
        return f"({t})" if p < prec else t
    if isinstance(e, N.Llamada):
        return f"{e.nombre}({', '.join(texto_expr(a) for a in e.args)})"
    return "?"


# ------------------------------------------------------------------ representaciones
def tabla_texto(a: Automata):
    """Tabla de transiciones en texto plano (→ inicial, * aceptación, /x salida)."""
    celdas = {}
    for t in a.transiciones:
        txt = t.destino
        if t.guarda:
            txt += f" [{t.guarda}]"
        if t.salida:
            txt += f" / {t.salida}"
        celdas.setdefault((t.origen, t.simbolo), []).append(txt)
    cab = ["δ"] + a.alfabeto
    filas = []
    for q in a.estados:
        marca = ("→" if q == a.inicial else " ") + ("*" if q in a.aceptacion else " ")
        filas.append([f"{marca}{q}"] + [" | ".join(celdas.get((q, s), ["—"])) for s in a.alfabeto])
    anchos = [max(len(str(f[i])) for f in [cab] + filas) for i in range(len(cab))]
    linea = "+" + "+".join("-" * (w + 2) for w in anchos) + "+"
    fmt = lambda f: "| " + " | ".join(str(c).ljust(w) for c, w in zip(f, anchos)) + " |"
    return "\n".join([linea, fmt(cab), linea] + [fmt(f) for f in filas] + [linea])


def tabla_markdown(a: Automata):
    celdas = {}
    for t in a.transiciones:
        txt = t.destino
        if t.guarda:
            txt += f" [{t.guarda}]"
        if t.salida:
            txt += f" / **{t.salida}**"
        celdas.setdefault((t.origen, t.simbolo), []).append(txt.replace("|", "\\|"))
    out = ["| δ | " + " | ".join(f"`{s}`" for s in a.alfabeto) + " |",
           "|---" * (len(a.alfabeto) + 1) + "|"]
    for q in a.estados:
        marca = ("→ " if q == a.inicial else "") + ("*" if q in a.aceptacion else "")
        out.append(f"| {marca}{q} | " + " | ".join("<br>".join(celdas.get((q, s), ["—"]))
                                                   for s in a.alfabeto) + " |")
    return "\n".join(out)


def _comprimir(a: Automata, max_cadena=6):
    """Para diagramas: colapsa la cadena q_i --1--> q_{i+1} de los gestos largos y
    agrupa los estados de interrupción q_i~1..q_i~K de cada i en un solo nodo.
    Devuelve (estados, transiciones, aceptacion) del diagrama."""
    if a.clase != "gesto":
        return a.estados, a.transiciones, set(a.aceptacion)
    d = a.descripcion
    n, m, k = d["cuadros_minimos"], d["cuadros_maximos"], d.get("cuadros_tolerados", 0)
    tope = n if m is None else m
    conservar = {0, 1, 2, tope - 1, tope}
    if m is not None:
        conservar |= {n - 1, n}
    ocultos = sorted(i for i in range(tope + 1) if i not in conservar)
    if len(ocultos) < 2:
        ocultos = []

    grupo = {}
    actual = []
    for i in ocultos + [None]:
        if actual and (i is None or i != actual[-1] + 1):
            nombre = f"q{actual[0]}…q{actual[-1]}"
            for j in actual:
                grupo[j] = nombre
            actual = []
        if i is not None:
            actual.append(i)

    sufijo = "~1" if k == 1 else f"~1…{k}"

    def alias(q):
        base, _, g = q.partition("~")
        if base != "qX" and int(base[1:]) in grupo:
            return grupo[int(base[1:])]
        return base + sufijo if g else base

    estados = list(dict.fromkeys(alias(q) for q in a.estados))
    aceptacion = {alias(q) for q in a.aceptacion}
    trans, vistos = [], set()
    for t in a.transiciones:
        o, dst = alias(t.origen), alias(t.destino)
        colapsado = o == dst and ("…" in o or "~" in o)
        simbolo = t.simbolo + ("⁺" if colapsado else "")
        clave = (o, simbolo, dst, t.salida)
        if clave in vistos:
            continue
        vistos.add(clave)
        trans.append(Transicion(o, simbolo, dst, t.salida, t.guarda))
    return estados, trans, aceptacion


def a_dot(a: Automata):
    estados, trans, acept = _comprimir(a)
    lineas = [f'digraph "{a.nombre}" {{', "  rankdir=LR;", '  node [shape=circle, fontname="Helvetica"];',
              '  edge [fontname="Helvetica", fontsize=10];', '  __inicio [shape=point];']
    for q in estados:
        forma = "doublecircle" if q in acept else ("box" if "…" in q or "~" in q else "circle")
        lineas.append(f'  "{q}" [shape={forma}];')
    lineas.append(f'  __inicio -> "{a.inicial}";')
    etiquetas = {}
    for t in trans:
        et = t.simbolo
        if t.guarda:
            et += f" [{t.guarda}]"
        if t.salida:
            et += f" / {t.salida}"
        etiquetas.setdefault((t.origen, t.destino), []).append(et)
    for (o, d), ets in etiquetas.items():
        lab = "\\n".join(ets).replace('"', '\\"')
        lineas.append(f'  "{o}" -> "{d}" [label="{lab}"];')
    lineas.append("}")
    return "\n".join(lineas)


def a_mermaid(a: Automata):
    estados, trans, acept = _comprimir(a)
    ids = {q: f"S{i}" for i, q in enumerate(estados)}
    lineas = ["stateDiagram-v2", "  direction LR"]
    for q in estados:
        lineas.append(f'  state "{q}" as {ids[q]}')
    lineas.append(f"  [*] --> {ids[a.inicial]}")
    etiquetas = {}
    for t in trans:
        et = t.simbolo
        if t.guarda:
            et += f" [{t.guarda}]"
        if t.salida:
            et += f" / {t.salida}"
        etiquetas.setdefault((t.origen, t.destino), []).append(et)
    for (o, d), ets in etiquetas.items():
        lab = ", ".join(ets).replace(":", "∶").replace('"', "'")
        lineas.append(f"  {ids[o]} --> {ids[d]} : {lab}")
    for q in sorted(acept):
        if q in ids:
            lineas.append(f"  {ids[q]} --> [*]")
    return "\n".join(lineas)
