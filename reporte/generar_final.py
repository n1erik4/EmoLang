"""Genera reporte/EmoLang_Reporte_Final.pdf: documentación técnica final del compilador.

Sigue la rúbrica del reporte final:
    a. Especificación formal del lenguaje (GLC con acciones semánticas, juego de
       instrucciones y notación de código intermedio).
    b. Manual de arquitectura e implementación.
    c. Manual de usuario y compilación.
    d. Suite de pruebas y casos de estudio (tests/semantic, tests/intermediate y
       tests/execution).

Las tablas de símbolos, la pila semántica, las cuádruplas, los costos de optimización,
el ensamblador, los resultados con GCC, los comandos de la CLI y el conteo de pruebas
se calculan al momento con el compilador real.

Uso (desde la raíz del proyecto, con gcc instalado):
    .venv/bin/python reporte/generar_final.py
"""

import argparse
import collections
import glob
import os
import re
import shutil
import sys
import tempfile
import unittest

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from PIL import Image as PILImage  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted,  # noqa: E402
                                SimpleDocTemplate, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents  # noqa: E402
from xml.sax.saxutils import escape  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from emolang import __main__ as CLI  # noqa: E402
from emolang import codigo_objeto as CO  # noqa: E402
from emolang.compilador import compilar_archivo  # noqa: E402
from emolang.costos import comparar  # noqa: E402
from emolang.direcciones import construir as construir_direcciones  # noqa: E402
from emolang.intermedio import PROGRAMA, resolver  # noqa: E402
from emolang.notaciones import convertir  # noqa: E402
from emolang import nodos as N  # noqa: E402
from emolang.automatas import texto_expr  # noqa: E402

FIG = os.path.join(AQUI, "figuras")
SALIDA = os.path.join(AQUI, "EmoLang_Reporte_Final.pdf")
ANCHO = letter[0] - 5 * cm - 12


# ------------------------------------------------------------------ fuentes y estilos
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
portada = ParagraphStyle("portada", fontName="Arial", fontSize=12, leading=16, alignment=TA_CENTER)
portada_b = ParagraphStyle("portada_b", parent=portada, fontName="Arial-B")

historia = []


def c(texto):
    return f'<font name="Consolas" size="9.6">{escape(str(texto))}</font>'


def p(texto):
    historia.append(Paragraph(texto, cuerpo))


def titulo(texto, nueva_pagina=False):
    if nueva_pagina:
        historia.append(PageBreak())
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
    """Explicación breve al inicio de una sección, como un párrafo normal del texto."""
    p(texto)


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


MAX_COLUMNAS = 92     # caracteres de Consolas 7.9 que caben en el ancho del texto


def _partir(linea):
    """Corta una línea larga de código en un «; » o un espacio, con sangría de continuación."""
    if len(linea) <= MAX_COLUMNAS:
        return [linea]
    etiqueta = re.match(r"\s*(?:verifica|genera):\s+", linea)          # esquema de traducción
    comentario = re.match(r"[^#]*?\s{2,}#\s", linea)                    # «código   # comentario»
    if etiqueta:
        n = len(etiqueta.group(0))
    elif comentario:
        n = len(comentario.group(0))
    else:
        n = len(linea) - len(linea.lstrip()) + 4
    sangria = " " * min(n, 40)
    partes, resto = [], linea
    while len(resto) > MAX_COLUMNAS:
        corte = resto.rfind("; ", 0, MAX_COLUMNAS)
        corte = corte + 1 if corte > len(sangria) + 10 else resto.rfind(" ", 0, MAX_COLUMNAS)
        if corte <= len(sangria):
            break
        partes.append(resto[:corte].rstrip())
        resto = sangria + resto[corte:].lstrip()
    return partes + [resto]


