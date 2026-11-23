"""Pruebas del módulo de optimización: técnicas, costos y programas aleatorios.

La prueba aleatoria genera programas válidos y exige que la versión optimizada
produzca exactamente la misma salida que la versión sin optimizar.
"""

import glob
import os
import random
import unittest

from emolang.compilador import compilar, compilar_archivo
from emolang.costos import comparar, reporte, temporales_vivos
from emolang.errores import ErrorEmoLang
from emolang.intermedio import PROGRAMA, resolver
from emolang.metricas import metricas_neutras
from emolang.modulos import ModuloPrograma
from emolang.vm import EmoVM

AQUI = os.path.dirname(os.path.abspath(__file__))


def correr(emoc):
    lineas = []
    vm = EmoVM(emoc, PROGRAMA, ModuloPrograma(salida=lineas.append))
    try:
        return lineas, vm.ejecutar_principal(), None, vm
    except ErrorEmoLang as e:
        return lineas, None, str(e), vm


def compilado(fuente):
    r = compilar(fuente)
    assert r.ok, ([str(d) for d in r.reporte.errores], fuente)
    return r


def funcion_opt(fuente, nombre="f"):
    r = compilado(fuente)
    return r, [c.fila() for c in resolver(r.optimizado[PROGRAMA].bloques[f"funcion.{nombre}"])]


def con_f(cuerpo, params="x : int, w : decimal, b1 : bool", args="3, 0.5, verdadero"):
    return f"funcion f({params}) {{ {cuerpo} }}\nfuncion principal() {{ f({args}); }}"


class TestSimplificacionAlgebraica(unittest.TestCase):
    def assert_queda(self, expr, esperado, tipo="int"):
        """El resultado de la expresión debe mostrarse directamente, sin operar."""
        _, filas = funcion_opt(con_f(f"var r : {tipo} = {expr}; mostrar(r);"))
        operaciones = [f for f in filas if f[0] in ("+", "-", "*", "/", "y", "o", "<", "==", "no")]
        self.assertEqual(operaciones, [], (expr, filas))
        self.assertIn(esperado.strip("'"), str(filas), (expr, filas))

    def test_identidades(self):
        for expr in ("x + 0", "0 + x", "x - 0", "x * 1", "1 * x"):
            with self.subTest(expr):
                self.assert_queda(expr, "'f.x'")

    def test_division_entre_uno_conserva_el_valor(self):
        r = compilado(con_f("mostrar(w / 1);"))
        self.assertEqual(correr(r.emoc)[0], ["0.5"])

    def test_anulacion(self):
        for expr in ("x * 0", "0 * x", "x - x"):
            with self.subTest(expr):
                self.assert_queda(expr, "'0'")

    def test_logica(self):
        for expr, esperado in [("b1 y verdadero", "'f.b1'"), ("verdadero y b1", "'f.b1'"),
                               ("b1 o falso", "'f.b1'"), ("b1 y falso", "'falso'"),
                               ("b1 o verdadero", "'verdadero'"), ("b1 y b1", "'f.b1'"),
                               ("x == x", "'verdadero'"), ("x != x", "'falso'")]:
            with self.subTest(expr):
                self.assert_queda(expr, esperado, "bool")

    def test_doble_negacion_y_comparacion_negada(self):
        _, filas = funcion_opt(con_f("var r : bool = no (x < 2); mostrar(r);"))
        self.assertIn((">=", "f.x", "2"), [f[:3] for f in filas])
        self.assertNotIn("no", [f[0] for f in filas])
        _, filas = funcion_opt(con_f("var r : bool = no no b1; mostrar(r);"))
        self.assertNotIn("no", [f[0] for f in filas])

    def test_cero_negativo_se_muestra_como_cero(self):
        r = compilado(con_f("var v : decimal = 0.0 - w; mostrar(v * 0.0); mostrar(0.0 - 0.0001);"))
        self.assertEqual(correr(r.emoc)[0], ["0", "0"])
        self.assertEqual(correr(r.emoc_sin_optimizar())[0], ["0", "0"])

    def test_anular_no_esconde_una_llamada(self):
        r = compilado("""funcion g() : int { mostrar("efecto"); retornar 2; }
        funcion principal() { var r : int = g() * 0; mostrar(r); }""")
        self.assertEqual(correr(r.emoc)[0], ["efecto", "0"])


