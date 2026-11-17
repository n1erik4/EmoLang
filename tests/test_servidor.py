"""Pruebas del servidor web: usuarios, roles y sesiones guardadas (web/servidor.py)."""

import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "web"))
import servidor as S  # noqa: E402


def resultado_terapia(n=5):
    return {"dominio": "terapia_facial", "clase": "rehabilitacion", "duracion_s": 42.0,
            "resumen": {"repeticiones": n}, "ejercicios": {"sonrisa": [0.9] * n},
            "bitacora": [[1.0, "repeticion", "sonrisa #1 simetria=0.90"]]}


class TestServicio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = S.Servicio(S.Base(os.path.join(self.tmp.name, "p.db")))

    def tearDown(self):
        self.s.db.con.close()
        self.tmp.cleanup()

    def registrar(self, correo="ana@ejemplo.mx", rol="terapia", **kw):
        datos = {"nombre": "Ana", "correo": correo, "contrasena": "secreta123", "rol": rol, "consentimiento": True}
        datos.update(kw)
        return self.s.registrar(datos)

    def test_registro_y_entrada(self):
        token, u = self.registrar()
        self.assertEqual((u["rol"], u["modulo"]), ("terapia", "terapia"))
        self.assertEqual(self.s.usuario_de(token)["correo"], "ana@ejemplo.mx")
        token2, u2 = self.s.entrar({"correo": "ANA@ejemplo.mx", "contrasena": "secreta123"})
        self.assertEqual(u2["id"], u["id"])
        self.s.salir(token2)
        self.assertIsNone(self.s.usuario_de(token2))

    def test_la_contrasena_no_se_guarda_en_claro(self):
        self.registrar()
        fila = self.s.db.uno("SELECT * FROM usuarios")
        self.assertNotIn(b"secreta123", bytes(fila["hash"]))
        self.assertEqual(len(fila["hash"]), 32)

    def test_errores_de_registro(self):
        casos = [({"rol": "medico"}, "tipo de usuario"), ({"consentimiento": False}, "aviso de privacidad"),
                 ({"contrasena": "corta"}, "8 caracteres"), ({"correo": "no-es-correo"}, "correo")]
        for cambio, texto in casos:
            with self.subTest(cambio=cambio), self.assertRaises(S.ErrorApi) as e:
                self.registrar(correo=cambio.pop("correo", "x@y.mx"), **cambio)
            self.assertIn(texto, e.exception.mensaje)
        self.registrar()
        with self.assertRaises(S.ErrorApi) as e:
            self.registrar()
        self.assertEqual(e.exception.estado, 409)

    def test_contrasena_incorrecta(self):
        self.registrar()
        for datos in ({"correo": "ana@ejemplo.mx", "contrasena": "otra12345"}, {"correo": "nadie@x.mx", "contrasena": "x"}):
            with self.assertRaises(S.ErrorApi) as e:
                self.s.entrar(datos)
            self.assertEqual(e.exception.estado, 401)

    def test_cada_rol_guarda_solo_su_modulo(self):
        _, ana = self.registrar()
        _, beto = self.registrar("beto@ejemplo.mx", "conductor")
        ana, beto = (self.s.db.uno("SELECT * FROM usuarios WHERE id = ?", (u["id"],)) for u in (ana, beto))
        sesion = {"modulo": "terapia", "fecha": "2026-11-17T10:00:00Z", "simetria_minima": 0.8,
                  "resultado": resultado_terapia()}
        self.s.guardar_sesion(ana, sesion)
        with self.assertRaises(S.ErrorApi) as e:
            self.s.guardar_sesion(beto, sesion)
        self.assertEqual(e.exception.estado, 403)
        self.assertEqual(len(self.s.sesiones(ana)), 1)
        self.assertEqual(self.s.sesiones(beto), [])          # nadie ve las sesiones de otra persona
        guardada = self.s.sesiones(ana)[0]
        self.assertEqual(guardada["r"]["ejercicios"]["sonrisa"], [0.9] * 5)
        self.assertEqual(guardada["simetria_minima"], 0.8)

    def test_borrar_cuenta_borra_sus_datos(self):
        token, u = self.registrar()
        fila = self.s.db.uno("SELECT * FROM usuarios WHERE id = ?", (u["id"],))
        self.s.guardar_sesion(fila, {"modulo": "terapia", "fecha": "2026-11-17T10:00:00Z", "resultado": resultado_terapia()})
        self.s.borrar_cuenta(fila)
        self.assertIsNone(self.s.usuario_de(token))
        self.assertEqual(self.s.db.uno("SELECT COUNT(*) AS n FROM sesiones")["n"], 0)


