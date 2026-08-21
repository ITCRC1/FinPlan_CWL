"use client";
import { usePlanningScenario, usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { money2 } from "@/lib/fmt";
import RecalcButton from "@/components/RecalcButton";
import AvisoLineasObligatorias from "@/components/AvisoLineasObligatorias";
import { useEffect, useState, useCallback, useRef } from "react";
import { HOTEL_ID } from "@/lib/hotel";
import IrA from "@/components/IrA";
import {
  getScenarios, getNonOp, bulkReplaceNonOp,
  nonopExcelUrl, importNonopExcel,
  type Scenario, type NonOpBulkRow,
} from "@/lib/api";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTH_KEYS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];

type LineKind = "manual" | "driver";
type LineDef = { code: string; name: string; account_code?: string; kind: LineKind; driverNote?: string };
type Section = { title: string; subtotal: string; lines: LineDef[] };

// Below-GOP organised by P&L group, mirroring the owner report. Manual lines
// are mini checkbooks; driver lines (mgmt fee, income tax) are computed.
const SECTIONS: Section[] = [
  // Cuentas reales de dueños (8xxx). Owners Fee (8005) y Capital Reserve (8020)
  // son % de revenue → tab Management Fees. Income Tax (8060) se calcula (30% EBT).
  // Aquí van las manuales, mapeadas a las líneas P&L below-GOP existentes.
  {
    title: "Other / Non-Deductible", subtotal: "Total Other Expenses",
    lines: [
      { code: "OTHER_EXPENSES", name: "Fines & Other Non-Deductible Expenses", account_code: "8025", kind: "manual" },
    ],
  },
  {
    title: "Financial Expenses", subtotal: "Financial Expenses",
    lines: [
      { code: "BANK_INTEREST", name: "Bank and Commissions Charges", account_code: "8030", kind: "manual" },
      { code: "LEASINGS_RENTS", name: "Interest on Loans", account_code: "8035", kind: "manual" },
      { code: "FINANCIAL_LOSSES", name: "Exchange Gain/Losses", account_code: "8045", kind: "manual" },
    ],
  },
  {
    title: "Depreciation", subtotal: "Total Depreciations",
    lines: [
      { code: "DEPRECIATION", name: "Depreciation", account_code: "8040", kind: "manual" },
    ],
  },
];

type Row = {
  key: string;
  report_line_code: string;
  account_code: string;
  detail_desc: string;
  months: Record<string, string>;
};

let _seq = 0;
function newKey() { return `r${Date.now()}_${_seq++}`; }
function emptyMonths(): Record<string, string> {
  return Object.fromEntries(MONTH_KEYS.map(mk => [mk, "0"]));
}
function num(v: string): number { return parseFloat(v) || 0; }
function fmtUsd(n: number) {
  if (!n) return <span style={{ color: "var(--text-disabled)" }}>—</span>;
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return <>{n < 0 ? `(${s})` : s}</>;
}

