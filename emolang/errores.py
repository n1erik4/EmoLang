"""Diagnósticos (errores y advertencias) compartidos por todas las fases."""

from dataclasses import dataclass, field

ERROR = "error"
ADVERTENCIA = "advertencia"
NOTA = "nota"          # observación de diseño: no impide compilar ni se cuenta como advertencia


@dataclass
class Diagnostico:
    fase: str          # lexico | sintactico | semantico | dominio | ejecucion
    nivel: str         # error | advertencia
    mensaje: str
    linea: int = 0
    columna: int = 0

    def __str__(self):
        pos = f"{self.linea}:{self.columna}" if self.linea else "-"
        return f"[{self.fase}] {self.nivel} en {pos}: {self.mensaje}"


@dataclass
class Reporte:
    diagnosticos: list = field(default_factory=list)

    def error(self, fase, mensaje, linea=0, columna=0):
        self.diagnosticos.append(Diagnostico(fase, ERROR, mensaje, linea, columna))

    def advertencia(self, fase, mensaje, linea=0, columna=0):
        self.diagnosticos.append(Diagnostico(fase, ADVERTENCIA, mensaje, linea, columna))

    def nota(self, fase, mensaje, linea=0, columna=0):
        self.diagnosticos.append(Diagnostico(fase, NOTA, mensaje, linea, columna))

    @property
    def notas(self):
        return [d for d in self.diagnosticos if d.nivel == NOTA]

    @property
    def errores(self):
        return [d for d in self.diagnosticos if d.nivel == ERROR]

    @property
    def advertencias(self):
        return [d for d in self.diagnosticos if d.nivel == ADVERTENCIA]

    def tiene_errores(self):
        return bool(self.errores)

    def ordenados(self):
        return sorted(self.diagnosticos, key=lambda d: (d.linea, d.columna))


class ErrorEmoLang(Exception):
    """Error que detiene una fase (p. ej. un error en tiempo de ejecución)."""

    def __init__(self, mensaje, linea=0, columna=0):
        super().__init__(mensaje)
        self.linea = linea
        self.columna = columna
