"use client";
import { usePlanningScenario, usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import RecalcButton from "@/components/RecalcButton";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  getScenarios, getPayrollDepts, getDeptCheckbook, getDeptSummary,
  addPositions, getNextPositionCode, duplicatePosition, deletePosition,
  downloadPayrollExcel, uploadPayrollExcel, updatePosition,
  bajarBeneficiosExcel, subirBeneficiosExcel,
  type Scenario, type Dept, type Position, type DeptSummaryMonth,
} from "@/lib/api";
import { departamentos, cargarDepartamentos, estaApagado } from "@/lib/cwl-depts";
import { HOTEL_ID, hotelSlug } from "@/lib/hotel";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

/** El selector ofrece TODOS los departamentos, tengan posiciones o no.
 *
 *  Antes solo salían los que ya tenían gente cargada, más dos escritos a mano
 *  (260 y 270). Con eso, empezar la planilla de un departamento nuevo era
 *  imposible desde la pantalla: no aparecía hasta que alguien le metiera una
 *  posición por otro lado. El owner lo dijo derecho — «lo que está desplegado
 *  va a existir, entonces debe tener planilla, opex, costo y todo lo que
 *  corresponda».
 *
 *  **Los que tienen gente van primero, con el nombre de la BD.** Ahí viven los
 *  sub-departamentos (0111 Front Desk, 0122 Cocina…) que NO están en el catálogo
 *  y que `mergeDepts` degradaría a «código — código». Después se agregan los del
 *  catálogo que falten.
 *
 *  **No se siembran filas de planilla en blanco**, a diferencia de OPEX y costo:
 *  una línea de gasto vacía es una cuenta esperando un monto, pero una fila de
 *  planilla vacía sería una persona que no existe. Lo que se abre es la puerta
 *  para cargar posiciones, no un empleado fantasma. */
function withExtraDepts(dbDepts: Dept[]): Dept[] {
  const have = new Set(dbDepts.map(d => d.dept_code));
  const extra = departamentos()
    .filter(d => !have.has(d.dept_code))
    .map(d => ({ dept_code: d.dept_code, dept_name: d.dept_name }));
  // El filtro del provisionamiento va DE ÚLTIMO: si fuera antes, un
  // departamento apagado volvería a entrar por la puerta de los agregados.
  return [...dbDepts, ...extra].filter(d => !estaApagado(d.dept_code, "PAYROLL"));
}

const CONCEPTS: { key: keyof DeptSummaryMonth; label: string; group: "base"|"auto"|"benefit" }[] = [
  { key: "c6000", label: "S&W",            group: "base" },
  { key: "c6001", label: "Overtime",        group: "base" },
  { key: "c6002", label: "Day Off",         group: "base" },
  { key: "c6003", label: "Work Holiday",    group: "base" },
  { key: "c6010", label: "Commissions",     group: "base" },
  { key: "c6024", label: "Vac. Taken",      group: "base" },
  { key: "c6027", label: "Incentive Bonus", group: "base" },
  { key: "base",  label: "BASE",            group: "auto" },
  { key: "c6020", label: "CCSS",            group: "auto" },
  { key: "c6021", label: "Aguinaldo",       group: "auto" },
  { key: "c6004", label: "Disabilities",    group: "benefit" },
  { key: "c6022", label: "Occ. Hazard",     group: "benefit" },
  { key: "c6023", label: "Vac. Prov.",      group: "benefit" },
  { key: "c6025", label: "Cafeteria",       group: "benefit" },
  { key: "c6026", label: "Severance",       group: "benefit" },
  { key: "c6028", label: "Housing",         group: "benefit" },
  { key: "c6029", label: "Transport",       group: "benefit" },
  { key: "c6030", label: "Other",           group: "benefit" },
  { key: "total", label: "TOTAL",           group: "auto" },
];

const GROUP_COLOR: Record<string, string> = {
  base:    "var(--text-primary)",
  auto:    "var(--brand)",
  benefit: "var(--text-secondary)",
};

