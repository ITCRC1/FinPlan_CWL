"use client";
import { usePlanningScenario, usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import AvisoMoneda from "@/components/AvisoMoneda";
import AvisoLineasObligatorias from "@/components/AvisoLineasObligatorias";
import RecalcButton from "@/components/RecalcButton";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  getScenarios, getOpexDepts, getOpexDeptCheckbook, updateOpexEntry, importAllOpex,
  getTipoCambio,
  opexExcelUrl, importOpexExcel, addOpexLines,
  type Scenario, type OpexAccount, type OpexEntry, type OpexDeptCheckbook,
  sembrarCuentas,
} from "@/lib/api";
import { mergeDepts, deptName, cargarDepartamentos, type CwlDept } from "@/lib/cwl-depts";
import { money2 } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
/** Llaves de mes del backend, en el mismo orden que MONTHS. `as const` para
 *  que sirvan de indice con tipo en las filas repartidas. */
const MONTH_KEYS = ["jan","feb","mar","apr","may","jun",
                    "jul","aug","sep","oct","nov","dec"] as const;


function fmtUsd(v: string | number | undefined) {
  const n = typeof v === "string" ? parseFloat(v) : (v ?? 0);
  if (!n || isNaN(n)) return <span style={{ color: "var(--text-disabled)" }}>—</span>;
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return <>{n < 0 ? `(${s})` : s}</>;
}

function fmtUsdNum(v: string): number {
  return parseFloat(v) || 0;
}

// Inline editable cell
/** El monto en dolares como texto, para el tooltip de una linea en colones. */
function fmtUsdTxt(v: string | number) {
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (!n || isNaN(n)) return "$0";
  return "$" + n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function NumCell({ value, onSave }: { value: string; onSave: (v: number) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(money2(value));

  function commit() {
    const n = parseFloat(draft);
    if (!isNaN(n)) onSave(n);
    setEditing(false);
  }

  return (
    <td
      className="mono"
      style={{ textAlign: "right", cursor: "text", padding: "2px 6px", minWidth: 78 }}
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
          style={{ width: 80, textAlign: "right" }}
        />
      ) : fmtUsd(value)}
    </td>
  );
}

