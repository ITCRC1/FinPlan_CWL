"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { bajarCuadros, type ColumnaCuadro, type FilaCuadro, type FormatoCol } from "@/lib/exportCuadro";
import { HOTEL_ID, hotelShort } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import {
  getScenarios, getPLCompare,
  type Scenario, type PLCompare, type PLColumn, type PLLine,
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
function fmt2(n: number) { return Math.abs(n) < 0.005 ? "-" : (n < 0 ? "(" : "") + Math.abs(n).toFixed(2) + (n < 0 ? ")" : ""); }
function fmtPct(n: number) { return Math.abs(n) < 0.0001 ? "-" : (n * 100).toFixed(1) + "%"; }

const lineAmt = (col: PLColumn | undefined, code: string) =>
  col?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;

export default function PLYtdReportPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("plYtd");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Cada selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca
  // se eligio abre con el preferido del owner.
  const [actualId, setActualId] = useEscenarioDe("reports/pl-ytd:actual", scenarios, "actual");
  const [budgetId, setBudgetId] = useEscenarioDe("reports/pl-ytd:budget", scenarios, "budget", undefined, true);
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
    try {
      setCmp(await getPLCompare([aid, bid].filter(Boolean), m));
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (actualId) load(actualId, budgetId, month); }, [actualId, budgetId, month, load]);

  const aCol = cmp?.versions[0]?.ytd;
  const bCol = budgetId ? cmp?.versions[1]?.ytd : undefined;
  const aLabel = cmp?.versions[0]?.label ?? "Actual";
  const bLabel = budgetId ? (cmp?.versions[1]?.label ?? "Budget") : "";
  const aRev = lineAmt(aCol, "TOTAL_REVENUES");
  const bRev = lineAmt(bCol, "TOTAL_REVENUES");

  const rows = aCol?.lines ?? [];

  const statRows = useMemo(() => {
    const k = (c?: PLColumn) => c?.kpis;
    const ka = k(aCol), kb = k(bCol);
    // El 5º campo es la unidad para el Excel: sin él la ocupación sale como un
    // número suelto y el ADR pierde los centavos.
    return [
      ["Total Rooms Available", ka?.rooms_available ?? 0, kb?.rooms_available ?? 0, (n:number)=>Math.round(n).toLocaleString(), "num"],
      ["Total Rooms Occupied", ka?.rooms_occupied ?? 0, kb?.rooms_occupied ?? 0, (n:number)=>Math.round(n).toLocaleString(), "num"],
      ["Total Guests", ka?.guests ?? 0, kb?.guests ?? 0, (n:number)=>Math.round(n).toLocaleString(), "num"],
      ["% Occupancy", (ka?.occupancy_pct ?? 0)*100, (kb?.occupancy_pct ?? 0)*100, (n:number)=>n.toFixed(1)+"%", "pct"],
      ["ADR", ka?.adr ?? 0, kb?.adr ?? 0, (n:number)=>"$"+n.toFixed(2), "usd2"],
    ] as [string, number, number, (n:number)=>string, FormatoCol][];
  }, [aCol, bCol]);

  const exportExcel = useCallback(async () => {
    if (!aCol) return;
    const usd: FormatoCol = "usd", pc: FormatoCol = "pct", u2: FormatoCol = "usd2";
    const columnas: ColumnaCuadro[] = [
      { label: t("colAccountDesc"), ancho: 38, formato: "texto" },
      { label: `${aLabel} $`, formato: usd }, { label: "% Rev", ancho: 10, formato: pc },
      { label: "PAR", formato: u2 }, { label: "POR", formato: u2 },
      ...(bCol ? [
        { label: `${bLabel} $`, formato: usd }, { label: "% Rev", ancho: 10, formato: pc },
        { label: "PAR", formato: u2 }, { label: "POR", formato: u2 },
        { label: "Var $", formato: usd }, { label: "Var %", ancho: 10, formato: pc },
      ] : []),
    ];
    const nulls = (n: number) => new Array(n).fill(null) as (number|null)[];
    const filas: FilaCuadro[] = [
      { label: t("statistics"), es_total: true, valores: nulls(columnas.length - 1) },
      // Las estadísticas sólo llenan la columna de importe; el resto va NULL
      // (celda vacía), no "" — antes eran cadenas vacías donde iba un número.
      ...statRows.map(([lbl, av, bv, , fmt]): FilaCuadro => ({
        label: lbl, nivel: 1, formato: fmt,
        valores: [fmt === "pct" ? av / 100 : av, null, null, null,
          ...(bCol ? [fmt === "pct" ? bv / 100 : bv, null, null, null, null, null] : [])],
      })),
      { label: "P&L", es_total: true, valores: nulls(columnas.length - 1) },
      ...rows.map((ln: PLLine): FilaCuadro => {
        const av = ln.amount_usd;
        const b = bCol?.lines.find(l => l.line_code === ln.line_code);
        const bv = b?.amount_usd ?? 0;
        const isTotal = /^(TOTAL_|GOP|EBITDA|EBT|NET_PROFIT)/.test(ln.line_code);
        return {
          label: ln.line_name, nivel: isTotal ? 0 : 1, es_total: isTotal,
          valores: [av, aRev ? av / aRev : null, ln.par ?? null, ln.por ?? null,
            ...(bCol ? [bv, bRev ? bv / bRev : null, b?.par ?? null, b?.por ?? null,
              av - bv, bv ? (av - bv) / Math.abs(bv) : null] : [])],
        };
      }),
    ];
    try {
      await bajarCuadros(`PL_YTD_${MONTHS[month-1]}`, [{
        titulo: `P&L YTD ${MONTHS[month-1]} — ${hotelShort()}`,
        subtitulo: bCol ? `${aLabel} vs ${bLabel} · USD` : `${aLabel} · USD`,
        hoja: "P&L YTD", columnas, filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }, [aCol, bCol, rows, statRows, aLabel, bLabel, aRev, bRev, month, t]);

  const th: React.CSSProperties = { textAlign: "right", padding: "5px 8px", fontSize: 11, fontWeight: 600 };
  const td: React.CSSProperties = { textAlign: "right", padding: "4px 8px", fontSize: 12, fontFamily: "var(--font-mono)" };

  return (
    <>
      <style>{`@media print { .no-print { display:none !important; } body * { visibility:hidden; } #rep, #rep * { visibility:visible; } #rep { position:absolute; inset:0; padding:14px; } table { font-size:9px !important; } td,th { padding:3px 5px !important; } }`}</style>
      <div className="pag pag-ancha" style={{ padding: "24px 28px 64px" }}>
      <IrA esc={budgetId} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700 }}>{t("title", { hotel: hotel.corto })}</h1>
            <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("subtitle")}</p>
          </div>
          <div className="no-print" style={{ display: "flex", gap: 8 }}>
            <button onClick={exportExcel} style={{ padding: "7px 14px", borderRadius: 6, cursor: "pointer", background: "var(--accent-excel)", color: "#fff", border: "none", fontSize: 13, fontWeight: 600 }}>⬇ Excel</button>
            <button onClick={() => window.print()} style={{ padding: "7px 14px", borderRadius: 6, cursor: "pointer", background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", fontSize: 13, fontWeight: 600 }}>🖨 PDF</button>
          </div>
        </div>

        <div className="no-print" style={{ display: "flex", gap: 16, alignItems: "flex-end", marginBottom: 18, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>Actual</div>
            <select value={actualId} onChange={e => setActualId(e.target.value)} className="fin-input">
              {scenarios.map(s => <option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>Budget</div>
            <select value={budgetId} onChange={e => setBudgetId(e.target.value)} className="fin-input">
              <option value="">{tc("none")}</option>
              {scenarios.map(s => <option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>{t("ytdThrough")}</div>
            <select value={month} onChange={e => setMonth(Number(e.target.value))} className="fin-input">
              {MONTHS.map((m, i) => <option key={i+1} value={i+1}>{m}</option>)}
            </select>
          </div>
        </div>

        {error && <div style={{ color: "var(--negative, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
        {loading ? <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div> : !aCol ? null : (
          <div id="rep" className="fin-sticky" style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", minWidth: 820 }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border-medium)" }}>
                  <th style={{ textAlign: "left", padding: "5px 8px", fontSize: 11, minWidth: 220 }}>YTD {MONTHS[month-1]} 2026</th>
                  <th style={{ ...th, color: "var(--positive, #1A7F4B)", borderLeft: "2px solid var(--border-medium)" }} colSpan={4}>{aLabel}</th>
                  {bCol && <th style={{ ...th }} colSpan={4}>{bLabel}</th>}
                  {bCol && <th style={{ ...th }} colSpan={2}>{tc("variance")}</th>}
                </tr>
                <tr style={{ borderBottom: "1px solid var(--border-medium)", color: "var(--text-secondary)" }}>
                  <th />
                  <th style={{ ...th, borderLeft: "2px solid var(--border-medium)" }}>$</th><th style={th}>% Rev</th><th style={th}>PAR</th><th style={th}>POR</th>
                  {bCol && <><th style={th}>$</th><th style={th}>% Rev</th><th style={th}>PAR</th><th style={th}>POR</th></>}
                  {bCol && <><th style={th}>$</th><th style={th}>%</th></>}
                </tr>
              </thead>
              <tbody>
                <tr><td colSpan={bCol?11:5} style={{ padding: "8px 8px 3px", fontSize: 10, fontWeight: 700, letterSpacing: 0.6, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("statistics")}</td></tr>
                {statRows.map(([lbl, av, bv, f]) => (
                  <tr key={lbl}>
                    <td style={{ padding: "4px 8px 4px 20px", fontSize: 12, color: "var(--text-secondary)" }}>{lbl}</td>
                    <td style={{ ...td, borderLeft: "2px solid var(--border-medium)" }}>{f(av)}</td><td style={td} /><td style={td} /><td style={td} />
                    {bCol && <><td style={td}>{f(bv)}</td><td style={td} /><td style={td} /><td style={td} /><td style={td} /><td style={td} /></>}
                  </tr>
                ))}
                <tr><td colSpan={bCol?11:5} style={{ padding: "10px 8px 3px", fontSize: 10, fontWeight: 700, letterSpacing: 0.6, color: "var(--text-secondary)", textTransform: "uppercase" }}>P&amp;L</td></tr>
                {rows.map((ln) => {
                  const isTotal = /^(TOTAL_|GOP|EBITDA|EBT|NET_PROFIT)/.test(ln.line_code);
                  const b = bCol?.lines.find(l => l.line_code === ln.line_code);
                  const av = ln.amount_usd, bv = b?.amount_usd ?? 0, dv = av - bv;
                  const rowSty: React.CSSProperties = isTotal ? { borderTop: "1px solid var(--border-medium)", fontWeight: 700 } : {};
                  return (
                    <tr key={ln.line_code} style={rowSty}>
                      <td style={{ padding: "4px 8px", fontSize: 12, fontWeight: isTotal?700:400, color: isTotal?"var(--text-primary)":"var(--text-secondary)" }}>{ln.line_name}</td>
                      <td style={{ ...td, borderLeft: "2px solid var(--border-medium)", fontWeight: isTotal?700:400 }}>{fmtUSD(av)}</td>
                      <td style={td}>{aRev?fmtPct(av/aRev):"-"}</td>
                      <td style={td}>{fmt2(ln.par ?? 0)}</td>
                      <td style={td}>{fmt2(ln.por ?? 0)}</td>
                      {bCol && <>
                        <td style={{ ...td, fontWeight: isTotal?700:400 }}>{fmtUSD(bv)}</td>
                        <td style={td}>{bRev?fmtPct(bv/bRev):"-"}</td>
                        <td style={td}>{fmt2(b?.par ?? 0)}</td>
                        <td style={td}>{fmt2(b?.por ?? 0)}</td>
                        <td style={{ ...td, color: dv<0?"var(--negative, #C0392B)":"var(--positive, #1A7F4B)" }}>{fmtUSD(dv)}</td>
                        <td style={{ ...td, color: dv<0?"var(--negative, #C0392B)":"var(--positive, #1A7F4B)" }}>{bv?fmtPct(dv/Math.abs(bv)):"-"}</td>
                      </>}
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
