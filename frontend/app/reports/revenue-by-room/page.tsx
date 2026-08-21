"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import IrA from "@/components/IrA";
import {
  getScenarios, getRevenueByRoomType, rtLabel,
  type Scenario, type RevenueByRoomType, type RoomTypeRow,
} from "@/lib/api";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const int = (n: number) => Math.round(n).toLocaleString("en-US");
const usd0 = (n: number) => { const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); return n < 0 ? `(${s})` : s; };
const usd2 = (n: number) => "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n: number) => (n * 100).toFixed(1) + "%";

// View = which months to aggregate
type View = { kind: "full" } | { kind: "ytd"; m: number } | { kind: "month"; m: number };

function aggregate(d: RevenueByRoomType, view: View): RoomTypeRow[] {
  if (view.kind === "full") return d.annual;
  const sel = view.kind === "month"
    ? d.months.filter(x => x.month === view.m)
    : d.months.filter(x => x.month <= view.m);
  const acc: Record<string, RoomTypeRow> = {};
  for (const rt of d.room_types)
    acc[rt.id] = { room_type_id: rt.id, room_type_code: rt.code, room_type_name: rt.name, units: rt.units,
      nights_available: 0, nights_occupied: 0, occupancy_pct: 0, revenue: 0, adr: 0, pax: 0 };
  for (const mo of sel) for (const r of mo.rows) {
    const a = acc[r.room_type_id]; if (!a) continue;
    a.nights_available += r.nights_available; a.nights_occupied += r.nights_occupied;
    a.revenue += r.revenue; a.pax += r.pax;
  }
  const total = Object.values(acc).reduce((s, a) => s + a.revenue, 0);
  return Object.values(acc).map(a => ({ ...a,
    occupancy_pct: a.nights_available ? a.nights_occupied / a.nights_available : 0,
    adr: a.nights_occupied ? a.revenue / a.nights_occupied : 0,
    pct_of_total: total ? a.revenue / total : 0 }));
}

