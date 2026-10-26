"""Sistema de tipos de EmoLang y reglas de conversión.

Reglas de conversión (implícitas):
  * int -> decimal                     (ensanchamiento)
  * decimal <-> proporcion              (decimal en [0, 1] equivale a 0%-100%)
  * int + decimal -> decimal
  * duracion: ms y s se normalizan a milisegundos en tiempo de compilación,
    por lo que 1 s == 1000 ms.
No se permite: decimal -> int (pérdida de precisión), número -> duracion sin
unidad, ni mezclar duracion con números en sumas o comparaciones.
"""

NUMERICOS = {"int", "decimal", "proporcion"}
COMPARACION = {"<", "<=", ">", ">=", "==", "!="}


def es_numerico(t):
    return t in NUMERICOS


def asignable(destino, origen):
    """¿Puede un valor de tipo `origen` guardarse en una variable `destino`?"""
    if origen is None or destino is None:
        return True  # ya se reportó un error antes; evitar cascadas
    if destino == origen:
        return True
    if destino == "decimal" and origen in ("int", "proporcion"):
        return True
    if destino == "proporcion" and origen in ("decimal", "int"):
        return True  # el rango [0, 1] se verifica aparte cuando el valor es constante
    return False


def tipo_binario(op, a, b):
    """Devuelve (tipo_resultado, mensaje_error)."""
    if a is None or b is None:
        return None, None

    if op in ("y", "o"):
        if a == b == "bool":
            return "bool", None
        return None, f"el operador '{op}' requiere operandos bool (recibió {a} y {b})"

    if op in COMPARACION:
        if es_numerico(a) and es_numerico(b):
            return "bool", None
        if a == b and a in ("duracion", "string", "bool") and (op in ("==", "!=") or a == "duracion"):
            return "bool", None
        if "duracion" in (a, b):
            return None, (f"no se puede comparar {a} con {b}; "
                          "indique la unidad (ms o s) en la constante")
        return None, f"no se puede comparar {a} con {b} usando '{op}'"

    if op == "+" and "string" in (a, b):
        return "string", None

    if op in ("+", "-"):
        if a == b == "duracion":
            return "duracion", None
        if es_numerico(a) and es_numerico(b):
            if a == b == "int":
                return "int", None
            return "decimal", None
        if "duracion" in (a, b):
            return None, f"no se puede operar {a} {op} {b}; ambos operandos deben ser duracion"
        return None, f"operador '{op}' no aplicable a {a} y {b}"

    if op == "*":
        if es_numerico(a) and es_numerico(b):
            return ("int" if a == b == "int" else "decimal"), None
        if {a, b} <= {"duracion", "int", "decimal"} and (a == "duracion") != (b == "duracion"):
            return "duracion", None
        return None, f"operador '*' no aplicable a {a} y {b}"

    if op == "/":
        if es_numerico(a) and es_numerico(b):
            return "decimal", None
        if a == "duracion" and b in ("int", "decimal"):
            return "duracion", None
        if a == b == "duracion":
            return "decimal", None
        return None, f"operador '/' no aplicable a {a} y {b}"

    return None, f"operador desconocido {op!r}"


def tipo_unario(op, t):
    if t is None:
        return None, None
    if op == "no":
        return ("bool", None) if t == "bool" else (None, f"'no' requiere bool (recibió {t})")
    if op == "-":
        if t == "proporcion":
            return "decimal", None
        if t in ("int", "decimal", "duracion"):
            return t, None
        return None, f"'-' no aplicable a {t}"
    return None, f"operador desconocido {op!r}"