export default function NonOpCheckbookPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios]   = useState<Scenario[]>([]);
  const [rows, setRows]             = useState<Row[]>([]);
  const [loading, setLoading]       = useState(true);
  const [saving, setSaving]         = useState(false);
  const [dirty, setDirty]           = useState(false);
  const [msg, setMsg]               = useState<string | null>(null);
  const [error, setError]           = useState<string | null>(null);
  const [xlsxUp, setXlsxUp]        = useState(false);
  const fileRef                     = useRef<HTMLInputElement>(null);

  async function handleXlsxUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !scenarioId) return;
    setXlsxUp(true); setMsg(null);
    try {
      const r = await importNonopExcel(scenarioId, file);
      setMsg(`✓ Excel importado: ${r.imported} líneas`);
      load(scenarioId);
    } catch (ex: unknown) {
      setMsg(`Error: ${ex instanceof Error ? ex.message : String(ex)}`);
    } finally {
      setXlsxUp(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const load = useCallback(async (sid: string) => {
    const data = await getNonOp(sid);
    const loaded: Row[] = [];
    for (const grp of data.lines) {
      for (const ln of grp.lines) {
        loaded.push({
          key: newKey(),
          report_line_code: grp.report_line_code,
          account_code: grp.account_code,
          detail_desc: ln.detail_desc,
          months: Object.fromEntries(MONTH_KEYS.map(mk => [mk, money2(ln[mk as keyof typeof ln] as string)])),
        });
      }
    }
    setRows(loaded);
    setDirty(false);
  }, []);

  useEffect(() => {
    (async () => {
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
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Recargar las líneas cuando cambia el escenario (sync con Master Data del año)
  useEffect(() => {
    if (scenarioId) load(scenarioId);
  }, [scenarioId, load]);

  function addLine(line: LineDef) {
    setRows(prev => [...prev, {
      key: newKey(), report_line_code: line.code,
      account_code: line.account_code ?? "", detail_desc: "", months: emptyMonths(),
    }]);
    setDirty(true);
  }
  function deleteRow(key: string) {
    setRows(prev => prev.filter(r => r.key !== key));
    setDirty(true);
  }
  function setMonth(key: string, mk: string, v: string) {
    setRows(prev => prev.map(r => r.key === key ? { ...r, months: { ...r.months, [mk]: v } } : r));
    setDirty(true);
  }
  function setDesc(key: string, v: string) {
    setRows(prev => prev.map(r => r.key === key ? { ...r, detail_desc: v } : r));
    setDirty(true);
  }

  async function save() {
    if (!scenarioId) return;
    setSaving(true);
    setMsg(null);
    try {
      const perLine: Record<string, number> = {};
      const payload: NonOpBulkRow[] = rows.map(r => {
        const idx = (perLine[r.report_line_code] = (perLine[r.report_line_code] ?? 0) + 1);
        return {
          report_line_code: r.report_line_code,
          account_code: r.account_code,
          account_name: "",
          detail_code: String(idx),
          detail_desc: r.detail_desc,
          ...Object.fromEntries(MONTH_KEYS.map(mk => [mk, num(r.months[mk])])),
        } as NonOpBulkRow;
      });
      const res = await bulkReplaceNonOp(scenarioId, payload);
      setMsg(`✓ Guardado: ${res.imported} líneas`);
      await load(scenarioId);
    } catch (e: unknown) {
      setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  function lineMonth(code: string, mk: string): number {
    return rows.filter(r => r.report_line_code === code).reduce((s, r) => s + num(r.months[mk]), 0);
  }
  function lineAnnual(code: string): number {
    return MONTH_KEYS.reduce((s, mk) => s + lineMonth(code, mk), 0);
  }

  const grandByMonth = MONTH_KEYS.map(mk =>
    SECTIONS.flatMap(s => s.lines).filter(l => l.kind === "manual")
      .reduce((s, l) => s + lineMonth(l.code, mk), 0)
  );
  const grandAnnual = grandByMonth.reduce((a, b) => a + b, 0);

  return (
    <div className="pag pag-ancha">
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>
            Gastos del Propietario — Below GOP
          </h2>
          <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)" }}>
            Por grupos de P&L · auxiliar por línea de detalle
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
          <RecalcButton scenarioId={scenarioId} />
          <button
            onClick={save}
            disabled={saving || !dirty || !scenarioId}
            style={{
              padding: "6px 18px", fontSize: 12, borderRadius: 4,
              background: dirty && !saving ? "#1E3A5F" : "var(--bg-elevated)",
              color: dirty && !saving ? "#90CAF9" : "var(--text-secondary)",
              border: `1px solid ${dirty && !saving ? "#2962FF" : "var(--border-subtle)"}`,
              cursor: dirty && !saving ? "pointer" : "default",
            }}
          >
            {saving ? "Guardando..." : dirty ? "Guardar cambios" : "Sin cambios"}
          </button>
          {scenarioId && (
            <a href={nonopExcelUrl(scenarioId)} download style={{
              padding: "5px 14px", fontSize: 12, borderRadius: 4, textDecoration: "none",
              background: "var(--bg-elevated)", color: "var(--text-secondary)",
              border: "1px solid var(--border-medium)", lineHeight: "20px", display: "inline-block",
            }}>⬇ Excel</a>
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

      <AvisoLineasObligatorias scenarioId={scenarioId} />

      <p style={{ margin: "0 0 12px", fontSize: 11, color: "var(--text-secondary)" }}>
        Management Fees (Revenue × %) e Income Tax (EBT × 30%) son drivers calculados — se muestran de referencia, no se editan aquí.
      </p>

      {msg && (
        <div style={{
          marginBottom: 12, padding: "8px 14px", borderRadius: 4, fontSize: 12,
          background: msg.startsWith("✓") ? "rgba(38,166,154,0.08)" : "rgba(239,83,80,0.08)",
          color: msg.startsWith("✓") ? "var(--positive)" : "var(--negative)",
          border: `1px solid ${msg.startsWith("✓") ? "var(--positive)" : "var(--negative)"}`,
        }}>{msg}</div>
      )}

      {loading && <p style={{ color: "var(--text-secondary)" }}>{tc("loading")}</p>}
      {error && (
        <div style={{ color: "var(--negative)", background: "var(--bg-surface)", padding: "12px 16px", borderRadius: 4 }}>
          ⚠ {error}
        </div>
      )}

      {!loading && !error && (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1440, fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", width: 300 }}>Detalle</th>
                {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 74 }}>{m}</th>)}
                <th style={{ textAlign: "right", color: "var(--brand)", minWidth: 88 }}>{tc("annual")}</th>
                <th style={{ width: 28 }}></th>
              </tr>
            </thead>
            <tbody>
              {SECTIONS.map(sec => (
                <SectionBlock
                  key={sec.title}
                  sec={sec}
                  rows={rows}
                  lineMonth={lineMonth}
                  lineAnnual={lineAnnual}
                  onAdd={addLine}
                  onDelete={deleteRow}
                  onSetMonth={setMonth}
                  onSetDesc={setDesc}
                />
              ))}

              <tr className="total" style={{ borderTop: "2px solid var(--border-medium)" }}>
                <td style={{ fontWeight: 700, color: "var(--text-primary)" }}>
                  TOTAL BELOW-GOP (líneas manuales)
                </td>
                {grandByMonth.map((v, i) => (
                  <td key={i} className="mono" style={{
                    textAlign: "right", fontWeight: 700,
                    color: v ? "var(--positive)" : "var(--text-disabled)",
                  }}>{fmtUsd(v)}</td>
                ))}
                <td className="mono" style={{ textAlign: "right", fontWeight: 700, color: "var(--positive)" }}>
                  {fmtUsd(grandAnnual)}
                </td>
                <td></td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SectionBlock({
  sec, rows, lineMonth, lineAnnual, onAdd, onDelete, onSetMonth, onSetDesc,
}: {
  sec: Section;
  rows: Row[];
  lineMonth: (code: string, mk: string) => number;
  lineAnnual: (code: string) => number;
  onAdd: (line: LineDef) => void;
  onDelete: (key: string) => void;
  onSetMonth: (key: string, mk: string, v: string) => void;
  onSetDesc: (key: string, v: string) => void;
}) {
  const subMonth = MONTH_KEYS.map(mk => sec.lines.reduce((s, l) => s + lineMonth(l.code, mk), 0));
  const subAnnual = subMonth.reduce((a, b) => a + b, 0);

  return (
    <>
      {/* Section header */}
      <tr style={{ background: "var(--bg-elevated)", borderTop: "1px solid var(--border-medium)" }}>
        <td colSpan={15} style={{
          color: "var(--text-secondary)", fontWeight: 600, fontSize: 11,
          letterSpacing: "0.04em", textTransform: "uppercase", paddingLeft: 8,
        }}>{sec.title}</td>
      </tr>

      {sec.lines.map(line => (
        <LineBlock
          key={line.code}
          line={line}
          lineRows={rows.filter(r => r.report_line_code === line.code)}
          lineMonth={lineMonth}
          lineAnnual={lineAnnual}
          onAdd={onAdd}
          onDelete={onDelete}
          onSetMonth={onSetMonth}
          onSetDesc={onSetDesc}
        />
      ))}

      {/* Section subtotal */}
      <tr style={{ borderTop: "1px solid var(--border-subtle)" }}>
        <td style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: 11, paddingLeft: 8 }}>
          {sec.subtotal}
        </td>
        {subMonth.map((v, i) => (
          <td key={i} className="mono" style={{
            textAlign: "right", fontWeight: 600, fontSize: 11,
            color: v ? "var(--text-primary)" : "var(--text-disabled)",
          }}>{fmtUsd(v)}</td>
        ))}
        <td className="mono" style={{ textAlign: "right", fontWeight: 700, color: "var(--brand)", fontSize: 11 }}>
          {fmtUsd(subAnnual)}
        </td>
        <td></td>
      </tr>
    </>
  );
}

function LineBlock({
  line, lineRows, lineMonth, lineAnnual, onAdd, onDelete, onSetMonth, onSetDesc,
}: {
  line: LineDef;
  lineRows: Row[];
  lineMonth: (code: string, mk: string) => number;
  lineAnnual: (code: string) => number;
  onAdd: (line: LineDef) => void;
  onDelete: (key: string) => void;
  onSetMonth: (key: string, mk: string, v: string) => void;
  onSetDesc: (key: string, v: string) => void;
}) {
  const t = useTranslations("nonop");
  const tc = useTranslations("common");
  // Driver lines: read-only reference (computed by the engine).
  if (line.kind === "driver") {
    return (
      <tr>
        <td style={{ paddingLeft: 20, color: "var(--text-secondary)", fontSize: 11 }}>
          {line.name}
          <span style={{
            marginLeft: 8, fontSize: 9, padding: "1px 6px", borderRadius: 3,
            background: "var(--bg-elevated)", color: "var(--text-disabled)",
          }}>driver · {line.driverNote}</span>
        </td>
        <td colSpan={14} style={{ color: "var(--text-disabled)", fontSize: 11, textAlign: "right", paddingRight: 8 }}>
          calculado en el P&L
        </td>
      </tr>
    );
  }

  const annual = lineAnnual(line.code);
  return (
    <>
      {/* Manual line header (account + line total) */}
      <tr>
        <td style={{ paddingLeft: 20, color: "var(--text-primary)", fontSize: 12, fontWeight: 500 }}>
          {line.name}
          {line.account_code && (
            <span style={{ marginLeft: 6, fontSize: 10, color: "var(--text-secondary)" }}>
              ({line.account_code})
            </span>
          )}
        </td>
        {MONTH_KEYS.map(mk => (
          <td key={mk} className="mono" style={{
            textAlign: "right", fontSize: 11, color: "var(--text-secondary)", padding: "2px 6px",
          }}>{fmtUsd(lineMonth(line.code, mk))}</td>
        ))}
        <td className="mono" style={{ textAlign: "right", fontWeight: 600, fontSize: 11, color: "var(--text-primary)" }}>
          {fmtUsd(annual)}
        </td>
        <td></td>
      </tr>

      {/* Detail rows */}
      {lineRows.map(r => {
        const rowAnnual = MONTH_KEYS.reduce((s, mk) => s + (parseFloat(r.months[mk]) || 0), 0);
        return (
          <tr key={r.key}>
            <td style={{ paddingLeft: 40 }}>
              <input
                value={r.detail_desc}
                placeholder={t("descPlaceholder")}
                onChange={e => onSetDesc(r.key, e.target.value)}
                className="fin-input"
                style={{ width: 230, fontSize: 11 }}
              />
            </td>
            {MONTH_KEYS.map(mk => (
              <td key={mk} className="mono" style={{ textAlign: "right", padding: "2px 6px" }}>
                <input
                  value={r.months[mk]}
                  onChange={e => onSetMonth(r.key, mk, e.target.value)}
                  className="fin-input"
                  style={{ width: 66, textAlign: "right" }}
                />
              </td>
            ))}
            <td className="mono" style={{
              textAlign: "right", fontSize: 11,
              color: rowAnnual ? "var(--text-primary)" : "var(--text-disabled)",
            }}>{fmtUsd(rowAnnual)}</td>
            <td style={{ textAlign: "center" }}>
              <button
                onClick={() => onDelete(r.key)}
                title={tc("deleteLine")}
                style={{ background: "none", border: "none", color: "var(--negative)", cursor: "pointer", fontSize: 14, padding: 0 }}
              >×</button>
            </td>
          </tr>
        );
      })}

      <tr>
        <td style={{ paddingLeft: 40 }}>
          <button
            onClick={() => onAdd(line)}
            style={{
              background: "none", border: "1px dashed var(--border-medium)",
              color: "var(--text-secondary)", borderRadius: 4, padding: "2px 10px",
              fontSize: 11, cursor: "pointer",
            }}
          >{t("addLine")}</button>
        </td>
        <td colSpan={14}></td>
      </tr>
    </>
  );
}
