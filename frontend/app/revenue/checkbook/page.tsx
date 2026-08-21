"use client";
import { usePlanningScenario, usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import AvisoLineasObligatorias from "@/components/AvisoLineasObligatorias";
import { useTranslations } from "next-intl";
import { money2 } from "@/lib/fmt";
import { useEffect, useState, useCallback } from "react";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type Cuadro, type ColumnaCuadro, type FilaCuadro } from "@/lib/exportCuadro";
import {
  getScenarios, getRevenueCheckbook, saveRevenueCheckbook, setRevenueSource,
  getRoomTypes, getOccupancyPct, getRackRates, getChannelsConfig,
  getDriverRatesSeed,
  type Scenario, type RevenueCheckbookRow, type RevenueSource,
  type RevenueBulkRow, type MonthKey,
} from "@/lib/api";
import { recalcularYContar } from "@/lib/recalcular";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTH_KEYS: MonthKey[] = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];

function daysInMonth(year: number, month1: number): number {
  return new Date(year, month1, 0).getDate();
}

interface RoomStats {
  available: number[]; occupied: number[]; roomRev: number[];
  netFactor: number[];     // factor neto de canales por mes
  paxPerNight: number;     // pax por noche ocupada
}

// Tarifas del paquete Classic (rack, se les aplica el net factor de canales).
// Food = Full Board / pax / noche · Tours = San Pedrillo + Caño / pax / estadía ·
// Transport = traslado / pax / estadía.
//
// YA NO ESTÁN ESCRITAS ACÁ. Eran nueve números fijos dentro de esta pantalla y
// son el producto de Corcovado —traslado Sierpe/Drake, San Pedrillo, Isla del
// Caño—: viajaban en el bundle, así que una propiedad nueva abría este checkbook
// con las tarifas de otro hotel y a un clic de guardarlas. Ahora vienen de
// `backend/app/seed_data/<HOTEL_ID>/driver_rates.json`.
//
// Sin semilla el botón queda apagado: llenar doce meses con ceros se ve igual
// que llenarlos bien, y eso es peor que no llenar nada.
const SIN_TARIFAS = {
  food: 0, tours: 0, transport: 0, nightsPerStay: 1, bevRatio: 0,
  retailPct: 0, innoceanaPct: 0, sustRate: 0, sustNonPay: 0,
};
type DriverRatesUI = typeof SIN_TARIFAS;

