"""Métricas faciales que el sensor publica en cada cuadro.

Son variables globales de solo lectura dentro de cualquier dominio. El rango
válido se usa en el análisis semántico para detectar umbrales fuera de rango y
gestos imposibles; el rango típico solo genera advertencias.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Metrica:
    nombre: str
    tipo: str
    minimo: float
    maximo: float
    tipico: tuple       # (min, max) observado en personas reales
    descripcion: str


METRICAS = {m.nombre: m for m in [
    Metrica("ear", "proporcion", 0.0, 1.0, (0.0, 0.45),
            "Razón de aspecto del ojo (promedio). Ojo abierto ~0.25-0.35, cerrado < 0.2"),
    Metrica("ear_izq", "proporcion", 0.0, 1.0, (0.0, 0.45), "EAR del ojo izquierdo"),
    Metrica("ear_der", "proporcion", 0.0, 1.0, (0.0, 0.45), "EAR del ojo derecho"),
    Metrica("mar", "proporcion", 0.0, 1.0, (0.0, 1.0),
            "Razón de aspecto de la boca. Boca cerrada ~0.0-0.1, bostezo > 0.6"),
    Metrica("sonrisa", "proporcion", 0.0, 1.0, (0.0, 1.0),
            "Intensidad de sonrisa normalizada (0 neutro, 1 máxima)"),
    Metrica("sonrisa_izq", "proporcion", 0.0, 1.0, (0.0, 1.0), "Elevación de la comisura izquierda"),
    Metrica("sonrisa_der", "proporcion", 0.0, 1.0, (0.0, 1.0), "Elevación de la comisura derecha"),
    Metrica("cejas", "proporcion", 0.0, 1.0, (0.0, 1.0), "Elevación de cejas normalizada"),
    Metrica("simetria", "proporcion", 0.0, 1.0, (0.0, 1.0),
            "Simetría facial izquierda/derecha (1 = perfectamente simétrico)"),
    Metrica("perclos", "proporcion", 0.0, 1.0, (0.0, 1.0),
            "Proporción de tiempo con ojos cerrados en los últimos 60 s"),
    Metrica("pitch", "decimal", -90.0, 90.0, (-45.0, 45.0),
            "Inclinación vertical de la cabeza en grados (positivo = hacia abajo)"),
    Metrica("yaw", "decimal", -90.0, 90.0, (-60.0, 60.0), "Giro horizontal de la cabeza en grados"),
    Metrica("roll", "decimal", -90.0, 90.0, (-45.0, 45.0), "Inclinación lateral de la cabeza en grados"),
    Metrica("rostro", "bool", 0, 1, (0, 1), "Verdadero si hay un rostro detectado en el cuadro"),
]}


def metricas_neutras():
    """Valores de un rostro neutro con ojos abiertos, mirando al frente."""
    return {
        "ear": 0.30, "ear_izq": 0.30, "ear_der": 0.30, "mar": 0.05,
        "sonrisa": 0.05, "sonrisa_izq": 0.05, "sonrisa_der": 0.05, "cejas": 0.2,
        "simetria": 0.97, "perclos": 0.0, "pitch": 0.0, "yaw": 0.0, "roll": 0.0, "rostro": True,
    }
