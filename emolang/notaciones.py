"""Conversión de expresiones entre notación infija, postfija y prefija.

  infija -> postfija    algoritmo de patio de maniobras (Dijkstra), con una pila de operadores
  postfija -> árbol     pila de operandos, de izquierda a derecha
  prefija -> árbol      pila de operandos, de derecha a izquierda
  árbol -> cualquiera   recorrido en posorden, preorden o inorden con paréntesis mínimos

Usa los tokens del analizador léxico y la misma precedencia de la gramática:
    o < y < no < comparaciones < + - < * / < signo

Operadores de la forma postfija y prefija:
    neg     signo negativo (unario)
    no      negación (unario)
    []      elemento de un arreglo: v i []
    f/n     llamada a la función f con n argumentos: a b f/2
"""

import re

from .errores import Reporte
from .lexico import analizar as tokenizar

PRECEDENCIA = {"o": 1, "y": 2, "no": 3, "<": 4, "<=": 4, ">": 4, ">=": 4, "==": 4, "!=": 4,
               "+": 5, "-": 5, "*": 6, "/": 6, "neg": 7}
BINARIOS = {"o", "y", "<", "<=", ">", ">=", "==", "!=", "+", "-", "*", "/", "[]"}
UNARIOS = {"no", "neg"}
COMPARACIONES = {"<", "<=", ">", ">=", "==", "!="}
_TOKEN_TEXTO = re.compile(r'"(?:[^"\\]|\\.)*"|\S+')
_LLAMADA = re.compile(r"^(.+)/(\d+)$")


class ErrorNotacion(ValueError):
    pass


# ------------------------------------------------------------------ infija a postfija
def _unir_tokens(fuente):
    """Convierte los tokens del lexer en símbolos; junta unidades, campos y cadenas."""
    reporte = Reporte()
    tokens, _ = tokenizar(fuente, reporte)
    if reporte.errores:
        raise ErrorNotacion(reporte.errores[0].mensaje)
    tokens = tokens[:-1]  # sin EOF
    salida, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        sig = tokens[i + 1] if i + 1 < len(tokens) else None
        if t.tipo in ("ENTERO", "DECIMAL") and sig is not None and sig.tipo in ("MS", "S", "PORCIENTO"):
            salida.append(("valor", t.lexema + sig.lexema))
            i += 2
        elif t.tipo == "ID" and sig is not None and sig.tipo == "PUNTO":
            if i + 2 >= len(tokens) or tokens[i + 2].tipo != "ID":
                raise ErrorNotacion(f"se esperaba un campo después de '{t.lexema}.'")
            salida.append(("valor", f"{t.lexema}.{tokens[i + 2].lexema}"))
            i += 3
        elif t.tipo == "ID" and sig is not None and sig.tipo == "PAR_IZQ":
            salida.append(("funcion", t.lexema))
            i += 1
        elif t.tipo in ("ID", "ENTERO", "DECIMAL", "CADENA", "VERDADERO", "FALSO"):
            salida.append(("valor", t.lexema))
            i += 1
        elif t.lexema in PRECEDENCIA or t.tipo in ("PAR_IZQ", "PAR_DER", "COR_IZQ", "COR_DER", "COMA"):
            salida.append(("simbolo", t.lexema))
            i += 1
        else:
            raise ErrorNotacion(f"'{t.lexema}' no puede formar parte de una expresión")
    return salida


def infija_a_postfija(fuente):
    """Algoritmo de patio de maniobras. Devuelve la lista de símbolos en postfija."""
    salida, pila = [], []
    espera_operando = True      # para distinguir el signo de la resta

    def sacar_mientras(prec):
        sacados = []
        while pila and pila[-1] in PRECEDENCIA and PRECEDENCIA[pila[-1]] >= prec:
            sacados.append(pila.pop())
        salida.extend(sacados)
        return sacados

    for clase, s in _unir_tokens(fuente):
        if clase == "valor":
            if not espera_operando:
                raise ErrorNotacion(f"falta un operador antes de {s}")
            salida.append(s)
            espera_operando = False
        elif clase == "funcion":
            if not espera_operando:
                raise ErrorNotacion(f"falta un operador antes de {s}")
            pila.append(("llamada", s, 0))    # el número de argumentos se ajusta al cerrar
        elif s == "(":
            if not espera_operando:
                raise ErrorNotacion("falta un operador antes de '('")
            if pila and isinstance(pila[-1], tuple) and pila[-1][0] == "llamada" and pila[-1][2] == 0:
                pila[-1] = ("llamada", pila[-1][1], 1)
                pila.append("(llamada")
            else:
                pila.append("(")
        elif s == ")":
            while pila and pila[-1] not in ("(", "(llamada"):
                if isinstance(pila[-1], tuple) or pila[-1] == "[":
                    raise ErrorNotacion("paréntesis sin balancear")
                salida.append(pila.pop())
            if not pila:
                raise ErrorNotacion("sobra un ')'")
            if pila.pop() == "(llamada":
                _, nombre, args = pila.pop()
                if espera_operando:
                    if args != 1:
                        raise ErrorNotacion("falta un argumento en la llamada")
                    args = 0
                salida.append(f"{nombre}/{args}")
            elif espera_operando:
                raise ErrorNotacion("paréntesis vacíos")
            espera_operando = False
        elif s == ",":
            if espera_operando:
                raise ErrorNotacion("falta un argumento antes de ','")
            while pila and pila[-1] not in ("(", "(llamada", "["):
                salida.append(pila.pop())
            if not pila or pila[-1] != "(llamada":
                raise ErrorNotacion("una coma solo puede separar argumentos de una función")
            _, nombre, args = pila[-2]
            pila[-2] = ("llamada", nombre, args + 1)
            espera_operando = True
        elif s == "[":
            if espera_operando:
                raise ErrorNotacion("falta el arreglo antes de '['")
            pila.append("[")
            espera_operando = True
        elif s == "]":
            if espera_operando:
                raise ErrorNotacion("falta el índice del arreglo")
            while pila and pila[-1] != "[":
                if pila[-1] in ("(", "(llamada"):
                    raise ErrorNotacion("corchetes sin balancear")
                salida.append(pila.pop())
            if not pila:
                raise ErrorNotacion("sobra un ']'")
            pila.pop()
            salida.append("[]")
        elif s == "no":
            if not espera_operando:
                raise ErrorNotacion("falta un operador antes de 'no'")
            if pila and pila[-1] in PRECEDENCIA and PRECEDENCIA[pila[-1]] > PRECEDENCIA["no"]:
                raise ErrorNotacion(f"'no' necesita paréntesis después de '{pila[-1]}'")
            pila.append("no")         # asociativo a la derecha y prefijo: no saca nada
        elif s == "-" and espera_operando:
            pila.append("neg")
        else:
            if espera_operando:
                raise ErrorNotacion(f"falta un operando antes de '{s}'")
            sacados = sacar_mientras(PRECEDENCIA[s])
            if s in COMPARACIONES and any(o in COMPARACIONES for o in sacados):
                raise ErrorNotacion("las comparaciones no se pueden encadenar; use 'y'")
            pila.append(s)
            espera_operando = True
    if espera_operando:
        raise ErrorNotacion("la expresión está incompleta")
    while pila:
        tope = pila.pop()
        if tope in ("(", "(llamada", "[") or isinstance(tope, tuple):
            raise ErrorNotacion("paréntesis o corchetes sin cerrar")
        salida.append(tope)
    return salida


