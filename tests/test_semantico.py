"""Pruebas del gestor de errores con los programas de tests/semantic.

Cada archivo .emo tiene errores intencionales marcados con «// error:». El compilador
debe reportar exactamente los errores de su archivo .esperado, uno o más en cada línea
marcada y ninguno en las demás, y no debe generar código.
"""

import glob
import os
import unittest

from emolang.compilador import compilar

AQUI = os.path.dirname(os.path.abspath(__file__))
PROGRAMAS = sorted(glob.glob(os.path.join(AQUI, "semantic", "*.emo")))


def errores_de(ruta):
    with open(ruta, encoding="utf-8") as f:
        fuente = f.read()
    r = compilar(fuente)
    errores = sorted(r.reporte.errores, key=lambda d: (d.linea, d.columna))
    marcadas = {i for i, l in enumerate(fuente.splitlines(), 1) if "// error:" in l}
    return r, errores, marcadas


class TestErroresSemanticos(unittest.TestCase):
    def test_hay_programas(self):
        nombres = {os.path.basename(r) for r in PROGRAMAS}
        self.assertTrue({"tipos.emo", "no_declarados.emo", "alcance.emo", "funciones.emo"} <= nombres)

    def test_errores_iguales_a_esperado(self):
        for ruta in PROGRAMAS:
            with self.subTest(os.path.basename(ruta)):
                _, errores, _ = errores_de(ruta)
                with open(ruta[:-4] + ".esperado", encoding="utf-8") as f:
                    esperado = f.read()
                self.assertEqual("".join(str(d) + "\n" for d in errores), esperado)

    def test_cada_linea_marcada_tiene_su_error(self):
        for ruta in PROGRAMAS:
            with self.subTest(os.path.basename(ruta)):
                _, errores, marcadas = errores_de(ruta)
                self.assertEqual({d.linea for d in errores}, marcadas)

    def test_no_se_genera_codigo(self):
        for ruta in PROGRAMAS:
            with self.subTest(os.path.basename(ruta)):
                r, _, _ = errores_de(ruta)
                self.assertFalse(r.ok)
                self.assertIsNone(r.cuadruplas)

    def test_los_errores_no_detienen_el_analisis(self):
        # el gestor de errores reporta todos los errores de una sola pasada
        for ruta in PROGRAMAS:
            with self.subTest(os.path.basename(ruta)):
                _, errores, _ = errores_de(ruta)
                self.assertGreaterEqual(len(errores), 7)


if __name__ == "__main__":
    unittest.main()
