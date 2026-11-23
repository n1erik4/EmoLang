"""Tema 4: generación de código objeto. Cuádruplas optimizadas -> ensamblador x86-64.

El traductor produce un archivo .asm en sintaxis Intel del ensamblador GNU (GAS) para
dos plataformas, que solo difieren en la convención de llamadas:

    windows   argumentos en rcx, rdx, r8, r9 (o xmm0-xmm3 según la posición),
              32 bytes de «espacio sombra» antes de cada llamada.  GCC de MSYS2.
    linux     argumentos enteros en rdi, rsi, rdx, rcx, r8, r9 y decimales en
              xmm0-xmm7, cada grupo por separado.  GCC del sistema (System V).

Administración de memoria en tiempo de ejecución:
    .text     las funciones traducidas, 'main' y un pequeño runtime (texto, errores)
    .data     variables globales (incluye arreglos y estructuras globales, en línea)
    .rodata   literales de texto (str_N) y decimales constantes (flt_N)
    pila      un marco por llamada, con las direcciones [rbp-k] de la tabla de direcciones

Asignación de registros: un análisis de flujo de datos (variables vivas) da el
intervalo de vida de cada variable entera de una función, y el algoritmo «linear
scan» las reparte entre rbx, r12, r13, r14 y r15.  Se eligieron porque las dos
convenciones los tratan como «preservados por la función llamada»: un valor que vive
en ellos sobrevive a una llamada.  Lo que no alcanza registro se queda en su lugar
del marco de pila.  Los decimales viven en memoria y se calculan en xmm0/xmm1.

Solo se traducen programas con 'funcion principal'; los módulos de dominio (gestos,
autómatas y máquinas de estado) se ejecutan en EmoVM, que tiene la cámara.
"""

import os
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass, field

from .direcciones import construir as construir_direcciones
from .errores import ErrorEmoLang
from .intermedio import MAX_REPETIR, PROGRAMA, Constante, es_temporal, resolver
from .tipos import elemento, es_arreglo, tamano

FLOTANTES = {"decimal", "proporcion", "duracion"}
REGISTROS = ["rbx", "r12", "r13", "r14", "r15"]
EXT_ASM = ".asm"


class NoSoportado(ErrorEmoLang):
    """Una construcción que el código objeto no traduce (p. ej. gestos de un dominio)."""


@dataclass(frozen=True)
class ABI:
    nombre: str
    enteros: tuple          # registros de argumentos enteros
    flotantes: tuple        # registros de argumentos decimales
    posicional: bool        # Windows: el argumento i usa el i-ésimo registro de su clase
    sombra: int             # bytes de espacio sombra que reserva quien llama
    rodata: str
    exe: str

    @property
    def a(self):
        return self.enteros


PLATAFORMAS = {
    "windows": ABI("windows", ("rcx", "rdx", "r8", "r9"), ("xmm0", "xmm1", "xmm2", "xmm3"),
                   True, 32, '.section .rdata,"dr"', ".exe"),
    "linux": ABI("linux", ("rdi", "rsi", "rdx", "rcx", "r8", "r9"),
                 tuple(f"xmm{i}" for i in range(8)), False, 0, ".section .rodata", ""),
}


def plataforma_local():
    return "windows" if sys.platform.startswith(("win", "cygwin", "msys")) else "linux"


def es_flotante(tipo):
    return tipo in FLOTANTES


def _etiqueta(nombre):
    return "".join(c if c.isalnum() or c == "_" else "_" for c in nombre)


def _bytes_asm(texto):
    return ", ".join(str(b) for b in texto.encode("utf-8") + bytes(1))


def _al16(n):
    return (n + 15) // 16 * 16


# ====================================================================== análisis
def sucesores(cuads, i):
    """Cuádruplas que pueden ejecutarse después de la i-ésima (índices desde 0)."""
    c = cuads[i]
    if c.op in ("ret", "retv"):
        return []
    if c.op == "goto":
        return [c.res - 1]
    siguiente = [i + 1] if i + 1 < len(cuads) else []
    if c.op == "gotoF":
        return siguiente + [c.res - 1]
    return siguiente


def usos_y_definicion(c):
    usos = [getattr(c, f) for f in c.lecturas()]
    return [x for x in usos if isinstance(x, str)], c.escribe()


def variables_vivas(cuads):
    """Análisis de flujo de datos hacia atrás: vivas_entrada[i] y vivas_salida[i]."""
    n = len(cuads)
    usos, defs = [], []
    for c in cuads:
        u, d = usos_y_definicion(c)
        usos.append(set(u))
        defs.append({d} if isinstance(d, str) else set())
    entrada = [set() for _ in range(n)]
    salida = [set() for _ in range(n)]
    cambio = True
    while cambio:
        cambio = False
        for i in reversed(range(n)):
            s = set()
            for j in sucesores(cuads, i):
                s |= entrada[j]
            e = usos[i] | (s - defs[i])
            if s != salida[i] or e != entrada[i]:
                salida[i], entrada[i] = s, e
                cambio = True
    return entrada, salida


@dataclass
class Intervalo:
    nombre: str
    inicio: int
    fin: int
    registro: str = None


