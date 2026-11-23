"""Pruebas del Tema 4: código objeto x86-64.

Los programas de tests/execution y tests/intermediate se traducen a ensamblador, se
ensamblan con gcc, se ejecutan y su salida debe ser igual al archivo .esperado: con y
sin optimizar y con y sin asignación de registros.  Además, los programas al azar del
optimizador se corren en EmoVM y en ensamblador y deben dar la misma salida.

Las pruebas que ejecutan necesitan gcc para la plataforma de esta computadora
(en Windows, el de MSYS2); si no está, se omiten.
"""

import glob
import os
import shutil
import tempfile
import unittest

from emolang import codigo_objeto as CO
from emolang.compilador import compilar, compilar_archivo
from emolang.errores import ErrorEmoLang
from emolang.intermedio import PROGRAMA, resolver
from emolang.modulos import ModuloPrograma
from emolang.vm import EmoVM
from tests.test_optimizador import Generador

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
HAY_GCC = shutil.which("gcc") is not None
LIMITE_64 = 2**63


def compilado(fuente):
    r = compilar(fuente)
    assert r.ok, [str(d) for d in r.reporte.errores]
    return r


def ensamblador(r, plataforma=None, optimizado=True, registros=True):
    progs = r.optimizado if optimizado else r.cuadruplas
    return CO.generar(progs[PROGRAMA], r.analisis, plataforma, registros)


class Ejecutor:
    """Ensambla y ejecuta en una carpeta temporal."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="emolang_asm_")

    def correr(self, co):
        asm = os.path.join(self.dir, "p.asm")
        exe = os.path.join(self.dir, "p" + CO.PLATAFORMAS[co.plataforma].exe)
        with open(asm, "w", encoding="utf-8") as f:
            f.write(co.asm)
        ok, mensajes = CO.ensamblar(asm, exe)
        assert ok, mensajes
        return CO.ejecutar(exe)

    def limpiar(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def salida_vm(r):
    lineas = []
    try:
        valor = EmoVM(r.emoc, PROGRAMA, ModuloPrograma(salida=lineas.append)).ejecutar_principal()
    except ErrorEmoLang as e:
        lineas.append(f"Error en tiempo de ejecución: {e}")
        valor = 1
    return "".join(x + "\n" for x in lineas), (valor if isinstance(valor, int) else 0) % 256


def cabe_en_64_bits(texto):
    for palabra in texto.split():
        if palabra.lstrip("-").isdigit() and abs(int(palabra)) >= LIMITE_64:
            return False
    return True


@unittest.skipUnless(HAY_GCC, "se necesita gcc para ensamblar")
class TestEjecucion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ej = Ejecutor()

    @classmethod
    def tearDownClass(cls):
        cls.ej.limpiar()

    def test_programas_de_prueba(self):
        rutas = sorted(glob.glob(os.path.join(AQUI, "execution", "*.emo")) +
                       glob.glob(os.path.join(AQUI, "intermediate", "*.emo")))
        self.assertGreaterEqual(len(rutas), 9)
        for ruta in rutas:
            r = compilar_archivo(ruta)
            with open(ruta[:-4] + ".esperado", encoding="utf-8") as f:
                esperado = f.read()
            for optimizado in (True, False):
                for registros in (True, False):
                    with self.subTest(programa=os.path.basename(ruta), optimizado=optimizado, registros=registros):
                        codigo, salida = self.ej.correr(ensamblador(r, None, optimizado, registros))
                        self.assertEqual(salida, esperado)
                        self.assertEqual(codigo, 0)

    def test_programas_al_azar_igual_que_emovm(self):
        comparados = 0
        for semilla in range(120):
            r = compilado(Generador(semilla).programa())
            esperado, codigo_vm = salida_vm(r)
            if not cabe_en_64_bits(esperado):
                continue          # Python no tiene límite; x86-64 usa enteros de 64 bits
            for optimizado in (True, False):
                with self.subTest(semilla=semilla, optimizado=optimizado):
                    codigo, salida = self.ej.correr(ensamblador(r, None, optimizado))
                    self.assertEqual(salida, esperado)
                    self.assertEqual(codigo, codigo_vm)
            comparados += 1
        self.assertGreater(comparados, 110)

    def test_errores_en_tiempo_de_ejecucion(self):
        casos = [
            ("funcion principal() : int { var d : int = 0; mostrar(\"antes\"); mostrar(10 / d); retornar 0; }",
             "antes\nError en tiempo de ejecución: división entre cero\n"),
            ("funcion leer(v : int[], i : int) : int { retornar v[i]; }\n"
             "funcion principal() : int { var v : int[3]; mostrar(leer(v, 2)); mostrar(leer(v, -1)); retornar 0; }",
             "0\nError en tiempo de ejecución: índice -1 fuera de rango: el arreglo tiene 3 elementos\n"),
        ]
        for fuente, esperado in casos:
            with self.subTest(esperado=esperado):
                r = compilado(fuente)
                self.assertEqual(salida_vm(r), (esperado, 1))
                self.assertEqual(self.ej.correr(ensamblador(r)), (1, esperado))

    def test_codigo_de_salida_es_el_valor_de_principal(self):
        r = compilado("funcion principal() : int { retornar 42; }")
        self.assertEqual(self.ej.correr(ensamblador(r)), (42, ""))

    def test_ensamblador_de_la_otra_plataforma_tiene_sintaxis_valida(self):
        """Se ensambla (sin enlazar) el código de la plataforma que no es la local."""
        r = compilar_archivo(os.path.join(AQUI, "execution", "calculadora.emo"))
        otra = "windows" if CO.plataforma_local() == "linux" else "linux"
        asm = ensamblador(r, otra).asm
        if CO.plataforma_local() == "linux":
            asm = asm.replace('.section .rdata,"dr"', ".section .rodata")
        else:
            asm = asm.replace(".section .rodata", '.section .rdata,"dr"').replace(
                '.section .note.GNU-stack,"",@progbits', "").replace("@PLT", "")
        ruta = os.path.join(self.ej.dir, "otra.asm")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(asm)
        import subprocess
        p = subprocess.run(["gcc", "-c", "-x", "assembler", ruta, "-o", ruta + ".o"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)


class TestConvencionDeLlamadas(unittest.TestCase):
    FUENTE = """
