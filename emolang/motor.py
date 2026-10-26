"""Motor de ejecución (objetivo específico 6).

En cada cuadro de video:
  1. Cada gesto evalúa su condición sobre las métricas -> símbolo '1' o '0' y
     avanza su AFD generado; si la transición tiene salida, se emite el evento.
  2. Las secuencias consumen los eventos de gestos con su AFD (KMP + ventana).
  3. Cada máquina de estados procesa los eventos del cuadro en su estado actual
     (primer 'cuando' que coincide) y luego evalúa sus bloques 'mientras'.
     Un 'mientras' se evalúa una sola vez por cuadro: nunca bloquea.
"""

from collections import deque
from dataclasses import dataclass, field

from . import nodos as N
from .errores import ErrorEmoLang
from .metricas import metricas_neutras

MAX_ENCADENAMIENTO = 32
MAX_REPETIR = 10_000


class _Transicion(Exception):
    def __init__(self, destino):
        self.destino = destino


@dataclass
class _GestoVivo:
    nodo: N.Gesto
    delta: dict
    estado: str
    activo: bool = False


@dataclass
class _SecuenciaVivo:
    nombre: str
    delta: dict
    inicial: str
    alfabeto: set
    ventana: float
    estado: str = None
    t_inicio: float = 0.0


@dataclass
class _MaquinaVivo:
    nodo: N.Maquina
    estados: dict
    actual: N.Estado = None
    locales: dict = field(default_factory=dict)
    t_entrada: float = 0.0
    historial: list = field(default_factory=list)


