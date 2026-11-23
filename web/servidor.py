"""Servidor de EmoLang: sirve la página y una API con usuarios y sesiones (SQLite).

    python web/servidor.py                 # construye web/dist y sirve en http://localhost:8000
    python web/servidor.py --https-local   # además HTTPS en la red local (puerto 8443) para celular y tablet
    python web/servidor.py --cert c.pem --key k.pem --anfitrion 0.0.0.0   # con un certificado propio
    python web/servidor.py --db datos.db   # otra base de datos

La cámara (getUserMedia) solo funciona en un contexto seguro: https o http://localhost.
Para usarla desde otro dispositivo de la red hace falta HTTPS; --https-local genera un
certificado autofirmado con openssl (guardado en web/certificados/, fuera de git) válido
para localhost y la IP de la red. El navegador mostrará un aviso que hay que aceptar una
vez («Configuración avanzada → Continuar»). La PC sigue usando http://localhost:8000.

Solo usa la biblioteca estándar de Python. La base de datos guarda:
    usuarios   nombre, correo, contraseña (scrypt con sal), rol y fecha del consentimiento
    tokens     sesiones iniciadas (solo se guarda el hash del token)
    sesiones   resultados de cada sesión: resumen numérico y bitácora; nunca video

Cada usuario tiene un rol: 'terapia' (terapia facial) o 'conductor' (conducción) y
solo puede guardar y consultar sesiones de su propio módulo.
"""

import argparse
import hashlib
import hmac
import http.server
import json
import os
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from urllib.parse import urlparse

