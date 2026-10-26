"""Genera reporte/EmoLang_Fase2_Desarrollo.pdf.

Uso (desde la raíz del proyecto):
    python reporte/capturas.py      # capturas de terminal
    python reporte/figuras.py       # diagramas
    python reporte/generar_reporte.py
"""

import os

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

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
FIG = os.path.join(AQUI, "figuras")
SALIDA = os.path.join(AQUI, "EmoLang_Fase2_Desarrollo.pdf")
FUENTES = r"C:\Windows\Fonts"

pdfmetrics.registerFont(TTFont("Arial", os.path.join(FUENTES, "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-B", os.path.join(FUENTES, "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial-I", os.path.join(FUENTES, "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Arial-BI", os.path.join(FUENTES, "arialbi.ttf")))
pdfmetrics.registerFont(TTFont("Consolas", os.path.join(FUENTES, "consola.ttf")))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-B", italic="Arial-I", boldItalic="Arial-BI")

ANCHO = letter[0] - 5 * cm

# ------------------------------------------------------------------ estilos
cuerpo = ParagraphStyle("cuerpo", fontName="Arial", fontSize=10.5, leading=15.5, alignment=TA_JUSTIFY,
                        spaceAfter=7)
lista = ParagraphStyle("lista", parent=cuerpo, leftIndent=16, bulletIndent=4, spaceAfter=3)
h1 = ParagraphStyle("h1", fontName="Arial-B", fontSize=12.5, leading=16, spaceBefore=16, spaceAfter=8,
                    keepWithNext=1)
h2 = ParagraphStyle("h2", fontName="Arial-B", fontSize=10.5, leading=14, spaceBefore=10, spaceAfter=5,
                    keepWithNext=1)
pie = ParagraphStyle("pie", fontName="Arial", fontSize=9, leading=12, alignment=TA_CENTER,
                     spaceBefore=4, spaceAfter=12)
codigo = ParagraphStyle("codigo", fontName="Consolas", fontSize=8.3, leading=10.6, leftIndent=12,
                        spaceBefore=2, spaceAfter=10)
celda = ParagraphStyle("celda", fontName="Arial", fontSize=8.8, leading=11.2, alignment=TA_LEFT)
celda_b = ParagraphStyle("celda_b", parent=celda, fontName="Arial-B")
portada = ParagraphStyle("portada", fontName="Arial", fontSize=12, leading=16, alignment=TA_CENTER)
portada_b = ParagraphStyle("portada_b", parent=portada, fontName="Arial-B")

historia = []
n_fig = [0]
n_tab = [0]


def p(texto, estilo=cuerpo):
    historia.append(Paragraph(texto, estilo))


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


def cod(texto):
    historia.append(Preformatted(texto.strip("\n"), codigo))


def figura(archivo, texto, ancho_cm=None, max_alto_cm=19):
    ruta = os.path.join(FIG, archivo)
    w, h = PILImage.open(ruta).size
    ancho = (ancho_cm * cm) if ancho_cm else ANCHO
    ancho = min(ancho, ANCHO)
    alto = ancho * h / w
    if alto > max_alto_cm * cm:
        alto = max_alto_cm * cm
        ancho = alto * w / h
    n_fig[0] += 1
    historia.append(KeepTogether([
        Image(ruta, width=ancho, height=alto),
        Paragraph(f"Figura {n_fig[0]}. {texto}", pie),
    ]))


def tabla(filas, anchos, texto=None, encabezado=True):
    datos = [[Paragraph(str(c), celda_b if (i == 0 and encabezado) else celda) for c in fila]
             for i, fila in enumerate(filas)]
    t = Table(datos, colWidths=[a * cm for a in anchos], repeatRows=1 if encabezado else 0)
    estilo = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, "black"),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, "black"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if encabezado:
        estilo.append(("LINEBELOW", (0, 0), (-1, 0), 0.5, "black"))
    t.setStyle(TableStyle(estilo))
    bloque = []
    if texto:
        n_tab[0] += 1
        bloque.append(Paragraph(f"Tabla {n_tab[0]}. {texto}", ParagraphStyle(
            "tt", parent=pie, spaceBefore=6, spaceAfter=4)))
    bloque.append(t)
    bloque.append(Spacer(1, 10))
    historia.append(KeepTogether(bloque))


def leer(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------ documento
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


def sin_numero(canvas, doc):
    pass


# ================================================================== PORTADA
historia.append(Image(os.path.join(FIG, "logo_tecnm.png"), width=3.6 * cm, height=3.6 * cm * 118 / 192,
                      hAlign="LEFT"))
historia.append(Spacer(1, 0.6 * cm))
for texto, estilo, despues in [
    ("TECNOLÓGICO NACIONAL DE MÉXICO", ParagraphStyle("pt", parent=portada_b, fontSize=14.5), 4),
    ("INSTITUTO TECNOLÓGICO DE OAXACA", portada_b, 22),
    ("MATERIA:", portada, 2),
    ("LENGUAJES Y AUTÓMATAS II", portada_b, 14),
    ("CLAVE DE MATERIA:", portada, 2),
    ("SCD1016", portada_b, 14),
    ("CARRERA:", portada_b, 2),
    ("INGENIERÍA EN SISTEMAS COMPUTACIONALES", portada, 26),
    ("PROYECTO INTEGRADOR – FASE 2: DESARROLLO (REPORTE DE AVANCE)", portada_b, 18),
    ("EmoLang", ParagraphStyle("pn", parent=portada_b, fontSize=17, leading=22), 26),
    ("ALUMNOS:", portada_b, 8),
    ("GARCIA GABRIEL BETSAIDA<br/>GINER COACHE NIERIKA<br/>JIMENEZ LOPEZ FERNANDO ARATH<br/>"
     "LEÓN RAMÍREZ CARLOS PAVEL<br/>ORTIZ MARTÍNEZ JOSÉ JULIÁN", portada, 24),
    ("NOMBRE DEL PROFESOR:", portada_b, 4),
    ("VELAZQUEZ HERNANDEZ MARICARMEN MONTSERRAT", portada, 14),
    ("<b>GRUPO</b>: 7SB", portada, 14),
    ("OAXACA DE JUÁREZ, OAXACA, OCTUBRE DE 2026", portada, 0),
]:
    historia.append(Paragraph(texto, estilo))
    historia.append(Spacer(1, despues))
historia.append(PageBreak())

# ================================================================== CONTENIDO
historia.append(Paragraph("Contenido", ParagraphStyle("hc", parent=h1, spaceBefore=0)))
indice = TableOfContents()
indice.levelStyles = [
    ParagraphStyle("t0", fontName="Arial", fontSize=9.8, leading=12.4, leftIndent=0, firstLineIndent=0,
                   spaceBefore=2),
    ParagraphStyle("t1", fontName="Arial", fontSize=9, leading=10.9, leftIndent=14, firstLineIndent=0),
]
indice.dotsMinLevel = 0
indice.tableStyle = TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("TOPPADDING", (0, 0), (-1, -1), 0.5),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)])
historia.append(indice)
historia.append(PageBreak())

