"""Pruebas de cada fase del compilador y del motor.

Ejecutar desde la raíz del proyecto:  python -m unittest -v
"""

import os
import unittest

from emolang import automatas as A
from emolang.compilador import compilar, compilar_archivo
from emolang.ejecucion import ejecutar
from emolang.lexico import analizar as lexico
from emolang.motor import Motor
from emolang.modulos import ModuloBase
from emolang.metricas import metricas_neutras
from emolang.sensores import SensorSimulado

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EJEMPLOS = os.path.join(RAIZ, "ejemplos")


def envolver(cuerpo, estados='estado a { }', extra=""):
    return f"""
    dominio d {{
        sensor camara {{ var fps : int = 10; }}
        {cuerpo}
        maquina m inicial a {{ {estados} }}
        {extra}
    }}"""


def mensajes(fuente, nivel="error"):
    r = compilar(fuente)
    return [d.mensaje for d in r.reporte.diagnosticos if d.nivel == nivel]


def contiene(lista, texto):
    return any(texto in m for m in lista)


class TestLexico(unittest.TestCase):
    def tipos(self, fuente):
        toks, rep = lexico(fuente)
        return [t.tipo for t in toks], rep

    def test_palabras_reservadas_e_identificadores(self):
        tipos, _ = self.tipos("gesto parpadeo = ear < 0.2 durante 100 ms;")
        self.assertEqual(tipos, ["GESTO", "ID", "ASIGNACION", "ID", "MENOR", "DECIMAL",
                                 "DURANTE", "ENTERO", "MS", "PUNTO_COMA", "EOF"])

    def test_unidades_pegadas_y_porcentaje(self):
        tipos, rep = self.tipos("100ms 2s 1.5s 40%")
        self.assertEqual(tipos, ["ENTERO", "MS", "ENTERO", "S", "DECIMAL", "S", "ENTERO", "PORCIENTO", "EOF"])
        self.assertFalse(rep.tiene_errores())

    def test_operadores_dobles_y_comentarios(self):
        tipos, _ = self.tipos("a <= b // comentario\n /* bloque */ c != d")
        self.assertEqual(tipos, ["ID", "MENOR_IGUAL", "ID", "ID", "DISTINTO", "ID", "EOF"])

    def test_errores_lexicos(self):
        _, rep = self.tipos('x = 3abc; y = "sin cerrar\n @')
        msgs = [d.mensaje for d in rep.errores]
        self.assertTrue(contiene(msgs, "no puede iniciar con dígito"))
        self.assertTrue(contiene(msgs, "cadena sin cerrar"))
        self.assertTrue(contiene(msgs, "carácter no reconocido"))

    def test_posiciones(self):
        toks, _ = lexico("dominio\n  x")
        self.assertEqual((toks[1].linea, toks[1].columna), (2, 3))


class TestSintactico(unittest.TestCase):
    def test_ejemplos_validos(self):
        for nombre in ("conduccion.emo", "rehabilitacion.emo"):
            r = compilar_archivo(os.path.join(EJEMPLOS, nombre))
            self.assertTrue(r.ok, [str(d) for d in r.reporte.errores])

    def test_precedencia(self):
        r = compilar(envolver("var x : bool = 1 + 2 * 3 > 6 y no falso;"), hasta="sintactico")
        expr = r.ast.dominios[0].variables[0].valor
        self.assertEqual(expr.op, "y")
        self.assertEqual(expr.izq.op, ">")
        self.assertEqual(expr.izq.izq.der.op, "*")

    def test_literales_de_dominio(self):
        r = compilar(envolver("var a : duracion = 2 s; var b : proporcion = 40%;"), hasta="sintactico")
        a, b = r.ast.dominios[0].variables
        self.assertEqual((a.valor.valor, a.valor.tipo_lit), (2000.0, "duracion"))
        self.assertEqual((b.valor.valor, b.valor.tipo_lit), (0.4, "proporcion"))

    def test_recuperacion_reporta_varios_errores(self):
        fuente = envolver("var x : int = ; gesto g = ear < 0.2 ; var y int = 3;")
        errores = mensajes(fuente)
        self.assertGreaterEqual(len(errores), 3)
        self.assertTrue(contiene(errores, "durante"))

    def test_mientras_fuera_de_estado(self):
        fuente = envolver("", "estado a { al_entrar { mientras verdadero { } } }")
        self.assertTrue(contiene(mensajes(fuente), "mientras"))