AQUI = os.path.dirname(os.path.abspath(__file__))
DB_POR_OMISION = os.path.join(AQUI, "emolang.db")
COOKIE = "emolang_sesion"
DURACION_TOKEN = timedelta(days=30)
MAX_CUERPO = 2 * 1024 * 1024
ROLES = {"terapia": "terapia", "conductor": "conduccion"}     # rol -> módulo que puede usar
RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id                INTEGER PRIMARY KEY,
    nombre            TEXT NOT NULL,
    correo            TEXT NOT NULL UNIQUE COLLATE NOCASE,
    hash              BLOB NOT NULL,
    sal               BLOB NOT NULL,
    rol               TEXT NOT NULL CHECK (rol IN ('terapia', 'conductor')),
    consentimiento_en TEXT NOT NULL,
    creado_en         TEXT NOT NULL,
    perfil            TEXT              -- JSON (terapia): esfuerzo máximo de la persona en cada ejercicio
);
CREATE TABLE IF NOT EXISTS tokens (
    hash        TEXT PRIMARY KEY,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    expira      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sesiones (
    id          INTEGER PRIMARY KEY,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    modulo      TEXT NOT NULL,
    fecha       TEXT NOT NULL,
    duracion_s  REAL NOT NULL,
    resultado   TEXT NOT NULL,          -- JSON: resumen, ejercicios y bitácora
    creado_en   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sesiones_usuario ON sesiones(usuario_id, fecha DESC);
"""


def ahora():
    return datetime.now(timezone.utc)


class ErrorApi(Exception):
    def __init__(self, estado, mensaje):
        super().__init__(mensaje)
        self.estado = estado
        self.mensaje = mensaje


# ====================================================================== base de datos
class Base:
    def __init__(self, ruta):
        self.ruta = ruta
        self._candado = threading.Lock()
        self.con = sqlite3.connect(ruta, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(ESQUEMA)
        columnas = {f["name"] for f in self.con.execute("PRAGMA table_info(usuarios)")}
        if "perfil" not in columnas:            # bases creadas antes de guardar la sonrisa máxima
            self.con.execute("ALTER TABLE usuarios ADD COLUMN perfil TEXT")
        self.con.commit()

    def ejecutar(self, sql, params=()):
        with self._candado:
            cur = self.con.execute(sql, params)
            self.con.commit()
            return cur

    def uno(self, sql, params=()):
        with self._candado:
            return self.con.execute(sql, params).fetchone()

    def todos(self, sql, params=()):
        with self._candado:
            return self.con.execute(sql, params).fetchall()


def _hash_contrasena(contrasena, sal):
    return hashlib.scrypt(contrasena.encode("utf-8"), salt=sal, n=2**14, r=8, p=1, dklen=32)


def _hash_token(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def usuario_publico(u):
    return {"id": u["id"], "nombre": u["nombre"], "correo": u["correo"], "rol": u["rol"],
            "modulo": ROLES[u["rol"]]}


class Servicio:
    """Reglas de la API, separadas del HTTP para poder probarlas directamente."""

    def __init__(self, base):
        self.db = base

    # ---------------------------------------------------------------- cuentas
    def registrar(self, datos):
        nombre = str(datos.get("nombre", "")).strip()
        correo = str(datos.get("correo", "")).strip().lower()
        contrasena = str(datos.get("contrasena", ""))
        rol = datos.get("rol")
        if not 1 <= len(nombre) <= 80:
            raise ErrorApi(400, "Escriba su nombre.")
        if not RE_CORREO.match(correo) or len(correo) > 120:
            raise ErrorApi(400, "El correo no es válido.")
        if len(contrasena) < 8:
            raise ErrorApi(400, "La contraseña debe tener al menos 8 caracteres.")
        if rol not in ROLES:
            raise ErrorApi(400, "Elija un tipo de usuario: terapia facial o conductor.")
        if datos.get("consentimiento") is not True:
            raise ErrorApi(400, "Para crear la cuenta debe aceptar el aviso de privacidad.")
        if self.db.uno("SELECT 1 FROM usuarios WHERE correo = ?", (correo,)):
            raise ErrorApi(409, "Ya existe una cuenta con ese correo.")
        sal = secrets.token_bytes(16)
        t = ahora().isoformat()
        cur = self.db.ejecutar(
            "INSERT INTO usuarios (nombre, correo, hash, sal, rol, consentimiento_en, creado_en) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nombre, correo, _hash_contrasena(contrasena, sal), sal, rol, t, t))
        return self._iniciar(cur.lastrowid)

    def entrar(self, datos):
        correo = str(datos.get("correo", "")).strip().lower()
        contrasena = str(datos.get("contrasena", ""))
        u = self.db.uno("SELECT * FROM usuarios WHERE correo = ?", (correo,))
        # Se calcula el hash aunque el correo no exista, para no revelar qué correos hay.
        sal = u["sal"] if u else b"\0" * 16
        calculado = _hash_contrasena(contrasena, sal)
        if not u or not hmac.compare_digest(calculado, u["hash"]):
            raise ErrorApi(401, "Correo o contraseña incorrectos.")
        return self._iniciar(u["id"])

    def _iniciar(self, usuario_id):
        token = secrets.token_urlsafe(32)
        self.db.ejecutar("DELETE FROM tokens WHERE expira < ?", (ahora().isoformat(),))
        self.db.ejecutar("INSERT INTO tokens (hash, usuario_id, expira) VALUES (?, ?, ?)",
                         (_hash_token(token), usuario_id, (ahora() + DURACION_TOKEN).isoformat()))
        u = self.db.uno("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
        return token, usuario_publico(u)

    def usuario_de(self, token):
        if not token:
            return None
        return self.db.uno(
            "SELECT u.* FROM tokens t JOIN usuarios u ON u.id = t.usuario_id WHERE t.hash = ? AND t.expira > ?",
            (_hash_token(token), ahora().isoformat()))

    def salir(self, token):
        if token:
            self.db.ejecutar("DELETE FROM tokens WHERE hash = ?", (_hash_token(token),))

    # ---------------------------------------------------------------- perfil (terapia)
    # El esfuerzo máximo de la persona en cada ejercicio (emolang/perfil.py): números, no imágenes.
    CLAVES_PERFIL = ("sonrisa_maxima", "cejas_maxima", "ojos_maxima")

    def perfil(self, u):
        guardado = json.loads(u["perfil"]) if u["perfil"] else {}
        return {k: guardado.get(k, 0.0) for k in self.CLAVES_PERFIL}

    def guardar_perfil(self, u, datos):
        if u["rol"] != "terapia":
            raise ErrorApi(403, "Solo las cuentas de terapia guardan su esfuerzo máximo.")
        if not isinstance(datos, dict) or not datos or set(datos) - set(self.CLAVES_PERFIL):
            raise ErrorApi(400, "Perfil inválido.")
        perfil = self.perfil(u)
        for k, v in datos.items():
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ErrorApi(400, "Perfil inválido.") from None
            if not 0.0 <= v <= 1.0:
                raise ErrorApi(400, "Perfil inválido.")
            perfil[k] = v
        self.db.ejecutar("UPDATE usuarios SET perfil = ? WHERE id = ?", (json.dumps(perfil), u["id"]))
        return perfil

    # ---------------------------------------------------------------- sesiones
    def guardar_sesion(self, u, datos):
        modulo = datos.get("modulo")
        if modulo != ROLES[u["rol"]]:
            raise ErrorApi(403, "Su tipo de usuario no puede guardar sesiones de ese módulo.")
        resultado = datos.get("resultado")
        if not isinstance(resultado, dict) or not isinstance(resultado.get("bitacora", []), list):
            raise ErrorApi(400, "Resultado inválido.")
        try:
            fecha = datetime.fromisoformat(str(datos.get("fecha")).replace("Z", "+00:00")).isoformat()
            duracion = float(resultado.get("duracion_s", 0))
        except ValueError:
            raise ErrorApi(400, "Fecha o duración inválidas.") from None
        guardado = {k: resultado.get(k) for k in ("dominio", "clase", "duracion_s", "resumen", "ejercicios", "bitacora")}
        guardado["simetria_minima"] = datos.get("simetria_minima")
        cur = self.db.ejecutar(
            "INSERT INTO sesiones (usuario_id, modulo, fecha, duracion_s, resultado, creado_en) VALUES (?, ?, ?, ?, ?, ?)",
            (u["id"], modulo, fecha, duracion, json.dumps(guardado, ensure_ascii=False), ahora().isoformat()))
        return {"id": cur.lastrowid}

    def sesiones(self, u, limite=100):
        filas = self.db.todos(
            "SELECT id, modulo, fecha, resultado FROM sesiones WHERE usuario_id = ? ORDER BY fecha DESC LIMIT ?",
            (u["id"], limite))
        salida = []
        for f in filas:
            r = json.loads(f["resultado"])
            salida.append({"id": f["id"], "modulo": f["modulo"], "fecha": f["fecha"],
                           "simetria_minima": r.pop("simetria_minima", None) or 0.8, "r": r})
        return salida

    def borrar_sesiones(self, u):
        self.db.ejecutar("DELETE FROM sesiones WHERE usuario_id = ?", (u["id"],))

    def borrar_cuenta(self, u):
        self.db.ejecutar("DELETE FROM usuarios WHERE id = ?", (u["id"],))


# ====================================================================== HTTP
def manejador(servicio, dist, seguro):
    class Manejador(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=dist, **kw)

        def log_message(self, formato, *args):
            if not self.path.startswith("/api/"):
                return
            super().log_message(formato, *args)

        def end_headers(self):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Permissions-Policy", "camera=(self), microphone=()")
            # Que el navegador revise si hay una versión nueva de la página en cada carga.
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        # ---------------------------------------------------------- utilidades
        def _token(self):
            for parte in (self.headers.get("Cookie") or "").split(";"):
                nombre, _, valor = parte.strip().partition("=")
                if nombre == COOKIE:
                    return valor
            return None

        def _cookie(self, token, borrar=False):
            atributos = ["Path=/", "HttpOnly", "SameSite=Strict"]
            if seguro:
                atributos.append("Secure")
            if borrar:
                return f"{COOKIE}=; Max-Age=0; " + "; ".join(atributos)
            return f"{COOKIE}={token}; Max-Age={int(DURACION_TOKEN.total_seconds())}; " + "; ".join(atributos)

        def _json(self, estado, datos, cookie=None):
            cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(estado)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(cuerpo)

        def _leer(self):
            # Solo JSON: junto con SameSite=Strict evita que otro sitio envíe formularios.
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                raise ErrorApi(415, "Se esperaba JSON.")
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_CUERPO:
                raise ErrorApi(413, "La solicitud es demasiado grande.")
            try:
                datos = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                raise ErrorApi(400, "JSON inválido.") from None
            if not isinstance(datos, dict):
                raise ErrorApi(400, "JSON inválido.")
            return datos

        def _usuario(self):
            u = servicio.usuario_de(self._token())
            if not u:
                raise ErrorApi(401, "Tu sesión expiró o se cerró. Vuelve a iniciar sesión.")
            return u

        def _api(self, metodo):
            ruta = urlparse(self.path).path
            try:
                if metodo == "GET" and ruta == "/api/yo":
                    # Sin sesión no es un error: la página solo muestra el acceso.
                    u = servicio.usuario_de(self._token())
                    return self._json(200, usuario_publico(u) if u else None)
                if metodo == "GET" and ruta == "/api/perfil":
                    return self._json(200, servicio.perfil(self._usuario()))
                if metodo == "PUT" and ruta == "/api/perfil":
                    u = self._usuario()
                    return self._json(200, servicio.guardar_perfil(u, self._leer()))
                if metodo == "GET" and ruta == "/api/sesiones":
                    return self._json(200, servicio.sesiones(self._usuario()))
                if metodo == "POST" and ruta == "/api/registro":
                    token, u = servicio.registrar(self._leer())
                    return self._json(201, u, self._cookie(token))
                if metodo == "POST" and ruta == "/api/entrar":
                    token, u = servicio.entrar(self._leer())
                    return self._json(200, u, self._cookie(token))
                if metodo == "POST" and ruta == "/api/salir":
                    servicio.salir(self._token())
                    return self._json(200, {"ok": True}, self._cookie(None, borrar=True))
                if metodo == "POST" and ruta == "/api/sesiones":
                    u = self._usuario()
                    return self._json(201, servicio.guardar_sesion(u, self._leer()))
                if metodo == "DELETE" and ruta == "/api/sesiones":
                    servicio.borrar_sesiones(self._usuario())
                    return self._json(200, {"ok": True})
                if metodo == "DELETE" and ruta == "/api/cuenta":
                    servicio.borrar_cuenta(self._usuario())
                    return self._json(200, {"ok": True}, self._cookie(None, borrar=True))
                raise ErrorApi(404, "No existe.")
            except ErrorApi as e:
                self._json(e.estado, {"error": e.mensaje})
            except Exception as e:     # noqa: BLE001
                self.log_error("error interno: %r", e)
                self._json(500, {"error": "Error interno del servidor."})

        def do_GET(self):
            if self.path.startswith("/api/"):
                return self._api("GET")
            return super().do_GET()

        def do_POST(self):
            self._api("POST")

        def do_PUT(self):
            self._api("PUT")

        def do_DELETE(self):
            self._api("DELETE")

    return Manejador


# ====================================================================== HTTPS
def ip_local():
    """IP de esta computadora en la red local (la que usarán el celular o la tablet)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))        # no envía nada: solo elige la interfaz de salida
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def certificado_local(carpeta, ip):
    """Genera (o reutiliza) un certificado autofirmado válido para localhost y la IP de la red."""
    os.makedirs(carpeta, exist_ok=True)
    cert, llave = os.path.join(carpeta, "cert.pem"), os.path.join(carpeta, "llave.pem")
    marca = os.path.join(carpeta, "ip.txt")
    previa = open(marca).read().strip() if os.path.exists(marca) else None
    if os.path.exists(cert) and os.path.exists(llave) and previa == ip:
        return cert, llave
    if not shutil.which("openssl"):
        raise SystemExit("--https-local necesita openssl (Linux: sudo apt install openssl; "
                         "Windows: viene con Git for Windows, en C:\\Program Files\\Git\\usr\\bin).")
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "825",
         "-keyout", llave, "-out", cert, "-subj", "/CN=EmoLang local",
         "-addext", f"subjectAltName=DNS:localhost,IP:127.0.0.1,IP:{ip}",
         "-addext", "extendedKeyUsage=serverAuth"],
        check=True, capture_output=True)
    os.chmod(llave, 0o600)
    with open(marca, "w") as f:
        f.write(ip)
    return cert, llave


