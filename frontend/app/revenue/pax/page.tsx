"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import PushRevenueButton from "@/components/PushRevenueButton";
import {
  getScenarios, getOccupancyPct, getRoomTypes, setPaxPerNight, rtLabel,
  type Scenario,
} from "@/lib/api";
import { fmtInt } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

const excelBtn: React.CSSProperties = {
  padding: "7px 16px", fontSize: 13, fontWeight: 700, borderRadius: 5, cursor: "pointer",
  background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)",
};
const MONTH_KEYS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"] as const;

// noches ocupadas por tipo de habitación (independiente del factor pax)
interface Row { id: string; code: string; name: string; nights: number[]; }

function daysInMonth(year: number, month1: number): number {
  return new Date(year, month1, 0).getDate();
}

export default function PaxPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("pax");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [rows, setRows] = useState<Row[]>([]);
  const [pax, setPax] = useState("1.8");       // factor editable
  const [savedPax, setSavedPax] = useState("1.8");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
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
    setLoading(true);
    try {
      const [occ, rt] = await Promise.all([getOccupancyPct(sid), getRoomTypes(HOTEL_ID, sid)]);
      const year = occ.year;
      const unitsById = Object.fromEntries(rt.room_types.map(r => [r.id, r.units]));
      const codeById: Record<string, string> = Object.fromEntries(rt.room_types.map(r => [r.id, r.code]));
      const closed = new Set(rt.closed_months);
      setPax(rt.pax_per_night); setSavedPax(rt.pax_per_night);
      // noches ocupadas = % ocupación × unidades × días (0 si cerrado)
      const computed: Row[] = occ.rooms.map(r => {
        const units = unitsById[r.room_type_id] ?? 0;
        const nights = MONTHS.map((_m, mi) =>
          closed.has(mi + 1) ? 0 : (parseFloat(r[MONTH_KEYS[mi]]) || 0) * units * daysInMonth(year, mi + 1));
        return { id: r.room_type_id, code: codeById[r.room_type_id] ?? "", name: r.name, nights };
      });
      setRows(computed);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const factor = parseFloat(pax) || 0;
  const paxOf = (r: Row, mi: number) => r.nights[mi] * factor;
  const monthTotals = MONTHS.map((_m, mi) => rows.reduce((s, r) => s + paxOf(r, mi), 0));
  const grand = monthTotals.reduce((s, v) => s + v, 0);
  const fmt = fmtInt;

  async function savePax() {
    setSaving(true); setError(null);
    try {
      const v = parseFloat(pax) || 0;
      await setPaxPerNight(HOTEL_ID, v);
      setSavedPax(String(v));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorSaving"));
    } finally { setSaving(false); }
  }

  // ── Excel: la misma grilla, con el pax como número ────────────────────────
  async function bajarExcel() {
    const sel = scenarios.find(s => s.id === scenarioId);
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const filas: FilaCuadro[] = rows.map(r => ({
      label: rtLabel(r.code, r.name), nivel: 1,
      valores: [...MONTHS.map((_m, mi) => paxOf(r, mi)),
                MONTHS.reduce((s, _m, mi) => s + paxOf(r, mi), 0)],
    }));
    filas.push({ label: "Total Pax", es_total: true, valores: [...monthTotals, grand] });
    try {
      await bajarCuadros("Pax", [{
        titulo: t("title"),
        subtitulo: `${esc} · ${t("xlsSubtitle", { factor })}`,
        hoja: "Pax",
        columnas: [
          { label: "Room Type", ancho: 34, formato: "texto" },
          ...MONTHS.map(m => ({ label: m, ancho: 10, formato: "num" as const })),
          { label: tc("year"), ancho: 14, formato: "num" as const },
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
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 200 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>)}
        </select>
        <PushRevenueButton scenarioId={scenarioId} />
        <button onClick={bajarExcel} title={t("excelHint")} style={excelBtn}>⬇ Excel</button>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{t("paxPerNight")}</span>
        <input className="fin-input mono" value={pax} onChange={e => setPax(e.target.value)}
          onFocus={e => e.target.select()} style={{ width: 70, textAlign: "right" }} />
        <button onClick={savePax} disabled={saving || pax === savedPax}
          style={{ padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, border: "none",
            cursor: (saving || pax === savedPax) ? "not-allowed" : "pointer",
            background: (saving || pax === savedPax) ? "var(--bg-surface)" : "var(--brand)",
            color: (saving || pax === savedPax) ? "var(--text-disabled)" : "#fff" }}>
          {saving ? tc("saving") : pax === savedPax ? t("saved") : tc("save")}
        </button>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 12 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b>, factor })}
      </p>

      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1200 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", minWidth: 220 }}>Room Type</th>
                {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 72 }}>{m}</th>)}
                <th style={{ textAlign: "right", minWidth: 90, borderLeft: "1px solid var(--border)" }}>{tc("year")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const annual = MONTHS.reduce((s, _m, mi) => s + paxOf(r, mi), 0);
                return (
                  <tr key={r.id}>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>{rtLabel(r.code, r.name)}</td>
                    {MONTHS.map((_m, mi) => {
                      const v = paxOf(r, mi);
                      return <td key={mi} className="mono" style={{ textAlign: "right", color: v ? "var(--text-primary)" : "var(--text-disabled)" }}>{fmt(v)}</td>;
                    })}
                    <td className="mono" style={{ textAlign: "right", fontWeight: 600, borderLeft: "1px solid var(--border)" }}>{fmt(annual)}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                <td style={{ textAlign: "left" }}>Total Pax</td>
                {monthTotals.map((t, mi) => <td key={mi} className="mono" style={{ textAlign: "right" }}>{fmt(t)}</td>)}
                <td className="mono" style={{ textAlign: "right", borderLeft: "1px solid var(--border)", color: "var(--brand)" }}>{fmt(grand)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
