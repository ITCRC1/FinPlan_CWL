"use client";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  getReportLines, getAccountMappings, getUnmappedAccounts,
  createAccountMapping, updateAccountMapping, deleteAccountMapping,
  type ReportLine, type AccountMappingRow, type UnmappedAccount, type AccountMappingCreate,
} from "@/lib/api";
import { bajarCuadros, type Cuadro, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

// ── tiny helpers ──────────────────────────────────────────────────────────────
const STATUS_COLOR: Record<string, string> = {
  YES: "var(--positive)", REVIEW: "#e6a817", NO: "var(--negative)",
};

function Badge({ status }: { status: string }) {
  return (
    <span style={{
      padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 700,
      background: STATUS_COLOR[status] ?? "var(--surface)",
      color: "#fff",
    }}>{status}</span>
  );
}

const BTN: React.CSSProperties = {
  padding: "6px 14px", borderRadius: 6, cursor: "pointer", fontSize: 12,
  fontWeight: 600, border: "1px solid var(--border)",
  background: "var(--surface)", color: "var(--text)",
};
const BTN_PRIMARY: React.CSSProperties = {
  ...BTN, background: "var(--brand)", color: "#fff", border: "none",
};
const BTN_DANGER: React.CSSProperties = {
  ...BTN, color: "var(--negative)",
};
const INPUT: React.CSSProperties = {
  background: "var(--surface)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: 5,
  padding: "5px 10px", fontSize: 13, width: "100%",
};
const SELECT_S: React.CSSProperties = {
  ...INPUT, cursor: "pointer",
};

// ── Add / Edit modal ──────────────────────────────────────────────────────────
interface ModalProps {
  lines: ReportLine[];
  initial?: Partial<AccountMappingCreate & { id: string }>;
  prefillDept?: string;
  prefillAccount?: string;
  onSave: (data: AccountMappingCreate) => Promise<void>;
  onClose: () => void;
}

function MappingModal({ lines, initial, prefillDept, prefillAccount, onSave, onClose }: ModalProps) {
  const tc = useTranslations("common");
  const t = useTranslations("mapping");
  const sections = Array.from(new Set(lines.filter(l => l.line_type !== "HEADER").map(l => l.section)));
  const [section, setSection] = useState(initial?.report_section ?? sections[0] ?? "");
  const filtered = lines.filter(l => l.section === section && l.line_type !== "HEADER");

  const [form, setForm] = useState<AccountMappingCreate>({
    active_status: "YES",
    report_line_code: initial?.report_line_code ?? filtered[0]?.line_code ?? "",
    report_line_name: initial?.report_line_name ?? "",
    report_section: section,
    source_origin: initial?.source_origin ?? "",
    source_department: initial?.source_department ?? "",
    // El «sin mapear» llega con el CÓDIGO del departamento, no con su nombre:
    // por eso precarga acá y no en el campo de al lado, donde salía «0120» como
    // si fuera el nombre del departamento.
    dept_code: initial?.dept_code ?? prefillDept ?? "",
    account_code: initial?.account_code ?? prefillAccount ?? "",
    account_name_example: initial?.account_name_example ?? "",
    financial_nature: initial?.financial_nature ?? "Expense",
    rollup_operator: "SUM",
    notes: initial?.notes ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  function set(k: keyof AccountMappingCreate, v: string) {
    setForm(f => ({ ...f, [k]: v }));
  }

  async function handleSave() {
    if (!form.account_code.trim() || !form.report_line_code) {
      setErr(t("modal.required"));
      return;
    }
    setSaving(true);
    try {
      await onSave({ ...form, report_section: section });
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("modal.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 10,
        padding: 28, width: 540, maxHeight: "90vh", overflowY: "auto",
      }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 20 }}>
          {initial?.id ? t("modal.editTitle") : t("modal.newTitle")}
        </h2>

        <div style={{ display: "grid", gap: 14 }}>
          {/* Status */}
          <div>
            <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>{tc("status")}</label>
            <select value={form.active_status} onChange={e => set("active_status", e.target.value)} style={SELECT_S}>
              {["YES","REVIEW","NO"].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          {/* Section + Line */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div>
              <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>{tc("section")}</label>
              <select value={section} onChange={e => {
                setSection(e.target.value);
                const first = lines.find(l => l.section === e.target.value && l.line_type !== "HEADER");
                if (first) set("report_line_code", first.line_code);
              }} style={SELECT_S}>
                {sections.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>{t("reportLine")}</label>
              <select value={form.report_line_code} onChange={e => set("report_line_code", e.target.value)} style={SELECT_S}>
                {filtered.map(l => <option key={l.line_code} value={l.line_code}>{l.line_name}</option>)}
              </select>
            </div>
          </div>

          {/* Departamento (código + nombre) y cuenta.
              El CÓDIGO es lo que rutea el P&L. Si se deja vacío el backend lo
              deriva del nombre — y si el nombre no es de los que sabe leer, la
              regla queda sin código y la cuenta cae en la línea del primer
              departamento. Estaba escondido; ahora se ve y se puede escribir. */}
          <div style={{ display: "grid", gridTemplateColumns: "90px 1fr 1fr", gap: 10 }}>
            <div>
              <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>{tc("code")}</label>
              <input value={form.dept_code ?? ""} onChange={e => set("dept_code", e.target.value)}
                     style={{ ...INPUT, fontFamily: "monospace" }} placeholder="0120" />
            </div>
            <div>
              <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>{t("deptGl")}</label>
              <input value={form.source_department ?? ""} onChange={e => set("source_department", e.target.value)} style={INPUT} placeholder={t("deptGlPlaceholder")} />
            </div>
            <div>
              <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>{t("accountGl")}</label>
              <input value={form.account_code} onChange={e => set("account_code", e.target.value)} style={INPUT} placeholder={t("accountGlPlaceholder")} />
            </div>
          </div>

          {/* Nature + Origin */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div>
              <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>{t("nature")}</label>
              <select value={form.financial_nature} onChange={e => set("financial_nature", e.target.value)} style={SELECT_S}>
                <option value="Revenue">Revenue</option>
                <option value="Expense">Expense</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>{t("origin")}</label>
              <input value={form.source_origin ?? ""} onChange={e => set("source_origin", e.target.value)} style={INPUT} placeholder={t("originPlaceholder")} />
            </div>
          </div>

          {/* Account name example */}
          <div>
            <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>{t("accountNameRef")}</label>
            <input value={form.account_name_example ?? ""} onChange={e => set("account_name_example", e.target.value)} style={INPUT} placeholder={t("accountNamePlaceholder")} />
          </div>

          {/* Notes */}
          <div>
            <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>{t("notes")}</label>
            <input value={form.notes ?? ""} onChange={e => set("notes", e.target.value)} style={INPUT} placeholder={t("notesPlaceholder")} />
          </div>

          {err && <div style={{ color: "var(--negative)", fontSize: 12 }}>{err}</div>}

          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 4 }}>
            <button onClick={onClose} style={BTN}>{tc("cancel")}</button>
            <button onClick={handleSave} disabled={saving} style={BTN_PRIMARY}>
              {saving ? tc("saving") : tc("save")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function MappingAdminPage() {
  const t = useTranslations("mapping");
  const tc = useTranslations("common");
  const [tab, setTab] = useState<"rules" | "unmapped">("rules");
  const [lines, setLines] = useState<ReportLine[]>([]);
  const [mappings, setMappings] = useState<AccountMappingRow[]>([]);
  const [unmapped, setUnmapped] = useState<UnmappedAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // El error de la descarga NO va a `error`: ese hace un return temprano y deja
  // la pantalla en blanco. Un Excel que falla no debería borrar el mapeo.
  const [expErr, setExpErr] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  // filters
  const [filterSection, setFilterSection] = useState("ALL");
  const [filterStatus, setFilterStatus] = useState("ALL");
  const [filterText, setFilterText] = useState("");
  const [filterDept, setFilterDept] = useState("ALL");
  const [filterLine, setFilterLine] = useState("ALL");

  // modal
  const [modal, setModal] = useState<{
    open: boolean;
    initial?: Partial<AccountMappingCreate & { id: string }>;
    prefillDept?: string;
    prefillAccount?: string;
  }>({ open: false });

  async function reload() {
    try {
      const [l, m, u] = await Promise.all([
        getReportLines(),
        getAccountMappings(),
        getUnmappedAccounts(),
      ]);
      setLines(l);
      setMappings(m);
      setUnmapped(u);
    } catch (e) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { reload(); }, []);

  const sections = useMemo(() => ["ALL", ...new Set(mappings.map(m => m.report_section ?? ""))].filter(Boolean), [mappings]);

  /** Los departamentos que existen, «0210 · Departamento de Utility». */
  const departamentos = useMemo(() => {
    const vistos = new Map<string, string>();
    for (const m of mappings) {
      const cod = (m.dept_code ?? "").trim();
      if (!cod) continue;
      if (!vistos.has(cod)) vistos.set(cod, (m.source_department ?? "").trim());
    }
    return [...vistos.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [mappings]);

  /** Las `Línea P&L` que existen, con cuántas reglas tiene cada una: sin el
   *  conteo no se sabe si una línea está vacía o si el filtro está mal puesto. */
  const lineasPL = useMemo(() => {
    const cuenta = new Map<string, number>();
    for (const m of mappings) {
      const l = (m.report_line_code ?? "").trim();
      if (l) cuenta.set(l, (cuenta.get(l) ?? 0) + 1);
    }
    return [...cuenta.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [mappings]);

  const filtered = useMemo(() => mappings.filter(m => {
    if (filterSection !== "ALL" && m.report_section !== filterSection) return false;
    if (filterStatus !== "ALL" && m.active_status !== filterStatus) return false;
    if (filterDept !== "ALL" && (m.dept_code ?? "").trim() !== filterDept) return false;
    if (filterLine !== "ALL" && (m.report_line_code ?? "").trim() !== filterLine) return false;
    if (filterText.trim()) {
      // Cada palabra tiene que aparecer en ALGÚN campo: así «0210 electric»
      // encuentra la de Utilities y no las 300 que dicen «electric».
      //
      // Y se busca sobre el CÓDIGO de la línea además del nombre. Antes no, y
      // era el campo que la pantalla muestra: escribir «OPEX_ROOMS» —lo que se
      // ve en la columna «Línea P&L»— no encontraba nada.
      const campos = [
        m.account_code, m.account_name_example, m.report_line_code,
        m.report_line_name, m.report_section, m.source_department,
        m.dept_code, m.source_origin, m.notes,
      ].map(x => (x ?? "").toString().toLowerCase()).join(" ");
      return filterText.toLowerCase().split(/\s+/).filter(Boolean)
        .every(palabra => campos.includes(palabra));
    }
    return true;
  }), [mappings, filterSection, filterStatus, filterText, filterDept, filterLine]);

  async function handleSave(data: AccountMappingCreate) {
    if (modal.initial?.id) {
      await updateAccountMapping(modal.initial.id, data as Partial<AccountMappingRow>);
    } else {
      await createAccountMapping(data);
    }
    await reload();
  }

  async function toggleStatus(row: AccountMappingRow) {
    const next = row.active_status === "YES" ? "NO" : "YES";
    await updateAccountMapping(row.id, { active_status: next });
    setMappings(ms => ms.map(m => m.id === row.id ? { ...m, active_status: next } : m));
  }

  async function handleDelete(id: string) {
    if (!confirm(t("deleteConfirm"))) return;
    await deleteAccountMapping(id);
    setMappings(ms => ms.filter(m => m.id !== id));
  }

  /* ── Bajar a Excel ─────────────────────────────────────────────────────────
     Los dos tabs en el mismo libro, una hoja cada uno, con los filtros que el
     usuario tenga puestos en «Reglas».

     Son cuadros de TEXTO: los códigos van como cadena a propósito. Un `dept_code`
     "0110" convertido a número se convierte en 110 y deja de casar con nada —
     que es justo el error que esta pantalla existe para cazar. */
  async function bajarExcel() {
    setExporting(true); setExpErr(null);
    try {
      const filasReglas: FilaCuadro[] = filtered.map(m => ({
        label: m.active_status,
        valores: [
          m.report_section ?? "—",
          m.report_line_code ?? "—",
          m.report_line_name ?? m.report_line_code,
          // Sin código el P&L no sabe a qué departamento mandar la cuenta.
          m.dept_code ?? t("noCode"),
          m.source_department ?? "—",
          m.account_code,
          m.account_name_example ?? "—",
          m.financial_nature,
        ],
      }));

      const cuadros: Cuadro[] = [
        {
          titulo: t("xls.rulesTitle"),
          subtitulo: t("xls.rulesSub", { n: filtered.length, total: mappings.length })
            + (filterSection !== "ALL" ? t("xls.sectionSuffix", { s: filterSection }) : "")
            + (filterStatus !== "ALL" ? t("xls.statusSuffix", { s: filterStatus }) : "")
            + (filterDept !== "ALL" ? t("xls.deptSuffix", { s: filterDept }) : "")
            + (filterLine !== "ALL" ? t("xls.lineSuffix", { s: filterLine }) : "")
            + (filterText ? t("xls.searchSuffix", { q: filterText }) : ""),
          hoja: t("xls.rulesSheet"),
          columnas: [
            { label: tc("status"), ancho: 10, formato: "texto" },
            { label: tc("section"), ancho: 26, formato: "texto" },
            { label: t("plLine"), ancho: 22, formato: "texto" },
            { label: t("reportLineCol"), ancho: 34, formato: "texto" },
            { label: tc("deptCode"), ancho: 11, formato: "texto" },
            { label: t("deptGl"), ancho: 30, formato: "texto" },
            { label: tc("account"), ancho: 10, formato: "texto" },
            { label: t("accountNameCol"), ancho: 28, formato: "texto" },
            { label: t("nature"), ancho: 12, formato: "texto" },
          ],
          filas: filasReglas,
        },
        {
          titulo: t("xls.unmappedTitle"),
          subtitulo: t("xls.unmappedSub"),
          hoja: t("xls.unmappedSheet"),
          columnas: [
            { label: tc("department"), ancho: 14, formato: "texto" },
            { label: tc("account"), ancho: 12, formato: "texto" },
            { label: tc("name"), ancho: 38, formato: "texto" },
            { label: t("totalActivity"), ancho: 18, formato: "usd" },
          ],
          filas: unmapped.map(u => ({
            label: u.dept_code,
            valores: [u.account_code, u.account_name, u.total_activity],
          })),
        },
      ];

      await bajarCuadros("Account_Mapping", cuadros);
    } catch (e) {
      setExpErr(e instanceof Error ? e.message : t("xls.error"));
    } finally {
      setExporting(false);
    }
  }

  if (loading) return <div style={{ padding: 32, color: "var(--text-dim)" }}>{tc("loading")}</div>;
  if (error) return <div style={{ padding: 32, color: "var(--negative)" }}>{error}</div>;

  return (
    <div className="pag pag-ancha" style={{ padding: "28px 28px 64px" }}>
      <IrA />
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Admin · Account Mapping</h1>
          <p style={{ fontSize: 12, color: "var(--text-dim)" }}>
            {t("stats", {
              total: mappings.length,
              activas: mappings.filter(m => m.active_status === "YES").length,
              revision: mappings.filter(m => m.active_status === "REVIEW").length,
              sinMapear: unmapped.length,
            })}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {expErr && <span style={{ fontSize: 12, color: "var(--negative)", maxWidth: 320 }}>{expErr}</span>}
          <button
            onClick={bajarExcel}
            disabled={exporting}
            title={t("xls.hint")}
            style={{ ...BTN, background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
            {exporting ? t("generating") : "⬇ Excel"}
          </button>
          <button style={BTN_PRIMARY} onClick={() => setModal({ open: true })}>{t("newRule")}</button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: "1px solid var(--border)" }}>
        {(["rules", "unmapped"] as const).map(k => (
          <button key={k} onClick={() => setTab(k)} style={{
            padding: "8px 18px", fontSize: 13, fontWeight: tab === k ? 700 : 400,
            borderRadius: "6px 6px 0 0", cursor: "pointer",
            background: tab === k ? "var(--brand)" : "transparent",
            color: tab === k ? "#fff" : "var(--text-dim)",
            border: "none",
          }}>
            {k === "rules" ? t("tabRules", { n: mappings.length }) : t("tabUnmapped", { n: unmapped.length })}
          </button>
        ))}
      </div>

      {/* ── Tab: Rules ── */}
      {tab === "rules" && (
        <>
          {/* Filters */}
          <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
            <input
              placeholder={t("searchPlaceholder")}
              title={t("searchTitle")}
              value={filterText}
              onChange={e => setFilterText(e.target.value)}
              style={{ ...INPUT, width: 300 }}
            />
            <select value={filterDept} onChange={e => setFilterDept(e.target.value)}
                    style={{ ...SELECT_S, width: 250 }}>
              <option value="ALL">{t("allDepts")}</option>
              {departamentos.map(([cod, nom]) => (
                <option key={cod} value={cod}>{cod}{nom ? ` · ${nom}` : ""}</option>
              ))}
            </select>
            <select value={filterLine} onChange={e => setFilterLine(e.target.value)}
                    style={{ ...SELECT_S, width: 230 }}>
              <option value="ALL">{t("allLines")}</option>
              {lineasPL.map(([l, n]) => (
                <option key={l} value={l}>{l} ({n})</option>
              ))}
            </select>
            <select value={filterSection} onChange={e => setFilterSection(e.target.value)} style={{ ...SELECT_S, width: 220 }}>
              {sections.map(s => <option key={s} value={s}>{s === "ALL" ? t("allSections") : s}</option>)}
            </select>
            <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={{ ...SELECT_S, width: 140 }}>
              <option value="ALL">{t("allStatuses")}</option>
              <option value="YES">YES</option>
              <option value="REVIEW">REVIEW</option>
              <option value="NO">NO</option>
            </select>
            {(filterText || filterDept !== "ALL" || filterLine !== "ALL"
              || filterSection !== "ALL" || filterStatus !== "ALL") && (
              <button onClick={() => { setFilterText(""); setFilterDept("ALL");
                                       setFilterLine("ALL"); setFilterSection("ALL");
                                       setFilterStatus("ALL"); }}
                      style={{ ...SELECT_S, width: "auto", padding: "6px 12px", cursor: "pointer" }}>
                {t("clearFilters")}
              </button>
            )}
            <span style={{ fontSize: 12, color: "var(--text-dim)", marginLeft: "auto" }}>
              {t("ofTotal", { n: filtered.length, total: mappings.length })}
            </span>
          </div>

          {/* Table */}
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)" }}>
                  {[tc("status"), tc("section"), t("plLine"), t("reportLineCol"),
                    t("deptGlCol"), tc("account"), t("accountNameCol"), t("nature"),
                    t("actions")].map(h => (
                    <th key={h} style={{ textAlign: "left", padding: "6px 10px", fontSize: 11, color: "var(--text-dim)", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(row => (
                  <tr key={row.id} style={{ borderBottom: "1px solid var(--border)", opacity: row.active_status === "NO" ? 0.45 : 1 }}>
                    <td style={{ padding: "5px 10px" }}><Badge status={row.active_status} /></td>
                    <td style={{ padding: "5px 10px", color: "var(--text-dim)", fontSize: 11, whiteSpace: "nowrap" }}>{row.report_section ?? "—"}</td>
                    {/* El CODIGO de la linea, no solo su nombre (owner,
                        2026-08-14). Dos lineas distintas pueden llamarse igual
                        —«F&B» era el ingreso y tambien el gasto— y revisar el
                        mapeo por el nombre no alcanza para saber a donde va la
                        cuenta. El codigo es lo que rutea. */}
                    <td style={{ padding: "5px 10px", fontFamily: "monospace", fontWeight: 700,
                                 whiteSpace: "nowrap", color: "var(--brand)" }}>
                      {row.report_line_code ?? "—"}
                    </td>
                    <td style={{ padding: "5px 10px", fontWeight: 600, whiteSpace: "nowrap" }}>{row.report_line_name ?? row.report_line_code}</td>
                    {/* El departamento con su código, igual que la cuenta. No es
                        simetría: el código es lo que RUTEA el P&L y el nombre es
                        la etiqueta, así que una regla sin código manda la cuenta
                        a la línea del primer departamento. Verlo en la tabla es
                        la forma de cacharlo. */}
                    <td style={{ padding: "5px 10px", color: "var(--text-dim)", maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {row.dept_code
                        ? <span style={{ fontFamily: "monospace", fontWeight: 700, color: "var(--text-primary)", marginRight: 8 }}>{row.dept_code}</span>
                        : <span title={t("noCodeTitle")}
                                style={{ fontFamily: "monospace", fontWeight: 700, color: "var(--negative)", marginRight: 8 }}>{t("noCode")}</span>}
                      {row.source_department ?? "—"}
                    </td>
                    <td style={{ padding: "5px 10px", fontFamily: "monospace", fontWeight: 700 }}>{row.account_code}</td>
                    <td style={{ padding: "5px 10px", color: "var(--text-dim)", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.account_name_example ?? "—"}</td>
                    <td style={{ padding: "5px 10px" }}>
                      <span style={{ fontSize: 11, color: row.financial_nature === "Revenue" ? "var(--positive)" : "var(--text-dim)" }}>
                        {row.financial_nature}
                      </span>
                    </td>
                    <td style={{ padding: "5px 10px", whiteSpace: "nowrap" }}>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button style={{ ...BTN, padding: "3px 10px", fontSize: 11 }}
                          onClick={() => setModal({ open: true, initial: { ...row, id: row.id } as Partial<AccountMappingCreate & { id: string }> })}>
                          {t("edit")}
                        </button>
                        <button style={{ ...BTN, padding: "3px 10px", fontSize: 11 }}
                          onClick={() => toggleStatus(row)}>
                          {row.active_status === "YES" ? t("deactivate") : t("activate")}
                        </button>
                        <button style={{ ...BTN_DANGER, padding: "3px 10px", fontSize: 11 }}
                          onClick={() => handleDelete(row.id)}>
                          ✕
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={8} style={{ padding: 24, textAlign: "center", color: "var(--text-dim)" }}>{tc("noResults")}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Tab: Unmapped ── */}
      {tab === "unmapped" && (
        <div>
          <p style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 16 }}>
            {t("unmappedIntro")}
          </p>
          {unmapped.length === 0
            ? <div style={{ padding: 32, textAlign: "center", color: "var(--positive)", fontWeight: 700 }}>{t("allMapped")}</div>
            : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid var(--border)" }}>
                    {[tc("department"), tc("account"), tc("name"), t("totalActivity"), ""].map(h => (
                      <th key={h} style={{ textAlign: "left", padding: "6px 10px", fontSize: 11, color: "var(--text-dim)" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {unmapped.map((u, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "5px 10px", color: "var(--text-dim)" }}>{u.dept_code}</td>
                      <td style={{ padding: "5px 10px", fontFamily: "monospace", fontWeight: 700 }}>{u.account_code}</td>
                      <td style={{ padding: "5px 10px" }}>{u.account_name}</td>
                      <td style={{ padding: "5px 10px", textAlign: "right", fontFamily: "monospace", color: u.total_activity < 0 ? "var(--negative)" : "var(--text)" }}>
                        {u.total_activity.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                      </td>
                      <td style={{ padding: "5px 10px" }}>
                        <button style={{ ...BTN_PRIMARY, padding: "3px 12px", fontSize: 11 }}
                          onClick={() => setModal({ open: true, prefillDept: u.dept_code, prefillAccount: u.account_code })}>
                          {t("mapBtn")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>
      )}

      {/* Modal */}
      {modal.open && (
        <MappingModal
          lines={lines}
          initial={modal.initial}
          prefillDept={modal.prefillDept}
          prefillAccount={modal.prefillAccount}
          onSave={handleSave}
          onClose={() => setModal({ open: false })}
        />
      )}
    </div>
  );
}
