"""Pruebas de funciones, ciclos clásicos, arreglos, estructuras, constantes y conversiones.

Los programas de tests/execution se ejecutan con y sin optimizar, y su salida se
compara con el archivo .esperado. Las mismas salidas servirán para el código objeto.
"""

import glob
import os
import unittest

from emolang.compilador import compilar, compilar_archivo
from emolang.errores import ErrorEmoLang
from emolang.intermedio import PROGRAMA
from emolang.modulos import ModuloPrograma
from emolang.vm import EmoVM

AQUI = os.path.dirname(os.path.abspath(__file__))


def correr(emoc):
    lineas = []
    valor = EmoVM(emoc, PROGRAMA, ModuloPrograma(salida=lineas.append)).ejecutar_principal()
    return lineas, valor


def compilado(fuente):
    r = compilar(fuente)
    assert r.ok, [str(d) for d in r.reporte.errores]
    return r


def salida(fuente):
    """Salida del programa; también verifica que optimizar no la cambie."""
    r = compilado(fuente)
    optimizada, _ = correr(r.emoc)
    sin_optimizar, _ = correr(r.emoc_sin_optimizar())
    assert optimizada == sin_optimizar, (optimizada, sin_optimizar)
    return optimizada


def errores(fuente):
    return [d.mensaje for d in compilar(fuente).reporte.errores]


def principal(cuerpo, antes=""):
    return f"{antes}\nfuncion principal() : int {{ {cuerpo} retornar 0; }}"


class TestAlgoritmos(unittest.TestCase):
    def test_programas_de_ejecucion(self):
        archivos = sorted(glob.glob(os.path.join(AQUI, "execution", "*.emo")))
        self.assertGreaterEqual(len(archivos), 4)
        for ruta in archivos:
            with self.subTest(programa=os.path.basename(ruta)):
                r = compilar_archivo(ruta)
                self.assertTrue(r.ok, [str(d) for d in r.reporte.errores])
                with open(ruta[:-4] + ".esperado", encoding="utf-8") as f:
                    esperado = f.read().splitlines()
                self.assertEqual(correr(r.emoc)[0], esperado)
                self.assertEqual(correr(r.emoc_sin_optimizar())[0], esperado)


class TestFunciones(unittest.TestCase):
    def test_recursion_con_marcos_independientes(self):
        s = salida(principal("mostrar(suma(4));", '''funcion suma(n : int) : int {
            si n == 0 { retornar 0; }
            var resto : int = suma(n - 1);
            retornar n + resto;
        }'''))
        self.assertEqual(s, ["10"])

    def test_parametro_reasignado_no_se_propaga(self):
        s = salida(principal("f(9);", "funcion f(n : int) { mostrar(n); n = 3; mostrar(n); }"))
        self.assertEqual(s, ["9", "3"])

    def test_funcion_modifica_variable_global(self):
        s = salida(principal("sube(); sube(); mostrar(cuenta);",
                             "var cuenta : int = 0; funcion sube() { cuenta = cuenta + 1; }"))
        self.assertEqual(s, ["2"])

    def test_retornar_sin_valor_termina_la_funcion(self):
        s = salida(principal("f(1); f(5);", '''funcion f(n : int) {
            si n > 3 { retornar; }
            mostrar(n);
        }'''))
        self.assertEqual(s, ["1"])

    def test_funcion_usada_desde_un_estado(self):
        fuente = '''funcion doble(x : int) : int { retornar x * 2; }
        dominio d { sensor c { var fps : int = 10; } var n : int = 4;
            maquina m inicial a { estado a { al_entrar { n = doble(n); } } } }'''
        r = compilado(fuente)
        from emolang.metricas import metricas_neutras
        from emolang.modulos import ModuloBase
        vm = EmoVM(r.emoc, "d", ModuloBase(salida=lambda *_: None))
        vm.paso(0.0, metricas_neutras())
        self.assertEqual(vm.mem["n"], 8)

    def test_funcion_sin_uso_se_elimina(self):
        r = compilado(principal("", "funcion nadie() { mostrar(1); }"))
        self.assertNotIn("nadie", r.optimizado[PROGRAMA].funciones)
        self.assertNotIn("funcion.nadie", r.emoc["dominios"][PROGRAMA]["bloques"])
        self.assertIn("nadie", r.cuadruplas[PROGRAMA].funciones)

    def test_errores_de_funciones(self):
        casos = [
            (principal("g();"), "no definida"),
            (principal("f(1, 2);", "funcion f(a : int) { }"), "espera 1 argumento"),
            (principal('f("x");', "funcion f(a : int) { }"), "se esperaba int"),
            ("funcion f() : int { mostrar(1); }\nfuncion principal() { }", "todos los caminos"),
            ("funcion f() : int { retornar \"x\"; }\nfuncion principal() { }", "debe devolver int"),
            ("funcion f() { retornar 1; }\nfuncion principal() { }", "no devuelve un valor"),
            ("funcion principal(a : int) { }", "no recibe parámetros"),
            ("funcion f() { mostrar(ear); }\nfuncion principal() { }", "solo se puede leer dentro de un dominio"),
            ("funcion f() { alarma(\"x\"); }\nfuncion principal() { }", "solo se puede usar dentro de un estado"),
            ("funcion f() { ir_a x; }\nfuncion principal() { }", "dentro de una máquina"),
            ("funcion f() { }\nfuncion f() { }", "ya fue declarado"),
            (principal("var x : int = f();", "funcion f() { }"), "no devuelve un valor"),
        ]
        for fuente, esperado in casos:
            with self.subTest(esperado=esperado):
                self.assertTrue(any(esperado in m for m in errores(fuente)), errores(fuente))

    def test_desbordamiento_de_pila_se_reporta(self):
        r = compilado(principal("f(1);", "funcion f(n : int) { f(n + 1); }"))
        with self.assertRaises(ErrorEmoLang):
            correr(r.emoc)


