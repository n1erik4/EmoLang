"""Arma el sitio web estático en web/dist (lo que se publica en GitHub Pages).

    python web/construir.py            # genera web/dist
    python web/construir.py --servir   # y lo sirve con la API de usuarios (web/servidor.py)

El navegador ejecuta el mismo paquete emolang con Pyodide: se empaca en
emolang.zip junto con los programas de ejemplos/ que usa la página.
"""

import argparse
import json
import os
import shutil
import subprocess
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DIST = os.path.join(AQUI, "dist")
PROGRAMAS = ["terapia_facial.emo", "conduccion.emo"]
# Módulos que solo sirven en la computadora (cámara con OpenCV, fotos, ensamblador, CLI).
SOLO_ESCRITORIO = {"camara.py", "captura.py", "diagnostico.py", "fotos.py", "codigo_objeto.py", "__main__.py"}


def version():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "local"


def construir(dist=DIST):
    if os.path.exists(dist):
        shutil.rmtree(dist)
    os.makedirs(dist)
    for nombre in os.listdir(AQUI):
        origen = os.path.join(AQUI, nombre)
        if nombre in ("dist", "pruebas", "construir.py", "servidor.py", "galeria.py", "__pycache__", "certificados") or nombre.endswith((".db", ".db-journal")):
            continue
        if os.path.isdir(origen):
            shutil.copytree(origen, os.path.join(dist, nombre))
        else:
            shutil.copy2(origen, dist)

    paquete = os.path.join(RAIZ, "emolang")
    with zipfile.ZipFile(os.path.join(dist, "emolang.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for nombre in sorted(os.listdir(paquete)):
            if nombre.endswith(".py") and nombre not in SOLO_ESCRITORIO:
                z.write(os.path.join(paquete, nombre), f"emolang/{nombre}")

    os.makedirs(os.path.join(dist, "programas"))
    for p in PROGRAMAS:
        shutil.copy2(os.path.join(RAIZ, "ejemplos", p), os.path.join(dist, "programas", p))

    v = version()
    with open(os.path.join(dist, "version.json"), "w", encoding="utf-8") as f:
        json.dump({"version": v}, f)
    # Evita que el navegador use archivos viejos después de publicar una versión nueva.
    for pagina in ("index.html", "landing.html"):
        ruta = os.path.join(dist, pagina)
        with open(ruta, encoding="utf-8") as f:
            html = f.read()
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(html.replace("__VERSION__", v))
    open(os.path.join(dist, ".nojekyll"), "w").close()
    print(f"Sitio en {dist} (versión {v})")
    return dist


def servir(dist, puerto=8000):
    """Sirve el sitio con la API de usuarios (web/servidor.py)."""
    import servidor
    servidor.servir(dist, puerto=puerto)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--servir", action="store_true")
    p.add_argument("--puerto", type=int, default=8000)
    a = p.parse_args()
    d = construir()
    if a.servir:
        servir(d, a.puerto)
