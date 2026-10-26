"""Validaciones propias del dominio (objetivo específico 4).

  * Umbrales fuera de rango: comparaciones de una métrica contra un valor que
    la métrica nunca puede tomar (o que es atípico).
  * Gestos imposibles: condiciones insatisfacibles (análisis de intervalos),
    duración mínima mayor a la máxima, duraciones menores a un cuadro.
  * Estados inalcanzables desde el estado inicial (recorrido BFS).
  * Transiciones contradictorias: un mismo evento lleva a destinos distintos.
"""

import math
from collections import deque
from dataclasses import dataclass

from . import nodos as N
from .errores import Reporte
from .metricas import METRICAS
from .semantico import evaluar_constante

FASE = "dominio"
MAX_CAJAS = 256

INVERSO = {"<": ">=", "<=": ">", ">": "<=", ">=": "<", "==": "!=", "!=": "=="}
ESPEJO = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}


# ------------------------------------------------------------------ intervalos
@dataclass(frozen=True)
class Intervalo:
    lo: float
    hi: float
    lo_inc: bool = True
    hi_inc: bool = True

    def vacio(self):
        return self.lo > self.hi or (self.lo == self.hi and not (self.lo_inc and self.hi_inc))

    def interseccion(self, o):
        if self.lo > o.lo or (self.lo == o.lo and not self.lo_inc):
            lo, lo_inc = self.lo, self.lo_inc
        else:
            lo, lo_inc = o.lo, o.lo_inc
        if self.hi < o.hi or (self.hi == o.hi and not self.hi_inc):
            hi, hi_inc = self.hi, self.hi_inc
        else:
            hi, hi_inc = o.hi, o.hi_inc
        return Intervalo(lo, hi, lo_inc, hi_inc)


def _rango(metrica):
    m = METRICAS[metrica]
    return Intervalo(float(m.minimo), float(m.maximo))


def _intervalo_de(op, c):
    inf = math.inf
    return {
        "<": [Intervalo(-inf, c, True, False)],
        "<=": [Intervalo(-inf, c)],
        ">": [Intervalo(c, inf, False, True)],
        ">=": [Intervalo(c, inf)],
        "==": [Intervalo(c, c)],
        "!=": [Intervalo(-inf, c, True, False), Intervalo(c, inf, False, True)],
    }[op]


def _intersectar_cajas(a, b):
    """Producto de dos listas de cajas (conjunción)."""
    resultado = []
    for x in a:
        for y in b:
            caja = dict(x)
            vacia = False
            for k, iv in y.items():
                caja[k] = caja[k].interseccion(iv) if k in caja else iv
                if caja[k].vacio():
                    vacia = True
                    break
            if not vacia:
                resultado.append(caja)
            if len(resultado) >= MAX_CAJAS:
                return resultado
    return resultado


class _Analizador:
    """Convierte una condición a una unión de 'cajas' (forma normal disyuntiva
    sobre intervalos por métrica) para decidir si es satisfacible."""

    def __init__(self, buscar):
        self.buscar = buscar
        self.desconocido = False
        self.atomos = []  # (metrica, op, valor, nodo)

    def cajas(self, e, negado=False):
        if isinstance(e, N.Binaria) and e.op in ("y", "o"):
            conj = (e.op == "y") != negado
            a = self.cajas(e.izq, negado)
            b = self.cajas(e.der, negado)
            return _intersectar_cajas(a, b) if conj else (a + b)[:MAX_CAJAS]
        if isinstance(e, N.Unaria) and e.op == "no":
            return self.cajas(e.operando, not negado)
        if isinstance(e, N.Literal) and e.tipo_lit == "bool":
            return [{}] if (e.valor != negado) else []
        if isinstance(e, N.Identificador) and e.nombre in METRICAS and METRICAS[e.nombre].tipo == "bool":
            v = 0.0 if negado else 1.0
            return [{e.nombre: Intervalo(v, v)}]
        if isinstance(e, N.Binaria) and e.op in INVERSO:
            atomo = self._atomo(e)
            if atomo:
                metrica, op, c = atomo
                if negado:
                    op = INVERSO[op]
                return [{metrica: iv.interseccion(_rango(metrica))} for iv in _intervalo_de(op, c)
                        if not iv.interseccion(_rango(metrica)).vacio()]
        self.desconocido = True
        return [{}]

    def _atomo(self, e):
        for metrica_lado, const_lado, op in ((e.izq, e.der, e.op), (e.der, e.izq, ESPEJO[e.op])):
            if isinstance(metrica_lado, N.Identificador) and metrica_lado.nombre in METRICAS:
                c = evaluar_constante(const_lado, self.buscar)
                if isinstance(c, bool):
                    c = float(c)
                if isinstance(c, (int, float)):
                    self.atomos.append((metrica_lado.nombre, op, float(c), e))
                    return metrica_lado.nombre, op, float(c)
        return None


