"""Orquesta las fases del compilador de EmoLang."""

from dataclasses import dataclass

from . import automatas, lexico, semantico, sintactico, validaciones
from .errores import Reporte


@dataclass
class Resultado:
    fuente: str
    tokens: list = None
    ast: object = None
    analisis: object = None
    imposibles: set = None
    automatas: dict = None
    reporte: Reporte = None

    @property
    def ok(self):
        return not self.reporte.tiene_errores()


def compilar(fuente: str, hasta="automatas") -> Resultado:
    """Ejecuta las fases en orden. Se detiene en la primera fase con errores
    (los errores léxicos y sintácticos se acumulan juntos para reportar todos)."""
    rep = Reporte()
    r = Resultado(fuente, reporte=rep)

    r.tokens, _ = lexico.analizar(fuente, rep)
    if hasta == "lexico":
        return r
    r.ast, _ = sintactico.analizar(r.tokens, rep)
    if hasta == "sintactico" or rep.tiene_errores():
        return r
    r.analisis, _ = semantico.analizar(r.ast, rep)
    if hasta == "semantico":
        return r
    # Las validaciones de dominio se ejecutan aunque haya errores semánticos
    # para reportar todos los problemas del programa en una sola pasada.
    r.imposibles, _ = validaciones.validar(r.analisis, rep)
    if hasta == "dominio" or rep.tiene_errores():
        return r
    r.automatas, _ = automatas.generar(r.analisis, rep)
    return r


def compilar_archivo(ruta, hasta="automatas"):
    with open(ruta, encoding="utf-8") as f:
        return compilar(f.read(), hasta)
