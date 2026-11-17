"""Pruebas del puente web (emolang/web.py), que la página ejecuta con Pyodide."""

import json
import os
import random
import unittest

from emolang.sensores import SensorSimulado
from emolang.web import SesionWeb

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fuente(nombre):
    with open(os.path.join(RAIZ, "ejemplos", nombre), encoding="utf-8") as f:
        return f.read()


def con_tasa_irregular(sensor, semilla=3):
    """Como un celular: de 10 a 30 cuadros por segundo, con marcas de tiempo irregulares."""
    r = random.Random(semilla)
    siguiente = 0.0
    for t, m in sensor:
        if t >= siguiente:
            yield t, m
            siguiente = t + r.uniform(33, 100)


class TestSesionWeb(unittest.TestCase):
    def correr(self, programa, escenario, segundos):
        s = SesionWeb(fuente(programa))
        mensajes, ultimo = [], None
        sensor = SensorSimulado(escenario, duracion=segundos)
        for t, m in con_tasa_irregular(sensor):
            ultimo = json.loads(s.paso(t, json.dumps({k: v for k, v in m.items() if not k.startswith("_")})))
            mensajes += ultimo["mensajes"]
        return s, ultimo, mensajes, json.loads(s.terminar())

    def test_terapia_completa_la_rutina(self):
        s, ultimo, mensajes, fin = self.correr("terapia_facial.emo", "terapia", 120)
        self.assertEqual(fin["clase"], "rehabilitacion")
        self.assertEqual({n: len(v) for n, v in fin["ejercicios"].items()}, {"sonrisa": 5, "cejas": 5, "ojos": 5})
        self.assertIn("Sonría y sostenga", mensajes)
        self.assertIn("¡Rutina completa!", mensajes)
        self.assertEqual(ultimo["estados"], {"rutina": "terminado"})
        self.assertTrue(any(tipo == "repeticion" for _, tipo, _ in fin["bitacora"]))

    def test_conduccion_avisa_alarmas(self):
        s, ultimo, mensajes, fin = self.correr("conduccion.emo", "conduccion", 60)
        self.assertEqual(fin["clase"], "conduccion")
        self.assertGreater(fin["resumen"]["alarmas_emitidas"], 0)
        self.assertTrue(any(tipo == "alarma" for _, tipo, _ in fin["bitacora"]))

    def test_la_alerta_se_apaga_al_abrir_los_ojos(self):
        """Al cerrar los ojos la cabeza no se mueve: 'atento' también exige ojos abiertos,
        si no, la alarma de microsueño nunca se apagaba."""
        s = SesionWeb(fuente("conduccion.emo"))
        base = {"ear": 0.31, "mar": 0.05, "pitch": 0.0, "yaw": 0.0}
        t, e, estados = 0, None, []
        for dur, m in [(8000, base), (2500, dict(base, ear=0.05)), (5000, base)]:
            fin = t + dur
            while t < fin:
                e = json.loads(s.paso(t, json.dumps(m)))
                if not estados or estados[-1] != e["estados"]["monitor"]:
                    estados.append(e["estados"]["monitor"])
                t += 50
        # normal -> alerta (microsueño) -> normal (atento); después el PERCLOS alto
        # por los ojos cerrados puede pasarlo a 'somnoliento', que no tiene alarma.
        self.assertEqual(estados[:3], ["normal", "alerta", "normal"])
        self.assertFalse(e["alarma"])

    def test_el_tiempo_avanza_a_ritmo_fijo(self):
        s = SesionWeb(fuente("terapia_facial.emo"))
        s.paso(1000.0, "{}")
        self.assertEqual(s.k, 31)          # 0, 33.3, ..., 1000 ms a 30 fps
        estado = json.loads(s.paso(1010.0, json.dumps({"sonrisa": 0.9})))
        self.assertEqual(s.k, 31)          # todavía no toca otro cuadro
        self.assertIn("estados", estado)

    def test_programa_con_errores(self):
        with self.assertRaises(ValueError):
            SesionWeb("dominio x { gesto g = ear < 2.0 durante 1 s; }")


if __name__ == "__main__":
    unittest.main()
