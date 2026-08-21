"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { BarChart, Bar, ComposedChart, LineChart, Line, LabelList, ResponsiveContainer, XAxis, YAxis, Tooltip, Legend, CartesianGrid } from "recharts";
import { useRef } from "react";
import {
  getScenarios, getPLMonthly, getOnTheBooks, getOtbEntry, saveOtbEntry, importOtbXml,
  getOtbWeeks, getOtbYears, clearOtb, getOtbParams, saveOtbParam,
  type Scenario, type PLMonthly, type OnTheBooks, type OtbEntryRow,
} from "@/lib/api";
import { semanasDe, fraccionForecast, type WeekDef } from "@/lib/weeks";
import { HOTEL_ID } from "@/lib/hotel";

/** Rótulos de mes de reserva, por si el catálogo no responde. */
const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

const lineAmt = (m: PLMonthly["months"][number] | undefined, code: string) => m?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;
const money0 = (v: number) => "$" + Math.round(v).toLocaleString("en-US");
const numF = (v: string) => { const n = parseFloat((v || "").toString().replace(/[, $]/g, "")); return isNaN(n) ? 0 : n; };
type ER = { month: number; rev: string; rrev: string; occ: string; pax: string };
const ECOLS: ("rev"|"rrev"|"occ"|"pax")[] = ["rev", "rrev", "occ", "pax"];

/**
 * On the Books: Budget contra lo que ya está vendido, por mes, con el pickup
 * de la semana. Vive acá y no en su página porque se usa en DOS lados — la
 * pantalla de Marketing Insight y la Presentación a la Junta — y duplicarlo
 * habría garantizado que uno de los dos se quedara viejo.
 *
 * `budgetInicial` fija contra qué presupuesto se compara al abrir: la Junta le
 * pasa el escenario que se está presentando, que es justo la pregunta del
 * dueño («¿cuánto del Budget 2027 ya está en books?»). Sin él, arranca en el
 * budget del año en curso, como siempre.
 *
 * `soloLectura` esconde cargar/borrar/importar: en una presentación esos
 * botones no pintan y un clic de más borra el OTB entero.
 */
