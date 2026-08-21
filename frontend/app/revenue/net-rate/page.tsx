"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import PushRevenueButton from "@/components/PushRevenueButton";
import {
  getScenarios, getRackRates, getChannelsConfig,
  type Scenario,
} from "@/lib/api";
import { fmtUsd } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTH_KEYS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"] as const;

const excelBtn: React.CSSProperties = {
  padding: "7px 16px", fontSize: 13, fontWeight: 700, borderRadius: 5, cursor: "pointer",
  background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)",
};

interface NetRow { room_type_id: string; name: string; rack: number[]; }

export default function NetRatePage() {
  const tc = useTranslations("common");
  const t = useTranslations("netRate");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [rows, setRows] = useState<NetRow[]>([]);
  const [netFactor, setNetFactor] = useState<number[]>(Array(12).fill(0));
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
      const [rack, ch] = await Promise.all([getRackRates(sid), getChannelsConfig(sid)]);
      setRows(rack.rooms.map(r => ({
        room_type_id: r.room_type_id, name: r.name,
        rack: MONTH_KEYS.map(mk => parseFloat(r[mk]) || 0),
      })));
      setNetFactor(ch.net_factor.map(v => parseFloat(v) || 0));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const fmt = fmtUsd;

  // ── Excel: la misma grilla, con las tarifas como número ───────────────────
  async function bajarExcel() {
    const sel = scenarios.find(s => s.id === scenarioId);
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    // El net factor es una fracción (0.75) → va como % para no perder decimales.
    const filas: FilaCuadro[] = [{
      label: "Net Factor", es_total: true, formato: "pct",
      valores: netFactor.map(nf => nf),
    }];
    for (const r of rows) {
      filas.push({
        label: r.name, nivel: 1,
        valores: r.rack.map((rk, mi) => rk * (netFactor[mi] || 0)),
      });
    }
    try {
      await bajarCuadros("Net_Rate", [{
        titulo: "Net Rate",
        subtitulo: `${esc} · ${t("xlsSubtitle")}`,
        hoja: "Net Rate",
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
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>Net Rate</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 200 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>)}
        </select>
        <PushRevenueButton scenarioId={scenarioId} />
        <button onClick={bajarExcel} title={t("excelHint")} style={excelBtn}>⬇ Excel</button>
      </div>
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
                {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 78 }}>{m}</th>)}
              </tr>
            </thead>
            <tbody>
              <tr style={{ color: "var(--brand)" }}>
                <td style={{ textAlign: "left", fontWeight: 600 }}>Net Factor</td>
                {netFactor.map((nf, mi) => <td key={mi} className="mono" style={{ textAlign: "right" }}>{nf.toFixed(4)}</td>)}
              </tr>
              {rows.map(r => (
                <tr key={r.room_type_id}>
                  <td style={{ textAlign: "left", fontWeight: 500 }}>{r.name}</td>
                  {r.rack.map((rk, mi) => (
                    <td key={mi} className="mono" style={{ textAlign: "right", color: rk ? "var(--text-primary)" : "var(--text-disabled)" }}>
                      {fmt(rk * (netFactor[mi] || 0))}
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