function num(v: string): number {
  const n = parseFloat((v || "").toString().replace(/[, $]/g, ""));
  return isNaN(n) ? 0 : n;
}
function fmtUsd(v: string | number): string {
  const n = typeof v === "string" ? num(v) : v;
  if (!n) return "—";
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${s})` : s;
}
function rowTotal(r: RevenueCheckbookRow): number {
  return MONTH_KEYS.reduce((s, mk) => s + num(r[mk]), 0);
}

const btnStyle = (enabled: boolean): React.CSSProperties => ({
  padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600,
  cursor: enabled ? "pointer" : "not-allowed", border: "none",
  background: enabled ? "var(--brand)" : "var(--bg-surface)",
  color: enabled ? "#fff" : "var(--text-disabled)",
});

export default function RevenueCheckbookPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("revCheckbook");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [rows, setRows] = useState<RevenueCheckbookRow[]>([]);
  const [stats, setStats] = useState<RoomStats | null>(null);
  const [source, setSource] = useState<RevenueSource>("drivers");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recalc, setRecalc] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rates, setRates] = useState<DriverRatesUI>(SIN_TARIFAS);

  // Las tarifas de ESTA propiedad. Si no trae, el botón queda apagado.
  useEffect(() => {
    (async () => {
      try {
        const s = await getDriverRatesSeed();
        const r = s.tarifas ?? {};
        if (!s.seeded) return;
        setRates({
          food: r.food ?? 0, tours: r.tours ?? 0, transport: r.transport ?? 0,
          nightsPerStay: r.nights_per_stay ?? 1, bevRatio: r.bev_ratio ?? 0,
          retailPct: r.retail_pct ?? 0, innoceanaPct: r.innoceana_pct ?? 0,
          sustRate: r.sust_rate ?? 0, sustNonPay: r.sust_non_pay ?? 0,
        });
      } catch { /* sin semilla: el botón queda apagado y la pantalla lo dice */ }
    })();
  }, []);

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
      const [cb, rt, occ, rack, ch] = await Promise.all([
        getRevenueCheckbook(sid), getRoomTypes(HOTEL_ID, sid),
        getOccupancyPct(sid), getRackRates(sid), getChannelsConfig(sid),
      ]);
      setRows(cb.lines.map(l => ({ ...l, ...Object.fromEntries(MONTH_KEYS.map(mk => [mk, money2(l[mk])])) })));
      setSource(cb.source);

      // KPIs de Rooms desde los drivers (mismo cálculo que Total Revenue)
      const year = occ.year;
      const closed = new Set(rt.closed_months);
      const unitsById = Object.fromEntries(rt.room_types.map(r => [r.id, r.units]));
      const nf = ch.net_factor.map(v => parseFloat(v) || 0);
      const rackById = Object.fromEntries(rack.rooms.map(r => [r.room_type_id, MONTH_KEYS.map(mk => parseFloat(r[mk]) || 0)]));
      const available = MONTHS.map((_m, mi) =>
        rt.room_types.reduce((s, r) => s + (closed.has(mi + 1) ? 0 : r.units * daysInMonth(year, mi + 1)), 0));
      const occupied = MONTHS.map((_m, mi) =>
        occ.rooms.reduce((s, r) => {
          if (closed.has(mi + 1)) return s;
          const u = unitsById[r.room_type_id] ?? 0;
          return s + (parseFloat(r[MONTH_KEYS[mi]]) || 0) * u * daysInMonth(year, mi + 1);
        }, 0));
      const roomRev = MONTHS.map((_m, mi) =>
        occ.rooms.reduce((s, r) => {
          if (closed.has(mi + 1)) return s;
          const u = unitsById[r.room_type_id] ?? 0;
          const nights = (parseFloat(r[MONTH_KEYS[mi]]) || 0) * u * daysInMonth(year, mi + 1);
          const rk = (rackById[r.room_type_id]?.[mi]) || 0;
          return s + nights * rk * (nf[mi] || 0);
        }, 0));
      setStats({ available, occupied, roomRev, netFactor: nf, paxPerNight: parseFloat(rt.pax_per_night) || 1.8 });
      setDirty(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  function setCell(rowIdx: number, mk: MonthKey, value: string) {
    setRows(prev => prev.map((r, i) => i === rowIdx ? { ...r, [mk]: value } : r));
    setDirty(true);
  }

  // Excel-style paste: distribute a tab/newline block starting at (rowIdx, monthIdx).
  function handlePaste(rowIdx: number, monthIdx: number, e: React.ClipboardEvent) {
    const text = e.clipboardData.getData("text");
    if (!text || (!text.includes("\t") && !text.includes("\n"))) return; // single value → default
    e.preventDefault();
    const grid = text.replace(/\r/g, "").split("\n").filter(l => l.length).map(l => l.split("\t"));
    setRows(prev => {
      const next = prev.map(r => ({ ...r }));
      grid.forEach((cells, dr) => {
        const ri = rowIdx + dr;
        if (ri >= next.length) return;
        cells.forEach((cell, dc) => {
          const mi = monthIdx + dc;
          if (mi >= MONTH_KEYS.length) return;
          next[ri][MONTH_KEYS[mi]] = money2(cell);
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
      const payload: RevenueBulkRow[] = rows.map(r => ({
        line: r.line,
        ...(Object.fromEntries(MONTH_KEYS.map(mk => [mk, num(r[mk])])) as Record<MonthKey, number>),
      }));
      const res = await saveRevenueCheckbook(scenarioId, payload);
      setDirty(false);
      setMsg(t("savedN", { n: res.saved }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorSaving"));
    } finally {
      setSaving(false);
    }
  }

  async function toggleSource(next: RevenueSource) {
    if (!scenarioId || next === source) return;
    setSource(next);
    try {
      await setRevenueSource(scenarioId, next);
      setMsg(next === "checkbook" ? t("sourceCheckbookMsg") : t("sourceDriversMsg"));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
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

  // ¿Hay con qué llenar? No importa si vino de la semilla o lo digitó el
  // usuario: lo que no puede pasar es llenar doce meses de ceros, que en
  // pantalla se ve idéntico a haberlos llenado bien.
  const hayTarifas = rates.food > 0 || rates.tours > 0 || rates.transport > 0
    || rates.sustRate > 0 || rates.retailPct > 0 || rates.innoceanaPct > 0;

  // Llena Room/Food/Tours/Transport desde los drivers (ocupación → pax-noche).
  // Food = per pax/noche → cantidad = pax-noche. Tours/Transport = per pax/estadía
  // → cantidad = estadías = pax-noche / noches por estadía. Tarifa × net factor del mes.
  function fillFromDrivers() {
    if (!stats || sel?.is_locked) return;
    if (!hayTarifas) {
      setError(t("noRatesToFill"));
      return;
    }
    const { occupied, roomRev, netFactor, paxPerNight } = stats;
    const np = rates.nightsPerStay || 1;
    const food = occupied.map((occ, i) => occ * paxPerNight * rates.food * (netFactor[i] || 0));
    const vals: Record<string, number[]> = {
      ROOMS: roomRev.slice(),
      FOOD: food,
      ACTIVITIES: occupied.map((occ, i) => (occ * paxPerNight / np) * rates.tours * (netFactor[i] || 0)),
      TRANSPORT: occupied.map((occ, i) => (occ * paxPerNight / np) * rates.transport * (netFactor[i] || 0)),
      BEVERAGE: food.map(f => f * rates.bevRatio / 100),
      RETAIL: roomRev.map(r => r * rates.retailPct / 100),
      INNOCEANA: roomRev.map(r => r * rates.innoceanaPct / 100),
      // Sustainability: fee por noche ocupada, sin net factor; descuenta el % que no paga.
      SUSTAINABILITY: occupied.map(occ => occ * rates.sustRate * (1 - rates.sustNonPay / 100)),
    };
    setRows(prev => prev.map(r => {
      const v = vals[r.line];
      if (!v) return r;
      const upd = { ...r };
      MONTH_KEYS.forEach((mk, i) => { upd[mk] = money2(v[i]); });
      return upd;
    }));
    setDirty(true);
    setMsg(t("filledFromDrivers"));
  }

  const monthTotals = MONTH_KEYS.map(mk => rows.reduce((s, r) => s + num(r[mk]), 0));
  const grandTotal = monthTotals.reduce((s, v) => s + v, 0);
  const sel = scenarios.find(s => s.id === scenarioId);

  // Baja lo que está en pantalla: los KPIs de Rooms y el checkbook completo,
  // con lo que el usuario tenga digitado (no lo último guardado).
  async function bajarExcel() {
    const escenario = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const colsMes = (fmt: ColumnaCuadro["formato"], ultima: string): ColumnaCuadro[] => [
      ...MONTHS.map(m => ({ label: m, ancho: 12, formato: fmt })),
      { label: ultima, ancho: 15, formato: fmt },
    ];
    const cuadros: Cuadro[] = [];

    if (stats) {
      const tAvail = stats.available.reduce((s, v) => s + v, 0);
      const tOcc = stats.occupied.reduce((s, v) => s + v, 0);
      const tRev = stats.roomRev.reduce((s, v) => s + v, 0);
      cuadros.push({
        titulo: t("xlsRoomsTitle"),
        subtitulo: escenario || undefined,
        hoja: "Rooms KPIs",
        columnas: [{ label: "Rooms", ancho: 30, formato: "texto" }, ...colsMes("num", "Full Year")],
        filas: [
          { label: "Total Rooms Available", valores: [...stats.available, tAvail] },
          { label: "Total Rooms Occupied", valores: [...stats.occupied, tOcc] },
          { label: "Total Pax", valores: [...stats.occupied.map(v => v * stats.paxPerNight), tOcc * stats.paxPerNight] },
          {
            label: "Occupancy %", formato: "pct",
            // Fracción, no 12.5: el % en Excel se guarda como 0.125.
            valores: [...stats.occupied.map((v, i) => stats.available[i] ? v / stats.available[i] : null),
              tAvail ? tOcc / tAvail : null],
          },
          {
            label: "ADR", formato: "usd2",
            valores: [...stats.roomRev.map((v, i) => stats.occupied[i] ? v / stats.occupied[i] : null),
              tOcc ? tRev / tOcc : null],
          },
        ],
      });
    }

    // Celda vacía en pantalla = celda vacía en el Excel. Un cero digitado sí es cero.
    const celda = (v: string) => (v ?? "").toString().trim() === "" ? null : num(v);
    const filas: FilaCuadro[] = rows.map(r => ({
      label: r.account ? `${r.account} · ${r.label}` : r.label,
      valores: [...MONTH_KEYS.map(mk => celda(r[mk])), rowTotal(r)],
    }));
    filas.push({ label: "TOTAL REVENUE", es_total: true, valores: [...monthTotals, grandTotal] });

    cuadros.push({
      titulo: t("xlsCheckbookTitle"),
      subtitulo: [escenario, `${t("plSource")} ${source === "checkbook" ? "Checkbook" : "Drivers"}`]
        .filter(Boolean).join(" · "),
      hoja: "Revenue Checkbook",
      columnas: [{ label: tc("line"), ancho: 34, formato: "texto" }, ...colsMes("usd2", tc("total"))],
      filas,
    });

    try {
      await bajarCuadros("Revenue_Checkbook", cuadros);
    } catch (e: unknown) {
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
        <select
          value={scenarioId}
          onChange={e => setScenarioId(e.target.value)}
          className="fin-input"
          style={{ minWidth: 220 }}
        >
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>
              {s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}
            </option>
          ))}
        </select>
      </div>

      <AvisoLineasObligatorias scenarioId={scenarioId} />

      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>

      {/* Source toggle */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "14px 0" }}>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{t("plSource")}</span>
        <div style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
          {(["drivers", "checkbook"] as RevenueSource[]).map(opt => (
            <button
              key={opt}
              onClick={() => toggleSource(opt)}
              disabled={sel?.is_locked}
              style={{
                padding: "6px 14px", fontSize: 13, border: "none", cursor: "pointer",
                background: source === opt ? "#2962FF" : "transparent",
                color: source === opt ? "#fff" : "var(--text-secondary)",
              }}
            >
              {opt === "drivers" ? t("optDrivers") : t("optCheckbook")}
            </button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <button onClick={handleSave} disabled={saving || !dirty || sel?.is_locked}
          style={btnStyle(!saving && dirty && !sel?.is_locked)}>
          {saving ? tc("saving") : dirty ? tc("save") : t("saved")}
        </button>
        <button onClick={handleRecalc} disabled={recalc || sel?.is_locked}
          style={btnStyle(!recalc && !sel?.is_locked)}>
          {recalc ? tc("recalc.running") : t("recalcPl")}
        </button>
        <button onClick={bajarExcel} title={t("excelHint")}
          style={{ ...btnStyle(true), background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>

      {/* Llenar desde drivers */}
      <div style={{
        display: "flex", alignItems: "flex-end", gap: 14, flexWrap: "wrap",
        padding: "12px 14px", marginBottom: 12, borderRadius: 8,
        border: "1px solid var(--border)", background: "var(--bg-surface)",
      }}>
        {([
          ["food", t("drvFood")],
          ["tours", t("drvTours")],
          ["transport", t("drvTransport")],
          ["nightsPerStay", t("drvNightsPerStay")],
          ["bevRatio", t("drvBevRatio")],
          ["retailPct", t("drvRetailPct")],
          ["innoceanaPct", t("drvInnoceanaPct")],
          ["sustRate", t("drvSustRate")],
          ["sustNonPay", t("drvSustNonPay")],
        ] as [keyof typeof rates, string][]).map(([key, label]) => (
          <label key={key} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
            {label}
            <input
              className="fin-input mono"
              type="number"
              value={rates[key]}
              disabled={sel?.is_locked}
              onChange={e => setRates(r => ({ ...r, [key]: parseFloat(e.target.value) || 0 }))}
              style={{ width: 110, textAlign: "right", padding: "4px 6px" }}
            />
          </label>
        ))}
        <button onClick={fillFromDrivers} disabled={!stats || !hayTarifas || sel?.is_locked}
          style={btnStyle(!!stats && hayTarifas && !sel?.is_locked)}>
          {t("fillFromDrivers")}
        </button>
        <span style={{ fontSize: 11, color: "var(--text-disabled)", maxWidth: 320 }}>
          {t("fillHint")}
        </span>
      </div>

      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
      {source === "drivers" && (
        <div style={{ fontSize: 12, color: "var(--text-disabled)", marginBottom: 8 }}>
          {t.rich("driversNote", { b: (c: React.ReactNode) => <b>{c}</b> })}
        </div>
      )}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <>
        {stats && (() => {
          const tAvail = stats.available.reduce((s, v) => s + v, 0);
          const tOcc = stats.occupied.reduce((s, v) => s + v, 0);
          const tRev = stats.roomRev.reduce((s, v) => s + v, 0);
          const numCell = (n: number) => Math.round(n).toLocaleString("en-US");
          const pctCell = (occ: number, av: number) => av ? (occ / av * 100).toFixed(1) + "%" : "—";
          const adrCell = (rev: number, occ: number) => occ ? "$" + (rev / occ).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
          const td: React.CSSProperties = { textAlign: "right" };
          const yr: React.CSSProperties = { textAlign: "right", borderLeft: "1px solid var(--border)", fontWeight: 600 };
          return (
            <div className="fin-sticky" style={{ overflowX: "auto", marginBottom: 16 }}>
              <table className="fin-table" style={{ minWidth: 1200 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", minWidth: 150 }}>Rooms</th>
                    {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 80 }}>{m}</th>)}
                    <th style={{ textAlign: "right", minWidth: 100, borderLeft: "1px solid var(--border)" }}>Full Year</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>Total Rooms Available</td>
                    {stats.available.map((v, i) => <td key={i} className="mono" style={td}>{numCell(v)}</td>)}
                    <td className="mono" style={yr}>{numCell(tAvail)}</td>
                  </tr>
                  <tr>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>Total Rooms Occupied</td>
                    {stats.occupied.map((v, i) => <td key={i} className="mono" style={td}>{numCell(v)}</td>)}
                    <td className="mono" style={yr}>{numCell(tOcc)}</td>
                  </tr>
                  <tr>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>Total Pax</td>
                    {stats.occupied.map((v, i) => <td key={i} className="mono" style={td}>{numCell(v * stats.paxPerNight)}</td>)}
                    <td className="mono" style={yr}>{numCell(tOcc * stats.paxPerNight)}</td>
                  </tr>
                  <tr>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>Occupancy %</td>
                    {stats.occupied.map((v, i) => <td key={i} className="mono" style={td}>{pctCell(v, stats.available[i])}</td>)}
                    <td className="mono" style={{ ...yr, color: "var(--brand)" }}>{pctCell(tOcc, tAvail)}</td>
                  </tr>
                  <tr>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>ADR</td>
                    {stats.roomRev.map((v, i) => <td key={i} className="mono" style={td}>{adrCell(v, stats.occupied[i])}</td>)}
                    <td className="mono" style={{ ...yr, color: "var(--brand)" }}>{adrCell(tRev, tOcc)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          );
        })()}
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1200 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", minWidth: 150 }}>{tc("line")}</th>
                {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 80 }}>{m}</th>)}
                <th style={{ textAlign: "right", minWidth: 100, borderLeft: "1px solid var(--border)" }}>Total</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={r.line}>
                  <td style={{ textAlign: "left", fontWeight: 500 }}>
                    {/* La cuenta va al lado del nombre donde la línea ES una
                        cuenta — hoy las tres del Club. Ver el ojo del backend:
                        4500/4501/4502 los comparten tres departamentos, así que
                        el número solo no identifica nada. */}
                    {r.account && (
                      <span className="mono" style={{ color: "var(--text-disabled)", marginRight: 8 }}>
                        {r.account}
                      </span>
                    )}
                    {r.label}
                  </td>
                  {MONTH_KEYS.map((mk, mi) => (
                    <td key={mk} style={{ padding: "1px 2px" }}>
                      <input
                        className="fin-input mono"
                        value={r[mk]}
                        disabled={sel?.is_locked}
                        onChange={e => setCell(ri, mk, e.target.value)}
                        onPaste={e => handlePaste(ri, mi, e)}
                        onFocus={e => e.target.select()}
                        style={{ width: "100%", textAlign: "right", padding: "3px 4px" }}
                      />
                    </td>
                  ))}
                  <td className="mono" style={{ textAlign: "right", fontWeight: 600, borderLeft: "1px solid var(--border)" }}>
                    {fmtUsd(rowTotal(r))}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                <td style={{ textAlign: "left" }}>TOTAL REVENUE</td>
                {monthTotals.map((t, i) => (
                  <td key={i} className="mono" style={{ textAlign: "right" }}>{fmtUsd(t)}</td>
                ))}
                <td className="mono" style={{ textAlign: "right", borderLeft: "1px solid var(--border)" }}>{fmtUsd(grandTotal)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        </>
      )}
    </div>
  );
}
