"""Bucle de ejecución: conecta un sensor con el motor y el módulo de dominio."""

import time
from dataclasses import dataclass

from .modulos import modulo_para
from .vm import EmoVM


@dataclass
class ResultadoEjecucion:
    motor: EmoVM
    modulo: object
    eventos: list           # (t_ms, evento)
    cuadros: int
    latencias_ms: list

    @property
    def resumen(self):
        return self.modulo.resumen()

    @property
    def latencia_media_ms(self):
        return sum(self.latencias_ms) / len(self.latencias_ms) if self.latencias_ms else 0.0

    @property
    def latencia_p95_ms(self):
        if not self.latencias_ms:
            return 0.0
        s = sorted(self.latencias_ms)
        return s[min(len(s) - 1, int(0.95 * len(s)))]


def regularizar(fuente, fps):
    """Convierte un flujo con marcas de tiempo irregulares (cámara real, CSV grabado)
    en cuadros cada 1000/fps ms, repitiendo la medición más reciente (retención de
    orden cero). Así 'durante 1 s' significa 1 s aunque la cámara entregue menos
    cuadros por segundo de los declarados en el sensor."""
    periodo = 1000.0 / fps
    k = 0
    for t, m in fuente:
        while k * periodo <= t + 0.5:
            yield k * periodo, m
            k += 1


def ejecutar(resultado, dominio, sensor, tiempo_real=False, sonido=False, verbose=True,
             al_cuadro=None, ocultar=("parpadeo",), emoc=None):
    """Ejecuta el programa en EmoVM. `emoc` permite indicar otro programa compilado."""
    def salida(texto):
        if verbose and not any(texto.rstrip().endswith(f"gesto      {o}") for o in ocultar):
            print(texto)

    modulo = modulo_para(dominio, sonido=sonido, salida=salida)
    motor = EmoVM(emoc or resultado.emoc, dominio, modulo)
    if hasattr(sensor, "motor"):
        sensor.motor = motor   # la cámara dibuja el estado del motor sobre el video

    eventos, latencias = [], []
    inicio_real = time.perf_counter()
    cuadros = 0
    fuente = regularizar(sensor, motor.fps) if getattr(sensor, "tasa_variable", False) else sensor
    for t, metricas in fuente:
        if tiempo_real:
            espera = t / 1000 - (time.perf_counter() - inicio_real)
            if espera > 0:
                time.sleep(espera)
        t0 = time.perf_counter()
        evs = motor.paso(t, metricas)
        latencias.append((time.perf_counter() - t0) * 1000)
        cuadros += 1
        eventos.extend((t, ev) for ev in evs)
        if al_cuadro:
            al_cuadro(motor, t, metricas, evs)
    modulo.finalizar()
    return ResultadoEjecucion(motor, modulo, eventos, cuadros, latencias)
