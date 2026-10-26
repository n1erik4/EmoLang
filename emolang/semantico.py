"""Analizador semántico: tabla de símbolos, ámbitos y verificación de tipos.

Ámbitos (de exterior a interior):
    global      métricas del sensor y funciones predefinidas
    dominio     variables del dominio y de sus sensores, gestos, secuencias, máquinas
    maquina     estados de la máquina
    estado      variables locales del estado (se reinician al entrar al estado)
    bloque      variables declaradas dentro de un bloque { }
"""

from dataclasses import dataclass, field

from . import nodos as N
from .errores import Reporte
from .metricas import METRICAS
from .tipos import asignable, tipo_binario, tipo_unario, es_numerico

FASE = "semantico"


@dataclass
class Simbolo:
    nombre: str
    categoria: str          # metrica | funcion | variable | gesto | secuencia | maquina | estado
    tipo: str
    ambito: str
    linea: int = 0
    mutable: bool = False
    valor: object = None    # valor inicial si es constante en compilación
    nodo: object = None


@dataclass
class Funcion:
    nombre: str
    params: list            # lista de tipos; "*" = cualquier tipo; None = variádica de cualquier tipo
    retorno: str
    descripcion: str


FUNCIONES = {f.nombre: f for f in [
    Funcion("alarma", ["string"], "void", "Activa la alarma sonora/visual con un mensaje"),
    Funcion("detener_alarma", [], "void", "Apaga la alarma"),
    Funcion("registrar", ["string"], "void", "Agrega un evento a la bitácora (CSV)"),
    Funcion("mostrar", None, "void", "Imprime valores en la consola/overlay"),
    Funcion("contar_repeticion", [], "void", "Registra una repetición del ejercicio y su simetría"),
    Funcion("repeticiones", [], "int", "Número de repeticiones contadas"),
    Funcion("tiempo_en_estado", [], "duracion", "Tiempo transcurrido desde que se entró al estado"),
    Funcion("abs", ["num"], "num", "Valor absoluto"),
    Funcion("a_porcentaje", ["decimal"], "decimal", "Convierte 0.4 -> 40.0"),
    Funcion("a_proporcion", ["decimal"], "proporcion", "Convierte 40 -> 0.4 (40%)"),
    Funcion("a_ms", ["duracion"], "decimal", "Duración expresada en milisegundos"),
    Funcion("a_s", ["duracion"], "decimal", "Duración expresada en segundos"),
]}


class Ambito:
    def __init__(self, nombre, padre=None):
        self.nombre = nombre
        self.padre = padre
        self.simbolos = {}

    def buscar(self, nombre):
        a = self
        while a:
            if nombre in a.simbolos:
                return a.simbolos[nombre]
            a = a.padre
        return None


@dataclass
class InfoDominio:
    nombre: str
    nodo: N.Dominio
    ambito: Ambito
    fps: int = 30
    gestos: dict = field(default_factory=dict)
    secuencias: dict = field(default_factory=dict)
    maquinas: dict = field(default_factory=dict)
    usados: set = field(default_factory=set)


@dataclass
class Analisis:
    programa: N.Programa
    dominios: dict
    tabla: list             # todos los símbolos, en orden de declaración


