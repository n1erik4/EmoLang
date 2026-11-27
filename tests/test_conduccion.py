"""Pruebas de la detección de microsueño y cabeceo con cámaras lentas (~15 fps).

Las cámaras de laptop y celular dan ~15 cuadros por segundo y MediaPipe a veces lee
mal uno o dos cuadros seguidos. Con 'tolerando 100 ms' eso reiniciaba el conteo del
microsueño y la alarma se atrasaba segundos o no sonaba.
"""

import json
import os
import unittest

from emolang.metricas import metricas_neutras, ojos_cerrados
from emolang.sensores import SensorSimulado
from emolang.web import SesionWeb

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS_CAMARA = 15
INICIO_MS = 30_000          # el evento empieza tras 30 s normales (PERCLOS ya estable)


def conduccion():
    with open(os.path.join(RAIZ, "ejemplos", "conduccion.emo"), encoding="utf-8") as f:
        return SesionWeb(f.read())


def abiertos(t):
    """Conductor atento con un ligero vaivén de la medición."""
    return {"ear": 0.30 + 0.01 * ((t // 200) % 2), "cierre_ojos": 0.05, "mar": 0.02, "pitch": 0.0, "yaw": 0.0}


def correr(s, cuadro, hasta_ms):
    """Pasa cuadros a 15 fps; devuelve [(t, estado del monitor)] desde INICIO_MS."""
    estados, t = [], 0.0
    while t <= hasta_ms:
        r = json.loads(s.paso(t, json.dumps(cuadro(t))))
        if t >= INICIO_MS:
            estados.append((t, r["estados"]["monitor"]))
        t += 1000 / FPS_CAMARA
    return estados


def primera_vez(estados, estado):
    return next((t - INICIO_MS for t, e in estados if e == estado), None)


class TestMetricaCierreOjos(unittest.TestCase):
    def test_ojos_cerrados_por_ear_o_por_cierre(self):
        self.assertFalse(ojos_cerrados(metricas_neutras()))
        self.assertTrue(ojos_cerrados(dict(metricas_neutras(), ear=0.1)))
        self.assertTrue(ojos_cerrados(dict(metricas_neutras(), cierre_ojos=0.7)))   # de lejos

    def test_perclos_cuenta_cierre_ojos(self):
        s = conduccion()
        cerrados = lambda t: dict(abiertos(t), ear=0.25, cierre_ojos=0.7)
        r = None
        for k in range(30):
            r = json.loads(s.paso(k * 100.0, json.dumps(cerrados(k * 100.0))))
        self.assertGreater(r["perclos"], 0.9)

    def test_el_simulador_publica_cierre_ojos(self):
        sensor = SensorSimulado("conduccion", duracion=60)
        cuadros = {round(t): m for t, m in sensor}
        tipo, ini, dur, _ = next(e for e in sensor.eventos if e[0] == "microsueno")
        dentro = cuadros[min(cuadros, key=lambda t: abs(t - (ini + dur / 2) * 1000))]
        self.assertGreater(dentro["cierre_ojos"], 0.7)
        self.assertLess(max(m["cierre_ojos"] for t, m in cuadros.items() if t < 1000), 0.2)


class TestMicrosuenoA15fps(unittest.TestCase):
    def microsueno(self, cuadro_malo):
        """Ojos cerrados 4 s; cuadro_malo(i) dice si el i-ésimo cuadro se lee mal."""
        def cuadro(t):
            if not INICIO_MS <= t < INICIO_MS + 4000:
                return abiertos(t)
            i = round((t - INICIO_MS) * FPS_CAMARA / 1000)
            if cuadro_malo(i):      # MediaPipe lee los ojos entreabiertos
                return dict(abiertos(t), ear=0.24, cierre_ojos=0.35)
            return dict(abiertos(t), ear=0.04, cierre_ojos=0.68)
        return primera_vez(correr(conduccion(), cuadro, INICIO_MS + 5000), "alerta")

    def test_sin_cuadros_malos(self):
        t = self.microsueno(lambda i: False)
        self.assertIsNotNone(t)
        self.assertLess(t, 1200)

    def test_dos_cuadros_malos_seguidos_no_reinician_el_conteo(self):
        # 2 de cada 6 cuadros mal leídos (133 ms): con 'tolerando 100 ms' nunca sonaba
        t = self.microsueno(lambda i: i % 6 in (4, 5))
        self.assertIsNotNone(t, "la alarma de microsueño no sonó")
        self.assertLess(t, 1500)

    def test_basta_cierre_ojos_si_ear_no_baja(self):
        def cuadro(t):
            if INICIO_MS <= t < INICIO_MS + 4000:
                return dict(abiertos(t), ear=0.24, cierre_ojos=0.68)   # de lejos
            return abiertos(t)
        t = primera_vez(correr(conduccion(), cuadro, INICIO_MS + 5000), "alerta")
        self.assertIsNotNone(t)
        self.assertLess(t, 1500)

    def test_parpadeos_no_dan_alarma(self):
        def cuadro(t):
            if t >= INICIO_MS and (t - INICIO_MS) % 3000 < 200:     # parpadeo de 200 ms cada 3 s
                return dict(abiertos(t), ear=0.05, cierre_ojos=0.8)
            return abiertos(t)
        estados = correr(conduccion(), cuadro, INICIO_MS + 15_000)
        self.assertIsNone(primera_vez(estados, "alerta"))


class TestCabeceo(unittest.TestCase):
    @staticmethod
    def cabeceos(*inicios_s):
        """Cabeza abajo 0.8 s con los ojos entrecerrados (sin cerrarlos del todo)."""
        def cuadro(t):
            for ini in inicios_s:
                a = INICIO_MS + ini * 1000
                if a <= t < a + 800:
                    return dict(abiertos(t), pitch=15.0, ear=0.24, cierre_ojos=0.3)
            return abiertos(t)
        return cuadro

    def test_un_cabeceo_pasa_a_somnoliento(self):
        estados = correr(conduccion(), self.cabeceos(0), INICIO_MS + 3000)
        t = primera_vez(estados, "somnoliento")
        self.assertIsNotNone(t)
        self.assertLess(t, 800)
        self.assertIsNone(primera_vez(estados, "alerta"))

    def test_el_segundo_cabeceo_da_la_alarma(self):
        estados = correr(conduccion(), self.cabeceos(0, 4), INICIO_MS + 6000)
        t = primera_vez(estados, "alerta")
        self.assertIsNotNone(t)
        self.assertGreater(t, 4000)
        self.assertLess(t, 4800)


if __name__ == "__main__":
    unittest.main()
