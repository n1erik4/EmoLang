"""Costo de un programa antes y después de optimizar.

Mide al ejecutar en EmoVM: cuádruplas ejecutadas, tiempo, profundidad de llamadas y pila.
Calcula al compilar: cuádruplas del programa, memoria de datos y registros necesarios.

Los registros se estiman como el mayor número de temporales vivos al mismo tiempo en un
bloque: es la cantidad que necesitaría el código objeto para no guardarlos en memoria.
"""

import statistics
import time
from dataclasses import dataclass

from .direcciones import construir
from .intermedio import PROGRAMA, es_temporal, resolver
from .metricas import metricas_neutras
from .modulos import ModuloBase, ModuloPrograma
from .vm import EmoVM


@dataclass
class Costo:
    cuadruplas: int = 0
    ejecutadas: int = 0
    tiempo_ms: float = 0.0
    datos_bytes: int = 0
    literales_bytes: int = 0
    pila_bytes: int = 0
    llamadas_anidadas: int = 0
    registros: int = 0


CAMPOS = [
    ("cuadruplas", "Cuádruplas del programa"),
    ("ejecutadas", "Cuádruplas ejecutadas"),
    ("tiempo_ms", "Tiempo en EmoVM (ms)"),
    ("datos_bytes", "Memoria de datos (bytes)"),
    ("literales_bytes", "Memoria de literales (bytes)"),
    ("pila_bytes", "Pila máxima (bytes)"),
    ("llamadas_anidadas", "Llamadas anidadas (máximo)"),
    ("registros", "Registros necesarios (estimado)"),
]


def temporales_vivos(cuadruplas):
    """Mayor número de temporales vivos a la vez, considerando los ciclos."""
    filas = resolver(cuadruplas)
    primero, ultimo = {}, {}
    for i, c in enumerate(filas):
        for campo in c.lecturas():
            x = getattr(c, campo)
            if es_temporal(x):
                primero.setdefault(x, i)
                ultimo[x] = i
        d = c.escribe()
        if es_temporal(d):
            primero.setdefault(d, i)
            ultimo[d] = max(ultimo.get(d, i), i)
    # Un temporal que nace antes de un ciclo y se lee dentro sigue vivo hasta que el ciclo termina.
    for i, c in enumerate(filas):
        if c.op in ("goto", "gotoF") and isinstance(c.res, int) and c.res - 1 <= i:
            inicio = c.res - 1
            for t in primero:
                if primero[t] < inicio and inicio <= ultimo[t] <= i:
                    ultimo[t] = i
    maximo = 0
    for i in range(len(filas)):
        maximo = max(maximo, sum(1 for t in primero if primero[t] <= i <= ultimo[t]))
    return maximo


def _estaticos(prog):
    tabla = construir(prog)
    return Costo(
        cuadruplas=sum(len(resolver(b)) for b in prog.bloques.values()),
        datos_bytes=sum(e.bytes for e in tabla.datos),
        literales_bytes=sum(e.bytes for e in tabla.literales),
        registros=max((temporales_vivos(b) for b in prog.bloques.values()), default=0),
    ), {n: tabla.marcos[f["bloque"]].bytes for n, f in prog.funciones.items()}, tabla


def _correr(fabrica, ejecutar, repeticiones):
    tiempos = []
    vm = None
    for _ in range(repeticiones):
        vm = fabrica()
        t0 = time.perf_counter()
        ejecutar(vm)
        tiempos.append((time.perf_counter() - t0) * 1000)
    return vm, statistics.median(tiempos)


def _medir(prog, emoc, dominio, modulo, cuadros, repeticiones):
    costo, marcos, tabla = _estaticos(prog)

    def fabrica():
        vm = EmoVM(emoc, dominio, modulo())
        vm.tam_marcos = marcos
        vm.ejecutadas = 0
        return vm

    if cuadros is None:
        def ejecutar(vm):
            vm.ejecutar_principal()
    else:
        def ejecutar(vm):
            for t, m in cuadros:
                vm.paso(t, m)

    vm, costo.tiempo_ms = _correr(fabrica, ejecutar, repeticiones)
    costo.ejecutadas = vm.ejecutadas
    costo.pila_bytes = vm.pila_maxima
    costo.llamadas_anidadas = vm.profundidad_maxima
    return costo


def _silencio(*_):
    pass


def comparar(resultado, dominio=None, cuadros=None, repeticiones=5):
    """Devuelve (costo sin optimizar, costo optimizado).

    Sin `dominio` mide 'funcion principal'; con `dominio`, recorre los `cuadros` de un sensor."""
    nombre = dominio or PROGRAMA
    modulo = (lambda: ModuloPrograma(salida=_silencio)) if dominio is None else (lambda: _modulo_de(dominio))
    antes = _medir(resultado.cuadruplas[nombre], resultado.emoc_sin_optimizar(), nombre, modulo,
                   cuadros, repeticiones)
    despues = _medir(resultado.optimizado[nombre], resultado.emoc, nombre, modulo, cuadros, repeticiones)
    return antes, despues


def _modulo_de(dominio):
    from .modulos import modulo_para
    return modulo_para(dominio, salida=_silencio)


def reporte(antes, despues):
    """Tabla de texto con el cambio de cada costo."""
    lineas = [f"{'COSTO':<34} {'ANTES':>12} {'DESPUÉS':>12} {'CAMBIO':>9}"]
    for campo, nombre in CAMPOS:
        a, d = getattr(antes, campo), getattr(despues, campo)
        cambio = f"{100 * (d - a) / a:+.1f}%" if a else "–"
        formato = (lambda v: f"{v:.3f}") if campo == "tiempo_ms" else str
        lineas.append(f"{nombre:<34} {formato(a):>12} {formato(d):>12} {cambio:>9}")
    return "\n".join(lineas)
