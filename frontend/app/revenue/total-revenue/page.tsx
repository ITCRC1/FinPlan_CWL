"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import {
  getScenarios, getRackRates, getChannelsConfig, getOccupancyPct, getRoomTypes, rtLabel, pushRevenueToCheckbook,
  type Scenario,
} from "@/lib/api";
import { fmtUsd, fmtInt } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

// Mismo estilo que el "⬇ Excel" de Planning · Big Picture.
const excelBtn: React.CSSProperties = {
  padding: "8px 16px", fontSize: 13, fontWeight: 700, borderRadius: 6, cursor: "pointer",
  background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)",
};

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTH_KEYS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"] as const;

interface Row { id: string; code: string; name: string; revenue: number[]; nights: number[]; available: number[]; }

function daysInMonth(year: number, month1: number): number {
  return new Date(year, month1, 0).getDate();
}

export default function TotalRevenuePage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("totalRev");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [rows, setRows] = useState<Row[]>([]);
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
      const [rack, ch, occ, rt] = await Promise.all([
        getRackRates(sid), getChannelsConfig(sid), getOccupancyPct(sid), getRoomTypes(HOTEL_ID, sid),
      ]);
      const year = occ.year;
      const nf = ch.net_factor.map(v => parseFloat(v) || 0);
      const unitsById = Object.fromEntries(rt.room_types.map(r => [r.id, r.units]));
      const codeById: Record<string, string> = Object.fromEntries(rt.room_types.map(r => [r.id, r.code]));
      const closed = new Set(rt.closed_months);
      const rackById = Object.fromEntries(rack.rooms.map(r => [r.room_type_id, MONTH_KEYS.map(mk => parseFloat(r[mk]) || 0)]));

      // Revenue = (rack × net factor) × (% ocupación × unidades × días, 0 si cerrado)
      const computed: Row[] = occ.rooms.map(r => {
        const occPct = MONTH_KEYS.map(mk => parseFloat(r[mk]) || 0);
        const rack12 = rackById[r.room_type_id] ?? Array(12).fill(0);
        const units = unitsById[r.room_type_id] ?? 0;
        const available = MONTHS.map((_m, mi) =>
          closed.has(mi + 1) ? 0 : units * daysInMonth(year, mi + 1));
        const nights = MONTHS.map((_m, mi) => occPct[mi] * available[mi]);
        const revenue = MONTHS.map((_m, mi) => nights[mi] * (rack12[mi] * (nf[mi] || 0)));
        return { id: r.room_type_id, code: codeById[r.room_type_id] ?? "", name: r.name, revenue, nights, available };
      });
      setRows(computed);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const monthTotals = MONTHS.map((_m, mi) => rows.reduce((s, r) => s + r.revenue[mi], 0));
  const monthNights = MONTHS.map((_m, mi) => rows.reduce((s, r) => s + r.nights[mi], 0));
  const monthAvail = MONTHS.map((_m, mi) => rows.reduce((s, r) => s + r.available[mi], 0));
  const grand = monthTotals.reduce((s, v) => s + v, 0);
  const totalNights = monthNights.reduce((s, v) => s + v, 0);
  const totalAvail = monthAvail.reduce((s, v) => s + v, 0);
  const rate = (rev: number, base: number) => (base ? rev / base : 0);
  const fmt = fmtUsd;
  const fmt2 = fmtUsd;

  const [pushing, setPushing] = useState(false);
  const [pushMsg, setPushMsg] = useState<string | null>(null);
  async function pasarAlCheckbook() {
    if (!scenarioId) return;
    setPushing(true); setPushMsg(null);
    try {
      // Primero muestro el antes/después y pido confirmación: mueve el P&L.
      const prev = await pushRevenueToCheckbook(scenarioId, true);
      const m = (n: number) => "$" + Math.round(n).toLocaleString("en-US");
      const cambios = prev.lineas.filter(l => Math.abs(l.dif) >= 1)
        .map(l => `  ${l.linea}: ${m(l.antes)} → ${m(l.despues)}`).join("\n");
      const ok = window.confirm(
        tc("pushRev.confirmHead") + "\n\n" +
        tc("pushRev.total", { antes: m(prev.total_antes), despues: m(prev.total_despues) }) + "\n\n" +
        (cambios ? tc("pushRev.byLine", { lista: cambios }) + "\n\n" : tc("pushRev.noChanges") + "\n\n") +
        tc("pushRev.confirmAsk"));
      if (!ok) { setPushing(false); return; }
      const r = await pushRevenueToCheckbook(scenarioId, false);
      setPushMsg("✓ " + tc("pushRev.done", { antes: m(r.total_antes), despues: m(r.total_despues), noches: "" }));
    } catch (e) {
      setPushMsg("✖ " + (e instanceof Error ? e.message : tc("error")));
    } finally { setPushing(false); }
  }

  // ── Excel: el mismo cuadro que se ve, con los números como NÚMERO ──────────
  async function bajarExcel() {
    const sel = scenarios.find(s => s.id === scenarioId);
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const filas: FilaCuadro[] = rows.map(r => ({
      label: rtLabel(r.code, r.name),
      nivel: 1,
      valores: [...r.revenue, r.revenue.reduce((s, v) => s + v, 0)],
    }));
    filas.push({ label: "Total Revenue", es_total: true, valores: [...monthTotals, grand] });
    filas.push({ label: t("nightsOccupied"), formato: "num", valores: [...monthNights, totalNights] });
    filas.push({ label: t("nightsAvailable"), formato: "num", valores: [...monthAvail, totalAvail] });
    // Sin base (0 noches) la tarifa no es cero: no aplica → celda vacía.
    filas.push({
      label: t("adrLabel"),
      valores: [...monthTotals.map((v, mi) => (monthNights[mi] ? v / monthNights[mi] : null)),
                totalNights ? grand / totalNights : null],
    });
    filas.push({
      label: t("revparLabel"),
      valores: [...monthTotals.map((v, mi) => (monthAvail[mi] ? v / monthAvail[mi] : null)),
                totalAvail ? grand / totalAvail : null],
    });
    try {
      await bajarCuadros("Total_Revenue", [{
        titulo: t("title"),
        subtitulo: `${esc} · ${t("xlsSubtitle")}`,
        hoja: "Total Revenue",
        columnas: [
          { label: "Room Type", ancho: 34, formato: "texto" },
          ...MONTHS.map(m => ({ label: m, formato: "usd2" as const })),
          { label: tc("year"), ancho: 16, formato: "usd2" as const },
        ],
        filas,
      }]);
    } catch (e) {
      setPushMsg("✖ " + (e instanceof Error ? e.message : t("excelFailed")));
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
        <div style={{ flex: 1 }} />
        <button onClick={bajarExcel} title={t("excelHint")} style={excelBtn}>⬇ Excel</button>
        <button onClick={pasarAlCheckbook} disabled={pushing || !scenarioId}
          title={t("pushHint")}
          style={{ padding: "8px 16px", fontSize: 13, fontWeight: 600, borderRadius: 6, border: "none",
                   cursor: pushing ? "default" : "pointer",
                   background: pushing ? "#555" : "var(--accent-excel)", color: "#fff" }}>
          {pushing ? tc("pushRev.running") : tc("pushRev.button")}
        </button>
      </div>
      {pushMsg && (
        <div style={{ fontSize: 12.5, marginTop: 8, padding: "8px 12px", borderRadius: 6,
                      background: "var(--bg-surface)", border: "1px solid var(--border-medium)",
                      color: pushMsg.startsWith("✖") ? "var(--accent-red, #C0392B)" : "var(--accent-green, #1A7F4B)" }}>
          {pushMsg}
        </div>
      )}
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 12 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b> })}
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
                {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 86 }}>{m}</th>)}
                <th style={{ textAlign: "right", minWidth: 110, borderLeft: "1px solid var(--border)" }}>{tc("year")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const annual = r.revenue.reduce((s, v) => s + v, 0);
                return (
                  <tr key={r.id}>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>{rtLabel(r.code, r.name)}</td>
                    {r.revenue.map((v, mi) => (
                      <td key={mi} className="mono" style={{ textAlign: "right", color: v ? "var(--text-primary)" : "var(--text-disabled)" }}>{fmt(v)}</td>
                    ))}
                    <td className="mono" style={{ textAlign: "right", fontWeight: 600, borderLeft: "1px solid var(--border)" }}>{fmt(annual)}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                <td style={{ textAlign: "left" }}>Total Revenue</td>
                {monthTotals.map((t, mi) => <td key={mi} className="mono" style={{ textAlign: "right" }}>{fmt(t)}</td>)}
                <td className="mono" style={{ textAlign: "right", borderLeft: "1px solid var(--border)", color: "var(--brand)" }}>{fmt(grand)}</td>
              </tr>
              <tr style={{ color: "var(--text-secondary)" }}>
                <td style={{ textAlign: "left" }}>{t("nightsOccupied")}</td>
                {monthNights.map((n, mi) => <td key={mi} className="mono" style={{ textAlign: "right" }}>{fmtInt(n)}</td>)}
                <td className="mono" style={{ textAlign: "right", borderLeft: "1px solid var(--border)" }}>{fmtInt(totalNights)}</td>
              </tr>
              <tr style={{ color: "var(--text-secondary)" }}>
                <td style={{ textAlign: "left" }}>{t("nightsAvailable")}</td>
                {monthAvail.map((n, mi) => <td key={mi} className="mono" style={{ textAlign: "right" }}>{fmtInt(n)}</td>)}
                <td className="mono" style={{ textAlign: "right", borderLeft: "1px solid var(--border)" }}>{fmtInt(totalAvail)}</td>
              </tr>
              <tr style={{ fontWeight: 600, color: "var(--brand)" }}>
                <td style={{ textAlign: "left" }}>{t("adrLabel")}</td>
                {monthTotals.map((t, mi) => <td key={mi} className="mono" style={{ textAlign: "right" }}>{fmt2(rate(t, monthNights[mi]))}</td>)}
                <td className="mono" style={{ textAlign: "right", borderLeft: "1px solid var(--border)" }}>{fmt2(rate(grand, totalNights))}</td>
              </tr>
              <tr style={{ fontWeight: 600, color: "var(--brand)" }}>
                <td style={{ textAlign: "left" }}>{t("revparLabel")}</td>
                {monthTotals.map((t, mi) => <td key={mi} className="mono" style={{ textAlign: "right" }}>{fmt2(rate(t, monthAvail[mi]))}</td>)}
                <td className="mono" style={{ textAlign: "right", borderLeft: "1px solid var(--border)" }}>{fmt2(rate(grand, totalAvail))}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