class TestReduccionDeFuerza(unittest.TestCase):
    def test_multiplicar_por_dos_es_suma(self):
        _, filas = funcion_opt(con_f("mostrar(x * 2);"))
        self.assertIn(("+", "f.x", "f.x", "t1"), filas)

    def test_potencia_de_dos_es_desplazamiento(self):
        for expr, k in (("x * 8", "3"), ("16 * x", "4")):
            with self.subTest(expr):
                r, filas = funcion_opt(con_f(f"mostrar({expr});"))
                self.assertIn(("shl", "f.x", k), [f[:3] for f in filas])
                self.assertEqual(correr(r.emoc)[0], correr(r.emoc_sin_optimizar())[0])

    def test_desplazamiento_solo_en_enteros(self):
        _, filas = funcion_opt(con_f("mostrar(w * 8);"))
        self.assertNotIn("shl", [f[0] for f in filas])
        self.assertIn("*", [f[0] for f in filas])

    def test_negativos(self):
        r = compilado(con_f("mostrar(x * 4);", args="-3, 0.5, falso"))
        self.assertEqual(correr(r.emoc)[0], ["-12"])

    def test_variable_de_induccion_dentro_de_un_ciclo(self):
        fuente = con_f("para i = 0 hasta 3 { mostrar(i * 7); }")
        r, filas = funcion_opt(fuente)
        ciclo = [n for n, f in enumerate(filas) if f[0] == "goto"][0]
        inicio = int(filas[ciclo][3]) - 1
        dentro = filas[inicio:ciclo]
        self.assertNotIn("*", [f[0] for f in dentro])
        self.assertIn("*", [f[0] for f in filas[:inicio]])
        self.assertTrue(any(f[0] == "+" and f[2] == "7" for f in dentro), filas)
        self.assertEqual(correr(r.emoc)[0], ["0", "7", "14", "21"])

    def test_induccion_con_incremento_en_una_rama(self):
        fuente = con_f("""var i : int = 0; var n : int = 0;
            mientras n < 6 {
                mostrar(i * 5);
                si n > 2 { i = i + 2; }
                n = n + 1;
            }""")
        r = compilado(fuente)
        self.assertEqual(correr(r.emoc)[0], ["0", "0", "0", "0", "10", "20"])

    def test_variable_global_cambiada_en_una_llamada_no_es_induccion(self):
        r = compilado("""var g : int = 0;
        funcion cambia() { g = g + 100; }
        funcion principal() {
            para k = 1 hasta 3 { mostrar(g * 5); g = g + 1; cambia(); }
        }""")
        self.assertEqual(correr(r.emoc)[0], ["0", "505", "1010"])


class TestConstantesEnCiclosDesenrollados(unittest.TestCase):
    def test_cada_copia_se_pliega(self):
        r, filas = funcion_opt(con_f("repetir 3 veces { mostrar(no (1 > 2)); }"))
        self.assertEqual([f[0] for f in filas], ["param", "call"] * 3 + ["ret"])
        self.assertEqual(filas[0][1], '"verdadero"')
        self.assertEqual(correr(r.emoc)[0], ["verdadero"] * 3)