class TestCiclos(unittest.TestCase):
    def test_mientras_clasico(self):
        self.assertEqual(salida(principal("var i : int = 0; mientras i < 3 { mostrar(i); i = i + 1; }")),
                         ["0", "1", "2"])

    def test_para_incluye_el_limite_y_lo_evalua_una_vez(self):
        self.assertEqual(salida(principal("var n : int = 2; para i = 1 hasta n { n = 10; mostrar(i); }")),
                         ["1", "2"])

    def test_para_que_no_entra(self):
        self.assertEqual(salida(principal("para i = 5 hasta 1 { mostrar(i); }")), [])

    def test_ciclos_anidados(self):
        s = salida(principal("para i = 1 hasta 2 { var j : int = 0; mientras j < 2 { mostrar(i, j); j = j + 1; } }"))
        self.assertEqual(s, ["1 0", "1 1", "2 0", "2 1"])

    def test_mientras_y_para_siguen_prohibidos_en_estados(self):
        base = "dominio d {{ maquina m inicial a {{ estado a {{ al_entrar {{ {} }} }} }} }}"
        self.assertTrue(errores(base.format("mientras verdadero { }")))
        self.assertTrue(errores(base.format("para i = 1 hasta 2 { }")))

    def test_condicion_debe_ser_bool(self):
        self.assertTrue(any("debe ser bool" in m for m in errores(principal("mientras 1 { }"))))
        self.assertTrue(any("deben ser int" in m for m in errores(principal("para i = 0.5 hasta 2 { }"))))


