"""Interfaz de línea de comandos de EmoLang.

    python -m emolang lexico      programa.emo
    python -m emolang sintactico  programa.emo
    python -m emolang semantico   programa.emo
    python -m emolang compilar    programa.emo [-o salida]
    python -m emolang ejecutar    programa.emo [--sensor simulado|csv|camara] ...
    python -m emolang evaluar     programa.emo [--escenario conduccion] ...
"""

import argparse
import json
import os
import sys
import time

from . import automatas as A
from .compilador import compilar_archivo
from .errores import ErrorEmoLang
from .nodos import arbol_texto

# La consola de Windows puede no usar UTF-8 por defecto.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _imprimir_diagnosticos(reporte, notas=True):
    for d in reporte.ordenados():
        if d.nivel != "nota" or notas:
            print("  " + str(d))
    e, a, n = len(reporte.errores), len(reporte.advertencias), len(reporte.notas)
    print(f"\n{e} error(es), {a} advertencia(s)" + (f", {n} nota(s)" if n and notas else ""))


def cmd_lexico(args):
    r = compilar_archivo(args.archivo, hasta="lexico")
    print(f"{'#':>4}  {'LÍNEA:COL':<10} {'TOKEN':<14} LEXEMA")
    for i, t in enumerate(r.tokens):
        print(f"{i:>4}  {f'{t.linea}:{t.columna}':<10} {t.tipo:<14} {t.lexema}")
    _imprimir_diagnosticos(r.reporte)
    return 0 if r.ok else 1


def cmd_sintactico(args):
    r = compilar_archivo(args.archivo, hasta="sintactico")
    if r.ast:
        print(arbol_texto(r.ast))
    _imprimir_diagnosticos(r.reporte)
    return 0 if r.ok else 1


def cmd_semantico(args):
    r = compilar_archivo(args.archivo, hasta="dominio")
    if r.analisis:
        print("TABLA DE SÍMBOLOS")
        print(f"{'NOMBRE':<18} {'CATEGORÍA':<10} {'TIPO':<11} {'ÁMBITO':<28} {'LÍNEA':>5}  VALOR INICIAL")
        for s in r.analisis.tabla:
            v = "" if s.valor is None else repr(s.valor)
            print(f"{s.nombre:<18} {s.categoria:<10} {s.tipo:<11} {s.ambito:<28} {s.linea:>5}  {v}")
        print()
    _imprimir_diagnosticos(r.reporte)
    return 0 if r.ok else 1


def _compilar_o_salir(ruta):
    r = compilar_archivo(ruta)
    if not r.ok:
        _imprimir_diagnosticos(r.reporte)
        print("\nCompilación fallida.")
        sys.exit(1)
    return r


