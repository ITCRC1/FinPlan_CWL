"use client";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import AvisoMoneda from "@/components/AvisoMoneda";
import { bajarCuadros, type ColumnaCuadro, type FilaCuadro, type FormatoCol } from "@/lib/exportCuadro";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import {
  getScenarios, getPLMonthly, setActualsThrough, createScenario, copyScenarioFrom,
  setScenarioStatus, setSourceMode, type PLMonthly, type PLLine, type Scenario,
} from "@/lib/api";
import { recalcularYContar } from "@/lib/recalcular";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

function templateLines(data: PLMonthly | null): PLLine[] {
  return data?.months[0]?.lines ?? [];
}

function byCodeMap(
  data: PLMonthly | null, month: number, ytd: boolean,
): Record<string, number> | null {
  if (!data) return null;
  const map: Record<string, number> = {};
  if (month === 0) {
    for (const [k, v] of Object.entries(data.annual)) map[k] = v;
  } else if (ytd) {
    for (let mm = 1; mm <= month; mm++)
      for (const ln of data.months.find((x) => x.month === mm)?.lines ?? [])
        map[ln.line_code] = (map[ln.line_code] ?? 0) + ln.amount_usd;
  } else {
    for (const ln of data.months.find((x) => x.month === month)?.lines ?? [])
      map[ln.line_code] = ln.amount_usd;
  }
  return map;
}

const EXPENSE_SECTIONS = new Set(["OPEXP", "OVERHEAD", "NON_OP"]);
function varColor(section: string, v: number): string {
  if (Math.abs(v) < 0.005) return "var(--text-dim)";
  return (EXPENSE_SECTIONS.has(section) ? v < 0 : v > 0)
    ? "var(--positive)" : "var(--negative)";
}

const TOTAL_CODES = new Set([
  "TOTAL_REVENUES","TOTAL_OPERATING_EXPENSES","OPERATING_PROFIT","TOTAL_OVERHEAD_EXPENSES",
  "TOTAL_GOP","TOTAL_RENT_MGMT_FEES","TOTAL_PROPERTY_INSURANCE","TOTAL_OTHER_EXPENSES",
  "TOTAL_NON_OP_EXPENSES","EBITDA_BEFORE_CAPITAL","CAPITAL_EXPENSE","EBITDA_AFTER_CAPITAL",
  "FINANCIAL_EXPENSES","TOTAL_DEPRECIATIONS","EBT","INCOME_TAXES","NET_PROFIT",
]);
const STRONG_CODES = new Set([
  "TOTAL_GOP","EBITDA_BEFORE_CAPITAL","EBITDA_AFTER_CAPITAL","EBT","NET_PROFIT",
]);
const SECTION_TITLES: Record<string, string> = {
  "REVENUES": "",
  "OPERATING EXPENSES": "OPERATING EXPENSES",
  "COST OF SALES": "COST OF SALES",
  "OVERHEAD COST OF SALES": "OVERHEAD COST OF SALES",
  "OPERATING PROFIT": "OPERATING PROFIT",
  "OVERHEAD EXPENSES": "OVERHEAD EXPENSES",
  "GOP": "",
  "OWNER / NON-OP EXPENSES": "NON-OPERATING EXPENSES",
  "CAPITAL": "CAPITAL",
  "EBITDA": "",
  "FINANCIAL EXPENSES": "FINANCIAL EXPENSES",
  "DEPRECIATION": "DEPRECIATION",
  "TAX / NET PROFIT": "",
};
/** El orden CURADO de las secciones. Ya no es la lista de qué se dibuja: es
 *  solo el orden. Ver `seccionesAMostrar`. */
const SECTION_ORDER = [
  "REVENUES","OPERATING EXPENSES","COST OF SALES","OPERATING PROFIT",
  "OVERHEAD EXPENSES","OVERHEAD COST OF SALES","GOP",
  "OWNER / NON-OP EXPENSES","EBITDA","CAPITAL","FINANCIAL EXPENSES","DEPRECIATION",
  "TAX / NET PROFIT",
];

/** Las secciones a dibujar: TODAS las que trae el motor, en el orden curado, y
 *  las que no estén en la lista al final en vez de perderse.
 *
 *  ⚠️ Antes se recorría `SECTION_ORDER` directo, o sea que era una LISTA BLANCA.
 *  Cuando el costo de ventas salió a sus propias secciones (2026-08-14) sus 19
 *  líneas se agrupaban y se tiraban — en pantalla Y en el Excel—, mientras
 *  `TOTAL_OPERATING_EXPENSES` sí las sumaba. El detalle no cuadraba con su
 *  propio subtotal y nada lo decía.
 *
 *  Una lista blanca de secciones se rompe callada cada vez que el motor gana
 *  una. Esta versión solo ordena. */
function seccionesAMostrar(grupos: Record<string, PLLine[]>): string[] {
  const conocidas = SECTION_ORDER.filter(s => grupos[s]?.length);
  const nuevas = Object.keys(grupos).filter(s => !SECTION_ORDER.includes(s));
  return [...conocidas, ...nuevas];
}

