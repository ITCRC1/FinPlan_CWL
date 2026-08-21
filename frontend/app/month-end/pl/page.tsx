"use client";
/**
 * Cierre de mes — P&L: cuatro columnas libres.
 *
 * Empezó con tres columnas atadas a un rol (Actual · Budget · Reforecast) y el
 * owner pidió lo contrario: **cuatro ranuras que no son esclavas de nada**, cada
 * una con el escenario que él quiera. Comparar dos versiones del Budget 2027
 * entre sí, o el Actual 2025 contra el 2026, son preguntas legítimas que la
 * versión con roles no dejaba hacer.
 *
 * **La variación necesita saber contra qué.** Con columnas libres ya no hay un
 * «budget» implícito, así que se elige: qué columna se compara y contra cuál.
 * Por defecto la 1 contra la 2, que es el caso de siempre.
 *
 * **El signo depende de la línea.** En ingresos y utilidades más es mejor; en
 * gastos más es peor. Sin eso, un gasto por encima saldría en verde — al revés
 * de lo que hay que ver al cerrar el mes.
 *
 * No hay endpoint nuevo: `/pl/compare/` devuelve por escenario los tres
 * horizontes (mes, YTD y año completo), así que cambiar de vista no cuesta un
 * viaje al servidor.
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  getScenarios, getPLCompare, getGastoPorClase, getCashflowBudget, getFbDetalle, getIngresoDetalle,
  getConsultaCatalogo, correrConsulta, bajarConsultaExcel,
  type ConsultaFila, type ConsultaCatalogo, type FbDetalle, type FbMes, type IngresoDetalle,
  type Scenario, type PLCompareVersion, type PLColumn, type GastoEscenario,
} from "@/lib/api";
import { HOTEL_ID } from "@/lib/hotel";
import { elegir } from "@/lib/escenarioPreferido";
import { bajarCuadros, type Cuadro, type FilaCuadro, type ColumnaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

/** Respaldo si el catálogo de idioma no trae la lista larga de meses. */
const MESES_FALLBACK = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"];

const RANURAS = 4;

/** Los sub-tabs. El primero es la cascada; los otros cinco abren una clase.
 *
 *  El gasto de propiedad se abre por CUENTA del mayor y no por departamento:
 *  vive todo en el mismo depto, asi que abrirlo por depto seria una sola fila. */
const VISTAS = [
  { key: "pl" },
  { key: "revenue" },
  { key: "payroll" },
  { key: "cost" },
  { key: "opex" },
  { key: "property" },
  { key: "consulta" },
  { key: "flow" },
  { key: "simple" },
  { key: "summary" },
  { key: "estado" },
  { key: "revdet" },
  { key: "fb" },
] as const;
type Vista = typeof VISTAS[number]["key"];

/** El «Total F&B Cost Detail» del owner, replicado (2026-08-14).
 *
 *  Es el primer cuadro que **no sale del P&L**. Ahí todo el A&B es una sola
 *  línea; comida / bebida / misceláneos vive un nivel más abajo, en la cuenta
 *  del mayor, así que tiene su propio endpoint (`/reports/fb-detalle/`).
 *
 *  ⚠️ El costo es **costo de ventas** (clase 5), no todo el gasto del
 *  departamento. `OPEX_FB` lleva además la planilla y 50 cuentas de opex —
 *  vajilla, lavandería, uniformes—; metiéndolas, el % de costo se iría al
 *  triple y seguiría pareciendo un porcentaje razonable de mirar. */
const FB_FILAS: {
  campo: keyof import("@/lib/api").FbMes | null;
  label: string; fuerte?: boolean; pctDe?: "comida" | "bebida" | "misc"; hueco?: boolean;
}[] = [
  { campo: "ing_comida", label: "Revenue F&B Food" },
  { campo: "ing_bebida", label: "Revenue F&B Beverage" },
  { campo: "ing_misc", label: "Revenue F&B Miscellaneous" },
  { campo: "ing_total", label: "Total Revenue", fuerte: true },
  { campo: null, label: "", hueco: true },
  { campo: "cos_comida", label: "F&B Food Cost" },
  { campo: "cos_bebida", label: "F&B Beverage Cost" },
  { campo: "cos_misc", label: "F&B Miscellaneous Cost" },
  { campo: "cos_total", label: "Total Cost", fuerte: true },
  { campo: null, label: "", hueco: true },
  { campo: null, label: "F&B Food Cost (%)", pctDe: "comida" },
  { campo: null, label: "F&B Beverage Cost (%)", pctDe: "bebida" },
  { campo: null, label: "F&B Miscellaneous Cost (%)", pctDe: "misc" },
];

/** El «Total Revenue Detail» del owner, en SU orden y con SUS nombres.
 *
 *  La primera versión ordenaba alfabéticamente por lo que devolvía el motor. El
 *  owner lo marcó (2026-08-14) y tenía razón: un cuadro que él ya lee todos los
 *  meses no se reordena porque a mí me parezca.
 *
 *  ⚠️ Tres de sus filas NO tienen línea en el P&L: son una apertura POR CUENTA
 *  dentro de Rooms y de A&B. Se ve en sus propios números — Food + Beverage +
 *  Misc dan exactamente el total de A&B de su otra hoja. `code: null` las deja
 *  en el cuadro, en su lugar, mostrando «—», en vez de borrarlas o —peor—
 *  parearlas a la línea que más se parezca y mostrar un número que se ve bien y
 *  está mal. */
const REV_DETALLE: { code: string | null; label: string; nota?: string }[] = [
  { code: "REV_ROOMS", label: "Rooms Revenue" },
  // Las tres que quedaban en gris. No tenian linea propia porque el P&L tenia
  // UNA sola para Rooms y otra para todo el A&B; el owner mando el mapeo por
  // cuenta y ahora existen (2026-08-14). Ver `separar_costo_de_ventas.py`.
  { code: "REV_ROOMS_OTHER", label: "Other Rooms Revenue" },
  { code: "REV_FB", label: "F&B Food" },
  { code: "REV_FB_BEV", label: "F&B Beverage" },
  { code: "REV_FB_MISC", label: "F&B Miscellaneous" },
  { code: "REV_SPA", label: "SPA" },
  { code: "REV_TOURS", label: "Tours" },
  { code: "REV_RETAIL", label: "Retail-Gift Shop" },
  { code: "REV_TRANSPORTATION", label: "Transportation" },
  { code: "REV_LAUNDRY", label: "Laundry" },
  { code: "REV_INNOCEANA", label: "Innoceana" },
  { code: "REV_CROWTHER_LAB", label: "Crowther Lab" },
  { code: "REV_SUSTAINABILITY", label: "Sustainability Fee" },
  { code: "REV_MISC_OTHER", label: "Misc Revenue Others" },
];

/** El «Profit & Loss Statement YTD» del owner, replicado (2026-08-14).
 *
 *  Mes y YTD lado a lado como el Monthly Summary, pero además con el **% sobre
 *  ingreso** de cada columna y una del **año anterior**, que es lo que convierte
 *  el cuadro en una lectura de estructura y no solo de variación.
 *
 *  **Los subtotales se DERIVAN, no se leen del motor.** El gasto acá está
 *  cortado por naturaleza —todas las 6, todas las 5, todas las 7, todas las 8—
 *  que es otro eje que las líneas del P&L (cortadas por departamento). Si el
 *  GOP se leyera del motor y el Total Expenses de las clases, la resta en
 *  pantalla podría no dar y nadie sabría cuál de los dos mirar.
 *
 *  Derivando, cada subtotal siempre es igual a sus partes. Y para no perder la
 *  otra verdad, el cuadro **compara el GOP derivado contra el del motor y avisa
 *  si se separan** — que es justo el tipo de diferencia que no se nota sola.
 */
const ESTADO: {
  code: string; label: string; gasto?: boolean; fuerte?: boolean; borde?: boolean;
}[] = [
  { code: "X_ROOMS", label: "Rooms Revenue" },
  { code: "X_FB", label: "F&B Revenue" },
  { code: "X_OTHER", label: "Other Revenue" },
  { code: "TOTAL_REVENUES", label: "Total Revenue", fuerte: true, borde: true },
  { code: "C_PAYROLL", label: "Payroll", gasto: true },
  { code: "C_COST", label: "Cost of Sales", gasto: true },
  { code: "C_OPEX", label: "Operating Expenses", gasto: true },
  { code: "X_TOTEXP", label: "Total Expenses", gasto: true, fuerte: true },
  { code: "X_GOP", label: "GOP", fuerte: true, borde: true },
  { code: "C_PROPERTY", label: "Property Expenses", gasto: true },
  { code: "X_EBITDA", label: "EBITDA", fuerte: true },
  { code: "NET_PROFIT", label: "Net Profit After Tax", fuerte: true, borde: true },
];

/** El «JUNE 2026 Summary» del owner, replicado (2026-08-14).
 *
 *  Es el único sub-tab que muestra **el mes y el YTD a la vez**, así que ignora
 *  a propósito el selector de horizonte de arriba: la gracia del cuadro es ver
 *  las dos cosas de un vistazo. `/pl/compare/` ya devuelve los dos horizontes en
 *  la misma respuesta, así que no cuesta un viaje extra.
 *
 *  Compara DOS escenarios —el par de variación elegido arriba—, no las cuatro
 *  ranuras: con cuatro columnas × dos horizontes serían diez columnas de números
 *  y deja de leerse de un vistazo, que es justo para lo que sirve.
 *
 *  `tipo` define el formato Y cómo se compara:
 *    · `pct`   la variación son PUNTOS porcentuales; el % es relativo
 *    · `num`   conteos, sin decimales
 *    · `usd`   dinero
 *    · `saldo` dinero, pero es un SALDO: el YTD no se suma, es el mismo número
 */
const SUMMARY: {
  code: string; label: string; tipo: "num" | "pct" | "usd" | "saldo";
  gasto?: boolean; fuerte?: boolean; separaAntes?: boolean;
}[] = [
  { code: "K_ROOMS_AVAIL", label: "Total Rooms Available", tipo: "num" },
  { code: "K_ROOMS_OCC", label: "Total Rooms Occupied", tipo: "num" },
  { code: "K_GUESTS", label: "Total Guests", tipo: "num" },
  { code: "K_OCC", label: "Occupancy %", tipo: "pct" },
  { code: "K_ADR", label: "ADR", tipo: "usd" },
  { code: "K_REVPAR", label: "RevPAR", tipo: "usd" },
  { code: "TOTAL_REVENUES", label: "Total Revenue", tipo: "usd", fuerte: true },
  { code: "X_ROOMS", label: "Rooms Revenue", tipo: "usd" },
  { code: "X_FB", label: "F&B Revenue", tipo: "usd" },
  { code: "X_OTHER", label: "Other Revenue", tipo: "usd" },
  { code: "TOTAL_GOP", label: "GOP", tipo: "usd", fuerte: true },
  { code: "EBITDA_BEFORE_CAPITAL", label: "EBITDA", tipo: "usd", fuerte: true },
  { code: "NET_PROFIT", label: "Net Profit", tipo: "usd", fuerte: true },
  { code: "X_CASH", label: "Cash (End of Month)", tipo: "saldo", fuerte: true, separaAntes: true },
];

/** Las líneas de ingreso que se suman en «F&B Revenue».
 *
 *  El bar privado es A&B por naturaleza aunque tenga su propia línea. Da igual
 *  para el cuadre: «Other» se calcula como el resto (Total − Rooms − F&B), así
 *  que los tres SIEMPRE suman Total Revenue, esté o no el bar acá dentro. Lo que
 *  cambia es dónde se ve. */
const LINEAS_FB = ["REV_FB", "REV_FB_BEV", "REV_FB_MISC", "REV_PRIVATE_BAR"];

/** Las lineas de ingreso que suman «Rooms».
 *
 *  ⚠️ Faltaban `REV_FB_BEV`, `REV_FB_MISC` y `REV_ROOMS_OTHER` desde que el
 *  ingreso quedo partido (2026-08-14), y el error NO SE VEIA: «Other Revenue»
 *  se calcula como el RESIDUO (Total − Rooms − A&B), asi que la bebida, los
 *  miscelaneos y el otro ingreso de habitaciones caian ahi en silencio y el
 *  cuadro seguia cuadrando contra Total Revenue. Numero que se ve bien y esta
 *  mal — justo lo que el residuo estaba pensado para evitar del otro lado.
 *
 *  Sumar las tres es correcto en los DOS caminos del motor: donde el split
 *  existe, `REV_FB` es solo comida; donde no existe (el resumen importado y el
 *  presupuesto por tarifas), las otras dos vienen en cero. No hay doble conteo. */
const LINEAS_ROOMS = ["REV_ROOMS", "REV_ROOMS_OTHER"];

/** El Simplified P&L de `/pl/simplified`, traído acá como COPIA — el original
 *  se queda donde está (owner, 2026-08-14).
 *
 *  Es la misma cascada de siempre agrupada en cinco bloques, para mirar el
 *  cierre de un vistazo. La diferencia con la otra pantalla es de dónde saca el
 *  dato: allá son dos columnas propias vía `/pl/monthly`; acá usa las CUATRO
 *  ranuras libres y el horizonte (mes / YTD / año) que ya están arriba. Un
 *  reporte metido adentro de otro con sus propios controles se desincroniza del
 *  de afuera y termina mostrando otro período sin que nadie lo note.
 *
 *  Los márgenes se derivan acá (`GOP/Revenue`, `Net/Revenue`) porque son
 *  cocientes: sumar doce márgenes mensuales no da el margen del año. */