export default function RevenueByRoomPage() {
  const tc = useTranslations("common");
  const t = useTranslations("revByRoom");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Este reporte sale de los DRIVERS (rate cards + ocupacion), que tienen los
  // presupuestos/forecasts — no los Actuales (snapshot de P&L sin drivers): por
  // eso el rol es "budget". Se acuerda de lo ultimo elegido EN ESTA pantalla, y
  // si nunca se eligio abre con el preferido del owner.
  const [scenarioId, setScenarioId] = useEscenarioDe("reports/revenue-by-room:budget", scenarios, "budget", undefined, true);
  const [data, setData] = useState<RevenueByRoomType | null>(null);
  const [viewKind, setViewKind] = useState<"full"|"ytd"|"month">("full");
  const [month, setMonth] = useState(5);
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
    try { setData(await getRevenueByRoomType(sid)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const view: View = viewKind === "full" ? { kind:"full" } : { kind: viewKind, m: month };
  const rows = useMemo(() => data ? aggregate(data, view) : [], [data, viewKind, month]); // eslint-disable-line react-hooks/exhaustive-deps
  const totals = useMemo(() => rows.reduce((t, r) => ({
    units: t.units + r.units, na: t.na + r.nights_available, no: t.no + r.nights_occupied,
    rev: t.rev + r.revenue, pax: t.pax + r.pax }), { units:0, na:0, no:0, rev:0, pax:0 }), [rows]);

  const viewLabel = viewKind === "full" ? "Full Year" : viewKind === "ytd" ? `YTD ${MONTHS[month-1]}` : MONTHS[month-1];

  const exportExcel = useCallback(async () => {
    // Ocupación y % del total van como FRACCIÓN (0.125), no como el texto
    // "12.5%" que se mandaba antes: así el Excel los reconoce como porcentaje.
    const filas: FilaCuadro[] = rows.map(r => ({
      label: rtLabel(r.room_type_code, r.room_type_name),
      valores: [r.units, r.nights_available, r.nights_occupied, r.occupancy_pct,
        r.revenue, r.adr, r.pax, r.pct_of_total ?? 0],
    }));
    filas.push({ label: "TOTAL", es_total: true,
      valores: [totals.units, totals.na, totals.no, totals.na ? totals.no / totals.na : 0,
        totals.rev, totals.no ? totals.rev / totals.no : 0, totals.pax, 1] });
    try {
      await bajarCuadros(`Rev_by_Room_${viewLabel.replace(/\s/g,"_")}`, [{
        titulo: t("excelTitulo"),
        subtitulo: `${viewLabel} · USD`,
        hoja: "Rev by Room",
        columnas: [
          { label: tc("category"), ancho: 34, formato: "texto" },
          { label: "Units", ancho: 10, formato: "num" },
          { label: t("nochesDisp"), formato: "num" },
          { label: t("nochesOcup"), formato: "num" },
          { label: t("occupancy"), ancho: 12, formato: "pct" },
          { label: "Revenue", ancho: 16, formato: "usd" },
          { label: "ADR", formato: "usd2" },
          { label: "Pax", ancho: 10, formato: "num" },
          { label: t("pctDelTotal"), ancho: 12, formato: "pct" },
        ],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }, [rows, totals, viewLabel, t, tc]);

  const th: React.CSSProperties = { textAlign:"right", padding:"6px 10px", fontSize:11, fontWeight:600 };
  const td: React.CSSProperties = { textAlign:"right", padding:"5px 10px", fontSize:12, fontFamily:"var(--font-mono)" };

  return (
    <>
      <style>{`@media print{.no-print{display:none!important}body *{visibility:hidden}#rep,#rep *{visibility:visible}#rep{position:absolute;inset:0;padding:16px}}`}</style>
      <div className="pag pag-media" style={{ padding:"24px 28px 64px" }}>
      <IrA esc={scenarioId} />
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:14, flexWrap:"wrap", gap:12 }}>
          <div>
            <h1 style={{ fontSize:22, fontWeight:700 }}>{t("title")}</h1>
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
          <div><div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>{t("vista")}</div>
            <select value={viewKind} onChange={e=>setViewKind(e.target.value as "full"|"ytd"|"month")} className="fin-input">
              <option value="full">Full Year</option><option value="ytd">{t("ytdThrough")}</option><option value="month">{t("monthOnly")}</option>
            </select></div>
          {viewKind !== "full" && <div><div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>{tc("month")}</div>
            <select value={month} onChange={e=>setMonth(Number(e.target.value))} className="fin-input">{MONTHS.map((m,i)=><option key={i+1} value={i+1}>{m}</option>)}</select></div>}
        </div>

        {error && <div style={{ color:"var(--negative, #C0392B)", fontSize:13, marginBottom:8 }}>{error}</div>}
        {loading ? <div style={{ color:"var(--text-secondary)", padding:24 }}>{tc("loading")}</div> : !data ? null : (
          <div id="rep" className="fin-sticky" style={{ overflowX:"auto" }}>
            <div style={{ fontSize:12, color:"var(--text-secondary)", marginBottom:6 }}>{viewLabel}</div>
            {totals.rev === 0 && <div style={{ fontSize:12, color:"var(--accent-amber, #856404)", marginBottom:8 }}>{t("noDrivers")}</div>}
            <table style={{ borderCollapse:"collapse", width:"100%", minWidth:760 }}>
              <thead>
                <tr style={{ borderBottom:"2px solid var(--border-medium)", color:"var(--text-secondary)" }}>
                  <th style={{ textAlign:"left", padding:"6px 10px", fontSize:11 }}>{tc("category")}</th>
                  <th style={th}>Units</th><th style={th}>{t("nochesDisp")}</th><th style={th}>{t("nochesOcup")}</th>
                  <th style={th}>{t("occupancy")}</th><th style={th}>Revenue</th><th style={th}>ADR</th><th style={th}>Pax</th><th style={th}>% total</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.room_type_id} style={{ borderBottom:"1px solid var(--border-light, rgba(255,255,255,0.05))" }}>
                    <td style={{ padding:"5px 10px", fontSize:12, color:"var(--text-primary)" }}>{rtLabel(r.room_type_code, r.room_type_name)}</td>
                    <td style={td}>{r.units}</td><td style={td}>{int(r.nights_available)}</td><td style={td}>{int(r.nights_occupied)}</td>
                    <td style={td}>{pct(r.occupancy_pct)}</td><td style={{ ...td, fontWeight:600 }}>{usd0(r.revenue)}</td>
                    <td style={td}>{usd2(r.adr)}</td><td style={td}>{int(r.pax)}</td>
                    <td style={{ ...td, color:"var(--brand)" }}>{pct(r.pct_of_total ?? 0)}</td>
                  </tr>
                ))}
                <tr style={{ borderTop:"2px solid var(--border-medium)", fontWeight:700 }}>
                  <td style={{ padding:"6px 10px", fontSize:12 }}>TOTAL</td>
                  <td style={td}>{totals.units}</td><td style={td}>{int(totals.na)}</td><td style={td}>{int(totals.no)}</td>
                  <td style={td}>{pct(totals.na?totals.no/totals.na:0)}</td><td style={td}>{usd0(totals.rev)}</td>
                  <td style={td}>{usd2(totals.no?totals.rev/totals.no:0)}</td><td style={td}>{int(totals.pax)}</td><td style={td}>100%</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
