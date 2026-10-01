/**
 * Planning Report: que los ORDINALES de cada fórmula apunten a la fila que suman.
 *
 * ## Por qué esto se corre de verdad y no se lee del código
 *
 * `suma_de` son índices: «esta fila es la suma de las filas 4, 5 y 6». El
 * checkbook arma dos pisos —cada departamento suma sus cuentas, y el TOTAL suma
 * los departamentos— sobre un arreglo que el modo compacto acorta. Un corrimiento
 * de uno no rompe nada que se vea: el exportador comprueba la fórmula contra el
 * número y, cuando no cuadra, **la descarta en silencio**. El reporte baja con
 * media hoja de números pegados y nadie se entera.
 *
 * Por eso acá se arman cuadros con datos sintéticos y se comprueba, celda por
 * celda y columna por columna, que `valores[suma_de]` suma exactamente lo que
 * dice la fila. Es la única manera de ver el corrimiento.
 *
 * Se corre con `node backend/tests/js/planning_report.js` (lo hace
 * `test_planning_report.py`). Sale distinto de cero si algo no cuadra.
 */
const fs = require("fs");
const path = require("path");

const RAIZ = path.resolve(__dirname, "../../../frontend");
const ts = require(path.join(RAIZ, "node_modules/typescript"));

/** Carga un módulo .ts del frontend borrándole los imports y pasándole lo que
 *  necesita por parámetro: no hay bundler acá y tampoco hace falta. */