class TestHttp(unittest.TestCase):
    """La API a través de HTTP, con la cookie de sesión."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        servicio = S.Servicio(S.Base(os.path.join(cls.tmp.name, "h.db")))
        with open(os.path.join(cls.tmp.name, "index.html"), "w") as f:
            f.write("<!doctype html><title>EmoLang</title>")
        cls.httpd = S.http.server.ThreadingHTTPServer(("127.0.0.1", 0), S.manejador(servicio, cls.tmp.name, False))
        cls.puerto = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def pedir(self, metodo, ruta, datos=None, cookie=None, tipo="application/json"):
        c = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=10)
        cabeceras = {}
        if datos is not None:
            cabeceras["Content-Type"] = tipo
        if cookie:
            cabeceras["Cookie"] = cookie
        c.request(metodo, ruta, body=json.dumps(datos) if datos is not None else None, headers=cabeceras)
        r = c.getresponse()
        cuerpo = r.read()
        return r.status, r.getheader("Set-Cookie"), (json.loads(cuerpo) if r.getheader("Content-Type", "").startswith("application/json") else cuerpo)

    def test_flujo_completo(self):
        estado, _, _ = self.pedir("GET", "/api/yo")
        self.assertEqual(estado, 401)
        estado, cookie, u = self.pedir("POST", "/api/registro", {"nombre": "Carla", "correo": "carla@x.mx",
                                                                 "contrasena": "secreta123", "rol": "conductor",
                                                                 "consentimiento": True})
        self.assertEqual(estado, 201)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        galleta = cookie.split(";")[0]
        estado, _, u = self.pedir("GET", "/api/yo", cookie=galleta)
        self.assertEqual((estado, u["rol"], u["modulo"]), (200, "conductor", "conduccion"))
        sesion = {"modulo": "conduccion", "fecha": "2026-11-17T10:00:00Z",
                  "resultado": {"duracion_s": 60, "resumen": {"alarmas_emitidas": 2}, "bitacora": []}}
        self.assertEqual(self.pedir("POST", "/api/sesiones", sesion, galleta)[0], 201)
        sesion["modulo"] = "terapia"
        self.assertEqual(self.pedir("POST", "/api/sesiones", sesion, galleta)[0], 403)
        estado, _, lista = self.pedir("GET", "/api/sesiones", cookie=galleta)
        self.assertEqual([x["r"]["resumen"]["alarmas_emitidas"] for x in lista], [2])
        estado, cookie, _ = self.pedir("POST", "/api/salir", {}, galleta)
        self.assertIn("Max-Age=0", cookie)
        self.assertEqual(self.pedir("GET", "/api/sesiones", cookie=galleta)[0], 401)

    def test_solo_acepta_json(self):
        estado, _, r = self.pedir("POST", "/api/entrar", {"correo": "a@b.mx"}, tipo="text/plain")
        self.assertEqual(estado, 415)

    def test_sirve_la_pagina(self):
        estado, _, cuerpo = self.pedir("GET", "/")
        self.assertEqual(estado, 200)
        self.assertIn(b"EmoLang", cuerpo)


if __name__ == "__main__":
    unittest.main()