class Motor:
    def __init__(self, analisis, automatas, dominio, modulo):
        if dominio not in analisis.dominios:
            raise ErrorEmoLang(f"el dominio '{dominio}' no existe")
        self.info = analisis.dominios[dominio]
        self.modulo = modulo
        self.fps = self.info.fps
        self.t = 0.0
        self.metricas = metricas_neutras()
        self.eventos_cuadro = []
        self.cuadro_n = 0
        self._perclos = deque()
        self._iniciado = False
        self._mq = None

        por_nombre = {a.nombre: a for a in automatas[dominio]}
        self.globales = {}
        for s in self.info.nodo.sensores:
            for v in s.variables:
                self.globales[v.nombre] = self._eval(v.valor, [])
        for v in self.info.nodo.variables:
            self.globales[v.nombre] = self._eval(v.valor, [])

        self.gestos = [
            _GestoVivo(g, por_nombre[g.nombre].delta(), por_nombre[g.nombre].inicial)
            for g in self.info.gestos.values() if g.nombre in por_nombre
        ]
        self.secuencias = []
        for s in self.info.secuencias.values():
            a = por_nombre[s.nombre]
            ventana = a.descripcion.get("ventana_ms")
            self.secuencias.append(_SecuenciaVivo(s.nombre, a.delta(), a.inicial, set(a.alfabeto),
                                                  ventana, a.inicial))
        self.maquinas = [_MaquinaVivo(m, {e.nombre: e for e in m.estados})
                         for m in self.info.maquinas.values()]

    # ------------------------------------------------------------------ ciclo
    def paso(self, t_ms, metricas):
        """Procesa un cuadro. Devuelve la lista de eventos emitidos."""
        self.t = t_ms
        self.cuadro_n += 1
        self.metricas = dict(metricas)
        self._actualizar_perclos()
        self.modulo.cuadro(t_ms, self.metricas)

        if not self._iniciado:
            self._iniciado = True
            for mq in self.maquinas:
                self._entrar(mq, mq.nodo.inicial)

        eventos = []
        for g in self.gestos:
            simbolo = "1" if self._eval(g.nodo.condicion, []) else "0"
            tr = g.delta[(g.estado, simbolo)]
            g.estado = tr.destino
            g.activo = simbolo == "1"
            if tr.salida:
                eventos.append(tr.salida)
                self.modulo.evento("gesto", tr.salida)

        for s in self.secuencias:
            for ev in list(eventos):
                if ev not in s.alfabeto:
                    continue
                if (s.ventana is not None and s.estado != s.inicial
                        and t_ms - s.t_inicio > s.ventana):
                    s.estado = s.inicial
                tr = s.delta[(s.estado, ev)]
                if s.estado == s.inicial or tr.destino == "s1":
                    s.t_inicio = t_ms
                s.estado = tr.destino
                if tr.salida:
                    eventos.append(tr.salida)
                    self.modulo.evento("secuencia", tr.salida)

        self.eventos_cuadro = eventos
        for mq in self.maquinas:
            self._paso_maquina(mq, eventos)
        return eventos

    def _actualizar_perclos(self):
        cerrado = float(self.metricas.get("ear", 0.3)) < 0.2
        self._perclos.append((self.t, cerrado))
        while self._perclos and self.t - self._perclos[0][0] > 60_000:
            self._perclos.popleft()
        self.metricas["perclos"] = sum(c for _, c in self._perclos) / len(self._perclos)

    # ------------------------------------------------------------------ máquinas
    def _paso_maquina(self, mq, eventos):
        self._mq = mq
        try:
            for ev in eventos:
                for c in mq.actual.cuandos:
                    if c.evento == ev:
                        if c.destino:
                            raise _Transicion(c.destino)
                        self._bloque(c.cuerpo, mq)
                        break
            for w in mq.actual.mientras:
                if self._eval(w.condicion, [mq.locales]):
                    self._bloque(w.cuerpo, mq)
        except _Transicion as tr:
            self._entrar(mq, tr.destino)

    def _entrar(self, mq, destino):
        self._mq = mq
        for _ in range(MAX_ENCADENAMIENTO):
            origen = mq.actual.nombre if mq.actual else None
            mq.actual = mq.estados[destino]
            mq.t_entrada = self.t
            mq.historial.append((self.t, origen, destino))
            self.modulo.evento("transicion", f"{mq.nodo.nombre}: {origen or 'inicio'} → {destino}")
            try:
                mq.locales = {}
                for v in mq.actual.variables:
                    mq.locales[v.nombre] = self._eval(v.valor, [mq.locales])
                if mq.actual.al_entrar:
                    self._bloque(mq.actual.al_entrar, mq)
                return
            except _Transicion as tr:
                destino = tr.destino
        raise ErrorEmoLang(f"ciclo de transiciones espontáneas en la máquina '{mq.nodo.nombre}' "
                           f"(más de {MAX_ENCADENAMIENTO} 'ir_a' en un mismo cuadro)")

    # ------------------------------------------------------------------ sentencias
    def _bloque(self, b, mq, entorno=None):
        entorno = (entorno or [mq.locales]) + [{}]
        for s in b.sentencias:
            self._sentencia(s, mq, entorno)

    def _sentencia(self, s, mq, entorno):
        if isinstance(s, N.DeclVar):
            entorno[-1][s.nombre] = self._eval(s.valor, entorno)
        elif isinstance(s, N.Asignacion):
            valor = self._eval(s.valor, entorno)
            for amb in reversed(entorno):
                if s.nombre in amb:
                    amb[s.nombre] = valor
                    return
            self.globales[s.nombre] = valor
        elif isinstance(s, N.Si):
            if self._eval(s.condicion, entorno):
                self._bloque(s.entonces, mq, entorno)
            elif isinstance(s.sino, N.Bloque):
                self._bloque(s.sino, mq, entorno)
            elif s.sino is not None:
                self._sentencia(s.sino, mq, entorno)
        elif isinstance(s, N.Repetir):
            n = int(self._eval(s.veces, entorno))
            if n > MAX_REPETIR:
                raise ErrorEmoLang(f"'repetir' excede el máximo de {MAX_REPETIR} vueltas por cuadro",
                                   s.linea, s.columna)
            for _ in range(max(0, n)):
                self._bloque(s.cuerpo, mq, entorno)
        elif isinstance(s, N.IrA):
            raise _Transicion(s.destino)
        elif isinstance(s, N.SentenciaLlamada):
            self._eval(s.llamada, entorno)

    # ------------------------------------------------------------------ expresiones
    def _buscar(self, nombre, entorno):
        for amb in reversed(entorno):
            if nombre in amb:
                return amb[nombre]
        if nombre in self.globales:
            return self.globales[nombre]
        if nombre in self.metricas:
            return self.metricas[nombre]
        raise ErrorEmoLang(f"variable '{nombre}' sin valor en tiempo de ejecución")

    def _eval(self, e, entorno):
        if isinstance(e, N.Literal):
            return e.valor
        if isinstance(e, N.Identificador):
            return self._buscar(e.nombre, entorno)
        if isinstance(e, N.Unaria):
            v = self._eval(e.operando, entorno)
            return (not v) if e.op == "no" else -v
        if isinstance(e, N.Binaria):
            if e.op == "y":
                return bool(self._eval(e.izq, entorno)) and bool(self._eval(e.der, entorno))
            if e.op == "o":
                return bool(self._eval(e.izq, entorno)) or bool(self._eval(e.der, entorno))
            a = self._eval(e.izq, entorno)
            b = self._eval(e.der, entorno)
            if e.op == "+" and e.tipo == "string":
                return _texto(a, e.izq.tipo) + _texto(b, e.der.tipo)
            if e.op == "/":
                if b == 0:
                    raise ErrorEmoLang("división entre cero", e.linea, e.columna)
                return a / b
            r = {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
                 "<": lambda: a < b, "<=": lambda: a <= b, ">": lambda: a > b,
                 ">=": lambda: a >= b, "==": lambda: a == b, "!=": lambda: a != b}[e.op]()
            return r
        if isinstance(e, N.Llamada):
            return self._llamar(e, entorno)
        raise ErrorEmoLang(f"expresión no soportada: {type(e).__name__}")

    def _llamar(self, e, entorno):
        args = [self._eval(a, entorno) for a in e.args]
        n = e.nombre
        m = self.modulo
        if n == "alarma":
            return m.alarma(args[0])
        if n == "detener_alarma":
            return m.detener_alarma()
        if n == "registrar":
            return m.registrar(args[0])
        if n == "mostrar":
            return m.mostrar(" ".join(_texto(v, a.tipo) for v, a in zip(args, e.args)))
        if n == "contar_repeticion":
            return m.contar_repeticion()
        if n == "repeticiones":
            return m.repeticiones()
        if n == "tiempo_en_estado":
            return self.t - self._mq.t_entrada if self._mq else 0.0
        if n == "abs":
            return abs(args[0])
        if n == "a_porcentaje":
            return args[0] * 100.0
        if n == "a_proporcion":
            return args[0] / 100.0
        if n == "a_ms":
            return float(args[0])
        if n == "a_s":
            return args[0] / 1000.0
        raise ErrorEmoLang(f"función '{n}' no implementada")

    # ------------------------------------------------------------------ consulta
    def estado_actual(self):
        return {mq.nodo.nombre: mq.actual.nombre if mq.actual else None for mq in self.maquinas}


def _texto(v, tipo):
    if tipo == "duracion":
        return f"{v / 1000:g} s" if abs(v) >= 1000 else f"{v:g} ms"
    if tipo == "proporcion":
        return f"{v * 100:.1f}%"
    if tipo == "bool":
        return "verdadero" if v else "falso"
    if isinstance(v, float):
        return f"{v:.3f}".rstrip("0").rstrip(".")
    return str(v)