class Semantico:
    def __init__(self, reporte: Reporte | None = None):
        self.reporte = reporte or Reporte()
        self.tabla = []
        self.global_ = Ambito("global")
        for m in METRICAS.values():
            self._definir(self.global_, Simbolo(m.nombre, "metrica", m.tipo, "global"))
        for f in FUNCIONES.values():
            self._definir(self.global_, Simbolo(f.nombre, "funcion", f.retorno, "global"))
        self.maquina_actual = None
        self.en_gesto = False

    # --- utilidades -------------------------------------------------------
    def _error(self, msg, nodo):
        self.reporte.error(FASE, msg, nodo.linea, nodo.columna)

    def _adv(self, msg, nodo):
        self.reporte.advertencia(FASE, msg, nodo.linea, nodo.columna)

    def _definir(self, ambito, simbolo, nodo=None):
        previo = ambito.buscar(simbolo.nombre)
        if simbolo.nombre in ambito.simbolos:
            self._error(f"'{simbolo.nombre}' ya fue declarado en este ámbito "
                        f"(línea {previo.linea})", nodo)
            return False
        if previo and previo.categoria in ("metrica", "funcion"):
            self._error(f"'{simbolo.nombre}' es un nombre reservado del sensor/funciones y "
                        "no puede redeclararse", nodo)
            return False
        if previo and nodo is not None:
            self._adv(f"'{simbolo.nombre}' oculta una declaración del ámbito '{previo.ambito}'", nodo)
        ambito.simbolos[simbolo.nombre] = simbolo
        if ambito is not self.global_:
            self.tabla.append(simbolo)
        return True

    # --- programa ---------------------------------------------------------
    def analizar(self, programa: N.Programa) -> Analisis:
        dominios = {}
        for dom in programa.dominios:
            if dom.nombre in dominios:
                self._error(f"dominio '{dom.nombre}' duplicado", dom)
                continue
            dominios[dom.nombre] = self._dominio(dom)
        return Analisis(programa, dominios, self.tabla)

    def _dominio(self, dom: N.Dominio):
        amb = Ambito(f"dominio {dom.nombre}", self.global_)
        info = InfoDominio(dom.nombre, dom, amb)
        self.info = info

        for sensor in dom.sensores:
            for v in sensor.variables:
                self._decl_var(v, amb, etiqueta=f"sensor {sensor.nombre}")
                if v.nombre == "fps":
                    fps = amb.simbolos.get("fps")
                    if fps and isinstance(fps.valor, (int, float)) and fps.tipo == "int":
                        if fps.valor <= 0 or fps.valor > 240:
                            self._error("fps debe estar entre 1 y 240", v)
                        else:
                            info.fps = int(fps.valor)
                    else:
                        self._error("fps debe ser una constante int", v)

        for v in dom.variables:
            self._decl_var(v, amb)

        # Se declaran primero todos los nombres para permitir referencias adelantadas
        for g in dom.gestos:
            if self._definir(amb, Simbolo(g.nombre, "gesto", "gesto", amb.nombre, g.linea, nodo=g), g):
                info.gestos[g.nombre] = g
        for s in dom.secuencias:
            if self._definir(amb, Simbolo(s.nombre, "secuencia", "secuencia", amb.nombre, s.linea, nodo=s), s):
                info.secuencias[s.nombre] = s
        for m in dom.maquinas:
            if self._definir(amb, Simbolo(m.nombre, "maquina", "maquina", amb.nombre, m.linea, nodo=m), m):
                info.maquinas[m.nombre] = m

        for g in dom.gestos:
            self._gesto(g, amb)
        for s in dom.secuencias:
            self._secuencia(s, amb)
        for m in dom.maquinas:
            self._maquina(m, amb)
        return info

    def _decl_var(self, v: N.DeclVar, amb: Ambito, etiqueta=None):
        if v.tipo_decl in ("gesto", "secuencia"):
            self._error(f"los {v.tipo_decl}s se declaran con la palabra '{v.tipo_decl}', no con 'var'", v)
            return
        t = self._expr(v.valor, amb)
        if not asignable(v.tipo_decl, t):
            self._error(f"no se puede asignar {t} a la variable '{v.nombre}' de tipo {v.tipo_decl}", v)
        valor = self._constante(v.valor, amb)
        self._verificar_rango(v.tipo_decl, valor, v)
        self._definir(amb, Simbolo(v.nombre, "variable", v.tipo_decl, etiqueta or amb.nombre,
                                   v.linea, mutable=True, valor=valor, nodo=v), v)

    def _verificar_rango(self, tipo, valor, nodo):
        if not isinstance(valor, (int, float)) or isinstance(valor, bool):
            return
        if tipo == "proporcion" and not (0.0 <= valor <= 1.0):
            self._error(f"umbral fuera de rango: una proporcion debe estar entre 0 y 1 "
                        f"(0% y 100%), se obtuvo {valor:g}", nodo)
        if tipo == "duracion" and valor < 0:
            self._error("una duración no puede ser negativa", nodo)

    # --- gestos y secuencias ----------------------------------------------
    def _gesto(self, g: N.Gesto, amb: Ambito):
        self.en_gesto = True
        t = self._expr(g.condicion, amb)
        self.en_gesto = False
        if t not in (None, "bool"):
            self._error(f"la condición del gesto '{g.nombre}' debe ser bool, no {t}", g.condicion)
        for nombre_campo, expr in (("durante", g.minimo), ("hasta", g.maximo),
                                   ("tolerando", g.tolerancia)):
            if expr is None:
                continue
            te = self._expr(expr, amb)
            if te not in (None, "duracion"):
                self._error(f"'{nombre_campo}' requiere una duración con unidad (ms o s), "
                            f"se recibió {te}", expr)
            self._verificar_rango("duracion", self._constante(expr, amb), expr)
        if not any(n in METRICAS for n in _identificadores(g.condicion)):
            self._adv(f"el gesto '{g.nombre}' no depende de ninguna métrica del sensor", g)

    def _secuencia(self, s: N.Secuencia, amb: Ambito):
        for ident in s.gestos:
            sim = amb.buscar(ident.nombre)
            if sim is None:
                self._error(f"gesto '{ident.nombre}' no declarado", ident)
            elif sim.categoria != "gesto":
                self._error(f"'{ident.nombre}' no es un gesto (es {sim.categoria})", ident)
            else:
                self.info.usados.add(ident.nombre)
        if len(s.gestos) < 2:
            self._adv(f"la secuencia '{s.nombre}' tiene un solo gesto; use el gesto directamente", s)
        if s.ventana is not None:
            t = self._expr(s.ventana, amb)
            if t not in (None, "duracion"):
                self._error(f"la ventana de la secuencia debe ser duracion, no {t}", s.ventana)
            self._verificar_rango("duracion", self._constante(s.ventana, amb), s.ventana)

    # --- máquinas de estado -----------------------------------------------
    def _maquina(self, m: N.Maquina, amb_dom: Ambito):
        amb = Ambito(f"maquina {m.nombre}", amb_dom)
        self.maquina_actual = m
        for e in m.estados:
            self._definir(amb, Simbolo(e.nombre, "estado", "estado", amb.nombre, e.linea, nodo=e), e)
        if m.inicial not in amb.simbolos:
            self._error(f"el estado inicial '{m.inicial}' no existe en la máquina '{m.nombre}'", m)
        for e in m.estados:
            self._estado(e, amb)
        self.maquina_actual = None

    def _estado(self, e: N.Estado, amb_maq: Ambito):
        amb = Ambito(f"estado {e.nombre}", amb_maq)
        for v in e.variables:
            self._decl_var(v, amb)
        if e.al_entrar:
            self._bloque(e.al_entrar, amb)
        for c in e.cuandos:
            sim = amb.buscar(c.evento)
            if sim is None:
                self._error(f"evento '{c.evento}' no declarado", c)
            elif sim.categoria not in ("gesto", "secuencia"):
                self._error(f"'cuando' requiere un gesto o secuencia; '{c.evento}' es {sim.categoria}", c)
            else:
                self.info.usados.add(c.evento)
            if c.destino is not None:
                self._destino(c.destino, c)
            if c.cuerpo is not None:
                self._bloque(c.cuerpo, amb)
        manejados = {c.evento for c in e.cuandos}
        for ident in e.ignorados:
            sim = amb.buscar(ident.nombre)
            if sim is None:
                self._error(f"evento '{ident.nombre}' no declarado", ident)
            elif sim.categoria not in ("gesto", "secuencia"):
                self._error(f"'ignorar' requiere gestos o secuencias; '{ident.nombre}' es "
                            f"{sim.categoria}", ident)
            elif ident.nombre in manejados:
                self._error(f"el estado '{e.nombre}' ignora '{ident.nombre}' pero también tiene "
                            f"'cuando {ident.nombre}'", ident)
        for w in e.mientras:
            t = self._expr(w.condicion, amb)
            if t not in (None, "bool"):
                self._error(f"la condición de 'mientras' debe ser bool, no {t}", w.condicion)
            self._bloque(w.cuerpo, amb)

    def _destino(self, nombre, nodo):
        m = self.maquina_actual
        if m is None:
            self._error("'ir_a' solo puede usarse dentro de una máquina de estados", nodo)
        elif nombre not in {e.nombre for e in m.estados}:
            self._error(f"el estado destino '{nombre}' no existe en la máquina '{m.nombre}'", nodo)

    # --- sentencias -------------------------------------------------------
    def _bloque(self, b: N.Bloque, padre: Ambito):
        amb = Ambito("bloque", padre)
        for s in b.sentencias:
            self._sentencia(s, amb)

    def _sentencia(self, s, amb):
        if isinstance(s, N.DeclVar):
            self._decl_var(s, amb, etiqueta=f"{_ambito_nombrado(amb)} (bloque)")
        elif isinstance(s, N.Asignacion):
            sim = amb.buscar(s.nombre)
            t = self._expr(s.valor, amb)
            if sim is None:
                self._error(f"variable '{s.nombre}' no declarada", s)
            elif not sim.mutable:
                self._error(f"'{s.nombre}' es {sim.categoria} y no se puede asignar", s)
            elif not asignable(sim.tipo, t):
                self._error(f"no se puede asignar {t} a '{s.nombre}' de tipo {sim.tipo}", s)
            else:
                self._verificar_rango(sim.tipo, self._constante(s.valor, amb), s)
        elif isinstance(s, N.Si):
            t = self._expr(s.condicion, amb)
            if t not in (None, "bool"):
                self._error(f"la condición de 'si' debe ser bool, no {t}", s.condicion)
            self._bloque(s.entonces, amb)
            if isinstance(s.sino, N.Bloque):
                self._bloque(s.sino, amb)
            elif s.sino is not None:
                self._sentencia(s.sino, amb)
        elif isinstance(s, N.Repetir):
            t = self._expr(s.veces, amb)
            if t not in (None, "int"):
                self._error(f"'repetir' requiere un número entero de veces, no {t}", s.veces)
            n = self._constante(s.veces, amb)
            if isinstance(n, int) and n <= 0:
                self._adv("'repetir' con cero o menos veces nunca ejecuta su cuerpo", s)
            self._bloque(s.cuerpo, amb)
        elif isinstance(s, N.IrA):
            self._destino(s.destino, s)
        elif isinstance(s, N.SentenciaLlamada):
            self._expr(s.llamada, amb, como_sentencia=True)

    # --- expresiones ------------------------------------------------------
    def _expr(self, e, amb, como_sentencia=False):
        t = self._tipo_expr(e, amb, como_sentencia)
        e.tipo = t
        return t

    def _tipo_expr(self, e, amb, como_sentencia):
        if isinstance(e, N.Literal):
            if e.tipo_lit == "proporcion":
                self._verificar_rango("proporcion", e.valor, e)
            return e.tipo_lit
        if isinstance(e, N.Identificador):
            sim = amb.buscar(e.nombre)
            if sim is None:
                self._error(f"identificador '{e.nombre}' no declarado", e)
                return None
            if sim.categoria in ("gesto", "secuencia", "maquina", "estado", "funcion"):
                self._error(f"'{e.nombre}' es {sim.categoria} y no puede usarse como valor", e)
                return None
            return sim.tipo
        if isinstance(e, N.Unaria):
            t, err = tipo_unario(e.op, self._expr(e.operando, amb))
            if err:
                self._error(err, e)
            return t
        if isinstance(e, N.Binaria):
            a = self._expr(e.izq, amb)
            b = self._expr(e.der, amb)
            t, err = tipo_binario(e.op, a, b)
            if err:
                self._error(err, e)
            return t
        if isinstance(e, N.Llamada):
            return self._llamada(e, amb, como_sentencia)
        return None

    def _llamada(self, e: N.Llamada, amb, como_sentencia):
        f = FUNCIONES.get(e.nombre)
        tipos_args = [self._expr(a, amb) for a in e.args]
        if f is None:
            self._error(f"función '{e.nombre}' no definida", e)
            return None
        if self.en_gesto:
            self._error(f"no se pueden llamar funciones dentro de la condición de un gesto", e)
        if f.params is not None:
            if len(tipos_args) != len(f.params):
                self._error(f"'{f.nombre}' espera {len(f.params)} argumento(s) y recibió "
                            f"{len(tipos_args)}", e)
                return None if f.retorno == "num" else f.retorno
            for i, (p, t) in enumerate(zip(f.params, tipos_args), 1):
                ok = (t is None or (p == "num" and es_numerico(t)) or asignable(p, t))
                if not ok:
                    self._error(f"argumento {i} de '{f.nombre}': se esperaba {p}, se recibió {t}", e)
        if f.retorno == "void" and not como_sentencia:
            self._error(f"'{f.nombre}' no devuelve un valor", e)
            return None
        if f.retorno == "num":
            return tipos_args[0] if tipos_args else None
        return f.retorno

    # --- evaluación de constantes (plegado) -------------------------------
    def _constante(self, e, amb):
        """Valor de la expresión si puede calcularse en compilación, si no None."""
        return evaluar_constante(e, lambda n: _valor_simbolo(amb.buscar(n)))