# ------------------------------------------------------------------ validador
class Validador:
    def __init__(self, analisis, reporte: Reporte):
        self.analisis = analisis
        self.reporte = reporte
        self.imposibles = set()

    def _error(self, msg, nodo):
        self.reporte.error(FASE, msg, nodo.linea, nodo.columna)

    def _adv(self, msg, nodo):
        self.reporte.advertencia(FASE, msg, nodo.linea, nodo.columna)

    def validar(self):
        for info in self.analisis.dominios.values():
            buscar = _buscador(info.ambito)
            for g in info.gestos.values():
                self._gesto(g, info, buscar)
            for s in info.secuencias.values():
                self._secuencia(s, info, buscar)
            for m in info.maquinas.values():
                self._maquina(m, info)
            for nombre, nodo in {**info.gestos, **info.secuencias}.items():
                if nombre not in info.usados:
                    self._adv(f"'{nombre}' se declara pero ningún 'cuando' ni secuencia lo usa", nodo)
        return self.imposibles

    # --- gestos -----------------------------------------------------------
    def _gesto(self, g: N.Gesto, info, buscar):
        an = _Analizador(buscar)
        cajas = an.cajas(g.condicion)

        for metrica, op, c, nodo in an.atomos:
            m = METRICAS[metrica]
            if m.tipo == "bool":
                continue
            if c < m.minimo or c > m.maximo:
                self._error(f"umbral fuera de rango: '{metrica}' toma valores en "
                            f"[{m.minimo:g}, {m.maximo:g}] y se comparó con {c:g}", nodo)
            elif c < m.tipico[0] or c > m.tipico[1]:
                self._adv(f"umbral atípico: '{metrica}' suele estar en "
                          f"[{m.tipico[0]:g}, {m.tipico[1]:g}] y se comparó con {c:g}", nodo)

        if not cajas:
            self.imposibles.add(g.nombre)
            self._error(f"gesto imposible: la condición de '{g.nombre}' nunca puede cumplirse", g)
        elif not an.desconocido and any(_caja_total(c) for c in cajas):
            self._adv(f"la condición de '{g.nombre}' siempre es verdadera", g)

        cuadro = 1000.0 / info.fps
        es_dur = lambda e: e is not None and e.tipo == "duracion"
        dmin = evaluar_constante(g.minimo, buscar) if es_dur(g.minimo) else None
        dmax = evaluar_constante(g.maximo, buscar) if es_dur(g.maximo) else None
        tol = evaluar_constante(g.tolerancia, buscar) if es_dur(g.tolerancia) else None
        if isinstance(tol, (int, float)) and isinstance(dmin, (int, float)) and tol >= dmin > 0:
            self._adv(f"la tolerancia de '{g.nombre}' ({tol:g} ms) no es menor que su duración "
                      f"mínima ({dmin:g} ms): interrupciones más largas que el gesto se ignorarían",
                      g.tolerancia)
        elif isinstance(tol, (int, float)) and 0 < tol < cuadro:
            self._adv(f"la tolerancia {tol:g} ms es menor a un cuadro ({cuadro:.1f} ms); no tiene efecto",
                      g.tolerancia)
        if isinstance(dmin, (int, float)) and isinstance(dmax, (int, float)) and dmin > dmax:
            self.imposibles.add(g.nombre)
            self._error(f"gesto imposible: '{g.nombre}' dura al menos {dmin:g} ms pero "
                        f"como máximo {dmax:g} ms", g)
        if isinstance(dmax, (int, float)) and dmax < cuadro:
            self.imposibles.add(g.nombre)
            self._error(f"gesto imposible: la duración máxima {dmax:g} ms es menor a un cuadro "
                        f"({cuadro:.1f} ms a {info.fps} fps)", g.maximo)
        elif isinstance(dmin, (int, float)) and 0 < dmin < cuadro:
            self._adv(f"la duración {dmin:g} ms es menor a un cuadro ({cuadro:.1f} ms a "
                      f"{info.fps} fps); se detectará en un solo cuadro", g.minimo)

    def _secuencia(self, s: N.Secuencia, info, buscar):
        malos = [i.nombre for i in s.gestos if i.nombre in self.imposibles]
        if malos:
            self.imposibles.add(s.nombre)
            self._error(f"secuencia imposible: '{s.nombre}' contiene gestos imposibles "
                        f"({', '.join(malos)})", s)
        if s.ventana is None:
            return
        # La ventana se mide del primer al último evento. Gestos distintos pueden
        # sostenerse a la vez, pero un gesto repetido debe soltarse (1 cuadro) y
        # volver a cumplir su duración mínima antes de emitirse otra vez.
        ventana = evaluar_constante(s.ventana, buscar)
        requerido = 0.0
        for previo, ident in zip(s.gestos, s.gestos[1:]):
            g = info.gestos.get(ident.nombre)
            if g is None or previo.nombre != ident.nombre:
                continue
            d = evaluar_constante(g.minimo, buscar)
            if isinstance(d, (int, float)):
                requerido += max(d, 1000.0 / info.fps) + 1000.0 / info.fps
        if isinstance(ventana, (int, float)) and ventana < requerido:
            self.imposibles.add(s.nombre)
            self._error(f"secuencia imposible: '{s.nombre}' necesita al menos {requerido:g} ms "
                        f"pero su ventana es de {ventana:g} ms", s.ventana)

    # --- máquinas ---------------------------------------------------------
    def _maquina(self, m: N.Maquina, info):
        estados = {e.nombre: e for e in m.estados}
        grafo = {e.nombre: set() for e in m.estados}

        for e in m.estados:
            for destino, _ in _transiciones_estado(e):
                if destino in estados:
                    grafo[e.nombre].add(destino)

            por_evento = {}
            for c in e.cuandos:
                por_evento.setdefault(c.evento, []).append(c)
                if c.evento in self.imposibles:
                    self._adv(f"la transición 'cuando {c.evento}' del estado '{e.nombre}' nunca "
                              "se dispara: el evento es imposible", c)
            for evento, cs in por_evento.items():
                incondicionales = {_destino_incondicional(c) for c in cs} - {None}
                if len(incondicionales) > 1:
                    self._error(f"transiciones contradictorias en '{e.nombre}': el evento "
                                f"'{evento}' lleva a {', '.join(sorted(incondicionales))}", cs[1])
                elif len(cs) > 1:
                    self._adv(f"el evento '{evento}' se maneja {len(cs)} veces en el estado "
                              f"'{e.nombre}'; solo se ejecuta el primero", cs[1])

            for w in e.mientras:
                if e.nombre in {d for d, _ in _ir_a_en(w.cuerpo)}:
                    self._adv(f"'ir_a {e.nombre}' dentro de 'mientras' reingresa al estado en cada "
                              "cuadro y reinicia sus variables", w)

        self._eventos_ignorados(m, grafo, set(info.gestos) | set(info.secuencias))

        if m.inicial not in estados:
            return
        alcanzados = {m.inicial}
        cola = deque([m.inicial])
        while cola:
            for d in grafo[cola.popleft()]:
                if d not in alcanzados:
                    alcanzados.add(d)
                    cola.append(d)
        for nombre, e in estados.items():
            if nombre not in alcanzados:
                self._error(f"estado inalcanzable: '{nombre}' no puede alcanzarse desde el "
                            f"estado inicial '{m.inicial}'", e)


    def _eventos_ignorados(self, m: N.Maquina, grafo, declarados):
        """Nota cuando un evento provoca una transición en algunos estados pero se
        ignora en otros (p. ej. 'distraccion' atendida en 'normal' y no en
        'somnoliento'). Se excluyen los estados finales (sin salidas), donde ignorar
        eventos es lo esperado. Un 'cuando evento { }' vacío lo declara intencional."""
        cambia, maneja = {}, {}
        for e in m.estados:
            for ident in e.ignorados:
                maneja.setdefault(ident.nombre, set()).add(e.nombre)
            for c in e.cuandos:
                maneja.setdefault(c.evento, set()).add(e.nombre)
                if c.destino or any(True for _ in _ir_a_en(c.cuerpo)):
                    cambia.setdefault(c.evento, set()).add(e.nombre)
        activos = [e.nombre for e in m.estados if grafo[e.nombre] - {e.nombre}]
        for evento, origenes in cambia.items():
            if evento not in declarados:     # ya se reportó como error semántico
                continue
            ignorado = [n for n in activos if n not in maneja[evento]]
            if ignorado:
                self.reporte.nota(
                    FASE, f"en la máquina '{m.nombre}', el evento '{evento}' cambia de estado en "
                    f"{', '.join(sorted(origenes))} pero se ignora en {', '.join(ignorado)} "
                    f"(si es intencional escriba 'ignorar {evento};' en esos estados)", m.linea, m.columna)


