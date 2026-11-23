"""Generación de código intermedio: cuádruplas (operador, arg1, arg2, resultado).

Recorre el AST ya verificado por el analizador semántico. Cada expresión se
traduce con una pila semántica explícita: un operando mete (lugar, tipo) y un
operador saca sus operandos, emite su cuádrupla y mete el temporal resultante.

Los gestos y secuencias conservan su autómata: la cuádrupla (afd, t, -, g) le
entrega al AFD de g el símbolo del cuadro, y (sec, -, -, s) le entrega a la
secuencia los eventos del cuadro. Las cuádruplas calculan condiciones y acciones;
el tiempo lo cuentan los autómatas.

Bloques de un dominio:
    init                 variables del sensor y del dominio (una vez al iniciar)
    gestos               condiciones de los gestos (en cada cuadro)
    E.al_entrar          variables locales y al_entrar del estado E
    E.cuando.EV          cuerpo de un 'cuando EV { ... }'
    E.mientras.N         condición y cuerpo de un 'mientras' (una vez por cuadro)
"""

import re
from dataclasses import dataclass, field

from . import nodos as N
from .tipos import PRIMITIVOS, elemento, es_arreglo, tamano

RE_TEMPORAL = re.compile(r"^[tc]\d+$")
# Operadores sin efectos secundarios: su resultado se puede plegar, reutilizar o quitar.
OPERADORES_PUROS = {"=", "+", "-", "*", "/", "<", "<=", ">", ">=", "==", "!=", "y", "o",
                    "neg", "no", "texto", "concat", "shl"}
# Además de los puros, estos dejan un valor en su resultado.
LECTURAS_MEMORIA = {"[]", "campo", "alloc", "alloc_e"}
MAX_REPETIR = 10_000


def es_temporal(x):
    return isinstance(x, str) and RE_TEMPORAL.match(x) is not None


@dataclass(frozen=True)
class Constante:
    valor: object
    tipo: str

    def __str__(self):
        v = self.valor
        if isinstance(v, bool):
            return "verdadero" if v else "falso"
        if isinstance(v, str):
            return f'"{v}"'
        if isinstance(v, float):
            return f"{v:g}"
        return str(v)


@dataclass
class Cuadrupla:
    op: str
    a1: object = None
    a2: object = None
    res: object = None
    linea: int = 0

    def lecturas(self):
        """Nombres de los campos que leen un valor (y no son nombres de función, tipos, etc.)."""
        if self.op in ("gotoF", "param", "afd", "texto", "neg", "no", "=", "chk_rep", "retv", "campo"):
            return ("a1",)
        if self.op in OPERADORES_PUROS or self.op == "[]":
            return ("a1", "a2")
        if self.op == "[]=":
            return ("a1", "a2", "res")
        if self.op == "campo=":
            return ("a1", "res")
        return ()

    def escribe(self):
        """Nombre que escribe esta cuádrupla, o None."""
        if self.op in OPERADORES_PUROS or self.op in LECTURAS_MEMORIA or (self.op == "call" and self.res is not None):
            return self.res
        return None

    def fila(self):
        return (self.op, _txt(self.a1), _txt(self.a2), _txt(self.res))

    def __str__(self):
        return "(" + ", ".join(self.fila()) + ")"


def _txt(x):
    return "–" if x is None else str(x)


@dataclass
class ProgramaIntermedio:
    dominio: str
    fps: int
    bloques: dict                 # nombre -> list[Cuadrupla] (con etiquetas 'etq')
    gestos: list                  # nombres de gestos, en orden
    secuencias: list              # nombres de secuencias, en orden
    maquinas: list                # tablas de despacho
    patrones: dict = field(default_factory=dict)  # secuencia -> gestos que la forman
    trazas: dict = field(default_factory=dict)   # línea -> pasos de la pila semántica
    funciones: dict = field(default_factory=dict)  # nombre -> {"params": [lugares], "bloque": nombre}
    estructuras: dict = field(default_factory=dict)  # nombre -> {campo: tipo}
    tipos: dict = field(default_factory=dict)  # lugar o (bloque, temporal) -> tipo


