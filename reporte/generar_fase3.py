"""Genera reporte/EmoLang_Fase3_Reporte.pdf con el mismo formato que el reporte de la fase 2.

El ensamblador, la asignación de registros, el mapeo de cuádruplas a instrucciones,
las pruebas ejecutadas con gcc y el conteo de pruebas se obtienen al momento del
compilador real, así que el documento no puede quedar desalineado del código.

Uso (desde la raíz del proyecto, con gcc instalado):
    .venv/bin/python reporte/generar_fase3.py
"""

import glob
import os
import re
import shutil
import sys
import tempfile
import unittest

from PIL import Image as PILImage
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents
from xml.sax.saxutils import escape

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from emolang import codigo_objeto as CO  # noqa: E402
from emolang.compilador import compilar, compilar_archivo  # noqa: E402
from emolang.errores import ErrorEmoLang  # noqa: E402
from emolang.intermedio import PROGRAMA, resolver  # noqa: E402
from emolang.modulos import ModuloPrograma  # noqa: E402
from emolang.vm import EmoVM  # noqa: E402

FIG = os.path.join(AQUI, "figuras")
SALIDA = os.path.join(AQUI, "EmoLang_Fase3_Reporte.pdf")
ANCHO = letter[0] - 5 * cm - 12


# ------------------------------------------------------------------ fuentes
def _fuentes():
    """Arial y Consolas en Windows; en Linux, Liberation Sans (mismas medidas que Arial)."""
    win = r"C:\Windows\Fonts"
    lib = "/usr/share/fonts/truetype/liberation"
    if os.path.exists(os.path.join(win, "arial.ttf")):
        return {"Arial": f"{win}/arial.ttf", "Arial-B": f"{win}/arialbd.ttf", "Arial-I": f"{win}/ariali.ttf",
                "Arial-BI": f"{win}/arialbi.ttf", "Consolas": f"{win}/consola.ttf"}
    return {"Arial": f"{lib}/LiberationSans-Regular.ttf", "Arial-B": f"{lib}/LiberationSans-Bold.ttf",
            "Arial-I": f"{lib}/LiberationSans-Italic.ttf", "Arial-BI": f"{lib}/LiberationSans-BoldItalic.ttf",
            "Consolas": f"{lib}/LiberationMono-Regular.ttf"}


for _nombre, _ruta in _fuentes().items():
    pdfmetrics.registerFont(TTFont(_nombre, _ruta))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-B", italic="Arial-I", boldItalic="Arial-BI")

cuerpo = ParagraphStyle("cuerpo", fontName="Arial", fontSize=10.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=7)
lista = ParagraphStyle("lista", parent=cuerpo, leftIndent=16, bulletIndent=4, spaceAfter=3)
h1 = ParagraphStyle("h1", fontName="Arial-B", fontSize=13, leading=17, spaceBefore=14, spaceAfter=8, keepWithNext=1)
h2 = ParagraphStyle("h2", fontName="Arial-B", fontSize=11, leading=14, spaceBefore=10, spaceAfter=5, keepWithNext=1)
pie = ParagraphStyle("pie", fontName="Arial-B", fontSize=9.5, leading=12, spaceBefore=6, spaceAfter=5, keepWithNext=1)
codigo = ParagraphStyle("codigo", fontName="Consolas", fontSize=7.9, leading=10, leftIndent=4)
celda = ParagraphStyle("celda", fontName="Arial", fontSize=8.8, leading=11, alignment=TA_LEFT)
celda_b = ParagraphStyle("celda_b", parent=celda, fontName="Arial-B")
celda_c = ParagraphStyle("celda_c", parent=celda, fontName="Consolas", fontSize=8.1)
simple_est = ParagraphStyle("simple", parent=cuerpo, spaceAfter=0)
portada = ParagraphStyle("portada", fontName="Arial", fontSize=12, leading=16, alignment=TA_CENTER)
portada_b = ParagraphStyle("portada_b", parent=portada, fontName="Arial-B")

historia = []


def c(texto):
    return f'<font name="Consolas" size="9.6">{escape(str(texto))}</font>'


def p(texto):
    historia.append(Paragraph(texto, cuerpo))


def titulo(texto):
    par = Paragraph(texto, h1)
    par._toc = (0, texto)
    historia.append(par)


def subtitulo(texto):
    par = Paragraph(texto, h2)
    par._toc = (1, texto)
    historia.append(par)


def vinetas(items):
    for it in items:
        historia.append(Paragraph(it, lista, bulletText="•"))
    historia.append(Spacer(1, 5))


def numerada(items):
    for i, it in enumerate(items, 1):
        historia.append(Paragraph(it, lista, bulletText=f"{i}."))
    historia.append(Spacer(1, 5))


def _con_titulo(bloque):
    if historia and hasattr(historia[-1], "_toc"):
        return [historia.pop()] + bloque
    return bloque


def simple(texto):
    """Recuadro «En palabras simples», como en el reporte de la fase 2."""
    t = Table([[Paragraph(f"<b>En palabras simples.</b> {texto}", simple_est)]], colWidths=[ANCHO])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, "black"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 7),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 7)]))
    historia.append(KeepTogether(_con_titulo([t, Spacer(1, 9)])))