# ================================================================== 1
titulo("1. Introducción")
p("Este documento reporta el avance de la segunda fase del proyecto integrador: el desarrollo de "
  "EmoLang, el lenguaje de dominio específico propuesto en el anteproyecto para describir gestos "
  "faciales como patrones temporales, validarlos y compilarlos a autómatas finitos que se ejecutan "
  "con una cámara convencional. Se describe lo implementado para cada objetivo específico, las "
  "pruebas realizadas con sus resultados y los cambios que surgieron respecto a la propuesta "
  "original. La sección 14 reúne los puntos que el equipo somete a revisión.")
p("Las ocho partes planteadas en los objetivos específicos tienen una primera versión funcional. El "
  "compilador procesa un programa completo y genera sus autómatas, y el motor de ejecución los "
  "evalúa en tiempo real con la cámara web. La evaluación con grabaciones de varios participantes "
  "(objetivo 8) tiene ya las herramientas y el protocolo, pero todavía no se realiza; los resultados "
  "cuantitativos de este reporte provienen de datos simulados y de pruebas con cámara hechas por un "
  "integrante del equipo.")
tabla([
    ["Objetivo específico", "Estado", "Archivos principales"],
    ["1. Sintaxis y gramática libre de contexto", "Implementado", "docs/gramatica.md"],
    ["2. Analizador léxico y sintáctico (AST)", "Implementado", "lexico.py, sintactico.py, nodos.py"],
    ["3. Analizador semántico (símbolos, ámbitos, tipos)", "Implementado", "semantico.py, tipos.py"],
    ["4. Validaciones propias del dominio", "Implementado", "validaciones.py"],
    ["5. Generador de autómatas (tabla y diagrama)", "Implementado", "automatas.py"],
    ["6. Motor de ejecución con MediaPipe", "Implementado; probado con cámara",
     "motor.py, ejecucion.py, camara.py"],
    ["7. Módulos de conducción y rehabilitación", "Implementado", "modulos.py"],
    ["8. Evaluación (exactitud, FP/FN, latencia)", "Simulada: hecha. Con participantes: pendiente",
     "evaluacion.py, captura.py, diagnostico.py"],
], [6.6, 4.4, 5.6], "Estado de los objetivos específicos.")

# ================================================================== 2
titulo("2. Herramientas y organización del proyecto")
p("El proyecto está escrito en Python. El compilador y el motor no tienen dependencias externas y "
  "funcionan desde Python 3.10. La parte de visión usa MediaPipe 1.1.1 (Face Landmarker: 478 puntos "
  "faciales y 52 coeficientes de expresión, o <i>blendshapes</i>) y OpenCV 5.0; como MediaPipe no "
  "tiene versiones para Python 3.13 o posterior, esa parte se ejecuta en un entorno virtual con "
  "Python 3.11. Las pruebas usan el módulo estándar <i>unittest</i>. El código fuente suma unas 3,900 "
  "líneas, más 360 de pruebas.")
p("Los analizadores léxico y sintáctico se escribieron a mano, sin generadores como ANTLR o PLY, "
  "para que cada fase del compilador quede visible y corresponda directamente con la teoría de la "
  "materia. La Figura 1 muestra cómo se conectan las fases.")
figura("fig_arquitectura.png", "Arquitectura: fases de compilación y ciclo de ejecución.")
p("Todas las funciones se usan desde la línea de comandos:")
tabla([
    ["Comando", "Función"],
    ["lexico, sintactico, semantico", "Muestran la salida de cada fase: tokens, árbol sintáctico, "
                                      "tabla de símbolos y diagnósticos."],
    ["compilar", "Genera los autómatas: tablas de transición, diagramas (Mermaid y Graphviz) y JSON."],
    ["ejecutar", "Ejecuta el programa con un sensor simulado, un CSV grabado o la cámara."],
    ["evaluar", "Calcula exactitud, falsos positivos/negativos y latencia contra datos etiquetados."],
    ["capturar", "Graba métricas de la cámara mientras una persona etiqueta los gestos con el teclado."],
    ["diagnostico", "Verifica con la cámara que cada métrica responda a los movimientos esperados."],
], [4.4, 12.2], "Comandos de la herramienta (python -m emolang &lt;comando&gt;).")

# ================================================================== 3
titulo("3. Especificación del lenguaje (objetivo 1)")
subtitulo("3.1 Estructura de un programa")
p("Un programa se compone de uno o más <b>dominios</b>. Cada dominio declara sus sensores, variables "
  "globales (umbrales), <b>gestos</b> (una condición sobre las métricas faciales sostenida durante un "
  "tiempo), <b>secuencias</b> (gestos en orden dentro de una ventana de tiempo) y <b>máquinas de "
  "estado</b> que reaccionan a esos eventos. Un fragmento del módulo de conducción:")