def contexto_tls(certificado, llave):
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certificado, llave)
    return ctx


def _servidor(servicio, dist, anfitrion, puerto, ctx=None):
    httpd = http.server.ThreadingHTTPServer((anfitrion, puerto), manejador(servicio, dist, ctx is not None))
    if ctx is not None:
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    return httpd


def servir(dist, db=DB_POR_OMISION, puerto=8000, anfitrion="127.0.0.1", certificado=None, llave=None,
           puerto_https=None):
    """Sirve por HTTP en anfitrion:puerto y, con certificado, también por HTTPS.

    Con certificado y puerto_https, HTTP queda en localhost (la PC) y HTTPS escucha en
    toda la red (celulares y tablets). Sin puerto_https, el único servidor usa HTTPS."""
    servicio = Servicio(Base(db))
    servidores, lineas = [], [f"EmoLang, base de datos: {db}"]
    ctx = contexto_tls(certificado, llave) if certificado else None
    if ctx is not None and puerto_https:
        servidores.append(_servidor(servicio, dist, "127.0.0.1", puerto))
        lineas.append(f"  En esta computadora:  http://localhost:{puerto}")
        servidores.append(_servidor(servicio, dist, "0.0.0.0", puerto_https, ctx))
        lineas.append(f"  Celular o tablet:     https://{ip_local()}:{puerto_https}   (misma red Wi-Fi)")
    else:
        servidores.append(_servidor(servicio, dist, anfitrion, puerto, ctx))
        esquema = "https" if ctx else "http"
        lineas.append(f"  En esta computadora:  {esquema}://localhost:{puerto}")
        if anfitrion in ("0.0.0.0", ""):
            lineas.append(f"  En la red local:      {esquema}://{ip_local()}:{puerto}")
            if ctx is None:
                lineas.append("  Aviso: sin HTTPS, la cámara solo funciona en esta computadora. Use --https-local.")
    if ctx is not None:
        lineas.append("  El certificado es autofirmado: la primera vez el navegador muestra una advertencia;"
                      " elija «Configuración avanzada» y luego «Continuar» (o «Visitar este sitio web»).")
    print("\n".join(lineas))
    for h in servidores[1:]:
        threading.Thread(target=h.serve_forever, daemon=True).start()
    try:
        servidores[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for h in servidores:
            h.server_close()


if __name__ == "__main__":
    import sys
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", line_buffering=True)   # consola de Windows y logs
        except Exception:
            pass
    import construir
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", default=DB_POR_OMISION)
    p.add_argument("--puerto", type=int, default=8000)
    p.add_argument("--anfitrion", help="0.0.0.0 para abrirlo desde otros dispositivos "
                                       "(por omisión 127.0.0.1, o 0.0.0.0 con HTTPS)")
    p.add_argument("--cert", "--certificado", dest="cert", help="certificado TLS (.pem) para servir con HTTPS")
    p.add_argument("--key", "--llave", dest="key", help="llave privada del certificado (.pem)")
    p.add_argument("--https-local", action="store_true",
                   help="genera un certificado autofirmado y sirve también por HTTPS en la red local")
    p.add_argument("--puerto-https", type=int, default=8443, help="puerto HTTPS con --https-local (8443)")
    a = p.parse_args()
    if bool(a.cert) != bool(a.key):
        p.error("--cert y --key van juntos")
    cert, key = a.cert, a.key
    if a.https_local and not cert:
        cert, key = certificado_local(os.path.join(AQUI, "certificados"), ip_local())
    if a.https_local:
        # HTTP para la PC (localhost) y HTTPS para la red local.
        servir(construir.construir(), a.db, a.puerto, "127.0.0.1", cert, key, puerto_https=a.puerto_https)
    else:
        anfitrion = a.anfitrion or ("0.0.0.0" if cert else "127.0.0.1")
        servir(construir.construir(), a.db, a.puerto, anfitrion, cert, key)