def tabla(filas, anchos, codigo_en=(), rotulo=None, juntar=True):
    datos = []
    for i, fila in enumerate(filas):
        renglon = []
        for j, v in enumerate(fila):
            texto = str(v)
            if i == 0:
                renglon.append(Paragraph(texto, celda_b))
            elif j in codigo_en:
                renglon.append(Paragraph(escape(texto).replace("\n", "<br/>"), celda_c))
            else:
                renglon.append(Paragraph(texto, celda))
        datos.append(renglon)
    total = sum(anchos)
    t = Table(datos, colWidths=[a * ANCHO / total for a in anchos], repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.5, "black"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    bloque = ([Paragraph(rotulo, pie)] if rotulo else []) + [t, Spacer(1, 11)]
    if juntar and len(filas) < 24:
        historia.append(KeepTogether(_con_titulo(bloque)))
    else:
        historia.extend(bloque)


def listado(texto, rotulo=None):
    t = Table([[Preformatted(l or " ", codigo)] for l in texto.rstrip("\n").split("\n")], colWidths=[ANCHO])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, "black"),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    if rotulo:
        historia.append(Paragraph(rotulo, pie))
    historia.append(t)
    historia.append(Spacer(1, 10))


def figura(ruta, rotulo, ancho_cm=15.5, max_alto_cm=19):
    w, h = PILImage.open(ruta).size
    ancho = min(ancho_cm * cm, ANCHO)
    alto = ancho * h / w
    if alto > max_alto_cm * cm:
        alto = max_alto_cm * cm
        ancho = alto * w / h
    historia.append(KeepTogether(_con_titulo([Paragraph(rotulo, pie), Image(ruta, width=ancho, height=alto),
                                              Spacer(1, 10)])))


class Documento(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, "_toc"):
            nivel, texto = flowable._toc
            self.notify("TOCEntry", (nivel, texto, self.page))


def numero_pagina(canvas, doc):
    canvas.saveState()
    canvas.setFont("Arial", 9)
    canvas.drawCentredString(letter[0] / 2, 1.4 * cm, str(doc.page))
    canvas.restoreState()


# ================================================================== DATOS REALES
print("Calculando datos del compilador…")
HAY_GCC = shutil.which("gcc") is not None
TMP = tempfile.mkdtemp(prefix="emolang_reporte_")

R_FACT = compilar_archivo("tests/execution/factorial.emo")
CO_FACT = CO.generar(R_FACT.optimizado[PROGRAMA], R_FACT.analisis, "linux")
CO_FACT_WIN = CO.generar(R_FACT.optimizado[PROGRAMA], R_FACT.analisis, "windows")
R_CALC = compilar_archivo("tests/execution/calculadora.emo")
CO_CALC_WIN = CO.generar(R_CALC.optimizado[PROGRAMA], R_CALC.analisis, "windows")


def funcion_asm(asm, etiqueta):
    """Las líneas de una función del .asm, desde su etiqueta hasta su epílogo (sin errores)."""
    lineas = asm.split("\n")
    i = lineas.index(f"{etiqueta}:")
    salida = []
    for l in lineas[i:]:
        salida.append(l)
        if l.strip() == "ret" and any(x.startswith(".Lfin_") for x in salida):
            break
    return salida


def mapeo(asm, etiqueta, numeros):
    """[(cuádrupla, instrucciones)] tomadas de los comentarios del .asm."""
    filas, actual = [], None
    for l in funcion_asm(asm, etiqueta):
        m = re.match(r"\s+#\s+(\d+)\s+(\(.*\))$", l)
        if m:
            actual = [int(m.group(1)), m.group(2), []]
            filas.append(actual)
        elif actual and l.startswith("    ") and not l.strip().startswith("#"):
            actual[2].append(l.strip())
        elif l.startswith(".Lfin"):
            actual = None
    return [(q, "\n".join(ins)) for n, q, ins in filas if n in numeros]


def correr_asm(co):
    asm = os.path.join(TMP, "p.asm")
    exe = os.path.join(TMP, "p")
    with open(asm, "w", encoding="utf-8") as f:
        f.write(co.asm)
    ok, msg = CO.ensamblar(asm, exe)
    if not ok:
        return None, msg
    return CO.ejecutar(exe)


PRUEBAS_ASM = []
if HAY_GCC:
    for ruta in sorted(glob.glob("tests/execution/*.emo") + glob.glob("tests/intermediate/*.emo")):
        r = compilar_archivo(ruta)
        with open(ruta[:-4] + ".esperado", encoding="utf-8") as f:
            esperado = f.read()
        iguales, instrucciones = 0, None
        for opt in (True, False):
            for reg in (True, False):
                co = CO.generar((r.optimizado if opt else r.cuadruplas)[PROGRAMA], r.analisis, "linux", reg)
                if opt and reg:
                    instrucciones = co.instrucciones
                cod_salida, salida = correr_asm(co)
                iguales += salida == esperado and cod_salida == 0
        PRUEBAS_ASM.append((os.path.relpath(ruta, "tests"), instrucciones, iguales))


def salida_vm(r):
    lineas = []
    try:
        valor = EmoVM(r.emoc, PROGRAMA, ModuloPrograma(salida=lineas.append)).ejecutar_principal()
    except ErrorEmoLang as e:
        lineas.append(f"Error en tiempo de ejecución: {e}")
        valor = 1
    return "".join(x + "\n" for x in lineas), (valor if isinstance(valor, int) else 0) % 256


AZAR = {"total": 0, "iguales": 0, "desborde": 0, "otras": 0}
if HAY_GCC:
    sys.path.insert(0, os.path.join(RAIZ, "tests"))
    from tests.test_optimizador import Generador
    for semilla in range(300):
        r = compilar(Generador(semilla).programa())
        esperado, cod = salida_vm(r)
        cod_salida, salida = correr_asm(CO.generar(r.optimizado[PROGRAMA], r.analisis, "linux"))
        AZAR["total"] += 1
        if salida == esperado and cod_salida == cod:
            AZAR["iguales"] += 1
        elif any(w.lstrip("-").isdigit() and abs(int(w)) >= 2**63 for w in esperado.split()):
            AZAR["desborde"] += 1
        else:
            AZAR["otras"] += 1


def contar_pruebas():
    cargador = unittest.TestLoader()
    conteo = {}
    for ruta in sorted(glob.glob("tests/test_*.py")):
        modulo = "tests." + os.path.basename(ruta)[:-3]
        conteo[os.path.basename(ruta)] = cargador.loadTestsFromName(modulo).countTestCases()
    return conteo


