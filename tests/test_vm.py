"""Pruebas de las cuádruplas, el optimizador, el formato .emoc y la máquina virtual.

La prueba central es diferencial: el intérprete del AST (motor.py), EmoVM sin
optimizar y EmoVM optimizada deben producir exactamente la misma bitácora.
"""

import json
import os
import tempfile
import unittest

from emolang import emoc as E
from emolang.compilador import compilar, compilar_archivo
from emolang.ejecucion import ejecutar
from emolang.errores import ErrorEmoLang
from emolang.intermedio import resolver
from emolang.metricas import metricas_neutras
from emolang.modulos import ModuloBase
from emolang.motor import Motor
from emolang.sensores import SensorSimulado
from emolang.vm import EmoVM

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EJEMPLOS = os.path.join(RAIZ, "ejemplos")


def programa(cuerpo, estados="estado a { }", dominio="d", sensor=""):
    return f"""dominio {dominio} {{
        sensor camara {{ {sensor} var fps : int = 10; }}
        {cuerpo}
        maquina m inicial a {{ {estados} }}
    }}"""


def compilado(fuente):
    r = compilar(fuente)
    assert r.ok, [str(d) for d in r.reporte.errores]
    return r


def errores(fuente):
    return [d.mensaje for d in compilar(fuente).reporte.errores]


def ops(r, bloque, dominio="d", optimizado=True):
    prog = (r.optimizado if optimizado else r.cuadruplas)[dominio]
    return [c.op for c in resolver(prog.bloques[bloque])]


def correr(fabrica, cuadros):
    """Ejecuta los cuadros y devuelve todo lo observable: bitácora, salida y estados."""
    salida = []
    modulo = ModuloBase(salida=salida.append)
    m = fabrica(modulo)
    estados, error = [], None
    try:
        for t, metricas in cuadros:
            m.paso(t, metricas)
            estados.append(dict(m.estado_actual()))
    except ErrorEmoLang as e:
        error = e.mensaje if hasattr(e, "mensaje") else str(e)
    return {"bitacora": modulo.bitacora, "salida": salida, "estados": estados,
            "reps": modulo.reps, "error": error}


def tres_versiones(r, dominio, cuadros):
    cuadros = list(cuadros)
    return (correr(lambda mod: Motor(r.analisis, r.automatas, dominio, mod), cuadros),
            correr(lambda mod: EmoVM(r.emoc_sin_optimizar(), dominio, mod), cuadros),
            correr(lambda mod: EmoVM(r.emoc_para_evaluar(), dominio, mod), cuadros))


