/**
 * Pegar desde Excel: que cada número entre como el que es.
 *
 * ## Por qué esto se corre y no se lee
 *
 * `2,1` tiene que entrar como **2,1** y `1,234` como **1234**. La misma coma,
 * dos significados, y la diferencia entre los dos es un factor de diez en el
 * pax — que multiplica los huéspedes y, con ellos, Food, Activities,
 * Transportation y Sustainability. Un error acá no rompe nada: escribe un
 * presupuesto equivocado que se ve perfectamente bien.
 *
 * Es exactamente lo que hace hoy la pantalla de rack rates: `num()` borra todas
 * las comas, así que un `2,1` copiado de un Excel en español entra como 21.
 *
 * Se corre con `node backend/tests/js/pegar_grilla.js` (lo hace
 * `test_pax_por_mes_y_categoria.py`). Sale distinto de cero si algo no cuadra.
 */
const fs = require("fs");
const path = require("path");

const RAIZ = path.resolve(__dirname, "../../../frontend");
const ts = require(path.join(RAIZ, "node_modules/typescript"));

function cargar(rel) {
  const src = fs.readFileSync(path.join(RAIZ, rel), "utf8")
    .replace(/^import[\s\S]*?from\s+"[^"]+";\s*$/gm, "");
  const js = ts.transpileModule(src, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const mod = { exports: {} };
  new Function("module", "exports", "require", js)(mod, mod.exports, require);
  return mod.exports;
}
const P = cargar("lib/pegarGrilla.ts");

let fallos = 0, checks = 0;
function ok(cond, que) {
  checks++;
  if (!cond) { fallos++; console.log(`  ✗ ${que}`); }
}
const es = (entrada, esperado) => {
  const r = P.numeroDeExcel(entrada);
  ok(Math.abs(r - esperado) < 1e-9, `«${entrada}» → ${esperado}, dio ${r}`);
};

/* ── 1 · El número, en todas las formas que lo escribe Excel ────────────── */

es("2,1", 2.1);          // ⚠️ el caso del owner: coma decimal
es("2.1", 2.1);
es("2", 2);
es("2,0", 2);
es("1,8", 1.8);
es("", 0);
es("   ", 0);
es("—", 0);              // la celda vacía que dibuja la pantalla

// Miles contra decimal: la coma separa TRES dígitos → son miles.
es("1,234", 1234);
es("1,234.56", 1234.56);
es("1.234,56", 1234.56); // Excel en español
es("1.234", 1.234);      // ⚠️ punto con tres dígitos: decimal, no miles.
                         //    Es el único ambiguo de verdad y se elige el
                         //    decimal porque un pax de 1.234 personas no existe
                         //    y uno de 1,234 sí.
es("650.000", 650);      // misma regla, y por eso los colones van con símbolo
es("₡650,000", 650000);
es("$1,234.56", 1234.56);
es("$ 1,234.56", 1234.56);
es("(1,054.50)", -1054.5);   // negativo contable
es("-2,1", -2.1);
es("75%", 0.75);
es("(75%)", -0.75);

/* ── 2 · El bloque: filas y columnas ────────────────────────────────────── */

ok(P.celdasPegadas("2,1") === null,
   "una celda sola NO es un pegado de grilla: que lo escriba el navegador");
ok(P.celdasPegadas("") === null, "vacío tampoco");

const fila = P.celdasPegadas("2,0\t2,1\t2,2");
ok(fila && fila.length === 1 && fila[0].length === 3, "una fila de tres meses");

// ⚠️ Excel en Windows manda \r\n. Sin limpiar el \r, el último valor de cada
// fila queda «2,2\r» y esa columna entra en cero.
const dos = P.celdasPegadas("2,0\t2,1\r\n1,8\t1,9\r\n");
ok(dos && dos.length === 2, `dos filas, no ${dos && dos.length} (el \\r\\n y el salto final)`);
ok(dos && dos[0][1] === "2,1" && dos[1][1] === "1,9",
   "y el último valor de cada fila llega limpio: " + JSON.stringify(dos));
ok(P.numeroDeExcel(dos[1][1]) === 1.9, "que además parsea");

/* ── 3 · Dónde cae cada celda ───────────────────────────────────────────── */

function repartir(texto, f0, c0, filas, cols) {
  const puestas = [];
  P.repartirPegado(P.celdasPegadas(texto), f0, c0, filas, cols,
                   (f, c, v) => puestas.push([f, c, v]));
  return puestas;
}

// Pegado de doce meses parado en enero de la primera fila.
const doce = Array.from({ length: 12 }, (_, i) => `2,${i}`).join("\t");
ok(repartir(doce, 0, 0, 4, 12).length === 12, "los doce meses entran");

// ⚠️ Parado en octubre: entran tres y los otros nueve se descartan EN SILENCIO.
// Tiene que llenar octubre, noviembre y diciembre — no fallar.
const tarde = repartir(doce, 0, 9, 4, 12);
ok(tarde.length === 3, `parado en octubre entran 3, no ${tarde.length}`);
ok(tarde[0][1] === 9 && tarde[2][1] === 11, "y son octubre, noviembre, diciembre");

// Un bloque de 4 filas pegado en la última fila: sólo entra una.
const bloque = ["a", "b", "c", "d"].join("\n");
ok(repartir(bloque, 3, 0, 4, 12).length === 1,
   "lo que se sale por abajo se descarta");

// Y cae donde corresponde, no todo en la primera celda — que es el defecto.
const rejilla = repartir("1\t2\n3\t4", 1, 2, 4, 12);
ok(JSON.stringify(rejilla) === JSON.stringify(
     [[1, 2, "1"], [1, 3, "2"], [2, 2, "3"], [2, 3, "4"]]),
   "⚠️ cada valor en SU celda: " + JSON.stringify(rejilla));

console.log(`${checks} comprobaciones · ${fallos} fallos`);
process.exit(fallos ? 1 : 0);