PRUEBAS = contar_pruebas()
TOTAL_PRUEBAS = sum(PRUEBAS.values())

with open("evaluacion/fotos_cerrar_ojos_cew.md", encoding="utf-8") as f:
    CEW_MD = f.read()
CEW = re.search(r"\| cerrar_ojos \| ear < ([\d.]+) \| (\d+) \| (\d+) \| (\d+) \| ([\d.]+)% \| ([\d.]+)% \| ear < ([\d.]+) "
                r"\(([\d.]+)% / ([\d.]+)%\)", CEW_MD).groups()
CEW_UTILES = re.search(r"\*\*útiles: (\d+)\*\*", CEW_MD).group(1)
CEW_FOTOS = re.search(r"Fotos: (\d+)", CEW_MD).group(1)
print(f"  {len(PRUEBAS_ASM)} programas en ensamblador, {AZAR['iguales']}/{AZAR['total']} al azar, {TOTAL_PRUEBAS} pruebas")


# ================================================================== PORTADA
historia.append(Image(os.path.join(FIG, "logo_tecnm.png"), width=4.3 * cm, height=4.3 * cm * 118 / 192, hAlign="LEFT"))
historia.append(Spacer(1, 0.7 * cm))
for texto, estilo, despues in [
    ("TECNOLÓGICO NACIONAL DE MÉXICO", ParagraphStyle("pt", parent=portada_b, fontSize=14.5), 4),
    ("INSTITUTO TECNOLÓGICO DE OAXACA", portada_b, 20),
    ("MATERIA:", portada, 2), ("LENGUAJES Y AUTÓMATAS II", portada_b, 14),
    ("CLAVE DE MATERIA:", portada, 2), ("SCD1016", portada_b, 14),
    ("CARRERA:", portada_b, 2), ("INGENIERÍA EN SISTEMAS COMPUTACIONALES", portada, 22),
    ("PROYECTO INTEGRADOR – FASE 3: CÓDIGO OBJETO, CALIBRACIÓN Y APLICACIÓN WEB", portada_b, 4),
    ("EmoLang", ParagraphStyle("pn", parent=portada_b, fontSize=19, leading=24), 4),
    ("Módulos de conducción y de terapia facial", portada, 22),
    ("ALUMNOS:", portada_b, 8),
    ("GARCIA GABRIEL BETSAIDA<br/>GINER COACHE NIERIKA<br/>JIMENEZ LOPEZ FERNANDO ARATH<br/>"
     "LEÓN RAMÍREZ CARLOS PAVEL<br/>ORTIZ MARTÍNEZ JOSÉ JULIÁN", portada, 20),
    ("NOMBRE DEL PROFESOR:", portada_b, 4), ("VELAZQUEZ HERNANDEZ MARICARMEN MONTSERRAT", portada, 12),
    ("<b>GRUPO</b>: 7SB", portada, 12),
    ("OAXACA DE JUÁREZ, OAXACA<br/>NOVIEMBRE DE 2026", portada, 0),
]:
    historia.append(Paragraph(texto, estilo))
    historia.append(Spacer(1, despues))
historia.append(PageBreak())

historia.append(Paragraph("Índice", ParagraphStyle("hc", parent=h1, spaceBefore=0)))
indice = TableOfContents()
indice.levelStyles = [
    ParagraphStyle("t0", fontName="Arial-B", fontSize=9.6, leading=12, spaceBefore=2),
    ParagraphStyle("t1", fontName="Arial", fontSize=9, leading=10.8, leftIndent=14),
]
indice.tableStyle = TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 0.6),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)])
historia.append(indice)
historia.append(PageBreak())

# ================================================================== 1
titulo("1. Introducción")
p("Este reporte continúa el de la fase 2. En aquella entrega el compilador de EmoLang ya hacía el análisis "
  "semántico, generaba cuádruplas y las optimizaba; faltaba el último tema de la rúbrica, el <b>código objeto</b>. "
  "En esta fase se terminó ese tema y se agregaron dos piezas que acercan el proyecto a su uso real:")
vinetas([
    "<b>Código objeto.</b> El compilador traduce las cuádruplas optimizadas a ensamblador x86-64, lo ensambla con "
    "GCC y lo ejecuta como un programa nativo, en Windows y en Linux.",
    "<b>Calibración con fotos.</b> Una herramienta mide con MediaPipe cientos o miles de fotos para revisar si los "
    "umbrales de la terapia facial separan bien cada ejercicio.",
    "<b>Aplicación web.</b> Los dos módulos funcionan desde el navegador de un celular, una tablet o una computadora, "
    "con un servidor propio que guarda las cuentas y los resultados. El video nunca sale del dispositivo.",
])
p("Como en el reporte anterior, cada parte técnica empieza con un recuadro que la explica en palabras simples, "
  "y al final hay un glosario con los términos nuevos.")
subtitulo("1.1 Estado del proyecto")
p("La tabla compara el estado de cada punto de la rúbrica con el de la fase 2. «Hecho» significa que funciona "
  "y tiene pruebas automáticas.")
tabla([
    ["Punto de la rúbrica", "Fase 2", "Ahora", "Dónde se ve"],
    ["Temas 1, 2 y 3: semántico, código intermedio y optimización", "Hecho", "Hecho", "Reporte de la fase 2"],
    ["Tema 4: código objeto (registros, ensamblador, memoria)", "En desarrollo",
     "Hecho; ejecutado en Linux; en Windows se revisó que ensambla", "Sección 2"],
    ["Pruebas integrales de código objeto (tests/execution)", "Solo en EmoVM", "En ensamblador real con GCC", "Sección 2.6"],
    ["Módulo de conducción", "Hecho", "Hecho; se corrigió la alarma que no se apagaba", "Sección 5"],
    ["Módulo de terapia facial", "Hecho con el simulador", "Calibración con fotos; funciona en la web", "Secciones 3 y 4"],
    ["Uso desde celular, tablet y PC", "–", "Hecho, con servidor propio", "Sección 4"],
    ["Pruebas con participantes", "Pendiente", "Pendiente", "Sección 8"],
], [5.2, 2.2, 4.2, 2.2])

