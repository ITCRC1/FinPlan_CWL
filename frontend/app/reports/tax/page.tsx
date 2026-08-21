"use client";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { elegir } from "@/lib/escenarioPreferido";
import { HOTEL_ID, hotelShort } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import IrA from "@/components/IrA";
import {
  getScenarios, getTax, saveTaxParams,
  type Scenario, type TaxPanorama, type TaxParams,
} from "@/lib/api";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const usd0 = (n: number) => { const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); return n < 0 ? `(${s})` : s; };
const pct = (n: number) => (n * 100).toFixed(2) + "%";

export default function TaxPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("tax");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [tax, setTax] = useState<TaxPanorama | null>(null);
  const [params, setParams] = useState<TaxParams>({ wh_rate:0.025, income_tax_rate:0.30, card_pct_rooms:0.90, card_pct_fb:0.70, card_pct_spa:0.80, card_pct_tours:0.75, card_pct_private_bar:1.00, card_pct_other:0.60 });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        // Abre con el preferido del owner, pero NO recuerda lo elegido a
        // propósito: «Aplicar» ESCRIBE los parámetros fiscales en el escenario
        // que esté en el selector. Un default que reabre siempre en el mismo
        // lugar se audita; uno que arrastra la elección de la visita anterior
        // convierte un click distraído en un guardado sobre otro presupuesto.
        setScenarioId((elegir(all, "budget") ?? all[0])?.id ?? "");
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    if (!sid) return;
    setLoading(true); setError(null);
    try { const d = await getTax(sid); setTax(d); setParams(d.params); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const save = async () => {
    setSaving(true); setError(null);
    try { await saveTaxParams(scenarioId, params); await load(scenarioId); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setSaving(false); }
  };

  const exportExcel = useCallback(async () => {
    if (!tax) return;
    const mensuales: FilaCuadro[] = tax.monthly.map(m => ({
      label: MONTHS[m.month-1], valores: [m.card_revenue, m.withholding],
    }));
    mensuales.push({ label: t("yearTotal"), es_total: true,
      valores: [tax.monthly.reduce((s,m)=>s+m.card_revenue,0), tax.cumulative_wh] });
    const anual: FilaCuadro[] = [
      { label: t("whAcumulada"), valores: [tax.cumulative_wh] },
      { label: t("ebtAnual"), valores: [tax.annual_ebt] },
      { label: t("rentaBruta"), valores: [tax.gross_income_tax] },
      { label: t("creditoRetencion"), valores: [tax.wh_credit] },
      { label: t("rentaNeta"), es_total: true, valores: [tax.net_income_tax] },
      { label: t("saldoAFavor"), valores: [tax.credit_balance] },
      // La tasa efectiva es un porcentaje, no una cadena "3.21%".
      { label: t("tasaEfectiva"), formato: "pct", valores: [tax.effective_tax_rate] },
    ];
    try {
      await bajarCuadros("Panorama_Fiscal", [
        { titulo: t("title", { hotel: hotelShort() }), subtitulo: t("excelSubMensual"),
          hoja: t("monthlyWithholding"),
          columnas: [
            { label: tc("month"), ancho: 14, formato: "texto" },
            { label: t("cardCollection"), ancho: 18, formato: "usd" },
            { label: t("withholdingPct", { pct: (params.wh_rate*100).toFixed(1) }), ancho: 18, formato: "usd" },
          ],
          filas: mensuales },
        { titulo: t("excelTituloAnual", { hotel: hotelShort() }), subtitulo: "USD",
          hoja: t("annualSettlement"),
          columnas: [
            { label: tc("concept"), ancho: 34, formato: "texto" },
            { label: t("monto"), ancho: 18, formato: "usd" },
          ],
          filas: anual },
      ]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }, [tax, params.wh_rate, t, tc]);

  const td: React.CSSProperties = { textAlign:"right", padding:"5px 12px", fontSize:12, fontFamily:"var(--font-mono)" };
  const inp: React.CSSProperties = { width: 90 };
  const pctInput = (label: string, key: keyof TaxParams) => (
    <div><div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>{label}</div>
      <input type="number" step="0.01" className="fin-input" style={inp} value={params[key]} onChange={e=>setParams(p=>({...p,[key]:Number(e.target.value)}))} /></div>
  );

  const summaryRows: [string, string, boolean?][] = tax ? [
    [t("whAcumulada"), usd0(tax.cumulative_wh)],
    [t("ebtAnual"), usd0(tax.annual_ebt)],
    [t("rentaBruta"), usd0(tax.gross_income_tax)],
    [t("creditoRetencion"), usd0(tax.wh_credit)],
    [t("rentaNeta"), usd0(tax.net_income_tax), true],
    [t("saldoAFavor"), usd0(tax.credit_balance)],
    [t("tasaEfectiva"), pct(tax.effective_tax_rate)],
  ] : [];

  return (
    <>
      <style>{`@media print{.no-print{display:none!important}body *{visibility:hidden}#rep,#rep *{visibility:visible}#rep{position:absolute;inset:0;padding:16px}}`}</style>
      <div className="pag pag-lectura" style={{ padding:"24px 28px 64px" }}>
      <IrA />
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

        <div className="no-print" style={{ display:"flex", gap:12, alignItems:"flex-end", marginBottom:8, flexWrap:"wrap" }}>
          <div><div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>{tc("scenario")}</div>
            <select value={scenarioId} onChange={e=>setScenarioId(e.target.value)} className="fin-input">{scenarios.map(s=><option key={s.id} value={s.id}>{scnLabel(s)}</option>)}</select></div>
          {pctInput(t("withholding"), "wh_rate")}
          {pctInput(t("renta"), "income_tax_rate")}
          {pctInput(t("cardPct", { linea: "Rooms" }), "card_pct_rooms")}
          {pctInput(t("cardPct", { linea: "F&B" }), "card_pct_fb")}
          {pctInput(t("cardPct", { linea: "Spa" }), "card_pct_spa")}
          {pctInput(t("cardPct", { linea: "Tours" }), "card_pct_tours")}
          {pctInput(t("cardPct", { linea: "Private Bar" }), "card_pct_private_bar")}
          {pctInput(t("cardPct", { linea: t("otros") }), "card_pct_other")}
          <button onClick={save} disabled={saving} style={{ padding:"8px 16px", borderRadius:6, cursor:"pointer", background:"var(--brand)", color:"#fff", border:"none", fontSize:13, fontWeight:600 }}>{saving?tc("saving"):t("aplicar")}</button>
        </div>

        {error && <div style={{ color:"var(--negative, #C0392B)", fontSize:13, marginBottom:8 }}>{error}</div>}
        {loading ? <div style={{ color:"var(--text-secondary)", padding:24 }}>{tc("loading")}</div> : !tax ? null : (
          <div id="rep" style={{ display:"flex", gap:24, flexWrap:"wrap", marginTop:12 }}>
            <div style={{ flex:"1 1 320px" }}>
              <h2 style={{ fontSize:14, fontWeight:600, margin:"0 0 8px" }}>{t("monthlyWithholding")}</h2>
              <table style={{ borderCollapse:"collapse", width:"100%" }}>
                <thead><tr style={{ borderBottom:"2px solid var(--border-medium)", color:"var(--text-secondary)" }}>
                  <th style={{ textAlign:"left", padding:"5px 12px", fontSize:11 }}>{tc("month")}</th>
                  <th style={{ textAlign:"right", padding:"5px 12px", fontSize:11 }}>{t("cardCollection")}</th>
                  <th style={{ textAlign:"right", padding:"5px 12px", fontSize:11 }}>{t("withholding")}</th>
                </tr></thead>
                <tbody>
                  {tax.monthly.map(m => (
                    <tr key={m.month}><td style={{ padding:"4px 12px", fontSize:12, color:"var(--text-secondary)" }}>{MONTHS[m.month-1]}</td>
                      <td style={td}>{usd0(m.card_revenue)}</td><td style={td}>{usd0(m.withholding)}</td></tr>
                  ))}
                  <tr style={{ borderTop:"2px solid var(--border-medium)", fontWeight:700 }}>
                    <td style={{ padding:"5px 12px", fontSize:12 }}>{t("yearTotal")}</td>
                    <td style={td}>{usd0(tax.monthly.reduce((s,m)=>s+m.card_revenue,0))}</td>
                    <td style={td}>{usd0(tax.cumulative_wh)}</td></tr>
                </tbody>
              </table>
            </div>
            <div style={{ flex:"1 1 320px" }}>
              <h2 style={{ fontSize:14, fontWeight:600, margin:"0 0 8px" }}>{t("annualSettlement")}</h2>
              <table style={{ borderCollapse:"collapse", width:"100%" }}>
                <tbody>
                  {summaryRows.map(([label, val, strong], i) => (
                    <tr key={i} style={strong?{ borderTop:"1px solid var(--border-medium)", borderBottom:"1px solid var(--border-medium)", fontWeight:700 }:undefined}>
                      <td style={{ padding:"6px 12px", fontSize:12, color:strong?"var(--text-primary)":"var(--text-secondary)" }}>{label}</td>
                      <td style={{ ...td, fontWeight:strong?700:400 }}>{val}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p style={{ fontSize:11, color:"var(--text-secondary)", marginTop:10 }}>{t("withholdingNote")}</p>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