# ------------------------------------------------------------------ auxiliares
def _caja_total(caja):
    for k, iv in caja.items():
        r = _rango(k)
        if iv.interseccion(r) != r:
            return False
    return True


def _buscador(ambito):
    def buscar(nombre):
        sim = ambito.buscar(nombre)
        return sim.valor if sim and sim.categoria == "variable" else None
    return buscar


def _ir_a_en(nodo, condicional=False):
    """Genera (destino, es_condicional) de cada ir_a dentro de un bloque."""
    if nodo is None:
        return
    if isinstance(nodo, N.Bloque):
        for s in nodo.sentencias:
            yield from _ir_a_en(s, condicional)
    elif isinstance(nodo, N.IrA):
        yield nodo.destino, condicional
    elif isinstance(nodo, N.Si):
        yield from _ir_a_en(nodo.entonces, True)
        yield from _ir_a_en(nodo.sino, True)
    elif isinstance(nodo, N.Repetir):
        yield from _ir_a_en(nodo.cuerpo, True)


def _transiciones_estado(e: N.Estado):
    for c in e.cuandos:
        if c.destino:
            yield c.destino, False
        yield from _ir_a_en(c.cuerpo)
    yield from _ir_a_en(e.al_entrar)
    for w in e.mientras:
        yield from _ir_a_en(w.cuerpo, True)


def _destino_incondicional(c: N.Cuando):
    if c.destino:
        return c.destino
    for d, cond in _ir_a_en(c.cuerpo):
        if not cond:
            return d
    return None


def validar(analisis, reporte: Reporte | None = None):
    reporte = reporte or Reporte()
    imposibles = Validador(analisis, reporte).validar()
    return imposibles, reporte
