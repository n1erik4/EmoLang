"""Pruebas del módulo de terapia facial con fotos fijas.

Una foto es un solo cuadro: sirve para calibrar los umbrales de cada ejercicio
(¿la sonrisa de esta foto supera umbral_sonrisa?) y para revisar la medida de
simetría, pero no prueba duraciones ni repeticiones.

Flujo:
    descargar  fotos con licencia abierta de Openverse, una carpeta por etiqueta,
               con creditos.csv (autor, licencia y página de origen de cada foto)
    analizar   cada foto pasa por MediaPipe con las mismas métricas que la cámara
    galeria    página HTML local para revisar las fotos y descartar las mal etiquetadas
    reporte    aciertos y falsas alarmas de cada ejercicio con los umbrales del
               programa, y el umbral que mejor separa las fotos

Las fotos son caras de personas: se guardan fuera del repositorio y solo se
comparten los números (métricas) y los créditos.
"""

import csv
import html
import json
import os
import statistics
import time
import urllib.parse
import urllib.request

ETIQUETAS = ("sonrisa", "cejas", "ojos_cerrados", "neutra", "ojos_abiertos")

CONSULTAS = {
    "sonrisa": ["smiling face portrait", "big smile closeup", "smiling woman portrait",
                "smiling man portrait", "toothy smile face", "laughing face closeup"],
    "cejas": ["raised eyebrows", "surprised face portrait", "eyebrows raised surprise",
              "surprised expression closeup", "shocked face portrait"],
    "ojos_cerrados": ["eyes closed portrait", "closed eyes face", "eyes closed meditation face",
                      "sleeping face closeup", "eyes shut portrait"],
    "neutra": ["neutral expression portrait", "serious face portrait", "expressionless face",
               "passport photo face", "headshot neutral expression"],
}

API = "https://api.openverse.org/v1/images/"
AGENTE = "emolang-pruebas/0.1 (proyecto academico)"
EXTENSIONES = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
COLUMNAS = ["etiqueta", "archivo", "rostro", "ear", "ear_izq", "ear_der", "mar", "sonrisa", "sonrisa_izq",
            "sonrisa_der", "cejas", "cejas_izq", "cejas_der", "simetria_sonrisa", "simetria_cejas",
            "simetria_ojos", "pitch", "yaw", "tam_rostro"]


# ====================================================================== descarga
def _pedir(url, tiempo=30):
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=tiempo) as r:
        return r.read()


def buscar(consulta, paginas=12):
    """Resultados de Openverse (sin clave: 20 por página, hasta 240 por búsqueda)."""
    for pagina in range(1, paginas + 1):
        q = urllib.parse.urlencode({"q": consulta, "page_size": 20, "page": pagina, "mature": "false"})
        try:
            datos = json.loads(_pedir(f"{API}?{q}"))
        except Exception as e:
            print(f"  aviso: '{consulta}' página {pagina}: {e}")
            return
        for r in datos.get("results", []):
            yield r
        if pagina >= datos.get("page_count", 0):
            return
        time.sleep(1.0)


def descargar(destino, por_etiqueta=200, etiquetas=ETIQUETAS):
    """Descarga hasta `por_etiqueta` fotos por etiqueta. Se puede repetir: no duplica."""
    for etiqueta in etiquetas:
        carpeta = os.path.join(destino, etiqueta)
        os.makedirs(carpeta, exist_ok=True)
        ruta_creditos = os.path.join(carpeta, "creditos.csv")
        vistos = set()
        if os.path.exists(ruta_creditos):
            with open(ruta_creditos, newline="", encoding="utf-8") as f:
                vistos = {fila["id"] for fila in csv.DictReader(f)}
        nuevo = not os.path.exists(ruta_creditos)
        with open(ruta_creditos, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(["id", "archivo", "titulo", "autor", "licencia", "url_licencia", "pagina", "consulta"])
            total = len(vistos)
            for consulta in CONSULTAS[etiqueta]:
                if total >= por_etiqueta:
                    break
                print(f"{etiqueta}: buscando '{consulta}' ({total}/{por_etiqueta})")
                for r in buscar(consulta):
                    if total >= por_etiqueta:
                        break
                    if r["id"] in vistos:
                        continue
                    vistos.add(r["id"])
                    ext = os.path.splitext(urllib.parse.urlparse(r["url"]).path)[1].lower()
                    archivo = r["id"] + (ext if ext in EXTENSIONES else ".jpg")
                    try:
                        datos = _pedir(r["url"])
                    except Exception:
                        continue
                    if len(datos) < 5000:
                        continue
                    with open(os.path.join(carpeta, archivo), "wb") as img:
                        img.write(datos)
                    w.writerow([r["id"], archivo, r.get("title") or "", r.get("creator") or "",
                                f"cc {r.get('license')} {r.get('license_version') or ''}".strip(),
                                r.get("license_url") or "", r.get("foreign_landing_url") or "", consulta])
                    f.flush()
                    total += 1
            print(f"{etiqueta}: {total} fotos")


# ====================================================================== análisis
def _detector():
    from mediapipe.tasks.python import BaseOptions, vision
    from .camara import asegurar_modelo
    opciones = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=asegurar_modelo()),
        running_mode=vision.RunningMode.IMAGE, num_faces=1,
        output_face_blendshapes=True, output_facial_transformation_matrixes=True)
    return vision.FaceLandmarker.create_from_options(opciones)