class Generador:
    def __init__(self, info, analisis, trazar=False):
        self.info = info
        self.analisis = analisis
        self.funciones = {}
        self.tipos = {}
        self.bloque_actual = None
        self.trazar = trazar
        self.trazas = {}
        self.bloques = {}
        self.cuads = None
        self.pila = []
        self.n_temp = self.n_cont = self.n_etq = self.n_decl = 0
        self.ambitos = [{}]
        self.prefijo = ""
        self.traza_actual = None

    # --- utilidades -------------------------------------------------------
    def _abrir(self, nombre):
        self.cuads = []
        self.bloques[nombre] = self.cuads
        self.bloque_actual = nombre
        self.n_temp = self.n_cont = self.n_etq = 0

    def _cerrar(self):
        self._emitir("ret")

    def _emitir(self, op, a1=None, a2=None, res=None, linea=0):
        c = Cuadrupla(op, a1, a2, res, linea)
        self.cuads.append(c)
        return c

    def _temporal(self, tipo=None):
        self.n_temp += 1
        t = f"t{self.n_temp}"
        self.tipos[(self.bloque_actual, t)] = tipo
        return t

    def _contador(self):
        self.n_cont += 1
        c = f"c{self.n_cont}"
        self.tipos[(self.bloque_actual, c)] = "int"
        return c

    def _resultado(self, t, tipo):
        """Mete un temporal a la pila semántica y registra su tipo."""
        if t is not None:
            self.tipos[(self.bloque_actual, t)] = tipo
        self.pila.append((t, tipo))

    def _etiqueta(self):
        self.n_etq += 1
        return f"L{self.n_etq}"

    def _slot(self, nombre):
        for amb in reversed(self.ambitos):
            if nombre in amb:
                return amb[nombre]
        return _seguro(nombre)     # métrica

    def _anota(self, accion, cuad=None):
        if self.traza_actual is not None:
            self.traza_actual.append({
                "accion": accion,
                "pila": [(str(l), t) for l, t in self.pila],
                "cuadrupla": str(cuad) if cuad else "",
            })

    def _empujar(self, lugar, tipo, accion):
        self.pila.append((lugar, tipo))
        self._anota(accion)

    def _sacar(self):
        return self.pila.pop()

    # --- dominio ----------------------------------------------------------
    def generar(self):
        info = self.info
        dom = info.nodo if info else None
        globales = self.ambitos[0]
        prog = self.analisis.programa

        self._abrir("init")
        for v in prog.variables:
            self._decl(v, globales, _seguro(v.nombre))
        if dom:
            for s in dom.sensores:
                for v in s.variables:
                    self._decl(v, globales, _seguro(v.nombre))
            for v in dom.variables:
                self._decl(v, globales, _seguro(v.nombre))
        self._cerrar()

        self._abrir("gestos")
        for g in (dom.gestos if dom else []):
            self._iniciar_traza(g.linea)
            lugar = self._valor(g.condicion)
            c = self._emitir("afd", lugar, None, g.nombre, g.linea)
            self._anota(f"Reconoce el gesto {g.nombre}: la condición es bool", c)
            self.traza_actual = None
        for s in (dom.secuencias if dom else []):
            self._emitir("sec", None, None, s.nombre, s.linea)
        self._cerrar()

        for f in prog.funciones:
            self._funcion(f)

        varias = dom is not None and len(dom.maquinas) > 1
        maquinas = [self._maquina(m, varias) for m in dom.maquinas] if dom else []
        return ProgramaIntermedio(
            info.nombre if info else PROGRAMA, info.fps if info else 0, self.bloques,
            [g.nombre for g in dom.gestos] if dom else [],
            [s.nombre for s in dom.secuencias] if dom else [],
            maquinas, {s.nombre: [i.nombre for i in s.gestos] for s in dom.secuencias} if dom else {},
            self.trazas, self.funciones, self.analisis.estructuras, self.tipos)

    def _funcion(self, f):
        bloque = f"funcion.{f.nombre}"
        self.prefijo = f.nombre
        locales = {p.nombre: f"{f.nombre}.{p.nombre}" for p in f.parametros}
        for p in f.parametros:
            self.tipos[locales[p.nombre]] = p.tipo_decl
        self.funciones[f.nombre] = {"params": [locales[p.nombre] for p in f.parametros], "bloque": bloque}
        self.ambitos.append(locales)
        self._abrir(bloque)
        self._bloque(f.cuerpo)
        self._cerrar()
        self.ambitos.pop()

    def _decl(self, v, ambito, slot):
        self.tipos[slot] = v.tipo_decl
        if es_arreglo(v.tipo_decl):
            self._emitir("alloc", Constante(tamano(v.tipo_decl), "int"), elemento(v.tipo_decl), slot, v.linea)
            if v.valor is not None:
                for i, e in enumerate(v.valor.elementos):
                    lugar = self._valor(e)
                    self._emitir("[]=", lugar, Constante(i, "int"), slot, v.linea)
            ambito[v.nombre] = slot
            return
        if v.tipo_decl not in PRIMITIVOS:
            self._emitir("alloc_e", v.tipo_decl, None, slot, v.linea)
            ambito[v.nombre] = slot
            return
        lugar = self._valor(v.valor, v.linea)     # el valor se evalúa antes de que exista el nombre
        c = self._emitir("=", lugar, None, slot, v.linea)
        self._anota(f"Reconoce la declaración de {v.nombre}", c)
        ambito[v.nombre] = slot

    # --- máquinas ---------------------------------------------------------
    def _maquina(self, m, varias):
        tabla = {"nombre": m.nombre, "inicial": m.inicial, "estados": {}}
        for e in m.estados:
            self.prefijo = f"{m.nombre}.{e.nombre}" if varias else e.nombre
            locales = {}
            self.ambitos.append(locales)
            ent = None
            if e.variables or e.al_entrar:
                ent = f"{self.prefijo}.al_entrar"
                self._abrir(ent)
                for v in e.variables:
                    self._decl(v, locales, f"{self.prefijo}.{v.nombre}")
                if e.al_entrar:
                    self._bloque(e.al_entrar)
                self._cerrar()

            cuandos = []
            for c in e.cuandos:
                nombre = None
                if c.cuerpo is not None:
                    nombre = f"{self.prefijo}.cuando.{c.evento}"
                    self._abrir(nombre)
                    self._bloque(c.cuerpo)
                    self._cerrar()
                cuandos.append({"evento": c.evento, "destino": c.destino, "bloque": nombre})

            mientras = []
            for i, w in enumerate(e.mientras, 1):
                nombre = f"{self.prefijo}.mientras.{i}"
                self._abrir(nombre)
                fin = self._etiqueta()
                self._emitir("gotoF", self._valor(w.condicion, w.linea), None, fin, w.linea)
                self._bloque(w.cuerpo)
                self._emitir("etq", res=fin)
                self._cerrar()
                mientras.append(nombre)

            tabla["estados"][e.nombre] = {
                "entrar": ent, "cuandos": cuandos, "mientras": mientras,
                "tras": [{"ms": tr.ms, "destino": tr.destino} for tr in e.tras],
            }
            self.ambitos.pop()
        return tabla

    # --- sentencias -------------------------------------------------------
    def _bloque(self, b):
        self.ambitos.append({})
        for s in b.sentencias:
            self._sentencia(s)
        self.ambitos.pop()

    def _sentencia(self, s):
        if isinstance(s, N.DeclVar):
            self.n_decl += 1
            self._decl(s, self.ambitos[-1], f"{self.prefijo}.{s.nombre}@{self.n_decl}")
        elif isinstance(s, N.Asignacion):
            self._iniciar_traza(s.linea)
            self._empujar(self._slot(s.nombre), None, f"Lee {s.nombre} y =; será el destino")
            lugar = self._expr(s.valor)
            self._sacar()
            self._sacar()
            c = self._emitir("=", lugar[0], None, self._slot(s.nombre), s.linea)
            self._anota(f"Lee ; y reconoce la asignación a {s.nombre}", c)
            self.traza_actual = None
        elif isinstance(s, N.AsignacionElem):
            self._asignar_elemento(s)
        elif isinstance(s, N.Mientras):
            self._mientras(s)
        elif isinstance(s, N.Para):
            self._para(s)
        elif isinstance(s, N.Retornar):
            if s.valor is None:
                self._emitir("ret", linea=s.linea)
            else:
                self._emitir("retv", self._valor(s.valor), linea=s.linea)
        elif isinstance(s, N.Si):
            self._si(s)
        elif isinstance(s, N.Repetir):
            self._repetir(s)
        elif isinstance(s, N.IrA):
            self._emitir("ir_a", None, None, s.destino, s.linea)
        elif isinstance(s, N.SentenciaLlamada):
            self._expr(s.llamada)
            self._sacar()

    def _asignar_elemento(self, s):
        d = s.destino
        if isinstance(d, N.Indice):
            self._expr(d.indice)
            self._fijar_antes_de([s.valor])
            i, _ = self._sacar()
            v = self._valor(s.valor)
            self._emitir("[]=", v, i, self._slot(d.base), s.linea)
        else:
            v = self._valor(s.valor)
            self._emitir("campo=", v, f"{d.estructura}.{d.campo}", self._slot(d.base), s.linea)

    def _mientras(self, s):
        inicio, fin = self._etiqueta(), self._etiqueta()
        self._emitir("etq", res=inicio)
        self._emitir("gotoF", self._valor(s.condicion), None, fin, s.linea)
        self._bloque(s.cuerpo)
        self._emitir("goto", res=inicio)
        self._emitir("etq", res=fin)

    def _para(self, s):
        self.n_decl += 1
        var = f"{self.prefijo}.{s.variable}@{self.n_decl}"
        self.tipos[var] = "int"
        self._emitir("=", self._valor(s.inicio), None, var, s.linea)
        tope = self._valor(s.fin)
        if not isinstance(tope, Constante):       # el límite se evalúa una sola vez
            copia = self._temporal("int")
            self._emitir("=", tope, None, copia, s.linea)
            tope = copia
        inicio, fin = self._etiqueta(), self._etiqueta()
        self._emitir("etq", res=inicio)
        t = self._temporal("bool")
        self._emitir("<=", var, tope, t, s.linea)
        self._emitir("gotoF", t, None, fin, s.linea)
        self.ambitos.append({s.variable: var})
        self._bloque(s.cuerpo)
        self.ambitos.pop()
        self._emitir("+", var, Constante(1, "int"), var, s.linea)
        self._emitir("goto", res=inicio)
        self._emitir("etq", res=fin)

    def _si(self, s):
        cond = self._valor(s.condicion, s.linea)
        if s.sino is None:
            fin = self._etiqueta()
            self._emitir("gotoF", cond, None, fin, s.linea)
            self._bloque(s.entonces)
            self._emitir("etq", res=fin)
            return
        otro, fin = self._etiqueta(), self._etiqueta()
        self._emitir("gotoF", cond, None, otro, s.linea)
        self._bloque(s.entonces)
        self._emitir("goto", res=fin)
        self._emitir("etq", res=otro)
        if isinstance(s.sino, N.Bloque):
            self._bloque(s.sino)
        else:
            self._si(s.sino)
        self._emitir("etq", res=fin)

    def _repetir(self, s):
        n = self._valor(s.veces, s.linea)
        if not isinstance(n, Constante):
            copia = self._temporal("int")     # el número de vueltas se evalúa una sola vez
            self._emitir("=", n, None, copia, s.linea)
            n = copia
        if not isinstance(n, Constante) or n.valor > MAX_REPETIR:
            self._emitir("chk_rep", n, None, None, s.linea)
        c = self._contador()
        inicio, fin = self._etiqueta(), self._etiqueta()
        self._emitir("=", Constante(0, "int"), None, c, s.linea)
        self._emitir("etq", res=inicio)
        t = self._temporal("bool")
        self._emitir("<", c, n, t, s.linea)
        self._emitir("gotoF", t, None, fin, s.linea)
        self._bloque(s.cuerpo)
        self._emitir("+", c, Constante(1, "int"), c, s.linea)
        self._emitir("goto", res=inicio)
        self._emitir("etq", res=fin)

    # --- expresiones ------------------------------------------------------
    def _iniciar_traza(self, linea):
        if self.trazar:
            self.traza_actual = []
            self.trazas[linea] = self.traza_actual

    def _valor(self, e, linea=None):
        """Evalúa una expresión y devuelve su lugar (saca el resultado de la pila)."""
        lugar = self._expr(e)
        self._sacar()
        return lugar[0]

    def _expr(self, e):
        if isinstance(e, N.Literal):
            lugar = Constante(e.valor, e.tipo_lit)
            self._empujar(lugar, e.tipo_lit, f"Lee la constante {lugar}")
        elif isinstance(e, N.Identificador):
            self._empujar(self._slot(e.nombre), e.tipo, f"Lee {e.nombre}")
        elif isinstance(e, N.Unaria):
            self._unaria(e)
        elif isinstance(e, N.Binaria):
            if e.op in ("y", "o") and _puede_fallar(e.der):
                self._corto_circuito(e)
            elif e.op == "+" and e.tipo == "string":
                self._concatenar(e)
            else:
                self._binaria(e)
        elif isinstance(e, N.Llamada):
            self._llamada(e)
        elif isinstance(e, N.Indice):
            i = self._valor(e.indice)
            t = self._temporal()
            self._emitir("[]", self._slot(e.base), i, t, e.linea)
            self._resultado(t, e.tipo)
        elif isinstance(e, N.Campo):
            t = self._temporal()
            self._emitir("campo", self._slot(e.base), f"{e.estructura}.{e.campo}", t, e.linea)
            self._resultado(t, e.tipo)
        else:
            raise TypeError(f"expresión no soportada: {type(e).__name__}")
        return self.pila[-1]

    def _unaria(self, e):
        self._expr(e.operando)
        x, _ = self._sacar()
        t = self._temporal()
        c = self._emitir("no" if e.op == "no" else "neg", x, None, t, e.linea)
        self._resultado(t, e.tipo)
        self._anota(f"Reconoce {e.op}: tipo {e.tipo}", c)

    def _fijar_antes_de(self, siguiente):
        """Si lo que sigue llama a una función, esta podría cambiar la variable que ya se
        evaluó: se copia a un temporal para conservar el orden de izquierda a derecha."""
        lugar, tipo = self.pila[-1]
        if isinstance(lugar, str) and not es_temporal(lugar) and any(self._llama(s) for s in siguiente):
            copia = self._temporal(tipo)
            self._emitir("=", lugar, None, copia)
            self.pila[-1] = (copia, tipo)

    def _llama(self, e):
        if isinstance(e, N.Llamada):
            return e.nombre in self.analisis.funciones or any(self._llama(a) for a in e.args)
        if isinstance(e, N.Binaria):
            return self._llama(e.izq) or self._llama(e.der)
        if isinstance(e, N.Unaria):
            return self._llama(e.operando)
        if isinstance(e, N.Indice):
            return self._llama(e.indice)
        return False

    def _binaria(self, e):
        self._expr(e.izq)
        self._fijar_antes_de([e.der])
        self._expr(e.der)
        b, tb = self._sacar()
        a, ta = self._sacar()
        t = self._temporal()
        c = self._emitir(e.op, a, b, t, e.linea)
        self._resultado(t, e.tipo)
        self._anota(f"Reconoce {a} {e.op} {b}: {ta} {e.op} {tb} = {e.tipo}", c)

    def _a_texto(self, lugar, tipo, linea):
        if tipo == "string":
            return lugar
        t = self._temporal("string")
        self._emitir("texto", lugar, tipo, t, linea)
        return t

    def _concatenar(self, e):
        self._expr(e.izq)
        self._fijar_antes_de([e.der])
        self._expr(e.der)
        b, tb = self._sacar()
        a, ta = self._sacar()
        a = self._a_texto(a, ta, e.linea)
        b = self._a_texto(b, tb, e.linea)
        t = self._temporal()
        c = self._emitir("concat", a, b, t, e.linea)
        self._resultado(t, "string")
        self._anota("Reconoce una concatenación: string", c)

    def _corto_circuito(self, e):
        """El lado derecho puede fallar (división): solo se evalúa si hace falta."""
        self._expr(e.izq)
        a, _ = self._sacar()
        r = self._temporal("bool")
        corto, fin = self._etiqueta(), self._etiqueta()
        if e.op == "o":
            n = self._temporal("bool")
            self._emitir("no", a, None, n, e.linea)
            a = n
        self._emitir("gotoF", a, None, corto, e.linea)
        self._expr(e.der)
        b, _ = self._sacar()
        self._emitir("=", b, None, r, e.linea)
        self._emitir("goto", res=fin)
        self._emitir("etq", res=corto)
        self._emitir("=", Constante(e.op == "o", "bool"), None, r, e.linea)
        self._emitir("etq", res=fin)
        self._resultado(r, "bool")

    def _llamada(self, e):
        for i, a in enumerate(e.args):
            self._expr(a)
            self._fijar_antes_de(e.args[i + 1:])
        valores = [self._sacar() for _ in e.args][::-1]
        variadica = e.nombre == "mostrar"
        lugares = []
        for lugar, tipo in valores:
            lugares.append(self._a_texto(lugar, tipo, e.linea) if variadica else lugar)
        for lugar in lugares:
            self._emitir("param", lugar, None, None, e.linea)
        devuelve = e.tipo != "void"
        t = self._temporal() if devuelve else None
        self._emitir("call", e.nombre, len(lugares), t, e.linea)
        self._resultado(t, e.tipo)


