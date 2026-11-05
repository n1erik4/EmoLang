"""Pruebas del convertidor de notaciones y de la tabla de direcciones."""

import glob
import os
import random
import unittest

from emolang.compilador import compilar, compilar_archivo
from emolang.direcciones import construir
from emolang.errores import Reporte
from emolang.intermedio import PROGRAMA
from emolang.lexico import analizar as tokenizar
from emolang import nodos as N
from emolang.notaciones import (ErrorNotacion, a_infija, a_postfija, a_prefija, convertir, infija_a_postfija,
                                postfija_a_arbol, prefija_a_arbol)
from emolang.sintactico import Sintactico

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def post_ast(e):
    """Postfija calculada recorriendo el árbol del analizador sintáctico real."""
    if isinstance(e, N.Literal):
        return [{True: "verdadero", False: "falso"}[e.valor] if isinstance(e.valor, bool) else str(e.valor)]
    if isinstance(e, N.Identificador):
        return [e.nombre]
    if isinstance(e, N.Unaria):
        return post_ast(e.operando) + ["no" if e.op == "no" else "neg"]
    if isinstance(e, N.Binaria):
        return post_ast(e.izq) + post_ast(e.der) + [e.op]
    if isinstance(e, N.Llamada):
        return [s for a in e.args for s in post_ast(a)] + [f"{e.nombre}/{len(e.args)}"]
    if isinstance(e, N.Indice):
        return [e.base] + post_ast(e.indice) + ["[]"]
    if isinstance(e, N.Campo):
        return [f"{e.base}.{e.campo}"]
    raise TypeError(type(e))


def analizar_expr(texto):
    reporte = Reporte()
    tokens, _ = tokenizar(texto, reporte)
    s = Sintactico(tokens, reporte)
    arbol = s._expr()
    assert s.actual.tipo == "EOF" and not reporte.errores, (texto, reporte.errores)
    return arbol


def expr_aleatoria(rng, nivel=0):
    """Expresión válida según la gramática; las comparaciones no se encadenan."""
    if nivel > 4 or rng.random() < 0.3:
        return rng.choice(["a", "b", "ear", "2", "0.5", "verdadero", "v[i]", "p.x", "f(a, 1)", "g()"])
    op = rng.choice(["+", "-", "*", "/", "y", "o", "<", "==", "neg", "no", "par"])
    if op == "par":
        return f"({expr_aleatoria(rng, nivel + 1)})"
    if op == "neg":
        return f"-{expr_paren(rng, nivel + 1)}"
    if op == "no":
        return f"no {expr_paren(rng, nivel + 1)}"
    return f"{expr_paren(rng, nivel + 1)} {op} {expr_paren(rng, nivel + 1)}"


def expr_paren(rng, nivel):
    """Los operandos con operador van entre paréntesis si la mezcla podría encadenar comparaciones."""
    e = expr_aleatoria(rng, nivel)
    return f"({e})" if rng.random() < 0.6 or any(c in e for c in "<=") or e.startswith("no ") else e