funcion f(a : int, b : decimal, c : int, d : decimal, e : int, g : int, h : int, i : int, j : int) : decimal {
    retornar a + b + c + d + e + g + h + i + j;
}
funcion principal() : int { mostrar(f(1, 2.0, 3, 4.0, 5, 6, 7, 8, 9)); retornar 0; }
"""

    def test_windows_usa_un_registro_por_posicion_y_espacio_sombra(self):
        asm = ensamblador(compilado(self.FUENTE), "windows").asm
        cuerpo = asm.split("f_f:")[1]
        self.assertIn("mov rbx, rcx", cuerpo)                         # a: 1.er argumento entero
        self.assertIn("movsd qword ptr [rbp-16], xmm1", cuerpo)       # b: 2.º argumento, en xmm1
        self.assertIn("mov rax, qword ptr [rbp+48]", cuerpo)          # e: 5.º argumento, en la pila
        llamada = asm.split("f_principal:")[1]
        self.assertIn("mov qword ptr [rsp+32], rax", llamada)         # 5.º argumento después de la sombra
        self.assertNotIn("@PLT", asm)
        self.assertIn('.section .rdata,"dr"', asm)

    def test_linux_separa_enteros_y_decimales(self):
        asm = ensamblador(compilado(self.FUENTE), "linux").asm
        cuerpo = asm.split("f_f:")[1]
        self.assertIn("mov rbx, rdi", cuerpo)                         # a
        self.assertIn("movsd qword ptr [rbp-16], xmm0", cuerpo)       # b: 1.er decimal
        self.assertIn("mov rax, qword ptr [rbp+16]", cuerpo)          # 7.º entero: primero en la pila
        self.assertIn("call printf@PLT", asm)


class TestAsignacionDeRegistros(unittest.TestCase):
    def asignacion(self, fuente, funcion="f"):
        r = compilado(fuente)
        co = ensamblador(r, "linux")
        return co.asignaciones[f"funcion.{funcion}"], r

    def test_intervalos_que_se_traslapan_no_comparten_registro(self):
        for semilla in range(40):
            r = compilado(Generador(semilla).programa())
            for asig in ensamblador(r, "linux").asignaciones.values():
                con_registro = [iv for iv in asig.intervalos if iv.registro]
                for i, a in enumerate(con_registro):
                    for b in con_registro[i + 1:]:
                        if a.registro == b.registro:
                            self.assertTrue(a.fin < b.inicio or b.fin < a.inicio, (semilla, a, b))

    def test_se_derrama_cuando_no_alcanzan_los_registros(self):
        fuente = """funcion f(a : int, b : int, c : int, d : int, e : int, g : int, h : int) : int {
            retornar a + b + c + d + e + g + h;
        }
        funcion principal() : int { mostrar(f(1, 2, 3, 4, 5, 6, 7)); retornar 0; }"""
        asig, _ = self.asignacion(fuente)
        self.assertEqual(len(asig.usados), len(CO.REGISTROS))
        self.assertTrue(asig.derramadas)

    def test_variable_viva_en_todo_el_ciclo(self):
        """Por el salto hacia atrás, el límite de un ciclo vive hasta el final del cuerpo."""
        fuente = """funcion f(n : int) : int {
            var suma : int = 0;
            para i = 0 hasta n * 2 { suma = suma + i; }
            retornar suma;
        }
        funcion principal() : int { mostrar(f(3)); retornar 0; }"""
        asig, r = self.asignacion(fuente)
        cuads = resolver(r.optimizado[PROGRAMA].bloques["funcion.f"])
        salto_atras = max(i for i, c in enumerate(cuads) if c.op == "goto")
        limite = next(c.a2 for c in cuads if c.op == "<=")
        iv = next(v for v in asig.intervalos if v.nombre == limite)
        self.assertGreaterEqual(iv.fin, salto_atras)

    def test_variables_vivas(self):
        r = compilado("funcion f(a : int) : int { var b : int = a * 3; retornar b + a; }\n"
                      "funcion principal() : int { mostrar(f(2)); retornar 0; }")
        cuads = resolver(r.cuadruplas[PROGRAMA].bloques["funcion.f"])
        entrada, _ = CO.variables_vivas(cuads)
        self.assertIn("f.a", entrada[0])
        self.assertEqual(entrada[-1], set())

    def test_los_decimales_no_usan_registros_enteros(self):
        asig, _ = self.asignacion("funcion f(x : decimal) : decimal { retornar x * 2.0; }\n"
                                  "funcion principal() : int { mostrar(f(1.5)); retornar 0; }")
        self.assertEqual(asig.registros, {})


class TestAlcance(unittest.TestCase):
    def test_un_modulo_de_dominio_se_queda_en_emovm(self):
        r = compilar_archivo(os.path.join(RAIZ, "ejemplos", "conduccion.emo"))
        self.assertTrue(r.ok)
        for prog in r.optimizado.values():
            with self.assertRaises(CO.NoSoportado):
                CO.generar(prog, r.analisis, "linux")

    def test_segmentos_de_memoria(self):
        r = compilado("var total : int = 5;\nvar tabla : int[4];\n"
                      "funcion suma(n : int) { total = total + n; tabla[1] = total; }\n"
                      "funcion principal() : int { suma(2); mostrar(\"hola\", total, tabla[1] * 2.5); retornar 0; }")
        asm = ensamblador(r, "linux").asm
        self.assertIn("g_total:  .zero 8", asm)
        self.assertIn("g_tabla:  .zero 40", asm)          # longitud + 4 elementos
        self.assertRegex(asm, r"str_\d+:  .byte 104, 111, 108, 97, 0")
        self.assertIn("flt_", asm)
        self.assertIn("    .data", asm)
        self.assertIn("    .text", asm)
        self.assertIn(".section .rodata", asm)


if __name__ == "__main__":
    unittest.main()
