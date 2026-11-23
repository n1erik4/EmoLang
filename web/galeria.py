"""Descarga las fotos de la galería del acceso (web/img/galeria/).

    .venv/bin/python web/galeria.py            # busca y descarga candidatas
    .venv/bin/python web/galeria.py --hoja     # además arma hoja.jpg para revisarlas

Solo usa fotos de dominio público de Openverse (licencias CC0 y PDM), así que se
pueden publicar sin pedir permiso. Cada foto se reduce a 312 px de alto y se
guarda su autor, licencia y página de origen en galeria.json.
Para quitar una foto: borre su entrada de galeria.json (y su archivo).
"""

import argparse
import io
import json
import os
import time
import urllib.parse
import urllib.request

from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.join(AQUI, "img", "galeria")
API = "https://api.openverse.org/v1/images/"
AGENTE = "emolang-galeria/0.1 (proyecto academico)"
ALTO = 312
POR_FILA = 8

GRUPOS = {
    "rostros": (["smiling face portrait", "smile closeup", "happy woman portrait", "laughing man portrait"],
                "Rostro sonriendo"),
    "manejo": (["driving car steering wheel", "night highway driving", "car dashboard road", "highway traffic"],
               "Manejo en carretera"),
    "tecnologia": (["smartphone camera", "webcam", "eye closeup", "camera lens"],
                   "Cámara y tecnología"),
}


def pedir(url, tiempo=25):
    for intento in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(req, timeout=tiempo) as r:
                return r.read()
        except Exception as e:
            print(f"  reintento {intento + 1}: {e}")
            time.sleep(2)
    return None


def candidatas(consulta):
    q = urllib.parse.urlencode({"q": consulta, "license": "cc0,pdm", "page_size": 20, "mature": "false"})
    datos = pedir(f"{API}?{q}")
    if not datos:
        return []
    return [r for r in json.loads(datos)["results"] if (r.get("width") or 0) >= 600 and (r.get("height") or 0) >= 400]


def descargar():
    os.makedirs(DESTINO, exist_ok=True)
    salida = {"fuente": "Openverse, dominio público (CC0 / PDM)", "grupos": {}}
    for grupo, (consultas, alt) in GRUPOS.items():
        fotos, vistos = [], set()
        for consulta in consultas:
            for r in candidatas(consulta):
                if len(fotos) >= POR_FILA * 2 or r["id"] in vistos:
                    continue
                vistos.add(r["id"])
                datos = pedir(r["url"])
                if not datos:
                    continue
                try:
                    img = Image.open(io.BytesIO(datos)).convert("RGB")
                except Exception:
                    continue
                w, h = img.size
                if w / h < 1.1:            # se prefieren fotos horizontales
                    continue
                img = img.resize((round(w * ALTO / h), ALTO), Image.LANCZOS)
                archivo = f"{grupo}_{len(fotos) + 1:02d}.jpg"
                img.save(os.path.join(DESTINO, archivo), quality=78, optimize=True, progressive=True)
                fotos.append({"archivo": archivo, "alt": alt, "ancho": img.width, "alto": img.height,
                              "titulo": r.get("title") or "", "autor": r.get("creator") or "",
                              "licencia": f"{r['license'].upper()} {r.get('license_version') or ''}".strip(),
                              "pagina": r.get("foreign_landing_url") or r["url"], "consulta": consulta})
                print(f"{grupo}: {archivo}  {r.get('title', '')[:50]}")
            time.sleep(1)
        salida["grupos"][grupo] = fotos
    with open(os.path.join(DESTINO, "galeria.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
    return salida


def hoja(salida):
    """Mosaico para revisar las candidatas: una fila por grupo."""
    filas = []
    for grupo, fotos in salida["grupos"].items():
        ims = [Image.open(os.path.join(DESTINO, f["archivo"])).resize((208, 156)) for f in fotos]
        fila = Image.new("RGB", (208 * max(1, len(ims)), 156), "white")
        for i, im in enumerate(ims):
            fila.paste(im, (208 * i, 0))
        filas.append(fila)
    ancho = max(f.width for f in filas)
    total = Image.new("RGB", (ancho, 160 * len(filas)), "white")
    for i, f in enumerate(filas):
        total.paste(f, (0, 160 * i))
    ruta = os.path.join(DESTINO, "..", "hoja.jpg")
    total.save(ruta, quality=80)
    print("hoja:", os.path.abspath(ruta))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--hoja", action="store_true")
    a = p.parse_args()
    s = descargar()
    if a.hoja:
        hoja(s)
