"""Nodos del árbol de sintaxis abstracta (AST) de EmoLang."""

from dataclasses import dataclass, field, fields


@dataclass
class Nodo:
    linea: int = field(default=0, kw_only=True)
    columna: int = field(default=0, kw_only=True)
    # Anotado por el analizador semántico (tipo de una expresión).
    tipo: str = field(default=None, kw_only=True, repr=False, compare=False)


# ---------------------------------------------------------------- declaraciones
@dataclass
class Programa(Nodo):
    dominios: list


@dataclass
class Dominio(Nodo):
    nombre: str
    sensores: list
    variables: list
    gestos: list
    secuencias: list
    maquinas: list


@dataclass
class Sensor(Nodo):
    nombre: str
    variables: list


@dataclass
class DeclVar(Nodo):
    nombre: str
    tipo_decl: str
    valor: "Nodo"


@dataclass
class Gesto(Nodo):
    nombre: str
    condicion: "Nodo"
    minimo: "Nodo"          # expresión de duración (durante)
    maximo: "Nodo" = None   # expresión de duración (hasta), opcional
    tolerancia: "Nodo" = None  # interrupción máxima perdonada (tolerando), opcional


@dataclass
class Secuencia(Nodo):
    nombre: str
    gestos: list            # list[Identificador]
    ventana: "Nodo" = None  # duración máxima entre el primero y el último


@dataclass
class Maquina(Nodo):
    nombre: str
    inicial: str
    estados: list


@dataclass
class Estado(Nodo):
    nombre: str
    variables: list
    al_entrar: "Bloque"
    cuandos: list
    mientras: list
    ignorados: list = field(default_factory=list)   # list[Identificador]


@dataclass
class Cuando(Nodo):
    evento: str
    destino: str = None      # forma corta: cuando g ir_a X;
    cuerpo: "Bloque" = None  # forma larga: cuando g { ... }


@dataclass
class Mientras(Nodo):
    condicion: "Nodo"
    cuerpo: "Bloque"


# ------------------------------------------------------------------ sentencias
@dataclass
class Bloque(Nodo):
    sentencias: list


@dataclass
class Asignacion(Nodo):
    nombre: str
    valor: "Nodo"


@dataclass
class Si(Nodo):
    condicion: "Nodo"
    entonces: Bloque
    sino: "Nodo" = None      # Bloque o Si


@dataclass
class Repetir(Nodo):
    veces: "Nodo"
    cuerpo: Bloque


@dataclass
class IrA(Nodo):
    destino: str


@dataclass
class SentenciaLlamada(Nodo):
    llamada: "Llamada"


# ----------------------------------------------------------------- expresiones
@dataclass
class Literal(Nodo):
    valor: object
    tipo_lit: str            # int | decimal | bool | string | duracion | proporcion


@dataclass
class Identificador(Nodo):
    nombre: str


@dataclass
class Binaria(Nodo):
    op: str
    izq: Nodo
    der: Nodo


@dataclass
class Unaria(Nodo):
    op: str                  # '-' | 'no'
    operando: Nodo


@dataclass
class Llamada(Nodo):
    nombre: str
    args: list


# ------------------------------------------------------------- impresión del AST
def _hijos(nodo):
    for f in fields(nodo):
        if f.name in ("linea", "columna", "tipo"):
            continue
        yield f.name, getattr(nodo, f.name)


def arbol_texto(nodo, sangria="", nombre=None, ultimo=True, raiz=True):
    """Devuelve el AST como texto con forma de árbol."""
    lineas = []
    rama = "" if raiz else ("└── " if ultimo else "├── ")
    etiqueta = f"{nombre}: " if nombre else ""

    if isinstance(nodo, Nodo):
        simples = []
        compuestos = []
        for k, v in _hijos(nodo):
            if isinstance(v, (Nodo, list)):
                if v not in (None, []):
                    compuestos.append((k, v))
            elif v is not None:
                simples.append(f"{k}={v!r}")
        anot = f" : {nodo.tipo}" if nodo.tipo else ""
        lineas.append(f"{sangria}{rama}{etiqueta}{type(nodo).__name__}({', '.join(simples)}){anot}")
        nueva = sangria + ("" if raiz else ("    " if ultimo else "│   "))
        for i, (k, v) in enumerate(compuestos):
            lineas.append(arbol_texto(v, nueva, k, i == len(compuestos) - 1, False))
    elif isinstance(nodo, list):
        lineas.append(f"{sangria}{rama}{etiqueta}[{len(nodo)}]")
        nueva = sangria + ("" if raiz else ("    " if ultimo else "│   "))
        for i, v in enumerate(nodo):
            lineas.append(arbol_texto(v, nueva, None, i == len(nodo) - 1, False))
    else:
        lineas.append(f"{sangria}{rama}{etiqueta}{nodo!r}")
    return "\n".join(lineas)