def _valor_simbolo(sim):
    if sim is None or sim.categoria != "variable":
        return None
    return sim.valor


def evaluar_constante(e, buscar):
    if isinstance(e, N.Literal):
        return e.valor
    if isinstance(e, N.Identificador):
        return buscar(e.nombre)
    if isinstance(e, N.Unaria):
        v = evaluar_constante(e.operando, buscar)
        if v is None:
            return None
        return (not v) if e.op == "no" else -v
    if isinstance(e, N.Binaria):
        a = evaluar_constante(e.izq, buscar)
        b = evaluar_constante(e.der, buscar)
        if a is None or b is None:
            return None
        try:
            return {
                "+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
                "/": lambda: a / b, "<": lambda: a < b, "<=": lambda: a <= b,
                ">": lambda: a > b, ">=": lambda: a >= b, "==": lambda: a == b,
                "!=": lambda: a != b, "y": lambda: a and b, "o": lambda: a or b,
            }[e.op]()
        except (ZeroDivisionError, TypeError):
            return None
    return None


def _identificadores(e):
    if isinstance(e, N.Identificador):
        yield e.nombre
    elif isinstance(e, N.Binaria):
        yield from _identificadores(e.izq)
        yield from _identificadores(e.der)
    elif isinstance(e, N.Unaria):
        yield from _identificadores(e.operando)
    elif isinstance(e, N.Llamada):
        for a in e.args:
            yield from _identificadores(a)


def _ambito_nombrado(amb):
    while amb and amb.nombre == "bloque":
        amb = amb.padre
    return amb.nombre if amb else "?"


def analizar(programa, reporte: Reporte | None = None):
    reporte = reporte or Reporte()
    return Semantico(reporte).analizar(programa), reporte
