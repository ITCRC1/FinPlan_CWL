"use client";
import { usePlanningScenario, usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import AvisoMoneda from "@/components/AvisoMoneda";
import AvisoLineasObligatorias from "@/components/AvisoLineasObligatorias";
import RecalcButton from "@/components/RecalcButton";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  getScenarios, getCostDepts, getCostDeptCheckbook, getCostSummary,
  updateCostEntry, recalculateCosts, costsExcelUrl, importCostsExcel,
  createCostEntry, deleteCostEntry, getCostCatalog,
  type Scenario, type CostEntry, type CostDeptCheckbook, type CostMonthlySummary,
  type CalcMode, type DriverType, type RevenueLine, type CostCatalogItem,
  sembrarCuentas,
} from "@/lib/api";
import { mergeDepts, deptName, cargarDepartamentos, type CwlDept } from "@/lib/cwl-depts";
import { money2 } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
/** Llaves de mes como vienen del backend, en el mismo orden que MONTHS. */
const MESES_KEY = ["jan","feb","mar","apr","may","jun",
                   "jul","aug","sep","oct","nov","dec"] as const;
const MONTH_KEYS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];

const DRIVER_OPTIONS: { value: DriverType; key: string }[] = [
  { value: "REVENUE_LINE", key: "drvRevenueLine" },
  { value: "OCC_ROOMS",    key: "drvOccRooms" },
  { value: "GUESTS",       key: "drvGuests" },
  { value: "AVAIL_ROOMS",  key: "drvAvailRooms" },
  { value: "KILOS",        key: "drvKilos" },
];

const REV_LINE_OPTIONS: { value: RevenueLine; label: string }[] = [
  { value: "FOOD",           label: "Food Revenue" },
  { value: "BEVERAGE",       label: "Beverage Revenue" },
  { value: "ROOMS",          label: "Room Revenue" },
  { value: "ACTIVITIES",     label: "Activities Revenue" },
  { value: "TRANSPORT",      label: "Transport Revenue" },
  { value: "INNOCEANA",      label: "Innoceana Revenue" },
  { value: "RETAIL",         label: "Retail Revenue" },
  { value: "SPA",            label: "Spa Revenue" },
  { value: "SUSTAINABILITY", label: "Sustainability Revenue" },
];

function fmtUsd(v: string | number) {
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (!n || isNaN(n)) return <span style={{ color: "var(--text-disabled)" }}>—</span>;
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return <span>{n < 0 ? `(${s})` : s}</span>;
}

function fmtPct(v: string) {
  const n = parseFloat(v);
  if (isNaN(n)) return "—";
  return (n * 100).toFixed(1) + "%";
}

