import { getEstadisticasCierre, type EstadisticasCierre, type PLDetail,
         type Scenario } from "@/lib/api";
import type { Cuadro, ColumnaCuadro, FilaCuadro } from "@/lib/exportCuadro";

/**
 * La aritmética de los tres cortes, sin una línea de pantalla.
 *
 * Vive aparte para poder correrla contra datos reales y contrastarla con el
 * PDF del owner. Una tabla financiera que sólo se puede verificar mirándola es
 * una tabla que nadie verifica.
 *
 * ## ⚠️ Los tres cortes son tres formas de sumar el MISMO arreglo de doce
 *
 * `/pl-detail/` devuelve los doce meses de cada fila. El mes es un índice, el
 * YTD son los primeros N, y el full year son los doce. No son tres consultas
 * ni tres plantillas: si lo fueran, podrían decir cosas distintas.
 *
 * ## ⚠️ El encabezado estadístico NO se calcula acá
 *
 * Sale de `/pl/{id}/estadisticas/?desde=&hasta=`, una llamada por corte y por
 * versión — el mismo endpoint del que lo saca el resto del cierre. Rederivarlo
 * en el cliente sería una segunda verdad, y hay cuatro reglas finas que no se
 * adivinan mirando los números:
 *
 * * **Nada de esto se suma.** Son razones: sumar los ADR de siete meses da algo
 *   que no significa nada y se ve perfectamente normal —en Amarena, $2.026
 *   contra los $286 reales—. El ADR del período se pondera por noches
 *   ocupadas, no es el promedio simple de los meses.
 * * **El ADR es el de las estadísticas**, no ingreso sobre noches. Los dos
 *   existen y no dan lo mismo: `REV_ROOMS` arrastra ingresos que no son noches
 *   vendidas e infla la tarifa en silencio.
 * * **RevPAR es ingreso TOTAL sobre disponibles**, no ingreso de habitaciones.
 *   Owner, 2026-09-08 (ver `pl_api._revpar`): *«revpar es total revenue
 *   per available room»*. Mide cuánto rinde cada habitación disponible con
 *   TODO lo que el hotel factura —spa, tours, A&B—, no sólo la noche; es lo
 *   que la literatura llama TRevPAR. Contra el PDF del owner, julio 2026:
 *   248.437,33 / 930 = 267,14 exacto. Con el ingreso de habitaciones daba
 *   112,52 — un número que se ve perfectamente razonable y mide otra cosa.
 * * **Los socios de un período son el PROMEDIO de los meses CON socios.**
 *   Owner, 2026-09-02: *«cuando presentes un YTD socios pagando, quiero que me
 *   des un promedio de los meses y no que sume»*. Amarena abrió el Club en
 *   marzo: contar enero y febrero en cero bajaría el promedio de 103 a 74, y
 *   sumar daría 516 socios donde hay 72. La cuota es total sobre total:
 *   ingreso del Club ÷ socios-mes, ponderada.
 */

const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
               "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
const MES3 = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
              "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