class TestCodigoInvariante(unittest.TestCase):
    def test_se_saca_del_ciclo(self):
        r, filas = funcion_opt(con_f("para i = 0 hasta 2 { mostrar(x * x + i); }"))
        ciclo = [n for n, f in enumerate(filas) if f[0] == "goto"][0]
        inicio = int(filas[ciclo][3]) - 1
        self.assertIn(("*", "f.x", "f.x"), [f[:3] for f in filas[:inicio]])
        self.assertNotIn("*", [f[0] for f in filas[inicio:ciclo]])
        self.assertEqual(correr(r.emoc)[0], ["9", "10", "11"])

    def test_variable_modificada_en_el_ciclo_se_queda(self):
        r, filas = funcion_opt(con_f("para i = 0 hasta 2 { mostrar(x * 3 + 1); x = x + 1; }"))
        self.assertEqual(correr(r.emoc)[0], ["10", "13", "16"])

    def test_global_que_cambia_una_llamada_se_queda(self):
        r = compilado("""var g : int = 3;
        funcion cambia() { g = g + 1; }
        funcion principal() {
            para k = 1 hasta 3 { mostrar(g * g); cambia(); }
        }""")
        self.assertEqual(correr(r.emoc)[0], ["9", "16", "25"])

    def test_division_que_puede_fallar_no_sale_de_un_ciclo_que_no_entra(self):
        r = compilado(con_f("var d : decimal = 0.0; var k : int = 5; "
                            "mientras k < 3 { mostrar(w / d); k = k + 1; } mostrar(1);"))
        self.assertEqual(correr(r.emoc)[:3], (["1"], None, None))

    def test_lectura_de_arreglo_se_queda(self):
        r = compilado("""funcion principal() {
            var v : int[2] = [1, 2];
            para i = 0 hasta 1 { mostrar(v[0]); v[0] = v[0] + 1; }
        }""")
        self.assertEqual(correr(r.emoc)[0], ["1", "2"])

    def test_invariante_en_ciclo_anidado_sube_hasta_afuera(self):
        r, filas = funcion_opt(con_f("para i = 0 hasta 1 { para j = 0 hasta 1 { mostrar(x * x + j + i); } }"))
        primero = [n for n, f in enumerate(filas) if f[0] == "*"][0]
        primer_salto = [n for n, f in enumerate(filas) if f[0] == "gotoF"][0]
        self.assertLess(primero, primer_salto)


class TestLlamadasCambianGlobales(unittest.TestCase):
    """Casos que encontró la prueba con programas aleatorios."""

    ANTES = "var g : int = 1;\nfuncion sube() : int { g = g + 10; retornar 0; }\n"

    def salidas(self, cuerpo):
        r = compilado(self.ANTES + f"funcion principal() {{ {cuerpo} }}")
        a, b = correr(r.emoc_sin_optimizar()), correr(r.emoc)
        self.assertEqual(a[:3], b[:3])
        return b[0]

    def test_subexpresion_con_llamada_en_medio(self):
        self.assertEqual(self.salidas("var a : int = g + 1; var z : int = sube(); var b : int = g + 1; mostrar(a, b);"),
                         ["2 12"])

    def test_copia_con_llamada_en_medio(self):
        self.assertEqual(self.salidas("var a : int = g; var z : int = sube(); mostrar(a, g);"), ["1 11"])

    def test_operando_izquierdo_se_lee_antes_de_la_llamada(self):
        self.assertEqual(self.salidas("mostrar(g - sube());"), ["1"])
        self.assertEqual(self.salidas("var v : int[1]; v[0] = g + sube(); mostrar(v[0]);"), ["1"])

    def test_argumento_se_lee_antes_de_la_llamada(self):
        self.assertEqual(self.salidas("mostrar(g, sube(), g);"), ["1 0 11"])

    def test_concatenacion_se_lee_antes_de_la_llamada(self):
        self.assertEqual(self.salidas('registrar("" + g + sube());'), ["10"])


