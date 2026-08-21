"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import PushRevenueButton from "@/components/PushRevenueButton";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getRackRates, saveRackRates, rtLabel,
  type Scenario, type RackRateRow, type RackRateBulkRow, type MonthKey,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTH_KEYS: MonthKey[] = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];

function num(v: string): number {
  const n = parseFloat((v || "").toString().replace(/[, $]/g, ""));
  return isNaN(n) ? 0 : n;
}
function fmt2(v: string | number): string {
  const n = typeof v === "string" ? num(v) : v;
  return n.toFixed(2);   // siempre 2 decimales
}

export default function RackRatesPage() {
  const tc = useTranslations("common");
  const t = useTranslations("rackRates");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [rows, setRows] = useState<RackRateRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
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
        const budget = elegir(all, "budget") ?? all[0];
        if (!budget) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarioId(sharedScenarioOr(budget.id));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : tc("error"));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setMsg(null);
    try {
      const res = await getRackRates(sid);
      // Normalizar a 2 decimales para mostrar
      setRows(res.rooms.map(r => {
        const out = { ...r };
        MONTH_KEYS.forEach(mk => { out[mk] = fmt2(r[mk]); });
        return out;
      }));
      setDirty(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  function setCell(ri: number, mk: MonthKey, value: string) {
    setRows(prev => prev.map((r, i) => i === ri ? { ...r, [mk]: value } : r));
    setDirty(true);
  }

  // Al salir de la celda, fijar 2 decimales.
  function blurCell(ri: number, mk: MonthKey) {
    setRows(prev => prev.map((r, i) => i === ri ? { ...r, [mk]: fmt2(r[mk]) } : r));
  }

  // Pegar un bloque desde Excel desde la celda (ri, mi).
  function handlePaste(ri: number, mi: number, e: React.ClipboardEvent) {
    const text = e.clipboardData.getData("text");
    if (!text || (!text.includes("\t") && !text.includes("\n"))) return;
    e.preventDefault();
    const grid = text.replace(/\r/g, "").split("\n").filter(l => l.length).map(l => l.split("\t"));
    setRows(prev => {
      const next = prev.map(r => ({ ...r }));
      grid.forEach((cells, dr) => {
        const r = ri + dr;
        if (r >= next.length) return;
        cells.forEach((cell, dc) => {
          const m = mi + dc;
          if (m >= MONTH_KEYS.length) return;
          next[r][MONTH_KEYS[m]] = fmt2(cell);
        });
      });
      return next;
    });
    setDirty(true);
  }

  async function handleSave() {
    if (!scenarioId) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const payload: RackRateBulkRow[] = rows.map(r => ({
        room_type_id: r.room_type_id,
        ...(Object.fromEntries(MONTH_KEYS.map(mk => [mk, num(r[mk])])) as Record<MonthKey, number>),
      }));
      const res = await saveRackRates(scenarioId, payload);
      setDirty(false);
      setMsg(t("savedN", { n: res.saved }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorSaving"));
    } finally {
      setSaving(false);
    }
  }

  const sel = scenarios.find(s => s.id === scenarioId);
  const btn = (enabled: boolean): React.CSSProperties => ({
    padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, border: "none",
    cursor: enabled ? "pointer" : "not-allowed",
    background: enabled ? "var(--brand)" : "var(--bg-surface)",
    color: enabled ? "#fff" : "var(--text-disabled)",
  });

  // ── Excel: la misma grilla, con las tarifas como número ───────────────────
  async function bajarExcel() {
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const filas: FilaCuadro[] = rows.map(r => ({
      label: rtLabel(r.code, r.name), nivel: 1,
      valores: MONTH_KEYS.map(mk => num(r[mk])),
    }));
    try {
      await bajarCuadros("Rack_Rates", [{
        titulo: t("title"),
        subtitulo: `${esc} · ${t("xlsSubtitle")}`,
        hoja: "Rack Rates",
        columnas: [
          { label: "Room Type", ancho: 34, formato: "texto" },
          ...MONTHS.map(m => ({ label: m, ancho: 11, formato: "usd2" as const })),
        ],
        filas,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          {t("title")}
        </h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 220 }}>
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>
              {s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}
            </option>
          ))}
        </select>
        <PushRevenueButton scenarioId={scenarioId} />
        <div style={{ flex: 1 }} />
        <button onClick={bajarExcel} title={t("excelHint")}
          style={{ ...btn(true), background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>⬇ Excel</button>
        <button onClick={handleSave} disabled={saving || !dirty || sel?.is_locked} style={btn(!saving && dirty && !sel?.is_locked)}>
          {saving ? tc("saving") : dirty ? tc("save") : t("saved")}
        </button>
      </div>

      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 16 }}>
        {t("intro")}
      </p>

      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1200 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", minWidth: 220 }}>Room Type</th>
                {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 78 }}>{m}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={r.room_type_id}>
                  <td style={{ textAlign: "left", fontWeight: 500 }}>{rtLabel(r.code, r.name)}</td>
                  {MONTH_KEYS.map((mk, mi) => (
                    <td key={mk} style={{ padding: "1px 2px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>$</span>
                        <input
                          className="fin-input mono"
                          value={r[mk]}
                          disabled={sel?.is_locked}
                          onChange={e => setCell(ri, mk, e.target.value)}
                          onBlur={() => blurCell(ri, mk)}
                          onPaste={e => handlePaste(ri, mi, e)}
                          onFocus={e => e.target.select()}
                          style={{ flex: 1, minWidth: 0, textAlign: "right", padding: "3px 4px" }}
                        />
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