def listado(texto, rotulo=None):
    lineas = [x for l in texto.rstrip("\n").split("\n") for x in _partir(l)]
    def recuadro(filas, arriba, abajo):
        t = Table([[Preformatted(l or "\u00a0", codigo)] for l in filas], colWidths=[ANCHO])
        estilo = [("LINEBEFORE", (0, 0), (0, -1), 0.5, "black"), ("LINEAFTER", (-1, 0), (-1, -1), 0.5, "black"),
                  ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
        if arriba:
            estilo.append(("LINEABOVE", (0, 0), (-1, 0), 0.5, "black"))
        if abajo:
            estilo.append(("LINEBELOW", (0, -1), (-1, -1), 0.5, "black"))
        t.setStyle(TableStyle(estilo))
        return t

    # Un listado largo no se mueve completo a la página siguiente: el rótulo se queda con sus
    # primeras líneas y el resto continúa en las páginas que haga falta.
    corte = 6 if len(lineas) > 30 else len(lineas)
    inicio = ([Paragraph(rotulo, pie)] if rotulo else []) + [recuadro(lineas[:corte], True, corte == len(lineas))]
    historia.append(KeepTogether(_con_titulo(inicio)))
    if corte < len(lineas):
        historia.append(recuadro(lineas[corte:], False, True))
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


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def numerar(texto):
    return "\n".join(f"{i:02d} {l}" for i, l in enumerate(texto.rstrip("\n").splitlines(), 1))


def tabla_cuadruplas(cuads, rotulo=None):
    filas = [["#", "Operador", "Arg1", "Arg2", "Resultado"]]
    for i, q in enumerate(resolver(cuads), 1):
        filas.append([i, *q.fila()])
    tabla(filas, [0.7, 1.4, 3.2, 2.2, 2.8], codigo_en=(1, 2, 3, 4), rotulo=rotulo, juntar=len(filas) < 24)


# ================================================================== DATOS REALES
print("Calculando datos del compilador…")
HAY_GCC = shutil.which("gcc") is not None
TMP = tempfile.mkdtemp(prefix="emolang_reporte_")


def correr_asm(co):
    asm = os.path.join(TMP, "p.asm")
    exe = os.path.join(TMP, "p")
    with open(asm, "w", encoding="utf-8") as f:
        f.write(co.asm)
    ok, msg = CO.ensamblar(asm, exe)
    if not ok:
        return None, msg
    return CO.ejecutar(exe)


def funcion_asm(asm, etiqueta):
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


# --- suite de pruebas por carpeta
SEMANTICAS = []
for ruta in sorted(glob.glob("tests/semantic/*.emo")):
    r = compilar_archivo(ruta)
    errores = r.reporte.errores
    fases = collections.Counter(d.fase for d in errores)
    marcadas = sum("// error:" in l for l in leer(ruta).splitlines())
    SEMANTICAS.append((os.path.basename(ruta), len(errores), marcadas, len(r.reporte.advertencias), fases,
                       r.cuadruplas is None))

INTERMEDIAS = []
for ruta in sorted(glob.glob("tests/intermediate/*.emo")):
    r = compilar_archivo(ruta)
    antes, despues = comparar(r, repeticiones=3)
    INTERMEDIAS.append((os.path.basename(ruta), antes, despues, r.informes[PROGRAMA].aplicaciones))

EJECUCION = []
MNEMONICOS = collections.Counter()
for ruta in sorted(glob.glob("tests/execution/*.emo") + glob.glob("tests/intermediate/*.emo")):
    r = compilar_archivo(ruta)
    esperado = leer(ruta[:-4] + ".esperado")
    co = CO.generar(r.optimizado[PROGRAMA], r.analisis, "linux")
    for l in co.asm.split("\n"):
        m = re.match(r"    ([a-z][a-z0-9]*)\b", l)
        if m:
            MNEMONICOS[m.group(1)] += 1
    iguales = 0
    if HAY_GCC:
        for opt in (True, False):
            for reg in (True, False):
                v = CO.generar((r.optimizado if opt else r.cuadruplas)[PROGRAMA], r.analisis, "linux", reg)
                cod, salida = correr_asm(v)
                iguales += salida == esperado and cod == 0
    EJECUCION.append((os.path.relpath(ruta, "tests"), co.instrucciones, len(esperado.splitlines()), iguales))


def contar_pruebas():
    cargador = unittest.TestLoader()
    conteo = {}
    for ruta in sorted(glob.glob("tests/test_*.py")):
        modulo = "tests." + os.path.basename(ruta)[:-3]
        conteo[os.path.basename(ruta)] = cargador.loadTestsFromName(modulo).countTestCases()
    return conteo


PRUEBAS = contar_pruebas()
TOTAL_PRUEBAS = sum(PRUEBAS.values())


# --- comandos de la CLI, tomados del analizador de argumentos real
class _Capturado(Exception):
    pass


def comandos_cli():
    original = argparse.ArgumentParser.parse_args

    def capturar(self, *a, **k):
        raise _Capturado(self)
    argparse.ArgumentParser.parse_args = capturar
    try:
        CLI.main([])
    except _Capturado as e:
        parser = e.args[0]
    finally:
        argparse.ArgumentParser.parse_args = original
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    ayudas = {a.dest: a.help for a in sub._choices_actions}
    salida = []
    for nombre, sp in sub.choices.items():
        posicionales, opciones = [], []
        for a in sp._actions:
            if isinstance(a, argparse._HelpAction):
                continue
            if a.option_strings:
                nombre_opc = max(a.option_strings, key=len)
                if a.choices:
                    nombre_opc += " {" + "|".join(a.choices) + "}"
                elif a.nargs != 0:
                    nombre_opc += " " + a.dest.upper()
                opciones.append((nombre_opc, a.help or ""))
            else:
                posicionales.append(a.dest if not a.choices else "{" + "|".join(a.choices) + "}")
        salida.append((nombre, ayudas[nombre], posicionales, opciones))
    return salida


COMANDOS = comandos_cli()

# --- programas de ejemplo usados en el texto
R_CALC = compilar_archivo("tests/execution/calculadora.emo")
R_FACT = compilar_archivo("tests/execution/factorial.emo")
CO_FACT = CO.generar(R_FACT.optimizado[PROGRAMA], R_FACT.analisis, "linux")
R_CICLOS = compilar_archivo("tests/intermediate/ciclos_anidados.emo")
FUENTE_CICLOS = leer("tests/intermediate/ciclos_anidados.emo")
LINEA_TRAZA = next(i for i, l in enumerate(FUENTE_CICLOS.splitlines(), 1) if "total = total +" in l)
TRAZA = R_CICLOS.cuadruplas[PROGRAMA].trazas[LINEA_TRAZA]
DIRS_FACT = construir_direcciones(R_FACT.optimizado[PROGRAMA])
R_TIPOS = compilar_archivo("tests/execution/tipos_y_textos.emo")
DIRS_TIPOS = construir_direcciones(R_TIPOS.optimizado[PROGRAMA])


# --- una misma expresión en las cuatro representaciones intermedias del curso
def _buscar_asignacion(x, linea):
    if isinstance(x, N.Asignacion) and x.linea == linea:
        return x
    hijos = x if isinstance(x, list) else (vars(x).values() if isinstance(x, N.Nodo) else [])
    for h in hijos:
        if isinstance(h, (list, N.Nodo)):
            r = _buscar_asignacion(h, linea)
            if r:
                return r
    return None


ASIG = _buscar_asignacion(R_CICLOS.ast.funciones, LINEA_TRAZA)
EXPR_TXT = texto_expr(ASIG.valor)
NOTAC = convertir(EXPR_TXT)
CUADS_EXPR = [q for q in resolver(R_CICLOS.cuadruplas[PROGRAMA].bloques["funcion.suma_tabla"])
              if q.linea == LINEA_TRAZA]


def _corto(x):
    """suma_tabla.total@1 → total, para que las representaciones se lean igual."""
    t = str(x)
    return re.sub(r"^suma_tabla\.([a-z_]+)(@\d+)?$", r"\1", t)


TRIPLOS, _pos = [], {}
for q in CUADS_EXPR:
    arg = lambda v: f"({_pos[v]})" if v in _pos else _corto(v)  # noqa: E731
    if q.op == "=":
        TRIPLOS.append(("=", _corto(q.res), arg(q.a1)))
    else:
        TRIPLOS.append((q.op, arg(q.a1), arg(q.a2)))
        _pos[q.res] = len(TRIPLOS) - 1
CODIGO_P = []
for s in NOTAC["postfija"].split():
    if s in "+-*/":
        CODIGO_P.append({"+": "ADI", "-": "SBI", "*": "MPI", "/": "DVR"}[s])
    elif s.isdigit():
        CODIGO_P.append(f"LDC {s}")
    else:
        CODIGO_P.append(f"LOD {s}")
CODIGO_P.append(f"STO {ASIG.nombre}")


def figura_arbol(e):
    """Árbol de expresión real con el tipo que le asignó el analizador semántico."""
    plt.rcParams.update({"font.family": "Liberation Sans"})
    pos, cont = [], [0]

    def etiqueta(n):
        if isinstance(n, N.Binaria):
            return n.op, [n.izq, n.der]
        if isinstance(n, N.Unaria):
            return n.op, [n.operando]
        return texto_expr(n), []

    def ubicar(n, nivel):
        et, hijos = etiqueta(n)
        xs = [ubicar(h, nivel + 1) for h in hijos]
        x = sum(xs) / len(xs) if xs else cont[0]
        if not xs:
            cont[0] += 1
        pos.append((n, et, x, nivel, hijos))
        return x

    ubicar(e, 0)
    niveles = max(q[3] for q in pos)
    fig, ax = plt.subplots(figsize=(5.2, 0.85 * (niveles + 1)))
    xde = {id(q[0]): q[2] * 1.7 for q in pos}
    w, h = 1.45, 0.88
    for n, et, x, nivel, hijos in pos:
        px, py = x * 1.7, -nivel * 1.35
        for hj in hijos:
            nh = next(q[3] for q in pos if q[0] is hj)
            ax.plot([px, xde[id(hj)]], [py - h / 2, -nh * 1.35 + h / 2], color="black", lw=0.6)
        ax.add_patch(FancyBboxPatch((px - w / 2, py - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.08",
                                    fill=False, lw=1.3 if nivel == 0 else 0.7))
        ax.text(px, py + 0.19, et, ha="center", va="center", fontsize=9.5, fontweight="bold")
        ax.text(px, py - 0.2, n.tipo, ha="center", va="center", fontsize=8)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.autoscale_view()
    ruta = os.path.join(FIG, "fig_final_arbol.png")
    fig.savefig(ruta, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return ruta
print(f"  {len(SEMANTICAS)} semánticas, {len(INTERMEDIAS)} intermedias, {len(EJECUCION)} en ensamblador, "
      f"{TOTAL_PRUEBAS} pruebas")


# ================================================================== FIGURA: diagrama de bloques
def figura_bloques():
    plt.rcParams.update({"font.family": "Liberation Sans", "font.size": 7})
    fig, ax = plt.subplots(figsize=(7.0, 8.4))
    ax.set_xlim(0, 14)
    ax.set_ylim(1.2, 17)
    ax.axis("off")

    def caja(x, y, w, h, tit, det="", grueso=0.8, punteada=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.12", fill=False,
                                    lw=grueso, color="black", ls="--" if punteada else "-"))
        if det:
            ax.text(x + w / 2, y + h * 0.66, tit, fontsize=7.8, fontweight="bold", ha="center", va="center")
            ax.text(x + w / 2, y + h * 0.3, det, fontsize=6.5, ha="center", va="center")
        else:
            ax.text(x + w / 2, y + h / 2, tit, fontsize=7.6, ha="center", va="center")
        return (x, y, w, h)

    def flecha(a, b, punteada=False, texto=None, lado="der"):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=8, lw=0.7, color="black",
                                     ls=(0, (3, 2)) if punteada else "-"))
        if texto:
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            ax.text(mx + (0.12 if lado == "der" else -0.12), my, texto, fontsize=6.2,
                    ha="left" if lado == "der" else "right", va="center", style="italic")

    X, W, H = 4.6, 4.8, 1.05
    fases = [
        ("Programa fuente (.emo)", ""),
        ("Analizador léxico", "lexico.py · AFD, lexema más largo"),
        ("Analizador sintáctico", "sintactico.py · descendente recursivo"),
        ("Analizador semántico", "semantico.py · ámbitos y tipos"),
        ("Validaciones del dominio", "validaciones.py · intervalos y grafos"),
        ("Código intermedio", "intermedio.py · cuádruplas"),
        ("Optimizador", "optimizador.py · locales, ciclos, globales"),
    ]
    etiquetas = [None, "tokens", "AST", "AST con tipos", "AST validado", "cuádruplas"]
    ys = []
    y = 15.6
    for i, (t, d) in enumerate(fases):
        alto = 0.75 if i == 0 else H
        caja(X, y, W, alto, t, d, grueso=1.4 if t in ("Analizador semántico", "Código intermedio",
                                                       "Optimizador") else 0.8)
        ys.append((y, alto))
        y -= alto + 0.62
    for i in range(len(fases) - 1):
        y0, a0 = ys[i]
        y1, a1 = ys[i + 1]
        flecha((X + W / 2, y0), (X + W / 2, y1 + a1), texto=etiquetas[i])

    # salidas: EmoVM y código objeto
    y_opt = ys[-1][0]
    yb = y_opt - 2.0
    izq = caja(0.4, yb, 5.6, 1.25, "Generador de .emoc", "emoc.py · autómatas y despacho")
    der = caja(8.0, yb, 5.6, 1.25, "Código objeto", "codigo_objeto.py · registros y x86-64")
    flecha((X + 1.2, y_opt), (3.2, yb + 1.25), texto="cuádruplas optimizadas", lado="izq")
    flecha((X + W - 1.2, y_opt), (10.8, yb + 1.25))
    yc = yb - 1.75
    caja(0.4, yc, 5.6, 1.15, "EmoVM", "vm.py · cámara y programas con dominio")
    caja(8.0, yc, 5.6, 1.15, "GCC (ensamblador y enlazador)", ".asm → ejecutable nativo")
    flecha((3.2, yb), (3.2, yc + 1.15), texto=".emoc")
    flecha((10.8, yb), (10.8, yc + 1.15), texto=".asm")

    # estructuras compartidas
    ts = caja(0.2, 9.0, 3.6, 1.6, "Tabla de símbolos", "Ambito → Simbolo\nfunciones y estructuras")
    ps = caja(0.2, 6.35, 3.6, 1.25, "Pila semántica", "(lugar, tipo)")
    er = caja(10.2, 11.3, 3.6, 2.4, "Registro de errores", "Reporte → Diagnostico\nfase, nivel, línea,\ncolumna y mensaje")
    y_sem, a_sem = ys[3]
    y_val, a_val = ys[4]
    y_int, a_int = ys[5]
    flecha((X, y_sem + a_sem / 2), (3.8, 10.2), punteada=True)
    flecha((X, y_val + a_val / 2), (3.8, 9.5), punteada=True)
    flecha((3.8, 9.15), (X, y_int + a_int * 0.75), punteada=True)
    flecha((X, y_int + a_int * 0.3), (3.8, 7.0), punteada=True)
    for k in (1, 2, 3, 4):
        yk, ak = ys[k]
        flecha((X + W, yk + ak / 2), (10.2, 11.5 + (4 - k) * 0.55), punteada=True)
    td = caja(10.2, y_opt, 3.6, 1.05, "Tabla de direcciones", "datos, literales y marcos")
    flecha((12.4, yb + 1.25), (12.4, y_opt), punteada=True)
    ax.text(0.2, yc - 0.55, "Línea continua: flujo del programa.   Línea punteada: consulta o registro en una estructura de datos.",
            fontsize=6.4, ha="left", va="center")
    ruta = os.path.join(FIG, "fig_final_bloques.png")
    fig.savefig(ruta, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return ruta


# ================================================================== PORTADA
historia.append(Image(os.path.join(FIG, "logo_tecnm.png"), width=4.3 * cm, height=4.3 * cm * 118 / 192, hAlign="LEFT"))
historia.append(Spacer(1, 0.7 * cm))
for texto, estilo, despues in [
    ("TECNOLÓGICO NACIONAL DE MÉXICO", ParagraphStyle("pt", parent=portada_b, fontSize=14.5), 4),
    ("INSTITUTO TECNOLÓGICO DE OAXACA", portada_b, 20),
    ("MATERIA:", portada, 2), ("LENGUAJES Y AUTÓMATAS II", portada_b, 14),
    ("CLAVE DE MATERIA:", portada, 2), ("SCD1016", portada_b, 14),
    ("CARRERA:", portada_b, 2), ("INGENIERÍA EN SISTEMAS COMPUTACIONALES", portada, 22),
    ("PROYECTO INTEGRADOR – REPORTE FINAL: DOCUMENTACIÓN TÉCNICA DEL COMPILADOR", portada_b, 4),
    ("EmoLang", ParagraphStyle("pn", parent=portada_b, fontSize=19, leading=24), 4),
    ("Lenguaje de dominio específico para el análisis de expresiones faciales", portada, 22),
    ("ALUMNOS:", portada_b, 8),
    ("GARCIA GABRIEL BETSAIDA<br/>GINER COACHE NIERIKA<br/>JIMENEZ LOPEZ FERNANDO ARATH<br/>"
     "LEÓN RAMÍREZ CARLOS PAVEL<br/>ORTIZ MARTÍNEZ JOSÉ JULIÁN", portada, 20),
    ("NOMBRE DE LA PROFESORA:", portada_b, 4), ("VELAZQUEZ HERNANDEZ MARICARMEN MONTSERRAT", portada, 12),
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
p("EmoLang es un lenguaje de dominio específico para describir, en pocas líneas, cómo reaccionar a las "
  "expresiones faciales que capta una cámara: detectar un microsueño al conducir o contar las repeticiones de "
  "un ejercicio de terapia facial. A lo largo del semestre se construyó su compilador completo, desde el análisis "
  "léxico hasta la generación de código objeto x86-64, junto con una máquina virtual (EmoVM) que ejecuta los "
  "programas con cámara en tiempo real.")
p("Este documento es la documentación técnica final del compilador. Reúne en un solo lugar el marco teórico y "
  "las decisiones de implementación que en los reportes de las fases 2 y 3 se presentaron por separado, y lo "
  "actualiza al estado final del código. Todos los ejemplos, tablas y conteos se generaron directamente con el "
  "compilador al momento de armar este reporte, así que corresponden exactamente a la versión entregada.")
subtitulo("1.1 Objetivo")
p("<b>Objetivo del proyecto integrador:</b> implementar un compilador para un lenguaje específico considerando "
  "todas sus etapas. El lenguaje específico es EmoLang y el compilador recorre las etapas de análisis léxico, "
  "sintáctico y semántico, generación de código intermedio, optimización y generación de código objeto para la "
  "arquitectura x86-64.")
subtitulo("1.2 Alcance del prototipo")
p("Un programa EmoLang tiene dos tipos de contenido, que pueden convivir en el mismo archivo:")
vinetas([
    "<b>Dominios</b> (" + c("dominio conduccion { … }") + "): sensores, gestos con duración, secuencias de gestos y "
    "máquinas de estado. Se compilan a autómatas finitos y cuádruplas, y los ejecuta EmoVM cuadro por cuadro con "
    "la cámara.",
    "<b>Programas de propósito general</b> (" + c("funcion principal() { … }") + "): funciones recursivas, ciclos, "
    "arreglos, estructuras y decimales. Además de EmoVM, se traducen a ensamblador x86-64, se ensamblan con GCC y "
    "se ejecutan como programas nativos en Linux y Windows.",
])
p("Los archivos fuente usan la extensión " + c(".emo") + ". El compilador está escrito en Python 3 sin "
  "generadores de analizadores: el léxico es un AFD escrito a mano y el sintáctico es descendente recursivo.")

# ================================================================== 2
titulo("2. Marco teórico y conceptual", nueva_pagina=True)
p("Esta sección reúne los conceptos de la teoría de compiladores en los que se apoya la implementación. Cada "
  "concepto se relaciona con el lugar del compilador de EmoLang donde se aplica.")
subtitulo("2.1 Gramáticas libres de contexto")
p("Una gramática libre de contexto es una cuádrupla G = (N, T, P, S), donde N es el conjunto de símbolos no "
  "terminales, T el de terminales (los componentes léxicos), P el conjunto de producciones de la forma A → α, "
  "donde A es un no terminal y α una cadena de terminales y no terminales, y S el símbolo inicial. Un programa es válido si existe una "
  "derivación de S hasta la cadena de tokens del programa; esa derivación se representa con un árbol de "
  "derivación. Las gramáticas libres de contexto ocupan el tipo 2 de la jerarquía de Chomsky: describen "
  "estructuras anidadas, como bloques y paréntesis, que una expresión regular no puede describir. Por eso el "
  "análisis léxico usa un autómata finito determinista y el sintáctico una gramática libre de contexto "
  "(Aho et al., 2008).")
p("Una gramática es <b>LL(1)</b> cuando, para elegir la producción que se aplica, basta con ver el siguiente "
  "token. Esto permite un <b>analizador descendente recursivo</b>: una función por cada no terminal, que llama a "
  "las funciones de los símbolos de su producción. Para lograrlo la gramática no debe ser ambigua ni tener "
  "recursión por la izquierda; la precedencia de los operadores se expresa con un no terminal por nivel. La "
  "gramática de EmoLang (sección 4.2) cumple estas condiciones salvo en un punto, que se resuelve viendo un "
  "token más.")

subtitulo("2.2 Fundamentos del análisis semántico")
p("<b>Reglas semánticas dirigidas por la sintaxis.</b> Una definición dirigida por la sintaxis asocia atributos "
  "a los símbolos de la gramática y reglas semánticas a las producciones. Un atributo es <i>sintetizado</i> si se "
  "calcula a partir de los hijos de un nodo (por ejemplo, el tipo de " + c("a + b") + " se calcula a partir de "
  "los tipos de a y b) y es <i>heredado</i> si se recibe del padre o de los hermanos (por ejemplo, el ámbito en el "
  "que se declara una variable). Cuando las acciones se escriben dentro de las producciones, en el punto donde se "
  "ejecutan, la definición se llama <b>esquema de traducción</b>. En EmoLang, " + c(".tipo") + " y " + c(".lugar") +
  " son sintetizados y el ámbito es heredado; el esquema completo está en la sección 4.5.")
p("<b>Árboles de expresiones.</b> El analizador sintáctico no conserva el árbol de derivación completo, sino un "
  "<i>árbol de sintaxis abstracta</i>: cada operador es un nodo interno y sus operandos son sus hijos; los "
  "paréntesis y los no terminales auxiliares desaparecen porque la forma del árbol ya expresa la precedencia. "
  "Recorrer el árbol en posorden produce la notación postfija y es el orden en que se emiten las instrucciones "
  "del código intermedio. La figura muestra el árbol real que construye el compilador para la expresión de la "
  f"línea {LINEA_TRAZA} de {c('tests/intermediate/ciclos_anidados.emo')}, con el tipo que el análisis semántico "
  "le asignó a cada nodo.")
figura(figura_arbol(ASIG.valor), f"Figura 1. Árbol de expresión de {escape(EXPR_TXT)}", ancho_cm=14)
p("<b>Pila semántica.</b> Mientras se recorre el árbol, los resultados parciales se guardan en una pila: cada "
  "operando mete su lugar y su tipo, y cada operador saca los de sus operandos y mete el de su resultado. Es la "
  "misma idea de la evaluación de una expresión postfija, aplicada a la generación de código (sección 5.4).")
p("<b>Tabla de símbolos.</b> Guarda la información de cada nombre declarado (categoría, tipo, ámbito, posición) y "
  "ofrece dos operaciones: insertar y buscar. Se puede implementar con listas, árboles de búsqueda o tablas hash; "
  "para lenguajes con ámbitos anidados se usa una tabla por ámbito, encadenada a la del ámbito que la contiene, de "
  "modo que la búsqueda va del ámbito más interno al más externo (alcance estático). EmoLang usa tablas hash "
  "encadenadas (sección 5.2).")
p("<b>Tabla de direcciones.</b> Asigna a cada nombre el lugar donde vivirá al ejecutarse: una dirección fija en "
  "el segmento de datos para las variables globales y los literales, o un desplazamiento dentro del "
  "<i>registro de activación</i> (marco de pila) de una función para parámetros, variables locales y temporales "
  "(sección 5.3).")
p("<b>Comprobación de tipos.</b> Es <i>estática</i> cuando se hace al compilar y <i>dinámica</i> cuando se hace "
  "al ejecutar. Una conversión puede ser <i>implícita</i> (coerción), cuando el compilador la inserta sola, como "
  "pasar de entero a decimal, o <i>explícita</i> (casting), cuando el programador la pide. EmoLang comprueba los "
  "tipos de forma estática; solo los límites de los arreglos y la división entre cero se revisan al ejecutar "
  "(secciones 4.3 y 4.4).")

subtitulo("2.3 Estudio comparativo de las representaciones de código intermedio")
p("El código intermedio es una representación del programa independiente de la máquina destino, que facilita la "
  "optimización y la traducción final. Las cuatro representaciones estudiadas en el curso son:")
vinetas([
    "<b>Notación polaca.</b> La <i>postfija</i> (polaca inversa) escribe los operadores después de sus operandos y "
    "la <i>prefija</i> antes. No necesita paréntesis y se evalúa con una pila.",
    "<b>Código P.</b> Instrucciones de una máquina de pila hipotética, usada originalmente por el compilador "
    "Pascal-P (Nori et al., 1981): " + c("LOD") + " y " + c("LDC") + " meten una variable o una constante en la "
    "pila, las operaciones (" + c("ADI") + ", " + c("MPI") + "…) trabajan sobre el tope y " + c("STO") + " guarda el "
    "resultado.",
    "<b>Triplos.</b> Instrucciones (operador, arg1, arg2) en las que el resultado no tiene nombre: otra instrucción "
    "se refiere a él por su posición, " + c("(n)") + ".",
    "<b>Cuádruplos.</b> Instrucciones (operador, arg1, arg2, resultado) en las que cada resultado se guarda en un "
    "temporal con nombre.",
])
p(f"Para compararlas se escribe en las cuatro la misma asignación de la figura 1, {c(ASIG.nombre + ' = ' + EXPR_TXT)}. "
  "La notación polaca la produce el convertidor del compilador (comando " + c("notacion") + "), los cuádruplos son "
  "los que emite el generador real y el código P y los triplos se derivaron de ellos.")
filas = [["Notación polaca", "Código P", "Triplos", "Cuádruplos"]]
col_p = [f"Postfija:\n{NOTAC['postfija']}  {ASIG.nombre} =", "", f"Prefija:\n= {ASIG.nombre} {NOTAC['prefija']}"]
col_cp = CODIGO_P
col_t = [f"({i}) ({', '.join(t)})" for i, t in enumerate(TRIPLOS)]
col_q = [str(q) for q in CUADS_EXPR]
filas.append(["\n".join(col_p), "\n".join(col_cp), "\n".join(col_t), "\n".join(col_q)])
tabla(filas, [3.6, 2, 3.6, 4.6], codigo_en=(0, 1, 2, 3), rotulo="La misma asignación en las cuatro representaciones")
tabla([
    ["Criterio", "Notación polaca", "Código P", "Triplos", "Cuádruplos"],
    ["Tamaño", "El menor", "Pequeño", "Mediano", "El mayor (un campo más)"],
    ["Temporales con nombre", "No", "No (usa la pila)", "No (usa posiciones)", "Sí"],
    ["Saltos de si, mientras y para", "Requiere extensiones", "Sí (instrucciones de salto)", "Sí", "Sí"],
    ["Mover o quitar instrucciones al optimizar", "Difícil", "Difícil: cambia el estado de la pila",
     "Difícil: cambian las referencias (n)", "Fácil: los nombres no cambian"],
    ["Traducción a una máquina de registros", "Indirecta", "Indirecta: simula la pila",
     "Directa", "Directa: cada temporal es un registro o una dirección"],
], [3.4, 2.4, 2.6, 2.6, 3.0], rotulo="Comparación de las representaciones")
p("Los cuádruplos se eligieron porque el optimizador necesita mover y quitar instrucciones, y porque el destino "
  "final, x86-64, es una máquina de registros: cada temporal con nombre se convierte en un registro o en una "
  "dirección del marco de pila. La notación polaca se conserva como herramienta (comando " + c("notacion") + ").")

subtitulo("2.4 Técnicas y tipos de optimización de código")
p("Optimizar es transformar el código intermedio para que use menos tiempo o memoria <b>sin cambiar el resultado "
  "del programa</b>. Las técnicas se clasifican por el alcance del código que examinan:")
tabla([
    ["Tipo", "Alcance", "Técnicas representativas"],
    ["Local", "Un bloque básico: instrucciones que se ejecutan en secuencia, sin saltos hacia dentro ni hacia fuera",
     "Plegado de constantes, eliminación de subexpresiones comunes, simplificación algebraica, reducción de fuerza"],
    ["De ciclos", "El cuerpo de un ciclo, donde se ejecuta la mayor parte del tiempo",
     "Movimiento de código invariante, variables de inducción, reducción de fuerza, desenrollado"],
    ["Global", "Una función completa, con su grafo de flujo de control",
     "Propagación de constantes, eliminación de código muerto e inalcanzable"],
    ["De mirilla", "Una ventana pequeña de instrucciones consecutivas",
     "Eliminar copias redundantes, unir una operación con la asignación que la sigue, saltos a saltos"],
], [2, 5, 6.5])
p("Las técnicas globales y de ciclos se apoyan en el <b>análisis de flujo de datos</b>: se calcula, para cada punto "
  "del programa, qué definiciones lo alcanzan o qué variables siguen vivas (se leerán después), resolviendo "
  "ecuaciones sobre el grafo de flujo de control hasta llegar a un punto fijo. El mismo análisis de variables "
  "vivas sirve después para asignar registros. Para saber si una optimización conviene se miden sus "
  "<b>costos</b> antes y después: instrucciones ejecutadas, tiempo, memoria de datos, tamaño de la pila y "
  "registros necesarios (secciones 5.6 y 7.3).")

subtitulo("2.5 Arquitectura del microprocesador y administración de memoria")
p("Un microprocesador ejecuta un ciclo de búsqueda, decodificación y ejecución sobre instrucciones en "
  "<b>lenguaje máquina</b>, códigos binarios que manipulan <b>registros</b> (pequeñas memorias dentro del "
  "procesador, las más rápidas) y la memoria principal. El <b>lenguaje ensamblador</b> es su representación "
  "simbólica: cada instrucción, como " + c("add rax, rbx") + ", corresponde a una instrucción de máquina. Un "
  "ensamblador la convierte a código objeto y un enlazador la une con las bibliotecas para formar el ejecutable.")
tabla([
    ["Registros de x86-64", "Uso"],
    ["rax, rbx, rcx, rdx, rsi, rdi, r8 a r15", "16 registros de propósito general de 64 bits. Sus mitades bajas "
     "conservan los nombres de 32 bits de x86 (eax, ebx, ecx…), que menciona el planteamiento del proyecto"],
    ["rsp, rbp", "Tope de la pila y base del marco de la función actual"],
    ["rip", "Dirección de la siguiente instrucción"],
    ["rflags", "Banderas que dejan las comparaciones (cero, signo, acarreo…) y que leen los saltos condicionales"],
    ["xmm0 a xmm15", "Registros SSE2 de 128 bits para aritmética de punto flotante"],
], [4.2, 9.3], codigo_en=(0,))
p("La <b>administración de memoria en tiempo de ejecución</b> divide la memoria de un programa en segmentos: "
  "el de <b>código</b> (instrucciones, solo lectura), el de <b>datos</b> estáticos (variables globales y literales "
  "de texto, con dirección fija), la <b>pila</b> (un registro de activación por cada llamada a función, con sus "
  "parámetros, variables locales, temporales y la dirección de regreso) y el <b>montículo</b> (memoria pedida "
  "durante la ejecución). La forma de pasar argumentos y de usar la pila la fija la <b>convención de llamadas</b> "
  "de cada sistema operativo, para que funciones compiladas por separado puedan llamarse entre sí. La "
  "<b>asignación de registros</b> decide qué variables viven en registros y cuáles en memoria; uno de los "
  "algoritmos más usados es <i>linear scan</i> (Poletto y Sarkar, 1999), que es el que implementa EmoLang "
  "(sección 5.7).")

# ================================================================== 3
titulo("3. Diagnóstico y contextualización", nueva_pagina=True)
subtitulo("3.1 Marco contextual")
p("La somnolencia al volante es un factor de riesgo reconocido en los accidentes de tránsito: un conductor "
  "cansado tarda más en reaccionar y puede tener microsueños de pocos segundos sin darse cuenta. Las señales "
  "visibles, como los ojos que se cierran más tiempo de lo normal, los bostezos o la cabeza que cae, se pueden "
  "medir con una cámara frente al rostro. En otro campo, las personas con parálisis facial hacen rutinas de "
  "ejercicios (sonreír, levantar las cejas, cerrar los ojos) en las que importa contar las repeticiones y "
  "observar la simetría entre los dos lados de la cara.")
p("Los dos casos comparten el mismo problema técnico: describir gestos que duran cierto tiempo, secuencias de "
  "gestos y las reacciones del sistema ante ellos. Escribirlo directamente en un lenguaje de propósito general "
  "mezcla la lógica del problema con el manejo de la cámara, los tiempos y los estados. EmoLang separa ambas "
  "cosas: el especialista describe en pocas líneas qué gestos le interesan y cómo reaccionar, y el compilador "
  "genera los autómatas y el código que los detecta. El prototipo funciona con una cámara web común y una "
  "computadora sin tarjeta gráfica dedicada, o con el navegador de un teléfono.")
subtitulo("3.2 Marco legal")
p("El proyecto procesa imágenes del rostro de una persona, así que el marco legal principal es el de la "
  "protección de datos personales. Las consideraciones y las medidas que se tomaron son:")
tabla([
    ["Ordenamiento", "Qué implica para el proyecto", "Medida tomada"],
    ["Ley Federal de Protección de Datos Personales en Posesión de los Particulares (DOF, 20 de marzo de 2025)",
     "La imagen del rostro identifica a una persona y es un dato personal; las métricas de salud o de fatiga "
     "pueden considerarse datos sensibles, que requieren consentimiento expreso e informado y un aviso de "
     "privacidad",
     "El video se procesa dentro del dispositivo y nunca se guarda ni se envía; solo se guardan resultados "
     "numéricos. Se pide aceptar el aviso de privacidad y se registra la fecha del consentimiento. La persona "
     "puede borrar sus sesiones o su cuenta"],
    ["Ley General de Salud y regulación sanitaria de dispositivos médicos (COFEPRIS)",
     "Un programa que se ofrezca para diagnosticar o tratar a pacientes puede considerarse un dispositivo médico",
     "EmoLang es un prototipo académico: el módulo de terapia acompaña ejercicios, no diagnostica ni sustituye la "
     "indicación de un profesional de la salud"],
    ["NOM-087-SCT-2-2017, tiempos de conducción y pausas de descanso en el autotransporte federal",
     "La prevención de la fatiga en conductores profesionales se basa en limitar las horas de manejo",
     "El módulo de conducción es un apoyo que avisa de señales de somnolencia; no sustituye los descansos que "
     "fija la norma"],
    ["Ley Federal del Derecho de Autor",
     "El software es una obra protegida; las bibliotecas y fotos de terceros se usan según su licencia",
     "MediaPipe y OpenCV se usan con licencia Apache 2.0; las fotos de calibración tienen licencias abiertas y "
     "se conserva su autoría; las fotos no se incluyen en el repositorio"],
], [3.6, 4.9, 5])
p("Una evaluación con participantes requeriría además un consentimiento informado específico para la prueba, "
  "explicando qué se mide y que no se graba video.")

subtitulo("3.3 Alcance del lenguaje prototipo")
tabla([
    ["Aspecto", "Lo que admite EmoLang", "Fuera del alcance"],
    ["Tipos de datos", "int, decimal, bool, string; duracion y proporcion (con unidades ms, s y %); arreglos de "
     "tamaño fijo de tipos primitivos; estructuras con campos primitivos; gesto y secuencia en los dominios",
     "Punteros, arreglos de estructuras, arreglos dinámicos"],
    ["Constantes", "const con valor conocido al compilar", "–"],
    ["Expresiones", "Aritméticas, relacionales y lógicas con precedencia; concatenación de textos", "Operadores de bits"],
    ["Estructuras de control", "si / sino, mientras, para … hasta, repetir … veces; en los dominios, cuando, "
     "mientras por cuadro e ir_a", "switch, break, continue"],
    ["Funciones", "Parámetros por valor (arreglos y estructuras por referencia), valor de regreso, recursión; "
     "funciones predefinidas de salida, conversión y del dominio", "Funciones como valores, sobrecarga"],
    ["Alcance de variables", "Estático y anidado: global, programa, función, bloque; en los dominios, dominio, "
     "máquina, estado y bloque", "–"],
    ["Entrada y salida", "Salida con mostrar; entrada de la cámara en los dominios", "Lectura del teclado o de archivos"],
], [2.6, 7.2, 3.7])

subtitulo("3.4 Plataforma de destino")
tabla([
    ["Opción", "A favor", "En contra", "Decisión"],
    ["Simulador de microprocesador (por ejemplo, de 8086 o MIPS)", "Permite ver registros y memoria paso a paso",
     "No puede usar la cámara ni las bibliotecas de C; los programas no corren fuera del simulador", "Descartada"],
    ["x86-64 real (Linux y Windows) con GCC", "Programas nativos en las computadoras del equipo; printf y malloc "
     "de la biblioteca de C; GDB para depurar", "Dos convenciones de llamada que atender", "Elegida para el código objeto"],
    ["Máquina virtual propia (EmoVM)", "Ejecuta los autómatas con la cámara cuadro por cuadro",
     "No es código máquina", "Se conserva para los dominios"],
], [3.3, 3.9, 4.2, 2.2])
p("El destino del código objeto es <b>x86-64</b>, en sintaxis Intel del ensamblador GNU, ejecutado directamente "
  "sobre el procesador de la computadora: es el «entorno de hardware objetivo» de las pruebas de la sección 7.4. "
  "Los programas con dominio siguen en EmoVM, porque dependen de la cámara y de autómatas que avanzan con cada "
  "cuadro de video.")

subtitulo("3.5 Herramientas de desarrollo")
tabla([
    ["Herramienta", "Uso"],
    ["Python 3.11", "Lenguaje de construcción del compilador, de EmoVM y del servidor web"],
    ["Analizadores escritos a mano", "Léxico (AFD) y sintáctico (descendente recursivo), sin generadores como PLY "
     "o ANTLR, para controlar los mensajes de error y poder explicar cada fase"],
    ["GCC y el ensamblador GNU (as)", "Ensamblar y enlazar el código objeto; MinGW-w64 de MSYS2 en Windows"],
    ["unittest", "Suite de pruebas automáticas"],
    ["MediaPipe Face Landmarker y OpenCV", "Puntos del rostro y captura de la cámara"],
    ["Pyodide", "Ejecutar el mismo compilador dentro del navegador"],
    ["Git y GitHub", "Control de versiones y portafolio del proyecto"],
], [4.2, 9.3])

# ================================================================== 4
titulo("4. Especificación formal del lenguaje", nueva_pagina=True)
simple("Esta sección es el «reglamento» de EmoLang: qué palabras existen, cómo se pueden combinar (la gramática), "
       "qué revisa el compilador en cada combinación y qué instrucciones produce para cada una.")
subtitulo("4.1 Componentes léxicos")
tabla([
    ["Token", "Patrón", "Ejemplos"],
    ["Palabras reservadas", "Lista fija (ver abajo)", "funcion, si, para, gesto"],
    ["ID", "[a-zA-Z_][a-zA-Z0-9_]* que no sea palabra reservada", "umbral_ojo, total, Punto"],
    ["ENTERO", "[0-9]+", "30"],
    ["DECIMAL", "[0-9]+ . [0-9]+", "0.21"],
    ["Unidades", "ms, s y %, pegadas o separadas del número", "500ms, 1.5 s, 60%"],
    ["CADENA", "Texto entre comillas dobles en una línea; escapes \\n \\t \\\" \\\\", '"¡Despierte!"'],
    ["Relacionales", "&lt;  &lt;=  &gt;  &gt;=  ==  !=", "ear &lt; 0.2"],
    ["Aritméticos y asignación", "+  -  *  /  =", "total + 1"],
    ["Lógicos", "y  o  no", "a y no b"],
    ["Delimitadores", "{ } ( ) [ ] , ; : .", ""],
    ["Comentarios (se descartan)", "// hasta fin de línea y /* bloque */", "// umbrales"],
], [2.6, 5.6, 3.3])
p("<b>Palabras reservadas:</b> " + c("dominio sensor usar var const funcion retornar estructura para gesto "
  "secuencia maquina inicial estado al_entrar cuando ignorar ir_a tras durante hasta tolerando en si sino mientras "
  "repetir veces int decimal bool string duracion proporcion verdadero falso y o no ms s") + ".")
p("El analizador léxico aplica la regla del lexema más largo (" + c("<=") + " antes que " + c("<") + "). Las métricas "
  "del sensor (" + c("ear") + ", " + c("mar") + ", " + c("pitch") + "…) y las funciones predefinidas no son palabras "
  "reservadas: llegan como " + c("ID") + " y el analizador semántico las resuelve en el ámbito global.")

subtitulo("4.2 Gramática libre de contexto")
p("EmoLang se define con la gramática G = (N, T, P, S), donde S = &lt;programa&gt;, N son los símbolos entre "
  "&lt; &gt; y T son los componentes léxicos de 4.1. Se escribe en notación EBNF: " + c("X*") + " es cero o más "
  "veces, " + c("X+") + " una o más y " + c("X?") + " opcional. Son abreviaturas de producciones recursivas "
  "(por ejemplo, " + c("<decl>*") + " equivale a " + c("<decls> → <decl> <decls> | ε") + "), así que la gramática "
  "sigue siendo libre de contexto.")
listado("""\
 1 <programa>     → ( <dominio> | <funcion> | <estructura> | <decl> )+
 2 <funcion>      → funcion ID ( <params>? ) ( : <tipo> )? <bloque>
 3 <params>       → ID : <tipo> ( , ID : <tipo> )*
 4 <estructura>   → estructura ID { ( ID : <tipo> ; )* }
 5 <dominio>      → dominio ID { <miembro>* }
 6 <miembro>      → <sensor> | <decl> | <gesto> | <secuencia> | <maquina>
 7 <sensor>       → sensor ID { ( usar <ids> ; | <decl> )* }
 8 <ids>          → ID ( , ID )*
 9 <decl>         → ( var | const ) ID : <tipo> ( = <inicial> )? ;
10 <inicial>      → <expr> | [ <expr> ( , <expr> )* ]
11 <tipo>         → ( int | decimal | bool | string | duracion | proporcion
                    | gesto | secuencia | ID ) ( [ ENTERO? ] )?
12 <gesto>        → gesto ID = <expr> durante <expr> ( hasta <expr> )? ( tolerando <expr> )? ;
13 <secuencia>    → secuencia ID = [ <ids> ] ( en <expr> )? ;
14 <maquina>      → maquina ID inicial ID { <estado>+ }
15 <estado>       → estado ID { <miembro_e>* }
16 <miembro_e>    → <decl> | al_entrar <bloque>
                  | cuando ID ir_a ID ; | cuando ID <bloque>
                  | cuando tras <expr> ir_a ID ;
                  | mientras <expr> <bloque> | ignorar <ids> ;
17 <bloque>       → { <sentencia>* }
18 <sentencia>    → <decl>
                  | <destino> = <expr> ;
                  | si <expr> <bloque> ( sino ( <si> | <bloque> ) )?
                  | mientras <expr> <bloque>
                  | para ID = <expr> hasta <expr> <bloque>
                  | repetir <expr> veces <bloque>
                  | retornar <expr>? ;
                  | ir_a ID ;
                  | <llamada> ;
19 <destino>      → ID | ID [ <expr> ] | ID . ID
20 <expr>         → <conj> ( o <conj> )*
21 <conj>         → <neg> ( y <neg> )*
22 <neg>          → no <neg> | <rel>
23 <rel>          → <suma> ( ( < | <= | > | >= | == | != ) <suma> )?
24 <suma>         → <term> ( ( + | - ) <term> )*
25 <term>         → <unario> ( ( * | / ) <unario> )*
26 <unario>       → - <unario> | <primario>
27 <primario>     → ENTERO ( ms | s | % )? | DECIMAL ( ms | s | % )?
                  | CADENA | verdadero | falso
                  | ID | ID [ <expr> ] | ID . ID | <llamada> | ( <expr> )
28 <llamada>      → ID ( ( <expr> ( , <expr> )* )? )""", "Producciones P de G")
p("Las producciones 20 a 26 fijan la precedencia, de menor a mayor: " + c("o") + ", " + c("y") + ", " + c("no") +
  ", relacionales (no asociativas), " + c("+ -") + ", " + c("* /") + " y el signo. La recursión izquierda se "
  "expresa como repetición porque el analizador es descendente recursivo. La gramática es LL(1), salvo en "
  + c("<sentencia>") + " cuando empieza con " + c("ID") + ": un segundo token decide entre asignación "
  "(" + c("=") + ", " + c("[") + ", " + c(".") + ") y llamada (" + c("(") + "). Algunas restricciones no son "
  "libres de contexto y las revisa el analizador semántico, no la gramática: " + c("mientras") + " y " + c("para") +
  " como ciclos solo dentro de una función, " + c("retornar") + " solo en funciones y el tamaño de un arreglo "
  "omitido solo en parámetros.")

subtitulo("4.3 Sistema de tipos")
tabla([
    ["Tipo", "Valores", "Representación"],
    ["int", "Enteros", "64 bits con signo"],
    ["decimal", "Reales", "IEEE 754 de 64 bits"],
    ["bool", "verdadero, falso", "0 o 1"],
    ["string", "Texto", "Dirección de una cadena terminada en cero"],
    ["duracion", "Tiempo; " + c("1.5 s") + " se guarda como 1500 ms", "Decimal en milisegundos"],
    ["proporcion", "Real en [0, 1]; " + c("40%") + " se guarda como 0.4", "Decimal"],
    ["T[n]", "Arreglo de n elementos primitivos", "Longitud seguida de los elementos"],
    ["Estructura", "Campos primitivos con nombre", "Un bloque de 8 bytes por campo"],
    ["gesto, secuencia", "Patrones temporales de un dominio", "Autómata finito"],
], [2.2, 6, 4.2])
tabla([
    ["Operación", "Resultado"],
    ["int + - * int", "int"],
    ["Mezcla de int, decimal y proporcion con + - *", "decimal"],
    ["número / número", "decimal (siempre)"],
    ["duracion ± duracion;  duracion * número;  duracion / número", "duracion"],
    ["duracion / duracion", "decimal"],
    ["string + cualquier tipo", "string (concatenación)"],
    ["Relacional entre números o entre duraciones", "bool"],
    ["== y != entre dos string o dos bool", "bool"],
    ["y, o, no", "Requieren bool y devuelven bool"],
    ["Asignación int → decimal, decimal ↔ proporcion", "Permitida (ensanchamiento)"],
    ["Asignación decimal → int, número → duracion", "Error: se usa a_int() o se escribe la unidad"],
    ["Cualquier otra combinación", "Error de tipo"],
], [7.5, 5], rotulo="Reglas de tipos que aplica la función tipo_binario y la relación asignable")

subtitulo("4.4 Conversión de tipos (casting)")
p("El verificador de tipos aplica conversiones implícitas solo cuando no se pierde información. Las demás "
  "conversiones tiene que pedirlas el programador con una función de conversión explícita.")
tabla([
    ["De", "A", "Implícita", "Explícita"],
    ["int", "decimal", "Sí (ensanchamiento)", "a_decimal(x)"],
    ["decimal", "int", "No: se pierde la parte decimal", "a_int(x): quita los decimales"],
    ["decimal", "proporcion", "Sí; si el valor es constante, se revisa que esté en [0, 1]", "a_proporcion(x): 40 → 40 %"],
    ["proporcion", "decimal", "Sí", "a_porcentaje(x): 0.4 → 40.0"],
    ["número", "duracion", "No: se exige la unidad (5 s)", "Escribir la unidad: 5 s, 300 ms"],
    ["duracion", "decimal", "No", "a_ms(x) o a_s(x)"],
    ["ms", "s", "Sí: todo se normaliza a milisegundos al compilar", "–"],
    ["cualquier tipo", "string", "Solo al concatenar con + y en mostrar", "–"],
    ["bool", "número (o al revés)", "No", "–"],
], [2.4, 2.4, 4.6, 4.1], codigo_en=(3,), rotulo="Tabla de conversión implícita y explícita de tipos")
p("Al generar código, una conversión implícita no siempre produce una instrucción: de int a decimal, el código "
  "objeto emite " + c("cvtsi2sd") + "; la conversión a texto para concatenar emite la cuádrupla " + c("texto") +
  "; y entre decimal y proporcion no hace falta nada, porque se representan igual.")

subtitulo("4.5 Gramática con acciones semánticas integradas")
p("El esquema de traducción asocia a cada producción las acciones que se ejecutan al reconocerla. Los "
  "símbolos tienen los atributos " + c(".tipo") + " (tipo del valor), " + c(".lugar") + " (variable, constante o "
  "temporal que guarda el valor), " + c(".valor") + " (valor de una constante, ya convertido a milisegundos o a "
  "proporción) y " + c(".linea") + " para los mensajes. Las acciones usan estas operaciones:")
tabla([
    ["Operación", "Qué hace", "Implementación"],
    ["buscar(id)", "Busca un nombre del ámbito actual hacia afuera", "Ambito.buscar"],
    ["insertar(id, cat, tipo)", "Agrega un símbolo; error si ya existe en el ámbito actual", "Semantico._definir"],
    ["abrir_ambito() / cerrar_ambito()", "Crea un ámbito hijo del actual o regresa al padre", "Ambito(nombre, padre)"],
    ["tipo_binario(op, t1, t2)", "Tipo del resultado según 4.3, o error", "tipos.tipo_binario"],
    ["asignable(destino, origen)", "Indica si un valor de tipo origen cabe en destino", "tipos.asignable"],
    ["meter(l, t) / sacar()", "Operaciones de la pila semántica", "Generador.pila"],
    ["nuevo_temp() / nueva_etq()", "Temporal t1, t2… o etiqueta L1, L2… del bloque", "Generador._temporal"],
    ["emitir(op, a1, a2, res)", "Agrega una cuádrupla al bloque actual", "Generador._emitir"],
    ["error(msg)", "Registra un diagnóstico y el nodo queda sin tipo", "Reporte.error"],
], [4.2, 6.2, 3.6], codigo_en=(0, 2))
p("En la implementación las acciones se ejecutan en dos recorridos del árbol de sintaxis abstracta: el analizador "
  "semántico hace las verificaciones (columna «verifica») y el generador de código intermedio emite las cuádruplas "
  "(columna «genera»). Se separan porque un estado, un gesto o una función pueden nombrarse antes de declararse; "
  "aquí se presentan juntas, integradas en cada producción. Si el primer recorrido encuentra errores, el segundo "
  "no se ejecuta.")
listado("""\
<programa> → { abrir_ambito(programa) }  ( <funcion> | <estructura> | <decl> | <dominio> )+
             { para cada función f: insertar(f.id, funcion, firma(f)) antes de revisar cuerpos }

<funcion> → funcion ID ( <params> ) : <tipo> <bloque>
   verifica: insertar(ID, funcion, (params) -> <tipo>); abrir_ambito(funcion ID);
             por cada parámetro p: insertar(p.id, parametro, p.tipo);
             si <tipo> ≠ void y no siempre_retorna(<bloque>): error("debe devolver un valor en todos los caminos")
   genera:   abrir bloque funcion.ID; <bloque>; emitir(ret)

<decl> → var ID : <tipo> = <expr> ;
   verifica: si buscar_local(ID): error("ya fue declarado");
             si no asignable(<tipo>, <expr>.tipo): error("no se puede asignar …");
             si <tipo> = proporcion y <expr> es constante: revisar 0 ≤ <expr>.valor ≤ 1;
             insertar(ID, variable, <tipo>)
   genera:   si <tipo> es T[n]: emitir(alloc, n, T, ID)   sino si es estructura: emitir(alloc_e, <tipo>, –, ID)
             sino: emitir(=, <expr>.lugar, –, ID)

<decl> → const ID : <tipo> = <expr> ;
   verifica: igual que var; además <expr> debe poder calcularse al compilar;
             insertar(ID, constante, <tipo>, valor = evaluar(<expr>)); la constante no es asignable
   genera:   emitir(=, <expr>.lugar, –, ID)   (la propagación de constantes la reemplaza por su valor)

<estructura> → estructura ID { campo1 : T1 ; … ; campok : Tk ; }
   verifica: insertar(ID, estructura, ID); cada Ti primitivo; nombres de campo distintos;
             estructuras[ID] = {campo1: T1, …, campok: Tk}
   genera:   nada; la tabla de campos la usan alloc_e, campo y campo= (posición·8 bytes)

<sentencia> → ID = <expr> ;
   verifica: s = buscar(ID); si s = nulo: error("no declarado"); si s es métrica o constante: error;
             si no asignable(s.tipo, <expr>.tipo): error("tipos incompatibles")
   genera:   emitir(=, <expr>.lugar, –, ID)

<sentencia> → ID [ <expr>1 ] = <expr>2 ;
   verifica: ID debe ser arreglo; <expr>1.tipo = int; asignable(elemento(ID.tipo), <expr>2.tipo)
   genera:   emitir([]=, <expr>2.lugar, <expr>1.lugar, ID)

<sentencia> → ID . campo = <expr> ;
   verifica: ID debe ser estructura con ese campo; asignable(campo.tipo, <expr>.tipo)
   genera:   emitir(campo=, <expr>.lugar, E.campo, ID)

<suma> → <suma>1 + <term>                       (igual para -, * y /)
   verifica: <suma>.tipo = tipo_binario(+, <suma>1.tipo, <term>.tipo); si es error: error("operador no aplicable")
   genera:   (l2, t2) = sacar(); (l1, t1) = sacar(); t = nuevo_temp();
             si <suma>.tipo = string: convertir con (texto, …) y emitir(concat, l1, l2, t)
             sino: emitir(+, l1, l2, t);
             meter(t, <suma>.tipo)

<rel> → <suma>1 op <suma>2                      (op: < <= > >= == !=)
   verifica: los dos lados numéricos, duraciones, o ambos string/bool para == y !=; <rel>.tipo = bool
   genera:   (l2, _) = sacar(); (l1, _) = sacar(); t = nuevo_temp(); emitir(op, l1, l2, t); meter(t, bool)

<conj> → <conj>1 y <neg>                         (igual para o)
   verifica: <conj>1.tipo = bool y <neg>.tipo = bool, si no: error("requiere operandos bool")
   genera:   (l2, _) = sacar(); (l1, _) = sacar(); t = nuevo_temp(); emitir(y, l1, l2, t); meter(t, bool)

<neg> → no <neg>1
   verifica: <neg>1.tipo = bool
   genera:   (l, _) = sacar(); t = nuevo_temp(); emitir(no, l, –, t); meter(t, bool)

<unario> → - <unario>1
   verifica: <unario>1.tipo numérico o duracion
   genera:   (l, tp) = sacar(); t = nuevo_temp(); emitir(neg, l, –, t); meter(t, tp)

<primario> → ID
   verifica: s = buscar(ID); si s = nulo: error("identificador no declarado");
             si s es métrica: debe estar en 'usar' del sensor y no puede leerse dentro de una función
   genera:   meter(ID, s.tipo)
<primario> → ENTERO | DECIMAL | CADENA | verdadero | falso
   genera:   meter(constante, tipo)      (NUM ms → valor; NUM s → valor·1000; NUM % → valor/100)
<primario> → ID [ <expr> ]
   verifica: ID es arreglo y <expr>.tipo = int
   genera:   (l, _) = sacar(); t = nuevo_temp(); emitir([], ID, l, t); meter(t, elemento(ID.tipo))

<llamada> → ID ( <expr>1 , … , <expr>n )
   verifica: f = buscar(ID); si f = nulo: error("función no definida");
             si n ≠ aridad(f): error("espera k argumento(s)"); por cada i: asignable(f.param[i], <expr>i.tipo);
             las acciones de dominio solo dentro de un estado; ninguna llamada dentro de un gesto
   genera:   por cada i: emitir(param, <expr>i.lugar); t = nuevo_temp(); emitir(call, ID, n, t); meter(t, f.retorno)

<sentencia> → si <expr> <bloque>1 sino <bloque>2
   verifica: <expr>.tipo = bool, si no: error("la condición de 'si' debe ser bool")
   genera:   Ls = nueva_etq(); Lf = nueva_etq(); emitir(gotoF, <expr>.lugar, –, Ls); <bloque>1;
             emitir(goto, –, –, Lf); Ls: <bloque>2; Lf:

<sentencia> → mientras <expr> <bloque>          (dentro de una función)
   verifica: <expr>.tipo = bool
   genera:   Li: <expr>; emitir(gotoF, <expr>.lugar, –, Lf); <bloque>; emitir(goto, –, –, Li); Lf:

<sentencia> → para ID = <expr>1 hasta <expr>2 <bloque>
   verifica: <expr>1 y <expr>2 de tipo int; abrir_ambito(bloque); insertar(ID, variable, int)
   genera:   emitir(=, <expr>1.lugar, –, ID); lim = nuevo_temp(); emitir(=, <expr>2.lugar, –, lim);
             Li: t = nuevo_temp(); emitir(<=, ID, lim, t); emitir(gotoF, t, –, Lf); <bloque>;
             emitir(+, ID, 1, ID); emitir(goto, –, –, Li); Lf:

<sentencia> → repetir <expr> veces <bloque>
   verifica: <expr>.tipo = int
   genera:   n = nuevo_temp(); emitir(=, <expr>.lugar, –, n); si n no es constante: emitir(chk_rep, n);
             c = nuevo_contador(); emitir(=, 0, –, c); Li: emitir(<, c, n, t); emitir(gotoF, t, –, Lf);
             <bloque>; emitir(+, c, 1, c); emitir(goto, –, –, Li); Lf:

<sentencia> → retornar <expr> ;
   verifica: dentro de una función; asignable(función.retorno, <expr>.tipo)
   genera:   emitir(retv, <expr>.lugar)

<gesto> → gesto ID = <expr> durante <expr>d ( hasta <expr>h )? ( tolerando <expr>t )? ;
   verifica: <expr>.tipo = bool, sin llamadas ni variables locales; d, h, t constantes de tipo duracion;
             análisis de intervalos: error si la condición es insatisfacible o si d > h
   genera:   construir AFD con N = techo(d / periodo) cuadros; emitir(afd, <expr>.lugar, –, ID) en el bloque gestos

<secuencia> → secuencia ID = [ g1, …, gk ] en <expr> ;
   verifica: cada gi es un gesto; 1 ≤ k ≤ 5
   genera:   AFD de reconocimiento de patrones (KMP); emitir(sec, –, –, ID)

<maquina> → maquina ID inicial E0 { <estado>+ }
   verifica: insertar todos los estados antes de revisarlos; E0 debe existir;
             recorrido en anchura desde E0: error en cada estado inalcanzable
<miembro_e> → cuando EV ir_a E ;
   verifica: EV es gesto o secuencia; E es estado de la misma máquina; un evento no lleva a dos destinos
   genera:   entrada (EV → E) en la tabla de despacho del estado; en un bloque: emitir(ir_a, –, –, E)""",
        "Esquema de traducción de EmoLang")

subtitulo("4.6 Notación de código intermedio elegida: cuádruplas")
p("El compilador usa <b>cuádruplas</b> de la forma " + c("(operador, arg1, arg2, resultado)") + ", elegidas "
  "después del estudio comparativo de la sección 2.3. Lo que decidió la elección fue el optimizador: la eliminación "
  "de código muerto, el movimiento de código invariante fuera de los ciclos y la propagación de constantes quitan "
  "y mueven instrucciones, y con cuádruplas eso no obliga a renumerar a las demás. Además, el resultado con nombre "
  "se convierte directamente en una dirección de memoria o un registro al generar el código objeto.")
expr_ej = "a + b * (c - d) / 2"
conv = convertir(expr_ej)
p("El comando " + c("notacion") + " convierte expresiones entre las notaciones infija, postfija y prefija con el "
  "algoritmo de Dijkstra (patio de maniobras) y un árbol de expresión. Para " + c(expr_ej) + ":")
tabla([["Notación", "Expresión"]] + [[k.capitalize(), v] for k, v in conv.items()], [2.5, 9], codigo_en=(1,))

subtitulo("4.7 Juego de instrucciones del código intermedio")
p("Estas son todas las cuádruplas que puede emitir el generador. Los temporales se llaman " + c("t1, t2…") +
  ", los contadores de " + c("repetir") + " " + c("c1, c2…") + " y las variables locales llevan el nombre de su "
  "función (" + c("factorial.n") + "). Los destinos de los saltos se escriben como número de cuádrupla.")
tabla([
    ["Operador", "Arg1", "Arg2", "Resultado", "Significado"],
    ["+  -  *  /", "a", "b", "t", "t ← a op b; la división siempre da decimal"],
    ["<  <=  >  >=  ==  !=", "a", "b", "t", "t ← verdadero si a op b"],
    ["y  o", "a", "b", "t", "Conjunción y disyunción lógicas"],
    ["no  neg", "a", "–", "t", "Negación lógica; cambio de signo"],
    ["shl", "a", "k", "t", "t ← a · 2^k (lo introduce la reducción de fuerza)"],
    ["=", "a", "–", "x", "Asignación x ← a"],
    ["texto", "a", "tipo", "t", "Convierte a texto con el formato del lenguaje"],
    ["concat", "a", "b", "t", "Une dos textos"],
    ["goto", "–", "–", "n", "Salta a la cuádrupla n"],
    ["gotoF", "a", "–", "n", "Salta a n si a es falso"],
    ["param", "a", "–", "–", "Agrega un argumento a la siguiente llamada"],
    ["call", "f", "n", "t", "Llama a f con n argumentos; el resultado queda en t"],
    ["retv  ret", "a", "–", "–", "Regresa con el valor a; regresa sin valor o termina el bloque"],
    ["alloc  alloc_e", "n / E", "T", "x", "Reserva un arreglo de n elementos T o una estructura E"],
    ["[]  []=", "x / v", "i", "t / x", "Lee x[i] en t; escribe v en x[i] (revisan el rango)"],
    ["campo  campo=", "x / v", "E.c", "t / x", "Lee o escribe el campo c de la estructura x"],
    ["chk_rep", "n", "–", "–", "Error si un repetir pide más de 10 000 vueltas"],
    ["afd", "a", "–", "g", "Entrega el símbolo 1 o 0 del cuadro al autómata del gesto g"],
    ["sec", "–", "–", "s", "Entrega los eventos del cuadro al autómata de la secuencia s"],
    ["ir_a", "–", "–", "E", "Cambia la máquina al estado E"],
], [2.6, 1.3, 1.1, 1.4, 7.2], codigo_en=(0, 1, 2, 3))
p("Las cuádruplas de un programa se agrupan en bloques: " + c("init") + " (variables globales), " + c("gestos") +
  " (condiciones que se evalúan en cada cuadro), un bloque por función (" + c("funcion.nombre") + ") y, en los "
  "dominios, los bloques " + c("al_entrar") + ", " + c("cuando") + " y " + c("mientras") + " de cada estado. "
  "Las cuatro últimas (" + c("chk_rep") + ", " + c("afd") + ", " + c("sec") + " e " + c("ir_a") + ") solo aparecen "
  "en programas con dominio y las ejecuta EmoVM.")

subtitulo("4.8 Juego de instrucciones del código objeto")
p("El destino del código objeto es la arquitectura <b>x86-64</b>, en sintaxis Intel del ensamblador GNU, con la "
  "convención System V en Linux y la de Microsoft en Windows. El traductor usa un subconjunto pequeño del juego de "
  "instrucciones. La tabla se armó contando las instrucciones que realmente aparecen en el ensamblador de los "
  f"{len(EJECUCION)} programas de prueba (incluido el runtime):")
GRUPOS = [
    ("Movimiento de datos", lambda m: m in ("mov", "movzx", "movsx", "movsxd", "lea", "push", "pop", "movq", "movsd",
                                            "movabs", "cqo", "xchg")),
    ("Aritmética entera", lambda m: m in ("add", "sub", "imul", "idiv", "neg", "inc", "dec", "shl", "sar", "and",
                                          "or", "xor", "not")),
    ("Aritmética de punto flotante (SSE2)", lambda m: m.endswith("sd") and m not in ("movsd",) or m in ("xorpd", "andpd",
                                                                                                        "sqrtsd")),
    ("Conversión entero ↔ decimal", lambda m: m.startswith("cvt")),
    ("Comparación y prueba", lambda m: m in ("cmp", "test", "ucomisd", "comisd")),
    ("Resultado de una comparación", lambda m: m.startswith("set")),
    ("Saltos", lambda m: m.startswith("j")),
    ("Llamadas y retorno", lambda m: m in ("call", "ret", "leave")),
]
filas, vistos = [["Grupo", "Instrucciones (veces que aparecen)"]], set()
for nombre, cond in GRUPOS:
    ms = sorted((m for m in MNEMONICOS if cond(m) and m not in vistos), key=lambda m: -MNEMONICOS[m])
    vistos.update(ms)
    if ms:
        filas.append([nombre, ", ".join(f"{m} ({MNEMONICOS[m]})" for m in ms)])
resto = sorted(m for m in MNEMONICOS if m not in vistos)
if resto:
    filas.append(["Otras", ", ".join(f"{m} ({MNEMONICOS[m]})" for m in resto)])
tabla(filas, [3.6, 9], codigo_en=(1,))
p("Los enteros, booleanos, direcciones de texto, arreglos y estructuras ocupan 8 bytes y viven en registros de "
  "propósito general; los decimales se calculan en los registros " + c("xmm0") + " y " + c("xmm1") + ". Las "
  "funciones de la biblioteca de C que usa el código generado son " + c("printf") + ", " + c("putchar") + " y "
  + c("snprintf") + " (salida y conversión a texto), " + c("strlen") + ", " + c("strcpy") + ", " + c("strcat") +
  " y " + c("strcmp") + " (textos), " + c("malloc") + " (arreglos y estructuras) y " + c("exit") +
  " (errores en tiempo de ejecución).")

# ================================================================== 3
titulo("5. Manual de arquitectura e implementación", nueva_pagina=True)
simple("El compilador es una cadena de etapas: cada una recibe lo que produjo la anterior, lo revisa o lo "
       "transforma y se lo pasa a la siguiente. Tres estructuras de datos acompañan a toda la cadena: la tabla de "
       "símbolos (qué nombres existen), la pila semántica (resultados parciales de una expresión) y el registro de "
       "errores.")
subtitulo("5.1 Diagrama de bloques del compilador")
figura(figura_bloques(), "Figura 2. Diagrama de bloques del compilador de EmoLang", ancho_cm=14.5, max_alto_cm=17.5)
p("El módulo " + c("emolang/compilador.py") + " ejecuta las fases en orden y guarda lo que produce cada una en un "
  "objeto " + c("Resultado") + ". Se detiene en la primera fase con errores, con una excepción: las validaciones "
  "del dominio se ejecutan aunque el semántico haya encontrado errores, para reportar todos los problemas en una "
  "sola compilación. La conexión entre las cuatro fases finales es la siguiente:")
tabla([
    ["De", "A", "Qué se entrega", "Estructura"],
    ["Semántico", "Intermedio", "AST con el tipo de cada expresión, la tabla de símbolos, las firmas de las "
     "funciones y los campos de cada estructura", "Analisis"],
    ["Intermedio", "Optimizador", "Cuádruplas por bloque, tipo de cada temporal y variable, y la traza de la pila "
     "semántica", "ProgramaIntermedio"],
    ["Optimizador", "Objeto y .emoc", "Las mismas estructuras ya optimizadas y un informe de cada técnica aplicada",
     "ProgramaIntermedio, Informe"],
    ["Objeto", "GCC", "Archivo .asm con la tabla de direcciones y la asignación de registros", "CodigoObjeto"],
], [2.1, 2.3, 6.8, 3.1], codigo_en=(3,))
LINEAS_MOD = {os.path.basename(f): sum(1 for _ in open(f, encoding="utf-8")) for f in glob.glob("emolang/*.py")}
MODULOS = [
    ("lexico.py", "Analizador léxico: AFD, tokens y errores léxicos"),
    ("sintactico.py", "Analizador sintáctico descendente recursivo con recuperación en modo pánico"),
    ("nodos.py", "Clases del árbol de sintaxis abstracta"),
    ("semantico.py", "Tabla de símbolos, ámbitos y verificación de tipos"),
    ("tipos.py", "Reglas de tipos y conversiones"),
    ("validaciones.py", "Validaciones del dominio: intervalos, gestos imposibles, estados inalcanzables"),
    ("automatas.py", "AFD de gestos, secuencias (KMP) y máquinas de estado"),
    ("intermedio.py", "Generador de cuádruplas con pila semántica"),
    ("optimizador.py", "Técnicas de optimización locales, de ciclos y globales"),
    ("direcciones.py", "Tabla de direcciones: segmento de datos, literales y marcos de pila"),
    ("codigo_objeto.py", "Asignación de registros y traducción a ensamblador x86-64"),
    ("emoc.py", "Archivo .emoc que carga la máquina virtual"),
    ("vm.py", "EmoVM: máquina virtual de cuádruplas y autómatas"),
    ("errores.py", "Registro de errores: Diagnostico y Reporte"),
    ("compilador.py", "Orquesta las fases"),
    ("__main__.py", "Interfaz de línea de comandos"),
]
tabla([["Módulo (emolang/)", "Responsabilidad", "Líneas"]] +
      [[m, d, LINEAS_MOD.get(m, "")] for m, d in MODULOS], [3.2, 9, 1.3], codigo_en=(0,),
      rotulo="Módulos del compilador")

subtitulo("5.2 Tabla de símbolos")
p("La tabla de símbolos es un árbol de ámbitos. Cada " + c("Ambito") + " tiene un diccionario de símbolos (búsqueda "
  "en tiempo constante) y una referencia a su ámbito padre. " + c("buscar(nombre)") + " revisa el ámbito actual y "
  "sube por los padres hasta encontrar el nombre; " + c("insertar") + " solo revisa el ámbito actual, por eso una "
  "variable local puede ocultar a una global, pero no puede declararse dos veces en el mismo bloque.")
listado("""\
@dataclass
class Simbolo:
    nombre: str
    categoria: str      # metrica | funcion | parametro | variable | constante | estructura
                        # | gesto | secuencia | maquina | estado
    tipo: str           # int, decimal[3], Punto, "(int, decimal) -> decimal", ...
    ambito: str         # global | programa | funcion f | dominio d | maquina m | estado e | (bloque)
    linea: int
    mutable: bool       # falso en métricas y constantes
    valor: object       # valor si se conoce al compilar (propagación y validación de rangos)
    nodo: object        # nodo del AST que lo declaró

class Ambito:
    nombre: str
    padre: Ambito | None
    simbolos: dict[str, Simbolo]

    def buscar(self, nombre):            # del ámbito actual hacia afuera
        a = self
        while a:
            if nombre in a.simbolos:
                return a.simbolos[nombre]
            a = a.padre
        return None""", "Estructura de datos (emolang/semantico.py)")
p("La jerarquía de ámbitos es la siguiente. El ámbito global ya contiene, antes de leer el programa, las "
  "métricas del sensor y las funciones predefinidas, cada una con su firma (" + c("Funcion(nombre, params, "
  "retorno)") + ").")
listado("""\
global        métricas del sensor (solo lectura) y funciones predefinidas
└─ programa   estructuras, funciones y variables globales
   └─ funcion f      parámetros y variables locales
      └─ bloque      variables de un si, mientras o para (incluye el contador del para)
└─ dominio d  variables del dominio y del sensor, gestos, secuencias y máquinas
   └─ maquina m      estados
      └─ estado e    variables locales (se reinician al entrar al estado)
         └─ bloque   variables declaradas dentro de llaves""")
filas = [["Nombre", "Categoría", "Tipo", "Ámbito", "Línea"]]
for s in R_CALC.analisis.tabla:
    filas.append([s.nombre, s.categoria, s.tipo, s.ambito, s.linea])
tabla(filas, [2.4, 2.2, 4.6, 3.6, 1.1], codigo_en=(0, 2),
      rotulo="Tabla de símbolos real de tests/execution/calculadora.emo (comando semantico)")
p("Además de la tabla, el análisis guarda los campos de cada estructura (" + c(str(R_CALC.analisis.estructuras)) +
  ") y el nodo de cada función, que usan el generador de código intermedio y el de código objeto.")

subtitulo("5.3 Tabla de direcciones")
p("Después de optimizar, " + c("emolang/direcciones.py") + " recorre las cuádruplas de cada bloque y le asigna "
  "a cada nombre su lugar en tiempo de ejecución. La tabla tiene tres partes: el segmento de datos (variables "
  "globales, con dirección fija " + c("datos+k") + "), los literales (textos " + c("str_N") + " y decimales "
  + c("flt_N") + ", de solo lectura) y un marco de pila por función, con desplazamientos " + c("[rbp-k]") +
  ". Cada valor ocupa una palabra de 8 bytes; un arreglo ocupa una palabra más para su longitud y una estructura "
  "una por campo. Un arreglo o una estructura recibidos como parámetro ocupan 8 bytes, porque se pasan por "
  "referencia.")
listado("""\
@dataclass
class Entrada:
    nombre: str        # variable, temporal, contador, literal
    tipo: str
    direccion: str     # datos+k | str_N | flt_N | [rbp-k]
    bytes: int
    categoria: str     # global | metrica | literal | parametro | local | temporal | contador

@dataclass
class Marco:
    bloque: str        # funcion.nombre
    entradas: list[Entrada]
    bytes: int         # múltiplo de 16, como piden las convenciones de llamada

@dataclass
class TablaDirecciones:
    datos: list[Entrada]
    literales: list[Entrada]
    marcos: dict[str, Marco]
    def buscar(self, bloque, nombre): ...   # primero el marco del bloque, después los datos""",
        "Estructura de datos (emolang/direcciones.py)")
tabla([["Nombre", "Categoría", "Tipo", "Dirección", "Bytes"]] +
      [[e.nombre, e.categoria, e.tipo, e.direccion, e.bytes] for e in DIRS_TIPOS.datos + DIRS_TIPOS.literales],
      [4, 2.3, 2.2, 2.4, 1.3], codigo_en=(0, 3),
      rotulo="Segmento de datos y literales de tests/execution/tipos_y_textos.emo (comando direcciones)")

subtitulo("5.4 Pila semántica")
p("El generador de código intermedio traduce cada expresión con una pila semántica explícita, una lista de pares "
  + c("(lugar, tipo)") + ". El árbol se recorre en posorden: un operando mete su lugar y su tipo; un operador saca "
  "sus operandos, emite su cuádrupla y mete el temporal del resultado. Al terminar la expresión queda un solo "
  "elemento, que saca quien la pidió (una asignación, un " + c("si") + ", un argumento). El tipo de cada temporal "
  "se guarda además en " + c("ProgramaIntermedio.tipos") + ", porque el código objeto lo necesita para elegir entre "
  "instrucciones enteras y de punto flotante.")
p(f"La tabla es la traza real que registra el generador para la línea {LINEA_TRAZA} de "
  f"{c('tests/intermediate/ciclos_anidados.emo')}, {c(FUENTE_CICLOS.splitlines()[LINEA_TRAZA - 1].strip())}. "
  "El tope de la pila está a la derecha.")
filas = [["Paso", "Acción del generador", "Pila semántica", "Cuádrupla emitida"]]
for i, paso in enumerate(TRAZA, 1):
    pila = "[" + ", ".join(f"({l}, {t})" for l, t in paso["pila"]) + "]"
    filas.append([i, escape(paso["accion"]), pila, paso["cuadrupla"]])
tabla(filas, [0.9, 4.4, 5.2, 3.6], codigo_en=(2, 3), juntar=False)

subtitulo("5.5 Registro de errores")
p("Todas las fases escriben en el mismo registro, un objeto " + c("Reporte") + " que acumula diagnósticos. Así el "
  "programador ve todos los errores de una sola compilación, ordenados por posición.")
listado("""\
@dataclass
class Diagnostico:
    fase: str        # lexico | sintactico | semantico | dominio | ejecucion
    nivel: str       # error | advertencia | nota
    mensaje: str
    linea: int
    columna: int
    # se imprime como:  [semantico] error en 12:5: no se puede asignar decimal a ...

@dataclass
class Reporte:
    diagnosticos: list[Diagnostico]
    def error(self, fase, mensaje, linea, columna): ...
    def advertencia(self, fase, mensaje, linea, columna): ...
    def nota(self, fase, mensaje, linea, columna): ...
    def tiene_errores(self) -> bool: ...
    def ordenados(self) -> list[Diagnostico]: ...   # por línea y columna""", "Estructura de datos (emolang/errores.py)")
tabla([
    ["Nivel", "Efecto", "Ejemplo"],
    ["error", "Impide generar código; el comando termina con código de salida 1", "Tipos incompatibles"],
    ["advertencia", "Se muestra, pero el programa compila", "Un gesto que nadie usa"],
    ["nota", "Observación de diseño; no se cuenta como advertencia",
     "Un evento que cambia de estado en unos estados y se ignora en otros"],
], [2, 6, 5])
p("Para no detenerse en el primer error, cada fase se recupera: el analizador sintáctico usa <b>modo pánico</b> "
  "(descarta tokens hasta un " + c(";") + ", una " + c("}") + " o el inicio de la siguiente declaración) y el "
  "semántico deja <b>sin tipo</b> al nodo con error, de modo que las expresiones que lo contienen no repiten el "
  "mismo mensaje. Un error en tiempo de ejecución (división entre cero, índice fuera de rango) se reporta con su "
  "línea y termina el programa con código 1, tanto en EmoVM como en el ejecutable nativo.")

subtitulo("5.6 Optimizador")
p("El optimizador recibe las cuádruplas y aplica sus técnicas hasta que ninguna produce cambios:")
tabla([
    ["Alcance", "Técnicas"],
    ["Local (dentro de un bloque básico)", "Plegado de constantes, eliminación de subexpresiones comunes, "
     "simplificación algebraica (x + 0, x · 1, x − x) y reducción de fuerza (x · 16 → x shl 4)"],
    ["Mirilla", "Une una operación con la asignación que la sigue: (+, a, b, t1)(=, t1, –, x) → (+, a, b, x)"],
    ["Ciclos", "Movimiento de código invariante, variables de inducción y desenrollado de repetir de hasta 4 vueltas"],
    ["Global", "Propagación de constantes, código muerto e inalcanzable y funciones que nadie llama"],
], [3.5, 10])
p("Cada aplicación queda en un " + c("Informe") + " con ejemplos de antes y después, que muestra el comando "
  + c("cuadruplas") + ". La sección 7.3 mide el efecto en los programas de prueba.")

subtitulo("5.7 Esquemas de traducción a ensamblador")
p("El traductor de " + c("emolang/codigo_objeto.py") + " recibe las cuádruplas optimizadas y la tabla de "
  "direcciones, y traduce cada cuádrupla con un esquema fijo. El archivo .asm conserva cada cuádrupla como "
  "comentario arriba de sus instrucciones, de modo que la traducción se puede seguir línea por línea.")
tabla([
    ["Cuádrupla", "Esquema en x86-64"],
    ["(=, a, –, x)", "mov r, a ; mov x, r   (o una sola instrucción si x tiene registro asignado)"],
    ["(+, a, b, t)  (−)  (*) con enteros", "mov rax, a ; add/sub/imul rax, b ; mov t, rax"],
    ["(+, a, b, t)  (−)  (*)  (/) con decimales", "movsd xmm0, a ; addsd/subsd/mulsd/divsd xmm0, b ; movsd t, xmm0"],
    ["(/, a, b, t)", "Compara b con 0.0 y salta al aviso de error; un entero se convierte antes con cvtsi2sd"],
    ["(op, a, b, t) relacional", "cmp a, b ; setl/setle/setg/setge/sete/setne al ; movzx t, al  "
     "(decimales: ucomisd y seta/setae; textos: call strcmp)"],
    ["(y, a, b, t)  (o)  (no)  (neg)", "and / or / xor 1 / neg sobre el registro"],
    ["(shl, a, k, t)", "shl r, k  (si el tipo es decimal, convierte el resultado)"],
    ["(gotoF, a, –, n)", "cmp a, 0 ; je .Ln   (si a es constante, el salto se resuelve al compilar)"],
    ["(goto, –, –, n)", "jmp .Ln"],
    ["(param, a)… (call, f, n, t)", "Coloca los argumentos según la convención; call f_nombre ; mov t, rax o movsd t, xmm0"],
    ["(retv, a)  (ret)", "mov rax, a o movsd xmm0, a ; jmp .Lfin_función  (epílogo único)"],
    ["(alloc, n, T, x)  (alloc_e, E, –, x)", "call malloc con 8·(n+1) bytes; guarda n en la primera palabra"],
    ["([], x, i, t)  ([]=, v, i, x)", "Revisa 0 ≤ i < longitud y lee o escribe en [x + 8 + 8·i]"],
    ["(campo, x, E.c, t)  (campo=)", "mov r, [x + 8·posición(c)]"],
    ["(texto, a, T, t)  (concat, a, b, t)", "call emo_texto_T ; call emo_concat  (rutinas del runtime)"],
    ["(chk_rep, n)", "cmp n, 10000 ; jg al aviso de error"],
], [4.6, 8.4], codigo_en=(0, 1), rotulo="Esquemas de traducción de cada cuádrupla")
tabla([["Cuádrupla", "Ensamblador generado"]] + mapeo(CO_FACT.asm, "f_factorial", {1, 2, 3, 6, 7, 8}),
      [4.5, 6], codigo_en=(0, 1), rotulo="Mapeo real de la función factorial (Linux, con registros)")
p("<b>Administración de memoria.</b> El programa se divide en " + c(".text") + " (funciones y runtime), "
  + c(".data") + " (variables globales), " + c(".rodata") + " (textos " + c("str_N") + " y decimales " + c("flt_N") +
  ") y la pila. Cada llamada crea un marco con " + c("push rbp ; mov rbp, rsp ; sub rsp, k") + ", donde k es el "
  "tamaño que calcula la tabla de direcciones, redondeado a múltiplo de 16 como exigen las dos convenciones.")
marco = DIRS_FACT.marcos["funcion.factorial_ciclo"]
tabla([["Nombre", "Categoría", "Tipo", "Dirección", "Bytes"]] +
      [[e.nombre, e.categoria, e.tipo, e.direccion, e.bytes] for e in marco.entradas],
      [4, 2.3, 2, 2.4, 1.3], codigo_en=(0, 3),
      rotulo=f"Marco de pila de factorial_ciclo ({marco.bytes} bytes), comando direcciones")
p("<b>Asignación de registros.</b> Un análisis de flujo de datos calcula las variables vivas en cada cuádrupla "
  "y, con ellas, el intervalo de vida de cada variable entera. El algoritmo <i>linear scan</i> (Poletto y Sarkar, "
  "1999) reparte los intervalos entre " + c("rbx, r12, r13, r14 y r15") + ", que las dos convenciones preservan a "
  "través de las llamadas. Si no hay registro libre, se manda a la pila el intervalo que termina más tarde.")
asig = CO_FACT.asignaciones["funcion.factorial_ciclo"]
tabla([["Variable", "Vive de la cuádrupla", "Hasta", "Lugar"]] +
      [[iv.nombre, iv.inicio + 1, iv.fin + 1, iv.registro or "pila"] for iv in asig.intervalos],
      [5, 3, 2, 3], codigo_en=(0, 3), rotulo="Asignación real de registros de factorial_ciclo")
tabla([
    ["Aspecto", "Linux (System V)", "Windows (Microsoft x64)"],
    ["Argumentos enteros", "rdi, rsi, rdx, rcx, r8, r9", "rcx, rdx, r8, r9"],
    ["Argumentos decimales", "xmm0 a xmm7", "xmm0 a xmm3"],
    ["Reparto", "Por clase: enteros y decimales por separado", "Por posición: el 2.º argumento usa rdx o xmm1"],
    ["Argumentos adicionales", "En la pila", "En la pila, después de 32 bytes de espacio sombra"],
    ["Valor de regreso", "rax o xmm0", "rax o xmm0"],
], [3, 5, 5], rotulo="Convenciones de llamada soportadas (opción --plataforma)")

# ================================================================== 4
titulo("6. Manual de usuario y compilación", nueva_pagina=True)
simple("Esta sección explica cómo instalar EmoLang en una computadora, cómo compilar y ejecutar un programa y qué "
       "hace cada comando de la interfaz de línea de comandos.")
subtitulo("6.1 Requisitos")
tabla([
    ["Componente", "Versión", "Para qué"],
    ["Python", "3.11 (el compilador funciona desde 3.10)", "Todo el proyecto; MediaPipe no soporta 3.13 o posterior"],
    ["GCC", "Cualquier versión reciente; en Windows, MinGW-w64 de MSYS2", "Ensamblar y enlazar el código objeto"],
    ["mediapipe, opencv-python", "Las de requirements.txt", "Solo para usar la cámara"],
    ["Sistema operativo", "Linux o Windows de 64 bits", "El código objeto es x86-64"],
], [3, 5, 5.5])
subtitulo("6.2 Instalación")
numerada([
    "Descargar el proyecto: " + c("git clone https://github.com/n1erik4/EmoLang.git") + " y entrar a la carpeta "
    + c("EmoLang") + ".",
    "Crear el entorno virtual con Python 3.11. En Linux: " + c("python3.11 -m venv .venv") + " (o "
    + c("uv venv --python 3.11 .venv") + "). En Windows: " + c("py -3.11 -m venv .venv") + ".",
    "Instalar las dependencias: " + c(".venv/bin/python -m pip install -r requirements.txt") + " (en Windows, "
    + c(r".venv\Scripts\python") + "). El compilador no necesita ninguna; las dependencias son para la cámara.",
    "Instalar GCC. En Linux suele venir con el sistema (" + c("sudo apt install gcc") + " en Debian y Ubuntu). En "
    "Windows: instalar MSYS2, ejecutar " + c("pacman -S mingw-w64-ucrt-x86_64-gcc") + " y agregar "
    + c(r"C:\msys64\ucrt64\bin") + " al PATH.",
    "Comprobar la instalación: " + c(".venv/bin/python -m unittest discover -s tests -t .") + " debe terminar en OK.",
])
p("En el resto de la sección, " + c("emolang") + " significa " + c(".venv/bin/python -m emolang") + " (en Windows, "
  + c(r".venv\Scripts\python -m emolang") + ").")
subtitulo("6.3 Compilar y ejecutar un programa")
listado("""\
$ emolang semantico tests/execution/factorial.emo         # tabla de símbolos y errores
$ emolang cuadruplas tests/execution/factorial.emo        # código intermedio optimizado
$ emolang correr tests/execution/factorial.emo            # ejecuta en EmoVM
$ emolang ensamblador tests/execution/factorial.emo --correr --registros
Ensamblador x86-64 (linux): factorial.asm  (""" + str(CO_FACT.instrucciones) + """ instrucciones)
...
10 3628800 3628800
(el programa terminó con código 0)""", "Ciclo de trabajo con un programa de propósito general")
listado("""\
$ emolang compilar ejemplos/conduccion.emo         # salida/conduccion/: .emoc y autómatas
$ emolang ejecutar ejemplos/conduccion.emo --sensor simulado --escenario conduccion
$ emolang ejecutar ejemplos/conduccion.emo --sensor camara --sonido
$ emolang evaluar ejemplos/conduccion.emo -o evaluacion/resultados_conduccion.md""",
        "Ciclo de trabajo con un programa de dominio")
p("Si el programa tiene errores, el compilador los lista con su fase, línea y columna, no genera ningún archivo y "
  "termina con código de salida 1. Con éxito termina con 0, y " + c("correr") + " y " + c("ensamblador --correr") +
  " terminan con el valor que devuelve " + c("principal") + ".")

subtitulo("6.4 Comandos de la CLI y parámetros")
AYUDA_EXTRA = {
    "--sin-optimizar": "Usa las cuádruplas sin optimizar",
    "--de": "Notación de la expresión de entrada (por omisión, infija)",
    "--salida": "Archivo o carpeta de salida",
    "--dominio": "Dominio a ejecutar si el archivo tiene varios",
    "--fps": "Cuadros por segundo",
    "--semilla": "Semilla del simulador (resultados reproducibles)",
    "--silencioso": "No imprime la bitácora en la consola",
    "--camara": "Índice de la cámara (0 = la integrada)",
    "--duracion": "Segundos de grabación o ejecución",
    "--programa": "Programa .emo con los umbrales a revisar",
    "--sensor": "Origen de las métricas: simulador, archivo CSV o cámara",
    "--escenario": "Escenario del simulador (repetible; por omisión, los del dominio)",
}


def _oracion(texto):
    """Primera letra en mayúscula, salvo en listas de valores como «conduccion | normal»."""
    return texto if " | " in texto else texto[0].upper() + texto[1:]
GRUPOS_CLI = [
    ("Análisis y código intermedio", ["lexico", "sintactico", "semantico", "cuadruplas", "direcciones", "costos",
                                      "notacion"]),
    ("Compilación y ejecución", ["compilar", "correr", "ensamblador", "ejecutar"]),
    ("Evaluación y herramientas", ["evaluar", "capturar", "diagnostico", "grabar", "fotos"]),
]
por_nombre = {cm_[0]: cm_ for cm_ in COMANDOS}
for grupo, nombres in GRUPOS_CLI:
    filas = [["Comando", "Descripción y parámetros"]]
    for n in nombres:
        _, ayuda, posicionales, opciones = por_nombre[n]
        uso = " ".join([n] + posicionales)
        detalle = escape(ayuda[0].upper() + ayuda[1:]) + "."
        for opc, ay in opciones:
            clave = opc.split()[0]
            ay = ay or AYUDA_EXTRA.get(clave, "")
            detalle += f"<br/>{c(opc)}: {escape(_oracion(ay)) if ay else ''}"
        filas.append([uso, detalle])
    tabla(filas, [3.6, 9.4], codigo_en=(0,), rotulo=grupo, juntar=False)
p("La lista se obtuvo del propio analizador de argumentos del compilador; " + c("emolang COMANDO --help") +
  " muestra la misma información en la terminal.")
subtitulo("6.5 Archivos que genera el compilador")
tabla([
    ["Archivo", "Comando", "Contenido"],
    ["salida/&lt;programa&gt;/&lt;programa&gt;.emoc", "compilar", "Programa compilado en JSON: autómatas, tablas de despacho y cuádruplas"],
    ["salida/&lt;programa&gt;/automatas.md", "compilar", "Tabla de transiciones y diagrama Mermaid de cada autómata"],
    ["salida/&lt;programa&gt;/*.dot", "compilar", "Un diagrama de Graphviz por autómata"],
    ["&lt;programa&gt;.asm", "ensamblador", "Ensamblador x86-64 comentado con las cuádruplas"],
    ["&lt;programa&gt; o &lt;programa&gt;.exe", "ensamblador --correr", "Ejecutable nativo generado por GCC"],
    ["Bitácora CSV", "ejecutar --bitacora", "Eventos, estados y alarmas con su tiempo"],
], [5.4, 3, 5.2])
subtitulo("6.6 Aplicación web")
p("Los dos módulos de dominio también se usan desde el navegador de un celular, una tablet o una computadora. "
  "El navegador ejecuta el mismo compilador y la misma EmoVM con Pyodide, y el servidor guarda las cuentas y los "
  "resultados (nunca el video). Para iniciarlo en la red local:")
listado("""\
$ .venv/bin/python web/servidor.py --https-local
  En esta computadora:  http://localhost:8000
  Celular o tablet:     https://<IP de la computadora>:8443   (misma red Wi-Fi)""")
p("La primera vez el navegador del celular advierte que el certificado es propio de la computadora; se acepta con "
  "«Configuración avanzada» y «Continuar». Hace falta HTTPS porque los navegadores solo permiten usar la cámara en "
  "páginas seguras.")

# ================================================================== 5
titulo("7. Suite de pruebas y casos de estudio", nueva_pagina=True)
simple("Para demostrar que cada parte del compilador funciona, hay programas de prueba escritos a propósito: unos "
       "con errores para ver que el compilador los encuentre, otros con código redundante para ver cuánto lo "
       "reduce el optimizador, y algoritmos clásicos que deben dar el resultado correcto ya convertidos en "
       "programas nativos.")
subtitulo("7.1 Organización")
listado("""\
tests/
├─ semantic/        errores intencionales      .esperado = errores que debe reportar
├─ intermediate/    ciclos y código redundante .esperado = salida del programa
├─ execution/       algoritmos clásicos        .esperado = salida del programa
└─ test_*.py        pruebas automáticas (unittest) que recorren las tres carpetas""")
p("Cada " + c(".emo") + " tiene a su lado un archivo " + c(".esperado") + ". En " + c("semantic") + " contiene los "
  "errores exactos que debe reportar el compilador; en las otras dos, la salida exacta que debe imprimir el "
  "programa. Las pruebas automáticas comparan carácter por carácter, así que cualquier cambio en el compilador que "
  "altere un resultado se detecta.")

subtitulo("7.2 Pruebas de análisis semántico (tests/semantic)")
p("Cada archivo agrupa un tipo de error y marca con " + c("// error:") + " las líneas donde el compilador debe "
  "detectar uno. La prueba " + c("tests/test_semantico.py") + " revisa que los errores reportados sean exactamente "
  "los de su " + c(".esperado") + ", que haya al menos un error en cada línea marcada y ninguno en las demás, y que "
  "no se genere código.")
DESC_SEM = {
    "tipos.emo": "Asignaciones incompatibles, operadores mal aplicados, condiciones que no son bool, índices y campos",
    "no_declarados.emo": "Variables, funciones, arreglos y tipos no declarados; redeclaraciones",
    "alcance.emo": "Locales de otra función o de otro bloque, acciones de dominio fuera de un estado, métricas "
                   "fuera de 'usar', llamadas dentro de un gesto y locales de otro estado",
    "funciones.emo": "Aridad, tipo de los argumentos, retorno faltante o de tipo incorrecto",
    "dominio.emo": "Umbrales fuera de rango, gestos imposibles, transiciones contradictorias y estados inalcanzables",
}
tabla([["Archivo", "Qué demuestra", "Líneas marcadas", "Errores", "¿Genera código?"]] +
      [[n, DESC_SEM.get(n, ""), m, e, "No" if sin else "Sí"] for n, e, m, _, _, sin in SEMANTICAS] +
      [["Total", "", sum(x[2] for x in SEMANTICAS), sum(x[1] for x in SEMANTICAS), ""]],
      [3.2, 6.0, 1.5, 1.5, 1.4], codigo_en=(0,))
RUTA_ALC = "tests/semantic/alcance.emo"
listado(numerar(leer(RUTA_ALC)), "Caso de estudio: tests/semantic/alcance.emo")
R_ALC = compilar_archivo(RUTA_ALC)
listado("$ emolang semantico tests/semantic/alcance.emo\n...\n" +
        "\n".join(str(d) for d in R_ALC.reporte.ordenados() if d.nivel != "nota") +
        f"\n\n{len(R_ALC.reporte.errores)} error(es), {len(R_ALC.reporte.advertencias)} advertencia(s)",
        "Salida del compilador (se omite la tabla de símbolos)")
p("El compilador encuentra los errores de todas las fases en una sola pasada. Las advertencias no impiden "
  "compilar: avisan que un gesto se declaró pero no se usa, o que no depende de ninguna métrica.")

subtitulo("7.3 Pruebas de código intermedio y optimización (tests/intermediate)")
p("Estos programas tienen a propósito ciclos anidados, cálculos que no cambian dentro de un ciclo, constantes, "
  "subexpresiones repetidas, variables sin usar, código inalcanzable y una función que nadie llama. La tabla "
  "compara cada programa antes y después de optimizar; los datos son del comando " + c("costos") + ".")
filas = [["Programa", "Cuádruplas (antes → después)", "Ejecutadas (antes → después)", "Reducción ejecutadas",
          "Técnicas aplicadas (veces)"]]
for n, a, d, apl in INTERMEDIAS:
    red = 100 * (a.ejecutadas - d.ejecutadas) / a.ejecutadas
    filas.append([n, f"{a.cuadruplas} → {d.cuadruplas}", f"{a.ejecutadas} → {d.ejecutadas}", f"{red:.1f} %",
                  ", ".join(f"{t} ({k})" for t, k in apl.most_common())])
tabla(filas, [3.9, 2.2, 2.4, 1.7, 4.3], codigo_en=(0,))
from emolang.costos import CAMPOS  # noqa: E402
filas = [["Costo"] + [n for n, *_ in INTERMEDIAS]]
for campo, nombre in CAMPOS:
    fila = [nombre]
    for _, a, d, _ in INTERMEDIAS:
        va, vd = getattr(a, campo), getattr(d, campo)
        fmt = (lambda v: f"{v:.3f}") if isinstance(va, float) else str
        fila.append(f"{fmt(va)} → {fmt(vd)}")
    filas.append(fila)
tabla(filas, [4.2, 3.1, 3.1, 3.1], rotulo="Análisis de costos antes → después de optimizar (comando costos)")
p("El tiempo se mide ejecutando cada programa en EmoVM y varía un poco entre corridas. Los registros necesarios "
  "son el mayor número de temporales vivos al mismo tiempo: pueden subir cuando un cálculo se saca de un ciclo, "
  "porque su resultado tiene que conservarse durante todo el ciclo.")
p("La medida que importa es la de cuádruplas <b>ejecutadas</b>. En " + c("ciclos_anidados.emo") + " el programa "
  "crece un poco, porque sacar un cálculo de un ciclo agrega una cuádrupla antes del ciclo, pero el número de "
  "instrucciones que se ejecutan baja, porque ese cálculo ya no se repite en cada vuelta.")
listado(numerar(FUENTE_CICLOS), "Caso de estudio: tests/intermediate/ciclos_anidados.emo")
tabla_cuadruplas(R_CICLOS.cuadruplas[PROGRAMA].bloques["funcion.suma_tabla"],
                 "Función suma_tabla antes de optimizar")
tabla_cuadruplas(R_CICLOS.optimizado[PROGRAMA].bloques["funcion.suma_tabla"],
                 "Función suma_tabla después de optimizar")
inf = R_CICLOS.informes[PROGRAMA]
ejemplos = [(t, a, d) for t, ej in inf.ejemplos.items() for a, d, b in ej if b == "funcion.suma_tabla"]
if ejemplos:
    tabla([["Técnica", "Antes", "Después"]] + [[t, a, d or "(se quita)"] for t, a, d in ejemplos],
          [2.5, 5, 5], codigo_en=(1, 2), rotulo="Lo que hizo el optimizador en suma_tabla (informe del optimizador)")
p(c("ancho * ancho") + " no cambia dentro de los ciclos, así que se calcula una sola vez antes de ellos "
  "(código invariante). " + c("i * 8") + " y " + c("j * 4") + " se cambian por desplazamientos (reducción de "
  "fuerza) y, como dependen del contador, se actualizan sumando una constante en cada vuelta (variables de "
  "inducción).")

subtitulo("7.4 Pruebas integrales de código objeto (tests/execution)")
p("Los algoritmos clásicos de la rúbrica (factorial, serie de Fibonacci, ordenamiento de arreglos y calculadora), "
  "más dos programas que prueban los tipos y el paso de muchos argumentos, se compilan a ensamblador x86-64, se "
  "ensamblan y enlazan con GCC y se ejecutan como programas nativos. Su salida debe ser idéntica al archivo "
  + c(".esperado") + ". Cada programa se prueba en cuatro versiones: con y sin optimizar, y con y sin asignación "
  "de registros. Los programas de " + c("tests/intermediate") + " también se ejecutan así.")
if HAY_GCC:
    tabla([["Programa", "Instrucciones x86-64 (optimizado)", "Líneas de salida", "Versiones correctas"]] +
          [[n, i, l, f"{k} de 4"] for n, i, l, k in EJECUCION], [6.2, 3.1, 2.2, 2.2], codigo_en=(0,),
          rotulo="Resultados en Linux x86-64 con GCC")
    total_ok = sum(k for *_, k in EJECUCION)
    p(f"Las <b>{total_ok} de {4 * len(EJECUCION)}</b> ejecuciones dieron exactamente la salida esperada. "
      "El código de Windows se revisó ensamblándolo; ejecutarlo requiere una computadora con Windows y MSYS2.")
RUTA_ORD = "tests/execution/ordenamiento.emo"
listado(numerar(leer(RUTA_ORD)), "Caso de estudio: tests/execution/ordenamiento.emo")
R_ORD = compilar_archivo(RUTA_ORD)
CO_ORD = CO.generar(R_ORD.optimizado[PROGRAMA], R_ORD.analisis, "linux")
salida_ord = None
if HAY_GCC:
    _, salida_ord = correr_asm(CO_ORD)
listado(f"$ emolang ensamblador {RUTA_ORD} --correr\n"
        f"Ensamblador x86-64 (linux): ordenamiento.asm  ({CO_ORD.instrucciones} instrucciones)\n" +
        (salida_ord or leer(RUTA_ORD[:-4] + ".esperado")) + "\n(el programa terminó con código 0)",
        "Ejecución del programa nativo")
fn_ord = "f_ordenar" if "f_ordenar:" in CO_ORD.asm.split("\n") else None
if fn_ord:
    lineas = funcion_asm(CO_ORD.asm, fn_ord)
    listado("\n".join(lineas[:46]) + ("\n    ..." if len(lineas) > 46 else ""),
            f"Inicio del ensamblador generado para {fn_ord[2:]} (comentarios = cuádruplas)")

subtitulo("7.5 Pruebas automáticas")
p(f"Además de las tres carpetas, la suite tiene <b>{TOTAL_PRUEBAS} pruebas</b> automáticas que cubren cada fase. "
  "Se ejecutan todas con " + c("python -m unittest discover -s tests -t .") + ".")
DESCR = {
    "test_emolang.py": "Léxico, sintáctico, semántico, autómatas y motor",
    "test_semantico.py": "Carpeta tests/semantic: gestor de errores",
    "test_vm.py": "Máquina virtual y equivalencia entre versiones optimizada y sin optimizar",
    "test_lenguaje.py": "Funciones, ciclos, arreglos, estructuras y algoritmos",
    "test_notaciones.py": "Conversión de notaciones y tabla de direcciones",
    "test_optimizador.py": "Cada técnica, costos y 300 programas generados al azar",
    "test_codigo_objeto.py": "Carpetas tests/execution y tests/intermediate en ensamblador con GCC",
    "test_conduccion.py": "Detección de microsueño y cabeceo con cámaras lentas",
    "test_esfuerzo_maximo.py": "Perfil de esfuerzo máximo de la terapia facial",
    "test_fotos.py": "Calibración de umbrales con fotos",
    "test_web.py": "Puente de la aplicación web",
    "test_servidor.py": "Servidor: cuentas, roles, sesiones y seguridad",
}
tabla([["Archivo", "Qué revisa", "Pruebas"]] +
      [[n, DESCR.get(n, ""), k] for n, k in PRUEBAS.items()] + [["Total", "", TOTAL_PRUEBAS]],
      [4, 8.5, 1.5], codigo_en=(0,))

# ================================================================== 6
titulo("8. Conclusiones", nueva_pagina=True)
_sem_err = sum(x[1] for x in SEMANTICAS)
_red = [100 * (a.ejecutadas - d.ejecutadas) / a.ejecutadas for _, a, d, _ in INTERMEDIAS]
_ok = sum(k for *_, k in EJECUCION)
p("Se cumplió el objetivo del proyecto integrador: se implementó un compilador completo para EmoLang, un "
  "lenguaje de dominio específico, que recorre todas las etapas de un compilador, desde el análisis léxico hasta "
  "la generación de código objeto para una arquitectura real. El resultado no se queda en un ejercicio aislado: "
  "el mismo compilador traduce los programas de propósito general a ejecutables x86-64 y los programas de "
  "dominio a autómatas que, con una cámara, detectan señales de somnolencia al conducir o cuentan los ejercicios "
  "de una rutina de terapia facial.")
p("<b>Análisis léxico, sintáctico y semántico.</b> Definir la gramática como LL(1) permitió escribir a mano un "
  "analizador descendente recursivo, sin generadores, y controlar cada mensaje de error y la recuperación en modo "
  "pánico. Sobre el árbol de sintaxis abstracta, el análisis semántico aplica las reglas dirigidas por la sintaxis: "
  "la tabla de símbolos con ámbitos anidados resuelve el alcance de cada nombre, el verificador de tipos aplica la "
  "tabla de conversiones implícitas y explícitas, y el registro de errores acumula los diagnósticos de todas las "
  f"fases. Los {len(SEMANTICAS)} programas de {c('tests/semantic')} lo demuestran: el compilador encontró los "
  f"{_sem_err} errores intencionales en una sola compilación, cada uno en su línea, y en ningún caso generó código.")
p("<b>Código intermedio.</b> El estudio comparativo de las representaciones intermedias llevó a elegir los "
  "cuádruplos, y la decisión se justificó en la práctica: como cada resultado tiene nombre, el optimizador puede "
  "mover, quitar o reutilizar instrucciones sin renumerar las demás, y cada temporal se traduce directamente a un "
  "registro o a una dirección de memoria. La pila semántica, recorriendo los árboles de expresión en posorden, "
  "genera las cuádruplas de las expresiones, asignaciones, estructuras de control, llamadas a funciones y "
  "estructuras con esquemas de traducción fijos, y el convertidor de notaciones completa el tema con las formas "
  "infija, prefija y postfija.")
p("<b>Optimización.</b> Las técnicas locales, de ciclos, globales y de mirilla se aplican hasta que ninguna produce "
  f"cambios. En los programas de {c('tests/intermediate')} redujeron las cuádruplas ejecutadas entre "
  f"{min(_red):.0f} % y {max(_red):.0f} %. Medir los costos antes y después dejó una lección: el número de "
  "instrucciones del programa no es la medida correcta, porque sacar un cálculo de un ciclo puede agregar una "
  "instrucción y aun así reducir mucho las que se ejecutan; también puede aumentar los registros necesarios, "
  "porque el valor calculado tiene que conservarse durante todo el ciclo.")
p("<b>Código objeto.</b> La traducción a ensamblador x86-64 puso en práctica la arquitectura del microprocesador: "
  "el análisis de variables vivas y el algoritmo linear scan reparten los registros físicos, la tabla de "
  "direcciones organiza los segmentos de datos y de literales y el marco de pila de cada función, y el traductor "
  "respeta las convenciones de llamada de Linux y de Windows para poder usar la biblioteca de C. Las "
  f"<b>{_ok} de {4 * len(EJECUCION)}</b> ejecuciones de los algoritmos clásicos y de los programas de prueba, con y "
  "sin optimización y con y sin asignación de registros, produjeron exactamente la salida esperada. Esta etapa "
  "además encontró un error que había pasado inadvertido en el optimizador, porque el procesador distingue entre "
  "enteros y decimales donde la máquina virtual no lo hacía; comparar dos ejecuciones independientes resultó ser "
  "una forma muy efectiva de validar un compilador.")
p(f"<b>Pruebas.</b> La suite automática de {TOTAL_PRUEBAS} pruebas, junto con las tres carpetas de casos de estudio, "
  "permitió modificar el compilador con confianza durante todo el semestre: cualquier cambio que alterara un "
  "resultado se detectaba de inmediato.")
p("<b>Limitaciones y trabajo futuro.</b> El código objeto para Windows se revisó ensamblándolo, pero falta "
  "ejecutarlo en una computadora con Windows. Los arreglos solo contienen tipos primitivos y no hay entrada de "
  "datos desde el teclado. Los gestos y las máquinas de estado se ejecutan en la máquina virtual y no en "
  "ensamblador, porque dependen de la cámara cuadro por cuadro. Finalmente, los módulos de conducción y de terapia "
  "facial se validaron con escenarios simulados, fotos y pruebas del equipo; el siguiente paso es una evaluación "
  "con participantes, con consentimiento informado y sin guardar video, como establece el marco legal.")

titulo("Referencias", nueva_pagina=True)
for r_txt in [
    "Aho, A. V., Lam, M. S., Sethi, R. y Ullman, J. D. (2008). <i>Compiladores: principios, técnicas y herramientas</i> (2.ª ed.). Pearson Educación.",
    "Louden, K. C. (2004). <i>Construcción de compiladores: principios y práctica</i>. Thomson.",
    "Poletto, M. y Sarkar, V. (1999). Linear scan register allocation. <i>ACM Transactions on Programming Languages and Systems</i>, 21(5), 895-913.",
    "Knuth, D. E., Morris, J. H. y Pratt, V. R. (1977). Fast pattern matching in strings. <i>SIAM Journal on Computing</i>, 6(2), 323-350.",
    "Dijkstra, E. W. (1961). <i>Algol 60 translation: An Algol 60 translator for the X1</i>. Mathematisch Centrum, Ámsterdam.",
    "Nori, K. V., Ammann, U., Jensen, K., Nägeli, H. H. y Jacobi, C. (1981). Pascal-P implementation notes. En D. W. Barron (Ed.), <i>Pascal: The Language and its Implementation</i>. Wiley.",
    "Matz, M., Hubička, J., Jaeger, A. y Mitchell, M. <i>System V Application Binary Interface: AMD64 Architecture Processor Supplement</i>.",
    "Microsoft. x64 calling convention. Documentación de Microsoft Learn.",
    "Intel Corporation. <i>Intel 64 and IA-32 Architectures Software Developer's Manual</i>.",
    "Cámara de Diputados del H. Congreso de la Unión (2025). <i>Ley Federal de Protección de Datos Personales en Posesión de los Particulares</i>. Diario Oficial de la Federación, 20 de marzo de 2025.",
    "Secretaría de Comunicaciones y Transportes (2017). <i>NOM-087-SCT-2-2017, que establece los tiempos de conducción y pausas de descanso para los conductores de los servicios de autotransporte federal</i>. Diario Oficial de la Federación.",
    "Lugaresi, C. et al. (2019). MediaPipe: A framework for building perception pipelines. arXiv:1906.08172.",
]:
    historia.append(Paragraph(r_txt, lista, bulletText="•"))

doc = Documento(SALIDA, pagesize=letter, leftMargin=2.5 * cm, rightMargin=2.5 * cm, topMargin=2.3 * cm,
                bottomMargin=2.3 * cm, title="EmoLang: Reporte final, documentación técnica del compilador",
                author="Equipo EmoLang, Grupo 7SB")
doc.multiBuild(historia, onFirstPage=lambda ca, d: None, onLaterPages=numero_pagina)
shutil.rmtree(TMP, ignore_errors=True)
print(SALIDA)
