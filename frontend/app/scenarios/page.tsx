"use client";
import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, createScenario, copyScenarioFrom, setSourceMode, setRevenueSource,
  setActualsThrough, markCurrentForecast, snapshotForecastMonth, budgetToForecastCurrent,
  renameScenario, deleteScenario, setScenarioStatus, ensureWorkingBudgets,
  getCopyInventory,
  type Scenario,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const HOTEL = HOTEL_ID;
// Working y Final son versiones protegidas: no se pueden borrar (regla de negocio).
const isProtected = (s: Scenario) => /working|final/i.test(s.version);
const TYPES = ["BUDGET", "FORECAST", "ACTUAL"] as const;

function label(s: Scenario): string {
  return `${s.type} ${s.version} ${s.year}`;
}

const btn = (enabled: boolean): React.CSSProperties => ({
  padding: "8px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, border: "none",
  cursor: enabled ? "pointer" : "not-allowed",
  background: enabled ? "var(--brand)" : "var(--bg-surface)",
  color: enabled ? "#fff" : "var(--text-disabled)",
});

export default function ScenariosPage() {
  // `tc` ya está tomado en esta pantalla: es el tipo de cambio.
  const tCom = useTranslations("common");
  const t = useTranslations("scenarios");
  const MONTHS = useTranslations("months").raw("short") as string[];
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // form
  const [showForm, setShowForm] = useState(false);
  const [year, setYear] = useState(new Date().getFullYear() + 1);
  const [type, setType] = useState<string>("BUDGET");
  const [version, setVersion] = useState("Draft1");
  const [tc, setTc] = useState("530");
  const [start, setStart] = useState<"blank" | "copy">("copy");
  const [sourceId, setSourceId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  // Qué escenarios sirven como origen de una copia. Se pide junto con la lista
  // para poder ordenar y marcar los orígenes ANTES de que se elija uno.
  // Ojo: NO es "tiene filas". Un escenario recién creado ya tiene 50 filas de
  // andamiaje (mix de canales, config de Villas, los 12 TC) y el P&L en cero;
  // el backend las descuenta y devuelve `vacio`.
  const [vacioPorEsc, setVacioPorEsc] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Auto: asegurar que exista 'Budget Working {año}' para 2027 en adelante.
      try { await ensureWorkingBudgets(2027, 2035, HOTEL); } catch { /* silencioso */ }
      const all = await getScenarios(HOTEL);
      // ordenar por año desc, luego tipo
      all.sort((a, b) => b.year - a.year || a.type.localeCompare(b.type) || a.version.localeCompare(b.version));
      setScenarios(all);
      let vacios: Record<string, boolean> = {};
      try {
        const inv = await getCopyInventory(HOTEL);
        vacios = Object.fromEntries(inv.escenarios.map(e => [e.id, e.vacio]));
        setVacioPorEsc(vacios);
      } catch { /* si el inventario falla, el orden cae al de siempre */ }
      // Preseleccionar un origen CON DATOS. Antes se tomaba el primer BUDGET de
      // una lista ordenada por año descendente: eso caía siempre en
      // "Budget Working 2035", que está vacío. Copiar de ahí daba una copia
      // vacía y el único aviso era un «copiadas 0 filas» al final.
      if (!sourceId && all.length) {
        const conDatos = all.filter(s => !vacios[s.id]);
        const elegibles = conDatos.length ? conDatos : all;
        // Entre los que tienen datos, la versión "Working" es la que manda en
        // esta casa (misma regla que el escenario por defecto). Sin esta
        // preferencia caía en "Draft1 2027" solo por orden alfabético.
        const budgets = elegibles.filter(s => s.type === "BUDGET");
        setSourceId((budgets.find(s => /working/i.test(s.version))
          ?? budgets[0] ?? elegibles[0]).id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setLoading(false);
    }
  }, [sourceId]);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    // El aviso va ANTES de crear nada. Si el origen no tiene filas, la copia
    // nace vacía; que eso se supiera recién al final —por un «copiadas 0
    // filas»— dejaba escenarios vacíos creados sin querer.
    let origenVacioConfirmado = false;
    if (start === "copy" && sourceId) {
      const src = scenarios.find(s => s.id === sourceId);
      if (src && vacioPorEsc[sourceId]) {
        if (!window.confirm(t("emptySourceConfirm", { origen: label(src) }))) return;
        origenVacioConfirmado = true;
      }
    }
    setBusy(true); setError(null); setMsg(null);
    try {
      const created = await createScenario({
        hotel_id: HOTEL, year, type, version: version.trim() || "v1", tc_default: parseFloat(tc) || 530,
      });
      // los presupuestos/forecasts armados en la app calculan desde los checkbooks
      await setSourceMode(created.id, "checkbook");
      await setRevenueSource(created.id, "checkbook");
      if (start === "copy" && sourceId) {
        // La copia se lleva el escenario ENTERO —mayor y snapshot del P&L
        // incluidos— y con él el `source_mode` del origen: así el nuevo lee el
        // P&L por el mismo camino y da los mismos números.
        const res = await copyScenarioFrom(created.id, sourceId, origenVacioConfirmado);
        const n = Object.values(res.copied).reduce((s, v) => s + v, 0);
        setMsg(t("createdCopy", { esc: label(created), n, fuente: res.source_mode ?? "" }));
        if (res.avisos?.length) setError(res.avisos.join(" · "));
      } else {
        setMsg(t("createdBlank", { esc: label(created) }));
      }
      setShowForm(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("createError"));
    } finally {
      setBusy(false);
    }
  }

  // Orígenes posibles, separados por si tienen algo adentro. Mientras el
  // inventario no llegó, `vacioPorEsc` está vacío y todos cuentan como "con
  // datos": nunca se marca vacío un escenario que no se midió.
  const tieneDatos = (s: Scenario) => !vacioPorEsc[s.id];
  const conDatos = scenarios.filter(tieneDatos);
  const vacios = scenarios.filter(s => !tieneDatos(s));

  const current = scenarios.find(s => s.type === "FORECAST" && s.is_current_forecast);
  const SNAP_VERSIONS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const isMonthlySnap = (s: Scenario) => s.type === "FORECAST" && SNAP_VERSIONS.includes(s.version);
  const mainScenarios = scenarios.filter(s => !isMonthlySnap(s));
  const monthlySnaps = scenarios.filter(isMonthlySnap);
  const [showSnaps, setShowSnaps] = useState(false);
  const [snapMonth, setSnapMonth] = useState(0);
  const effSnapMonth = snapMonth || current?.actuals_through || 0;

  async function handleSnapshot() {
    if (!current || !effSnapMonth) return;
    const monthName = MONTHS[effSnapMonth - 1];
    if (!window.confirm(t("snapshotConfirm", {
      mes: monthName, anio: String(current.year), esc: label(current),
    }))) return;
    setBusy(true); setError(null); setMsg(null);
    try {
      const snap = await snapshotForecastMonth(current.id, effSnapMonth);
      setMsg(t("snapshotCreated", { label: snap.label }));
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("snapshotError"));
    } finally {
      setBusy(false);
    }
  }

  async function handleRollover(budget: Scenario) {
    if (!window.confirm(t("rolloverConfirm", {
      anio: String(budget.year), esc: label(budget),
    }))) return;
    setBusy(true); setError(null); setMsg(null);
    try {
      const fc = await budgetToForecastCurrent(budget.id);
      setMsg(t("rolloverCreated", { label: fc.label }));
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("rolloverError"));
    } finally {
      setBusy(false);
    }
  }

  async function handleRename(s: Scenario) {
    const nv = window.prompt(t("renamePrompt", { tipo: s.type, anio: String(s.year), version: s.version }), s.version);
    if (!nv || nv.trim() === s.version) return;
    setBusy(true); setError(null); setMsg(null);
    try {
      await renameScenario(s.id, nv.trim());
      setMsg(t("renamed", { antes: label(s), ahora: nv.trim() }));
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("renameError"));
    } finally { setBusy(false); }
  }

  async function handleToggleLock(s: Scenario) {
    const next = s.is_locked ? "draft" : "locked";
    const verb = s.is_locked ? t("unlockVerb") : t("lockVerb");
    if (!window.confirm(t("lockConfirm", {
      verbo: verb.charAt(0).toUpperCase() + verb.slice(1), esc: label(s),
    }))) return;
    setBusy(true); setError(null); setMsg(null);
    try {
      await setScenarioStatus(s.id, next);
      setMsg(s.is_locked ? t("opened", { esc: label(s) }) : t("lockedMsg", { esc: label(s) }));
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tCom("error"));
    } finally { setBusy(false); }
  }

  async function handleDelete(s: Scenario) {
    if (!window.confirm(t("deleteConfirm", { esc: label(s) }))) return;
    setBusy(true); setError(null); setMsg(null);
    try {
      await deleteScenario(s.id);
      setMsg(t("deleted", { esc: label(s) }));
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("deleteError"));
    } finally { setBusy(false); }
  }

  // ── Bajar a Excel ──────────────────────────────────────────────────────────
  // Este cuadro es casi todo texto (tipo, versión, estado, fuente del P&L) y el
  // exportador de la casa solo lleva números en las celdas de valor. Así que lo
  // descriptivo viaja en la etiqueta de la fila —tal como se lee en pantalla— y
  // en columnas quedan los tres datos que sí son números: el año, si está
  // enllavada y hasta qué mes manda el actual. Es el inventario de versiones,
  // que es para lo que uno se lleva esta pantalla.
  async function bajarExcel() {
    setError(null); setMsg(null);
    if (!scenarios.length) { setError(t("noScenariosExport")); return; }
    const fila = (s: Scenario): FilaCuadro => ({
      label: t("xls.row", {
        tipo: s.type, version: s.version, estado: s.status,
        current: s.is_current_forecast ? t("xls.currentSuffix") : "",
        fuente: s.source_mode ?? "imported",
      }),
      nivel: 1,
      valores: [s.year, s.is_locked ? 1 : 0, s.actuals_through || null],
    });
    const filas: FilaCuadro[] = [
      { label: t("xls.scenarios"), es_total: true, valores: [null, null, null] },
      ...mainScenarios.map(fila),
    ];
    if (monthlySnaps.length) {
      filas.push({ label: t("xls.monthlySnaps"), es_total: true, valores: [null, null, null] });
      filas.push(...monthlySnaps.map(fila));
    }
    try {
      await bajarCuadros("Escenarios", [{
        titulo: t("xls.title"),
        subtitulo: t("xls.sub"),
        hoja: t("xls.scenarios"),
        columnas: [
          { label: t("xls.col1"), ancho: 62, formato: "texto" },
          { label: tCom("year"), ancho: 9, formato: "num" },
          { label: t("xls.lockedCol"), ancho: 12, formato: "num" },
          { label: t("xls.cutCol"), ancho: 20, formato: "num" },
        ],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : t("xls.error")); }
  }

  const statusPill = (s: string): React.CSSProperties => {
    const map: Record<string, [string, string]> = {
      locked: ["var(--accent-red, #C0392B)", "rgba(192,57,43,0.12)"],
      approved: ["var(--accent-green, #1A7F4B)", "rgba(26,127,75,0.12)"],
      draft: ["var(--text-secondary)", "var(--bg-surface)"],
    };
    const [color, bg] = map[s] ?? map.draft;
    return { fontSize: 11, padding: "2px 8px", borderRadius: 5, color, background: bg };
  };

  return (
    <div className="pag pag-media" style={{ padding: 24 }}>
      <IrA />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{t("title")}</h1>
        <div style={{ flex: 1 }} />
        <button onClick={bajarExcel} title={t("excelHint")}
          style={{ padding: "8px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, cursor: "pointer", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>⬇ Excel</button>
        <button onClick={() => setShowForm(v => !v)} style={btn(true)}>
          {showForm ? tCom("cancel") : t("newScenario")}
        </button>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 16 }}>
        {t("intro")}
      </p>

      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {showForm && (
        <div style={{ border: "1px solid var(--border-medium)", borderRadius: 8, padding: 16, marginBottom: 20, background: "var(--bg-surface)" }}>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
              {tCom("year")}
              <input className="fin-input mono" type="number" value={year} onChange={e => setYear(parseInt(e.target.value) || year)} style={{ width: 90 }} />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
              {t("type")}
              <select className="fin-input" value={type} onChange={e => setType(e.target.value)} style={{ width: 130 }}>
                {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
              {t("version")}
              <input className="fin-input" value={version} onChange={e => setVersion(e.target.value)} placeholder={t("versionPlaceholder")} style={{ width: 140 }} />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
              {t("fxLabel")}
              <input className="fin-input mono" value={tc} onChange={e => setTc(e.target.value)} style={{ width: 90 }} />
            </label>
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>{t("howStarts")}</div>
            <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "center" }}>
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13, cursor: "pointer" }}>
                <input type="radio" checked={start === "copy"} onChange={() => setStart("copy")} /> {t("copyFrom")}
              </label>
              {/* Los orígenes CON datos van arriba; los vacíos, abajo y dichos.
                  Con el orden viejo (año descendente) el primero de la lista era
                  "Budget Working 2035", vacío — y era el que quedaba elegido. */}
              <select className="fin-input" value={sourceId} disabled={start !== "copy"} onChange={e => setSourceId(e.target.value)} style={{ minWidth: 260, opacity: start === "copy" ? 1 : 0.5 }}>
                {conDatos.map(s => <option key={s.id} value={s.id}>{label(s)}</option>)}
                {vacios.length > 0 && (
                  <optgroup label={t("emptyGroup")}>
                    {vacios.map(s => <option key={s.id} value={s.id}>{label(s)}{t("noData")}</option>)}
                  </optgroup>
                )}
              </select>
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13, cursor: "pointer" }}>
                <input type="radio" checked={start === "blank"} onChange={() => setStart("blank")} /> {t("blank")}
              </label>
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            <button onClick={handleCreate} disabled={busy} style={btn(!busy)}>
              {busy ? t("creating") : t("createScenario")}
            </button>
          </div>
        </div>
      )}

      {current && (
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "14px 18px", marginBottom: 20 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{t("monthlySnapshot")}</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>
            {t.rich("snapshotHelp", {
              esc: label(current), mes: MONTHS[(effSnapMonth || 1) - 1], anio: String(current.year),
              b: (c: React.ReactNode) => <strong>{c}</strong>,
            })}
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("monthToSave")}</label>
            <select className="fin-input" style={{ fontSize: 12 }} value={effSnapMonth}
              onChange={e => setSnapMonth(Number(e.target.value))}>
              <option value={0} disabled>{t("pickMonth")}</option>
              {MONTHS.map((mn, i) => <option key={i + 1} value={i + 1}>{mn} {current.year}</option>)}
            </select>
            <button onClick={handleSnapshot} disabled={busy || !effSnapMonth}
              style={{ padding: "7px 14px", borderRadius: 6, cursor: effSnapMonth ? "pointer" : "default", background: effSnapMonth && !busy ? "var(--accent-excel)" : "#555", color: "#fff", border: "none", fontSize: 13, fontWeight: 600 }}>
              {busy ? t("copying") : t("snapshotBtn")}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tCom("loading")}</div>
      ) : (
        <table className="fin-table" style={{ width: "100%" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>{t("type")}</th>
              <th style={{ textAlign: "left" }}>{t("version")}</th>
              <th style={{ textAlign: "right" }}>{tCom("year")}</th>
              <th style={{ textAlign: "left" }}>{tCom("status")}</th>
              <th style={{ textAlign: "left" }}>{t("plSource")}</th>
              <th style={{ textAlign: "left" }}>{t("rollingCut")}</th>
              <th style={{ textAlign: "right" }}></th>
            </tr>
          </thead>
          <tbody>
            {mainScenarios.map(s => (
              <tr key={s.id}>
                <td style={{ textAlign: "left", fontWeight: 500 }}>{s.type}{s.is_locked ? " 🔒" : ""}</td>
                <td style={{ textAlign: "left" }}>
                  {s.version}
                  {s.type === "FORECAST" && (s.is_current_forecast
                    ? <span title={t("currentHint")} style={{ marginLeft: 6, fontSize: 11, fontWeight: 700, color: "var(--accent-green, #1A7F4B)" }}>{t("current")}</span>
                    : <button onClick={async () => {
                        try {
                          await markCurrentForecast(s.id);
                          setScenarios(prev => prev.map(x => x.type === "FORECAST" && x.hotel_id === s.hotel_id && x.year === s.year
                            ? { ...x, is_current_forecast: x.id === s.id } : x));
                          setMsg(t("nowCurrent", { esc: label(s) }));
                        } catch (err) { setError(err instanceof Error ? err.message : tCom("error")); }
                      }} style={{ marginLeft: 6, fontSize: 10, padding: "1px 6px", cursor: "pointer", background: "transparent", border: "1px solid var(--border-medium)", borderRadius: 4, color: "var(--text-secondary)" }}>{t("markCurrent")}</button>
                  )}
                </td>
                <td className="mono" style={{ textAlign: "right" }}>{s.year}</td>
                <td style={{ textAlign: "left" }}><span style={statusPill(s.status)}>{s.status}</span></td>
                <td style={{ textAlign: "left", color: "var(--text-secondary)", fontSize: 12 }}>{s.source_mode ?? "imported"}</td>
                <td style={{ textAlign: "left" }}>
                  {s.type === "FORECAST" ? (
                    <select className="fin-input" style={{ fontSize: 12 }} value={s.actuals_through ?? 0}
                      onChange={async e => {
                        const m = Number(e.target.value);
                        try {
                          await setActualsThrough(s.id, m);
                          setScenarios(prev => prev.map(x => x.id === s.id ? { ...x, actuals_through: m } : x));
                          setMsg(t("cutMsg", {
                            esc: label(s),
                            valor: m === 0 ? t("cutNone") : t("cutUntil", { mes: MONTHS[m - 1] }),
                          }));
                        } catch (err) { setError(err instanceof Error ? err.message : tCom("error")); }
                      }}>
                      <option value={0}>{tCom("noneDash")}</option>
                      {MONTHS.map((mn, i) => <option key={i+1} value={i+1}>{t("actualsUntil", { mes: mn })}</option>)}
                    </select>
                  ) : <span style={{ color: "var(--text-disabled)", fontSize: 12 }}>—</span>}
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {s.type === "BUDGET" && (
                    <button onClick={() => handleRollover(s)} disabled={busy}
                      title={t("rolloverHint")}
                      style={{ fontSize: 11, marginRight: 10, padding: "2px 8px", cursor: "pointer", background: "transparent", border: "1px solid var(--brand)", borderRadius: 4, color: "var(--brand)" }}>
                      → Forecast Current
                    </button>
                  )}
                  <button onClick={() => handleToggleLock(s)} disabled={busy} title={s.is_locked ? t("openTitle") : t("lockTitle")}
                    style={{ fontSize: 11, marginRight: 6, padding: "2px 8px", cursor: "pointer", background: "transparent", border: `1px solid ${s.is_locked ? "var(--accent-green, #1A7F4B)" : "var(--border-medium)"}`, borderRadius: 4, color: s.is_locked ? "var(--accent-green, #1A7F4B)" : "var(--text-secondary)" }}>
                    {s.is_locked ? t("openBtn") : t("lockBtn")}
                  </button>
                  <button onClick={() => handleRename(s)} disabled={busy || s.is_locked} title={s.is_locked ? t("renameLocked") : t("renameTitle")}
                    style={{ fontSize: 11, marginRight: 6, padding: "2px 8px", cursor: s.is_locked ? "not-allowed" : "pointer", opacity: s.is_locked ? 0.5 : 1, background: "transparent", border: "1px solid var(--border-medium)", borderRadius: 4, color: "var(--text-secondary)" }}>
                    {t("renameBtn")}
                  </button>
                  {s.status === "draft" && !isProtected(s) ? (
                    <button onClick={() => handleDelete(s)} disabled={busy} title={t("deleteVersion")}
                      style={{ fontSize: 11, marginRight: 10, padding: "2px 8px", cursor: "pointer", background: "transparent", border: "1px solid #7a2e2e", borderRadius: 4, color: "#c96" }}>
                      🗑
                    </button>
                  ) : isProtected(s) ? (
                    <span title={t("protectedHint")} style={{ marginRight: 10, fontSize: 12 }}>🔒</span>
                  ) : null}
                  <a href={`/pl/full`} style={{ fontSize: 12, color: "var(--brand)", textDecoration: "none" }}>{t("viewPL")}</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {monthlySnaps.length > 0 && (
        <div style={{ marginTop: 22 }}>
          <button onClick={() => setShowSnaps(v => !v)}
            style={{ background: "transparent", border: "none", cursor: "pointer", fontSize: 14, fontWeight: 600, color: "var(--text-primary)", padding: 0 }}>
            {showSnaps ? "▾" : "▸"} {t("xls.monthlySnaps")} ({monthlySnaps.length})
          </button>
          {showSnaps && (
            <table className="fin-table" style={{ width: "100%", marginTop: 10 }}>
              <thead><tr>
                <th style={{ textAlign: "left" }}>{tCom("month")}</th>
                <th style={{ textAlign: "right" }}>{tCom("year")}</th>
                <th style={{ textAlign: "left" }}>{tCom("status")}</th>
                <th style={{ textAlign: "left" }}>{t("cut")}</th>
                <th style={{ textAlign: "right" }}></th>
              </tr></thead>
              <tbody>
                {monthlySnaps.sort((a, b) => b.year - a.year || SNAP_VERSIONS.indexOf(b.version) - SNAP_VERSIONS.indexOf(a.version)).map(s => (
                  <tr key={s.id}>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>Forecast {s.version}{s.is_locked ? " 🔒" : ""}</td>
                    <td className="mono" style={{ textAlign: "right" }}>{s.year}</td>
                    <td style={{ textAlign: "left" }}><span style={statusPill(s.status)}>{s.status}</span></td>
                    <td style={{ textAlign: "left", color: "var(--text-secondary)", fontSize: 12 }}>{s.actuals_through ? t("until", { mes: MONTHS[s.actuals_through - 1] }) : "—"}</td>
                    <td style={{ textAlign: "right" }}>
                      <a href={`/pl/full`} style={{ fontSize: 12, color: "var(--brand)", textDecoration: "none" }}>{t("viewPL")}</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
