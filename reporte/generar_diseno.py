"""Genera reporte/EmoLang_Fase2_Diseno_Compilador.pdf.

Las tablas de símbolos, las cuádruplas, la traza de la pila, los mensajes de error,
los números de la optimización y las pruebas se obtienen al momento del compilador
real, así que el documento no puede quedar desalineado del código.

Uso (desde la raíz del proyecto):
    python reporte/generar_diseno.py
"""

import os
import sys
import unittest

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
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

from emolang import automatas as A  # noqa: E402
from emolang import nodos as N  # noqa: E402
from emolang.compilador import compilar, compilar_archivo  # noqa: E402
from emolang.ejecucion import ejecutar  # noqa: E402
from emolang.intermedio import resolver  # noqa: E402
from emolang.metricas import METRICAS  # noqa: E402
from emolang.sensores import SensorSimulado  # noqa: E402

FIG = os.path.join(AQUI, "figuras")
SALIDA = os.path.join(AQUI, "EmoLang_Fase2_Diseno_Compilador.pdf")
FUENTES = r"C:\Windows\Fonts"
ANCHO = letter[0] - 5 * cm - 12   # el marco de la página reserva 6 puntos por lado

pdfmetrics.registerFont(TTFont("Arial", os.path.join(FUENTES, "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-B", os.path.join(FUENTES, "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial-I", os.path.join(FUENTES, "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Arial-BI", os.path.join(FUENTES, "arialbi.ttf")))
pdfmetrics.registerFont(TTFont("Consolas", os.path.join(FUENTES, "consola.ttf")))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-B", italic="Arial-I", boldItalic="Arial-BI")

cuerpo = ParagraphStyle("cuerpo", fontName="Arial", fontSize=10.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=7)
lista = ParagraphStyle("lista", parent=cuerpo, leftIndent=16, bulletIndent=4, spaceAfter=3)
h1 = ParagraphStyle("h1", fontName="Arial-B", fontSize=13, leading=17, spaceBefore=14, spaceAfter=8, keepWithNext=1)
h2 = ParagraphStyle("h2", fontName="Arial-B", fontSize=11, leading=14, spaceBefore=10, spaceAfter=5, keepWithNext=1)
pie = ParagraphStyle("pie", fontName="Arial-B", fontSize=9.5, leading=12, spaceBefore=6, spaceAfter=5, keepWithNext=1)
codigo = ParagraphStyle("codigo", fontName="Consolas", fontSize=7.9, leading=10, leftIndent=4)
celda = ParagraphStyle("celda", fontName="Arial", fontSize=8.8, leading=11, alignment=TA_LEFT)
celda_b = ParagraphStyle("celda_b", parent=celda, fontName="Arial-B")
celda_c = ParagraphStyle("celda_c", parent=celda, fontName="Consolas", fontSize=8.3)
portada = ParagraphStyle("portada", fontName="Arial", fontSize=12, leading=16, alignment=TA_CENTER)
portada_b = ParagraphStyle("portada_b", parent=portada, fontName="Arial-B")

historia = []


def c(texto):
    """Texto en fuente de código dentro de un párrafo."""
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


def numerada(items):
    for i, it in enumerate(items, 1):
        historia.append(Paragraph(it, lista, bulletText=f"{i}."))
    historia.append(Spacer(1, 5))


def _con_titulo(bloque):
    """Si lo anterior es un título, lo mete al bloque para que no quede solo al final de la página."""
    if historia and hasattr(historia[-1], "_toc"):
        return [historia.pop()] + bloque
    return bloque


def tabla(filas, anchos, codigo_en=(), rotulo=None, juntar=True):
    """`codigo_en`: columnas en fuente de código. El texto se escapa, salvo si ya trae marcas."""
    datos = []
    for i, fila in enumerate(filas):
        renglon = []
        for j, v in enumerate(fila):
            texto = str(v)
            if i == 0:
                renglon.append(Paragraph(texto, celda_b))
            elif j in codigo_en:
                renglon.append(Paragraph(escape(texto), celda_c))
            else:
                renglon.append(Paragraph(texto, celda))
        datos.append(renglon)
    total = sum(anchos)
    t = Table(datos, colWidths=[a * ANCHO / total for a in anchos], repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, "black"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    bloque = []
    if rotulo:
        bloque.append(Paragraph(rotulo, pie))
    bloque.append(t)
    bloque.append(Spacer(1, 11))
    if juntar and len(filas) < 24:
        historia.append(KeepTogether(_con_titulo(bloque)))
    else:
        historia.extend(bloque)


def listado(texto, rotulo=None):
    # Un renglón de tabla por línea, para que el listado pueda partirse entre páginas.
    t = Table([[Preformatted(l or " ", codigo)] for l in texto.rstrip("\n").split("\n")], colWidths=[ANCHO])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, "black"),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    if rotulo:
        historia.append(Paragraph(rotulo, pie))
    historia.append(t)
    historia.append(Spacer(1, 10))


def figura(ruta, rotulo, ancho_cm=14.5, max_alto_cm=19):
    w, h = PILImage.open(ruta).size
    ancho = min(ancho_cm * cm, ANCHO)
    alto = ancho * h / w
    if alto > max_alto_cm * cm:
        alto = max_alto_cm * cm
        ancho = alto * w / h
    historia.append(KeepTogether(_con_titulo([Paragraph(rotulo, pie), Image(ruta, width=ancho, height=alto), Spacer(1, 10)])))


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


# ------------------------------------------------------------------ datos reales
ruta_cond = os.path.join(RAIZ, "ejemplos", "conduccion.emo")
ruta_rehab = os.path.join(RAIZ, "ejemplos", "rehabilitacion.emo")
R = compilar_archivo(ruta_cond)
RR = compilar_archivo(ruta_rehab)
assert R.ok and RR.ok
PROG = R.cuadruplas["conduccion"]
OPT = R.optimizado["conduccion"]
INF = R.informes["conduccion"]
PROG_R = RR.cuadruplas["rehabilitacion"]
OPT_R = RR.optimizado["rehabilitacion"]
INF_R = RR.informes["rehabilitacion"]
DOM = R.analisis.dominios["conduccion"]
GESTO_CABECEO = DOM.gestos["cabeceo"]

with open(ruta_cond, encoding="utf-8") as f:
    FUENTE = f.read()


def linea_de(fragmento):
    for i, l in enumerate(FUENTE.splitlines(), 1):
        if fragmento in l:
            return i
    raise ValueError(fragmento)


def explicar(q):
    op, a1, a2, res = q.op, q.a1, q.a2, q.res
    if op in ("<", "<=", ">", ">=", "==", "!="):
        return f"{res} es verdadero si {escape(str(a1))} {escape(op)} {escape(str(a2))}"
    if op == "y":
        return f"{res} es verdadero si {a1} y {a2} lo son"
    if op == "o":
        return f"{res} es verdadero si {a1} o {a2} lo es"
    if op == "no":
        return f"{res} es la negación de {a1}"
    if op == "neg":
        return f"{res} es {a1} con el signo cambiado"
    if op == "afd":
        return f"Entrega al AFD de {res} el símbolo 1 o 0 del cuadro"
    if op == "sec":
        return f"Entrega al AFD de {res} los eventos del cuadro"
    if op in ("+", "-", "*", "/"):
        return f"Calcula {a1} {op} {a2} y lo guarda en {res}"
    if op == "=":
        return f"Guarda {escape(str(a1))} en {res}"
    if op == "texto":
        return f"Convierte {a1} ({a2}) a texto"
    if op == "concat":
        return "Une los dos textos"
    if op == "gotoF":
        return f"Si {a1} es falso, salta a la cuádrupla {res}"
    if op == "goto":
        return f"Salta a la cuádrupla {res}"
    if op == "param":
        return "Prepara el argumento"
    if op == "call":
        return f"Llama a {a1} con {a2} argumento(s)"
    if op == "ir_a":
        return f"Cambia al estado {res}"
    if op == "chk_rep":
        return "Revisa el límite de vueltas"
    if op == "ret":
        return "Termina el bloque"
    return ""


def tabla_cuadruplas(cuads, rotulo=None):
    filas = [["#", "Operador", "Arg1", "Arg2", "Resultado", "Qué se hace"]]
    for i, q in enumerate(resolver(cuads), 1):
        filas.append([i, *q.fila(), explicar(q)])
    tabla(filas, [0.8, 1.9, 3.3, 2.7, 2.7, 4.8], codigo_en=(1, 2, 3, 4), rotulo=rotulo)


def tamano(cuads):
    return len(resolver(cuads))


def primer_ejemplo(tecnica, *informes):
    for inf in informes:
        ej = inf.ejemplos.get(tecnica)
        if ej:
            return ej[0]
    return ("", "", "")


def error_real(fuente):
    r = compilar(fuente)
    assert r.reporte.errores, fuente
    return r.reporte.errores[0].mensaje


def programa_prueba(cuerpo_txt="", estados="estado a { }", dominio="conduccion", sensor="usar ear, mar;"):
    return (f"dominio {dominio} {{ sensor camara {{ {sensor} var fps : int = 30; }} var alertas : int = 0;\n"
            f"{cuerpo_txt}\nmaquina m inicial a {{ {estados} }} }}")


def contar_pruebas():
    return unittest.TestLoader().discover("tests", top_level_dir=".").countTestCases()


def latencia():
    res = ejecutar(R, "conduccion", SensorSimulado("conduccion", semilla=1), verbose=False)
    return res.latencia_media_ms, res.latencia_p95_ms


# ------------------------------------------------------------------ figuras
def caja(ax, x, y, w, h, titulo_caja, detalle="", grueso=0.8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.08", fill=False,
                                lw=grueso, color="black"))
    if detalle:
        ax.text(x + 0.14, y + h * 0.63, titulo_caja, fontsize=7.6, fontweight="bold", va="center")
        ax.text(x + 0.14, y + h * 0.28, detalle, fontsize=6.4, va="center")
    else:
        ax.text(x + w / 2, y + h / 2, titulo_caja, fontsize=7.6, ha="center", va="center")


def figura_arquitectura():
    plt.rcParams.update({"font.family": "Arial"})
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    ax.set_xlim(0, 13.2)
    ax.set_ylim(0, 9.2)
    ax.axis("off")
    izq = [("Analizador léxico", "AFD escrito a mano: tokens y errores léxicos"),
           ("Analizador sintáctico", "Descendente recursivo: AST y modo pánico"),
           ("Analizador semántico", "Tabla de símbolos, ámbitos y tipos"),
           ("Validaciones de dominio", "Umbrales, gestos imposibles, inalcanzables"),
           ("Generador de autómatas", "AFD de gestos, secuencias (KMP) y estados"),
           ("Código intermedio", "Cuádruplas con pila semántica"),
           ("Optimizador", "Seis técnicas sobre las cuádruplas"),
           ("Generador del .emoc", "Autómatas, despacho y cuádruplas")]
    der = [("Cámara", "OpenCV: cuadros RGB"),
           ("MediaPipe Face Landmarker", "478 puntos y 52 blendshapes"),
           ("Cálculo de métricas", "ear, mar, pitch, yaw, sonrisa, simetría..."),
           ("Regularización del ritmo", "Lleva los cuadros al fps del programa"),
           ("Bloque gestos", "Cuádruplas de condiciones y AFD de gestos"),
           ("Máquinas de estado", "cuando, tras, mientras y al_entrar"),
           ("Módulos de dominio", "Alarma y registro; conteo y simetría")]
    ax.add_patch(FancyBboxPatch((0.1, 0.1), 6.2, 9.0, boxstyle="round,pad=0,rounding_size=0.1", fill=False, lw=0.8))
    ax.add_patch(FancyBboxPatch((6.9, 0.1), 6.2, 9.0, boxstyle="round,pad=0,rounding_size=0.1", fill=False, lw=0.8))
    ax.text(0.35, 8.8, "Compilador · emolang compilar", fontsize=8, fontweight="bold", va="center")
    ax.text(7.15, 8.8, "EmoVM · emolang ejecutar", fontsize=8, fontweight="bold", va="center")

    def columna(x, cajas, alto, hueco):
        ys = []
        y = 8.45 - alto
        for i, (t, d) in enumerate(cajas):
            resaltar = t in ("Bloque gestos", "Máquinas de estado")
            caja(ax, x, y, 5.6, alto, t, d, grueso=1.5 if resaltar else 0.8)
            ys.append(y)
            if i < len(cajas) - 1:
                ax.add_patch(FancyArrowPatch((x + 2.8, y), (x + 2.8, y - hueco), arrowstyle="-|>",
                                             mutation_scale=7, lw=0.6, color="black"))
            y -= alto + hueco
        return ys

    ys_i = columna(0.4, izq, 0.82, 0.19)
    ys_d = columna(7.2, der, 0.93, 0.24)
    a = (6.0, ys_i[-1] + 0.41)
    b = (7.2, ys_d[4] + 0.46)
    ax.plot([a[0], 6.6, 6.6], [a[1], a[1], b[1]], color="black", lw=0.7)
    ax.add_patch(FancyArrowPatch((6.6, b[1]), b, arrowstyle="-|>", mutation_scale=7, lw=0.7, color="black"))
    ax.text(6.46, (a[1] + b[1]) / 2, ".emoc", fontsize=6.6, ha="center", va="center", rotation=90)
    ruta = os.path.join(FIG, "fig_diseno_arquitectura.png")
    fig.savefig(ruta, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return ruta


def _texto_nodo(e):
    if isinstance(e, N.Binaria):
        return e.op, [e.izq, e.der]
    if isinstance(e, N.Unaria):
        return e.op, [e.operando]
    return A.texto_expr(e), []


def figura_arbol(e, lugares):
    """Dibuja el AST real de una expresión con el tipo que le asignó el analizador."""
    plt.rcParams.update({"font.family": "Arial"})
    posiciones = []
    contador = [0]

    def ubicar(n, nivel):
        et, hijos = _texto_nodo(n)
        xs = [ubicar(h, nivel + 1) for h in hijos]
        if xs:
            x = sum(xs) / len(xs)
        else:
            x = contador[0]
            contador[0] += 1
        posiciones.append((n, et, x, nivel, xs))
        return x

    ubicar(e, 0)
    niveles = max(pos[3] for pos in posiciones)
    fig, ax = plt.subplots(figsize=(6.0, 0.9 * (niveles + 1)))
    ancho_h, alto_h = 1.8, 0.62
    x_de = {id(pos[0]): pos[2] * 1.9 for pos in posiciones}
    for n, et, x, nivel, _ in posiciones:
        px, py = x * 1.9, -nivel * 1.25
        hijos = _texto_nodo(n)[1]
        for h in hijos:
            nivel_h = nivel + 1
            ax.plot([px, x_de[id(h)]], [py - alto_h / 2, -nivel_h * 1.25 + alto_h / 2], color="black", lw=0.6)
        grueso = 1.4 if nivel == 0 else 0.7
        ax.add_patch(FancyBboxPatch((px - ancho_h / 2, py - alto_h / 2), ancho_h, alto_h,
                                    boxstyle="round,pad=0,rounding_size=0.08", fill=False, lw=grueso))
        ax.text(px, py + 0.12, et, ha="center", va="center", fontsize=7.4, fontweight="bold")
        detalle = n.tipo + (f" · {lugares[et]}" if et in lugares else "")
        ax.text(px, py - 0.15, detalle, ha="center", va="center", fontsize=6.6)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.autoscale_view()
    ruta = os.path.join(FIG, "fig_diseno_arbol.png")
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
    ("PROYECTO INTEGRADOR – FASE 2: DISEÑO DEL COMPILADOR", portada_b, 14),
    ("EmoLang", ParagraphStyle("pn", parent=portada_b, fontSize=19, leading=24), 22),
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

# ================================================================== ÍNDICE
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
titulo("1. Alcance del prototipo")
p(f"El prototipo compila un programa EmoLang (extensión {c('.emo')}) a un archivo {c('.emoc')} y lo ejecuta "
  "en tiempo real, en CPU, con un solo rostro frente a una cámara RGB. Cumple el objetivo del anteproyecto: "
  "los gestos y los estados se traducen a autómatas finitos, y las condiciones y acciones a cuádruplas.")
subtitulo("1.1 Qué incluye y qué no")
tabla([
    ["Incluido en el prototipo", "Fuera del prototipo"],
    ["Uno o varios dominios por archivo; se ejecuta uno a la vez", "Importar o combinar varios archivos"],
    ["Un rostro frente a una cámara RGB", "Varios rostros o varias cámaras"],
    ["Módulos de dominio: conducción y rehabilitación", "Otros módulos con acciones propias"],
    [f"{len(METRICAS)} métricas faciales predefinidas (1.4)", "Métricas nuevas o modelos de visión propios"],
    ["Funciones predefinidas (1.4)", "Funciones definidas por el usuario"],
    ["Ejecución en CPU; el ritmo de la cámara se normaliza al fps del programa", "GPU, celular o hardware embebido"],
    ["Mensajes de error con línea y columna; varios errores por compilación", "Corrección automática de errores"],
], [1, 1])
subtitulo("1.2 Tipos de datos")
tabla([
    ["Tipo", "Ejemplo", "Descripción"],
    ["int", "30", "Número entero"],
    ["decimal", "0.5", "Número con punto decimal"],
    ["bool", "verdadero, falso", "Valor lógico"],
    ["string", '"Mire al frente"', "Texto"],
    ["duracion", "500 ms, 1.5 s", "Tiempo; se guarda en milisegundos al compilar"],
    ["proporcion", "0.21, 60%", "Valor entre 0 y 1; 60% se guarda como 0.6"],
    ["gesto", "gesto bostezo = mar > umbral durante 1.5 s;", "Condición sostenida en el tiempo; se compila a un AFD"],
    ["secuencia", "secuencia fatiga = [bostezo, cabeceo] en 10 s;", "Hasta 5 gestos en orden, dentro de una ventana; se compila a un AFD"],
], [1.3, 4, 4.4], codigo_en=(0, 1))
p(f"Conversiones implícitas: {c('int')} a {c('decimal')}, {c('decimal')} a {c('proporcion')} y viceversa (si el "
  f"valor es constante se verifica que esté entre 0 y 1). {c('1 s')} equivale a {c('1000 ms')}. No se permite "
  f"{c('decimal')} a {c('int')} ni un número sin unidad como duración.")
subtitulo("1.3 Estructuras de control")
tabla([
    ["Estructura", "Sintaxis", "Uso"],
    ["Condicional", "si c { … } sino { … }", "Ejecuta un bloque u otro según la condición"],
    ["Ciclo con número fijo", "repetir N veces { … }", "Repite el bloque N veces dentro del cuadro"],
    ["Ciclo por cuadro", "mientras c { … }", "Se declara en un estado; se revisa una vez por cuadro y no bloquea"],
    ["Máquina de estados", "maquina, inicial, estado", "Define los estados y el estado de inicio"],
    ["Transiciones", "cuando g ir_a E; ir_a E; cuando tras D ir_a E;", "Cambio de estado por un evento, desde un bloque o por tiempo"],
    ["Bloques de estado", "al_entrar { … } cuando g { … }", "Lo que se hace al entrar y al ocurrir un evento"],
    ["Evento sin efecto", "ignorar g;", "Declara que el estado no reacciona a g a propósito"],
], [2.4, 4.3, 5], codigo_en=(1,))
subtitulo("1.4 Métricas y acciones")
filas = [["Métrica", "Tipo", "Qué mide"]]
for m in METRICAS.values():
    filas.append([m.nombre, m.tipo, m.descripcion])
tabla(filas, [1.4, 1.4, 7], codigo_en=(0, 1))
p(f"La métrica {c('ear')} sigue a Soukupová y Čech (2016) y {c('perclos')} a Wierwille et al. (1994). El dominio de una "
  "función se revisa al compilar, según el nombre del dominio.")
tabla([
    ["Función", "Dominio", "Qué hace"],
    ["alarma(m), detener_alarma()", "conducción", "Activa la alarma con el mensaje m; la apaga"],
    ["contar_repeticion(), repeticiones()", "rehabilitación", "Cuenta una repetición con su simetría; devuelve cuántas van"],
    ["registrar(m)", "ambos", "Agrega m a la bitácora, que se exporta a CSV"],
    ["mostrar(a, b, …)", "ambos", "Muestra uno o más valores"],
    ["tiempo_en_estado()", "ambos", "Tiempo desde que se entró al estado actual"],
    ["abs, a_porcentaje, a_proporcion, a_ms, a_s", "ambos", "Valor absoluto y conversiones explícitas"],
], [4.2, 1.6, 5], codigo_en=(0,))

# ================================================================== 2
titulo("2. Gramática libre de contexto (GLC)")
p("EmoLang se define con la gramática G = (N, T, P, S), donde S = &lt;programa&gt;, N son los símbolos entre "
  "&lt; &gt; y T son los componentes léxicos de 2.1. El analizador léxico es un AFD escrito a mano que aplica "
  "la regla del lexema más largo.")
subtitulo("2.1 Componentes léxicos (T)")
tabla([
    ["Token", "Patrón", "Ejemplos"],
    ["Palabras reservadas", "Lista fija",
     "dominio sensor usar var gesto secuencia maquina inicial estado al_entrar cuando ignorar ir_a tras durante "
     "hasta tolerando en si sino mientras repetir veces int decimal bool string duracion proporcion verdadero falso y o no ms s"],
    ["ID", "Letra o _, seguida de letras, dígitos o _", "umbral_ojo, alertas, ear"],
    ["ENTERO", "Dígitos", "30"],
    ["DECIMAL", "Dígitos, punto y dígitos", "0.21"],
    ["Unidades", "ms, s y %, juntas o separadas del número", "500ms, 1.5 s, 60%"],
    ["CADENA", "Texto entre comillas dobles, en una línea", '"¡Despierte!"'],
    ["Comparación", "&lt;, &gt;, &lt;=, &gt;=, ==, !=", "ear < 0.2"],
    ["Operadores", "+, -, *, /, =", "alertas + 1"],
    ["Delimitadores", "{ } ( ) [ ] , ; :", ""],
    ["Comentarios (se descartan)", "// hasta fin de línea y /* bloque */", "// umbrales"],
], [2.2, 3.2, 5], codigo_en=(2,))
p(f"Las métricas y las funciones no son palabras reservadas: el analizador léxico las entrega como {c('ID')} y el "
  "semántico las resuelve en la tabla de símbolos. Por eso una variable no puede llamarse como una métrica.")
subtitulo("2.2 Producciones (P)")
listado("""\
 1 <programa>    → <dominio>+
 2 <dominio>     → dominio ID { <miembro>* }
 3 <miembro>     → <sensor> | <decl> | <gesto> | <secuencia> | <maquina>
 4 <sensor>      → sensor ID { ( usar <ids> ; | <decl> )* }
 5 <ids>         → ID ( , ID )*
 6 <decl>        → var ID : <tipo> = <expr> ;
 7 <tipo>        → int | decimal | bool | string | duracion | proporcion | gesto | secuencia
 8 <gesto>       → gesto ID = <expr> durante <expr> ( hasta <expr> )? ( tolerando <expr> )? ;
 9 <secuencia>   → secuencia ID = [ <ids> ] ( en <expr> )? ;
10 <maquina>     → maquina ID inicial ID { <estado>+ }
11 <estado>      → estado ID { <miembro_e>* }
12 <miembro_e>   → <decl>
                 | al_entrar <bloque>
                 | cuando ID ir_a ID ;
                 | cuando ID <bloque>
                 | cuando tras <expr> ir_a ID ;
                 | mientras <expr> <bloque>
                 | ignorar <ids> ;
13 <bloque>      → { <sentencia>* }
14 <sentencia>   → <decl> | ID = <expr> ; | <si> | repetir <expr> veces <bloque>
                 | ir_a ID ; | <llamada> ;
15 <si>          → si <expr> <bloque> ( sino ( <si> | <bloque> ) )?
16 <expr>        → <conj> ( o <conj> )*
17 <conj>        → <neg> ( y <neg> )*
18 <neg>         → no <neg> | <rel>
19 <rel>         → <suma> ( ( < | <= | > | >= | == | != ) <suma> )?
20 <suma>        → <term> ( ( + | - ) <term> )*
21 <term>        → <unario> ( ( * | / ) <unario> )*
22 <unario>      → - <unario> | <primario>
23 <primario>    → ( ENTERO | DECIMAL ) ( ms | s | % )? | CADENA | verdadero | falso
                 | ID | <llamada> | ( <expr> )
24 <llamada>     → ID ( ( <expr> ( , <expr> )* )? )""")
p(f"{c('X*')} significa cero o más veces, {c('X+')} una o más y {c('X?')} opcional. Son abreviaturas: por ejemplo, "
  f"{c('<decl>*')} equivale a {c('<decls> → <decl> <decls> | ε')}, así que la gramática sigue siendo libre de "
  "contexto. Las producciones 16 a 22 dan la precedencia, de mayor a menor: signo, luego * y /, + y -, las "
  f"comparaciones, {c('no')}, {c('y')} y al final {c('o')}. La recursión izquierda se escribe como repetición porque "
  f"el analizador es descendente recursivo. La gramática es LL(1), salvo en {c('<sentencia>')} con {c('ID')}: un token "
  f"más decide entre asignación y llamada. {c('gesto')} y {c('secuencia')} como tipo de una variable se aceptan en la "
  "sintaxis y los rechaza el análisis semántico, con un mensaje que indica cómo declararlos.")
subtitulo("2.3 Programa de ejemplo")
numerado = "\n".join(f"{i:02d} {l}" for i, l in enumerate(FUENTE.splitlines(), 1))
p("Todos los ejemplos del documento usan este programa, que es el archivo "
  f"{c('ejemplos/conduccion.emo')} del proyecto. Los umbrales se ajustaron con las pruebas de cámara del equipo.")
listado(numerado, "Listado 1. Detección de fatiga (dominio conducción).")

# ================================================================== 3
titulo("3. Reglas semánticas dirigidas por la sintaxis")
p("El analizador sintáctico construye el árbol de sintaxis abstracta (AST). Después, dos recorridos aplican las "
  "reglas: el análisis semántico revisa tipos y nombres; el generador de código intermedio emite las cuádruplas. "
  "Se separan porque los nombres de los estados, gestos y secuencias pueden usarse antes de declararse.")
subtitulo("3.1 Atributos")
tabla([
    ["Atributo", "Significado"],
    [".tipo", "Tipo del resultado (int, decimal, bool, …). Si hubo un error, queda vacío para no repetir mensajes"],
    [".lugar", "Dónde queda el valor: una variable, una constante o un temporal (t1, t2, …)"],
    [".valor", "Valor de una constante ya convertido: milisegundos o proporción de 0 a 1"],
    [".linea, .columna", "Posición en el archivo, para los mensajes de error"],
], [1.3, 8], codigo_en=(0,))
subtitulo("3.2 Esquema de traducción")
tabla([
    ["Producción", "Regla semántica"],
    ["<decl> → var ID : <tipo> = <expr> ;", f"ID no debe existir en el ámbito actual y el tipo de {c('<expr>')} debe ser asignable a {c('<tipo>')}. Se inserta ID en la tabla de símbolos y se emite {c('(=, <expr>.lugar, –, ID)')} en el bloque init o al_entrar que corresponda"],
    ["<sentencia> → ID = <expr> ;", f"ID debe existir y ser una variable; una métrica no se puede asignar. Se emite {c('(=, <expr>.lugar, –, ID)')}"],
    ["<suma> → <suma>₁ + <term>", f"El tipo se calcula con las reglas de 3.3. Se crea un temporal t y se emite {c('(+, <suma>.lugar, <term>.lugar, t)')}. Si un operando es string, se emite texto y concat"],
    ["<term> → <term>₁ * <unario>", "Igual que la suma, con *"],
    ["<rel> → <suma>₁ OP <suma>₂", f"Los dos lados deben poder compararse. El resultado es bool y se emite {c('(OP, <suma>₁.lugar, <suma>₂.lugar, t)')}"],
    ["<primario> → ID", "Se busca ID en la tabla; su tipo y su lugar pasan a la pila. Si es una métrica, debe estar en usar"],
    ["<primario> → NUM ms | NUM s", "El valor se guarda en milisegundos desde el análisis sintáctico; se usa como constante"],
    ["<primario> → NUM %", "El valor se guarda como n / 100 y no puede pasar de 1"],
    ["<gesto> → gesto ID = <expr> durante …", f"{c('<expr>')} debe ser bool y sin llamadas; las duraciones, constantes. Se construye el AFD del gesto y se emite {c('(afd, <expr>.lugar, –, ID)')} en el bloque gestos"],
    ["<secuencia> → secuencia ID = [ <ids> ] …", f"Cada nombre debe ser un gesto, de 1 a 5. Con uno solo se advierte. Se construye el AFD (KMP) y se emite {c('(sec, –, –, ID)')}"],
    ["<si> → si <expr> <bloque> sino <bloque>", f"{c('<expr>')} debe ser bool. Se emite un gotoF hacia el sino y un goto hacia el final"],
    ["<miembro_e> → mientras <expr> <bloque>", f"{c('<expr>')} debe ser bool. Crea un bloque propio; se emite un gotoF hacia su final. No hay salto de regreso: se revisa una vez por cuadro"],
    ["<sentencia> → repetir <expr> veces <bloque>", f"{c('<expr>')} debe ser int. Se emite un contador, su comparación y un salto de regreso. Si no es constante, además se emite chk_rep"],
    ["<llamada> → ID ( … )", f"La función debe existir, recibir los tipos que pide y estar permitida en el dominio. Se emite un {c('param')} por argumento y {c('(call, ID, n, t)')}"],
    ["<estado> → estado ID { … }", "Se abre su ámbito; sus variables se reinician cada vez que se entra al estado"],
    ["<maquina> → maquina ID inicial ID { … }", "El estado inicial debe existir. Los estados se insertan antes de revisarlos, porque un ir_a puede nombrar uno declarado después"],
    ["<miembro_e> → cuando ID …", "ID debe ser un gesto o secuencia y el destino un estado de la misma máquina"],
    ["<miembro_e> → cuando tras <expr> ir_a ID ;", "La duración debe ser constante y mayor que cero. Se agrega a la tabla de despacho del estado"],
], [4, 6.4], codigo_en=(0,), juntar=False)
subtitulo("3.3 Reglas de tipos")
tabla([
    ["Operación", "Resultado"],
    ["int + int, int - int, int * int", "int"],
    ["int + decimal, decimal + proporcion y demás mezclas numéricas", "decimal"],
    ["número / número", "decimal"],
    ["duracion + duracion, duracion - duracion", "duracion"],
    ["duracion * número, duracion / número", "duracion"],
    ["duracion / duracion", "decimal"],
    ["string + cualquier tipo", "string"],
    ["Comparación entre números o entre duraciones", "bool"],
    ["== y != entre dos string o dos bool", "bool"],
    ["y, o, no", "Solo con bool; el resultado es bool"],
    ["Cualquier otra combinación", "Error de tipo"],
], [6.5, 3.5], codigo_en=())
subtitulo("3.4 Verificaciones semánticas")
p("Los mensajes de esta tabla son los que produce el compilador con cada ejemplo.")
est_b = "estado a { cuando g ir_a a; }"
gesto_ok = "gesto g = ear < 0.2 durante 1 s;"
casos = [
    ("Variable no declarada", "alertas = velocidad;", programa_prueba("", "estado a { al_entrar { alertas = velocidad; } }")),
    ("Declarada dos veces en el mismo ámbito", "dos var alertas", programa_prueba("var alertas : int = 1;")),
    ("Tipos incompatibles", 'alertas = "hola";', programa_prueba("", 'estado a { al_entrar { alertas = "hola"; } }')),
    ("Asignar a una métrica", "ear = 0.5;", programa_prueba("", "estado a { al_entrar { ear = 0.5; } }")),
    ("Métrica no habilitada en usar", "sonrisa con usar ear, mar", programa_prueba("gesto g = sonrisa > 0.5 durante 1 s;", est_b)),
    ("Umbral fuera de rango", "mar > 120%", programa_prueba("gesto g = mar > 120% durante 1 s;", est_b)),
    ("Gesto imposible", "ear < 0.2 y ear > 0.3", programa_prueba("gesto g = ear < 0.2 y ear > 0.3 durante 1 s;", est_b)),
    ("Duración sin unidad", "durante 5", programa_prueba("gesto g = ear < 0.2 durante 5;", est_b)),
    ("Secuencia demasiado larga", "seis gestos", programa_prueba(gesto_ok + " secuencia s1 = [g, g, g, g, g, g];", "estado a { cuando s1 ir_a a; }")),
    ("Transiciones contradictorias", "dos cuando g a destinos distintos", programa_prueba(gesto_ok, "estado a { cuando g ir_a b; cuando g ir_a c; } estado b { } estado c { }")),
    ("Estado inalcanzable", "b sin transición que llegue", programa_prueba("", "estado a { } estado b { }")),
    ("Estado inicial inexistente", "inicial z", f"dominio conduccion {{ sensor camara {{ var fps : int = 30; }} maquina m inicial z {{ estado a {{ }} }} }}"),
    ("Acción fuera de su dominio", "alarma en rehabilitacion", programa_prueba("", 'estado a { al_entrar { alarma("x"); } }', dominio="rehabilitacion")),
]
filas = [["Verificación", "Ejemplo", "Mensaje del compilador"]]
for nombre, ej, fuente in casos:
    filas.append([nombre, ej, escape(error_real(fuente))])
tabla(filas, [2.6, 2.6, 5.2], codigo_en=(1,), juntar=False)
p("Además, el compilador emite advertencias que no impiden compilar: umbrales atípicos, gestos sin usar, condiciones "
  f"siempre verdaderas y eventos atendidos en unos estados pero olvidados en otros sin declararlos con {c('ignorar')}. "
  "Para detectar gestos imposibles, la condición se lleva a forma normal disyuntiva sobre intervalos por métrica y se "
  "interseca con el rango válido de cada una. Los estados inalcanzables se detectan con un recorrido en anchura desde "
  "el estado inicial.")

# ================================================================== 4
titulo("4. Construcción de árboles de expresión")
ln_cab = GESTO_CABECEO.linea
texto_cond = A.texto_expr(GESTO_CABECEO.condicion)
p(f"El analizador sintáctico arma un árbol por cada expresión: primero las hojas y luego cada operador con sus "
  f"hijos. El análisis semántico recorre el árbol y le asigna a cada nodo su tipo con las reglas de 3.3. "
  f"Ejemplo con la condición de la línea {ln_cab} del Listado 1, {c(texto_cond)}:")
numerada([
    f"{c('hoja(pitch)')}: decimal, tomado de la tabla de símbolos",
    f"{c('hoja(cabeceo_grados)')}: decimal, tomado de la tabla de símbolos",
    f"{c('nodo(>, pitch, cabeceo_grados)')}: bool, porque es una comparación entre números",
    f"{c('hoja(ear)')}: proporcion, tomado de la tabla de símbolos",
    f"{c('hoja(0.27)')}: decimal",
    f"{c('nodo(<, ear, 0.27)')}: bool, porque es una comparación entre números",
    f"{c('nodo(y, >, <)')}: bool, porque los dos operandos son bool",
])
cuads_cab = PROG.bloques["gestos"]
lugares = {}
for q in cuads_cab:
    if q.op == "afd" and q.res == "cabeceo":
        i = cuads_cab.index(q)
        lugares = {cuads_cab[i - 1].op: cuads_cab[i - 1].res, cuads_cab[i - 2].op: cuads_cab[i - 2].res,
                   cuads_cab[i - 3].op: cuads_cab[i - 3].res}
        posorden = [cuads_cab[i - 3], cuads_cab[i - 2], cuads_cab[i - 1]]
figura(figura_arbol(GESTO_CABECEO.condicion, lugares), f"Figura 1. Árbol de expresión de la línea {ln_cab}", ancho_cm=12.5)
p(f"Las comparaciones quedan más abajo que {c('y')}, por eso se calculan primero. Al recorrer el árbol en posorden "
  f"({c('pitch cabeceo_grados > ear 0.27 < y')}) salen las cuádruplas {c(posorden[0])}, {c(posorden[1])} y "
  f"{c(posorden[2])} del bloque gestos (sección 7.2).")

# ================================================================== 5
titulo("5. Pila semántica")
p("La pila semántica guarda el lugar y el tipo de cada parte ya reconocida de una expresión. La usa el generador "
  f"de código intermedio ({c('emolang/intermedio.py')}) mientras recorre el árbol en posorden.")
subtitulo("5.1 Funcionamiento")
numerada([
    "Al llegar a una hoja, mete en la pila su lugar y su tipo.",
    "Al llegar a un operador, saca sus operandos, emite la cuádrupla con el tipo que ya calculó el análisis semántico y mete el temporal del resultado.",
    "Al terminar la expresión, la pila queda con un solo elemento: el lugar del resultado. Lo saca quien la pidió (una asignación, un gesto, un si).",
])
p("Los errores de tipo se detectan antes, en el análisis semántico: el nodo con error queda sin tipo para no repetir "
  "el mensaje, y si hay errores no se genera código.")
subtitulo(f"5.2 Ejemplo con la línea {ln_cab}")
p(f"La tabla es la traza que registra el generador para {c(texto_cond)}. Cada entrada de la pila es (lugar, tipo) y "
  "el tope está a la derecha.")
filas = [["Paso", "Qué hace el generador", "Pila semántica", "Cuádrupla emitida"]]
for i, paso in enumerate(PROG.trazas[ln_cab], 1):
    pila = "[" + ", ".join(f"({l}, {t})" for l, t in paso["pila"]) + "]"
    filas.append([i, escape(paso["accion"]), pila, paso["cuadrupla"]])
tabla(filas, [1.1, 4, 5, 3], codigo_en=(2, 3))

# ================================================================== 6
titulo("6. Tabla de símbolos")
p("La tabla guarda cada nombre declarado. Los ámbitos, del más externo al más interno, son: <b>global</b> (métricas y "
  "funciones), <b>dominio</b> (variables del dominio y de sus sensores, gestos, secuencias y máquinas), <b>máquina</b> "
  "(estados), <b>estado</b> (variables locales) y <b>bloque</b> (variables declaradas dentro de llaves). Un nombre se "
  "busca del ámbito actual hacia afuera. Las variables de un sensor se guardan en el ámbito del dominio con la etiqueta "
  "de su sensor. Tabla final del Listado 1:")
filas = [["Nombre", "Categoría", "Tipo", "Ámbito", "Valor o dato", "Línea"]]
usadas = sorted(DOM.habilitadas)
sensor_nodo = DOM.nodo.sensores[0]
datos_gesto = {a.nombre: a for a in R.automatas["conduccion"]}
for s in R.analisis.tabla:
    v = ""
    if s.categoria == "variable":
        v = repr(s.valor) if not isinstance(s.valor, float) else f"{s.valor:g}"
    elif s.categoria == "gesto":
        d = datos_gesto[s.nombre].descripcion
        v = f"{d['durante_ms']:g} ms"
        if d["hasta_ms"]:
            v += f" a {d['hasta_ms']:g} ms"
        if d["tolerancia_ms"]:
            v += f"; tolera {d['tolerancia_ms']:g} ms"
    elif s.categoria == "secuencia":
        d = datos_gesto[s.nombre].descripcion
        v = f"{', '.join(d['patron'])}; {d['ventana_ms']:g} ms"
    elif s.categoria == "maquina":
        v = f"inicial: {s.nodo.inicial}"
    filas.append([s.nombre, s.categoria, s.tipo, s.ambito, v, s.linea])
for m in usadas:
    me = METRICAS[m]
    filas.append([m, "métrica", me.tipo, "global", f"{me.minimo:g} a {me.maximo:g}; habilitada en usar", sensor_nodo.usar[0].linea])
tabla(filas, [2.5, 1.5, 1.8, 2.6, 3.2, 0.9], codigo_en=(0,), juntar=False)

# ================================================================== 7
titulo("7. Cuádruplas")
b_alerta, b_mientras, b_somn, b_term = "alerta.al_entrar", "normal.mientras.1", "somnoliento.mientras.1", "terminado.al_entrar"
p("Cada cuádrupla tiene la forma (operador, arg1, arg2, resultado). Las genera el compilador por bloques: "
  f"{c('init')} con las variables, {c('gestos')} con las condiciones, y por cada estado sus bloques {c('al_entrar')}, "
  f"{c('cuando')} y {c('mientras')}. Los temporales ({c('t1, t2, …')}) vuelven a empezar en cada bloque. Una variable local "
  f"se escribe con su estado, como {c('normal.parpadeos')}. Las duraciones y "
  f"los porcentajes ya llegan convertidos: el analizador sintáctico guarda {c('1.5 s')} como {c('1500')} y {c('33%')} "
  f"como {c('0.33')}. Para ver las de cualquier programa: {c('python -m emolang cuadruplas archivo.emo --sin-optimizar')}.")
subtitulo(f"7.1 Bloque init: variables (líneas {linea_de('var fps')} a {linea_de('var alertas')})")
tabla_cuadruplas(PROG.bloques["init"])
subtitulo(f"7.2 Bloque gestos (líneas {linea_de('gesto parpadeo')} a {linea_de('secuencia fatiga')})")
p(f"Se ejecuta en cada cuadro. Solo calcula las condiciones: el tiempo lo cuenta el autómata de cada gesto (7.6). "
  f"Por eso no hay un temporizador en las cuádruplas, y una cláusula como {c('tolerando 100 ms')} no genera ninguna.")
tabla_cuadruplas(PROG.bloques["gestos"])
subtitulo(f"7.3 Bloque al_entrar del estado alerta (líneas {linea_de('alertas = alertas + 1')} a {linea_de('Se recomienda') + 1})")
tabla_cuadruplas(PROG.bloques[b_alerta])
subtitulo(f"7.4 Bloques mientras (líneas {linea_de('mientras perclos')} y {linea_de('mientras tiempo_en_estado')})")
p("Un mientras no tiene salto de regreso. El siguiente cuadro vuelve a ejecutar el bloque desde el inicio, así que "
  "nunca detiene el procesamiento del video.")
tabla_cuadruplas(PROG.bloques[b_mientras], "Bloque mientras del estado normal")
tabla_cuadruplas(PROG.bloques[b_somn], "Bloque mientras del estado somnoliento")
subtitulo("7.5 Un ciclo repetir")
p(f"El Listado 1 no usa {c('repetir')}. Este bloque es el {c('al_entrar')} del estado terminado de "
  f"{c('ejemplos/rehabilitacion.emo')}, que contiene {c('repetir 3 veces')}. El contador {c('c1')} solo existe en este nivel.")
tabla_cuadruplas(PROG_R.bloques[b_term])
subtitulo("7.6 Relación con los autómatas")
p("El anteproyecto pide traducir gestos y estados a autómatas finitos con tabla de transiciones y diagrama. Las "
  f"cuádruplas {c('afd')} y {c('sec')} son la unión entre ambas partes. Un gesto se compila a un AFD sobre el alfabeto "
  f"{{1, 0}}, donde {c('q_i')} significa que la condición lleva i cuadros. La duración se discretiza con el fps: "
  f"{c('N = techo(durante / periodo)')}. Las secuencias usan un AFD construido con el algoritmo KMP y las máquinas de estado se "
  f"traducen directamente, con {c('λ')} para las transiciones espontáneas. {c('python -m emolang compilar')} genera todas "
  "las tablas y los diagramas.")
figura(os.path.join(FIG, "fig_afd_gesto.png"), "Figura 2. AFD de un gesto de tres cuadros; la transición marcada emite el evento g", ancho_cm=15)
fatiga = datos_gesto["fatiga"]
filas = [["δ", *fatiga.alfabeto]]
celdas = {(t.origen, t.simbolo): t.destino + (f" / {t.salida}" if t.salida else "") for t in fatiga.transiciones}
for q in fatiga.estados:
    marca = ("→ " if q == fatiga.inicial else "") + ("* " if q in fatiga.aceptacion else "")
    filas.append([marca + q, *[celdas[(q, s)] for s in fatiga.alfabeto]])
tabla(filas, [2, 3, 3], codigo_en=(0, 1, 2), rotulo="Tabla de transiciones de la secuencia fatiga (→ inicial, * aceptación, / evento emitido)")
monitor = datos_gesto["monitor"]
filas = [["Estado", "Evento", "Destino", "Condición"]]
for t in monitor.transiciones:
    filas.append([t.origen, t.simbolo, t.destino, t.guarda or ""])
tabla(filas, [2, 2.4, 2, 5.4], codigo_en=(0, 1, 2, 3), rotulo="Transiciones de la máquina monitor (λ = espontánea)", juntar=False)

# ================================================================== 8
titulo("8. Técnicas de optimización")
ant, des = sum(INF.antes.values()), sum(INF.despues.values())
ant_r, des_r = sum(INF_R.antes.values()), sum(INF_R.despues.values())
p(f"El optimizador aplica seis técnicas sobre las cuádruplas de la sección 7, hasta que ya ninguna produce cambios. "
  f"El Listado 1 baja de {ant} a {des} cuádruplas y {c('ejemplos/rehabilitacion.emo')} de {ant_r} a {des_r}. "
  "Las reutilizaciones de subexpresiones se limitan a un mismo bloque, porque los temporales no se conservan entre bloques.")
subtitulo("8.1 Técnicas")
ej_prop = primer_ejemplo("propagacion", INF)
ej_plg = next(e for e in INF.ejemplos["plegado"])
ej_sub = primer_ejemplo("subexpresiones", INF)
ej_mir = next(e for e in INF.ejemplos["mirilla"] if "alertas" in e[0])
ej_mue = next(e for e in INF.ejemplos["muerto"] if "parpadeos" in e[0])
ej_des = primer_ejemplo("desenrollado", INF_R)
tabla([
    ["Técnica", "Qué hace", "Ejemplo real", "Veces"],
    ["Propagación de constantes", "Cambia una variable con una sola escritura constante por su valor",
     f"{c(ej_prop[0])} queda {c(ej_prop[1])}", INF.aplicaciones["propagacion"]],
    ["Plegado de constantes", "Calcula al compilar las operaciones que solo tienen constantes",
     f"{c(ej_plg[0])} queda {c(ej_plg[1])}", INF.aplicaciones["plegado"]],
    ["Eliminación de subexpresiones comunes", "Reutiliza una operación ya calculada en el bloque",
     f"{c(ej_sub[0])}: {ej_sub[1]}", INF.aplicaciones["subexpresiones"]],
    ["Eliminación de código muerto", "Quita lo que no afecta al resultado: escrituras que nadie lee, código inalcanzable, gestos y secuencias sin uso",
     f"{c(ej_mue[0])}: {ej_mue[1]}", INF.aplicaciones["muerto"]],
    ["Mirilla", "Une una operación con la asignación que la sigue",
     f"{c(ej_mir[0])} queda {c(ej_mir[1])}", INF.aplicaciones["mirilla"]],
    ["Desenrollado de ciclos", "Cambia un repetir constante de hasta 4 vueltas por copias de su cuerpo",
     f"{ej_des[0]} queda en {ej_des[1]} (rehabilitación)", INF_R.aplicaciones["desenrollado"]],
], [2.3, 3.5, 4.5, 1.1])
p(f"La columna Veces cuenta las aplicaciones en el Listado 1; el desenrollado, en rehabilitación. La variable "
  f"{c('parpadeos')} es un caso que vale la pena revisar: se incrementa, pero nada la lee, así que el optimizador quita esa "
  f"suma y el bloque {c('normal.cuando.parpadeo')} queda vacío. El evento sigue detectándose. Un gesto sin uso también se "
  f"elimina al ejecutar, salvo en {c('emolang evaluar')}, que necesita medir todos los gestos declarados.")
subtitulo("8.2 Resultado por bloque")
filas = [["Bloque", "Antes", "Después"]]
for nombre in INF.antes:
    filas.append([nombre, INF.antes[nombre], INF.despues[nombre]])
filas.append(["Total", ant, des])
tabla(filas, [6, 1.2, 1.2], codigo_en=(0,))
subtitulo("8.3 Bloque gestos optimizado")
tabla_cuadruplas(OPT.bloques["gestos"])
subtitulo("8.4 Bloque al_entrar de alerta optimizado")
tabla_cuadruplas(OPT.bloques[b_alerta])
subtitulo("8.5 Ciclo repetir desenrollado")
n_ant_ciclo = 3 * 6 + 3
p(f"El {c('repetir 3 veces')} del bloque de 7.5 ejecutaba {n_ant_ciclo} cuádruplas del ciclo: la inicialización, seis "
  "por vuelta y las dos de la última comparación. Ahora ejecuta seis, sin contador ni saltos.")
tabla_cuadruplas(OPT_R.bloques[b_term])
subtitulo("8.6 Comprobación")
n_pruebas = contar_pruebas()
p(f"Una optimización no debe cambiar lo que hace el programa. El proyecto tiene {n_pruebas} pruebas automáticas; las de "
  f"equivalencia ejecutan los dos programas de ejemplo en 30 corridas simuladas, con 5 semillas, ruido normal y triple. "
  "En cada corrida comparan el intérprete directo del árbol, EmoVM sin optimizar y EmoVM optimizada. Las tres deben "
  "producir la misma bitácora, la misma salida y los mismos estados en cada cuadro.")

# ================================================================== 9
titulo("9. Plataforma y arquitectura")
p(f"EmoLang compila a un archivo {c('.emoc')} con los autómatas, la tabla de despacho de los estados y las cuádruplas. "
  "Ese archivo lo ejecuta una máquina virtual propia, EmoVM, escrita en Python, en una computadora con CPU y cámara web.")
subtitulo("9.1 Elección de la plataforma")
tabla([
    ["Opción", "A favor", "En contra", "Decisión"],
    ["Código nativo x86-64", "Mayor rendimiento", "Habría que conectar MediaPipe y la cámara desde C/C++; no cabe en el semestre", "Descartada"],
    ["Traducir EmoLang a Python", "Rápido de construir", "Las cuádruplas y los autómatas ya no se pueden mostrar ni revisar", "Descartada"],
    ["Máquina virtual propia (EmoVM)", "Se integra directo con MediaPipe; las cuádruplas y los autómatas se pueden mostrar y probar", "Más lenta que el código nativo, pero suficiente: ver abajo", "Elegida"],
], [2.6, 3.5, 3.5, 1.4])
media, p95 = latencia()
p(f"En la prueba simulada del Listado 1, EmoVM tardó en promedio {media:.3f} ms por cuadro (p95 de {p95:.3f} ms), de "
  "los 33.3 ms disponibles a 30 fps. Esa medición no incluye la extracción de puntos faciales de MediaPipe. En las "
  "pruebas con la cámara del equipo se obtuvieron unos 10 fps, y el sistema regulariza el ritmo para que "
  f"{c('durante 1 s')} siga significando un segundo.")
subtitulo("9.2 Arquitectura")
figura(figura_arquitectura(), "Figura 3. Arquitectura del compilador y de la máquina virtual", ancho_cm=15.5)
p(f"La columna izquierda se ejecuta una vez, al compilar. La derecha se ejecuta en cada cuadro de video. El archivo "
  f"{c('.emoc')} que escribe el generador es lo que carga la máquina virtual.")
subtitulo("9.3 Tecnologías")
tabla([
    ["Componente", "Tecnología"],
    ["Lenguaje de implementación", "Python 3.11 con cámara (MediaPipe no soporta 3.13 o posterior); el compilador funciona desde Python 3.10"],
    ["Análisis léxico y sintáctico", "Escritos a mano: AFD y descendente recursivo, sin generador"],
    ["Captura de video", "OpenCV"],
    ["Puntos faciales", "MediaPipe Face Landmarker"],
    ["Cálculo de métricas", "NumPy"],
    ["Diagrama de los autómatas", "Mermaid y archivos DOT de Graphviz, generados por el compilador"],
    ["Sonido de la alarma", "winsound de Python en Windows; aviso de la terminal en otros sistemas"],
    ["Equipo", "Laptop x86-64 sin GPU dedicada, con cámara web"],
], [3, 7])
p("El analizador se escribió a mano y no con PLY u otro generador porque así cada fase se puede revisar y explicar "
  "directamente, se controlan los mensajes de error y la recuperación en modo pánico, y el compilador no depende de "
  "otra biblioteca. Una gramática LL(1) como esta se presta bien a ese método.")

titulo("Referencias")
for r_txt in [
    "Aho, A. V., Lam, M. S., Sethi, R. y Ullman, J. D. (2008). <i>Compiladores: principios, técnicas y herramientas</i> (2.ª ed.). Pearson Educación.",
    "Knuth, D. E., Morris, J. H. y Pratt, V. R. (1977). Fast pattern matching in strings. <i>SIAM Journal on Computing</i>, 6(2), 323-350.",
    "Louden, K. C. (2004). <i>Construcción de compiladores: principios y práctica</i>. Thomson.",
    "Lugaresi, C. et al. (2019). MediaPipe: A framework for building perception pipelines. arXiv:1906.08172.",
    "Soukupová, T. y Čech, J. (2016). Real-time eye blink detection using facial landmarks. <i>21st Computer Vision Winter Workshop</i>.",
    "Wierwille, W. W. et al. (1994). <i>Research on vehicle-based driver status/performance monitoring</i>. Reporte DOT HS 808 247, NHTSA.",
    "Google. MediaPipe Face Landmarker. Documentación oficial de MediaPipe Solutions.",
]:
    historia.append(Paragraph(r_txt, lista, bulletText="•"))

doc = Documento(SALIDA, pagesize=letter, leftMargin=2.5 * cm, rightMargin=2.5 * cm, topMargin=2.3 * cm,
                bottomMargin=2.3 * cm, title="EmoLang: Fase 2, Diseño del compilador",
                author="Equipo EmoLang, Grupo 7SB")
doc.multiBuild(historia, onFirstPage=lambda ca, d: None, onLaterPages=numero_pagina)
print(SALIDA)