export const usd = (n: number | null) =>
  n === null ? "" : Math.abs(n) < 0.005 ? "—"
    : (n < 0 ? "(" : "") + Math.abs(n).toLocaleString("en-US",
        { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "");
export const numero = (n: number | null) =>
  n === null ? "" : n ? n.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—";
export const pct = (n: number | null) =>
  n === null ? "" : n ? (n * 100).toFixed(2) + "%" : "—";

/** Un corte = qué meses entran. Los tres salen del mismo arreglo de doce. */
export interface Corte { clave: "mes" | "ytd" | "full"; titulo: string; meses: number[] }

/** Las filas del encabezado estadístico.
 *
 *  ⚠️ `calc` sólo LEE el corte que ya vino calculado del backend. Si alguna vez
 *  aparece acá una división, es que se está fabricando un segundo indicador. */
export const KPIS: {
  rotulo: string;
  fmt: (n: number | null) => string;
  calc: (e: EstadisticasCierre | null) => number | null;
  fuerte?: boolean;
  /** En un corte de varios meses el número es un promedio mensual, no un
   *  acumulado. La pantalla lo dice al pasar el mouse; el archivo, al pie. */
  promEnRango?: boolean;
}[] = [
  { rotulo: "Total available Rooms", fmt: numero, calc: e => e?.rooms_available ?? null },
  { rotulo: "Total Rooms Occupied", fmt: numero, calc: e => e?.rooms_occupied ?? null },
  { rotulo: "Total Guests", fmt: numero, calc: e => e?.guests ?? null },
  { rotulo: "% Occupancy", fmt: pct, fuerte: true, calc: e => e?.occupancy_pct ?? null },
  { rotulo: "Average Daily Room Only", fmt: usd, fuerte: true, calc: e => e?.adr ?? null },
  { rotulo: "Total RevPAR", fmt: usd, fuerte: true, calc: e => e?.revpar ?? null },
  // ── El Club ────────────────────────────────────────────────────────────────
  // ⚠️ `null` —no cero— cuando la propiedad no tiene Club: un cero se lee como
  // «no hay socios» donde en realidad no hay Club. Por eso `?? null` y no `?? 0`.
  { rotulo: "Socios pagando (Club)", fmt: numero, promEnRango: true,
    calc: e => e?.club_pagando ?? null },
  // Otra pregunta: «cuántos socios hay hoy». En un mes suelto coincide con el
  // promedio, así que la diferencia sólo se ve en YTD y en el full year.
  { rotulo: "Socios al cierre del mes", fmt: numero,
    calc: e => e?.club_pagando_cierre ?? null },
  { rotulo: "Cuota promedio por socio", fmt: usd, fuerte: true, promEnRango: true,
    calc: e => e?.club_cuota_promedio ?? null },
];

/** Los tres ámbitos del cuadro, con el nombre que lleva su pestaña.
 *
 *  Owner, 2026-09-30: *«este tab tiene varias versiones —consolidado, Hotel y
 *  Club—; me gustaría que cuando se baje al excel automáticamente despliegue
 *  las 3 versiones en tab 1, tab 2 y tab 3 con su respectivo nombre»*.
 *
 *  ⚠️ **La lista vive acá y no en la pantalla.** El selector de la pantalla y
 *  el Excel tienen que ofrecer los mismos tres: si un día se agrega un ámbito
 *  en el `<select>` y nadie se acuerda del archivo, el Excel sigue bajando tres
 *  hojas y nada avisa que falta una — ni el archivo ni la pantalla se ven mal.
 */
export const AMBITOS = [
  { clave: "consolidado", rotulo: "Consolidado" },
  { clave: "hotel", rotulo: "Hotel" },
  { clave: "club", rotulo: "Club" },
] as const;

/** El ancho de las columnas, compartido por la franja de estadísticas y por el
 *  cuadro que va debajo.
 *
 *  Owner, 2026-09-30: *«necesito que esto quede súper alineado»*.
 *
 *  ⚠️ **Dos tablas HTML distintas no se alinean solas.** Cada una reparte el
 *  ancho entre sus columnas según su propio contenido, así que con los mismos
 *  datos quedan corridas —y es peor que si estuvieran lejos: se leen como una
 *  sola y cada número cae bajo el encabezado del vecino.
 *
 *  Se alinean cuando las tres cosas coinciden: el MISMO número de columnas
 *  —por eso la franja también lleva su varianza—, el MISMO ancho, y
 *  `table-layout: fixed`, que es lo que hace que el navegador obedezca el ancho
 *  en vez de estirar la columna del texto más largo. */
export const ANCHO_ROTULO = 250;
export const ANCHO_DATO = 116;

/** Los tres renglones que sólo existen si la propiedad tiene Club.
 *
 *  ⚠️ Una definición: la pantalla y el archivo tienen que esconder los MISMOS
 *  renglones, o el Excel llevaría tres filas en blanco que la pantalla no
 *  muestra y que se leen como un dato que falta. */
export const esDelClub = (rotulo: string) =>
  rotulo.startsWith("Socios") || rotulo.startsWith("Cuota");

/** El rango de meses de un corte, tal como lo pide el endpoint (1-12).
 *
 *  ⚠️ Sale del propio corte y no de una tabla aparte: el encabezado y el cuerpo
 *  del cuadro tienen que estar mirando exactamente los mismos meses. */
export const rangoDe = (c: Corte): [number, number] =>
  [c.meses[0] + 1, c.meses[c.meses.length - 1] + 1];

/** El encabezado de cada corte × cada versión. Una llamada por celda.
 *
 *  Una versión que falle queda en `null` y sus celdas salen vacías — mejor un
 *  hueco que un cero que se lee como «no hubo». */
export async function estadisticasDeLosCortes(
  cortes: Corte[], versiones: { scenario_id: string }[],
): Promise<(EstadisticasCierre | null)[][]> {
  return Promise.all(cortes.map(c => {
    const [desde, hasta] = rangoDe(c);
    return Promise.all(versiones.map(v =>
      getEstadisticasCierre(v.scenario_id, desde, hasta).catch(() => null)));
  }));
}

/** Lo que va al pie del cuadro y del Word: las dos reglas que un número del
 *  encabezado no puede contar por sí solo. */
export const PIE_ESTADISTICO =
  "El encabezado es de la propiedad completa y no se acumula: en un corte de "
  + "varios meses la ocupación, el ADR y el RevPAR se rederivan sobre los "
  + "totales del período, los socios son el promedio mensual de los meses con "
  + "socios, y la cuota es el ingreso del Club dividido entre los socios-mes.";

export const suma = (a: number[] | undefined, meses: number[]) =>
  meses.reduce((t, i) => t + (a?.[i] ?? 0), 0);


/** Los tres cortes de un mes de cierre. El mes es un índice; el YTD son los
 *  primeros N; el full year son los doce.
 *
 *  ⚠️ **`anio` va en el rótulo.** Owner, 2026-09-30, mirando el Excel: *«en
 *  algún lugar hay que poner el año… puede ir en el Agosto: que sea Agosto
 *  2026, YTD Agosto 2026 y Full Year 2026»*. Un archivo que se archiva y se
 *  manda tiene que decir de qué año es; el título de la hoja lo dice, pero la
 *  hoja se imprime, se recorta y se pega en otro lado.
 *
 *  Sin `anio` el rótulo sale como antes: hay pantallas que lo llaman sin el
 *  dato a mano y un «Agosto undefined» sería peor que no ponerlo. */
export function cortesDe(mes: number, anio?: number): Corte[] {
  const y = anio ? ` ${anio}` : "";
  return [
    { clave: "mes", titulo: `${MESES[mes - 1]}${y}`, meses: [mes - 1] },
    { clave: "ytd", titulo: `YTD ${MESES[mes - 1]}${y}`,
      meses: Array.from({ length: mes }, (_, i) => i) },
    { clave: "full", titulo: `Full Year${y}`,
      meses: Array.from({ length: 12 }, (_, i) => i) },
  ];
}

/* ══════════════════ El cuadro: pantalla, Excel y Word ════════════════════ */

/** Qué par se resta en cada corte.
 *
 *  ⚠️ En el full year NO se usa el Actual: son los meses cargados y nada más,
 *  así que restarle doce meses de Budget da una diferencia que parece un
 *  derrumbe y sólo dice que el año no terminó. Se usa el Forecast, que es lo
 *  que el corte pregunta: cómo va a aterrizar. El PDF del owner hace lo mismo.
 *
 *  El tipo sale de `escenarios` y no del rótulo: el rótulo es texto libre. */
export function parDe(
  c: Corte, versiones: { scenario_id: string }[], escenarios: Scenario[],
  /** La vista, para que el año completo reste la MISMA versión que está
   *  mostrando en su primera columna. Sin ella se resta el primer FORECAST de
   *  la lista, que puede no ser el que se ve: con dos forecast cargados —uno en
   *  una ranura y el Current— la columna decía uno y la varianza restaba el
   *  otro. */
  vista?: Vista,
): [number, number] | null {
  const tipoDe = (sid: string) => escenarios.find(s => s.id === sid)?.type ?? "";
  const iDe = (t: string) => versiones.findIndex(v => tipoDe(v.scenario_id) === t);
  const budget = iDe("BUDGET");
  if (budget < 0) return null;
  let contra: number;
  if (c.clave !== "full") {
    contra = iDe("ACTUAL");
  } else {
    // El campeón del año completo es quien ocupa su primera columna, siempre
    // que sea un Forecast. Si no hay ninguno, no hay varianza: restarle doce
    // meses de Budget al Actual da un derrumbe que sólo dice que el año no
    // terminó.
    const j = vista?.vi(0, 2);
    contra = (j !== undefined && j >= 0
              && tipoDe(versiones[j]?.scenario_id ?? "") === "FORECAST")
      ? j : iDe("FORECAST");
  }
  if (contra < 0 || contra === budget) return null;
  return [contra, budget];
}

//: Cómo se llama cada tipo de versión en la cabecera, en una palabra.
const TIPO_CORTO: Record<string, string> = {
  ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast",
};

/** El rótulo de la columna de variación. Una sola palabra, en los tres cortes
 *  y en los tres armados. */
export const ROTULO_VAR = "Variance";

/**
 * El rótulo CORTO de una versión: su tipo, en una palabra.
 *
 * Owner, 2026-09-30, con una captura de cómo quiere la cabecera: «Actual»,
 * «Budget», «Variance», «Forecast» arriba y el período abajo. Antes iba el
 * nombre completo —«ACTUAL Final»— pegado al período dentro de la misma celda.
 *
 * ⚠️ **Si dos columnas son del mismo tipo, se les agrega el nombre.** Pasa de
 * verdad: un forecast en una ranura y el Forecast Current ocupando el año
 * completo. Dos columnas que dicen «Forecast» no se distinguen, y el rótulo
 * corto dejaría de identificar la versión, que es lo único que tiene que hacer.
 */
export function rotulosDeVersion(
  versiones: { scenario_id: string }[], escenarios: Scenario[],
): (sid: string) => string {
  const de = (sid: string) => escenarios.find(e => e.id === sid);
  const vistos = new Set<string>();
  const repetido = new Set<string>();
  for (const v of versiones) {
    const t = de(v.scenario_id)?.type ?? "";
    if (!t) continue;
    if (vistos.has(t)) repetido.add(t); else vistos.add(t);
  }
  return (sid: string) => {
    const e = de(sid);
    if (!e) return sid.slice(0, 8);
    const base = TIPO_CORTO[e.type]
      ?? (e.type ? e.type[0] + e.type.slice(1).toLowerCase() : "");
    return repetido.has(e.type) ? `${base} ${e.version}` : base;
  };
}

/**
 * Cómo se dibujan las columnas de un cuadro de tres cortes.
 *
 * ⚠️ **`versiones` no es lo mismo que las columnas.** El año completo necesita
 * el Forecast Current aunque el usuario no lo haya puesto en ninguna ranura: sin
 * él la primera columna del año es el Actual, que sólo tiene los meses cargados
 * —2.928 noches disponibles donde el año tiene 5.824— y la caída contra el
 * Budget sólo significa que el año no terminó (owner, 2026-09-30: *«en el
 * comparativo full year debe ser Forecast y no la versión Actual Final para que
 * contenga los 12 meses»*).
 *
 * Así que el Forecast Current se PIDE siempre y viaja en `versiones` sin
 * columna propia. Quitarlo de una ranura deja de comparar contra él sin romper
 * el año completo, y volver a ponerlo es elegirlo en la ranura otra vez.
 */
export interface Vista {
  /** Los índices de `versiones` que tienen columna, en orden. */
  columnas: number[];
  /** Qué versión ocupa la columna `col` en el corte `ci`. */
  vi: (col: number, ci: number) => number;
}

export function vistaDe(
  versiones: { scenario_id: string }[],
  /** Los ids que SON columnas, en orden. Sin esto, todas. */
  visibles?: string[],
  /** Quién ocupa la primera columna del año completo. */
  actualDelFullYear = "",
  /** Para poder caer en CUALQUIER forecast si el Current no vino. */
  escenarios: Scenario[] = [],
): Vista {
  const columnas = visibles?.length
    ? visibles.map(id => versiones.findIndex(v => v.scenario_id === id))
        .filter(i => i >= 0)
    : versiones.map((_v, i) => i);
  // El campeón del año completo, en orden de preferencia:
  //   1. el Forecast Current, que es el que el owner quiere ver;
  //   2. CUALQUIER forecast que sí haya venido —con las cuatro ranuras llenas
  //      el backend corta la quinta versión y el Current se queda afuera, y
  //      entonces un forecast de una ranura sigue siendo mejor que el Actual:
  //      tiene los doce meses;
  //   3. nada, y la columna se queda con lo que haya. Peor que el ideal, pero
  //      no un número inventado.
  const tipoDe = (sid: string) => escenarios.find(e => e.id === sid)?.type ?? "";
  const full = (actualDelFullYear
    ? versiones.findIndex(v => v.scenario_id === actualDelFullYear) : -1);
  const campeon = full >= 0
    ? full : versiones.findIndex(v => tipoDe(v.scenario_id) === "FORECAST");
  return {
    columnas,
    vi: (col, ci) => (ci === 2 && col === 0 && campeon >= 0 ? campeon
                      : (columnas[col] ?? col)),
  };
}

/** El valor de una fila para una versión y un corte. */
export const valorDe = (
  f: { series: (number[] | null)[] }, vi: number, meses: number[],
) => (f.series?.[vi] ? suma(f.series[vi]!, meses) : null);

/** Las celdas de una fila: cada corte, cada columna, y la varianza.
 *
 *  `de` recibe el índice de VERSIÓN ya resuelto —no la posición de la columna—
 *  y el índice del corte, que es lo que necesitan las filas del encabezado: su
 *  valor no se saca de los meses, sino del corte ya calculado por el backend
 *  para ese rango.
 *
 *  ⚠️ La varianza se calcula sobre las versiones del PAR, no sobre las celdas
 *  ya dibujadas. Son lo mismo mientras el par esté a la vista, y cuando no lo
 *  está —el Forecast Current que viaja sin columna— restar posiciones daría la
 *  diferencia de otras dos versiones. */
export function celdasDe(
  cortes: Corte[], versiones: { scenario_id: string }[], escenarios: Scenario[],
  de: (vi: number, meses: number[], ci: number) => number | null,
  vista?: Vista,
): (number | null)[] {
  const v = vista ?? vistaDe(versiones);
  return cortes.flatMap((c, ci) => {
    const par = parDe(c, versiones, escenarios, v);
    const vs = v.columnas.map((_c, col) => de(v.vi(col, ci), c.meses, ci));
    if (!par) return vs;
    const a = de(par[0], c.meses, ci);
    const b = de(par[1], c.meses, ci);
    return [...vs, a === null || b === null ? null : a - b];
  });
}

/**
 * El cuadro completo, para el Excel de la pantalla Y para el capítulo del Word.
 *
 * ⚠️ UNA definición. El Word arma el mismo archivo que el botón: dos copias se
 * separan en el primer arreglo y nadie sabría cuál de los dos manda.
 */
/** El nombre del ámbito. Si llega uno que no está en la lista se devuelve tal
 *  cual: mejor una pestaña con un nombre raro que una sin nombre. */
export const rotuloAmbito = (clave: string) =>
  AMBITOS.find(a => a.clave === clave)?.rotulo ?? clave;

/* ═══════════ Qué suma cada subtotal de la cascada del P&L ════════════════ */

/** Los totales que son la SUMA del detalle que tienen justo arriba.
 *
 *  ⚠️ **No están todos los totales, y faltan a propósito.** `TOTAL GROSS
 *  OPERATING PROFIT`, los dos EBITDA, el EBT y el `NET PROFIT` son RESTAS: la
 *  utilidad es ingreso menos gasto, y el contrato sólo sabe sumar filas.
 *  Declararlos acá no rompería nada —el exportador comprueba antes de
 *  escribir— pero diría que son algo que no son. */
const SUMA_DEL_DETALLE = new Set([
  "TOTAL REVENUES", "Total Operationg expenses", "OPERATING PROFIT",
  "TOTAL OVERHEAD EXPENSES", "TOTAL RENT AND MANAGEMENT FEES",
  "PROPERTY INSURANCE", "TOTAL OTHER EXPENSES", "CAPITAL EXPENSE",
  "FINANCIAL EXPENSES", "TOTAL DEPRECIATIONS",
  // La hoja del Club tiene su propia cascada. «Total Operating Expenses» con E
  // mayúscula es la del Club; la del Consolidado va con e minúscula, tal como
  // la escribió el owner (ver `CONSOLIDADO` en `pl_detail_api.py`).
  "Total Slary and Benefits", "Total Operating Expenses",
]);

/** Los totales que suman SUBTOTALES, no detalle: el detalle ya está contado
 *  dentro de cada subtotal y sumar los dos niveles contaría todo dos veces. */
// ⚠️ «Operationg» NO es una errata de este archivo: es como se llama el
// subtotal en la plantilla del P&L de esta propiedad
// (`pl_detail_api.py`). Esta tabla se indexa POR ROTULO, asi que tiene que
// decir lo mismo: con «Operating» el subtotal no se encuentra, su formula no
// se declara y el Excel baja ese renglon como numero pegado — sin que nada
// avise. Si algun dia se corrige la plantilla, se corrige aca tambien.
const SUMA_DE_SUBTOTALES = new Set([
  "TOTAL NON OP EXPENSES",   // renta y fees, seguro y otros
  "Total Gastos",            // Club: planilla más opex
]);

/** La cascada: qué le RESTA cada resultado a cuál.
 *
 *  La clave es el rótulo del resultado; el valor, los rótulos que entran con
 *  signo `+` y los que entran con `−`.
 *
 *  ⚠️ **Acá está la mitad que `suma_de` no puede decir.** Un GOP no es la suma
 *  de nada: es Operating Profit menos Overhead. Son las cinco líneas que todo
 *  el mundo mira, y sin esto quedaban como número pegado mientras el detalle
 *  de arriba ya bajaba con fórmula. */
const RESULTADOS: Record<string, { mas: string[]; menos: string[] }> = {
  "TOTAL GROSS OPERATING PROFIT": {
    mas: ["OPERATING PROFIT"], menos: ["TOTAL OVERHEAD EXPENSES"] },
  "EBITDA BEFORE CAPITAL": {
    mas: ["TOTAL GROSS OPERATING PROFIT"], menos: ["TOTAL NON OP EXPENSES"] },
  "EBITDA AFTER CAPITAL": {
    mas: ["EBITDA BEFORE CAPITAL"], menos: ["CAPITAL EXPENSE"] },
  "EARNINGS BEFORE INCOME TAXES": {
    mas: ["EBITDA AFTER CAPITAL"],
    menos: ["FINANCIAL EXPENSES", "TOTAL DEPRECIATIONS"] },
  "NET PROFIT": {
    mas: ["EARNINGS BEFORE INCOME TAXES"], menos: ["Income Taxes (30%)"] },
};

/**
 * Los rótulos que ALGÚN resultado de la cascada usa como operando.
 *
 * ⚠️ **Estas filas no las esconde «esconder las líneas en cero».** No son
 * detalle: son el término de una resta. Si la fila no se dibuja, `resultadosDelPL`
 * no encuentra el operando y no declara la fórmula — y el exportador deja el
 * número del motor sin decir nada.
 *
 * Medido el 2026-10-01 en el Budget Working 2027 de Amarena, donde el impuesto
 * da cero en las tres versiones: `Income Taxes (30%)` se escondía y **NET PROFIT
 * bajaba como número pegado en las tres hojas del P&L** mientras todo el detalle
 * de arriba llevaba fórmula. Es la línea que más se mira del reporte.
 *
 * Un «Income Taxes (30%) — 0.00» visible es, además, lo que corresponde: un P&L
 * que salta del EBT al Net Profit sin mostrar el impuesto obliga a creerle.
 */
export const OPERANDOS_DE_LA_CASCADA = new Set(
  Object.values(RESULTADOS).flatMap(r => [...r.mas, ...r.menos]));

/**
 * Qué filas suma cada subtotal y cada total, en ORDINALES del arreglo que se
 * EMITE.
 *
 * ⚠️ **Se cuenta sobre lo emitido y no sobre la plantilla.** El cuadro saca los
 * espaciadores siempre, los `det` en cero cuando va compacto, y las tres filas
 * del Club cuando el ámbito es Hotel: un índice escrito a mano queda bien el
 * día que se escribe y apunta a otra fila en cuanto cambian los datos — y
 * `suma_de` degrada EN SILENCIO, así que nadie se entera.
 *
 * ⚠️ Lo que devuelve es una PROPUESTA. El exportador la comprueba contra el
 * número que ya venía y sólo entonces escribe la fórmula: si la cascada del
 * ámbito no muestra todos los componentes —pasa en el Hotel, donde el subtotal
 * de renta no queda neto del Club y sus dos renglones sí— queda el número del
 * motor, que es el lado correcto en el que equivocarse.
 */
export function componentesDelPL(
  emitidas: { tipo: "sec" | "det" | "sub" | "tot" | "esp"; rotulo: string }[],
): (number[] | undefined)[] {
  return emitidas.map((f, i) => {
    if (f.tipo !== "sub" && f.tipo !== "tot") return undefined;
    const comp: number[] = [];
    if (SUMA_DEL_DETALLE.has(f.rotulo)) {
      // El bloque de detalle contiguo que tiene arriba. Se corta solo en el
      // encabezado de sección o en el subtotal anterior.
      for (let k = i - 1; k >= 0 && emitidas[k].tipo === "det"; k--) comp.unshift(k);
    } else if (SUMA_DE_SUBTOTALES.has(f.rotulo)) {
      // Los subtotales que hay desde el total anterior. Las filas de detalle
      // del medio NO entran: ya están contadas dentro de su subtotal.
      for (let k = i - 1; k >= 0 && emitidas[k].tipo !== "tot"; k--) {
        if (emitidas[k].tipo === "sub") comp.unshift(k);
      }
    }
    return comp.length ? comp : undefined;
  });
}

/**
 * Qué filas RESTA cada resultado de la cascada, con su signo, en ordinales del
 * arreglo que se EMITE.
 *
 * ⚠️ Se buscan por rótulo sobre lo emitido, y sólo se declara cuando están
 * TODOS los operandos: en el modo compacto una línea puede no haberse
 * dibujado, y una fórmula a la que le falta un término da otra cifra. Si falta
 * alguno, no se declara y queda el número del motor.
 */
export function resultadosDelPL(
  emitidas: { tipo: "sec" | "det" | "sub" | "tot" | "esp"; rotulo: string }[],
): ([number, number][] | undefined)[] {
  const donde = (rot: string) => emitidas.findIndex(f => f.rotulo === rot);
  return emitidas.map(f => {
    const r = RESULTADOS[f.rotulo];
    if (!r) return undefined;
    const partes: [number, number][] = [];
    for (const [lista, signo] of [[r.mas, 1], [r.menos, -1]] as const) {
      for (const rot of lista) {
        const k = donde(rot);
        if (k < 0) return undefined;
        partes.push([k, signo] as [number, number]);
      }
    }
    return partes.length ? partes : undefined;
  });
}

export function cuadroTresCortes(
  datos: PLDetail, mes: number, escenarios: Scenario[], ambito: string,
  compacto = true,
  /** El encabezado por corte × versión, de `estadisticasDeLosCortes`. Sin él
   *  las filas del encabezado salen VACÍAS, no en cero: el archivo diría que
   *  el hotel no vendió nada. */
  stats?: (EstadisticasCierre | null)[][],
  /** Quién ocupa la primera columna del año completo.
   *
   *  ⚠️ El Forecast Current, no el Actual. El Actual del año son los meses
   *  cargados, así que ahí REPETÍA el YTD al centavo — dos columnas idénticas
   *  con rótulos distintos no dicen que el año no terminó, se leen como dos
   *  cifras que casualmente coinciden.
   *
   *  Owner, 2026-09-30, sobre los 17 tabs: la primera columna del full year es
   *  el Forecast Current, y tiene que ser la misma en todos. Los checkbooks y
   *  el armado ya lo hacían; faltaban los tres P&L. */
  actualDelFullYear = "",
  /** Los ids que SON columnas, en orden. Sin esto, todas las que traiga la
   *  respuesta.
   *
   *  ⚠️ El Forecast Current se pide SIEMPRE para poder dibujar el año completo,
   *  incluso cuando el usuario lo sacó de las ranuras. Sin `visibles` volvería
   *  a aparecer como columna en los tres cortes, que es justo lo que se quiso
   *  quitar. */
  visibles?: string[],
): Cuadro {
  const cortes = cortesDe(mes, datos.year);
  const versiones = datos.versiones ?? [];
  const doce = Array.from({ length: 12 }, (_, i) => i);
  const filas = (datos.filas ?? []).filter(f =>
    !compacto || f.tipo !== "det"
    // ⚠️ El operando de una resta de la cascada NO se esconde por estar en cero:
    // sin la fila, el resultado pierde su fórmula y baja como número pegado.
    || OPERANDOS_DE_LA_CASCADA.has(f.rotulo)
    || (f.series ?? []).some(x => x && suma(x, doce) !== 0));
  /** ⚠️ **Se declara ANTES de `columnas`, que es quien la usa.** La versión
   *  anterior de esto era un `const viDe` puesto DESPUÉS, y un `const` no
   *  existe hasta su línea: armar las columnas tiraba «Cannot access 'viDe'
   *  before initialization» y las tres hojas del P&L —Consolidado, Hotel y
   *  Club— se caían del Excel y del Word sin decir por qué. TypeScript no lo
   *  marca: la zona muerta temporal es de ejecución, no de tipos. */
  const vista = vistaDe(versiones, visibles, actualDelFullYear, escenarios);
  /** El rótulo corto de cada versión: «Actual», «Budget», «Forecast». */
  const corto = rotulosDeVersion(versiones, escenarios);

  /** Cuántas columnas ocupa cada corte: sus columnas más la variación, si la
   *  hay. Hace falta para saber en qué columna del Excel cae cada una. */
  const anchoCorte = (c: Corte) =>
    vista.columnas.length + (parDe(c, versiones, escenarios, vista) ? 1 : 0);

  /** En qué columna está A LA VISTA la versión `vi` dentro del corte `ci`, o
   *  `null` si ninguna la muestra. */
  const colDe = (vi: number, ci: number, base: number) => {
    const j = vista.columnas.findIndex((_c, col) => vista.vi(col, ci) === vi);
    return j < 0 ? null : base + j;
  };

  const columnas: ColumnaCuadro[] = [
    { label: "ACCOUNT DESCRIPTION", ancho: 42, formato: "texto" },
    ...cortes.flatMap((c, ci) => {
      // La primera columna de este corte, base 0 sobre `columnas` (la 0 es el
      // rótulo de la fila).
      const base = 1 + cortes.slice(0, ci).reduce((a, x) => a + anchoCorte(x), 0);
      const par = parDe(c, versiones, escenarios, vista);
      return [
        // ⚠️ DOS líneas: la versión arriba, el período abajo. Y la raya gruesa
        // en la primera columna de cada bloque, que es lo que separa el mes del
        // acumulado y del año (owner, 2026-09-30).
        ...vista.columnas.map((_c, col) => ({
          label: corto(versiones[vista.vi(col, ci)].scenario_id),
          sub: c.titulo,
          ...(col === 0 ? { abre_grupo: true } : {}),
          ancho: 16, formato: "usd2" as const })),
        // ⚠️ La variación va como FÓRMULA, no como número (owner, 2026-09-30).
        //
        // El par lo da `parDe`, que en el año completo devuelve Forecast contra
        // Budget y no Actual contra Budget: escribir `=Actual-Budget` a mano
        // ahí pondría en el archivo una resta que el sistema no hace.
        //
        // ⚠️ Y se apunta a la columna que MUESTRA cada operando, no a su índice
        // en `versiones`. En el año completo la primera columna puede estar
        // mostrando otra versión —el Forecast Current que eligió el usuario— y
        // entonces `=C-D` restaría dos columnas que no son las del cálculo. Si
        // el operando no está a la vista, no hay fórmula y queda el número:
        // una celda sin fórmula se puede revisar; una fórmula que resta lo que
        // no es, no.
        ...(par
          ? [{ label: ROTULO_VAR, ancho: 16,
               formato: "usd2" as const,
               ...(colDe(par[0], ci, base) !== null
                   && colDe(par[1], ci, base) !== null
                 ? { resta: [colDe(par[0], ci, base)!,
                             colDe(par[1], ci, base)!] as [number, number] }
                 : {}) }]
          : []),
      ];
    }),
  ];

  const kpi: FilaCuadro[] = KPIS.map((k): FilaCuadro => ({
    label: k.rotulo, es_total: !!k.fuerte,
    formato: k.fmt === pct ? "pct" : k.fmt === numero ? "num" : "usd2",
    // ⚠️ `vi` YA viene resuelto por la vista: aplicarle otra vez la regla del
    // año completo la aplicaría dos veces.
    valores: celdasDe(cortes, versiones, escenarios,
      (vi, _m, ci) => k.calc(stats?.[ci]?.[vi] ?? null), vista),
  })).filter((f, i) => !esDelClub(KPIS[i].rotulo)
                       || f.valores.some(v => v !== null));

  // ⚠️ El arreglo EMITIDO, aparte: es sobre él que se cuentan los ordinales de
  // `suma_de`. `filas` ya sacó los `det` en cero cuando el cuadro va compacto, y
  // el ámbito Hotel viene sin las tres filas del Club, así que un ordinal
  // contado sobre la plantilla apunta a otra fila en cuanto cambia el dato.
  const emitidas = filas.filter(f => f.tipo !== "esp");
  const cuerpo: FilaCuadro[] = emitidas.map(f => ({
    label: f.rotulo,
    // ⚠️ Sección y total no son lo mismo: el total lleva recuadro negro y la
    // sección sólo su banda. Ver `es_seccion` en `exportCuadro`.
    es_total: f.tipo === "tot" || f.tipo === "sub",
    es_seccion: f.tipo === "sec",
    formato: "usd2",
    // ⚠️ Los encabezados de sección van SIN números, no en cero: un cero ahí
    // se leería como «esta sección no tuvo movimiento».
    valores: f.tipo === "sec"
      ? celdasDe(cortes, versiones, escenarios, () => null, vista)
      : celdasDe(cortes, versiones, escenarios,
                 (vi, meses) => valorDe(f, vi, meses), vista),
  }));
  // ⚠️ Los subtotales y totales, como SUMA de las filas que se ven (owner,
  // 2026-09-30: «revisar los subtotales con los totales y que todo lleve
  // fórmula»). La varianza ya bajaba como `resta`; esto es la otra mitad.
  //
  // Lo que se declara es una propuesta: el exportador la comprueba contra el
  // número que calculó el motor y sólo escribe `=X12+X13+…` cuando da lo mismo.
  componentesDelPL(emitidas).forEach((comp, i) => {
    if (comp) cuerpo[i].suma_de = comp;
  });
  // ⚠️ Y la cascada, que NO se suma: el GOP es Operating Profit menos
  // Overhead. Sin esto, las cinco líneas que todo el mundo mira quedaban como
  // número pegado mientras el detalle de arriba ya bajaba con fórmula.
  resultadosDelPL(emitidas).forEach((comb, i) => {
    if (comb) cuerpo[i].combina_filas = comb;
  });

  return {
    // ⚠️ El ámbito va en el TÍTULO y en el nombre de la pestaña. Tres hojas
    // llamadas «Full P&L Ago» las desempata Excel con un número —«Full P&L Ago
    // 2», «…3»— y entonces hay que abrirlas una por una para saber cuál es el
    // Club.
    titulo: `Full P&L ${MESES[mes - 1]} ${datos.year} · ${rotuloAmbito(ambito)}`
            + ` · mes, YTD y full year`,
    subtitulo: `${datos.escenario} · ${ambito} — la varianza del full year es `
      + `Forecast contra Budget: el Actual del año todavía no existe. `
      + PIE_ESTADISTICO,
    hoja: `P&L ${MES3[mes - 1]} ${rotuloAmbito(ambito)}`,
    columnas,
    // ⚠️ El encabezado estadístico va en la FRANJA, no entre las filas.
    //
    // Owner, 2026-09-30, marcando esas nueve filas en el Excel: *«hay que
    // quitar estas líneas, están duplicadas y desconfiguradas»*. Y tenía las
    // dos cosas: el archivo ya trae la franja arriba —la misma lista, las
    // mismas columnas— así que el cuerpo las repetía; y como el cuadro las
    // marcaba `es_total` cuando la estadística es «fuerte», bajaban con el
    // recuadro negro de un total, que es lo que se veía desconfigurado.
    // ⚠️ Un renglón entero en blanco NO va: sin `stats` —el Word los pide
    // aparte— la franja saldría como nueve filas vacías arriba del cuadro, que
    // se leen como que el hotel no vendió nada.
    kpis: kpi.filter(k => k.valores.some(v => v !== null))
             .map(k => ({ label: k.label, valores: k.valores })),
    // El rótulo lleva el corte: «Agosto 2026 · Actual». En la hoja no se
    // escriben —la cabecera de abajo ya los dice— pero el Word sí los imprime.
    kpis_columnas: columnas.slice(1).map(
      c => (c.sub ? `${c.sub} · ${c.label}` : c.label)),
    filas: cuerpo,
  };
}
