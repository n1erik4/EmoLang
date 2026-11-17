"""Prueba de punta a punta en Chromium con una cámara falsa (un video .y4m).

    .venv/bin/python web/pruebas/navegador.py VIDEO.y4m [--modulo terapia] [--https] [--salida carpeta]

Arranca web/servidor.py con una base de datos temporal, abre la página (en tamaño de
celular por omisión), crea una cuenta con el rol del módulo, hace la sesión con la
cámara falsa y espera la pantalla de resultados. Con --https entra por la IP de la
red local con un certificado autofirmado, como lo hará un celular.
"""

import argparse
import json
import os
import sys
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright

AQUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(AQUI)
sys.path.insert(0, WEB)
import construir  # noqa: E402
import servidor  # noqa: E402

ROL = {"terapia": "terapia", "conduccion": "conductor"}


def arrancar(https, tmp):
    """Servidor en un hilo; devuelve la URL de la página."""
    dist = construir.construir()
    db = os.path.join(tmp, "prueba.db")
    if https:
        ip = servidor.ip_local()
        cert, llave = servidor.certificado_local(os.path.join(tmp, "cert"), ip)
        args = dict(certificado=cert, llave=llave, puerto=8766, puerto_https=8767)
        url = f"https://{ip}:8767/"
    else:
        args = dict(puerto=8766)
        url = "http://127.0.0.1:8766/"
    threading.Thread(target=servidor.servir, args=(dist, db), kwargs=args, daemon=True).start()
    time.sleep(1.0)
    return url


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("--modulo", default="terapia")
    p.add_argument("--salida", default=".")
    p.add_argument("--ancho", type=int, default=390)
    p.add_argument("--alto", type=int, default=844)
    p.add_argument("--limite", type=float, default=150)
    p.add_argument("--https", action="store_true", help="entrar por la IP de la red con certificado autofirmado")
    p.add_argument("--primera", type=float, default=6, help="segundos hasta la primera captura")
    p.add_argument("--cada", type=float, default=12, help="segundos entre capturas")
    a = p.parse_args()
    os.makedirs(a.salida, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="emolang_web_")
    url = arrancar(a.https, tmp)
    errores = []
    with sync_playwright() as pw:
        nav = pw.chromium.launch(args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-video-capture={os.path.abspath(a.video)}"])
        contexto = nav.new_context(viewport={"width": a.ancho, "height": a.alto}, device_scale_factor=2,
                                   is_mobile=a.ancho < 700, has_touch=a.ancho < 700,
                                   ignore_https_errors=True)   # la persona acepta la advertencia
        pag = contexto.new_page()
        pag.on("console", lambda m: m.type in ("error", "warning") and errores.append(f"{m.type}: {m.text}"))
        pag.on("pageerror", lambda e: errores.append(f"pageerror: {e}"))
        pag.goto(url)
        print("página:", url, "| contexto seguro:", pag.evaluate("window.isSecureContext"))
        pag.wait_for_selector("#acceso:not([hidden])", timeout=15_000)
        pag.screenshot(path=f"{a.salida}/0_acceso.png", full_page=True)
        pag.click("#tab-registro")
        f = pag.locator("#form-registro")
        f.locator(f'input[name="rol"][value="{ROL[a.modulo]}"]').check()
        f.locator('input[name="nombre"]').fill("Persona de Prueba")
        f.locator('input[name="correo"]').fill("prueba@ejemplo.com")
        f.locator('input[name="contrasena"]').fill("contrasena-segura")
        f.locator('input[name="consentimiento"]').check()
        f.locator('button[type="submit"]').click()
        pag.wait_for_selector("#inicio:not([hidden])", timeout=15_000)
        pag.screenshot(path=f"{a.salida}/1_inicio.png", full_page=True)
        t = time.time()
        pag.wait_for_selector('#chip-motor[data-estado="listo"]', state="attached", timeout=120_000)
        pag.wait_for_selector('#chip-detector[data-estado="listo"]', state="attached", timeout=120_000)
        print(f"carga: {time.time() - t:.1f} s")
        pag.click(f'[data-iniciar="{a.modulo}"]')
        pag.wait_for_selector("#capa:not([hidden])", timeout=30_000)
        time.sleep(1.5)
        pag.screenshot(path=f"{a.salida}/2_calibrando.png")
        pag.wait_for_selector("#capa", state="hidden", timeout=30_000)
        print(f"calibrado: {time.time() - t:.1f} s")
        capturas, inicio = 0, time.time()
        while time.time() - inicio < a.limite:
            if pag.is_visible("#resultados"):
                break
            if capturas < 3 and time.time() - inicio > a.primera + capturas * a.cada:
                capturas += 1
                pag.screenshot(path=f"{a.salida}/3_sesion_{capturas}.png")
                print(" ", pag.inner_text("#instruccion"), "|", " / ".join(
                    pag.locator(".ejercicio__sim").all_inner_texts() or [pag.inner_text("#estado-conductor-texto")]))
            time.sleep(0.5)
        if not pag.is_visible("#resultados"):
            pag.click("#boton-terminar")
        pag.wait_for_selector("#resultados:not([hidden])", timeout=10_000)
        time.sleep(0.5)
        pag.screenshot(path=f"{a.salida}/4_resultados.png", full_page=True)
        print("resultados:", " | ".join(pag.locator(".tarjeta").all_inner_texts()).replace("\n", " "))
        guardadas = pag.evaluate("fetch('api/sesiones', {credentials: 'same-origin'}).then(r => r.json())")
        print("sesiones guardadas en el servidor:", json.dumps(guardadas)[:300])
        nav.close()
    print("errores de consola:", len(errores))
    for e in errores[:15]:
        print("  ", e[:300])


if __name__ == "__main__":
    main()
