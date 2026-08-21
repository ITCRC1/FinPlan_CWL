"use client";
import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getPLMonthly, getAssignments, getExpenseTotals,
  getRoomTypes, getOccupancyPct, getRackRates, getChannelsConfig,
  type Scenario, type SectionRow,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro, type FormatoCol } from "@/lib/exportCuadro";
import { elegir, useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const MK = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"] as const;
function daysIn(year: number, m1: number): number { return new Date(year, m1, 0).getDate(); }

type Exp = { payroll: number; cos: number; opex: number };
type RoomKpis = { avail: number; occ: number; pax: number; occPct: number; adr: number; revpar: number };
type Vals = { annual: Record<string, number>; exp: Exp | null; months: { kpis: { rooms_available: number; rooms_occupied: number; guests: number } }[] };
type Snap = { id: string; label: string; vals: Vals; kpis: RoomKpis | null };

const GREEN = "var(--accent-green, #1A7F4B)", RED = "var(--accent-red, #C0392B)";

function kpisFromPL(v: Vals): RoomKpis {
  let avail = 0, occ = 0, pax = 0;
  for (const m of v.months) { avail += m.kpis.rooms_available; occ += m.kpis.rooms_occupied; pax += m.kpis.guests; }
  const rr = v.annual["REV_ROOMS"] ?? 0;
  return { avail, occ, pax, occPct: avail ? occ / avail * 100 : 0, adr: occ ? rr / occ : 0, revpar: avail ? rr / avail : 0 };
}
async function fetchRoomKpis(sid: string): Promise<RoomKpis> {
  const [rt, occ, rack, ch] = await Promise.all([
    getRoomTypes(HOTEL_ID, sid), getOccupancyPct(sid), getRackRates(sid), getChannelsConfig(sid),
  ]);
  const year = occ.year;
  const closed = new Set(rt.closed_months);
  const units = Object.fromEntries(rt.room_types.map(r => [r.id, r.units]));
  const ppn = parseFloat(rt.pax_per_night) || 1.8;
  const nf = ch.net_factor.map(v => parseFloat(v) || 0);
  const rackById = Object.fromEntries(rack.rooms.map(r => [r.room_type_id, MK.map(k => parseFloat(r[k]) || 0)]));
  let avail = 0, occN = 0, roomRev = 0;
  MK.forEach((_k, mi) => {
    if (closed.has(mi + 1)) return;
    const days = daysIn(year, mi + 1);
    occ.rooms.forEach(r => {
      const u = units[r.room_type_id] ?? 0; avail += u * days;
      const nights = (parseFloat(r[MK[mi]]) || 0) * u * days; occN += nights;
      roomRev += nights * ((rackById[r.room_type_id]?.[mi]) || 0) * (nf[mi] || 0);
    });
  });
  return { avail, occ: occN, pax: occN * ppn, occPct: avail ? occN / avail * 100 : 0, adr: occN ? roomRev / occN : 0, revpar: avail ? roomRev / avail : 0 };
}

const usd2 = (v: number) => {
  const s = "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return v < 0 ? "(" + s + ")" : s;
};
const intf = (v: number) => Math.round(v).toLocaleString("en-US");
function money(n: number): string {
  if (!n) return "—";
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? "(" + s + ")" : s;
}

// `xls` es el formato de la celda en Excel y `esc` la escala: la ocupación se
// guarda como 62.5 y en Excel va como 0.625, porque el formato de porcentaje
// multiplica por cien. Sin la escala el archivo diría 6250%.
// `label` es el rótulo cuando el término es canónico (USALI: ADR, RevPAR, GOP…)
// y `lk` la clave del catálogo cuando es texto que se traduce.
type Metric = {
  key: string; label: string; lk?: string; fmt: (v: number) => string;
  down?: boolean; strong?: boolean; sep?: boolean;
  xls: FormatoCol; esc?: number;
};
const METRICS: Metric[] = [
  { key: "OCC", label: "Occupancy", lk: "m.occ", fmt: v => v.toFixed(1) + "%", xls: "pct", esc: 0.01 },
  { key: "ADR", label: "ADR", fmt: usd2, xls: "usd2" },
  { key: "REVPAR", label: "RevPAR", fmt: usd2, xls: "usd2" },
  { key: "PAX", label: "Total Pax", fmt: intf, xls: "num" },
  { key: "TOTAL_REVENUES", label: "Total Revenue", fmt: money, strong: true, xls: "usd" },
  { key: "PAYROLL", label: "Payroll Expenses", lk: "m.payroll", fmt: money, down: true, xls: "usd" },
  { key: "COS", label: "Cost of Sales", lk: "m.cos", fmt: money, down: true, xls: "usd" },
  { key: "OPEX", label: "Operating Expenses", lk: "m.opex", fmt: money, down: true, xls: "usd" },
  { key: "NONOP", label: "Owner Expenses", lk: "m.nonop", fmt: money, down: true, xls: "usd" },
  { key: "GOP", label: "GOP", fmt: money, strong: true, xls: "usd" },
  { key: "EBITDA_BEFORE", label: "EBITDA", fmt: money, strong: true, xls: "usd" },
  { key: "NET_PROFIT", label: "Net Profit", fmt: money, strong: true, xls: "usd" },
];
function mval(s: Snap | null, key: string): number {
  if (!s) return 0;
  if (key === "OCC") return s.kpis?.occPct ?? 0;
  if (key === "ADR") return s.kpis?.adr ?? 0;
  if (key === "REVPAR") return s.kpis?.revpar ?? 0;
  if (key === "PAX") return s.kpis?.pax ?? 0;
  if (key === "PAYROLL") return s.vals.exp?.payroll ?? 0;
  if (key === "COS") return s.vals.exp?.cos ?? 0;
  if (key === "OPEX") return s.vals.exp?.opex ?? 0;
  if (key === "NONOP") return s.vals.annual["TOTAL_NON_OP"] ?? 0;
  return s.vals.annual[key] ?? 0;
}
function deltaTxt(now: number, base: number, down: boolean): { txt: string; color: string } | null {
  if (!base) return null;
  const d = (now - base) / Math.abs(base) * 100;
  const good = down ? d < 0 : d > 0;
  return { txt: (d >= 0 ? "+" : "") + d.toFixed(1) + "%", color: d === 0 ? "var(--text-disabled)" : good ? GREEN : RED };
}

function statusColor(s: string): string {
  return ({ pending: "var(--text-secondary)", in_progress: "var(--brand)", in_review: "var(--accent-amber, #856404)", approved: "var(--accent-green, #1A7F4B)" } as Record<string, string>)[s] ?? "var(--text-secondary)";
}

export default function CommandCenterPage() {
  const tc = useTranslations("common");
  const t = useTranslations("command");
  // El rótulo de la métrica: del catálogo si se traduce, literal si es canónico.
  const mLabel = (m: Metric) => (m.lk ? t(m.lk) : m.label);
  const statusLabel = (st: string) => t(`status.${st}`);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // El escenario que se esta midiendo es el presupuesto en armado, y la pantalla
  // se acuerda de cual era. Las tres referencias de abajo no son una eleccion
  // que valga la pena recordar: son el punto de partida de la comparacion.
  const [scenarioId, setScenarioId] = useEscenarioDe("command:budget", scenarios, "budget", undefined, true);
  const [cmpIds, setCmpIds] = useState<string[]>(["", "", ""]);   // 3 comparaciones
  const [cur, setCur] = useState<Snap | null>(null);
  const [comps, setComps] = useState<(Snap | null)[]>([null, null, null]);
  const [sections, setSections] = useState<SectionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        // El escenario propio lo elige `useEscenarioDe`; las referencias salen
        // de la misma regla del owner, para que no se vayan al año más nuevo.
        setScenarios(all);
        const actual = elegir(all, "actual");
        const fcast = elegir(all, "forecast");
        const propio = elegir(all, "budget");
        const budget2 = all.find(s => s.type === "BUDGET" && s.id !== propio?.id);
        setCmpIds([actual?.id ?? "", fcast?.id ?? "", budget2?.id ?? ""]);
      } catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
      finally { setLoading(false); }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchSnap = useCallback(async (id: string, all: Scenario[], withDrivers: boolean): Promise<Snap> => {
    const sc = all.find(s => s.id === id);
    const [pl, exp, drv] = await Promise.all([
      getPLMonthly(id),
      getExpenseTotals(id).catch(() => null),
      withDrivers ? fetchRoomKpis(id).catch(() => null) : Promise.resolve(null),
    ]);
    const vals: Vals = { annual: pl.annual, exp, months: pl.months.map(m => ({ kpis: m.kpis })) };
    const kpis = (drv && drv.avail > 0) ? drv : kpisFromPL(vals);
    return { id, label: sc ? `${sc.type} ${sc.version} ${sc.year}` : "—", vals, kpis };
  }, []);

  const load = useCallback(async (sid: string, cids: string[], all: Scenario[]) => {
    setLoading(true); setError(null);
    try {
      const [vCur, asg, ...cs] = await Promise.all([
        fetchSnap(sid, all, true),
        getAssignments(sid),
        ...cids.map(id => id ? fetchSnap(id, all, false) : Promise.resolve(null)),
      ]);
      setCur(vCur); setSections(asg.sections); setComps(cs as (Snap | null)[]);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }
  }, [fetchSnap]);

  useEffect(() => { if (scenarioId && scenarios.length) load(scenarioId, cmpIds, scenarios); }, [scenarioId, cmpIds, scenarios, load]);

  const approved = sections.filter(s => s.status === "approved").length;
  const pct = sections.length ? Math.round(approved / sections.length * 100) : 0;
  const td: React.CSSProperties = { textAlign: "right", padding: "6px 10px", fontFamily: "var(--font-mono)" };

  // ── Bajar a Excel ────────────────────────────────────────────────────────
  // Tres hojas. Los valores y las variaciones van separados porque el formato
  // se define por fila: la fila de ADR es en dólares, y su variación es un
  // porcentaje — no pueden compartir la misma fila sin que una de las dos
  // salga con el formato equivocado.
  async function bajarExcel() {
    const activos = comps.map((c, i) => ({ c, i })).filter(x => x.c) as { c: Snap; i: number }[];
    const col = (label: string, formato: FormatoCol = "usd") => ({ label, formato, ancho: 16 });

    const valores: FilaCuadro[] = METRICS.map(m => ({
      label: mLabel(m), es_total: !!m.strong, formato: m.xls,
      valores: [mval(cur, m.key), ...activos.map(x => mval(x.c, m.key))]
        .map(v => v * (m.esc ?? 1)),
    }));

    // Variación contra cada referencia, con el mismo criterio que la pantalla:
    // sobre el valor absoluto de la base, y "no aplica" si la base es cero.
    const variacion: FilaCuadro[] = METRICS.map(m => ({
      label: mLabel(m) + (m.down ? t("xls.lowerIsBetter") : ""),
      es_total: !!m.strong, formato: "pct",
      valores: activos.map(x => {
        const base = mval(x.c, m.key);
        return base ? (mval(cur, m.key) - base) / Math.abs(base) : null;
      }),
    }));

    const avance: FilaCuadro[] = sections.map(s => ({
      label: s.label,
      formato: "num",
      valores: [s.status === "approved" ? 1 : 0, s.locked ? 1 : 0],
    }));
    avance.push({
      label: t("xls.approvedOf", { n: approved, total: sections.length }), es_total: true,
      formato: "num", valores: [approved, sections.filter(s => s.locked).length],
    });

    const mio = cur?.label ?? t("thisScenario");
    try {
      await bajarCuadros("Command_Center", [
        { titulo: t("xls.indicatorsTitle", { esc: mio }), hoja: t("xls.indicatorsSheet"),
          subtitulo: t("xls.indicatorsSub"),
          columnas: [{ label: tc("indicator"), ancho: 30, formato: "texto" },
                     col(mio), ...activos.map(x => col(x.c.label))],
          filas: valores },
        { titulo: t("xls.varianceTitle", { esc: mio }), hoja: t("xls.varianceSheet"),
          subtitulo: t("xls.varianceSub"),
          columnas: [{ label: tc("indicator"), ancho: 34, formato: "texto" },
                     ...activos.map(x => col("vs " + x.c.label, "pct"))],
          filas: variacion },
        { titulo: t("teamProgress"), hoja: t("xls.progressSheet"),
          subtitulo: t("xls.progressSub"),
          columnas: [{ label: tc("section"), ancho: 34, formato: "texto" },
                     { label: t("xls.approved"), ancho: 12, formato: "num" },
                     { label: t("xls.locked"), ancho: 12, formato: "num" }],
          filas: avance },
      ]);
    } catch (e) { setError(e instanceof Error ? e.message : t("xls.error")); }
  }

  return (
    <div className="pag pag-media" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>Command Center</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 200 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}</option>)}
        </select>
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", margin: "10px 0 6px" }}>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("compareAgainst")}</span>
        {[0, 1, 2].map(i => (
          <select key={i} value={cmpIds[i]} className="fin-input" style={{ minWidth: 190, fontSize: 12 }}
            onChange={e => setCmpIds(prev => prev.map((v, j) => j === i ? e.target.value : v))}>
            <option value="">{tc("noneDash")}</option>
            {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}</option>)}
          </select>
        ))}
        <button onClick={bajarExcel} disabled={loading || !cur}
          title={t("excelHint")}
          style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: loading || !cur ? "default" : "pointer", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 16 }}>
        {t("intro")}
      </p>

      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <>
          <div className="fin-sticky" style={{ overflowX: "auto", marginBottom: 24 }}>
            <table className="fin-table" style={{ width: "100%", minWidth: 760 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>{tc("indicator")}</th>
                  <th style={{ textAlign: "right", color: "var(--brand)" }}>{t("thisScenario")}</th>
                  {comps.map((c, i) => <th key={i} style={{ textAlign: "right" }}>{c ? c.label : "—"}</th>)}
                </tr>
              </thead>
              <tbody>
                {METRICS.map(m => {
                  const v = mval(cur, m.key);
                  return (
                    <tr key={m.key} style={m.strong ? { borderTop: "1px solid var(--border-medium)" } : undefined}>
                      <td style={{ textAlign: "left", fontWeight: m.strong ? 600 : 400, color: m.down ? "var(--text-secondary)" : "var(--text-primary)" }}>{mLabel(m)}</td>
                      <td style={{ ...td, fontWeight: 600 }}>{m.fmt(v)}</td>
                      {comps.map((c, i) => {
                        if (!c) return <td key={i} style={{ ...td, color: "var(--text-disabled)" }}>—</td>;
                        const cv = mval(c, m.key);
                        const d = deltaTxt(v, cv, !!m.down);
                        return (
                          <td key={i} style={td}>
                            <div>{m.fmt(cv)}</div>
                            <div style={{ fontSize: 10, color: d?.color ?? "var(--text-disabled)" }}>{d?.txt ?? "—"}</div>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <h2 style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", margin: "0 0 8px" }}>{t("teamProgress")}</h2>
          <div style={{ height: 8, borderRadius: 999, background: "var(--bg-surface)", overflow: "hidden", marginBottom: 6 }}>
            <div style={{ width: `${pct}%`, height: "100%", background: approved === sections.length && sections.length ? "var(--accent-green, #1A7F4B)" : "var(--brand)" }} />
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>{t("sectionsApproved", { aprobadas: approved, total: sections.length })}</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 8 }}>
            {sections.map(s => (
              <div key={s.section} style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "9px 12px" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: statusColor(s.status), flexShrink: 0 }} />
                <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", flex: 1 }}>{s.label}{s.locked && " 🔒"}</span>
                <span style={{ fontSize: 11, color: statusColor(s.status) }}>{statusLabel(s.status)}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