class TestSemantico(unittest.TestCase):
    def test_conversiones_validas(self):
        fuente = envolver("""
            var a : decimal = 3 + 0.5;
            var b : proporcion = 0.25;
            var c : decimal = b;
            var d : duracion = 1 s + 500 ms;
            var e : bool = d > 1200 ms;
            var f : string = "n=" + 3;
            gesto g = ear < b durante d;""", "estado a { cuando g ir_a a; }")
        self.assertEqual(mensajes(fuente), [])

    def test_errores_de_tipo(self):
        fuente = envolver("""
            var a : int = 2.5;
            var b : duracion = 5;
            var c : bool = 1 s > 3;
            var e : int = verdadero + 1;""")
        errores = mensajes(fuente)
        self.assertTrue(contiene(errores, "no se puede asignar decimal"))
        self.assertTrue(contiene(errores, "no se puede asignar int a la variable 'b'"))
        self.assertTrue(contiene(errores, "indique la unidad"))
        self.assertTrue(contiene(errores, "no aplicable a bool"))

    def test_ambitos(self):
        fuente = envolver("var global_ : int = 0;", """
            estado a {
                var local : int = 1;
                al_entrar { local = local + global_; var b : int = 2; }
                cuando g { b = 3; }
            }""", extra="gesto g = ear < 0.2 durante 1 s;")
        errores = mensajes(fuente)
        self.assertEqual(errores, ["variable 'b' no declarada"])

    def test_redeclaracion_y_reservados(self):
        errores = mensajes(envolver("var x : int = 1; var x : int = 2; var ear : decimal = 0.3;"))
        self.assertTrue(contiene(errores, "ya fue declarado"))
        self.assertTrue(contiene(errores, "nombre reservado"))

    def test_metricas_solo_lectura_y_funciones(self):
        errores = mensajes(envolver("", 'estado a { al_entrar { ear = 0.1; alarma(3); var x : int = registrar("a"); } }'))
        self.assertTrue(contiene(errores, "no se puede asignar"))
        self.assertTrue(contiene(errores, "se esperaba string"))
        self.assertTrue(contiene(errores, "no devuelve un valor"))

    def test_tabla_de_simbolos(self):
        r = compilar(envolver("var u : proporcion = 30%;"), hasta="semantico")
        sim = {s.nombre: s for s in r.analisis.tabla}
        self.assertEqual(sim["fps"].ambito, "sensor camara")
        self.assertAlmostEqual(sim["u"].valor, 0.3)
        self.assertEqual(sim["a"].categoria, "estado")


class TestValidacionesDominio(unittest.TestCase):
    def test_umbral_fuera_de_rango(self):
        errores = mensajes(envolver("var p : proporcion = 120%; gesto g = ear > 1.5 durante 1 s;",
                                    "estado a { cuando g ir_a a; }"))
        self.assertTrue(contiene(errores, "proporcion debe estar entre 0 y 1"))
        self.assertTrue(contiene(errores, "umbral fuera de rango: 'ear'"))

    def test_gestos_imposibles(self):
        fuente = envolver("""
            gesto g1 = ear < 0.1 y ear > 0.3 durante 1 s;
            gesto g2 = mar > 0.5 durante 2 s hasta 1 s;
            gesto g3 = no (pitch > 10.0 o pitch <= 10.0) durante 1 s;
            gesto g4 = ear < 0.2 durante 1 s hasta 50 ms;
            gesto ok = ear < 0.1 o ear > 0.3 durante 1 s;""",
            "estado a { cuando g1 ir_a a; cuando g2 ir_a a; cuando g3 ir_a a; cuando g4 ir_a a; cuando ok ir_a a; }")
        errores = mensajes(fuente)
        for g in ("'g1'", "'g2'", "'g3'"):
            self.assertTrue(contiene(errores, f"gesto imposible: la condición de {g}") or
                            contiene(errores, f"gesto imposible: {g}"), g)
        self.assertTrue(contiene(errores, "menor a un cuadro"))
        self.assertFalse(contiene(errores, "'ok'"))

    def test_secuencia_imposible_por_ventana(self):
        fuente = envolver("""
            gesto a1 = mar > 0.6 durante 2 s;
            gesto a2 = pitch > 20.0 durante 1 s;
            secuencia rep = [a1, a1] en 2 s;
            secuencia mix = [a1, a2] en 2 s;""", "estado a { cuando rep ir_a a; cuando mix ir_a a; }")
        errores = mensajes(fuente)
        self.assertTrue(contiene(errores, "secuencia imposible: 'rep'"))
        self.assertFalse(contiene(errores, "'mix'"))   # gestos distintos pueden solaparse

    def test_estados_inalcanzables_y_contradictorios(self):
        fuente = envolver("gesto g = ear < 0.2 durante 1 s;", """
            estado a { cuando g ir_a b; cuando g { ir_a c; } }
            estado b { cuando g { si verdadero { ir_a a; } } }
            estado c { }
            estado d { cuando g ir_a a; }""")
        errores = mensajes(fuente)
        self.assertTrue(contiene(errores, "transiciones contradictorias en 'a'"))
        self.assertTrue(contiene(errores, "estado inalcanzable: 'd'"))
        self.assertFalse(contiene(errores, "'c' no puede"))

    def test_eventos_ignorados_e_ignorar(self):
        gestos = "gesto g = ear < 0.2 durante 1 s; gesto h = mar > 0.4 durante 1 s;"
        estados = """
            estado a { cuando g ir_a b; cuando h ir_a a; }
            estado b { cuando h ir_a a; %s }
            estado fin { }"""
        notas = mensajes(envolver(gestos, estados % ""), "nota")
        self.assertTrue(contiene(notas, "el evento 'g' cambia de estado en a pero se ignora en b"))
        self.assertFalse(contiene(notas, "fin"))           # los estados finales no cuentan
        self.assertEqual(mensajes(envolver(gestos, estados % "ignorar g;"), "nota"), [])
        errores = mensajes(envolver(gestos, estados % "ignorar g, h, x;"))
        self.assertTrue(contiene(errores, "ignora 'h' pero también tiene 'cuando h'"))
        self.assertTrue(contiene(errores, "evento 'x' no declarado"))

    def test_advertencias(self):
        adv = mensajes(envolver("gesto g = ear >= 0.0 durante 1 s; gesto h = mar > 0.9 durante 1 s;",
                                "estado a { cuando g ir_a a; }"), "advertencia")
        self.assertTrue(contiene(adv, "siempre es verdadera"))
        self.assertTrue(contiene(adv, "'h' se declara pero"))
        self.assertFalse(contiene(adv, "umbral atípico"))