function fmtUSD(n: number): string {
  if (n === 0) return "-";
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${s})` : s;
}

function fmtPct(n: number): string {
  if (!n) return "-";
  return (n * 100).toFixed(1) + "%";
}

// Casing rules: section titles and totals → UPPERCASE; line items → Title Case.
// Line names come from the DB with inconsistent casing (some ALL CAPS, some Title).
const KEEP_UPPER = new Set(["F&B", "SPA", "IT", "ADR", "REVPAR"]);
function titleCase(s: string): string {
  return s.split(" ").map((w) => {
    if (!w) return w;
    if (KEEP_UPPER.has(w.toUpperCase())) return w.toUpperCase();
    if (/^\(.*\)$/.test(w)) return w;          // keep "(3%)", "(5%)"
    if (w === "/" || w === "&" || w === "-") return w;
    // lowercase the word, then capitalize the first letter after each hyphen
    return w.toLowerCase().replace(/(^|-)([a-záéíóúñ])/g, (_, sep, c) => sep + c.toUpperCase());
  }).join(" ");
}
function displayLineName(name: string, isTotal: boolean): string {
  return isTotal ? name.toUpperCase() : titleCase(name);
}

function getKpis(data: PLMonthly | null, month: number, ytd: boolean) {
  if (!data) return null;

  // Single month: use the month's KPIs directly.
  if (month !== 0 && !ytd) {
    const m = data.months.find(x => x.month === month);
    return m ? { ...m.kpis } : null;
  }

  // Range: Año (all 12) or YTD (Jan..month). Derive ADR/RevPAR from the
  // monthly KPIs so they stay consistent with their own source (rate cards
  // for Budget/Forecast, historical for Actual) — no dependency on GL lines.
  const startMonth = 1;
  const endMonth = month === 0 ? 12 : month;
  let avail = 0, occ = 0, roomRev = 0;
  for (let mm = startMonth; mm <= endMonth; mm++) {
    const k = data.months.find(x => x.month === mm)?.kpis;
    if (!k) continue;
    avail += k.rooms_available;
    occ   += k.rooms_occupied;
    // Reconstruct room revenue from monthly ADR × occupied (consistent w/ KPI source)
    roomRev += k.adr * k.rooms_occupied;
  }
  return {
    rooms_available: avail,
    rooms_occupied: occ,
    occupancy_pct: avail ? occ / avail : 0,
    adr: occ ? roomRev / occ : 0,
    revpar: avail ? roomRev / avail : 0,
  };
}

const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
const SNAP_MONTHS = ["ENE","FEB","MAR","ABR","MAY","JUN","JUL","AGO","SEP","OCT","NOV","DIC"];
function scnLabel(s: Scenario): string {
  const t = TYPE_LABEL[s.type] ?? s.type;
  const hideVer = !s.version || ["actual","from-xlsx"].includes(s.version);
  return hideVer ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

// ---- Select styling ----
const SEL: React.CSSProperties = {
  background: "var(--bg-input)", color: "var(--text-primary)",
  border: "1px solid var(--border)", borderRadius: 5,
  padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer",
  minWidth: 160,
};

export default function PLFullPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("pl");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [plById, setPlById] = useState<Record<string, PLMonthly>>({});
  // Col 1 = el real de referencia, Col 2 = el presupuesto, Col 3 = el forecast.
  // Una llave por columna: con una sola compartida, elegir en una le cambiaria
  // el escenario a las otras dos. Mientras nadie las mueva abren con los
  // preferidos del owner.
  const [col1Id, setCol1Id] = useEscenarioDe("pl/full:actual",   scenarios, "actual");
  const [col2Id, setCol2Id] = useEscenarioDe("pl/full:budget",   scenarios, "budget", undefined, true);
  const [col3Id, setCol3Id] = useEscenarioDe("pl/full:forecast", scenarios, "forecast");
  const [month, setMonth] = useState<number>(0);
  const [ytd, setYtd] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newFcModal, setNewFcModal] = useState(false);
  const [newFcSaving, setNewFcSaving] = useState(false);
  const [closingMonth, setClosingMonth] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);  // 'mode' | 'recalc' feedback

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        if (!all.length) { setError(t("sinEscenarios")); return; }
        // Sort: ACTUAL first, then BUDGET, then FORECAST; newest year first within type.
        const sorted = [...all].sort((a, b) =>
          a.year !== b.year ? b.year - a.year :
          (["ACTUAL","BUDGET","FORECAST"].indexOf(a.type) - ["ACTUAL","BUDGET","FORECAST"].indexOf(b.type))
        );
        // El orden es solo para el desplegable; que columna abre con que
        // escenario lo decide `useEscenarioDe` cuando llega la lista.
        setScenarios(sorted);
        const pls = await Promise.all(
          all.map(async (s) => [s.id, await getPLMonthly(s.id)] as const),
        );
        setPlById(Object.fromEntries(pls));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error");
      } finally {
        setLoading(false);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Reload PL data for a single scenario (after actuals_through change or new scenario created)
  const refreshScenarioPL = useCallback(async (scenarioId: string) => {
    const pl = await getPLMonthly(scenarioId);
    setPlById(prev => ({ ...prev, [scenarioId]: pl }));
  }, []);

  // Toggle P&L source: imported snapshot ↔ checkbook (rolls up auxiliares)
  const handleToggleMode = useCallback(async (scenarioId: string, mode: "imported" | "checkbook") => {
    setBusy("mode");
    try {
      await setSourceMode(scenarioId, mode);
      setScenarios(prev => prev.map(s => s.id === scenarioId ? { ...s, source_mode: mode } : s));
      await refreshScenarioPL(scenarioId);
    } finally {
      setBusy(null);
    }
  }, [refreshScenarioPL]);

  // Recalc payroll → allocations → P&L from the checkbooks, then refresh
  const handleRecalc = useCallback(async (scenarioId: string) => {
    setBusy("recalc");
    try {
      const aviso = await recalcularYContar(scenarioId);
      await refreshScenarioPL(scenarioId);
      // Un recálculo a medias devuelve 200. Sin esto, el P&L se refrescaba con
      // datos incompletos y la pantalla no decía nada.
      if (aviso.startsWith("⚠")) setError(aviso);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("errorRecalcular"));
    } finally {
      setBusy(null);
    }
  }, [refreshScenarioPL]); // eslint-disable-line react-hooks/exhaustive-deps

  // Update actuals_through on a FORECAST scenario, then refresh its PL
  const handleActualsThrough = useCallback(async (scenarioId: string, month: number) => {
    await setActualsThrough(scenarioId, month);
    setScenarios(prev => prev.map(s => s.id === scenarioId ? { ...s, actuals_through: month } : s));
    await refreshScenarioPL(scenarioId);
  }, [refreshScenarioPL]);

  // Create a new FORECAST scenario by copying from a source, then add to list + select in col3
  const handleNewForecast = useCallback(async (sourceId: string, version: string) => {
    setNewFcSaving(true);
    try {
      const source = scenarios.find(s => s.id === sourceId)!;
      const newScn = await createScenario({ year: source.year, type: "FORECAST", version, hotel_id: source.hotel_id });
      await copyScenarioFrom(newScn.id, sourceId);
      const pl = await getPLMonthly(newScn.id);
      setScenarios(prev => [...prev, newScn].sort((a, b) =>
        a.year !== b.year ? b.year - a.year :
        (["ACTUAL","BUDGET","FORECAST"].indexOf(a.type) - ["ACTUAL","BUDGET","FORECAST"].indexOf(b.type))
      ));
      setPlById(prev => ({ ...prev, [newScn.id]: pl }));
      setCol3Id(newScn.id);
      setNewFcModal(false);
    } finally {
      setNewFcSaving(false);
    }
  }, [scenarios, setCol3Id]);

  // Close current month: snapshot LIVE as-is (actuals_through already set by user via dropdown)
  // Name = last actual month. LIVE's actuals_through is NOT advanced here — user controls that.
  const handleCloseMonth = useCallback(async () => {
    const live = scenarios.find(s => s.type === "FORECAST" && s.version === "LIVE");
    if (!live) return;
    const lastActual = live.actuals_through ?? 0;
    if (lastActual === 0 || lastActual > 12) return;
    const snapshotVersion = `${SNAP_MONTHS[lastActual - 1]}-${live.year}`;
    setClosingMonth(true);
    try {
      // 1. Create snapshot scenario
      const snap = await createScenario({ year: live.year, type: "FORECAST", version: snapshotVersion, hotel_id: live.hotel_id });
      // 2. Copy all planning data from LIVE
      await copyScenarioFrom(snap.id, live.id);
      // 3. Snapshot gets same actuals_through as LIVE (e.g. MAY-2026 → Jan-May actuals, Jun-Dec forecast)
      await setActualsThrough(snap.id, lastActual);
      // 4. Lock the snapshot
      await setScenarioStatus(snap.id, "locked");
      // 5. Load snapshot PL + update state
      const snapPL = await getPLMonthly(snap.id);
      const snapWithLock: Scenario = { ...snap, status: "locked", is_locked: true, actuals_through: lastActual };
      setScenarios(prev =>
        [...prev, snapWithLock].sort((a, b) =>
          a.year !== b.year ? b.year - a.year :
          (["ACTUAL","BUDGET","FORECAST"].indexOf(a.type) - ["ACTUAL","BUDGET","FORECAST"].indexOf(b.type))
        )
      );
      setPlById(prev => ({ ...prev, [snap.id]: snapPL }));
      // Auto-select snapshot in Col2 for comparison
      setCol2Id(snap.id);
    } finally {
      setClosingMonth(false);
    }
  }, [scenarios, setCol2Id]);

  const useYtd = ytd && month > 0;

  const maps = useMemo(() => ({
    c1: col1Id ? byCodeMap(plById[col1Id], month, useYtd) : null,
    c2: col2Id ? byCodeMap(plById[col2Id], month, useYtd) : null,
    c3: col3Id ? byCodeMap(plById[col3Id], month, useYtd) : null,
  }), [plById, col1Id, col2Id, col3Id, month, useYtd]);

  const kpiMaps = useMemo(() => ({
    c1: col1Id ? getKpis(plById[col1Id] ?? null, month, useYtd) : null,
    c2: col2Id ? getKpis(plById[col2Id] ?? null, month, useYtd) : null,
    c3: col3Id ? getKpis(plById[col3Id] ?? null, month, useYtd) : null,
  }), [plById, col1Id, col2Id, col3Id, month, useYtd]);

  const template = useMemo(() => {
    const id = col1Id || col2Id || col3Id;
    return id ? templateLines(plById[id] ?? null) : [];
  }, [plById, col1Id, col2Id, col3Id]);

  const grouped = useMemo(() => {
    const g: Record<string, PLLine[]> = {};
    for (const ln of template) (g[ln.section] ??= []).push(ln);
    return g;
  }, [template]);

  const exportExcel = useCallback(async () => {
    const col1Scn = scenarios.find(s => s.id === col1Id);
    const col2Scn = scenarios.find(s => s.id === col2Id);
    const col3Scn = scenarios.find(s => s.id === col3Id);
    const viewLbl = month === 0 ? "Full Year" : (ytd && month > 0 ? "YTD " : "") + MONTHS[month - 1];
    const usd: FormatoCol = "usd", pc: FormatoCol = "pct";
    const columnas: ColumnaCuadro[] = [
      { label: tc("line"), ancho: 38, formato: "texto" },
      { label: col1Scn ? scnLabel(col1Scn) : "Col 1", formato: usd },
      { label: col2Scn ? scnLabel(col2Scn) : "Col 2", formato: usd },
      { label: "Var $ (2vs1)", formato: usd },
      { label: "Var % (2vs1)", ancho: 11, formato: pc },
      { label: col3Scn ? scnLabel(col3Scn) : "Col 3", formato: usd },
      { label: "Var $ (3vs1)", formato: usd },
      { label: "Var % (3vs1)", ancho: 11, formato: pc },
    ];
    const vacia = new Array(columnas.length - 1).fill(null) as (number|null)[];

    // El panel de estadísticas también está en pantalla; el Excel lo omitía.
    const filas: FilaCuadro[] = [];
    if (kpiMaps.c1 || kpiMaps.c2 || kpiMaps.c3) {
      filas.push({ label: "STATISTICS", es_total: true, valores: vacia });
      const kFilas: [string, (k: NonNullable<typeof kpiMaps.c1>) => number, FormatoCol][] = [
        ["Rooms Available", k => k.rooms_available, "num"],
        ["Rooms Occupied",  k => k.rooms_occupied,  "num"],
        ["Occupancy %",     k => k.occupancy_pct,   "pct"],
        ["ADR",             k => k.adr,             "usd2"],
        ["RevPAR",          k => k.revpar,          "usd2"],
      ];
      for (const [label, get, formato] of kFilas) {
        filas.push({ label, nivel: 1, formato,
          valores: [kpiMaps.c1 ? get(kpiMaps.c1) : null, kpiMaps.c2 ? get(kpiMaps.c2) : null, null, null,
                    kpiMaps.c3 ? get(kpiMaps.c3) : null, null, null] });
      }
    }

    for (const section of seccionesAMostrar(grouped)) {
      const lines = grouped[section];
      if (!lines?.length) continue;
      const title = SECTION_TITLES[section];
      if (title) filas.push({ label: title, es_total: true, valores: vacia });
      for (const ln of lines) {
        const isTotal = TOTAL_CODES.has(ln.line_code);
        const isHeader = ln.line_code.startsWith("SEC_");
        const v1 = maps.c1?.[ln.line_code] ?? 0;
        const v2 = maps.c2?.[ln.line_code] ?? 0;
        const v3 = maps.c3?.[ln.line_code] ?? 0;
        // Columna sin escenario = celda vacía, no cero.
        const hay2 = !!(maps.c1 && maps.c2), hay3 = !!(maps.c1 && maps.c3);
        filas.push({
          label: displayLineName(ln.line_name, isTotal || isHeader),
          nivel: isTotal ? 0 : 1, es_total: isTotal,
          valores: [
            maps.c1 ? v1 : null,
            maps.c2 ? v2 : null,
            hay2 ? v2 - v1 : null,
            hay2 && Math.abs(v1) > 0.005 ? (v2 - v1) / Math.abs(v1) : null,
            maps.c3 ? v3 : null,
            hay3 ? v3 - v1 : null,
            hay3 && Math.abs(v1) > 0.005 ? (v3 - v1) / Math.abs(v1) : null,
          ],
        });
      }
    }

    try {
      await bajarCuadros(`PL_${viewLbl.replace(/\s/g, "_")}`, [{
        titulo: `P&L — ${hotel.corto}`,
        subtitulo: t("colsCompareSub", { vista: viewLbl }),
        hoja: `PL ${viewLbl}`,
        columnas, filas,
      }]);
    } catch (e) {
      // `setError` acá reemplaza la pantalla entera por el mensaje; para una
      // descarga fallida basta con avisar sin perder el P&L.
      alert(e instanceof Error ? e.message : t("excelFallo"));
    }
  }, [scenarios, col1Id, col2Id, col3Id, month, ytd, maps, kpiMaps, grouped, hotel, t, tc]);

  if (loading) return <div style={{ padding: 32, color: "var(--text-dim)" }}>{t("loadingScenarios")}</div>;
  if (error)   return <div style={{ padding: 32, color: "var(--negative)" }}>{error}</div>;

  const viewLabel = month === 0 ? "Full Year" : (useYtd ? "YTD " : "") + MONTHS[month - 1];
  const col1Scn = scenarios.find(s => s.id === col1Id);
  const col2Scn = scenarios.find(s => s.id === col2Id);
  const col3Scn = scenarios.find(s => s.id === col3Id);

  return (
    <>
    <div className="pag pag-ancha" style={{ padding: "28px 28px 64px" }}>
      <IrA esc={col2Id} />
      {/* Quien LEE el P&L tiene que enterarse si salio con un TC viejo. */}
      <AvisoMoneda scenarioId={col1Id} />
      <style>{`
        @media print {
          body * { visibility: hidden; }
          #pl-print-area, #pl-print-area * { visibility: visible; }
          #pl-print-area { position: absolute; inset: 0; padding: 24px; }
          .no-print { display: none !important; }
          table { font-size: 10px !important; }
        }
      `}</style>

      {/* ── Header ── */}
      <div style={{ marginBottom: 24, display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>{t("fullTitle", { hotel: hotel.corto })}</h1>
          <p style={{ fontSize: 12, color: "var(--text-dim)" }}>
            {t("colsCompareSub", { vista: viewLabel })}
          </p>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 8, marginTop: 4 }}>
          <button onClick={exportExcel} style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "7px 14px", borderRadius: 6, cursor: "pointer",
            background: "var(--accent-excel)", color: "#fff", border: "none",
            fontSize: 13, fontWeight: 600,
          }}>
            ⬇ Excel
          </button>
          <button onClick={() => window.print()} style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "7px 14px", borderRadius: 6, cursor: "pointer",
            background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)",
            fontSize: 13, fontWeight: 600,
          }}>
            🖨 PDF
          </button>
        </div>
      </div>

      {/* ── Column selectors ── */}
      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16,
        marginBottom: 24, padding: "16px 20px",
        background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
      }}>
        {([
          { label: t("col1Label"), val: col1Id, set: setCol1Id },
          { label: t("colNLabel", { n: 2 }), val: col2Id, set: setCol2Id },
          { label: t("colNLabel", { n: 3 }), val: col3Id, set: setCol3Id },
        ] as const).map(({ label, val, set }) => {
          const scn = scenarios.find(s => s.id === val);
          const isForecast = scn?.type === "FORECAST";
          return (
            <div key={label}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-dim)", letterSpacing: 0.5, marginBottom: 6, textTransform: "uppercase" }}>
                {label}
              </div>
              <select value={val} onChange={e => set(e.target.value)} style={SEL}>
                <option value="" style={{ background: "var(--bg-input)", color: "var(--text-primary)" }}>{tc("none")}</option>
                {scenarios.map(s => (
                  <option key={s.id} value={s.id} style={{ background: "var(--bg-input)", color: "var(--text-primary)" }}>{scnLabel(s)}</option>
                ))}
              </select>
              {/* Actuals-through control — only for FORECAST scenarios */}
              {isForecast && (
                <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 11, color: "var(--text-dim)", whiteSpace: "nowrap" }}>{t("actualsThrough")}</span>
                  <select
                    value={scn.actuals_through ?? 0}
                    onChange={e => handleActualsThrough(scn.id, Number(e.target.value))}
                    style={{ ...SEL, minWidth: 0, flex: 1, fontSize: 12, padding: "4px 8px" }}
                  >
                    <option value={0} style={{ background: "var(--bg-input)" }}>{tc("noneDash")}</option>
                    {MONTHS.map((m, i) => (
                      <option key={i+1} value={i+1} style={{ background: "var(--bg-input)" }}>{m}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Forecast actions ── */}
      {(() => {
        const live = scenarios.find(s => s.type === "FORECAST" && s.version === "LIVE");
        const lastActual = live ? (live.actuals_through ?? 0) : 0;
        const canClose = live && lastActual >= 1 && lastActual <= 12;
        const closeLabel = canClose ? t("cerrarMes", { mes: SNAP_MONTHS[lastActual - 1], year: live!.year }) : null;
        return (
          <div className="no-print" style={{ marginBottom: 16, display: "flex", gap: 10, alignItems: "center" }}>
            {canClose && (
              <button
                onClick={handleCloseMonth}
                disabled={closingMonth}
                style={{
                  padding: "6px 16px", fontSize: 12, borderRadius: 5,
                  cursor: closingMonth ? "wait" : "pointer",
                  background: closingMonth ? "var(--surface)" : "#1a4a7a",
                  color: closingMonth ? "var(--text-dim)" : "#fff",
                  border: "1px solid #1a4a7a", fontWeight: 600,
                  opacity: closingMonth ? 0.7 : 1,
                }}
              >
                {closingMonth ? t("cerrando") : closeLabel}
              </button>
            )}
            <button onClick={() => setNewFcModal(true)} style={{
              padding: "6px 14px", fontSize: 12, borderRadius: 5, cursor: "pointer",
              background: "var(--surface)", color: "var(--text-dim)",
              border: "1px solid var(--border)", fontWeight: 500,
            }}>
              {t("nuevoForecastDesde")}
            </button>
          </div>
        );
      })()}

      {/* ── Build mode: fuente del P&L de la Columna 1 ── */}
      {(() => {
        const scn = scenarios.find(s => s.id === col1Id);
        if (!scn) return null;
        const mode = scn.source_mode ?? "imported";
        const isCheckbook = mode === "checkbook";
        return (
          <div className="no-print" style={{
            marginBottom: 20, padding: "10px 14px", display: "flex",
            alignItems: "center", gap: 12, flexWrap: "wrap",
            background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
          }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: 0.5 }}>
              Col 1 · {scnLabel(scn)} · {t("fuentePl")}
            </span>
            {(["imported", "checkbook"] as const).map(m => (
              <button key={m}
                onClick={() => mode !== m && handleToggleMode(scn.id, m)}
                disabled={busy === "mode"}
                style={{
                  padding: "5px 14px", fontSize: 12, borderRadius: 5,
                  cursor: busy === "mode" ? "wait" : "pointer", fontWeight: 600,
                  background: mode === m ? "var(--brand)" : "var(--surface)",
                  color: mode === m ? "#fff" : "var(--text-dim)",
                  border: mode === m ? "1px solid var(--brand)" : "1px solid var(--border)",
                }}>
                {m === "imported" ? t("modoImportado") : t("modoCheckbook")}
              </button>
            ))}
            {isCheckbook && (
              <button onClick={() => handleRecalc(scn.id)} disabled={busy === "recalc"}
                style={{
                  padding: "5px 16px", fontSize: 12, borderRadius: 5, marginLeft: "auto",
                  cursor: busy === "recalc" ? "wait" : "pointer", fontWeight: 600,
                  background: busy === "recalc" ? "var(--surface)" : "var(--accent-excel)",
                  color: busy === "recalc" ? "var(--text-dim)" : "#fff",
                  border: "1px solid #1a6b3c",
                }}>
                {busy === "recalc" ? t("recalculando") : t("recalcularBtn")}
              </button>
            )}
            <span style={{ fontSize: 11, color: "var(--text-dim)", flexBasis: "100%" }}>
              {isCheckbook ? t("ayudaCheckbook") : t("ayudaImportado")}
            </span>
          </div>
        );
      })()}

      {/* ── Month selector + YTD toggle ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {[tc("year"), ...MONTHS].map((label, i) => (
            <button key={i} onClick={() => setMonth(i)} style={{
              padding: "6px 13px", fontSize: 12, borderRadius: 5, cursor: "pointer",
              fontWeight: month === i ? 700 : 400,
              background: month === i ? "var(--brand)" : "var(--surface)",
              color: month === i ? "#fff" : "var(--text)",
              border: month === i ? "1px solid var(--brand)" : "1px solid var(--border)",
            }}>
              {label}
            </button>
          ))}
        </div>
        {month > 0 && (
          <div style={{ display: "flex", gap: 4, marginLeft: 4 }}>
            {([[tc("month"), false], ["YTD", true]] as const).map(([label, val]) => (
              <button key={label} onClick={() => setYtd(val)} style={{
                padding: "6px 14px", fontSize: 12, borderRadius: 5, cursor: "pointer",
                fontWeight: 700,
                background: ytd === val ? "var(--positive)" : "var(--surface)",
                color: ytd === val ? "#fff" : "var(--text)",
                border: ytd === val ? "1px solid var(--positive)" : "1px solid var(--border)",
              }}>
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── P&L Table ── */}
      <div id="pl-print-area">

      {/* ── KPI Stats Header ── */}
      {(kpiMaps.c1 || kpiMaps.c2 || kpiMaps.c3) && (
        <div style={{
          display: "grid", gridTemplateColumns: "22% 1fr 1fr 1fr",
          gap: 0, marginBottom: 16,
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6,
          overflow: "hidden",
        }}>
          {/* Label column */}
          <div style={{ padding: "10px 12px", borderRight: "1px solid var(--border)" }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.6, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 8 }}>
              Statistics
            </div>
            {["Rooms Available","Rooms Occupied","Occupancy %","ADR","RevPAR"].map(l => (
              <div key={l} style={{ fontSize: 12, color: "var(--text-dim)", padding: "3px 0" }}>{l}</div>
            ))}
          </div>
          {/* One column per scenario */}
          {([
            { k: kpiMaps.c1, scn: col1Scn },
            { k: kpiMaps.c2, scn: col2Scn },
            { k: kpiMaps.c3, scn: col3Scn },
          ] as const).map(({ k, scn }, i) => (
            <div key={i} style={{ padding: "10px 12px", borderRight: i < 2 ? "1px solid var(--border)" : undefined }}>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 8, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {scn ? scnLabel(scn) : "—"}
              </div>
              {k ? (
                <>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", padding: "3px 0" }}>{k.rooms_available.toLocaleString()}</div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", padding: "3px 0" }}>{k.rooms_occupied > 0 ? Math.round(k.rooms_occupied).toLocaleString() : "—"}</div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--positive)", padding: "3px 0" }}>{fmtPct(k.occupancy_pct)}</div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", padding: "3px 0" }}>{k.adr > 0 ? "$" + Math.round(k.adr).toLocaleString() : "—"}</div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", padding: "3px 0" }}>{k.revpar > 0 ? "$" + Math.round(k.revpar).toLocaleString() : "—"}</div>
                </>
              ) : (
                <div style={{ fontSize: 11, color: "var(--text-dim)" }}>—</div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
      <table className="fin-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: "2px solid var(--border)" }}>
            <th style={{ textAlign: "left", padding: "6px 8px", fontSize: 11, color: "var(--text-dim)", width: "22%" }} />
            {/* Col 1 */}
            <th style={{ textAlign: "right", padding: "6px 8px", fontSize: 11, fontWeight: 700, color: "var(--text)", whiteSpace: "nowrap" }}>
              {col1Scn ? scnLabel(col1Scn) : "Col 1"}
            </th>
            {/* Col 2 + variance */}
            <th style={{ textAlign: "right", padding: "6px 8px", fontSize: 11, fontWeight: 700, color: "var(--text)", whiteSpace: "nowrap" }}>
              {col2Scn ? scnLabel(col2Scn) : col2Id ? "…" : "—"}
            </th>
            <th style={{ textAlign: "right", padding: "6px 4px", fontSize: 10, color: "var(--text-dim)", whiteSpace: "nowrap" }}>Var $</th>
            <th style={{ textAlign: "right", padding: "6px 8px", fontSize: 10, color: "var(--text-dim)", whiteSpace: "nowrap" }}>Var %</th>
            {/* Col 3 + variance */}
            <th style={{ textAlign: "right", padding: "6px 8px", fontSize: 11, fontWeight: 700, color: "var(--text)", whiteSpace: "nowrap" }}>
              {col3Scn ? scnLabel(col3Scn) : col3Id ? "…" : "—"}
            </th>
            <th style={{ textAlign: "right", padding: "6px 4px", fontSize: 10, color: "var(--text-dim)", whiteSpace: "nowrap" }}>Var $</th>
            <th style={{ textAlign: "right", padding: "6px 8px", fontSize: 10, color: "var(--text-dim)", whiteSpace: "nowrap" }}>Var %</th>
          </tr>
        </thead>
        <tbody>
          {seccionesAMostrar(grouped).map((section) => {
            const rows = grouped[section];
            if (!rows?.length) return null;
            const title = SECTION_TITLES[section];
            return (
              <Fragment key={section}>
                {title && (
                  <tr>
                    <td colSpan={8} style={{
                      paddingTop: 16, paddingBottom: 5, paddingLeft: 8,
                      fontSize: 11, fontWeight: 700, letterSpacing: 0.6,
                      color: "var(--text-dim)", borderBottom: "1px solid var(--border)",
                      textTransform: "uppercase",
                    }}>
                      {title}
                    </td>
                  </tr>
                )}
                {rows.map((ln) => {
                  const isTotal  = TOTAL_CODES.has(ln.line_code);
                  const isStrong = STRONG_CODES.has(ln.line_code);
                  const isHeader = ln.line_code.startsWith("SEC_");
                  const fw = isTotal ? 700 : 400;

                  const v1 = maps.c1?.[ln.line_code] ?? 0;
                  const v2 = maps.c2?.[ln.line_code] ?? 0;
                  const v3 = maps.c3?.[ln.line_code] ?? 0;
                  const d2 = v2 - v1;
                  const d3 = v3 - v1;
                  const p2 = Math.abs(v1) > 0.005 ? (d2 / Math.abs(v1)) * 100 : null;
                  const p3 = Math.abs(v1) > 0.005 ? (d3 / Math.abs(v1)) * 100 : null;

                  const amtColor = (v: number) =>
                    v < 0 ? "var(--negative)" : isStrong ? "var(--positive)" : "var(--text)";

                  function pctStr(p: number | null, d: number) {
                    if (p === null) return "—";
                    return `${d > 0 ? "+" : ""}${p.toFixed(1)}%`;
                  }

                  return (
                    <tr key={ln.line_code} style={{
                      borderTop: isStrong ? "2px solid var(--border)" : undefined,
                      background: isStrong ? "rgba(255,255,255,0.02)" : undefined,
                    }}>
                      <td style={{
                        padding: "4px 8px", paddingLeft: isTotal ? 8 : 22,
                        fontWeight: fw, whiteSpace: "nowrap",
                        color: isTotal ? "var(--text)" : "var(--text-dim)",
                      }}>
                        {displayLineName(ln.line_name, isTotal || isHeader)}
                      </td>
                      {/* Col 1 */}
                      <td className="mono" style={{ padding: "4px 8px", textAlign: "right", fontWeight: fw, color: maps.c1 ? amtColor(v1) : "var(--text-dim)" }}>
                        {maps.c1 ? fmtUSD(v1) : "—"}
                      </td>
                      {/* Col 2 */}
                      <td className="mono" style={{ padding: "4px 8px", textAlign: "right", fontWeight: fw, color: maps.c2 ? amtColor(v2) : "var(--text-dim)" }}>
                        {maps.c2 ? fmtUSD(v2) : "—"}
                      </td>
                      <td className="mono" style={{ padding: "4px 4px", textAlign: "right", fontWeight: fw, color: maps.c1 && maps.c2 ? varColor(section, d2) : "var(--text-dim)" }}>
                        {maps.c1 && maps.c2 ? fmtUSD(d2) : "—"}
                      </td>
                      <td className="mono" style={{ padding: "4px 8px", textAlign: "right", fontSize: 11, color: maps.c1 && maps.c2 ? varColor(section, d2) : "var(--text-dim)" }}>
                        {maps.c1 && maps.c2 ? pctStr(p2, d2) : "—"}
                      </td>
                      {/* Col 3 */}
                      <td className="mono" style={{ padding: "4px 8px", textAlign: "right", fontWeight: fw, color: maps.c3 ? amtColor(v3) : "var(--text-dim)" }}>
                        {maps.c3 ? fmtUSD(v3) : "—"}
                      </td>
                      <td className="mono" style={{ padding: "4px 4px", textAlign: "right", fontWeight: fw, color: maps.c1 && maps.c3 ? varColor(section, d3) : "var(--text-dim)" }}>
                        {maps.c1 && maps.c3 ? fmtUSD(d3) : "—"}
                      </td>
                      <td className="mono" style={{ padding: "4px 8px", textAlign: "right", fontSize: 11, color: maps.c1 && maps.c3 ? varColor(section, d3) : "var(--text-dim)" }}>
                        {maps.c1 && maps.c3 ? pctStr(p3, d3) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      </div>
      </div>
    </div>

    {/* ── New Forecast Modal ── */}
    {newFcModal && <NewForecastModal
      scenarios={scenarios}
      saving={newFcSaving}
      onConfirm={handleNewForecast}
      onClose={() => setNewFcModal(false)}
    />}
    </>
  );
}

// ── New Forecast Modal ─────────────────────────────────────────────────────────

function NewForecastModal({
  scenarios, saving, onConfirm, onClose,
}: {
  scenarios: Scenario[];
  saving: boolean;
  onConfirm: (sourceId: string, version: string) => void;
  onClose: () => void;
}) {
  const tc = useTranslations("common");
  const t = useTranslations("pl");
  const [sourceId, setSourceId] = useState(() => {
    const def = scenarios.find(s => s.type === "BUDGET") ?? scenarios[0];
    return def?.id ?? "";
  });
  const [version, setVersion] = useState("reforecast-1");

  const copyable = scenarios.filter(s => s.type !== "ACTUAL");

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999,
    }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 10,
        padding: "28px 32px", minWidth: 400, maxWidth: 480,
      }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>{t("newForecast")}</h2>
        <p style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 24 }}>
          {t("nuevoForecastAyuda")}
        </p>

        <label style={{ fontSize: 11, fontWeight: 700, color: "var(--text-dim)", letterSpacing: 0.5, textTransform: "uppercase", display: "block", marginBottom: 4 }}>
          {t("origenCopiarDesde")}
        </label>
        <select value={sourceId} onChange={e => setSourceId(e.target.value)} style={{ ...SEL, width: "100%", marginBottom: 16 }}>
          {copyable.map(s => (
            <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>
              {s.type === "BUDGET" ? "Budget" : "Forecast"} {s.year} · {s.version}
            </option>
          ))}
        </select>

        <label style={{ fontSize: 11, fontWeight: 700, color: "var(--text-dim)", letterSpacing: 0.5, textTransform: "uppercase", display: "block", marginBottom: 4 }}>
          {t("versionNuevoForecast")}
        </label>
        <input
          type="text"
          value={version}
          onChange={e => setVersion(e.target.value)}
          placeholder={t("forecastPlaceholder")}
          style={{ ...SEL, width: "100%", boxSizing: "border-box", marginBottom: 24 }}
        />

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{
            padding: "8px 18px", borderRadius: 6, cursor: "pointer",
            background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", fontSize: 13,
          }}>
            {tc("cancel")}
          </button>
          <button
            onClick={() => onConfirm(sourceId, version.trim() || "reforecast-1")}
            disabled={saving || !sourceId}
            style={{
              padding: "8px 18px", borderRadius: 6, cursor: saving ? "wait" : "pointer",
              background: "var(--brand)", color: "#fff", border: "none", fontSize: 13, fontWeight: 600,
              opacity: saving ? 0.7 : 1,
            }}
          >
            {saving ? t("creando") : t("crearForecast")}
          </button>
        </div>
      </div>
    </div>
  );
}