# ================================================================== 2
titulo("2. Tema 4: código objeto")
simple("Es el último paso del compilador. Las cuádruplas son una forma ordenada del programa, pero el procesador "
       "no las entiende. Este paso las cambia por instrucciones del procesador (ensamblador), decide qué datos "
       "viven en las «casillas» rápidas del procesador (registros) y dónde va todo lo demás en la memoria.")
p(f"El traductor está en {c('emolang/codigo_objeto.py')} y se usa con el comando {c('ensamblador')}. Recibe las "
  "cuádruplas optimizadas de la fase 2 y la tabla de direcciones, y produce un archivo <b>.asm</b> en sintaxis Intel "
  "del ensamblador GNU, el mismo que trae GCC. Con la opción " + c("--correr") + " además lo ensambla y lo ejecuta.")
listado("$ python -m emolang ensamblador tests/execution/factorial.emo --correr --registros\n"
        f"Ensamblador x86-64 (linux): factorial.asm  ({CO_FACT.instrucciones} instrucciones)\n"
        "...\n0 1 1\n1 1 1\n2 2 2\n...\n10 3628800 3628800\n\n(el programa terminó con código 0)",
        "Uso del comando (salida recortada)")
p("Solo se traducen los programas con " + c("funcion principal") + ", como los algoritmos de la rúbrica (factorial, "
  "Fibonacci, ordenamiento y calculadora). Los módulos de dominio siguen ejecutándose en EmoVM, porque sus gestos "
  "dependen de la cámara y de los autómatas en tiempo real.")

subtitulo("2.1 Plataformas y convención de llamadas")
simple("Cada sistema operativo tiene sus reglas para llamar a una función: en qué registros van los datos que "
       "recibe y quién reserva espacio en la pila. Si el programa no sigue esas reglas, no puede usar funciones "
       "como printf.")
p("La fase 2 eligió Windows con GCC de MSYS2. Como el equipo también trabaja en Linux, el traductor genera para las "
  "dos plataformas con la opción " + c("--plataforma") + "; la diferencia está casi toda en cómo se pasan los "
  "argumentos:")
tabla([
    ["Aspecto", "Windows (convención de Microsoft)", "Linux (System V)"],
    ["Argumentos enteros", "rcx, rdx, r8, r9", "rdi, rsi, rdx, rcx, r8, r9"],
    ["Argumentos decimales", "xmm0 a xmm3", "xmm0 a xmm7"],
    ["Cómo se reparten", "Por posición: el 2.º argumento usa rdx o xmm1, sea del tipo que sea",
     "Por clase: enteros y decimales llevan cuentas separadas"],
    ["Más argumentos", "En la pila, después de 32 bytes de «espacio sombra»", "En la pila"],
    ["Valor de regreso", "rax (entero) o xmm0 (decimal)", "rax (entero) o xmm0 (decimal)"],
], [3, 5, 5])
lineas_win = funcion_asm(CO_CALC_WIN.asm, "f_calcular")[:10]
listado("\n".join(lineas_win), "Inicio de calcular(codigo : int, a : decimal, b : decimal) en Windows: "
        "codigo llega en rcx, a en xmm1 y b en xmm2")
p("La prueba " + c("argumentos_pila.emo") + " llama a funciones con nueve y siete argumentos, así que algunos "
  "viajan por la pila; da el mismo resultado que EmoVM.")

subtitulo("2.2 Administración de memoria")
simple("El programa en ejecución divide su memoria en partes: una para las instrucciones, otra para las variables "
       "globales, otra para los textos fijos y una pila donde cada llamada a función aparta su propio espacio.")
tabla([
    ["Segmento", "Qué guarda", "Cómo se genera"],
    [".text", "Las funciones traducidas, main y un pequeño runtime", "Una etiqueta f_nombre por función"],
    [".data", "Variables globales; arreglos y estructuras globales en línea", "g_nombre: .zero bytes"],
    [".rodata", "Textos (str_N) y decimales constantes (flt_N)", "Los decimales se escriben con sus 8 bytes exactos"],
    ["Pila", "Parámetros, locales y temporales de cada llamada", "Las direcciones [rbp-k] de la tabla de direcciones"],
], [2, 6, 6])
p("Cada función empieza con el mismo prólogo: guarda el marco anterior, crea el suyo y aparta los bytes que pide "
  "la tabla de direcciones, más el lugar de los registros que va a usar y de los argumentos que pasará. El tamaño "
  "siempre es múltiplo de 16, como exigen las dos convenciones. Un arreglo guarda su longitud seguida de sus "
  "elementos; por eso el acceso " + c("v[i]") + " revisa primero el índice contra esa longitud.")
listado("\n".join(funcion_asm(CO_FACT.asm, "f_factorial")[:9]), "Prólogo de factorial en Linux")
p("El runtime son unas cuantas rutinas escritas también en ensamblador: escribir texto con printf, convertir "
  "números a texto con el mismo formato que EmoVM (por ejemplo, 15.0 se escribe «15» y −0 se escribe «0»), "
  "unir textos y avisar los errores en tiempo de ejecución, como la división entre cero o un índice fuera de rango.")

subtitulo("2.3 Asignación de registros")
simple("El procesador tiene pocas casillas rápidas. El compilador averigua en qué tramo del programa se usa cada "
       "variable y reparte las casillas para que dos variables que se usan al mismo tiempo no compartan la misma. "
       "Lo que no cabe se queda en la memoria.")
