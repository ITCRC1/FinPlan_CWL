"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros } from "@/lib/exportCuadro";
import {
  getScenarios, getRoomTypes, getOccupancyPct, getSpaBudget, saveSpaBudget,
  type Scenario, type MonthKey,
} from "@/lib/api";
import { recalcularYContar } from "@/lib/recalcular";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTH_KEYS: MonthKey[] = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];

function daysInMonth(year: number, month1: number): number {
  return new Date(year, month1, 0).getDate();
}
function fnum(v: string): number {
  const n = parseFloat((v || "").toString().replace(/[, %$]/g, ""));
  return isNaN(n) ? 0 : n;
}

const btnStyle = (enabled: boolean): React.CSSProperties => ({
  padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600,
  cursor: enabled ? "pointer" : "not-allowed", border: "none",
  background: enabled ? "var(--brand)" : "var(--bg-surface)",
  color: enabled ? "#fff" : "var(--text-disabled)",
});

export default function SpaBudgetPage() {
  const tc = useTranslations("common");
  const t = useTranslations("spa");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [pax, setPax] = useState<number[]>(Array(12).fill(0));
  const [capture, setCapture] = useState<string[]>(Array(12).fill("0")); // % (0..100)
  const [avgPrice, setAvgPrice] = useState<string>("0");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recalc, setRecalc] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** `false` = el escenario arma sus ingresos con tarifas y ocupación y no lee
   *  el checkbook, así que la línea SPA que escribimos al guardar no va a
   *  llegar al P&L. Se avisa en vez de dejarlo pasar callado. */
  const [llegaAlPl, setLlegaAlPl] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        // La regla del owner, una sola: `elegir(all, "budget")` = Budget Working
        // 2027. Acá había un año QUEMADO A MANO y, si no aparecía, `all[0]` —
        // que con `/scenarios/` ordenado por año descendente es **Working
        // 2035**. Ver `lib/escenarioPreferido`.
        const budget = elegir(all, "budget") ?? all[0];
        if (!budget) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarioId(sharedScenarioOr(budget.id));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : t("errorLoadingScenarios"));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setMsg(null);
    try {
      const [rt, occ, spa] = await Promise.all([
        getRoomTypes(HOTEL_ID, sid), getOccupancyPct(sid), getSpaBudget(sid),
      ]);
      const year = occ.year;
      const closed = new Set(rt.closed_months);
      const unitsById = Object.fromEntries(rt.room_types.map(r => [r.id, r.units]));
      const ppn = parseFloat(rt.pax_per_night) || 1.8;
      const occupied = MONTHS.map((_m, mi) =>
        occ.rooms.reduce((s, r) => {
          if (closed.has(mi + 1)) return s;
          const u = unitsById[r.room_type_id] ?? 0;
          return s + (parseFloat(r[MONTH_KEYS[mi]]) || 0) * u * daysInMonth(year, mi + 1);
        }, 0));
      setPax(occupied.map(o => o * ppn));

      const capByMonth = Object.fromEntries(spa.months.map(m => [m.month, m.capture_pct]));
      setCapture(MONTHS.map((_m, mi) => String((parseFloat(capByMonth[mi + 1] ?? "0") || 0) * 100)));
      setAvgPrice(spa.avg_price);
      setLlegaAlPl(spa.llega_al_pl !== false);
      setDirty(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const sel = scenarios.find(s => s.id === scenarioId);
  const price = fnum(avgPrice);
  const captureFrac = capture.map(c => fnum(c) / 100);
  const treatments = pax.map((p, i) => p * captureFrac[i]);
  const revenue = treatments.map(t => t * price);
  const tPax = pax.reduce((s, v) => s + v, 0);
  const tTreat = treatments.reduce((s, v) => s + v, 0);
  const tRev = revenue.reduce((s, v) => s + v, 0);

  function setCapCell(mi: number, value: string) {
    setCapture(prev => prev.map((c, i) => i === mi ? value : c));
    setDirty(true);
  }

  async function handleSave() {
    if (!scenarioId) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const months = MONTH_KEYS.map((_mk, i) => ({
        month: i + 1, capture_pct: captureFrac[i], revenue: Math.round(revenue[i]),
      }));
      const res = await saveSpaBudget(scenarioId, price, months);
      setDirty(false);
      if (res.llega_al_pl !== undefined) setLlegaAlPl(res.llega_al_pl);
      const total = `$${Math.round(parseFloat(res.spa_total)).toLocaleString("en-US")}`;
      // Decir "→ línea SPA del checkbook" cuando el escenario no lee el
      // checkbook es dar por hecho lo que no pasó: se escribió, sí, pero el P&L
      // no la va a mirar.
      setMsg(res.llega_al_pl === false
        ? t("savedNotInPl", { total })
        : t("savedInCheckbook", { total }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorSaving"));
    } finally {
      setSaving(false);
    }
  }

  async function handleRecalc() {
    if (!scenarioId) return;
    setRecalc(true); setMsg(null);
    try {
      if (dirty) await handleSave();
      const aviso = await recalcularYContar(scenarioId, t("plRecalculated"));
      setMsg(aviso);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorRecalc"));
    } finally {
      setRecalc(false);
    }
  }

  async function bajarExcel() {
    try {
      await bajarCuadros("Spa_Capture_Rate", [{
        titulo: t("title"),
        subtitulo: [sel ? `${sel.type} ${sel.version} ${sel.year}` : "",
          t("avgPriceXls", { precio: price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) })]
          .filter(Boolean).join(" · "),
        hoja: "Spa",
        columnas: [
          { label: "Spa", ancho: 26, formato: "texto" },
          ...MONTHS.map(m => ({ label: m, ancho: 12, formato: "num" as const })),
          { label: "Full Year", ancho: 15, formato: "num" as const },
        ],
        filas: [
          { label: "Total Pax", valores: [...pax, tPax] },
          // El capture rate se digita como 12.5 y viaja como 0.125.
          { label: t("captureRate"), formato: "pct", valores: [...captureFrac, tPax ? tTreat / tPax : null] },
          { label: t("treatments"), valores: [...treatments, tTreat] },
          { label: t("spaRevenue"), es_total: true, formato: "usd2", valores: [...revenue, tRev] },
        ],
      }]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  const numCell = (n: number) => Math.round(n).toLocaleString("en-US");
  const usd = (n: number) => n ? (n < 0 ? "(" : "") + "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "") : "—";
  const td: React.CSSProperties = { textAlign: "right" };
  const yr: React.CSSProperties = { textAlign: "right", borderLeft: "1px solid var(--border)", fontWeight: 600 };

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 220 }}>
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>
          ))}
        </select>
      </div>

      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>

      {!llegaAlPl && (
        <div style={{ marginTop: 14, padding: "12px 16px", borderRadius: 8, fontSize: 12.5,
          background: "rgba(200,162,74,0.08)", border: "1px solid #c8a24a", maxWidth: "90ch" }}>
          {t.rich("notCheckbook", { b: (c: React.ReactNode) => <b>{c}</b> })}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "flex-end", gap: 14, flexWrap: "wrap", margin: "14px 0" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
          {t("avgPrice")}
          <input className="fin-input mono" type="number" value={avgPrice}
            disabled={sel?.is_locked}
            onChange={e => { setAvgPrice(e.target.value); setDirty(true); }}
            style={{ width: 160, textAlign: "right", padding: "4px 6px" }} />
        </label>
        <div style={{ flex: 1 }} />
        <button onClick={handleSave} disabled={saving || !dirty || sel?.is_locked} style={btnStyle(!saving && dirty && !sel?.is_locked)}>
          {saving ? tc("saving") : dirty ? tc("save") : t("saved")}
        </button>
        <button onClick={handleRecalc} disabled={recalc || sel?.is_locked} style={btnStyle(!recalc && !sel?.is_locked)}>
          {recalc ? tc("recalc.running") : t("recalcPl")}
        </button>
        <button onClick={bajarExcel} disabled={loading} title={t("excelHint")}
          style={{ ...btnStyle(!loading), background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>

      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1200 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", minWidth: 180 }}>Spa</th>
                {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 80 }}>{m}</th>)}
                <th style={{ textAlign: "right", minWidth: 100, borderLeft: "1px solid var(--border)" }}>Full Year</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ textAlign: "left", fontWeight: 500 }}>Total Pax</td>
                {pax.map((v, i) => <td key={i} className="mono" style={td}>{numCell(v)}</td>)}
                <td className="mono" style={yr}>{numCell(tPax)}</td>
              </tr>
              <tr>
                <td style={{ textAlign: "left", fontWeight: 500 }}>{t("captureRate")}</td>
                {capture.map((c, i) => (
                  <td key={i} style={{ padding: "1px 2px" }}>
                    <input className="fin-input mono" value={c} disabled={sel?.is_locked}
                      onChange={e => setCapCell(i, e.target.value)} onFocus={e => e.target.select()}
                      style={{ width: "100%", textAlign: "right", padding: "3px 4px" }} />
                  </td>
                ))}
                <td className="mono" style={{ ...yr, color: "var(--brand)" }}>{tPax ? (tTreat / tPax * 100).toFixed(1) + "%" : "—"}</td>
              </tr>
              <tr>
                <td style={{ textAlign: "left", fontWeight: 500 }}>{t("treatments")}</td>
                {treatments.map((v, i) => <td key={i} className="mono" style={td}>{numCell(v)}</td>)}
                <td className="mono" style={yr}>{numCell(tTreat)}</td>
              </tr>
              <tr>
                <td style={{ textAlign: "left", fontWeight: 500 }}>{t("spaRevenue")}</td>
                {revenue.map((v, i) => <td key={i} className="mono" style={td}>{usd(v)}</td>)}
                <td className="mono" style={{ ...yr, color: "var(--brand)" }}>{usd(tRev)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