cod("""
dominio conduccion {
    sensor camara { var fps : int = 30; }
    var umbral_ojo : proporcion = 0.20;

    gesto parpadeo   = ear < umbral_ojo y mar < umbral_bostezo durante 60 ms hasta 400 ms;
    gesto microsueno = ear < umbral_ojo y mar < umbral_bostezo durante 1 s tolerando 100 ms;
    secuencia fatiga = [bostezo, cabeceo] en 10 s;

    maquina monitor inicial normal {
        estado normal {
            cuando microsueno ir_a alerta;
            mientras perclos > umbral_perclos { ir_a somnoliento; }
        }
        estado alerta {
            al_entrar { alarma("¡Despierte!"); registrar("microsueño"); }
            cuando atento ir_a normal;
        }
    }
}""")
p("Los programas completos de ambos módulos están en los anexos A y B.")

subtitulo("3.2 Componentes léxicos")
tabla([
    ["Categoría", "Definición"],
    ["Identificador", "[a-zA-Z_][a-zA-Z0-9_]* que no sea palabra reservada"],
    ["Entero / decimal", "[0-9]+ y [0-9]+.[0-9]+"],
    ["Cadena", "texto entre comillas dobles, con escapes \\n \\t \\\" \\\\"],
    ["Unidades", "ms, s y %, que pueden ir pegadas al número (100ms, 2s, 40%)"],
    ["Operadores", "+ - * / &lt; &lt;= &gt; &gt;= == != = y los lógicos y, o, no"],
    ["Delimitadores", "{ } ( ) [ ] ; , :"],
    ["Comentarios", "// hasta el fin de la línea y /* bloque */"],
    ["Palabras reservadas", "dominio sensor var gesto secuencia maquina inicial estado al_entrar cuando "
                            "ignorar ir_a durante hasta tolerando en si sino mientras repetir veces int "
                            "decimal bool string duracion proporcion verdadero falso y o no ms s"],
], [3.6, 13.0], "Componentes léxicos.")

subtitulo("3.3 Gramática")
p("La gramática libre de contexto, en notación EBNF:")
cod("""
programa     = dominio , { dominio } ;
dominio      = "dominio" ID "{" { sensor | decl_var | gesto | secuencia | maquina } "}" ;
sensor       = "sensor" ID "{" { decl_var } "}" ;
decl_var     = "var" ID ":" tipo "=" expr ";" ;
tipo         = "int" | "decimal" | "bool" | "string" | "duracion" | "proporcion" ;
gesto        = "gesto" ID "=" expr "durante" expr [ "hasta" expr ] [ "tolerando" expr ] ";" ;
secuencia    = "secuencia" ID "=" "[" ID { "," ID } "]" [ "en" expr ] ";" ;
maquina      = "maquina" ID "inicial" ID "{" estado { estado } "}" ;
estado       = "estado" ID "{" { miembro_est } "}" ;
miembro_est  = decl_var | "al_entrar" bloque | "cuando" ID ( "ir_a" ID ";" | bloque )
             | "mientras" expr bloque | "ignorar" ID { "," ID } ";" ;
bloque       = "{" { sentencia } "}" ;
sentencia    = decl_var | ID "=" expr ";" | "si" expr bloque [ "sino" ( si | bloque ) ]
             | "repetir" expr "veces" bloque | "ir_a" ID ";" | llamada ";" ;
expr         = conjuncion { "o" conjuncion } ;
conjuncion   = negacion { "y" negacion } ;
negacion     = "no" negacion | comparacion ;
comparacion  = suma [ ( "<" | "<=" | ">" | ">=" | "==" | "!=" ) suma ] ;
suma         = termino { ( "+" | "-" ) termino } ;
termino      = unario { ( "*" | "/" ) unario } ;
unario       = "-" unario | primario ;
primario     = ( ENTERO | DECIMAL ) [ "ms" | "s" | "%" ] | CADENA | "verdadero" | "falso"
             | ID | llamada | "(" expr ")" ;
llamada      = ID "(" [ expr { "," expr } ] ")" ;""")
p("La gramática es LL(1) salvo en <i>sentencia</i> cuando inicia con un identificador; ahí se usa "
  "un token adicional de anticipación (= indica asignación y ( indica llamada). La precedencia, de "
  "menor a mayor, es: o, y, no, comparaciones (no asociativas), suma y resta, producto y división, "
  "menos unario.")

subtitulo("3.4 Tipos y reglas de conversión")
p("Además de los tipos primitivos, el lenguaje tiene <b>duracion</b> (se normaliza a milisegundos "
  "durante la compilación) y <b>proporcion</b> (un real entre 0 y 1 que también puede escribirse como "
  "porcentaje). Los gestos y las secuencias se declaran con su propia palabra reservada.")
tabla([
    ["Conversión", "Permitida", "Observación"],
    ["int → decimal", "Sí", "Ensanchamiento"],
    ["int + decimal", "Sí", "El resultado es decimal"],
    ["decimal ↔ proporcion", "Sí", "Si el valor es constante se verifica que esté en [0, 1]"],
    ["ms ↔ s", "Sí", "1 s = 1000 ms; se normaliza en compilación"],
    ["decimal → int", "No", "Pérdida de precisión"],
    ["número → duracion", "No", "Se exige la unidad: 5 s, no 5"],
    ["duracion comparada con número", "No", "Se exige la unidad en la constante"],
], [5.0, 2.2, 9.4], "Reglas de conversión de tipos.")
p("Para conversiones explícitas existen las funciones a_porcentaje(0.4) = 40.0, a_proporcion(40) = "
  "40 %, a_ms(2 s) = 2000.0 y a_s(500 ms) = 0.5.")

subtitulo("3.5 Ámbitos")
p("Los ámbitos, de exterior a interior, son: <b>global</b> (métricas del sensor, de solo lectura, y "
  "funciones predefinidas), <b>dominio</b> (variables del dominio y de sus sensores, gestos, "
  "secuencias y máquinas), <b>máquina</b> (nombres de sus estados), <b>estado</b> (variables locales, "
  "que se reinician cada vez que se entra al estado) y <b>bloque</b>. Las condiciones de los gestos "
  "se evalúan en el ámbito del dominio, por lo que pueden usar umbrales globales pero no variables "
  "locales de un estado.")

