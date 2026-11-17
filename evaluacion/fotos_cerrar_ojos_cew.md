# Terapia facial: prueba con fotos fijas

Fotos: 2423; descartadas en la revisión: 0; sin rostro detectado: 4; rostro pequeño o de perfil (cara < 15% del ancho o giro > 25°): 28; **útiles: 2391**.

| Etiqueta | Fotos útiles |
|---|---:|
| ojos_cerrados | 1165 |
| ojos_abiertos | 1226 |

## Ejercicios con los umbrales del programa

Una foto positiva es la de la etiqueta del ejercicio; las negativas, las de etiquetas que con seguridad no lo muestran (ojos_abiertos solo cuenta para cerrar_ojos).

| Ejercicio | Condición | Detectadas | No detectadas | Falsas alarmas | Sensibilidad | Especificidad | Mejor umbral con estas fotos |
|---|---|---:|---:|---:|---:|---:|---|
| sonreir | – | sin fotos suficientes | | | | | |
| elevar_cejas | – | sin fotos suficientes | | | | | |
| cerrar_ojos | ear < 0.15 | 1125 | 40 | 69 | 96.6% | 94.4% | ear < 0.146 (96.2% / 94.8%) |

## Distribución de cada métrica por etiqueta

| Etiqueta | sonrisa (mediana) | cejas (mediana) | ear (mediana) |
|---|---:|---:|---:|
| ojos_cerrados | 0.05 | 0.21 | 0.049 |
| ojos_abiertos | 0.03 | 0.04 | 0.293 |

## Simetría medida en las fotos positivas

En fotos de personas sin parálisis la simetría debería ser alta; las fotos con valores bajos conviene revisarlas (cara girada, sombra o expresión asimétrica real).

| Ejercicio | Fotos | Promedio | Mínima | Debajo de 80 % |
|---|---:|---:|---:|---:|
| ojos_cerrados | 1165 | 85.1% | 21.1% | 313 |

Fuentes: Openverse (licencias Creative Commons; autores y licencias en `creditos.csv` de cada carpeta) y CEW, Closed Eyes in the Wild (Song et al., 2014). Una foto es un cuadro: esta prueba calibra umbrales, no mide duraciones ni repeticiones.