@dataclass
class Asignacion:
    bloque: str
    intervalos: list = field(default_factory=list)
    registros: dict = field(default_factory=dict)     # nombre -> registro
    derramadas: list = field(default_factory=list)    # sin registro: se quedan en la pila

    @property
    def usados(self):
        return sorted(set(self.registros.values()), key=REGISTROS.index)


def asignar_registros(bloque, cuads, candidatos, parametros=(), registros=REGISTROS):
    """Linear scan (Poletto y Sarkar, 1999) sobre los intervalos de vida."""
    entrada, _ = variables_vivas(cuads)
    puntos = {}

    def marcar(x, i):
        if x in candidatos:
            a, b = puntos.get(x, (i, i))
            puntos[x] = (min(a, i), max(b, i))

    for p in parametros:
        marcar(p, 0)
    for i, c in enumerate(cuads):
        for x in entrada[i]:
            marcar(x, i)
        _, d = usos_y_definicion(c)
        if isinstance(d, str):
            marcar(d, i)
    intervalos = sorted((Intervalo(x, a, b) for x, (a, b) in puntos.items()), key=lambda v: (v.inicio, v.nombre))
    asig = Asignacion(bloque, intervalos)
    activos, libres = [], list(registros)
    for iv in intervalos:
        for viejo in [a for a in activos if a.fin < iv.inicio]:
            activos.remove(viejo)
            libres.append(viejo.registro)
            libres.sort(key=registros.index)
        if libres:
            iv.registro = libres.pop(0)
            activos.append(iv)
        else:
            # Se derrama el intervalo que termina más tarde: libera el registro por más tiempo.
            peor = max(activos, key=lambda a: a.fin)
            if peor.fin > iv.fin:
                iv.registro, peor.registro = peor.registro, None
                activos.remove(peor)
                activos.append(iv)
                asig.derramadas.append(peor.nombre)
            else:
                asig.derramadas.append(iv.nombre)
    asig.registros = {iv.nombre: iv.registro for iv in intervalos if iv.registro}
    return asig