subtitulo("3.6 Semántica de ejecución")
p("En cada cuadro de video: (1) cada gesto evalúa su condición y avanza su autómata; (2) cada "
  "secuencia consume los eventos emitidos por los gestos; (3) cada máquina procesa los eventos en su "
  "estado actual (se ejecuta el primer <i>cuando</i> que coincide) y después evalúa sus bloques "
  "<i>mientras</i>. Como pide el anteproyecto, <i>mientras</i> se evalúa una sola vez por cuadro y nunca "
  "bloquea la ejecución; <i>repetir N veces</i> se ejecuta completo dentro del cuadro. Una transición "
  "(ir_a) reinicia las variables locales del estado destino y ejecuta su bloque <i>al_entrar</i>.")

# ================================================================== 4
titulo("4. Análisis léxico (objetivo 2)")
p("El analizador léxico recorre el texto carácter por carácter. Cada rama del método principal "
  "corresponde a un estado de un autómata finito determinista que reconoce una categoría: "
  "identificadores y palabras reservadas, números, cadenas, símbolos de uno o dos caracteres "
  "(aplicando la regla del lexema más largo, por ejemplo &lt;= antes que &lt;) y comentarios. Cada "
  "token guarda su línea y columna para los mensajes de error.")
p("Un caso particular del dominio son las unidades pegadas al número: en 100ms el analizador separa "
  "el número de la unidad, mientras que 3abc se reporta como error porque un identificador no puede "
  "iniciar con un dígito. También se detectan caracteres no reconocidos, cadenas sin cerrar y "
  "comentarios de bloque sin cerrar. Los errores no detienen el análisis: se registran y se continúa "
  "con el siguiente token.")
figura("cap_lexico.png", "Primeros tokens del programa de conducción.", ancho_cm=12.5)

# ================================================================== 5
titulo("5. Análisis sintáctico (objetivo 2)")
p("El analizador sintáctico es descendente recursivo: cada producción de la gramática es un método. "
  "Produce un árbol de sintaxis abstracta (AST) cuyos nodos están definidos en nodos.py; las "
  "constantes con unidad ya llegan normalizadas al árbol (2 s se guarda como 2000 ms y 40 % como "
  "0.4).")
p("Ante un error se aplica recuperación en modo pánico: se reporta el error y se descartan tokens "
  "hasta un punto de sincronización (punto y coma, llave de cierre o el inicio de la siguiente "
  "declaración). Así se informan varios errores en una sola compilación en lugar de detenerse en el "
  "primero. El analizador también da mensajes propios del lenguaje, por ejemplo cuando a un gesto le "
  "falta la cláusula durante o cuando se usa mientras fuera de un estado.")
figura("cap_sintactico.png", "Árbol de sintaxis abstracta del programa de rehabilitación (inicio).",
       ancho_cm=13.5)

# ================================================================== 6
titulo("6. Análisis semántico (objetivo 3)")
p("El analizador semántico recorre el AST con una tabla de símbolos organizada como una cadena de "
  "ámbitos. Para cada símbolo guarda su nombre, categoría (variable, gesto, secuencia, máquina, "
  "estado), tipo, ámbito, línea y, cuando se puede calcular en compilación, su valor inicial. Ese "
  "valor se obtiene por plegado de constantes y lo usan después las validaciones de dominio.")
p("Las verificaciones que realiza son: identificadores no declarados o redeclarados en el mismo "
  "ámbito; uso de nombres reservados (métricas y funciones); asignación a métricas, gestos o "
  "estados; compatibilidad de tipos en asignaciones, operadores y argumentos de funciones; que las "
  "condiciones de si, mientras y de los gestos sean bool; que durante, hasta, tolerando y la ventana "
  "de una secuencia sean de tipo duracion; que ir_a apunte a un estado de la misma máquina; y que "
  "cuando e ignorar se refieran a gestos o secuencias. Además anota en cada expresión del AST su "
  "tipo, que el motor usa para mostrar valores (por ejemplo, una proporción se imprime como 16.5 %).")
figura("cap_semantico.png", "Tabla de símbolos del programa de conducción.", ancho_cm=14.5)

# ================================================================== 7
titulo("7. Validaciones propias del dominio (objetivo 4)")
p("Esta fase revisa reglas que un lenguaje de propósito general no podría verificar, porque "
  "dependen del significado de las métricas faciales y del tiempo. Se ejecuta aunque haya errores "
  "semánticos, para reportar todos los problemas de una vez.")
tabla([
    ["Validación", "Técnica", "Ejemplo de mensaje"],
    ["Umbral fuera de rango", "Cada métrica tiene un rango válido y uno típico (ear en [0, 1], típico "
                              "0 a 0.45). Fuera del válido es error; fuera del típico, advertencia.",
     "umbral fuera de rango: 'ear' toma valores en [0, 1] y se comparó con 1.2"],
    ["Gesto imposible", "Análisis de intervalos sobre la condición (ver abajo); además duración mínima "
                        "mayor que la máxima, o máxima menor que un cuadro.",
     "gesto imposible: la condición de 'imposible1' nunca puede cumplirse"],
    ["Secuencia imposible", "Contiene un gesto imposible, o la ventana no alcanza para repetir un "
                            "mismo gesto.", "secuencia imposible: 'rep' necesita al menos 2200 ms"],
    ["Estado inalcanzable", "Recorrido en anchura (BFS) del grafo de transiciones desde el estado "
                            "inicial.", "estado inalcanzable: 'huerfano' no puede alcanzarse..."],
    ["Transiciones contradictorias", "Un mismo evento con transiciones incondicionales a destinos "
                                     "distintos en el mismo estado (no determinismo).",
     "el evento 'bien' lleva a b, c"],
    ["Eventos ignorados (nota)", "Un evento que cambia de estado en unos estados y se ignora en otros "
                                 "sin declararlo con ignorar.",
     "'distraccion' cambia de estado en normal pero se ignora en somnoliento"],
], [3.4, 6.8, 6.4], "Validaciones de dominio.")
p("<b>Análisis de intervalos.</b> La condición de un gesto se transforma a forma normal disyuntiva "
  "sobre intervalos: cada comparación métrica-constante se convierte en un intervalo (ear &lt; 0.1 da "
  "[0, 0.1)), la conjunción intersecta intervalos de la misma métrica, la disyunción los une y la "
  "negación se propaga con las leyes de De Morgan. Si todas las alternativas resultantes quedan vacías "
  "al intersectarlas con el rango válido de cada métrica, la condición es insatisfacible. Por ejemplo, "
  "ear &lt; 0.1 y ear &gt; 0.3 produce un intervalo vacío.")
