/**
 * Monta GrillaPax DE VERDAD en un DOM y le dispara un paste de Excel.
 *
 * Owner, 2026-10-04, dos veces: *«rate y todo queda en la primera celda»* y,
 * despues de la primera correccion, *«trate de hacer copy paste en pax y sigue
 * igual»*. La segunda resulto ser el bundle viejo todavia servido — pero no
 * habia forma de SABERLO sin esto.
 *
 * `pegar_grilla.js` comprueba el parser. Esto comprueba lo otro, que es lo que
 * fallaba: que el `onPaste` este enganchado al input, que React lo reciba, que
 * los valores terminen cada uno en SU celda, y que la coma siga siendo decimal
 * cuando el guardado los convierte a numero.
 *
 * Necesita `jsdom`, que no esta en el repo. Sin el, el test que lo invoca se
 * saltea — es un arnes de diagnostico, no una barrera de CI.
 */
const fs = require("fs");
const path = require("path");
// ⚠️ `jsdom` no esta en el repo: se busca donde este. Sin el, este arnes no
// corre y el test que lo invoca se saltea — es diagnostico, no barrera.
let JSDOM;
try { ({ JSDOM } = require("jsdom")); }
catch { console.log("sin jsdom: no se puede montar el DOM"); process.exit(77); }

const RAIZ = path.resolve(__dirname, "../../../frontend");
const dom = new JSDOM("<!doctype html><html><body><div id='r'></div></body></html>",
                      { url: "http://localhost" });
global.window = dom.window;
global.document = dom.window.document;
global.navigator = dom.window.navigator;
global.Event = dom.window.Event;
global.MouseEvent = dom.window.MouseEvent;
global.HTMLElement = dom.window.HTMLElement;
global.IS_REACT_ACT_ENVIRONMENT = true;

const React = require(path.join(RAIZ, "node_modules/react"));
const ReactDOM = require(path.join(RAIZ, "node_modules/react-dom/client"));
const { act } = require(path.join(RAIZ, "node_modules/react"));
const ts = require(path.join(RAIZ, "node_modules/typescript"));

/** Carga un .ts/.tsx del frontend resolviendo sus imports de `@/lib/...`. */
const cache = {};
function cargar(rel, extra = {}) {
  if (cache[rel]) return cache[rel];
  const src = fs.readFileSync(path.join(RAIZ, rel), "utf8");
  const js = ts.transpileModule(src, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React,
                       target: ts.ScriptTarget.ES2020, esModuleInterop: true },
  }).outputText;
  const mod = { exports: {} };
  const req = (n) => {
    if (n === "react") return React;
    if (n.startsWith("@/lib/pegarGrilla")) return cargar("lib/pegarGrilla.ts");
    if (n.startsWith("@/lib/api")) return extra.api ?? {};
    return require(n);
  };
  // ⚠️ `React` va inyectado: el .tsx no lo importa (lo pone Next) y el JSX
  // transpilado llama a `React.createElement`.
  new Function("module", "exports", "require", "React", js)(
    mod, mod.exports, req, React);
  return (cache[rel] = mod.exports);
}

/* ── El api, de mentira pero con la forma de verdad ──────────────────────── */
const FILAS = ["A", "B", "C", "D"].map((c, i) => ({
  room_type_id: `rt${i}`, code: `X0${i + 1}`, name: `Categoría ${c}`, units: 4,
  meses: Array.from({ length: 12 }, (_, m) => ({
    month: m + 1, pax: "2.0",
    // ⚠️ La fila C no tiene tarifa en marzo: la celda no se escribe.
    hay_tarifa: !(i === 2 && m === 2),
  })),
}));
let ultimoGuardado = null;
const api = {
  rtLabel: (c, n) => `${c} ${n}`,
  getPaxGrid: async () => ({ scenario_id: "s", year: 2027, semilla: "2.0", filas: FILAS }),
  setPaxGrid: async (_s, celdas) => { ultimoGuardado = celdas;
                                      return { guardadas: celdas.length, sin_tarifa: [] }; },
};

const G = cargar("app/revenue/pax/GrillaPax.tsx", { api });

let fallos = 0, checks = 0;
const ok = (c, q) => { checks++; if (!c) { fallos++; console.log(`  ✗ ${q}`); } };

