"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useRef } from "react";
import { HOTEL_ID } from "@/lib/hotel";
import IrA from "@/components/IrA";
import {
  getScenarios, getFteReport,
  payrollExcelUrl, importPayrollExcel,
  type Scenario, type FteReportRow,
} from "@/lib/api";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

function FteCell({ fte }: { fte: number }) {
  if (fte === 0) return <td className="mono" style={{ color: "var(--text-disabled)", textAlign: "center" }}>—</td>;
  const color = fte >= 1 ? "var(--text-primary)" : fte >= 0.5 ? "var(--warning)" : "var(--negative)";
  return <td className="mono" style={{ color, textAlign: "center", fontWeight: fte >= 1 ? 500 : 400 }}>{fte.toFixed(1)}</td>;
}

export default function FteReportPage() {
  const tc = useTranslations("common");
  const t = useTranslations("payrollCb");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios]   = useState<Scenario[]>([]);
  const [rows, setRows]             = useState<FteReportRow[]>([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);
  const [xlsxMsg, setXlsxMsg]      = useState<string | null>(null);
  const [xlsxUp, setXlsxUp]        = useState(false);
  const fileRef                     = useRef<HTMLInputElement>(null);

  async function loadReport(sid: string) {
    const data = await getFteReport(sid);
    setRows(data);
  }

  useEffect(() => {
    async function init() {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        // La regla del owner, una sola: `elegir(all, "budget")` = Budget Working
        // 2027. Acá había un año QUEMADO A MANO y, si no aparecía, `all[0]` —
        // que con `/scenarios/` ordenado por año descendente es **Working
        // 2035**. Ver `lib/escenarioPreferido`.
        const sc = elegir(all, "budget") ?? all[0];
        if (!sc) { setError(`No hay escenarios para ${HOTEL_ID}.`); return; }
        setScenarioId(sharedScenarioOr(sc.id));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Error");
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  // Recargar el reporte cuando cambia el escenario (sync con Master Data del año)
  useEffect(() => {
    if (!scenarioId) return;
    loadReport(scenarioId).catch(e => setError(e instanceof Error ? e.message : "Error"));
  }, [scenarioId]);

  async function handleXlsxUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !scenarioId) return;
    setXlsxUp(true); setXlsxMsg(null);
    try {
      const r = await importPayrollExcel(scenarioId, file);
      setXlsxMsg(`✓ ${r.imported} posiciones importadas. ${r.note ?? "Recalcula la planilla después."}`);
      await loadReport(scenarioId);
    } catch (ex: unknown) {
      setXlsxMsg(`Error: ${ex instanceof Error ? ex.message : String(ex)}`);
    } finally {
      setXlsxUp(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  // Group rows by dept
  const byDept: Record<string, { name: string; rows: FteReportRow[] }> = {};
  for (const row of rows) {
    if (!byDept[row.dept_code]) byDept[row.dept_code] = { name: row.dept_name, rows: [] };
    byDept[row.dept_code].rows.push(row);
  }

  const totals = MONTHS.map((_, i) =>
    rows.reduce((s, r) => s + (r.fte_by_month[i] ?? 0), 0)
  );

  return (
    <div className="pag pag-ancha">
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>
            Reporte FTE — Planilla
          </h2>
          <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)" }}>
            Todos los departamentos × 12 meses
          </p>
        </div>
        <select
          value={scenarioId ?? ""}
          onChange={e => setScenarioId(e.target.value)}
          title={tc("scenarioSynced")}
          style={{
            background: "var(--bg-input)", color: "var(--text-primary)",
            border: "1px solid var(--border-medium)", borderRadius: 4,
            padding: "5px 10px", fontSize: 13, cursor: "pointer",
          }}
        >
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>
          ))}
        </select>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          {scenarioId && (
            <a href={payrollExcelUrl(scenarioId)} download style={{
              padding: "5px 14px", fontSize: 12, borderRadius: 4, textDecoration: "none",
              background: "var(--bg-elevated)", color: "var(--text-secondary)",
              border: "1px solid var(--border-medium)", lineHeight: "20px", display: "inline-block",
            }}>⬇ Excel Planilla</a>
          )}
          <input ref={fileRef} type="file" accept=".xlsx" style={{ display: "none" }} onChange={handleXlsxUpload} />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={xlsxUp || !scenarioId}
            style={{
              padding: "5px 14px", fontSize: 12, borderRadius: 4,
              background: xlsxUp ? "var(--bg-elevated)" : "#1E3A5F",
              color: xlsxUp ? "var(--text-disabled)" : "#90CAF9",
              border: "1px solid #2962FF", cursor: xlsxUp ? "default" : "pointer",
            }}
          >{xlsxUp ? "Subiendo..." : "↑ Subir Excel"}</button>
        </div>
      </div>

      {xlsxMsg && (
        <div style={{
          marginBottom: 12, padding: "8px 14px", borderRadius: 4, fontSize: 12,
          background: xlsxMsg.startsWith("✓") ? "rgba(38,166,154,0.08)" : "rgba(239,83,80,0.08)",
          color: xlsxMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)",
          border: `1px solid ${xlsxMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)"}`,
        }}>{xlsxMsg}</div>
      )}

      {loading && <p style={{ color: "var(--text-secondary)" }}>{tc("loading")}</p>}
      {error && (
        <div style={{ color: "var(--negative)", background: "var(--bg-surface)", padding: "12px 16px", borderRadius: 4 }}>
          ⚠ {error}
        </div>
      )}

      {!loading && !error && rows.length === 0 && (
        <p style={{ color: "var(--text-secondary)" }}>
          Sin datos de planilla. Exportá el Excel, llenalo con las posiciones y salarios, y subilo con el botón ↑.
        </p>
      )}

      {!loading && !error && rows.length > 0 && (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table">
            <thead>
              <tr>
                <th style={{ textAlign: "left", width: 120 }}>{tc("dept")}</th>
                <th style={{ textAlign: "left", width: 180 }}>{t("position")}</th>
                <th style={{ textAlign: "left", width: 140 }}>{tc("employee")}</th>
                {MONTHS.map(m => <th key={m} style={{ textAlign: "center" }}>{m}</th>)}
                <th style={{ textAlign: "center" }}>Total</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(byDept).map(([deptCode, dept]) => {
                const deptTotals = MONTHS.map((_, i) =>
                  dept.rows.reduce((s, r) => s + (r.fte_by_month[i] ?? 0), 0)
                );
                const deptAnnual = deptTotals.reduce((s, v) => s + v, 0);
                return [
                  <tr key={`dept-${deptCode}`} style={{ background: "var(--bg-elevated)" }}>
                    <td colSpan={3} style={{
                      color: "var(--brand)", fontWeight: 600, fontSize: 12,
                      borderTop: "1px solid var(--border-medium)",
                    }}>
                      {deptCode} — {dept.name}
                    </td>
                    {deptTotals.map((v, i) => (
                      <td key={i} className="mono" style={{
                        textAlign: "center", fontWeight: 600,
                        color: v === 0 ? "var(--text-disabled)" : "var(--brand)",
                        borderTop: "1px solid var(--border-medium)",
                      }}>
                        {v === 0 ? "—" : v.toFixed(1)}
                      </td>
                    ))}
                    <td className="mono" style={{
                      textAlign: "center", fontWeight: 700, color: "var(--brand)",
                      borderTop: "1px solid var(--border-medium)",
                    }}>
                      {deptAnnual.toFixed(1)}
                    </td>
                  </tr>,
                  ...dept.rows.map(row => {
                    const annual = row.fte_by_month.reduce((s, v) => s + v, 0);
                    return (
                      <tr key={row.position_id}>
                        <td style={{ color: "var(--text-secondary)", fontSize: 11, paddingLeft: 20 }}>{deptCode}</td>
                        <td style={{ color: "var(--text-primary)" }}>{row.position_name}</td>
                        <td style={{ color: row.employee_name === "VACANTE" ? "var(--text-disabled)" : "var(--text-secondary)" }}>
                          {row.employee_name}
                        </td>
                        {row.fte_by_month.map((fte, i) => <FteCell key={i} fte={fte} />)}
                        <td className="mono" style={{
                          textAlign: "center", fontWeight: 600,
                          color: annual === 0 ? "var(--text-disabled)" : "var(--text-primary)",
                        }}>
                          {annual === 0 ? "—" : annual.toFixed(1)}
                        </td>
                      </tr>
                    );
                  }),
                ];
              })}
              <tr className="total">
                <td colSpan={3} style={{ color: "var(--text-primary)", fontWeight: 700 }}>TOTAL FTE</td>
                {totals.map((v, i) => (
                  <td key={i} className="mono" style={{ textAlign: "center", fontWeight: 700, color: "var(--positive)" }}>
                    {v === 0 ? "—" : v.toFixed(1)}
                  </td>
                ))}
                <td className="mono" style={{ textAlign: "center", fontWeight: 700, color: "var(--positive)" }}>
                  {totals.reduce((s, v) => s + v, 0).toFixed(1)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
