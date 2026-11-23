"""Pruebas del reporte de fotos fijas (sin MediaPipe: las métricas se escriben a mano)."""

import csv
import os
import shutil
import tempfile
import unittest

from emolang import fotos as F

AQUI = os.path.dirname(os.path.abspath(__file__))
PROGRAMA = os.path.join(os.path.dirname(AQUI), "ejemplos", "terapia_facial.emo")


def fila(etiqueta, archivo, sonrisa=0.05, cejas=0.1, ear=0.3, rostro=1, tam=0.4, yaw=0.0, sim=0.95):
    return {"etiqueta": etiqueta, "archivo": archivo, "rostro": rostro, "ear": ear, "ear_izq": ear, "ear_der": ear,
            "mar": 0.05, "sonrisa": sonrisa, "sonrisa_izq": sonrisa, "sonrisa_der": sonrisa, "cejas": cejas,
            "cejas_izq": cejas, "cejas_der": cejas, "simetria_sonrisa": sim, "simetria_cejas": sim,
            "simetria_ojos": sim, "pitch": 0.0, "yaw": yaw, "tam_rostro": tam}


class TestReporteFotos(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.csv = os.path.join(self.dir, "metricas.csv")
        filas = [
            fila("sonrisa", "sonrisa/a.jpg", sonrisa=0.9, sim=0.6),
            fila("sonrisa", "sonrisa/b.jpg", sonrisa=0.7),
            fila("sonrisa", "sonrisa/c.jpg", sonrisa=0.3),            # sonrisa leve: cuenta si es lo máximo que la persona sonríe
            fila("sonrisa", "sonrisa/lejos.jpg", sonrisa=0.9, tam=0.05),   # cara pequeña: no cuenta
            fila("sonrisa", "sonrisa/mala.jpg", sonrisa=0.0),         # descartada en la revisión
            fila("cejas", "cejas/a.jpg", cejas=0.8),
            fila("cejas", "cejas/perfil.jpg", cejas=0.8, yaw=60.0),  # de perfil: no cuenta
            fila("ojos_cerrados", "ojos_cerrados/a.jpg", ear=0.08),
            fila("neutra", "neutra/a.jpg"),
            fila("neutra", "neutra/b.jpg", sonrisa=0.45),            # falsa alarma de sonrisa
            fila("neutra", "neutra/sin.jpg", rostro=0),
        ]
        with open(self.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=F.COLUMNAS)
            w.writeheader()
            for x in filas:
                if not x["rostro"]:
                    x = {"etiqueta": x["etiqueta"], "archivo": x["archivo"], "rostro": 0}
                w.writerow(x)
        with open(os.path.join(self.dir, "descartadas.txt"), "w", encoding="utf-8") as f:
            f.write("sonrisa/mala.jpg\n")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_cuenta_aciertos_y_falsas_alarmas(self):
        texto = F.reporte(self.csv, PROGRAMA, self.dir)
        self.assertIn("descartadas en la revisión: 1", texto)
        self.assertIn("sin rostro detectado: 1", texto)
        self.assertIn("**útiles: 7**", texto)
        # sonreir: 2 de 3 sonrisas pasan 0.4; 1 de 4 negativas (neutra b) es falsa alarma
        self.assertIn("| sonreir | sonrisa > 0.18 | 3 | 0 | 1 | 100.0% | 75.0% |", texto)
        self.assertIn("| cerrar_ojos | ear < 0.216 | 1 | 0 | 0 | 100.0% | 100.0% |", texto)
        self.assertIn("| sonrisa | 3 | ", texto)

    def test_mejor_umbral_separa_las_fotos(self):
        u, _, sens, espec = F._mejor_umbral([0.9, 0.7, 0.5], [0.1, 0.2, 0.45], "mayor")
        self.assertEqual((sens, espec), (1.0, 1.0))
        self.assertTrue(0.45 <= u < 0.5)

    def test_umbrales_vienen_del_programa(self):
        self.assertEqual(F.umbrales_del_programa(PROGRAMA), {"sonrisa": 0.18, "cejas": 0.22, "ear": 0.216})


if __name__ == "__main__":
    unittest.main()