export function OnTheBooksPanel({ budgetInicial, soloLectura }: {
  budgetInicial?: string; soloLectura?: boolean;
} = {}) {
  const t = useTranslations("otb");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  /** Los meses en minúscula para nombrar un corte: `18-ago-2026`. */
  const MESES_COR = MONTHS.map(m => m.toLowerCase());
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  /** UN escenario, no dos.
   *
   *  Antes había «Budget» y «OTB en» por separado, y era una trampa: el OTB se
   *  guarda DENTRO de un escenario, así que apuntar los dos selectores a cosas
   *  distintas comparaba el presupuesto de uno contra las reservas de otro sin
   *  avisar. El owner lo pidió en una línea — «yo solo quiero comparar un
   *  escenario y todo lo demás viene del xml». */
  const [budId, setBudId] = useState("");
  const otbId = budId;
  /** El AÑO que se está mirando. Sale del XML, no del escenario.
   *
   *  El archivo del owner trae horizonte multi-año (1.826 días = 5 años) en el
   *  MISMO XML. Sin este selector la pantalla mostraba el año del escenario y
   *  no había cómo ver los otros — y peor, un import viejo que apiló los tres
   *  años sobre 2026 daba enero al 132% de ocupación. */
  const [anio, setAnio] = useState(0);
  const [otbYears, setOtbYears] = useState<number[]>([]);
  const [week, setWeek] = useState(20);
  const [prevWeek, setPrevWeek] = useState(0);          // corte anterior a comparar (0 = ninguno)
  const [loadedWeeks, setLoadedWeeks] = useState<number[]>([]);
  const [metric, setMetric] = useState<"total"|"rooms">("total");
  const [bud, setBud] = useState<PLMonthly | null>(null);
  const [otb, setOtb] = useState<OnTheBooks | null>(null);
  const [otbPrev, setOtbPrev] = useState<OnTheBooks | null>(null);
  const [otbParams, setOtbParams] = useState<Record<number, number>>({});   // % venta en propiedad POR SEMANA (guardado en el historial)
  const [savingPct, setSavingPct] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [erows, setErows] = useState<ER[]>([]);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        const b = all.find(s => s.id === budgetInicial)
          ?? all.find(s => s.type === "BUDGET" && s.year === new Date().getFullYear())
          ?? all.find(s => s.type === "BUDGET") ?? all[0];
        setBudId(b?.id ?? "");
      } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
      finally { setLoading(false); }
    })();
  }, [budgetInicial]);

  const load = useCallback(async (bid: string, oid: string, wk: number, yr: number) => {
    if (!bid || !oid) return;
    setLoading(true); setError(null);
    try {
      const [b, o] = await Promise.all([getPLMonthly(bid), getOnTheBooks(oid, wk, yr || undefined)]);
      setBud(b); setOtb(o);
    }
    catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (budId) load(budId, otbId, week, anio); }, [budId, otbId, week, anio, load]);

  // Los años que trae el XML cargado. Al cambiar de escenario se re-elige uno:
  // el del escenario si está, si no el primero que haya dato.
  useEffect(() => {
    if (!otbId) { setOtbYears([]); return; }
    let cancel = false;
    getOtbYears(otbId).then(r => {
      if (cancel) return;
      setOtbYears(r.years);
      const propio = scenarios.find(s => s.id === otbId)?.year;
      setAnio(r.years.includes(propio ?? 0) ? (propio as number) : (r.years[0] ?? 0));
    }).catch(() => { if (!cancel) { setOtbYears([]); setAnio(0); } });
    return () => { cancel = true; };
  }, [otbId, scenarios]);

  // Semanas cargadas (para el selector de comparación) — se refresca al cambiar de escenario, importar o borrar.
  const refreshWeeks = useCallback(async (oid: string) => {
    if (!oid) { setLoadedWeeks([]); return; }
    try { const r = await getOtbWeeks(oid); setLoadedWeeks(r.weeks); }
    catch { setLoadedWeeks([]); }
  }, []);
  useEffect(() => { refreshWeeks(otbId); }, [otbId, refreshWeeks]);
  // % de venta en propiedad por semana (parte del historial guardado)
  useEffect(() => { if (otbId) getOtbParams(otbId).then(r => setOtbParams(r.by_week ?? {})).catch(() => setOtbParams({})); }, [otbId]);
  // Al abrir (o cambiar de escenario OTB), arrancar en la ÚLTIMA semana subida.
  const didInitWeek = useRef(false);
  useEffect(() => { didInitWeek.current = false; }, [otbId]);
  useEffect(() => {
    if (!didInitWeek.current && loadedWeeks.length) {
      didInitWeek.current = true;
      setWeek(Math.max(...loadedWeeks));
    }
  }, [loadedWeeks]);
  // Por defecto, semana anterior = la mayor cargada que sea < semana actual.
  useEffect(() => {
    const prior = loadedWeeks.filter(w => w < week);
    setPrevWeek(prior.length ? Math.max(...prior) : 0);
  }, [week, loadedWeeks]);
  // Snapshot de la semana anterior (para el cuadro Week-over-Week).
  useEffect(() => {
    if (!otbId || !prevWeek) { setOtbPrev(null); return; }
    let cancel = false;
    getOnTheBooks(otbId, prevWeek, anio || undefined).then(o => { if (!cancel) setOtbPrev(o); }).catch(() => { if (!cancel) setOtbPrev(null); });
    return () => { cancel = true; };
    // ⚠️ `anio` VA en las dependencias: la línea de arriba lo usa para pedir el
    // corte anterior. Sin él, al cambiar de año el corte ACTUAL se recargaba y
    // el anterior se quedaba con el del año viejo — y la columna de comparación
    // (el movimiento entre cortes) restaba dos años distintos. No fallaba:
    // mostraba un número plausible.
  }, [otbId, prevWeek, anio]);

  const rows = useMemo(() => MONTHS.map((_lbl, i) => {
    const m = i + 1;
    const bm = bud?.months.find(x => x.month === m);
    const om = otb?.months.find(x => x.month === m);
    const bTot = lineAmt(bm, "TOTAL_REVENUES"), oTot = om?.total_revenue ?? 0;
    const bRm = lineAmt(bm, "REV_ROOMS"), oRm = om?.rooms_revenue ?? 0;
    const bRev = metric === "total" ? bTot : bRm;
    const oRev = metric === "total" ? oTot : oRm;
    const bOcc = bm?.kpis.occupancy_pct ?? 0;
    const oOcc = om?.occupancy_pct ?? 0;
    const gap = bRev - oRev;
    const pct = bRev ? oRev / bRev : 0;
    return { m, bRev, oRev, gap, pct, bOcc, oOcc,
             bTot, oTot, gapTot: bTot - oTot, bRm, oRm, gapRm: bRm - oRm };
  }), [bud, otb, metric]);

  const tot = rows.reduce((t, r) => ({ bRev: t.bRev + r.bRev, oRev: t.oRev + r.oRev,
    bTot: t.bTot + r.bTot, oTot: t.oTot + r.oTot, bRm: t.bRm + r.bRm, oRm: t.oRm + r.oRm }),
    { bRev: 0, oRev: 0, bTot: 0, oTot: 0, bRm: 0, oRm: 0 });
  const totGap = tot.bRev - tot.oRev;
  const totPct = tot.bRev ? tot.oRev / tot.bRev : 0;
  // El calendario sigue al año del escenario del OTB, no a un 2026 quemado.
  /** El calendario de CORTES va por el año en que se toma el corte, no por el
   *  año del dato. Un corte del 17-ago-2026 sobre un XML que proyecta 2028
   *  sigue siendo un corte de agosto de 2026. Antes esto usaba el año del
   *  escenario: con el Budget 2027 seleccionado, un corte tomado en agosto de
   *  2026 se rotulaba con fechas de 2027. */
  const SEMANAS: WeekDef[] = semanasDe(new Date().getFullYear());

  /** El CORTE que regía en una fecha: el último snapshot cargado con fecha de
   *  inicio menor o igual a la elegida.
   *
   *  No es «la semana que contiene esa fecha»: si esa semana no se cargó, el
   *  corte vigente es el anterior. Devolver «no hay» obligaría a adivinar qué
   *  semanas existen, que es justamente lo que el owner quería dejar de hacer
   *  (2026-08-18: «acá solo hay fecha de inicio y fecha final»).
   */
  const corteEn = useCallback((fecha: string): number => {
    if (!fecha) return 0;
    const candidatas = SEMANAS
      .filter(w => w.start <= fecha && loadedWeeks.includes(w.n))
      .map(w => w.n);
    return candidatas.length ? Math.max(...candidatas) : 0;
  }, [SEMANAS, loadedWeeks]);

  /** La fecha de inicio de un corte, para que los campos muestren lo elegido. */
  const fechaDe = (n: number) => SEMANAS.find(w => w.n === n)?.start ?? "";

  /** Un corte se nombra por su FECHA. Nunca por su número de semana.
   *
   *  «W34» no le dice nada a nadie fuera de esta pantalla, y encima el número
   *  solo no lleva año: el mismo «W34» era agosto de 2026 o de 2027 según qué
   *  escenario estuviera elegido. La fecha no tiene esa ambigüedad. */
  const fmtCorte = (n: number) => {
    const w = SEMANAS.find(x => x.n === n);
    if (!w) return "—";
    const [y, m, d] = w.start.split("-");
    return `${d}-${MESES_COR[Number(m) - 1]}-${y}`;
  };
  const corteLabel = fmtCorte(week);
  const hoyISO = new Date().toISOString().slice(0, 10);
  const cortesCargados = loadedWeeks.length;
  // Trending: Budget vs OTB (Forecast) + media móvil 2 períodos del OTB
  const trend = rows.map((r, i) => ({
    label: MONTHS[r.m-1], Budget: Math.round(r.bRev), Forecast: Math.round(r.oRev),
    MA: Math.round(i === 0 ? r.oRev : (r.oRev + rows[i-1].oRev) / 2),
    gap: Math.round(r.gap),
  }));
  const occData = rows.map(r => ({ label: MONTHS[r.m-1], Budget: +(r.bOcc*100).toFixed(1), "On the Books": +(r.oOcc*100).toFixed(1) }));
  const gapData = rows.map(r => ({ label: MONTHS[r.m-1], GAP: Math.round(r.gap) }));
  // GAP por trimestre (Forecast − Budget; negativo = OTB por debajo del Budget) para los boxes del gráfico
  const gapKfmt = (v: number) => { const s = "$" + Math.abs(Math.round(v / 1000)).toLocaleString("en-US") + "K"; return v < 0 ? `-${s}` : s; };
  const quarterGaps = [[1,2,3],[4,5,6],[7,8,9],[10,11,12]]
    .map((q, i) => { const ms = rows.filter(r => q.includes(r.m)); return ms.length ? { q: `Q${i+1}`, gap: ms.reduce((a, r) => a + (r.oRev - r.bRev), 0) } : null; })
    .filter((x): x is { q: string; gap: number } => x !== null);

  // % de venta en propiedad de la semana actual y de la anterior (cada una el suyo)
  const curPct = otbParams[week] ?? 0.126;
  const prevPct = prevWeek ? (otbParams[prevWeek] ?? 0.126) : 0.126;

  // ───── Comparación semanal (Week over Week): semana actual vs anterior, por mes + trimestre ─────
  const cmp = useMemo(() => {
    if (!bud || !otb) return null;
    const budM = (m: number) => bud.months.find(x => x.month === m);
    const otbM = (src: OnTheBooks | null, m: number) => src?.months.find(x => x.month === m);
    const sd = (a: number, b: number) => (b ? a / b : 0);
    const agg = (label: string, list: number[]) => {
      let budTot = 0, curTot = 0, curRR = 0, curOcc = 0, avail = 0, prevTot = 0, prevRR = 0, prevOcc = 0;
      let curRRfore = 0, prevRRfore = 0;   // la parte del Rooms Revenue que es forecast
      for (const m of list) {
        const bm = budM(m), c = otbM(otb, m), p = otbM(otbPrev, m);
        budTot += lineAmt(bm, "TOTAL_REVENUES");
        curTot += c?.total_revenue ?? 0; curOcc += c?.rooms_occupied ?? 0; avail += c?.rooms_available ?? 0;
        prevTot += p?.total_revenue ?? 0; prevOcc += p?.rooms_occupied ?? 0;
        curRR += c?.rooms_revenue ?? 0;
        prevRR += p?.rooms_revenue ?? 0;
        // El % de venta en propiedad va SOLO sobre el forecast — el history ya
        // lo trae adentro y aplicarlo ahí lo contaría dos veces (owner,
        // 18-ago-2026). Cada corte tiene su propia frontera history/forecast.
        curRRfore += (c?.rooms_revenue ?? 0) * fraccionForecast(m, otb.year, fechaDe(week));
        prevRRfore += (p?.rooms_revenue ?? 0) * fraccionForecast(m, otb.year, fechaDe(prevWeek));
      }
      // Ajuste: venta posible en la propiedad = % × Rooms Revenue del FORECAST.
      // Cada corte usa SU propio % guardado (parte del historial de cortes).
      const onProp = curPct * curRRfore, onPropPrev = prevPct * prevRRfore;
      const curAdj = curTot + onProp, prevAdj = prevTot + onPropPrev;   // OTB ajustado = reservas + propiedad
      return {
        label,
        adrTot: sd(curTot, curOcc) - sd(prevTot, prevOcc),   // ADR Total Revenue (rev total / noches), diff
        adrOnly: sd(curRR, curOcc) - sd(prevRR, prevOcc),    // ADR Only (rooms rev / noches), diff
        occ: sd(curOcc, avail) - sd(prevOcc, avail),          // Occupancy %, diff (fracción)
        otbPure: curTot,                                      // OTB de la semana (reservas)
        gapPure: curTot - budTot,                             // NET GAP solo reservas (sin ajuste)
        onProp,                                               // venta posible en la propiedad
        adj: curAdj,                                          // OTB ajustado (reservas + propiedad)
        gapCur: curAdj - budTot,                              // NET GAP ajustado / neto (OTB ajustado − Budget)
        gapPrev: prevAdj - budTot,                            // NET GAP semana anterior (ajustado)
        variance: curAdj - prevAdj,                           // Variance (pickup) sobre el AJUSTADO
      };
    };
    const ALL = [1,2,3,4,5,6,7,8,9,10,11,12];
    const months = ALL.map(m => agg(MONTHS[m-1], [m]));
    const fy = agg(tc("fullYear"), ALL);  // FY y trimestres siguen agregando los 12 meses
    const quarters = [[1,2,3],[4,5,6],[7,8,9],[10,11,12]].map((q, i) => agg(`Q${i+1}`, q));
    return { left: [...months, fy], right: [...quarters, fy] };
  }, [bud, otb, otbPrev, curPct, prevPct]);
  type CmpCol = NonNullable<typeof cmp>["left"][number];
  const fmtP = (v: number, dec = 2) => { const a = "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }); return v < 0 ? `(${a})` : a; };
  const fmtPct = (v: number) => `${v < 0 ? "-" : ""}${Math.abs(v * 100).toFixed(2)}%`;
  /** ⚠️ `gap` y `sep` son BANDERAS, no se deducen del rótulo.
   *
   *  Antes se calculaban con `lbl.startsWith("NET GAP")` y comparando el
   *  rótulo entero contra un literal en español. Con los rótulos saliendo del
   *  catálogo eso se rompe en cuanto cambia el idioma: la fila deja de estar
   *  resaltada y las dos líneas separadoras desaparecen. */
  const cmpRows: { id: string; lbl: string; get: (c: CmpCol) => number; fmt: (v: number) => string; strong?: boolean; needsPrev?: boolean; gap?: boolean; sep?: boolean }[] = [
    { id: "adrTot", lbl: "ADR Total Revenue", get: c => c.adrTot, fmt: v => fmtP(v), needsPrev: true },
    { id: "adrOnly", lbl: "ADR Only", get: c => c.adrOnly, fmt: v => fmtP(v), needsPrev: true },
    { id: "occ", lbl: "Occupancy %", get: c => c.occ, fmt: v => fmtPct(v), needsPrev: true },
    { id: "otbPure", lbl: t("filaOtbCorte"), get: c => c.otbPure, fmt: v => fmtP(v), sep: true },
    { id: "gapPure", lbl: t("filaNetGapReservas"), get: c => c.gapPure, fmt: v => fmtP(v), gap: true },
    { id: "onProp", lbl: t("filaVentaPropiedad", { pct: (curPct * 100).toFixed(2) }), get: c => c.onProp, fmt: v => fmtP(v) },
    { id: "adj", lbl: t("filaOtbAjustado"), get: c => c.adj, fmt: v => fmtP(v), strong: true },
    { id: "gapCur", lbl: t("filaNetGapAjustado"), get: c => c.gapCur, fmt: v => fmtP(v), strong: true, gap: true, sep: true },
    { id: "gapPrev", lbl: t("filaNetGapAnterior"), get: c => c.gapPrev, fmt: v => fmtP(v), strong: true, needsPrev: true, gap: true },
    { id: "variance", lbl: t("filaVariance"), get: c => c.variance, fmt: v => fmtP(v), strong: true, needsPrev: true, gap: true },
  ];
  const hasPrev = !!otbPrev;
  const prevCorteLabel = prevWeek ? fmtCorte(prevWeek) : null;

  const xmlRef = useRef<HTMLInputElement>(null);
  async function handleXml(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (!files.length || !otbId) return;
    setMsg(null);
    try {
      // El orden no importa: el backend asigna por monto (mayor = Total Revenue).
      const r = await importOtbXml(otbId, week, files[0], files[1]);
      // Un archivo multi-año no tiene UN total: se reporta año por año. El
      // «FY rev» que decía antes era la suma de todos ellos.
      const detalle = r.por_anio.map(a => `${a.year}: $${Math.round(a.revenue).toLocaleString("en-US")} (${a.noches.toLocaleString("en-US")} ${t("nochesUnidad")})`).join(" · ");
      setMsg(t("panelXmlOk", { corte: corteLabel, dias: String(r.days), detalle }));
      load(budId, otbId, week, anio);
      refreshWeeks(otbId);
      // persistir el % de venta en propiedad de esta semana (parte del historial)
      const wp = otbParams[week] ?? 0.126;
      await saveOtbParam(otbId, week, wp); setOtbParams(p => ({ ...p, [week]: wp }));
    } catch (ex) {
      setMsg(`Error: ${ex instanceof Error ? ex.message : String(ex)}`);
    } finally {
      if (xmlRef.current) xmlRef.current.value = "";
    }
  }

  async function clearAll() {
    if (!otbId) return;
    const oname = scenarios.find(s => s.id === otbId);
    if (!window.confirm(t("borrarConfirm", { escenario: oname ? scnLabel(oname) : otbId }))) return;
    setMsg(null);
    try {
      const r = await clearOtb(otbId);
      setMsg(t("borrarOk", { meses: String(r.months_deleted), dias: String(r.daily_deleted) }));
      await refreshWeeks(otbId);
      load(budId, otbId, week, anio);
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
  }

  async function openEntry() {
    if (!otbId) return;
    setMsg(null);
    try {
      const d = await getOtbEntry(otbId, week, anio || undefined);
      setErows(d.rows.map(r => ({ month: r.month, rev: r.total_revenue ? String(r.total_revenue) : "", rrev: r.rooms_revenue ? String(r.rooms_revenue) : "", occ: r.rooms_occupied ? String(r.rooms_occupied) : "", pax: r.guests ? String(r.guests) : "" })));
      setEditing(true);
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
  }
  function setECell(ri: number, col: "rev"|"rrev"|"occ"|"pax", v: string) { setErows(prev => prev.map((r, i) => i === ri ? { ...r, [col]: v } : r)); }
  function ePaste(ri: number, ci: number, e: React.ClipboardEvent) {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const grid = text.replace(/\r/g, "").split("\n").filter(l => l.length).map(l => l.split("\t"));
    setErows(prev => { const next = prev.map(r => ({ ...r })); grid.forEach((cells, dr) => { const r = ri + dr; if (r >= next.length) return; cells.forEach((cell, dc) => { const c = ci + dc; if (c >= ECOLS.length) return; next[r][ECOLS[c]] = String(numF(cell)); }); }); return next; });
  }
  async function saveEntry() {
    if (!otbId) return;
    setSaving(true); setMsg(null);
    try {
      const payload: OtbEntryRow[] = erows.map(r => ({ month: r.month, total_revenue: numF(r.rev), rooms_revenue: numF(r.rrev), rooms_occupied: numF(r.occ), guests: numF(r.pax) }));
      const res = await saveOtbEntry(otbId, week, payload, anio || undefined);
      setMsg(t("guardadoOk", { corte: corteLabel, anio: String(anio || ""), meses: String(res.rows_saved) }));
      const o = await getOnTheBooks(otbId, week, anio || undefined); setOtb(o); setEditing(false);
      // persistir el % de venta en propiedad de esta semana (parte del historial)
      const wp = otbParams[week] ?? 0.126;
      await saveOtbParam(otbId, week, wp); setOtbParams(p => ({ ...p, [week]: wp }));
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setSaving(false); }
  }

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 5, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const th: React.CSSProperties = { textAlign: "right", padding: "6px 12px", fontSize: 10.5, color: "var(--text-secondary)", fontWeight: 700, textTransform: "uppercase", whiteSpace: "nowrap" };
  const td: React.CSSProperties = { textAlign: "right", padding: "5px 12px", fontSize: 12.5 };
  const inp: React.CSSProperties = { width: "100%", textAlign: "right", padding: "4px 6px", background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 3, color: "var(--text-primary)", fontSize: 12.5, outline: "none" };

  return (
    <div className="print-dashboard" style={{ padding: "22px 26px 48px", maxWidth: 1240, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>On the <span style={{ color: "var(--brand)" }}>Books</span> · {otb?.year ?? ""}</h1>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 0" }}>{t("corteAl")} <b style={{ color: "var(--text-primary)" }}>{corteLabel}</b>{otbYears.length > 1 ? <> · {t("anioMinuscula")} <b style={{ color: "var(--text-primary)" }}>{anio}</b></> : null} · <b style={{ color: "var(--brand)" }}>{metric === "total" ? "Total Revenue" : "Rooms Only"}</b> · {t("panelSubtitulo")}</p>
          <div className="no-print" style={{ display: "inline-flex", gap: 0, marginTop: 8, border: "1px solid var(--border-medium)", borderRadius: 6, overflow: "hidden" }}>
            {(["total","rooms"] as const).map(mk => (
              <button key={mk} onClick={() => setMetric(mk)} style={{ padding: "5px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", border: "none", background: metric === mk ? "var(--brand)" : "var(--bg-elevated)", color: metric === mk ? "#fff" : "var(--text-secondary)" }}>{mk === "total" ? "Total Revenue" : "Rooms Only"}</button>
            ))}
          </div>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <input ref={xmlRef} type="file" accept=".xml,.XML" multiple style={{ display: "none" }} onChange={handleXml} />
          <button hidden={soloLectura} onClick={() => xmlRef.current?.click()} title={t("panelXmlAyuda")} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--accent-xml)", color: "#fff", border: "none", alignSelf: "flex-end" }}>{t("xmlOpera")}</button>
          <button hidden={soloLectura} onClick={openEntry} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--positive)", color: "#fff", border: "none", alignSelf: "flex-end" }}>{t("cargarOtb")}</button>
          <button hidden={soloLectura} onClick={clearAll} title={t("borrarOtbAyuda")} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--negative)", color: "#fff", border: "none", alignSelf: "flex-end" }}>{t("borrarOtb")}</button>
          <button hidden={soloLectura} onClick={() => window.print()} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", alignSelf: "flex-end" }}>{tc("print")}</button>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("scenario")}</span>
            <select value={budId} onChange={e => setBudId(e.target.value)} style={{ ...sel, minWidth: 200 }}>
              {scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}
            </select>
          </div>
          {/* El año lo manda el XML: un mismo archivo trae varios. Si solo trae
              uno, el selector no aporta nada y no se muestra. */}
          {otbYears.length > 1 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("anioXml")}</span>
              <select value={anio} onChange={e => setAnio(Number(e.target.value))} style={sel}>
                {otbYears.map(y => <option key={y} value={y} style={{ background: "var(--bg-input)" }}>{y}</option>)}
              </select>
            </div>
          )}
        </div>

        {/* Los cortes se piden POR FECHA, libremente.
            Antes había que traducir «del 3 al 16 de agosto» a números de
            semana antes de poder preguntar, y para eso había que saberse de
            memoria qué semana era cuál. Cada fecha resuelve al último corte
            que ya estaba cargado ese día — no inventa cortes que no existen. */}
        <div className="no-print" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10,
                      marginTop: 10, paddingTop: 10, width: "100%",
                      borderTop: "1px solid var(--border-subtle)" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-secondary)" }}>
            <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase" }}>{t("corteAl")}</span>
            <input type="date" value={fechaDe(week)} max={hoyISO}
                   onChange={e => { const n = corteEn(e.target.value); if (n) setWeek(n); }}
                   style={{ ...sel, minWidth: 0, padding: "5px 8px" }} />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-secondary)" }}>
            <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase" }}>{t("compararDesde")}</span>
            <input type="date" value={fechaDe(prevWeek)} max={fechaDe(week) || hoyISO}
                   onChange={e => setPrevWeek(corteEn(e.target.value))}
                   style={{ ...sel, minWidth: 0, padding: "5px 8px" }} />
            {prevWeek > 0 && (
              <button onClick={() => setPrevWeek(0)} title={t("quitarComparacion")}
                      style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: 14, padding: "0 2px" }}>×</button>
            )}
          </label>
          <span style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>
            {prevWeek
              ? <>{t("pickupDe")} <b style={{ color: "var(--text-primary)" }}>{prevCorteLabel}</b> {t("pickupA")} <b style={{ color: "var(--brand)" }}>{corteLabel}</b></>
              : <>{t("cortePalabra")} <b style={{ color: "var(--brand)" }}>{corteLabel}</b> {t("ponerCompararDesde")}</>}
            {" · "}{t("cortesCargados", { n: cortesCargados })}
          </span>
        </div>
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
      {msg && <div style={{ color: msg.startsWith("Error") ? "var(--negative)" : "var(--positive)", fontSize: 12.5, marginBottom: 8 }}>{msg}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>{tc("loading")}</div>}

      {editing && (
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--positive)", borderRadius: 8, overflow: "hidden", marginBottom: 16 }}>
          <div style={{ padding: "10px 16px", background: "rgba(38,166,154,0.1)", borderBottom: "1px solid var(--border-medium)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 700 }}>{t("cargarOtbTitulo", { corte: corteLabel, escenario: scenarios.find(s => s.id === otbId) ? scnLabel(scenarios.find(s => s.id === otbId)!) : "" })}</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={saveEntry} disabled={saving} style={{ padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: saving ? "default" : "pointer", background: "var(--positive)", color: "#fff", border: "none" }}>{saving ? tc("saving") : t("guardarBoton")}</button>
              <button onClick={() => setEditing(false)} style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--bg-elevated)", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>{tc("close")}</button>
            </div>
          </div>
          <div style={{ padding: "8px 14px", fontSize: 11.5, color: "var(--text-secondary)" }}>{t("pegarAyuda", { cols: `Total Revenue · Rooms Revenue · ${t("roomsOccupied")} · ${tc("guests")}` })}</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr style={{ background: "var(--bg-header)", borderBottom: "1px solid var(--border-medium)" }}>
              <th style={{ ...th, textAlign: "left" }}>{tc("month")}</th><th style={{ ...th, color: "var(--brand)" }}>Total Revenue</th><th style={{ ...th, color: "var(--brand)" }}>Rooms Revenue</th><th style={{ ...th, color: "var(--brand)" }}>{t("roomsOccupied")}</th><th style={{ ...th, color: "var(--brand)" }}>{tc("guests")}</th>
            </tr></thead>
            <tbody>
              {erows.map((r, ri) => (
                <tr key={r.month} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "3px 12px", fontSize: 12.5 }}>{MONTHS[r.month-1]}</td>
                  {ECOLS.map((col, ci) => (
                    <td key={col} style={{ padding: "2px 4px" }}><input className="mono" value={r[col]} onChange={e => setECell(ri, col, e.target.value)} onPaste={e => ePaste(ri, ci, e)} onFocus={e => e.target.select()} style={inp} /></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && bud && otb && <>
        {/* KPI cards */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
          {[["Budget Full Year", money0(tot.bRev), "var(--text-primary)"], ["On the Books", money0(tot.oRev), "var(--brand)"], [t("gapPorVender"), money0(totGap), totGap >= 0 ? "var(--warning)" : "var(--positive)"], [t("pctEnBooks"), (totPct*100).toFixed(1) + "%", "var(--positive)"]].map(([l, v, c], i) => (
            <div key={i} style={{ flex: "1 1 0", minWidth: 150, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 6 }}>{l}</div>
              <div className="mono" style={{ fontSize: 21, fontWeight: 800, color: c as string }}>{v}</div>
            </div>
          ))}
        </div>

        {/* ───── Comparación semanal (Week over Week): actual vs anterior, por mes + trimestre ───── */}
        {cmp && (
          <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, overflow: "hidden", marginBottom: 16 }}>
            <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border-medium)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 700 }}>{t("movimientoEntreCortes")} · <span style={{ color: "var(--brand)" }}>{corteLabel}</span>{prevCorteLabel ? <> vs <span style={{ color: "var(--text-secondary)" }}>{prevCorteLabel}</span></> : ""}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <label style={{ fontSize: 11, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6 }}>
                  {t("ventaPropiedadDelCorte")} <b style={{ color: "var(--brand)" }}>{corteLabel}</b> {t("pctDelRoomsRev")}
                  <input className="mono" type="number" step="0.1" value={+(curPct * 100).toFixed(2)}
                    onChange={e => setOtbParams(p => ({ ...p, [week]: (parseFloat(e.target.value) || 0) / 100 }))}
                    onBlur={async () => { if (!otbId) return; setSavingPct(true); try { await saveOtbParam(otbId, week, otbParams[week] ?? 0.126); } finally { setSavingPct(false); } }}
                    style={{ width: 64, textAlign: "right", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-subtle)", borderRadius: 4, padding: "3px 6px", fontSize: 12 }} />
                  % {savingPct ? <span style={{ color: "var(--text-secondary)" }}>{t("guardandoMin")}</span> : <span style={{ color: "var(--positive)" }}>{t("guardadoEnElCorte")}</span>}
                </label>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("otbAjustadoNota")}</span>
              </div>
            </div>
            {!prevWeek && <div style={{ padding: "9px 16px", fontSize: 12, color: "var(--warning)" }}>{t.rich("elegiCompararDesde", { b: (c: React.ReactNode) => <b>{c}</b> })}</div>}
            <div className="fin-sticky" style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", whiteSpace: "nowrap" }}>
                <thead>
                  <tr style={{ background: "var(--bg-header)", borderBottom: "1px solid var(--border-medium)" }}>
                    <th style={{ ...th, textAlign: "left" }}>{tc("metric")}</th>
                    {cmp.left.map((c, i) => <th key={"lh" + i} style={{ ...th, background: i === cmp.left.length - 1 ? "rgba(58,111,216,0.14)" : undefined, borderLeft: i === 0 ? "1px solid var(--border-medium)" : undefined }}>{c.label}</th>)}
                    <th style={{ ...th, borderLeft: "2px solid var(--border-medium)", padding: "6px 4px" }} />
                    {cmp.right.map((c, i) => <th key={"rh" + i} style={{ ...th, background: i === cmp.right.length - 1 ? "rgba(58,111,216,0.14)" : undefined, borderLeft: i === 0 ? "1px solid var(--border-medium)" : undefined }}>{c.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {cmpRows.map((row, ri) => {
                    const isGap = !!row.gap;
                    const mute = !!row.needsPrev && !hasPrev;   // sin semana anterior → "—" en filas que dependen de ella
                    const sep = !!row.sep;
                    return (
                      <tr key={row.id} style={{ borderBottom: "1px solid var(--border-subtle)", borderTop: sep ? "2px solid var(--border-medium)" : undefined }}>
                        <td style={{ padding: "5px 12px", fontSize: 12, fontWeight: row.strong ? 700 : 600, color: isGap ? "var(--text-primary)" : "var(--text-secondary)", textAlign: "left" }}>{row.lbl}</td>
                        {cmp.left.map((c, i) => { const v = row.get(c); return <td key={"l" + ri + i} className="mono" style={{ ...td, fontWeight: row.strong ? 700 : 400, color: mute ? "var(--text-secondary)" : (v < 0 ? "var(--negative)" : "var(--text-primary)"), background: i === cmp.left.length - 1 ? "rgba(58,111,216,0.10)" : undefined, borderLeft: i === 0 ? "1px solid var(--border-medium)" : undefined }}>{mute ? "—" : row.fmt(v)}</td>; })}
                        <td style={{ borderLeft: "2px solid var(--border-medium)" }} />
                        {cmp.right.map((c, i) => { const v = row.get(c); return <td key={"r" + ri + i} className="mono" style={{ ...td, fontWeight: row.strong ? 700 : 400, color: mute ? "var(--text-secondary)" : (v < 0 ? "var(--negative)" : "var(--text-primary)"), background: i === cmp.right.length - 1 ? "rgba(58,111,216,0.10)" : undefined, borderLeft: i === 0 ? "1px solid var(--border-medium)" : undefined }}>{mute ? "—" : row.fmt(v)}</td>; })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Trending chart: Budget vs OTB (Forecast) + media móvil */}
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "16px 18px", marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", textAlign: "center", marginBottom: 8 }}>{t("trendTitulo", { anio: String(otb.year) })}</div>
          <div style={{ position: "relative" }}>
          {quarterGaps.length > 0 && (
            <div style={{ position: "absolute", top: 18, left: 64, right: 16, display: "flex", justifyContent: "space-around", gap: 8, pointerEvents: "none", zIndex: 2 }}>
              {quarterGaps.map(g => (
                <div key={g.q} style={{ border: "1.5px solid #EF4444", borderRadius: 4, padding: "3px 12px", background: "rgba(20,26,40,0.88)", fontSize: 12.5, fontWeight: 800, color: "#EF4444", whiteSpace: "nowrap", textAlign: "center" }}>
                  <span style={{ color: "var(--text-secondary)", fontWeight: 700 }}>{g.q} </span>GAP: {gapKfmt(g.gap)}
                </div>
              ))}
            </div>
          )}
          <ResponsiveContainer width="100%" height={340}>
            <ComposedChart data={trend} margin={{ top: 24, right: 16, left: 8, bottom: 4 }} barCategoryGap="22%">
              <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "var(--text-secondary)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v/1000).toLocaleString("en-US")}K`} width={58} />
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              <Tooltip content={(p: any) => {
                if (!p?.active || !p?.payload?.length) return null;
                const d = p.payload[0].payload;
                const gapAbs = (d.Budget ?? 0) - (d.Forecast ?? 0);
                return (
                  <div style={{ background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 6, fontSize: 12, padding: "8px 12px" }}>
                    <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.label}</div>
                    <div style={{ color: "#3A6FD8" }}>Revenue Budget: ${Number(d.Budget).toLocaleString("en-US")}</div>
                    <div style={{ color: "#E58B2B" }}>Revenue Forecast (OTB): ${Number(d.Forecast).toLocaleString("en-US")}</div>
                    <div style={{ color: gapAbs > 0 ? "#F59E0B" : "#26A69A", fontWeight: 700 }}>{t("gapAbsoluto")}: ${Number(gapAbs).toLocaleString("en-US")}</div>
                    <div style={{ color: "#EF4444" }}>{t("mediaMovil2pCorto")}: ${Number(d.MA).toLocaleString("en-US")}</div>
                  </div>
                );
              }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="Budget" name="Revenue Budget" fill="#3A6FD8" radius={[2,2,0,0]} />
              <Bar dataKey="Forecast" name="Revenue Forecast (OTB)" fill="#E58B2B" radius={[2,2,0,0]} />
              <Line type="monotone" dataKey="MA" name={t("mediaMovil2p")} stroke="#EF4444" strokeWidth={2} strokeDasharray="6 3" dot={{ r: 2, fill: "#EF4444" }} />
            </ComposedChart>
          </ResponsiveContainer>
          </div>
        </div>

        {/* Monthly table */}
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, overflow: "hidden" }}>
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "var(--bg-header)" }}>
                <th style={{ ...th, textAlign: "left" }} rowSpan={2}>{tc("month")}</th>
                <th style={{ ...th, textAlign: "center", borderLeft: "1px solid var(--border-medium)", color: "var(--brand)" }} colSpan={3}>Total Revenue</th>
                <th style={{ ...th, textAlign: "center", borderLeft: "1px solid var(--border-medium)", color: "#E58B2B" }} colSpan={3}>Total Rooms (Only)</th>
                <th style={{ ...th, borderLeft: "1px solid var(--border-medium)" }} rowSpan={2}>B.Occ</th>
                <th style={{ ...th }} rowSpan={2}>OTB.Occ</th>
              </tr>
              <tr style={{ background: "var(--bg-header)", borderBottom: "1px solid var(--border-medium)" }}>
                <th style={{ ...th, borderLeft: "1px solid var(--border-medium)" }}>Budget</th><th style={th}>OTB</th><th style={th}>GAP</th>
                <th style={{ ...th, borderLeft: "1px solid var(--border-medium)" }}>Budget</th><th style={th}>OTB</th><th style={th}>GAP</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.m} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "5px 12px", fontSize: 12.5, color: "var(--text-primary)" }}>{MONTHS[r.m-1]}</td>
                  <td className="mono" style={{ ...td, borderLeft: "1px solid var(--border-medium)" }}>{money0(r.bTot)}</td>
                  <td className="mono" style={{ ...td, color: "var(--brand)" }}>{r.oTot ? money0(r.oTot) : "—"}</td>
                  <td className="mono" style={{ ...td, color: r.gapTot > 0 ? "var(--warning)" : "var(--positive)" }}>{money0(r.gapTot)}</td>
                  <td className="mono" style={{ ...td, borderLeft: "1px solid var(--border-medium)" }}>{money0(r.bRm)}</td>
                  <td className="mono" style={{ ...td, color: "#E58B2B" }}>{r.oRm ? money0(r.oRm) : "—"}</td>
                  <td className="mono" style={{ ...td, color: r.gapRm > 0 ? "var(--warning)" : "var(--positive)" }}>{money0(r.gapRm)}</td>
                  <td className="mono" style={{ ...td, color: "var(--text-secondary)", borderLeft: "1px solid var(--border-medium)" }}>{(r.bOcc*100).toFixed(1)}%</td>
                  <td className="mono" style={{ ...td, color: "var(--text-secondary)" }}>{r.oOcc ? (r.oOcc*100).toFixed(1) + "%" : "—"}</td>
                </tr>
              ))}
              <tr style={{ borderTop: "2px solid var(--border-medium)", background: "rgba(255,255,255,0.03)", fontWeight: 700 }}>
                <td style={{ padding: "6px 12px", fontSize: 13, fontWeight: 700 }}>{tc("fullYear").toUpperCase()}</td>
                <td className="mono" style={{ ...td, fontWeight: 700, borderLeft: "1px solid var(--border-medium)" }}>{money0(tot.bTot)}</td>
                <td className="mono" style={{ ...td, fontWeight: 700, color: "var(--brand)" }}>{money0(tot.oTot)}</td>
                <td className="mono" style={{ ...td, fontWeight: 700, color: (tot.bTot-tot.oTot) > 0 ? "var(--warning)" : "var(--positive)" }}>{money0(tot.bTot - tot.oTot)}</td>
                <td className="mono" style={{ ...td, fontWeight: 700, borderLeft: "1px solid var(--border-medium)" }}>{money0(tot.bRm)}</td>
                <td className="mono" style={{ ...td, fontWeight: 700, color: "#E58B2B" }}>{money0(tot.oRm)}</td>
                <td className="mono" style={{ ...td, fontWeight: 700, color: (tot.bRm-tot.oRm) > 0 ? "var(--warning)" : "var(--positive)" }}>{money0(tot.bRm - tot.oRm)}</td>
                <td className="mono" style={{ ...td, borderLeft: "1px solid var(--border-medium)" }}></td><td className="mono" style={td}></td>
              </tr>
            </tbody>
          </table>
          </div>
        </div>

        {/* Más gráficos */}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 16 }}>
          <div style={{ flex: "1 1 460px", minWidth: 0, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "14px 16px" }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", textAlign: "center", marginBottom: 10 }}>{t("occTituloTrend", { anio: String(otb.year) })}</div>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={occData} margin={{ top: 14, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: "var(--text-secondary)", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `${v}%`} width={40} domain={[0, 100]} />
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                <Tooltip contentStyle={{ background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 6, fontSize: 12 }} formatter={(v: any, n: any) => [`${v}%`, n]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="Budget" name="% Budget" stroke="#3A6FD8" strokeWidth={2.5} dot={{ r: 2 }}>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  <LabelList dataKey="Budget" position="bottom" fill="#7f93c4" fontSize={9} formatter={(v: any) => `${v}%`} />
                </Line>
                <Line type="monotone" dataKey="On the Books" name="% Forecast (OTB)" stroke="#E58B2B" strokeWidth={2.5} dot={{ r: 2 }}>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  <LabelList dataKey="On the Books" position="top" fill="#e3a866" fontSize={9} formatter={(v: any) => `${v}%`} />
                </Line>
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div style={{ flex: "1 1 460px", minWidth: 0, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "14px 16px" }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10, textAlign: "center" }}>{t("gapPorVenderMes")}</div>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={gapData} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: "var(--text-secondary)", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `$${Math.round(v/1000)}K`} width={48} />
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                <Tooltip contentStyle={{ background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 6, fontSize: 12 }} formatter={(v: any) => [`$${Number(v).toLocaleString("en-US")}`, "GAP"]} />
                <Bar dataKey="GAP" fill="#F59E0B" radius={[2,2,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {!otb.has_data && <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 12 }}>{t.rich("panelSinDatos", { boton: t("cargarOtb"), b: (c: React.ReactNode) => <b>{c}</b> })}</p>}
      </>}
    </div>
  );
}
