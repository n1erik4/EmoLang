"""EmoVM: máquina virtual que ejecuta un programa compilado (.emoc).

En cada cuadro de video:
  1. Corre el bloque 'gestos': calcula cada condición con cuádruplas y le entrega
     el símbolo 1 o 0 al AFD del gesto; las secuencias consumen los eventos.
  2. Cada máquina de estados atiende los eventos del cuadro en su estado actual
     (primer 'cuando' que coincide), revisa sus 'tras' y corre sus 'mientras'.
"""

from collections import deque

from .errores import ErrorEmoLang
from .intermedio import MAX_REPETIR, es_temporal
from .metricas import metricas_neutras
from .optimizador import calcular

MAX_ENCADENAMIENTO = 32
_VACIO = {"int": 0, "decimal": 0.0, "proporcion": 0.0, "duracion": 0.0, "bool": False, "string": ""}


def _revisar_indice(i, base, linea):
    if not 0 <= i < len(base):
        raise ErrorEmoLang(f"índice {i} fuera de rango: el arreglo tiene {len(base)} elementos", linea, 0)


class _Transicion(Exception):
    def __init__(self, destino):
        self.destino = destino


class _Constante:
    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v


def _decodificar(x):
    return _Constante(x["k"]) if isinstance(x, dict) else x


class _GestoVivo:
    def __init__(self, a):
        self.nombre = a["nombre"]
        self.estado = a["inicial"]
        self.activo = False
        self.delta = {(t["origen"], t["simbolo"]): t for t in a["transiciones"]}


class _SecuenciaVivo:
    def __init__(self, a):
        self.nombre = a["nombre"]
        self.inicial = a["inicial"]
        self.estado = a["inicial"]
        self.alfabeto = set(a["alfabeto"])
        self.ventana = a["descripcion"].get("ventana_ms")
        self.t_inicio = 0.0
        self.delta = {(t["origen"], t["simbolo"]): t for t in a["transiciones"]}


class _MaquinaVivo:
    def __init__(self, tabla):
        self.nombre = tabla["nombre"]
        self.inicial = tabla["inicial"]
        self.estados = tabla["estados"]
        self.actual = None
        self.t_entrada = 0.0


