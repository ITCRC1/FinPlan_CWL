"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import { semanasDe, fraccionForecast, type WeekDef } from "@/lib/weeks";
import { bajarCuadros, type Cuadro, type FilaCuadro, type FormatoCol } from "@/lib/exportCuadro";

/** Firma mínima de `useTranslations` que necesitan los armadores de rótulos.
 *  Los rótulos salen del catálogo, así que dejaron de ser constantes de módulo
 *  y pasaron a ser funciones que reciben el traductor. */
type Tr = (key: string) => string;

/** Las tres formas de mirar el On the Books.
 *
 *  `noches` es la que pidió el owner el 18-ago-2026: el On the Books de
 *  HABITACIONES VENDIDAS, sin plata de por medio. Un mes puede verse bien en
 *  dólares y estar vacío de gente si la tarifa subió — en noches eso no se
 *  puede disimular.
 */
type Vista = "total" | "rooms" | "noches";
const VISTAS: readonly Vista[] = ["total", "rooms", "noches"] as const;
const rotuloVista = (t: Tr): Record<Vista, string> => ({
  total: t("vistaTotal"), rooms: t("vistaRooms"), noches: t("vistaNoches"),
});
/** El 8.1 es una TABLA y puede mostrar las dos platas a la vez; el 8.5.1 es un
 *  gráfico de tres series y no. Por eso «Todo» existe solo en el 8.1 — y es su
 *  arranque, para que nadie pierda de vista lo que ya tenía. */
type VistaTabla = Vista | "todo";
const VISTAS_TABLA: readonly VistaTabla[] = ["todo", "total", "rooms", "noches"] as const;
const rotuloTabla = (t: Tr): Record<VistaTabla, string> => ({ todo: t("vistaTodo"), ...rotuloVista(t) });

/** Qué campo de `budget`/`otb` lee cada vista. */
const CAMPO_VISTA: Record<Vista, "total_revenue" | "rooms_only" | "rooms_occ"> = {
  total: "total_revenue", rooms: "rooms_only", noches: "rooms_occ",
};
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";
import {
  getScenarios, getPLMonthly, getOnTheBooks, getOtbWeeks, getOtbYears, getOtbParams, getOtbPacing, getDailyOcc, importOtbXml,
  type Scenario, type PLMonthly, type OnTheBooks, type OtbMonth, type OtbPacing, type DailyOcc,
} from "@/lib/api";

// La semana que contiene HOY. El upload nunca pide elegir semana — la calcula
// sola de la fecha real — así "subí cuando se pueda" no depende de acordarse
// en qué número de semana calendario estamos.
function semanaDeHoy(semanas: WeekDef[]): WeekDef | undefined {
  const hoy = new Date().toISOString().slice(0, 10);
  return semanas.find(w => hoy >= w.start && hoy <= w.end) ?? semanas[semanas.length - 1];
}

/**
 * Tab 8 · On the Books — puerto 1:1 de C:\DAILY-OPS\frontend\app\on-the-books\page.tsx.
 *
 * Mismos 8 sub-tabs, mismos nombres, mismas fórmulas (Sales on Property,
 * NET GAP, umbrales de riesgo del heatmap, media móvil de 2 períodos,
 * Análisis 2027). Lo ÚNICO que cambia es de dónde sale el dato: DAILY-OPS
 * tiene property_id + snapshot_date (fecha calendario); FinPlan tiene
 * scenario_id + week (semana ISO 1..53, sin fecha calendario propia — por
 * eso "snapshot_date" se muestra acá como el label de la semana). El resto
 * — cálculos, umbrales, colores, textos — es el mismo código, no una
 * versión adaptada.
 */

/** Rótulos de mes de reserva: si el catálogo no responde, la tabla igual sale. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** Los meses del catálogo, con MONTHS de red. */
function useMeses(): string[] {
  const tm = useTranslations("months");
  return (tm.raw("short") as string[]) ?? MONTHS;
}
const subtabs = (t: Tr) => [
  { id: "8.1", label: t("tab81") },
  { id: "8.2", label: t("tab82") },
  { id: "8.3", label: t("tab83") },
  { id: "8.4", label: t("tab84") },
  { id: "8.5", label: t("tab85") },
  { id: "8.5.1", label: t("tab851") },
  { id: "8.6", label: t("tab86") },
  { id: "8.7", label: t("tab87") },
];

type Metrics = {
  total_revenue: number; rooms_only: number; rooms_avail: number;
  rooms_occ: number; guests: number; adr_total: number; adr_only: number; occ: number;
};
type MonthData = {
  month: number; budget: Metrics; otb: Metrics; diff: Metrics;
  sales_on_property: number; net_gap: number;
  prev_total_revenue?: number | null; otb_move?: number | null; occ_move?: number | null;
  /** El movimiento entre cortes en NOCHES. En la vista de habitaciones
   *  vendidas no puede mostrarse el de dólares: ahí no hay plata. */
  otb_move_rooms?: number | null;
};
type Report = {
  year: number; snapshot_date: string | null; compare_snapshot_date?: string | null;
  months: MonthData[];
  net_gap_total: number; budget_total_revenue: number; otb_total_revenue: number;
  otb_move_total?: number | null;
};

const money = (v: number) =>
  v < 0 ? `(${Math.round(Math.abs(v)).toLocaleString()})` : Math.round(v).toLocaleString();
const dec = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 1 });
const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const neg = (v: number) => (v < 0 ? "text-red-400" : "");

const th = "px-2 py-1.5 text-right text-[11px] font-medium text-white/60";
const thl = "px-3 py-1.5 text-left text-[11px] font-medium text-white/60";
const tdL = "px-3 py-1 text-left text-white/80 whitespace-nowrap";

const lineAmt = (m: PLMonthly["months"][number] | undefined, code: string) =>
  m?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;


// ── Adaptador: arma el `Report` (forma exacta de DAILY-OPS) desde lo que
// FinPlan ya expone (getPLMonthly + getOnTheBooks + %Sales on Property). ──
function buildReport(
  bud: PLMonthly, otb: OnTheBooks, otbPrev: OnTheBooks | null,
  curPct: number, prevPct: number, weekLabel: string, prevWeekLabel: string | null,
  corteISO: string,
): Report {
  const otbM = (src: OnTheBooks | null, m: number): OtbMonth | undefined => src?.months.find(x => x.month === m);
  const adr = (rev: number, rooms: number) => (rooms ? rev / rooms : 0);
  const occ = (o: number, a: number) => (a ? o / a : 0);

  const months: MonthData[] = [];
  for (let m = 1; m <= 12; m++) {
    const bm = bud.months.find(x => x.month === m);
    const bt = lineAmt(bm, "TOTAL_REVENUES"), br = lineAmt(bm, "REV_ROOMS");
    const ba = bm?.kpis.rooms_available ?? 0, bo = bm?.kpis.rooms_occupied ?? 0, bg = bm?.kpis.guests ?? 0;
    const o = otbM(otb, m);
    const ot = o?.total_revenue ?? 0, orr = o?.rooms_revenue ?? 0, oo = o?.rooms_occupied ?? 0,
          og = o?.guests ?? 0, oa = o?.rooms_available ?? 0;
    // Solo sobre el forecast: el history ya trae su venta en propiedad.
    const sop = round2(orr * curPct * fraccionForecast(m, otb.year, corteISO));
    const p = otbM(otbPrev, m);
    const prevTotal = p ? p.total_revenue : null;

    months.push({
      month: m,
      budget: { total_revenue: round2(bt), rooms_only: round2(br), rooms_avail: ba, rooms_occ: bo,
                guests: bg, adr_total: adr(bt, bo), adr_only: adr(br, bo), occ: occ(bo, ba) },
      otb: { total_revenue: round2(ot), rooms_only: round2(orr), rooms_avail: oa, rooms_occ: round2(oo),
             guests: round2(og), adr_total: adr(ot, oo), adr_only: adr(orr, oo), occ: occ(oo, oa) },
      sales_on_property: sop,
      diff: { total_revenue: round2(ot - bt), rooms_only: round2(orr - br), rooms_avail: round2(oa - ba),
              rooms_occ: round2(oo - bo), guests: round2(og - bg), adr_total: round2(adr(ot, oo) - adr(bt, bo)),
              adr_only: round2(adr(orr, oo) - adr(br, bo)), occ: round4(occ(oo, oa) - occ(bo, ba)) },
      net_gap: round2((ot - bt) + sop),
      prev_total_revenue: prevTotal !== null ? round2(prevTotal) : null,
      otb_move: prevTotal !== null ? round2(ot - prevTotal) : null,
      otb_move_rooms: p ? round2(oo - p.rooms_occupied) : null,
    });
  }
  const otbTotal = round2(months.reduce((s, m) => s + m.otb.total_revenue, 0));
  const prevTotalSum = otbPrev ? months.reduce((s, m) => s + (m.prev_total_revenue ?? 0), 0) : null;
  return {
    year: otb.year, snapshot_date: weekLabel, compare_snapshot_date: prevWeekLabel,
    months,
    net_gap_total: round2(months.reduce((s, m) => s + m.net_gap, 0)),
    budget_total_revenue: round2(months.reduce((s, m) => s + m.budget.total_revenue, 0)),
    otb_total_revenue: otbTotal,
    otb_move_total: prevTotalSum !== null ? round2(otbTotal - prevTotalSum) : null,
  };
}
function round2(v: number) { return Math.round(v * 100) / 100; }
function round4(v: number) { return Math.round(v * 10000) / 10000; }

// Colapso por cuartos (Q1-Q4): cada mes o un cuarto agregado
type Col =
  | { kind: "m"; month: MonthData; label: string }
  | { kind: "q"; q: number; months: MonthData[]; label: string };

function buildCols(months: MonthData[], collapsed: number[], meses: string[] = MONTHS): Col[] {
  const cols: Col[] = [];
  for (let q = 1; q <= 4; q++) {
    const qm = months.slice((q - 1) * 3, q * 3);
    if (collapsed.includes(q)) cols.push({ kind: "q", q, months: qm, label: `Q${q}` });
    else qm.forEach((mo, i) => cols.push({ kind: "m", month: mo, label: meses[(q - 1) * 3 + i] }));
  }
  return cols;
}

function useQuarters() {
  const [collapsed, setCollapsed] = useState<number[]>([]);
  const toggle = (q: number) => setCollapsed((c) => (c.includes(q) ? c.filter((x) => x !== q) : [...c, q]));
  return { collapsed, toggle };
}

function QuarterBar({ collapsed, toggle }: { collapsed: number[]; toggle: (q: number) => void }) {
  const t = useTranslations("otb");
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-white/50">
      <span>{t("quarters")}</span>
      {[1, 2, 3, 4].map((q) => {
        const c = collapsed.includes(q);
        return (
          <button key={q} onClick={() => toggle(q)}
            className={`rounded px-2 py-0.5 font-mono ${c ? "bg-brand/30 text-white" : "bg-[#1E2130] text-white/60 hover:text-white"}`}
            title={c ? t("expandirQ", { q }) : t("colapsarQ", { q })}>
            {c ? "＋" : "－"} Q{q}
          </button>
        );
      })}
      <span className="text-white/30">{t("quartersAyuda")}</span>
    </div>
  );
}

const qsum = (ms: MonthData[], get: (d: MonthData) => number) => ms.reduce((s, x) => s + get(x), 0);
const qAdr = (ms: MonthData[], side: "budget" | "otb", kind: "total" | "only") => {
  const rev = qsum(ms, (d) => (kind === "total" ? d[side].total_revenue : d[side].rooms_only));
  const occ = qsum(ms, (d) => d[side].rooms_occ);
  return occ ? rev / occ : 0;
};
const qOcc = (ms: MonthData[], side: "budget" | "otb") => {
  const o = qsum(ms, (d) => d[side].rooms_occ), a = qsum(ms, (d) => d[side].rooms_avail);
  return a ? o / a : 0;
};