function fmtUsd(v: number) {
  if (!v) return "—";
  const s = "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return v < 0 ? `(${s})` : s;
}
function fmtFte(v: number) {
  if (v === 0) return <span style={{ color: "var(--text-disabled)" }}>0.0</span>;
  return <span style={{ color: v < 1 ? "var(--warning)" : "var(--text-primary)" }}>{v.toFixed(1)}</span>;
}

type ViewMode = "summary" | "positions";

export default function PayrollCheckbookPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("payrollCb");
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios]     = useState<Scenario[]>([]);
  const [depts, setDepts]             = useState<Dept[]>([]);
  const [selectedDept, setSelected]   = useState<string | null>(null);
  const [positions, setPositions]     = useState<Position[]>([]);
  const [summary, setSummary]         = useState<DeptSummaryMonth[]>([]);
  const [view, setView]               = useState<ViewMode>("summary");
  const [loading, setLoading]         = useState(true);
  const [deptLoading, setDeptLoading] = useState(false);
  const [error, setError]             = useState<string | null>(null);

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
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : tc("error"));
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  // Recargar departamentos cuando cambia el escenario (sync con Master Data del año)
  useEffect(() => {
    if (!scenarioId) return;
    getPayrollDepts(scenarioId).then(async raw => {
      await cargarDepartamentos();   // los nombres y qué está escondido
      const d = withExtraDepts(raw);
      setDepts(d);
      setSelected(prev => (prev && d.some(x => x.dept_code === prev)) ? prev : (d[0]?.dept_code ?? null));
    }).catch(() => { /* sin depts para este escenario */ });
  }, [scenarioId]);

  const loadDept = useCallback(async (deptCode: string) => {
    if (!scenarioId) return;
    setDeptLoading(true);
    try {
      const [cb, sum] = await Promise.all([
        getDeptCheckbook(scenarioId, deptCode),
        getDeptSummary(scenarioId, deptCode),
      ]);
      setPositions(cb.positions);
      setSummary(sum);
    } finally {
      setDeptLoading(false);
    }
  }, [scenarioId]);

  useEffect(() => {
    if (selectedDept) loadDept(selectedDept);
  }, [selectedDept, loadDept]);

  // ── Excel download / upload + add positions ──────────────────────────────────
  const fileRef = useRef<HTMLInputElement>(null);
  // Excel de conceptos MANUALES (horas extra, bono, cesantía, transporte,
  // vivienda, otros): una hoja por concepto, una fila por posición.
  const benefRef = useRef<HTMLInputElement>(null);

  async function bajarBeneficios() {
    if (!scenarioId) return;
    setBusy("benef-download");
    try {
      const blob = await bajarBeneficiosExcel(scenarioId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `beneficios_${scenarioId.slice(0, 8)}.xlsx`;
      a.click(); URL.revokeObjectURL(url);
      flash(t("benefitsDownloaded"));
    } catch (e) { flash(e instanceof Error ? e.message : tc("error")); }
    finally { setBusy(null); }
  }

  async function subirBeneficios(file: File) {
    if (!scenarioId) return;
    setBusy("benef-upload");
    try {
      const r = await subirBeneficiosExcel(scenarioId, file);
      const extra = r.avisos?.length ? ` · ${r.avisos.join(" · ")}` : "";
      flash(t("benefitsUploaded", { celdas: r.celdas_escritas, posiciones: r.posiciones_tocadas, conceptos: r.conceptos.length }) + extra);
      if (selectedDept) await loadDept(selectedDept);
    } catch (e) { flash(e instanceof Error ? e.message : tc("error")); }
    finally { setBusy(null); }
  }
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [addModal, setAddModal] = useState(false);

  const flash = (m: string) => { setToast(m); setTimeout(() => setToast(null), 5000); };

  // Download the LOCKED Excel (only salary + FTE editable) — one sheet per dept
  const handleDownload = useCallback(async () => {
    if (!scenarioId) return;
    setBusy("download");
    try {
      const blob = await downloadPayrollExcel(scenarioId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `Planilla_${hotelSlug()}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      flash(t("excelDownloaded"));
    } catch (e) {
      flash(e instanceof Error ? e.message : t("errorDownloading"));
    } finally { setBusy(null); }
  }, [scenarioId]);

  // Upload the filled Excel → re-applies salary + FTE (structure stays as in app)
  const handleUpload = useCallback(async (file: File) => {
    if (!scenarioId) return;
    setBusy("upload");
    try {
      const res = await uploadPayrollExcel(scenarioId, file);
      const d = withExtraDepts(await getPayrollDepts(scenarioId));
      setDepts(d);
      if (selectedDept) await loadDept(selectedDept);
      flash(t("payrollUpdated", { n: res.imported ?? "" }));
    } catch (e) {
      flash(e instanceof Error ? e.message : t("errorUploading"));
    } finally { setBusy(null); }
  }, [scenarioId, selectedDept, loadDept]);

  // Append N copies of a position to the current roster (bulk = current + new)
  const handleAddPositions = useCallback(async (
    deptCode: string, positionName: string, positionCode: string, count: number,
    salary: number, currency: string,
  ) => {
    if (!scenarioId) return;
    setBusy("add");
    try {
      // SOLO inserta. Antes mandaba el roster completo a `bulkPayroll`, que
      // borra toda la planilla y la recrea: como los conceptos cuelgan de la
      // posición con ON DELETE CASCADE, agregar una persona se llevaba las
      // horas extra, comisiones y bonos DIGITADOS de todas las demás.
      const dn = depts.find(d => d.dept_code === deptCode)?.dept_name ?? "";
      const res = await addPositions(scenarioId, {
        dept_code: deptCode, dept_name: dn,
        position_name: positionName, position_code: positionCode,
        count, salary_amount: salary || 0, salary_currency: currency,
      });
      const d = withExtraDepts(await getPayrollDepts(scenarioId));
      setDepts(d);
      setSelected(deptCode);
      await loadDept(deptCode);
      setAddModal(false);
      flash(t("positionsAdded", { count, nombre: positionName, codigos: res.codes.join(", ") }));
    } catch (e) {
      flash(e instanceof Error ? `⚠ ${e.message}` : `⚠ ${tc("error")}`);
    } finally { setBusy(null); }
  }, [scenarioId, depts, loadDept]);

  // Duplicate a position (+1 persona) — optimistic: append locally, no full reload
  const handleDuplicate = useCallback(async (pos: Position) => {
    if (!scenarioId) return;
    try {
      const res = await duplicatePosition(scenarioId, pos.id);
      const copy: Position = {
        ...pos, id: res.id, employee_name: res.employee_name,
        months: pos.months.map(m => ({ ...m, entry: null })),
      };
      setPositions(prev => {
        const idx = prev.findIndex(p => p.id === pos.id);
        const next = [...prev];
        next.splice(idx + 1, 0, copy);  // insert right after the source
        return next;
      });
    } catch (e) {
      flash(e instanceof Error ? e.message : t("errorDuplicating"));
    }
  }, [scenarioId]);

  const handleDeletePos = useCallback(async (pos: Position) => {
    if (!scenarioId) return;
    setPositions(prev => prev.filter(p => p.id !== pos.id));  // optimista
    try {
      await deletePosition(scenarioId, pos.id);
    } catch (e) {
      flash(e instanceof Error ? e.message : t("errorDeleting"));
      if (selectedDept) loadDept(selectedDept);  // revertir si falló
    }
  }, [scenarioId, selectedDept, loadDept]);

  // Edit a position field in the app (currency / employee / salary) — optimistic
  const handleEditPos = useCallback(async (
    pos: Position, fields: Partial<{ employee_name: string; salary_amount: number; salary_currency: string }>,
  ) => {
    if (!scenarioId) return;
    setPositions(prev => prev.map(p => p.id === pos.id ? { ...p, ...fields } : p));
    try {
      await updatePosition(scenarioId, pos.id, fields);
    } catch (e) {
      flash(e instanceof Error ? e.message : t("errorEditing"));
      if (selectedDept) loadDept(selectedDept);
    }
  }, [scenarioId, selectedDept, loadDept]);

  const selectedDeptName = depts.find(d => d.dept_code === selectedDept)?.dept_name ?? selectedDept;

  // Annual total per concept
  function annualTotal(key: keyof DeptSummaryMonth) {
    return summary.reduce((s, m) => s + (m[key] as number), 0);
  }

  return (
    <div className="pag pag-ancha">
      <IrA esc={scenarioId} />
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>
            {t("title")}
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

        {/* Excel + add-positions actions */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <RecalcButton scenarioId={scenarioId} />
          <button onClick={() => setAddModal(true)} disabled={!!busy}
            style={{ padding: "5px 12px", fontSize: 12, borderRadius: 4, cursor: "pointer",
              background: "var(--bg-surface)", color: "var(--text-primary)",
              border: "1px solid var(--border-medium)", fontWeight: 600 }}>
            {t("addPositionsBtn")}
          </button>
          <button onClick={handleDownload} disabled={!!busy}
            style={{ padding: "5px 12px", fontSize: 12, borderRadius: 4, cursor: "pointer",
              background: "var(--accent-excel)", color: "#fff", border: "none", fontWeight: 600 }}>
            {busy === "download" ? t("downloading") : "⬇ Excel"}
          </button>
          <button onClick={() => fileRef.current?.click()} disabled={!!busy}
            style={{ padding: "5px 12px", fontSize: 12, borderRadius: 4, cursor: "pointer",
              background: "var(--bg-surface)", color: "var(--text-primary)",
              border: "1px solid var(--border-medium)", fontWeight: 600 }}>
            {busy === "upload" ? t("uploading") : t("upload")}
          </button>
          <input ref={fileRef} type="file" accept=".xlsx" style={{ display: "none" }}
            onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f); e.target.value = ""; }} />
          <span style={{ width: 1, height: 20, background: "var(--border-medium)" }} />
          <button onClick={bajarBeneficios} disabled={!!busy}
            title={t("conceptsHint")}
            style={{ padding: "5px 12px", fontSize: 12, borderRadius: 4, cursor: "pointer",
              background: "var(--bg-surface)", color: "var(--text-primary)",
              border: "1px solid var(--border-medium)", fontWeight: 600 }}>
            {busy === "benef-download" ? t("downloading") : t("downloadBenefits")}
          </button>
          <button onClick={() => benefRef.current?.click()} disabled={!!busy}
            title={t("uploadBenefitsHint")}
            style={{ padding: "5px 12px", fontSize: 12, borderRadius: 4, cursor: "pointer",
              background: "var(--bg-surface)", color: "var(--text-primary)",
              border: "1px solid var(--border-medium)", fontWeight: 600 }}>
            {busy === "benef-upload" ? t("uploading") : t("uploadBenefits")}
          </button>
          <input ref={benefRef} type="file" accept=".xlsx" style={{ display: "none" }}
            onChange={e => { const f = e.target.files?.[0]; if (f) subirBeneficios(f); e.target.value = ""; }} />
        </div>

        {/* View toggle */}
        <div style={{ display: "flex", gap: 0 }}>
          {([["summary",t("viewSummary")],["positions",t("viewPositions")]] as [ViewMode,string][]).map(([v,label], i, arr) => (
            <button key={v} onClick={() => setView(v)} style={{
              padding: "5px 14px", fontSize: 12,
              background: view === v ? "var(--brand)" : "var(--bg-surface)",
              color: view === v ? "#fff" : "var(--text-secondary)",
              border: "1px solid var(--border-medium)",
              borderRadius: i === 0 ? "4px 0 0 4px" : i === arr.length - 1 ? "0 4px 4px 0" : "0",
              cursor: "pointer",
            }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {toast && (
        <div style={{ marginBottom: 12, padding: "8px 14px", borderRadius: 4, fontSize: 12,
          background: "rgba(38,166,154,0.12)", color: "var(--positive)",
          border: "1px solid var(--positive)" }}>
          {toast}
        </div>
      )}

      {addModal && (
        <AddPositionsModal
          depts={depts}
          defaultDept={selectedDept ?? (depts[0]?.dept_code ?? "")}
          scenarioId={scenarioId}
          busy={busy === "add"}
          onClose={() => setAddModal(false)}
          onAdd={handleAddPositions}
        />
      )}

      {loading && <p style={{ color: "var(--text-secondary)" }}>{tc("loading")}</p>}
      {error && (
        <div style={{ color: "var(--negative)", background: "var(--bg-surface)", padding: "12px 16px", borderRadius: 4, marginBottom: 16 }}>
          ⚠ {error}
          <p style={{ margin: "4px 0 0", fontSize: 11, color: "var(--text-secondary)" }}>
            {t("backendHint")}
          </p>
        </div>
      )}

      {!loading && !error && deptLoading && (
        <p style={{ color: "var(--text-secondary)", fontSize: 12 }}>{tc("loadingDept")}</p>
      )}

      {/* ── VIEW: Summary (17 concepts × 12 months) ── */}
      {!loading && !error && !deptLoading && view === "summary" && summary.length > 0 && (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <div style={{ marginBottom: 8, fontSize: 13, color: "var(--text-primary)", fontWeight: 600 }}>
            {selectedDeptName}
          </div>
          <table className="fin-table">
            <thead>
              <tr>
                <th style={{ textAlign: "left", width: 140 }}>{tc("concept")}</th>
                {MONTHS.map(m => <th key={m}>{m}</th>)}
                <th style={{ color: "var(--brand)" }}>{tc("annual")}</th>
              </tr>
            </thead>
            <tbody>
              {CONCEPTS.map(c => {
                const isTotal = c.key === "total";
                const isBase  = c.key === "base";
                const isAuto  = c.group === "auto" && !isTotal;
                return (
                  <tr key={c.key} className={isTotal || isBase ? "total" : ""}>
                    <td style={{
                      color: GROUP_COLOR[c.group],
                      fontWeight: isTotal || isBase ? 600 : 400,
                      paddingLeft: c.group === "benefit" ? 20 : undefined,
                    }}>
                      {isAuto && !isBase ? <span style={{ opacity: 0.5 }}>⟳ </span> : null}
                      {c.label}
                    </td>
                    {summary.map(m => (
                      <td key={m.month} className="mono" style={{
                        color: isTotal ? "var(--text-primary)" :
                               isBase  ? "var(--brand)" :
                               c.group === "benefit" ? "var(--text-secondary)" : undefined,
                        fontWeight: isTotal || isBase ? 600 : 400,
                      }}>
                        {fmtUsd(m[c.key] as number)}
                      </td>
                    ))}
                    <td className="mono" style={{ fontWeight: 600, color: isTotal ? "var(--positive)" : undefined }}>
                      {fmtUsd(annualTotal(c.key))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── VIEW: Positions (FTE + SW per position × month) ── */}
      {!loading && !error && !deptLoading && view === "positions" && (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          {positions.length === 0 ? (
            <p style={{ color: "var(--text-secondary)" }}>
              {t("noPositions")}
            </p>
          ) : (
            <table className="fin-table">
              <thead>
                <tr>
                  <th style={{ textAlign: "left", width: 60 }}>{tc("code")}</th>
                  <th style={{ textAlign: "left", width: 160 }}>{t("position")}</th>
                  <th style={{ textAlign: "left", width: 140 }}>{tc("employee")}</th>
                  <th>{t("salary")}</th>
                  {MONTHS.map(m => <th key={m}>{m}<br/><span style={{ fontWeight: 400, opacity: 0.6 }}>FTE / SW</span></th>)}
                  <th>{t("annualTotal")}</th>
                  <th style={{ width: 70 }}></th>
                </tr>
              </thead>
              <tbody>
                {positions.map(pos => {
                  const annualSw = pos.months.reduce((s, m) =>
                    s + (m.entry?.c6000_sw ?? 0), 0);
                  const annualTotal = pos.months.reduce((s, m) =>
                    s + (m.entry?.total ?? 0), 0);
                  return (
                    <tr key={pos.id}>
                      <td style={{ color: "var(--text-secondary)", fontSize: 11 }}>{pos.position_code}</td>
                      <td style={{ color: "var(--text-primary)" }}>{pos.position_name}</td>
                      <td>
                        <input
                          defaultValue={pos.employee_name}
                          onBlur={e => { const v = e.target.value.trim();
                            if (v && v !== pos.employee_name) handleEditPos(pos, { employee_name: v }); }}
                          style={{ width: 130, background: "transparent", fontSize: 12,
                            color: pos.employee_name === "VACANTE" ? "var(--text-disabled)" : "var(--text-secondary)",
                            border: "1px solid transparent", borderRadius: 4, padding: "2px 4px" }}
                          onFocus={e => e.target.style.border = "1px solid var(--border-medium)"}
                          onBlurCapture={e => e.target.style.border = "1px solid transparent"} />
                      </td>
                      <td className="mono" style={{ whiteSpace: "nowrap" }}>
                        {pos.salary_currency === "CRC"
                          ? "₡" + Math.round(pos.salary_amount).toLocaleString("es-CR")
                          : "$" + pos.salary_amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        <select value={pos.salary_currency}
                          onChange={e => handleEditPos(pos, { salary_currency: e.target.value })}
                          title={t("personCurrency")}
                          style={{ marginLeft: 6, fontSize: 10, padding: "1px 2px", cursor: "pointer",
                            background: "var(--bg-input)", color: "var(--text-secondary)",
                            border: "1px solid var(--border-medium)", borderRadius: 3 }}>
                          <option value="CRC">CRC</option>
                          <option value="USD">USD</option>
                        </select>
                      </td>
                      {pos.months.map(mdata => (
                        <td key={mdata.month} style={{ padding: "4px 8px" }}>
                          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 1 }}>
                            <span className="mono" style={{ fontSize: 11 }}>{fmtFte(mdata.fte)}</span>
                            <span className="mono" style={{ fontSize: 10, color: "var(--text-secondary)" }}>
                              {mdata.entry ? fmtUsd(mdata.entry.c6000_sw) : "—"}
                            </span>
                          </div>
                        </td>
                      ))}
                      <td className="mono" style={{ fontWeight: 600 }}>
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 1 }}>
                          <span style={{ color: "var(--positive)" }}>{fmtUsd(annualTotal)}</span>
                          <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>SW: {fmtUsd(annualSw)}</span>
                        </div>
                      </td>
                      <td style={{ whiteSpace: "nowrap", textAlign: "center" }}>
                        <button title={t("duplicate")} onClick={() => handleDuplicate(pos)}
                          disabled={!!busy}
                          style={{ padding: "2px 8px", fontSize: 13, fontWeight: 700, cursor: "pointer",
                            background: "var(--brand)", color: "#fff", border: "none", borderRadius: 4 }}>
                          {busy === `dup-${pos.id}` ? "…" : "+1"}
                        </button>
                        <button title={t("deletePerson")} onClick={() => handleDeletePos(pos)}
                          disabled={!!busy}
                          style={{ marginLeft: 4, padding: "2px 7px", fontSize: 12, cursor: "pointer",
                            background: "var(--bg-surface)", color: "var(--negative)",
                            border: "1px solid var(--border-medium)", borderRadius: 4 }}>
                          {busy === `del-${pos.id}` ? "…" : "✕"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Empty state when no data and no error */}
      {!loading && !error && !deptLoading && view === "summary" && summary.length === 0 && (
        <p style={{ color: "var(--text-secondary)" }}>
          {t("noPayrollData")}
        </p>
      )}
    </div>
  );
}

// ── Add positions modal ────────────────────────────────────────────────────────
function AddPositionsModal({
  depts, defaultDept, scenarioId, busy, onClose, onAdd,
}: {
  depts: Dept[];
  defaultDept: string;
  scenarioId: string;
  busy: boolean;
  onClose: () => void;
  onAdd: (dept: string, name: string, code: string, count: number, salary: number, currency: string) => void;
}) {
  const t = useTranslations("payrollCb");
  const tc = useTranslations("common");
  const [dept, setDept] = useState(defaultDept);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [count, setCount] = useState(1);
  const [salary, setSalary] = useState(0);
  const [currency, setCurrency] = useState("CRC");
  // Los códigos que va a asignar el backend, mostrados ANTES de agregar: el
  // código es la llave de los reportes de planilla, así que el usuario tiene
  // que ver cuál le toca a cada quien mientras todavía puede cambiarlo.
  const [sugeridos, setSugeridos] = useState<string[]>([]);
  useEffect(() => {
    let vivo = true;
    if (!scenarioId || !dept || count < 1) { setSugeridos([]); return; }
    getNextPositionCode(scenarioId, dept, Math.min(count, 12))
      .then(r => { if (vivo) setSugeridos(r.codes); })
      .catch(() => { if (vivo) setSugeridos([]); });
    return () => { vivo = false; };
  }, [scenarioId, dept, count]);

  const inp: React.CSSProperties = {
    background: "var(--bg-input)", color: "var(--text-primary)",
    border: "1px solid var(--border-medium)", borderRadius: 4,
    padding: "6px 10px", fontSize: 13, width: "100%",
  };
  const lbl: React.CSSProperties = { fontSize: 11, color: "var(--text-secondary)", marginBottom: 4, display: "block" };

  const canSave = dept && name.trim() && count >= 1;

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 50,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: "var(--bg-surface)", border: "1px solid var(--border-medium)",
        borderRadius: 8, padding: 20, width: 440, maxWidth: "90vw",
      }}>
        <h3 style={{ margin: "0 0 4px", fontSize: 16, color: "var(--text-primary)" }}>{t("addPositions")}</h3>
        <p style={{ margin: "0 0 16px", fontSize: 12, color: "var(--text-secondary)" }}>
          {t("addPositionsHelp")}
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div style={{ gridColumn: "1 / 3" }}>
            <label style={lbl}>{tc("department")}</label>
            <select value={dept} onChange={e => setDept(e.target.value)} style={inp}>
              {depts.map(d => <option key={d.dept_code} value={d.dept_code}>{d.dept_code} — {d.dept_name}</option>)}
            </select>
          </div>
          <div style={{ gridColumn: "1 / 3" }}>
            <label style={lbl}>{t("positionName")}</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder={t("positionNamePlaceholder")} style={inp} />
          </div>
          <div>
            <label style={lbl}>{tc("code")}</label>
            <input value={code} onChange={e => setCode(e.target.value)}
              placeholder={sugeridos.length ? sugeridos.join(", ") : t("codeAuto")} style={inp} />
            <div style={{ fontSize: 10.5, color: "var(--text-secondary)", marginTop: 3 }}>
              {code.trim()
                ? t("codeExplicit")
                : sugeridos.length
                  ? t("codeAssigned", { n: sugeridos.length, codigos: sugeridos.join(", ") })
                  : t("codeBlank")}
            </div>
          </div>
          <div>
            <label style={lbl}>{t("quantity")}</label>
            <input type="number" min={1} value={count} onChange={e => setCount(Number(e.target.value))} style={inp} />
          </div>
          <div>
            <label style={lbl}>{t("baseSalary")}</label>
            <input type="number" min={0} value={salary} onChange={e => setSalary(Number(e.target.value))} style={inp} />
          </div>
          <div>
            <label style={lbl}>{tc("currency")}</label>
            <select value={currency} onChange={e => setCurrency(e.target.value)} style={inp}>
              <option value="CRC">CRC</option>
              <option value="USD">USD</option>
            </select>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
          <button onClick={onClose} disabled={busy} style={{
            padding: "7px 14px", fontSize: 13, borderRadius: 5, cursor: "pointer",
            background: "var(--bg-surface)", color: "var(--text-secondary)",
            border: "1px solid var(--border-medium)" }}>{tc("cancel")}</button>
          <button
            onClick={() => onAdd(dept, name.trim(), code.trim(), count, salary, currency)}
            disabled={!canSave || busy}
            style={{
              padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600,
              cursor: canSave && !busy ? "pointer" : "not-allowed",
              background: canSave && !busy ? "var(--brand)" : "var(--bg-surface)",
              color: canSave && !busy ? "#fff" : "var(--text-disabled)", border: "none" }}>
            {busy ? t("adding") : t("addN", { n: count })}
          </button>
        </div>
      </div>
    </div>
  );
}
