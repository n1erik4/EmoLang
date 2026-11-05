"""Optimizador de cuádruplas. Aplica seis técnicas hasta que ya no hay cambios:

  propagación    una variable con una sola escritura constante se cambia por su valor
  plegado        operaciones entre constantes se calculan al compilar
  desenrollado   un 'repetir' constante de hasta 4 vueltas se cambia por copias del cuerpo
  subexpresiones una operación ya calculada en el mismo bloque se reutiliza
  mirilla        una operación y la asignación que la sigue se unen en una cuádrupla
  código muerto  se quita lo que no afecta al resultado: escrituras que nadie lee,
                 código inalcanzable, y gestos o secuencias que nadie usa

Toda optimización conserva el comportamiento observable: alarmas, registros,
transiciones y eventos (lo comprueban las pruebas comparando ambas versiones).
"""

import copy
from collections import Counter
from dataclasses import dataclass, field

from .intermedio import Constante, Cuadrupla, OPERADORES_PUROS, es_temporal
from .tipos import texto_valor

MAX_DESENROLLADO = 4
EXPRESIONES = OPERADORES_PUROS - {"="}
TECNICAS = ["propagacion", "plegado", "subexpresiones", "muerto", "mirilla", "desenrollado"]


@dataclass
class Informe:
    aplicaciones: Counter = field(default_factory=Counter)
    ejemplos: dict = field(default_factory=dict)       # técnica -> [(antes, después, bloque)]
    antes: dict = field(default_factory=dict)          # bloque -> número de cuádruplas
    despues: dict = field(default_factory=dict)
    gestos_quitados: list = field(default_factory=list)

    def anota(self, tecnica, antes, despues="", bloque=""):
        self.aplicaciones[tecnica] += 1
        self.ejemplos.setdefault(tecnica, [])
        if len(self.ejemplos[tecnica]) < 12:
            self.ejemplos[tecnica].append((str(antes), str(despues), bloque))


def _tipo_de(v):
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "decimal"
    return "string"


def calcular(op, a, b):
    """Valor de una operación pura. Lo comparten el optimizador y la máquina virtual."""
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return a / b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if op == "y":
        return bool(a) and bool(b)
    if op == "o":
        return bool(a) or bool(b)
    if op == "neg":
        return -a
    if op == "no":
        return not a
    if op == "texto":
        return texto_valor(a, b)
    if op == "concat":
        return a + b
    if op == "=":
        return a
    raise ValueError(op)


