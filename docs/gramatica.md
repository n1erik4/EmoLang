# Especificación de EmoLang

## 1. Componentes léxicos

| Categoría | Patrón / lexemas |
|---|---|
| Identificador `ID` | `[a-zA-Z_][a-zA-Z0-9_]*` que no sea palabra reservada |
| Entero `ENTERO` | `[0-9]+` |
| Decimal `DECIMAL` | `[0-9]+\.[0-9]+` |
| Cadena `CADENA` | `"…"` con escapes `\n \t \" \\` (una sola línea) |
| Unidades | `ms`, `s`, `%` (pueden ir pegadas al número: `100ms`, `2s`, `40%`) |
| Comentarios | `// hasta fin de línea` y `/* bloque */` |
| Operadores | `+ - * / < <= > >= == != =` y lógicos `y o no` |
| Delimitadores | `{ } ( ) [ ] ; , :` |

**Palabras reservadas:** `dominio sensor var gesto secuencia maquina inicial estado al_entrar cuando ignorar ir_a durante hasta tolerando en si sino mientras repetir veces int decimal bool string duracion proporcion verdadero falso y o no ms s`

El analizador léxico es un AFD implementado a mano (`emolang/lexico.py`) que aplica la regla del lexema más largo (`<=` antes que `<`).

## 2. Gramática libre de contexto (EBNF)

```ebnf
programa      = dominio , { dominio } ;
dominio       = "dominio" ID "{" { miembro_dom } "}" ;
miembro_dom   = sensor | decl_var | gesto | secuencia | maquina ;

sensor        = "sensor" ID "{" { decl_var } "}" ;
decl_var      = "var" ID ":" tipo "=" expr ";" ;
tipo          = "int" | "decimal" | "bool" | "string"
              | "duracion" | "proporcion" | "gesto" | "secuencia" ;

gesto         = "gesto" ID "=" expr "durante" expr [ "hasta" expr ] [ "tolerando" expr ] ";" ;
secuencia     = "secuencia" ID "=" "[" ID { "," ID } "]" [ "en" expr ] ";" ;

maquina       = "maquina" ID "inicial" ID "{" estado { estado } "}" ;
estado        = "estado" ID "{" { miembro_est } "}" ;
miembro_est   = decl_var
              | "al_entrar" bloque
              | "cuando" ID ( "ir_a" ID ";" | bloque )
              | "mientras" expr bloque
              | "ignorar" ID { "," ID } ";" ;

bloque        = "{" { sentencia } "}" ;
sentencia     = decl_var
              | ID "=" expr ";"
              | "si" expr bloque [ "sino" ( si | bloque ) ]
              | "repetir" expr "veces" bloque
              | "ir_a" ID ";"
              | llamada ";" ;

expr          = disyuncion ;
disyuncion    = conjuncion { "o" conjuncion } ;
conjuncion    = negacion { "y" negacion } ;
negacion      = "no" negacion | comparacion ;
comparacion   = suma [ ( "<" | "<=" | ">" | ">=" | "==" | "!=" ) suma ] ;
suma          = termino { ( "+" | "-" ) termino } ;
termino       = unario { ( "*" | "/" ) unario } ;
unario        = "-" unario | primario ;
primario      = ( ENTERO | DECIMAL ) [ "ms" | "s" | "%" ]
              | CADENA | "verdadero" | "falso"
              | ID | llamada | "(" expr ")" ;
llamada       = ID "(" [ expr { "," expr } ] ")" ;
```

La gramática es LL(1) salvo en `sentencia` con `ID`, que se decide con un token de anticipación adicional (`=` → asignación, `(` → llamada). Se implementa con un analizador descendente recursivo (`emolang/sintactico.py`) con recuperación de errores en modo pánico (sincroniza en `;`, `}` y en el inicio de la siguiente declaración).

**Precedencia** (de menor a mayor): `o` < `y` < `no` < comparaciones (no asociativas) < `+ -` < `* /` < `-` unario.

## 3. Sistema de tipos

| Tipo | Valores | Ejemplo |
|---|---|---|
| `int` | enteros | `3` |
| `decimal` | reales | `0.25` |
| `bool` | `verdadero`, `falso` | |
| `string` | texto | `"hola"` |
| `duracion` | tiempo (se normaliza a milisegundos) | `300 ms`, `1.5 s` |
| `proporcion` | real en [0, 1] | `0.4`, `40%` |
| `gesto` | patrón temporal (se declara con `gesto`) | |
| `secuencia` | lista ordenada de gestos (se declara con `secuencia`) | `[bostezo, cabeceo]` |

### Reglas de conversión

| Origen → destino | ¿Permitida? | Nota |
|---|---|---|
| `int` → `decimal` | Sí | ensanchamiento |
| `decimal` → `proporcion` | Sí | si el valor es constante se verifica que esté en [0, 1] |
| `proporcion` → `decimal` | Sí | |
| `decimal` → `int` | **No** | pérdida de precisión |
| número → `duracion` | **No** | se exige la unidad: `5 s` |
| `ms` ↔ `s` | Sí | `1 s == 1000 ms` (normalizado en compilación) |

### Operadores

