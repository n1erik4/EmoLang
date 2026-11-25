"""Diagnóstico guiado del sensor de cámara.

Pide a la persona una serie de posturas/gestos, promedia las métricas en la
segunda mitad de cada paso (ya estabilizada) y verifica que cada métrica
responda en la dirección esperada (p. ej. que pitch aumente al bajar la cabeza).
"""

import re

PASO_MS = 4000

# (instrucción, clave, comprobación sobre el promedio, descripción de lo esperado)
PASOS = [
    ("Mire al frente, rostro neutro", "frente", None, ""),
    ("Baje la CABEZA, barbilla al pecho (no solo los ojos)", "abajo",
     lambda p, b: p["pitch"] - b["pitch"] > 6, "pitch debe AUMENTAR más de 6 grados"),
    ("Suba la CABEZA, mire al techo", "arriba",
     lambda p, b: p["pitch"] - b["pitch"] < -6, "pitch debe DISMINUIR más de 6 grados"),
    ("Gire la cabeza a SU izquierda (como ver el espejo)", "izquierda",
     lambda p, b: abs(p["yaw"] - b["yaw"]) > 15, "yaw debe cambiar más de 15 grados"),
    ("Gire la cabeza a SU derecha (como ver el espejo)", "derecha",
     lambda p, b: abs(p["yaw"] - b["yaw"]) > 15, "yaw debe cambiar más de 15 grados"),
    ("Cierre los ojos (siga escuchando el pitido)", "ojos",
     lambda p, b: p["ear"] < 0.2 < b["ear"] or p["cierre_ojos"] > 0.5 > b["cierre_ojos"],
     "ear debe bajar de 0.20 o cierre_ojos subir de 0.50 con los ojos cerrados"),
    ("Abra la boca grande (como bostezo)", "boca", lambda p, b: p["mar"] > 0.3,
     "mar debe superar 0.30"),
    ("Sonria ampliamente", "sonrisa", lambda p, b: p["sonrisa"] > 0.4,
     "sonrisa debe superar 0.40"),
    ("Eleve las cejas lo más que pueda", "cejas", lambda p, b: p["cejas"] > 0.5,
     "cejas debe superar 0.50"),
]
METRICAS = ["ear", "cierre_ojos", "mar", "sonrisa", "cejas", "pitch", "yaw", "roll", "simetria"]
ANCHO = 12