# ====================================================================== traductor
class Traductor:
    def __init__(self, prog, analisis, plataforma="linux", con_registros=True):
        if prog.dominio != PROGRAMA:
            raise NoSoportado(f"el dominio '{prog.dominio}' se ejecuta en EmoVM; el código objeto "
                              "solo traduce programas con 'funcion principal'")
        self.prog = prog
        self.abi = PLATAFORMAS[plataforma]
        self.con_registros = con_registros
        self.tabla = construir_direcciones(prog)
        self.retornos = {n: f.retorno for n, f in analisis.funciones.items()}
        self.bloques = {n: resolver(c) for n, c in prog.bloques.items()}
        self.literales = {}          # (clase, valor) -> etiqueta
        self.globales = {e.nombre: e for e in self.tabla.datos}
        self.asignaciones = {}
        self.lineas = []
        self.n_etq = 0
        self.instrucciones = 0

    # ------------------------------------------------------------- salida
    def _e(self, texto):
        self.lineas.append("    " + texto)
        self.instrucciones += 1

    def _comentario(self, texto):
        self.lineas.append(f"    # {texto}")

    def _etq(self, nombre):
        self.lineas.append(f"{nombre}:")

    def _nueva_etq(self, pista):
        self.n_etq += 1
        return f".L{pista}_{self.n_etq}"

    # ------------------------------------------------------------- tipos y lugares
    def tipo(self, x):
        if isinstance(x, Constante):
            return x.tipo
        if es_temporal(x):
            if x.startswith("c"):
                return "int"
            return self.prog.tipos.get((self.bloque, x))
        return self.prog.tipos.get(x)

    def _entrada(self, x):
        return self.tabla.buscar(self.bloque, x)

    def es_agregado(self, x):
        t = self.tipo(x)
        return t is not None and (es_arreglo(t) or t in self.prog.estructuras)

    def es_referencia(self, x):
        """Un arreglo o estructura recibido como parámetro (o en un temporal) es un apuntador."""
        e = self._entrada(x)
        return es_temporal(x) or (e is not None and e.categoria == "parametro")

    def lugar(self, x):
        """Operando de memoria o registro donde vive la variable x."""
        if x in self.registros:
            return self.registros[x]
        e = self._entrada(x)
        if e is None:
            raise NoSoportado(f"'{x}' no tiene dirección (¿métrica de un dominio?)")
        if e.direccion.startswith("["):
            return f"qword ptr {e.direccion}"
        return f"qword ptr [rip + g_{_etiqueta(x)}]"

    def _direccion_agregado(self, x):
        e = self._entrada(x)
        if e.direccion.startswith("["):
            return e.direccion
        return f"[rip + g_{_etiqueta(x)}]"

    def literal(self, k):
        v = k.valor
        if isinstance(v, str):
            clave = ("str", v)
            prefijo = "str"
        else:
            v = float(v)
            clave = ("flt", v)
            prefijo = "flt"
        if clave not in self.literales:
            self.literales[clave] = f"{prefijo}_{len(self.literales) + 1}"
        return self.literales[clave]

    # ------------------------------------------------------------- cargas y guardados
    def cargar(self, x, reg):
        """Copia los 8 bytes de x a un registro entero (sin convertir el tipo)."""
        if isinstance(x, Constante):
            v = x.valor
            if isinstance(v, bool):
                self._e(f"mov {reg}, {int(v)}")
            elif isinstance(v, str):
                self._e(f"lea {reg}, [rip + {self.literal(x)}]")
            elif es_flotante(x.tipo) or isinstance(v, float):
                self._e(f"mov {reg}, qword ptr [rip + {self.literal(x)}]")
            elif -2**31 <= v < 2**31:
                self._e(f"mov {reg}, {v}")
            else:
                self._e(f"movabs {reg}, {v}")
            return
        if self.es_agregado(x) and not self.es_referencia(x):
            self._e(f"lea {reg}, {self._direccion_agregado(x)}")
            return
        lugar = self.lugar(x)
        if lugar != reg:
            self._e(f"mov {reg}, {lugar}")

    def cargar_flt(self, x, xmm):
        """Deja x en un registro xmm como decimal; convierte si x es entero."""
        if es_flotante(self.tipo(x)):
            if isinstance(x, Constante):
                self._e(f"movsd {xmm}, qword ptr [rip + {self.literal(x)}]")
            else:
                self._e(f"movsd {xmm}, {self.lugar(x)}")
        else:
            self.cargar(x, "rax")
            self._e(f"cvtsi2sd {xmm}, rax")

    def guardar(self, reg, x):
        lugar = self.lugar(x)
        if lugar != reg:
            self._e(f"mov {lugar}, {reg}")

    def guardar_flt(self, xmm, x):
        self._e(f"movsd {self.lugar(x)}, {xmm}")

    def cargar_como(self, x, tipo_destino, reg):
        """Carga x en reg con la representación del tipo destino (entero -> decimal)."""
        if es_flotante(tipo_destino) and not es_flotante(self.tipo(x)):
            self.cargar_flt(x, "xmm0")
            self._e(f"movq {reg}, xmm0")
        else:
            self.cargar(x, reg)

    def copiar(self, x, destino):
        if self.es_agregado(destino) and not self.es_referencia(destino):
            raise NoSoportado(f"no se puede reasignar el arreglo o estructura '{destino}'")
        if es_flotante(self.tipo(destino)) and not es_flotante(self.tipo(x)):
            self.cargar_flt(x, "xmm0")
            self.guardar_flt("xmm0", destino)
        elif destino in self.registros:
            self.cargar(x, self.registros[destino])
        else:
            self.cargar(x, "rax")
            self.guardar("rax", destino)

    # ------------------------------------------------------------- funciones
    def _candidatos(self, cuads):
        """Variables del marco que pueden vivir en un registro entero."""
        marco = self.tabla.marcos.get(self.bloque)
        nombres = set()
        for e in (marco.entradas if marco else []):
            t = self.tipo(e.nombre)
            if es_flotante(t) or t is None and not e.nombre.startswith("c"):
                continue
            if self.es_agregado(e.nombre) and e.categoria != "parametro":
                continue
            nombres.add(e.nombre)
        return nombres

    def _ubicar_argumentos(self, tipos):
        """Dónde va cada argumento: ('reg', nombre) o ('pila', índice de palabra)."""
        abi, lugares = self.abi, []
        ni = nf = npila = 0
        for i, t in enumerate(tipos):
            flt = es_flotante(t)
            if abi.posicional:
                if i < len(abi.enteros):
                    lugares.append(("reg", (abi.flotantes if flt else abi.enteros)[i]))
                else:
                    lugares.append(("pila", i))
            elif flt and nf < len(abi.flotantes):
                lugares.append(("reg", abi.flotantes[nf]))
                nf += 1
            elif not flt and ni < len(abi.enteros):
                lugares.append(("reg", abi.enteros[ni]))
                ni += 1
            else:
                lugares.append(("pila", npila))
                npila += 1
        return lugares

    def _espacio_salida(self, cuads):
        """Bytes que reserva el marco para los argumentos de las llamadas que hace."""
        maximo = 0
        for c in cuads:
            if c.op == "call" and c.a1 in self.prog.funciones:
                tipos = [self.tipo(p) for p in self.prog.funciones[c.a1]["params"]]
                pila = [x for k, x in self._ubicar_argumentos(tipos) if k == "pila"]
                maximo = max(maximo, 8 * (max(pila) + 1) if pila else 0)
        return _al16(max(maximo, self.abi.sombra) if self.abi.sombra else maximo)

    def funcion(self, bloque, etiqueta, params=(), retorno="void"):
        self.bloque = bloque
        cuads = self.bloques[bloque]
        self.retorno = retorno
        self.registros = {}
        if self.con_registros:
            asig = asignar_registros(bloque, cuads, self._candidatos(cuads), params)
            self.asignaciones[bloque] = asig
            self.registros = asig.registros
            guardados = asig.usados
        else:
            guardados = []
        marco = self.tabla.marcos[bloque].bytes
        salida = self._espacio_salida(cuads)
        total = _al16(marco + 8 * len(guardados) + salida)
        self.fin = f".Lfin_{etiqueta}"
        self.errores = []

        self.lineas.append("")
        self.lineas.append(f"    # ---- {bloque}: marco de {marco} bytes, "
                           f"{len(guardados)} registro(s) preservado(s), {salida} bytes para argumentos")
        self._etq(etiqueta)
        self._e("push rbp")
        self._e("mov rbp, rsp")
        if total:
            self._e(f"sub rsp, {total}")
        guardar_en = {r: f"qword ptr [rbp-{marco + 8 * (i + 1)}]" for i, r in enumerate(guardados)}
        for r, lugar in guardar_en.items():
            self._e(f"mov {lugar}, {r}")
        # Los argumentos llegan en registros o en la pila de quien llama.
        for p, (clase, donde) in zip(params, self._ubicar_argumentos([self.tipo(p) for p in params])):
            if clase == "reg" and donde.startswith("xmm"):
                self._e(f"movsd {self.lugar(p)}, {donde}")
            elif clase == "reg":
                self.guardar(donde, p)
            else:
                self._e(f"mov rax, qword ptr [rbp+{16 + 8 * donde}]")
                self.guardar("rax", p)

        destinos = {c.res for c in cuads if c.op in ("goto", "gotoF")}
        self.argumentos = []
        for i, c in enumerate(cuads, 1):
            if i in destinos:
                self._etq(f".L{etiqueta}_{i}")
            self._comentario(f"{i:>3}  {c}")
            self.cuadrupla(c, etiqueta)

        self._etq(self.fin)
        for r, lugar in guardar_en.items():
            self._e(f"mov {r}, {lugar}")
        self._e("leave")
        self._e("ret")
        for etq, instrucciones in self.errores:
            self._etq(etq)
            for ins in instrucciones:
                self._e(ins)

    # ------------------------------------------------------------- cuádruplas
    def cuadrupla(self, c, etiqueta):
        op = c.op
        a = self.abi.a
        if op == "=":
            self.copiar(c.a1, c.res)
        elif op in ("+", "-", "*"):
            self._aritmetica(c)
        elif op == "/":
            self._division(c)
        elif op in ("<", "<=", ">", ">=", "==", "!="):
            self._comparacion(c)
        elif op in ("y", "o"):
            self.cargar(c.a1, "rax")
            self.cargar(c.a2, "rcx")
            self._e(f"{'and' if op == 'y' else 'or'} rax, rcx")
            self.guardar("rax", c.res)
        elif op == "no":
            self.cargar(c.a1, "rax")
            self._e("xor rax, 1")
            self.guardar("rax", c.res)
        elif op == "neg":
            if es_flotante(self.tipo(c.res)):
                self.cargar_flt(c.a1, "xmm1")
                self._e("xorpd xmm0, xmm0")
                self._e("subsd xmm0, xmm1")
                self.guardar_flt("xmm0", c.res)
            else:
                self.cargar(c.a1, "rax")
                self._e("neg rax")
                self.guardar("rax", c.res)
        elif op == "shl":
            self.cargar(c.a1, "rax")
            if isinstance(c.a2, Constante):
                self._e(f"shl rax, {c.a2.valor}")
            else:
                self.cargar(c.a2, "rcx")
                self._e("shl rax, cl")
            if es_flotante(self.tipo(c.res)):
                # La reducción de fuerza puede cambiar (decimal * 2^k) por shl: se convierte al final.
                self._e("cvtsi2sd xmm0, rax")
                self.guardar_flt("xmm0", c.res)
            else:
                self.guardar("rax", c.res)
        elif op == "texto":
            self._texto(c)
        elif op == "concat":
            self.cargar(c.a1, a[0])
            self.cargar(c.a2, a[1])
            self._e("call emo_concat")
            self.guardar("rax", c.res)
        elif op == "gotoF":
            destino = f".L{etiqueta}_{c.res}"
            if isinstance(c.a1, Constante):
                if not c.a1.valor:
                    self._e(f"jmp {destino}")
            else:
                self.cargar(c.a1, "rax")
                self._e("test rax, rax")
                self._e(f"je {destino}")
        elif op == "goto":
            self._e(f"jmp .L{etiqueta}_{c.res}")
        elif op == "param":
            self.argumentos.append(c.a1)
        elif op == "call":
            args, self.argumentos = self.argumentos, []
            self._llamada(c, args)
        elif op == "retv":
            if es_flotante(self.retorno):
                self.cargar_flt(c.a1, "xmm0")
            else:
                self.cargar(c.a1, "rax")
            self._e(f"jmp {self.fin}")
        elif op == "ret":
            if self.retorno == "void":
                self._e("xor eax, eax")
            self._e(f"jmp {self.fin}")
        elif op == "chk_rep":
            err = self._nueva_etq("rep")
            self.cargar(c.a1, "rax")
            self._e(f"cmp rax, {MAX_REPETIR}")
            self._e(f"jg {err}")
            self.errores.append((err, ["call emo_error_repetir"]))
        elif op == "alloc":
            self._reservar(c.res, c.a1)
        elif op == "alloc_e":
            self._reservar(c.res, None, len(self.prog.estructuras[c.a1]))
        elif op == "[]":
            self._indice(c.a1, c.a2)
            self._e("mov r10, qword ptr [rax + rcx*8 + 8]")
            self.guardar("r10", c.res)
        elif op == "[]=":
            self.cargar_como(c.a1, elemento(self.tipo(c.res)), "r10")
            self._indice(c.res, c.a2)
            self._e("mov qword ptr [rax + rcx*8 + 8], r10")
        elif op == "campo":
            self.cargar(c.a1, "rax")
            self._e(f"mov r10, qword ptr [rax + {self._campo(c.a2)}]")
            self.guardar("r10", c.res)
        elif op == "campo=":
            estructura, nombre = c.a2.split(".")
            self.cargar_como(c.a1, self.prog.estructuras[estructura][nombre], "r10")
            self.cargar(c.res, "rax")
            self._e(f"mov qword ptr [rax + {self._campo(c.a2)}], r10")
        else:
            raise NoSoportado(f"la cuádrupla '{op}' es propia de un dominio y se ejecuta en EmoVM")

    def _campo(self, nombre):
        estructura, campo = nombre.split(".")
        return 8 * list(self.prog.estructuras[estructura]).index(campo)

    def _aritmetica(self, c):
        flt = es_flotante(self.tipo(c.res)) or es_flotante(self.tipo(c.a1)) or es_flotante(self.tipo(c.a2))
        if flt:
            self.cargar_flt(c.a1, "xmm0")
            self.cargar_flt(c.a2, "xmm1")
            self._e({"+": "addsd", "-": "subsd", "*": "mulsd"}[c.op] + " xmm0, xmm1")
            self.guardar_flt("xmm0", c.res)
            return
        destino = self.registros.get(c.res, "rax")
        if destino != "rax" and c.a2 == c.res and c.a1 != c.res:
            destino = "rax"          # el segundo operando se leería ya modificado
        self.cargar(c.a1, destino)
        instr = {"+": "add", "-": "sub", "*": "imul"}[c.op]
        if isinstance(c.a2, Constante) and -2**31 <= int(c.a2.valor) < 2**31:
            self._e(f"{instr} {destino}, {int(c.a2.valor)}")
        else:
            self._e(f"{instr} {destino}, {self._operando_ent(c.a2, 'rcx')}")
        self.guardar(destino, c.res)

    def _operando_ent(self, x, auxiliar):
        """Un operando entero directo: registro o memoria (carga constantes y agregados)."""
        if not isinstance(x, Constante) and x in self.registros:
            return self.registros[x]
        if isinstance(x, Constante) or (self.es_agregado(x) and not self.es_referencia(x)):
            self.cargar(x, auxiliar)
            return auxiliar
        return self.lugar(x)

    def _division(self, c):
        err = self._nueva_etq("div0")
        self.cargar_flt(c.a1, "xmm0")
        self.cargar_flt(c.a2, "xmm1")
        self._e("xorpd xmm2, xmm2")
        self._e("ucomisd xmm1, xmm2")
        siguiente = self._nueva_etq("div")
        self._e(f"jp {siguiente}")
        self._e(f"je {err}")
        self._etq(siguiente)
        self._e("divsd xmm0, xmm1")
        self.guardar_flt("xmm0", c.res)
        self.errores.append((err, ["call emo_error_division"]))

    def _comparacion(self, c):
        t1, t2 = self.tipo(c.a1), self.tipo(c.a2)
        if t1 == "string" or t2 == "string":
            a = self.abi.a
            self.cargar(c.a1, a[0])
            self.cargar(c.a2, a[1])
            self._e(f"call strcmp{'@PLT' if self.abi.nombre == 'linux' else ''}")
            self._e("movsxd rax, eax")
            self._e("cmp rax, 0")
            self._poner(c.op, c.res)
        elif es_flotante(t1) or es_flotante(t2):
            self.cargar_flt(c.a1, "xmm0")
            self.cargar_flt(c.a2, "xmm1")
            # Con NaN, ucomisd deja «no ordenado»; seta/setae dan falso, como en Python.
            if c.op in ("<", "<="):
                self._e("ucomisd xmm1, xmm0")
                self._e("seta al" if c.op == "<" else "setae al")
            elif c.op in (">", ">="):
                self._e("ucomisd xmm0, xmm1")
                self._e("seta al" if c.op == ">" else "setae al")
            elif c.op == "==":
                self._e("ucomisd xmm0, xmm1")
                self._e("sete al")
                self._e("setnp cl")
                self._e("and al, cl")
            else:
                self._e("ucomisd xmm0, xmm1")
                self._e("setne al")
                self._e("setp cl")
                self._e("or al, cl")
            self._e("movzx eax, al")
            self.guardar("rax", c.res)
        else:
            self.cargar(c.a1, "rax")
            if isinstance(c.a2, Constante) and -2**31 <= int(c.a2.valor) < 2**31:
                self._e(f"cmp rax, {int(c.a2.valor)}")
            else:
                self._e(f"cmp rax, {self._operando_ent(c.a2, 'rcx')}")
            self._poner(c.op, c.res)

    def _poner(self, op, res):
        cc = {"<": "l", "<=": "le", ">": "g", ">=": "ge", "==": "e", "!=": "ne"}[op]
        self._e(f"set{cc} al")
        self._e("movzx eax, al")
        self.guardar("rax", res)

    def _texto(self, c):
        t = c.a2
        a = self.abi.a
        if t == "string":
            self.copiar(c.a1, c.res)
            return
        if es_flotante(t):
            self.cargar_flt(c.a1, "xmm0")
            rutina = {"decimal": "emo_texto_decimal", "proporcion": "emo_texto_proporcion",
                      "duracion": "emo_texto_duracion"}[t]
        elif t == "bool":
            self.cargar(c.a1, a[0])
            rutina = "emo_texto_bool"
        elif t == "int":
            self.cargar(c.a1, a[0])
            rutina = "emo_texto_int"
        else:
            raise NoSoportado(f"no se puede convertir {t} a texto")
        self._e(f"call {rutina}")
        self.guardar("rax", c.res)

    def _indice(self, base, indice):
        """Deja la dirección del arreglo en rax y el índice revisado en rcx."""
        err = self._nueva_etq("indice")
        self.cargar(base, "rax")
        self.cargar(indice, "rcx")
        self._e("cmp rcx, qword ptr [rax]")
        self._e(f"jae {err}")       # sin signo: un índice negativo también queda fuera
        a = self.abi.a
        self.errores.append((err, [f"mov {a[1]}, qword ptr [rax]", f"mov {a[0]}, rcx" if a[0] != "rcx" else "nop",
                                   "call emo_error_indice"]))

    def _reservar(self, destino, n, campos=None):
        if self.es_referencia(destino):
            raise NoSoportado(f"'{destino}' no tiene espacio propio para reservar")
        self._e(f"lea rax, {self._direccion_agregado(destino)}")
        if campos is None:
            if not isinstance(n, Constante):
                raise NoSoportado("un arreglo debe tener tamaño constante")
            self._e(f"mov qword ptr [rax], {n.valor}")
            palabras, inicio = n.valor, 8
        else:
            palabras, inicio = campos, 0
        for i in range(palabras):
            self._e(f"mov qword ptr [rax + {inicio + 8 * i}], 0")

    # ------------------------------------------------------------- llamadas
    def _llamada(self, c, args):
        nombre = c.a1
        a = self.abi.a
        if nombre in self.prog.funciones:
            params = self.prog.funciones[nombre]["params"]
            tipos = [self.tipo(p) for p in params]
            for x, t, (clase, donde) in zip(args, tipos, self._ubicar_argumentos(tipos)):
                if clase == "reg" and donde.startswith("xmm"):
                    self.cargar_flt(x, donde)
                elif clase == "reg":
                    self.cargar_como(x, t, donde)
                else:
                    self.cargar_como(x, t, "rax")
                    desplazamiento = self.abi.sombra + 8 * (donde - (len(a) if self.abi.posicional else 0))
                    self._e(f"mov qword ptr [rsp+{desplazamiento}], rax")
            self._e(f"call f_{_etiqueta(nombre)}")
            if c.res is not None:
                if es_flotante(self.retornos.get(nombre)):
                    self.guardar_flt("xmm0", c.res)
                else:
                    self.guardar("rax", c.res)
            return
        if nombre in ("mostrar", "registrar"):
            for i, x in enumerate(args):
                if i:
                    self._e(f"lea {a[0]}, [rip + {self.literal(Constante(' ', 'string'))}]")
                    self._e("call emo_escribir")
                self.cargar(x, a[0])
                self._e("call emo_escribir")
            self._e("call emo_fin_linea")
            return
        x = args[0] if args else None
        res = c.res
        if nombre in ("a_int",):
            if es_flotante(self.tipo(x)):
                self.cargar_flt(x, "xmm0")
                self._e("cvttsd2si rax, xmm0")
                self.guardar("rax", res)
            else:
                self.copiar(x, res)
        elif nombre in ("a_decimal", "a_ms"):
            self.cargar_flt(x, "xmm0")
            self.guardar_flt("xmm0", res)
        elif nombre in ("a_porcentaje", "a_proporcion", "a_s"):
            factor = {"a_porcentaje": 100.0, "a_proporcion": 100.0, "a_s": 1000.0}[nombre]
            self.cargar_flt(x, "xmm0")
            self._e(f"movsd xmm1, qword ptr [rip + {self.literal(Constante(factor, 'decimal'))}]")
            self._e("mulsd xmm0, xmm1" if nombre == "a_porcentaje" else "divsd xmm0, xmm1")
            self.guardar_flt("xmm0", res)
        elif nombre == "abs":
            if es_flotante(self.tipo(x)):
                self.cargar_flt(x, "xmm0")
                self._e("xorpd xmm1, xmm1")
                self._e("subsd xmm1, xmm0")
                self._e("maxsd xmm0, xmm1")
                self.guardar_flt("xmm0", res)
            else:
                self.cargar(x, "rax")
                self._e("mov rcx, rax")
                self._e("neg rcx")
                self._e("cmovns rax, rcx")
                self.guardar("rax", res)
        else:
            raise NoSoportado(f"la función '{nombre}' es propia de un dominio y se ejecuta en EmoVM")

    # ------------------------------------------------------------- programa
    def traducir(self):
        funciones = self.prog.funciones
        if "principal" not in funciones:
            raise NoSoportado("el programa no tiene 'funcion principal'")
        cuerpo_inicio = len(self.lineas)
        if self.bloques.get("init") and any(c.op != "ret" for c in self.bloques["init"]):
            self.funcion("init", "emo_inicio")
            hay_inicio = True
        else:
            hay_inicio = False
        for nombre, f in funciones.items():
            self.funcion(f["bloque"], f"f_{_etiqueta(nombre)}", f["params"], self.retornos.get(nombre, "void"))
        cuerpo = self.lineas[cuerpo_inicio:]

        principal = [
            "",
            "    # ---- punto de entrada: inicializa los globales y llama a principal",
            "main:",
            "    push rbp",
            "    mov rbp, rsp",
            f"    sub rsp, {max(16, self.abi.sombra)}",
        ]
        if hay_inicio:
            principal.append("    call emo_inicio")
        principal.append("    call f_principal")
        if self.retornos.get("principal", "void") not in ("int",):
            principal.append("    xor eax, eax")
        principal += ["    leave", "    ret"]

        salida = [
            f"# EmoLang -> ensamblador x86-64 ({self.abi.nombre}), sintaxis Intel de GNU as",
            f"# Generado por 'python -m emolang ensamblador'. Ensamblar con: gcc programa{EXT_ASM} -o programa{self.abi.exe}",
            "    .intel_syntax noprefix",
            "",
            "# ======================== segmento de datos: variables globales",
            "    .data",
            "    .p2align 3",
        ]
        for e in self.tabla.datos:
            if e.categoria == "metrica":
                raise NoSoportado(f"la métrica '{e.nombre}' solo existe en un dominio")
            salida.append(f"g_{_etiqueta(e.nombre)}:  .zero {e.bytes}    # {e.nombre} : {e.tipo}")
        salida += [
            "",
            "# ======================== literales de solo lectura",
            f"    {self.abi.rodata}",
            "    .p2align 3",
        ]
        for (clase, v), etq in self.literales.items():
            if clase == "flt":
                bits = struct.unpack("<Q", struct.pack("<d", v))[0]
                salida.append(f"{etq}:  .quad 0x{bits:016x}    # {v!r}")
            else:
                salida.append(f"{etq}:  .byte {_bytes_asm(v)}    # {v!r}")
        salida += runtime_datos(self.abi)
        salida += [
            "",
            "# ======================== segmento de código",
            "    .text",
            "    .globl main",
        ]
        salida += principal + cuerpo + runtime_codigo(self.abi)
        if self.abi.nombre == "linux":
            salida.append('    .section .note.GNU-stack,"",@progbits')
        return "\n".join(salida) + "\n"