p("Otras advertencias: gestos o secuencias declarados y no usados, condiciones siempre verdaderas, "
  "duraciones menores a un cuadro, transiciones que dependen de un gesto imposible y una tolerancia "
  "mayor o igual a la duración del gesto. La Figura 5 muestra el resultado con un programa escrito "
  "con errores intencionales.")
figura("cap_errores.png", "Diagnósticos del programa ejemplos/errores.emo (errores intencionales).")

# ================================================================== 8
titulo("8. Generación de autómatas (objetivo 5)")
subtitulo("8.1 Autómata de un gesto")
p("Un gesto se traduce a un autómata finito determinista sobre el alfabeto Σ = {1, 0}, donde 1 "
  "significa que la condición se cumple en el cuadro actual. La duración se convierte a cuadros con "
  "N = ⌈D · fps / 1000⌉. El estado q<sub>i</sub> significa que la condición lleva i cuadros cumplidos. "
  "Con 1 se avanza de q<sub>i</sub> a q<sub>i+1</sub>; con 0 se regresa a q<sub>0</sub>. El autómata "
  "es una máquina de Mealy: la transición que llega a q<sub>N</sub> emite el evento del gesto "
  "(marcado como / g en las figuras). Así se modela lo que plantea el anteproyecto: un ojo cerrado "
  "durante un cuadro es un parpadeo; durante un segundo, un posible microsueño.")
figura("fig_afd_gesto.png", "AFD de un gesto de 3 cuadros (100 ms a 30 fps). Doble círculo: "
                            "estado de aceptación.", ancho_cm=12)
p("Si el gesto tiene duración máxima (hasta M), se agregan los estados hasta q<sub>M</sub> y un estado "
  "de exceso q<sub>X</sub>, y el evento se emite al soltar la condición sólo si duró entre N y M "
  "cuadros. Así se distingue un parpadeo (60 a 400 ms) de un microsueño.")

subtitulo("8.2 Tolerancia a interrupciones")
p("Durante las pruebas se observó que un solo cuadro con ruido reinicia el conteo de un gesto "
  "sostenido (sección 11.3). Por eso se agregó la cláusula tolerando T, que perdona hasta K = "
  "round(T · fps / 1000) cuadros seguidos sin cumplirse la condición. Se agregan los estados "
  "q<sub>i</sub>~g, que significan i cuadros cumplidos y g cuadros de interrupción: con 1 se continúa "
  "el conteo y con 0 la interrupción crece hasta superar K, momento en que se regresa a q<sub>0</sub>. "
  "El resultado sigue siendo un autómata finito.")
figura("fig_afd_tolerancia.png", "El mismo gesto con tolerancia de un cuadro (estados q<sub>i</sub>~1).",
       ancho_cm=12.5)
p("El costo es el número de estados, que crece a 1 + N(K + 1) en un gesto sin máximo. La Tabla 6 "
  "muestra los tamaños en el programa de conducción.")
tabla([
    ["Gesto", "Definición", "Estados"],
    ["parpadeo", "durante 60 ms hasta 400 ms", "14"],
    ["cabeceo", "durante 300 ms tolerando 100 ms", "37"],
    ["microsueno", "durante 1 s tolerando 100 ms", "121"],
    ["bostezo", "durante 1.5 s tolerando 200 ms", "316"],
    ["distraccion", "durante 2 s tolerando 200 ms", "421"],
    ["atento", "durante 3 s tolerando 200 ms", "631"],
], [3.2, 7.0, 2.4], "Número de estados de los autómatas de gesto generados (30 fps).")
figura("cap_compilar_parpadeo.png", "Tabla de transiciones generada para el gesto parpadeo. "
                                    "→ marca el estado inicial, * los de aceptación y / el evento emitido.",
       ancho_cm=12.5)

subtitulo("8.3 Secuencias")
p("Una secuencia como [bostezo, cabeceo] en 10 s se traduce a un autómata de reconocimiento de "
  "patrones construido con el algoritmo de Knuth, Morris y Pratt, cuyo alfabeto son los eventos de "
  "los gestos que la componen. Si entre el primer evento y el último pasa más tiempo que la ventana, "
  "el autómata regresa a s<sub>0</sub>.")
figura("cap_compilar_fatiga.png", "Autómata de la secuencia fatiga.", ancho_cm=9)

subtitulo("8.4 Máquinas de estado")
p("Las máquinas declaradas se traducen directamente: sus estados son los declarados y su alfabeto, "
  "los eventos que aparecen en sus cuando. Las transiciones dentro de un si llevan una guarda entre "
  "corchetes, y las que ocurren desde al_entrar o mientras se marcan con λ (transición espontánea). "
  "Un evento que ejecuta acciones sin cambiar de estado aparece como un lazo con salida «acciones».")
figura("fig_maquina_monitor.png", "Diagrama generado de la máquina monitor del módulo de conducción.")
p("Para cada autómata el comando compilar produce la tabla de transiciones en texto, un archivo "
  "Markdown con tablas y diagramas Mermaid, un archivo .dot para Graphviz y un JSON con la "
  "definición completa, que es lo que carga el motor.")

# ================================================================== 9
titulo("9. Motor de ejecución y sensor de cámara (objetivo 6)")
subtitulo("9.1 Ciclo por cuadro")
p("El motor no vuelve a interpretar las condiciones temporales: evalúa la condición de cada gesto "
  "para obtener el símbolo 1 o 0 y consulta la tabla de transiciones generada. Las secuencias y las "
  "máquinas también se ejecutan desde sus tablas. Las sentencias de los bloques (asignaciones, si, "
  "repetir, llamadas) sí se interpretan sobre el AST. El tiempo de procesamiento medido es de 0.05 a "
  "0.1 ms por cuadro, muy por debajo de los 33 ms disponibles a 30 fps.")
