"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getPLCompare, getPLCompareRange,
  type Scenario, type PLCompare, type PLCompareRange, type PLColumn,
} from "@/lib/api";
import { bajarCuadros, type Cuadro, type FormatoCol } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTHS_EN = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const lineAmt = (c: PLColumn | undefined, code: string) => c?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;

const GOLD = "#c8a24a";

// ── Períodos: Mes (con selector) y trimestres/año, con su tramo de meses fijo.
// El card de la derecha siempre es "YTD hasta el fin de este período" — para
// Q4/Full Year eso es el año completo, así que las dos tarjetas coinciden a
// propósito: es la misma identidad que ya usaba Mes/YTD, extendida.
type PeriodKey = "month" | "q1" | "q2" | "q3" | "q4" | "full";
const PERIODS: { key: PeriodKey; label: string; range: [number, number] | null }[] = [
  { key: "month", label: "Month", range: null },
  { key: "q1", label: "Q1", range: [1, 3] },
  { key: "q2", label: "Q2", range: [4, 6] },
  { key: "q3", label: "Q3", range: [7, 9] },
  { key: "q4", label: "Q4", range: [10, 12] },
  { key: "full", label: "Full Year", range: [1, 12] },
];
const periodLabel = (p: PeriodKey, month: number) =>
  p === "month" ? MONTHS_EN[month - 1].toUpperCase()
  : p === "full" ? "FULL YEAR"
  : p.toUpperCase();

type Kind = "count" | "pct" | "money2" | "money";
type Metric = { label: string; icon: string; kind: Kind; strong?: boolean; tint?: string; get: (c: PLColumn | undefined) => number };
const METRICS: Metric[] = [
  { label: "Total Rooms Available", icon: "🛏️", kind: "count", get: c => c?.kpis.rooms_available ?? 0 },
  { label: "Total Rooms Occupied", icon: "🔑", kind: "count", get: c => c?.kpis.rooms_occupied ?? 0 },
  { label: "Total Guests", icon: "👥", kind: "count", get: c => c?.kpis.guests ?? 0 },
  { label: "Occupancy %", icon: "🟢", kind: "pct", tint: "rgba(38,166,154,0.10)", get: c => (c?.kpis.occupancy_pct ?? 0) * 100 },
  { label: "ADR", icon: "💲", kind: "money2", get: c => c?.kpis.adr ?? 0 },
  { label: "RevPAR", icon: "📈", kind: "money2", get: c => { const ra = c?.kpis.rooms_available ?? 0; return ra ? lineAmt(c, "TOTAL_REVENUES") / ra : 0; } },
  { label: "Total Revenue", icon: "🪙", kind: "money", strong: true, get: c => lineAmt(c, "TOTAL_REVENUES") },
];

const c0 = (v: number) => Math.round(v).toLocaleString("en-US");
const m2 = (v: number) => {
  const s = "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return v < 0 ? "(" + s + ")" : s;
};
function fmtVal(v: number, k: Kind): string {
  if (k === "count") return c0(v);
  if (k === "pct") return v.toFixed(2) + "%";
  return m2(v);
}
function fmtVarAbs(v: number, k: Kind): string {
  if (Math.abs(v) < 0.005) return "—";
  if (k === "pct") return (v >= 0 ? "" : "(") + Math.abs(v).toFixed(2) + "pp" + (v >= 0 ? "" : ")");
  if (k === "count") return (v >= 0 ? "" : "(") + c0(Math.abs(v)) + (v >= 0 ? "" : ")");
  const s = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return v >= 0 ? "$" + s : "($" + s + ")";
}