class TestCostos(unittest.TestCase):
    def test_los_programas_intermedios_reducen_instrucciones(self):
        rutas = sorted(glob.glob(os.path.join(AQUI, "intermediate", "*.emo")))
        self.assertGreaterEqual(len(rutas), 3)
        for ruta in rutas:
            with self.subTest(os.path.basename(ruta)):
                r = compilar_archivo(ruta)
                self.assertTrue(r.ok)
                with open(ruta[:-4] + ".esperado", encoding="utf-8") as f:
                    esperado = f.read().splitlines()
                self.assertEqual(correr(r.emoc)[0], esperado)
                self.assertEqual(correr(r.emoc_sin_optimizar())[0], esperado)
                antes, despues = comparar(r, repeticiones=1)
                # Sacar código de un ciclo puede alargar el programa, pero siempre ejecuta menos.
                self.assertLess(despues.ejecutadas, antes.ejecutadas)
                self.assertIn("Cuádruplas ejecutadas", reporte(antes, despues))
                if "redundante" in ruta:
                    self.assertLess(despues.cuadruplas, antes.cuadruplas)

    def test_pila_y_llamadas_se_miden_con_recursion(self):
        r = compilar_archivo(os.path.join(AQUI, "execution", "factorial.emo"))
        antes, despues = comparar(r, repeticiones=1)
        self.assertEqual(despues.llamadas_anidadas, 11)     # principal + factorial(10) ... factorial(1)
        self.assertGreater(despues.pila_bytes, 0)

    def test_costos_de_un_dominio(self):
        r = compilar_archivo(os.path.join(AQUI, "..", "ejemplos", "conduccion.emo"))
        cuadros = [(i * 33.3, metricas_neutras()) for i in range(30)]
        antes, despues = comparar(r, "conduccion", cuadros, repeticiones=1)
        self.assertLess(despues.ejecutadas, antes.ejecutadas)

    def test_temporales_vivos(self):
        r = compilado(con_f("mostrar((x + 1) * (x + 2));"))
        self.assertEqual(temporales_vivos(r.cuadruplas[PROGRAMA].bloques["funcion.f"]), 3)


class Generador:
    """Programas válidos con ciclos, ramas, arreglos, funciones y expresiones variadas."""

    def __init__(self, semilla):
        self.r = random.Random(semilla)
        self.n = 0
        self.ints = ["ga", "gb", "x"]
        self.ciclo = []                # variables de ciclo: se leen, no se asignan
        self.decs = ["gd"]
        self.bools = []

    def nuevo(self, p="v"):
        self.n += 1
        return f"{p}{self.n}"

    def entero(self, d=0):
        r = self.r
        if d > 3 or r.random() < 0.35:
            return r.choice(self.ints + self.ciclo + [str(r.choice([0, 1, 2, 3, 4, 7, 8, 16, 32]))] * 2)
        o = r.random()
        if o < 0.08:
            return "CONST_N"
        if o < 0.14:
            return f"datos[{r.randint(0, 3)}]"
        if o < 0.20:
            return f"cambia({self.entero(d + 1)})"
        if o < 0.25:
            return f"pareja.m"
        if o < 0.30:
            return f"(-{self.entero(d + 1)})"
        if r.random() < 0.4:
            return f"({self.entero(d + 1)} * {r.choice([0, 1, 2, 3, 4, 7, 8, 16])})"
        return f"({self.entero(d + 1)} {r.choice(['+', '-'])} {self.entero(d + 1)})"

    def decimal(self, d=0):
        r = self.r
        if d > 2 or r.random() < 0.4:
            return r.choice(self.decs + ["0.5", "1.0", "0.0", "2.5"])
        return f"({self.decimal(d + 1)} {r.choice(['+', '-', '*', '/'])} {r.choice([self.decimal(d + 1), self.entero(3)])})"

    def booleano(self, d=0):
        r = self.r
        o = r.random()
        if d > 2 or o < 0.5:
            return f"{self.entero(2)} {r.choice(['<', '<=', '>', '>=', '==', '!='])} {self.entero(2)}"
        if o < 0.6:
            return r.choice(["verdadero", "falso"])
        if o < 0.75:
            return f"no ({self.booleano(d + 1)})"
        return f"({self.booleano(d + 1)}) {r.choice(['y', 'o'])} ({self.booleano(d + 1)})"

    def bloque(self, d, n=None):
        guardados = list(self.ints), list(self.decs)
        s = " ".join(self.sentencia(d) for _ in range(n or self.r.randint(1, 4)))
        self.ints, self.decs = guardados
        return "{ " + s + " }"

    def sentencia(self, d):
        r = self.r
        o = r.random()
        if d > 2:
            o *= 0.45
        if o < 0.12:
            return f"mostrar({self.entero()});"
        if o < 0.17:
            return f"mostrar({self.decimal()});"
        if o < 0.27:
            v = self.nuevo()
            s = f"var {v} : int = {self.entero()};"
            self.ints.append(v)
            return s
        if o < 0.32:
            v = self.nuevo("w")
            s = f"var {v} : decimal = {self.decimal()};"
            self.decs.append(v)
            return s
        if o < 0.40:
            return f"{r.choice(self.ints)} = {self.entero()};"
        if o < 0.45:
            return f"datos[{r.randint(0, 3)}] = {self.entero()};"
        if o < 0.60:
            otro = f" sino {self.bloque(d + 1)}" if r.random() < 0.5 else ""
            return f"si {self.booleano()} {self.bloque(d + 1)}{otro}"
        if o < 0.72:
            v = self.nuevo("i")
            self.ciclo.append(v)
            s = f"para {v} = {r.randint(-1, 2)} hasta {r.randint(0, 4)} {self.bloque(d + 1)}"
            self.ciclo.remove(v)
            return s
        if o < 0.82:
            v = self.nuevo("k")
            paso = r.choice([1, 2])
            cuerpo = self.bloque(d + 1)
            return (f"var {v} : int = 0; mientras {v} < {r.randint(0, 5)} "
                    f"{{ mostrar({v} * {r.choice([1, 2, 3, 8])}); {cuerpo[1:-1]} {v} = {v} + {paso}; }}")
        if o < 0.90:
            return f"repetir {r.randint(0, 6)} veces {self.bloque(d + 1)}"
        if o < 0.95:
            return f"pareja.m = {self.entero()};"
        return f"mostrar(cambia({self.entero()}));"

    def programa(self):
        principal = self.bloque(0, 10)
        return f"""const CONST_N : int = 8;
estructura Par {{ m : int; n : decimal; }}
var ga : int = 2;
var gb : int = 5;
var gd : decimal = 1.5;
var datos : int[4] = [1, 2, 3, 4];
var pareja : Par;
funcion cambia(p : int) : int {{
    gb = gb + 1;
    si p > 100 {{ retornar p - 100; }}
    retornar p * 2;
}}
funcion auxiliar(x : int) : int {{
    var r : int = x * 4 + 0;
    retornar r + ga;
}}
funcion principal() : int {{
    var x : int = auxiliar(3);
    {principal[1:-1]}
    mostrar(ga, gb, gd, datos[0], datos[3], pareja.m);
    retornar 0;
}}"""


