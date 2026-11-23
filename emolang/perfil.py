"""Esfuerzo máximo de cada persona: cada ejercicio se mide contra lo que ella puede hacer.

Con parálisis facial una persona puede no sonreír con fuerza, no subir mucho las cejas o
no cerrar del todo los ojos: para ella un movimiento ligero ya es su mejor esfuerzo y
debe contar. Para alguien que sí puede moverse más, ese mismo movimiento ligero no debe
contar. Por eso los ejercicios no se comparan contra un número fijo sino contra el
máximo de la persona:

    sonrisa_rel = sonrisa / sonrisa máxima
    cejas_rel   = (cejas - cejas en reposo) / subida máxima de cejas
    ojos_rel    = cierre / cierre máximo,   cierre = (ear abierto - ear) / ear abierto

Todo se aprende solo, sin pasos extra en la rutina:
  - el máximo de cada ejercicio es el mayor movimiento SOSTENIDO 300 ms (un cuadro con
    ruido o un parpadeo no suben la vara), partiendo del 80 % del de la sesión anterior
    (se guarda en la cuenta) y nunca menor que PISOS, para que la cara relajada no cuente;
  - las cejas en reposo y el ojo abierto son los valores TÍPICOS de la persona con la
    cara relajada (sin sonreír ni subir las cejas) en los últimos 20 s: percentil 30 de las cejas y 75 de la
    apertura del ojo. No se usan extremos: un ceño fruncido o los ojos muy abiertos al
    levantar las cejas harían que la cara relajada pareciera movimiento.
"""

from collections import deque

# Movimiento mínimo que se toma como máximo personal. Con los umbrales del programa
# (60 %, 60 %, 70 %) lo más ligero que puede contar es: sonrisa 18 %, cejas 12 % arriba
# de su reposo y cierre de ojos 28 % (ear 0.22 si el ojo abierto mide 0.30).
PISOS = {"sonrisa": 0.30, "cejas": 0.20, "ojos": 0.40}
EJERCICIOS = tuple(PISOS)
SOSTENIDO_MS = 300
FRACCION_PREVIA = 0.8
EAR_ABIERTO = 0.30            # hasta medir el ojo abierto de la persona
EAR_ABIERTO_RANGO = (0.22, 0.45)
CEJAS_REPOSO_TIPICO = 0.10    # para fotos sueltas, donde no hay reposo de la persona
VENTANA_REPOSO_MS = 20_000
MUESTRAS_MINIMAS = 20         # ~0.7 s de cara relajada antes de usar sus valores
SONRISA_RELAJADA = 0.15       # como el «reposo» del programa
CEJAS_RELAJADAS = 0.10        # cejas a menos de esto de su reposo