class TestEquivalencia(unittest.TestCase):
    def iguales(self, r, dominio, cuadros):
        motor, vm, optimizada = tres_versiones(r, dominio, cuadros)
        self.assertEqual(motor, vm, "EmoVM sin optimizar difiere del motor")
        self.assertEqual(motor, optimizada, "EmoVM optimizada difiere del motor")
        return motor

    def test_ejemplos_con_varias_semillas_y_ruido(self):
        for archivo, dominio, escenarios in [
            ("conduccion.emo", "conduccion", ["conduccion", "normal"]),
            ("rehabilitacion.emo", "rehabilitacion", ["rehabilitacion"]),
            ("terapia_facial.emo", "terapia_facial", ["terapia"]),
        ]:
            r = compilar_archivo(os.path.join(EJEMPLOS, archivo))
            for esc in escenarios:
                for semilla in range(5):
                    for ruido in (1.0, 3.0):
                        with self.subTest(archivo=archivo, esc=esc, semilla=semilla, ruido=ruido):
                            s = SensorSimulado(esc, semilla=semilla, ruido=0.012 * ruido)
                            self.iguales(r, dominio, s)

    def cuadros(self, n=60, **cambios):
        return [(i * 100.0, dict(metricas_neutras(), **cambios)) for i in range(n)]

    def test_control_de_flujo_y_alcances(self):
        r = compilado(programa('''
            var n : int = 0; var t1 : int = 5; var c1 : decimal = 0.5; var fijo : int = 2;
            var r : proporcion = 40%; var d : duracion = 1.5 s;
            gesto cerrado = ear < 0.2 durante 200 ms;
        ''', '''
            estado a {
                var n2 : int = 3;
                var lema : string = "hola";
                al_entrar {
                    var n : int = 7;
                    n = n + fijo;
                    repetir 3 veces { var k : int = n; k = k + 1; mostrar("k", k, r, d, verdadero, c1); }
                    repetir fijo veces { repetir 2 veces { t1 = t1 + 1; } }
                    repetir n2 + 3 veces { t1 = t1 + 1; }
                    repetir 0 veces { t1 = 100; }
                    si n > 100 { registrar("no"); } sino si n > 8 { registrar("si " + n); }
                    sino { registrar("otro"); }
                    registrar(lema + " " + t1 + " " + r + " " + d + " " + (c1 + 0.25));
                }
                cuando cerrado {
                    n = n + 1;
                    si n >= 2 { ir_a b; }
                    registrar("sigue");
                }
                mientras tiempo_en_estado() > 3 s { n = n + 1000; registrar("t " + n); }
            }
            estado b {
                al_entrar { registrar("en b " + n); si n > 1 { ir_a c; } registrar("no llega"); }
            }
            estado c {
                cuando tras 1 s ir_a a;
            }
        '''))
        patron = [(i * 100.0, dict(metricas_neutras(), ear=0.1 if (i // 4) % 2 else 0.3))
                  for i in range(120)]
        obs = self.iguales(r, "d", patron)
        self.assertGreater(len(obs["bitacora"]), 5)

    def test_corto_circuito_evita_division_entre_cero(self):
        r = compilado(programa("var z : int = 0;", '''
            estado a { al_entrar {
                si z != 0 y 10 / z > 1 { registrar("no"); } sino { registrar("protegido"); }
                si z == 0 o 10 / z > 1 { registrar("protegido o"); }
            } }'''))
        obs = self.iguales(r, "d", self.cuadros(3))
        self.assertIsNone(obs["error"])

    def test_division_entre_cero_falla_al_ejecutar(self):
        r = compilado(programa("var z : decimal = 0.0;", '''
            estado a { al_entrar { z = 10 / z; registrar("no"); } }'''))
        obs = self.iguales(r, "d", self.cuadros(3))
        self.assertIn("división entre cero", obs["error"])

    def test_dos_maquinas_con_los_mismos_nombres(self):
        fuente = '''dominio d { sensor cam { var fps : int = 10; }
            var total : int = 0;
            maquina m1 inicial a { estado a { var x : int = 1; al_entrar { total = total + x; } } }
            maquina m2 inicial a { estado a { var x : int = 10; al_entrar { total = total + x; registrar("t" + total); } } }
        }'''
        obs = self.iguales(compilado(fuente), "d", self.cuadros(2))
        self.assertEqual(obs["bitacora"][-1][2], "t11")


class TestTerapiaFacial(unittest.TestCase):
    def setUp(self):
        self.r = compilar_archivo(os.path.join(EJEMPLOS, "terapia_facial.emo"))

    def test_compila_sin_advertencias(self):
        self.assertEqual([str(d) for d in self.r.reporte.diagnosticos], [])

    def test_rutina_completa_con_simetria_por_ejercicio(self):
        res = ejecutar(self.r, "terapia_facial", SensorSimulado("terapia", semilla=1), verbose=False)
        self.assertEqual(res.motor.estado_actual(), {"rutina": "terminado"})
        for nombre in ("sonrisa", "cejas", "ojos"):
            self.assertEqual(res.resumen[f"ejercicio {nombre}"]["repeticiones"], 5)
        registros = [d for _, t, d in res.modulo.bitacora if t == "registro"]
        for texto in ("sonrisa asimétrica", "cejas asimétricas", "cierre de ojos asimétrico"):
            self.assertTrue(any(texto in r for r in registros), registros)

    def test_varias_semillas_terminan_la_rutina(self):
        for semilla in range(10):
            res = ejecutar(self.r, "terapia_facial", SensorSimulado("terapia", semilla=semilla), verbose=False)
            self.assertEqual(res.resumen["repeticiones"], 15, semilla)

    def test_un_gesto_de_otro_ejercicio_no_cuenta(self):
        cuadros = [(i * 100.0, dict(metricas_neutras(), cejas=0.8 if i > 10 else 0.2)) for i in range(40)]
        obs = correr(lambda mod: EmoVM(self.r.emoc, "terapia_facial", mod), cuadros)
        self.assertEqual(obs["reps"], [])

    def test_contar_ejercicio_solo_en_terapia(self):
        fuente = programa("", 'estado a { al_entrar { contar_ejercicio("x", 0.5); } }', dominio="conduccion")
        self.assertTrue(any("rehabilitacion" in m for m in errores(fuente)))


class TestCuadruplas(unittest.TestCase):
    def test_precedencia_en_el_orden_de_las_cuadruplas(self):
        r = compilado(programa("var n : decimal = 0.0; var v : int = 1; var f : int = 2;",
                               "estado a { al_entrar { n = v + 0.5 * f; } }"))
        filas = [c.fila() for c in r.cuadruplas["d"].bloques["a.al_entrar"]]
        self.assertEqual(filas[:3], [("*", "0.5", "f", "t1"), ("+", "v", "t1", "t2"), ("=", "t2", "–", "n")])

    def test_pila_semantica_queda_vacia_y_se_traza(self):
        fuente = programa("var n : decimal = 0.0; var v : int = 1; var f : int = 2;",
                          "estado a { al_entrar {\n n = v + 0.5 * f;\n } }")
        r = compilado(fuente)
        traza = r.cuadruplas["d"].trazas[5]
        self.assertEqual(traza[-1]["pila"], [])
        self.assertEqual(traza[-1]["cuadrupla"], "(=, t2, –, n)")
        self.assertIn("(*, 0.5, f, t1)", [p["cuadrupla"] for p in traza])

    def test_saltos_resueltos(self):
        r = compilado(programa("var v : int = 1;", '''estado a { al_entrar {
            si v > 0 { v = 2; } sino { v = 3; } } }'''))
        filas = resolver(r.cuadruplas["d"].bloques["a.al_entrar"])
        self.assertEqual([c.op for c in filas], [">", "gotoF", "=", "goto", "=", "ret"])
        self.assertEqual(filas[1].res, 5)
        self.assertEqual(filas[3].res, 6)


class TestOptimizador(unittest.TestCase):
    def test_propagacion_y_plegado(self):
        r = compilado(programa("var u : proporcion = 0.2; var g : decimal = 20.0;"
                               "gesto x = yaw < -g y ear < u durante 1 s;",
                               "estado a { cuando x ir_a a; }"))
        self.assertEqual(ops(r, "gestos", optimizado=False)[:2], ["neg", "<"])
        filas = [c.fila() for c in r.optimizado["d"].bloques["gestos"]]
        self.assertIn(("<", "yaw", "-20", "t2"), filas)
        self.assertIn(("<", "ear", "0.2", "t3"), filas)
        # las variables propagadas dejan de escribirse
        self.assertNotIn("u", [c.res for c in r.optimizado["d"].bloques["init"]])

    def test_variable_modificada_no_se_propaga(self):
        r = compilado(programa("var u : proporcion = 0.2; gesto x = ear < u durante 1 s;",
                               'estado a { cuando x { u = 0.1; registrar("x"); } }'))
        self.assertIn(("<", "ear", "u", "t1"), [c.fila() for c in r.optimizado["d"].bloques["gestos"]])

    def test_subexpresion_comun_en_gestos(self):
        r = compilado(programa("gesto a1 = ear < 0.2 y mar < 0.3 durante 1 s;"
                               "gesto a2 = ear < 0.2 y mar < 0.3 durante 2 s;",
                               "estado a { cuando a1 ir_a a; cuando a2 ir_a a; }"))
        afds = [c for c in r.optimizado["d"].bloques["gestos"] if c.op == "afd"]
        self.assertEqual(afds[0].a1, afds[1].a1)
        self.assertEqual(ops(r, "gestos").count("<"), 2)

    def test_mirilla(self):
        r = compilado(programa("var n : int = 0;", 'estado a { al_entrar { n = n + 1; registrar("n" + n); } }'))
        self.assertIn(("+", "n", "1", "n"), [c.fila() for c in r.optimizado["d"].bloques["a.al_entrar"]])

    def test_desenrollado_hasta_cuatro(self):
        r = compilado(programa("", 'estado a { al_entrar { repetir 4 veces { registrar("x"); } } }'))
        self.assertEqual(ops(r, "a.al_entrar"), ["param", "call"] * 4 + ["ret"])
        r = compilado(programa("", 'estado a { al_entrar { repetir 5 veces { registrar("x"); } } }'))
        self.assertIn("gotoF", ops(r, "a.al_entrar"))

    def test_codigo_muerto(self):
        r = compilado(programa("var cuenta : int = 0; gesto g = ear < 0.2 durante 1 s;"
                               "gesto sin_uso = mar > 0.5 durante 1 s;",
                               "estado a { cuando g { cuenta = cuenta + 1; } ignorar sin_uso; }"))
        self.assertEqual(ops(r, "a.cuando.g"), ["ret"])          # nadie lee 'cuenta'
        self.assertEqual(r.optimizado["d"].gestos, ["g"])
        self.assertEqual(r.informes["d"].gestos_quitados, ["sin_uso"])

    def test_salto_constante_y_codigo_inalcanzable(self):
        r = compilado(programa("var modo : int = 1;", '''estado a { al_entrar {
            si modo == 1 { registrar("uno"); } sino { registrar("otro"); } } }'''))
        self.assertEqual(ops(r, "a.al_entrar"), ["param", "call", "ret"])

    def test_gestos_de_una_secuencia_se_conservan(self):
        r = compilado(programa("gesto g1 = ear < 0.2 durante 1 s; gesto g2 = mar > 0.5 durante 1 s;"
                               "secuencia s1 = [g1, g2] en 5 s;",
                               "estado a { cuando s1 ir_a a; }"))
        self.assertEqual(r.optimizado["d"].gestos, ["g1", "g2"])

    def test_el_optimizado_es_mas_corto_en_los_ejemplos(self):
        for archivo in ("conduccion.emo", "rehabilitacion.emo"):
            r = compilar_archivo(os.path.join(EJEMPLOS, archivo))
            inf = next(iter(r.informes.values()))
            self.assertLess(sum(inf.despues.values()), sum(inf.antes.values()))


class TestEmoc(unittest.TestCase):
    def test_ida_y_vuelta_por_archivo(self):
        r = compilar_archivo(os.path.join(EJEMPLOS, "conduccion.emo"))
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "p.emoc")
            E.guardar(r.emoc, ruta)
            cargado = E.cargar(ruta)
        directo = ejecutar(r, "conduccion", SensorSimulado("conduccion", semilla=1), verbose=False)
        desde_archivo = ejecutar(r, "conduccion", SensorSimulado("conduccion", semilla=1), verbose=False,
                                 emoc=cargado)
        self.assertEqual(directo.modulo.bitacora, desde_archivo.modulo.bitacora)

    def test_rechaza_otros_archivos(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "x.emoc")
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump({"formato": "otro"}, f)
            with self.assertRaises(ValueError):
                E.cargar(ruta)


class TestLenguaje(unittest.TestCase):
    def test_metrica_no_habilitada(self):
        msgs = errores(programa("gesto g = sonrisa > 0.5 durante 1 s;", "estado a { cuando g ir_a a; }",
                                sensor="usar ear, mar;"))
        self.assertTrue(any("no está habilitada" in m for m in msgs))

    def test_usar_con_nombre_invalido(self):
        msgs = errores(programa("", sensor="usar velocidad;"))
        self.assertTrue(any("no es una métrica" in m for m in msgs))

    def test_sin_usar_se_permiten_todas(self):
        self.assertEqual(errores(programa("gesto g = sonrisa > 0.5 durante 1 s;",
                                          "estado a { cuando g ir_a a; }")), [])

    def test_alarma_fuera_de_su_dominio(self):
        msgs = errores(programa("", 'estado a { al_entrar { alarma("x"); } }', dominio="rehabilitacion"))
        self.assertTrue(any("solo está disponible en el dominio conduccion" in m for m in msgs))

    def test_conteo_fuera_de_su_dominio(self):
        msgs = errores(programa("", "estado a { al_entrar { contar_repeticion(); } }", dominio="conduccion"))
        self.assertTrue(any("solo está disponible en el dominio rehabilitacion" in m for m in msgs))

    def test_secuencia_con_mas_de_cinco_gestos(self):
        msgs = errores(programa("gesto g = ear < 0.2 durante 1 s; secuencia s1 = [g, g, g, g, g, g];",
                                "estado a { cuando s1 ir_a a; }"))
        self.assertTrue(any("el máximo es 5" in m for m in msgs))

    def test_tras_cambia_de_estado(self):
        r = compilado(programa("", "estado a { cuando tras 1 s ir_a b; } estado b { }"))
        res = correr(lambda mod: EmoVM(r.emoc, "d", mod),
                     [(i * 100.0, metricas_neutras()) for i in range(12)])
        self.assertEqual(res["estados"][9], {"m": "a"})
        self.assertEqual(res["estados"][10], {"m": "b"})

    def test_tras_requiere_duracion_constante_positiva(self):
        self.assertTrue(errores(programa("", "estado a { cuando tras 5 ir_a a; }")))
        self.assertTrue(errores(programa("", "estado a { cuando tras 0 s ir_a a; }")))

    def test_tras_contradictorio(self):
        msgs = errores(programa("", "estado a { cuando tras 1 s ir_a b; cuando tras 1 s ir_a c; } "
                                    "estado b { } estado c { }"))
        self.assertTrue(any("contradictorias" in m for m in msgs))

    def test_tras_cuenta_para_estados_alcanzables(self):
        self.assertEqual(errores(programa("", "estado a { cuando tras 1 s ir_a b; } estado b { }")), [])
        msgs = errores(programa("", "estado a { } estado b { }"))
        self.assertTrue(any("inalcanzable" in m for m in msgs))


if __name__ == "__main__":
    unittest.main()
