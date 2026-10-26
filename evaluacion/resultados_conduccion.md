# Evaluación de `ejemplos/conduccion.emo` — dominio `conduccion`

- Fuentes (10): escenarios simulados conduccion (×5), normal (×5)
- Emparejamiento: detección entre 0 ms antes del inicio etiquetado y 1500 ms después del fin

## Reconocimiento de gestos

| Gesto | VP | FP | FN | Precisión | Recall | F1 | Exactitud | Latencia detección (media) |
|---|---|---|---|---|---|---|---|---|
| bostezo | 10 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 1900 ms |
| cabeceo | 5 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 440 ms |
| distraccion | 5 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 2167 ms |
| microsueno | 10 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 967 ms |
| parpadeo | 113 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 198 ms |
| **Total** | 143 | 0 | 0 | 100.0% | 100.0% | 100.0% | 100.0% | 448 ms |

Gestos sin verdad de terreno (no evaluados): atento

Exactitud = VP / (VP + FP + FN). La latencia de detección incluye la duración mínima que el propio gesto exige (`durante`).

## Latencia de procesamiento del motor

- Cuadros procesados: 15000
- Media: 0.043 ms/cuadro · p95: 0.063 ms · máximo: 1.950 ms
- Presupuesto a 30 fps: 33.3 ms/cuadro (el motor usa 0.13% en promedio, sin contar la extracción de puntos faciales de MediaPipe)