class TestAutomatas(unittest.TestCase):
    def correr(self, a, simbolos):
        d = a.delta()
        q, salidas = a.inicial, []
        for s in simbolos:
            t = d[(q, s)]
            q = t.destino
            salidas.append(t.salida)
        return q, salidas

    def test_gesto_minimo(self):
        a = A.afd_gesto("g", 300, None, fps=10)        # 3 cuadros
        self.assertEqual(len(a.estados), 4)
        q, sal = self.correr(a, "110111110")
        self.assertEqual(sal, [None, None, None, None, None, "g", None, None, None])
        self.assertEqual(q, "q0")

    def test_gesto_con_maximo_parpadeo(self):
        a = A.afd_gesto("p", 100, 300, fps=10)         # entre 1 y 3 cuadros
        _, sal = self.correr(a, "1100" + "11110")      # 2 cuadros: sí; 4 cuadros: excede
        self.assertEqual(sal.count("p"), 1)
        self.assertIn("qX", a.estados)

    def test_gesto_con_tolerancia(self):
        a = A.afd_gesto("g", 300, None, fps=10, tolerancia_ms=100)   # 3 cuadros, perdona 1
        self.assertIn("q2~1", a.estados)
        _, sal = self.correr(a, "11011")             # una interrupción de 1 cuadro: se perdona
        self.assertEqual(sal, [None, None, None, "g", None])
        _, sal = self.correr(a, "1100111")           # dos cuadros de interrupción: se reinicia
        self.assertEqual(sal, [None] * 6 + ["g"])
        self.assertIn("q3~1", a.aceptacion)

    def test_gesto_con_maximo_y_tolerancia(self):
        a = A.afd_gesto("p", 100, 300, fps=10, tolerancia_ms=100)    # 1-3 cuadros, perdona 1
        _, sal = self.correr(a, "1010" + "0")        # 1+1 cuadros con hueco; se suelta con K+1 ceros
        self.assertEqual(sal, [None, None, None, None, "p"])
        _, sal = self.correr(a, "110110" + "0")      # 4 cuadros cumplidos: excede el máximo
        self.assertNotIn("p", sal)

    def test_tolerancia_en_el_lenguaje(self):
        fuente = envolver("gesto g = ear < 0.2 durante 1 s tolerando 200 ms;",
                          "estado a { cuando g ir_a a; }")
        r = compilar(fuente)
        self.assertTrue(r.ok)
        g = next(a for a in r.automatas["d"] if a.nombre == "g")
        self.assertEqual(g.descripcion["cuadros_tolerados"], 2)
        adv = mensajes(envolver("gesto h = ear < 0.2 durante 300 ms tolerando 1 s;",
                                "estado a { cuando h ir_a a; }"), "advertencia")
        self.assertTrue(contiene(adv, "no es menor que su duración"))
        self.assertTrue(contiene(mensajes(envolver("gesto k = ear < 0.2 durante 1 s tolerando 3;",
                                                   "estado a { cuando k ir_a a; }")), "'tolerando'"))

    def test_secuencia_kmp(self):
        a = A.afd_secuencia("s", ["x", "y", "x"], None)
        _, sal = self.correr(a, ["x", "y", "x", "y", "x", "x", "y"])
        self.assertEqual(sal, [None, None, "s", None, "s", None, None])

    def test_generacion_y_formatos(self):
        r = compilar_archivo(os.path.join(EJEMPLOS, "conduccion.emo"))
        lista = r.automatas["conduccion"]
        maquina = next(a for a in lista if a.clase == "maquina")
        self.assertIn(A.LAMBDA, maquina.alfabeto)
        for a in lista:
            self.assertIn("digraph", A.a_dot(a))
            self.assertIn("stateDiagram-v2", A.a_mermaid(a))
            self.assertIn("δ", A.tabla_texto(a))


