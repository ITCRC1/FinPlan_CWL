"use client";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID, hotelShort } from "@/lib/hotel";
import IrA from "@/components/IrA";
import {
  getScenarios, getPayrollDeptReport,
  type Scenario, type PayrollDeptReport,
} from "@/lib/api";

const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const usd0 = (n: number) => { const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); return n < 0 ? `(${s})` : s; };
const fte = (n: number) => n.toFixed(1);

export default function PayrollDeptReportPage() {
  const tc = useTranslations("common");
  // `t` ya está tomado más abajo en este archivo (los totales).
  const tPd = useTranslations("payrollDept");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // La planilla detallada (posiciones) vive en presupuestos/forecasts, por eso
  // el rol es "budget". El selector se acuerda de lo ultimo elegido EN ESTA
  // pantalla, y si nunca se eligio abre con el preferido del owner.
  const [scenarioId, setScenarioId] = useEscenarioDe("reports/payroll-dept:budget", scenarios, "budget", undefined, true);
  const [data, setData] = useState<PayrollDeptReport | null>(null);
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

  const load = useCallback(async (sid: string) => {
    if (!sid) return;
    setLoading(true); setError(null);
    try { setData(await getPayrollDeptReport(sid)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const rows = data?.depts ?? [];
  const t = data?.totals;

  const exportExcel = useCallback(async () => {
    if (!data) return;
    const filas: FilaCuadro[] = rows.map(r => ({
      label: r.dept_name,
      valores: [r.headcount, r.fte_avg, r.sw_annual, r.total_annual],
    }));
    if (t) filas.push({ label: "TOTAL", es_total: true,
      valores: [t.headcount, t.fte_avg, t.sw_annual, t.total_annual] });
    try {
      await bajarCuadros("Planilla_x_Dept", [{
        titulo: tPd("title", { hotel: hotelShort() }),
        subtitulo: tPd("subtitle"),
        hoja: "Planilla x Dept",
        columnas: [
          { label: tc("department"), ancho: 34, formato: "texto" },
          { label: "Headcount", ancho: 12, formato: "num" },
          { label: tPd("ftePromCol"), ancho: 12, formato: "num1" },
          { label: tPd("baseSalaryCol"), ancho: 20, formato: "usd" },
          { label: tPd("totalCostCol"), ancho: 22, formato: "usd" },
        ],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : tPd("excelFallo")); }
  }, [data, rows, t, tPd, tc]);

  const th: React.CSSProperties = { textAlign:"right", padding:"6px 12px", fontSize:11, fontWeight:600 };
  const td: React.CSSProperties = { textAlign:"right", padding:"5px 12px", fontSize:12, fontFamily:"var(--font-mono)" };

  return (
    <>
      <style>{`@media print{.no-print{display:none!important}body *{visibility:hidden}#rep,#rep *{visibility:visible}#rep{position:absolute;inset:0;padding:16px}}`}</style>
      <div className="pag pag-media" style={{ padding:"24px 28px 64px" }}>
      <IrA esc={scenarioId} />
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:14, flexWrap:"wrap", gap:12 }}>
          <div>
            <h1 style={{ fontSize:22, fontWeight:700 }}>{tPd("title", { hotel: hotelShort() })}</h1>
            <p style={{ fontSize:12, color:"var(--text-secondary)" }}>{tPd("subtitle")}</p>
          </div>
          <div className="no-print" style={{ display:"flex", gap:8 }}>
            <button onClick={exportExcel} style={{ padding:"7px 14px", borderRadius:6, cursor:"pointer", background:"var(--accent-excel)", color:"#fff", border:"none", fontSize:13, fontWeight:600 }}>⬇ Excel</button>
            <button onClick={()=>window.print()} style={{ padding:"7px 14px", borderRadius:6, cursor:"pointer", background:"var(--bg-elevated)", color:"var(--text-primary)", border:"1px solid var(--border-medium)", fontSize:13, fontWeight:600 }}>🖨 PDF</button>
          </div>
        </div>

        <div className="no-print" style={{ display:"flex", gap:14, alignItems:"flex-end", marginBottom:18 }}>
          <div><div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>{tc("scenario")}</div>
            <select value={scenarioId} onChange={e=>setScenarioId(e.target.value)} className="fin-input">{scenarios.map(s=><option key={s.id} value={s.id}>{scnLabel(s)}</option>)}</select></div>
        </div>

        {error && <div style={{ color:"var(--negative, #C0392B)", fontSize:13, marginBottom:8 }}>{error}</div>}
        {loading ? <div style={{ color:"var(--text-secondary)", padding:24 }}>{tc("loading")}</div> : !data ? null : (
          <div id="rep" className="fin-sticky" style={{ overflowX:"auto" }}>
            {(!rows.length || (t && t.total_annual === 0)) &&
              <div style={{ fontSize:12, color:"var(--accent-amber, #856404)", marginBottom:8 }}>{tPd("noDetail")}</div>}
            <table style={{ borderCollapse:"collapse", width:"100%", minWidth:640 }}>
              <thead>
                <tr style={{ borderBottom:"2px solid var(--border-medium)", color:"var(--text-secondary)" }}>
                  <th style={{ textAlign:"left", padding:"6px 12px", fontSize:11 }}>{tc("department")}</th>
                  <th style={th}>Headcount</th><th style={th}>{tPd("ftePromCol")}</th>
                  <th style={th}>{tPd("baseSalary")}</th><th style={th}>{tPd("totalCost")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.dept_code} style={{ borderBottom:"1px solid var(--border-light, rgba(255,255,255,0.05))" }}>
                    <td style={{ padding:"5px 12px", fontSize:12, color:"var(--text-primary)" }}>{r.dept_name}</td>
                    <td style={td}>{r.headcount}</td><td style={td}>{fte(r.fte_avg)}</td>
                    <td style={td}>{usd0(r.sw_annual)}</td><td style={{ ...td, fontWeight:600 }}>{usd0(r.total_annual)}</td>
                  </tr>
                ))}
                {t && (
                  <tr style={{ borderTop:"2px solid var(--border-medium)", fontWeight:700 }}>
                    <td style={{ padding:"6px 12px", fontSize:12 }}>TOTAL</td>
                    <td style={td}>{t.headcount}</td><td style={td}>{fte(t.fte_avg)}</td>
                    <td style={td}>{usd0(t.sw_annual)}</td><td style={td}>{usd0(t.total_annual)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