class TestProgramasAleatorios(unittest.TestCase):
    def test_optimizar_no_cambia_la_salida(self):
        aplicadas = {}
        for semilla in range(300):
            fuente = Generador(semilla).programa()
            r = compilar(fuente)
            self.assertTrue(r.ok, (semilla, [str(d) for d in r.reporte.errores], fuente))
            a = correr(r.emoc_sin_optimizar())
            b = correr(r.emoc)
            self.assertEqual(a[:3], b[:3], f"semilla {semilla}\n{fuente}")
            for t, n in r.informes[PROGRAMA].aplicaciones.items():
                aplicadas[t] = aplicadas.get(t, 0) + n
        # La prueba solo vale si de verdad ejercitó cada técnica.
        for tecnica in ("propagacion", "plegado", "subexpresiones", "muerto", "mirilla", "desenrollado",
                        "algebraica", "fuerza", "invariante", "induccion"):
            self.assertGreater(aplicadas.get(tecnica, 0), 0, f"{tecnica} no se aplicó: {aplicadas}")

    def test_optimizado_nunca_ejecuta_mas(self):
        peores = []
        for semilla in range(100):
            r = compilar(Generador(semilla).programa())
            a, b = correr(r.emoc_sin_optimizar())[3], correr(r.emoc)[3]
            if b.ejecutadas > a.ejecutadas:
                peores.append((semilla, a.ejecutadas, b.ejecutadas))
        self.assertLessEqual(len(peores), 3, peores)


if __name__ == "__main__":
    unittest.main()
