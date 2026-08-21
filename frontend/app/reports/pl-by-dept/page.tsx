"use client";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import {
  getScenarios, getPLByDept,
  type Scenario, type PLByDept,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
/** USD con 2 decimales; negativo entre paréntesis; 0 → "—". */
function usd(n: number) {
  if (Math.abs(n) < 0.005) return "—";
  const s = Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${s})` : s;
}

export default function PLByDeptReportPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("plByDept");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se eligio
  // abre con el Budget preferido del owner.
  const [scenarioId, setScenarioId] = useEscenarioDe("reports/pl-by-dept:budget", scenarios, "budget", undefined, true);
  const [month, setMonth] = useState(0);   // 0 = Full Year
  const [ytd, setYtd] = useState(true);
  const [data, setData] = useState<PLByDept | null>(null);
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

  const load = useCallback(async (sid: string, m: number, y: boolean) => {
    if (!sid) return;
    setLoading(true); setError(null);
    try {
      setData(await getPLByDept(sid, m, m > 0 && y));
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId, month, ytd); }, [scenarioId, month, ytd, load]);

  const viewLabel = month === 0 ? "Full Year" : (ytd ? "YTD " : "") + MONTHS[month - 1];
  const bg = data?.below_gop;

  const th: React.CSSProperties = { padding: "6px 12px", fontSize: 11, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.4, fontWeight: 700 };
  const td: React.CSSProperties = { padding: "5px 12px", fontSize: 13, textAlign: "right" };
  const sectionTd: React.CSSProperties = { padding: "7px 12px", fontSize: 12, fontWeight: 700, color: "var(--brand)", textTransform: "uppercase", letterSpacing: 0.5 };
  const opDepts = (data?.departments ?? []).filter(d => d.kind === "operating");
  const ohDepts = (data?.departments ?? []).filter(d => d.kind === "overhead");
  const pctCell = (val: number, rev: number) =>
    Math.abs(rev) > 0.005 ? <div style={{ fontSize: 10.5, fontWeight: 400, color: "var(--text-secondary)" }}>{((val / rev) * 100).toFixed(1)}%</div> : null;

  /* El Excel lleva lo mismo que la pantalla, pero en NÚMERO: los % que la vista
     dibuja debajo de cada cifra salen como columna propia (fracción), no como
     texto pegado. Below-GOP va en su propia hoja porque tiene una sola columna
     de monto: meterlo en la grilla de 6 columnas sería inventar un lugar. */
  async function bajarExcel() {
    if (!data) return;
    const VACIA: (number | null)[] = [null, null, null, null, null, null, null, null];
    const razon = (v: number, rev: number) => Math.abs(rev) > 0.005 ? v / rev : null;
    const filas: FilaCuadro[] = [];
    filas.push({ label: t("seccionOperativos"), nivel: 0, es_total: true, valores: VACIA });
    for (const d of opDepts) {
      filas.push({
        label: d.name, nivel: 1,
        valores: [d.revenue, d.payroll, razon(d.payroll, d.revenue), d.operating,
                  razon(d.operating, d.revenue), d.total_expenses, d.gop, razon(d.gop, d.revenue)],
      });
    }
    filas.push({ label: "Total Operating Profit", nivel: 0, es_total: true,
                 valores: [null, null, null, null, null, null, data.total_operating_profit, null] });
    if (ohDepts.length) {
      filas.push({ label: t("seccionOverhead"), nivel: 0, es_total: true, valores: VACIA });
      for (const d of ohDepts) {
        // Overhead no tiene ingresos: la celda va vacía (null), no en cero.
        filas.push({ label: d.name, nivel: 1,
                     valores: [null, d.payroll, null, d.operating, null, d.total_expenses, null, null] });
      }
      filas.push({ label: "Total Overhead", nivel: 0, es_total: true,
                   valores: [null, null, null, null, null, data.total_overhead, null, null] });
    }
    filas.push({ label: "GROSS OPERATING PROFIT (GOP)", nivel: 0, es_total: true,
                 valores: [null, null, null, null, null, null, data.total_gop, null] });

    const below: FilaCuadro[] = bg ? [
      { label: "Rent", nivel: 1, valores: [-bg.rent] },
      { label: "Management Fees (3% + 5%)", nivel: 1, valores: [-bg.fees] },
      { label: "Property Insurance", nivel: 1, valores: [-bg.insurance] },
      { label: "Other Expenses", nivel: 1, valores: [-bg.other] },
      { label: "Total Non-Op Expenses", nivel: 0, es_total: true, valores: [-bg.total_non_op] },
      { label: "EBITDA Before Capital", nivel: 0, es_total: true, valores: [bg.ebitda_before_capital] },
      { label: "Capital Expense", nivel: 1, valores: [-bg.capital] },
      { label: "Financial Expenses", nivel: 1, valores: [-bg.financial] },
      { label: "Total Depreciation", nivel: 1, valores: [-bg.depreciation] },
      { label: "Earnings Before Income Taxes (EBT)", nivel: 0, es_total: true, valores: [bg.ebt] },
      { label: "Income Taxes", nivel: 1, valores: [-bg.income_taxes] },
      { label: "Net Profit", nivel: 0, es_total: true, valores: [bg.net_profit] },
    ] : [];

    const sub = `${hotel.nombre} · USD · ${viewLabel} · ${scenarios.find(s => s.id === scenarioId) ? scnLabel(scenarios.find(s => s.id === scenarioId)!) : ""}`;
    try {
      await bajarCuadros("PL_por_Departamento", [
        {
          titulo: t("titulo"), subtitulo: sub, hoja: t("hoja"),
          columnas: [
            { label: tc("department"), ancho: 40, formato: "texto" },
            { label: "Revenue", formato: "usd2" },
            { label: "Payroll", formato: "usd2" },
            { label: "% Payroll", ancho: 11, formato: "pct" },
            { label: t("gastosOperativos"), ancho: 17, formato: "usd2" },
            { label: t("pctGastosOp"), ancho: 12, formato: "pct" },
            { label: t("totalGastos"), ancho: 15, formato: "usd2" },
            { label: "GOP", formato: "usd2" },
            { label: "% GOP", ancho: 10, formato: "pct" },
          ],
          filas,
        },
        ...(below.length ? [{
          titulo: "Below GOP (company-level)", subtitulo: sub, hoja: "Below GOP",
          columnas: [{ label: tc("concept"), ancho: 44, formato: "texto" as const }, { label: t("monto"), ancho: 16, formato: "usd2" as const }],
          filas: below,
        }] : []),
      ]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }

  function BelowRow({ label, value, strong, indent }: { label: string; value: number; strong?: boolean; indent?: boolean }) {
    return (
      <tr style={{ borderTop: strong ? "1px solid var(--border-medium)" : undefined, background: strong ? "rgba(255,255,255,0.02)" : undefined }}>
        <td style={{ padding: "5px 12px", paddingLeft: indent ? 28 : 12, fontSize: 13, fontWeight: strong ? 700 : 400, color: strong ? "var(--text-primary)" : "var(--text-secondary)" }}>{label}</td>
        <td className="mono" style={{ ...td, fontWeight: strong ? 700 : 400, color: value < 0 ? "var(--negative)" : "var(--text-primary)" }}>{usd(value)}</td>
      </tr>
    );
  }

  return (
    <div className="print-dashboard pag pag-media" style={{ padding: "20px 24px" }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>{t("titulo")}</h1>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 0" }}>
            {hotel.nombre} · USD · {viewLabel}
          </p>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <button onClick={() => window.print()} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)" }}>{tc("print")}</button>
          <button onClick={bajarExcel} disabled={!data?.has_data} title={t("excelBtnTitle")}
            style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: data?.has_data ? "pointer" : "default", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)", opacity: data?.has_data ? 1 : 0.5 }}>⬇ Excel</button>
          <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 220 }}>
            {scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}
          </select>
        </div>
      </div>

      {/* Period selector */}
      <div className="no-print" style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 18, flexWrap: "wrap" }}>
        {["Full Year", ...MONTHS].map((label, i) => (
          <button key={i} onClick={() => setMonth(i)} style={{
            padding: "5px 11px", fontSize: 12, borderRadius: 5, cursor: "pointer",
            fontWeight: month === i ? 700 : 400,
            background: month === i ? "var(--brand)" : "var(--bg-elevated)",
            color: month === i ? "#fff" : "var(--text-secondary)",
            border: `1px solid ${month === i ? "var(--brand)" : "var(--border-medium)"}`,
          }}>{label}</button>
        ))}
        {month > 0 && ([[ "Mes", tc("month") ], [ "YTD", "YTD" ]] as const).map(([lbl, txt]) => {
          const active = (lbl === "YTD") === ytd;
          return (
            <button key={lbl} onClick={() => setYtd(lbl === "YTD")} style={{
              padding: "5px 11px", fontSize: 12, borderRadius: 5, cursor: "pointer", fontWeight: 700,
              background: active ? "var(--positive)" : "var(--bg-elevated)",
              color: active ? "#fff" : "var(--text-secondary)",
              border: `1px solid ${active ? "var(--positive)" : "var(--border-medium)"}`,
            }}>{txt}</button>
          );
        })}
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>{tc("loading")}</div>}

      {!loading && data && !data.has_data && (
        <div style={{ color: "var(--text-secondary)", fontSize: 13, padding: 12, background: "var(--bg-elevated)", borderRadius: 8 }}>
          {t("sinDetalleGl")}
        </div>
      )}

      {!loading && data && data.has_data && (
        <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-medium)", background: "var(--bg-header)" }}>
                <th style={{ ...th, textAlign: "left" }}>{tc("department")}</th>
                <th style={{ ...th, textAlign: "right" }}>Revenue</th>
                <th style={{ ...th, textAlign: "right" }}>Payroll</th>
                <th style={{ ...th, textAlign: "right" }}>{t("gastosOperativos")}</th>
                <th style={{ ...th, textAlign: "right" }}>{t("totalGastos")}</th>
                <th style={{ ...th, textAlign: "right" }}>GOP</th>
              </tr>
            </thead>
            <tbody>
              {/* Operativos (generan ingresos) */}
              <tr style={{ background: "var(--bg-header)" }}>
                <td colSpan={6} style={sectionTd}>{t("seccionOperativos")}</td>
              </tr>
              {opDepts.map(d => (
                <tr key={d.group} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "5px 12px", fontSize: 13, color: "var(--text-primary)" }}>{d.name}</td>
                  <td className="mono" style={td}>{usd(d.revenue)}</td>
                  <td className="mono" style={td}>{usd(d.payroll)}{pctCell(d.payroll, d.revenue)}</td>
                  <td className="mono" style={td}>{usd(d.operating)}{pctCell(d.operating, d.revenue)}</td>
                  <td className="mono" style={td}>{usd(d.total_expenses)}</td>
                  <td className="mono" style={{ ...td, fontWeight: 600, color: d.gop < 0 ? "var(--negative)" : "var(--positive)" }}>{usd(d.gop)}{pctCell(d.gop, d.revenue)}</td>
                </tr>
              ))}
              <tr style={{ borderTop: "1px solid var(--border-medium)", background: "rgba(38,166,154,0.08)" }}>
                <td colSpan={5} style={{ padding: "6px 12px", fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>Total Operating Profit</td>
                <td className="mono" style={{ ...td, fontWeight: 700, color: data.total_operating_profit < 0 ? "var(--negative)" : "var(--positive)" }}>{usd(data.total_operating_profit)}</td>
              </tr>

              {/* Overhead — gastos no distribuidos (sin ingresos) */}
              {ohDepts.length > 0 && <>
                <tr style={{ background: "var(--bg-header)" }}>
                  <td colSpan={6} style={sectionTd}>{t("seccionOverhead")}</td>
                </tr>
                {ohDepts.map(d => (
                  <tr key={d.group} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "5px 12px", fontSize: 13, color: "var(--text-primary)" }}>{d.name}</td>
                    <td className="mono" style={{ ...td, color: "var(--text-disabled)" }}>—</td>
                    <td className="mono" style={td}>{usd(d.payroll)}</td>
                    <td className="mono" style={td}>{usd(d.operating)}</td>
                    <td className="mono" style={{ ...td, fontWeight: 600 }}>{usd(d.total_expenses)}</td>
                    <td className="mono" style={{ ...td, color: "var(--text-disabled)" }}>—</td>
                  </tr>
                ))}
                <tr style={{ borderTop: "1px solid var(--border-medium)", background: "rgba(239,83,80,0.08)" }}>
                  <td colSpan={4} style={{ padding: "6px 12px", fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>Total Overhead</td>
                  <td className="mono" style={{ ...td, fontWeight: 700 }}>{usd(data.total_overhead)}</td>
                  <td className="mono" style={{ ...td, color: "var(--text-disabled)" }}>—</td>
                </tr>
              </>}

              {/* GOP = Operating Profit − Overhead */}
              <tr style={{ borderTop: "2px solid var(--border-medium)", background: "rgba(255,255,255,0.04)" }}>
                <td colSpan={5} style={{ padding: "7px 12px", fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>GROSS OPERATING PROFIT (GOP)</td>
                <td className="mono" style={{ ...td, fontWeight: 700, color: data.total_gop < 0 ? "var(--negative)" : "var(--positive)" }}>{usd(data.total_gop)}</td>
              </tr>
            </tbody>
          </table>

          {/* Below GOP (company-level) */}
          {bg && (
            <table style={{ width: "100%", borderCollapse: "collapse", borderTop: "1px solid var(--border-medium)" }}>
              <tbody>
                <BelowRow label="Rent" value={-bg.rent} indent />
                <BelowRow label="Management Fees (3% + 5%)" value={-bg.fees} indent />
                <BelowRow label="Property Insurance" value={-bg.insurance} indent />
                <BelowRow label="Other Expenses" value={-bg.other} indent />
                <BelowRow label="Total Non-Op Expenses" value={-bg.total_non_op} strong />
                <BelowRow label="EBITDA Before Capital" value={bg.ebitda_before_capital} strong />
                <BelowRow label="Capital Expense" value={-bg.capital} indent />
                <BelowRow label="Financial Expenses" value={-bg.financial} indent />
                <BelowRow label="Total Depreciation" value={-bg.depreciation} indent />
                <BelowRow label="Earnings Before Income Taxes (EBT)" value={bg.ebt} strong />
                <BelowRow label="Income Taxes" value={-bg.income_taxes} indent />
                <BelowRow label="Net Profit" value={bg.net_profit} strong />
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
