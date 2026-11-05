"""Analizador léxico de EmoLang.

Convierte el texto fuente en una lista de tokens. Implementado a mano como un
autómata finito determinista: cada rama de `_siguiente` corresponde a un estado
del AFD que reconoce una categoría léxica.
"""

from dataclasses import dataclass

from .errores import Reporte

PALABRAS_RESERVADAS = {
    # estructura
    "dominio", "sensor", "usar", "var", "const", "funcion", "retornar", "estructura", "gesto", "secuencia", "maquina", "inicial",
    "estado", "al_entrar", "cuando", "ignorar", "ir_a", "tras", "durante", "hasta", "tolerando", "en",
    # control
    "si", "sino", "mientras", "repetir", "veces", "para",
    # tipos
    "int", "decimal", "bool", "string", "duracion", "proporcion",
    # literales y operadores lógicos
    "verdadero", "falso", "y", "o", "no",
    # unidades
    "ms", "s",
}

TIPOS = {"int", "decimal", "bool", "string", "duracion", "proporcion", "gesto", "secuencia"}

# Símbolos de dos caracteres primero para respetar la regla del lexema más largo.
SIMBOLOS_DOBLES = {"<=": "MENOR_IGUAL", ">=": "MAYOR_IGUAL", "==": "IGUAL", "!=": "DISTINTO"}
SIMBOLOS_SIMPLES = {
    "{": "LLAVE_IZQ", "}": "LLAVE_DER", "(": "PAR_IZQ", ")": "PAR_DER",
    "[": "COR_IZQ", "]": "COR_DER", ";": "PUNTO_COMA", ",": "COMA", ":": "DOS_PUNTOS",
    "=": "ASIGNACION", "<": "MENOR", ">": "MAYOR", "+": "MAS", "-": "MENOS",
    "*": "POR", "/": "ENTRE", "%": "PORCIENTO", ".": "PUNTO",
}


@dataclass
class Token:
    tipo: str       # categoría: ID, ENTERO, DECIMAL, CADENA, palabra reservada en MAYÚSCULAS, símbolo...
    lexema: str
    linea: int
    columna: int
    valor: object = None

    def __repr__(self):
        return f"Token({self.tipo}, {self.lexema!r}, {self.linea}:{self.columna})"


class Lexico:
    def __init__(self, fuente: str, reporte: Reporte | None = None):
        self.fuente = fuente
        self.reporte = reporte or Reporte()
        self.pos = 0
        self.linea = 1
        self.columna = 1

    # --- utilidades -------------------------------------------------------
    def _ver(self, k=0):
        i = self.pos + k
        return self.fuente[i] if i < len(self.fuente) else ""

    def _avanzar(self):
        c = self.fuente[self.pos]
        self.pos += 1
        if c == "\n":
            self.linea += 1
            self.columna = 1
        else:
            self.columna += 1
        return c

    def _error(self, mensaje, linea, columna):
        self.reporte.error("lexico", mensaje, linea, columna)

    # --- análisis ---------------------------------------------------------
    def tokens(self):
        resultado = []
        while True:
            tok = self._siguiente()
            if tok is None:
                continue
            resultado.append(tok)
            if tok.tipo == "EOF":
                return resultado

    def _siguiente(self):
        self._saltar_blancos_y_comentarios()
        linea, col = self.linea, self.columna
        c = self._ver()

        if c == "":
            return Token("EOF", "", linea, col)

        if c.isalpha() or c == "_":
            return self._identificador(linea, col)

        if c.isdigit():
            return self._numero(linea, col)

        if c == '"':
            return self._cadena(linea, col)

        dos = c + self._ver(1)
        if dos in SIMBOLOS_DOBLES:
            self._avanzar(); self._avanzar()
            return Token(SIMBOLOS_DOBLES[dos], dos, linea, col)

        if c in SIMBOLOS_SIMPLES:
            self._avanzar()
            return Token(SIMBOLOS_SIMPLES[c], c, linea, col)

        self._avanzar()
        self._error(f"carácter no reconocido {c!r}", linea, col)
        return None

    def _saltar_blancos_y_comentarios(self):
        while True:
            c = self._ver()
            if c and c in " \t\r\n":
                self._avanzar()
            elif c == "/" and self._ver(1) == "/":
                while self._ver() and self._ver() != "\n":
                    self._avanzar()
            elif c == "/" and self._ver(1) == "*":
                linea, col = self.linea, self.columna
                self._avanzar(); self._avanzar()
                while self._ver() and not (self._ver() == "*" and self._ver(1) == "/"):
                    self._avanzar()
                if not self._ver():
                    self._error("comentario de bloque sin cerrar", linea, col)
                    return
                self._avanzar(); self._avanzar()
            else:
                return

    def _identificador(self, linea, col):
        inicio = self.pos
        while self._ver() and (self._ver().isalnum() or self._ver() == "_"):
            self._avanzar()
        lexema = self.fuente[inicio:self.pos]
        if lexema in PALABRAS_RESERVADAS:
            return Token(lexema.upper(), lexema, linea, col)
        return Token("ID", lexema, linea, col)

    def _numero(self, linea, col):
        inicio = self.pos
        while self._ver().isdigit():
            self._avanzar()
        es_decimal = False
        if self._ver() == "." and self._ver(1).isdigit():
            es_decimal = True
            self._avanzar()
            while self._ver().isdigit():
                self._avanzar()
        elif self._ver() == ".":
            self._avanzar()
            self._error("número decimal mal formado: falta parte fraccionaria", linea, col)
        if self._ver().isalpha() or self._ver() == "_":
            # p. ej. "3abc": se consume como un solo lexema inválido
            while self._ver().isalnum() or self._ver() == "_":
                self._avanzar()
            lexema = self.fuente[inicio:self.pos]
            # "100ms" o "2s" sin espacio sí son válidos: se separan en número + unidad
            for unidad in ("ms", "s"):
                num = lexema[: -len(unidad)]
                if lexema.endswith(unidad) and _es_numero(num):
                    self.pos -= len(unidad)
                    self.columna -= len(unidad)
                    return self._token_numero(num, linea, col)
            self._error(f"identificador no puede iniciar con dígito: {lexema!r}", linea, col)
            return None
        lexema = self.fuente[inicio:self.pos]
        return self._token_numero(lexema, linea, col, es_decimal)

    @staticmethod
    def _token_numero(lexema, linea, col, es_decimal=None):
        if es_decimal is None:
            es_decimal = "." in lexema
        if es_decimal:
            return Token("DECIMAL", lexema, linea, col, float(lexema))
        return Token("ENTERO", lexema, linea, col, int(lexema))

    def _cadena(self, linea, col):
        self._avanzar()  # comilla inicial
        partes = []
        while self._ver() and self._ver() != '"':
            if self._ver() == "\n":
                break
            if self._ver() == "\\":
                self._avanzar()
                esc = self._avanzar() if self._ver() else ""
                partes.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(esc, esc))
            else:
                partes.append(self._avanzar())
        if self._ver() != '"':
            self._error("cadena sin cerrar", linea, col)
            return Token("CADENA", "".join(partes), linea, col, "".join(partes))
        self._avanzar()
        texto = "".join(partes)
        return Token("CADENA", f'"{texto}"', linea, col, texto)


def _es_numero(s):
    if not s:
        return False
    partes = s.split(".")
    return len(partes) <= 2 and all(p.isdigit() for p in partes)


def analizar(fuente: str, reporte: Reporte | None = None):
    reporte = reporte or Reporte()
    return Lexico(fuente, reporte).tokens(), reporte
