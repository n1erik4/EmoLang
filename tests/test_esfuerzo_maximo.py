"""Cada ejercicio se mide contra el esfuerzo máximo de la persona (emolang/perfil.py).

Un movimiento ligero (sonrisa, subir las cejas, cerrar los ojos) cuenta si es lo más que
esa persona puede hacer (por ejemplo, con parálisis facial), pero no si ya mostró que
puede moverse más.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

from emolang.perfil import PISOS, Perfil, umbral_en_foto
from emolang.web import SesionWeb

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "web"))
import servidor as S  # noqa: E402

with open(os.path.join(RAIZ, "ejemplos", "terapia_facial.emo"), encoding="utf-8") as f:
    TERAPIA = f.read()
REPOSO = {"sonrisa": 0.02, "sonrisa_izq": 0.02, "sonrisa_der": 0.02, "cejas": 0.1, "ear": 0.3}


class Rutina:
    """Sesión web de terapia alimentada a mano, como la cámara del celular."""

    def __init__(self, perfil=None):
        self.s = SesionWeb(TERAPIA, perfil=perfil)
        self.t = 0
        self.reps = 0
        self.correr(REPOSO, 1500)

    def correr(self, m, ms):
        fin = self.t + ms
        while self.t < fin:
            self.reps = json.loads(self.s.paso(self.t, json.dumps(m)))["repeticiones"]
            self.t += 33

    def hacer(self, cambios, ms=1200):
        antes = self.reps
        self.correr(dict(REPOSO, **cambios), ms)
        self.correr(REPOSO, 1000)
        return self.reps > antes

    def sonrisa(self, nivel):
        return self.hacer({"sonrisa": nivel, "sonrisa_izq": nivel, "sonrisa_der": nivel})

    def cejas(self, nivel):
        return self.hacer({"cejas": nivel})

    def ojos(self, ear):
        return self.hacer({"ear": ear}, ms=1500)

    def a_cejas(self):
        """Hace las 5 sonrisas para llegar al ejercicio de cejas."""
        for _ in range(5):
            assert self.sonrisa(0.8)

    def a_ojos(self):
        self.a_cejas()
        for _ in range(5):
            assert self.cejas(0.7)


class TestSonrisaMaxima(unittest.TestCase):
    def test_si_la_sonrisa_ligera_es_su_maximo_cuenta(self):
        r = Rutina()
        self.assertEqual([r.sonrisa(0.25) for _ in range(5)], [True] * 5)

    def test_si_puede_sonreir_mas_la_ligera_no_cuenta(self):
        r = Rutina()
        self.assertTrue(r.sonrisa(0.80))
        self.assertFalse(r.sonrisa(0.25))
        self.assertTrue(r.sonrisa(0.70))

    def test_la_cara_relajada_nunca_cuenta(self):
        r = Rutina()
        self.assertFalse(any(r.sonrisa(0.12) for _ in range(3)))
        self.assertAlmostEqual(0.6 * PISOS["sonrisa"], 0.18)        # lo más ligero que puede contar

    def test_la_sesion_anterior_marca_la_vara(self):
        r = Rutina(perfil=json.dumps({"sonrisa_maxima": 0.80}))
        self.assertFalse(r.sonrisa(0.25))               # ya se sabe que puede sonreír más
        self.assertTrue(r.sonrisa(0.60))
        self.assertGreaterEqual(json.loads(r.s.perfil())["sonrisa_maxima"], 0.6)

    def test_cejas_ligeras_si_son_su_maximo(self):
        r = Rutina()
        r.a_cejas()
        self.assertEqual([r.cejas(0.28) for _ in range(5)], [True] * 5)     # sube 0.18 desde 0.10

    def test_cejas_ligeras_no_cuentan_si_puede_subirlas_mas(self):
        r = Rutina()
        r.a_cejas()
        self.assertTrue(r.cejas(0.70))
        self.assertFalse(r.cejas(0.28))
        self.assertFalse(r.cejas(0.15))         # casi en reposo

    def test_cejas_altas_en_reposo_no_cuentan_como_movimiento(self):
        p = Perfil()
        for i in range(30):                         # su cara en reposo tiene las cejas en 0.40
            m = p.derivar(dict(REPOSO, cejas=0.40), i * 33.0)
        self.assertEqual(m["cejas_rel"], 0.0)
        m = p.derivar(dict(REPOSO, cejas=0.55), 1000.0)
        self.assertAlmostEqual(m["cejas_rel"], 0.15 / PISOS["cejas"])

    def test_ojos_que_no_cierran_del_todo_si_es_su_maximo(self):
        r = Rutina()
        r.a_ojos()
        self.assertEqual([r.ojos(0.20) for _ in range(5)], [True] * 5)      # cierra 1/3, no del todo

    def test_ojos_entrecerrados_no_cuentan_si_puede_cerrarlos(self):
        r = Rutina()
        r.a_ojos()
        self.assertTrue(r.ojos(0.05))
        self.assertFalse(r.ojos(0.20))

    def test_un_parpadeo_no_sube_la_vara_de_los_ojos(self):
        p = Perfil()
        t = 0.0
        for _ in range(30):
            p.derivar(dict(REPOSO), t); t += 33
        for _ in range(5):                      # parpadeo de ~150 ms
            p.derivar(dict(REPOSO, ear=0.05), t); t += 33
        for _ in range(30):
            p.derivar(dict(REPOSO), t); t += 33
        self.assertAlmostEqual(p.referencia("ojos"), PISOS["ojos"])

    def test_ojo_abierto_de_la_persona(self):
        p = Perfil()
        for i in range(20):
            p.derivar(dict(REPOSO, ear=0.25), i * 33.0)
        self.assertAlmostEqual(p.ear_abierto, 0.25)
        self.assertAlmostEqual(p.movimientos({"ear": 0.25})["ojos"], 0.0)

    def test_ojos_muy_abiertos_o_ceno_fruncido_no_atoran_la_rutina(self):
        r = Rutina()
        r.a_cejas()
        for _ in range(5):                                  # al subir las cejas abre mucho los ojos
            self.assertTrue(r.hacer({"cejas": 0.7, "ear": 0.42}))
        r.correr(dict(REPOSO, cejas=0.0), 400)              # frunce el ceño un momento
        r.correr(REPOSO, 1000)
        m = r.s.vm.perfil.derivar(dict(REPOSO), r.t)
        self.assertLess(m["ojos_rel"], 0.25)                # relajado sigue siendo relajado
        self.assertLess(m["cejas_rel"], 0.25)
        self.assertTrue(r.ojos(0.05))

    def test_umbral_en_fotos_sueltas(self):
        self.assertEqual((umbral_en_foto("sonrisa", 0.6), umbral_en_foto("cejas", 0.6), umbral_en_foto("ojos", 0.7)),
                         (0.18, 0.22, 0.216))

    def test_un_pico_de_ruido_no_sube_la_vara(self):
        p = Perfil()
        for i in range(20):
            p.derivar({"sonrisa": 0.4}, i * 33.0)
        p.derivar({"sonrisa": 0.95}, 700.0)              # un solo cuadro
        self.assertAlmostEqual(p.referencia("sonrisa"), 0.4)

    def test_perfil_invalido_se_ignora(self):
        self.assertEqual(Perfil.desde_dict({"sonrisa_maxima": "x"}).previas["sonrisa"], 0.0)
        self.assertEqual(Perfil.desde_dict(None).referencia("cejas"), PISOS["cejas"])
        viejo = Perfil.desde_dict({"sonrisa_maxima": 0.5})          # guardado antes de cejas y ojos
        self.assertEqual(viejo.previas, {"sonrisa": 0.5, "cejas": 0.0, "ojos": 0.0})


class TestPerfilEnElServidor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = os.path.join(self.tmp.name, "p.db")

    def tearDown(self):
        self.tmp.cleanup()

    def usuario(self, s, rol="terapia", correo="ana@x.mx"):
        token, _ = s.registrar({"nombre": "Ana", "correo": correo, "contrasena": "secreta123", "rol": rol,
                                "consentimiento": True})
        return s.usuario_de(token)

    def test_guardar_leer_y_validar(self):
        s = S.Servicio(S.Base(self.ruta))
        u = self.usuario(s)
        self.assertEqual(s.perfil(u), {"sonrisa_maxima": 0.0, "cejas_maxima": 0.0, "ojos_maxima": 0.0})
        s.guardar_perfil(u, {"sonrisa_maxima": 0.42, "cejas_maxima": 0.3, "ojos_maxima": 0.5})
        self.assertEqual(s.perfil(s.db.uno("SELECT * FROM usuarios WHERE id = ?", (u["id"],))),
                         {"sonrisa_maxima": 0.42, "cejas_maxima": 0.3, "ojos_maxima": 0.5})
        for malo in ({"sonrisa_maxima": 2}, {"sonrisa_maxima": "x"}, {"nariz_maxima": 0.2}, {}, []):
            with self.subTest(malo=malo), self.assertRaises(S.ErrorApi) as e:
                s.guardar_perfil(u, malo)
            self.assertEqual(e.exception.estado, 400)
        with self.assertRaises(S.ErrorApi) as e:
            s.guardar_perfil(self.usuario(s, rol="conductor", correo="b@x.mx"), {"sonrisa_maxima": 0.5})
        self.assertEqual(e.exception.estado, 403)
        s.db.con.close()

    def test_base_creada_antes_de_la_sonrisa_maxima(self):
        con = sqlite3.connect(self.ruta)
        con.executescript(S.ESQUEMA.replace(
            ",\n    perfil            TEXT              -- JSON (terapia): esfuerzo máximo de la persona en cada ejercicio", ""))
        con.close()
        s = S.Servicio(S.Base(self.ruta))      # agrega la columna sin perder nada
        u = self.usuario(s)
        s.guardar_perfil(u, {"sonrisa_maxima": 0.3})
        s.db.con.close()


if __name__ == "__main__":
    unittest.main()