p("Primero se hace un <b>análisis de flujo de datos</b> (variables vivas): recorriendo el programa hacia atrás se "
  "calcula, para cada cuádrupla, qué variables todavía se van a leer después. Con eso cada variable tiene un "
  "<b>intervalo de vida</b>. Un ciclo alarga el intervalo hasta el salto de regreso, porque en la siguiente vuelta "
  "la variable se vuelve a leer.")
p("Después, el algoritmo <b>linear scan</b> (Poletto y Sarkar, 1999) recorre los intervalos en orden y les asigna "
  "uno de cinco registros: rbx, r12, r13, r14 y r15. Se eligieron porque en las dos convenciones la función llamada "
  "debe conservarlos, así que un valor guardado ahí sobrevive a una llamada. Si no hay registro libre, se manda a la "
  "pila el intervalo que termina más tarde. Los decimales viven en memoria y se calculan en xmm0 y xmm1.")
asig = CO_FACT.asignaciones["funcion.factorial_ciclo"]
tabla([["Variable", "Vive de la cuádrupla", "Hasta", "Lugar"]] +
      [[iv.nombre, iv.inicio + 1, iv.fin + 1, iv.registro or "pila"] for iv in asig.intervalos],
      [5, 3, 2, 3], codigo_en=(0, 3), rotulo="Asignación real de factorial_ciclo (comando ensamblador --registros)")
p(f"t2 vive solo en las cuádruplas 4 y 5, cuando {c('factorial_ciclo.n')} ya no se usa, así que puede reutilizar "
  "rbx. Con la opción " + c("--sin-registros") + " todo se queda en la pila; las pruebas comparan las dos versiones.")

subtitulo("2.4 Traducción de cuádruplas a ensamblador")
p("Cada cuádrupla se traduce con un esquema fijo. El archivo .asm conserva cada cuádrupla como comentario arriba de "
  "sus instrucciones, así que se puede seguir la traducción línea por línea. Este es un fragmento real de factorial:")
tabla([["Cuádrupla", "Ensamblador x86-64 generado"]] + mapeo(CO_FACT.asm, "f_factorial", {1, 2, 3, 6, 7, 8}),
      [4.5, 6], codigo_en=(0, 1), rotulo="Cuádruplas de factorial y su traducción (Linux)")
tabla([
    ["Cuádrupla", "Traducción"],
    ["+ - * con enteros", "add, sub, imul sobre el registro asignado; si una constante cabe en 32 bits se usa directo"],
    ["+ - * / con decimales", "addsd, subsd, mulsd, divsd en xmm0; un entero se convierte antes con cvtsi2sd"],
    ["/ (siempre decimal)", "Antes de dividir se compara el divisor con 0; si lo es, salta al aviso de error"],
    ["< <= > >= == !=", "cmp y setl/setle… (enteros); ucomisd y seta/setae (decimales, correcto con NaN); strcmp (textos)"],
    ["gotoF, goto", "test y je; jmp. Si la condición es constante, el salto se resuelve al compilar"],
    ["param, call", "Los argumentos se acumulan y se colocan según la convención al llegar a call"],
    ["retv, ret", "El valor queda en rax o xmm0 y se salta al epílogo de la función"],
    ["[], []=", "Revisa el índice contra la longitud y lee o escribe en [base + 8 + i·8]"],
    ["texto, concat", "Llaman a las rutinas del runtime"],
], [3.5, 10], rotulo="Esquemas de traducción")

subtitulo("2.5 Un error que encontró esta etapa")
p("Al comparar el ensamblador con EmoVM apareció un error de la fase de optimización. La reducción de fuerza "
  "cambiaba " + c("(1.0 * 32) * gb") + " por " + c("gb shl 5") + ", pero el temporal seguía marcado como decimal. "
  "EmoVM no lo notaba, porque Python cambia de tipo solo; en el procesador, el desplazamiento deja un entero que "
  "luego se leía como si fuera un decimal. Ahora el traductor convierte el resultado de " + c("shl") +
  " cuando su tipo es decimal.")

subtitulo("2.6 Pruebas del código objeto")
p("Los programas de " + c("tests/execution") + " y " + c("tests/intermediate") + " se traducen, se ensamblan con "
  "GCC, se ejecutan y su salida se compara con su archivo .esperado. Cada uno se prueba en cuatro versiones: con y "
  "sin optimizar, y con y sin asignación de registros.")
if PRUEBAS_ASM:
    tabla([["Programa", "Instrucciones (optimizado)", "Versiones iguales a .esperado"]] +
          [[n, i, f"{k} de 4"] for n, i, k in PRUEBAS_ASM], [6, 3.5, 4], codigo_en=(0,),
          rotulo="Resultados en Linux con GCC")
p(f"Además se generaron {AZAR['total']} programas al azar con ciclos, condiciones, arreglos, estructuras, globales "
  f"y decimales, y cada uno se ejecutó en EmoVM y en ensamblador. <b>{AZAR['iguales']}</b> dieron exactamente la "
  f"misma salida. Los {AZAR['desborde']} restantes calculan números enormes: Python no tiene límite para los "
  "enteros y x86-64 usa 64 bits, así que en ensamblador se desbordan. Es una diferencia esperada del hardware, no "
  "un error del traductor." + (f" Hubo {AZAR['otras']} diferencias de otro tipo." if AZAR["otras"] else ""))
p("Los mensajes de error en tiempo de ejecución también son iguales en las dos versiones, por ejemplo «índice 5 "
  "fuera de rango: el arreglo tiene 3 elementos», y el programa termina con código 1. El código de Windows se "
  "revisó ensamblándolo; ejecutarlo requiere una computadora con Windows y MSYS2.")

