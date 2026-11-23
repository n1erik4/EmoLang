"""Tabla de direcciones: dónde vive cada nombre durante la ejecución.

  datos      variables globales, variables de estado y métricas: dirección fija
  literales  cadenas y decimales constantes: dirección fija y solo lectura
  pila       parámetros, locales, temporales y contadores de cada bloque: desplazamiento
             respecto a rbp dentro del marco de pila (negativo porque la pila crece hacia abajo)

Cada valor simple ocupa 8 bytes. Un arreglo guarda su longitud seguida de sus elementos.
Un arreglo o estructura recibido como parámetro ocupa 8 bytes: es una referencia.
"""

from dataclasses import dataclass, field

from .intermedio import Constante, es_temporal
from .metricas import METRICAS
from .tipos import es_arreglo, tamano

PALABRA = 8


@dataclass
class Entrada:
    nombre: str
    tipo: str
    direccion: str
    bytes: int
    categoria: str


@dataclass
class Marco:
    bloque: str
    entradas: list = field(default_factory=list)
    bytes: int = 0                 # múltiplo de 16, como pide la convención de llamadas


@dataclass
class TablaDirecciones:
    datos: list = field(default_factory=list)
    literales: list = field(default_factory=list)
    marcos: dict = field(default_factory=dict)

    def buscar(self, bloque, nombre):
        marco = self.marcos.get(bloque)
        for e in (marco.entradas if marco else []):
            if e.nombre == nombre:
                return e
        for e in self.datos:
            if e.nombre == nombre:
                return e
        return None


def _bytes(tipo, estructuras, es_parametro=False):
    if es_parametro or tipo is None:
        return PALABRA
    if es_arreglo(tipo):
        n = tamano(tipo)
        return PALABRA if n is None else PALABRA * (n + 1)
    if tipo in estructuras:
        return PALABRA * max(1, len(estructuras[tipo]))
    return PALABRA


def construir(prog):
    tabla = TablaDirecciones()
    desplazamiento_datos = 0
    vistos_datos, vistos_literales = set(), {}
    locales_de = {f["bloque"]: nombre + "." for nombre, f in prog.funciones.items()}
    parametros = {f["bloque"]: f["params"] for f in prog.funciones.values()}

    def literal(k):
        if k.tipo == "string" or isinstance(k.valor, float):
            clave = (type(k.valor).__name__, k.valor)
            if clave not in vistos_literales:
                prefijo = "str" if isinstance(k.valor, str) else "flt"
                etiqueta = f"{prefijo}_{len(vistos_literales) + 1}"
                vistos_literales[clave] = etiqueta
                n = len(k.valor.encode("utf-8")) + 1 if isinstance(k.valor, str) else PALABRA
                tabla.literales.append(Entrada(str(k), k.tipo, etiqueta, n, "literal"))

    for nombre, bloque in prog.bloques.items():
        marco = Marco(nombre)
        fin = 0

        def en_marco(x, categoria, es_parametro=False):
            nonlocal fin
            if any(e.nombre == x for e in marco.entradas):
                return
            tipo = prog.tipos.get((nombre, x)) if es_temporal(x) else prog.tipos.get(x)
            n = _bytes(tipo, prog.estructuras, es_parametro)
            fin += n
            marco.entradas.append(Entrada(x, tipo or "", f"[rbp-{fin}]", n, categoria))

        for p in parametros.get(nombre, []):
            en_marco(p, "parametro", es_parametro=True)

        prefijo = locales_de.get(nombre)
        for c in bloque:
            usados = [getattr(c, f) for f in c.lecturas()]
            if c.escribe():
                usados.append(c.escribe())
            for x in usados:
                if isinstance(x, Constante):
                    literal(x)
                elif not isinstance(x, str):
                    continue
                elif es_temporal(x):
                    en_marco(x, "contador" if x.startswith("c") else "temporal")
                elif prefijo and x.startswith(prefijo):
                    en_marco(x, "local")
                elif x not in vistos_datos:
                    vistos_datos.add(x)
                    tipo = METRICAS[x].tipo if x in METRICAS else prog.tipos.get(x)
                    n = _bytes(tipo, prog.estructuras)
                    categoria = "metrica" if x in METRICAS else "global"
                    tabla.datos.append(Entrada(x, tipo or "", f"datos+{desplazamiento_datos}", n, categoria))
                    desplazamiento_datos += n
        marco.bytes = (fin + 15) // 16 * 16
        tabla.marcos[nombre] = marco
    return tabla
