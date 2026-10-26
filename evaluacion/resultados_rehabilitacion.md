# Evaluación de `ejemplos/rehabilitacion.emo` — dominio `rehabilitacion`

- Fuentes (5): escenarios simulados rehabilitacion (×5)
- Emparejamiento: detección entre 0 ms antes del inicio etiquetado y 1500 ms después del fin

## Reconocimiento de gestos

| Gesto | VP | FP | FN | Precisión | Recall | F1 | Exactitud | Latencia detección (media) |
|---|---|---|---|---|---|---|---|---|
| sonreir | 50 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 646 ms |
| **Total** | 50 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 646 ms |

Gestos sin verdad de terreno (no evaluados): reposo

Exactitud = VP / (VP + FP + FN). La latencia de detección incluye la duración mínima que el propio gesto exige (`durante`).

## Latencia de procesamiento del motor

- Cuadros procesados: 6750
- Media: 0.024 ms/cuadro · p95: 0.038 ms · máximo: 0.490 ms
- Presupuesto a 30 fps: 33.3 ms/cuadro (el motor usa 0.07% en promedio, sin contar la extracción de puntos faciales de MediaPipe)