# Protocolo de evaluación con datos reales (objetivo 8)

El objetivo es medir, con una cámara RGB convencional, la **exactitud** del reconocimiento de gestos, los **falsos positivos y negativos** y la **latencia**, comparando lo que detecta EmoLang contra etiquetas puestas por una persona.

## 1. Preparación

- Cámara web a la altura de los ojos, a 50–80 cm, con iluminación frontal pareja (evitar contraluz).
- Entorno: `.venv\Scripts\python` (Python 3.11 con MediaPipe).
- Una carpeta `grabaciones/` con un archivo por sesión: `p<participante>_<sesion>.csv`.
- Anotar por participante: lentes (sí/no), iluminación, cámara usada, fps real.

## 2. Captura con etiquetas

```bash
.venv\Scripts\python -m emolang capturar grabaciones/p1_conduccion.csv
```

1. Los primeros 2 s son de calibración: mirar al frente con el rostro neutro.
2. Presionar la tecla **al iniciar** el gesto y **otra vez al terminarlo**:

| Tecla | Gesto | Cómo realizarlo |
|---|---|---|
| `b` | bostezo | bostezo completo (boca muy abierta ≥ 2 s) |
| `m` | microsueño | cerrar los ojos 1.5–3 s, relajando la cabeza |
| `c` | cabeceo | bajar la cabeza ~20–30° y regresar (< 1 s) |
| `d` | distracción | girar la cabeza a un lado ≥ 3 s (mirar el espejo lateral) |
| `s` | sonrisa | sonrisa amplia sostenida ≥ 1 s |
| `q` | — | terminar |

Lo más práctico es que **una segunda persona** presione las teclas mientras el participante hace los gestos; así las etiquetas no alteran el gesto.

Los parpadeos no se etiquetan a mano porque duran ~150 ms; quedan fuera de la evaluación real (en la simulada sí se evalúan).

## 3. Sesiones sugeridas por participante

| Sesión | Duración | Contenido |
|---|---|---|
| `conduccion` | ~3 min | 5 bostezos, 5 microsueños, 5 cabeceos, 3 distracciones, separados por ≥ 5 s de conducción normal (mirar al frente, parpadear, hablar) |
| `normal` | ~3 min | sin gestos objetivo: hablar, mirar los espejos brevemente, reír, beber agua. Mide **falsos positivos** |
| `rehabilitacion` | ~1.5 min | 10 sonrisas sostenidas con reposo entre cada una |

Con 3–5 participantes se obtienen ~25 eventos por gesto, suficiente para reportar precisión y recall.

## 4. Evaluación

```bash
python -m emolang evaluar ejemplos/conduccion.emo ^
    --csv grabaciones/p1_conduccion.csv --csv grabaciones/p1_normal.csv ^
    --csv grabaciones/p2_conduccion.csv --csv grabaciones/p2_normal.csv ^
    -o evaluacion/resultados_reales_conduccion.md

python -m emolang evaluar ejemplos/rehabilitacion.emo ^
    --csv grabaciones/p1_rehabilitacion.csv -o evaluacion/resultados_reales_rehab.md
```

**Criterio de emparejamiento:** una detección cuenta como verdadero positivo si ocurre entre 500 ms antes del inicio etiquetado (`--anticipo`, compensa el retraso al presionar la tecla) y 1500 ms después del fin (`--tolerancia`). Cada evento real se empareja con a lo más una detección; las detecciones sobrantes son falsos positivos y los eventos sin detección, falsos negativos.

**Métricas:** precisión = VP/(VP+FP), recall = VP/(VP+FN), F1, exactitud = VP/(VP+FP+FN), latencia de detección (desde el inicio etiquetado; incluye la duración mínima `durante` del gesto) y latencia de procesamiento del motor por cuadro.

## 5. Ajuste de umbrales

Las grabaciones se pueden reproducir cuantas veces se quiera sin repetir la sesión:

```bash
python -m emolang ejecutar ejemplos/conduccion.emo --sensor csv --csv grabaciones/p1_conduccion.csv
```

Para un reporte honesto, ajuste los umbrales con las grabaciones de unos participantes y reporte los resultados con las de **otros** (por ejemplo, ajustar con p1–p2 y evaluar con p3–p5).

## 6. Robustez (simulada)

`evaluar --ruido N` multiplica el ruido del sensor simulado. Comparación de la versión inicial del ejemplo de conducción (`reporte/conduccion_version_inicial.emo`: sin `tolerando` y sin las condiciones sobre `mar`) contra la actual, con el mismo simulador y 20 corridas por escenario:

| Ruido | Versión | Exactitud total | Recall cabeceo | FP parpadeo | FP microsueño |
|---|---|---|---|---|---|
| ×1 | inicial | 87.6 % | 95 % | 39 | 40 |
| ×1 | actual | 100 % | 100 % | 0 | 0 |
| ×2 | inicial | 78.6 % | 80 % | 126 | 23 |
| ×2 | actual | 99.3 % | 100 % | 4 | 0 |
| ×3 | inicial | 68.2 % | 25 % | 239 | 3 |
| ×3 | actual | 97.6 % | 100 % | 13 | 0 |

Los falsos microsueños de la versión inicial vienen de los bostezos: el diagnóstico con cámara real mostró que al bostezar `ear` baja a ~0.15 (los ojos se entrecierran), y el simulador se ajustó a ese dato.

La mejora se obtuvo modificando únicamente el programa EmoLang, no el motor: es el tipo de ajuste que el lenguaje busca poner en manos del experto del dominio.