# ================================================================== 3
titulo("3. Calibración de la terapia facial con fotos")
simple("Antes de probar con personas conviene saber si los umbrales tienen sentido; por ejemplo, si «sonrisa mayor "
       "que 40 %» de verdad separa una sonrisa de una cara seria. Para eso se midieron miles de fotos de las que ya "
       "se sabe qué expresión muestran.")
p("Una foto es un solo cuadro de video: sirve para calibrar umbrales y revisar la simetría, pero no prueba "
  "duraciones ni repeticiones. La herramienta es el comando " + c("fotos") + ", con cuatro pasos:")
numerada([
    f"{c('descargar')}: baja fotos con licencia abierta de Openverse, una carpeta por expresión, y guarda autor, "
    "licencia y página de origen de cada una.",
    f"{c('analizar')}: mide cada foto con MediaPipe, con exactamente las mismas métricas que la cámara.",
    f"{c('galeria')}: arma una página para revisar las fotos y descartar las mal etiquetadas.",
    f"{c('reporte')}: cuenta aciertos y falsas alarmas con los umbrales del programa y busca el umbral que mejor "
    "separa las fotos.",
])
p("Las fotos son caras de personas: se guardan fuera del repositorio y solo se conservan los números.")
subtitulo("3.1 Ojos cerrados: base de datos CEW")
p(f"La base <i>Closed Eyes in the Wild</i> (Song et al., 2014) tiene {CEW_FOTOS} caras revisadas por "
  f"investigadores, con ojos abiertos o cerrados. De ellas, {CEW_UTILES} tuvieron el rostro de frente y bien "
  "detectado.")
tabla([
    ["Ejercicio", "Condición", "Detectadas", "No detectadas", "Falsas alarmas", "Sensibilidad", "Especificidad"],
    ["cerrar_ojos", f"ear &lt; {CEW[0]}", CEW[1], CEW[2], CEW[3], f"{CEW[4]} %", f"{CEW[5]} %"],
], [2.6, 2.2, 1.8, 2, 2, 2, 2.1], rotulo="Umbral del programa contra las fotos de CEW")
p(f"El mejor umbral posible con estas fotos es ear &lt; {CEW[6]} ({CEW[7]} % / {CEW[8]} %), prácticamente el "
  "mismo que ya tenía el programa, así que <b>umbral_ojos = 0.15 se conserva</b>, ahora con evidencia.")
subtitulo("3.2 Lo que enseñaron las fotos de internet")
p("Para sonrisa y cejas se usaron fotos de Openverse. Los resultados mostraron un problema de los datos, no del "
  "programa: las etiquetas salen del título de la foto. Al revisar las de «ojos cerrados», la mayoría tenían los "
  "ojos abiertos (un acercamiento a un ojo, una persona con binoculares), y MediaPipe las midió bien.")
tabla([
    ["Expresión", "Fotos descargadas", "Útiles", "Calidad de la etiqueta"],
    ["Sonrisa", "300", "191", "Aceptable: la mitad marca sonrisa de 0.62 o más; hay que limpiar"],
    ["Cejas levantadas", "300", "92", "Baja: muchas «sorpresas» sin cejas levantadas"],
    ["Ojos cerrados", "158", "37", "Mala: casi todas con los ojos abiertos"],
    ["Neutra", "20", "6", "Insuficiente"],
], [3, 2.5, 1.5, 6.5])
p("Conclusión: los umbrales de sonrisa y cejas no se cambian hasta tener datos confiables. Para cejas, ninguna "
  "base abierta tiene bien etiquetado el gesto; lo más útil será que el equipo se grabe con el comando "
  + c("capturar") + ", que ya existía desde la fase 2.")

# ================================================================== 4
titulo("4. Aplicación web")
simple("Ahora los dos módulos se usan desde el navegador del celular, la tablet o la computadora. La página "
       "hace todo el trabajo con la cámara dentro del dispositivo; el servidor solo entrega la página y guarda "
       "las cuentas y los resultados en números.")
subtitulo("4.1 Arquitectura")
tabla([
    ["Parte", "Dónde corre", "Qué hace"],
    ["MediaPipe (JavaScript)", "Navegador", "Encuentra los 478 puntos de la cara en cada cuadro de la cámara"],
    ["Métricas (web/js/rostro.js)", "Navegador", "Calcula ear, mar, sonrisa, cejas, simetría y pose, igual que camara.py"],
    ["Compilador y EmoVM (Pyodide)", "Navegador", "El mismo paquete emolang de Python, compilado a WebAssembly"],
    ["Puente (emolang/web.py)", "Navegador", "Ejecuta EmoVM a 30 cuadros por segundo aunque la cámara entregue menos"],
    ["Servidor (web/servidor.py)", "Laptop", "Cuentas, roles y resultados en SQLite; HTTPS en la red local"],
], [4, 2.2, 8])
p("Gracias a Pyodide no se escribió un segundo intérprete: el navegador ejecuta el mismo compilador y la misma "
  "EmoVM que las pruebas. Compilar el programa de terapia tarda unos 18 ms y cada cuadro menos de 0.1 ms. Para "
  "asegurar que las métricas de JavaScript son las mismas que las de Python, se compararon en 60 casos reales de "
  "MediaPipe: la diferencia máxima fue de 1.4 × 10<super>−14</super>, que es solo redondeo.")
subtitulo("4.2 Cuentas, roles y privacidad")
p("Cada persona crea una cuenta y elige un rol: <b>terapia</b> o <b>conductor</b>. Cada rol ve solo su módulo, "
  "su historial y sus estadísticas. El servidor usa solo la biblioteca estándar de Python:")
