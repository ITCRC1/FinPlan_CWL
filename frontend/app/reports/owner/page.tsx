"use client";
import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import IrA from "@/components/IrA";
import {
  getScenarios, getPLMonthly, getExpenseTotals, getAnnotations,
  getRoomTypes, getOccupancyPct, getRackRates, getChannelsConfig,
  downloadOwnerReportExcel,
  type Scenario, type Annotation,
} from "@/lib/api";

const MK = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"] as const;
// Con hueco en 0: los meses acá se indexan 1..12.
const MONTHS_FALLBACK = ["", "Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
function daysIn(y: number, m1: number) { return new Date(y, m1, 0).getDate(); }
const usd0 = (n: number) => n ? "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
const usd2 = (n: number) => "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const intf = (n: number) => Math.round(n).toLocaleString("en-US");

export default function OwnerReportPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("owner");
  const tm = useTranslations("months");
  const tmShort = tm.raw("short") as string[] | undefined;
  const MONTHS = tmShort ? ["", ...tmShort] : MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // El selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se
  // eligio abre con el preferido del owner.
  const [scenarioId, setScenarioId] = useEscenarioDe("reports/owner:budget", scenarios, "budget", undefined, true);
  const [annual, setAnnual] = useState<Record<string, number>>({});
  const [exp, setExp] = useState<{ payroll: number; cos: number; opex: number } | null>(null);
  const [kpi, setKpi] = useState<{ occPct: number; adr: number; revpar: number; pax: number } | null>(null);
  const [notes, setNotes] = useState<Annotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
      } catch (e: unknown) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setError(null);
    try {
      const [pl, et, an, rt, occ, rack, ch] = await Promise.all([
        getPLMonthly(sid), getExpenseTotals(sid).catch(() => null),
        getAnnotations(sid, { kind: "comment" }),
        getRoomTypes(HOTEL_ID, sid), getOccupancyPct(sid), getRackRates(sid), getChannelsConfig(sid),
      ]);
      setAnnual(pl.annual); setExp(et); setNotes(an.annotations);
      // KPIs desde drivers
      const year = occ.year; const closed = new Set(rt.closed_months);
      const units = Object.fromEntries(rt.room_types.map(r => [r.id, r.units]));
      const ppn = parseFloat(rt.pax_per_night) || 1.8;
      const nf = ch.net_factor.map(v => parseFloat(v) || 0);
      const rackById = Object.fromEntries(rack.rooms.map(r => [r.room_type_id, MK.map(k => parseFloat(r[k]) || 0)]));
      let avail = 0, occN = 0, rev = 0;
      MK.forEach((_k, mi) => {
        if (closed.has(mi + 1)) return; const d = daysIn(year, mi + 1);
        occ.rooms.forEach(r => {
          const u = units[r.room_type_id] ?? 0; avail += u * d;
          const nights = (parseFloat(r[MK[mi]]) || 0) * u * d; occN += nights;
          rev += nights * ((rackById[r.room_type_id]?.[mi]) || 0) * (nf[mi] || 0);
        });
      });
      setKpi({ occPct: avail ? occN / avail * 100 : 0, adr: occN ? rev / occN : 0, revpar: avail ? rev / avail : 0, pax: occN * ppn });
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const sel = scenarios.find(s => s.id === scenarioId);
  const a = (k: string) => annual[k] ?? 0;
  const PL_ROWS: [string, number, boolean?][] = [
    ["Total Revenue", a("TOTAL_REVENUES")],
    ["Gastos de Planilla", -(exp?.payroll ?? 0), true],
    ["Costos de venta", -(exp?.cos ?? 0), true],
    ["Gastos Operativos", -(exp?.opex ?? 0), true],
    ["Gastos del Propietario", -a("TOTAL_NON_OP"), true],
    ["GOP", a("GOP")],
    ["EBITDA", a("EBITDA_BEFORE")],
    ["Net Profit", a("NET_PROFIT")],
  ];

  // narrativa agrupada por sección
  const bySec: Record<string, Annotation[]> = {};
  for (const n of notes) (bySec[n.label] ??= []).push(n);

  async function handleExportExcel() {
    if (!scenarioId) return;
    setExporting(true); setError(null);
    try {
      const blob = await downloadOwnerReportExcel(scenarioId, {
        scenario_label: sel ? `${sel.type} ${sel.version} ${sel.year}` : "",
        kpis: { occ_pct: kpi?.occPct ?? 0, adr: kpi?.adr ?? 0, revpar: kpi?.revpar ?? 0, pax: kpi?.pax ?? 0 },
        pl_rows: PL_ROWS.map(([label, v, strong]) => ({ label, value: v, strong: !!strong })),
        notes: notes.map(n => ({
          section: n.label,
          ref: n.ref || "",
          month_name: n.month > 0 ? MONTHS[n.month] : "",
          body: n.body,
        })),
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `owner_report_${sel ? `${sel.type}_${sel.version}_${sel.year}` : scenarioId}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Error al exportar"); }
    finally { setExporting(false); }
  }

  return (
    <div className="pag pag-lectura" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div className="no-print" style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 200 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <button onClick={handleExportExcel} disabled={exporting || loading} style={{ padding: "8px 16px", fontSize: 13, fontWeight: 600, borderRadius: 5, border: "1px solid var(--brand)", background: "transparent", color: "var(--brand)", cursor: exporting ? "default" : "pointer", opacity: exporting || loading ? 0.6 : 1 }}>
          {exporting ? "Exportando…" : "Exportar Excel"}
        </button>
        <button onClick={() => window.print()} style={{ padding: "8px 16px", fontSize: 13, fontWeight: 600, borderRadius: 5, border: "none", background: "var(--brand)", color: "#fff", cursor: "pointer" }}>
          Imprimir / PDF
        </button>
      </div>

      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <div>
          <div style={{ marginBottom: 16 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
              {hotel.nombre} — {sel ? `${sel.type} ${sel.version} ${sel.year}` : ""}
            </h2>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("subtitle")}</div>
          </div>

          {/* KPIs */}
          {kpi && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))", gap: 10, marginBottom: 18 }}>
              {[["Ocupación", kpi.occPct.toFixed(1) + "%"], ["ADR", usd2(kpi.adr)], ["RevPAR", usd2(kpi.revpar)], ["Total Pax", intf(kpi.pax)]].map(([l, v]) => (
                <div key={l} style={{ background: "var(--bg-surface)", borderRadius: 8, padding: "10px 12px" }}>
                  <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{l}</div>
                  <div style={{ fontSize: 18, fontWeight: 600, color: "var(--brand)" }}>{v}</div>
                </div>
              ))}
            </div>
          )}

          {/* P&L resumen */}
          <table className="fin-table" style={{ width: "100%", marginBottom: 22 }}>
            <tbody>
              {PL_ROWS.map(([label, v, strong]) => (
                <tr key={label} style={["GOP", "EBITDA", "Net Profit", "Total Revenue"].includes(label) ? { borderTop: "1px solid var(--border-medium)" } : undefined}>
                  <td style={{ textAlign: "left", fontWeight: ["GOP", "EBITDA", "Net Profit", "Total Revenue"].includes(label) ? 700 : 400, color: strong ? "var(--text-secondary)" : "var(--text-primary)" }}>{label}</td>
                  <td className="mono" style={{ textAlign: "right", fontWeight: ["GOP", "EBITDA", "Net Profit", "Total Revenue"].includes(label) ? 700 : 400 }}>
                    {v < 0 ? "(" + usd0(-v) + ")" : usd0(v)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Narrativa */}
          <h3 style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", margin: "0 0 10px" }}>{t("varianceExplained")}</h3>
          {notes.length === 0 ? (
            <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>{t("noComments")}</div>
          ) : (
            Object.entries(bySec).map(([label, list]) => (
              <div key={label} style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--brand)", marginBottom: 4 }}>{label}</div>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {list.map(n => (
                    <li key={n.id} style={{ fontSize: 13, color: "var(--text-primary)", lineHeight: 1.6, marginBottom: 3 }}>
                      {(n.ref || n.month > 0) && (
                        <b>{[n.ref, n.month > 0 ? MONTHS[n.month] : ""].filter(Boolean).join(" · ")}: </b>
                      )}
                      {n.body}
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
      )}

      <style>{`@media print { .no-print { display: none !important; } a, nav { display: none !important; } }`}</style>
    </div>
  );
}
