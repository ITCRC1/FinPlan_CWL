"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { HOTEL_ID, hotelShort } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import {
  getScenarios, getPLCompare,
  type Scenario, type PLCompare, type PLColumn, type PLCompareVersion,
} from "@/lib/api";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
function fmtUSD(n: number) {
  if (Math.abs(n) < 0.5) return "-";
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${s})` : s;
}
const lineAmt = (col: PLColumn | undefined, code: string) =>
  col?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;

type Horizon = "month" | "ytd" | "full";
type RoleId = { actual: string; budget: string; reforecast: string; forecast: string; ly: string };

export default function PLFullReportPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("pl");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Cinco selectores, cinco llaves: con una sola, elegir en una columna le
  // cambiaria el escenario a las otras cuatro. Cada una abre con el preferido
  // del owner mientras nadie la haya movido a mano.
  const [actualId,     setActualId]     = useEscenarioDe("reports/pl-full:actual",     scenarios, "actual");
  const [budgetId,     setBudgetId]     = useEscenarioDe("reports/pl-full:budget",     scenarios, "budget", undefined, true);
  // Reforecast y Forecast son los dos del mismo tipo: arrancan en el mismo
  // Forecast preferido y se separan en cuanto el owner mueva uno.
  const [reforecastId, setReforecastId] = useEscenarioDe("reports/pl-full:reforecast", scenarios, "forecast");
  const [forecastId,   setForecastId]   = useEscenarioDe("reports/pl-full:forecast",   scenarios, "forecast");
  // "LY" es el año cerrado anterior, no el actual.
  const [lyId,         setLyId]         = useEscenarioDe("reports/pl-full:ly",         scenarios, "actualAnterior");
  const roles = useMemo<RoleId>(
    () => ({ actual: actualId, budget: budgetId, reforecast: reforecastId, forecast: forecastId, ly: lyId }),
    [actualId, budgetId, reforecastId, forecastId, lyId],
  );
  const setRole: Record<keyof RoleId, (id: string) => void> = {
    actual: setActualId, budget: setBudgetId, reforecast: setReforecastId,
    forecast: setForecastId, ly: setLyId,
  };
  const [month, setMonth] = useState(5);
  const [cmp, setCmp] = useState<PLCompare | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // La eleccion de cada columna la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (r: RoleId, m: number) => {
    const ids = [...new Set(Object.values(r).filter(Boolean))];
    if (!ids.length) return;
    setLoading(true); setError(null);
    try { setCmp(await getPLCompare(ids, m)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(roles, month); }, [roles, month, load]);

  const byId = useMemo(() => {
    const m: Record<string, PLCompareVersion> = {};
    (cmp?.versions ?? []).forEach(v => { m[v.scenario_id] = v; });
    return m;
  }, [cmp]);

  const col = (id: string, h: Horizon): PLColumn | undefined => id ? byId[id]?.[h] : undefined;
  const amt = (id: string, h: Horizon, code: string) => lineAmt(col(id, h), code);

  // Row template = lines from any present full column (budget preferred)
  const rows = useMemo(() => {
    const src = col(roles.budget, "full") ?? col(roles.actual, "full") ?? cmp?.versions[0]?.full;
    return src?.lines ?? [];
  }, [cmp, roles, byId]); // eslint-disable-line react-hooks/exhaustive-deps

  // 13 columns: Month(A,B,Var,RF) · YTD(A,B,Var,RF) · Full(F,B,Var,RF,LY)
  const colDefs: { h: Horizon; role: keyof RoleId | "var"; varOf?: [keyof RoleId, keyof RoleId] }[] = [
    { h:"month", role:"actual" }, { h:"month", role:"budget" }, { h:"month", role:"var", varOf:["actual","budget"] }, { h:"month", role:"reforecast" },
    { h:"ytd", role:"actual" }, { h:"ytd", role:"budget" }, { h:"ytd", role:"var", varOf:["actual","budget"] }, { h:"ytd", role:"reforecast" },
    { h:"full", role:"forecast" }, { h:"full", role:"budget" }, { h:"full", role:"var", varOf:["forecast","budget"] }, { h:"full", role:"reforecast" }, { h:"full", role:"ly" },
  ];
  const cellVal = (code: string, cd: typeof colDefs[number]): number => {
    if (cd.role === "var") { const [x,y]=cd.varOf!; return amt(roles[x],cd.h,code) - amt(roles[y],cd.h,code); }
    return amt(roles[cd.role as keyof RoleId], cd.h, code);
  };

  const subHead = ["Actual","Budget","Var","Reforecast","Actual","Budget","Var","Reforecast","Forecast","Budget","Var","Reforecast","Actual LY"];

  // Sin escenario asignado a un rol la celda va vacía, no en cero: "no hay
  // dato" y "cero" no son lo mismo en un P&L.
  const cellValOrNull = (code: string, cd: typeof colDefs[number]): number | null => {
    const ids = cd.role === "var" ? [roles[cd.varOf![0]], roles[cd.varOf![1]]] : [roles[cd.role as keyof RoleId]];
    if (ids.some(id => !id)) return null;
    return cellVal(code, cd);
  };

  const exportExcel = useCallback(async () => {
    if (!rows.length) return;
    const grupo = (i: number) => i < 4 ? `${t("mesUpper")} ${MONTHS[month-1]}` : i < 8 ? `YTD ${MONTHS[month-1]}` : "FULL YEAR";
    const filas: FilaCuadro[] = rows.map(ln => {
      const isTotal = /^(TOTAL_|GOP|EBITDA|EBT|NET_PROFIT)/.test(ln.line_code);
      return {
        label: ln.line_name, nivel: isTotal ? 0 : 1, es_total: isTotal,
        valores: colDefs.map(cd => cellValOrNull(ln.line_code, cd)),
      };
    });
    try {
      await bajarCuadros(`Full_PL_${MONTHS[month-1]}`, [{
        titulo: `Full P&L — ${hotelShort()}`,
        subtitulo: t("excelSubtitulo", { mes: MONTHS[month-1] }),
        hoja: "Full P&L",
        columnas: [
          { label: tc("line"), ancho: 40, formato: "texto" },
          // El grupo va pegado al nombre: el exportador tiene una sola fila de
          // cabecera, y sin el grupo hay cuatro "Budget" indistinguibles.
          ...colDefs.map((_, i) => ({ label: `${grupo(i)}\n${subHead[i]}`, ancho: 15, formato: "usd" as const })),
        ],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }, [rows, roles, month, byId]); // eslint-disable-line react-hooks/exhaustive-deps

  const th: React.CSSProperties = { textAlign:"right", padding:"4px 7px", fontSize:10, fontWeight:600, whiteSpace:"nowrap" };
  const td: React.CSSProperties = { textAlign:"right", padding:"3px 7px", fontSize:11, fontFamily:"var(--font-mono)", whiteSpace:"nowrap" };
  const groupBorder = "2px solid var(--border-medium)";

  const roleSel = (key: keyof RoleId, label: string) => (
    <div>
      <div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>{label}</div>
      <select value={roles[key]} onChange={e=>setRole[key](e.target.value)} className="fin-input" style={{ fontSize:12 }}>
        <option value="">{tc("none")}</option>
        {scenarios.map(s=><option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
      </select>
    </div>
  );

  return (
    <>
      <style>{`@media print { .no-print{display:none!important} body *{visibility:hidden} #rep,#rep *{visibility:visible} #rep{position:absolute;inset:0;padding:10px} table{font-size:8px!important} td,th{padding:2px 4px!important} }`}</style>
      <div className="pag pag-ancha" style={{ padding:"24px 28px 64px" }}>
      <IrA esc={budgetId} />
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:14, flexWrap:"wrap", gap:12 }}>
          <div>
            <h1 style={{ fontSize:22, fontWeight:700 }}>{t("fullExecTitle", { hotel: hotel.corto })}</h1>
            <p style={{ fontSize:12, color:"var(--text-secondary)" }}>{t("fullSubtitle")}</p>
          </div>
          <div className="no-print" style={{ display:"flex", gap:8 }}>
            <button onClick={exportExcel} style={{ padding:"7px 14px", borderRadius:6, cursor:"pointer", background:"var(--accent-excel)", color:"#fff", border:"none", fontSize:13, fontWeight:600 }}>⬇ Excel</button>
            <button onClick={()=>window.print()} style={{ padding:"7px 14px", borderRadius:6, cursor:"pointer", background:"var(--bg-elevated)", color:"var(--text-primary)", border:"1px solid var(--border-medium)", fontSize:13, fontWeight:600 }}>🖨 PDF</button>
          </div>
        </div>

        <div className="no-print" style={{ display:"flex", gap:12, alignItems:"flex-end", marginBottom:18, flexWrap:"wrap" }}>
          {roleSel("actual","Actual")}
          {roleSel("budget","Budget")}
          {roleSel("reforecast","Reforecast")}
          {roleSel("forecast","Forecast (Full Year)")}
          {roleSel("ly", t("lastYear"))}
          <div>
            <div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>{t("mesYtdHasta")}</div>
            <select value={month} onChange={e=>setMonth(Number(e.target.value))} className="fin-input" style={{ fontSize:12 }}>
              {MONTHS.map((m,i)=><option key={i+1} value={i+1}>{m}</option>)}
            </select>
          </div>
        </div>

        {error && <div style={{ color:"var(--negative, #C0392B)", fontSize:13, marginBottom:8 }}>{error}</div>}
        {loading ? <div style={{ color:"var(--text-secondary)", padding:24 }}>{tc("loading")}</div> : !rows.length ? null : (
          <div id="rep" className="fin-sticky" style={{ overflowX:"auto" }}>
            <table style={{ borderCollapse:"collapse", minWidth:1100 }}>
              <thead>
                <tr style={{ borderBottom:"1px solid var(--border-medium)" }}>
                  <th style={{ textAlign:"left", padding:"4px 8px", fontSize:11, minWidth:210 }} />
                  <th colSpan={4} style={{ ...th, textAlign:"center", borderLeft:groupBorder, color:"var(--text-primary)" }}>{t("mesUpper")} — {MONTHS[month-1]}</th>
                  <th colSpan={4} style={{ ...th, textAlign:"center", borderLeft:groupBorder, color:"var(--text-primary)" }}>YTD {MONTHS[month-1]}</th>
                  <th colSpan={5} style={{ ...th, textAlign:"center", borderLeft:groupBorder, color:"var(--text-primary)" }}>FULL YEAR</th>
                </tr>
                <tr style={{ borderBottom:"1px solid var(--border-medium)", color:"var(--text-secondary)" }}>
                  <th style={{ textAlign:"left", padding:"4px 8px", fontSize:10 }}>{tc("line")}</th>
                  {colDefs.map((cd,i)=>(
                    <th key={i} style={{ ...th, borderLeft: (i===0||i===4||i===8)?groupBorder:undefined }}>{subHead[i]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(ln => {
                  const isTotal = /^(TOTAL_|GOP|EBITDA|EBT|NET_PROFIT)/.test(ln.line_code);
                  return (
                    <tr key={ln.line_code} style={isTotal?{ borderTop:"1px solid var(--border-medium)", fontWeight:700 }:undefined}>
                      <td style={{ padding:"3px 8px", fontSize:11, fontWeight:isTotal?700:400, color:isTotal?"var(--text-primary)":"var(--text-secondary)", whiteSpace:"nowrap" }}>{ln.line_name}</td>
                      {colDefs.map((cd,i)=>{
                        const v = cellVal(ln.line_code, cd);
                        const isVar = cd.role==="var";
                        return (
                          <td key={i} style={{ ...td, borderLeft:(i===0||i===4||i===8)?groupBorder:undefined,
                            fontWeight:isTotal?700:400,
                            color: isVar ? (v<0?"var(--negative, #C0392B)":"var(--positive, #1A7F4B)") : "var(--text-primary)" }}>
                            {fmtUSD(v)}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