def _seguro(nombre):
    """Una variable llamada como un temporal no debe confundirse con él."""
    return f"global.{nombre}" if RE_TEMPORAL.match(nombre) else nombre


PROGRAMA = "programa"     # entrada del programa con 'funcion principal' (sin dominio)


def _puede_fallar(e):
    if isinstance(e, N.Binaria):
        return e.op == "/" or _puede_fallar(e.izq) or _puede_fallar(e.der)
    if isinstance(e, N.Unaria):
        return _puede_fallar(e.operando)
    if isinstance(e, N.Llamada):
        return True               # una función del usuario puede tener efectos o fallar
    if isinstance(e, N.Indice):
        return True               # un índice puede salirse del arreglo
    return False


def generar(analisis, trazar=False):
    """Devuelve {dominio: ProgramaIntermedio}."""
    programas = {nombre: Generador(info, analisis, trazar).generar() for nombre, info in analisis.dominios.items()}
    if "principal" in analisis.funciones:
        programas[PROGRAMA] = Generador(None, analisis, trazar).generar()
    return programas


def resolver(cuadruplas):
    """Quita las etiquetas y deja los saltos con el número de cuádrupla (desde 1)."""
    posiciones, numero = {}, 1
    for c in cuadruplas:
        if c.op == "etq":
            posiciones[c.res] = numero
        else:
            numero += 1
    salida = []
    for c in cuadruplas:
        if c.op == "etq":
            continue
        res = posiciones[c.res] if c.op in ("goto", "gotoF") else c.res
        salida.append(Cuadrupla(c.op, c.a1, c.a2, res, c.linea))
    return salida