subtitulo("9.2 Velocidad de la cámara")
p("La cámara usada en las pruebas entrega unos 10 cuadros por segundo, no 30. Como los autómatas "
  "cuentan cuadros, un gesto de 1 s tardaba en realidad unos 3 s en detectarse. Se resolvió con una "
  "normalización: el motor recibe cuadros a ritmo fijo (el fps declarado en el sensor del programa) y, "
  "si la cámara se atrasa, repite la medición más reciente. Así, 1 s en el lenguaje es 1 s real sin "
  "importar la cámara. Una prueba unitaria reproduce este caso.")
subtitulo("9.3 Métricas faciales")
p("De los puntos que entrega MediaPipe se calculan las métricas que usan los programas:")
vinetas([
    "<b>ear</b> (razón de aspecto del ojo, Soukupová y Čech): (|p2 − p6| + |p3 − p5|) / (2 |p1 − p4|) "
    "con seis puntos alrededor de cada ojo; se promedian ambos ojos.",
    "<b>mar</b> (razón de aspecto de la boca): distancia vertical promedio entre los labios internos "
    "dividida entre la distancia entre las comisuras.",
    "<b>sonrisa</b>, <b>sonrisa_izq</b>, <b>sonrisa_der</b> y <b>cejas</b>: coeficientes de expresión "
    "(blendshapes) de MediaPipe.",
    "<b>pitch</b>, <b>yaw</b>, <b>roll</b>: ángulos de la cabeza obtenidos de la matriz de "
    "transformación facial, relativos a una postura neutra medida al inicio.",
    "<b>simetria</b>: 1 menos la diferencia relativa entre el lado izquierdo y el derecho.",
    "<b>perclos</b>: proporción de cuadros con ojos cerrados en los últimos 60 s (Wierwille et al.).",
])
p("La postura neutra se calibra durante los primeros 2 s: el sistema espera a detectar el rostro y "
  "sólo acepta la calibración si la cabeza permanece quieta; durante la ejecución se puede recalibrar "
  "con la tecla r. Además del sensor de cámara existen un sensor simulado (genera métricas a partir de "
  "un guion de eventos y conoce la verdad de terreno) y un sensor que reproduce grabaciones en CSV.")

# ================================================================== 10
titulo("10. Módulos de dominio (objetivo 7)")
p("Los módulos implementan las funciones con efectos y el resumen final. Se eligen según el nombre "
  "del dominio.")
vinetas([
    "<b>Conducción</b>: alarma(mensaje) activa un aviso sonoro y visual sobre el video, "
    "detener_alarma() lo apaga y registrar(mensaje) agrega un evento a la bitácora, que se exporta a "
    "CSV. El resumen informa alarmas emitidas, tiempo en alarma y gestos detectados.",
    "<b>Rehabilitación</b>: contar_repeticion() registra una repetición con la simetría del momento y "
    "repeticiones() devuelve el conteo. El resumen informa repeticiones, simetría promedio, mínima y "
    "máxima, y el ritmo promedio entre repeticiones.",
])
figura("cap_ejecutar_conduccion.png", "Ejecución del programa de conducción con el escenario simulado.",
       ancho_cm=13)
figura("cap_ejecutar_rehab.png", "Final de la ejecución del programa de rehabilitación: conteo de "
                                 "repeticiones y simetría.", ancho_cm=13)

# ================================================================== 11
titulo("11. Pruebas y resultados (objetivo 8)")
subtitulo("11.1 Pruebas unitarias")
p("Hay 35 pruebas automáticas que cubren cada fase. Todas pasan en Python 3.14 y en Python 3.11.")
tabla([
    ["Grupo", "Pruebas", "Qué verifican"],
    ["Léxico", "5", "Tokens, unidades pegadas, operadores dobles, comentarios, errores y posiciones."],
    ["Sintáctico", "5", "Ejemplos válidos, precedencia, literales con unidad, recuperación de errores."],
    ["Semántico", "6", "Conversiones válidas e inválidas, ámbitos, redeclaraciones, funciones, tabla."],
    ["Validaciones", "6", "Umbrales, gestos y secuencias imposibles, estados inalcanzables, "
                          "contradicciones, eventos ignorados, advertencias."],
    ["Autómatas", "7", "Ejecución de los AFD de gestos (con máximo y tolerancia), KMP y formatos."],
    ["Motor", "6", "Transiciones, mientras no bloqueante, cámara lenta, escenarios completos."],
], [2.6, 1.6, 12.4], "Pruebas unitarias por grupo.")
figura("cap_unittest.png", "Resultado de las pruebas unitarias.", ancho_cm=15)

subtitulo("11.2 Evaluación con escenarios simulados")
p("El sensor simulado genera métricas con ruido y conoce cuándo ocurre cada gesto. Se usaron dos "
  "escenarios de conducción: uno con bostezos, microsueños, cabeceos y distracciones (40 s), y uno "
  "normal con sólo parpadeos (60 s) para medir falsos positivos; además un escenario de "
  "rehabilitación con 10 sonrisas. Cada escenario se corrió 20 veces con distinta semilla aleatoria. "
  "Una detección es verdadera positiva si ocurre entre el inicio del gesto real y 1.5 s después de su "
  "fin. Las magnitudes del simulador se ajustaron con las mediciones de la cámara real (sección 11.4).")
tabla([
    ["Gesto", "VP", "FP", "FN", "Precisión", "Recall", "Latencia media"],
    ["parpadeo", "447", "0", "0", "100 %", "100 %", "191 ms"],
    ["microsueno", "40", "0", "0", "100 %", "100 %", "967 ms"],
    ["bostezo", "40", "0", "0", "100 %", "100 %", "1,923 ms"],
    ["cabeceo", "20", "0", "0", "100 %", "100 %", "473 ms"],
    ["distraccion", "20", "0", "0", "100 %", "100 %", "2,172 ms"],
    ["sonreir (rehabilitación)", "200", "0", "0", "100 %", "100 %", "646 ms"],
], [4.6, 1.4, 1.4, 1.4, 2.3, 2.3, 3.2], "Resultados con datos simulados (20 corridas por escenario).")
p("La latencia de detección incluye la duración mínima que exige cada gesto (un microsueño necesita "
  "1 s), por lo que no es un retraso del sistema. Estos resultados deben leerse como una cota "
  "superior: el simulador es más regular que una persona real. Su utilidad principal es comparar "
  "versiones de un programa en las mismas condiciones, como en la siguiente sección.")