vinetas([
    "Las contraseñas se guardan protegidas con scrypt y sal; nunca en texto plano.",
    "La sesión usa una cookie que JavaScript no puede leer, que no viaja a otros sitios y, con HTTPS, solo viaja cifrada.",
    "Se guarda el resumen numérico y la bitácora de cada sesión; <b>nunca el video</b>, como se prometió en el "
    "marco legal de la fase 2. La persona puede borrar sus sesiones o su cuenta completa.",
    "Al registrarse hay que aceptar el aviso de privacidad, y se guarda la fecha del consentimiento.",
])
subtitulo("4.3 Uso desde el celular")
p("Los navegadores solo permiten usar la cámara en páginas seguras (HTTPS). Por eso el servidor tiene la opción "
  + c("--https-local") + ", que crea un certificado propio con la dirección de la laptop en la red. La computadora "
  "entra por http://localhost:8000 y los celulares por https://&lt;IP de la laptop&gt;:8443; la primera vez el "
  "navegador muestra una advertencia que hay que aceptar.")
p("Durante la sesión la página calibra la postura, muestra la instrucción en grande, el avance de cada ejercicio y "
  "medidores con la marca del umbral, y guía con voz (útil al cerrar los ojos). En conducción, la alarma pone la "
  "pantalla en rojo, suena y se lee en voz alta. Al terminar se ven los resultados y se puede descargar la bitácora "
  "en CSV.")
figura(os.path.join(FIG, "fig_web_celular.png"), "Figura 1. La aplicación en un celular: acceso, inicio de una "
       "persona con rol de terapia y resultados de una rutina", ancho_cm=15.5)
subtitulo("4.4 Pruebas de la aplicación")
p("Para probar sin una persona frente a la cámara se armaron videos con fotos ya medidas (cara neutra, sonrisa, "
  "cejas, ojos cerrados y bostezo) y se usaron como cámara falsa de Chromium. La prueba "
  + c("web/pruebas/navegador.py") + " arranca el servidor, crea una cuenta, hace la sesión y revisa el resultado:")
tabla([
    ["Prueba", "Resultado"],
    ["Celular por HTTPS con la IP de la red", "La página es segura y la cámara tiene permiso"],
    ["Rutina de terapia completa", "15 repeticiones con su simetría; termina sola y se guarda en el servidor"],
    ["Conducción en computadora", "Microsueño → alarma con sonido y voz → regreso a «Atento»; se guarda en el servidor"],
    ["Voz", "La página pide decir cada instrucción a volumen completo, empezando al tocar «Comenzar»"],
], [5, 9])
p("Lo que no se puede simular es el teléfono real: el permiso de la cámara y la voz dependen de cada modelo y "
  "navegador. La aplicación ya se abrió en un teléfono del equipo; con esa prueba se ajustó la activación del "
  "audio, porque los teléfonos solo dejan sonar una página si el sonido empieza al tocar un botón.")

# ================================================================== 5
titulo("5. Corrección del módulo de conducción")
p("La prueba de la aplicación encontró un error del programa " + c("conduccion.emo") + ": después de un "
  "microsueño, la alarma nunca se apagaba. Para salir del estado de alerta el programa espera el gesto "
  + c("atento") + " (mirar al frente durante 3 segundos), que solo revisaba la postura de la cabeza. Al cerrar los "
  "ojos la cabeza no se mueve, así que el autómata de " + c("atento") + " nunca se reiniciaba y no volvía a avisar.")
listado("// antes\ngesto atento = pitch < 10.0 y yaw < 20.0 y yaw > -20.0\n"
        "               durante 3 s tolerando 200 ms;\n"
        "// ahora: también exige los ojos abiertos\ngesto atento = pitch < 10.0 y yaw < 20.0 y yaw > -20.0 y ear > umbral_ojo\n"
        "               durante 3 s tolerando 200 ms;",
        "El cambio")
p("Ahora, al cerrar los ojos el gesto se interrumpe, y 3 segundos después de abrirlos ocurre otra vez y apaga la "
  "alarma. Hay una prueba automática para que el error no regrese, y la evaluación con el simulador sigue en 100 %.")

# ================================================================== 6
titulo("6. Pruebas")
p(f"La suite tiene ahora <b>{TOTAL_PRUEBAS} pruebas</b> (148 en la fase 2). Se ejecutan todas con "
  + c("python -m unittest discover -s tests -t .") + ".")
DESCR = {
    "test_emolang.py": "Léxico, sintáctico, semántico, autómatas y motor",
    "test_vm.py": "Máquina virtual, terapia facial y equivalencia entre versiones",
    "test_lenguaje.py": "Funciones, ciclos, arreglos, estructuras y algoritmos",
    "test_notaciones.py": "Convertidor de notaciones y tabla de direcciones",
    "test_optimizador.py": "Cada técnica, costos y 300 programas al azar",
    "test_codigo_objeto.py": "Ensamblador con GCC, convenciones de llamada y asignación de registros",
    "test_fotos.py": "Reporte de la calibración con fotos",
    "test_web.py": "Puente web: rutina completa, alarmas y ritmo fijo",
    "test_servidor.py": "Servidor: cuentas, roles, sesiones y seguridad",
}
tabla([["Archivo", "Qué revisa", "Pruebas"]] +
      [[n, DESCR.get(n, ""), k] for n, k in PRUEBAS.items()] + [["Total", "", TOTAL_PRUEBAS]],
      [4, 8.5, 1.5], codigo_en=(0,))
p("Fuera de Python hay dos pruebas más: " + c("web/pruebas/metricas.test.mjs") + " compara las métricas de "
  "JavaScript con las de Python, y " + c("web/pruebas/navegador.py") + " hace la prueba de punta a punta en Chromium.")