class EmoVM:
    def __init__(self, emoc, dominio, modulo):
        if dominio not in emoc["dominios"]:
            raise ErrorEmoLang(f"el dominio '{dominio}' no existe")
        d = emoc["dominios"][dominio]
        self.modulo = modulo
        self.fps = d["fps"]
        self.t = 0.0
        self.metricas = metricas_neutras()
        self.eventos_cuadro = []
        self.cuadro_n = 0
        self.mem = {}
        self._eventos = []
        self._perclos = deque()
        self._iniciado = False
        self._mq = None
        self.bloques = {n: [(c[0], _decodificar(c[1]), _decodificar(c[2]), c[3], c[4]) for c in b]
                        for n, b in d["bloques"].items()}
        self.gestos = {a["nombre"]: _GestoVivo(a) for a in d["gestos"]}
        self.secuencias = {a["nombre"]: _SecuenciaVivo(a) for a in d["secuencias"]}
        self.maquinas = [_MaquinaVivo(m) for m in d["maquinas"]]
        self.funciones = d.get("funciones", {})
        self.estructuras = d.get("estructuras", {})
        self._correr("init")

    def ejecutar_principal(self):
        """Ejecuta 'funcion principal' y devuelve su resultado."""
        self.modulo.cuadro(0.0, self.metricas)
        try:
            return self._llamar_funcion("principal", [])
        except RecursionError:
            raise ErrorEmoLang("desbordamiento de pila: demasiadas llamadas anidadas") from None

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
                self._entrar(mq, mq.inicial)

        self._eventos = []
        self._correr("gestos")
        self.eventos_cuadro = self._eventos
        for mq in self.maquinas:
            self._paso_maquina(mq, self._eventos)
        return self._eventos

    def _actualizar_perclos(self):
        cerrado = float(self.metricas.get("ear", 0.3)) < 0.2
        self._perclos.append((self.t, cerrado))
        while self._perclos and self.t - self._perclos[0][0] > 60_000:
            self._perclos.popleft()
        self.metricas["perclos"] = sum(c for _, c in self._perclos) / len(self._perclos)

    # ------------------------------------------------------------------ máquinas
    def _paso_maquina(self, mq, eventos):
        self._mq = mq
        estado = mq.estados[mq.actual]
        try:
            for ev in eventos:
                for c in estado["cuandos"]:
                    if c["evento"] == ev:
                        if c["destino"]:
                            raise _Transicion(c["destino"])
                        self._correr(c["bloque"])
                        break
            for tr in estado["tras"]:
                if self.t - mq.t_entrada >= tr["ms"]:
                    raise _Transicion(tr["destino"])
            for b in estado["mientras"]:
                self._correr(b)
        except _Transicion as tr:
            self._entrar(mq, tr.destino)

    def _entrar(self, mq, destino):
        self._mq = mq
        for _ in range(MAX_ENCADENAMIENTO):
            origen = mq.actual
            mq.actual = destino
            mq.t_entrada = self.t
            self.modulo.evento("transicion", f"{mq.nombre}: {origen or 'inicio'} → {destino}")
            try:
                bloque = mq.estados[destino]["entrar"]
                if bloque:
                    self._correr(bloque)
                return
            except _Transicion as tr:
                destino = tr.destino
        raise ErrorEmoLang(f"ciclo de transiciones espontáneas en la máquina '{mq.nombre}' "
                           f"(más de {MAX_ENCADENAMIENTO} 'ir_a' en un mismo cuadro)")

    # ------------------------------------------------------------------ cuádruplas
    def _leer(self, x):
        if type(x) is _Constante:
            return x.v
        if x in self.mem:
            return self.mem[x]
        if x in self.metricas:
            return self.metricas[x]
        raise ErrorEmoLang(f"variable '{x}' sin valor en tiempo de ejecución")

    def _llamar_funcion(self, nombre, args):
        f = self.funciones[nombre]
        return self._correr(f["bloque"], dict(zip(f["params"], args)), nombre + ".")

    def _correr(self, nombre, marco=None, prefijo=None):
        """Ejecuta un bloque. Una función usa su propio marco para parámetros, locales y
        temporales, lo que permite la recursión; lo demás se guarda en la memoria global."""
        bloque = self.bloques[nombre]
        global_ = self.mem
        if marco is None:
            leer = self._leer
            escribir = global_.__setitem__
        else:
            def leer(x):
                if type(x) is not _Constante and x in marco:
                    return marco[x]
                return self._leer(x)

            def escribir(destino, valor):
                if es_temporal(destino) or destino.startswith(prefijo):
                    marco[destino] = valor
                else:
                    global_[destino] = valor
        params = []
        pc = 0
        while True:
            op, a1, a2, res, linea = bloque[pc]
            pc += 1
            if op == "ret":
                return None
            if op == "retv":
                return leer(a1)
            if op == "=":
                escribir(res, leer(a1))
            elif op == "gotoF":
                if not leer(a1):
                    pc = res - 1
            elif op == "goto":
                pc = res - 1
            elif op == "param":
                params.append(leer(a1))
            elif op == "call":
                valor = self._llamar(a1, params)
                params = []
                if res is not None:
                    escribir(res, valor)
            elif op == "afd":
                self._avanzar_gesto(res, leer(a1))
            elif op == "sec":
                self._avanzar_secuencia(res)
            elif op == "ir_a":
                raise _Transicion(res)
            elif op == "chk_rep":
                if leer(a1) > MAX_REPETIR:
                    raise ErrorEmoLang(f"'repetir' excede el máximo de {MAX_REPETIR} vueltas por cuadro",
                                       linea, 0)
            elif op == "texto":
                escribir(res, calcular(op, leer(a1), a2))
            elif op == "neg" or op == "no":
                escribir(res, calcular(op, leer(a1), None))
            elif op == "alloc":
                escribir(res, [_VACIO[a2]] * leer(a1))
            elif op == "alloc_e":
                escribir(res, {c: _VACIO[t] for c, t in self.estructuras[a1].items()})
            elif op == "[]":
                base, i = leer(a1), leer(a2)
                _revisar_indice(i, base, linea)
                escribir(res, base[i])
            elif op == "[]=":
                base, i = leer(res), leer(a2)
                _revisar_indice(i, base, linea)
                base[i] = leer(a1)
            elif op == "campo":
                escribir(res, leer(a1)[a2.split(".")[1]])
            elif op == "campo=":
                leer(res)[a2.split(".")[1]] = leer(a1)
            else:
                b = leer(a2)
                if op == "/" and b == 0:
                    raise ErrorEmoLang("división entre cero", linea, 0)
                escribir(res, calcular(op, leer(a1), b))

    def _avanzar_gesto(self, nombre, condicion):
        g = self.gestos[nombre]
        simbolo = "1" if condicion else "0"
        tr = g.delta[(g.estado, simbolo)]
        g.estado = tr["destino"]
        g.activo = simbolo == "1"
        if tr["salida"]:
            self._eventos.append(tr["salida"])
            self.modulo.evento("gesto", tr["salida"])

    def _avanzar_secuencia(self, nombre):
        s = self.secuencias[nombre]
        for ev in list(self._eventos):
            if ev not in s.alfabeto:
                continue
            if s.ventana is not None and s.estado != s.inicial and self.t - s.t_inicio > s.ventana:
                s.estado = s.inicial
            tr = s.delta[(s.estado, ev)]
            if s.estado == s.inicial or tr["destino"] == "s1":
                s.t_inicio = self.t
            s.estado = tr["destino"]
            if tr["salida"]:
                self._eventos.append(tr["salida"])
                self.modulo.evento("secuencia", tr["salida"])

    def _llamar(self, n, args):
        if n in self.funciones:
            return self._llamar_funcion(n, args)
        m = self.modulo
        if n == "alarma":
            return m.alarma(args[0])
        if n == "detener_alarma":
            return m.detener_alarma()
        if n == "registrar":
            return m.registrar(args[0])
        if n == "mostrar":
            return m.mostrar(" ".join(args))
        if n == "contar_repeticion":
            return m.contar_repeticion()
        if n == "contar_ejercicio":
            return m.contar_ejercicio(args[0], args[1])
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
        if n == "a_int":
            return int(args[0])
        if n == "a_decimal":
            return float(args[0])
        raise ErrorEmoLang(f"función '{n}' no implementada")

    # ------------------------------------------------------------------ consulta
    def estado_actual(self):
        return {mq.nombre: mq.actual for mq in self.maquinas}

    def gestos_activos(self):
        return [g.nombre for g in self.gestos.values() if g.activo]
