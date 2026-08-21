"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { FAM_FB, FAM_ROOMS, familia } from "@/lib/plFamilias";
import { bajarCuadros, type FilaCuadro, type FormatoCol } from "@/lib/exportCuadro";
import { HOTEL_ID, hotelShort } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import {
  getScenarios, getPLCompare,
  type Scenario, type PLCompare, type PLColumn,
} from "@/lib/api";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const lineAmt = (c: PLColumn | undefined, code: string) => c?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;

type Kind = "count" | "pct" | "money2" | "money";
type Metric = { label: string; kind: Kind; get: (c: PLColumn | undefined) => number; strong?: boolean };
const METRICS: Metric[] = [
  { label: "Total Rooms Available", kind: "count", get: c => c?.kpis.rooms_available ?? 0 },
  { label: "Total Rooms Occupied", kind: "count", get: c => c?.kpis.rooms_occupied ?? 0 },
  { label: "Total Guests", kind: "count", get: c => c?.kpis.guests ?? 0 },
  { label: "Occupancy %", kind: "pct", get: c => (c?.kpis.occupancy_pct ?? 0) * 100 },
  { label: "ADR", kind: "money2", get: c => c?.kpis.adr ?? 0 },
  { label: "RevPAR", kind: "money2", get: c => c?.kpis.revpar ?? 0 },
  { label: "Total Revenue", kind: "money", strong: true, get: c => lineAmt(c, "TOTAL_REVENUES") },
  // Las FAMILIAS, no la linea suelta: el ingreso de Rooms y de A&B esta
  // partido en varias lineas desde el 2026-08-14. Ver `lib/plFamilias.ts`.
  { label: "Rooms Revenue", kind: "money", get: c => familia(FAM_ROOMS, (x: string) => lineAmt(c, x)) },
  { label: "F&B Revenue", kind: "money", get: c => familia(FAM_FB, (x: string) => lineAmt(c, x)) },
  { label: "Other Revenue", kind: "money", get: c => lineAmt(c, "TOTAL_REVENUES")
      - familia(FAM_ROOMS, (x: string) => lineAmt(c, x)) - familia(FAM_FB, (x: string) => lineAmt(c, x)) },
  { label: "GOP", kind: "money", strong: true, get: c => lineAmt(c, "GOP") },
  { label: "EBITDA", kind: "money", strong: true, get: c => lineAmt(c, "EBITDA_BEFORE") },
  { label: "Net Profit", kind: "money", strong: true, get: c => lineAmt(c, "NET_PROFIT") },
];

function fmt(v: number, k: Kind): string {
  if (k === "count") return Math.round(v).toLocaleString("en-US");
  if (k === "pct") return v.toFixed(1) + "%";
  if (k === "money2") return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const s = "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return Math.abs(v) < 0.5 ? "-" : (v < 0 ? `(${s})` : s);
}

