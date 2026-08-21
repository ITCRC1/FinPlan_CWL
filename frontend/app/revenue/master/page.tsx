"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getScenarioMaster, saveScenarioMaster, createRoomType, updateRoomType, rtLabel,
  type Scenario, type RoomType,
} from "@/lib/api";
import { recalcularYContar } from "@/lib/recalcular";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

const btn = (enabled: boolean): React.CSSProperties => ({
  padding: "8px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, border: "none",
  cursor: enabled ? "pointer" : "not-allowed",
  background: enabled ? "var(--brand)" : "var(--bg-surface)",
  color: enabled ? "#fff" : "var(--text-disabled)",
});

export default function MasterDataPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("master");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [rooms, setRooms] = useState<RoomType[]>([]);
  const [units, setUnits] = useState<Record<string, string>>({});
  const [names, setNames] = useState<Record<string, string>>({});
  const [showHidden, setShowHidden] = useState(false);
  const [busyCat, setBusyCat] = useState(false);
  const [closed, setClosed] = useState<Set<number>>(new Set());
  const [pax, setPax] = useState("1.8");
  const [seeded, setSeeded] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recalc, setRecalc] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        // La regla del owner, una sola: `elegir(all, "budget")` = Budget Working
        // 2027. Acá había un año QUEMADO A MANO y, si no aparecía, `all[0]` —
        // que con `/scenarios/` ordenado por año descendente es **Working
        // 2035**. Ver `lib/escenarioPreferido`.
        const b = elegir(all, "budget") ?? all[0];
        if (!b) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarioId(sharedScenarioOr(b.id));
      } catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
      finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setMsg(null);
    try {
      const m = await getScenarioMaster(sid);
      setRooms(m.room_types);
      setUnits(Object.fromEntries(m.room_types.map(r => [r.id, String(r.units)])));
      setNames(Object.fromEntries(m.room_types.map(r => [r.id, r.name])));
      setClosed(new Set(m.closed_months));
      setPax(m.pax_per_night);
      setSeeded(m.seeded); setDirty(false);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const sel = scenarios.find(s => s.id === scenarioId);
  const visibleRooms = showHidden ? rooms : rooms.filter(r => r.active);
  const hiddenCount = rooms.filter(r => !r.active).length;
  const totalUnits = rooms.filter(r => r.active).reduce((s, r) => s + (parseInt(units[r.id]) || 0), 0);

  function toggleMonth(m1: number) {
    setClosed(prev => { const n = new Set(prev); if (n.has(m1)) n.delete(m1); else n.add(m1); return n; });
    setDirty(true);
  }
  function setUnit(id: string, v: string) {
    setUnits(prev => ({ ...prev, [id]: v })); setDirty(true);
  }

  async function handleSave() {
    if (!scenarioId) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      await saveScenarioMaster(scenarioId, {
        closed_months: [...closed].sort((a, b) => a - b),
        pax_per_night: parseFloat(pax) || 0,
        units: Object.fromEntries(rooms.map(r => [r.id, parseInt(units[r.id]) || 0])),
      });
      setSeeded(false); setDirty(false);
      setMsg(t("savedYear"));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("errorSaving")); }
    finally { setSaving(false); }
  }

  async function handleRecalc() {
    if (!scenarioId) return;
    setRecalc(true); setMsg(null);
    try {
      if (dirty) await handleSave();
      const aviso = await recalcularYContar(scenarioId,
        t("recalcDone"));
      setMsg(aviso);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("errorRecalc")); }
    finally { setRecalc(false); }
  }

  // ── Excel: inventario + parámetros del año ────────────────────────────────
  // Va el inventario COMPLETO (también las ocultas, marcadas): el archivo es el
  // detalle, no la vista filtrada.
  async function bajarExcel() {
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const filas: FilaCuadro[] = rooms.map(r => ({
      label: rtLabel(r.code, r.name) + (r.active ? "" : t("hiddenSuffix")),
      nivel: 1,
      valores: [parseInt(units[r.id]) || 0],
    }));
    filas.push({ label: t("totalActive"), es_total: true, valores: [totalUnits] });
    filas.push({ label: t("yearParams"), es_total: true, valores: [null] });
    filas.push({ label: t("paxFactor"), nivel: 1, formato: "usd2", valores: [parseFloat(pax) || 0] });
    filas.push({ label: t("closedMonthsCount"), nivel: 1, valores: [closed.size] });
    try {
      await bajarCuadros("Master_Data", [
        {
          titulo: t("xlsTitle"),
          subtitulo: t("xlsSubtitle", { esc }),
          hoja: t("xlsSheetInventory"),
          columnas: [
            { label: tc("category"), ancho: 40, formato: "texto" },
            { label: "Units", ancho: 14, formato: "num" },
          ],
          filas,
        },
        {
          titulo: t("closedMonths"),
          subtitulo: t("xlsClosedSubtitle"),
          hoja: t("closedMonths"),
          columnas: [
            { label: tc("concept"), ancho: 26, formato: "texto" },
            ...MONTHS.map(m => ({ label: m, ancho: 8, formato: "num" as const })),
          ],
          filas: [{
            label: t("closedRow"),
            // Abierto no es "cero meses cerrados", es que no aplica → celda vacía.
            valores: MONTHS.map((_m, i) => (closed.has(i + 1) ? 1 : null)),
          }],
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  const hotel = sel?.hotel_id ?? HOTEL_ID;
  async function addCategory() {
    const name = window.prompt(t("promptNewCategory"));
    if (!name || !name.trim()) return;
    setBusyCat(true); setError(null); setMsg(null);
    try { await createRoomType(hotel, { name: name.trim(), units: 0 }); await load(scenarioId); setMsg(t("categoryAdded")); }
    catch (e) { setError(e instanceof Error ? e.message : tc("error")); } finally { setBusyCat(false); }
  }
  async function commitName(r: RoomType) {
    const nv = (names[r.id] ?? "").trim();
    if (!nv || nv === r.name) return;
    setBusyCat(true); setError(null);
    try { await updateRoomType(hotel, r.id, { name: nv }); setRooms(rs => rs.map(x => x.id === r.id ? { ...x, name: nv } : x)); setMsg(t("renamed", { nombre: nv })); }
    catch (e) { setError(e instanceof Error ? e.message : tc("error")); } finally { setBusyCat(false); }
  }
  async function toggleHidden(r: RoomType) {
    setBusyCat(true); setError(null); setMsg(null);
    try { await updateRoomType(hotel, r.id, { active: !r.active }); await load(scenarioId); }
    catch (e) { setError(e instanceof Error ? e.message : tc("error")); } finally { setBusyCat(false); }
  }
  return (
    <div className="pag pag-lectura" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 220 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <button onClick={bajarExcel} title={t("excelHint")}
          style={{ ...btn(true), background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>⬇ Excel</button>
        <button onClick={handleSave} disabled={saving || !dirty || sel?.is_locked} style={btn(!saving && dirty && !sel?.is_locked)}>
          {saving ? tc("saving") : dirty ? tc("save") : t("saved")}
        </button>
        <button onClick={handleRecalc} disabled={recalc || sel?.is_locked} style={btn(!recalc && !sel?.is_locked)}>
          {recalc ? tc("recalc.running") : t("recalc")}
        </button>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 16 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b>, alcance: t("ofThisScenario") })}
      </p>

      {seeded && <p style={{ color: "var(--accent-amber, #856404)", fontSize: 12, marginBottom: 8 }}>{t("usingHotelValues")}</p>}
      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginBottom: 20 }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
              {t("paxFactor")}
              <input className="fin-input mono" value={pax} disabled={sel?.is_locked}
                onChange={e => { setPax(e.target.value); setDirty(true); }} onFocus={e => e.target.select()}
                style={{ width: 90, textAlign: "right" }} />
            </label>
            <div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>{t("closedMonths")}</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {MONTHS.map((m, i) => {
                  const isClosed = closed.has(i + 1);
                  return (
                    <button key={m} onClick={() => toggleMonth(i + 1)} disabled={sel?.is_locked}
                      style={{ padding: "5px 10px", fontSize: 12, borderRadius: 4, cursor: sel?.is_locked ? "not-allowed" : "pointer",
                        border: "1px solid var(--border-medium)",
                        background: isClosed ? "var(--accent-red, #C0392B)" : "var(--bg-surface)",
                        color: isClosed ? "#fff" : "var(--text-secondary)" }}>
                      {m}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "8px 0", flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>{t("inventory")}</h2>
            <button onClick={addCategory} disabled={busyCat || sel?.is_locked} style={{ padding: "5px 14px", fontSize: 12, fontWeight: 600, borderRadius: 5, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "none" }}>{t("addRoomType")}</button>
            {hiddenCount > 0 && (
              <button onClick={() => setShowHidden(v => !v)} style={{ padding: "4px 10px", fontSize: 12, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>
                {showHidden ? t("hideHiddenOnes") : t("showHiddenOnes", { n: hiddenCount })}
              </button>
            )}
          </div>
          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", margin: "0 0 8px", maxWidth: 640 }}>
            {t.rich("codeHelp", { b: (c: React.ReactNode) => <b>{c}</b>, code: tc("code") })}
          </p>
          <table className="fin-table" style={{ width: "100%", maxWidth: 720 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", width: 90 }} title={t("fixedCodeHint")}>{tc("code")}</th>
                <th style={{ textAlign: "left" }}>{t("categoryName")}</th>
                <th style={{ textAlign: "right", width: 110 }}>Units</th>
                <th style={{ textAlign: "right", width: 120 }}></th>
              </tr>
            </thead>
            <tbody>
              {visibleRooms.map(r => (
                <tr key={r.id} style={{ opacity: r.active ? 1 : 0.5 }}>
                  <td style={{ padding: "4px 8px" }}>
                    <span className="mono" title={t("fixedCodeNotEditable")} style={{ fontWeight: 700, letterSpacing: 0.5, color: "var(--brand)", background: "var(--bg-input, #1b2130)", border: "1px solid var(--border-medium)", borderRadius: 5, padding: "2px 8px", fontSize: 12 }}>
                      {r.code || "—"}
                    </span>
                  </td>
                  <td style={{ textAlign: "left", padding: "1px 2px" }}>
                    <input className="fin-input" value={names[r.id] ?? r.name} disabled={sel?.is_locked || busyCat}
                      onChange={e => setNames(p => ({ ...p, [r.id]: e.target.value }))}
                      onBlur={() => commitName(r)} onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                      style={{ width: "100%", fontWeight: 500, padding: "3px 6px", textAlign: "center" }} />
                  </td>
                  <td style={{ padding: "1px 2px", textAlign: "right" }}>
                    <input className="fin-input mono" value={units[r.id] ?? ""} disabled={sel?.is_locked || !r.active}
                      onChange={e => setUnit(r.id, e.target.value)} onFocus={e => e.target.select()}
                      style={{ width: 90, textAlign: "right", padding: "3px 4px" }} />
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button onClick={() => toggleHidden(r)} disabled={busyCat} title={r.active ? t("hideHint") : t("showHint")}
                      style={{ fontSize: 11, padding: "2px 9px", cursor: "pointer", background: "transparent", border: "1px solid var(--border-medium)", borderRadius: 4, color: "var(--text-secondary)" }}>
                      {r.active ? t("hide") : t("show")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                <td />
                <td style={{ textAlign: "left" }}>{t("totalActive")}</td>
                <td className="mono" style={{ textAlign: "right" }}>{totalUnits}</td>
                <td />
              </tr>
            </tfoot>
          </table>
        </>
      )}
    </div>
  );
}