class TestConversion(unittest.TestCase):
    def test_precedencia(self):
        self.assertEqual(convertir("a + 0.5 * b"),
                         {"infija": "a + 0.5 * b", "postfija": "a 0.5 b * +", "prefija": "+ a * 0.5 b"})

    def test_parentesis_cambian_el_orden(self):
        r = convertir("(a + b) * c")
        self.assertEqual(r["postfija"], "a b + c *")
        self.assertEqual(r["prefija"], "* + a b c")
        self.assertEqual(r["infija"], "(a + b) * c")

    def test_asociatividad_izquierda(self):
        self.assertEqual(convertir("a - b - c")["postfija"], "a b - c -")
        self.assertEqual(convertir("a - (b - c)")["postfija"], "a b c - -")
        self.assertEqual(convertir("a - (b - c)")["infija"], "a - (b - c)")

    def test_parentesis_innecesarios_se_quitan(self):
        self.assertEqual(convertir("((a * b)) + (c)")["infija"], "a * b + c")

    def test_expresion_del_lenguaje(self):
        r = convertir("pitch > cabeceo_grados y ear < 0.27")
        self.assertEqual(r["postfija"], "pitch cabeceo_grados > ear 0.27 < y")
        self.assertEqual(r["prefija"], "y > pitch cabeceo_grados < ear 0.27")

    def test_signo_y_negacion(self):
        self.assertEqual(convertir("-a * b")["postfija"], "a neg b *")
        self.assertEqual(convertir("no a y b")["postfija"], "a no b y")
        self.assertEqual(convertir("no (a y b)")["postfija"], "a b y no")
        self.assertEqual(convertir("a - -b")["postfija"], "a b neg -")
        self.assertEqual(convertir("no a < b")["postfija"], "a b < no")

    def test_llamadas_arreglos_y_campos(self):
        self.assertEqual(convertir("f(a + 1, g(b), h())")["postfija"], "a 1 + b g/1 h/0 f/3")
        self.assertEqual(convertir("v[i + 1] * p.x")["postfija"], "v i 1 + [] p.x *")
        self.assertEqual(convertir("f(a + 1, g(b), h())")["infija"], "f(a + 1, g(b), h())")
        self.assertEqual(convertir("v[i + 1] * p.x")["infija"], "v[i + 1] * p.x")

    def test_unidades_y_cadenas(self):
        self.assertEqual(convertir("mar > 60%")["postfija"], "mar 60% >")
        self.assertEqual(convertir("t < 1.5 s")["postfija"], "t 1.5s <")
        self.assertEqual(convertir('"hola mundo" + a')["postfija"], '"hola mundo" a +')

    def test_comparacion_entre_parentesis_no_se_encadena(self):
        self.assertEqual(convertir("(a < b) == c")["postfija"], "a b < c ==")
        self.assertEqual(convertir("(a < b) == c")["infija"], "(a < b) == c")
        self.assertEqual(convertir("a y no b")["postfija"], "a b no y")

    def test_desde_postfija_y_prefija(self):
        for origen, texto in (("postfija", "a 0.5 b * +"), ("prefija", "+ a * 0.5 b")):
            self.assertEqual(convertir(texto, origen)["infija"], "a + 0.5 * b")
        self.assertEqual(convertir('"a b" c +', "postfija")["prefija"], '+ "a b" c')
        self.assertEqual(convertir("a b g/2 neg", "postfija")["infija"], "-g(a, b)")

    def test_errores(self):
        for mala in ["a +", "* a", "(a + b", "a + b)", "a b", "f(a,", "f(,a)", "v[", "v[]", "a < b < c",
                     "()", "a @ b", "a, b", "", "(a < b < c)", "f(a < b < c)", "a + no b", "-no a",
                     "a < b + c < d"]:
            with self.subTest(expresion=mala):
                with self.assertRaises(ErrorNotacion):
                    convertir(mala)
        for mala, origen in [("a +", "postfija"), ("a b", "postfija"), ("+ a", "prefija"), ("a b", "prefija")]:
            with self.subTest(expresion=mala, origen=origen):
                with self.assertRaises(ErrorNotacion):
                    convertir(mala, origen)


class TestContraElCompilador(unittest.TestCase):
    """El convertidor usa otro algoritmo que el analizador: deben coincidir siempre."""

    def test_coincide_con_el_analizador_y_hace_ida_y_vuelta(self):
        rng = random.Random(2026)
        for _ in range(1500):
            e = expr_aleatoria(rng)
            post = infija_a_postfija(e)
            self.assertEqual(post, post_ast(analizar_expr(e)), e)
            arbol = postfija_a_arbol(post)
            self.assertEqual(a_postfija(prefija_a_arbol(a_prefija(arbol))), post, e)
            # la infija reconstruida con paréntesis mínimos significa lo mismo
            self.assertEqual(infija_a_postfija(a_infija(arbol)), post, e)

    def test_expresiones_de_los_ejemplos(self):
        for ruta in glob.glob(os.path.join(RAIZ, "ejemplos", "*.emo")):
            if "errores" in ruta:
                continue
            r = compilar_archivo(ruta)
            for dom in r.analisis.dominios.values():
                for g in dom.gestos.values():
                    from emolang.automatas import texto_expr
                    # los umbrales con % o unidades se escriben distinto en el árbol
                    texto = texto_expr(g.condicion)
                    if "%" not in texto and " ms" not in texto and " s" not in texto:
                        self.assertEqual(infija_a_postfija(texto), post_ast(g.condicion))