export default function SummaryReportPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("summary");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Cada selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca
  // se eligio abre con el preferido del owner.
  const [actualId, setActualId] = useEscenarioDe("reports/summary:actual", scenarios, "actual");
  const [budgetId, setBudgetId] = useEscenarioDe("reports/summary:budget", scenarios, "budget", undefined, true);
  const [month, setMonth] = useState(5);
  const [cmp, setCmp] = useState<PLCompare | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const load = useCallback(async (aid: string, bid: string, m: number) => {
    if (!aid) return;
    setLoading(true); setError(null);
    try { setCmp(await getPLCompare([aid, bid].filter(Boolean), m)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (actualId) load(actualId, budgetId, month); }, [actualId, budgetId, month, load]);

  const a = cmp?.versions[0];
  const b = budgetId ? cmp?.versions[1] : undefined;

  const data = useMemo(() => METRICS.map(mt => {
    const aM = mt.get(a?.month), bM = mt.get(b?.month), aY = mt.get(a?.ytd), bY = mt.get(b?.ytd);
    return { mt, aM, bM, vM: aM - bM, pM: bM ? (aM - bM) / Math.abs(bM) : 0,
             aY, bY, vY: aY - bY, pY: bY ? (aY - bY) / Math.abs(bY) : 0 };
  }), [a, b]);

  const exportExcel = useCallback(async () => {
    // Los valores van como NÚMERO — antes viajaban ya formateados ("$1,234.00")
    // y el Excel resultante no se podía sumar ni graficar.
    const conBudget = !!b;
    const filas: FilaCuadro[] = data.map(r => {
      // Las métricas en % se guardan en el estado ×100 para pintarlas; en Excel
      // el porcentaje va como FRACCIÓN y el formato de celda pone el signo.
      const esc = r.mt.kind === "pct" ? 0.01 : 1;
      const fila: FilaCuadro = {
        label: r.mt.label,
        es_total: !!r.mt.strong,
        valores: [
          r.aM * esc,
          conBudget ? r.bM * esc : null,
          conBudget ? r.vM * esc : null,
          conBudget ? r.pM : null,
          r.aY * esc,
          conBudget ? r.bY * esc : null,
          conBudget ? r.vY * esc : null,
          conBudget ? r.pY : null,
        ],
      };
      if (r.mt.kind === "pct") fila.formato = "pct";
      return fila;
    });
    const usd: FormatoCol = "usd", pc: FormatoCol = "pct";
    try {
      await bajarCuadros(`Summary_${MONTHS[month-1]}`, [{
        titulo: `Summary ${MONTHS[month-1]} — ${hotelShort()}`,
        subtitulo: t("excelSubtitulo") + (conBudget ? "" : t("excelSinBudget")),
        hoja: "Summary",
        columnas: [
          { label: tc("metric"), ancho: 32, formato: "texto" },
          { label: `Actual ${MONTHS[month-1]}`, formato: usd },
          { label: "Budget", formato: usd },
          { label: "Var $", formato: usd },
          { label: "Var %", ancho: 10, formato: pc },
          { label: `YTD Actual ${MONTHS[month-1]}`, formato: usd },
          { label: "YTD Budget", formato: usd },
          { label: "YTD Var $", formato: usd },
          { label: "YTD Var %", ancho: 10, formato: pc },
        ],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }, [data, month, b, t, tc]);

  const th: React.CSSProperties = { textAlign:"right", padding:"6px 10px", fontSize:11, fontWeight:600, whiteSpace:"nowrap" };
  const td: React.CSSProperties = { textAlign:"right", padding:"5px 10px", fontSize:12, fontFamily:"var(--font-mono)" };
  const pcol = (p: number) => p === 0 ? "var(--text-disabled)" : p > 0 ? "var(--positive, #1A7F4B)" : "var(--negative, #C0392B)";

  return (
    <>
      <style>{`@media print{.no-print{display:none!important}body *{visibility:hidden}#rep,#rep *{visibility:visible}#rep{position:absolute;inset:0;padding:16px}}`}</style>
      <div className="pag pag-ancha" style={{ padding:"24px 28px 64px" }}>
      <IrA esc={budgetId} />
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:14, flexWrap:"wrap", gap:12 }}>
          <div>
            <h1 style={{ fontSize:22, fontWeight:700 }}>{t("title", { hotel: hotel.corto })}</h1>
            <p style={{ fontSize:12, color:"var(--text-secondary)" }}>{t("subtitle")}</p>
          </div>
          <div className="no-print" style={{ display:"flex", gap:8 }}>
            <button onClick={exportExcel} style={{ padding:"7px 14px", borderRadius:6, cursor:"pointer", background:"var(--accent-excel)", color:"#fff", border:"none", fontSize:13, fontWeight:600 }}>⬇ Excel</button>
            <button onClick={()=>window.print()} style={{ padding:"7px 14px", borderRadius:6, cursor:"pointer", background:"var(--bg-elevated)", color:"var(--text-primary)", border:"1px solid var(--border-medium)", fontSize:13, fontWeight:600 }}>🖨 PDF</button>
          </div>
        </div>

        <div className="no-print" style={{ display:"flex", gap:14, alignItems:"flex-end", marginBottom:18, flexWrap:"wrap" }}>
          <div><div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>Actual</div>
            <select value={actualId} onChange={e=>setActualId(e.target.value)} className="fin-input">{scenarios.map(s=><option key={s.id} value={s.id}>{scnLabel(s)}</option>)}</select></div>
          <div><div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>Budget</div>
            <select value={budgetId} onChange={e=>setBudgetId(e.target.value)} className="fin-input"><option value="">{tc("none")}</option>{scenarios.map(s=><option key={s.id} value={s.id}>{scnLabel(s)}</option>)}</select></div>
          <div><div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>{t("mesYtdHasta")}</div>
            <select value={month} onChange={e=>setMonth(Number(e.target.value))} className="fin-input">{MONTHS.map((m,i)=><option key={i+1} value={i+1}>{m}</option>)}</select></div>
        </div>

        {error && <div style={{ color:"var(--negative, #C0392B)", fontSize:13, marginBottom:8 }}>{error}</div>}
        {loading ? <div style={{ color:"var(--text-secondary)", padding:24 }}>{tc("loading")}</div> : !a ? null : (
          <div id="rep" className="fin-sticky" style={{ overflowX:"auto" }}>
            <table style={{ borderCollapse:"collapse", width:"100%", minWidth:760 }}>
              <thead>
                <tr style={{ borderBottom:"1px solid var(--border-medium)" }}>
                  <th style={{ textAlign:"left", padding:"6px 10px", fontSize:11 }} />
                  <th colSpan={4} style={{ ...th, textAlign:"center", borderLeft:"2px solid var(--border-medium)", color:"var(--text-primary)" }}>{t("mesUpper")} — {MONTHS[month-1]}</th>
                  <th colSpan={4} style={{ ...th, textAlign:"center", borderLeft:"2px solid var(--border-medium)", color:"var(--text-primary)" }}>YTD {MONTHS[month-1]}</th>
                </tr>
                <tr style={{ borderBottom:"1px solid var(--border-medium)", color:"var(--text-secondary)" }}>
                  <th style={{ textAlign:"left", padding:"6px 10px", fontSize:11 }}>{tc("indicator")}</th>
                  <th style={{ ...th, borderLeft:"2px solid var(--border-medium)" }}>Actual</th><th style={th}>Budget</th><th style={th}>Var $</th><th style={th}>Var %</th>
                  <th style={{ ...th, borderLeft:"2px solid var(--border-medium)" }}>Actual</th><th style={th}>Budget</th><th style={th}>Var $</th><th style={th}>Var %</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r,i) => (
                  <tr key={i} style={r.mt.strong?{ borderTop:"1px solid var(--border-medium)", fontWeight:700 }:undefined}>
                    <td style={{ padding:"5px 10px", fontSize:12, fontWeight:r.mt.strong?700:400, color:r.mt.strong?"var(--text-primary)":"var(--text-secondary)" }}>{r.mt.label}</td>
                    <td style={{ ...td, borderLeft:"2px solid var(--border-medium)", fontWeight:r.mt.strong?700:400 }}>{fmt(r.aM,r.mt.kind)}</td>
                    <td style={td}>{b?fmt(r.bM,r.mt.kind):"—"}</td>
                    <td style={{ ...td, color:b?pcol(r.vM):"var(--text-disabled)" }}>{b?fmt(r.vM,r.mt.kind):"—"}</td>
                    <td style={{ ...td, color:b?pcol(r.pM):"var(--text-disabled)" }}>{b?(r.pM*100).toFixed(1)+"%":"—"}</td>
                    <td style={{ ...td, borderLeft:"2px solid var(--border-medium)", fontWeight:r.mt.strong?700:400 }}>{fmt(r.aY,r.mt.kind)}</td>
                    <td style={td}>{b?fmt(r.bY,r.mt.kind):"—"}</td>
                    <td style={{ ...td, color:b?pcol(r.vY):"var(--text-disabled)" }}>{b?fmt(r.vY,r.mt.kind):"—"}</td>
                    <td style={{ ...td, color:b?pcol(r.pY):"var(--text-disabled)" }}>{b?(r.pY*100).toFixed(1)+"%":"—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{ fontSize:11, color:"var(--text-secondary)", marginTop:10 }}>{t("cashNote")}</p>
          </div>
        )}
      </div>
    </>
  );
}
