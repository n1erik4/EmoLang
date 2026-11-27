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
    Metrica("sonrisa_rel", "proporcion", 0.0, 1.0, (0.0, 1.0),
            "Sonrisa entre la sonrisa máxima de la persona (1 = lo más que sonríe); ver perfil.py"),
    Metrica("cejas_rel", "proporcion", 0.0, 1.0, (0.0, 1.0),
            "Subida de cejas desde su reposo entre la subida máxima de la persona; ver perfil.py"),
    Metrica("ojos_rel", "proporcion", 0.0, 1.0, (0.0, 1.0),
            "Cierre de los ojos entre lo más que la persona los cierra (1 = su mejor cierre); ver perfil.py"),
    Metrica("sonrisa_izq", "proporcion", 0.0, 1.0, (0.0, 1.0), "Elevación de la comisura izquierda"),
    Metrica("sonrisa_der", "proporcion", 0.0, 1.0, (0.0, 1.0), "Elevación de la comisura derecha"),
    Metrica("cejas", "proporcion", 0.0, 1.0, (0.0, 1.0), "Elevación de cejas normalizada"),
    Metrica("cejas_izq", "proporcion", 0.0, 1.0, (0.0, 1.0), "Elevación de la ceja izquierda"),
    Metrica("cejas_der", "proporcion", 0.0, 1.0, (0.0, 1.0), "Elevación de la ceja derecha"),
    Metrica("simetria", "proporcion", 0.0, 1.0, (0.0, 1.0),
            "Simetría facial izquierda/derecha (1 = perfectamente simétrico)"),
    Metrica("simetria_sonrisa", "proporcion", 0.0, 1.0, (0.0, 1.0), "Simetría de la sonrisa"),
    Metrica("simetria_cejas", "proporcion", 0.0, 1.0, (0.0, 1.0), "Simetría de la elevación de cejas"),
    Metrica("cierre_ojos", "proporcion", 0.0, 1.0, (0.0, 1.0),
            "Cierre de los párpados según MediaPipe (eyeBlink, promedio de ambos ojos): 0 abiertos, "
            "1 cerrados. A diferencia de ear, no depende de la distancia a la cámara"),
    Metrica("simetria_ojos", "proporcion", 0.0, 1.0, (0.0, 1.0), "Simetría del cierre de los ojos"),
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
        "sonrisa": 0.05, "sonrisa_rel": 0.0, "cejas_rel": 0.0, "ojos_rel": 0.0, "sonrisa_izq": 0.05, "sonrisa_der": 0.05, "cejas": 0.2,
        "cejas_izq": 0.2, "cejas_der": 0.2, "simetria_sonrisa": 1.0, "simetria_cejas": 1.0, "simetria_ojos": 1.0, "cierre_ojos": 0.0,
        "simetria": 0.97, "perclos": 0.0, "pitch": 0.0, "yaw": 0.0, "roll": 0.0, "rostro": True,
    }


# PERCLOS: un cuadro cuenta con los ojos cerrados si ear < EAR_CERRADO (de cerca es
# confiable) o si cierre_ojos > CIERRE_CERRADO. De lejos el ear casi no baja (medido
# con la persona lejos: 0.29 abiertos, 0.24 cerrados), pero el eyeBlink de MediaPipe sí.
EAR_CERRADO = 0.2
CIERRE_CERRADO = 0.5


def ojos_cerrados(m):
    return (float(m.get("ear", 0.3)) < EAR_CERRADO
            or float(m.get("cierre_ojos", 0.0)) > CIERRE_CERRADO)