class TestDirecciones(unittest.TestCase):
    def tabla(self, fuente):
        r = compilar(fuente)
        self.assertTrue(r.ok, [str(d) for d in r.reporte.errores])
        return construir(r.cuadruplas[PROGRAMA])

    def test_globales_locales_y_temporales(self):
        t = self.tabla("""var g : int = 1;
        funcion f(a : int, v : int[]) : int {
            var x : int = a + g;
            retornar x + v[0];
        }
        funcion principal() : int { var d : int[2]; retornar f(1, d); }""")
        self.assertEqual(t.buscar("funcion.f", "f.a").direccion, "[rbp-8]")
        self.assertEqual(t.buscar("funcion.f", "f.a").categoria, "parametro")
        self.assertEqual(t.buscar("funcion.f", "f.v").direccion, "[rbp-16]")
        self.assertEqual(t.buscar("funcion.f", "f.v").bytes, 8)       # referencia
        self.assertEqual(t.buscar("funcion.f", "t1").categoria, "temporal")
        self.assertEqual(t.buscar("funcion.f", "g").direccion, "datos+0")
        self.assertEqual(t.marcos["funcion.f"].bytes % 16, 0)

    def test_arreglo_local_ocupa_longitud_y_elementos(self):
        t = self.tabla("funcion principal() : int { var d : int[3]; d[0] = 1; retornar d[0]; }")
        entrada = [e for e in t.marcos["funcion.principal"].entradas if e.nombre.startswith("principal.d")][0]
        self.assertEqual(entrada.bytes, 32)
        self.assertEqual(entrada.tipo, "int[3]")

    def test_estructura_ocupa_sus_campos(self):
        t = self.tabla("""estructura P { x : int; w : decimal; }
        var p : P;
        funcion principal() : int { p.x = 1; retornar p.x; }""")
        self.assertEqual([e for e in t.datos if e.nombre == "p"][0].bytes, 16)

    def test_literales_sin_repetir(self):
        t = self.tabla('''funcion principal() : int {
            mostrar("hola"); mostrar("hola"); mostrar("ñ"); var d : decimal = 0.5; mostrar(d);
            retornar 0; }''')
        self.assertEqual([(e.direccion, e.bytes) for e in t.literales],
                         [("str_1", 5), ("str_2", 3), ("flt_3", 8)])

    def test_marcos_no_se_enciman(self):
        for ruta in glob.glob(os.path.join(RAIZ, "tests", "execution", "*.emo")):
            r = compilar_archivo(ruta)
            for marco in construir(r.optimizado[PROGRAMA]).marcos.values():
                ocupado = 0
                for e in marco.entradas:
                    ocupado += e.bytes
                    self.assertEqual(e.direccion, f"[rbp-{ocupado}]")
                self.assertGreaterEqual(marco.bytes, ocupado)

    def test_ejemplos_de_gestos(self):
        r = compilar_archivo(os.path.join(RAIZ, "ejemplos", "conduccion.emo"))
        t = construir(r.optimizado["conduccion"])
        self.assertEqual(t.buscar("gestos", "ear").categoria, "metrica")
        self.assertEqual(t.buscar("alerta.al_entrar", "alertas").categoria, "global")
        self.assertEqual(t.buscar("gestos", "t1").tipo, "bool")


if __name__ == "__main__":
    unittest.main()