export default function OperationSnapshotPage() {
  const tc = useTranslations("common");
  const t = useTranslations("opsSummary");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Cada selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca
  // se eligio abre con el preferido del owner.
  const [actualId, setActualId] = useEscenarioDe("operation-insight/summary:actual", scenarios, "actual");
  const [budgetId, setBudgetId] = useEscenarioDe("operation-insight/summary:budget", scenarios, "budget", undefined, true);
  const [period, setPeriod] = useState<PeriodKey>("month");
  const [month, setMonth] = useState(5);
  const [cmp, setCmp] = useState<PLCompare | null>(null);
  const [rangeCmp, setRangeCmp] = useState<PLCompareRange | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const range = PERIODS.find(p => p.key === period)?.range ?? null;
  const throughMonth = range ? range[1] : month;

  useEffect(() => {
    (async () => {
      try {
        // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (aid: string, bid: string, thru: number, p: PeriodKey, rng: [number, number] | null) => {
    if (!aid) return;
    setLoading(true); setError(null);
    const ids = [aid, bid].filter(Boolean);
    try {
      // El card de la izquierda para Q1-Q4 necesita SU PROPIO rango — no es
      // una resta de columnas YTD ya armadas (ADR pondera por noches, y el
      // impuesto tiene una corrección anual: ninguna de las dos es aditiva).
      // Mes y Full Year no necesitan la llamada extra: salen de .month/.full
      // en la misma respuesta que ya trae el card de la derecha (YTD).
      const needsRange = p === "q1" || p === "q2" || p === "q3" || p === "q4";
      const [c, rc] = await Promise.all([
        getPLCompare(ids, thru),
        needsRange ? getPLCompareRange(ids, rng![0], rng![1]) : Promise.resolve(null),
      ]);
      setCmp(c); setRangeCmp(rc);
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (actualId) load(actualId, budgetId, throughMonth, period, range); }, [actualId, budgetId, throughMonth, period, range, load]);

  // Columna "izquierda" (el período elegido) y "derecha" (YTD hasta su fin).
  const leftCol = useCallback((idx: number): PLColumn | undefined => {
    if (period === "month") return cmp?.versions[idx]?.month;
    if (period === "full") return cmp?.versions[idx]?.full;
    return rangeCmp?.versions[idx]?.range;
  }, [period, cmp, rangeCmp]);
  const rightCol = useCallback((idx: number): PLColumn | undefined => cmp?.versions[idx]?.ytd, [cmp]);

  const a = cmp?.versions[0];
  const aLeft = leftCol(0), bLeft = budgetId ? leftCol(1) : undefined;
  const aRight = rightCol(0), bRight = budgetId ? rightCol(1) : undefined;

  const rows = useMemo(() => METRICS.map(mt => {
    const aM = mt.get(aLeft), bM = mt.get(bLeft), aY = mt.get(aRight), bY = mt.get(bRight);
    return { mt, aM, bM, vM: aM - bM, pM: bM ? (aM - bM) / Math.abs(bM) : 0,
             aY, bY, vY: aY - bY, pY: bY ? (aY - bY) / Math.abs(bY) : 0 };
  }), [aLeft, bLeft, aRight, bRight]);

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const pcol = (p: number) => Math.abs(p) < 0.0001 ? "var(--text-disabled)" : p > 0 ? "var(--positive)" : "var(--negative)";

  // ── Bajar a Excel ──────────────────────────────────────────────────────────
  // Las dos tarjetas (período elegido y YTD) van cada una en su hoja. La Var %
  // va en una TERCERA hoja y no como columna de las otras dos: el cuadro
  // mezcla noches, ocupación y dólares en la misma columna, así que el formato
  // se define por fila — y con formato de fila una columna de porcentajes al
  // final saldría con el formato de la métrica (0.05 se vería como "0").
  async function bajarExcel() {
    setError(null);
    if (!a) { setError(t("sinDatosExport")); return; }
    const aScn = scenarios.find(s => s.id === actualId), bScn = scenarios.find(s => s.id === budgetId);
    const nA = aScn ? scnLabel(aScn) : "Actual", nB = bScn ? scnLabel(bScn) : "Budget";
    const anio = aScn?.year ?? new Date().getFullYear();
    const fmtDe = (k: Kind): FormatoCol => k === "count" ? "num" : k === "pct" ? "pct" : k === "money2" ? "usd2" : "usd";
    const pLbl = periodLabel(period, month);
    const ytdLbl = `YTD ${MONTHS_EN[throughMonth - 1]}`;

    const hoja = (nombre: string, titulo: string, kind: "left" | "right"): Cuadro => ({
      titulo, hoja: nombre,
      subtitulo: t("excelSubtitulo", { a: nA, b: nB }),
      columnas: [
        { label: tc("metric"), ancho: 30, formato: "texto" },
        { label: nA, ancho: 18, formato: "usd" },
        { label: nB, ancho: 18, formato: "usd" },
        { label: "Var", ancho: 18, formato: "usd" },
      ],
      filas: rows.map(r => {
        // METRICS devuelve la ocupación ya multiplicada por 100 para pintarla;
        // al Excel va como FRACCIÓN, que es lo que entiende el formato %.
        const esc = r.mt.kind === "pct" ? 100 : 1;
        const av = (kind === "left" ? r.aM : r.aY) / esc;
        const bv = (kind === "left" ? r.bM : r.bY) / esc;
        return { label: r.mt.label, es_total: !!r.mt.strong, formato: fmtDe(r.mt.kind), valores: [av, bv, av - bv] };
      }),
    });

    const varPct: Cuadro = {
      titulo: t("varPctTitulo"),
      subtitulo: t("varPctSubtitulo"),
      hoja: "Var %",
      columnas: [
        { label: tc("metric"), ancho: 30, formato: "texto" },
        { label: `Var % ${pLbl}`, ancho: 16, formato: "pct" },
        { label: `Var % ${ytdLbl}`, ancho: 16, formato: "pct" },
      ],
      filas: rows.map(r => ({
        label: r.mt.label, es_total: !!r.mt.strong,
        valores: [r.bM ? r.pM : null, r.bY ? r.pY : null],
      })),
    };

    try {
      await bajarCuadros("Performance_Snapshot", [
        hoja(pLbl, `${pLbl} ${anio} · Performance Snapshot`, "left"),
        hoja("YTD", `${ytdLbl} ${anio} · Performance Snapshot`, "right"),
        varPct,
      ]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }

  const Card = ({ title, icon, kind }: { title: string; icon: string; kind: "left" | "right" }) => (
    <div style={{ flex: "1 1 520px", minWidth: 0, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "16px 22px", background: "linear-gradient(90deg, #16234d, #244481)", color: "#fff" }}>
        <span style={{ width: 40, height: 40, borderRadius: "50%", border: `2px solid ${GOLD}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 19 }}>{icon}</span>
        <span style={{ fontSize: 20, fontWeight: 800, letterSpacing: 0.5 }}>{title}</span>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "var(--bg-header)" }}>
            <th style={{ textAlign: "left", padding: "9px 16px", fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.6 }}>Metric</th>
            {["Actual","Budget","Var $","Var %"].map(h => <th key={h} style={{ textAlign: "right", padding: "9px 14px", fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.6 }}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const av = kind === "left" ? r.aM : r.aY, bv = kind === "left" ? r.bM : r.bY;
            const vAbs = kind === "left" ? r.vM : r.vY, vp = kind === "left" ? r.pM : r.pY;
            const strong = r.mt.strong;
            const vc = strong ? (vp >= 0 ? "#5ee0a0" : "#ff8e8e") : pcol(vp);
            const rowBg = strong ? "linear-gradient(90deg, #16234d, #244481)" : (r.mt.tint ?? (i % 2 ? "rgba(255,255,255,0.018)" : "transparent"));
            return (
              <tr key={i} style={{ borderTop: "1px solid var(--border-subtle)", background: rowBg }}>
                <td style={{ padding: "11px 16px", fontSize: 13.5, fontWeight: strong ? 800 : 600, color: strong ? "#fff" : "var(--text-primary)", whiteSpace: "nowrap" }}>
                  <span style={{ display: "inline-flex", width: 26, height: 26, borderRadius: "50%", background: strong ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.06)", alignItems: "center", justifyContent: "center", fontSize: 13, marginRight: 10, verticalAlign: "middle" }}>{r.mt.icon}</span>
                  {r.mt.label}
                </td>
                <td className="mono" style={{ textAlign: "right", padding: "11px 14px", fontSize: 15, fontWeight: strong ? 800 : 700, color: strong ? "#fff" : "var(--text-primary)" }}>{fmtVal(av, r.mt.kind)}</td>
                <td className="mono" style={{ textAlign: "right", padding: "11px 14px", fontSize: 14, fontWeight: 600, color: strong ? "#cdd6ea" : "var(--text-secondary)" }}>{fmtVal(bv, r.mt.kind)}</td>
                <td className="mono" style={{ textAlign: "right", padding: "11px 14px", fontSize: 13.5, fontWeight: 800, color: vc }}>{fmtVarAbs(vAbs, r.mt.kind)}</td>
                <td className="mono" style={{ textAlign: "right", padding: "11px 14px", fontSize: 13.5, fontWeight: 800, color: vc }}>{bv ? (vp >= 0 ? "" : "-") + Math.abs(vp*100).toFixed(1) + "%" : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  const anioBanner = a?.year ?? new Date().getFullYear();
  const pLbl = periodLabel(period, month);

  return (
    <div className="print-dashboard pag pag-media" style={{ padding: "20px 20px 44px" }}>
      <IrA esc={budgetId} />
      {/* Banner */}
      <div style={{ textAlign: "center", marginBottom: 6 }}>
        <h1 style={{ fontSize: 36, fontWeight: 800, margin: 0, letterSpacing: -0.5 }}><span style={{ color: "var(--text-primary)" }}>{pLbl.charAt(0) + pLbl.slice(1).toLowerCase()} {anioBanner} </span><span style={{ color: "var(--brand)" }}>Performance Snapshot</span></h1>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginTop: 6 }}>
          <span style={{ height: 2, width: 60, background: "var(--border-medium)" }} />
          <span style={{ fontSize: 14, color: "var(--text-secondary)", fontWeight: 600 }}>Actual vs Budget <span style={{ color: GOLD, fontWeight: 800 }}>|</span> {period === "month" ? "Monthly" : period === "full" ? "Annual" : "Quarterly"} and YTD</span>
          <span style={{ height: 2, width: 60, background: "var(--border-medium)" }} />
        </div>
      </div>

      {/* Sub-tabs de período */}
      <div className="no-print" style={{ display: "flex", gap: 6, justifyContent: "center", margin: "18px 0 4px" }}>
        {PERIODS.map(p => (
          <button key={p.key} onClick={() => setPeriod(p.key)}
            style={{
              padding: "7px 16px", fontSize: 12.5, fontWeight: 700, borderRadius: 999, cursor: "pointer",
              border: `1px solid ${period === p.key ? "var(--brand)" : "var(--border-medium)"}`,
              background: period === p.key ? "var(--brand)" : "var(--bg-input)",
              color: period === p.key ? "#fff" : "var(--text-secondary)",
            }}>
            {p.label}
          </button>
        ))}
      </div>

      <div className="no-print" style={{ display: "flex", gap: 10, justifyContent: "center", margin: "12px 0 22px", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Actual</span><select value={actualId} onChange={e => setActualId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Budget</span><select value={budgetId} onChange={e => setBudgetId(e.target.value)} style={sel}><option value="" style={{ background: "var(--bg-input)" }}>{tc("none")}</option>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
        {period === "month" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("month")}</span><select value={month} onChange={e => setMonth(Number(e.target.value))} style={sel}>{MONTHS.map((m, i) => <option key={i+1} value={i+1} style={{ background: "var(--bg-input)" }}>{m}</option>)}</select></div>
        )}
        <button onClick={bajarExcel} title={t("excelBtnTitle")} style={{ alignSelf: "flex-end", padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>⬇ Excel</button>
        <button onClick={() => window.print()} style={{ alignSelf: "flex-end", padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)" }}>{tc("print")}</button>
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13, textAlign: "center" }}>{tc("loading")}</div>}

      {!loading && a && <>
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "flex-start" }}>
          <Card title={`${pLbl} ${anioBanner}`} icon="📅" kind="left" />
          <Card title={`YTD ${MONTHS_EN[throughMonth-1].toUpperCase()} ${anioBanner}`} icon="📊" kind="right" />
        </div>
        <div style={{ marginTop: 18, display: "flex", justifyContent: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "11px 20px", fontSize: 12.5, color: "var(--text-secondary)" }}>
            <span style={{ width: 22, height: 22, borderRadius: "50%", background: "var(--brand)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800 }}>i</span>
            {t("notaUsd")}
          </div>
        </div>
      </>}
    </div>
  );
}