# ------------------------------------------------------------------ árbol
class Nodo:
    __slots__ = ("op", "hijos")

    def __init__(self, op, hijos=()):
        self.op = op
        self.hijos = list(hijos)


def _aridad(s):
    if s in BINARIOS:
        return 2
    if s in UNARIOS:
        return 1
    m = _LLAMADA.match(s)
    return int(m.group(2)) if m and not s.startswith('"') else 0


def separar(texto):
    """Separa una expresión postfija o prefija escrita como texto."""
    return _TOKEN_TEXTO.findall(texto) if isinstance(texto, str) else list(texto)


def postfija_a_arbol(simbolos):
    pila = []
    for s in separar(simbolos):
        n = _aridad(s)
        if len(pila) < n:
            raise ErrorNotacion(f"faltan operandos para '{s}'")
        hijos = pila[len(pila) - n:] if n else []
        if n:
            del pila[len(pila) - n:]
        pila.append(Nodo(s, hijos))
    if len(pila) != 1:
        raise ErrorNotacion("sobran operandos en la expresión")
    return pila[0]


def prefija_a_arbol(simbolos):
    pila = []
    for s in reversed(separar(simbolos)):
        n = _aridad(s)
        if len(pila) < n:
            raise ErrorNotacion(f"faltan operandos para '{s}'")
        hijos = [pila.pop() for _ in range(n)]
        pila.append(Nodo(s, hijos))
    if len(pila) != 1:
        raise ErrorNotacion("sobran operandos en la expresión")
    return pila[0]


def a_postfija(nodo):
    salida = []
    for h in nodo.hijos:
        salida.extend(a_postfija(h))
    salida.append(nodo.op)
    return salida


def a_prefija(nodo):
    salida = [nodo.op]
    for h in nodo.hijos:
        salida.extend(a_prefija(h))
    return salida


def a_infija(nodo, minimo=0):
    """Infija con solo los paréntesis necesarios."""
    op = nodo.op
    if op == "[]":
        return f"{a_infija(nodo.hijos[0], 8)}[{a_infija(nodo.hijos[1])}]"
    m = _LLAMADA.match(op) if not op.startswith('"') else None
    if m:
        return f"{m.group(1)}({', '.join(a_infija(h) for h in nodo.hijos)})"
    if not nodo.hijos:
        return op
    p = PRECEDENCIA[op]
    if op == "neg":
        texto = "-" + a_infija(nodo.hijos[0], p)
    elif op == "no":
        texto = "no " + a_infija(nodo.hijos[0], p)
    else:
        izq = p + 1 if op in COMPARACIONES else p
        texto = f"{a_infija(nodo.hijos[0], izq)} {op} {a_infija(nodo.hijos[1], p + 1)}"
    return f"({texto})" if p < minimo else texto


# ------------------------------------------------------------------ interfaz
def convertir(texto, origen="infija"):
    """Devuelve {'infija': str, 'postfija': str, 'prefija': str}."""
    if origen == "infija":
        arbol = postfija_a_arbol(infija_a_postfija(texto))
    elif origen == "postfija":
        arbol = postfija_a_arbol(texto)
    elif origen == "prefija":
        arbol = prefija_a_arbol(texto)
    else:
        raise ValueError(f"notación desconocida: {origen}")
    return {"infija": a_infija(arbol), "postfija": " ".join(a_postfija(arbol)),
            "prefija": " ".join(a_prefija(arbol))}