subtitulo("11.3 Robustez ante ruido")
p("Para medir el efecto de los cambios hechos al programa de conducción durante el desarrollo, se "
  "comparó la versión inicial (sin tolerando y sin las condiciones sobre mar) con la versión actual, "
  "aumentando el ruido del simulador al doble y al triple. Ambas se midieron con el mismo simulador.")
tabla([
    ["Ruido", "Versión", "Exactitud total", "Recall cabeceo", "FP parpadeo", "FP microsueño"],
    ["×1", "Inicial", "87.6 %", "95 %", "39", "40"],
    ["", "Actual", "100 %", "100 %", "0", "0"],
    ["×2", "Inicial", "78.6 %", "80 %", "126", "23"],
    ["", "Actual", "99.3 %", "100 %", "4", "0"],
    ["×3", "Inicial", "68.2 %", "25 %", "239", "3"],
    ["", "Actual", "97.6 %", "100 %", "13", "0"],
], [1.6, 2.0, 3.0, 3.0, 3.0, 3.0], "Versión inicial contra versión actual del programa de conducción "
                                    "(exactitud = VP / (VP + FP + FN)).")
p("La mejora se obtuvo modificando sólo el programa EmoLang, sin cambiar el motor: tolerando evita "
  "que el ruido reinicie los gestos sostenidos, y agregar y mar &lt; umbral_bostezo a parpadeo y "
  "microsueño evita confundirlos con los ojos entrecerrados durante un bostezo. Es el tipo de ajuste "
  "que el lenguaje busca dejar en manos de quien conoce el dominio.")

subtitulo("11.4 Pruebas con cámara real")
p("Se agregó el comando diagnostico, que pide a la persona una serie de movimientos (mirar al frente, "
  "bajar y subir la cabeza, girar a cada lado, cerrar los ojos, abrir la boca y sonreír), promedia las "
  "métricas de cada paso y verifica que respondan en la dirección esperada. La primera ejecución "
  "(Figura 14) reveló tres problemas.")
figura("cap_camara_diag1.png", "Primer diagnóstico con la cámara.", ancho_cm=15.5)
tabla([
    ["Hallazgo", "Evidencia", "Cambio realizado"],
    ["La cámara entrega ~10 fps, no 30", "321 cuadros en ~34 s", "Normalización del ritmo de cuadros "
                                                                 "en el motor (9.2)"],
    ["Al bostezar o sonreír se entrecierran los ojos", "ear = 0.15 con la boca abierta y 0.18 al "
                                                       "sonreír (umbral 0.20)",
     "Condición y mar &lt; umbral_bostezo en parpadeo y microsueño; simulador ajustado"],
    ["La postura neutra quedó mal calibrada", "pitch = 10.7° mirando al frente en el segundo "
                                              "diagnóstico", "Calibración que espera a que la cabeza "
                                                              "esté quieta y recalibración con r"],
    ["La boca abierta da mar ≈ 0.38", "El umbral de bostezo era 0.55", "Umbral de bostezo a 33 %"],
    ["El giro de cabeza da 23° a 33°", "Umbral de distracción de 30°", "Umbral a 20° (variable "
                                                                       "giro_grados)"],
], [4.4, 5.6, 6.6], "Hallazgos de las pruebas con cámara.")
figura("cap_camara_diag2.png", "Segundo diagnóstico, con movimientos amplios.", ancho_cm=15.5)
p("Después se ejecutó el programa de conducción completo con la cámara (Figura 16). Se detectaron "
  "bostezo, microsueño, cabeceo, la secuencia fatiga y distracción. La distracción se detectó tres "
  "veces pero sólo la primera generó alarma, porque en ese momento el monitor estaba en el estado "
  "normal; en somnoliento el programa no tenía regla para ese evento. No era una falla del detector "
  "sino de las reglas del programa. Se corrigió el ejemplo y se agregó al compilador la nota de "
  "eventos ignorados y la instrucción ignorar (sección 12), para que este tipo de omisión se detecte "
  "antes de ejecutar. En la misma prueba se vio que el monitor entraba y salía de somnoliento cada "
  "15 s mientras el PERCLOS seguía alto; se cambió la condición de salida para exigir también que el "
  "PERCLOS baje.")
figura("cap_camara_vivo.png", "Ejecución en vivo con la cámara (versión del programa anterior a las "
                              "correcciones descritas).", ancho_cm=13.5)

# ================================================================== 12
titulo("12. Cambios respecto al anteproyecto")
p("Ningún elemento del anteproyecto se eliminó. Los siguientes cambios y agregados surgieron durante "
  "el desarrollo y se someten a revisión:")
tabla([
    ["Elemento", "Cambio", "Motivo"],
    ["Cláusula hasta en gestos", "Agregada: duración máxima de un gesto.",
     "Distinguir un parpadeo de un microsueño con la misma condición."],
    ["Cláusula tolerando", "Agregada.", "Un cuadro con ruido reiniciaba los gestos sostenidos "
                                         "(sección 11.3)."],
    ["Instrucción ignorar y nivel nota", "Agregados.", "Detectar eventos atendidos en unos estados "
                                                       "y olvidados en otros (sección 11.4)."],
    ["Declaración de gestos y secuencias", "Con su propia palabra (gesto, secuencia) y no con var.",
     "Un gesto no es un valor que cambie; es un patrón que se compila a un autómata."],
    ["mientras", "Sólo puede declararse directamente en un estado.",
     "Se evalúa una vez por cuadro; dentro de un bloque de una sola ejecución no tendría sentido."],
    ["ms y s", "Son palabras reservadas.", "Permite escribir 100 ms y 2 s sin ambigüedad; no pueden "
                                           "usarse como nombres."],
    ["Conversiones explícitas", "Funciones a_porcentaje, a_proporcion, a_ms, a_s.",
     "Hacer visibles las conversiones que no son implícitas."],
    ["decimal → int", "Prohibida implícitamente.", "Evitar pérdida de precisión silenciosa."],
    ["Sensores de prueba", "Sensor simulado, reproducción de CSV, captura etiquetada y diagnóstico.",
     "Probar y evaluar sin depender de la cámara."],
], [4.0, 5.6, 7.0], "Cambios y agregados respecto al anteproyecto.")

