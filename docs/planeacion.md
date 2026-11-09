# Planeación del proyecto final

Lista de cotejo contra el documento `Proyecto Integrador_Automatas 2.pdf`.
Estado revisado contra el código el 5 de noviembre de 2026.

Entrega: **27 de noviembre o antes**. Meta interna: **todo listo el viernes 20**, para dejar una semana de margen.

`[x]` hecho · `[~]` parcial · `[ ]` falta

## Decisión de arquitectura

- La rúbrica exige ensamblador y registros físicos, así que el compilador tendrá un backend x86-64 que genera un `.asm`.
- EmoVM se conserva para ejecutar con la cámara en tiempo real.
- Objetivo: x86-64 en Windows, con sintaxis Intel, ensamblado y enlazado con GCC de MSYS2. Se comprobó con un factorial recursivo en ensamblador: `factorial(10) = 3628800`.
- Para instalar la herramienta en otra computadora: `pacman -S mingw-w64-ucrt-x86_64-gcc` dentro de MSYS2.

## Tema 1: Análisis semántico

- [x] Acciones semánticas dirigidas por la sintaxis
- [x] Árboles de expresiones y pila semántica
- [x] Verificación de tipos y conversiones implícitas
- [x] Conversiones explícitas: hay `a_ms`, `a_s`, `a_porcentaje`, `a_proporcion`; `a_int` y `a_decimal` ya están
- [x] Tabla de símbolos
- [x] Tabla de direcciones (`emolang/direcciones.py`)
- [x] Detector de errores: no declaradas, tipos, funciones no definidas

## Tema 2: Código intermedio

- [x] Convertidor de notaciones infija, prefija y postfija (`emolang/notaciones.py`)
- [x] Cuádruplas
- [x] Declaraciones, expresiones y asignación
- [x] `si` / `sino` con saltos
- [x] Ciclos: `repetir`, `mientras` por cuadro y, en funciones, `mientras` clásico y `para`
- [x] Funciones con parámetros, retorno y recursión
- [x] Estructuras
- [x] Arreglos

## Tema 3: Optimización

- [x] Local: plegado y subexpresiones comunes
- [x] Mirilla
- [x] Global: propagación de constantes y código muerto
- [x] Ciclos: desenrollado, código invariante y variables de inducción
- [x] Simplificación algebraica
- [x] Reducción de fuerza
- [x] Costos antes y después: `python -m emolang costos`

## Tema 4: Código objeto

- [ ] Asignación de registros
- [ ] Traducción de cuádruplas a `.asm`
- [ ] Segmento de datos para literales de texto
- [ ] Marco de pila para funciones

## Documentación

- [ ] Marco teórico: comparación de representaciones intermedias, optimización, arquitectura y memoria
- [ ] Marco contextual y legal
- [~] GLC con acciones semánticas integradas (hay un PDF de diseño, se debe actualizar)
- [~] Juego de instrucciones intermedias (en `docs/gramatica.md`)
- [~] Manual de arquitectura: falta conectar con el código objeto y el mapeo a ensamblador
- [~] Manual de usuario: hay un README; falta instalación y parámetros completos

## Suite de pruebas

- [~] `tests/semantic/`: hay `ejemplos/errores.emo` y pruebas unitarias; falta la carpeta
- [x] `tests/intermediate/`: ciclos anidados y código redundante, con reducción antes y después
- [~] `tests/execution/`: Fibonacci, factorial, ordenamiento y calculadora ya corren en EmoVM; falta en ensamblador

## Presentación y portafolio

- [ ] Demostración en vivo: fuente, tabla de símbolos, cuádruplas, optimizado y ejecución en ensamblador
- [~] Repositorio con control de versiones: hay un solo commit y cambios sin confirmar
- [ ] Reportes de práctica, matriz de valoración y lista de cotejo

## Módulo de terapia facial

Objetivo 7 del anteproyecto. El alcance es facial, no de cuerpo.

- [x] Rutina de tres ejercicios: sonrisa, elevar cejas y cerrar ojos (`ejemplos/terapia_facial.emo`)
- [x] Conteo y simetría por ejercicio, con resumen de la sesión
- [x] Pruebas con el sensor simulado
- [ ] Probar con cámara real
- [ ] Calibrar los umbrales con esas pruebas
- [ ] Evaluar con participantes (también pendiente en conducción)

## Calendario

| Fechas | Trabajo | Estado |
|---|---|---|
| 5 de noviembre | Ampliar el lenguaje: funciones, ciclos, arreglos, estructuras, constantes y conversiones | Hecho, sin commit |
| 5 de noviembre | Rutina de terapia facial con el sensor simulado | Hecho, sin commit |
| Cuanto antes | Con buena luz: probar la cámara en conducción y terapia facial, y calibrar umbrales. Confirmar los cambios en Git | Pendiente |
| 6 al 8 | Tabla de direcciones y convertidor de notaciones | Hecho, sin commit |
| 8 al 10 | Optimizador: simplificación algebraica, reducción de fuerza, código invariante y costos | Hecho, sin commit |
| 10 al 15 | Backend x86-64: registros, `.asm`, segmentos y marco de pila; los cuatro algoritmos en ensamblador | |
| 15 al 17 | Gestos en ensamblador. Se recorta si el backend se atrasa, porque va después de lo obligatorio | |
| 16 al 18 | Suite de pruebas en `tests/semantic`, `tests/intermediate` y `tests/execution` | |
| 18 al 20 | Reporte final y manuales con los datos reales | |
| 21 al 26 | Ensayos de la defensa y margen para imprevistos | |

**En paralelo desde ahora, sin depender del código:** marco teórico, marco contextual y legal, y aclarar las dudas con la maestra.

## Dudas para la maestra

- El PDF corta la frase "Presentación del proyecto en di". Falta saber qué requisito es.
- "tefextofo" parece un error de escritura de "texto"; conviene confirmarlo.
- ¿Ella proporciona la matriz de valoración y la lista de cotejo?
- ¿"Estructuras" se refiere a registros tipo `struct`? El plan supone que sí.
- ¿Acepta dos ejecuciones: `.asm` para el compilador y EmoVM para la cámara en vivo?