def cmd_compilar(args):
    r = _compilar_o_salir(args.archivo)
    base = os.path.splitext(os.path.basename(args.archivo))[0]
    salida = args.salida or os.path.join("salida", base)
    os.makedirs(salida, exist_ok=True)

    md = [f"# Autómatas generados — `{os.path.basename(args.archivo)}`\n"]
    datos = {}
    for dominio, lista in r.automatas.items():
        md.append(f"## Dominio `{dominio}`\n")
        datos[dominio] = [a.a_dict() for a in lista]
        for a in lista:
            print(f"\n{a.clase.upper()} {a.nombre}  ({len(a.estados)} estados)")
            _describir(a)
            print(A.tabla_texto(a))
            with open(os.path.join(salida, f"{dominio}.{a.nombre}.dot"), "w", encoding="utf-8") as f:
                f.write(A.a_dot(a))
            md.append(f"### {a.clase.capitalize()} `{a.nombre}`\n")
            md.append(_descripcion_md(a))
            md.append("\n**Tabla de transiciones** (→ inicial, * aceptación, `/ x` evento emitido)\n")
            md.append(A.tabla_markdown(a))
            md.append("\n```mermaid\n" + A.a_mermaid(a) + "\n```\n")
    with open(os.path.join(salida, "automatas.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    with open(os.path.join(salida, "programa.json"), "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print()
    _imprimir_diagnosticos(r.reporte)
    print(f"\nArchivos generados en: {os.path.abspath(salida)}")
    print("  automatas.md (tablas + diagramas Mermaid), programa.json, *.dot (Graphviz)")
    return 0


def _describir(a):
    d = a.descripcion
    if a.clase == "gesto":
        rango = f"{d['cuadros_minimos']}" + (f"–{d['cuadros_maximos']}" if d["cuadros_maximos"] else "+")
        tol = f"   |   tolera {d['cuadros_tolerados']} cuadro(s) de interrupción" if d["cuadros_tolerados"] else ""
        print(f"  condición: {d['condicion']}   |   {rango} cuadros a {d['fps']} fps{tol}   |   "
              f"emite {d['emision']}")
    elif a.clase == "secuencia":
        v = f" en {d['ventana_ms']:g} ms" if d["ventana_ms"] else ""
        print(f"  patrón: {' → '.join(d['patron'])}{v}")


def _descripcion_md(a):
    d = a.descripcion
    if a.clase == "gesto":
        hasta = f", máximo {d['hasta_ms']:g} ms ({d['cuadros_maximos']} cuadros)" if d["hasta_ms"] else ""
        return (f"- Condición: `{d['condicion']}`\n- Duración mínima {d['durante_ms']:g} ms "
                f"({d['cuadros_minimos']} cuadros a {d['fps']} fps){hasta}\n"
                + (f"- Tolera interrupciones de hasta {d['cuadros_tolerados']} cuadro(s) "
                   f"({d['tolerancia_ms']:g} ms): `q_i~g` = i cuadros cumplidos y g cuadros de interrupción\n"
                   if d["cuadros_tolerados"] else "") +
                f"- Alfabeto: `1` = condición verdadera en el cuadro, `0` = falsa\n"
                f"- Emite el evento {d['emision']}\n")
    if a.clase == "secuencia":
        v = f" dentro de {d['ventana_ms']:g} ms" if d["ventana_ms"] else ""
        return f"- Patrón: {' → '.join(d['patron'])}{v} (AFD construido con KMP)\n"
    return "- `λ` = transición espontánea (al_entrar / mientras); `[...]` = guarda\n"


def _crear_sensor(args, fps):
    from . import sensores
    if args.sensor == "simulado":
        return sensores.SensorSimulado(args.escenario, fps=fps, semilla=args.semilla,
                                       duracion=args.duracion)
    if args.sensor == "csv":
        if not args.csv:
            sys.exit("Indique el archivo con --csv")
        return sensores.SensorCSV(args.csv, fps=fps)
    from .camara import SensorCamara
    return SensorCamara(indice=args.camara, fps=fps, duracion=args.duracion,
                        mostrar_video=not args.sin_video)


def cmd_ejecutar(args):
    from .ejecucion import ejecutar
    r = _compilar_o_salir(args.archivo)
    if r.reporte.advertencias and not args.silencioso:
        _imprimir_diagnosticos(r.reporte, notas=False)
        print()
    dominio = args.dominio or next(iter(r.analisis.dominios))
    fps = r.analisis.dominios[dominio].fps
    if args.sensor == "simulado" and not args.escenario:
        args.escenario = "rehabilitacion" if "rehab" in dominio else "conduccion"
    sensor = _crear_sensor(args, fps)
    try:
        res = ejecutar(r, dominio, sensor, tiempo_real=args.tiempo_real, sonido=args.sonido,
                       verbose=not args.silencioso)
    except ErrorEmoLang as e:
        print(f"\nError en tiempo de ejecución: {e}")
        return 1
    print("\nRESUMEN DEL MÓDULO DE DOMINIO")
    for k, v in res.resumen.items():
        print(f"  {k}: {v}")
    print(f"  cuadros procesados: {res.cuadros}  |  latencia de procesamiento: "
          f"media {res.latencia_media_ms:.3f} ms, p95 {res.latencia_p95_ms:.3f} ms por cuadro")
    if args.bitacora:
        res.modulo.exportar_bitacora(args.bitacora)
        print(f"  bitácora exportada a {os.path.abspath(args.bitacora)}")
    return 0


def cmd_evaluar(args):
    from .evaluacion import evaluar, fuentes_csv, fuentes_simuladas, reporte_markdown
    r = _compilar_o_salir(args.archivo)
    dominio = args.dominio or next(iter(r.analisis.dominios))
    fps = r.analisis.dominios[dominio].fps
    if args.csv:
        fuentes = fuentes_csv(args.csv, fps)
        anticipo = 500 if args.anticipo is None else args.anticipo
    else:
        escenarios = args.escenario or (["rehabilitacion"] if "rehab" in dominio else ["conduccion", "normal"])
        fuentes = fuentes_simuladas(escenarios, fps, range(args.repeticiones), args.ruido)
        anticipo = args.anticipo or 0
    try:
        res = evaluar(r, dominio, fuentes, tolerancia_ms=args.tolerancia, anticipo_ms=anticipo)
    except ValueError as e:
        print(e)
        return 1
    md = reporte_markdown(res, args.archivo)
    print(md)
    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"\nReporte guardado en {os.path.abspath(args.salida)}")
    return 0


def cmd_capturar(args):
    from .captura import TECLAS, capturar
    print("Captura con etiquetas. Presione la tecla al INICIAR y otra vez al TERMINAR cada gesto:")
    for k, v in TECLAS.items():
        print(f"  [{k}] {v}")
    print("  [q] / Esc terminar\n")
    cuadros, intervalos = capturar(args.destino, indice=args.camara, fps=args.fps, duracion=args.duracion)
    conteo = {}
    for tipo, _, _ in intervalos:
        conteo[tipo] = conteo.get(tipo, 0) + 1
    print(f"\n{cuadros} cuadros guardados en {os.path.abspath(args.destino)}")
    print("Gestos etiquetados: " + (", ".join(f"{t} ×{n}" for t, n in conteo.items()) or "ninguno"))
    return 0


def cmd_diagnostico(args):
    from .diagnostico import PASOS, diagnosticar, reporte
    print(f"Diagnóstico de la cámara: {len(PASOS)} pasos de 4 s (más 2 s de calibración).")
    print("Siga las instrucciones de la ventana; un pitido marca cada paso nuevo.\n")
    print(reporte(*diagnosticar(indice=args.camara)))
    return 0


def cmd_grabar(args):
    from . import sensores
    s = sensores.SensorSimulado(args.escenario, fps=args.fps, semilla=args.semilla, duracion=args.duracion)
    sensores.grabar_csv(s, args.destino)
    print(f"Métricas simuladas guardadas en {os.path.abspath(args.destino)}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="emolang", description="Compilador y motor de EmoLang")
    sub = p.add_subparsers(dest="comando", required=True)

    for nombre, ayuda in [("lexico", "muestra la tabla de tokens"),
                          ("sintactico", "muestra el árbol de sintaxis abstracta"),
                          ("semantico", "muestra la tabla de símbolos y validaciones")]:
        sp = sub.add_parser(nombre, help=ayuda)
        sp.add_argument("archivo")

    sp = sub.add_parser("compilar", help="genera los autómatas (tablas y diagramas)")
    sp.add_argument("archivo")
    sp.add_argument("-o", "--salida")

    sp = sub.add_parser("ejecutar", help="ejecuta el programa sobre un sensor")
    sp.add_argument("archivo")
    sp.add_argument("--sensor", choices=["simulado", "csv", "camara"], default="simulado")
    sp.add_argument("--escenario", help="conduccion | normal | rehabilitacion (sensor simulado)")
    sp.add_argument("--csv", help="archivo de métricas para --sensor csv")
    sp.add_argument("--camara", type=int, default=0, help="índice de la cámara")
    sp.add_argument("--dominio")
    sp.add_argument("--duracion", type=float, help="segundos a ejecutar")
    sp.add_argument("--semilla", type=int, default=7)
    sp.add_argument("--tiempo-real", action="store_true", help="simulación al ritmo real del fps")
    sp.add_argument("--sonido", action="store_true", help="pitido al activar alarmas")
    sp.add_argument("--sin-video", action="store_true", help="no mostrar ventana de cámara")
    sp.add_argument("--bitacora", help="exportar bitácora de eventos a CSV")
    sp.add_argument("--silencioso", action="store_true")

    sp = sub.add_parser("evaluar", help="exactitud, falsos positivos/negativos y latencia")
    sp.add_argument("archivo")
    sp.add_argument("--dominio")
    sp.add_argument("--escenario", action="append")
    sp.add_argument("--repeticiones", type=int, default=5, help="semillas aleatorias por escenario")
    sp.add_argument("--csv", action="append", help="grabación real etiquetada (repetible)")
    sp.add_argument("--ruido", type=float, default=1.0, help="multiplicador del ruido del simulador")
    sp.add_argument("--anticipo", type=float,
                    help="ms antes del inicio etiquetado en que se acepta la detección (500 en grabaciones reales)")
    sp.add_argument("--tolerancia", type=float, default=1500, help="ms de tolerancia tras el evento real")
    sp.add_argument("-o", "--salida", help="guardar reporte Markdown")

    sp = sub.add_parser("capturar", help="graba métricas de la cámara con etiquetas manuales")
    sp.add_argument("destino")
    sp.add_argument("--camara", type=int, default=0)
    sp.add_argument("--fps", type=int, default=30)
    sp.add_argument("--duracion", type=float, help="segundos máximos de grabación")

    sp = sub.add_parser("diagnostico", help="verifica con la cámara que cada métrica responda bien")
    sp.add_argument("--camara", type=int, default=0)

    sp = sub.add_parser("grabar", help="genera un CSV de métricas simuladas")
    sp.add_argument("escenario")
    sp.add_argument("destino")
    sp.add_argument("--fps", type=int, default=30)
    sp.add_argument("--semilla", type=int, default=7)
    sp.add_argument("--duracion", type=float)

    args = p.parse_args(argv)
    return {"lexico": cmd_lexico, "sintactico": cmd_sintactico, "semantico": cmd_semantico,
            "compilar": cmd_compilar, "ejecutar": cmd_ejecutar, "evaluar": cmd_evaluar,
            "capturar": cmd_capturar, "diagnostico": cmd_diagnostico, "grabar": cmd_grabar}[args.comando](args)


if __name__ == "__main__":
    sys.exit(main())
