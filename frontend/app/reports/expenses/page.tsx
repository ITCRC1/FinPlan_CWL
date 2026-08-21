"use client";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import {
  getScenarios, getOpexReport, getCostsReport, getRevenueDetailReport, getBelowGopReport,
  type Scenario, type DeptAccountReport,
} from "@/lib/api";
import { deptName } from "@/lib/cwl-depts";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID, hotelShort } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import IrA from "@/components/IrA";

const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const usd0 = (n: number) => { const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); return n < 0 ? `(${s})` : s; };

type Kind = "opex" | "costs" | "revenue" | "belowgop";

export default function ExpensesReportPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("expenses");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // El selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se
  // eligio abre con el preferido del owner.
  const [scenarioId, setScenarioId] = useEscenarioDe("reports/expenses:budget", scenarios, "budget", undefined, true);
  const [kind, setKind] = useState<Kind>("opex");
  const [data, setData] = useState<DeptAccountReport | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
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

  const load = useCallback(async (sid: string, k: Kind) => {
    if (!sid) return;
    setLoading(true); setError(null);
    try { setData(k === "opex" ? await getOpexReport(sid) : k === "costs" ? await getCostsReport(sid) : k === "revenue" ? await getRevenueDetailReport(sid) : await getBelowGopReport(sid)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (scenarioId) load(scenarioId, kind); }, [scenarioId, kind, load]);

  const depts = data?.depts ?? [];
  const grand = depts.reduce((s, d) => s + d.annual, 0);
  const title = kind === "opex" ? "Gastos Operativos (OPEX)" : kind === "costs" ? "Costos de Venta" : kind === "revenue" ? "Ingresos por cuenta" : "Gastos del Propietario (Below-GOP)";

  const exportExcel = useCallback(async () => {
    if (!data) return;
    // La jerarquía va en `nivel` (sangría real de Excel). Antes se simulaba con
    // espacios dentro del texto: ordenar o copiar la columna la borraba.
    const filas: FilaCuadro[] = [];
    depts.forEach(d => {
      filas.push({ label: `${deptName(d.dept_code)} (${d.dept_code})`, nivel: 0, es_total: true, valores: [d.annual] });
      d.accounts.forEach(a => filas.push({ label: `${a.account_code} ${a.account_name}`, nivel: 1, valores: [a.annual] }));
    });
    filas.push({ label: "TOTAL", nivel: 0, es_total: true, valores: [grand] });
    const hoja = kind === "opex" ? "OPEX" : kind === "costs" ? "Costos de Venta"
               : kind === "revenue" ? "Ingresos" : "Below-GOP";
    try {
      await bajarCuadros(`${kind}_x_dept`, [{
        titulo: `${title} por departamento y cuenta — ${hotelShort()}`,
        subtitulo: "Anual · USD",
        hoja,
        columnas: [
          { label: "Departamento / Cuenta", ancho: 52, formato: "texto" },
          { label: "Anual USD", ancho: 16, formato: "usd" },
        ],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo generar el Excel"); }
  }, [data, depts, grand, title, kind]);

  const td: React.CSSProperties = { textAlign:"right", padding:"5px 12px", fontSize:12, fontFamily:"var(--font-mono)" };

  return (
    <>
      <style>{`@media print{.no-print{display:none!important}body *{visibility:hidden}#rep,#rep *{visibility:visible}#rep{position:absolute;inset:0;padding:16px}}`}</style>
      <div className="pag pag-lectura" style={{ padding:"24px 28px 64px" }}>
      <IrA esc={scenarioId} />
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:14, flexWrap:"wrap", gap:12 }}>
          <div>
            <h1 style={{ fontSize:22, fontWeight:700 }}>{title} — {hotel.corto}</h1>
            <p style={{ fontSize:12, color:"var(--text-secondary)" }}>{t("subtitle")}</p>
          </div>
          <div className="no-print" style={{ display:"flex", gap:8 }}>
            <button onClick={exportExcel} style={{ padding:"7px 14px", borderRadius:6, cursor:"pointer", background:"var(--accent-excel)", color:"#fff", border:"none", fontSize:13, fontWeight:600 }}>⬇ Excel</button>
            <button onClick={()=>window.print()} style={{ padding:"7px 14px", borderRadius:6, cursor:"pointer", background:"var(--bg-elevated)", color:"var(--text-primary)", border:"1px solid var(--border-medium)", fontSize:13, fontWeight:600 }}>🖨 PDF</button>
          </div>
        </div>

        <div className="no-print" style={{ display:"flex", gap:14, alignItems:"flex-end", marginBottom:18, flexWrap:"wrap" }}>
          <div><div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>{tc("scenario")}</div>
            <select value={scenarioId} onChange={e=>setScenarioId(e.target.value)} className="fin-input">{scenarios.map(s=><option key={s.id} value={s.id}>{scnLabel(s)}</option>)}</select></div>
          <div><div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>Tipo</div>
            <select value={kind} onChange={e=>setKind(e.target.value as Kind)} className="fin-input">
              <option value="opex">Gastos Operativos (OPEX)</option>
              <option value="costs">{t("costOfSales")}</option>
              <option value="revenue">{t("revenueByAccount")}</option>
              <option value="belowgop">{t("ownerExpenses")}</option>
            </select></div>
        </div>

        {error && <div style={{ color:"var(--negative, #C0392B)", fontSize:13, marginBottom:8 }}>{error}</div>}
        {loading ? <div style={{ color:"var(--text-secondary)", padding:24 }}>{tc("loading")}</div> : !data ? null : (
          <div id="rep" className="fin-sticky" style={{ overflowX:"auto" }}>
            {!depts.length && <div style={{ fontSize:12, color:"var(--accent-amber, #856404)", marginBottom:8 }}>Este escenario no tiene {title.toLowerCase()} en checkbook (vive en presupuestos/forecasts).</div>}
            <table style={{ borderCollapse:"collapse", width:"100%", minWidth:560 }}>
              <thead>
                <tr style={{ borderBottom:"2px solid var(--border-medium)", color:"var(--text-secondary)" }}>
                  <th style={{ textAlign:"left", padding:"6px 12px", fontSize:11 }}>Departamento / Cuenta</th>
                  <th style={{ textAlign:"right", padding:"6px 12px", fontSize:11 }}>{tc("annual")}</th>
                </tr>
              </thead>
              <tbody>
                {depts.map(d => {
                  const isOpen = open[d.dept_code] ?? false;
                  return (
                    <>
                      <tr key={d.dept_code} style={{ borderTop:"1px solid var(--border-medium)", cursor:"pointer" }}
                        onClick={()=>setOpen(o=>({...o,[d.dept_code]: !isOpen}))}>
                        <td style={{ padding:"6px 12px", fontSize:12, fontWeight:600, color:"var(--text-primary)" }}>
                          {isOpen ? "▾ " : "▸ "}{deptName(d.dept_code)} <span style={{ color:"var(--text-disabled)", fontWeight:400 }}>({d.dept_code})</span>
                        </td>
                        <td style={{ ...td, fontWeight:700 }}>{usd0(d.annual)}</td>
                      </tr>
                      {isOpen && d.accounts.map(a => (
                        <tr key={d.dept_code+a.account_code}>
                          <td style={{ padding:"4px 12px 4px 30px", fontSize:12, color:"var(--text-secondary)" }}>{a.account_code} {a.account_name}</td>
                          <td style={td}>{usd0(a.annual)}</td>
                        </tr>
                      ))}
                    </>
                  );
                })}
                <tr style={{ borderTop:"2px solid var(--border-medium)", fontWeight:700 }}>
                  <td style={{ padding:"6px 12px", fontSize:12 }}>TOTAL</td>
                  <td style={td}>{usd0(grand)}</td>
                </tr>
              </tbody>
            </table>
            <p style={{ fontSize:11, color:"var(--text-secondary)", marginTop:10 }}>{t("clickHint")}</p>
          </div>
        )}
      </div>
    </>
  );
}
