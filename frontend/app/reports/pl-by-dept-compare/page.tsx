"use client";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import {
  getScenarios, getPLByDept,
  type Scenario, type PLByDept,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
function usd(n: number | null) {
  if (n === null || Math.abs(n) < 0.005) return "—";
  const s = Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${s})` : s;
}

export default function PLByDeptCompareReportPage() {
  const tc = useTranslations("common");
  const t = useTranslations("plByDept");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Las tres columnas son Budget / Actual / Forecast: cada una con su llave,
  // porque compartir una haria que elegir en la primera moviera las otras dos.
  // Mientras nadie las toque abren con los preferidos del owner.
  const [id0, setId0] = useEscenarioDe("reports/pl-by-dept-compare:budget",   scenarios, "budget", undefined, true);
  const [id1, setId1] = useEscenarioDe("reports/pl-by-dept-compare:actual",   scenarios, "actual");
  const [id2, setId2] = useEscenarioDe("reports/pl-by-dept-compare:forecast", scenarios, "forecast");
  const ids = useMemo<[string, string, string]>(() => [id0, id1, id2], [id0, id1, id2]);
  const setters: ((v: string) => void)[] = [setId0, setId1, setId2];
  const [month, setMonth] = useState(0);
  const [ytd, setYtd] = useState(true);
  const [byId, setById] = useState<Record<string, PLByDept>>({});
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

  const load = useCallback(async (theIds: string[], m: number, y: boolean) => {
    const uniq = [...new Set(theIds.filter(Boolean))];
    if (!uniq.length) return;
    setLoading(true); setError(null);
    try {
      const results = await Promise.all(uniq.map(async id => [id, await getPLByDept(id, m, m > 0 && y)] as const));
      setById(Object.fromEntries(results));
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(ids, month, ytd); }, [ids, month, ytd, load]);

  const viewLabel = month === 0 ? "Full Year" : (ytd ? "YTD " : "") + MONTHS[month - 1];
  const cols = ids.filter(Boolean);
  const setId = (i: number, v: string) => setters[i](v);

  // Union de departamentos (orden del primero, luego extras)
  const groupOrder: string[] = [];
  const groupName: Record<string, string> = {};
  const groupKind: Record<string, "operating" | "overhead"> = {};
  for (const id of cols) {
    const d = byId[id];
    if (!d) continue;
    for (const r of d.departments) {
      if (!(r.group in groupName)) { groupName[r.group] = r.name; groupKind[r.group] = r.kind; groupOrder.push(r.group); }
    }
  }
  const opGroups = groupOrder.filter(g => groupKind[g] === "operating");
  const ohGroups = groupOrder.filter(g => groupKind[g] === "overhead");

  const OP_METRICS: { key: "revenue" | "payroll" | "operating" | "gop"; label: string; strong?: boolean }[] = [
    { key: "revenue", label: "Revenue" },
    { key: "payroll", label: "Payroll" },
    { key: "operating", label: t("gastosOperativos") },
    { key: "gop", label: t("utilidadDepartamental"), strong: true },
  ];
  const OH_METRICS: { key: "payroll" | "operating" | "total_expenses"; label: string; strong?: boolean }[] = [
    { key: "payroll", label: "Payroll" },
    { key: "operating", label: t("gastosOperativos") },
    { key: "total_expenses", label: t("totalGasto"), strong: true },
  ];
  const metricOf = (id: string, group: string, key: "revenue" | "payroll" | "operating" | "gop" | "total_expenses"): number | null => {
    const d = byId[id]; if (!d) return null;
    const r = d.departments.find(x => x.group === group);
    return r ? r[key] : null;
  };
  const totalGop = (id: string): number | null => byId[id]?.total_gop ?? null;
  const totalOpProfit = (id: string): number | null => byId[id]?.total_operating_profit ?? null;
  const totalOverhead = (id: string): number | null => byId[id]?.total_overhead ?? null;
  const belowOf = (id: string, key: keyof PLByDept["below_gop"]): number | null => {
    const d = byId[id]; return d ? d.below_gop[key] : null;
  };

  const th: React.CSSProperties = { padding: "6px 12px", fontSize: 11, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.4, fontWeight: 700, textAlign: "right" };
  const tdN: React.CSSProperties = { padding: "5px 12px", fontSize: 13, textAlign: "right" };
  const pctStyle: React.CSSProperties = { fontSize: 10.5, fontWeight: 400, color: "var(--text-secondary)" };
  const sectionTd: React.CSSProperties = { padding: "7px 12px", fontSize: 12, fontWeight: 700, color: "var(--brand)", textTransform: "uppercase", letterSpacing: 0.5 };
  const anyData = cols.some(id => byId[id]?.has_data);

  const GroupBlock = ({ groups, metrics, showPct }: {
    groups: string[];
    metrics: { key: "revenue" | "payroll" | "operating" | "gop" | "total_expenses"; label: string; strong?: boolean }[];
    showPct: boolean;
  }) => (
    <>
      {groups.map(g => (
        <Fragment key={g}>
          <tr style={{ background: "rgba(41,98,255,0.07)", borderTop: "1px solid var(--border-medium)" }}>
            <td colSpan={cols.length + 1} style={{ padding: "5px 12px", fontSize: 12, fontWeight: 700, color: "var(--text-primary)", textTransform: "uppercase", letterSpacing: 0.3 }}>{groupName[g]}</td>
          </tr>
          {metrics.map(m => (
            <tr key={m.key} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
              <td style={{ padding: "4px 12px 4px 28px", fontSize: 12.5, fontWeight: m.strong ? 700 : 400, color: m.strong ? "var(--text-primary)" : "var(--text-secondary)" }}>{m.label}</td>
              {cols.map(id => {
                const v = metricOf(id, g, m.key);
                const rev = metricOf(id, g, "revenue");
                const neg = v !== null && v < 0;
                const col = m.key === "gop" ? (neg ? "var(--negative)" : "var(--positive)") : (neg ? "var(--negative)" : "var(--text-primary)");
                const pct = (showPct && m.key !== "revenue" && v !== null && rev !== null && Math.abs(rev) > 0.005) ? (v / rev) * 100 : null;
                return (
                  <td key={id} className="mono" style={{ ...tdN, fontWeight: m.strong ? 700 : 400, color: col }}>
                    {usd(v)}
                    {pct !== null && <div style={pctStyle}>{pct.toFixed(1)}%</div>}
                  </td>
                );
              })}
            </tr>
          ))}
        </Fragment>
      ))}
    </>
  );

  /* Un comparativo sin la comparación no sirve: el archivo lleva UNA columna por
     versión elegida, más Var $ y Var % de la 2ª contra la 1ª. Los % sobre ventas
     que la vista pinta debajo de cada cifra salen como fila propia, en fracción. */
  async function bajarExcel() {
    const nombreDe = (id: string) => { const s = scenarios.find(x => x.id === id); return s ? scnLabel(s) : "—"; };
    const hayVar = cols.length >= 2;
    const conVar = (base: (number | null)[]): (number | null)[] => {
      if (!hayVar) return base;
      const b = base[0], a = base[1];
      const d = (a === null || b === null) ? null : a - b;
      // Variación contra una base de cero no es infinito: no aplica.
      const p = (d === null || b === null || Math.abs(b) < 0.005) ? null : d / Math.abs(b);
      return [...base, d, p];
    };
    // En las filas de % la variación queda vacía: restar dos porcentajes no es una variación.
    const sinVar = (base: (number | null)[]): (number | null)[] => hayVar ? [...base, null, null] : base;
    const VACIA: (number | null)[] = Array(cols.length + (hayVar ? 2 : 0)).fill(null);

    const filas: FilaCuadro[] = [];
    const bloque = (groups: string[], metrics: typeof OP_METRICS | typeof OH_METRICS, showPct: boolean) => {
      for (const g of groups) {
        filas.push({ label: groupName[g], nivel: 1, es_total: true, valores: VACIA });
        for (const m of metrics) {
          filas.push({ label: m.label, nivel: 2, es_total: !!m.strong, valores: conVar(cols.map(id => metricOf(id, g, m.key))) });
          if (showPct && m.key !== "revenue") {
            filas.push({
              label: t("pctSobreVentasDe", { label: m.label }), nivel: 3, formato: "pct",
              valores: sinVar(cols.map(id => {
                const v = metricOf(id, g, m.key), rev = metricOf(id, g, "revenue");
                return (v === null || rev === null || Math.abs(rev) < 0.005) ? null : v / rev;
              })),
            });
          }
        }
      }
    };

    filas.push({ label: t("seccionOperativos"), nivel: 0, es_total: true, valores: VACIA });
    bloque(opGroups, OP_METRICS, true);
    filas.push({ label: "Total Operating Profit", nivel: 0, es_total: true, valores: conVar(cols.map(totalOpProfit)) });
    if (ohGroups.length) {
      filas.push({ label: t("seccionOverhead"), nivel: 0, es_total: true, valores: VACIA });
      bloque(ohGroups, OH_METRICS, false);
      filas.push({ label: "Total Overhead", nivel: 0, es_total: true, valores: conVar(cols.map(totalOverhead)) });
    }
    filas.push({ label: "GROSS OPERATING PROFIT (GOP)", nivel: 0, es_total: true, valores: conVar(cols.map(totalGop)) });
    filas.push({
      label: t("gopPctSobreVentas"), nivel: 1, formato: "pct",
      valores: sinVar(cols.map(id => {
        const v = totalGop(id);
        const rev = (byId[id]?.departments ?? []).reduce((s, r) => s + r.revenue, 0);
        return (v === null || Math.abs(rev) < 0.005) ? null : v / rev;
      })),
    });

    const below: [string, keyof PLByDept["below_gop"], 1 | -1, boolean][] = [
      ["Total Non-Op Expenses", "total_non_op", -1, true],
      ["EBITDA Before Capital", "ebitda_before_capital", 1, true],
      ["Capital Expense", "capital", -1, false],
      ["Financial Expenses", "financial", -1, false],
      ["Total Depreciation", "depreciation", -1, false],
      ["Earnings Before Income Taxes (EBT)", "ebt", 1, true],
      ["Income Taxes", "income_taxes", -1, false],
      ["Net Profit", "net_profit", 1, true],
    ];
    filas.push({ label: "BELOW GOP", nivel: 0, es_total: true, valores: VACIA });
    for (const [label, sel, sign, strong] of below) {
      filas.push({ label, nivel: strong ? 0 : 1, es_total: strong,
                   valores: conVar(cols.map(id => { const raw = belowOf(id, sel); return raw === null ? null : raw * sign; })) });
    }

    try {
      await bajarCuadros("PL_por_Departamento_Compare", [{
        titulo: t("tituloCompare"),
        subtitulo: `USD · ${viewLabel} · ${cols.map(nombreDe).join(" vs ")}`,
        hoja: "Compare",
        columnas: [
          { label: tc("concept"), ancho: 46, formato: "texto" },
          ...cols.map(id => ({ label: nombreDe(id), ancho: 17, formato: "usd2" as const })),
          ...(hayVar ? [
            { label: `Var $ (${nombreDe(cols[1])} − ${nombreDe(cols[0])})`, ancho: 20, formato: "usd2" as const },
            { label: "Var %", ancho: 11, formato: "pct" as const },
          ] : []),
        ],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }

  function BelowRow({ label, sel, sign, strong }: { label: string; sel: keyof PLByDept["below_gop"]; sign: 1 | -1; strong?: boolean }) {
    return (
      <tr style={{ borderTop: strong ? "1px solid var(--border-medium)" : undefined, background: strong ? "rgba(255,255,255,0.02)" : undefined }}>
        <td style={{ padding: "5px 12px", paddingLeft: strong ? 12 : 28, fontSize: 13, fontWeight: strong ? 700 : 400, color: strong ? "var(--text-primary)" : "var(--text-secondary)" }}>{label}</td>
        {cols.map(id => {
          const raw = belowOf(id, sel);
          const v = raw === null ? null : raw * sign;
          return <td key={id} className="mono" style={{ ...tdN, fontWeight: strong ? 700 : 400, color: v !== null && v < 0 ? "var(--negative)" : "var(--text-primary)" }}>{usd(v)}</td>;
        })}
      </tr>
    );
  }

  return (
    <div className="print-dashboard pag pag-media" style={{ padding: "20px 24px" }}>
      <IrA esc={id0} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>{t("tituloCompare")}</h1>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 0" }}>
{t("subtituloCompare", { vista: viewLabel })}
          </p>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <button onClick={() => window.print()} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", alignSelf: "flex-end" }}>{tc("print")}</button>
          <button onClick={bajarExcel} disabled={!anyData} title={t("excelBtnTitleCompare")}
            style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: anyData ? "pointer" : "default", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)", alignSelf: "flex-end", opacity: anyData ? 1 : 0.5 }}>⬇ Excel</button>
          {[t("version", { n: 1 }), t("version", { n: 2 }), t("version", { n: 3 })].map((label, i) => (
            <div key={i} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", letterSpacing: 0.5, textTransform: "uppercase" }}>{label}</span>
              <select value={ids[i]} onChange={e => setId(i, e.target.value)} className="fin-input" style={{ minWidth: 180 }}>
                {i > 0 && <option value="" style={{ background: "var(--bg-input)" }}>{tc("none")}</option>}
                {scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}
              </select>
            </div>
          ))}
        </div>
      </div>

      {/* Period selector */}
      <div className="no-print" style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 18, flexWrap: "wrap" }}>
        {["Full Year", ...MONTHS].map((label, i) => (
          <button key={i} onClick={() => setMonth(i)} style={{
            padding: "5px 11px", fontSize: 12, borderRadius: 5, cursor: "pointer", fontWeight: month === i ? 700 : 400,
            background: month === i ? "var(--brand)" : "var(--bg-elevated)", color: month === i ? "#fff" : "var(--text-secondary)",
            border: `1px solid ${month === i ? "var(--brand)" : "var(--border-medium)"}`,
          }}>{label}</button>
        ))}
        {month > 0 && ([[ "Mes", tc("month") ], [ "YTD", "YTD" ]] as const).map(([lbl, txt]) => {
          const active = (lbl === "YTD") === ytd;
          return (
            <button key={lbl} onClick={() => setYtd(lbl === "YTD")} style={{
              padding: "5px 11px", fontSize: 12, borderRadius: 5, cursor: "pointer", fontWeight: 700,
              background: active ? "var(--positive)" : "var(--bg-elevated)", color: active ? "#fff" : "var(--text-secondary)",
              border: `1px solid ${active ? "var(--positive)" : "var(--border-medium)"}`,
            }}>{txt}</button>
          );
        })}
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>{tc("loading")}</div>}

      {!loading && !anyData && (
        <div style={{ color: "var(--text-secondary)", fontSize: 13, padding: 12, background: "var(--bg-elevated)", borderRadius: 8 }}>
          {t("sinDetalleGlCompare")}
        </div>
      )}

      {!loading && anyData && (
        <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-medium)", background: "var(--bg-header)" }}>
                <th style={{ ...th, textAlign: "left" }}>{tc("concept")}</th>
                {cols.map(id => {
                  const s = scenarios.find(x => x.id === id);
                  return <th key={id} style={th}>{s ? scnLabel(s) : "—"}</th>;
                })}
              </tr>
            </thead>
            <tbody>
              {/* Departamentos generadores de ingresos */}
              <tr style={{ background: "var(--bg-header)" }}>
                <td colSpan={cols.length + 1} style={sectionTd}>{t("seccionOperativos")}</td>
              </tr>
              <GroupBlock groups={opGroups} metrics={OP_METRICS} showPct />
              <tr style={{ borderTop: "1px solid var(--border-medium)", background: "rgba(38,166,154,0.08)" }}>
                <td style={{ padding: "6px 12px", fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>Total Operating Profit</td>
                {cols.map(id => {
                  const v = totalOpProfit(id);
                  return <td key={id} className="mono" style={{ ...tdN, fontWeight: 700, color: v !== null && v < 0 ? "var(--negative)" : "var(--positive)" }}>{usd(v)}</td>;
                })}
              </tr>

              {/* Overhead — gastos no distribuidos (sin ingresos) */}
              {ohGroups.length > 0 && <>
                <tr style={{ background: "var(--bg-header)" }}>
                  <td colSpan={cols.length + 1} style={sectionTd}>{t("seccionOverhead")}</td>
                </tr>
                <GroupBlock groups={ohGroups} metrics={OH_METRICS} showPct={false} />
                <tr style={{ borderTop: "1px solid var(--border-medium)", background: "rgba(239,83,80,0.08)" }}>
                  <td style={{ padding: "6px 12px", fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>Total Overhead</td>
                  {cols.map(id => {
                    const v = totalOverhead(id);
                    return <td key={id} className="mono" style={{ ...tdN, fontWeight: 700, color: "var(--text-primary)" }}>{usd(v)}</td>;
                  })}
                </tr>
              </>}

              {/* GOP = Operating Profit − Overhead */}
              <tr style={{ borderTop: "2px solid var(--border-medium)", background: "rgba(255,255,255,0.05)" }}>
                <td style={{ padding: "7px 12px", fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>GROSS OPERATING PROFIT (GOP)</td>
                {cols.map(id => {
                  const v = totalGop(id);
                  const rev = (byId[id]?.departments ?? []).reduce((s, r) => s + r.revenue, 0);
                  const pct = v !== null && Math.abs(rev) > 0.005 ? (v / rev) * 100 : null;
                  return (
                    <td key={id} className="mono" style={{ ...tdN, fontWeight: 700, color: v !== null && v < 0 ? "var(--negative)" : "var(--positive)" }}>
                      {usd(v)}
                      {pct !== null && <div style={pctStyle}>{pct.toFixed(1)}%</div>}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>

          {/* Below GOP chain */}
          <table style={{ width: "100%", borderCollapse: "collapse", borderTop: "1px solid var(--border-medium)" }}>
            <tbody>
              <BelowRow label="Total Non-Op Expenses" sel="total_non_op" sign={-1} strong />
              <BelowRow label="EBITDA Before Capital" sel="ebitda_before_capital" sign={1} strong />
              <BelowRow label="Capital Expense" sel="capital" sign={-1} />
              <BelowRow label="Financial Expenses" sel="financial" sign={-1} />
              <BelowRow label="Total Depreciation" sel="depreciation" sign={-1} />
              <BelowRow label="Earnings Before Income Taxes (EBT)" sel="ebt" sign={1} strong />
              <BelowRow label="Income Taxes" sel="income_taxes" sign={-1} />
              <BelowRow label="Net Profit" sel="net_profit" sign={1} strong />
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
