"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import PushRevenueButton from "@/components/PushRevenueButton";
import {
  getScenarios, getOccupancyPct, saveOccupancyPct, getRoomTypes, rtLabel,
  type Scenario, type OccPctRow, type OccPctBulkRow, type MonthKey,
} from "@/lib/api";
import { fmtInt } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTH_KEYS: MonthKey[] = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];

function fracToPct(s: string): string { return String(parseFloat((parseFloat(s) * 100 || 0).toFixed(2))); }
function pctNum(v: string): number {
  const n = parseFloat((v || "").toString().replace(/[%, ]/g, ""));
  return isNaN(n) ? 0 : n;
}
function daysInMonth(year: number, month1: number): number {
  return new Date(year, month1, 0).getDate();
}

export default function OccupancyPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("occupancy");
  const ttr = useTranslations("totalRev");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [rows, setRows] = useState<OccPctRow[]>([]);   // % (string)
  const [unitsById, setUnitsById] = useState<Record<string, number>>({});
  const [codeById, setCodeById] = useState<Record<string, string>>({});
  const [closed, setClosed] = useState<Set<number>>(new Set());
  const [year, setYear] = useState(2026);
  const [seeded, setSeeded] = useState(false);
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
      } finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setMsg(null);
    try {
      const [res, rt] = await Promise.all([getOccupancyPct(sid), getRoomTypes(HOTEL_ID, sid)]);
      setUnitsById(Object.fromEntries(rt.room_types.map(r => [r.id, r.units])));
      setCodeById(Object.fromEntries(rt.room_types.map(r => [r.id, r.code])));
      setClosed(new Set(rt.closed_months));
      setYear(res.year);
      setRows(res.rooms.map(r => {
        const out = { ...r };
        MONTH_KEYS.forEach(mk => { out[mk] = fracToPct(r[mk]); });
        return out;
      }));
      setSeeded(res.seeded);
      setDirty(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  function setCell(ri: number, mk: MonthKey, value: string) {
    setRows(prev => prev.map((r, i) => i === ri ? { ...r, [mk]: value } : r));
    setDirty(true);
  }

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
          next[r][MONTH_KEYS[m]] = String(pctNum(cell));
        });
      });
      return next;
    });
    setDirty(true);
  }

  function applyJanToAll() {
    setRows(prev => prev.map(r => {
      const out = { ...r };
      MONTH_KEYS.forEach(mk => { out[mk] = r.jan; });
      return out;
    }));
    setDirty(true);
  }

  async function handleSave() {
    if (!scenarioId) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const payload: OccPctBulkRow[] = rows.map(r => ({
        room_type_id: r.room_type_id,
        ...(Object.fromEntries(MONTH_KEYS.map(mk => [mk, pctNum(r[mk]) / 100])) as Record<MonthKey, number>),
      }));
      const res = await saveOccupancyPct(scenarioId, payload);
      setSeeded(false); setDirty(false);
      setMsg(t("savedN", { n: res.saved }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorSaving"));
    } finally { setSaving(false); }
  }

  // ── Noches ocupadas (derivado en vivo): % × unidades × días (0 si cerrado) ──
  function occNights(ri: number, mi: number): number {
    if (closed.has(mi + 1)) return 0;
    const units = unitsById[rows[ri]?.room_type_id] ?? 0;
    return (pctNum(rows[ri][MONTH_KEYS[mi]]) / 100) * units * daysInMonth(year, mi + 1);
  }
  const monthOccTotals = MONTHS.map((_, mi) => rows.reduce((s, _r, ri) => s + occNights(ri, mi), 0));
  const grandOcc = monthOccTotals.reduce((s, v) => s + v, 0);

  // Noches DISPONIBLES = unidades totales × días del mes. Los meses cerrados NO
  // se descuentan del denominador: la capacidad física existe igual, y así el
  // porcentaje coincide con el que ya muestran Planning y el P&L (45.5% en 2027).
  // Si se descontara octubre, esta pantalla diría 49.7% y sería la única.
  const unidadesTotales = rows.reduce((s, r) => s + (unitsById[r.room_type_id] ?? 0), 0);
  const monthAvail = MONTHS.map((_, mi) => unidadesTotales * daysInMonth(year, mi + 1));
  const grandAvail = monthAvail.reduce((s, v) => s + v, 0);
  const pctOcup = (ocupadas: number, disponibles: number) =>
    disponibles ? (ocupadas / disponibles * 100).toFixed(1) + "%" : "—";
  const fmt = fmtInt;

  const sel = scenarios.find(s => s.id === scenarioId);
  const btn = (enabled: boolean): React.CSSProperties => ({
    padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, border: "none",
    cursor: enabled ? "pointer" : "not-allowed",
    background: enabled ? "var(--brand)" : "var(--bg-surface)",
    color: enabled ? "#fff" : "var(--text-disabled)",
  });

  // ── Excel: las DOS grillas, una por hoja ──────────────────────────────────
  async function bajarExcel() {
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const colRT = { label: "Room Type", ancho: 34, formato: "texto" as const };
    // Los % viajan como FRACCIÓN (0.45), no como 45.
    const filasPct: FilaCuadro[] = rows.map(r => ({
      label: rtLabel(codeById[r.room_type_id], r.name), nivel: 1,
      valores: MONTH_KEYS.map(mk => pctNum(r[mk]) / 100),
    }));
    const filasNoches: FilaCuadro[] = rows.map((r, ri) => ({
      label: rtLabel(codeById[r.room_type_id], r.name), nivel: 1,
      valores: [...MONTHS.map((_m, mi) => occNights(ri, mi)),
                MONTHS.reduce((s, _m, mi) => s + occNights(ri, mi), 0)],
    }));
    filasNoches.push({ label: tc("total"), es_total: true, valores: [...monthOccTotals, grandOcc] });
    filasNoches.push({ label: ttr("nightsAvailable"), valores: [...monthAvail, grandAvail] });
    filasNoches.push({
      label: t("overallPct"), es_total: true, formato: "pct",
      // Sin noches disponibles el % no es cero: no aplica → celda vacía.
      valores: [...monthOccTotals.map((t2, mi) => (monthAvail[mi] ? t2 / monthAvail[mi] : null)),
                grandAvail ? grandOcc / grandAvail : null],
    });
    try {
      await bajarCuadros("Ocupacion", [
        {
          titulo: t("title"),
          subtitulo: `${esc} · ${t("xlsPctSubtitle")}`,
          hoja: t("xlsPctSheet"),
          columnas: [colRT, ...MONTHS.map(m => ({ label: m, ancho: 9, formato: "pct" as const }))],
          filas: filasPct,
        },
        {
          titulo: t("nightsTitle"),
          subtitulo: `${esc} · ${t("xlsNightsSubtitle")}`,
          hoja: t("xlsNightsSheet"),
          columnas: [
            colRT,
            ...MONTHS.map(m => ({ label: m, ancho: 10, formato: "num" as const })),
            { label: tc("year"), ancho: 14, formato: "num" as const },
          ],
          filas: filasNoches,
        },
      ]);
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
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 200 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>)}
        </select>
        <PushRevenueButton scenarioId={scenarioId} />
        <div style={{ flex: 1 }} />
        <button onClick={applyJanToAll} disabled={sel?.is_locked || !rows.length}
          style={{ padding: "7px 12px", fontSize: 12, borderRadius: 5, cursor: "pointer",
            background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>
          {t("applyJanToAll", { mes: MONTHS[0] })}
        </button>
        <button onClick={bajarExcel} title={t("excelHint")}
          style={{ ...btn(true), background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>⬇ Excel</button>
        <button onClick={handleSave} disabled={saving || !dirty || sel?.is_locked} style={btn(!saving && dirty && !sel?.is_locked)}>
          {saving ? tc("saving") : dirty ? tc("save") : t("saved")}
        </button>
      </div>

      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 12 }}>
        {t("intro")}
      </p>

      {seeded && <p style={{ color: "var(--accent-amber, #856404)", fontSize: 12, marginBottom: 8 }}>{t("suggested", { hotel: hotel.corto })}</p>}
      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          {/* Grilla 1: % de ocupación (editable) */}
          <table className="fin-table" style={{ minWidth: 1200 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", minWidth: 220 }}>Room Type</th>
                {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 70 }}>{m}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={r.room_type_id}>
                  <td style={{ textAlign: "left", fontWeight: 500 }}>{rtLabel(codeById[r.room_type_id], r.name)}</td>
                  {MONTH_KEYS.map((mk, mi) => (
                    <td key={mk} style={{ padding: "1px 2px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <input className="fin-input mono" value={r[mk]} disabled={sel?.is_locked}
                          onChange={e => setCell(ri, mk, e.target.value)}
                          onPaste={e => handlePaste(ri, mi, e)} onFocus={e => e.target.select()}
                          style={{ flex: 1, minWidth: 0, textAlign: "right", padding: "3px 4px" }} />
                        <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>%</span>
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          {/* Grilla 2: noches ocupadas (calculado) */}
          <h2 style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", margin: "24px 0 8px" }}>
            {t("nightsTitle")}
          </h2>
          <table className="fin-table" style={{ minWidth: 1200 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", minWidth: 220 }}>Room Type</th>
                {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 70 }}>{m}</th>)}
                <th style={{ textAlign: "right", minWidth: 80, borderLeft: "1px solid var(--border)" }}>{tc("year")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => {
                const annual = MONTHS.reduce((s, _m, mi) => s + occNights(ri, mi), 0);
                return (
                  <tr key={r.room_type_id}>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>{rtLabel(codeById[r.room_type_id], r.name)}</td>
                    {MONTHS.map((_m, mi) => (
                      <td key={mi} className="mono" style={{ textAlign: "right", color: occNights(ri, mi) ? "var(--text-primary)" : "var(--text-disabled)" }}>
                        {occNights(ri, mi) ? fmt(occNights(ri, mi)) : "—"}
                      </td>
                    ))}
                    <td className="mono" style={{ textAlign: "right", fontWeight: 600, borderLeft: "1px solid var(--border)" }}>{fmt(annual)}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                <td style={{ textAlign: "left" }}>{tc("total")}</td>
                {monthOccTotals.map((t, mi) => <td key={mi} className="mono" style={{ textAlign: "right" }}>{fmt(t)}</td>)}
                <td className="mono" style={{ textAlign: "right", borderLeft: "1px solid var(--border)" }}>{fmt(grandOcc)}</td>
              </tr>
              <tr style={{ fontWeight: 700 }}>
                <td style={{ textAlign: "left", color: "var(--text-secondary)" }}>
                  {ttr("nightsAvailable")}
                </td>
                {monthAvail.map((d, mi) => (
                  <td key={mi} className="mono" style={{ textAlign: "right", color: "var(--text-secondary)", fontWeight: 500 }}>{fmt(d)}</td>
                ))}
                <td className="mono" style={{ textAlign: "right", color: "var(--text-secondary)", fontWeight: 500, borderLeft: "1px solid var(--border)" }}>{fmt(grandAvail)}</td>
              </tr>
              <tr style={{ fontWeight: 800 }}>
                <td style={{ textAlign: "left", color: "var(--brand)" }}>{t("overall")}</td>
                {monthOccTotals.map((t, mi) => (
                  <td key={mi} className="mono" style={{ textAlign: "right", color: "var(--brand)" }}>
                    {pctOcup(t, monthAvail[mi])}
                  </td>
                ))}
                <td className="mono" style={{ textAlign: "right", color: "var(--brand)", borderLeft: "1px solid var(--border)" }}>
                  {pctOcup(grandOcc, grandAvail)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