const SIMPLE: {
  titulo: string;
  filas: { code: string; label: string; sangria?: boolean; fuerte?: boolean;
           margen?: boolean; gasto?: boolean; sinMotor?: boolean }[];
}[] = [
  { titulo: "REVENUE", filas: [
    { code: "TOTAL_REVENUES", label: "TOTAL REVENUE", fuerte: true },
  ]},
  { titulo: "DEPARTMENTAL EXPENSES", filas: [
    { code: "TOTAL_OPERATING_EXPENSES", label: "Total Operating Expenses", sangria: true, gasto: true },
    { code: "TOTAL_OVERHEAD_EXPENSES", label: "Total Overhead Expenses", sangria: true, gasto: true },
    { code: "OPERATING_PROFIT", label: "OPERATING PROFIT", fuerte: true, sinMotor: true },
  ]},
  { titulo: "GROSS OPERATING PROFIT", filas: [
    { code: "TOTAL_GOP", label: "GOP", fuerte: true },
    { code: "GOP_MARGIN", label: "GOP Margin", sangria: true, margen: true },
  ]},
  { titulo: "NON-OPERATING & CAPITAL", filas: [
    { code: "TOTAL_NON_OP_EXPENSES", label: "Non-Op Expenses", sangria: true, gasto: true },
    { code: "EBITDA_BEFORE_CAPITAL", label: "EBITDA", fuerte: true },
    { code: "CAPITAL_EXPENSE", label: "CapEx Reserve", sangria: true, gasto: true },
    { code: "EBITDA_AFTER_CAPITAL", label: "EBITDA after CapEx", sinMotor: true },
  ]},
  { titulo: "FINANCIAL & TAX", filas: [
    { code: "FINANCIAL_EXPENSES", label: "Financial Expenses", sangria: true, gasto: true },
    { code: "TOTAL_DEPRECIATIONS", label: "Depreciation", sangria: true, gasto: true },
    { code: "EBT", label: "EBT" },
    { code: "INCOME_TAXES", label: "Income Taxes", sangria: true, gasto: true },
    { code: "NET_PROFIT", label: "NET PROFIT", fuerte: true },
    { code: "NET_MARGIN", label: "Net Margin", sangria: true, margen: true },
  ]},
];

/** La cascada, en el orden del cuadro del owner. */
// `sinMotor`: la línea tiene fórmula pero el motor puede devolverla en 0.00
// según por dónde salga el P&L de ese escenario. Un cero acá se lee como «la
// operación no dejó nada», que es una afirmación fuerte y falsa, así que se
// muestra «—».
//
// ⚠️ Ya NO es incondicional. Desde el 2026-08-14 el P&L de un Actual usa el
// detalle del mayor cuando sus totales coinciden con el resumen importado, y en
// ese caso estas dos líneas SÍ traen número (Actual 2025 y 2026). Solo se queda
// sin dato el escenario cuyo detalle no cuadra —hoy el Actual 2024, por los
// $40,613 sin cuenta—, que sigue saliendo del resumen y ahí la plantilla vieja
// del motor no las emite.
//
// Por eso el guión ahora depende del VALOR, no de la línea: `sinMotor` marca
// «puede venir vacía», y se dibuja «—» solo cuando de verdad viene en cero.
//   · OPERATING_PROFIT  = SUM(PROFIT_*)
//   · EBITDA_AFTER_CAPITAL = EBITDA_BEFORE_CAPITAL − CAPITAL_EXPENSE
const CASCADA: { code: string; label: string; fuerte?: boolean; gasto?: boolean; sinMotor?: boolean }[] = [
  { code: "TOTAL_REVENUES", label: "TOTAL REVENUES", fuerte: true },
  { code: "TOTAL_OPERATING_EXPENSES", label: "Total Operating expenses", gasto: true },
  { code: "OPERATING_PROFIT", label: "OPERATING PROFIT", fuerte: true, sinMotor: true },
  { code: "TOTAL_OVERHEAD_EXPENSES", label: "TOTAL OVERHEAD EXPENSES", gasto: true },
  { code: "TOTAL_GOP", label: "TOTAL GROSS OPERATING PROFIT", fuerte: true },
  { code: "TOTAL_NON_OP_EXPENSES", label: "TOTAL NON OP EXPENSES", gasto: true },
  { code: "EBITDA_BEFORE_CAPITAL", label: "EBITDA BEFORE CAPITAL", fuerte: true },
  { code: "EBITDA_AFTER_CAPITAL", label: "EBITDA AFTER CAPITAL", fuerte: true, sinMotor: true },
  { code: "EBT", label: "EARNINGS BEFORE INCOME TAXES", fuerte: true },
  { code: "NET_PROFIT", label: "NET PROFIT", fuerte: true },
];

/** El pie del cuadro: el gasto por NATURALEZA, no por departamento.
 *
 *  Owner: todas las cuentas 6, todas las 5, todas las 7 y todas las 8. No sale
 *  del P&L porque sus lineas estan cortadas por departamento: sumar los OPEX_*
 *  no da todas las 7, porque la planilla y el costo de esos mismos
 *  departamentos entran en la misma linea. Es otro eje, con su propio endpoint. */
const CLASES = [
  { key: "payroll", label: "Total Payroll and Benefits" },
  { key: "opex", label: "Total Operating Expenses" },
  { key: "cost", label: "Total Cost" },
  { key: "property", label: "Total Property Expenses" },
] as const;

const usd = (n: number) =>
  (n < 0 ? "-" : "") + "$" + Math.abs(n).toLocaleString("en-US",
    { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n: number) => (n * 100).toFixed(2) + "%";
const num0 = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });

/** Rojo para los negativos. En un P&L un número negativo es la información, no
 *  un detalle de formato: una utilidad en rojo se tiene que ver de un vistazo. */
const colorNum = (n: number) => n < 0 ? "var(--negative)" : undefined;

function valor(col: PLColumn | undefined, code: string): number {
  if (!col) return 0;
  const l = col.lines.find(x => x.line_code === code);
  return l ? Number(l.amount_usd) : 0;
}

/** ¿Esta línea viene VACÍA para esta columna?
 *
 *  Solo se aplica a las marcadas `sinMotor`, y depende del VALOR: si el motor
 *  la devolvió con número —cosa que ahora pasa en los Actual cuyo detalle
 *  cuadra— se muestra el número. Antes el guión era incondicional y habría
 *  escondido un dato bueno. */
function vacio(l: { code: string; sinMotor?: boolean }, col?: PLColumn): boolean {
  return !!l.sinMotor && Math.abs(valor(col, l.code)) < 0.005;
}

