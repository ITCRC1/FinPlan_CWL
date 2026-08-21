"use client";
import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import {
  getScenarios, getAssignments, setAssignee, setSectionStatus, setSectionLock,
  getValidations, listUsers, getStoredUser,
  type Scenario, type AssignmentRow, type AuthUser, type Validation,
} from "@/lib/api";
import { CWL_DEPTS } from "@/lib/cwl-depts";
import { HOTEL_ID } from "@/lib/hotel";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const OPS = CWL_DEPTS.filter(d => d.dept_code !== "0191");
const REV = CWL_DEPTS.filter(d => ["0110","0120","0140","0150","0151","0152","0155","0156","0161"].includes(d.dept_code));
// Los rubros de abajo-GOP no vienen del catálogo de departamentos: son de la
// pantalla, así que su rótulo sale del catálogo de textos (`board.nonop.*`).
const NONOP = [
  { dept_code: "mgmt", lk: "nonop.mgmt" },
  { dept_code: "insurance", lk: "nonop.insurance" },
  { dept_code: "capital", lk: "nonop.capital" },
  { dept_code: "financial", lk: "nonop.financial" },
  { dept_code: "depreciation", lk: "nonop.depreciation" },
];
// `label` viene de la base (nombre del departamento) y no se traduce; `lk` es
// clave del catálogo, para lo que sí es texto de la pantalla.
const STRUCT: { section: string; lk: string; items: { ref: string; label?: string; lk?: string }[] }[] = [
  { section: "master", lk: "sec.master", items: [{ ref: "", lk: "sec.general" }] },
  { section: "revenue", lk: "sec.revenue", items: REV.map(d => ({ ref: d.dept_code, label: d.dept_name })) },
  { section: "costs", lk: "sec.costs", items: OPS.map(d => ({ ref: d.dept_code, label: d.dept_name })) },
  { section: "payroll", lk: "sec.payroll", items: OPS.map(d => ({ ref: d.dept_code, label: d.dept_name })) },
  { section: "opex", lk: "sec.opex", items: OPS.map(d => ({ ref: d.dept_code, label: d.dept_name })) },
  { section: "nonop", lk: "sec.nonop", items: NONOP.map(d => ({ ref: d.dept_code, lk: d.lk })) },
];

function statusStyle(s: string): React.CSSProperties {
  const m: Record<string, [string, string]> = {
    pending: ["var(--text-secondary)", "var(--bg-elevated, var(--bg-surface))"],
    in_progress: ["var(--brand)", "rgba(41,98,255,0.12)"],
    in_review: ["var(--accent-amber, #856404)", "rgba(133,100,4,0.14)"],
    approved: ["var(--accent-green, #1A7F4B)", "rgba(26,127,75,0.14)"],
  };
  const [c, b] = m[s] ?? m.pending;
  return { fontSize: 10, padding: "2px 7px", borderRadius: 5, color: c, background: b, whiteSpace: "nowrap" };
}
const sbtn: React.CSSProperties = {
  padding: "3px 8px", fontSize: 11, borderRadius: 4, cursor: "pointer",
  background: "var(--bg-elevated, var(--bg-surface))", color: "var(--text-secondary)", border: "1px solid var(--border-medium)",
};