class Optimizador:
    def __init__(self, prog, conservar_gestos=False):
        self.prog = copy.deepcopy(prog)
        self.conservar_gestos = conservar_gestos
        self.informe = Informe()
        self.n_etq = 0
        self.cambio = False

    def optimizar(self):
        inf = self.informe
        inf.antes = {n: _contar(b) for n, b in self.prog.bloques.items()}
        for _ in range(20):
            self.cambio = False
            self._propagar()
            for nombre in list(self.prog.bloques):
                self._plegar(nombre)
                self._desenrollar(nombre)
                self._subexpresiones(nombre)
                self._mirilla(nombre)
            self._muerto()
            if not self.cambio:
                break
        inf.despues = {n: _contar(b) for n, b in self.prog.bloques.items()}
        return self.prog, inf

    # --- propagación ------------------------------------------------------
    def _propagar(self):
        escrituras = Counter(c.escribe() for b in self.prog.bloques.values() for c in b if c.escribe())
        globales = {}
        # Un parámetro recibe su valor en cada llamada: esa escritura no aparece en las cuádruplas.
        parametros = {p for f in self.prog.funciones.values() for p in f["params"]}
        for b in self.prog.bloques.values():
            for c in b:
                if (c.op == "=" and isinstance(c.a1, Constante) and not es_temporal(c.res)
                        and escrituras[c.res] == 1 and c.res not in parametros):
                    globales[c.res] = c.a1
        for nombre, b in self.prog.bloques.items():
            locales = Counter(c.escribe() for c in b if es_temporal(c.escribe()))
            temporales = {c.res: c.a1 for c in b if c.op == "=" and isinstance(c.a1, Constante)
                          and es_temporal(c.res) and locales[c.res] == 1}
            for c in b:
                for campo in c.lecturas():
                    x = getattr(c, campo)
                    if isinstance(x, str) and x in globales:
                        antes = str(c)
                        setattr(c, campo, globales[x])
                        self.informe.anota("propagacion", antes, c, nombre)
                        self.cambio = True
                    elif isinstance(x, str) and x in temporales:
                        setattr(c, campo, temporales[x])
                        self.cambio = True

    # --- plegado ----------------------------------------------------------
    def _plegar(self, nombre):
        bloque = self.prog.bloques[nombre]
        salida = []
        for c in bloque:
            if c.op == "chk_rep" and isinstance(c.a1, Constante):
                self.cambio = True
                continue
            if c.op == "gotoF" and isinstance(c.a1, Constante):
                self.cambio = True
                self.informe.anota("plegado", c, "salto resuelto", nombre)
                if not c.a1.valor:
                    salida.append(Cuadrupla("goto", res=c.res, linea=c.linea))
                continue
            if c.op in EXPRESIONES and self._constantes(c):
                antes = str(c)
                try:
                    v = calcular(c.op, c.a1.valor, c.a2 if c.op == "texto" else
                                 (c.a2.valor if c.a2 is not None else None))
                except (ZeroDivisionError, TypeError):
                    salida.append(c)      # el error debe ocurrir al ejecutar, con su línea
                    continue
                nueva = Cuadrupla("=", Constante(v, _tipo_de(v)), None, c.res, c.linea)
                self.informe.anota("plegado", antes, nueva, nombre)
                self.cambio = True
                salida.append(nueva)
                continue
            salida.append(c)
        self.prog.bloques[nombre] = salida

    @staticmethod
    def _constantes(c):
        return all(isinstance(getattr(c, f), Constante) for f in c.lecturas())

    # --- desenrollado -----------------------------------------------------
    def _desenrollar(self, nombre):
        bloque = self.prog.bloques[nombre]
        i = 0
        while i < len(bloque):
            c = bloque[i]
            if not (c.op == "=" and isinstance(c.res, str) and c.res.startswith("c")
                    and es_temporal(c.res) and isinstance(c.a1, Constante) and c.a1.valor == 0
                    and i + 3 < len(bloque)):
                i += 1
                continue
            contador = c.res
            etq, cmp_, salto = bloque[i + 1], bloque[i + 2], bloque[i + 3]
            if not (etq.op == "etq" and cmp_.op == "<" and cmp_.a1 == contador
                    and isinstance(cmp_.a2, Constante) and salto.op == "gotoF"):
                i += 1
                continue
            n = cmp_.a2.valor
            fin = next(j for j, q in enumerate(bloque) if q.op == "etq" and q.res == salto.res)
            if not isinstance(n, int) or n > MAX_DESENROLLADO:
                i = fin + 1
                continue
            # bloque[fin-2] y bloque[fin-1] son el incremento y el regreso
            cuerpo = bloque[i + 4:fin - 2]
            copias = []
            for _ in range(max(0, n)):
                copias.extend(self._clonar(cuerpo))
            antes = _contar(bloque[i:fin + 1])
            bloque[i:fin + 1] = copias
            self.informe.anota("desenrollado", f"repetir {n} veces ({antes} cuádruplas con contador)",
                               f"{len(copias)} cuádruplas sin saltos", nombre)
            self.cambio = True
            i += len(copias)

    def _clonar(self, cuerpo):
        """Copia el cuerpo con etiquetas nuevas para no duplicar destinos de salto."""
        mapa = {}
        for q in cuerpo:
            if q.op == "etq":
                self.n_etq += 1
                mapa[q.res] = f"LD{self.n_etq}"
        copia = []
        for q in cuerpo:
            d = copy.copy(q)
            if d.op in ("etq", "goto", "gotoF") and d.res in mapa:
                d.res = mapa[d.res]
            copia.append(d)
        return copia

    # --- subexpresiones comunes -------------------------------------------
    def _subexpresiones(self, nombre):
        bloque = self.prog.bloques[nombre]
        escrituras = Counter(c.escribe() for c in bloque if c.escribe())
        tabla = {}
        reemplazos = {}
        salida = []
        for i, c in enumerate(bloque):
            if c.op == "etq":
                tabla.clear()
                reemplazos.clear()
                salida.append(c)
                continue
            for campo in c.lecturas():
                x = getattr(c, campo)
                if isinstance(x, str) and x in reemplazos:
                    setattr(c, campo, reemplazos[x])
            if c.op in EXPRESIONES:
                clave = (c.op, _clave(c.a1), _clave(c.a2))
                previo = tabla.get(clave)
                if (previo is not None and escrituras[previo] == 1 and es_temporal(c.res)
                        and escrituras[c.res] == 1 and self._solo_lee_antes_de_etiqueta(bloque, i, c.res)):
                    reemplazos[c.res] = previo
                    self.informe.anota("subexpresiones", c, f"se reutiliza {previo}", nombre)
                    self.cambio = True
                    continue
            destino = c.escribe()
            if destino:
                reemplazos.pop(destino, None)
                for k in [k for k, v in tabla.items() if v == destino or destino in k[1:]]:
                    del tabla[k]
            if c.op in EXPRESIONES and es_temporal(c.res) and c.res not in (c.a1, c.a2):
                tabla[(c.op, _clave(c.a1), _clave(c.a2))] = c.res
            salida.append(c)
        self.prog.bloques[nombre] = salida

    @staticmethod
    def _solo_lee_antes_de_etiqueta(bloque, i, t):
        etiqueta = False
        for q in bloque[i + 1:]:
            if q.op == "etq":
                etiqueta = True
            elif etiqueta and t in [getattr(q, f) for f in q.lecturas()]:
                return False
        return True

    # --- mirilla ----------------------------------------------------------
    def _mirilla(self, nombre):
        bloque = self.prog.bloques[nombre]
        # etiquetas sin saltos que lleguen a ellas
        destinos = {c.res for c in bloque if c.op in ("goto", "gotoF")}
        sin_etq = [c for c in bloque if c.op != "etq" or c.res in destinos]
        if len(sin_etq) != len(bloque):
            self.cambio = True
        bloque = sin_etq
        lecturas = Counter(getattr(c, f) for c in bloque for f in c.lecturas()
                           if isinstance(getattr(c, f), str))
        salida = []
        for c in bloque:
            previa = salida[-1] if salida else None
            if (c.op == "=" and previa is not None and es_temporal(c.a1) and previa.escribe() == c.a1
                    and lecturas[c.a1] == 1 and previa.op != "="):
                antes = f"{previa} y {c}"
                previa.res = c.res
                self.informe.anota("mirilla", antes, previa, nombre)
                self.cambio = True
                continue
            if c.op == "etq" and previa is not None and previa.op == "goto" and previa.res == c.res:
                salida.pop()              # salto a la cuádrupla siguiente
                self.informe.anota("mirilla", previa, "se quita", nombre)
                self.cambio = True
            salida.append(c)
        self.prog.bloques[nombre] = salida

    # --- código muerto ----------------------------------------------------
    def _muerto(self):
        for nombre in list(self.prog.bloques):
            self._inalcanzable(nombre)
        self._funciones_sin_uso()
        if not self.conservar_gestos:
            self._eventos_sin_uso()
        self._escrituras_sin_lector()

    def _inalcanzable(self, nombre):
        bloque = self.prog.bloques[nombre]
        salida, muerto = [], False
        destinos = {c.res for c in bloque if c.op in ("goto", "gotoF")}
        for i, c in enumerate(bloque):
            if c.op == "etq" and c.res in destinos:
                muerto = False
            if muerto and i < len(bloque) - 1 and c.op != "etq":
                self.informe.anota("muerto", c, "inalcanzable", nombre)
                self.cambio = True
                continue
            salida.append(c)
            if c.op in ("goto", "ir_a", "ret", "retv"):
                muerto = True
        self.prog.bloques[nombre] = salida

    def _funciones_sin_uso(self):
        prog = self.prog
        por_bloque = {f["bloque"]: n for n, f in prog.funciones.items()}
        vivas, pendientes = set(), [b for b in prog.bloques if b not in por_bloque]
        if "principal" in prog.funciones:
            pendientes.append(prog.funciones["principal"]["bloque"])
        vistos = set(pendientes)
        while pendientes:
            for c in prog.bloques[pendientes.pop()]:
                if c.op == "call" and c.a1 in prog.funciones:
                    vivas.add(c.a1)
                    b = prog.funciones[c.a1]["bloque"]
                    if b not in vistos:
                        vistos.add(b)
                        pendientes.append(b)
        for n in list(prog.funciones):
            if n not in vivas and n != "principal":
                self.informe.anota("muerto", f"funcion {n}", "nadie la llama", prog.funciones[n]["bloque"])
                self.informe.despues.pop(prog.funciones[n]["bloque"], None)
                del prog.bloques[prog.funciones[n]["bloque"]]
                del prog.funciones[n]
                self.cambio = True

    def _eventos_sin_uso(self):
        prog = self.prog
        usados = {c["evento"] for m in prog.maquinas for e in m["estados"].values() for c in e["cuandos"]}
        for s, patron in prog.patrones.items():
            if s in usados:
                usados |= set(patron)
        salida = []
        for c in prog.bloques["gestos"]:
            if c.op in ("afd", "sec") and c.res not in usados:
                self.informe.anota("muerto", c, f"'{c.res}' no tiene quien lo use", "gestos")
                self.informe.gestos_quitados.append(c.res)
                self.cambio = True
                continue
            salida.append(c)
        prog.bloques["gestos"] = salida
        prog.gestos = [g for g in prog.gestos if g in usados]
        prog.secuencias = [s for s in prog.secuencias if s in usados]

    def _escrituras_sin_lector(self):
        """Análisis de vivacidad sobre todo el programa: un valor está vivo si llega a
        una acción, a un salto, a un autómata o a una división que puede fallar."""
        prog = self.prog

        def llave(bloque, x):
            return (bloque, x) if es_temporal(x) else x

        vivos, pendientes = set(), []

        def marcar(bloque, x):
            if isinstance(x, str):
                k = llave(bloque, x)
                if k not in vivos:
                    vivos.add(k)
                    pendientes.append(k)

        escritores = {}
        for nombre, b in prog.bloques.items():
            for c in b:
                d = c.escribe()
                if d and c.op != "call" and not _division_riesgosa(c):
                    escritores.setdefault(llave(nombre, d), []).append((nombre, c))
                elif c.op not in ("etq", "goto", "ret"):
                    for f in c.lecturas():
                        marcar(nombre, getattr(c, f))
        while pendientes:
            for nombre, c in escritores.get(pendientes.pop(), []):
                for f in c.lecturas():
                    marcar(nombre, getattr(c, f))

        for nombre, b in prog.bloques.items():
            salida = []
            for c in b:
                d = c.escribe()
                if (d and c.op != "call" and not _division_riesgosa(c)
                        and llave(nombre, d) not in vivos):
                    self.informe.anota("muerto", c, "su resultado nunca se lee", nombre)
                    self.cambio = True
                    continue
                salida.append(c)
            prog.bloques[nombre] = salida


def _division_riesgosa(c):
    """Quitar estas operaciones escondería un error que debe ocurrir al ejecutar."""
    if c.op == "[]":
        return True
    return c.op == "/" and not (isinstance(c.a2, Constante) and c.a2.valor != 0)


def _clave(x):
    if isinstance(x, Constante):
        return ("k", repr(x.valor))
    return x


def _contar(bloque):
    return sum(1 for c in bloque if c.op != "etq")


def optimizar(programas, conservar_gestos=False):
    """Recibe {dominio: ProgramaIntermedio}; devuelve ({dominio: programa}, {dominio: Informe})."""
    optimizados, informes = {}, {}
    for dominio, prog in programas.items():
        optimizados[dominio], informes[dominio] = Optimizador(prog, conservar_gestos).optimizar()
    return optimizados, informes