# ================================================================== 7
titulo("7. Manual de usuario")
subtitulo("7.1 Instalación")
numerada([
    "Descargar el proyecto: " + c("git clone https://github.com/n1erik4/EmoLang.git") + ".",
    "Crear el entorno con Python 3.11 (MediaPipe no funciona con versiones más nuevas). En Windows: "
    + c("py -3.11 -m venv .venv") + "; en Linux, con uv: " + c("uv venv --python 3.11 .venv") + ".",
    "Instalar las dependencias: " + c("pip install -r requirements.txt") + " dentro del entorno.",
    "Para el código objeto, GCC: en Windows, MSYS2 con " + c("pacman -S mingw-w64-ucrt-x86_64-gcc") +
    "; en Linux suele venir instalado.",
])
subtitulo("7.2 Comandos nuevos")
tabla([
    ["Comando", "Qué hace"],
    ["ensamblador programa.emo", "Genera programa.asm para la plataforma de la computadora"],
    ["  --correr", "Además lo ensambla con gcc y lo ejecuta"],
    ["  --registros", "Muestra la asignación de registros de cada función"],
    ["  --plataforma windows|linux", "Genera para la otra plataforma"],
    ["  --sin-optimizar / --sin-registros", "Para comparar contra la versión completa"],
    ["fotos descargar|analizar|galeria|reporte CARPETA", "Calibración con fotos (sección 3)"],
], [6, 8], codigo_en=(0,))
subtitulo("7.3 Aplicación web")
listado("python3 web/servidor.py --https-local\n"
        "  En esta computadora:  http://localhost:8000\n"
        "  Celular o tablet:     https://192.168.0.104:8443   (misma red Wi-Fi)",
        "Arranque del servidor en la laptop")
numerada([
    "Conectar el celular o la tablet a la misma red Wi-Fi que la laptop y abrir la dirección https que muestra el "
    "servidor. La primera vez, aceptar la advertencia del navegador («Configuración avanzada» → «Continuar»).",
    "Crear una cuenta, elegir el rol (terapia o conductor) y aceptar el aviso de privacidad.",
    "Tocar «Comenzar», dar permiso a la cámara y mirar al frente unos segundos para calibrar.",
    "Subir el volumen de contenido del teléfono para escuchar la guía por voz y las alarmas.",
])

# ================================================================== 8
titulo("8. Lo que falta")
vinetas([
    "Ejecutar el código objeto en una computadora con Windows y MSYS2.",
    "Carpeta " + c("tests/semantic") + " con un archivo por tipo de error semántico, como pide la rúbrica.",
    "Limpiar las fotos de sonrisa en la galería y grabar al equipo haciendo el ejercicio de cejas para fijar sus umbrales.",
    "Evaluación con participantes, con consentimiento informado y sin guardar video.",
    "Unir la rama de trabajo con la rama principal del repositorio para el portafolio.",
    "Ensayo de la demostración en vivo.",
])

# ================================================================== GLOSARIO
titulo("Glosario")
tabla([
    ["Término", "Significado"],
    ["Código objeto", "Las instrucciones del procesador que produce el compilador; aquí, un archivo .asm."],
    ["Convención de llamadas", "Reglas de cada sistema para pasar datos a una función y recibir su resultado."],
    ["Intervalo de vida", "Tramo del programa en el que una variable todavía se va a leer."],
    ["Linear scan", "Algoritmo que reparte los registros recorriendo los intervalos de vida en orden."],
    ["Marco de pila", "Espacio de memoria que aparta una llamada a función para sus datos."],
    ["Pyodide", "Python compilado para ejecutarse dentro del navegador."],
    ["HTTPS", "Conexión cifrada; los navegadores la exigen para usar la cámara desde otro dispositivo."],
    ["Certificado autofirmado", "Credencial HTTPS creada por el propio equipo; el navegador avisa la primera vez."],
    ["Sensibilidad", "De los casos que sí muestran el gesto, cuántos se detectaron."],
    ["Especificidad", "De los casos que no muestran el gesto, cuántos no dieron falsa alarma."],
    ["Desbordamiento", "Cuando un número no cabe en los 64 bits de un registro."],
], [3.5, 10])

titulo("Referencias")
for r_txt in [
    "Aho, A. V., Lam, M. S., Sethi, R. y Ullman, J. D. (2008). <i>Compiladores: principios, técnicas y herramientas</i> (2.ª ed.). Pearson Educación.",
    "Poletto, M. y Sarkar, V. (1999). Linear scan register allocation. <i>ACM Transactions on Programming Languages and Systems</i>, 21(5), 895-913.",
    "Matz, M., Hubička, J., Jaeger, A. y Mitchell, M. <i>System V Application Binary Interface: AMD64 Architecture Processor Supplement</i>.",
    "Microsoft. x64 calling convention. Documentación de Microsoft Learn.",
    "Song, F., Tan, X., Liu, X. y Chen, S. (2014). Eyes closeness detection from still images with multi-scale histograms of principal oriented gradients. <i>Pattern Recognition</i>, 47(9), 2825-2838.",
    "Lugaresi, C. et al. (2019). MediaPipe: A framework for building perception pipelines. arXiv:1906.08172.",
    "Proyecto Pyodide. Documentación oficial de Pyodide.",
    "WordPress Foundation. Openverse: búsqueda de obras con licencia abierta.",
    "Cámara de Diputados del H. Congreso de la Unión (2025). <i>Ley Federal de Protección de Datos Personales en Posesión de los Particulares</i>. Diario Oficial de la Federación, 20 de marzo de 2025.",
]:
    historia.append(Paragraph(r_txt, lista, bulletText="•"))

doc = Documento(SALIDA, pagesize=letter, leftMargin=2.5 * cm, rightMargin=2.5 * cm, topMargin=2.3 * cm,
                bottomMargin=2.3 * cm, title="EmoLang: Fase 3, código objeto, calibración y aplicación web",
                author="Equipo EmoLang, Grupo 7SB")
doc.multiBuild(historia, onFirstPage=lambda ca, d: None, onLaterPages=numero_pagina)
shutil.rmtree(TMP, ignore_errors=True)
print(SALIDA)