class TestArreglosYEstructuras(unittest.TestCase):
    def test_arreglo_inicia_en_cero_y_se_escribe(self):
        s = salida(principal("var v : int[3]; v[1] = 5; mostrar(v[0], v[1], v[2]);"))
        self.assertEqual(s, ["0 5 0"])

    def test_arreglo_se_pasa_por_referencia(self):
        s = salida(principal("var v : int[2] = [1, 2]; pon(v); mostrar(v[0]);",
                             "funcion pon(a : int[]) { a[0] = 9; }"))
        self.assertEqual(s, ["9"])

    def test_arreglo_local_es_propio_de_cada_llamada(self):
        s = salida(principal("mostrar(f(2));", '''funcion f(n : int) : int {
            var v : int[1];
            v[0] = n;
            si n > 0 { var x : int = f(n - 1); }
            retornar v[0];
        }'''))
        self.assertEqual(s, ["2"])

    def test_variable_modificada_no_da_error_falso_de_rango(self):
        s = salida(principal("var v : int[2]; var i : int = 5; i = 1; v[i] = 7; mostrar(v[i]);"))
        self.assertEqual(s, ["7"])
        s = salida(principal("var u : decimal = 2.0; u = 0.5; var p : proporcion = 0.1; p = u; mostrar(p);"))
        self.assertEqual(s, ["50.0%"])

    def test_constante_fuera_de_rango_se_detecta_al_compilar(self):
        msgs = errores(principal("var v : int[2]; v[N] = 1;", "const N : int = 2;"))
        self.assertTrue(any("fuera de rango" in m for m in msgs))

    def test_indice_fuera_de_rango_al_ejecutar(self):
        r = compilado(principal("var v : int[2]; var i : int = 5; i = i + 0; mostrar(v[i]);"))
        with self.assertRaises(ErrorEmoLang):
            correr(r.emoc)

    def test_lectura_de_indice_invalido_no_se_elimina(self):
        r = compilado(principal("var v : int[2]; var i : int = 5; i = i + 0; var x : int = v[i];"))
        with self.assertRaises(ErrorEmoLang):
            correr(r.emoc)

    def test_estructura_por_referencia(self):
        s = salida(principal("var p : Punto; p.x = 3; mueve(p); mostrar(p.x, p.z);",
                             "estructura Punto { x : int; z : decimal; }\n"
                             "funcion mueve(q : Punto) { q.x = q.x + 1; q.z = 0.5; }"))
        self.assertEqual(s, ["4 0.5"])

    def test_errores(self):
        est = "estructura P { x : int; }\n"
        casos = [
            (principal("var v : int[0];"), "mayor que cero"),
            (principal("var v : int[2] = [1];"), "tiene 2 elementos"),
            (principal('var v : int[1] = ["a"];'), "no se puede guardar"),
            (principal("var v : int[2]; v[0.5] = 1;"), "debe ser int"),
            (principal("var v : int[2]; v[2] = 1;"), "fuera de rango"),
            (principal("var n : int = 0; n[0] = 1;"), "no es un arreglo"),
            (principal("var a : int[2]; var b : int[2]; a = b;"), "no se puede asignar completo"),
            (principal("var v : int[2]; mostrar(v);"), "solo recibe valores primitivos"),
            (principal('var v : int[2]; registrar("x" + v);'), "no se puede concatenar"),
            (principal("var p : P; p.z = 1;", est), "no tiene el campo"),
            (principal("var n : int = 0; n.x = 1;"), "no es una estructura"),
            (principal('var p : P; p.x = "a";', est), "no se puede asignar"),
            (principal("var p : Nada;"), "tipo desconocido"),
            ("estructura Q { p : int; p : int; }\nfuncion principal() { }", "está repetido"),
        ]
        for fuente, esperado in casos:
            with self.subTest(esperado=esperado):
                self.assertTrue(any(esperado in m for m in errores(fuente)), errores(fuente))


class TestConstantesYConversiones(unittest.TestCase):
    def test_constante_no_se_puede_asignar(self):
        msgs = errores(principal("N = 2;", "const N : int = 1;"))
        self.assertTrue(any("constante" in m and "no se puede asignar" in m for m in msgs))

    def test_constante_debe_conocerse_al_compilar(self):
        msgs = errores(principal("", "var a : int = 1;\nfuncion f() : int { retornar 1; }\nconst N : int = f();"))
        self.assertTrue(any("debe conocerse al compilar" in m for m in msgs))
        msgs = errores(principal("", "var a : int = 1;\nconst N : int = a;"))
        self.assertTrue(any("debe conocerse al compilar" in m for m in msgs))

    def test_conversiones_explicitas(self):
        self.assertEqual(salida(principal("mostrar(a_int(2.9), a_decimal(1) / 4);")), ["2 0.25"])
        msgs = errores(principal('mostrar(a_int("x"));'))
        self.assertTrue(any("se esperaba num" in m for m in msgs))

    def test_decimal_a_int_requiere_conversion(self):
        self.assertTrue(errores(principal("var n : int = 2.5;")))
        self.assertEqual(salida(principal("var n : int = a_int(2.5); mostrar(n);")), ["2"])


if __name__ == "__main__":
    unittest.main()