export default function BoardPage() {
  const tc = useTranslations("common");
  const t = useTranslations("board");
  // El rótulo sale del catálogo si es texto de la pantalla; si viene de la base
  // (nombre del departamento) se muestra tal cual.
  const lbl = (x: { label?: string; lk?: string }) => (x.lk ? t(x.lk) : x.label ?? "");
  const statusLabel = (st: string) => t(`status.${st}`);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // El tablero sigue el presupuesto que el equipo esta armando, no el ultimo
  // creado; y se acuerda de cual se estaba mirando.
  const [scenarioId, setScenarioId] = useEscenarioDe("board:budget", scenarios, "budget", undefined, true);
  const [rows, setRows] = useState<Record<string, AssignmentRow>>({});  // key section|ref
  const [vals, setVals] = useState<Validation[]>([]);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const me = typeof window !== "undefined" ? getStoredUser() : null;
  const isAdmin = me?.role === "admin";

  useEffect(() => {
    (async () => {
      try {
        // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
        if (me?.role === "admin") { try { setUsers(await listUsers()); } catch { /* noop */ } }
      } catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
      finally { setLoading(false); }
    })();
  }, []); // eslint-disable-line

  const load = useCallback(async (sid: string) => {
    setLoading(true); setError(null);
    try {
      const [r, v] = await Promise.all([getAssignments(sid), getValidations(sid).catch(() => null)]);
      const map: Record<string, AssignmentRow> = {};
      for (const a of r.assignments) map[`${a.section}|${a.ref}`] = a;
      setRows(map);
      setVals(v?.validations ?? []);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try { await fn(); await load(scenarioId); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : "Error"); }
  }
  const get = (section: string, ref: string): AssignmentRow | null => rows[`${section}|${ref}`] ?? null;

  const valsFor = (section: string) => vals.filter(v => v.section === section && v.level !== "ok");
  const vColor = (lvl: string) => lvl === "error" ? "var(--accent-red, #C0392B)" : "var(--accent-amber, #856404)";
  const nWarn = vals.filter(v => v.level === "warn").length;
  const nErr = vals.filter(v => v.level === "error").length;

  const totalItems = STRUCT.reduce((s, g) => s + g.items.length, 0);
  const totalApproved = STRUCT.reduce((s, g) => s + g.items.filter(it => get(g.section, it.ref)?.status === "approved").length, 0);
  const pct = totalItems ? Math.round(totalApproved / totalItems * 100) : 0;

  return (
    <div className="pag pag-media" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 220 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}</option>)}
        </select>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 12 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b> })}{" "}
        {isAdmin ? t("introAdmin") : t("introCollab")}
      </p>

      <div style={{ height: 8, borderRadius: 999, background: "var(--bg-surface)", overflow: "hidden", marginBottom: 6 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: totalApproved === totalItems ? "var(--accent-green, #1A7F4B)" : "var(--brand)" }} />
      </div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>
        {t("deptsApproved", { n: totalApproved, total: totalItems })}
        {(nErr > 0 || nWarn > 0) && (
          <span style={{ marginLeft: 10 }}>
            {nErr > 0 && <span style={{ color: "var(--accent-red, #C0392B)" }}>{t("errors", { n: nErr })} </span>}
            {nWarn > 0 && <span style={{ color: "var(--accent-amber, #856404)" }}>{t("openValidations", { n: nWarn })}</span>}
          </span>
        )}
      </div>

      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {STRUCT.map(g => {
            const appr = g.items.filter(it => get(g.section, it.ref)?.status === "approved").length;
            const sv = valsFor(g.section);
            const isOpen = open[g.section] ?? false;
            return (
              <div key={g.section} style={{ border: "1px solid var(--border-medium)", borderRadius: 8, overflow: "hidden" }}>
                <div onClick={() => setOpen(o => ({ ...o, [g.section]: !isOpen }))}
                  style={{ display: "flex", alignItems: "center", gap: 8, padding: "11px 14px", cursor: "pointer", background: "var(--bg-surface)" }}>
                  <span style={{ color: "var(--text-secondary)", fontSize: 12, width: 14 }}>{isOpen ? "▾" : "▸"}</span>
                  <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", flex: 1 }}>{t(g.lk)}</span>
                  {sv.length > 0 && (
                    <span style={{ fontSize: 11, color: vColor(sv.some(v => v.level === "error") ? "error" : "warn") }}>
                      ⚠ {sv.length}
                    </span>
                  )}
                  <span style={{ fontSize: 12, color: appr === g.items.length ? "var(--accent-green, #1A7F4B)" : "var(--text-secondary)" }}>
                    {t("approvedOf", { n: appr, total: g.items.length })}
                  </span>
                </div>

                {isOpen && (
                  <div>
                    {sv.length > 0 && (
                      <div style={{ padding: "8px 14px 4px 30px", borderTop: "1px solid var(--border-medium)" }}>
                        {sv.map((v, i) => (
                          <div key={i} style={{ fontSize: 12, color: vColor(v.level), marginBottom: 2 }}>
                            {v.level === "error" ? "⛔" : "⚠"} {v.message}
                          </div>
                        ))}
                      </div>
                    )}
                    {g.items.map(it => {
                      const a = get(g.section, it.ref);
                      const status = a?.status ?? "pending";
                      const locked = a?.locked ?? false;
                      const mine = !!me && a?.assignee?.id === me.id;
                      const canMove = (isAdmin || mine) && (!locked || isAdmin);
                      return (
                        <div key={it.ref} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
                          padding: "8px 14px 8px 30px", borderTop: "1px solid var(--border-medium)" }}>
                          <span style={{ fontSize: 13, color: "var(--text-primary)", flex: 1, minWidth: 130 }}>
                            {lbl(it)} {locked && <span title={t("lockedTitle")}>🔒</span>}
                          </span>
                          {isAdmin ? (
                            <select value={a?.assignee?.id ?? ""} className="fin-input" style={{ fontSize: 11, minWidth: 150, padding: "2px 4px" }}
                              onChange={e => act(() => setAssignee(scenarioId, g.section, e.target.value || null, it.ref))}>
                              <option value="">{t("unassignedOption")}</option>
                              {users.map(u => <option key={u.id} value={u.id}>{u.name || u.email}</option>)}
                            </select>
                          ) : (
                            <span style={{ fontSize: 11, color: "var(--text-secondary)", minWidth: 120 }}>{a?.assignee?.name ?? t("unassigned")}{mine && t("youSuffix")}</span>
                          )}
                          <span style={statusStyle(status)}>{statusLabel(status)}</span>
                          <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                            {canMove && status === "pending" && <button style={sbtn} onClick={() => act(() => setSectionStatus(scenarioId, g.section, "in_progress", it.ref))}>{t("start")}</button>}
                            {canMove && status === "in_progress" && <button style={sbtn} onClick={() => act(() => setSectionStatus(scenarioId, g.section, "in_review", it.ref))}>{t("toReview")}</button>}
                            {isAdmin && status === "in_review" && <>
                              <button style={{ ...sbtn, color: "var(--accent-green, #1A7F4B)" }} onClick={() => act(() => setSectionStatus(scenarioId, g.section, "approved", it.ref))}>{t("approve")}</button>
                              <button style={sbtn} onClick={() => act(() => setSectionStatus(scenarioId, g.section, "in_progress", it.ref))}>{t("sendBack")}</button>
                            </>}
                            {isAdmin && status === "approved" && <button style={sbtn} onClick={() => act(() => setSectionStatus(scenarioId, g.section, "in_progress", it.ref))}>{t("reopen")}</button>}
                            {isAdmin && <button style={{ ...sbtn, color: locked ? "var(--accent-amber, #856404)" : "var(--text-secondary)" }} onClick={() => act(() => setSectionLock(scenarioId, g.section, !locked, it.ref))}>{locked ? t("open") : t("lock")}</button>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