const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

export default function OnTheBooksPage() {
  const t = useTranslations("otb");
  const tc = useTranslations("common");
  const MESES = useMeses();
  /** Los meses en minúscula para nombrar un corte: `18-ago-2026`. */
  const MESES_COR = MESES.map(m => m.toLowerCase());
  const ALL_SUBTABS = subtabs(t);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  /** UN escenario para las dos cosas. Eran dos hooks con preferencias
   *  separadas —«budget» y «actual»— así que la pantalla ABRÍA comparando el
   *  presupuesto de un escenario contra las reservas de otro, sin decirlo.
   *  Ahora el On the Books se lee del mismo escenario que se presupuesta. */
  const [budId, setBudId] = useEscenarioDe("operation-insight/on-the-books:budget", scenarios, "budget", undefined, true);
  const otbId = budId;
  const [tab, setTab] = useState("8.1");
  const [week, setWeek] = useState(0);
  const [prevWeek, setPrevWeek] = useState(0);
  const [loadedWeeks, setLoadedWeeks] = useState<number[]>([]);
  /** ¿Ya sabemos si este escenario tiene cortes? Sin esto, un escenario SIN
   *  On the Books se quedaba en «Loading…» para siempre: `week` valía 0, el
   *  efecto de carga salía antes de pedir nada, `data` nunca dejaba de ser
   *  null — y la pantalla decía que estaba cargando algo que nunca iba a
   *  llegar. El owner lo reportó como «sigue pegado». */
  const [cortesListos, setCortesListos] = useState(false);
  // El XML del owner trae horizonte multi-año en el MISMO archivo (forecast
  // hasta varios años adelante del corte) — un solo escenario OTB puede tener
  // 2026, 2027, 2028... cargados a la vez. `year` elige cuál se está viendo;
  // gobierna TODOS los sub-tabs (8.5.1 aparte, que compara dos a la vez).
  const [year, setYear] = useState(0);
  const [availYears, setAvailYears] = useState<number[]>([]);
  /** Para qué escenario se eligió el `year` que está puesto. */
  const escDelAnio = useRef("");
  const [otbParams, setOtbParams] = useState<Record<number, number>>({});
  const [bud, setBud] = useState<PLMonthly | null>(null);
  const [otb, setOtb] = useState<OnTheBooks | null>(null);
  const [otbPrev, setOtbPrev] = useState<OnTheBooks | null>(null);
  const [pacing, setPacing] = useState<OtbPacing | null>(null);
  const [heat, setHeat] = useState<DailyOcc | null>(null);
  const [err, setErr] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [recalcMsg, setRecalcMsg] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const xmlRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
    // lista: aca solo se carga.
    (async () => {
      try { setScenarios(await getScenarios(HOTEL_ID)); }
      catch (e) { setErr(e instanceof Error ? e.message : tc("error")); }
    })();
  }, []);

  // Semanas cargadas → default: comparar los DOS cortes más recientes (this
  // week vs last week), como hace DAILY-OPS con snapshots — no asume que la
  // "anterior" es la semana calendario -1: es la ÚLTIMA carga previa, sea
  // cual sea la distancia real entre las dos.
  useEffect(() => {
    if (!otbId) return;
    let live = true;
    setCortesListos(false);
    getOtbWeeks(otbId).then(r => {
      if (!live) return;
      const ws = r.weeks;
      setLoadedWeeks(ws);
      if (ws.length >= 2) { setWeek(ws[ws.length - 1]); setPrevWeek(ws[ws.length - 2]); }
      else if (ws.length === 1) { setWeek(ws[0]); setPrevWeek(0); }
      else { setWeek(0); setPrevWeek(0); setAvailYears([]); setYear(0); }
      setCortesListos(true);
    }).catch(() => { if (live) { setLoadedWeeks([]); setWeek(0); setPrevWeek(0); setCortesListos(true); } });
    return () => { live = false; };
  }, [otbId, refreshKey]);

  useEffect(() => { if (otbId) getOtbParams(otbId).then(r => setOtbParams(r.by_week ?? {})).catch(() => setOtbParams({})); }, [otbId, refreshKey]);

  // Años cargados en ESTA semana (el XML trae varios a la vez en el mismo
  // archivo) — si el año elegido ya no está entre los disponibles (cambió de
  // semana/escenario), cae al más nuevo.
  useEffect(() => {
    if (!otbId || !week) { setAvailYears([]); return; }
    let live = true;
    getOtbYears(otbId, week).then(r => {
      if (!live) return;
      setAvailYears(r.years);
      // Al abrir se muestra el año DEL ESCENARIO, no el más nuevo del archivo.
      //
      // Antes caía en `years[years.length - 1]`: con un XML que proyecta a
      // 2028, el Budget 2027 abría comparando su presupuesto contra las
      // reservas de **2028** —el año más vacío del archivo, 1.426 noches
      // contra 4.621 del 2026— y nada en pantalla decía que eran años
      // distintos. Solo si el escenario no tiene año en el archivo se cae al
      // primero que sí haya.
      // ⚠️ Al CAMBIAR DE ESCENARIO se re-elige el año, aunque el que estaba
      // siga disponible. Antes solo se re-elegía si el año dejaba de existir:
      // pasando de Budget 2027 a Budget 2026, el 2027 seguía en la lista y se
      // quedaba pegado — la pantalla mostraba el presupuesto de 2026 contra
      // las reservas de 2027, y el total de Variance salía de dos años
      // distintos sin que nada lo dijera. Elegir el año a mano se respeta
      // mientras el escenario no cambie.
      const cambioDeEscenario = escDelAnio.current !== otbId;
      escDelAnio.current = otbId;
      if (r.years.length && (cambioDeEscenario || !r.years.includes(year))) {
        const propio = scenarios.find(s => s.id === otbId)?.year;
        setYear(r.years.includes(propio ?? 0) ? (propio as number) : r.years[0]);
      }
    }).catch(() => setAvailYears([]));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [otbId, week, refreshKey, scenarios]);

  useEffect(() => {
    // El `setErr("")` va ANTES del corte, no después.
    //
    // Estaba adentro, pasado el `return`: al pasar a un escenario SIN On the
    // Books el efecto salía sin limpiar nada y el error del escenario anterior
    // se quedaba en pantalla para siempre. El owner vio un 409 de «escenario
    // bloqueado» conviviendo con un «✓ Recalculated» — dos mensajes que se
    // contradecían, y ninguno de los dos era del momento.
    setErr("");
    if (!budId || !otbId || !week || !year) {
      // Sin corte que mostrar hay que BORRAR lo que había, no dejarlo.
      //
      // Antes solo se salía: al pasar a un escenario sin On the Books, los
      // números del escenario ANTERIOR se quedaban en pantalla bajo el nombre
      // del nuevo — el peor de los tres errores de esta pantalla, porque no
      // parece un error, parece un dato. Y el «Recalculando…» se colgaba para
      // siempre porque nunca llegaba a decir cómo terminó.
      setBud(null); setOtb(null); setOtbPrev(null);
      setRecalcMsg(m => (m ? "" : m));
      return;
    }
    let live = true;
    (async () => {
      try {
        const [b, o, p] = await Promise.all([
          getPLMonthly(budId), getOnTheBooks(otbId, week, year),
          prevWeek ? getOnTheBooks(otbId, prevWeek, year) : Promise.resolve(null),
        ]);
        if (!live) return;
        // ⚠️ Un corte anterior SIN datos de este año no es una comparación
        // válida: es la ausencia de comparación.
        //
        // `getOnTheBooks` siempre devuelve los doce meses, con ceros donde no
        // hay filas. Si el corte del 6-jul no cubre 2027, la resta daba
        // «OTB − 0» = el OTB entero, y el reporte anunciaba que TODO el 2027
        // se había vendido en esas seis semanas. `has_data` distingue «cero
        // vendido» de «este corte no llega hasta acá».
        setBud(b); setOtb(o); setOtbPrev(p && p.has_data ? p : null);
        setRecalcMsg(m => m ? t("recalculado", { hora: new Date().toLocaleTimeString() }) : m);
      } catch (e) {
        if (!live) return;
        setErr(e instanceof Error ? e.message : tc("error"));
        setRecalcMsg(m => m ? "" : m);   // falló: nada de visto verde
      }
    })();
    return () => { live = false; };
  }, [budId, otbId, week, prevWeek, year, refreshKey]);

  useEffect(() => {
    if (tab === "8.4" && otbId && year) getOtbPacing(otbId, year).then(setPacing).catch(() => setPacing(null));
  }, [tab, otbId, year, refreshKey]);
  useEffect(() => {
    if (tab === "8.3" && otbId && week && year) getDailyOcc(otbId, week, year).then(setHeat).catch(() => setHeat(null));
  }, [tab, otbId, week, year, refreshKey]);

  /** El calendario de CORTES va por el año en que se toma el corte, no por el
   *  año del dato que se está mirando. Antes seguía a `year`: al elegir el
   *  2028 del XML, un corte tomado el 17-ago-2026 se rotulaba «17-Aug-2028». */
  const SEMANAS = useMemo(() => semanasDe(new Date().getFullYear()), []);
  const hoyISO = new Date().toISOString().slice(0, 10);
  /** La fecha en que arranca un corte. Vacío si ese corte no existe. */
  const fechaDe = (n: number) => SEMANAS.find(w => w.n === n)?.start ?? "";
  /** El corte que regía en esa fecha: el ÚLTIMO cargado en o antes de ese día.
   *  No es «el corte de esa semana» — si esa semana no se subió, devuelve el
   *  anterior que sí existe, en vez de mostrar una pantalla vacía. */
  const corteEn = (fecha: string): number => {
    if (!fecha) return 0;
    const cand = SEMANAS.filter(w => w.start <= fecha && loadedWeeks.includes(w.n)).map(w => w.n);
    return cand.length ? Math.max(...cand) : 0;
  };
  /** Un corte se nombra por su FECHA, no por «W34»: el número solo no lleva
   *  año y no le dice nada a nadie fuera de esta pantalla. */
  const fmtCorte = (n: number) => {
    const w = SEMANAS.find(x => x.n === n);
    if (!w) return "—";
    const [y, m, d] = w.start.split("-");
    return `${d}-${MESES_COR[Number(m) - 1]}-${y}`;
  };
  const weekLabel = week ? fmtCorte(week) : "";
  const prevWeekLabel = prevWeek ? fmtCorte(prevWeek) : null;
  const curPct = otbParams[week] ?? 0.126;
  const prevPct = prevWeek ? (otbParams[prevWeek] ?? 0.126) : 0.126;

  const data = useMemo(() => {
    if (!bud || !otb) return null;
    return buildReport(bud, otb, otbPrev, curPct, prevPct, weekLabel, prevWeekLabel, fechaDe(week));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bud, otb, otbPrev, curPct, prevPct, weekLabel, prevWeekLabel, week]);

  const moved = data?.otb_move_total;
  /** Recalcular no puede declarar éxito por reloj.
   *
   *  Era `setTimeout(400)` y después «✓ Recalculated», pasara lo que pasara:
   *  el visto verde salía igual aunque la carga hubiera fallado. Ahora espera
   *  a que el efecto de carga termine de verdad y dice lo que ocurrió. */
  /** Bajar el Tab 8 a Excel: UNA HOJA POR CATEGORÍA de dato.
   *
   *  «Poné el Excel en este tab para poder bajar cada tab en formato
   *  profesional, y en tabs cada categoría de dato para poder analizar bien»
   *  (owner, 18-ago-2026).
   *
   *  Cuatro hojas —Budget, On the Books, Diff, NET GAP— cada una con los doce
   *  meses y su total. Se exporta SIEMPRE todo, sin importar qué vista esté
   *  puesta en pantalla: el conmutador sirve para leer, y el archivo es para
   *  analizar.
   *
   *  Los valores van como NÚMERO, nunca como texto ya formateado: un Excel con
   *  las cifras en texto no se puede sumar ni graficar, que es justo para lo
   *  que se baja.
   */
  async function bajarExcel() {
    if (!data) return;
    setRecalcMsg("");
    const ms = data.months;
    const sum = (get: (d: MonthData) => number) => ms.reduce((t, d) => t + get(d), 0);
    const fila = (
      label: string, get: (d: MonthData) => number,
      formato: FormatoCol, opts?: { total?: boolean; nivel?: number; sinTotal?: boolean },
    ): FilaCuadro => ({
      label, nivel: opts?.nivel, es_total: opts?.total, formato,
      valores: [...ms.map(get), opts?.sinTotal ? null : sum(get)],
    });
    const columnas = [
      { label: tc("metric"), ancho: 26, formato: "texto" as FormatoCol },
      ...MESES.map(m => ({ label: m, ancho: 12 })),
      { label: tc("total"), ancho: 14 },
    ];
    const sub = t("excelSub", {
      escenario: scnLabel(scenarios.find(s => s.id === budId)!),
      corte: weekLabel, anio: String(year),
    });

    // Las tres categorías comparten las mismas métricas: se arman una vez.
    const bloque = (pick: (d: MonthData) => Metrics, conProp: boolean): FilaCuadro[] => [
      fila("Total Revenue", d => pick(d).total_revenue, "usd", { total: true }),
      fila("Rooms Only", d => pick(d).rooms_only, "usd", { total: true }),
      fila(t("roomsAvailable"), d => pick(d).rooms_avail, "num", { total: true }),
      fila(t("roomsOccupied"), d => pick(d).rooms_occ, "num1", { total: true }),
      fila(tc("guests"), d => pick(d).guests, "num1", { total: true }),
      // ADR y Occupancy son RATIOS: sumarlos no significa nada, por eso van sin
      // total. Un promedio de promedios tampoco sería el ADR del período.
      fila("ADR Total", d => pick(d).adr_total, "usd", { sinTotal: true }),
      fila("ADR Only", d => pick(d).adr_only, "usd", { sinTotal: true }),
      fila("Occupancy %", d => pick(d).occ, "pct", { sinTotal: true }),
      ...(conProp
        ? [fila(`＋ ${t("salesOnProperty")}`, d => d.sales_on_property, "usd", { total: true, nivel: 1 })]
        : []),
    ];

    const cuadros: Cuadro[] = [
      { titulo: "Budget", subtitulo: sub, hoja: "Budget", columnas, filas: bloque(d => d.budget, false) },
      { titulo: "On the Books (OTB)", subtitulo: sub, hoja: "On the Books", columnas, filas: bloque(d => d.otb, true) },
      { titulo: t("grupoDiff"), subtitulo: sub, hoja: "Diff", columnas, filas: bloque(d => d.diff, false) },
      {
        titulo: t("excelNetGapTitulo"),
        subtitulo: sub, hoja: "NET GAP", columnas,
        filas: [
          fila("NET GAP", d => d.net_gap, "usd", { total: true }),
          fila(t("netGapNoches"), d => d.diff.rooms_occ, "num1", { total: true }),
          // La fila del movimiento solo si HAY con qué comparar. Un «OTB Δ = 0»
          // se lee como «no se movió nada», cuando la verdad es que ese corte
          // no cubre este año — no es lo mismo, y la celda vacía no existe en
          // una fila que no debería estar.
          ...(otbPrev ? [
            fila(`OTB Δ  ${data.compare_snapshot_date} → ${data.snapshot_date}`,
                 d => d.otb_move ?? 0, "usd", { total: true }),
            fila(t("otbDeltaNoches"), d => d.otb_move_rooms ?? 0, "num1", { total: true }),
          ] : []),
        ],
      },
    ];
    try {
      await bajarCuadros("OnTheBooks", cuadros);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  const recalc = () => { setRecalcMsg(t("recalculando")); setRefreshKey(k => k + 1); };

  // ── Subir XML de Opera — "cuando se pueda", no por calendario semanal ──────
  // La semana la calcula sola de HOY (semanaDeHoy), no se elige a mano: así
  // no hay que acordarse en qué semana calendario se está para subir. Solo
  // TOCA la semana de hoy — el resto del historial (semanas anteriores) queda
  // intacto, porque el import solo borra/reemplaza esa única semana.
  async function handleXml(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (!files.length || !otbId) return;
    setUploadMsg(null); setUploading(true);
    try {
      const wk = semanaDeHoy(SEMANAS)?.n ?? week ?? 1;
      const r = await importOtbXml(otbId, wk, files[0], files[1]);
      // Un XML multi-año NO tiene un «FY revenue»: tiene uno por año. El que
      // se mostraba acá era la suma de todos —$6.315.043 cuando el 2026 solo
      // eran $4.513.865— y el owner lo cazó justamente porque «ninguno de los
      // escenarios tiene ese saldo». No lo tenía ninguno: eran tres años juntos.
      const detalle = r.por_anio.map(a => `${a.year}: $${Math.round(a.revenue).toLocaleString("en-US")} (${a.noches.toLocaleString("en-US")} ${t("nochesUnidad")})`).join(" · ");
      setUploadMsg(t("xmlOk", { corte: fmtCorte(wk), dias: String(r.days), detalle }));
      setRefreshKey(k => k + 1);
    } catch (ex) {
      setUploadMsg(`Error: ${ex instanceof Error ? ex.message : String(ex)}`);
    } finally {
      setUploading(false);
      if (xmlRef.current) xmlRef.current.value = "";
    }
  }

  const sel = "rounded border border-white/15 bg-[#0F1118] px-2 py-1 text-white text-xs";

  return (
    <section className="pag pag-media space-y-4 p-5">
      <IrA esc={budId} />
      <div>
        <h1 className="text-xl font-semibold text-white">{t("titulo")}</h1>
        <p className="text-xs text-white/50">
          {t("subtitulo", { anio: String(data?.year ?? ""), hotel: HOTEL_ID })}{data?.snapshot_date && (
            <> · {t("otbCut")} <b className="text-white/70">{data.snapshot_date}</b></>
          )}. {t("reemplazaExcel")}
          <br />
          <span className="text-amber-300/80">{t.rich("notaGrossOfComps", { b: (c: React.ReactNode) => <b>{c}</b> })}</span>
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-[#161923] px-3 py-2 text-xs">
        {/* UN escenario y fechas libres. Nada de semanas.
            «yo solo quiero comparar un escenario, y todo lo demás viene del
            xml, y no quiero semanas, que esté libre» (owner, 18-ago-2026).
            Antes había cuatro desplegables —Budget, OTB en, from, to— y los
            dos primeros podían apuntar a escenarios distintos, comparando el
            presupuesto de uno contra las reservas de otro sin avisar. */}
        <label className="flex items-center gap-1 text-white/60">{tc("scenario")}
          <select value={budId} onChange={e => setBudId(e.target.value)} className={sel}>
            {scenarios.map(s => <option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1 text-white/60">{t("corteAl")}
          <input type="date" value={fechaDe(week)} max={hoyISO}
                 onChange={e => { const n = corteEn(e.target.value); if (n) setWeek(n); }}
                 className={sel} />
        </label>
        <label className="flex items-center gap-1 text-white/60">{t("compararDesde")}
          <input type="date" value={fechaDe(prevWeek)} max={fechaDe(week) || hoyISO}
                 onChange={e => setPrevWeek(corteEn(e.target.value))}
                 className={sel} />
          {prevWeek > 0 && (
            <button onClick={() => setPrevWeek(0)} title={t("quitarComparacion")}
                    className="px-1 text-white/40 hover:text-white/80">×</button>
          )}
        </label>
        {availYears.length > 1 && (
          <label className="flex items-center gap-1 text-white/60" title={t("anioXmlAyuda")}>{t("anioXml")}
            <select value={year} onChange={e => setYear(Number(e.target.value))} className={sel}>
              {availYears.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
        )}
        {data && (
          <span className="text-white/50">
            {t("corteFinal")} <b className="text-white/80">{data.snapshot_date ?? "—"}</b>
            {data.compare_snapshot_date
              ? <> {t("vsInicial")} <b className="text-white/80">{data.compare_snapshot_date}</b>
                  {moved != null && <> · {t("otbMovio")} <b className={moved < 0 ? "text-red-400" : "text-emerald-400"}>{moved >= 0 ? "+" : ""}${money(moved)}</b></>}</>
              : <span className="text-white/30"> · {t("sinCorteAnterior")}</span>}
          </span>
        )}
        <span className="ml-auto flex items-center gap-2">
          <input ref={xmlRef} type="file" multiple accept=".xml" style={{ display: "none" }} onChange={handleXml} />
          {/* El candado del escenario NO aplica acá: subir el XML no toca
              ninguna cifra del presupuesto. «El escenario es solo una
              referencia comparativa, pero no tiene nada que ver con las
              subidas» (owner). Llegué a apagar este botón en escenarios
              enllavados; era al revés. */}
          <button onClick={() => xmlRef.current?.click()} disabled={uploading || !otbId}
            className="rounded bg-fuchsia-600/80 px-2.5 py-1 text-white hover:bg-fuchsia-600 disabled:opacity-50"
            title={t("xmlOperaAyuda")}>
            {uploading ? t("subiendo") : t("xmlOpera")}
          </button>
          {tab === "8.1" && data && (
            <button onClick={bajarExcel}
              className="rounded border border-emerald-400/40 px-2.5 py-1 text-emerald-300 hover:bg-emerald-400/10"
              title={t("excelAyuda")}>
              {t("excel")}
            </button>
          )}
          {tab === "8.1" && (
            <button onClick={() => window.print()}
              className="rounded bg-white/10 px-2.5 py-1 text-white/80 hover:bg-white/20"
              title={t("imprimirPdfAyuda")}>
              {t("imprimirPdf")}
            </button>
          )}
          <button onClick={recalc}
            className="rounded bg-brand/80 px-2.5 py-1 text-white hover:bg-brand"
            title={t("recalcularAyuda")}>
            {t("recalcular")}
          </button>
          {recalcMsg && <span className={recalcMsg.startsWith("✓") ? "text-emerald-400" : "text-white/50"}>{recalcMsg}</span>}
        </span>
      </div>
      {uploadMsg && (
        <div className={`rounded-lg border px-3 py-2 text-xs ${uploadMsg.startsWith("Error") ? "border-red-500/30 bg-red-500/10 text-red-300" : "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"}`}>
          {uploadMsg}
        </div>
      )}

      <nav className="flex flex-wrap gap-1 border-b border-white/10 pb-2">
        {ALL_SUBTABS.map((s) => (
          <button key={s.id} onClick={() => setTab(s.id)}
            className={`rounded px-2.5 py-1 text-[11px] ${tab === s.id ? "bg-brand text-white" : "bg-[#1E2130] text-white/60 hover:text-white"}`}>
            {s.label}
          </button>
        ))}
      </nav>

      {err && (
        <div className="rounded border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
          {t("sinDatosOtb", { err })}
        </div>
      )}
      {!err && !data && (
        cortesListos && !loadedWeeks.length
          ? <div className="rounded-lg border border-amber-400/30 bg-amber-400/5 px-4 py-3 text-xs text-amber-200/90">
              {t.rich("vacioSinCortes", { b: (c: React.ReactNode) => <b>{c}</b> })}
            </div>
          : <div className="text-xs text-white/50">{tc("loading")}</div>
      )}

      {tab === "8.1" && data && <ONTBReport data={data} />}
      {tab === "8.2" && data && <Dashboard data={data} curPct={curPct} />}
      {tab === "8.3" && <Heatmap heat={heat} bud={bud} meses={data?.months ?? []} />}
      {tab === "8.4" && <Pacing pacing={pacing} />}
      {tab === "8.5" && data && <RevenueTrend data={data} />}
      {tab === "8.5.1" && <Analisis2027 scenarios={scenarios} budId={budId} otbId={otbId} week={week} />}
      {tab === "8.6" && data && <OccupancyTrend data={data} />}
      {tab === "8.7" && data && <VariancePie data={data} />}
    </section>
  );
}

/* ---------- 8.1 ONTB Report ---------- */
function ONTBReport({ data }: { data: Report }) {
  const t = useTranslations("otb");
  const tc = useTranslations("common");
  const MESES = useMeses();
  const ROTULO_TABLA = rotuloTabla(t);
  const { collapsed, toggle } = useQuarters();
  /** Por cuál de las tres vistas se despliega el reporte.
   *
   *  «Meter en 8.1 que se despliegue por Total Revenue y Only Rooms, y quiero
   *  que pueda hacer un on the books de solo habitaciones vendidas» (owner,
   *  18-ago-2026). Arranca en Full Revenue, que es lo que mostraba antes:
   *  nadie pierde la vista que ya tenía. */
  const [vista, setVista] = useState<VistaTabla>("todo");
  const cols = buildCols(data.months, collapsed, MESES);
  const all = data.months;
  const sum = (get: (d: MonthData) => number) => qsum(all, get);
  const qbg = "bg-[#242838]";
  const move = data.otb_move_total;
  const hasWoW = move != null && data.compare_snapshot_date != null;

  const Row = (
    label: string,
    get: (d: MonthData) => number,
    fmt: (v: number) => string,
    opts?: { total?: boolean; indent?: boolean; money?: boolean; qv?: (ms: MonthData[]) => number },
  ) => (
    <tr className="border-t border-white/5">
      <td className={`${tdL} sticky left-0 z-10 bg-[#0f1118] ${opts?.indent ? "pl-6 text-white/60" : ""}`}>{label}</td>
      {cols.map((c, i) => {
        const v = c.kind === "m" ? get(c.month) : (opts?.qv ? opts.qv(c.months) : qsum(c.months, get));
        return (
          <td key={i} className={`px-2 py-1 text-right ${c.kind === "q" ? `${qbg} font-medium` : ""} ${opts?.money ? neg(v) : ""}`}>{fmt(v)}</td>
        );
      })}
      <td className={`px-2 py-1 text-right font-medium border-l border-white/10 ${opts?.total ? neg(sum(get)) : "text-white/30"}`}>
        {opts?.total ? fmt(sum(get)) : "—"}
      </td>
    </tr>
  );

  const groupHead = (label: string, cls: string) => (
    <tr className="bg-[#161923]">
      <td className={`sticky left-0 z-10 bg-[#161923] px-3 py-1.5 text-left text-[11px] font-bold uppercase tracking-wide ${cls}`} colSpan={cols.length + 2}>{label}</td>
    </tr>
  );

  /** Las filas de noches (Rooms Available/Occupied, Guests, Occupancy) se ven
   *  SIEMPRE: son las mismas en las tres vistas y son el esqueleto del reporte.
   *  Lo que el conmutador prende y apaga es la PLATA. */
  const verPlata = vista !== "noches";
  /** Los totales de la derecha también cambian de unidad con la vista. */
  const gapTotal = verPlata ? data.net_gap_total
                            : data.months.reduce((a, d) => a + d.diff.rooms_occ, 0);
  const moveVista = verPlata ? (move ?? 0)
                             : data.months.reduce((a, d) => a + (d.otb_move_rooms ?? 0), 0);

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <div className="flex items-center gap-1">
          {VISTAS_TABLA.map((v) => (
            <button key={v} onClick={() => setVista(v)}
              className={`rounded px-2.5 py-1 text-[11px] ${vista === v ? "bg-brand text-white" : "bg-[#1E2130] text-white/60 hover:text-white"}`}>
              {ROTULO_TABLA[v]}
            </button>
          ))}
        </div>
        <QuarterBar collapsed={collapsed} toggle={toggle} />
      </div>
      <div className="overflow-auto rounded-lg border border-white/10 max-h-[72vh]">
        <table className="w-full text-xs">
          <thead className="bg-[#1E2130]">
            <tr>
              <th className={`${thl} sticky left-0 top-0 z-30 bg-[#1E2130]`}>{tc("metric")}</th>
              {cols.map((c, i) => (
                <th key={i} className={`${th} sticky top-0 z-20 ${c.kind === "q" ? `${qbg} text-white/80` : "bg-[#1E2130]"}`}>{c.label}</th>
              ))}
              <th className={`${th} sticky top-0 z-20 bg-[#1E2130] border-l border-white/10`}>{tc("total")}</th>
            </tr>
          </thead>
          <tbody>
            {groupHead("Budget", "text-sky-300")}
            {verPlata && vista !== "rooms" &&
              Row("Total Revenue", (d) => d.budget.total_revenue, (v) => `$${money(v)}`, { total: true, money: true })}
            {verPlata && vista !== "total" &&
              Row("Rooms Only", (d) => d.budget.rooms_only, (v) => `$${money(v)}`, { total: true, money: true })}
            {Row(t("roomsAvailable"), (d) => d.budget.rooms_avail, (v) => dec(v), { total: true })}
            {Row(t("roomsOccupied"), (d) => d.budget.rooms_occ, (v) => dec(v), { total: true })}
            {Row(tc("guests"), (d) => d.budget.guests, (v) => dec(v), { total: true })}
            {verPlata && vista !== "rooms" &&
              Row("ADR Total", (d) => d.budget.adr_total, (v) => `$${money(v)}`, { money: true, qv: (ms) => qAdr(ms, "budget", "total") })}
            {verPlata && vista !== "total" &&
              Row("ADR Only", (d) => d.budget.adr_only, (v) => `$${money(v)}`, { money: true, qv: (ms) => qAdr(ms, "budget", "only") })}
            {Row("Occupancy %", (d) => d.budget.occ, (v) => pct(v), { qv: (ms) => qOcc(ms, "budget") })}

            {groupHead("On The Books (OTB)", "text-emerald-300")}
            {verPlata && vista !== "rooms" &&
              Row("Total Revenue", (d) => d.otb.total_revenue, (v) => `$${money(v)}`, { total: true, money: true })}
            {verPlata && vista !== "total" &&
              Row("Rooms Only", (d) => d.otb.rooms_only, (v) => `$${money(v)}`, { total: true, money: true })}
            {Row(t("roomsOccupied"), (d) => d.otb.rooms_occ, (v) => dec(v), { total: true })}
            {Row(tc("guests"), (d) => d.otb.guests, (v) => dec(v), { total: true })}
            {verPlata && vista !== "rooms" &&
              Row("ADR Total", (d) => d.otb.adr_total, (v) => `$${money(v)}`, { money: true, qv: (ms) => qAdr(ms, "otb", "total") })}
            {verPlata && vista !== "total" &&
              Row("ADR Only", (d) => d.otb.adr_only, (v) => `$${money(v)}`, { money: true, qv: (ms) => qAdr(ms, "otb", "only") })}
            {Row("Occupancy %", (d) => d.otb.occ, (v) => pct(v), { qv: (ms) => qOcc(ms, "otb") })}
            {verPlata &&
              Row(t("salesOnProperty"), (d) => d.sales_on_property, (v) => `$${money(v)}`, { total: true, indent: true, money: true })}

            {groupHead(t("grupoDiff"), "text-amber-300")}
            {verPlata && vista !== "rooms" &&
              Row("Total Revenue", (d) => d.diff.total_revenue, (v) => `$${money(v)}`, { total: true, money: true })}
            {verPlata && vista !== "total" &&
              Row("Rooms Only", (d) => d.diff.rooms_only, (v) => `$${money(v)}`, { total: true, money: true })}
            {Row(t("roomsOccupied"), (d) => d.diff.rooms_occ, (v) => dec(v), { total: true, money: true })}
            {Row(tc("guests"), (d) => d.diff.guests, (v) => dec(v), { total: true, money: true })}
            {verPlata && vista !== "rooms" &&
              Row("ADR Total", (d) => d.diff.adr_total, (v) => `$${money(v)}`, { money: true, qv: (ms) => qAdr(ms, "otb", "total") - qAdr(ms, "budget", "total") })}
            {verPlata && vista !== "total" &&
              Row("ADR Only", (d) => d.diff.adr_only, (v) => `$${money(v)}`, { money: true, qv: (ms) => qAdr(ms, "otb", "only") - qAdr(ms, "budget", "only") })}
            {Row("Occupancy %", (d) => d.diff.occ, (v) => pct(v), { money: true, qv: (ms) => qOcc(ms, "otb") - qOcc(ms, "budget") })}

            {/* En la vista de noches el NET GAP es de NOCHES, no de dólares:
                se colaban pesos en un reporte que no habla de plata. */}
            <tr className="border-t-2 border-white/20 bg-emerald-900/20 font-bold">
              <td className="sticky left-0 z-10 bg-[#0f1a15] px-3 py-2 text-left text-emerald-200">
                {verPlata ? "NET GAP" : t("netGapNoches")}
              </td>
              {cols.map((c, i) => {
                const get = (d: MonthData) => (verPlata ? d.net_gap : d.diff.rooms_occ);
                const v = c.kind === "m" ? get(c.month) : qsum(c.months, get);
                return <td key={i} className={`px-2 py-2 text-right ${c.kind === "q" ? qbg : ""} ${neg(v)}`}>{verPlata ? `$${money(v)}` : dec(v)}</td>;
              })}
              <td className={`px-2 py-2 text-right border-l border-white/10 ${neg(gapTotal)}`}>{verPlata ? `$${money(gapTotal)}` : dec(gapTotal)}</td>
            </tr>

            {groupHead(t("grupoMovimiento"), "text-fuchsia-300")}
            {hasWoW ? (
              <tr className="border-t border-white/5 font-medium">
                <td className={`${tdL} sticky left-0 z-10 bg-[#0f1118]`}>
                  OTB Δ <span className="text-white/40">({data.compare_snapshot_date} → {data.snapshot_date})</span>
                </td>
                {cols.map((c, i) => {
                  const get = (d: MonthData) => (verPlata ? (d.otb_move ?? 0) : (d.otb_move_rooms ?? 0));
                  const v = c.kind === "m" ? get(c.month) : qsum(c.months, get);
                  return (
                    <td key={i} className={`px-2 py-1 text-right ${c.kind === "q" ? qbg : ""} ${v < 0 ? "text-red-400" : v > 0 ? "text-emerald-400" : "text-white/40"}`}>
                      {v > 0 ? "+" : ""}{verPlata ? (v === 0 ? "$0" : `$${money(v)}`) : dec(v)}
                    </td>
                  );
                })}
                <td className={`px-2 py-1 text-right border-l border-white/10 ${moveVista < 0 ? "text-red-400" : moveVista > 0 ? "text-emerald-400" : "text-white/40"}`}>
                  {moveVista > 0 ? "+" : ""}{verPlata ? `$${money(moveVista)}` : dec(moveVista)}
                </td>
              </tr>
            ) : (
              <tr className="border-t border-white/5">
                <td className="px-3 py-2 text-left text-amber-300/80 text-[11px]" colSpan={cols.length + 2}>
                  {t("sinCorteAnteriorTabla")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* El cartel habla en la unidad de la vista. En «Habitaciones vendidas»
          decía «creció $143.297», que es plata metida en un reporte de noches. */}
      {hasWoW && (
        <div className={`rounded-lg border px-3 py-2 text-sm font-semibold ${moveVista > 0 ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : moveVista < 0 ? "border-red-500/30 bg-red-500/10 text-red-300" : "border-white/15 bg-white/5 text-white/70"}`}>
          {t(moveVista > 0 ? "bannerSube" : moveVista < 0 ? "bannerBaja" : "bannerIgual", {
            monto: `${moveVista >= 0 ? "+" : ""}${verPlata ? `$${money(moveVista)}` : `${dec(moveVista)} ${t("habitacionesUnidad")}`}`,
            desde: data.compare_snapshot_date ?? "", hasta: data.snapshot_date ?? "",
          })}
        </div>
      )}
    </div>
  );
}

/* ---------- 8.2 Dashboard ---------- */
function Dashboard({ data, curPct }: { data: Report; curPct: number }) {
  const t = useTranslations("otb");
  const tc = useTranslations("common");
  const MESES = useMeses();
  const { collapsed, toggle } = useQuarters();
  const cols = buildCols(data.months, collapsed, MESES);
  const qbg = "bg-[#242838]";
  const otbRev = (d: MonthData) => d.otb.total_revenue;
  const onProp = (d: MonthData) => d.sales_on_property;
  const forecast = (d: MonthData) => d.otb.total_revenue + d.sales_on_property;
  const budget = (d: MonthData) => d.budget.total_revenue;
  const sumB = qsum(data.months, budget);
  const sumOTB = qsum(data.months, otbRev);
  const sumOnProp = qsum(data.months, onProp);
  const sumF = qsum(data.months, forecast);
  const sumG = data.net_gap_total;
  const rBudget = (d: MonthData) => d.budget.rooms_only;
  const rForecast = (d: MonthData) => d.otb.rooms_only;
  const rGap = (d: MonthData) => d.otb.rooms_only - d.budget.rooms_only;
  const sumRB = qsum(data.months, rBudget);
  const sumRF = qsum(data.months, rForecast);
  const sumRG = sumRF - sumRB;

  const Row = (label: string, cls: string, get: (d: MonthData) => number, total: number, strong = false) => (
    <tr className={strong ? "border-t-2 border-white/20 bg-emerald-900/20 font-bold" : "border-t border-white/5"}>
      <td className={strong ? "px-3 py-2 text-left text-emerald-200" : `${tdL} ${cls}`}>{label}</td>
      {cols.map((c, i) => {
        const v = c.kind === "m" ? get(c.month) : qsum(c.months, get);
        return <td key={i} className={`px-2 py-1.5 text-right ${c.kind === "q" ? `${qbg} font-medium` : ""} ${neg(v)}`}>${money(v)}</td>;
      })}
      <td className={`px-2 py-1.5 text-right font-medium border-l border-white/10 ${neg(total)}`}>${money(total)}</td>
    </tr>
  );

  const groupHead = (label: string) => (
    <tr className="bg-[#161923]">
      <td className="px-3 py-1.5 text-left text-[11px] font-bold uppercase tracking-wide text-white/60" colSpan={cols.length + 2}>{label}</td>
    </tr>
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card label={t("cardBudgetAnio")} value={`$${money(sumB)}`} tone="sky" />
        <Card label={t("cardForecast")} value={`$${money(sumF)}`} tone="emerald"
              sub={t("cardForecastSub", { otb: `$${money(sumOTB)}`, prop: `$${money(sumOnProp)}` })} />
        <Card label={t("cardNetGapAnio")} value={`$${money(sumG)}`} tone={sumG < 0 ? "red" : "emerald"} />
        <Card label={t("cardRoomsOnlyGap")} value={`$${money(sumRG)}`} tone={sumRG < 0 ? "red" : "emerald"} />
      </div>
      <QuarterBar collapsed={collapsed} toggle={toggle} />
      <div className="overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full text-xs">
          <thead className="bg-[#1E2130]">
            <tr>
              <th className={thl}>{tc("metric")}</th>
              {cols.map((c, i) => <th key={i} className={`${th} ${c.kind === "q" ? `${qbg} text-white/80` : ""}`}>{c.label}</th>)}
              <th className={`${th} border-l border-white/10`}>{tc("total")}</th>
            </tr>
          </thead>
          <tbody>
            {groupHead("Total Revenue")}
            {Row("Revenue Budget", "text-sky-300", budget, sumB)}
            {Row(t("filaOtbRevenue"), "text-white/45", otbRev, sumOTB)}
            {Row(t("filaOnProperty", { pct: (curPct * 100).toFixed(1) }), "text-white/45", onProp, sumOnProp)}
            {Row("＝ Revenue Forecast", "text-emerald-300 font-medium", forecast, sumF)}
            {Row("NET GAP", "", (d) => d.net_gap, sumG, true)}

            {groupHead("Rooms Only")}
            {Row("Rooms Only Budget", "text-sky-300", rBudget, sumRB)}
            {Row("Rooms Only Forecast (OTB)", "text-emerald-300", rForecast, sumRF)}
            {Row(t("filaRoomsOnlyGap"), "", rGap, sumRG, true)}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-white/40">
        {t.rich("dashboardNota", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>
    </div>
  );
}

function Card({ label, value, tone, sub }: { label: string; value: string; tone: "sky" | "emerald" | "red"; sub?: string }) {
  const c = { sky: "text-sky-300", emerald: "text-emerald-300", red: "text-red-400" }[tone];
  return (
    <div className="rounded-lg border border-white/10 bg-[#161923] p-3">
      <div className="text-[11px] uppercase tracking-wide text-white/50">{label}</div>
      <div className={`mt-1 text-lg font-bold ${c}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[10px] text-white/40">{sub}</div>}
    </div>
  );
}

/* ---------- 8.3 Daily Heatmap ---------- */
const RISK_BG: Record<string, string> = {
  CRITICAL: "bg-red-900 text-red-100",
  HIGH: "bg-red-600/80 text-white",
  MID: "bg-amber-500/80 text-black",
  OK: "bg-emerald-600/80 text-white",
};
function riskFlag(occ: number): string {
  if (occ < 0.15) return "CRITICAL";
  if (occ < 0.30) return "HIGH";
  if (occ < 0.45) return "MID";
  return "OK";
}
function action(risk: string): string {
  return ({ CRITICAL: "PUSH", HIGH: "RATE", MID: "WATCH" } as Record<string, string>)[risk] ?? "HOLD";
}

/**
 * ⚠️ `meses` entra por las columnas de Pax y ADR del lado izquierdo.
 *
 * Estaban escritas literalmente como «—»: nunca traían número, mientras la nota
 * al pie prometía «Noches / Pax / ADR / Occ%». El dato DIARIO del heatmap solo
 * lleva `rooms_sold` y `occ_pct`, así que no salía de ahí — pero esas columnas
 * son del MES, y el OTB mensual sí tiene pax y ADR. Es el mismo dato que la
 * pestaña 8.1 ya muestra.
 *
 * Se usa `adr_only` y no `adr_total` a propósito: la columna de Budget de al
 * lado se calcula como `REV_ROOMS / noches ocupadas`, que es ADR de habitación
 * sola. Poner el ADR total de un lado y el de habitación del otro habría hecho
 * que la comparación se leyera como una caída de tarifa que no existe.
 */
function Heatmap({ heat, bud, meses }: { heat: DailyOcc | null; bud: PLMonthly | null; meses: MonthData[] }) {
  const t = useTranslations("otb");
  const tc = useTranslations("common");
  const MESES = useMeses();
  if (!heat) return <div className="text-xs text-white/50">{tc("loading")}</div>;
  if (!heat.has_data) return <div className="text-xs text-amber-200">{t("sinDatosDiarios")}</div>;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-[11px] text-white/60">
        <span>{t("heatIntro")} <b className="text-white/80">W{heat.week}</b>. {t("heatOccDef")}</span>
        <span className="flex items-center gap-2">
          {["OK", "MID", "HIGH", "CRITICAL"].map((k) => (
            <span key={k} className={`rounded px-1.5 py-0.5 ${RISK_BG[k]}`}>{k}</span>
          ))}
        </span>
        <span className="text-white/40">{t("heatAccion")}</span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-white/10">
        <table className="text-[10px]">
          <thead className="bg-[#1E2130]">
            <tr>
              <th rowSpan={2} className="sticky left-0 bg-[#1E2130] px-2 py-1 text-left text-white/60">{tc("month")}</th>
              {Array.from({ length: 31 }, (_, i) => <th rowSpan={2} key={i} className="w-7 px-0.5 py-1 text-center text-white/40 align-bottom">{i + 1}</th>)}
              <th colSpan={4} className="border-l border-white/15 px-2 py-1 text-center text-[10px] font-bold uppercase tracking-wide text-emerald-300">Forecast (OTB)</th>
              <th colSpan={4} className="border-l border-white/15 px-2 py-1 text-center text-[10px] font-bold uppercase tracking-wide text-sky-300">Budget</th>
              <th rowSpan={2} className="border-l border-white/15 px-2 py-1 text-right align-bottom text-white/60">{t("occVar")}</th>
            </tr>
            <tr>
              <th className="border-l border-white/15 px-2 py-0.5 text-right text-emerald-300/70">{t("nochesCol")}</th>
              <th className="px-2 py-0.5 text-right text-emerald-300/70">Pax</th>
              <th className="px-2 py-0.5 text-right text-emerald-300/70">ADR</th>
              <th className="px-2 py-0.5 text-right text-emerald-300/70">Occ%</th>
              <th className="border-l border-white/15 px-2 py-0.5 text-right text-sky-300/70">{t("nochesCol")}</th>
              <th className="px-2 py-0.5 text-right text-sky-300/70">Pax</th>
              <th className="px-2 py-0.5 text-right text-sky-300/70">ADR</th>
              <th className="px-2 py-0.5 text-right text-sky-300/70">Occ%</th>
            </tr>
          </thead>
          <tbody>
            {heat.months.map((mo) => {
              const bm = bud?.months.find(x => x.month === mo.month);
              const bAvail = bm?.kpis.rooms_available ?? 0, bOcc = bm?.kpis.rooms_occupied ?? 0;
              const bGuests = bm?.kpis.guests ?? 0, bRoomsRev = lineAmt(bm, "REV_ROOMS");
              const budgetOcc = bAvail ? bOcc / bAvail : 0;
              const budgetAdr = bOcc ? bRoomsRev / bOcc : 0;
              const noches = mo.days.reduce((s, d) => s + (d?.rooms_sold ?? 0), 0);
              const om = meses.find(x => x.month === mo.month)?.otb;
              const variance = mo.avg_occ - budgetOcc;
              return (
                <tr key={mo.month} className="border-t border-white/5">
                  <td className="sticky left-0 bg-[#0F1118] px-2 py-1 text-left text-white/70 whitespace-nowrap">{MESES[mo.month - 1]}</td>
                  {Array.from({ length: 31 }, (_, i) => {
                    const cell = mo.days[i];
                    if (!cell) return <td key={i} className="w-7" />;
                    const risk = riskFlag(cell.occ_pct);
                    return (
                      <td key={i} className={`w-7 px-0.5 py-1 text-center ${RISK_BG[risk]}`}
                        title={`${MESES[mo.month - 1]} ${cell.day}: ${cell.rooms_sold}/${heat.inventory} · ${risk} · ${action(risk)}`}>
                        {Math.round(cell.occ_pct * 100)}
                      </td>
                    );
                  })}
                  <td className="border-l border-white/15 px-2 py-1 text-right text-white/80">{dec(noches)}</td>
                  <td className="px-2 py-1 text-right text-white/80">{om ? dec(om.guests) : "—"}</td>
                  <td className="px-2 py-1 text-right text-white/80">{om ? `$${money(om.adr_only)}` : "—"}</td>
                  <td className="px-2 py-1 text-right font-medium text-emerald-300">{pct(mo.avg_occ)}</td>
                  <td className="border-l border-white/15 px-2 py-1 text-right text-white/60">{dec(bOcc)}</td>
                  <td className="px-2 py-1 text-right text-white/60">{dec(bGuests)}</td>
                  <td className="px-2 py-1 text-right text-white/60">${money(budgetAdr)}</td>
                  <td className="px-2 py-1 text-right font-medium text-sky-300">{pct(budgetOcc)}</td>
                  <td className={`border-l border-white/15 px-2 py-1 text-right font-medium ${variance < 0 ? "text-red-400" : "text-emerald-400"}`}>
                    {variance >= 0 ? "+" : ""}{pct(variance)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-white/40">{t("heatNota1", { noches: t("nochesCol") })} <span className="text-emerald-300">Forecast (OTB)</span> vs <span className="text-sky-300">Budget</span>{t("heatNota2")}</p>
    </div>
  );
}

/* ---------- 8.4 Pacing ---------- */
function Pacing({ pacing }: { pacing: OtbPacing | null }) {
  const t = useTranslations("otb");
  const tc = useTranslations("common");
  if (!pacing) return <div className="text-xs text-white/50">{tc("loading")}</div>;
  const snaps = pacing.snapshots;
  const max = Math.max(1, ...snaps.map((s) => s.total_revenue));

  return (
    <div className="space-y-3">
      <p className="text-xs text-white/60">
        {t("pacingIntro")}
        {snaps.length < 2 && <span className="text-amber-300"> {t("pacingAcumulando", { n: snaps.length })}</span>}
      </p>
      <div className="space-y-1.5">
        {snaps.map((s) => (
          <div key={s.week} className="flex items-center gap-3">
            <span className="w-24 text-right text-xs text-white/70">W{s.week}</span>
            <div className="relative h-6 flex-1 rounded bg-[#161923]">
              <div className="h-6 rounded bg-emerald-600/70" style={{ width: `${(s.total_revenue / max) * 100}%` }} />
              <span className="absolute inset-y-0 left-2 flex items-center text-[11px] text-white">${money(s.total_revenue)}</span>
            </div>
            <span className={`w-28 text-right text-xs ${s.delta_vs_prev === null ? "text-white/30" : neg(s.delta_vs_prev)}`}>
              {s.delta_vs_prev === null ? "—" : `${s.delta_vs_prev >= 0 ? "+" : ""}$${money(s.delta_vs_prev)}`}
            </span>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-white/40">{t("pacingNota")}</p>
    </div>
  );
}

/* ---------- 8.5 Revenue Trend (OTB Forecast vs Budget + 2-per moving avg) ---------- */
function RevenueTrend({ data }: { data: Report }) {
  const t = useTranslations("otb");
  const MESES = useMeses();
  const m = data.months;
  const curMonth = 1;
  const budget = m.map((d) => d.budget.total_revenue);
  const forecast = m.map((d) => d.otb.total_revenue);
  const ma = forecast.map((v, i) => (i === 0 ? null : (v + forecast[i - 1]) / 2));

  const W = 1120, H = 470, L = 70, R = 20, T = 40, B = 70;
  const plotW = W - L - R, plotH = H - T - B;
  const rawMax = Math.max(1, ...budget, ...forecast);
  const yMax = Math.ceil(rawMax / 100000) * 100000;
  const band = plotW / 12;
  const barW = band * 0.30;
  const y = (v: number) => T + plotH - (v / yMax) * plotH;
  const cx = (i: number) => L + i * band + band / 2;
  const kfmt = (v: number) => `$${Math.round(v / 1000).toLocaleString()}k`;

  const gridY = Array.from({ length: yMax / 100000 + 1 }, (_, i) => i * 100000);
  const maPts = ma.map((v, i) => (v === null ? null : `${cx(i)},${y(v)}`)).filter(Boolean).join(" ");

  return (
    <div className="space-y-2 max-w-[1500px] mx-auto">
      <div className="rounded-lg border border-white/10 bg-[#0F1118] p-3">
        <div className="mb-1 text-center text-sm font-semibold text-white/90">{t("trendTitulo", { anio: String(data.year) })}</div>
        <div className="overflow-x-auto">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[760px]" role="img">
            {gridY.map((g) => (
              <g key={g}>
                <line x1={L} y1={y(g)} x2={W - R} y2={y(g)} stroke="var(--border-subtle)" />
                <text x={L - 8} y={y(g) + 3} textAnchor="end" fontSize="10" fill="var(--text-secondary)">${(g / 1000).toLocaleString()}k</text>
              </g>
            ))}
            {m.map((d, i) => {
              const bx = cx(i) - barW - 2;
              const fx = cx(i) + 2;
              return (
                <g key={i}>
                  <rect x={bx} y={y(budget[i])} width={barW} height={T + plotH - y(budget[i])} fill="var(--accent-budget)">
                    <title>{`${MESES[i]} Budget: $${money(budget[i])}`}</title>
                  </rect>
                  <rect x={fx} y={y(forecast[i])} width={barW} height={T + plotH - y(forecast[i])} fill="#ED7D31">
                    <title>{`${MESES[i]} Forecast (OTB): $${money(forecast[i])}`}</title>
                  </rect>
                  <text x={bx + barW / 2} y={y(budget[i]) - 4} textAnchor="middle" fontSize="9" fill="var(--text-primary)">{kfmt(budget[i])}</text>
                  <text x={fx + barW / 2} y={y(forecast[i]) - 4} textAnchor="middle" fontSize="9" fill="var(--text-primary)">{kfmt(forecast[i])}</text>
                  {budget[i] - forecast[i] > 15000 && (i + 1) >= curMonth && (
                    <text x={cx(i)} y={T + plotH + 30} textAnchor="middle" fontSize="9" fontWeight="bold" fill="#f87171">GAP {kfmt(budget[i] - forecast[i])}</text>
                  )}
                  <text x={cx(i)} y={T + plotH + 15} textAnchor="middle" fontSize="11" fill="var(--text-secondary)">{MESES[i]}</text>
                </g>
              );
            })}
            <polyline points={maPts} fill="none" stroke="#ff0000" strokeWidth="2.5" strokeDasharray="8 4" />
            {ma.map((v, i) => v === null ? null : <circle key={i} cx={cx(i)} cy={y(v)} r="2.5" fill="#ff0000" />)}
          </svg>
        </div>
        <div className="mt-1 flex flex-wrap items-center justify-center gap-4 text-[11px] text-white/70">
          <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-sm" style={{ background: "var(--accent-budget)" }} /> Revenue Budget</span>
          <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-sm" style={{ background: "#ED7D31" }} /> Revenue Forecast (OTB)</span>
          <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-5" style={{ background: "#ff0000" }} /> {t("mediaMovil2p")}</span>
        </div>
      </div>
      <p className="text-[11px] text-white/40">
        {t("trendNota", { corte: data.snapshot_date ?? "" })}
      </p>
    </div>
  );
}

/* ---------- 8.5.1 Análisis 2027 (OTB 2027 vs 2026, mismo snapshot) ---------- */
function Analisis2027({ scenarios, budId, otbId, week }: {
  scenarios: Scenario[]; budId: string; otbId: string; week: number;
}) {
  // ⚠️ El presupuesto es EL DE ARRIBA. No hay selector propio acá.
  //
  // Lo tenía, y elegía solo «el primer BUDGET que diga working» — que en la
  // lista es el **Budget 2035**. Resultado: el sub-tab abría comparando contra
  // 2035 aunque arriba estuviera el Budget 2026 · Final, y no había nada que
  // avisara. «Engancha esto en Budget 2026 Final, siempre sale Budget 2035»
  // (owner, 18-ago-2026). Es la misma regla de toda esta pantalla: un solo
  // escenario, el de arriba.
  const t = useTranslations("otb");
  const tc = useTranslations("common");
  const MESES = useMeses();
  const ROTULO_VISTA = rotuloVista(t);
  const [yearA, setYearA] = useState(0);   // año 1 (ej. 2026)
  const [yearB, setYearB] = useState(0);   // año 2 (ej. 2027)
  const [years, setYears] = useState<number[]>([]);

  // Años que trae el escenario OTB de arriba, EN esta semana.
  useEffect(() => {
    if (!otbId || !week) { setYears([]); return; }
    let live = true;
    getOtbYears(otbId, week).then(r => {
      if (!live) return;
      setYears(r.years);
      if (r.years.length) {
        setYearA(a => r.years.includes(a) ? a : r.years[0]);
        setYearB(b => r.years.includes(b) ? b : (r.years[1] ?? r.years[0]));
      }
    }).catch(() => setYears([]));
    return () => { live = false; };
  }, [otbId, week]);

  const y27 = yearB || yearA || new Date().getFullYear();
  const y26 = yearA || y27 - 1;

  const [y27r, setY27r] = useState<Report | null>(null);
  const [y26r, setY26r] = useState<Report | null>(null);
  const [err, setErr] = useState("");
  /** Tres vistas, no dos: además de la plata, las HABITACIONES VENDIDAS.
   *  «Quiero que pueda hacer un on the books de solo habitaciones vendidas»
   *  (owner, 18-ago-2026). En noches no hay ADR ni tarifa de por medio: es
   *  cuánto se vendió, sin que el precio lo maquille. */
  const [metric, setMetric] = useState<Vista>("total");
  const { collapsed, toggle } = useQuarters();

  useEffect(() => {
    if (!budId || !otbId || !week) return;
    let live = true; setErr(""); setY27r(null); setY26r(null);
    (async () => {
      try {
        const bud = await getPLMonthly(budId);
        const [otbB_, otbA_] = await Promise.all([
          yearB ? getOnTheBooks(otbId, week, yearB) : Promise.resolve(null),
          yearA ? getOnTheBooks(otbId, week, yearA) : Promise.resolve(null),
        ]);
        if (!live) return;
        // pct 0 acá: el 8.5.1 compara OTB puro entre dos años, sin on-property.
        if (otbB_) setY27r(buildReport(bud, otbB_, null, 0, 0, "", null, ""));
        if (otbA_) setY26r(buildReport(bud, otbA_, null, 0, 0, "", null, ""));
      } catch (e) { if (live) setErr(e instanceof Error ? e.message : tc("error")); }
    })();
    return () => { live = false; };
  }, [budId, otbId, week, yearA, yearB]);

  const sel = "rounded border border-white/15 bg-[#0F1118] px-2 py-1 text-white text-xs";
  const picker = (
    <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-[#161923] px-3 py-2 text-xs">
      <label className="flex items-center gap-1 text-white/60">{t("anio1")}
        <select value={yearA} onChange={e => setYearA(Number(e.target.value))} className={sel}>
          {years.map(y => <option key={y} value={y}>{y}</option>)}
        </select>
      </label>
      <label className="flex items-center gap-1 text-white/60">{t("anio2")}
        <select value={yearB} onChange={e => setYearB(Number(e.target.value))} className={sel}>
          {years.map(y => <option key={y} value={y}>{y}</option>)}
        </select>
      </label>
    </div>
  );

  const budScn = scenarios.find(s => s.id === budId);
  const budLabel = budScn ? scnLabel(budScn) : `Budget ${y27}`;

  if (err) return <>{picker}<div className="text-xs text-amber-200">({err})</div></>;
  if (!years.length) return <>{picker}<div className="text-xs text-amber-200">{t("sinAniosCargados")}</div></>;
  if (!y27r && !y26r) return <>{picker}<div className="text-xs text-white/50">{tc("loading")}</div></>;
  if (years.length < 2) return <>{picker}<div className="text-xs text-amber-200">{t.rich("unSoloAnio", { anio: String(years[0]), b: (c: React.ReactNode) => <b>{c}</b> })}</div></>;

  const field = CAMPO_VISTA[metric];
  const enNoches = metric === "noches";
  const budget27 = MONTHS.map((_, i) => y27r?.months[i]?.budget[field] ?? 0);
  const rev26 = MONTHS.map((_, i) => y26r?.months[i]?.otb[field] ?? 0);
  const rev27 = MONTHS.map((_, i) => y27r?.months[i]?.otb[field] ?? 0);
  const has27 = rev27.some((v) => v > 0);
  const totalB27 = budget27.reduce((a, b) => a + b, 0);
  const total26 = rev26.reduce((a, b) => a + b, 0);
  const total27 = rev27.reduce((a, b) => a + b, 0);
  const gapBudget = total27 - totalB27;

  /** Bajar el 8.5.1 a Excel: UNA HOJA POR VISTA.
   *
   *  «Necesito poder bajar esto a Excel por tab: Full Revenue, Rooms Revenue,
   *  Habitaciones vendidas» (owner, 18-ago-2026).
   *
   *  Tres hojas, cada una con las mismas tres series y los doce meses más el
   *  Full Year. Se exportan las TRES siempre, no solo la que esté puesta en
   *  pantalla: el conmutador es para mirar, el archivo es para analizar — y
   *  bajarlo tres veces para tener las tres sería el mismo trabajo hecho a
   *  mano.
   */
  async function bajarExcel() {
    if (!y27r && !y26r) return;
    const columnas = [
      { label: t("serie"), ancho: 28, formato: "texto" as FormatoCol },
      ...MESES.map(m => ({ label: m, ancho: 12 })),
      { label: tc("fullYear"), ancho: 14 },
    ];
    const cuadros: Cuadro[] = VISTAS.map(v => {
      const f = CAMPO_VISTA[v];
      // En noches no hay plata: el formato cambia con la vista, no solo el número.
      const fmt: FormatoCol = v === "noches" ? "num1" : "usd";
      const serie = (label: string, get: (i: number) => number): FilaCuadro => {
        const vals = MONTHS.map((_m, i) => get(i));
        return { label, formato: fmt, valores: [...vals, vals.reduce((a, b) => a + b, 0)] };
      };
      const bud = (i: number) => y27r?.months[i]?.budget[f] ?? 0;
      const a26 = (i: number) => y26r?.months[i]?.otb[f] ?? 0;
      const a27 = (i: number) => y27r?.months[i]?.otb[f] ?? 0;
      return {
        titulo: `${t("analisis")} ${y26}/${y27} — ${ROTULO_VISTA[v]}`,
        subtitulo: `${budLabel} · OTB ${y26} · OTB ${y27}`,
        hoja: ROTULO_VISTA[v],
        columnas,
        filas: [
          serie(budLabel, bud),
          serie(`OTB ${y26}`, a26),
          serie(`OTB ${y27}`, a27),
          { label: `OTB ${y27} vs ${budLabel}`, formato: fmt, es_total: true,
            valores: [...MONTHS.map((_m, i) => a27(i) - bud(i)),
                      MONTHS.reduce((t, _m, i) => t + a27(i) - bud(i), 0)] },
        ],
      };
    });
    try { await bajarCuadros(`Analisis_${y26}_${y27}`, cuadros); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }

  const seriesMeta = [
    { label: budLabel, color: "var(--accent-budget)" },
    { label: `OTB ${y26}`, color: "#8C9196" },
    { label: `OTB ${y27}`, color: "#ED7D31" },
  ];
  const s3 = (arr: number[], idxs: number[]) => idxs.reduce((a, i) => a + arr[i], 0);
  const cols: { label: string; vals: number[]; q: number }[] = [];
  for (let q = 1; q <= 4; q++) {
    const idxs = [0, 1, 2].map((k) => (q - 1) * 3 + k);
    if (collapsed.includes(q)) {
      cols.push({ label: `Q${q}`, vals: [s3(budget27, idxs), s3(rev26, idxs), s3(rev27, idxs)], q });
    } else {
      idxs.forEach((i) => cols.push({ label: MESES[i], vals: [budget27[i], rev26[i], rev27[i]], q }));
    }
  }
  const fyVals = [totalB27, total26, total27];

  const FY_W = 1.6;
  const W = 1600, H = 520, L = 70, R = 74, T = 40, B = 70;
  const plotW = W - L - R, plotH = H - T - B, y0 = T + plotH;
  const N = cols.length;
  const band = plotW / (N + FY_W);
  const barW = band * 0.26;
  const gap = band * 0.06;
  const groupW = seriesMeta.length * barW + (seriesMeta.length - 1) * gap;
  const cx = (i: number) => L + i * band + band / 2;
  // En noches no hay «$» ni miles: 454 habitaciones no son «$0k».
  const kfmt = (v: number) => (enNoches ? Math.round(v).toLocaleString()
                                        : `$${Math.round(v / 1000).toLocaleString()}k`);
  const mfmt = (v: number) => (enNoches ? Math.round(v).toLocaleString()
                               : v >= 1000000 ? `$${(v / 1000000).toFixed(2)}M` : v <= 0 ? "$0" : kfmt(v));
  const rawMax = Math.max(1, ...cols.flatMap((c) => c.vals));
  const lStep = enNoches
    ? (rawMax <= 200 ? 50 : rawMax <= 600 ? 100 : rawMax <= 1500 ? 250 : 500)
    : (rawMax <= 700000 ? 100000 : rawMax <= 1400000 ? 200000 : 500000);
  const yMax = Math.ceil(rawMax / lStep) * lStep;
  const y = (v: number) => y0 - (v / yMax) * plotH;
  const gridY = Array.from({ length: Math.floor(yMax / lStep) + 1 }, (_, i) => i * lStep);
  const fyX0 = L + N * band;
  const fyCx = fyX0 + (band * FY_W) / 2;
  const fyRawMax = Math.max(1, ...fyVals);
  const fyStep = enNoches ? (fyRawMax <= 3000 ? 1000 : 2000) : (fyRawMax <= 3000000 ? 1000000 : 2000000);
  const fyMax = Math.ceil(fyRawMax / fyStep) * fyStep;
  const fyY = (v: number) => y0 - (v / fyMax) * plotH;
  const fyTicks = Array.from({ length: Math.floor(fyMax / fyStep) + 1 }, (_, i) => i * fyStep);
  const dividers: number[] = [];
  for (let i = 0; i < cols.length - 1; i++) if (cols[i].q !== cols[i + 1].q) dividers.push(L + (i + 1) * band);
  const metricLbl = ROTULO_VISTA[metric];

  return (
    <div className="space-y-2">
      {picker}
      <div className="rounded-lg border border-white/10 bg-[#0F1118] p-3">
        <div className="mb-1 text-center text-sm font-semibold text-white/90">{t("analisis")} {y26}/{y27} — {budLabel} · OTB {y26} · OTB {y27} · {metricLbl}</div>
        {!has27 && (
          <div className="mb-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-200">
            {t("sinOtbEnSnapshot", { anio: String(y27) })}
          </div>
        )}
        <div className="mb-2 flex flex-wrap items-center gap-x-5 gap-y-2">
          <div className="flex items-center gap-1">
            {VISTAS.map((mk) => (
              <button key={mk} onClick={() => setMetric(mk)}
                className={`rounded px-2.5 py-1 text-[11px] ${metric === mk ? "bg-brand text-white" : "bg-[#1E2130] text-white/60 hover:text-white"}`}>
                {ROTULO_VISTA[mk]}
              </button>
            ))}
            <button onClick={bajarExcel}
              className="ml-2 rounded border border-emerald-400/40 px-2.5 py-1 text-[11px] text-emerald-300 hover:bg-emerald-400/10"
              title={t("excelTresVistasAyuda", { v1: ROTULO_VISTA.total, v2: ROTULO_VISTA.rooms, v3: ROTULO_VISTA.noches })}>
              {t("excel")}
            </button>
          </div>
          <QuarterBar collapsed={collapsed} toggle={toggle} />
        </div>
        <div className="overflow-x-auto">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[760px]" role="img">
            <rect x={fyX0} y={T} width={W - R - fyX0} height={plotH} fill="var(--bg-elevated)" />
            {gridY.map((g) => (
              <g key={g}>
                <line x1={L} y1={y(g)} x2={W - R} y2={y(g)} stroke="var(--border-subtle)" />
                <text x={L - 8} y={y(g) + 3} textAnchor="end" fontSize="10" fill="var(--text-secondary)">${(g / 1000).toLocaleString()}k</text>
              </g>
            ))}
            {fyTicks.map((t, i) => (
              <text key={i} x={W - R + 6} y={fyY(t) + 3} textAnchor="start" fontSize="9" fill="var(--text-secondary)">{mfmt(t)}</text>
            ))}
            {dividers.map((dx, i) => (
              <line key={i} x1={dx} y1={T} x2={dx} y2={y0} stroke="#ef4444" strokeWidth={3} />
            ))}
            <line x1={fyX0} y1={T - 8} x2={fyX0} y2={y0} stroke="#dc2626" strokeWidth={4.5} />
            {cols.map((c, i) => {
              const gx = cx(i) - groupW / 2;
              return (
                <g key={i}>
                  {seriesMeta.map((s, si) => {
                    const bx = gx + si * (barW + gap);
                    const v = c.vals[si];
                    const topY = y(v);
                    const lx = bx + barW / 2;
                    return (
                      <g key={si}>
                        <rect x={bx} y={topY} width={barW} height={y0 - topY} fill={s.color}>
                          <title>{`${c.label} ${s.label}: $${money(v)}`}</title>
                        </rect>
                        {v > 0 && (
                          <text x={lx} y={topY - 5} textAnchor="middle" fontSize="9" fontWeight="600" fill="var(--text-primary)">{kfmt(v)}</text>
                        )}
                      </g>
                    );
                  })}
                  <text x={cx(i)} y={y0 + 15} textAnchor="middle" fontSize="11" fill="var(--text-secondary)">{c.label}</text>
                </g>
              );
            })}
            {(() => {
              const gx = fyCx - groupW / 2;
              return (
                <g>
                  {seriesMeta.map((s, si) => {
                    const bx = gx + si * (barW + gap);
                    const v = fyVals[si];
                    const topY = fyY(v);
                    const lx = bx + barW / 2;
                    return (
                      <g key={si}>
                        <rect x={bx} y={topY} width={barW} height={y0 - topY} fill={s.color}>
                          <title>{`Full Year ${s.label}: $${money(v)}`}</title>
                        </rect>
                        {v > 0 && (
                          <text x={lx} y={topY - 5} textAnchor="middle" fontSize="9" fontWeight="700" fill="var(--text-primary)">{mfmt(v)}</text>
                        )}
                      </g>
                    );
                  })}
                  <text x={fyCx} y={y0 + 15} textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--text-primary)">{tc("fullYear")}</text>
                </g>
              );
            })()}
          </svg>
        </div>
        <div className="mt-1 flex flex-wrap items-center justify-center gap-4 text-[11px] text-white/70">
          {seriesMeta.map((s) => (
            <span key={s.label} className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-sm" style={{ background: s.color }} /> {s.label}</span>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-3 text-[11px]">
        <div className="rounded-lg border border-white/10 bg-[#161923] px-3 py-2"><span className="text-white/50">{budLabel}:</span> <b className="text-sky-300">${money(totalB27)}</b></div>
        <div className="rounded-lg border border-white/10 bg-[#161923] px-3 py-2"><span className="text-white/50">OTB {y26}:</span> <b className="text-white/70">${money(total26)}</b></div>
        <div className="rounded-lg border border-white/10 bg-[#161923] px-3 py-2"><span className="text-white/50">OTB {y27}:</span> <b className="text-orange-300">${money(total27)}</b></div>
        <div className="rounded-lg border border-white/10 bg-[#161923] px-3 py-2"><span className="text-white/50">OTB {y27} vs Budget:</span> <b className={gapBudget >= 0 ? "text-emerald-300" : "text-red-300"}>{gapBudget >= 0 ? "+" : "−"}${money(Math.abs(gapBudget))}</b></div>
      </div>
      <p className="text-[11px] text-white/40">
        {t("a851Nota1", { metrica: metricLbl, unidad: cols.length === 12 ? t("porMes") : t("porPeriodo") })} <span className="text-sky-300">{budLabel}</span> · <span className="text-white/70">OTB {y26}</span> · <span className="text-orange-300">OTB {y27}</span>. {t.rich("a851Nota2", {
          v1: ROTULO_VISTA.total, v2: ROTULO_VISTA.rooms, v3: ROTULO_VISTA.noches,
          fy: tc("fullYear"), anio: String(y27), b: (c: React.ReactNode) => <b>{c}</b>,
        })}
      </p>
    </div>
  );
}

/* ---------- 8.6 Occupancy Trend (% Budget vs % Forecast, líneas) ---------- */
function OccupancyTrend({ data }: { data: Report }) {
  const t = useTranslations("otb");
  const MESES = useMeses();
  const m = data.months;
  const budget = m.map((d) => d.budget.occ);
  const forecast = m.map((d) => d.otb.occ);

  const W = 1120, H = 450, L = 55, R = 20, T = 40, B = 60;
  const plotW = W - L - R, plotH = H - T - B;
  const yMax = 1.0;
  const band = plotW / 12;
  const cx = (i: number) => L + i * band + band / 2;
  const y = (v: number) => T + plotH - (v / yMax) * plotH;
  const poly = (arr: number[]) => arr.map((v, i) => `${cx(i)},${y(v)}`).join(" ");
  const grid = Array.from({ length: 10 }, (_, i) => (i + 1) / 10);

  return (
    <div className="space-y-2 max-w-[1500px] mx-auto">
      <div className="rounded-lg border border-white/10 bg-[#0F1118] p-3">
        <div className="mb-1 text-center text-sm font-semibold text-white/90">{t("occTituloTrend", { anio: String(data.year) })}</div>
        <div className="overflow-x-auto">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[760px]" role="img">
            {grid.map((g) => (
              <g key={g}>
                <line x1={L} y1={y(g)} x2={W - R} y2={y(g)} stroke="var(--border-subtle)" />
                <text x={L - 8} y={y(g) + 3} textAnchor="end" fontSize="10" fill="var(--text-secondary)">{Math.round(g * 100)}%</text>
              </g>
            ))}
            <polyline points={poly(budget)} fill="none" stroke="var(--accent-budget)" strokeWidth="2.5" />
            <polyline points={poly(forecast)} fill="none" stroke="#ED7D31" strokeWidth="2.5" />
            {m.map((d, i) => (
              <g key={i}>
                <circle cx={cx(i)} cy={y(budget[i])} r="3" fill="var(--accent-budget)" />
                <circle cx={cx(i)} cy={y(forecast[i])} r="3" fill="#ED7D31" />
                <text x={cx(i)} y={y(forecast[i]) - 7} textAnchor="middle" fontSize="9" fontWeight="bold" fill="#ED7D31">{Math.round(forecast[i] * 100)}%</text>
                <text x={cx(i)} y={y(budget[i]) + 14} textAnchor="middle" fontSize="9" fontWeight="bold" fill="#7aa0e0">{Math.round(budget[i] * 100)}%</text>
                <text x={cx(i)} y={T + plotH + 16} textAnchor="middle" fontSize="11" fill="var(--text-secondary)">{MESES[i]}</text>
              </g>
            ))}
          </svg>
        </div>
        <div className="mt-1 flex flex-wrap items-center justify-center gap-4 text-[11px] text-white/70">
          <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-5" style={{ background: "var(--accent-budget)" }} /> % Budget {data.year}</span>
          <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-5" style={{ background: "#ED7D31" }} /> % Forecast (OTB) {data.year}</span>
        </div>
      </div>
      <p className="text-[11px] text-white/40">{t("occNota", { corte: data.snapshot_date ?? "" })}</p>
    </div>
  );
}

/* ---------- 8.7 Variance Breakdown (de dónde sale la diferencia) ---------- */

/** Paleta PASTEL. Pedida por el owner el 18-ago-2026 («que sea más pastel»).
 *  Tonos suaves y de luminosidad pareja: ninguna porción grita más que otra por
 *  el color, solo por su tamaño. El % va en negro porque son tonos claros. */
const PIE_COLORS = ["#F4A6A6", "#F7C59F", "#FFD6A5", "#FDFFB6", "#CAFFBF", "#A8D8B9",
  "#9BF6FF", "#BDE0FE", "#A0C4FF", "#B8C0FF", "#CDB4DB", "#FFC8DD"];

function VariancePie({ data }: { data: Report }) {
  const t = useTranslations("otb");
  const tc = useTranslations("common");
  const MESES = useMeses();
  /** La TORTA solo puede repartir el déficit: con signos mezclados no
   *  significaría nada. Los doce meses van en la tabla de al lado. */
  const slices = data.months
    .map((d) => ({ name: MESES[d.month - 1], val: d.net_gap < 0 ? -d.net_gap : 0 }))
    .filter((s) => s.val > 0)
    .sort((a, b) => b.val - a.val);
  const total = slices.reduce((s, x) => s + x.val, 0);

  /** Los DOCE meses, ordenados de positivo a negativo por Total Revenue.
   *
   *  «Pongamos todos, y el dato de cada uno, y que se ordene de positivo a
   *  negativo así vemos rápido, orden por Full Revenue» (owner, 18-ago-2026).
   *  Antes salían SOLO los meses en déficit: los que van adelantados del
   *  presupuesto no se veían, y son la mitad de la historia. */
  const filas = [...data.months]
    .map((d) => ({
      name: MESES[d.month - 1],
      budT: d.budget.total_revenue, otbT: d.otb.total_revenue, varT: d.diff.total_revenue,
      budR: d.budget.rooms_only, otbR: d.otb.rooms_only, varR: d.diff.rooms_only,
      iColor: slices.findIndex((x) => x.name === MESES[d.month - 1]),
    }))
    .sort((a, b) => b.varT - a.varT);

  const tot = filas.reduce((a, f) => ({
    budT: a.budT + f.budT, otbT: a.otbT + f.otbT, varT: a.varT + f.varT,
    budR: a.budR + f.budR, otbR: a.otbR + f.otbR, varR: a.varR + f.varR,
  }), { budT: 0, otbT: 0, varT: 0, budR: 0, otbR: 0, varR: 0 });

  const cx = 150, cy = 150, r = 132;
  let ang = -Math.PI / 2;
  const paths = slices.map((sl, i) => {
    const frac = sl.val / total;
    const a0 = ang, a1 = ang + frac * 2 * Math.PI;
    ang = a1;
    const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    const mid = (a0 + a1) / 2;
    return {
      d: `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 ${frac > 0.5 ? 1 : 0} 1 ${x1} ${y1} Z`,
      color: PIE_COLORS[i % PIE_COLORS.length], frac,
      lx: cx + r * 0.62 * Math.cos(mid), ly: cy + r * 0.62 * Math.sin(mid), sl,
    };
  });

  const dolar = (v: number) => (v < 0 ? `$(${money(-v)})` : `$${money(v)}`);
  const tono = (v: number) => (v < 0 ? "text-rose-300" : v > 0 ? "text-emerald-300" : "text-white/40");
  const th = "px-2 py-1 text-right font-medium text-white/50 whitespace-nowrap";
  const td = "px-2 py-1 text-right whitespace-nowrap";

  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-white/10 bg-[#0F1118] p-3">
        <div className="mb-2 text-sm font-semibold text-white/90">
          {t("varianceTitulo")}
        </div>
        {/* Torta a la IZQUIERDA y tabla ocupando todo lo que queda. Antes la
            tabla era `max-w-sm` y dejaba media pantalla en blanco. */}
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
          {slices.length > 0 && (
            <div className="shrink-0">
              <div className="mb-1 text-center text-[11px] text-white/50">{t("deDondeDeficit")}</div>
              <svg viewBox="0 0 300 300" className="w-[250px]" role="img">
                {paths.map((p, i) => (
                  <g key={i}>
                    <path d={p.d} fill={p.color} stroke="#0F1118" strokeWidth="1.5" />
                    {p.frac > 0.05 && (
                      <text x={p.lx} y={p.ly} textAnchor="middle" fontSize="11" fontWeight="bold" fill="#000">
                        {Math.round(p.frac * 100)}%
                      </text>
                    )}
                  </g>
                ))}
              </svg>
              <div className="mt-1 text-center text-[11px] text-white/50">
                {t("deficitAnio")} <b className="text-rose-300">{dolar(-total)}</b>
              </div>
            </div>
          )}

          <div className="min-w-0 flex-1 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide">
                  <th className="px-2 py-1 text-left text-white/50">{tc("month")}</th>
                  <th className={`${th} border-l border-white/10`} colSpan={3}>Total Revenue</th>
                  <th className={`${th} border-l border-white/10`} colSpan={3}>Rooms Only</th>
                  <th className={`${th} border-l border-white/10`}>{t("pctDelDeficit")}</th>
                </tr>
                <tr className="text-[10px]">
                  <th className="px-2 py-1 text-left text-white/40" />
                  <th className={`${th} border-l border-white/10`}>Budget</th>
                  <th className={th}>OTB</th>
                  <th className={th}>{tc("variance")}</th>
                  <th className={`${th} border-l border-white/10`}>Budget</th>
                  <th className={th}>OTB</th>
                  <th className={th}>{tc("variance")}</th>
                  <th className={`${th} border-l border-white/10`} />
                </tr>
              </thead>
              <tbody>
                {filas.map((f, i) => {
                  const pi = f.iColor >= 0 ? paths[f.iColor] : null;
                  return (
                    <tr key={i} className="border-t border-white/5">
                      <td className="whitespace-nowrap px-2 py-1 text-left">
                        <span className="mr-2 inline-block h-2.5 w-2.5 rounded-sm align-middle"
                              style={{ background: pi ? pi.color : "transparent",
                                       border: pi ? "none" : "1px solid rgba(255,255,255,.15)" }} />
                        {f.name}
                      </td>
                      <td className={`${td} border-l border-white/10 text-white/60`}>{dolar(f.budT)}</td>
                      <td className={`${td} text-white/60`}>{dolar(f.otbT)}</td>
                      <td className={`${td} font-medium ${tono(f.varT)}`}>{dolar(f.varT)}</td>
                      <td className={`${td} border-l border-white/10 text-white/60`}>{dolar(f.budR)}</td>
                      <td className={`${td} text-white/60`}>{dolar(f.otbR)}</td>
                      <td className={`${td} font-medium ${tono(f.varR)}`}>{dolar(f.varR)}</td>
                      <td className={`${td} border-l border-white/10 text-white/50`}>
                        {pi ? `${Math.round(pi.frac * 100)}%` : "—"}
                      </td>
                    </tr>
                  );
                })}
                <tr className="border-t border-white/20 font-bold">
                  <td className="px-2 py-1 text-left">{t("totalAnio")}</td>
                  <td className={`${td} border-l border-white/10`}>{dolar(tot.budT)}</td>
                  <td className={td}>{dolar(tot.otbT)}</td>
                  <td className={`${td} ${tono(tot.varT)}`}>{dolar(tot.varT)}</td>
                  <td className={`${td} border-l border-white/10`}>{dolar(tot.budR)}</td>
                  <td className={td}>{dolar(tot.otbR)}</td>
                  <td className={`${td} ${tono(tot.varR)}`}>{dolar(tot.varR)}</td>
                  <td className={`${td} border-l border-white/10`}>100%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <p className="text-[11px] text-white/40">
        {t.rich("varianceNota", { corte: data.snapshot_date ?? "", b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>
    </div>
  );
}

