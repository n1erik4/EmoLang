// Compara web/js/rostro.js con emolang/camara.py sobre resultados reales de MediaPipe.
// Uso: node web/pruebas/metricas.test.mjs casos.json
// (casos.json se genera con:  .venv/bin/python -m emolang.web_casos FOTOS casos.json)
import { readFileSync } from "node:fs";
import { metricasDe, NEUTRAS } from "../js/rostro.js";

const casos = JSON.parse(readFileSync(process.argv[2], "utf8"));
let peor = 0, campoPeor = "", fallas = 0;
for (const c of casos) {
  const m = metricasDe(c.resultado, c.ancho, c.alto, NEUTRAS, c.base);
  for (const [k, v] of Object.entries(c.esperado)) {
    const d = typeof v === "boolean" ? (m[k] === v ? 0 : 1) : Math.abs(m[k] - v);
    if (d > peor) { peor = d; campoPeor = k; }
    if (d > 1e-9) fallas++;
  }
}
console.log(`${casos.length} casos, diferencia máxima ${peor.toExponential(2)} (${campoPeor || "-"}), ${fallas} diferencias`);
process.exit(fallas ? 1 : 0);