function cargar(rel, inyecta = {}) {
  const src = fs.readFileSync(path.join(RAIZ, rel), "utf8")
    .replace(/^import[\s\S]*?from\s+"[^"]+";\s*$/gm, "");
  const js = ts.transpileModule(src, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const mod = { exports: {} };
  const nombres = Object.keys(inyecta);
  new Function("module", "exports", "require", ...nombres, js)(
    mod, mod.exports, require, ...nombres.map(n => inyecta[n]));
  return mod.exports;
}

const T = cargar("lib/tresCortes.ts");
const P = cargar("lib/planningReport.ts", {
  componentesDelPL: T.componentesDelPL,
  OPERANDOS_DE_LA_CASCADA: T.OPERANDOS_DE_LA_CASCADA,
  resultadosDelPL: T.resultadosDelPL,
  rotuloAmbito: T.rotuloAmbito,
  suma: T.suma,
});

let fallos = 0;
let checks = 0;
function ok(cond, que) {
  checks++;
  if (!cond) { fallos++; console.log(`  ✗ ${que}`); }
}
const CENT = 0.011;

/* ── Datos sintéticos ───────────────────────────────────────────────────── */

const SID = ["s0", "s1", "s2"];
const ESCENARIOS = SID.map((id, i) => ({
  id, type: "BUDGET", version: ["Working", "Final", "Draft"][i], year: 2027 - i,
}));
/** Doce meses reproducibles y distintos entre sí: un mes que vale lo mismo que
 *  otro esconde justo el corrimiento que esto busca. */
const serie = (semilla) =>
  Array.from({ length: 12 }, (_, m) => Math.round((semilla * 131 + m * 97) % 977) + m);

/* ── 1 · Las columnas ───────────────────────────────────────────────────── */

for (const n of [1, 2, 3]) {
  const nombre = (vi) => `v${vi}`;
  const par = P.parPorDefecto(n);
  const cols = P.columnasPlanning(n, nombre, par);
  ok(cols.length === 1 + 12 + n + (par ? 1 : 0),
     `columnas con ${n} versiones: ${cols.length}`);
  ok(JSON.stringify(cols[13].suma_cols) === JSON.stringify([1,2,3,4,5,6,7,8,9,10,11,12]),
     `el año de la principal suma sus doce meses (${n} versiones)`);
  for (let vi = 1; vi < n; vi++) {
    ok(!cols[13 + vi].suma_cols,
       `el año de la versión comparada ${vi} NO lleva fórmula`);
  }
  if (par) {
    const v = cols[cols.length - 1];
    ok(v.resta[0] === 13 + par[0] && v.resta[1] === 13 + par[1],
       `la variación resta las columnas de AÑO (${n} versiones)`);
    ok(cols[v.resta[0]].label === "Full Year" && cols[v.resta[1]].label === "Full Year",
       `y las dos a las que apunta son columnas de año (${n} versiones)`);
  } else {
    ok(!cols.some(c => c.resta), "con una sola versión no hay variación");
  }
}

/** Que cada fórmula de un cuadro cuadre: `suma_de` contra las filas que nombra,
 *  `combina_filas` con su signo, `resta` y `suma_cols` contra las columnas. */
function auditar(cuadro, etiqueta) {
  const nCols = cuadro.columnas.length - 1;
  for (const f of cuadro.filas) {
    if (f.suma_de) {
      for (let j = 0; j < nCols; j++) {
        // ⚠️ Una celda con algún sumando VACÍO no se audita, y no es una
        // excusa: un blanco no es un cero. Pasa en el checkbook abierto, donde
        // la versión que lee del mayor no tiene sub-líneas. El exportador
        // comprueba celda por celda, ve que la suma no da y deja el número del
        // motor — que es exactamente lo que corresponde ahí.
        if (f.suma_de.some(i => cuadro.filas[i].valores[j] === null)) continue;
        const esperado = f.suma_de.reduce(
          (t, i) => t + (typeof cuadro.filas[i].valores[j] === "number"
            ? cuadro.filas[i].valores[j] : 0), 0);
        const real = typeof f.valores[j] === "number" ? f.valores[j] : 0;
        ok(Math.abs(esperado - real) < CENT,
           `${etiqueta} · «${f.label}» col ${j}: suma_de da ${esperado}, la fila dice ${real}`);
      }
      // Y que no se sume a sí misma ni a otro subtotal por accidente: contar dos
      // veces cuadra igual de bien con el número equivocado.
      ok(!f.suma_de.includes(cuadro.filas.indexOf(f)),
         `${etiqueta} · «${f.label}» se suma a sí misma`);
    }
    if (f.combina_filas) {
      for (let j = 0; j < nCols; j++) {
        const esperado = f.combina_filas.reduce(
          (t, [i, s]) => t + s * (typeof cuadro.filas[i].valores[j] === "number"
            ? cuadro.filas[i].valores[j] : 0), 0);
        const real = typeof f.valores[j] === "number" ? f.valores[j] : 0;
        ok(Math.abs(esperado - real) < CENT,
           `${etiqueta} · «${f.label}» col ${j}: combina da ${esperado}, la fila dice ${real}`);
      }
    }
  }
  // La columna del año contra sus doce meses, fila por fila.
  const anio = cuadro.columnas.findIndex(c => c.suma_cols);
  for (const f of cuadro.filas) {
    const v = f.valores[anio - 1];
    if (typeof v !== "number") continue;
    const meses = f.valores.slice(0, 12);
    if (!meses.every(x => typeof x === "number")) continue;
    const s = meses.reduce((a, b) => a + b, 0);
    if (f.formato === "pct" || f.formato === "num1" || f.esRazon) continue;
    ok(Math.abs(s - v) < CENT,
       `${etiqueta} · «${f.label}»: el año dice ${v} y sus meses suman ${s}`);
  }
}

/* ── 1b · Los doce meses pueden ser de CUALQUIER version ────────────────── */
//
// Owner, 2026-10-01: «quiero que metas la opcion de generar un 12 meses de
// Forecast y Budget 2026».
//
// ⚠️ La formula `=SUM(B5:M5)` TIENE que mudarse con la eleccion. Si se queda
// clavada en la primera columna de año, escribe una suma en una columna cuyos
// doce sumandos no estan en la hoja: el exportador la descarta en silencio y el
// reporte pierde su celda mas mirada sin que nada avise.
for (const mv of [0, 1, 2]) {
  const cols = P.columnasPlanning(3, (vi) => `v${vi}`, [0, 1], 34, mv);
  const conFormula = cols
    .map((c, i) => [c, i])
    .filter(([c]) => c.suma_cols)
    .map(([, i]) => i);
  ok(conFormula.length === 1,
     `una sola columna de año suma sus meses (mv=${mv}): ${conFormula.length}`);
  ok(conFormula[0] === 13 + mv,
     `⚠️ con mv=${mv} la formula va en la columna ${13 + mv} y fue a la `
     + `${conFormula[0]}`);
  ok(cols[13 + mv].sub === `v${mv}`,
     `y esa columna es la de la version ${mv}: ${cols[13 + mv].sub}`);
}

/* ── 2 · El P&L ─────────────────────────────────────────────────────────── */

const PL = {
  year: 2027,
  versiones: SID.slice(0, 2).map(id => ({ scenario_id: id, escenario: id })),
  filas: [
    { tipo: "sec", rotulo: "REVENUES", series: [null, null] },
    { tipo: "det", rotulo: "Rooms", series: [serie(1), serie(2)] },
    { tipo: "det", rotulo: "Food", series: [serie(3), serie(4)] },
    { tipo: "det", rotulo: "Vacía", series: [Array(12).fill(0), Array(12).fill(0)] },
  ],
};
for (const compacto of [false, true]) {
  const c = P.cuadroPlanning(PL, ESCENARIOS, { ambito: "hotel", compacto });
  auditar(c, `P&L compacto=${compacto}`);
  ok(c.filas.length === (compacto ? 3 : 4),
     `el modo compacto saca la fila en cero (${c.filas.length} filas)`);
  ok(c.filas[0].valores.every(v => v === null),
     "el encabezado de sección va SIN números, no en cero");
}

// Y que el cuadro traiga de verdad los meses de esa version, no solo la
// formula: un encabezado que dice una cosa sobre numeros de otra es peor que
// no tener la opcion.
for (const mv of [0, 1]) {
  const c = P.cuadroPlanning(PL, ESCENARIOS,
                             { ambito: "hotel", compacto: true, mesesDe: mv });
  const rooms = c.filas.find(f => f.label === "Rooms");
  const esperado = PL.filas[1].series[mv];
  ok(esperado.every((v, i) => Math.abs(rooms.valores[i] - v) < CENT),
     `⚠️ con mesesDe=${mv} los doce meses son de la version ${mv}`);
  // El año de ESA version sigue siendo la suma de esos meses.
  const suma = esperado.reduce((a, b) => a + b, 0);
  ok(Math.abs(rooms.valores[12 + mv] - suma) < CENT,
     `y su año (col ${12 + mv}) es la suma: ${rooms.valores[12 + mv]} vs ${suma}`);
  ok(c.subtitulo.includes("Los doce meses son de"),
     "el subtitulo dice de quien son los meses");
}

/* ── 3 · Las aperturas ──────────────────────────────────────────────────── */

const GASTOS = SID.map((id, vi) => ({
  scenario_id: id, type: "BUDGET", version: "v", year: 2027,
  meses: [], nombres_cuenta: { 8040: "DEPRECIATION" },
  detalle: {
    opex: { "0110": serie(10 + vi), "0260": serie(20 + vi), "0999": Array(12).fill(0) },
    property: { 8040: serie(30 + vi) },
    revenue: { ROOMS: serie(40 + vi) },
  },
}));
const DEPTOS = { "0110": "Habitaciones", "0260": "Club Madresal" };
for (const compacto of [false, true]) {
  const c = P.cuadroApertura("opex", GASTOS, DEPTOS, ESCENARIOS, { ambito: "", compacto });
  auditar(c, `apertura opex compacto=${compacto}`);
  const total = c.filas[c.filas.length - 1];
  ok(total.es_total && total.suma_de.length === c.filas.length - 1,
     "el TOTAL de la apertura suma TODAS las filas que se ven");
  ok(c.filas.length === (compacto ? 3 : 4),
     `la apertura esconde la clave en cero (${c.filas.length} filas)`);
  ok(c.filas[0].label.startsWith("0110 ") || c.filas[0].label.startsWith("0260 "),
     "la fila lleva el código y el nombre del departamento");
}
const prop = P.cuadroApertura("property", GASTOS, DEPTOS, ESCENARIOS,
                              { ambito: "", compacto: true });
ok(prop.filas[0].label === "8040 · DEPRECIATION",
   `el gasto de propiedad se rotula con el NOMBRE de la cuenta: «${prop.filas[0].label}»`);

/* ── 4 · Los checkbooks ─────────────────────────────────────────────────── */
//
// Dos departamentos con dos cuentas cada uno, más una cuenta en cero: es el caso
// que corre los ordinales cuando el modo compacto la saca.

const DET = {
  clase: "opex", clave: "", rotulo: "Total Operating Expenses",
  versiones: SID.slice(0, 2).map(id => ({ scenario_id: id, escenario: id, fuente: "Auxiliar" })),
  filas: [
    { dept_code: "0110", dept_name: "Habitaciones", cuenta: "7065", nombre: "CLEANING",
      series: { s0: serie(51), s1: serie(52) } },
    { dept_code: "0110", dept_name: "Habitaciones", cuenta: "7350", nombre: "LINEN",
      series: { s0: serie(53), s1: serie(54) } },
    { dept_code: "0110", dept_name: "Habitaciones", cuenta: "7999", nombre: "VACÍA",
      series: { s0: Array(12).fill(0), s1: Array(12).fill(0) } },
    { dept_code: "0260", dept_name: "Club", cuenta: "7065", nombre: "CLEANING",
      series: { s0: serie(55), s1: serie(56) } },
  ],
};
for (const compacto of [false, true]) {
  const c = P.cuadroCheckbook(DET, ESCENARIOS, { ambito: "", compacto });
  auditar(c, `checkbook compacto=${compacto}`);
  const total = c.filas[c.filas.length - 1];
  const subs = c.filas
    .map((f, i) => [f, i])
    .filter(([f]) => f.es_total && f.label.startsWith("Total "))
    .map(([, i]) => i);
  ok(JSON.stringify(total.suma_de) === JSON.stringify(subs),
     "⚠️ el TOTAL suma los SUBTOTALES de departamento, no las cuentas");
  ok(subs.length === 2, `un subtotal por departamento (${subs.length})`);
  // La 7065 de Habitaciones y la 7065 del Club son dos filas, no una.
  const setenta = c.filas.filter(f => f.label.startsWith("7065 "));
  ok(setenta.length === 2,
     `la misma cuenta en dos departamentos son DOS filas (${setenta.length})`);
}
// Y el caso que de verdad corre los ordinales: la cuenta escondida está en el
// MEDIO del primer departamento.
const comp = P.cuadroCheckbook(DET, ESCENARIOS, { ambito: "", compacto: true });
ok(!comp.filas.some(f => f.label.startsWith("7999")),
   "el modo compacto saca la cuenta en cero del medio");

/* ── 5 · Las estadísticas ───────────────────────────────────────────────── */
//
// ⚠️ El año de una RAZÓN no es la suma de los doce meses. Acá se le dan al
// constructor doce ocupaciones del 50% y un año del 50%: si alguien lo hiciera
// sumar, el año saldría 600%.

const mes = (m) => ({
  year: 2027, escenario: "s0", desde: m, hasta: m,
  rooms_available: 100, rooms_occupied: 50, guests: 80,
  occupancy_pct: 0.5, rooms_revenue: 1000 + m, adr: 20, revpar: 10,
  revpar_bruto: 12, club_pagando: 100, club_revenue: 500, club_cuota_promedio: 5,
});
const EST = {
  meses: Array.from({ length: 12 }, (_, i) => mes(i + 1)),
  anios: [{ ...mes(1), desde: 1, hasta: 12, rooms_available: 1200,
            rooms_occupied: 600, guests: 960,
            rooms_revenue: Array.from({ length: 12 }, (_, i) => 1000 + i + 1)
              .reduce((a, b) => a + b, 0) }],
  versiones: [{ scenario_id: "s0", escenario: "s0" }],
};
const ce = P.cuadroEstadisticas(EST, ESCENARIOS, { ambito: "", compacto: false });
const porRotulo = Object.fromEntries(ce.filas.map(f => [f.label, f]));
ok(porRotulo["Ocupación %"].valores[12] === 0.5,
   `⚠️ la ocupación del AÑO viene del servidor, no de sumar: `
   + `${porRotulo["Ocupación %"].valores[12]}`);
ok(porRotulo["ADR"].valores[12] === 20, "el ADR del año tampoco se suma");
ok(porRotulo["Noches disponibles"].valores[12] === 1200,
   "las noches del año sí son el total del período");
ok(Math.abs(porRotulo["Ingreso de habitaciones"].valores[12]
            - porRotulo["Ingreso de habitaciones"].valores.slice(0, 12)
                .reduce((a, b) => a + b, 0)) < CENT,
   "el ingreso del año SÍ coincide con la suma de sus meses");
ok(porRotulo["Ocupación %"].formato === "pct", "la ocupación se mira como porcentaje");

// Una propiedad sin Club: las filas de Club no se dibujan en modo compacto.
const sinClub = { ...EST, anios: [{ ...EST.anios[0], club_pagando: null,
                                    club_revenue: null, club_cuota_promedio: null }] };
const ceSin = P.cuadroEstadisticas(sinClub, ESCENARIOS, { ambito: "", compacto: true });
ok(!ceSin.filas.some(f => f.label.startsWith("Club")),
   "sin Club, no hay filas de Club: `null` no es cero socios");


/* ── 6 · El checkbook ABIERTO en sub-líneas ─────────────────────────────── */
//
// ⚠️ Es la aritmética más frágil del archivo. Las filas de cuenta y las de
// sub-línea se intercalan, así que `desde + i` dejó de servir para el subtotal
// del departamento: apunta a una sub-línea y el subtotal sale mal. Y si el
// subtotal sumara cuentas Y sub-líneas, contaría cada peso dos veces.

const DET_ABIERTO = {
  clase: "opex", clave: "", rotulo: "Total Operating Expenses",
  versiones: SID.slice(0, 2).map(id => ({ scenario_id: id, escenario: id, fuente: "Auxiliar" })),
  filas: [
    { dept_code: "0110", dept_name: "Habitaciones", cuenta: "7105", nombre: "CONTRACT",
      series: { s0: sumaDe([serie(61), serie(62), serie(63)]), s1: serie(64) },
      subs: [
        { code: "800", nombre: "Coral", series: { s0: serie(61) } },
        { code: "801", nombre: "Fumigación Hotel", series: { s0: serie(62) } },
        { code: "802", nombre: "Reservation Fee", series: { s0: serie(63) } },
      ] },
    { dept_code: "0110", dept_name: "Habitaciones", cuenta: "7065", nombre: "CLEANING",
      series: { s0: serie(65), s1: serie(66) },
      subs: [{ code: "800", nombre: "General", series: { s0: serie(65) } }] },
    { dept_code: "0260", dept_name: "Club", cuenta: "7065", nombre: "CLEANING",
      series: { s0: serie(67), s1: serie(68) },
      subs: [] },
  ],
};
function sumaDe(series) {
  return Array.from({ length: 12 }, (_, m) =>
    series.reduce((t, s) => t + s[m], 0));
}

for (const compacto of [false, true]) {
  const c = P.cuadroCheckbook(DET_ABIERTO, ESCENARIOS, { ambito: "", compacto });
  auditar(c, `checkbook abierto compacto=${compacto}`);
  const idx = (pre) => c.filas.findIndex(f => f.label.startsWith(pre));

  // La cuenta suma sus sub-líneas…
  const cuenta = c.filas[idx("7105 ")];
  ok(cuenta.suma_de && cuenta.suma_de.length === 3,
     `7105 suma sus TRES sub-líneas (${cuenta.suma_de && cuenta.suma_de.length})`);
  ok(cuenta.suma_de.every(i => c.filas[i].label.match(/^(800|801|802) · /)),
     "⚠️ y los ordinales apuntan a las SUB-LÍNEAS, no a otra cuenta: "
     + (cuenta.suma_de || []).map(i => c.filas[i].label).join(" | "));

  // …y el subtotal del departamento suma las CUENTAS, no las sub-líneas.
  const sub0110 = c.filas[idx("Total 0110")];
  ok(sub0110.suma_de.every(i => /^7\d{3} · /.test(c.filas[i].label)),
     "⚠️ el subtotal de departamento suma CUENTAS, no sub-líneas: "
     + sub0110.suma_de.map(i => c.filas[i].label).join(" | "));
  ok(sub0110.suma_de.length === 2, "las dos cuentas del 0110");

  // La cuenta sin sub-líneas no declara una suma vacía.
  const club = c.filas.find(f => f.label.startsWith("7065 ")
                                 && c.filas.indexOf(f) > idx("0260"));
  ok(!club.suma_de, "una cuenta sin sub-líneas no declara `suma_de`");

  // ⚠️ La versión que NO abrió deja la celda VACÍA, no en cero.
  // valores: [0..11] los meses · [12] el año de v0 · [13] el de v1 · [14] la
  // variación.
  const coral = c.filas[idx("800 · Coral")];
  ok(coral.valores[13] === null,
     `la versión que no abrió va VACÍA, no en cero: ${coral.valores[13]}`);
  ok(typeof coral.valores[12] === "number", "y la que sí abrió trae su año");
}

/* ── 7 · La plantilla ───────────────────────────────────────────────────── */

const POS = (vi) => ({
  scenario_id: SID[vi], escenario: SID[vi], year: 2027 - vi,
  posiciones: [
    { id: `p${vi}1`, dept_code: "0110", dept_name: "Habitaciones",
      position_code: "500", position_name: "ROOM ATTENDANT", employee_name: "VACANTE",
      employee_type: "1-Permanente", salary_amount: 520000, salary_currency: "CRC",
      fte: Array(12).fill(1), sw: serie(70 + vi) },
    { id: `p${vi}2`, dept_code: "0260", dept_name: "Club",
      position_code: "501", position_name: "HOST", employee_name: "DELGADO MELISSA",
      employee_type: "1-Permanente", salary_amount: 2500, salary_currency: "USD",
      fte: Array(12).fill(0.5), sw: serie(80 + vi) },
  ],
});
for (const metrica of ["fte", "sw"]) {
  const c = P.cuadroPosiciones([POS(0), POS(1)], ESCENARIOS,
                               { ambito: "", compacto: true, metrica });
  auditar(c, `plantilla ${metrica}`);
  const total = c.filas[c.filas.length - 1];
  ok(total.suma_de.every(i => c.filas[i].label.startsWith("Total ")),
     "el TOTAL de la plantilla suma los subtotales de departamento");
  if (metrica === "fte") {
    ok(Math.abs(total.valores[12] - 18) < CENT,
       `12 meses × (1.0 + 0.5) = 18.0 FTE-mes, no ${total.valores[12]}`);
  }
  ok(c.filas.some(f => f.label.includes("₡520,000")),
     "el salario CONTRATADO va en el rótulo, con su símbolo");
  ok(c.filas.some(f => f.label.includes("$2,500")),
     "y el que está en dólares, con el suyo");
}
// ⚠️ TRES PLAZAS IGUALES SON TRES, Y SU PLATA NO SE PIERDE.
//
// Medido el 2026-10-01 contra produccion: en Ama de Llaves habia tres «ROOM
// ATTENDANT · VACANTE», la llave era la misma y el mapa se quedaba con la
// ultima. La hoja decia $289.813,08 contra los $305.465,16 de la cuenta 6000
// del checkbook — 15.652,08 que desaparecian sin que nada fallara, porque un
// total mas chico se ve igual de bien que uno correcto.
const TRES = {
  scenario_id: "s0", escenario: "s0", year: 2027,
  posiciones: [1, 2, 3].map(i => ({
    id: `r${i}`, dept_code: "0113", dept_name: "Ama de Llaves",
    position_code: "500", position_name: "ROOM ATTENDANT", employee_name: "VACANTE",
    employee_type: "1-Permanente", salary_amount: 400000, salary_currency: "CRC",
    fte: Array(12).fill(1), sw: Array(12).fill(100),
  })),
};
for (const metrica of ["fte", "sw"]) {
  const c = P.cuadroPosiciones([TRES], ESCENARIOS,
                               { ambito: "", compacto: true, metrica });
  auditar(c, `tres plazas iguales · ${metrica}`);
  const total = c.filas[c.filas.length - 1];
  const esperado = metrica === "fte" ? 36 : 3600;   // 3 plazas x 12 meses
  ok(Math.abs(total.valores[12] - esperado) < CENT,
     `⚠️ tres plazas iguales (${metrica}): el año tiene que dar ${esperado} y `
     + `da ${total.valores[12]} — la plata de las otras dos se perdio`);
  ok(c.filas.some(f => f.label.startsWith("ROOM ATTENDANT x3 ")),
     "y la fila dice que son TRES: "
     + c.filas.filter(f => f.label.includes("ROOM")).map(f => f.label).join(" | "));
}

// ⚠️ Emparejadas por depto+posición+empleado: al clonar un escenario el id
// cambia, y con el id como llave el cuadro sale en diagonal.
const clonada = P.cuadroPosiciones([POS(0), POS(1)], ESCENARIOS,
                                   { ambito: "", compacto: true });
ok(clonada.filas.filter(f => f.label.startsWith("ROOM ATTENDANT")).length === 1,
   "la misma posición en dos versiones es UNA fila, aunque el id cambie");

/* ── 8 · El reparto ─────────────────────────────────────────────────────── */

const REP = {
  versiones: SID.slice(0, 2).map(id => ({ scenario_id: id })),
  deptos: { "0110": "Habitaciones", "0260": "Club" },
  resumen: [
    { CAFETERIA: { "0110": serie(91), "0260": serie(92) },
      LAUNDRY: { "0110": serie(93) },
      BASES: { CAFETERIA: { "0110": Array(12).fill(10), "0260": Array(12).fill(5) },
               LAUNDRY: { "0110": Array(12).fill(200) } } },
    { CAFETERIA: { "0110": serie(94), "0260": serie(95) },
      LAUNDRY: { "0110": serie(96) }, BASES: { CAFETERIA: {}, LAUNDRY: {} } },
  ],
};
const caf = P.cuadroReparto("CAFETERIA", REP, ESCENARIOS, { ambito: "", compacto: true });
auditar(caf, "reparto cafetería");
ok(caf.filas.some(f => f.label.startsWith("TOTAL (el reparto")),
   "⚠️ el total del reparto dice que tiene que dar CERO: es la regla "
   + "«Cafetería y Lavandería siempre neto $0», no un reparto vacío");
ok(caf.filas.some(f => f.label === "TOTAL FTE"), "y el de la base, el suyo");
const baseFte = caf.filas.find(f => f.label === "TOTAL FTE");
ok(Math.abs(baseFte.valores[12] - 180) < CENT,
   `12 × (10 + 5) = 180 FTE-mes de base, no ${baseFte.valores[12]}`);
ok(baseFte.formato === "num1", "⚠️ la base NO se mira como dólares: son FTE");
const lav = P.cuadroReparto("LAUNDRY", REP, ESCENARIOS, { ambito: "", compacto: true });
auditar(lav, "reparto lavandería");
ok(lav.filas.some(f => f.label === "TOTAL KILOS"), "en lavandería la base son kilos");

/* ── Cierre ─────────────────────────────────────────────────────────────── */

console.log(`${checks} comprobaciones · ${fallos} fallos`);
process.exit(fallos ? 1 : 0);
