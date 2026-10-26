"""Analizador sintáctico descendente recursivo de EmoLang.

Cada método `_regla` implementa una producción de la gramática documentada en
docs/gramatica.md. Ante un error se aplica recuperación en modo pánico: se
reporta el error y se descartan tokens hasta un punto de sincronización
(';' o '}'), lo que permite informar varios errores en una sola pasada.
"""

from . import nodos as N
from .errores import Reporte
from .lexico import TIPOS


class _ErrorSintactico(Exception):
    pass


OPERADORES_COMPARACION = {
    "MENOR": "<", "MENOR_IGUAL": "<=", "MAYOR": ">", "MAYOR_IGUAL": ">=",
    "IGUAL": "==", "DISTINTO": "!=",
}

INICIO_MIEMBRO_DOMINIO = {"SENSOR", "VAR", "GESTO", "SECUENCIA", "MAQUINA"}
INICIO_MIEMBRO_ESTADO = {"VAR", "AL_ENTRAR", "CUANDO", "MIENTRAS", "IGNORAR"}


class Sintactico:
    def __init__(self, tokens, reporte: Reporte | None = None):
        self.tokens = tokens
        self.reporte = reporte or Reporte()
        self.i = 0

    # --- utilidades -------------------------------------------------------
    @property
    def actual(self):
        return self.tokens[self.i]

    def _ver(self, k=1):
        j = min(self.i + k, len(self.tokens) - 1)
        return self.tokens[j]

    def _es(self, *tipos):
        return self.actual.tipo in tipos

    def _avanzar(self):
        tok = self.actual
        if tok.tipo != "EOF":
            self.i += 1
        return tok

    def _aceptar(self, tipo):
        if self._es(tipo):
            return self._avanzar()
        return None

    def _esperar(self, tipo, descripcion=None):
        if self._es(tipo):
            return self._avanzar()
        tok = self.actual
        encontrado = "fin de archivo" if tok.tipo == "EOF" else repr(tok.lexema)
        self._error(f"se esperaba {descripcion or tipo.lower()} y se encontró {encontrado}", tok)

    def _error(self, mensaje, tok=None):
        tok = tok or self.actual
        self.reporte.error("sintactico", mensaje, tok.linea, tok.columna)
        raise _ErrorSintactico()

    def _sincronizar(self, tambien=()):
        """Modo pánico: descarta tokens hasta ';' (consumido) o '}' / inicio de miembro."""
        while not self._es("EOF"):
            if self._aceptar("PUNTO_COMA"):
                return
            if self._es("LLAVE_DER") or self.actual.tipo in tambien:
                return
            if self._es("LLAVE_IZQ"):
                self._saltar_bloque()
                return
            self._avanzar()

    def _saltar_bloque(self):
        nivel = 0
        while not self._es("EOF"):
            t = self._avanzar()
            if t.tipo == "LLAVE_IZQ":
                nivel += 1
            elif t.tipo == "LLAVE_DER":
                nivel -= 1
                if nivel == 0:
                    return

    def _id(self, descripcion="un identificador"):
        return self._esperar("ID", descripcion)

    @staticmethod
    def _pos(tok):
        return {"linea": tok.linea, "columna": tok.columna}

    # --- programa ---------------------------------------------------------
    def programa(self):
        dominios = []
        while not self._es("EOF"):
            try:
                dominios.append(self._dominio())
            except _ErrorSintactico:
                self._sincronizar(tambien={"DOMINIO"})
                self._aceptar("LLAVE_DER")
        if not dominios and not self.reporte.tiene_errores():
            self.reporte.error("sintactico", "el programa debe declarar al menos un dominio", 1, 1)
        return N.Programa(dominios, linea=1, columna=1)

    def _dominio(self):
        inicio = self._esperar("DOMINIO", "'dominio'")
        nombre = self._id("el nombre del dominio").lexema
        self._esperar("LLAVE_IZQ", "'{'")
        dom = N.Dominio(nombre, [], [], [], [], [], **self._pos(inicio))
        while not self._es("LLAVE_DER", "EOF"):
            try:
                self._miembro_dominio(dom)
            except _ErrorSintactico:
                self._sincronizar(tambien=INICIO_MIEMBRO_DOMINIO)
        self._esperar("LLAVE_DER", "'}' al cerrar el dominio")
        return dom

    def _miembro_dominio(self, dom):
        if self._es("SENSOR"):
            dom.sensores.append(self._sensor())
        elif self._es("VAR"):
            dom.variables.append(self._decl_var())
        elif self._es("GESTO"):
            dom.gestos.append(self._gesto())
        elif self._es("SECUENCIA"):
            dom.secuencias.append(self._secuencia())
        elif self._es("MAQUINA"):
            dom.maquinas.append(self._maquina())
        else:
            self._error(f"declaración no válida dentro de un dominio: {self.actual.lexema!r} "
                        "(se esperaba sensor, var, gesto, secuencia o maquina)")

    def _sensor(self):
        inicio = self._esperar("SENSOR")
        nombre = self._id("el nombre del sensor").lexema
        self._esperar("LLAVE_IZQ", "'{'")
        variables = []
        while not self._es("LLAVE_DER", "EOF"):
            try:
                if not self._es("VAR"):
                    self._error("un sensor solo puede contener declaraciones 'var'")
                variables.append(self._decl_var())
            except _ErrorSintactico:
                self._sincronizar(tambien={"VAR"})
        self._esperar("LLAVE_DER", "'}' al cerrar el sensor")
        return N.Sensor(nombre, variables, **self._pos(inicio))

    def _decl_var(self):
        inicio = self._esperar("VAR")
        nombre = self._id("el nombre de la variable").lexema
        self._esperar("DOS_PUNTOS", "':' seguido del tipo")
        tipo_tok = self.actual
        if tipo_tok.lexema not in TIPOS:
            self._error(f"tipo desconocido {tipo_tok.lexema!r}")
        self._avanzar()
        self._esperar("ASIGNACION", "'=' (toda variable debe inicializarse)")
        valor = self._expr()
        self._esperar("PUNTO_COMA", "';'")
        return N.DeclVar(nombre, tipo_tok.lexema, valor, **self._pos(inicio))

    def _gesto(self):
        inicio = self._esperar("GESTO")
        nombre = self._id("el nombre del gesto").lexema
        self._esperar("ASIGNACION", "'='")
        condicion = self._expr()
        self._esperar("DURANTE", "'durante' (un gesto es un patrón en el tiempo)")
        minimo = self._expr()
        maximo = None
        if self._aceptar("HASTA"):
            maximo = self._expr()
        tolerancia = None
        if self._aceptar("TOLERANDO"):
            tolerancia = self._expr()
        self._esperar("PUNTO_COMA", "';'")
        return N.Gesto(nombre, condicion, minimo, maximo, tolerancia, **self._pos(inicio))

    def _secuencia(self):
        inicio = self._esperar("SECUENCIA")
        nombre = self._id("el nombre de la secuencia").lexema
        self._esperar("ASIGNACION", "'='")
        self._esperar("COR_IZQ", "'['")
        elementos = []
        tok = self._id("un gesto")
        elementos.append(N.Identificador(tok.lexema, **self._pos(tok)))
        while self._aceptar("COMA"):
            tok = self._id("un gesto")
            elementos.append(N.Identificador(tok.lexema, **self._pos(tok)))
        self._esperar("COR_DER", "']'")
        ventana = None
        if self._aceptar("EN"):
            ventana = self._expr()
        self._esperar("PUNTO_COMA", "';'")
        return N.Secuencia(nombre, elementos, ventana, **self._pos(inicio))

    def _maquina(self):
        inicio = self._esperar("MAQUINA")
        nombre = self._id("el nombre de la máquina").lexema
        self._esperar("INICIAL", "'inicial' seguido del estado inicial")
        inicial = self._id("el estado inicial").lexema
        self._esperar("LLAVE_IZQ", "'{'")
        estados = []
        while not self._es("LLAVE_DER", "EOF"):
            try:
                if not self._es("ESTADO"):
                    self._error("una máquina solo puede contener declaraciones 'estado'")
                estados.append(self._estado())
            except _ErrorSintactico:
                self._sincronizar(tambien={"ESTADO"})
        self._esperar("LLAVE_DER", "'}' al cerrar la máquina")
        if not estados:
            self.reporte.error("sintactico", f"la máquina '{nombre}' no declara estados",
                               inicio.linea, inicio.columna)
        return N.Maquina(nombre, inicial, estados, **self._pos(inicio))

    def _estado(self):
        inicio = self._esperar("ESTADO")
        nombre = self._id("el nombre del estado").lexema
        self._esperar("LLAVE_IZQ", "'{'")
        est = N.Estado(nombre, [], None, [], [], **self._pos(inicio))
        while not self._es("LLAVE_DER", "EOF"):
            try:
                if self._es("VAR"):
                    est.variables.append(self._decl_var())
                elif self._es("AL_ENTRAR"):
                    tok = self._avanzar()
                    if est.al_entrar is not None:
                        self.reporte.error("sintactico", "el estado ya tiene un bloque 'al_entrar'",
                                           tok.linea, tok.columna)
                    est.al_entrar = self._bloque()
                elif self._es("CUANDO"):
                    est.cuandos.append(self._cuando())
                elif self._es("MIENTRAS"):
                    tok = self._avanzar()
                    cond = self._expr()
                    est.mientras.append(N.Mientras(cond, self._bloque(), **self._pos(tok)))
                elif self._es("IGNORAR"):
                    self._avanzar()
                    while True:
                        tok = self._id("un gesto o secuencia")
                        est.ignorados.append(N.Identificador(tok.lexema, **self._pos(tok)))
                        if not self._aceptar("COMA"):
                            break
                    self._esperar("PUNTO_COMA", "';'")
                else:
                    self._error(f"elemento no válido dentro de un estado: {self.actual.lexema!r} "
                                "(se esperaba var, al_entrar, cuando, mientras o ignorar)")
            except _ErrorSintactico:
                self._sincronizar(tambien=INICIO_MIEMBRO_ESTADO)
        self._esperar("LLAVE_DER", "'}' al cerrar el estado")
        return est

    def _cuando(self):
        inicio = self._esperar("CUANDO")
        evento = self._id("un gesto o secuencia").lexema
        if self._aceptar("IR_A"):
            destino = self._id("el estado destino").lexema
            self._esperar("PUNTO_COMA", "';'")
            return N.Cuando(evento, destino=destino, **self._pos(inicio))
        if self._es("LLAVE_IZQ"):
            return N.Cuando(evento, cuerpo=self._bloque(), **self._pos(inicio))
        self._error("se esperaba 'ir_a' o un bloque '{' después del evento")

    # --- sentencias -------------------------------------------------------
    def _bloque(self):
        inicio = self._esperar("LLAVE_IZQ", "'{'")
        sentencias = []
        while not self._es("LLAVE_DER", "EOF"):
            try:
                sentencias.append(self._sentencia())
            except _ErrorSintactico:
                self._sincronizar()
        self._esperar("LLAVE_DER", "'}'")
        return N.Bloque(sentencias, **self._pos(inicio))

    def _sentencia(self):
        tok = self.actual
        if self._es("VAR"):
            return self._decl_var()
        if self._es("SI"):
            return self._si()
        if self._es("REPETIR"):
            self._avanzar()
            veces = self._expr()
            self._esperar("VECES", "'veces'")
            return N.Repetir(veces, self._bloque(), **self._pos(tok))
        if self._es("MIENTRAS"):
            self._error("'mientras' se evalúa una vez por cuadro y solo puede declararse "
                        "directamente dentro de un estado")
        if self._es("IR_A"):
            self._avanzar()
            destino = self._id("el estado destino").lexema
            self._esperar("PUNTO_COMA", "';'")
            return N.IrA(destino, **self._pos(tok))
        if self._es("ID"):
            if self._ver().tipo == "ASIGNACION":
                self._avanzar(); self._avanzar()
                valor = self._expr()
                self._esperar("PUNTO_COMA", "';'")
                return N.Asignacion(tok.lexema, valor, **self._pos(tok))
            if self._ver().tipo == "PAR_IZQ":
                llamada = self._llamada()
                self._esperar("PUNTO_COMA", "';'")
                return N.SentenciaLlamada(llamada, **self._pos(tok))
        self._error(f"sentencia no válida que inicia con {tok.lexema!r}")

    def _si(self):
        inicio = self._esperar("SI")
        cond = self._expr()
        entonces = self._bloque()
        sino = None
        if self._aceptar("SINO"):
            sino = self._si() if self._es("SI") else self._bloque()
        return N.Si(cond, entonces, sino, **self._pos(inicio))

    # --- expresiones (precedencia ascendente) -----------------------------
    def _expr(self):
        return self._o()

    def _o(self):
        izq = self._y()
        while self._es("O"):
            tok = self._avanzar()
            izq = N.Binaria("o", izq, self._y(), **self._pos(tok))
        return izq

    def _y(self):
        izq = self._no()
        while self._es("Y"):
            tok = self._avanzar()
            izq = N.Binaria("y", izq, self._no(), **self._pos(tok))
        return izq

    def _no(self):
        if self._es("NO"):
            tok = self._avanzar()
            return N.Unaria("no", self._no(), **self._pos(tok))
        return self._comparacion()

    def _comparacion(self):
        izq = self._suma()
        if self.actual.tipo in OPERADORES_COMPARACION:
            tok = self._avanzar()
            izq = N.Binaria(OPERADORES_COMPARACION[tok.tipo], izq, self._suma(), **self._pos(tok))
            if self.actual.tipo in OPERADORES_COMPARACION:
                self._error("las comparaciones no se pueden encadenar; use 'y'")
        return izq

    def _suma(self):
        izq = self._termino()
        while self._es("MAS", "MENOS"):
            tok = self._avanzar()
            izq = N.Binaria(tok.lexema, izq, self._termino(), **self._pos(tok))
        return izq

    def _termino(self):
        izq = self._unario()
        while self._es("POR", "ENTRE"):
            tok = self._avanzar()
            izq = N.Binaria(tok.lexema, izq, self._unario(), **self._pos(tok))
        return izq

    def _unario(self):
        if self._es("MENOS"):
            tok = self._avanzar()
            return N.Unaria("-", self._unario(), **self._pos(tok))
        return self._primario()

    def _primario(self):
        tok = self.actual
        if self._es("ENTERO", "DECIMAL"):
            self._avanzar()
            if self._es("MS", "S"):
                unidad = self._avanzar().tipo
                ms = tok.valor if unidad == "MS" else tok.valor * 1000
                return N.Literal(float(ms), "duracion", **self._pos(tok))
            if self._es("PORCIENTO"):
                self._avanzar()
                return N.Literal(tok.valor / 100.0, "proporcion", **self._pos(tok))
            tipo = "int" if tok.tipo == "ENTERO" else "decimal"
            return N.Literal(tok.valor, tipo, **self._pos(tok))
        if self._es("CADENA"):
            self._avanzar()
            return N.Literal(tok.valor, "string", **self._pos(tok))
        if self._es("VERDADERO", "FALSO"):
            self._avanzar()
            return N.Literal(tok.tipo == "VERDADERO", "bool", **self._pos(tok))
        if self._es("ID"):
            if self._ver().tipo == "PAR_IZQ":
                return self._llamada()
            self._avanzar()
            return N.Identificador(tok.lexema, **self._pos(tok))
        if self._aceptar("PAR_IZQ"):
            e = self._expr()
            self._esperar("PAR_DER", "')'")
            return e
        encontrado = "fin de archivo" if tok.tipo == "EOF" else repr(tok.lexema)
        self._error(f"se esperaba una expresión y se encontró {encontrado}")

    def _llamada(self):
        tok = self._id("el nombre de la función")
        self._esperar("PAR_IZQ", "'('")
        args = []
        if not self._es("PAR_DER"):
            args.append(self._expr())
            while self._aceptar("COMA"):
                args.append(self._expr())
        self._esperar("PAR_DER", "')'")
        return N.Llamada(tok.lexema, args, **self._pos(tok))


def analizar(tokens, reporte: Reporte | None = None):
    reporte = reporte or Reporte()
    return Sintactico(tokens, reporte).programa(), reporte