def fotos_de(carpeta):
    """(etiqueta, ruta) de cada foto: la etiqueta es el nombre de la subcarpeta."""
    for etiqueta in sorted(os.listdir(carpeta)):
        sub = os.path.join(carpeta, etiqueta)
        if not os.path.isdir(sub):
            continue
        for nombre in sorted(os.listdir(sub)):
            if nombre.lower().endswith(EXTENSIONES):
                yield etiqueta, os.path.join(sub, nombre)


def analizar(carpeta, salida_csv):
    import cv2
    import mediapipe as mp
    from .camara import metricas_de
    from .metricas import metricas_neutras
    filas, sin_rostro = [], 0
    with _detector() as detector:
        filas, sin_rostro = _analizar_con(detector, carpeta, metricas_de, metricas_neutras, cv2, mp)
    with open(salida_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)
    print(f"{len(filas)} fotos analizadas, {sin_rostro} sin rostro detectado -> {salida_csv}")
    return filas


LADO_MINIMO = 320


def _escala(img):
    """Las fotos pequeñas (p. ej. CEW, 100x100) se amplían: el detector falla con caras diminutas."""
    return max(1.0, LADO_MINIMO / min(img.shape[:2]))


def _variantes(img, cv2):
    """La foto tal cual y, si no se encuentra la cara, con margen: en un recorte muy
    cerrado la cara ocupa toda la imagen y el detector no la reconoce."""
    k = _escala(img)
    if k > 1:
        img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    yield img
    alto, ancho = img.shape[:2]
    yield cv2.copyMakeBorder(img, alto // 2, alto // 2, ancho // 2, ancho // 2, cv2.BORDER_CONSTANT, value=(0, 0, 0))


def _analizar_con(detector, carpeta, metricas_de, metricas_neutras, cv2, mp):
    filas, sin_rostro = [], 0
    for etiqueta, ruta in fotos_de(carpeta):
        img = cv2.imread(ruta)
        if img is None:
            continue
        ancho_original = img.shape[1]
        for intento in _variantes(img, cv2):
            alto, ancho = intento.shape[:2]
            rgb = cv2.cvtColor(intento, cv2.COLOR_BGR2RGB)
            res = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
            if res.face_landmarks:
                break
        m = metricas_de(res, ancho, alto, metricas_neutras())
        fila = {"etiqueta": etiqueta, "archivo": os.path.relpath(ruta, carpeta), "rostro": int(m.get("rostro", False))}
        if fila["rostro"]:
            xs = [q.x * ancho for q in res.face_landmarks[0]]
            escala = ancho / (ancho_original * _escala(img))     # píxeles de la variante por píxel original
            fila["tam_rostro"] = round(min(1.0, (max(xs) - min(xs)) / escala / ancho_original), 3)
            for c in COLUMNAS[3:-1]:
                fila[c] = round(float(m.get(c, 0.0)), 4)
        else:
            sin_rostro += 1
        filas.append(fila)
    return filas, sin_rostro


# ====================================================================== revisión
def descartadas(carpeta):
    ruta = os.path.join(carpeta, "descartadas.txt")
    if not os.path.exists(ruta):
        return set()
    with open(ruta, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip()}


def galeria(carpeta, csv_metricas, salida_html):
    """Página local para revisar las fotos. Al marcar las mal etiquetadas, el botón
    descarga descartadas.txt, que se copia a la carpeta de fotos."""
    filas = _leer(csv_metricas)
    ya = descartadas(carpeta)
    tarjetas = []
    for etiqueta in ETIQUETAS + tuple(sorted({f["etiqueta"] for f in filas} - set(ETIQUETAS))):
        grupo = [f for f in filas if f["etiqueta"] == etiqueta]
        if not grupo:
            continue
        tarjetas.append(f'<h2>{html.escape(etiqueta)} ({len(grupo)})</h2><div class="rejilla">')
        for f in grupo:
            ruta = os.path.join(os.path.abspath(carpeta), f["archivo"])
            if f["rostro"] == "1":
                info = (f"sonrisa {float(f['sonrisa']):.2f} · cejas {float(f['cejas']):.2f} · "
                        f"ear {float(f['ear']):.2f}")
            else:
                info = "sin rostro"
            marcada = " checked" if f["archivo"] in ya else ""
            tarjetas.append(
                f'<label class="t"><img loading="lazy" src="file://{html.escape(ruta)}">'
                f'<span>{html.escape(info)}</span>'
                f'<span><input type="checkbox" value="{html.escape(f["archivo"])}"{marcada}> descartar</span></label>')
        tarjetas.append("</div>")
    pagina = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Revisión de fotos</title>
<style>
body{{font-family:system-ui,sans-serif;margin:16px;background:#fafafa;color:#222}}
.rejilla{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px}}
.t{{background:#fff;border:1px solid #ddd;border-radius:6px;padding:6px;font-size:12px;display:flex;flex-direction:column;gap:4px}}
.t img{{width:100%;height:150px;object-fit:cover;border-radius:4px}}
.t:has(input:checked){{opacity:.35;border-color:#c00}}
#barra{{position:sticky;top:0;background:#fafafa;padding:8px 0;border-bottom:1px solid #ddd}}
</style></head><body>
<div id="barra"><b>Marque las fotos que no muestran el ejercicio de su grupo.</b>
<button onclick="guardar()">Descargar descartadas.txt</button> <span id="n"></span></div>
{''.join(tarjetas)}
<script>
function cuenta(){{document.getElementById('n').textContent=document.querySelectorAll('input:checked').length+' marcadas';}}
document.addEventListener('change',cuenta);cuenta();
function guardar(){{
  const v=[...document.querySelectorAll('input:checked')].map(x=>x.value).join('\\n')+'\\n';
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([v],{{type:'text/plain'}}));
  a.download='descartadas.txt';a.click();
}}
</script></body></html>"""
    with open(salida_html, "w", encoding="utf-8") as f:
        f.write(pagina)
    print(f"Galería: {salida_html}  (copie descartadas.txt a {carpeta})")


# ====================================================================== reporte
def _leer(ruta):
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def umbrales_del_programa(ruta_programa):
    """Lee umbral_sonrisa, umbral_cejas y umbral_ojos del programa de terapia."""
    from .compilador import compilar_archivo
    r = compilar_archivo(ruta_programa, hasta="semantico")
    valores = {s.nombre: s.valor for s in r.analisis.tabla if s.nombre.startswith("umbral_")}
    return {"sonrisa": valores.get("umbral_sonrisa", 0.4), "cejas": valores.get("umbral_cejas", 0.5),
            "ear": valores.get("umbral_ojos", 0.15)}


# (ejercicio, métrica, etiqueta positiva, sentido): 'mayor' = el gesto ocurre si métrica > umbral
EJERCICIOS = [("sonreir", "sonrisa", "sonrisa", "mayor"),
              ("elevar_cejas", "cejas", "cejas", "mayor"),
              ("cerrar_ojos", "ear", "ojos_cerrados", "menor")]
# Fotos que con seguridad NO muestran el ejercicio. 'ojos_abiertos' (CEW) puede tener
# sonrisas o cejas levantadas, así que solo es negativa para cerrar_ojos.
NEGATIVAS = {"sonrisa": {"cejas", "ojos_cerrados", "neutra"},
             "cejas": {"sonrisa", "ojos_cerrados", "neutra"},
             "ojos_cerrados": {"sonrisa", "cejas", "neutra", "ojos_abiertos"}}
SIMETRIA = {"sonrisa": "simetria_sonrisa", "cejas": "simetria_cejas", "ojos_cerrados": "simetria_ojos"}


def _cuenta(pos, neg, umbral, sentido):
    cumple = (lambda v: v > umbral) if sentido == "mayor" else (lambda v: v < umbral)
    vp = sum(cumple(v) for v in pos)
    fp = sum(cumple(v) for v in neg)
    sens = vp / len(pos) if pos else 0.0
    espec = 1 - fp / len(neg) if neg else 0.0
    return vp, len(pos) - vp, fp, len(neg) - fp, sens, espec


def _mejor_umbral(pos, neg, sentido):
    """El umbral que maximiza sensibilidad + especificidad (índice de Youden)."""
    candidatos = sorted(set(round(v, 3) for v in pos + neg))
    mejor = None
    for u in candidatos:
        *_, sens, espec = _cuenta(pos, neg, u, sentido)
        if mejor is None or sens + espec > mejor[1]:
            mejor = (u, sens + espec, sens, espec)
    return mejor


def reporte(csv_metricas, ruta_programa, carpeta=None, salida=None, tam_minimo=0.15, giro_maximo=25.0):
    filas = _leer(csv_metricas)
    excluir = descartadas(carpeta) if carpeta else set()
    total = len(filas)
    revisadas = [f for f in filas if f["archivo"] not in excluir]
    con_rostro = [f for f in revisadas if f["rostro"] == "1"]
    utiles = [f for f in con_rostro if float(f["tam_rostro"]) >= tam_minimo and abs(float(f["yaw"])) <= giro_maximo]
    umbrales = umbrales_del_programa(ruta_programa)
    out = ["# Terapia facial: prueba con fotos fijas", ""]
    out.append(f"Fotos: {total}; descartadas en la revisión: {total - len(revisadas)}; "
               f"sin rostro detectado: {len(revisadas) - len(con_rostro)}; "
               f"rostro pequeño o de perfil (cara < {tam_minimo:.0%} del ancho o giro > {giro_maximo:g}°): "
               f"{len(con_rostro) - len(utiles)}; **útiles: {len(utiles)}**.")
    out.append("")
    out.append("| Etiqueta | Fotos útiles |")
    out.append("|---|---:|")
    for e in ETIQUETAS:
        n = sum(f['etiqueta'] == e for f in utiles)
        if n:
            out.append(f"| {e} | {n} |")
    out += ["", "## Ejercicios con los umbrales del programa", "",
            "Una foto positiva es la de la etiqueta del ejercicio; las negativas, las de etiquetas que con "
            "seguridad no lo muestran (ojos_abiertos solo cuenta para cerrar_ojos).", "",
            "| Ejercicio | Condición | Detectadas | No detectadas | Falsas alarmas | Sensibilidad | Especificidad "
            "| Mejor umbral con estas fotos |",
            "|---|---|---:|---:|---:|---:|---:|---|"]
    for ejercicio, metrica, positiva, sentido in EJERCICIOS:
        pos = [float(f[metrica]) for f in utiles if f["etiqueta"] == positiva]
        neg = [float(f[metrica]) for f in utiles if f["etiqueta"] in NEGATIVAS[positiva]]
        if not pos or not neg:
            out.append(f"| {ejercicio} | – | sin fotos suficientes | | | | | |")
            continue
        u = umbrales["ear" if metrica == "ear" else metrica]
        vp, fn, fp, vn, sens, espec = _cuenta(pos, neg, u, sentido)
        mu, _, msens, mespec = _mejor_umbral(pos, neg, sentido)
        signo = ">" if sentido == "mayor" else "<"
        out.append(f"| {ejercicio} | {metrica} {signo} {u:g} | {vp} | {fn} | {fp} | {sens:.1%} | {espec:.1%} "
                   f"| {metrica} {signo} {mu:g} ({msens:.1%} / {mespec:.1%}) |")
    out += ["", "## Distribución de cada métrica por etiqueta", "",
            "| Etiqueta | sonrisa (mediana) | cejas (mediana) | ear (mediana) |", "|---|---:|---:|---:|"]
    for e in ETIQUETAS:
        g = [f for f in utiles if f["etiqueta"] == e]
        if g:
            med = lambda c: statistics.median(float(f[c]) for f in g)
            out.append(f"| {e} | {med('sonrisa'):.2f} | {med('cejas'):.2f} | {med('ear'):.3f} |")
    out += ["", "## Simetría medida en las fotos positivas", "",
            "En fotos de personas sin parálisis la simetría debería ser alta; las fotos con valores bajos "
            "conviene revisarlas (cara girada, sombra o expresión asimétrica real).", "",
            "| Ejercicio | Fotos | Promedio | Mínima | Debajo de 80 % |", "|---|---:|---:|---:|---:|"]
    for e, col in SIMETRIA.items():
        v = [float(f[col]) for f in utiles if f["etiqueta"] == e]
        if v:
            out.append(f"| {e} | {len(v)} | {statistics.mean(v):.1%} | {min(v):.1%} | {sum(x < 0.8 for x in v)} |")
    out += ["", "Fuentes: Openverse (licencias Creative Commons; autores y licencias en `creditos.csv` de "
            "cada carpeta) y CEW, Closed Eyes in the Wild (Song et al., 2014). Una foto es un cuadro: esta prueba calibra umbrales, "
            "no mide duraciones ni repeticiones."]
    texto = "\n".join(out) + "\n"
    if salida:
        with open(salida, "w", encoding="utf-8") as f:
            f.write(texto)
    return texto
