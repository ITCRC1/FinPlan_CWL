"use client";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { ordenarEscenarios } from "@/lib/ordenEscenarios";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import {
  getScenarios, getSalaryPositions, getSalaryConfig, saveSalaryConfig, getReasignacionesSalarioSeed,
  type Scenario, type SalaryDept, type SalaryPosition, type SalaryRule, type ReasignacionSalario,
} from "@/lib/api";
import { recalcularYContar } from "@/lib/recalcular";
import IrA from "@/components/IrA";

// Los meses salen de `months.short` del catálogo; esto queda de respaldo.
const MESES_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const m0 = (v: number) => { if (!v) return "–"; const s = "$" + Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 }); return v < 0 ? `(${s})` : s; };
const Z = () => Array(12).fill(0) as number[];
const GOLD = "#c8a24a";

export default function SalaryAllocationPage() {
  const tc = useTranslations("common");
  const t = useTranslations("salaryAlloc");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // El selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se
  // eligio abre con el preferido del owner. Antes se tomaba el primero de la
  // lista ordenada, asi que cualquier cambio de orden le cambiaba el escenario
  // a la pantalla.
  const [scnId, setScnId] = useEscenarioDe("allocations/salary:budget", scenarios, "budget", undefined, true);
  const [depts, setDepts] = useState<SalaryDept[]>([]);
  const [positions, setPositions] = useState<SalaryPosition[]>([]);
  const [ccssRate, setCcssRate] = useState(0.2683);
  const [aguDiv, setAguDiv] = useState(12);
  const [rules, setRules] = useState<SalaryRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // Ordenado como en Tipo de Cambio: el año en curso primero, para leer
        // la lista. Cuál queda elegido lo decide `useEscenarioDe`.
        setScenarios(ordenarEscenarios(await getScenarios(HOTEL_ID)));
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); } finally { setLoading(false); }
    })();
  }, []);

  async function load(id: string) {
    if (!id) return; setLoading(true); setError(null); setMsg(null);
    try {
      const [pos, cfg] = await Promise.all([getSalaryPositions(id), getSalaryConfig(id)]);
      setDepts(pos.depts); setPositions(pos.positions); setCcssRate(pos.ccss_rate); setAguDiv(pos.aguinaldo_divisor);
      setRules(cfg.map(r => ({ ...r, salary_override: r.salary_override ?? Z(), dummy_monthly: r.dummy_monthly ?? Z() })));
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); } finally { setLoading(false); }
  }
  useEffect(() => { if (scnId) load(scnId); /* eslint-disable-next-line */ }, [scnId]);

  const deptName = useMemo(() => { const m: Record<string, string> = {}; depts.forEach(d => m[d.dept_code] = d.dept_name); return m; }, [depts]);
  const fteOf = useMemo(() => { const m: Record<string, number[]> = {}; depts.forEach(d => m[d.dept_code] = d.fte); return m; }, [depts]);

  function calcRule(r: SalaryRule) {
    const auto = Z();
    positions.filter(p => p.dept_code === r.source_dept && p.position_code === r.position_code).forEach(p => p.sw.forEach((v, i) => auto[i] += v));
    const ov = r.salary_override ?? Z();
    const sw = auto.map((v, i) => ov[i] ? ov[i] : v);
    const ccss = sw.map(v => v * ccssRate);
    const agu = sw.map(v => aguDiv ? v / aguDiv : 0);
    const caf = sw.map(v => v * (r.cafeteria_pct || 0));
    const dummy = r.dummy_monthly ?? Z();
    const total = sw.map((v, i) => v + ccss[i] + agu[i] + caf[i] + (dummy[i] || 0));
    const reassign = total.map(v => v * (r.portion_pct || 0));
    const dist: Record<string, number[]> = {}; r.target_depts.forEach(t => dist[t] = Z());
    for (let m = 0; m < 12; m++) {
      const sumF = r.target_depts.reduce((a, t) => a + (fteOf[t]?.[m] || 0), 0);
      if (sumF > 0) r.target_depts.forEach(t => { dist[t][m] = reassign[m] * ((fteOf[t]?.[m] || 0) / sumF); });
    }
    return { sw, ccss, agu, caf, dummy, total, reassign, dist };
  }

  // cafeteria 20%: el depto carga un costo real de alimentacion por empleado
  // (cuenta 6025), asi que viaja con la persona cuando el salario se reasigna.
  const blank = (): SalaryRule => ({ source_dept: "", position_code: "", position_name: "", portion_pct: 1, cafeteria_pct: 0.20, salary_override: Z(), dummy_monthly: Z(), target_depts: [], account: "6000", active: true });
  function addRule() { setRules(r => [...r, blank()]); }
  function setRule(i: number, patch: Partial<SalaryRule>) { setRules(r => r.map((x, j) => j === i ? { ...x, ...patch } : x)); }
  function setSource(i: number, key: string) { const [dept, code] = key.split("|"); const p = positions.find(x => x.dept_code === dept && x.position_code === code); setRule(i, { source_dept: dept, position_code: code, position_name: p?.position_name ?? "" }); }
  function setVec(i: number, field: "salary_override" | "dummy_monthly", mi: number, v: string) { const val = parseFloat(String(v).replace(/[$,\s]/g, "")) || 0; setRules(r => r.map((x, j) => j === i ? { ...x, [field]: (x[field] ?? Z()).map((d, k) => k === mi ? val : d) } : x)); }
  function fillYear(i: number, field: "salary_override" | "dummy_monthly") { setRules(r => r.map((x, j) => { if (j !== i) return x; const base = (x[field] ?? Z())[0]; return { ...x, [field]: Z().map(() => base) }; })); }

  /**
   * Las reasignaciones que hace la operación: UN renglón por destino.
   *
   * YA NO ESTÁN ESCRITAS ACÁ. Eran nueve renglones fijos dentro de esta
   * pantalla —ROOM ATTENDANT del 0113, el guía de aventura del 0150, el chofer
   * del 0152— o sea puestos y departamentos de Corcovado, viajando en el
   * bundle. Otra propiedad abría este botón y le proponía la operación de un
   * hotel que no es el suyo. Ahora vienen de
   * `backend/app/seed_data/<HOTEL_ID>/reasignaciones_salario.json`.
   *
   * Por PUESTO y no por código: antes esto listaba códigos (508, 598, 604…) que
   * eran los de la planilla 2026, y al cargar el head count 2027 pasaron a
   * 0113-04, 0150-02, 0152-01… — las cinco reglas quedaron apuntando al vacío
   * sin que nada lo dijera. `legacy` es el código viejo, de respaldo para abrir
   * escenarios anteriores.
   *
   * `fte` es cuántos FTE del puesto se mueven a ESE destino: 2 camareras a la
   * cafetería; el guía de aventura mitad a Compras y mitad a Transporte. Antes
   * un renglón traía varios destinos y el motor los repartía solo por el FTE
   * de cada uno — el owner no podía ver cuánto le tocaba a cada departamento.
   */
  const [plantilla, setPlantilla] = useState<ReasignacionSalario[]>([]);
  useEffect(() => {
    (async () => {
      try { setPlantilla((await getReasignacionesSalarioSeed()).reasignaciones ?? []); }
      catch { /* sin semilla: el botón lo dice en vez de proponer la de otro */ }
    })();
  }, []);

  function suggestRules() {
    if (!plantilla.length) {
      setError(t("noTemplate"));
      return;
    }
    const ds = new Set(depts.map(d => d.dept_code));
    const built: SalaryRule[] = [];
    const noHallados: string[] = [];   // puestos que la planilla ya no tiene

    for (const pl of plantilla) {
      const delDepto = positions.filter(x => x.dept_code === pl.source);
      const nom = (s: string) => (s || "").trim().toUpperCase();
      // Por nombre exacto; si no, por prefijo (el chofer viene como
      // "Driver-PRADOS-INSUMOS-DRAKE"); de último, el código viejo.
      const p = delDepto.find(x => nom(x.position_name) === pl.name)
        ?? delDepto.find(x => nom(x.position_name).startsWith(pl.name))
        ?? delDepto.find(x => x.position_code === pl.legacy);
      if (!p) { if (!noHallados.includes(pl.name)) noHallados.push(`${pl.source} ${pl.name}`); continue; }
      built.push({
        ...blank(), source_dept: pl.source, position_code: p.position_code,
        position_name: p.position_name, portion_pct: pl.fte,
        target_depts: ds.has(pl.target) ? [pl.target] : [],
      });
    }
    if (!built.length) { setError(t("noTemplatePosition")); return; }
    setRules(built);
    const falta = noHallados.length ? t("notFound", { lista: noHallados.join(", ") }) : "";
    setMsg(t("rulesBuilt", { n: built.length, falta }));
  }

  /** Por qué una regla no está moviendo plata. Vacío = está trabajando. */
  function porQueNoMueve(r: SalaryRule): string | null {
    if (!r.source_dept || !r.position_code) return t("whyPickPosition");
    const hay = positions.some(p => p.dept_code === r.source_dept && p.position_code === r.position_code);
    const ov = r.salary_override ?? [];
    if (!hay && !ov.some(v => v)) {
      return t("whyPositionGone", { pos: r.position_code, dept: r.source_dept });
    }
    if (!r.target_depts.length) return t("whyNoTarget");
    if (r.target_depts.length > 1) {
      return t("whyManyTargets", { n: r.target_depts.length, lista: r.target_depts.join(", ") });
    }
    const conFte = r.target_depts.some(t => (fteOf[t] ?? []).some(v => v > 0));
    if (!conFte) return t("whyNoFte");
    if (!hay) return t("whyManualSalary", { pos: r.position_code });
    return null;
  }
  async function save() { if (!scnId) return; setSaving(true); setMsg(null); setError(null); try { await saveSalaryConfig(scnId, rules.filter(r => r.source_dept && r.position_code)); setMsg(t("saved")); } catch (e) { setError(e instanceof Error ? e.message : "Error"); } finally { setSaving(false); } }
  async function apply() { if (!scnId) return; setApplying(true); setMsg(null); setError(null); try { await saveSalaryConfig(scnId, rules.filter(r => r.source_dept && r.position_code)); setMsg(await recalcularYContar(scnId, t("applied"))); } catch (e) { setError(e instanceof Error ? e.message : "Error"); } finally { setApplying(false); } }

  /**
   * Todas las tarjetas en UNA hoja: cada regla abre con una banda de sección y
   * debajo van sus mismas filas de 12 meses. Una hoja por regla obligaría a
   * saltar entre nueve pestañas para ver un reparto que se lee de corrido.
   *
   * El aviso de «esta regla no está reasignando nada» viaja en la banda: es
   * justo el dato que explica por qué las filas de abajo dan cero.
   */
  async function bajarExcel() {
    const VACIA = Array(13).fill(null) as (number | null)[];
    const tot = (v: number[]) => v.reduce((a, b) => a + b, 0);
    const filas: FilaCuadro[] = [];

    for (const r of rules) {
      const motivo = porQueNoMueve(r);
      filas.push({
        label: [`${r.source_dept} ${deptName[r.source_dept] ?? ""}`.trim(),
          `${r.position_code} ${r.position_name}`.trim()].filter(Boolean).join(" · ")
          + (motivo ? ` — ⚠ ${motivo}` : ""),
        es_total: true, valores: VACIA,
      });
      if (!r.source_dept || !r.position_code) continue;   // en pantalla tampoco hay tabla
      const c = calcRule(r);
      const fila = (label: string, vals: number[], opts?: { total?: boolean; nivel?: number }) =>
        filas.push({ label, nivel: opts?.nivel ?? 1, es_total: !!opts?.total, valores: [...vals, tot(vals)] });

      fila(t("rowSalary"), c.sw);
      fila(t("rowCcss", { pct: (ccssRate * 100).toFixed(2) }), c.ccss);
      fila(t("rowAguinaldo", { div: aguDiv }), c.agu);
      fila(t("rowCafeteria", { pct: ((r.cafeteria_pct || 0) * 100).toFixed(0) }), c.caf);
      fila(t("rowDummy"), c.dummy);
      fila(t("rowReassigned", { fte: r.portion_pct.toFixed(2) }), c.reassign, { total: true });
      for (const d of r.target_depts) fila(`${t("debitRow")} ${d} ${deptName[d] ?? ""}`.trim(), c.dist[d] ?? Z(), { nivel: 2 });
      // El crédito sale en negativo, igual que en pantalla: es lo que el
      // departamento de origen deja de cargar.
      fila(`${t("creditRow")} ${r.source_dept} ${deptName[r.source_dept] ?? ""}`.trim(), c.reassign.map(v => -v), { nivel: 2 });
    }

    const s = scenarios.find(x => x.id === scnId);
    try {
      await bajarCuadros("Salary_Allocation", [{
        titulo: t("xlsTitle"),
        subtitulo: s ? `${s.type} ${s.year}${s.version && !["actual", "from-xlsx"].includes(s.version) ? ` · ${s.version}` : ""}` : undefined,
        hoja: "Salary Allocation",
        columnas: [
          { label: tc("concept"), ancho: 46, formato: "texto" },
          ...MONTHS.map(mo => ({ label: mo, ancho: 12, formato: "usd" as const })),
          { label: tc("total"), ancho: 15, formato: "usd" as const },
        ],
        filas,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "6px 10px", fontSize: 13 };
  const tdN: React.CSSProperties = { padding: "8px 10px", textAlign: "right", fontSize: 12.5, whiteSpace: "nowrap" };
  // Encabezado de las tablas de cada tarjeta. `position` la fija cada celda:
  // globals.css pega el thead de TODA tabla al viewport y aca estorba.
  const thFijo: React.CSSProperties = { padding: "11px 10px", whiteSpace: "nowrap" };
  const btn = (bg: string, fg: string): React.CSSProperties => ({ ...sel, fontWeight: 700, cursor: "pointer", background: bg, color: fg, borderColor: bg });
  const inp: React.CSSProperties = { width: 66, textAlign: "right", background: "var(--bg-input)", color: "var(--text-primary)", border: `1px solid ${GOLD}66`, borderRadius: 4, padding: "5px 6px", fontSize: 12 };

  return (
    <div className="pag pag-media" style={{ padding: "20px 16px 44px" }}>
      <IrA esc={scnId} />
      <h1 style={{ fontSize: 28, fontWeight: 800, textAlign: "center", margin: "0 0 4px" }}>
        <span style={{ color: "var(--text-primary)" }}>Salary </span><span style={{ color: "var(--brand)" }}>Allocation</span>
      </h1>
      <p style={{ textAlign: "center", color: "var(--text-secondary)", fontSize: 12.5, marginTop: 0, maxWidth: 920, margin: "0 auto 4px" }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b>, auto: t("autoByFte") })}
      </p>

      <div style={{ display: "flex", gap: 10, justifyContent: "center", alignItems: "center", margin: "14px 0", flexWrap: "wrap" }}>
        <select value={scnId} onChange={e => setScnId(e.target.value)} style={sel}>
          {scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{s.type} {s.year}{s.version && !["actual", "from-xlsx"].includes(s.version) ? ` · ${s.version}` : ""}</option>)}
        </select>
        <button onClick={suggestRules} disabled={!positions.length} style={btn("var(--bg-elevated)", GOLD)}>{t("suggestRules")}</button>
        <button onClick={addRule} disabled={!positions.length} style={btn("var(--bg-input)", "var(--brand)")}>{t("add")}</button>
        <button onClick={save} disabled={saving} style={btn("var(--brand)", "#fff")}>{saving ? "…" : t("saveBtn")}</button>
        <button onClick={apply} disabled={applying} style={btn("var(--positive)", "#fff")}>{applying ? t("applying") : t("apply")}</button>
        <button onClick={bajarExcel} disabled={!rules.length} title={t("excelTitle")}
          style={{ ...btn("transparent", "var(--positive)"), borderColor: "var(--positive)" }}>⬇ Excel</button>
      </div>

      {msg && <div style={{ color: "var(--positive)", fontSize: 13, textAlign: "center", marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--negative)", fontSize: 13, textAlign: "center", marginBottom: 8 }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", textAlign: "center" }}>{tc("loading")}</div>}
      {!loading && positions.length === 0 && <div style={{ textAlign: "center", color: "var(--text-disabled)", fontSize: 13 }}>{t("noPayroll")}</div>}
      {!loading && positions.length > 0 && rules.length === 0 && <div style={{ textAlign: "center", color: "var(--text-secondary)", fontSize: 14, padding: 20 }}>{t.rich("startHint", { b: (c: React.ReactNode) => <b>{c}</b>, sugerir: t("suggestRules"), agregar: t("add") })}</div>}

      {/* ── Una TARJETA por posición: config arriba + tabla 12 meses debajo ── */}
      {!loading && rules.map((r, i) => {
        const c = calcRule(r);
        const rowsDef: { label: string; vals: number[]; bold?: boolean; color?: string; field?: "salary_override" | "dummy_monthly" }[] = [
          { label: t("rowSalary"), vals: c.sw, field: "salary_override", color: GOLD },
          { label: t("rowCcss", { pct: (ccssRate * 100).toFixed(2) }), vals: c.ccss },
          { label: t("rowAguinaldo", { div: aguDiv }), vals: c.agu },
          { label: t("rowCafeteria", { pct: ((r.cafeteria_pct || 0) * 100).toFixed(0) }), vals: c.caf },
          { label: t("rowDummy"), vals: c.dummy, field: "dummy_monthly", color: GOLD },
          { label: t("rowReassigned", { fte: r.portion_pct.toFixed(2) }), vals: c.reassign, bold: true },
        ];
        return (
          <div key={i} style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, marginBottom: 26 }}>
            {/* config header */}
            <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border-medium)", display: "flex", gap: 14, rowGap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <select value={r.source_dept && r.position_code ? `${r.source_dept}|${r.position_code}` : ""} onChange={e => setSource(i, e.target.value)} style={{ ...sel, minWidth: 300, maxWidth: 420, flex: "1 1 300px" }}>
                <option value="">{t("pickPosition")}</option>
                {positions.map(p => <option key={`${p.dept_code}|${p.position_code}`} value={`${p.dept_code}|${p.position_code}`} style={{ background: "var(--bg-input)" }}>{p.dept_code} {deptName[p.dept_code]} · {p.position_code} {p.position_name}</option>)}
              </select>
              <label style={{ fontSize: 12, color: "var(--text-secondary)" }} title={t("fteHint")}>{t("fteToReassign")} <input className="mono" value={+r.portion_pct.toFixed(2)} onChange={e => setRule(i, { portion_pct: parseFloat(e.target.value) || 0 })} style={{ ...sel, width: 56, textAlign: "right", padding: "4px 6px" }} /></label>
              <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("cafeteria")}<input className="mono" value={+((r.cafeteria_pct || 0) * 100).toFixed(1)} onChange={e => setRule(i, { cafeteria_pct: (parseFloat(e.target.value) || 0) / 100 })} style={{ ...sel, width: 50, textAlign: "right", padding: "4px 6px" }} />%</label>
              {/* UN destino por renglon. Antes era una lista y el reparto entre
                  varios lo hacia el motor solo, proporcional al FTE de cada
                  destino: el owner veia una linea y no podia saber cuanto le
                  tocaba a cada departamento. Ahora se agrega un renglon por
                  destino y cada uno dice su FTE. */}
              <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6 }}>
                {t("goesInto")}
                <select value={r.target_depts[0] ?? ""} onChange={e => setRule(i, { target_depts: e.target.value ? [e.target.value] : [] })} style={{ ...sel, minWidth: 210 }}>
                  <option value="">{t("pickDept")}</option>
                  {depts.filter(d => d.dept_code !== r.source_dept).map(d => (
                    <option key={d.dept_code} value={d.dept_code} style={{ background: "var(--bg-input)" }}>{d.dept_code} {d.dept_name}</option>
                  ))}
                </select>
              </label>
              <button onClick={() => setRules(rs => rs.filter((_, j) => j !== i))} style={{ marginLeft: "auto", background: "none", border: "none", color: "var(--negative)", cursor: "pointer", fontSize: 18 }}>×</button>
            </div>
            {/* Una regla que no mueve plata tiene que decirlo. Las 6 que había
                apuntaban a códigos de la planilla 2026 y se veían normales,
                calculando cero en silencio. */}
            {(() => {
              const motivo = porQueNoMueve(r);
              return motivo ? (
                <div style={{
                  padding: "9px 16px", fontSize: 12, lineHeight: 1.5,
                  background: "rgba(192,57,43,0.12)",
                  borderBottom: "1px solid var(--border-subtle)",
                  color: "var(--negative, #C0392B)", fontWeight: 600,
                }}>
                  {t("ruleNotMoving", { motivo })}
                </div>
              ) : null;
            })()}
            {/* 12-month table */}
            {r.source_dept && r.position_code && (
              <div style={{ overflow: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1240 }}>
                  <thead><tr style={{ background: "var(--bg-header)", fontSize: 11.5, fontWeight: 800, color: "var(--text-secondary)", letterSpacing: "0.04em" }}>
                    {/* `top: auto` desactiva SOLO el pegado vertical que impone
                        globals.css a toda tabla. Cada tarjeta es corta: ahi el
                        encabezado pegajoso no sirve de nada y se montaba encima
                        de las filas de Salario y CCSS. La 1a columna sigue
                        pegada a la izquierda, que es lo que si hace falta al
                        correrse por los 12 meses. */}
                    <th style={{ ...thFijo, textAlign: "left", position: "sticky", left: 0, top: "auto", zIndex: 3, background: "var(--bg-header)", minWidth: 230 }}>{t("conceptHead")}</th>
                    {MONTHS.map(mo => <th key={mo} style={{ ...tdN, ...thFijo, position: "static" }}>{mo}</th>)}
                    <th style={{ ...tdN, ...thFijo, position: "static", color: GOLD }}>TOTAL</th>
                  </tr></thead>
                  <tbody>
                    {rowsDef.map((row, ri) => (
                      <tr key={ri} style={{ borderTop: "1px solid var(--border-subtle)", background: row.bold ? "rgba(99,102,241,0.10)" : "transparent" }}>
                        <td style={{ padding: "9px 12px", fontSize: 12.5, fontWeight: row.bold ? 800 : 600, color: row.color ?? "var(--text-primary)", position: "sticky", left: 0, background: "var(--bg-elevated)", whiteSpace: "nowrap" }}>
                          {row.label}{row.field && <button onClick={() => fillYear(i, row.field!)} title={t("copyJanHint")} style={{ marginLeft: 6, fontSize: 10, background: "none", border: `1px solid ${GOLD}66`, borderRadius: 4, color: GOLD, cursor: "pointer", padding: "0 4px" }}>{t("toYear")}</button>}
                        </td>
                        {row.vals.map((v, mi) => row.field ? (
                          <td key={mi} style={{ padding: "5px 3px" }}><input className="mono" value={v || ""} placeholder="0" onChange={e => setVec(i, row.field!, mi, e.target.value)} style={inp} /></td>
                        ) : (
                          <td key={mi} className="mono" style={{ ...tdN, fontWeight: row.bold ? 800 : 500, color: row.bold ? "var(--text-primary)" : "var(--text-secondary)" }}>{m0(v)}</td>
                        ))}
                        <td className="mono" style={{ ...tdN, fontWeight: 800, color: GOLD }}>{m0(row.vals.reduce((a, b) => a + b, 0))}</td>
                      </tr>
                    ))}
                    {r.target_depts.map(dep => (
                      <tr key={dep} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                        <td style={{ padding: "9px 12px 9px 26px", fontSize: 12, position: "sticky", left: 0, background: "var(--bg-elevated)", whiteSpace: "nowrap" }}>{t("debitRow")} {dep} {deptName[dep]}</td>
                        {c.dist[dep].map((v, mi) => <td key={mi} className="mono" style={tdN}>{m0(v)}</td>)}
                        <td className="mono" style={{ ...tdN, fontWeight: 700, color: GOLD }}>{m0(c.dist[dep].reduce((a, b) => a + b, 0))}</td>
                      </tr>
                    ))}
                    <tr style={{ borderTop: "1px solid var(--border-medium)" }}>
                      <td style={{ padding: "9px 12px", fontSize: 12, fontWeight: 700, color: "var(--brand)", position: "sticky", left: 0, background: "var(--bg-elevated)", whiteSpace: "nowrap" }}>{t("creditRow")} {r.source_dept} {deptName[r.source_dept]}</td>
                      {c.reassign.map((v, mi) => <td key={mi} className="mono" style={{ ...tdN, color: "var(--brand)" }}>{m0(-v)}</td>)}
                      <td className="mono" style={{ ...tdN, fontWeight: 700, color: "var(--brand)" }}>{m0(-c.reassign.reduce((a, b) => a + b, 0))}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
