"""Convierte las salidas de texto de reporte/capturas/*.txt en imágenes con
aspecto de terminal (fondo negro, texto gris, Consolas)."""

import os
import sys

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

AQUI = os.path.dirname(os.path.abspath(__file__))
TXT = os.path.join(AQUI, "capturas")
PNG = os.path.join(AQUI, "figuras")
FUENTES = r"C:\Windows\Fonts"

ESCALA = 2
TAM = 13 * ESCALA
FONDO = (12, 12, 12)
TEXTO = (204, 204, 204)
MARGEN = 14 * ESCALA

principal = ImageFont.truetype(os.path.join(FUENTES, "consola.ttf"), TAM)
respaldo = ImageFont.truetype(os.path.join(FUENTES, "seguisym.ttf"), TAM)
mapa_principal = TTFont(os.path.join(FUENTES, "consola.ttf")).getBestCmap()
ANCHO_CELDA = principal.getlength("M")
ALTO_LINEA = int(TAM * 1.32)


def _ancho(c):
    return 2 if ord(c) > 0xFFFF else 1


def _envolver(linea, columnas):
    partes, actual, n = [], "", 0
    for c in linea:
        w = _ancho(c)
        if n + w > columnas:
            partes.append(actual)
            actual, n = "", 0
        actual += c
        n += w
    partes.append(actual)
    return partes


def renderizar(lineas, destino, columnas=118):
    filas = [p for l in lineas for p in _envolver(l.rstrip("\n"), columnas)]
    usadas = max(sum(_ancho(c) for c in f) for f in filas)
    ancho = int(MARGEN * 2 + ANCHO_CELDA * max(usadas, 60))
    alto = MARGEN * 2 + ALTO_LINEA * len(filas)
    img = Image.new("RGB", (ancho, alto), FONDO)
    d = ImageDraw.Draw(img)
    for i, fila in enumerate(filas):
        x = MARGEN
        y = MARGEN + i * ALTO_LINEA
        for c in fila:
            fuente = principal if ord(c) in mapa_principal else respaldo
            d.text((x, y), c, font=fuente, fill=TEXTO)
            x += ANCHO_CELDA * _ancho(c)
    img.save(destino, dpi=(220, 220))
    return destino


def leer(nombre):
    with open(os.path.join(TXT, nombre), encoding="utf-8") as f:
        return f.read().splitlines()


PROMPT = r"PS C:\Users\pc\EmoLang> "


def captura(salida, nombre_txt, comando=None, rango=None, final=True, columnas=118):
    lineas = leer(nombre_txt)
    if rango:
        lineas = lineas[rango[0]:rango[1]]
    if comando:
        lineas = [PROMPT + comando] + lineas
        if final:
            lineas += [PROMPT.rstrip()]
    return renderizar(lineas, os.path.join(PNG, salida), columnas)


def todas():
    os.makedirs(PNG, exist_ok=True)
    c = captura
    c("cap_lexico.png", "lexico.txt", "python -m emolang lexico ejemplos/conduccion.emo",
      (0, 30), final=False)
    c("cap_sintactico.png", "sintactico.txt", "python -m emolang sintactico ejemplos/rehabilitacion.emo",
      (0, 46), final=False)
    c("cap_semantico.png", "semantico.txt", "python -m emolang semantico ejemplos/conduccion.emo")
    c("cap_errores.png", "errores.txt", "python -m emolang semantico ejemplos/errores.emo",
      (16, None), columnas=112)
    c("cap_compilar_parpadeo.png", "compilar.txt", "python -m emolang compilar ejemplos/conduccion.emo",
      (0, 21), final=False, columnas=124)
    c("cap_compilar_fatiga.png", "compilar.txt", None, (1583, 1593))
    c("cap_ejecutar_conduccion.png", "ejecutar_conduccion.txt",
      "python -m emolang ejecutar ejemplos/conduccion.emo")
    lineas = leer("ejecutar_rehab.txt")
    c("cap_ejecutar_rehab.png", "ejecutar_rehab.txt", "python -m emolang ejecutar ejemplos/rehabilitacion.emo",
      (len(lineas) - 34, None))
    c("cap_unittest.png", "unittest.txt", "python -m unittest discover -s tests -t . -v", columnas=124)
    c("cap_camara_diag1.png", "camara_diagnostico_1.txt", columnas=124)
    c("cap_camara_diag2.png", "camara_diagnostico_2.txt", columnas=124)
    c("cap_camara_vivo.png", "camara_vivo.txt", columnas=124)


if __name__ == "__main__":
    todas()
    print("capturas generadas en", PNG, file=sys.stderr)