// Inline editable number cell
function NumCell({
  value, onSave, disabled = false,
}: {
  value: string; onSave: (v: number) => void; disabled?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(money2(value));

  function commit() {
    const n = parseFloat(draft);
    if (!isNaN(n)) onSave(n);
    setEditing(false);
  }

  if (disabled) return (
    <td className="mono" style={{ textAlign: "right", color: "var(--text-disabled)" }}>
      {fmtUsd(value)}
    </td>
  );

  return (
    <td
      className="mono"
      style={{ textAlign: "right", cursor: "text", padding: "2px 6px" }}
      onClick={() => { setDraft(money2(value)); setEditing(true); }}
    >
      {editing ? (
        <input
          autoFocus
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={e => { if (e.key === "Enter") commit(); if (e.key === "Escape") setEditing(false); }}
          className="fin-input"
          style={{ width: 90, textAlign: "right" }}
        />
      ) : (
        fmtUsd(value)
      )}
    </td>
  );
}

export default function CostsCheckbookPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("costs");
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios]         = useState<Scenario[]>([]);
  const [depts, setDepts]                 = useState<CwlDept[]>([]);
  const [selectedDept, setSelected]       = useState<string | null>(null);
  const [checkbook, setCheckbook]         = useState<CostDeptCheckbook | null>(null);
  const [summary, setSummary]             = useState<CostMonthlySummary[]>([]);
  const [loading, setLoading]             = useState(true);
  const [deptLoading, setDeptLoading]     = useState(false);
  const [saving, setSaving]               = useState<string | null>(null);  // entry id being saved
  const [recalcRunning, setRecalcRunning] = useState(false);
  const [error, setError]                 = useState<string | null>(null);
  const [xlsxMsg, setXlsxMsg]            = useState<string | null>(null);
  const [xlsxUp, setXlsxUp]             = useState(false);
  const [addModal, setAddModal]         = useState(false);
  const [catalog, setCatalog]           = useState<CostCatalogItem[]>([]);
  const fileRef                           = useRef<HTMLInputElement>(null);

  async function handleXlsxUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !scenarioId) return;
    setXlsxUp(true); setXlsxMsg(null);
    try {
      const r = await importCostsExcel(scenarioId, file);
      setXlsxMsg(t("xlsImported", { n: r.imported }));
      const dbDepts = await getCostDepts(scenarioId);
      await cargarDepartamentos();   // nombres del catálogo, no de una lista a mano
      const d = mergeDepts(dbDepts.map(x => x.dept_code), "COST");
      setDepts(d);
      if (selectedDept) loadDept(selectedDept);
    } catch (ex: unknown) {
      setXlsxMsg(`${tc("error")}: ${ex instanceof Error ? ex.message : String(ex)}`);
    } finally {
      setXlsxUp(false);
      if (fileRef.current) fileRef.current.value = "";
    }
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
        if (!sc) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarioId(sharedScenarioOr(sc.id));
        try { setCatalog(await getCostCatalog()); } catch { /* catálogo opcional */ }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : tc("error"));
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  // Recargar la lista de departamentos cuando cambia el escenario (sync con Master Data)
  useEffect(() => {
    if (!scenarioId) return;
    getCostDepts(scenarioId).then(async dbDepts => {
      await cargarDepartamentos();   // nombres del catálogo, no de una lista a mano
      const d = mergeDepts(dbDepts.map(x => x.dept_code), "COST");
      setDepts(d);
      setSelected(prev => (prev && d.some(x => x.dept_code === prev)) ? prev : (d[0]?.dept_code ?? null));
    }).catch(() => { /* sin depts para este escenario */ });
  }, [scenarioId]);

  const loadDept = useCallback(async (deptCode: string) => {
    if (!scenarioId) return;
    setDeptLoading(true);
    try {
      const [cb, sum] = await Promise.all([
        getCostDeptCheckbook(scenarioId, deptCode),
        getCostSummary(scenarioId, deptCode),
      ]);
      setCheckbook(cb);
      setSummary(sum);
    } finally {
      setDeptLoading(false);
    }
  }, [scenarioId]);

  const [sembrando, setSembrando] = useState(false);
  /** Abre en CERO las cuentas que el catálogo le da a este departamento.
   *  Sin esto no había forma de empezar a presupuestar uno desde la pantalla:
   *  el Club Madresal tenía planilla e ingreso y ninguna línea donde escribir. */
  async function sembrar() {
    if (!scenarioId || !selectedDept) return;
    setSembrando(true);
    try {
      const r = await sembrarCuentas(scenarioId, selectedDept, ["5"]);
      await loadDept(selectedDept);
      alert(r.creadas
        ? t("seedOpened", { n: r.creadas, dept: selectedDept })
        : t("seedNothing"));
    } catch (e) {
      alert(e instanceof Error ? e.message : tc("error"));
    } finally { setSembrando(false); }
  }

  useEffect(() => {
    if (selectedDept) loadDept(selectedDept);
  }, [selectedDept, loadDept]);

  async function saveEntryMonth(entry: CostEntry, monthKey: string, value: number) {
    if (!scenarioId) return;
    setSaving(entry.id);
    try {
      await updateCostEntry(scenarioId, entry.id, { [monthKey]: value });
      if (selectedDept) await loadDept(selectedDept);
    } finally {
      setSaving(null);
    }
  }

  async function saveEntryDriver(entry: CostEntry, patch: Record<string, unknown>) {
    if (!scenarioId) return;
    setSaving(entry.id);
    try {
      await updateCostEntry(scenarioId, entry.id, patch);
      if (selectedDept) await loadDept(selectedDept);
    } finally {
      setSaving(null);
    }
  }

  // Guarda el % de un mes (fracción) y recalcula para ver el monto.
  async function saveMonthlyRate(entry: CostEntry, monthKey: string, pct: number) {
    if (!scenarioId) return;
    setSaving(entry.id);
    try {
      await updateCostEntry(scenarioId, entry.id, { ["rate_" + monthKey]: String(pct / 100) });
      await recalculateCosts(scenarioId);
      if (selectedDept) await loadDept(selectedDept);
    } finally {
      setSaving(null);
    }
  }

  async function handleRecalculate() {
    if (!scenarioId) return;
    setRecalcRunning(true);
    try {
      await recalculateCosts(scenarioId);
      if (selectedDept) await loadDept(selectedDept);
    } finally {
      setRecalcRunning(false);
    }
  }

  async function handleAddCost(body: Record<string, unknown>) {
    if (!scenarioId) return;
    const dept = (body.dept_code as string) || selectedDept;
    if (!dept) return;
    await createCostEntry(scenarioId, dept, body);
    const dbDepts = await getCostDepts(scenarioId);
    setDepts(mergeDepts(dbDepts.map(x => x.dept_code), "COST"));
    setSelected(dept);
    await loadDept(dept);
    setAddModal(false);
  }

  async function handleDeleteCost(entry: CostEntry) {
    if (!scenarioId || !selectedDept) return;
    setSaving(entry.id);
    try {
      await deleteCostEntry(scenarioId, entry.id);
      await loadDept(selectedDept);
    } finally {
      setSaving(null);
    }
  }

  const revRef = checkbook?.revenue_reference ?? {};

  return (
    <div className="pag pag-ancha">
      <IrA esc={scenarioId} />
      <AvisoMoneda scenarioId={scenarioId} />
      <AvisoLineasObligatorias scenarioId={scenarioId} />
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>
            Cost of Sales
          </h2>
          <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)" }}>
            {t("subtitle")}
          </p>
        </div>

        {/* Scenario selector (sincronizado con Master Data del año) */}
        <select
          value={scenarioId ?? ""}
          onChange={e => setScenarioId(e.target.value)}
          title={t("scenarioSynced")}
          style={{
            marginLeft: 24, background: "var(--bg-input)", color: "var(--text-primary)",
            border: "1px solid var(--border-medium)", borderRadius: 4,
            padding: "5px 10px", fontSize: 13, cursor: "pointer",
          }}
        >
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>
          ))}
        </select>

        {/* Dept selector */}
        <select
          value={selectedDept ?? ""}
          onChange={e => setSelected(e.target.value)}
          style={{
            marginLeft: 24,
            background: "var(--bg-input)", color: "var(--text-primary)",
            border: "1px solid var(--border-medium)", borderRadius: 4,
            padding: "5px 10px", fontSize: 13, cursor: "pointer",
          }}
        >
          {depts.map(d => (
            <option key={d.dept_code} value={d.dept_code}>
              {d.dept_code} — {d.dept_name}
            </option>
          ))}
        </select>

        {/* Action buttons */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <RecalcButton scenarioId={scenarioId} />
          <button
            onClick={() => setAddModal(true)}
            disabled={!scenarioId}
            style={{
              padding: "5px 14px", fontSize: 12, borderRadius: 4, fontWeight: 600,
              background: "var(--bg-surface)", color: "var(--text-primary)",
              border: "1px solid var(--border-medium)", cursor: "pointer",
            }}
          >{t("addCostBtn")}</button>
          <button
            onClick={handleRecalculate}
            disabled={recalcRunning || !scenarioId}
            style={{
              padding: "5px 14px", fontSize: 12, borderRadius: 4,
              background: recalcRunning ? "var(--bg-elevated)" : "var(--brand)",
              color: recalcRunning ? "var(--text-secondary)" : "#fff",
              border: "none", cursor: recalcRunning ? "default" : "pointer",
            }}
          >{recalcRunning ? tc("recalc.running") : t("recalcBtn")}</button>
          {scenarioId && (
            <a href={costsExcelUrl(scenarioId)} download style={{
              padding: "5px 14px", fontSize: 12, borderRadius: 4, textDecoration: "none",
              background: "var(--bg-elevated)", color: "var(--text-secondary)",
              border: "1px solid var(--border-medium)", lineHeight: "20px", display: "inline-block",
            }}>⬇ Excel</a>
          )}
          {/* Abre las cuentas de costo que el catálogo le da a este
              departamento, en cero. Ver el comentario de `sembrar`. */}
          <button
            onClick={sembrar}
            disabled={sembrando || !scenarioId || !selectedDept}
            title={t("seedHint")}
            style={{
              padding: "5px 14px", fontSize: 12, borderRadius: 4,
              background: "var(--bg-elevated)",
              color: sembrando ? "var(--text-disabled)" : "var(--text-secondary)",
              border: "1px solid var(--border-subtle)",
              cursor: sembrando || !selectedDept ? "default" : "pointer",
            }}
          >{sembrando ? t("seedRunning") : t("seedBtn")}</button>
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
          >{xlsxUp ? t("uploading") : t("uploadExcel")}</button>
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

      {addModal && (
        <AddCostModal
          catalog={catalog}
          defaultDept={selectedDept ?? (depts[0]?.dept_code ?? "")}
          onClose={() => setAddModal(false)}
          onAdd={handleAddCost}
        />
      )}

      {loading && <p style={{ color: "var(--text-secondary)" }}>{tc("loading")}</p>}
      {error && (
        <div style={{ color: "var(--negative)", background: "var(--bg-surface)", padding: "12px 16px", borderRadius: 4 }}>
          ⚠ {error}
        </div>
      )}
      {!loading && !error && deptLoading && (
        <p style={{ color: "var(--text-secondary)", fontSize: 12 }}>{t("loadingDept")}</p>
      )}

      {!loading && !error && !deptLoading && checkbook && (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1400, fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", width: 60 }}>{t("colAccount")}</th>
                <th style={{ textAlign: "left", width: 160 }}>{t("description")}</th>
                <th style={{ textAlign: "center", width: 80 }}>{t("colMode")}</th>
                <th style={{ textAlign: "center", width: 100 }}>Driver</th>
                <th style={{ textAlign: "center", width: 80 }}>{t("colRate")}</th>
                <th style={{ textAlign: "left", width: 120 }}>{t("colRevRef")}</th>
                {MONTHS.map(m => (
                  <th key={m} style={{ textAlign: "right", minWidth: 80 }}>{m}</th>
                ))}
                <th style={{ textAlign: "right", color: "var(--brand)" }}>{tc("annual")}</th>
              </tr>
            </thead>
            <tbody>
              {/* Reference revenue rows */}
              <tr style={{ background: "var(--bg-elevated)" }}>
                <td colSpan={6} style={{ color: "var(--text-secondary)", fontStyle: "italic", fontSize: 11 }}>
                  {t("referenceRow")}
                </td>
                {MONTHS.map((_, i) => (
                  <td key={i} className="mono" style={{ textAlign: "right", color: "var(--text-secondary)", fontSize: 11 }}>
                    {fmtUsd(revRef[i + 1]?.total ?? "0")}
                  </td>
                ))}
                <td className="mono" style={{ textAlign: "right", color: "var(--text-secondary)", fontSize: 11 }}>
                  {fmtUsd(String(Object.values(revRef).reduce((s, r) => s + parseFloat(r.total || "0"), 0)))}
                </td>
              </tr>

              {/* Cost entry rows */}
              {checkbook.entries.length === 0 ? (
                <tr>
                  <td colSpan={6 + 13} style={{ color: "var(--text-secondary)", padding: "16px 12px", textAlign: "center" }}>
                    {t.rich("noCostLines", { b: (c: React.ReactNode) => <b>{c}</b>, boton: t("addCostBtn") })}
                  </td>
                </tr>
              ) : (
                checkbook.entries.map(entry => {
                  const isDriver = entry.calc_mode === "DRIVER";
                  const isSaving = saving === entry.id;

                  return (
                    <tr key={entry.id} style={{ opacity: isSaving ? 0.6 : 1 }}>
                      <td style={{ color: "var(--text-secondary)", fontSize: 11 }}>
                        <button title={t("deleteLine")} onClick={() => handleDeleteCost(entry)}
                          disabled={isSaving}
                          style={{ marginRight: 6, padding: "0 5px", fontSize: 11, cursor: "pointer",
                            background: "transparent", color: "var(--negative)",
                            border: "1px solid var(--border-medium)", borderRadius: 3 }}>✕</button>
                        {entry.account_code}
                      </td>
                      <td style={{ color: "var(--text-primary)" }}>
                        {entry.account_name}
                        {(entry.currency ?? "USD") === "CRC" && (
                          <span
                            title={t("colonesHint")}
                            style={{
                              marginLeft: 6, padding: "1px 5px", borderRadius: 3,
                              fontSize: 9.5, fontWeight: 700, letterSpacing: 0.3,
                              background: "var(--bg-elevated)", color: "var(--accent-gold, #856404)",
                              border: "1px solid var(--border-medium)",
                            }}>₡ CRC</span>
                        )}
                      </td>

                      {/* Mode selector */}
                      <td style={{ textAlign: "center" }}>
                        <select
                          value={entry.calc_mode}
                          onChange={e => saveEntryDriver(entry, { calc_mode: e.target.value as CalcMode })}
                          style={{
                            background: "var(--bg-input)", color: isDriver ? "var(--brand)" : "var(--text-secondary)",
                            border: "1px solid var(--border-subtle)", borderRadius: 3,
                            fontSize: 11, padding: "2px 4px", cursor: "pointer",
                          }}
                        >
                          <option value="MANUAL">MANUAL</option>
                          <option value="DRIVER">DRIVER</option>
                        </select>
                      </td>

                      {/* Driver type (only when DRIVER) */}
                      <td style={{ textAlign: "center" }}>
                        {isDriver ? (
                          <select
                            value={entry.driver_type}
                            onChange={e => saveEntryDriver(entry, { driver_type: e.target.value as DriverType })}
                            style={{
                              background: "var(--bg-input)", color: "var(--text-primary)",
                              border: "1px solid var(--border-subtle)", borderRadius: 3,
                              fontSize: 11, padding: "2px 4px", cursor: "pointer",
                            }}
                          >
                            <option value="">—</option>
                            {DRIVER_OPTIONS.map(o => (
                              <option key={o.value} value={o.value}>{t(o.key)}</option>
                            ))}
                          </select>
                        ) : (
                          <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>—</span>
                        )}
                      </td>

                      {/* Rate / pct editable */}
                      <td style={{ textAlign: "center" }}>
                        {isDriver ? (
                          <RateCell
                            value={entry.driver_pct_or_rate}
                            driverType={entry.driver_type}
                            onSave={v => saveEntryDriver(entry, { driver_pct_or_rate: String(v) })}
                          />
                        ) : (
                          <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>—</span>
                        )}
                      </td>

                      {/* Revenue line ref (only for REVENUE_LINE driver) */}
                      <td>
                        {isDriver && entry.driver_type === "REVENUE_LINE" ? (
                          <select
                            value={entry.revenue_line_ref}
                            onChange={e => saveEntryDriver(entry, { revenue_line_ref: e.target.value as RevenueLine })}
                            style={{
                              background: "var(--bg-input)", color: "var(--text-primary)",
                              border: "1px solid var(--border-subtle)", borderRadius: 3,
                              fontSize: 11, padding: "2px 4px", cursor: "pointer", maxWidth: 120,
                            }}
                          >
                            <option value="">—</option>
                            {REV_LINE_OPTIONS.map(o => (
                              <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                          </select>
                        ) : (
                          <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>—</span>
                        )}
                      </td>

                      {/* Monthly cells: % editable per month for REVENUE_LINE driver,
                          else editable amount (MANUAL) or read-only (other drivers) */}
                      {MONTH_KEYS.map((mk) => (
                        isDriver && entry.driver_type === "REVENUE_LINE" ? (
                          <MonthPctCell
                            key={mk}
                            pct={entry.rates?.[mk] != null
                              ? parseFloat(entry.rates![mk] as string)
                              : parseFloat(entry.driver_pct_or_rate || "0")}
                            amount={entry.months[mk] ?? "0"}
                            onSave={v => saveMonthlyRate(entry, mk, v)}
                          />
                        ) : (
                          <NumCell
                            key={mk}
                            value={entry.months[mk] ?? "0"}
                            disabled={isDriver}
                            onSave={v => saveEntryMonth(entry, mk, v)}
                          />
                        )
                      ))}

                      {/* Annual total */}
                      <td className="mono" style={{ textAlign: "right", fontWeight: 600, color: "var(--positive)" }}>
                        {fmtUsd(entry.annual_total)}
                      </td>
                    </tr>
                  );
                })
              )}

              {/* Lo que le cayo por reparto: no se edita, pero el P&L lo suma.
                  Sin esto la pantalla enseñaba un numero y el P&L otro. */}
              {(checkbook.allocated?.length ?? 0) > 0 && (
                <>
                  <tr>
                    <td colSpan={19} style={{
                      paddingTop: 14, fontSize: 11, fontWeight: 700,
                      color: "var(--text-secondary)", letterSpacing: "0.04em",
                    }}>
                      {t("allocatedHeader")}
                    </td>
                  </tr>
                  {checkbook.allocated!.map(r => (
                    <tr key={`${r.account_code}-${r.target_dept}-${r.source_dept}`}
                        style={{ background: "rgba(41,98,255,0.05)" }}>
                      <td colSpan={6} style={{ color: "var(--text-secondary)" }}>
                        <b style={{ color: "var(--brand)" }}>{r.account_code}</b>{" "}
                        {r.account_name || "—"}
                        <span style={{ color: "var(--text-disabled)", fontSize: 10 }}>
                          {r.target_dept && r.target_dept !== selectedDept
                            ? ` · ${t("allocTo", { dept: `${r.target_dept} ${deptName(r.target_dept)}` })}`
                            : ""}
                          {" "}· {t("allocFrom", { dept: r.source_dept })}
                          {r.basis_type ? ` · ${t("allocBy", { base: r.basis_type.toLowerCase() })}` : ""}
                        </span>
                      </td>
                      {MESES_KEY.map(mk => (
                        <td key={mk} className="mono" style={{ textAlign: "right", color: "var(--text-secondary)" }}>
                          {fmtUsd(r[mk])}
                        </td>
                      ))}
                      <td className="mono" style={{ textAlign: "right", fontWeight: 600, color: "var(--brand)" }}>
                        {fmtUsd(r.total)}
                      </td>
                    </tr>
                  ))}
                </>
              )}

              {/* Separator */}
              {checkbook.entries.length > 0 && (
                <>
                  {/* Total CoS row */}
                  <tr className="total">
                    <td colSpan={6} style={{ fontWeight: 700, color: "var(--text-primary)" }}>
                      {(checkbook.allocated?.length ?? 0) > 0
                        ? t("totalCosCheckbookOnly")
                        : "TOTAL COST OF SALES"}
                    </td>
                    {summary.map(m => (
                      <td key={m.month} className="mono" style={{ textAlign: "right", fontWeight: 700 }}>
                        {fmtUsd(m.total_cos)}
                      </td>
                    ))}
                    <td className="mono" style={{ textAlign: "right", fontWeight: 700 }}>
                      {fmtUsd(String(summary.reduce((s, m) => s + parseFloat(m.total_cos || "0"), 0)))}
                    </td>
                  </tr>

                  {/* El numero que de verdad llega al P&L: checkbook + reparto.
                      Es el que hay que comparar contra el estado de resultados. */}
                  {(checkbook.allocated?.length ?? 0) > 0 && (
                    <tr className="total" style={{ background: "rgba(41,98,255,0.10)" }}>
                      <td colSpan={6} style={{ fontWeight: 700, color: "var(--brand)" }}>
                        {t("totalIntoPl")}
                      </td>
                      {summary.map((m, i) => (
                        <td key={m.month} className="mono"
                            style={{ textAlign: "right", fontWeight: 700, color: "var(--brand)" }}>
                          {fmtUsd(String(
                            parseFloat(m.total_cos || "0")
                            + checkbook.allocated!.reduce((s, r) => s + parseFloat(r[MESES_KEY[i]] || "0"), 0)
                          ))}
                        </td>
                      ))}
                      <td className="mono" style={{ textAlign: "right", fontWeight: 800, color: "var(--brand)" }}>
                        {fmtUsd(String(
                          summary.reduce((s, m) => s + parseFloat(m.total_cos || "0"), 0)
                          + checkbook.allocated!.reduce((s, r) => s + parseFloat(r.total || "0"), 0)
                        ))}
                      </td>
                    </tr>
                  )}

                  {/* Gross Profit row */}
                  <tr style={{ background: "rgba(38,166,154,0.06)" }}>
                    <td colSpan={6} style={{ fontWeight: 600, color: "var(--positive)" }}>
                      GROSS PROFIT
                      {(checkbook.allocated?.length ?? 0) > 0 && (
                        <span style={{ color: "var(--text-disabled)", fontSize: 10, fontWeight: 400 }}>
                          {" "}· {t("withoutAllocation")}
                        </span>
                      )}
                    </td>
                    {summary.map(m => {
                      const gp = parseFloat(m.gross_profit);
                      return (
                        <td key={m.month} className="mono" style={{
                          textAlign: "right", fontWeight: 600,
                          color: gp >= 0 ? "var(--positive)" : "var(--negative)",
                        }}>
                          {fmtUsd(m.gross_profit)}
                        </td>
                      );
                    })}
                    <td className="mono" style={{
                      textAlign: "right", fontWeight: 700,
                      color: summary.reduce((s, m) => s + parseFloat(m.gross_profit || "0"), 0) >= 0
                        ? "var(--positive)" : "var(--negative)",
                    }}>
                      {fmtUsd(String(summary.reduce((s, m) => s + parseFloat(m.gross_profit || "0"), 0)))}
                    </td>
                  </tr>

                  {/* Margin % row */}
                  <tr>
                    <td colSpan={6} style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                      {t("grossMarginPct")}
                    </td>
                    {summary.map(m => (
                      <td key={m.month} className="mono" style={{ textAlign: "right", fontSize: 11, color: "var(--text-secondary)" }}>
                        {fmtPct(m.margin_pct)}
                      </td>
                    ))}
                    <td className="mono" style={{ textAlign: "right", fontSize: 11, color: "var(--text-secondary)" }}>
                      {(() => {
                        const totalRev = summary.reduce((s, m) => s + parseFloat(m.relevant_revenue || "0"), 0);
                        const totalGP  = summary.reduce((s, m) => s + parseFloat(m.gross_profit || "0"), 0);
                        return totalRev ? ((totalGP / totalRev) * 100).toFixed(1) + "%" : "—";
                      })()}
                    </td>
                  </tr>
                </>
              )}
            </tbody>
          </table>
        </div>
      )}

      {!loading && !error && !deptLoading && !checkbook && (
        <div style={{ color: "var(--text-secondary)", marginTop: 16 }}>
          {t("pickDept")}
        </div>
      )}
    </div>
  );
}

// ── Rate cell: shows % when REVENUE_LINE, $ otherwise ────────────────────────

function RateCell({
  value, driverType, onSave,
}: {
  value: string; driverType: string; onSave: (v: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const isRevLine = driverType === "REVENUE_LINE";
  const display = isRevLine
    ? (parseFloat(value) * 100).toFixed(1) + "%"
    : "$" + parseFloat(value).toLocaleString("en-US", { minimumFractionDigits: 2 });

  function commit(raw: string) {
    let n = parseFloat(raw);
    if (isNaN(n)) return;
    if (isRevLine && n > 1) n = n / 100;  // accept "28" as "0.28"
    onSave(n);
    setEditing(false);
  }

  const [draft, setDraft] = useState(
    isRevLine ? (parseFloat(value) * 100).toFixed(1) : money2(value),
  );

  return (
    <span
      style={{ cursor: "pointer", color: "var(--brand)", fontSize: 11 }}
      onClick={() => { setDraft(isRevLine ? (parseFloat(value) * 100).toFixed(1) : money2(value)); setEditing(true); }}
    >
      {editing ? (
        <input
          autoFocus
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={() => commit(draft)}
          onKeyDown={e => { if (e.key === "Enter") commit(draft); if (e.key === "Escape") setEditing(false); }}
          className="fin-input"
          style={{ width: 70, textAlign: "right" }}
        />
      ) : (
        display
      )}
    </span>
  );
}

// ── Celda de mes: % editable arriba, monto calculado abajo ──────────────────────
function MonthPctCell({
  pct, amount, onSave,
}: {
  pct: number; amount: string; onSave: (pctValue: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState((pct * 100).toFixed(1));
  function commit() {
    const n = parseFloat(draft);
    if (!isNaN(n)) onSave(n);
    setEditing(false);
  }
  const amt = parseFloat(amount || "0");
  return (
    <td style={{ textAlign: "right", padding: "2px 6px", minWidth: 64 }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 1 }}>
        {editing ? (
          <input
            autoFocus value={draft}
            onChange={e => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={e => { if (e.key === "Enter") commit(); if (e.key === "Escape") setEditing(false); }}
            className="fin-input" style={{ width: 52, textAlign: "right", fontSize: 11 }}
          />
        ) : (
          <span onClick={() => { setDraft((pct * 100).toFixed(1)); setEditing(true); }}
            className="mono" style={{ cursor: "pointer", color: "var(--brand)", fontSize: 11 }}>
            {(pct * 100).toFixed(1)}%
          </span>
        )}
        <span className="mono" style={{ fontSize: 10, color: "var(--text-secondary)" }}>
          {amt ? (amt < 0 ? "(" : "") + "$" + Math.abs(amt).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (amt < 0 ? ")" : "") : "—"}
        </span>
      </div>
    </td>
  );
}

// Cada departamento → su línea de ingreso (el costo suele ser % de ese ingreso).
// F&B arranca en FOOD; para Beverage se agrega una segunda línea de costo.
const DEPT_REV_LINE: Record<string, RevenueLine> = {
  "0110": "ROOMS", "0120": "FOOD", "0130": "SPA", "0150": "ACTIVITIES",
  "0152": "TRANSPORT", "0155": "INNOCEANA", "0165": "RETAIL",
};

// ── Add cost line modal ─────────────────────────────────────────────────────────
function AddCostModal({
  catalog, defaultDept, onClose, onAdd,
}: {
  catalog: CostCatalogItem[];
  defaultDept: string;
  onClose: () => void;
  onAdd: (body: Record<string, unknown>) => Promise<void>;
}) {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("costs");
  const MONTH_K = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];

  // Departamentos que TIENEN cuentas de costo (del catálogo); cuentas esclavas.
  const catDepts = Array.from(new Set(catalog.map(c => c.dept_code)));
  const deptLabel = (dc: string) =>
    catalog.find(c => c.dept_code === dc)?.line_name || deptName(dc) || dc;
  const initialDept = catDepts.includes(defaultDept) ? defaultDept : (catDepts[0] ?? defaultDept);

  const [dept, setDept] = useState(initialDept);
  const acctsFor = (dc: string) => catalog.filter(c => c.dept_code === dc);
  const [account, setAccount] = useState(acctsFor(initialDept)[0]?.account_code ?? "");
  const [name, setName] = useState(acctsFor(initialDept)[0]?.name ?? "");
  // PCT = % del ingreso · FIXED = mismo monto los 12 meses · MENSUAL = uno por mes
  const [kind, setKind] = useState<"PCT" | "FIXED" | "MENSUAL" | "FTE">("PCT");
  const [revLine, setRevLine] = useState<RevenueLine>(DEPT_REV_LINE[initialDept] ?? "FOOD");
  const [rate, setRate] = useState(30);
  const [monthlyAmt, setMonthlyAmt] = useState(0);
  const [porMes, setPorMes] = useState<number[]>(Array(12).fill(0));
  const [porFte, setPorFte] = useState(0);
  // Moneda de la linea. En colones el dato maestro son los colones y el dolar
  // de cada mes lo deriva el sistema con el TC de ese mes.
  const [moneda, setMoneda] = useState<"USD" | "CRC">("USD");
  const [saving, setSaving] = useState(false);

  // Al cambiar de departamento: ajusta cuenta (1ra del catálogo), nombre e ingreso-driver.
  function changeDept(dc: string) {
    setDept(dc);
    const first = acctsFor(dc)[0];
    setAccount(first?.account_code ?? "");
    setName(first?.name ?? "");
    setRevLine(DEPT_REV_LINE[dc] ?? "FOOD");
  }

  // Al elegir la cuenta, autocompleta la descripción (editable).
  function changeAccount(ac: string) {
    setAccount(ac);
    const hit = acctsFor(dept).find(c => c.account_code === ac);
    if (hit) setName(hit.name);
  }

  const inp: React.CSSProperties = {
    background: "var(--bg-input)", color: "var(--text-primary)",
    border: "1px solid var(--border-medium)", borderRadius: 4,
    padding: "6px 10px", fontSize: 13, width: "100%",
  };
  const lbl: React.CSSProperties = { fontSize: 11, color: "var(--text-secondary)", marginBottom: 4, display: "block" };
  const canSave = dept && account.trim() && name.trim();

  async function save() {
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        dept_code: dept, account_code: account.trim(), account_name: name.trim(),
      };
      if (kind === "PCT") {
        body.calc_mode = "DRIVER";
        body.driver_type = "REVENUE_LINE";
        body.revenue_line_ref = revLine;
        body.driver_pct_or_rate = String(rate / 100);  // 30 → 0.30
      } else if (kind === "FTE") {
        // Monto por persona: el motor lo multiplica por el FTE de cada mes.
        body.calc_mode = "DRIVER";
        body.driver_type = "FTE";
        body.driver_pct_or_rate = String(porFte);
      } else if (kind === "FIXED") {
        // Monto fijo: mismo monto en los 12 meses
        body.calc_mode = "MANUAL";
        const col = (m: string) => moneda === "CRC" ? `crc_${m}` : m;
        for (const m of MONTH_K) body[col(m)] = String(monthlyAmt);
      } else {
        // Uno por mes: es el caso de la cafeteria, que no es parejo en el ano.
        body.calc_mode = "MANUAL";
        const col = (m: string) => moneda === "CRC" ? `crc_${m}` : m;
        MONTH_K.forEach((m, i) => { body[col(m)] = String(porMes[i] || 0); });
      }
      body.currency = moneda;
      await onAdd(body);
    } finally { setSaving(false); }
  }

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 50,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: "var(--bg-surface)", border: "1px solid var(--border-medium)",
        borderRadius: 8, padding: 20, width: 460, maxWidth: "90vw",
      }}>
        <h3 style={{ margin: "0 0 4px", fontSize: 16, color: "var(--text-primary)" }}>{t("addCost")}</h3>
        <p style={{ margin: "0 0 16px", fontSize: 12, color: "var(--text-secondary)" }}>
          {t("addCostHelp")}
          {dept === "0120" && " " + t("addCostHelpFb")}
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <label style={lbl}>{tc("department")}</label>
            <select value={dept} onChange={e => changeDept(e.target.value)} style={inp}>
              {catDepts.map(dc => <option key={dc} value={dc}>{dc} — {deptLabel(dc)}</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>{t("accountField")}</label>
            <select value={account} onChange={e => changeAccount(e.target.value)} style={inp}>
              {acctsFor(dept).map(c => (
                <option key={c.account_code} value={c.account_code}>{c.account_code} — {c.name}</option>
              ))}
            </select>
          </div>
          <div style={{ gridColumn: "1 / 3" }}>
            <label style={lbl}>{t("descriptionSuggested")}</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder={t("descriptionPlaceholder")} style={inp} />
          </div>
          <div style={{ gridColumn: "1 / 3" }}>
            <label style={lbl}>{t("lineCurrency")}</label>
            <div style={{ display: "flex", gap: 0 }}>
              {([["USD", t("currencyUsd")], ["CRC", t("currencyCrc")]] as [typeof moneda, string][])
                .map(([k, label], i) => (
                <button key={k} type="button" onClick={() => setMoneda(k)} style={{
                  flex: 1, padding: "6px 10px", fontSize: 12, cursor: "pointer", fontWeight: 600,
                  background: moneda === k ? "var(--brand)" : "var(--bg-input)",
                  color: moneda === k ? "#fff" : "var(--text-secondary)",
                  border: "1px solid var(--border-medium)",
                  borderRadius: i === 0 ? "4px 0 0 4px" : "0 4px 4px 0",
                }}>{label}</button>
              ))}
            </div>
            {moneda === "CRC" && (
              <p style={{ margin: "6px 0 0", fontSize: 11, color: "var(--text-secondary)",
                lineHeight: 1.6 }}>
                {t.rich("crcHelp", { b: (c: React.ReactNode) => <b>{c}</b> })}
              </p>
            )}
          </div>
          <div style={{ gridColumn: "1 / 3" }}>
            <label style={lbl}>{t("costType")}</label>
            <div style={{ display: "flex", gap: 0 }}>
              {([["PCT",t("kindPct")],["FTE",t("kindFte")],["FIXED",t("kindFixed")],["MENSUAL",t("kindMonthly")]] as [typeof kind,string][]).map(([k,label],i,arr) => (
                <button key={k} type="button" onClick={() => setKind(k)} style={{
                  flex: 1, padding: "6px 10px", fontSize: 12, cursor: "pointer", fontWeight: 600,
                  background: kind === k ? "var(--brand)" : "var(--bg-input)",
                  color: kind === k ? "#fff" : "var(--text-secondary)",
                  border: "1px solid var(--border-medium)",
                  borderRadius: i === 0 ? "4px 0 0 4px"
                    : i === arr.length - 1 ? "0 4px 4px 0" : "0",
                }}>{label}</button>
              ))}
            </div>
          </div>
          {kind === "PCT" && (
            <>
              <div>
                <label style={lbl}>{t("revenueLine")}</label>
                <select value={revLine} onChange={e => setRevLine(e.target.value as RevenueLine)} style={inp}>
                  {["FOOD","BEVERAGE","ROOMS","ACTIVITIES","TRANSPORT","INNOCEANA","RETAIL","SPA","SUSTAINABILITY"]
                    .map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div>
                <label style={lbl}>{t("percentField")}</label>
                <input type="number" value={rate} onChange={e => setRate(Number(e.target.value))} style={inp} />
              </div>
            </>
          )}
          {kind === "FTE" && (
            <div style={{ gridColumn: "1 / 3" }}>
              <label style={lbl}>{t("perPersonMonth")}</label>
              <input type="number" value={porFte}
                     onChange={e => setPorFte(Number(e.target.value))}
                     onFocus={e => e.target.select()}
                     placeholder={t("perPersonPlaceholder")}
                     style={inp} />
              <p style={{ margin: "6px 0 0", fontSize: 11, color: "var(--text-secondary)",
                lineHeight: 1.6 }}>
                {t.rich("fteHelp", { b: (c: React.ReactNode) => <b>{c}</b> })}
                {dept === "0220" && (
                  <> {t.rich("fteHelpCafeteria", { b: (c: React.ReactNode) => <b>{c}</b> })}</>
                )}
              </p>
            </div>
          )}
          {kind === "FIXED" && (
            <div style={{ gridColumn: "1 / 3" }}>
              <label style={lbl}>{t("fixedAmountField", { moneda: moneda === "CRC" ? "₡" : "USD" })}</label>
              <input type="number" value={monthlyAmt} onChange={e => setMonthlyAmt(Number(e.target.value))}
                     placeholder={t("fixedAmountPlaceholder")} style={inp} />
            </div>
          )}
          {kind === "MENSUAL" && (
            <div style={{ gridColumn: "1 / 3" }}>
              <label style={lbl}>{t("monthlyAmountField", { moneda: moneda === "CRC" ? t("currencyCrc") : "USD" })}</label>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 6 }}>
                {MONTHS
                  .map((m, i) => (
                  <label key={m} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontSize: 10, color: "var(--text-disabled)" }}>{m}</span>
                    <input type="number" value={porMes[i]}
                      onFocus={e => e.target.select()}
                      onChange={e => setPorMes(p => {
                        const c = [...p]; c[i] = Number(e.target.value) || 0; return c;
                      })}
                      style={{ ...inp, padding: "4px 6px", fontSize: 12, textAlign: "right" }} />
                  </label>
                ))}
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 8 }}>
                <button type="button" onClick={() => setPorMes(Array(12).fill(porMes[0] || 0))}
                  title={t("copyJanHint", { mes: MONTHS[0] })}
                  style={{
                    padding: "4px 10px", fontSize: 11.5, borderRadius: 4, cursor: "pointer",
                    background: "var(--bg-input)", color: "var(--text-primary)",
                    border: "1px solid var(--border-medium)", fontWeight: 600,
                  }}>{t("copyJanBtn", { mes: MONTHS[0] })}</button>
                <span style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>
                  {tc("year")}: <b style={{ color: "var(--brand)" }}>
                    ${porMes.reduce((a, b) => a + b, 0).toLocaleString("en-US")}
                  </b>
                </span>
                <span style={{ fontSize: 11, color: "var(--text-disabled)" }}>
                  {t("octoberClosed")}
                </span>
              </div>
            </div>
          )}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
          <button onClick={onClose} disabled={saving} style={{
            padding: "7px 14px", fontSize: 13, borderRadius: 5, cursor: "pointer",
            background: "var(--bg-surface)", color: "var(--text-secondary)",
            border: "1px solid var(--border-medium)" }}>{tc("cancel")}</button>
          <button onClick={save} disabled={!canSave || saving} style={{
            padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600,
            cursor: canSave && !saving ? "pointer" : "not-allowed",
            background: canSave && !saving ? "var(--brand)" : "var(--bg-surface)",
            color: canSave && !saving ? "#fff" : "var(--text-disabled)", border: "none" }}>
            {saving ? t("adding") : t("add")}
          </button>
        </div>
      </div>
    </div>
  );
}