// Collapsible account group
function AccountGroup({
  acct,
  expanded,
  onToggle,
  onSaveEntry,
  onToggleMoneda,
  onAddLines,
  saving,
  addingLines,
}: {
  acct: OpexAccount;
  expanded: boolean;
  onToggle: () => void;
  onSaveEntry: (entry: OpexEntry, monthKey: string, value: number) => void;
  onToggleMoneda: (entry: OpexEntry) => void;
  onAddLines: (acct: OpexAccount) => void;
  saving: string | null;
  addingLines: string | null;   // account_code currently being extended
}) {
  const t = useTranslations("opexCheckbook");
  const isAdding = addingLines === acct.account_code;

  return (
    <>
      {/* Account header row */}
      <tr
        style={{
          background: "var(--bg-elevated)",
          borderTop: "1px solid var(--border-medium)",
        }}
      >
        <td colSpan={2} style={{
          color: "var(--text-primary)", fontWeight: 600, fontSize: 12,
          paddingLeft: 8, cursor: "pointer",
        }}
          onClick={onToggle}
        >
          <span style={{ marginRight: 6, color: "var(--text-secondary)", fontSize: 10 }}>
            {expanded ? "▾" : "▸"}
          </span>
          {acct.account_code} — {acct.account_name}
          <span style={{ marginLeft: 8, fontSize: 10, color: "var(--text-secondary)" }}>
            ({acct.lines.length} líneas)
          </span>
          <button
            onClick={e => { e.stopPropagation(); onAddLines(acct); }}
            disabled={isAdding}
            style={{
              marginLeft: 12, padding: "1px 8px", fontSize: 10, borderRadius: 3,
              background: isAdding ? "var(--bg-elevated)" : "var(--bg-input)",
              color: isAdding ? "var(--text-disabled)" : "var(--text-secondary)",
              border: "1px solid var(--border-subtle)", cursor: isAdding ? "default" : "pointer",
              verticalAlign: "middle",
            }}
          >
            {isAdding ? "…" : t("add10Lines")}
          </button>
        </td>
        {MONTH_KEYS.map(mk => (
          <td key={mk} className="mono" style={{
            textAlign: "right", fontSize: 12, fontWeight: 600,
            color: "var(--brand)", padding: "4px 6px",
          }}>
            {fmtUsd(acct.monthly_totals[mk])}
          </td>
        ))}
        <td className="mono" style={{
          textAlign: "right", fontWeight: 700, color: "var(--brand)", padding: "4px 8px",
        }}>
          {fmtUsd(acct.annual_total)}
        </td>
      </tr>

      {/* Detail lines */}
      {expanded && acct.lines.map(line => (
        <tr key={line.id} style={{ opacity: saving === line.id ? 0.6 : 1 }}>
          <td style={{
            color: "var(--text-secondary)", fontSize: 10,
            paddingLeft: 24, minWidth: 50,
          }}>
            {line.detail_code}
          </td>
          <td style={{ color: "var(--text-secondary)", fontSize: 11, maxWidth: 220 }}>
            {line.detail_desc || "—"}
            <button
              onClick={() => onToggleMoneda(line)}
              title={(line.currency ?? "USD") === "CRC"
                ? t("lineCrcHint")
                : t("lineUsdHint")}
              style={{
                marginLeft: 6, padding: "1px 5px", borderRadius: 3, cursor: "pointer",
                fontSize: 9.5, fontWeight: 700, letterSpacing: 0.3,
                background: (line.currency ?? "USD") === "CRC"
                  ? "var(--bg-elevated)" : "transparent",
                color: (line.currency ?? "USD") === "CRC"
                  ? "var(--accent-gold, #856404)" : "var(--text-disabled)",
                border: "1px solid var(--border-medium)",
              }}>
              {(line.currency ?? "USD") === "CRC" ? "₡ CRC" : "$ USD"}
            </button>
          </td>
          {MONTH_KEYS.map(mk => (
            (line.currency ?? "USD") === "CRC" ? (
              <NumCell
                key={mk}
                value={line.crc_months?.[mk] ?? "0"}
                onSave={v => onSaveEntry(line, `crc_${mk}`, v)}
              />
            ) : (
              <NumCell
                key={mk}
                value={line.months[mk] ?? "0"}
                onSave={v => onSaveEntry(line, mk, v)}
              />
            )
          ))}
          <td className="mono" style={{
            textAlign: "right", fontSize: 11,
            color: parseFloat(line.annual_total) > 0 ? "var(--text-primary)" : "var(--text-disabled)",
          }}>
            {(line.currency ?? "USD") === "CRC" ? (
              <span title={`Equivale a ${fmtUsdTxt(line.annual_total)} con el tipo de cambio de cada mes`}>
                ₡{Number(line.crc_annual ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}
              </span>
            ) : fmtUsd(line.annual_total)}
          </td>
        </tr>
      ))}
    </>
  );
}

export default function OpexCheckbookPage() {
  const tc = useTranslations("common");
  const t = useTranslations("opexCheckbook");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios]         = useState<Scenario[]>([]);
  const [depts, setDepts]                 = useState<CwlDept[]>([]);
  const [selectedDept, setSelected]       = useState<string | null>(null);
  // TC del escenario: al pasar una linea a colones se siembran los colones con el
  // dolar actual x este TC, para no perder lo que ya estaba cargado.
  const [tcPromedio, setTcPromedio]       = useState(0);
  const [checkbook, setCheckbook]         = useState<OpexDeptCheckbook | null>(null);
  const [expanded, setExpanded]           = useState<Set<string>>(new Set());
  const [loading, setLoading]             = useState(true);
  const [deptLoading, setDeptLoading]     = useState(false);
  const [saving, setSaving]               = useState<string | null>(null);
  const [importing, setImporting]         = useState(false);
  const [importMsg, setImportMsg]         = useState<string | null>(null);
  const [xlsxUploading, setXlsxUploading] = useState(false);
  const [xlsxMsg, setXlsxMsg]             = useState<string | null>(null);
  const [addingLines, setAddingLines]     = useState<string | null>(null);
  const [error, setError]                 = useState<string | null>(null);
  const fileInputRef                       = useRef<HTMLInputElement>(null);

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

  // Recargar departamentos cuando cambia el escenario (sync con Master Data)
  useEffect(() => {
    if (!scenarioId) return;
    getTipoCambio(scenarioId).then(r => {
      const v = r.months.map(m => Number(m.tc_crc_usd ?? 0)).filter(x => x > 0);
      setTcPromedio(v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0);
    }).catch(() => setTcPromedio(0));
    getOpexDepts(scenarioId).then(async dbDepts => {
      await cargarDepartamentos();   // nombres del catálogo, no de una lista a mano
      const d = mergeDepts(dbDepts.map(x => x.dept_code), "OPEX");
      setDepts(d);
      setSelected(prev => (prev && d.some(x => x.dept_code === prev)) ? prev : (d[0]?.dept_code ?? null));
    }).catch(() => { /* sin depts para este escenario */ });
  }, [scenarioId]);

  const loadDept = useCallback(async (deptCode: string) => {
    if (!scenarioId) return;
    setDeptLoading(true);
    try {
      const cb = await getOpexDeptCheckbook(scenarioId, deptCode);
      setCheckbook(cb);
      // Auto-expand accounts that have non-zero annual total
      const nonZero = new Set(
        cb.accounts.filter(a => parseFloat(a.annual_total) > 0).map(a => a.account_code)
      );
      setExpanded(nonZero);
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
      const r = await sembrarCuentas(scenarioId, selectedDept, ["7"]);
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

  async function handleSaveEntry(entry: OpexEntry, monthKey: string, value: number) {
    if (!scenarioId) return;
    setSaving(entry.id);
    try {
      await updateOpexEntry(scenarioId, entry.id, { [monthKey]: value });
      if (selectedDept) await loadDept(selectedDept);
    } finally {
      setSaving(null);
    }
  }

  /** Cambia la moneda de una linea. Al pasarla a colones se siembran los colones
   *  con el dolar actual x el TC, para no perder lo que ya estaba cargado. */
  async function handleToggleMoneda(entry: OpexEntry) {
    if (!scenarioId) return;
    const aCRC = (entry.currency ?? "USD") !== "CRC";
    setSaving(entry.id);
    try {
      const body: Record<string, unknown> = { currency: aCRC ? "CRC" : "USD" };
      if (aCRC) {
        const tc = tcPromedio || 0;
        if (tc > 0) {
          MONTH_KEYS.forEach(mk => {
            body[`crc_${mk}`] = Math.round(parseFloat(entry.months[mk] ?? "0") * tc);
          });
        }
      }
      await updateOpexEntry(scenarioId, entry.id, body);
      if (selectedDept) await loadDept(selectedDept);
    } finally {
      setSaving(null);
    }
  }

  async function handleImport() {
    if (!scenarioId) return;
    setImporting(true);
    setImportMsg(null);
    try {
      const result = await importAllOpex(scenarioId);
      setImportMsg(t("imported", { n: result.imported }));
      const raw = await getOpexDepts(scenarioId);
      const d = mergeDepts(raw.map(x => x.dept_code), "OPEX");
      setDepts(d);
      if (d.length > 0 && !selectedDept) setSelected(d[0].dept_code);
      if (selectedDept) await loadDept(selectedDept);
    } catch (e: unknown) {
      setImportMsg(`${tc("error")}: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setImporting(false);
    }
  }

  async function handleAddLines(acct: OpexAccount) {
    if (!scenarioId || !selectedDept) return;
    setAddingLines(acct.account_code);
    try {
      await addOpexLines(scenarioId, selectedDept, acct.account_code, acct.account_name, 10);
      await loadDept(selectedDept);
    } finally {
      setAddingLines(null);
    }
  }

  async function handleXlsxUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !scenarioId) return;
    setXlsxUploading(true);
    setXlsxMsg(null);
    try {
      const result = await importOpexExcel(scenarioId, file);
      setXlsxMsg(`✓ Excel importado: ${result.imported} líneas en ${result.depts} depts`);
      const raw = await getOpexDepts(scenarioId);
      const d = mergeDepts(raw.map(x => x.dept_code), "OPEX");
      setDepts(d);
      if (selectedDept) await loadDept(selectedDept);
    } catch (ex: unknown) {
      setXlsxMsg(`${tc("error")}: ${ex instanceof Error ? ex.message : String(ex)}`);
    } finally {
      setXlsxUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function toggleAccount(acctCode: string) {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(acctCode)) next.delete(acctCode);
      else next.add(acctCode);
      return next;
    });
  }

  function expandAll() {
    if (!checkbook) return;
    setExpanded(new Set(checkbook.accounts.map(a => a.account_code)));
  }
  function collapseAll() { setExpanded(new Set()); }

  // Grand totals per month
  const monthTotals = MONTH_KEYS.map(mk =>
    fmtUsdNum(checkbook?.dept_monthly_totals[mk] ?? "0")
  );

  return (
    <div className="pag pag-ancha">
      <IrA esc={scenarioId} />
      <AvisoMoneda scenarioId={scenarioId} />
      <AvisoLineasObligatorias scenarioId={scenarioId} />
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>
            OPEX — Checkbook
          </h2>
          <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)" }}>
            {t("subtitle")}
          </p>
        </div>

        {/* Scenario selector (sincronizado con Master Data del año) */}
        <select
          value={scenarioId ?? ""}
          onChange={e => setScenarioId(e.target.value)}
          title={tc("scenarioSynced")}
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
          disabled={depts.length === 0}
          style={{
            marginLeft: 24,
            background: "var(--bg-input)", color: "var(--text-primary)",
            border: "1px solid var(--border-medium)", borderRadius: 4,
            padding: "5px 10px", fontSize: 13, cursor: "pointer",
          }}
        >
          {depts.length === 0
            ? <option value="">{tc("noData")}</option>
            : depts.map(d => (
                <option key={d.dept_code} value={d.dept_code}>
                  {d.dept_code} — {d.dept_name}
                </option>
              ))
          }
        </select>

        {/* Expand/collapse controls */}
        {checkbook && checkbook.accounts.length > 0 && (
          <div style={{ display: "flex", gap: 4 }}>
            <button onClick={expandAll} style={{
              padding: "4px 10px", fontSize: 11,
              background: "var(--bg-elevated)", color: "var(--text-secondary)",
              border: "1px solid var(--border-subtle)", borderRadius: 4, cursor: "pointer",
            }}>{tc("expandAll")}</button>
            <button onClick={collapseAll} style={{
              padding: "4px 10px", fontSize: 11,
              background: "var(--bg-elevated)", color: "var(--text-secondary)",
              border: "1px solid var(--border-subtle)", borderRadius: 4, cursor: "pointer",
            }}>{tc("collapseAll")}</button>
          </div>
        )}

        {/* Action buttons */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <RecalcButton scenarioId={scenarioId} />
          {/* Download Excel */}
          {scenarioId && (
            <a
              href={opexExcelUrl(scenarioId)}
              download
              style={{
                padding: "5px 14px", fontSize: 12, borderRadius: 4, textDecoration: "none",
                background: "var(--bg-elevated)", color: "var(--text-secondary)",
                border: "1px solid var(--border-medium)", cursor: "pointer",
                display: "inline-block", lineHeight: "20px",
              }}
            >
              ⬇ Excel
            </a>
          )}

          {/* Abre las cuentas que el catálogo le da a este departamento, en
              cero. Sin esto no había forma de empezar a presupuestar un
              departamento desde la pantalla: el Club Madresal tenía planilla e
              ingreso y ninguna línea de gasto donde escribir. */}
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
          >
            {sembrando ? t("seedRunning") : t("seedBtn")}
          </button>

          {/* Upload Excel */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
            style={{ display: "none" }}
            onChange={handleXlsxUpload}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={xlsxUploading || !scenarioId}
            style={{
              padding: "5px 14px", fontSize: 12, borderRadius: 4,
              background: xlsxUploading ? "var(--bg-elevated)" : "#1E3A5F",
              color: xlsxUploading ? "var(--text-secondary)" : "#90CAF9",
              border: "1px solid #2962FF", cursor: xlsxUploading ? "default" : "pointer",
            }}
          >
            {xlsxUploading ? t("uploading") : t("uploadExcel")}
          </button>

          {/* Server import (legacy) */}
          <button
            onClick={handleImport}
            disabled={importing || !scenarioId}
            style={{
              padding: "5px 14px", fontSize: 12, borderRadius: 4,
              background: importing ? "var(--bg-elevated)" : "var(--bg-elevated)",
              color: importing ? "var(--text-disabled)" : "var(--text-secondary)",
              border: "1px solid var(--border-subtle)", cursor: importing ? "default" : "pointer",
            }}
          >
            {importing ? t("importing") : t("importServer")}
          </button>
        </div>
      </div>

      {/* Status messages */}
      {xlsxMsg && (
        <div style={{
          marginBottom: 12, padding: "8px 14px", borderRadius: 4, fontSize: 12,
          background: xlsxMsg.startsWith("✓") ? "rgba(38,166,154,0.08)" : "rgba(239,83,80,0.08)",
          color: xlsxMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)",
          border: `1px solid ${xlsxMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)"}`,
        }}>
          {xlsxMsg}
        </div>
      )}
      {importMsg && (
        <div style={{
          marginBottom: 12, padding: "8px 14px", borderRadius: 4, fontSize: 12,
          background: importMsg.startsWith("✓") ? "rgba(38,166,154,0.08)" : "rgba(239,83,80,0.08)",
          color: importMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)",
          border: `1px solid ${importMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)"}`,
        }}>
          {importMsg}
        </div>
      )}

      {loading && <p style={{ color: "var(--text-secondary)" }}>{tc("loading")}</p>}
      {error && (
        <div style={{ color: "var(--negative)", background: "var(--bg-surface)", padding: "12px 16px", borderRadius: 4 }}>
          ⚠ {error}
        </div>
      )}
      {!loading && !error && deptLoading && (
        <p style={{ color: "var(--text-secondary)", fontSize: 12 }}>{tc("loadingDept")}</p>
      )}

      {/* Empty state */}
      {!loading && !error && !deptLoading && depts.length === 0 && (
        <div style={{
          color: "var(--text-secondary)", background: "var(--bg-surface)",
          padding: "24px", borderRadius: 4, textAlign: "center", fontSize: 13,
        }}>
          {t("emptyState")}
          <br />
          <span style={{ fontSize: 11, opacity: 0.7 }}>
            {t("emptyStateHint")}
          </span>
        </div>
      )}

      {/* Checkbook table */}
      {!loading && !error && !deptLoading && checkbook && checkbook.accounts.length > 0 && (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1440, fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", width: 50 }}>#</th>
                <th style={{ textAlign: "left", width: 200 }}>{t("colDetail")}</th>
                {MONTHS.map(m => (
                  <th key={m} style={{ textAlign: "right", minWidth: 78 }}>{m}</th>
                ))}
                <th style={{ textAlign: "right", color: "var(--brand)", minWidth: 90 }}>{tc("annual")}</th>
              </tr>
            </thead>
            <tbody>
              {checkbook.accounts.map(acct => (
                <AccountGroup
                  key={acct.account_code}
                  acct={acct}
                  expanded={expanded.has(acct.account_code)}
                  onToggle={() => toggleAccount(acct.account_code)}
                  onSaveEntry={handleSaveEntry}
                  onToggleMoneda={handleToggleMoneda}
                  onAddLines={handleAddLines}
                  saving={saving}
                  addingLines={addingLines}
                />
              ))}

              {/* Lo que le cayo por reparto (cafeteria 0220, lavanderia 0161):
                  no se edita aqui, pero el P&L lo suma. Sin esto el 0110
                  enseñaba $25,295.87 en la 7310 y el P&L tenia $40,881.68. */}
              {(checkbook.allocated?.length ?? 0) > 0 && (
                <>
                  <tr>
                    <td colSpan={15} style={{
                      paddingTop: 14, fontSize: 11, fontWeight: 700,
                      color: "var(--text-secondary)", letterSpacing: "0.04em",
                    }}>
                      {t("allocatedHeader")}
                    </td>
                  </tr>
                  {checkbook.allocated!.map(r => (
                    <tr key={`${r.account_code}-${r.target_dept}-${r.source_dept}`}
                        style={{ background: "rgba(41,98,255,0.05)" }}>
                      <td colSpan={2} style={{ color: "var(--text-secondary)" }}>
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
                      {MONTH_KEYS.map(mk => (
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

              {/* Dept total row */}
              <tr className="total" style={{ borderTop: "2px solid var(--border-medium)" }}>
                <td colSpan={2} style={{ fontWeight: 700, color: "var(--text-primary)" }}>
                  TOTAL OPEX — {selectedDept} {deptName(selectedDept ?? "")}
                  {(checkbook.allocated?.length ?? 0) > 0 && (
                    <span style={{ color: "var(--text-disabled)", fontSize: 10, fontWeight: 400 }}>
                      {" "}· {t("onlyCheckbook")}
                    </span>
                  )}
                </td>
                {monthTotals.map((v, i) => (
                  <td key={i} className="mono" style={{
                    textAlign: "right", fontWeight: 700,
                    color: v > 0 ? "var(--positive)" : "var(--text-disabled)",
                  }}>
                    {v > 0 ? <>${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</> : "—"}
                  </td>
                ))}
                <td className="mono" style={{
                  textAlign: "right", fontWeight: 700, color: "var(--positive)",
                }}>
                  {fmtUsd(checkbook.dept_annual_total)}
                </td>
              </tr>

              {/* El numero contra el que hay que comparar el P&L. */}
              {(checkbook.allocated?.length ?? 0) > 0 && (
                <tr className="total" style={{ background: "rgba(41,98,255,0.10)" }}>
                  <td colSpan={2} style={{ fontWeight: 700, color: "var(--brand)" }}>
                    {t("totalIntoPl")}
                  </td>
                  {monthTotals.map((v, i) => {
                    const rep = checkbook.allocated!.reduce(
                      (s, r) => s + parseFloat(r[MONTH_KEYS[i]] || "0"), 0);
                    return (
                      <td key={i} className="mono"
                          style={{ textAlign: "right", fontWeight: 700, color: "var(--brand)" }}>
                        ${(v + rep).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                    );
                  })}
                  <td className="mono" style={{ textAlign: "right", fontWeight: 800, color: "var(--brand)" }}>
                    {fmtUsd(String(
                      parseFloat(checkbook.dept_annual_total || "0")
                      + parseFloat(checkbook.allocated_annual_total || "0")
                    ))}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