| Operación | Resultado |
|---|---|
| `int (+ - *) int` | `int` |
| `int + decimal`, `decimal + proporcion`, … | `decimal` |
| `num / num` | `decimal` |
| `duracion ± duracion` | `duracion` |
| `duracion * num`, `duracion / num` | `duracion` |
| `duracion / duracion` | `decimal` |
| `string + cualquiera` | `string` (concatenación) |
| comparación numérica o entre duraciones | `bool` |
| `y`, `o`, `no` | requieren y devuelven `bool` |

Conversiones explícitas: `a_porcentaje(0.4) = 40.0`, `a_proporcion(40) = 40%`, `a_ms(2 s) = 2000.0`, `a_s(500 ms) = 0.5`.

## 4. Ámbitos

```
global      métricas del sensor (solo lectura) y funciones predefinidas
└─ dominio  variables del dominio y de sus sensores, gestos, secuencias, máquinas
   └─ maquina   nombres de estados
      └─ estado     variables locales (se reinicializan cada vez que se entra al estado)
         └─ bloque     variables declaradas dentro de { }
```

Las condiciones de los gestos se evalúan en el ámbito del dominio: pueden usar métricas y variables globales (umbrales), pero no variables locales de un estado ni llamadas a funciones.

## 5. Métricas del sensor

| Métrica | Tipo | Rango | Descripción |
|---|---|---|---|
| `ear`, `ear_izq`, `ear_der` | proporcion | 0–1 (típico 0–0.45) | razón de aspecto del ojo |
| `mar` | proporcion | 0–1 | razón de aspecto de la boca |
| `sonrisa`, `sonrisa_izq`, `sonrisa_der` | proporcion | 0–1 | intensidad de sonrisa |
| `cejas` | proporcion | 0–1 | elevación de cejas |
| `simetria` | proporcion | 0–1 | simetría izquierda/derecha |
| `perclos` | proporcion | 0–1 | % de tiempo con ojos cerrados (60 s) |
| `pitch`, `yaw`, `roll` | decimal | −90–90 | pose de la cabeza en grados |
| `rostro` | bool | | hay un rostro en el cuadro |

## 6. Funciones predefinidas

| Función | Tipo | Descripción |
|---|---|---|
| `alarma(string)` | — | activa la alarma (módulo de conducción) |
| `detener_alarma()` | — | apaga la alarma |
| `registrar(string)` | — | agrega un evento a la bitácora |
| `mostrar(…)` | — | imprime valores |
| `contar_repeticion()` | — | registra una repetición y su simetría (módulo de rehabilitación) |
| `repeticiones()` | `int` | repeticiones contadas |
| `tiempo_en_estado()` | `duracion` | tiempo desde que se entró al estado |
| `abs(num)` | num | valor absoluto |
| `a_porcentaje`, `a_proporcion`, `a_ms`, `a_s` | | conversiones explícitas |

## 7. Semántica de ejecución

En cada cuadro de video (`fps` del sensor, 30 por defecto):

1. Cada **gesto** evalúa su condición → símbolo `1`/`0` y avanza su AFD. Un gesto `durante D` emite su evento cuando la condición se ha sostenido `⌈D/periodo⌉` cuadros seguidos. Con `hasta M` el evento se emite **al soltar** la condición, solo si duró entre `D` y `M` (por ejemplo, un parpadeo y no un microsueño).
   Con `tolerando T` se perdonan interrupciones de hasta `K = round(T/periodo)` cuadros: el conteo no avanza durante la interrupción, pero tampoco se reinicia (estados `q_i~g` = i cuadros cumplidos y g cuadros de interrupción). Con `hasta`, el gesto se considera "soltado" cuando la interrupción supera K cuadros.
2. Cada **secuencia** consume los eventos de sus gestos con un AFD de reconocimiento de patrones (KMP). Si entre el primer y el último evento pasa más tiempo que la ventana `en W`, se reinicia.
3. Cada **máquina** procesa los eventos del cuadro en su estado actual: se ejecuta el primer `cuando` que coincide con cada evento; después se evalúan los `mientras` del estado. Una transición (`ir_a`) termina el cuadro de esa máquina, reinicia las variables locales del nuevo estado y ejecuta su `al_entrar`.
4. `mientras C { … }` se evalúa **una vez por cuadro** y nunca bloquea; `repetir N veces` se ejecuta completo dentro del cuadro.

## 8. Diagnósticos

| Fase | Ejemplos |
|---|---|
| Léxica | carácter no reconocido, cadena o comentario sin cerrar, `3abc` |
| Sintáctica | token inesperado, falta `durante`, `mientras` fuera de un estado, comparaciones encadenadas |
| Semántica | identificador no declarado, redeclaración, tipos incompatibles, asignación a métricas, aridad/tipos de funciones, `ir_a` a estado inexistente |
| Nota (no impide compilar) | un evento cambia de estado en unos estados pero se ignora en otros sin declararlo con `ignorar` (los estados finales no cuentan) |
| Dominio | umbral fuera de rango o atípico, gesto imposible (condición insatisfacible, mínimo > máximo, máximo < un cuadro), tolerancia ≥ duración mínima, secuencia imposible, estado inalcanzable, transiciones contradictorias, eventos que nunca se disparan, gestos sin usar, condición siempre verdadera |

La detección de gestos imposibles usa **análisis de intervalos**: la condición se lleva a forma normal disyuntiva sobre intervalos por métrica (aplicando De Morgan para `no`) y se intersecta con el rango válido de cada métrica; si todas las "cajas" quedan vacías, la condición es insatisfacible.