def _limitar(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


class _Ventana:
    """Valores de los últimos 300 ms: devuelve (mínimo, máximo) cuando ya hay 300 ms."""

    def __init__(self):
        self.v = deque()

    def agregar(self, t_ms, valor):
        self.v.append((t_ms, valor))
        while t_ms - self.v[0][0] > SOSTENIDO_MS:
            self.v.popleft()
        if t_ms - self.v[0][0] < SOSTENIDO_MS * 0.9:
            return None
        valores = [x for _, x in self.v]
        return min(valores), max(valores)


class Perfil:
    def __init__(self, sonrisa_maxima=0.0, cejas_maxima=0.0, ojos_maxima=0.0):
        self.previas = {"sonrisa": float(sonrisa_maxima or 0.0), "cejas": float(cejas_maxima or 0.0),
                        "ojos": float(ojos_maxima or 0.0)}           # de sesiones anteriores
        self.maximas = {e: 0.0 for e in EJERCICIOS}                    # de esta sesión
        self.cejas_reposo = None
        self._ear_medido = None
        self._relajada = deque()           # (t, cejas, ear) con la cara relajada
        self._cuadros = 0
        self._ventanas = {k: _Ventana() for k in EJERCICIOS}

    def referencia(self, ejercicio="sonrisa"):
        """El máximo de la persona contra el que se mide <ejercicio>_rel."""
        return max(PISOS[ejercicio], FRACCION_PREVIA * self.previas[ejercicio], self.maximas[ejercicio])

    def movimientos(self, m):
        """Cuánto se mueve la persona en cada ejercicio en este cuadro."""
        cejas = float(m.get("cejas", 0.0))
        reposo = cejas if self.cejas_reposo is None else self.cejas_reposo
        ear = float(m.get("ear", self.ear_abierto))
        return {"sonrisa": _limitar(float(m.get("sonrisa", 0.0))),
                "cejas": _limitar(cejas - reposo),
                "ojos": _limitar((self.ear_abierto - ear) / self.ear_abierto)}

    def derivar(self, metricas, t_ms):
        """Agrega sonrisa_rel, cejas_rel y ojos_rel al cuadro (no modifica el original)."""
        m = dict(metricas)
        if m.get("rostro", True):
            self._aprender_bases(t_ms, m)
        mov = self.movimientos(m)
        for e in EJERCICIOS:
            if m.get("rostro", True):
                sostenido = self._ventanas[e].agregar(t_ms, mov[e])
                if sostenido:
                    self.maximas[e] = max(self.maximas[e], sostenido[0])
            m[f"{e}_rel"] = _limitar(mov[e] / self.referencia(e))
        return m

    def _aprender_bases(self, t_ms, m):
        cejas_arriba = self.cejas_reposo is not None and float(m.get("cejas", 0.0)) - self.cejas_reposo > CEJAS_RELAJADAS
        if float(m.get("sonrisa", 0.0)) < SONRISA_RELAJADA and not cejas_arriba:
            self._relajada.append((t_ms, float(m.get("cejas", 0.0)), float(m.get("ear", EAR_ABIERTO))))
        while self._relajada and t_ms - self._relajada[0][0] > VENTANA_REPOSO_MS:
            self._relajada.popleft()
        self._cuadros += 1
        if len(self._relajada) >= MUESTRAS_MINIMAS and (self.cejas_reposo is None or self._cuadros % 10 == 0):
            cejas = sorted(c for _, c, _ in self._relajada)
            ears = sorted(e for _, _, e in self._relajada)
            self.cejas_reposo = cejas[int(0.30 * (len(cejas) - 1))]
            self._ear_medido = ears[int(0.75 * (len(ears) - 1))]

    @property
    def ear_abierto(self):
        """Apertura del ojo abierto de la persona (EAR_ABIERTO hasta medirla)."""
        return EAR_ABIERTO if self._ear_medido is None else _limitar(self._ear_medido, *EAR_ABIERTO_RANGO)

    # ------------------------------------------------------------- guardar
    def a_dict(self):
        return {f"{e}_maxima": round(self.maximas[e] if self.maximas[e] > 0 else self.previas[e], 4)
                for e in EJERCICIOS}

    @classmethod
    def desde_dict(cls, datos):
        datos = datos or {}
        valores = {}
        for e in EJERCICIOS:
            try:
                valores[f"{e}_maxima"] = _limitar(float(datos.get(f"{e}_maxima") or 0.0))
            except (TypeError, ValueError):
                valores[f"{e}_maxima"] = 0.0
        return cls(**valores)


def umbral_en_foto(ejercicio, umbral):
    """En una foto suelta no hay historial de la persona: su máximo es el piso. Devuelve
    el valor crudo más ligero que puede contar (sonrisa o cejas: mayor que; ear: menor que)."""
    minimo = umbral * PISOS[ejercicio]
    if ejercicio == "sonrisa":
        return round(minimo, 3)
    if ejercicio == "cejas":
        return round(CEJAS_REPOSO_TIPICO + minimo, 3)
    return round(EAR_ABIERTO * (1 - minimo), 3)
