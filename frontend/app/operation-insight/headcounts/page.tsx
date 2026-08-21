"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getPayrollDeptReport, getPayrollDeptReportMonthly,
  downloadDeptFteTemplate, importDeptFte,
  type Scenario, type PayrollDeptReport, type PayrollDeptRow,
  type PayrollDeptMonthlyReport, type PayrollDeptMonthlyRow,
} from "@/lib/api";
import { bajarCuadros, type Cuadro, type FilaCuadro } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

const GOLD = "#c8a24a";
const int0 = (v: number) => Math.round(v).toLocaleString("en-US");
const m0 = (v: number) => "$" + Math.round(v).toLocaleString("en-US");
const f1 = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

type Merged = {
  dept_code: string; dept_name: string;
  aHc: number; bHc: number; aFte: number; bFte: number; aCost: number; bCost: number;
};
type View = "annual" | "monthly";
type Metric = "hc" | "fte" | "cost";

export default function HeadcountsPage() {
  const tc = useTranslations("common");
  const t = useTranslations("headcounts");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Cada selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca
  // se eligio abre con el preferido del owner.
  const [actualId, setActualId] = useEscenarioDe("operation-insight/headcounts:actual", scenarios, "actual");
  const [budgetId, setBudgetId] = useEscenarioDe("operation-insight/headcounts:budget", scenarios, "budget", undefined, true);
  const [view, setView] = useState<View>("annual");
  const [metric, setMetric] = useState<Metric>("hc");
  const [showSide, setShowSide] = useState<"actual" | "budget">("actual");
  const [aRep, setARep] = useState<PayrollDeptReport | null>(null);
  const [bRep, setBRep] = useState<PayrollDeptReport | null>(null);
  const [aMon, setAMon] = useState<PayrollDeptMonthlyReport | null>(null);
  const [bMon, setBMon] = useState<PayrollDeptMonthlyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Plantilla de FTE real por depto (cuando la planilla no viene cargada al
  // detalle, ej. un actual que solo trae costo del GL). Se baja/sube contra
  // `actualId` — la versión Actual que esté puesta en el selector de arriba.
  const [fteUploading, setFteUploading] = useState(false);
  const [fteMsg, setFteMsg] = useState<string | null>(null);
  const fteFileRef = useRef<HTMLInputElement>(null);

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

  const load = useCallback(async (aid: string, bid: string) => {
    if (!aid) return;
    setLoading(true); setError(null);
    try {
      const [a, b, am, bm] = await Promise.all([
        getPayrollDeptReport(aid),
        bid ? getPayrollDeptReport(bid) : Promise.resolve(null),
        getPayrollDeptReportMonthly(aid),
        bid ? getPayrollDeptReportMonthly(bid) : Promise.resolve(null),
      ]);
      setARep(a); setBRep(b); setAMon(am); setBMon(bm);
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (actualId) load(actualId, budgetId); }, [actualId, budgetId, load]);

  // ── Anual (Actual vs Budget) ────────────────────────────────────────────────
  const merged = useMemo<Merged[]>(() => {
    const map = new Map<string, Merged>();
    const seed = (code: string, name: string) => {
      let r = map.get(code);
      if (!r) { r = { dept_code: code, dept_name: name || code, aHc: 0, bHc: 0, aFte: 0, bFte: 0, aCost: 0, bCost: 0 }; map.set(code, r); }
      else if ((!r.dept_name || r.dept_name === r.dept_code) && name) r.dept_name = name;
      return r;
    };
    (aRep?.depts ?? []).forEach((d: PayrollDeptRow) => { const r = seed(d.dept_code, d.dept_name); r.aHc = d.headcount; r.aFte = d.fte_avg; r.aCost = d.total_annual; });
    (bRep?.depts ?? []).forEach((d: PayrollDeptRow) => { const r = seed(d.dept_code, d.dept_name); r.bHc = d.headcount; r.bFte = d.fte_avg; r.bCost = d.total_annual; });
    return [...map.values()].sort((a, b) => a.dept_code.localeCompare(b.dept_code));
  }, [aRep, bRep]);

  const tot = useMemo(() => merged.reduce((t, r) => ({
    aHc: t.aHc + r.aHc, bHc: t.bHc + r.bHc, aFte: t.aFte + r.aFte, bFte: t.bFte + r.bFte, aCost: t.aCost + r.aCost, bCost: t.bCost + r.bCost,
  }), { aHc: 0, bHc: 0, aFte: 0, bFte: 0, aCost: 0, bCost: 0 }), [merged]);

  // ── Mensual (12 meses) ──────────────────────────────────────────────────────
  const monRep = showSide === "actual" ? aMon : bMon;

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const dcol = (v: number) => Math.abs(v) < 0.0001 ? "var(--text-disabled)" : v > 0 ? "var(--positive)" : "var(--negative)";
  const th: React.CSSProperties = { padding: "10px 14px", fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.6, textAlign: "right", whiteSpace: "nowrap" };
  const td: React.CSSProperties = { padding: "10px 14px", fontSize: 13.5, textAlign: "right", color: "var(--text-primary)" };

  const sIcon = (v: number, suffix = "") => Math.abs(v) < 0.05 ? "—" : (v > 0 ? "+" : "−") + (suffix === "$" ? "$" + int0(Math.abs(v)) : (suffix === "f" ? f1(Math.abs(v)) : int0(Math.abs(v))));

  const seg = (active: boolean): React.CSSProperties => ({
    padding: "6px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer",
    background: active ? "var(--brand)" : "transparent", color: active ? "#fff" : "var(--text-secondary)",
    border: "none",
  });
  const segWrap: React.CSSProperties = { display: "flex", border: "1px solid var(--border-medium)", borderRadius: 6, overflow: "hidden", background: "var(--bg-input)" };

  const AnnualRow = ({ r, strong }: { r: Merged; strong?: boolean }) => {
    // Solo FTE en pantalla — HC y Costo salen de la vista anual (siguen en el
    // Excel exportado, que trae el detalle completo).
    const dFte = r.aFte - r.bFte;
    const bg = strong ? "linear-gradient(90deg, #16234d, #244481)" : undefined;
    const fg = strong ? "#fff" : "var(--text-primary)";
    return (
      <tr style={{ borderTop: "1px solid var(--border-subtle)", background: bg }}>
        <td style={{ ...td, textAlign: "left", fontWeight: strong ? 800 : 600, color: fg, whiteSpace: "nowrap" }}>
          {!strong && <span className="mono" style={{ color: "var(--text-disabled)", fontSize: 11, marginRight: 8 }}>{r.dept_code}</span>}
          {strong ? "TOTAL" : r.dept_name}
        </td>
        <td className="mono" style={{ ...td, fontWeight: strong ? 800 : 700, color: fg }}>{f1(r.aFte)}</td>
        <td className="mono" style={{ ...td, color: strong ? "#cdd6ea" : "var(--text-secondary)" }}>{f1(r.bFte)}</td>
        <td className="mono" style={{ ...td, fontWeight: 800, color: strong ? "#fff" : dcol(dFte) }}>{sIcon(dFte, "f")}</td>
      </tr>
    );
  };

  // valor de una celda mensual según métrica
  const cellVal = (row: PayrollDeptMonthlyRow | { headcount: number[]; fte: number[]; total: number[] }, m: number) =>
    metric === "hc" ? row.headcount[m] : metric === "fte" ? row.fte[m] : row.total[m];
  const fmtCell = (v: number) => metric === "hc" ? int0(v) : metric === "fte" ? f1(v) : m0(v);
  // resumen de fila (col final): HC/FTE → promedio; Costo → total
  const rowSummary = (row: { headcount: number[]; fte: number[]; total: number[]; total_annual?: number }) => {
    if (metric === "cost") return row.total_annual ?? row.total.reduce((a, b) => a + b, 0);
    const arr = metric === "hc" ? row.headcount : row.fte;
    return arr.reduce((a, b) => a + b, 0) / 12;
  };
  const summaryLabel = metric === "cost" ? tc("total") : t("prom");
  const metricLabel = metric === "hc" ? t("posiciones") : metric === "fte" ? "FTE" : t("costoCargas");
  const colFinal = metric === "cost" ? t("colFinalTotal") : t("colFinalProm");

  // ── Bajar a Excel ──────────────────────────────────────────────────────────
  // Salen las DOS vistas en el mismo libro (anual y los 12 meses), aunque en
  // pantalla haya una sola a la vista: cambiar de vista es para leer, no para
  // recortar el archivo que uno se lleva. La hoja mensual respeta la métrica y
  // el lado (Actual/Budget) elegidos, que es lo que define qué números son.
  async function bajarExcel() {
    setError(null);
    const aScn = scenarios.find(s => s.id === actualId), bScn = scenarios.find(s => s.id === budgetId);
    const nA = aScn ? scnLabel(aScn) : "Actual", nB = bScn ? scnLabel(bScn) : "Budget";
    const cuadros: Cuadro[] = [];

    if (merged.length) {
      const fila = (r: Merged, total?: boolean): FilaCuadro => ({
        label: total ? "TOTAL" : `${r.dept_code} · ${r.dept_name}`,
        es_total: !!total,
        valores: [
          r.aHc, r.bHc, r.aHc - r.bHc,
          r.aFte, r.bFte, r.aFte - r.bFte,
          r.aCost, r.bCost, r.aCost - r.bCost,
          r.bCost ? (r.aCost - r.bCost) / Math.abs(r.bCost) : null,
        ],
      });
      cuadros.push({
        titulo: t("excelTituloAnual"),
        subtitulo: t("excelSubtituloAnual", { a: nA, b: nB }),
        hoja: tc("annual"),
        columnas: [
          { label: tc("department"), ancho: 34, formato: "texto" },
          { label: `HC ${nA}`, ancho: 12, formato: "num" },
          { label: `HC ${nB}`, ancho: 12, formato: "num" },
          { label: "Δ HC", ancho: 10, formato: "num" },
          { label: `FTE ${nA}`, ancho: 12, formato: "num1" },
          { label: `FTE ${nB}`, ancho: 12, formato: "num1" },
          { label: "Δ FTE", ancho: 10, formato: "num1" },
          { label: `${t("costo")} ${nA}`, ancho: 16, formato: "usd" },
          { label: `${t("costo")} ${nB}`, ancho: 16, formato: "usd" },
          { label: `Δ ${t("costo")}`, ancho: 16, formato: "usd" },
          { label: "Var %", ancho: 10, formato: "pct" },
        ],
        filas: [...merged.map(r => fila(r)), fila({ dept_code: "", dept_name: "TOTAL", ...tot }, true)],
      });
    }

    if (monRep && monRep.depts.length) {
      const fmt = metric === "cost" ? ("usd" as const) : metric === "fte" ? ("num1" as const) : ("num" as const);
      const filas: FilaCuadro[] = monRep.depts.map(r => ({
        label: `${r.dept_code} · ${r.dept_name}`,
        valores: [...MONTHS.map((_, m) => cellVal(r, m)), rowSummary(r)],
      }));
      filas.push({
        label: "TOTAL", es_total: true,
        valores: [...MONTHS.map((_, m) => cellVal(monRep.totals, m)), rowSummary(monRep.totals)],
      });
      cuadros.push({
        titulo: t("excelTituloMensual", { metric: metricLabel }),
        subtitulo: t("excelSubtituloMensual", { scn: showSide === "actual" ? nA : nB, colFinal }),
        hoja: t("mensual"),
        columnas: [
          { label: tc("department"), ancho: 34, formato: "texto" },
          ...MONTHS.map(m => ({ label: m, ancho: 12, formato: fmt })),
          { label: summaryLabel, ancho: 14, formato: fmt },
        ],
        filas,
      });
    }

    if (!cuadros.length) { setError(t("sinDatosExport")); return; }
    try { await bajarCuadros("Headcounts", cuadros); }
    catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }

  // ── Plantilla de FTE real por depto: bajar / subir ──────────────────────────
  // Va contra `actualId` — la versión activa del selector "Actual" de arriba,
  // no una elegida aparte. Un depto que ya tiene planilla cargada al detalle
  // no necesita esto; existe para el que no la tiene y el FTE calculado da 0.
  async function bajarPlantillaFte() {
    if (!actualId) return;
    setFteMsg(null);
    try {
      const blob = await downloadDeptFteTemplate(actualId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `FTE_Real_${actualId.slice(0, 8)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setFteMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
  }
  async function subirPlantillaFte(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !actualId) return;
    setFteUploading(true); setFteMsg(null);
    try {
      const r = await importDeptFte(actualId, file, false);
      setFteMsg(t("fteCargado", { meses: r.months_present.join(", "), filas: r.rows }));
      const a = await getPayrollDeptReport(actualId);
      const am = await getPayrollDeptReportMonthly(actualId);
      setARep(a); setAMon(am);
    } catch (ex) {
      setFteMsg(`Error: ${ex instanceof Error ? ex.message : String(ex)}`);
    } finally {
      setFteUploading(false);
      if (fteFileRef.current) fteFileRef.current.value = "";
    }
  }

  return (
    <div className={`print-dashboard pag ${view === "monthly" ? "pag-ancha" : "pag-media"}`} style={{ padding: "20px 20px 44px" }}>
      <IrA esc={budgetId} />
      <div style={{ textAlign: "center", marginBottom: 6 }}>
        <h1 style={{ fontSize: 34, fontWeight: 800, margin: 0, letterSpacing: -0.5 }}>
          <span style={{ color: "var(--text-primary)" }}>Headcounts </span><span style={{ color: "var(--brand)" }}>{t("porDepartamento")}</span>
        </h1>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginTop: 6 }}>
          <span style={{ height: 2, width: 60, background: "var(--border-medium)" }} />
          <span style={{ fontSize: 14, color: "var(--text-secondary)", fontWeight: 600 }}>
            {view === "annual" ? <>Actual vs Budget <span style={{ color: GOLD, fontWeight: 800 }}>|</span> {t("fteAnual")}</>
              : <>{t("doceMeses")} <span style={{ color: GOLD, fontWeight: 800 }}>|</span> {t("porMes", { metric: metricLabel })}</>}
          </span>
          <span style={{ height: 2, width: 60, background: "var(--border-medium)" }} />
        </div>
      </div>

      <div className="no-print" style={{ display: "flex", gap: 10, justifyContent: "center", alignItems: "flex-end", margin: "16px 0 22px", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Actual</span><select value={actualId} onChange={e => setActualId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Budget</span><select value={budgetId} onChange={e => setBudgetId(e.target.value)} style={sel}><option value="" style={{ background: "var(--bg-input)" }}>{tc("none")}</option>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("vista")}</span>
          <div style={segWrap}><button onClick={() => setView("annual")} style={seg(view === "annual")}>{tc("annual")}</button><button onClick={() => setView("monthly")} style={seg(view === "monthly")}>{t("mensual")}</button></div>
        </div>
        {view === "monthly" && <>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("metric")}</span>
            <div style={segWrap}><button onClick={() => setMetric("hc")} style={seg(metric === "hc")}>HC</button><button onClick={() => setMetric("fte")} style={seg(metric === "fte")}>FTE</button><button onClick={() => setMetric("cost")} style={seg(metric === "cost")}>{t("costo")}</button></div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("mostrar")}</span>
            <div style={segWrap}><button onClick={() => setShowSide("actual")} style={seg(showSide === "actual")}>Actual</button><button onClick={() => setShowSide("budget")} style={seg(showSide === "budget")} disabled={!budgetId}>Budget</button></div>
          </div>
        </>}
        <button onClick={bajarExcel} title={t("excelBtnTitle")} style={{ alignSelf: "flex-end", padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>⬇ Excel</button>
        <button onClick={() => window.print()} style={{ alignSelf: "flex-end", padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)" }}>{tc("print")}</button>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("fteRealLabel")}</span>
          <div style={{ display: "flex", gap: 6 }}>
            <button onClick={bajarPlantillaFte} disabled={!actualId} title={t("ftePlantillaTitle")} style={{ padding: "7px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: actualId ? "pointer" : "default", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>{t("plantillaBtn")}</button>
            <input ref={fteFileRef} type="file" accept=".xlsx" style={{ display: "none" }} onChange={subirPlantillaFte} />
            <button onClick={() => fteFileRef.current?.click()} disabled={!actualId || fteUploading} title={t("fteSubirTitle")} style={{ padding: "7px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: (!actualId || fteUploading) ? "default" : "pointer", background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>{fteUploading ? t("uploading") : t("subirBtn")}</button>
          </div>
        </div>
      </div>
      {fteMsg && <div style={{ color: fteMsg.startsWith("Error") ? "var(--negative)" : "var(--positive)", fontSize: 12.5, marginBottom: 8, textAlign: "center" }}>{fteMsg}</div>}

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8, textAlign: "center" }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13, textAlign: "center" }}>{tc("loading")}</div>}

      {/* ── ANUAL ── */}
      {!loading && view === "annual" && merged.length > 0 && (
        <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "var(--bg-header)" }}>
                <th style={{ ...th, textAlign: "left" }}>{tc("department")}</th>
                <th style={th}>FTE Act</th><th style={th}>FTE Bud</th><th style={th}>Δ FTE</th>
              </tr>
            </thead>
            <tbody>
              {merged.map((r) => <AnnualRow key={r.dept_code} r={r} />)}
              <AnnualRow r={{ dept_code: "", dept_name: "TOTAL", ...tot }} strong />
            </tbody>
          </table>
        </div>
      )}

      {/* ── MENSUAL ── */}
      {!loading && view === "monthly" && monRep && monRep.depts.length > 0 && (
        <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1100 }}>
            <thead>
              <tr style={{ background: "var(--bg-header)" }}>
                <th style={{ ...th, textAlign: "left", position: "sticky", left: 0, background: "var(--bg-header)" }}>{tc("department")}</th>
                {MONTHS.map(m => <th key={m} style={{ ...th, padding: "10px 8px" }}>{m}</th>)}
                <th style={{ ...th, color: GOLD }}>{summaryLabel}</th>
              </tr>
            </thead>
            <tbody>
              {monRep.depts.map((r) => (
                <tr key={r.dept_code} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                  <td style={{ ...td, textAlign: "left", fontWeight: 600, whiteSpace: "nowrap", position: "sticky", left: 0, background: "var(--bg-elevated)" }}>
                    <span className="mono" style={{ color: "var(--text-disabled)", fontSize: 11, marginRight: 8 }}>{r.dept_code}</span>{r.dept_name}
                  </td>
                  {MONTHS.map((_, m) => {
                    const v = cellVal(r, m);
                    return <td key={m} className="mono" style={{ ...td, padding: "10px 8px", color: v ? "var(--text-primary)" : "var(--text-disabled)" }}>{v ? fmtCell(v) : "—"}</td>;
                  })}
                  <td className="mono" style={{ ...td, fontWeight: 800, color: GOLD }}>{fmtCell(rowSummary(r))}</td>
                </tr>
              ))}
              <tr style={{ borderTop: "1px solid var(--border-subtle)", background: "linear-gradient(90deg, #16234d, #244481)" }}>
                <td style={{ ...td, textAlign: "left", fontWeight: 800, color: "#fff", position: "sticky", left: 0, background: "var(--accent-total)" }}>TOTAL</td>
                {MONTHS.map((_, m) => <td key={m} className="mono" style={{ ...td, padding: "10px 8px", fontWeight: 800, color: "#fff" }}>{fmtCell(cellVal(monRep.totals, m))}</td>)}
                <td className="mono" style={{ ...td, fontWeight: 800, color: "#fff" }}>{fmtCell(rowSummary(monRep.totals))}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {!loading && ((view === "annual" && merged.length === 0) || (view === "monthly" && (!monRep || monRep.depts.length === 0))) && !error && (
        <div style={{ color: "var(--text-secondary)", fontSize: 13, textAlign: "center", marginTop: 24 }}>
          {t("sinPlanilla", { lado: view === "monthly" ? (showSide === "actual" ? "Actual" : "Budget") : "" })}
        </div>
      )}

      {!loading && (
        <div style={{ marginTop: 18, display: "flex", justifyContent: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "11px 20px", fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 820 }}>
            <span style={{ width: 22, height: 22, borderRadius: "50%", background: "var(--brand)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, flexShrink: 0 }}>i</span>
            {view === "annual"
              ? <>{t("hcHint")}</>
              : <>{t("hintMensual", { colFinal })}</>}
          </div>
        </div>
      )}
    </div>
  );
}