(async () => {
  const cont = document.getElementById("r");
  const root = ReactDOM.createRoot(cont);
  await act(async () => {
    root.render(React.createElement(G.default, {
      scenarioId: "s", bloqueado: false, onCambio: () => {},
    }));
  });
  await act(async () => { await new Promise(r => setTimeout(r, 10)); });

  const inputs = [...cont.querySelectorAll("input")];
  ok(inputs.length === 4 * 12 - 1,
     `hay un input por celda con tarifa: ${inputs.length} (esperado 47)`);

  /** Dispara un paste de verdad sobre un input, como lo hace el navegador. */
  function pegarEn(idx, texto) {
    const ev = new dom.window.Event("paste", { bubbles: true, cancelable: true });
    ev.clipboardData = { getData: () => texto };
    inputs[idx].dispatchEvent(ev);
    return ev;
  }

  // ── 1 · Doce meses en la primera fila, parado en enero ──────────────────
  const doce = Array.from({ length: 12 }, (_, i) => `2,${i}`).join("\t");
  await act(async () => { pegarEn(0, doce); });
  const fila0 = [...cont.querySelectorAll("input")].slice(0, 12).map(i => i.value);
  ok(JSON.stringify(fila0) === JSON.stringify(
       Array.from({ length: 12 }, (_, i) => `2,${i}`)),
     `⚠️ los doce caen cada uno en SU celda, no en la primera: `
     + JSON.stringify(fila0));

  // ── 2 · Un bloque de 2×2 parado en la fila 2, mes 5 ─────────────────────
  const todos = () => [...cont.querySelectorAll("input")];
  const idxDe = (fila, mes) => {   // los inputs vienen en orden, salteando C-marzo
    let n = 0;
    for (let f = 0; f < 4; f++) for (let m = 0; m < 12; m++) {
      if (f === 2 && m === 2) continue;
      if (f === fila && m === mes) return n;
      n++;
    }
    return -1;
  };
  await act(async () => { pegarEn(idxDe(1, 4), "1,5\t1,6\n1,7\t1,8"); });
  const t = todos();
  ok(t[idxDe(1, 4)].value === "1,5" && t[idxDe(1, 5)].value === "1,6"
     && t[idxDe(2, 4)].value === "1,7" && t[idxDe(2, 5)].value === "1,8",
     "un bloque de 2×2 cae desde la celda donde se pegó: "
     + [t[idxDe(1,4)].value, t[idxDe(1,5)].value,
        t[idxDe(2,4)].value, t[idxDe(2,5)].value].join(" | "));

  // ── 3 · La celda SIN tarifa se saltea y no corre el bloque ──────────────
  await act(async () => { pegarEn(idxDe(2, 0), "9,1\t9,2\t9,3\t9,4") });
  const u = todos();
  ok(u[idxDe(2, 0)].value === "9,1" && u[idxDe(2, 1)].value === "9,2",
     "lo que cae antes de la celda sin tarifa entra");
  ok(u[idxDe(2, 3)].value === "9,4",
     `⚠️ y lo de después NO se corre un mes: abril dice ${u[idxDe(2,3)].value}, `
     + "tiene que decir 9,4");
  ok(cont.textContent.includes("se saltearon"), "y se dice que una quedó fuera");

  // ── 4 · Una celda sola la sigue escribiendo el navegador ────────────────
  const ev = pegarEn(0, "3,3");
  ok(!ev.defaultPrevented,
     "una celda sola no la intercepta la grilla: la escribe el navegador");

  // ── 5 · Lo pegado se GUARDA como número, no como texto ──────────────────
  const btn = [...cont.querySelectorAll("button")]
    .find(b => /Guardar/.test(b.textContent));
  ok(btn && !btn.disabled, "el botón de guardar se habilitó con lo pegado");
  await act(async () => { btn.dispatchEvent(
    new dom.window.MouseEvent("click", { bubbles: true })); });
  await act(async () => { await new Promise(r => setTimeout(r, 10)); });
  // ⚠️ Enero de la fila 0 vale «2,0» y NO «3,3»: el pegado de una celda sola no
  // lo intercepta la grilla, y jsdom no implementa el pegado por defecto del
  // navegador. En un navegador de verdad diría 3,3 — acá lo que se comprueba es
  // justamente que la grilla no se metió.
  const enero0 = (ultimoGuardado ?? []).find(c => c.room_type_id === "rt0" && c.month === 1);
  ok(enero0 && Math.abs(enero0.pax - 2) < 1e-9,
     `enero de la fila 0 guarda lo pegado en el bloque: ${enero0 && enero0.pax}`);
  // Y el decimal con coma sobrevive hasta el guardado, que es lo que importa.
  const feb0 = (ultimoGuardado ?? []).find(c => c.room_type_id === "rt0" && c.month === 2);
  ok(feb0 && Math.abs(feb0.pax - 2.1) < 1e-9,
     `⚠️ «2,1» se guarda como 2.1, no como 21: ${feb0 && feb0.pax}`);
  const mayo1 = (ultimoGuardado ?? []).find(c => c.room_type_id === "rt1" && c.month === 5);
  ok(mayo1 && Math.abs(mayo1.pax - 1.5) < 1e-9,
     `y «1,5» como 1.5: ${mayo1 && mayo1.pax}`);

  console.log(`${checks} comprobaciones · ${fallos} fallos`);
  process.exit(fallos ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