class TestMotor(unittest.TestCase):
    def motor(self, fuente, dominio="d"):
        r = compilar(fuente)
        self.assertTrue(r.ok, [str(d) for d in r.reporte.errores])
        mod = ModuloBase(salida=lambda *a: None)
        return Motor(r.analisis, r.automatas, dominio, mod), mod

    def test_transicion_por_gesto_y_variables(self):
        fuente = envolver("var n : int = 0; gesto cerrado = ear < 0.2 durante 300 ms;", """
            estado a { cuando cerrado { n = n + 1; si n >= 2 { ir_a b; } } }
            estado b { al_entrar { repetir 3 veces { n = n + 10; } } }""")
        m, _ = self.motor(fuente)
        abierto, cerrado = metricas_neutras(), dict(metricas_neutras(), ear=0.1)
        t = 0
        for patron in [cerrado] * 3 + [abierto] + [cerrado] * 3:
            m.paso(t, patron)
            t += 100
        self.assertEqual(m.estado_actual(), {"m": "b"})
        self.assertEqual(m.globales["n"], 32)

    def test_mientras_no_bloquea(self):
        fuente = envolver("var cuadros : int = 0;", """
            estado a { mientras verdadero { cuadros = cuadros + 1; }
                       mientras tiempo_en_estado() >= 500 ms { ir_a b; } }
            estado b { }""")
        m, _ = self.motor(fuente)
        for i in range(10):
            m.paso(i * 100, metricas_neutras())
        self.assertEqual(m.globales["cuadros"], 6)    # 0..500 ms, luego cambia de estado
        self.assertEqual(m.estado_actual(), {"m": "b"})

    def test_camara_lenta_se_normaliza_al_fps_del_programa(self):
        class CamaraLenta:            # ~9.4 fps irregulares, como la cámara medida
            tasa_variable = True

            def __iter__(self):
                t = 0.0
                while t < 4000:
                    yield t, dict(metricas_neutras(), ear=0.1 if t >= 1000 else 0.3)
                    t += 106 + (t % 7)

        fuente = """dominio d { sensor camara { var fps : int = 30; }
            gesto cerrado = ear < 0.2 durante 1 s;
            maquina m inicial a { estado a { cuando cerrado ir_a a; } } }"""
        r = compilar(fuente)
        res = ejecutar(r, "d", CamaraLenta(), verbose=False)
        t_det = [t for t, e in res.eventos if e == "cerrado"]
        self.assertEqual(len(t_det), 1)
        self.assertAlmostEqual(t_det[0] - 1000, 1000, delta=150)   # ~1 s, no ~3.2 s
        self.assertGreater(res.cuadros, 110)                      # ~30 cuadros por segundo

    def test_conduccion_simulada(self):
        r = compilar_archivo(os.path.join(EJEMPLOS, "conduccion.emo"))
        res = ejecutar(r, "conduccion", SensorSimulado("conduccion", semilla=1), verbose=False)
        detectados = [e for _, e in res.eventos]
        for g in ("bostezo", "microsueno", "cabeceo", "fatiga"):
            self.assertIn(g, detectados)
        self.assertGreaterEqual(res.resumen["alarmas_emitidas"], 1)

    def test_escenario_normal_sin_alarmas(self):
        r = compilar_archivo(os.path.join(EJEMPLOS, "conduccion.emo"))
        res = ejecutar(r, "conduccion", SensorSimulado("normal", semilla=3), verbose=False)
        self.assertEqual(res.resumen["alarmas_emitidas"], 0)

    def test_rehabilitacion_cuenta_repeticiones(self):
        r = compilar_archivo(os.path.join(EJEMPLOS, "rehabilitacion.emo"))
        res = ejecutar(r, "rehabilitacion", SensorSimulado("rehabilitacion", semilla=2), verbose=False)
        self.assertEqual(res.resumen["repeticiones"], 8)
        self.assertEqual(res.motor.estado_actual(), {"ejercicio": "terminado"})


if __name__ == "__main__":
    unittest.main()
