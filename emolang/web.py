"""Puente entre la página web y EmoLang (corre en el navegador con Pyodide).

La página calcula las métricas de cada cuadro con MediaPipe en JavaScript y las
entrega aquí como JSON; el video nunca sale del dispositivo. Esta clase compila
el programa, lo ejecuta en EmoVM a ritmo fijo y devuelve lo que la interfaz
necesita mostrar: mensajes, estado de las máquinas, repeticiones, alarmas y, al
final, el resumen y la bitácora.
"""

import json

from .compilador import compilar
from .intermedio import PROGRAMA
from .metricas import metricas_neutras
from .modulos import clase_dominio, modulo_para
from .perfil import Perfil
from .vm import EmoVM


class SesionWeb:
    def __init__(self, fuente, dominio=None, perfil=None):
        r = compilar(fuente)
        if not r.ok:
            raise ValueError("; ".join(str(d) for d in r.reporte.errores))
        dominios = [d for d in r.emoc["dominios"] if d != PROGRAMA]
        if not dominios:
            raise ValueError("el programa no tiene un dominio")
        self.dominio = dominio or dominios[0]
        self.clase = clase_dominio(self.dominio)
        self.modulo = modulo_para(self.dominio, salida=lambda texto: None)
        self._mensajes, self._registros = [], []
        mostrar, registrar = self.modulo.mostrar, self.modulo.registrar

        def mostrar_web(texto):
            mostrar(texto)
            self._mensajes.append(texto)

        def registrar_web(texto):
            registrar(texto)
            self._registros.append(texto)

        self.modulo.mostrar, self.modulo.registrar = mostrar_web, registrar_web
        self.vm = EmoVM(r.emoc, self.dominio, self.modulo)
        # sonrisa máxima guardada en la cuenta (perfil.py)
        self.vm.perfil = Perfil.desde_dict(json.loads(perfil) if isinstance(perfil, str) else perfil)
        self.periodo = 1000.0 / self.vm.fps
        self.k = 0
        self.ultimas = metricas_neutras()
        self.alarmas_vistas = 0
        # Valores iniciales de las variables del dominio (umbrales, meta...): la página
        # los usa para dibujar la marca de cada umbral.
        self.configuracion = {v.nombre: v.valor for v in r.analisis.tabla
                              if v.categoria == "variable" and v.ambito == f"dominio {self.dominio}"
                              and isinstance(v.valor, (int, float)) and not isinstance(v.valor, bool)}

    # ------------------------------------------------------------------ cuadros
    def paso(self, t_ms, metricas_json):
        """Procesa las métricas de un cuadro de la cámara (marca de tiempo irregular).

        Igual que ejecucion.regularizar: se ejecutan los cuadros fijos de 1000/fps ms
        que caben hasta t_ms, repitiendo la medición más reciente."""
        m = dict(self.ultimas)
        m.update(json.loads(metricas_json))
        self.ultimas = m
        eventos = []
        while self.k * self.periodo <= t_ms + 0.5:
            eventos += self.vm.paso(self.k * self.periodo, m)
            self.k += 1
        return json.dumps(self._estado(eventos), ensure_ascii=False)

    def _estado(self, eventos):
        mod = self.modulo
        nuevas = mod.alarmas - self.alarmas_vistas
        self.alarmas_vistas = mod.alarmas
        mensajes, registros = self._mensajes, self._registros
        self._mensajes, self._registros = [], []
        return {
            "t_ms": self.vm.t,
            "eventos": eventos,
            "estados": self.vm.estado_actual(),
            "gestos_activos": self.vm.gestos_activos(),
            "mensajes": mensajes,
            "registros": registros,
            "alarma": mod.alarma_activa,
            "alarma_mensaje": mod.alarma_mensaje,
            "nuevas_alarmas": nuevas,
            "ejercicios": {n: [round(s, 4) for s in v] for n, v in mod.ejercicios.items()},
            "repeticiones": len(mod.reps),
            "perclos": round(self.vm.metricas.get("perclos", 0.0), 4),
            **{k: round(float(self.vm.metricas.get(k, 0.0)), 4) for k in ("sonrisa_rel", "cejas_rel", "ojos_rel")},
        }

    def perfil(self):
        return json.dumps(self.vm.perfil.a_dict())

    # ------------------------------------------------------------------ cierre
    def terminar(self):
        self.modulo.finalizar()
        return json.dumps({
            "dominio": self.dominio,
            "clase": self.clase,
            "duracion_s": round(self.vm.t / 1000, 1),
            "resumen": self.modulo.resumen(),
            "ejercicios": self.modulo.ejercicios,
            "bitacora": [[round(t / 1000, 3), tipo, det] for t, tipo, det in self.modulo.bitacora],
        }, ensure_ascii=False)


    def info(self):
        return json.dumps({"dominio": self.dominio, "clase": self.clase, "fps": self.vm.fps,
                           "configuracion": self.configuracion}, ensure_ascii=False)


def nueva_sesion(fuente, perfil=None):
    return SesionWeb(fuente, perfil=perfil)
