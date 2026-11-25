"""Pitido y voz en la computadora (Windows y Linux), sin bloquear la cámara.

En Windows usa winsound. En Linux genera el tono como WAV y lo toca con pw-play,
paplay o aplay; la voz usa spd-say o espeak-ng. Si no hay nada de eso, el pitido
cae al timbre de la terminal y la voz no se dice (la instrucción ya está en pantalla).
"""

import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import wave

_TONOS = {}
_REPRODUCTORES = ("pw-play", "paplay", "aplay")


def pitido(frecuencia=880, ms=150):
    try:
        import winsound
        threading.Thread(target=winsound.Beep, args=(frecuencia, ms), daemon=True).start()
        return
    except ImportError:
        pass
    reproductor = next((r for r in _REPRODUCTORES if shutil.which(r)), None)
    if reproductor:
        try:
            ruta = _tono(frecuencia, ms)
            args = [reproductor, "-q", ruta] if reproductor == "aplay" else [reproductor, ruta]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            pass
    print("\a", end="", flush=True)


def decir(texto):
    """Dice el texto en español sin esperar a que termine."""
    if sys.platform == "win32":
        return      # sin voz en Windows: queda el pitido
    for args in (["spd-say", "-l", "es", "-r", "10", texto], ["espeak-ng", "-v", "es-419", texto]):
        if shutil.which(args[0]):
            try:
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except OSError:
                pass


def _tono(frecuencia, ms, tasa=22050):
    """WAV de un tono senoidal (con rampas para que no truene), guardado una sola vez."""
    clave = (frecuencia, ms)
    if clave not in _TONOS:
        n = int(tasa * ms / 1000)
        rampa = max(1, int(tasa * 0.01))
        muestras = []
        for i in range(n):
            g = min(1.0, i / rampa, (n - i) / rampa)
            muestras.append(int(0.5 * 32767 * g * math.sin(2 * math.pi * frecuencia * i / tasa)))
        fd, ruta = tempfile.mkstemp(prefix=f"emolang_{frecuencia}_{ms}_", suffix=".wav")
        os.close(fd)
        with wave.open(ruta, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(tasa)
            w.writeframes(struct.pack(f"<{n}h", *muestras))
        _TONOS[clave] = ruta
    return _TONOS[clave]
