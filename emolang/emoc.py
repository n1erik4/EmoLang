"""Formato .emoc: el programa compilado que carga la máquina virtual EmoVM.

Es un documento JSON con, por cada dominio, las tablas de los autómatas, la tabla
de despacho de las máquinas de estado y los bloques de cuádruplas. Los saltos ya
están resueltos a números de cuádrupla y las constantes se escriben como {"k": v}.
"""

import json

from .intermedio import Constante, resolver

VERSION = 1


def _operando(x):
    return {"k": x.valor} if isinstance(x, Constante) else x


def serializar_bloque(cuadruplas):
    return [[c.op, _operando(c.a1), _operando(c.a2), _operando(c.res), c.linea]
            for c in resolver(cuadruplas)]


def construir(programas, automatas, optimizado=True):
    dominios = {}
    for nombre, prog in programas.items():
        por_nombre = {a.nombre: a for a in automatas.get(nombre, [])}
        dominios[nombre] = {
            "fps": prog.fps,
            "optimizado": optimizado,
            "gestos": [por_nombre[g].a_dict() for g in prog.gestos],
            "secuencias": [por_nombre[s].a_dict() for s in prog.secuencias],
            "diagramas": [a.a_dict() for a in automatas.get(nombre, []) if a.clase == "maquina"],
            "maquinas": prog.maquinas,
            "funciones": prog.funciones,
            "estructuras": prog.estructuras,
            "bloques": {b: serializar_bloque(c) for b, c in prog.bloques.items()},
        }
    return {"formato": "emoc", "version": VERSION, "dominios": dominios}


def guardar(emoc, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(emoc, f, ensure_ascii=False, indent=1)


def cargar(ruta):
    with open(ruta, encoding="utf-8") as f:
        emoc = json.load(f)
    if emoc.get("formato") != "emoc" or emoc.get("version") != VERSION:
        raise ValueError(f"{ruta} no es un archivo .emoc compatible (versión {VERSION})")
    return emoc
