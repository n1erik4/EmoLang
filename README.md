# EmoLang

Lenguaje de dominio específico para describir **gestos faciales como patrones temporales**, verificarlos semánticamente y compilarlos a **autómatas finitos** que se ejecutan en tiempo real con una cámara estándar (MediaPipe).

Proyecto Integrador · Lenguajes y Autómatas II · Instituto Tecnológico de Oaxaca · Grupo 7SB

```emo
dominio conduccion {
    sensor camara { usar ear, mar, pitch; var fps : int = 30; }
    var umbral_ojo : proporcion = 0.20;

    gesto parpadeo   = ear < umbral_ojo durante 60 ms hasta 400 ms;
    gesto microsueno = ear < umbral_ojo durante 1 s tolerando 100 ms;
    gesto bostezo    = mar > 55% durante 1.5 s;
    gesto cabeceo    = pitch > 15.0 y ear < 0.27 durante 300 ms;
    secuencia fatiga = [bostezo, cabeceo] en 10 s;

    maquina monitor inicial normal {
        estado normal {
            cuando microsueno ir_a alerta;
            cuando bostezo    ir_a somnoliento;
        }
        estado somnoliento { cuando fatiga ir_a alerta; }
        estado alerta {
            al_entrar { alarma("¡Despierte!"); registrar("microsueño"); }
        }
    }
}
```

## Estructura

```
emolang/
  lexico.py        analizador léxico (AFD hecho a mano)            → objetivo 2
  sintactico.py    analizador sintáctico descendente recursivo + AST → objetivo 2
  nodos.py         nodos del árbol de sintaxis abstracta
  semantico.py     tabla de símbolos, ámbitos, verificación de tipos → objetivo 3
  tipos.py         reglas de tipos y conversiones
  validaciones.py  validaciones de dominio (análisis de intervalos, BFS) → objetivo 4
  automatas.py     generador de AFD: tablas, Graphviz (DOT), Mermaid, JSON → objetivo 5
  intermedio.py    código intermedio: cuádruplas con pila semántica
  optimizador.py   seis técnicas de optimización sobre las cuádruplas
  emoc.py          formato del programa compilado (.emoc)
  vm.py            EmoVM: ejecuta el .emoc cuadro por cuadro              → objetivo 6
  motor.py         intérprete directo del AST, referencia para las pruebas de equivalencia
  camara.py        sensor de cámara con MediaPipe Face Landmarker   → objetivo 6
  sensores.py      sensor simulado (con verdad de terreno) y CSV
  modulos.py       módulos de conducción y rehabilitación           → objetivo 7
  evaluacion.py    exactitud, falsos positivos/negativos, latencia  → objetivo 8
ejemplos/          conduccion.emo, rehabilitacion.emo, terapia_facial.emo, errores.emo
docs/gramatica.md  gramática EBNF, tipos, ámbitos, semántica           → objetivo 1
  captura.py       grabación con cámara + etiquetado manual (verdad de terreno)
tests/             pruebas unitarias de todas las fases
docs/protocolo_evaluacion.md   cómo grabar y evaluar con datos reales
```

## Uso

El compilador y el sensor simulado no tienen dependencias (Python ≥ 3.10).

```bash
python -m emolang lexico     ejemplos/conduccion.emo   # tabla de tokens
python -m emolang sintactico ejemplos/conduccion.emo   # árbol de sintaxis abstracta
python -m emolang semantico  ejemplos/errores.emo      # tabla de símbolos + errores
python -m emolang cuadruplas ejemplos/conduccion.emo   # cuádruplas y optimización
python -m emolang compilar   ejemplos/conduccion.emo   # .emoc y autómatas → salida/conduccion/

python -m emolang ejecutar ejemplos/conduccion.emo      # sensor simulado
python -m emolang ejecutar salida/conduccion/conduccion.emoc   # ya compilado
python -m emolang ejecutar ejemplos/rehabilitacion.emo --bitacora eventos.csv
python -m emolang ejecutar ejemplos/terapia_facial.emo --bitacora sesion.csv   # sonrisa, cejas y ojos
python -m emolang evaluar  ejemplos/conduccion.emo -o evaluacion/resultados.md
python -m emolang evaluar  ejemplos/conduccion.emo --ruido 3 --repeticiones 20   # robustez

python -m unittest discover -s tests -t .
```

`compilar` genera `salida/<programa>/<programa>.emoc` (lo que ejecuta EmoVM), `automatas.md` (tablas de transiciones y diagramas Mermaid, se ven directamente en GitHub/VS Code), `programa.json` y un `.dot` por autómata (`dot -Tpng archivo.dot -o archivo.png` si tienen Graphviz).

### Con cámara (MediaPipe)

MediaPipe no soporta Python 3.13+, así que se usa el entorno virtual con Python 3.11:

```bash
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m emolang ejecutar ejemplos/conduccion.emo --sensor camara --sonido
```

Los primeros 2 s calibran la postura neutra (mire al frente). `q` o `Esc` para salir. El modelo `modelos/face_landmarker.task` se descarga solo la primera vez.

**Evaluación con datos reales:** `capturar` graba las métricas de la cámara mientras usted marca el inicio y fin de cada gesto con una tecla; después `evaluar --csv` mide exactitud, FP/FN y latencia contra esas etiquetas. Ver [docs/protocolo_evaluacion.md](docs/protocolo_evaluacion.md).

```bash
.venv\Scripts\python -m emolang capturar grabaciones/p1_conduccion.csv
python -m emolang evaluar ejemplos/conduccion.emo --csv grabaciones/p1_conduccion.csv -o evaluacion/real.md
```

Otras opciones de `ejecutar`: `--sensor csv --csv datos.csv`, `--escenario normal|conduccion|rehabilitacion`, `--tiempo-real`, `--duracion 60`. Para generar un CSV de prueba: `python -m emolang grabar conduccion datos.csv`.

## Cómo se traduce un gesto a autómata

`gesto microsueno = ear < 0.2 durante 1 s;` a 30 fps se convierte en un AFD sobre el alfabeto {1, 0} con 31 estados: `q_i` = "la condición lleva i cuadros seguidos". Con `1` avanza, con `0` vuelve a `q0`; la transición `q29 →1→ q30` emite el evento `microsueno`. Con `hasta`, el evento se emite al soltar la condición dentro del intervalo (así se distingue un parpadeo de un microsueño). Con `tolerando 100 ms` se agregan estados `q_i~g` que perdonan hasta 3 cuadros de interrupción (ruido de la cámara) sin reiniciar el conteo. Las secuencias usan un AFD de reconocimiento de patrones (KMP) y las máquinas de estado se traducen directamente, con `λ` para las transiciones espontáneas. Detalles en [docs/gramatica.md](docs/gramatica.md).