# ====================================================================== runtime
def runtime_datos(abi):
    textos = {
        "rt_fmt_s": "%s", "rt_fmt_int": "%lld", "rt_fmt_dec": "%.3f", "rt_fmt_prop": "%.1f%%",
        "rt_fmt_seg": "%g s", "rt_fmt_ms": "%g ms", "rt_verdadero": "verdadero", "rt_falso": "falso",
        "rt_cero": "0",
        "rt_err_fmt": "Error en tiempo de ejecución: %s\n",
        "rt_err_indice": "Error en tiempo de ejecución: índice %lld fuera de rango: el arreglo tiene %lld elementos\n",
        "rt_err_div": "división entre cero",
        "rt_err_rep": f"'repetir' excede el máximo de {MAX_REPETIR} vueltas por cuadro",
    }
    lineas = ["", "# ---- textos del runtime"]
    for etq, t in textos.items():
        lineas.append(f"{etq}:  .byte {_bytes_asm(t)}")
    lineas += [
        "    .p2align 3",
        "rt_mil:  .quad 0x408f400000000000    # 1000.0",
        "rt_cien: .quad 0x4059000000000000    # 100.0",
    ]
    return lineas


def runtime_codigo(abi):
    a1, a2, a3, a4 = abi.enteros[:4]
    lin = abi.nombre == "linux"
    llamada = "@PLT" if lin else ""

    def fmt_decimal(etq_fmt, n=48):
        """snprintf(buf, n, fmt, xmm0): en Windows un decimal variádico va también en el registro entero."""
        cuerpo = [
            "push rbp", "mov rbp, rsp", "sub rsp, 48",
            "movsd qword ptr [rbp-8], xmm0",
            f"mov {a1}, {n}", f"call malloc{llamada}", "mov qword ptr [rbp-16], rax",
            f"mov {a1}, rax", f"mov {a2}, {n}", f"lea {a3}, [rip + {etq_fmt}]",
        ]
        if lin:
            cuerpo += ["movsd xmm0, qword ptr [rbp-8]", "mov eax, 1"]
        else:
            cuerpo += ["movsd xmm3, qword ptr [rbp-8]", "mov r9, qword ptr [rbp-8]"]
        cuerpo += [f"call snprintf{llamada}", "mov rax, qword ptr [rbp-16]"]
        return cuerpo

    rutinas = {
        "emo_escribir": [            # escribir(texto): printf("%s", texto)
            "push rbp", "mov rbp, rsp", "sub rsp, 32",
            f"mov {a2}, {a1}", f"lea {a1}, [rip + rt_fmt_s]", "xor eax, eax", f"call printf{llamada}",
            "leave", "ret"],
        "emo_fin_linea": [
            "push rbp", "mov rbp, rsp", "sub rsp, 32",
            f"mov {a1}, 10", f"call putchar{llamada}", "leave", "ret"],
        "emo_texto_int": [
            "push rbp", "mov rbp, rsp", "sub rsp, 48", f"mov qword ptr [rbp-8], {a1}",
            f"mov {a1}, 32", f"call malloc{llamada}", "mov qword ptr [rbp-16], rax",
            f"mov {a1}, rax", f"mov {a2}, 32", f"lea {a3}, [rip + rt_fmt_int]", f"mov {a4}, qword ptr [rbp-8]",
            "xor eax, eax", f"call snprintf{llamada}", "mov rax, qword ptr [rbp-16]", "leave", "ret"],
        "emo_texto_bool": [
            "lea rax, [rip + rt_verdadero]", f"test {a1}, {a1}", "jne 1f", "lea rax, [rip + rt_falso]",
            "1:", "ret"],
        # Igual que Python: f"{v:.3f}".rstrip("0").rstrip(".") y «-0» se escribe «0».
        "emo_texto_decimal": fmt_decimal("rt_fmt_dec") + [
            f"mov {a1}, rax", f"call strlen{llamada}",
            "mov rcx, qword ptr [rbp-16]", "lea rdx, [rcx + rax - 1]",
            "2:", "cmp byte ptr [rdx], 48", "jne 3f", "mov byte ptr [rdx], 0", "dec rdx", "jmp 2b",
            "3:", "cmp byte ptr [rdx], 46", "jne 4f", "mov byte ptr [rdx], 0",
            "4:", "cmp word ptr [rcx], 0x302d", "jne 5f", "cmp byte ptr [rcx + 2], 0", "jne 5f",
            "lea rax, [rip + rt_cero]", "leave", "ret",
            "5:", "mov rax, rcx", "leave", "ret"],
        "emo_texto_proporcion": ["mulsd xmm0, qword ptr [rip + rt_cien]"],   # cae en la siguiente
        "emo_texto_proporcion_": fmt_decimal("rt_fmt_prop") + ["leave", "ret"],
        "emo_texto_duracion": [
            "movsd xmm1, xmm0", "xorpd xmm2, xmm2", "subsd xmm2, xmm0", "maxsd xmm1, xmm2",  # |v|
            "ucomisd xmm1, qword ptr [rip + rt_mil]", "jb emo_texto_ms",
            "divsd xmm0, qword ptr [rip + rt_mil]", "jmp emo_texto_seg"],
        "emo_texto_seg": fmt_decimal("rt_fmt_seg") + ["leave", "ret"],
        "emo_texto_ms": fmt_decimal("rt_fmt_ms") + ["leave", "ret"],
        "emo_concat": [
            "push rbp", "mov rbp, rsp", "sub rsp, 64",
            f"mov qword ptr [rbp-8], {a1}", f"mov qword ptr [rbp-16], {a2}",
            f"call strlen{llamada}", "mov qword ptr [rbp-24], rax",
            f"mov {a1}, qword ptr [rbp-16]", f"call strlen{llamada}",
            f"mov rcx, qword ptr [rbp-24]", f"lea {a1}, [rax + rcx + 1]", f"call malloc{llamada}",
            "mov qword ptr [rbp-32], rax",
            f"mov {a1}, rax", f"mov {a2}, qword ptr [rbp-8]", f"call strcpy{llamada}",
            f"mov {a1}, qword ptr [rbp-32]", f"mov {a2}, qword ptr [rbp-16]", f"call strcat{llamada}",
            "mov rax, qword ptr [rbp-32]", "leave", "ret"],
        "emo_error_texto": [
            "push rbp", "mov rbp, rsp", "sub rsp, 32",
            f"mov {a2}, {a1}", f"lea {a1}, [rip + rt_err_fmt]", "xor eax, eax", f"call printf{llamada}",
            f"mov {a1}, 1", f"call exit{llamada}"],
        "emo_error_division": [f"lea {a1}, [rip + rt_err_div]", "jmp emo_error_texto"],
        "emo_error_repetir": [f"lea {a1}, [rip + rt_err_rep]", "jmp emo_error_texto"],
        "emo_error_indice": [
            "push rbp", "mov rbp, rsp", "sub rsp, 32",
            f"mov {a3}, {a2}", f"mov {a2}, {a1}", f"lea {a1}, [rip + rt_err_indice]", "xor eax, eax",
            f"call printf{llamada}", f"mov {a1}, 1", f"call exit{llamada}"],
    }
    lineas = ["", "# ======================== runtime: texto, salida y errores"]
    for nombre, cuerpo in rutinas.items():
        lineas.append(f"{nombre}:")
        for ins in cuerpo:
            lineas.append(ins if ins.endswith(":") and ins[:-1].isdigit() else "    " + ins)
    return lineas


# ====================================================================== interfaz
@dataclass
class CodigoObjeto:
    asm: str
    plataforma: str
    asignaciones: dict
    instrucciones: int


def generar(prog, analisis, plataforma=None, con_registros=True):
    t = Traductor(prog, analisis, plataforma or plataforma_local(), con_registros)
    asm = t.traducir()
    return CodigoObjeto(asm, t.abi.nombre, t.asignaciones, t.instrucciones)


def ensamblar(ruta_asm, ruta_exe, compilador=None):
    """Ensambla y enlaza con GCC. Devuelve (ok, mensajes)."""
    gcc = compilador or shutil.which("gcc")
    if not gcc:
        return False, "no se encontró gcc (en Windows: MSYS2 con mingw-w64-ucrt-x86_64-gcc)"
    p = subprocess.run([gcc, "-x", "assembler", ruta_asm, "-o", ruta_exe],
                       capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def ejecutar(ruta_exe, tiempo=30):
    p = subprocess.run([os.path.abspath(ruta_exe)], capture_output=True, timeout=tiempo)
    return p.returncode, p.stdout.decode("utf-8", errors="replace")