def diagnosticar(indice=0, salida=print):
    from .camara import SensorCamara

    sensor = SensorCamara(indice=indice, mostrar_video=True,
                          duracion=len(PASOS) * PASO_MS / 1000)
    estado = {"paso": 0}
    sensor.lineas_extra = lambda: [
        f"Paso {estado['paso'] + 1}/{len(PASOS)}: {PASOS[min(estado['paso'], len(PASOS) - 1)][0]}",
    ]
    muestras = {p[1]: [] for p in PASOS}
    sin_rostro = 0
    total = 0
    paso_previo = -1
    for t, m in sensor:
        i = int(t // PASO_MS)
        if i >= len(PASOS):
            break
        estado["paso"] = i
        if i != paso_previo:
            paso_previo = i
            salida(f"  Paso {i + 1}: {PASOS[i][0]}")
            _avisar(i)
        total += 1
        if not m["rostro"]:
            sin_rostro += 1
            continue
        if t % PASO_MS >= PASO_MS / 2:   # solo la segunda mitad, ya en la postura
            muestras[PASOS[i][1]].append({k: float(m[k]) for k in METRICAS})

    prom = {k: _promedio(v) for k, v in muestras.items()}
    fps = sensor.cuadros_leidos / sensor.segundos if sensor.segundos else 0.0
    return prom, sin_rostro, total, fps


def reporte(prom, sin_rostro, total, fps=None):
    lineas = ["", "PROMEDIOS POR PASO",
              f"{'paso':<11}" + "".join(f"{k:>{ANCHO}}" for k in METRICAS)]
    for _, clave, _, _ in PASOS:
        p = prom.get(clave)
        if p is None:
            lineas.append(f"{clave:<11}  (sin datos: no se detectó el rostro)")
        else:
            lineas.append(f"{clave:<11}" + "".join(f"{p[k]:>{ANCHO}.2f}" for k in METRICAS))

    lineas += ["", "VERIFICACIÓN"]
    base = prom.get("frente")
    fallas = 0
    for instr, clave, chequeo, esperado in PASOS:
        if chequeo is None:
            continue
        p = prom.get(clave)
        if p is None or base is None:
            lineas.append(f"  ?  {instr}: sin datos")
            fallas += 1
            continue
        ok = chequeo(p, base)
        fallas += not ok
        medido = {"abajo": "pitch", "arriba": "pitch", "izquierda": "yaw", "derecha": "yaw"}.get(clave)
        detalle = f" (cambió {p[medido] - base[medido]:+.1f}°)" if medido else ""
        lineas.append(f"  {'OK   ' if ok else 'FALLA'}  {instr}: {esperado}{detalle}")
    izq, der = prom.get("izquierda"), prom.get("derecha")
    if izq and der and base:
        signos_opuestos = (izq["yaw"] - base["yaw"]) * (der["yaw"] - base["yaw"]) < 0
        fallas += not signos_opuestos
        lineas.append(f"  {'OK   ' if signos_opuestos else 'FALLA'}  yaw tiene signo opuesto a la izquierda "
                      f"({izq['yaw'] - base['yaw']:+.0f}) y a la derecha ({der['yaw'] - base['yaw']:+.0f})")
    lineas += _separacion_ojos(prom)
    if fps:
        lineas.append(f"\nVelocidad real de la cámara: {fps:.1f} fps "
                      "(el motor la normaliza al fps del programa)")
    if total:
        lineas.append(f"\nCuadros sin rostro: {sin_rostro}/{total} ({100 * sin_rostro / total:.0f}%)")
    lineas.append("Todo correcto." if fallas == 0 else
                  f"{fallas} verificación(es) fallaron: copie este reporte para revisarlo.")
    return "\n".join(lineas)


def _separacion_ojos(prom):
    """Qué tan bien separa cada métrica los ojos cerrados de lo que se le parece (bajar la
    cabeza, sonreír, bostezar). Es informativo: sirve para elegir el umbral del programa."""
    ojos = prom.get("ojos")
    otros = {c: prom[c] for c in ("frente", "abajo", "sonrisa", "boca") if prom.get(c)}
    if not ojos or not otros:
        return []
    lineas = ["", "OJOS CERRADOS CONTRA GESTOS PARECIDOS (frente, abajo, sonrisa, boca)"]
    for k, cerrado_menor in (("ear", True), ("cierre_ojos", False)):
        peor = min(v[k] for v in otros.values()) if cerrado_menor else max(v[k] for v in otros.values())
        margen = (peor - ojos[k]) if cerrado_menor else (ojos[k] - peor)
        lineas.append(f"  {k:<12} cerrados {ojos[k]:.2f}  ·  el más parecido {peor:.2f}  ·  margen {margen:+.2f}"
                      + ("" if margen > 0.1 else "  (poco: se confundiría)"))
    return lineas


def _promedio(muestras):
    if not muestras:
        return None
    return {k: sum(m[k] for m in muestras) / len(muestras) for k in METRICAS}


def _avisar(i):
    """Pitido y la instrucción en voz alta: con los ojos cerrados no se puede leer la
    ventana, y sin aviso la persona se atrasa y mezcla un paso con el siguiente."""
    from .sonido import decir, pitido
    pitido(880, 150)
    texto = re.sub(r"\s*\(.*?\)", "", PASOS[i][0]).lower()
    if i > 0 and PASOS[i - 1][1] == "ojos":
        texto = "abra los ojos. " + texto
    decir(texto)