export default function MonthEndPLPage() {
  const t  = useTranslations("monthEndPl");
  const tc = useTranslations("common");
  const mesesRaw = t.raw("mesesLargos") as unknown;
  const MESES = Array.isArray(mesesRaw) ? mesesRaw as string[] : MESES_FALLBACK;
  /** Negrita dentro de un texto traducido. Ver `t.rich` de next-intl. */
  const bold = { b: (c: React.ReactNode) => <strong>{c}</strong> };
  const hoy = new Date();
  const [year, setYear] = useState(hoy.getFullYear());
  const [mes, setMes] = useState(Math.max(1, hoy.getMonth()));   // el mes que se cierra es el anterior
  const [horizonte, setHorizonte] = useState<"month" | "ytd" | "full">("month");
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  const [ranuras, setRanuras] = useState<string[]>(Array(RANURAS).fill(""));
  const [varA, setVarA] = useState(0);
  const [varB, setVarB] = useState(1);
  const [datos, setDatos] = useState<PLCompareVersion[]>([]);
  const [gastos, setGastos] = useState<GastoEscenario[]>([]);
  const [avisoGasto, setAvisoGasto] = useState<string | null>(null);
  const [deptos, setDeptos] = useState<Record<string, string>>({});
  // La caja final por escenario. Vive aparte del P&L y se pide SOLO cuando se
  // abre el Summary: es el unico cuadro que la usa, y son dos viajes mas.
  const [caja, setCaja] = useState<Record<string, number[]>>({});
  const [avisoCaja, setAvisoCaja] = useState<string | null>(null);
  // El año anterior, solo para la columna «% del ingreso» del P&L Statement. Se
  // elige solo —el ACTUAL del año previo— y se pide aparte: no es una ranura,
  // es contexto de lectura.
  const [prevPL, setPrevPL] = useState<PLCompareVersion | null>(null);
  const [prevGasto, setPrevGasto] = useState<GastoEscenario | null>(null);
  // A&B por cuenta. Endpoint propio, se pide solo al abrir ese tab.
  const [fb, setFb] = useState<FbDetalle | null>(null);
  const [avisoFb, setAvisoFb] = useState<string | null>(null);
  // El ingreso por linea calculado desde la CUENTA. No sale del P&L: el del
  // Actual viene del resumen importado, que no trae la apertura de A&B ni
  // "Other Rooms Revenue" y mete el miscelaneo dentro de Sustainability.
  const [ing, setIng] = useState<IngresoDetalle | null>(null);
  const [avisoIng, setAvisoIng] = useState<string | null>(null);
  const [vista, setVista] = useState<Vista>("pl");
  // Consulta libre. Vive en su propio estado porque no comparte nada con el
  // cuadro: ahi se miran totales, aca se buscan filas.
  const [cat, setCat] = useState<ConsultaCatalogo | null>(null);
  const [cjto, setCjto] = useState("gl");
  const [fCuenta, setFCuenta] = useState("");
  const [fDept, setFDept] = useState("");
  const [fClases, setFClases] = useState<Set<string>>(new Set());
  const [fPos, setFPos] = useState("");
  const [fCtaDesde, setFCtaDesde] = useState("");
  const [fCtaHasta, setFCtaHasta] = useState("");
  // La consulta tiene su PROPIO rango de meses. Podria heredar el horizonte del
  // cuadro, pero se usa distinto: arriba se cierra un mes, aca se busca una
  // serie. Atarlos obligaria a mover el cuadro para cambiar la consulta.
  const [qDesde, setQDesde] = useState(1);
  const [qHasta, setQHasta] = useState(12);
  const [qFilas, setQFilas] = useState<ConsultaFila[]>([]);
  const [qInfo, setQInfo] = useState<{ cantidad: number; total: number; truncado: boolean } | null>(null);
  const [qCargando, setQCargando] = useState(false);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* ── Se recuerda cómo quedó la pantalla ──────────────────────────────────
   *
   * Owner (2026-08-14): «cada vez que salgo se va para Budget 2035 y cosas
   * raras». Antes, cada visita rearmaba las ranuras desde cero con el año en
   * curso, así que el trabajo de elegir las versiones se perdía al salir.
   *
   * Se guarda en el navegador —no en la base—: es una preferencia de pantalla,
   * no un dato del presupuesto, y cada persona mira lo suyo.
   *
   * ⚠️ Los ids guardados se VALIDAN contra los escenarios que existen hoy. Un
   * escenario borrado dejaría una ranura apuntando a la nada y la pantalla
   * saldría vacía sin decir por qué. Lo que ya no existe se cae solo y esa
   * ranura vuelve al valor por defecto.
   */
  const MEMORIA = "finplan.month-end.pl";
  const guardado = useRef<Record<string, unknown> | null>(null);

  useEffect(() => {
    try {
      const crudo = window.localStorage.getItem(MEMORIA);
      if (!crudo) return;
      const g = JSON.parse(crudo) as Record<string, unknown>;
      guardado.current = g;
      if (typeof g.year === "number") setYear(g.year);
      if (typeof g.mes === "number" && g.mes >= 1 && g.mes <= 12) setMes(g.mes);
      if (g.horizonte === "month" || g.horizonte === "ytd" || g.horizonte === "full") {
        setHorizonte(g.horizonte);
      }
      if (VISTAS.some(v => v.key === g.vista)) setVista(g.vista as Vista);
      if (typeof g.varA === "number") setVarA(g.varA);
      if (typeof g.varB === "number") setVarB(g.varB);
    } catch {
      // Un guardado corrupto no puede impedir abrir la pantalla.
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setEscenarios(all);

        // Lo que el owner dejó elegido, si esos escenarios siguen existiendo.
        const vivos = new Set(all.map(s => s.id));
        const previas = guardado.current?.ranuras;
        const rescatadas = Array.isArray(previas)
          ? Array.from({ length: RANURAS }, (_, i) =>
              typeof previas[i] === "string" && vivos.has(previas[i] as string)
                ? previas[i] as string : "")
          : null;
        if (rescatadas?.some(Boolean)) { setRanuras(rescatadas); return; }

        // Arranque razonable, NO una atadura: cualquiera se puede cambiar.
        //
        // Los tres papeles salen de `elegir()`, la misma regla que usan los
        // demas reportes. Antes se tomaba el año del reloj: con eso, el 1 de
        // enero la pantalla cambiaba sola de escenarios sin que nadie tocara
        // nada, y el corte de un ciclo de planificacion lo decide el owner.
        setRanuras([
          elegir(all, "actual")?.id ?? "",
          elegir(all, "budget")?.id ?? "",
          elegir(all, "forecast")?.id ?? "",
          "",
        ]);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : t("errEscenarios"));
      }
    })();
  }, [t]);

  // Se guarda cuando ya hay escenarios cargados. Antes de eso las ranuras están
  // en blanco y guardarlas borraría la selección anterior.
  useEffect(() => {
    if (!escenarios.length) return;
    try {
      window.localStorage.setItem(MEMORIA, JSON.stringify({
        year, mes, horizonte, vista, varA, varB, ranuras,
      }));
    } catch {
      // Sin espacio o en modo privado: que no recuerde es molesto, que truene
      // la pantalla es peor.
    }
  }, [escenarios.length, year, mes, horizonte, vista, varA, varB, ranuras]);

  const cargar = useCallback(async () => {
    const ids = ranuras.filter(Boolean);
    if (!ids.length) { setDatos([]); setCargando(false); return; }
    setCargando(true); setError(null);
    try {
      // El P&L y el gasto por clase se piden juntos pero NO se atan: con
      // Promise.all, un fallo del segundo tumbaba el primero y la pantalla
      // entera salia en $0.00 con un 404 arriba. Paso de verdad, en el minuto
      // entre que se desplego el frontend y termino de desplegarse el backend.
      //
      // Un cuadro completo en cero se lee como «el mes no tuvo movimiento», que
      // es una afirmacion, no un error. Ahora el P&L manda y el pie del cuadro
      // avisa aparte si no pudo cargar.
      const r = await getPLCompare(ids, mes);
      setDatos(r.versions);
      setAvisoGasto(null);
      try {
        const g = await getGastoPorClase(ids, true);
        setGastos(g.escenarios);
        setDeptos(g.departamentos ?? {});
      } catch {
        setGastos([]);
        setAvisoGasto(t("errGastoClase"));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errPl"));
    } finally {
      setCargando(false);
    }
  }, [ranuras, mes, t]);

  useEffect(() => { cargar(); }, [cargar]);

  useEffect(() => {
    if (vista === "consulta" && !cat) getConsultaCatalogo().then(setCat).catch(() => setCat(null));
  }, [vista, cat]);

  // La caja final de los dos escenarios comparados. Se pide al abrir el Summary
  // y no antes; si falla, el resto del cuadro sigue en pie y solo esa fila queda
  // sin dato. Un cuadro entero en blanco por una fila seria peor.
  useEffect(() => {
    if (vista !== "summary") return;
    const ids = [ranuras[varA], ranuras[varB]].filter(id => id && !caja[id]);
    if (!ids.length) return;
    (async () => {
      try {
        const rs = await Promise.all(ids.map(async id => {
          const cf = await getCashflowBudget(id);
          const fila = cf.rows.find(r => r.key === "ENDING_CASH");
          return [id, fila?.values ?? []] as const;
        }));
        setCaja(prev => ({ ...prev, ...Object.fromEntries(rs) }));
        setAvisoCaja(null);
      } catch {
        setAvisoCaja(t("errCaja"));
      }
    })();
  }, [vista, ranuras, varA, varB, caja, t]);

  useEffect(() => {
    if (vista !== "revdet") return;
    const ids = [ranuras[varA], ranuras[varB]].filter(Boolean);
    if (!ids.length) return;
    (async () => {
      try { setIng(await getIngresoDetalle(ids)); setAvisoIng(null); }
      catch (e) {
        setIng(null);
        setAvisoIng(e instanceof Error ? e.message : t("errIngreso"));
      }
    })();
  }, [vista, ranuras, varA, varB, t]);

  useEffect(() => {
    if (vista !== "fb") return;
    const ids = [ranuras[varA], ranuras[varB]].filter(Boolean);
    if (!ids.length) return;
    (async () => {
      try { setFb(await getFbDetalle(ids)); setAvisoFb(null); }
      catch (e) {
        setFb(null);
        setAvisoFb(e instanceof Error ? e.message : t("errFb"));
      }
    })();
  }, [vista, ranuras, varA, varB, t]);

  /** El escenario del año anterior para la última columna del P&L Statement.
   *  Se elige solo: el ACTUAL del año previo al de la columna comparada. */
  const prevScn = useMemo(() => {
    const base = escenarios.find(s => s.id === ranuras[varA]);
    if (!base) return null;
    return escenarios.find(s => s.type === "ACTUAL" && s.year === base.year - 1) ?? null;
  }, [escenarios, ranuras, varA]);

  useEffect(() => {
    if (vista !== "estado" || !prevScn) { return; }
    if (prevPL?.scenario_id === prevScn.id) return;
    (async () => {
      try {
        const r = await getPLCompare([prevScn.id], mes);
        setPrevPL(r.versions[0] ?? null);
      } catch { setPrevPL(null); }
      try {
        const g = await getGastoPorClase([prevScn.id], false);
        setPrevGasto(g.escenarios[0] ?? null);
      } catch { setPrevGasto(null); }
    })();
  }, [vista, prevScn, mes, prevPL]);

  const filtroConsulta = useCallback(() => ({
    conjunto: cjto,
    escenarios: ranuras.filter(Boolean),
    cuenta: fCuenta, dept: fDept,
    clase: Array.from(fClases).sort().join(","),
    posicion: fPos, cuentaDesde: fCtaDesde, cuentaHasta: fCtaHasta,
    mesDesde: qDesde, mesHasta: qHasta,
  }), [cjto, ranuras, fCuenta, fDept, fClases, fPos, fCtaDesde, fCtaHasta, qDesde, qHasta]);

  async function correr() {
    setQCargando(true); setError(null);
    try {
      const r = await correrConsulta(filtroConsulta());
      setQFilas(r.filas);
      setQInfo({ cantidad: r.cantidad, total: r.total, truncado: r.truncado });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errConsulta"));
    } finally {
      setQCargando(false);
    }
  }

  const cols = useMemo(
    () => ranuras.map(id => id ? datos.find(d => d.scenario_id === id)?.[horizonte] : undefined),
    [ranuras, datos, horizonte]);

  const usadas = ranuras.map((id, i) => ({ id, i })).filter(x => x.id);

  /** Dónde se insertan las dos columnas de variación.
   *
   * Al final del todo quedaban lejos de las columnas que comparan: con cuatro
   * escenarios había que cruzar la tabla entera para leer el delta de la 1 vs
   * la 2. Van justo después de la última de las dos comparadas. */
  const trasVariacion = useMemo(() => {
    const pos = usadas.findIndex(u => u.i === Math.max(varA, varB));
    return pos < 0 ? usadas.length : pos + 1;
  }, [usadas, varA, varB]);

  const etiqueta = useCallback((id: string) => {
    const s = escenarios.find(x => x.id === id);
    return s ? `${s.type} ${s.version} ${s.year}` : "—";
  }, [escenarios]);

  /** Una columna sin dato del período: todas sus líneas en cero. */
  const vacia = (c: PLColumn | undefined) =>
    !!c && c.lines.every(l => Number(l.amount_usd) === 0);

  const sinDatoVar = !ranuras[varA] || !ranuras[varB] || vacia(cols[varA]) || vacia(cols[varB]);

  function variacion(code: string, esGasto?: boolean) {
    if (sinDatoVar) return { d: 0, p: 0, bueno: false, sinDato: true };
    const a = valor(cols[varA], code);
    const b = valor(cols[varB], code);
    const d = a - b;
    const p = b !== 0 ? d / Math.abs(b) : 0;
    // En gasto, gastar de más es malo aunque el número sea positivo.
    return { d, p, bueno: esGasto ? d < 0 : d > 0, sinDato: false };
  }

  /** Suma la clase en el periodo elegido. El endpoint devuelve los doce meses
   *  justamente para que cambiar de horizonte no cueste otro viaje. */
  const gastoClase = useCallback((idx: number, clave: typeof CLASES[number]["key"]) => {
    const g = gastos.find(x => x.scenario_id === ranuras[idx]);
    if (!g) return 0;
    const hasta = horizonte === "month" ? [mes] : horizonte === "ytd"
      ? Array.from({ length: mes }, (_, i) => i + 1)
      : Array.from({ length: 12 }, (_, i) => i + 1);
    return g.meses.filter(m => hasta.includes(m.month))
      .reduce((s, m) => s + Number(m[clave]), 0);
  }, [gastos, ranuras, horizonte, mes]);

  /** Las claves (departamentos o cuentas) que aparecen en alguna columna, y el
   *  valor de cada una en el periodo elegido. Se arma la union de todas las
   *  columnas: si un depto existe en el budget y no en el real, tiene que salir
   *  igual — en cero, que es justo el dato interesante. */
  const apertura = useCallback((clase: string) => {
    const meses = horizonte === "month" ? [mes] : horizonte === "ytd"
      ? Array.from({ length: mes }, (_, i) => i + 1)
      : Array.from({ length: 12 }, (_, i) => i + 1);
    const claves = new Set<string>();
    for (const g of gastos) {
      Object.keys(g.detalle?.[clase] ?? {}).forEach(k => claves.add(k));
    }
    const valor = (idx: number, clave: string) => {
      const g = gastos.find(x => x.scenario_id === ranuras[idx]);
      const serie = g?.detalle?.[clase]?.[clave];
      if (!serie) return 0;
      return meses.reduce((s2, m) => s2 + Number(serie[m - 1] ?? 0), 0);
    };
    return { claves: Array.from(claves).sort(), valor };
  }, [gastos, ranuras, horizonte, mes]);

  const periodo = horizonte === "month" ? MESES[mes - 1]
    : t("periodoRango", { ini: MESES[0], fin: MESES[horizonte === "ytd" ? mes - 1 : 11] });

  function bajarExcel() {
    const columnas: ColumnaCuadro[] = [
      { label: "ACCOUNT DESCRIPTION", ancho: 38, formato: "texto" },
      ...usadas.slice(0, trasVariacion).map(u => ({ label: etiqueta(u.id), ancho: 17, formato: "usd2" as const })),
      { label: t("variacionD"), ancho: 16, formato: "usd2" as const },
      { label: t("variacionP"), ancho: 12, formato: "pct" as const },
      ...usadas.slice(trasVariacion).map(u => ({ label: etiqueta(u.id), ancho: 17, formato: "usd2" as const })),
    ];

    /** Los valores de una fila, con la variación en el mismo lugar que en pantalla. */
    const enOrden = (porColumna: (i: number) => number | null,
                     dv: number | null, pv: number | null) => [
      ...usadas.slice(0, trasVariacion).map(u => porColumna(u.i)),
      dv, pv,
      ...usadas.slice(trasVariacion).map(u => porColumna(u.i)),
    ];
    // Las estadisticas van en el MISMO cuadro, arriba, como en el Excel del
    // owner. Cada renglon pisa el formato de la columna: hay conteos, un
    // porcentaje y dolares en la misma columna, y con un solo formato la
    // ocupacion saldria como "$0.36".
    const filas: FilaCuadro[] = [
      { label: t("estadisticas"), es_total: true, valores: enOrden(() => null, null, null) },
      ...kpis.map((k, i) => ({
        label: k.label,
        formato: (i <= 2 ? "num" : i === 3 ? "pct" : "usd2") as "num" | "pct" | "usd2",
        valores: enOrden(j => {
          const c = cols[j];
          if (!c) return null;
          return [c.kpis.rooms_available, c.kpis.rooms_occupied, c.kpis.guests,
                  c.kpis.occupancy_pct, c.kpis.adr, c.kpis.revpar][i];
        }, null, null),
      })),
      { label: "", valores: enOrden(() => null, null, null) },
      { label: "P&L", es_total: true, valores: enOrden(() => null, null, null) },
      ...CASCADA.map(l => {
        const v = variacion(l.code, l.gasto);
        return {
          label: l.label, es_total: l.fuerte,
          valores: enOrden(j => vacio(l, cols[j]) ? null : valor(cols[j], l.code),
                           v.sinDato || vacio(l, cols[varA]) ? null : v.d,
                           v.sinDato || vacio(l, cols[varA]) ? null : v.p),
        };
      }),
      { label: "", valores: enOrden(() => null, null, null) },
      ...CLASES.map(c => {
        const b = gastoClase(varB, c.key);
        const d = sinDatoVar ? null : gastoClase(varA, c.key) - b;
        return {
          label: c.label,
          valores: enOrden(j => gastoClase(j, c.key), d,
                           d === null || b === 0 ? null : d / Math.abs(b)),
        };
      }),
      {
        label: "Total Operating and Property Expenses", es_total: true,
        valores: enOrden(j => CLASES.reduce((s2, c) => s2 + gastoClase(j, c.key), 0), null, null),
      },
    ];
    const cuadro: Cuadro = {
      titulo: t("xlTitulo", { periodo, year: String(year) }),
      subtitulo: sinDatoVar ? t("xlSinVariacion")
        : t("xlVariacionEntre", { escA: etiqueta(ranuras[varA]), escB: etiqueta(ranuras[varB]) }),
      hoja: t("xlHoja"),
      columnas, filas,
    };
    bajarCuadros(`Cierre_${year}_${horizonte}_${String(mes).padStart(2, "0")}`, [cuadro]);
  }

  // `position: static` pisa el sticky global de `thead th`. Estas dos tablas
  // tienen seis y diez filas: el encabezado fijo no aporta nada y se montaba
  // sobre la primera fila. El sticky sirve en las tablas largas, no aca.
  // Los ENCABEZADOS van centrados sobre su columna; los NÚMEROS siguen
  // alineados a la derecha. No es inconsistencia: las cifras se leen comparando
  // unidades, decenas y centenas, y eso solo funciona si el punto decimal cae
  // siempre en el mismo lugar. Centrar los montos rompe esa columna invisible.
  const TH: React.CSSProperties = {
    padding: "8px 10px", textAlign: "center", fontWeight: 700, position: "static",
    color: "var(--brand)",
  };
  const TD: React.CSSProperties = { padding: "5px 10px", textAlign: "right" };
  const TDL: React.CSSProperties = { padding: "5px 10px", textAlign: "left" };
  const SEL: React.CSSProperties = {
    background: "var(--bg-surface)", color: "var(--text-primary)",
    border: "1px solid var(--border-medium)", borderRadius: 5,
    padding: "5px 9px", fontSize: 12.5,
  };

  const kpis: { label: string; get: (c?: PLColumn) => string }[] = [
    { label: "Total available Rooms", get: c => c ? num0(c.kpis.rooms_available) : "—" },
    { label: "Total Rooms Occupied", get: c => c ? num0(c.kpis.rooms_occupied) : "—" },
    { label: "Total Guests", get: c => c ? num0(c.kpis.guests) : "—" },
    { label: "% Occupancy", get: c => c ? pct(c.kpis.occupancy_pct) : "—" },
    { label: "Average Daily Room Only", get: c => c ? usd(c.kpis.adr) : "—" },
    { label: "Total RevPAR", get: c => c ? usd(c.kpis.revpar) : "—" },
  ];

  const vacias = usadas.filter(u => vacia(cols[u.i]));

  /**
   * Las dos tablas —estadísticas y P&L— tienen distinta cantidad de columnas:
   * la de abajo suma Variación $ y %. Con ancho automático cada una reparte por
   * su cuenta y las columnas no coinciden ni por casualidad: se ve como dos
   * cuadros distintos pegados, que es justo lo que el owner marcó.
   *
   * Se fija la MISMA rejilla en las dos (`table-layout: fixed` + este colgroup)
   * y la de arriba deja en blanco las dos celdas de variación. Así «ACTUAL
   * actual 2026» cae exactamente sobre su columna en los dos cuadros.
   */
  const rejilla = (
    <colgroup>
      <col style={{ width: 300 }} />
      {usadas.slice(0, trasVariacion).map(u => <col key={`a${u.i}`} style={{ width: 165 }} />)}
      <col style={{ width: 150 }} />
      <col style={{ width: 110 }} />
      {usadas.slice(trasVariacion).map(u => <col key={`b${u.i}`} style={{ width: 165 }} />)}
    </colgroup>
  );
  const anchoTabla = 300 + usadas.length * 165 + 260;

  return (
    <div className="pag pag-ancha" style={{ padding: "18px 22px" }}>
      <IrA esc={ranuras[1]} />
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>{t("titulo")}</h1>
        <select value={mes} onChange={e => setMes(Number(e.target.value))} style={SEL}>
          {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
        <select value={year} onChange={e => setYear(Number(e.target.value))} style={SEL}>
          {Array.from(new Set(escenarios.map(s => s.year))).sort((a, b) => b - a)
            .map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        {(["month", "ytd", "full"] as const).map(k => (
          <button key={k} onClick={() => setHorizonte(k)} style={{
            ...SEL, cursor: "pointer", fontWeight: 600,
            background: horizonte === k ? "var(--brand)" : "var(--bg-surface)",
            color: horizonte === k ? "#fff" : "var(--text-secondary)",
            border: horizonte === k ? "none" : SEL.border,
          }}>{t(`horizonte_${k}`)}</button>
        ))}
        <button onClick={bajarExcel} style={{ ...SEL, cursor: "pointer", fontWeight: 600 }}>⬇ Excel</button>
      </div>

      {/* Cuatro ranuras libres. Cada una acepta CUALQUIER escenario de cualquier
          año: comparar dos versiones del Budget 2027 entre sí es una pregunta
          legítima, y con columnas atadas a un rol no se podía hacer. */}
      <div style={{ display: "flex", gap: 10, marginBottom: 10, flexWrap: "wrap", fontSize: 12 }}>
        {ranuras.map((id, i) => (
          <label key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ color: "var(--text-secondary)" }}>{i + 1}</span>
            <select value={id} style={SEL}
              onChange={e => setRanuras(prev => prev.map((v, j) => j === i ? e.target.value : v))}>
              <option value="">{t("ranuraVacia")}</option>
              {escenarios.map(s => (
                <option key={s.id} value={s.id}>{s.year} · {s.type} {s.version}</option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 14, fontSize: 12, flexWrap: "wrap" }}>
        <span style={{ color: "var(--text-secondary)" }}>{t("variacionLabel")}</span>
        <select value={varA} onChange={e => setVarA(Number(e.target.value))} style={SEL}>
          {ranuras.map((id, i) => (
            <option key={i} value={i} disabled={!id}>{i + 1} · {id ? etiqueta(id) : t("vacia")}</option>
          ))}
        </select>
        <span style={{ color: "var(--text-secondary)" }}>{t("contra")}</span>
        <select value={varB} onChange={e => setVarB(Number(e.target.value))} style={SEL}>
          {ranuras.map((id, i) => (
            <option key={i} value={i} disabled={!id}>{i + 1} · {id ? etiqueta(id) : t("vacia")}</option>
          ))}
        </select>
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
        {VISTAS.map(v => (
          <button key={v.key} onClick={() => setVista(v.key)} style={{
            ...SEL, cursor: "pointer", fontWeight: 600,
            background: vista === v.key ? "var(--brand)" : "var(--bg-surface)",
            color: vista === v.key ? "#fff" : "var(--text-secondary)",
            border: vista === v.key ? "none" : SEL.border,
          }}>{t(`tab_${v.key}`)}</button>
        ))}
      </div>

      {vacias.length > 0 && (
        <div style={{
          padding: "9px 12px", borderRadius: 6, marginBottom: 14, fontSize: 12.5,
          background: "rgba(230,168,23,0.12)", border: "1px solid rgba(230,168,23,0.4)",
        }}>
          {t("colSinDatoPre", { n: vacias.length })}{" "}
          <strong>{vacias.map(u => `${u.i + 1} (${etiqueta(u.id)})`).join(", ")}</strong>{" "}
          {t("colSinDatoPost", { n: vacias.length })}
          {sinDatoVar && ` ${t("varSinCalcular")}`}
        </div>
      )}

      {avisoGasto && (
        <div style={{
          padding: "9px 12px", borderRadius: 6, marginBottom: 12, fontSize: 12.5,
          background: "rgba(230,168,23,0.12)", border: "1px solid rgba(230,168,23,0.4)",
        }}>{avisoGasto}</div>
      )}

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

      {vista === "fb" && (() => {
        /* Total F&B Cost Detail. Único cuadro que no sale del P&L — ver
         * `FB_FILAS` y `/reports/fb-detalle/`. */
        const idA = ranuras[varA], idB = ranuras[varB];
        if (!idA || !idB) return (
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {t("eligePar")}
          </p>
        );
        if (avisoFb) return (
          <div style={{ padding: "9px 12px", borderRadius: 6, fontSize: 12.5,
            background: "rgba(230,168,23,0.12)", border: "1px solid rgba(230,168,23,0.4)",
          }}>{avisoFb}</div>
        );
        if (!fb) return <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>{tc("loading")}</p>;

        const eA = fb.escenarios.find(x => x.scenario_id === idA);
        const eB = fb.escenarios.find(x => x.scenario_id === idB);
        const mesesDe = (h: "month" | "ytd") =>
          h === "month" ? [mes] : Array.from({ length: mes }, (_, i) => i + 1);

        const suma = (e: typeof eA, campo: keyof FbMes, h: "month" | "ytd") => {
          if (!e) return null;
          const ms = mesesDe(h);
          return e.meses.filter(m => ms.includes(m.month))
            .reduce((s, m) => s + Number(m[campo]), 0);
        };

        /* El % de costo se calcula sobre el ACUMULADO del período, no
         * promediando los meses: es un cociente. Promediar doce porcentajes da
         * un número que no es el costo del año. */
        const pctCosto = (e: typeof eA, g: "comida" | "bebida" | "misc",
                          h: "month" | "ytd") => {
          const ing = suma(e, `ing_${g}` as keyof FbMes, h);
          const cos = suma(e, `cos_${g}` as keyof FbMes, h);
          return ing ? (cos ?? 0) / ing : null;
        };

        const bloques = [
          { titulo: `${MESES[mes - 1]} ${year}`, h: "month" as const },
          { titulo: t("ytdA", { mes: MESES[mes - 1], year: String(year) }), h: "ytd" as const },
        ];
        const TH2: React.CSSProperties = { ...TH, fontSize: 12 };
        const BL = "2px solid var(--border-medium)";

        const celdas = (f: typeof FB_FILAS[number], h: "month" | "ytd") => {
          const es = f.pctDe !== undefined;
          const a = es ? pctCosto(eA, f.pctDe!, h) : suma(eA, f.campo as keyof FbMes, h);
          const b = es ? pctCosto(eB, f.pctDe!, h) : suma(eB, f.campo as keyof FbMes, h);
          const d = a === null || b === null ? null : a - b;
          const p = d === null || !b || es ? null : d / Math.abs(b);
          // En costo, gastar de más es malo aunque el número sea positivo.
          const esCosto = es || String(f.campo ?? "").startsWith("cos_");
          const bueno = d !== null && (esCosto ? d < 0 : d > 0);
          return { a, b, d, p, es, bueno };
        };
        const fmtFb = (n: number | null, es: boolean) =>
          n === null ? "—" : es ? pct(n) : usd(n);

        function bajarFb() {
          const columnas: ColumnaCuadro[] = [
            { label: "Department", ancho: 28, formato: "texto" },
            ...bloques.flatMap(bl => ([
              { label: `${etiqueta(idA)} · ${bl.titulo}`, ancho: 18, formato: "usd2" as const },
              { label: `${etiqueta(idB)} · ${bl.titulo}`, ancho: 18, formato: "usd2" as const },
              { label: "Var $", ancho: 15, formato: "usd2" as const },
              { label: "Var %", ancho: 10, formato: "pct" as const },
            ])),
          ];
          const filas: FilaCuadro[] = FB_FILAS.filter(f => !f.hueco).map(f => ({
            label: f.label, es_total: !!f.fuerte,
            formato: f.pctDe !== undefined ? "pct" : undefined,
            valores: bloques.flatMap(bl => {
              const c = celdas(f, bl.h);
              return [c.a, c.b, c.d, c.p];
            }),
          }));
          bajarCuadros(`FB_Cost_Detail_${MESES[mes - 1]}_${year}`, [{
            titulo: `Total F&B Cost Detail ${MESES[mes - 1].toUpperCase()} ${year}`,
            subtitulo: `${etiqueta(idA)} vs ${etiqueta(idB)} · USD`,
            hoja: `F&B ${MESES[mes - 1]}`,
            columnas, filas,
          }]).catch(e => alert(e instanceof Error ? e.message : t("errExcel")));
        }

        return (
          <div>
            <div style={{ display: "flex", alignItems: "flex-start",
                          justifyContent: "space-between", gap: 16, marginBottom: 12 }}>
              <p style={{ fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 820 }}>
                {t.rich("fbIntro", bold)}
              </p>
              <button onClick={bajarFb} style={{
                padding: "6px 13px", borderRadius: 6, cursor: "pointer", flexShrink: 0,
                background: "var(--accent-excel)", color: "#fff", border: "none",
                fontSize: 12.5, fontWeight: 600,
              }}>⬇ Excel</button>
            </div>

            {fb.sin_clasificar.length > 0 && (
              <div style={{
                padding: "9px 12px", borderRadius: 6, marginBottom: 12, fontSize: 12.5,
                background: "rgba(230,168,23,0.12)", border: "1px solid rgba(230,168,23,0.4)",
              }}>
                {t.rich("fbSinClasificar", { ...bold, cuentas: fb.sin_clasificar.join(" · ") })}
              </div>
            )}

            <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 1120 }}>
              <thead>
                <tr>
                  <th rowSpan={2} style={{ ...TH, textAlign: "left", verticalAlign: "bottom" }}>Department</th>
                  {bloques.map(bl => (
                    <th key={bl.h} colSpan={4} style={{ ...TH, borderLeft: BL }}>{bl.titulo}</th>
                  ))}
                </tr>
                <tr>
                  {bloques.map(bl => (
                    <Fragment key={bl.h}>
                      <th style={{ ...TH2, borderLeft: BL }}>{etiqueta(idA)}</th>
                      <th style={TH2}>{etiqueta(idB)}</th>
                      <th style={{ ...TH2, color: "var(--brand)" }}>Var $</th>
                      <th style={{ ...TH2, color: "var(--brand)" }}>Var %</th>
                    </Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {FB_FILAS.map((f, i) => f.hueco ? (
                  <tr key={`h${i}`}><td colSpan={9} style={{ height: 12 }} /></tr>
                ) : (
                  <tr key={f.label} style={f.fuerte
                    ? { background: "var(--bg-elevated)", borderTop: BL } : undefined}>
                    <td style={{ ...TDL, fontWeight: f.fuerte ? 700 : 500 }}>{f.label}</td>
                    {bloques.map(bl => {
                      const c = celdas(f, bl.h);
                      const cv = c.d === null || c.d === 0 ? "var(--text-secondary)"
                        : c.bueno ? "var(--positive)" : "var(--negative)";
                      return (
                        <Fragment key={bl.h}>
                          <td className="mono" style={{ ...TD, borderLeft: BL,
                            fontWeight: f.fuerte ? 700 : 400,
                            color: c.a !== null && c.a < 0 ? "var(--negative)" : undefined }}>
                            {fmtFb(c.a, c.es)}</td>
                          <td className="mono" style={{ ...TD, fontWeight: f.fuerte ? 700 : 400,
                            color: c.b !== null && c.b < 0 ? "var(--negative)" : undefined }}>
                            {fmtFb(c.b, c.es)}</td>
                          <td className="mono" style={{ ...TD, color: cv, fontSize: 12.5 }}>
                            {fmtFb(c.d, c.es)}</td>
                          <td className="mono" style={{ ...TD, color: cv, fontSize: 12 }}>
                            {c.p === null ? "—" : `${(c.p * 100).toFixed(1)}%`}</td>
                        </Fragment>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            </div>

            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 12, maxWidth: 900 }}>
              {t.rich("fbPie", bold)}
            </p>
          </div>
        );
      })()}

      {vista === "revdet" && (() => {
        /* Total Revenue Detail, en el ORDEN Y CON LOS NOMBRES del owner.
         *
         * ⚠️ NO sale del P&L. El del Actual se arma con el RESUMEN importado,
         * que es más grueso que el mayor: todo el A&B en una línea, sin «Other
         * Rooms Revenue», y el ingreso misceláneo metido dentro de
         * Sustainability. Por eso «F&B Beverage», «F&B Miscellaneous» y «Misc
         * Revenue Others» salían en CERO siendo falso (owner, 2026-08-14).
         *
         * Este cuadro se calcula desde la CUENTA, que sí tiene la apertura, con
         * el MISMO resolvedor del motor — así ve exactamente lo que ve el P&L.
         * Verificado YTD mayo del Actual 2026: $3,293,523.64 en los dos.
         *
         * REGLA DEL OWNER: una línea sin saldo en ninguno de los escenarios
         * pedidos no se muestra. Aparece sola cuando tiene movimiento. */
        const idA = ranuras[varA], idB = ranuras[varB];
        if (!idA || !idB) return (
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {t("eligePar")}
          </p>
        );
        if (avisoIng) return (
          <div style={{ padding: "9px 12px", borderRadius: 6, fontSize: 12.5,
            background: "rgba(230,168,23,0.12)", border: "1px solid rgba(230,168,23,0.4)",
          }}>{avisoIng}</div>
        );
        if (!ing) return <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>{tc("loading")}</p>;

        // Se captura antes: dentro de `bajarDetalle` TypeScript pierde el
        // estrechamiento de `ing` y lo vuelve a ver como posiblemente nulo.
        const nombresIng = ing.nombres;
        const eA = ing.escenarios.find(x => x.scenario_id === idA);
        const eB = ing.escenarios.find(x => x.scenario_id === idB);
        const mesesDe = (h: "month" | "ytd") =>
          h === "month" ? [mes] : Array.from({ length: mes }, (_, i) => i + 1);

        const val = (e: typeof eA, code: string | null, h: "month" | "ytd") => {
          if (!e || !code) return null;
          const ms = mesesDe(h);
          return e.meses.filter(m => ms.includes(m.month))
            .reduce((sum, m) => sum + Number(m[code] ?? 0), 0);
        };
        const totalPL = (e: typeof eA, h: "month" | "ytd") => {
          if (!e) return null;
          const ms = mesesDe(h);
          return e.pl.filter(x => ms.includes(x.month))
            .reduce((sum, x) => sum + Number(x.total_revenues), 0);
        };

        const bloques = [
          { titulo: MESES[mes - 1] + " " + year, h: "month" as const },
          { titulo: t("ytdA", { mes: MESES[mes - 1], year: String(year) }), h: "ytd" as const },
        ];
        const TH2: React.CSSProperties = { ...TH, fontSize: 12 };
        const BL = "2px solid var(--border-medium)";

        // Lo que el motor trae y no está en la lista del owner: NO se pierde,
        // sale abajo aparte.
        const enLista = new Set(REV_DETALLE.map(r => r.code).filter(Boolean) as string[]);
        const sobrantes = Object.keys(nombresIng).filter(c => !enLista.has(c))
          .sort((a, b) => nombresIng[a].localeCompare(nombresIng[b]));
        const todas = [...enLista, ...sobrantes];

        /* La regla del owner. Una línea se muestra solo si tiene saldo en alguno
         * de los dos escenarios, en el mes o en el acumulado. Un cuadro lleno de
         * ceros hace trabajar la vista de gratis y esconde lo que sí se movió. */
        const conSaldo = (code: string | null) => {
          if (!code) return false;
          return bloques.some(bl =>
            Math.abs(val(eA, code, bl.h) ?? 0) > 0.005 ||
            Math.abs(val(eB, code, bl.h) ?? 0) > 0.005);
        };
        const visibles = REV_DETALLE.filter(r => conSaldo(r.code));
        const sobrVis = sobrantes.filter(conSaldo);
        const ocultas = (REV_DETALLE.length + sobrantes.length)
          - (visibles.length + sobrVis.length);

        // El detalle contra el TOTAL del P&L. Si no dan, el resumen importado y
        // el mayor no dicen lo mismo, y eso hay que verlo.
        const brechas = bloques.map(bl => {
          const suma = todas.reduce((sum, c) => sum + (val(eA, c, bl.h) ?? 0), 0);
          return { bl, d: suma - (totalPL(eA, bl.h) ?? 0) };
        }).filter(x => Math.abs(x.d) > 1);

        const filaTabla = (code: string | null, label: string, total: boolean,
                           nota = "", clave = "") => (
          <tr key={clave || code || label} style={total
            ? { background: "var(--bg-elevated)", borderTop: BL } : undefined}>
            <td style={{ ...TDL, fontWeight: total ? 700 : 500 }}>{label}</td>
            {bloques.map(bl => {
              const a = total ? totalPL(eA, bl.h) : val(eA, code, bl.h);
              const b = total ? totalPL(eB, bl.h) : val(eB, code, bl.h);
              const d = a === null || b === null ? null : a - b;
              const p = d === null || !b ? null : d / Math.abs(b);
              const cv = d === null || d === 0 ? "var(--text-secondary)"
                : d > 0 ? "var(--positive)" : "var(--negative)";
              return (
                <Fragment key={bl.h}>
                  <td className="mono" style={{ ...TD, borderLeft: BL,
                    fontWeight: total ? 700 : 400,
                    color: a !== null && a < 0 ? "var(--negative)" : undefined }}>
                    {a === null ? "—" : usd(a)}</td>
                  <td className="mono" style={{ ...TD, fontWeight: total ? 700 : 400,
                    color: b !== null && b < 0 ? "var(--negative)" : undefined }}>
                    {b === null ? "—" : usd(b)}</td>
                  <td className="mono" style={{ ...TD, color: cv, fontSize: 12.5 }}>
                    {d === null ? "—" : usd(d)}</td>
                  <td className="mono" style={{ ...TD, color: cv, fontSize: 12 }}>
                    {p === null ? "—" : (p * 100).toFixed(1) + "%"}</td>
                </Fragment>
              );
            })}
            <td style={{ ...TDL, borderLeft: BL, fontSize: 11.5,
              color: "var(--text-disabled)" }}>{nota}</td>
          </tr>
        );

        function bajarDetalle() {
          const columnas: ColumnaCuadro[] = [
            { label: "Department", ancho: 28, formato: "texto" },
            ...bloques.flatMap(bl => ([
              { label: etiqueta(idA) + " · " + bl.titulo, ancho: 18, formato: "usd2" as const },
              { label: etiqueta(idB) + " · " + bl.titulo, ancho: 18, formato: "usd2" as const },
              { label: "Var $", ancho: 15, formato: "usd2" as const },
              { label: "Var %", ancho: 10, formato: "pct" as const },
            ])),
            { label: "Notes", ancho: 30, formato: "texto" as const },
          ];
          const fila = (code: string | null, label: string, total: boolean,
                        nota = ""): FilaCuadro => ({
            label, es_total: total,
            valores: [
              ...bloques.flatMap(bl => {
                const a = total ? totalPL(eA, bl.h) : val(eA, code, bl.h);
                const b = total ? totalPL(eB, bl.h) : val(eB, code, bl.h);
                const d = a === null || b === null ? null : a - b;
                return [a, b, d, d === null || !b ? null : d / Math.abs(b)];
              }),
              nota || null,
            ],
          });
          bajarCuadros("Revenue_Detail_" + MESES[mes - 1] + "_" + year, [{
            titulo: "Total Revenue Detail " + MESES[mes - 1].toUpperCase() + " " + year,
            subtitulo: etiqueta(idA) + " vs " + etiqueta(idB) + " · USD",
            hoja: "Revenue " + MESES[mes - 1],
            columnas,
            filas: [
              ...visibles.map(r => fila(r.code, r.label, false, r.nota ?? "")),
              ...sobrVis.map(c => fila(c, nombresIng[c], false,
                t("revdetNotaSobrante"))),
              fila(null, "TOTAL", true),
            ],
          }]).catch(e => alert(e instanceof Error ? e.message : t("errExcel")));
        }

        return (
          <div>
            <div style={{ display: "flex", alignItems: "flex-start",
                          justifyContent: "space-between", gap: 16, marginBottom: 12 }}>
              <p style={{ fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 820 }}>
                {t.rich("revdetIntro", bold)}
              </p>
              <button onClick={bajarDetalle} style={{
                padding: "6px 13px", borderRadius: 6, cursor: "pointer", flexShrink: 0,
                background: "var(--accent-excel)", color: "#fff", border: "none",
                fontSize: 12.5, fontWeight: 600,
              }}>⬇ Excel</button>
            </div>

            {brechas.length > 0 && (
              <div style={{
                padding: "9px 12px", borderRadius: 6, marginBottom: 12, fontSize: 12.5,
                background: "rgba(230,168,23,0.12)", border: "1px solid rgba(230,168,23,0.4)",
              }}>
                {t.rich("revdetBrecha", {
                  ...bold,
                  esc: etiqueta(idA),
                  detalle: brechas.map(x => x.bl.titulo + ", " + usd(x.d)).join(" · "),
                })}
              </div>
            )}

            <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 1180 }}>
              <thead>
                <tr>
                  <th rowSpan={2} style={{ ...TH, textAlign: "left", verticalAlign: "bottom" }}>Department</th>
                  {bloques.map(bl => (
                    <th key={bl.h} colSpan={4} style={{ ...TH, borderLeft: BL }}>{bl.titulo}</th>
                  ))}
                  <th rowSpan={2} style={{ ...TH, borderLeft: BL }}>Notes</th>
                </tr>
                <tr>
                  {bloques.map(bl => (
                    <Fragment key={bl.h}>
                      <th style={{ ...TH2, borderLeft: BL }}>{etiqueta(idA)}</th>
                      <th style={TH2}>{etiqueta(idB)}</th>
                      <th style={{ ...TH2, color: "var(--brand)" }}>Var $</th>
                      <th style={{ ...TH2, color: "var(--brand)" }}>Var %</th>
                    </Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibles.map(r => filaTabla(r.code, r.label, false, r.nota ?? "", r.label))}
                {sobrVis.length > 0 && (
                  <tr><td colSpan={10} style={{ ...TDL, paddingTop: 12, fontSize: 10.5,
                    fontWeight: 700, letterSpacing: 0.8, color: "var(--text-secondary)" }}>
                    {t("revdetNoEnCuadro")}
                  </td></tr>
                )}
                {sobrVis.map(c => filaTabla(c, nombresIng[c], false))}
                {filaTabla(null, "TOTAL", true)}
              </tbody>
            </table>
            </div>

            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 12, maxWidth: 900 }}>
              {ocultas > 0 && <>{t.rich("revdetOcultas", { ...bold, n: ocultas })} </>}
              {t("revdetPie")}
            </p>
          </div>
        );
      })()}

      {vista === "estado" && (() => {
        /* Profit & Loss Statement: mes y YTD, con el % sobre ingreso de cada
         * columna y la estructura del año anterior. Ver `ESTADO`. */
        const idA = ranuras[varA], idB = ranuras[varB];
        const vA = datos.find(d => d.scenario_id === idA);
        const vB = datos.find(d => d.scenario_id === idB);
        const gA = gastos.find(g => g.scenario_id === idA);
        const gB = gastos.find(g => g.scenario_id === idB);

        const mesesDe = (h: "month" | "ytd") =>
          h === "month" ? [mes] : Array.from({ length: mes }, (_, i) => i + 1);

        /** El gasto de una clase, para un escenario y horizonte. */
        const clase = (g: GastoEscenario | null | undefined,
                       k: typeof CLASES[number]["key"], h: "month" | "ytd") => {
          if (!g) return null;
          const ms = mesesDe(h);
          return g.meses.filter(m => ms.includes(m.month))
            .reduce((s, m) => s + Number(m[k]), 0);
        };

        /** El valor de una línea. Los subtotales se DERIVAN — ver `ESTADO`. */
        const dato = (v: PLCompareVersion | null | undefined,
                      g: GastoEscenario | null | undefined,
                      code: string, h: "month" | "ytd"): number | null => {
          const c = v?.[h];
          const rev = c ? valor(c, "TOTAL_REVENUES") : null;
          const fb = c ? LINEAS_FB.reduce((s, l) => s + valor(c, l), 0) : null;
          const rooms = c ? LINEAS_ROOMS.reduce((s, l) => s + valor(c, l), 0) : null;
          const pay = clase(g, "payroll", h), cos = clase(g, "cost", h);
          const ope = clase(g, "opex", h), pro = clase(g, "property", h);
          const totExp = pay === null || cos === null || ope === null
            ? null : pay + cos + ope;
          switch (code) {
            case "X_ROOMS": return rooms;
            case "X_FB":    return fb;
            case "X_OTHER": return c && rev !== null && fb !== null && rooms !== null
                                 ? rev - rooms - fb : null;
            case "C_PAYROLL":  return pay;
            case "C_COST":     return cos;
            case "C_OPEX":     return ope;
            case "C_PROPERTY": return pro;
            case "X_TOTEXP":   return totExp;
            case "X_GOP":      return rev === null || totExp === null ? null : rev - totExp;
            case "X_EBITDA": {
              if (rev === null || totExp === null || pro === null) return null;
              return rev - totExp - pro;
            }
            default: return c ? valor(c, code) : null;
          }
        };

        const pctRev = (v: PLCompareVersion | null | undefined,
                        g: GastoEscenario | null | undefined,
                        code: string, h: "month" | "ytd"): number | null => {
          const rev = v?.[h] ? valor(v[h]!, "TOTAL_REVENUES") : null;
          const x = dato(v, g, code, h);
          return rev && x !== null ? x / rev : null;
        };

        /* ⚠️ El GOP derivado (ingreso − clases 5/6/7) contra el del motor
         * (suma de las líneas por departamento). Son dos caminos distintos y
         * TIENEN que dar lo mismo; si se separan, hay gasto que un camino ve y
         * el otro no. Es exactamente el tipo de diferencia que no avisa sola. */
        const gopMotor = vA?.ytd ? valor(vA.ytd, "TOTAL_GOP") : null;
        const gopDerivado = dato(vA, gA, "X_GOP", "ytd");
        const brecha = gopMotor !== null && gopDerivado !== null
          ? gopDerivado - gopMotor : null;
        const hayBrecha = brecha !== null && Math.abs(brecha) > 1;

        const bloques = [
          { titulo: `${MESES[mes - 1]} ${year}`, h: "month" as const },
          { titulo: t("ytdA", { mes: MESES[mes - 1], year: String(year) }), h: "ytd" as const },
        ];
        const TH2: React.CSSProperties = { ...TH, fontSize: 11.5 };
        const BL = "2px solid var(--border-medium)";

        if (!idA || !idB) return (
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {t("eligePar")}
          </p>
        );

        function bajarEstado() {
          const columnas: ColumnaCuadro[] = [
            { label: "Line Item", ancho: 26, formato: "texto" },
            ...bloques.flatMap(bl => ([
              { label: `${etiqueta(idA)} · ${bl.titulo}`, ancho: 17, formato: "usd2" as const },
              { label: `${etiqueta(idB)} · ${bl.titulo}`, ancho: 17, formato: "usd2" as const },
              { label: "Var $", ancho: 15, formato: "usd2" as const },
              { label: "Var %", ancho: 10, formato: "pct" as const },
              { label: `% Rev ${bl.titulo}`, ancho: 12, formato: "pct" as const },
              { label: `% Rev Budget ${bl.titulo}`, ancho: 13, formato: "pct" as const },
            ])),
            { label: prevScn ? `% Rev ${prevScn.year}` : `% Rev ${t("anioAnt")}`, ancho: 12, formato: "pct" as const },
            { label: "Commentary", ancho: 34, formato: "texto" as const },
          ];
          const filas: FilaCuadro[] = ESTADO.map(f => ({
            label: f.label, es_total: !!f.fuerte,
            valores: [
              ...bloques.flatMap(bl => {
                const a = dato(vA, gA, f.code, bl.h);
                const b = dato(vB, gB, f.code, bl.h);
                const d = a === null || b === null ? null : a - b;
                const p = d === null || !b ? null : d / Math.abs(b);
                return [a, b, d, p, pctRev(vA, gA, f.code, bl.h), pctRev(vB, gB, f.code, bl.h)];
              }),
              pctRev(prevPL, prevGasto, f.code, "ytd"),
              null,
            ],
          }));
          bajarCuadros(`PL_Statement_${MESES[mes - 1]}_${year}`, [{
            titulo: `Profit & Loss Statement YTD ${MESES[mes - 1].toUpperCase()} ${year}`,
            subtitulo: `${etiqueta(idA)} vs ${etiqueta(idB)} · USD`,
            hoja: `P&L ${MESES[mes - 1]}`,
            columnas, filas,
          }]).catch(e => alert(e instanceof Error ? e.message : t("errExcel")));
        }

        return (
          <div>
            <div style={{ display: "flex", alignItems: "flex-start",
                          justifyContent: "space-between", gap: 16, marginBottom: 12 }}>
              <p style={{ fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 820 }}>
                {t.rich("estadoIntro", bold)}
              </p>
              <button onClick={bajarEstado} style={{
                padding: "6px 13px", borderRadius: 6, cursor: "pointer", flexShrink: 0,
                background: "var(--accent-excel)", color: "#fff", border: "none",
                fontSize: 12.5, fontWeight: 600,
              }}>⬇ Excel</button>
            </div>

            {hayBrecha && (
              <div style={{
                padding: "9px 12px", borderRadius: 6, marginBottom: 12, fontSize: 12.5,
                background: "rgba(230,168,23,0.12)", border: "1px solid rgba(230,168,23,0.4)",
              }}>
                {t.rich("estadoBrecha", {
                  ...bold,
                  derivado: usd(gopDerivado!), motor: usd(gopMotor!), brecha: usd(brecha!),
                })}
              </div>
            )}

            <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 1560 }}>
              <thead>
                <tr>
                  <th rowSpan={2} style={{ ...TH, textAlign: "left", verticalAlign: "bottom" }}>Line Item</th>
                  {bloques.map(bl => (
                    <th key={bl.h} colSpan={6} style={{ ...TH, borderLeft: BL }}>{bl.titulo}</th>
                  ))}
                  <th rowSpan={2} style={{ ...TH, borderLeft: BL }}>
                    % Rev<br />{prevScn ? prevScn.year : t("anioAnt")}
                  </th>
                  <th rowSpan={2} style={{ ...TH, borderLeft: BL }}>Commentary</th>
                </tr>
                <tr>
                  {bloques.map(bl => (
                    <Fragment key={bl.h}>
                      <th style={{ ...TH2, borderLeft: BL }}>{etiqueta(idA)}</th>
                      <th style={TH2}>{etiqueta(idB)}</th>
                      <th style={{ ...TH2, color: "var(--brand)" }}>Var $</th>
                      <th style={{ ...TH2, color: "var(--brand)" }}>Var %</th>
                      <th style={TH2}>% Rev</th>
                      <th style={TH2}>% Rev Bud</th>
                    </Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ESTADO.map(f => (
                  <tr key={f.code} style={{
                    background: f.fuerte ? "var(--bg-elevated)" : undefined,
                    borderTop: f.borde ? BL : undefined,
                  }}>
                    <td style={{ ...TDL, fontWeight: f.fuerte ? 700 : 500 }}>{f.label}</td>
                    {bloques.map(bl => {
                      const a = dato(vA, gA, f.code, bl.h);
                      const b = dato(vB, gB, f.code, bl.h);
                      const d = a === null || b === null ? null : a - b;
                      // ⚠️ Se divide por el VALOR ABSOLUTO de la base. Dividir
                      // por el valor con signo invierte la lectura cuando la
                      // base es negativa: un GOP que empeora de −118,970 a
                      // −151,862 saldría como «+28%», en verde. El Excel del
                      // owner tiene justo esa vuelta.
                      const p = d === null || !b ? null : d / Math.abs(b);
                      const cv = d === null || d === 0 ? "var(--text-secondary)"
                        : (f.gasto ? d < 0 : d > 0) ? "var(--positive)" : "var(--negative)";
                      const num = (x: number | null) => x === null ? "—" : usd(x);
                      const pc = (x: number | null) => x === null ? "—" : pct(x);
                      return (
                        <Fragment key={bl.h}>
                          <td className="mono" style={{ ...TD, borderLeft: BL,
                            fontWeight: f.fuerte ? 700 : 400,
                            color: a !== null && a < 0 ? "var(--negative)" : undefined }}>{num(a)}</td>
                          <td className="mono" style={{ ...TD, fontWeight: f.fuerte ? 700 : 400,
                            color: b !== null && b < 0 ? "var(--negative)" : undefined }}>{num(b)}</td>
                          <td className="mono" style={{ ...TD, color: cv, fontSize: 12.5 }}>{num(d)}</td>
                          <td className="mono" style={{ ...TD, color: cv, fontSize: 12 }}>
                            {p === null ? "—" : `${(p * 100).toFixed(1)}%`}
                          </td>
                          <td className="mono" style={{ ...TD, fontSize: 12, color: "var(--text-secondary)" }}>
                            {pc(pctRev(vA, gA, f.code, bl.h))}
                          </td>
                          <td className="mono" style={{ ...TD, fontSize: 12, color: "var(--text-secondary)" }}>
                            {pc(pctRev(vB, gB, f.code, bl.h))}
                          </td>
                        </Fragment>
                      );
                    })}
                    <td className="mono" style={{ ...TD, borderLeft: BL, fontSize: 12,
                      color: "var(--text-secondary)" }}>
                      {prevPL ? (pctRev(prevPL, prevGasto, f.code, "ytd") === null ? "—"
                        : pct(pctRev(prevPL, prevGasto, f.code, "ytd")!)) : "—"}
                    </td>
                    <td style={{ ...TDL, borderLeft: BL }}></td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>

            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 12, maxWidth: 900 }}>
              {prevScn
                ? t.rich("estadoPieConPrev", { ...bold, esc: etiqueta(prevScn.id) })
                : t("estadoPieSinPrev")}
              {" "}{t.rich("estadoPieSubtotales", bold)}
            </p>
          </div>
        );
      })()}

      {vista === "summary" && (() => {
        /* El cuadro de cierre del owner: mes y YTD lado a lado. Ver `SUMMARY`. */
        const idA = ranuras[varA], idB = ranuras[varB];
        const vA = datos.find(d => d.scenario_id === idA);
        const vB = datos.find(d => d.scenario_id === idB);

        /** El valor de una fila para un escenario y un horizonte. */
        const dato = (v: PLCompareVersion | undefined, id: string,
                      code: string, h: "month" | "ytd"): number | null => {
          if (!v) return null;
          // La caja es un SALDO, no un flujo: el «YTD» de la caja final es el
          // mismo saldo del mes, no la suma de los meses. Sumarlo daria un
          // numero que no significa nada — y en el cuadro del owner las dos
          // columnas muestran exactamente lo mismo, que lo confirma.
          if (code === "X_CASH") {
            const serie = caja[id];
            return serie && serie.length >= mes ? serie[mes - 1] : null;
          }
          const c = v[h];
          if (!c) return null;
          switch (code) {
            case "K_ROOMS_AVAIL": return c.kpis.rooms_available;
            case "K_ROOMS_OCC":   return c.kpis.rooms_occupied;
            case "K_GUESTS":      return c.kpis.guests;
            case "K_OCC":         return c.kpis.occupancy_pct;
            case "K_ADR":         return c.kpis.adr;
            case "K_REVPAR":      return c.kpis.revpar;
            // «Other» es el RESTO, no una suma de líneas sueltas. Así los tres
            // renglones de ingreso siempre suman Total Revenue: si mañana
            // aparece una línea nueva, cae acá sola en vez de desaparecer del
            // cuadro sin que nadie lo note.
            case "X_ROOMS": return LINEAS_ROOMS.reduce((s, l) => s + valor(c, l), 0);
            case "X_FB":    return LINEAS_FB.reduce((s, l) => s + valor(c, l), 0);
            case "X_OTHER": return valor(c, "TOTAL_REVENUES")
                                 - LINEAS_ROOMS.reduce((s, l) => s + valor(c, l), 0)
                                 - LINEAS_FB.reduce((s, l) => s + valor(c, l), 0);
            default: return valor(c, code);
          }
        };

        const fmt = (n: number | null, tipo: typeof SUMMARY[number]["tipo"]) =>
          n === null ? "—" : tipo === "pct" ? pct(n) : tipo === "num" ? num0(n) : usd(n);

        /** Un par de columnas (valor A, valor B) con su variación. */
        const par = (f: typeof SUMMARY[number], h: "month" | "ytd") => {
          const a = dato(vA, idA, f.code, h);
          const b = dato(vB, idB, f.code, h);
          const d = a === null || b === null ? null : a - b;
          const p = d === null || !b ? null : d / Math.abs(b);
          // En gasto, gastar de mas es malo aunque el numero sea positivo. Acá
          // todas las filas son ingreso, resultado o volumen: más es mejor.
          const bueno = d !== null && (f.gasto ? d < 0 : d > 0);
          return { a, b, d, p, bueno };
        };

        const TH2: React.CSSProperties = { ...TH, fontSize: 12 };
        const bloques = [
          { titulo: `${MESES[mes - 1]} ${year}`, h: "month" as const },
          { titulo: t("ytdA", { mes: MESES[mes - 1], year: String(year) }), h: "ytd" as const },
        ];

        function bajarSummary() {
          const columnas: ColumnaCuadro[] = [
            { label: "Metric", ancho: 30, formato: "texto" },
            ...bloques.flatMap(bl => ([
              { label: `${etiqueta(idA)} · ${bl.titulo}`, ancho: 18, formato: "usd2" as const },
              { label: `${etiqueta(idB)} · ${bl.titulo}`, ancho: 18, formato: "usd2" as const },
              { label: "Var $", ancho: 15, formato: "usd2" as const },
              { label: "Var %", ancho: 11, formato: "pct" as const },
            ])),
            { label: "Notes", ancho: 30, formato: "texto" as const },
          ];
          const filas: FilaCuadro[] = SUMMARY.map(f => ({
            label: f.label,
            es_total: !!f.fuerte,
            formato: f.tipo === "pct" ? "pct" : f.tipo === "num" ? "num" : undefined,
            valores: [
              ...bloques.flatMap(bl => {
                const v = par(f, bl.h);
                return [v.a, v.b, v.d, v.p];
              }),
              null,
            ],
          }));
          bajarCuadros(`Summary_${MESES[mes - 1]}_${year}`, [{
            titulo: `${MESES[mes - 1].toUpperCase()} ${year} Summary`,
            subtitulo: `${etiqueta(idA)} vs ${etiqueta(idB)} · USD`,
            hoja: `Summary ${MESES[mes - 1]}`,
            columnas, filas,
          }]).catch(e => alert(e instanceof Error ? e.message : t("errExcel")));
        }

        if (!idA || !idB) return (
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {t("eligePar")}
          </p>
        );

        return (
          <div>
            <div style={{ display: "flex", alignItems: "flex-start",
                          justifyContent: "space-between", gap: 16, marginBottom: 12 }}>
              <p style={{ fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 820 }}>
                {t.rich("summaryIntro", { ...bold, escA: etiqueta(idA), escB: etiqueta(idB) })}
              </p>
              <button onClick={bajarSummary} style={{
                padding: "6px 13px", borderRadius: 6, cursor: "pointer", flexShrink: 0,
                background: "var(--accent-excel)", color: "#fff", border: "none",
                fontSize: 12.5, fontWeight: 600,
              }}>⬇ Excel</button>
            </div>

            {avisoCaja && (
              <div style={{
                padding: "9px 12px", borderRadius: 6, marginBottom: 12, fontSize: 12.5,
                background: "rgba(230,168,23,0.12)", border: "1px solid rgba(230,168,23,0.4)",
              }}>{avisoCaja}</div>
            )}

            <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 1180 }}>
              <thead>
                <tr>
                  <th rowSpan={2} style={{ ...TH, textAlign: "left", verticalAlign: "bottom" }}>Metric</th>
                  {bloques.map(bl => (
                    <th key={bl.h} colSpan={4} style={{ ...TH, borderLeft: "2px solid var(--border-medium)" }}>
                      {bl.titulo}
                    </th>
                  ))}
                  <th rowSpan={2} style={{ ...TH, borderLeft: "2px solid var(--border-medium)" }}>Notes</th>
                </tr>
                <tr>
                  {bloques.map(bl => (
                    <Fragment key={bl.h}>
                      <th style={{ ...TH2, borderLeft: "2px solid var(--border-medium)" }}>{etiqueta(idA)}</th>
                      <th style={TH2}>{etiqueta(idB)}</th>
                      <th style={{ ...TH2, color: "var(--brand)" }}>Var $</th>
                      <th style={{ ...TH2, color: "var(--brand)" }}>Var %</th>
                    </Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {SUMMARY.map(f => (
                  <Fragment key={f.code}>
                    {f.separaAntes && (
                      <tr><td colSpan={10} style={{ height: 10, borderBottom: "1px solid var(--border-medium)" }} /></tr>
                    )}
                    <tr style={f.fuerte ? { background: "var(--bg-elevated)" } : undefined}>
                      <td style={{ ...TDL, fontWeight: f.fuerte ? 700 : 500 }}>{f.label}</td>
                      {bloques.map(bl => {
                        const v = par(f, bl.h);
                        const cv = v.d === null || v.d === 0 ? "var(--text-secondary)"
                          : v.bueno ? "var(--positive)" : "var(--negative)";
                        return (
                          <Fragment key={bl.h}>
                            <td className="mono" style={{ ...TD, fontWeight: f.fuerte ? 700 : 400,
                              borderLeft: "2px solid var(--border-medium)",
                              color: v.a !== null && v.a < 0 ? "var(--negative)" : undefined }}>
                              {fmt(v.a, f.tipo)}
                            </td>
                            <td className="mono" style={{ ...TD, fontWeight: f.fuerte ? 700 : 400,
                              color: v.b !== null && v.b < 0 ? "var(--negative)" : undefined }}>
                              {fmt(v.b, f.tipo)}
                            </td>
                            <td className="mono" style={{ ...TD, color: cv, fontSize: 12.5 }}>
                              {v.d === null ? "—" : fmt(v.d, f.tipo)}
                            </td>
                            <td className="mono" style={{ ...TD, color: cv, fontSize: 12 }}>
                              {v.p === null ? "—" : `${v.p >= 0 ? "" : "-"}${(Math.abs(v.p) * 100).toFixed(1)}%`}
                            </td>
                          </Fragment>
                        );
                      })}
                      <td style={{ ...TDL, borderLeft: "2px solid var(--border-medium)" }}></td>
                    </tr>
                  </Fragment>
                ))}
              </tbody>
            </table>
            </div>

            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 12, maxWidth: 880 }}>
              {t.rich("summaryPie", bold)}
            </p>
          </div>
        );
      })()}

      {vista === "simple" && (() => {
        /* Copia del Simplified P&L, alimentada con las ranuras y el horizonte
         * de esta pantalla. Ver el comentario de `SIMPLE` arriba. */
        const margen = (c: PLColumn | undefined, code: string) => {
          if (!c) return 0;
          const rev = valor(c, "TOTAL_REVENUES");
          if (!rev) return 0;
          return valor(c, code === "GOP_MARGIN" ? "TOTAL_GOP" : "NET_PROFIT") / rev;
        };
        const celda = (c: PLColumn | undefined, f: typeof SIMPLE[number]["filas"][number]) => {
          if (!c) return "—";
          if (vacio(f, c)) return "—";
          if (f.margen) return pct(margen(c, f.code));
          return usd(valor(c, f.code));
        };
        return (
          <div>
            <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 12, maxWidth: 880 }}>
              {t.rich("simpleIntro", { ...bold, periodo: periodo.toLowerCase() })}
            </p>
            <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ width: anchoTabla, tableLayout: "fixed" }}>
              {rejilla}
              <thead>
                <tr>
                  <th style={{ ...TH, textAlign: "left" }}>{periodo}</th>
                  {usadas.slice(0, trasVariacion).map(u => <th key={u.i} style={TH}>{etiqueta(u.id)}</th>)}
                  <th style={{ ...TH, color: "var(--brand)" }}>{t("variacionD")}</th>
                  <th style={{ ...TH, color: "var(--brand)" }}>{t("variacionP")}</th>
                  {usadas.slice(trasVariacion).map(u => <th key={u.i} style={TH}>{etiqueta(u.id)}</th>)}
                </tr>
              </thead>
              <tbody>
                {/* Las estadísticas van arriba, igual que en la pantalla original. */}
                <tr><td colSpan={usadas.length + 3} style={{
                  ...TDL, paddingTop: 12, fontSize: 10.5, fontWeight: 700,
                  letterSpacing: 0.8, color: "var(--text-secondary)",
                }}>STATISTICS</td></tr>
                {kpis.map(k => (
                  <tr key={k.label}>
                    <td style={{ ...TDL, paddingLeft: 22, color: "var(--text-secondary)" }}>{k.label}</td>
                    {usadas.slice(0, trasVariacion).map(u => (
                      <td key={u.i} className="mono" style={TD}>{k.get(cols[u.i])}</td>
                    ))}
                    <td></td><td></td>
                    {usadas.slice(trasVariacion).map(u => (
                      <td key={u.i} className="mono" style={TD}>{k.get(cols[u.i])}</td>
                    ))}
                  </tr>
                ))}

                {SIMPLE.map(sec => (
                  <Fragment key={sec.titulo}>
                    <tr><td colSpan={usadas.length + 3} style={{
                      ...TDL, paddingTop: 12, fontSize: 10.5, fontWeight: 700,
                      letterSpacing: 0.8, color: "var(--text-secondary)",
                      borderBottom: "1px solid var(--border-medium)",
                    }}>{sec.titulo}</td></tr>
                    {sec.filas.map(f => {
                      const v = variacion(f.code, f.gasto);
                      // El margen es un cociente: su variación son puntos
                      // porcentuales, no dólares. Restar los dólares del GOP
                      // acá diría cualquier cosa.
                      const dm = f.margen && !v.sinDato
                        ? margen(cols[varA], f.code) - margen(cols[varB], f.code) : null;
                      const color = v.sinDato || vacio(f, cols[varA]) || v.d === 0 ? "var(--text-secondary)"
                        : v.bueno ? "var(--positive)" : "var(--negative)";
                      return (
                        <tr key={f.code} style={f.fuerte ? { background: "var(--bg-elevated)" } : undefined}>
                          <td style={{
                            ...TDL, paddingLeft: f.sangria ? 22 : 10,
                            fontWeight: f.fuerte ? 700 : 500,
                            color: f.fuerte ? "var(--text-primary)" : "var(--text-secondary)",
                          }}>{f.label}</td>
                          {usadas.slice(0, trasVariacion).map(u => (
                            <td key={u.i} className="mono" style={{
                              ...TD, fontWeight: f.fuerte ? 700 : 400,
                              color: vacio(f, cols[u.i]) ? "var(--text-disabled)"
                                : f.margen ? undefined : colorNum(valor(cols[u.i], f.code)),
                            }}>{celda(cols[u.i], f)}</td>
                          ))}
                          <td className="mono" style={{ ...TD, color, fontSize: 12.5 }}>
                            {v.sinDato || vacio(f, cols[varA]) ? "—"
                              : dm !== null ? (dm >= 0 ? "+" : "") + pct(dm)
                              : (v.d >= 0 ? "+" : "") + usd(v.d)}
                          </td>
                          <td className="mono" style={{ ...TD, color, fontSize: 12 }}>
                            {v.sinDato || vacio(f, cols[varA]) || f.margen || v.p === 0 ? "—"
                              : `${v.p >= 0 ? "+" : ""}${(v.p * 100).toFixed(1)}%`}
                          </td>
                          {usadas.slice(trasVariacion).map(u => (
                            <td key={u.i} className="mono" style={{
                              ...TD, fontWeight: f.fuerte ? 700 : 400,
                              color: vacio(f, cols[u.i]) ? "var(--text-disabled)"
                                : f.margen ? undefined : colorNum(valor(cols[u.i], f.code)),
                            }}>{celda(cols[u.i], f)}</td>
                          ))}
                        </tr>
                      );
                    })}
                  </Fragment>
                ))}
              </tbody>
            </table>
            </div>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 12, maxWidth: 880 }}>
              {t.rich("simplePie", bold)}
            </p>
          </div>
        );
      })()}

      {vista === "flow" && (() => {
        /* Flow Through: la misma variacion del P&L, resumida en los conceptos
         * con los que el owner explica el mes. No recalcula nada — toma las
         * lineas de la cascada y las clases del pie, que ya estan conciliadas.
         *
         * El orden es deliberado: arriba lo que suma, en el medio lo que resta
         * abierto por naturaleza del gasto, y abajo los dos resultados. Se lee
         * como una explicacion, no como una tabla. */
        const filaPL = (code: string, esGasto: boolean) => {
          const v = variacion(code, esGasto);
          return { d: v.sinDato ? null : v.d, bueno: v.bueno };
        };
        const filaClase = (k: typeof CLASES[number]["key"]) => {
          const a = gastoClase(varA, k), b = gastoClase(varB, k);
          const d = sinDatoVar ? null : a - b;
          return { d, bueno: d !== null && d < 0 };
        };
        const conceptos: { label: string; v: { d: number | null; bueno: boolean }; fuerte?: boolean }[] = [
          { label: "Revenue", v: filaPL("TOTAL_REVENUES", false) },
          { label: "Payroll and Benefits", v: filaClase("payroll") },
          { label: "Operating Expenses", v: filaClase("opex") },
          { label: "Cost of Sales", v: filaClase("cost") },
          { label: "Property / Capital", v: filaClase("property") },
          { label: "EBITDA Before Capital", v: filaPL("EBITDA_BEFORE_CAPITAL", false), fuerte: true },
          { label: "Net Profit", v: filaPL("NET_PROFIT", false), fuerte: true },
        ];
        return (
          <div>
            <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 12, maxWidth: 880 }}>
              {t.rich("flowIntro", {
                ...bold,
                escA: etiqueta(ranuras[varA]), escB: etiqueta(ranuras[varB]),
                periodo: periodo.toLowerCase(),
              })}
            </p>
            <table className="fin-table" style={{ maxWidth: 620 }}>
              <thead>
                <tr>
                  <th style={{ ...TH, textAlign: "left" }}>{tc("concept")}</th>
                  <th style={TH}>{t("variacionDolar")}</th>
                </tr>
              </thead>
              <tbody>
                {conceptos.map(c => (
                  <tr key={c.label} style={c.fuerte ? { background: "var(--bg-elevated)" } : undefined}>
                    <td style={{ ...TDL, fontWeight: c.fuerte ? 700 : 500 }}>{c.label}</td>
                    <td className="mono" style={{
                      ...TD, fontWeight: c.fuerte ? 700 : 400,
                      color: c.v.d === null || c.v.d === 0 ? "var(--text-secondary)"
                        : c.v.bueno ? "var(--positive)" : "var(--negative)",
                    }}>{c.v.d === null ? "—" : usd(c.v.d)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 12, maxWidth: 880 }}>
              {t.rich("flowPie", bold)}
            </p>
          </div>
        );
      })()}

      {vista === "consulta" && (
        <div>
          <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 12, maxWidth: 900 }}>
            {t.rich("consultaIntro", bold)}
          </p>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
            <select value={cjto} onChange={e => setCjto(e.target.value)} style={{ ...SEL, minWidth: 260 }}>
              {(cat?.conjuntos ?? [{ key: "gl", label: t("glDetalle"), nota: "" }]).map(c => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>
            <input value={fCuenta} onChange={e => setFCuenta(e.target.value)}
              placeholder={t("phCuenta")} style={{ ...SEL, width: 170 }} />
            <input value={fDept} onChange={e => setFDept(e.target.value)}
              placeholder={t("phDepto")} style={{ ...SEL, width: 140 }} />
            {/* Clase = primer digito de la cuenta. Va aparte del campo de cuenta
                porque se COMBINAN: clase 6 y 7, y ademas cuenta que empiece con
                60, tiene que dar la interseccion. Si compartieran campo, una
                anularia a la otra sin que se note. */}
            <span style={{ display: "flex", gap: 3, alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "var(--text-secondary)", marginRight: 3 }}>{t("clase")}</span>
              {["1","2","3","4","5","6","7","8","9"].map(d => {
                const on = fClases.has(d);
                return (
                  <button key={d} title={t("claseTitle", { d })}
                    onClick={() => setFClases(prev => {
                      const n = new Set(prev);
                      if (n.has(d)) n.delete(d); else n.add(d);
                      return n;
                    })}
                    style={{
                      width: 26, height: 26, borderRadius: 5, cursor: "pointer",
                      fontSize: 12, fontWeight: 600,
                      background: on ? "var(--brand)" : "var(--bg-surface)",
                      color: on ? "#fff" : "var(--text-secondary)",
                      border: on ? "none" : "1px solid var(--border-medium)",
                    }}>{d}</button>
                );
              })}
              {fClases.size > 0 && (
                <button onClick={() => setFClases(new Set())} title={t("todasLasClases")}
                  style={{ ...SEL, padding: "3px 8px", cursor: "pointer", fontSize: 11 }}>
                  {t("todas")}
                </button>
              )}
            </span>
            <input value={fCtaDesde} onChange={e => setFCtaDesde(e.target.value)}
              placeholder={t("phCtaDesde")} style={{ ...SEL, width: 100 }} />
            <input value={fCtaHasta} onChange={e => setFCtaHasta(e.target.value)}
              placeholder={t("phCtaHasta")} style={{ ...SEL, width: 100 }} />
            <input value={fPos} onChange={e => setFPos(e.target.value)}
              placeholder={t("phPosicion")} style={{ ...SEL, width: 150 }} />
            <span style={{ display: "flex", gap: 4, alignItems: "center", fontSize: 11,
                           color: "var(--text-secondary)" }}>
              {t("meses")}
              <select value={qDesde} onChange={e => setQDesde(Number(e.target.value))} style={SEL}>
                {MESES.map((m, i) => <option key={m} value={i + 1}>{m.slice(0, 3)}</option>)}
              </select>
              <span>{t("aRango")}</span>
              <select value={qHasta} onChange={e => setQHasta(Number(e.target.value))} style={SEL}>
                {MESES.map((m, i) => <option key={m} value={i + 1}>{m.slice(0, 3)}</option>)}
              </select>
            </span>
            <button onClick={correr} disabled={qCargando}
              style={{ ...SEL, cursor: "pointer", fontWeight: 600, background: "var(--brand)", color: "#fff", border: "none" }}>
              {qCargando ? t("buscando") : t("buscar")}
            </button>
            <button onClick={() => bajarConsultaExcel(filtroConsulta()).catch(e => setError(String(e)))}
              style={{ ...SEL, cursor: "pointer", fontWeight: 600 }}>⬇ Excel</button>
          </div>

          {(cat?.conjuntos ?? []).find(c => c.key === cjto)?.nota && (
            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>
              {(cat?.conjuntos ?? []).find(c => c.key === cjto)?.nota}
            </p>
          )}

          {qInfo && (
            <p style={{ fontSize: 12.5, marginBottom: 10 }}>
              <strong>{qInfo.cantidad.toLocaleString("en-US")}</strong> {t("filas")} ·
              {" "}{t("totalLabel")} <strong className="mono">{usd(qInfo.total)}</strong>
              {qInfo.truncado && (
                <span style={{ color: "var(--negative)" }}>
                  {" "}{t("truncado")}
                </span>
              )}
            </p>
          )}

          <div className="fin-scroll-x" style={{ overflowX: "auto", maxHeight: "60vh" }}>
            <table className="fin-table" style={{ minWidth: 1100 }}>
              <thead>
                <tr>
                  {["escenario","mes","depto","nombreDepto","cuenta","nombreCuenta","lineaPl","posicion","monto"]
                    .map((h, i) => (
                      <th key={h} style={{ ...TH, textAlign: i === 8 ? "right" : "left" }}>{t(`col_${h}`)}</th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {qFilas.map((f, i) => (
                  <tr key={i}>
                    <td style={TDL}>{f.escenario}</td>
                    <td style={TDL}>{f.mes}</td>
                    <td style={TDL} className="mono">{f.dept_code}</td>
                    <td style={TDL}>{f.dept_name}</td>
                    <td style={TDL} className="mono">{f.account_code}</td>
                    <td style={TDL}>{f.account_name}</td>
                    <td style={TDL} className="mono">{f.linea_pl}</td>
                    <td style={TDL} className="mono">
                      {f.position_code}{f.employee ? ` · ${f.employee}` : ""}
                    </td>
                    <td className="mono" style={{ ...TD, color: f.monto < 0 ? "var(--negative)" : undefined }}>
                      {usd(f.monto)}
                    </td>
                  </tr>
                ))}
                {!qFilas.length && !qCargando && (
                  <tr><td colSpan={9} style={{ padding: 14, fontSize: 12.5, color: "var(--text-secondary)" }}>
                    {t("consultaVacia")}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!cargando && vista !== "pl" && vista !== "consulta" && vista !== "flow" && (() => {
        const clase = vista as string;
        const { claves, valor } = apertura(clase);
        const esProp = clase === "property";
        // En propiedad el rotulo es la CUENTA con su nombre; en los demas, el
        // departamento con el suyo. Una lista de 8005, 8020, 8040 no le dice
        // nada a nadie (owner, 2026-08-14).
        const nombreCta = (k: string) => {
          for (const g of gastos) {
            const n = g.nombres_cuenta?.[k];
            if (n) return n;
          }
          return "";
        };
        const rotulo = (k: string) => {
          const n = esProp ? nombreCta(k) : deptos[k];
          return n ? `${k} · ${n}` : k;
        };
        // El ingreso sube cuando crece; el gasto, al reves. Sin esto, gastar de
        // mas saldria en verde en cuatro de los cinco cuadros.
        const esGasto = clase !== "revenue";
        const filasOrden = claves
          .map(k => ({ k, ref: Math.abs(valor(varA, k)) + Math.abs(valor(varB, k)) }))
          .sort((a, b) => b.ref - a.ref)
          .map(x => x.k);
        const total = (i: number) => claves.reduce((s2, k) => s2 + valor(i, k), 0);
        const fila = (k: string | null) => {
          const a = k === null ? total(varA) : valor(varA, k);
          const b = k === null ? total(varB) : valor(varB, k);
          const d = sinDatoVar ? 0 : a - b;
          const p = b !== 0 ? d / Math.abs(b) : 0;
          const bueno = esGasto ? d < 0 : d > 0;
          const color = sinDatoVar || d === 0 ? "var(--text-secondary)"
            : bueno ? "var(--positive)" : "var(--negative)";
          const celda = (i: number) => {
            const v = k === null ? total(i) : valor(i, k);
            return <td key={i} className="mono"
              style={{ ...TD, fontWeight: k === null ? 700 : 400,
                       color: v < 0 ? "var(--negative)" : undefined }}>{usd(v)}</td>;
          };
          return (
            <tr key={k ?? "__total"} style={k === null ? { background: "var(--bg-elevated)" } : undefined}>
              <td style={{ ...TDL, fontWeight: k === null ? 700 : 500 }}>
                {k === null ? "TOTAL" : rotulo(k)}
              </td>
              {usadas.slice(0, trasVariacion).map(u => celda(u.i))}
              <td style={{ ...TD, color, fontWeight: k === null ? 700 : 400 }} className="mono">
                {sinDatoVar ? "—" : usd(d)}
              </td>
              <td style={{ ...TD, color, fontWeight: k === null ? 700 : 400 }} className="mono">
                {sinDatoVar || !p ? "—" : pct(p)}
              </td>
              {usadas.slice(trasVariacion).map(u => celda(u.i))}
            </tr>
          );
        };
        return (
          <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
            {claves.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                {t("sinApertura")}
              </div>
            ) : (
              <table className="fin-table" style={{ width: anchoTabla, tableLayout: "fixed" }}>
                {rejilla}
                <thead>
                  <tr>
                    <th style={{ ...TH, textAlign: "left" }}>
                      {esProp ? t("hdrCuenta") : t("hdrDepartamento")} · {periodo}
                    </th>
                    {usadas.slice(0, trasVariacion).map(u => <th key={u.i} style={TH}>{etiqueta(u.id)}</th>)}
                    <th style={TH}>{t("variacionD")}</th>
                    <th style={TH}>{t("variacionP")}</th>
                    {usadas.slice(trasVariacion).map(u => <th key={u.i} style={TH}>{etiqueta(u.id)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {filasOrden.map(k => fila(k))}
                  {fila(null)}
                </tbody>
              </table>
            )}
          </div>
        );
      })()}

      {vista === "pl" && (cargando ? <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{tc("loading")}</div> : (
        <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
          <table className="fin-table"
            style={{ marginBottom: 18, width: anchoTabla, tableLayout: "fixed" }}>
            {rejilla}
            <thead>
              <tr>
                <th style={{ ...TH, textAlign: "left" }}>{periodo}</th>
                {usadas.slice(0, trasVariacion).map(u => <th key={u.i} style={TH}>{etiqueta(u.id)}</th>)}
                <th></th><th></th>
                {usadas.slice(trasVariacion).map(u => <th key={u.i} style={TH}>{etiqueta(u.id)}</th>)}
              </tr>
            </thead>
            <tbody>
              {kpis.map(k => {
                const celda = (i: number) => {
                  const t = k.get(cols[i]);
                  return <td key={i} className="mono"
                    style={{ ...TD, color: t.startsWith("-") ? "var(--negative)" : undefined }}>{t}</td>;
                };
                return (
                  <tr key={k.label}>
                    <td style={{ ...TDL, fontWeight: 600 }}>{k.label}</td>
                    {usadas.slice(0, trasVariacion).map(u => celda(u.i))}
                    <td></td><td></td>
                    {usadas.slice(trasVariacion).map(u => celda(u.i))}
                  </tr>
                );
              })}
            </tbody>
          </table>

          <table className="fin-table" style={{ width: anchoTabla, tableLayout: "fixed" }}>
            {rejilla}
            <thead>
              <tr>
                <th style={{ ...TH, textAlign: "left" }}>ACCOUNT DESCRIPTION</th>
                {usadas.slice(0, trasVariacion).map(u => <th key={u.i} style={TH}>{etiqueta(u.id)}</th>)}
                <th style={{ ...TH, color: "var(--brand)" }}>{t("variacionD")}</th>
                <th style={{ ...TH, color: "var(--brand)" }}>{t("variacionP")}</th>
                {usadas.slice(trasVariacion).map(u => <th key={u.i} style={TH}>{etiqueta(u.id)}</th>)}
              </tr>
            </thead>
            <tbody>
              {CASCADA.map(l => {
                const v = variacion(l.code, l.gasto);
                const color = v.sinDato || v.d === 0 ? "var(--text-secondary)"
                  : v.bueno ? "var(--positive)" : "var(--negative)";
                return (
                  <tr key={l.code} style={l.fuerte ? { background: "var(--bg-elevated)" } : undefined}>
                    <td style={{ ...TDL, fontWeight: l.fuerte ? 700 : 500 }}>
                      {l.code === "TOTAL_REVENUES" ? (
                        // El ingreso tambien tiene su apertura por departamento.
                        <button onClick={() => setVista("revenue")}
                          title={t("verIngresoPorDepto")}
                          style={{
                            background: "none", border: "none", padding: 0,
                            font: "inherit", fontWeight: 700, color: "var(--text-primary)",
                            cursor: "pointer", textAlign: "left",
                            textDecoration: "underline", textDecorationStyle: "dotted",
                            textUnderlineOffset: 3, textDecorationColor: "var(--text-disabled)",
                          }}>{l.label}</button>
                      ) : l.label}
                    </td>
                    {usadas.slice(0, trasVariacion).map(u => (
                      <td key={u.i} style={{ ...TD, fontWeight: l.fuerte ? 700 : 400,
                        color: vacio(l, cols[u.i]) ? "var(--text-disabled)" : colorNum(valor(cols[u.i], l.code)) }}
                        className="mono"
                        title={vacio(l, cols[u.i]) ? t("lineaSinResumen") : undefined}>
                        {vacio(l, cols[u.i]) ? "—" : usd(valor(cols[u.i], l.code))}
                      </td>
                    ))}
                    <td style={{ ...TD, color }} className="mono">{v.sinDato || vacio(l, cols[varA]) ? "—" : usd(v.d)}</td>
                    <td style={{ ...TD, color }} className="mono">{v.sinDato || l.sinMotor || !v.p ? "—" : pct(v.p)}</td>
                    {usadas.slice(trasVariacion).map(u => (
                      <td key={u.i} style={{ ...TD, fontWeight: l.fuerte ? 700 : 400,
                        color: vacio(l, cols[u.i]) ? "var(--text-disabled)" : colorNum(valor(cols[u.i], l.code)) }}
                        className="mono">
                        {vacio(l, cols[u.i]) ? "—" : usd(valor(cols[u.i], l.code))}
                      </td>
                    ))}
                  </tr>
                );
              })}
              <tr><td colSpan={usadas.length + 3} style={{ height: 12 }}></td></tr>

              {CLASES.map(c => {
                const a = gastoClase(varA, c.key);
                const b = gastoClase(varB, c.key);
                const d = sinDatoVar ? 0 : a - b;
                const p = b !== 0 ? d / Math.abs(b) : 0;
                // Son todas cuentas de GASTO: gastar de mas siempre es peor.
                const color = sinDatoVar || d === 0 ? "var(--text-secondary)"
                  : d < 0 ? "var(--positive)" : "var(--negative)";
                const celda = (i: number) => {
                  const v = gastoClase(i, c.key);
                  return <td key={i} className="mono"
                    style={{ ...TD, color: v < 0 ? "var(--negative)" : undefined }}>{usd(v)}</td>;
                };
                return (
                  <tr key={c.key}>
                    {/* La linea lleva a su sub-tab: es la misma cifra abierta por
                        departamento, y ahi es donde se explica de donde sale.
                        Cerrar el circulo evita el paso de «ver el total, ir a
                        buscar el tab, acordarse de que periodo estaba mirando». */}
                    <td style={TDL}>
                      <button onClick={() => setVista(c.key)}
                        title={t("verPorDepto", { clase: c.label })}
                        style={{
                          background: "none", border: "none", padding: 0,
                          font: "inherit", color: "var(--text-primary)",
                          cursor: "pointer", textAlign: "left",
                          textDecoration: "underline",
                          textDecorationStyle: "dotted",
                          textUnderlineOffset: 3,
                          textDecorationColor: "var(--text-disabled)",
                        }}>{c.label}</button>
                    </td>
                    {usadas.slice(0, trasVariacion).map(u => celda(u.i))}
                    <td style={{ ...TD, color }} className="mono">{sinDatoVar ? "—" : usd(d)}</td>
                    <td style={{ ...TD, color }} className="mono">{sinDatoVar || !p ? "—" : pct(p)}</td>
                    {usadas.slice(trasVariacion).map(u => celda(u.i))}
                  </tr>
                );
              })}

              {(() => {
                const tot = (i: number) => CLASES.reduce((s, c) => s + gastoClase(i, c.key), 0);
                const d = sinDatoVar ? 0 : tot(varA) - tot(varB);
                const b = tot(varB);
                const p = b !== 0 ? d / Math.abs(b) : 0;
                const color = sinDatoVar || d === 0 ? "var(--text-secondary)"
                  : d < 0 ? "var(--positive)" : "var(--negative)";
                return (
                  <tr style={{ background: "var(--bg-elevated)" }}>
                    <td style={{ ...TDL, fontWeight: 700 }}>Total Operating and Property Expenses</td>
                    {usadas.slice(0, trasVariacion).map(u => (
                      <td key={u.i} style={{ ...TD, fontWeight: 700 }} className="mono">{usd(tot(u.i))}</td>
                    ))}
                    <td style={{ ...TD, color, fontWeight: 700 }} className="mono">{sinDatoVar ? "—" : usd(d)}</td>
                    <td style={{ ...TD, color, fontWeight: 700 }} className="mono">{sinDatoVar || !p ? "—" : pct(p)}</td>
                    {usadas.slice(trasVariacion).map(u => (
                      <td key={u.i} style={{ ...TD, fontWeight: 700 }} className="mono">{usd(tot(u.i))}</td>
                    ))}
                  </tr>
                );
              })()}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}