# ================================================================== 13
titulo("13. Limitaciones y trabajo pendiente")
vinetas([
    "Falta la evaluación con varios participantes. Los resultados cuantitativos son de datos "
    "simulados; las pruebas con cámara las hizo una sola persona, y los umbrales de los ejemplos se "
    "ajustaron con sus mediciones.",
    "Mirar hacia abajo (por ejemplo, al tablero) también reduce ear a 0.18–0.21, cerca del umbral de "
    "microsueño. Hay que revisarlo con grabaciones reales.",
    "La magnitud de pitch es menor de lo esperado (unos 20° entre mirar arriba y abajo). Su signo es "
    "correcto, pero falta confirmar si la medición se queda corta o si los movimientos fueron "
    "pequeños.",
    "Con tolerancia, los autómatas de gestos largos crecen a cientos de estados. No afecta el "
    "rendimiento, pero las tablas completas son difíciles de leer; los diagramas agrupan los estados "
    "intermedios.",
    "El parpadeo no puede etiquetarse a mano (dura unos 150 ms), así que en la evaluación real sólo se "
    "medirá con datos simulados.",
    "No hay interfaz gráfica: el uso es desde la terminal, con una ventana de video que muestra las "
    "métricas, el estado de cada máquina y las alarmas.",
])
p("El siguiente paso es aplicar el protocolo de evaluación (docs/protocolo_evaluacion.md): grabar con "
  "cada participante una sesión de conducción simulada, una normal y una de rehabilitación, "
  "etiquetando los gestos con el comando capturar, y medir exactitud, falsos positivos y negativos y "
  "latencia con evaluar. Para no sobreajustar, los umbrales se ajustarán con unos participantes y los "
  "resultados se reportarán con otros.")

# ================================================================== 14
titulo("14. Puntos para revisión")
p("El equipo solicita retroalimentación sobre los siguientes puntos:")
numerada([
    "¿Se aceptan los agregados al lenguaje (hasta, tolerando, ignorar) o deben quedar fuera del "
    "alcance del proyecto?",
    "¿Es adecuado escribir los analizadores a mano, o se espera el uso de un generador como ANTLR, "
    "PLY o Flex/Bison?",
    "¿La forma de presentar los autómatas (tabla de transiciones más diagrama, con estados agrupados "
    "en los gestos largos) cubre lo que pide el objetivo 5?",
    "¿El protocolo de evaluación (3 a 5 participantes, tres sesiones cada uno, etiquetado manual) es "
    "suficiente para el objetivo 8?",
    "¿Se mantienen ambos módulos de dominio (conducción y rehabilitación) o conviene concentrarse en "
    "uno para la entrega final?",
    "¿Hay algún formato o sección que deba tener el reporte final que no esté en este avance?",
])

# ================================================================== referencias
titulo("Referencias")
refs = [
    "House, J. W. y Brackmann, D. E. (1985). Facial nerve grading system. <i>Otolaryngology–Head and "
    "Neck Surgery</i>, 93(2), 146–147.",
    "Knuth, D. E., Morris, J. H. y Pratt, V. R. (1977). Fast pattern matching in strings. <i>SIAM "
    "Journal on Computing</i>, 6(2), 323–350.",
    "Lugaresi, C. et al. (2019). MediaPipe: A framework for building perception pipelines. "
    "<i>arXiv:1906.08172</i>.",
    "Mernik, M., Heering, J. y Sloane, A. M. (2005). When and how to develop domain-specific "
    "languages. <i>ACM Computing Surveys</i>, 37(4), 316–344.",
    "Soukupová, T. y Čech, J. (2016). Real-time eye blink detection using facial landmarks. "
    "<i>21st Computer Vision Winter Workshop</i>.",
    "Wierwille, W. W., Ellsworth, L. A., Wreggit, S. S., Fairbanks, R. J. y Kirn, C. L. (1994). "
    "<i>Research on vehicle-based driver status/performance monitoring: development, validation, and "
    "refinement of algorithms for detection of driver drowsiness</i>. National Highway Traffic "
    "Safety Administration, DOT HS 808 247.",
]
for r in refs:
    historia.append(Paragraph(r, ParagraphStyle("ref", parent=cuerpo, leftIndent=18, firstLineIndent=-18,
                                                alignment=TA_LEFT)))

# ================================================================== anexos
historia.append(PageBreak())
titulo("Anexo A. Programa del módulo de conducción")
cod(leer("ejemplos/conduccion.emo"))
historia.append(PageBreak())
titulo("Anexo B. Programa del módulo de rehabilitación")
cod(leer("ejemplos/rehabilitacion.emo"))
titulo("Anexo C. Cómo reproducir los resultados")
cod(r"""
python -m unittest discover -s tests -t .
python -m emolang compilar  ejemplos/conduccion.emo
python -m emolang ejecutar  ejemplos/conduccion.emo
python -m emolang evaluar   ejemplos/conduccion.emo --repeticiones 20 --ruido 3
python -m emolang evaluar   reporte/conduccion_version_inicial.emo --repeticiones 20 --ruido 3

.venv\Scripts\python -m emolang diagnostico
.venv\Scripts\python -m emolang ejecutar ejemplos/conduccion.emo --sensor camara --sonido
.venv\Scripts\python -m emolang capturar grabaciones/p1_conduccion.csv
""")

doc = Documento(SALIDA, pagesize=letter, leftMargin=2.5 * cm, rightMargin=2.5 * cm,
                topMargin=2.5 * cm, bottomMargin=2.3 * cm, title="EmoLang – Fase 2: Desarrollo",
                author="García Gabriel, Giner Coache, Jiménez López, León Ramírez, Ortiz Martínez")
doc.multiBuild(historia, onFirstPage=sin_numero, onLaterPages=numero_pagina)
print("PDF generado:", SALIDA)
