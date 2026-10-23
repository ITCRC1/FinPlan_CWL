"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import {
  getScenarios, getRackRates, getChannelsConfig, getOccupancyPct, getRoomTypes, rtLabel, pushRevenueToCheckbook,
  type Scenario,
} from "@/lib/api";
import { fmtUsd } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import BloqueRevenue from "./BloqueRevenue";

// Mismo estilo que el "⬇ Excel" de Planning · Big Picture.
const excelBtn: React.CSSProperties = {
  padding: "8px 16px", fontSize: 13, fontWeight: 700, borderRadius: 6, cursor: "pointer",
  background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)",
};

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTH_KEYS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"] as const;

interface Row {
  id: string; code: string; name: string;
  /** Lo que se cobra: rack × noches. Antes de lo que se lleva el canal. */
  rack: number[];
  /** Lo que queda: rack × factor neto × noches. Es lo que va al P&L. */
  revenue: number[];
  nights: number[]; available: number[];
}

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
        // ⚠️ Dos ingresos, no uno con un ajuste al final. El de RACK es lo que
        // se le cobra al huésped; el NETO, lo que queda después de la comisión
        // del canal, y es el que mueve el P&L. Owner, 2026-10-04: *«necesito
        // poder ver total revenue tarifa rack, y después total revenue por tipo
        // de habitación net rate»*.
        const rack = MONTHS.map((_m, mi) => nights[mi] * rack12[mi]);
        const revenue = MONTHS.map((_m, mi) => rack[mi] * (nf[mi] || 0));
        return { id: r.room_type_id, code: codeById[r.room_type_id] ?? "", name: r.name,
                 rack, revenue, nights, available };
      });
      setRows(computed);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const monthRack = MONTHS.map((_m, mi) => rows.reduce((s, r) => s + r.rack[mi], 0));
  const monthTotals = MONTHS.map((_m, mi) => rows.reduce((s, r) => s + r.revenue[mi], 0));
  const monthNights = MONTHS.map((_m, mi) => rows.reduce((s, r) => s + r.nights[mi], 0));
  const monthAvail = MONTHS.map((_m, mi) => rows.reduce((s, r) => s + r.available[mi], 0));
  const grandRack = monthRack.reduce((s, v) => s + v, 0);
  const grand = monthTotals.reduce((s, v) => s + v, 0);
  const totalNights = monthNights.reduce((s, v) => s + v, 0);
  const totalAvail = monthAvail.reduce((s, v) => s + v, 0);

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

  // ── Excel: los MISMOS dos bloques que se ven ──────────────────────────────
  //
  // ⚠️ Los dos, y en el mismo orden. El owner compara rack contra neto mirando
  // una tabla debajo de la otra; un Excel que trajera sólo el neto le pediría
  // rehacer la resta a mano, que es justo lo que la pantalla le ahorra.
  async function bajarExcel() {
    const sel = scenarios.find(s => s.id === scenarioId);
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const nocheFila = (rotulo: string, serie: number[], total: number): FilaCuadro => ({
      label: rotulo, formato: "num", valores: [...serie, total],
    });
    // Sin base (0 noches) la tarifa no es cero: no aplica → celda vacía.
    const tarifaFila = (rotulo: string, tot: number[], base: number[],
                        anual: number, baseAnual: number): FilaCuadro => ({
      label: rotulo,
      valores: [...tot.map((v, mi) => (base[mi] ? v / base[mi] : null)),
                baseAnual ? anual / baseAnual : null],
    });

    const bloque = (
      titulo: string, valores: (r: typeof rows[number]) => number[],
      tot: number[], anual: number, rotTotal: string,
      rotAdr: string, rotRevpar: string, conNoches: boolean,
    ): FilaCuadro[] => {
      const out: FilaCuadro[] = [{ label: titulo, es_seccion: true,
                                   valores: Array(13).fill(null) }];
      const desde = out.length;
      rows.forEach(r => out.push({
        label: rtLabel(r.code, r.name), nivel: 1,
        valores: [...valores(r), valores(r).reduce((s2, v) => s2 + v, 0)],
      }));
      out.push({ label: rotTotal, es_total: true,
                 suma_de: rows.map((_r, i) => desde + i),
                 valores: [...tot, anual] });
      if (conNoches) {
        out.push(nocheFila(t("nightsOccupied"), monthNights, totalNights));
        out.push(nocheFila(t("nightsAvailable"), monthAvail, totalAvail));
        // ⚠️ `pct` y no `num`: en el Excel es un porcentaje de verdad, así que
        // va como fracción con formato de porcentaje — no como «40.5» suelto,
        // que al multiplicarlo por algo da cien veces lo que debería.
        out.push({ label: t("occupancyLabel"), formato: "pct",
          valores: [...monthNights.map((n, mi) =>
                      (monthAvail[mi] ? n / monthAvail[mi] : null)),
                    totalAvail ? totalNights / totalAvail : null] });
      }
      out.push(tarifaFila(rotAdr, tot, monthNights, anual, totalNights));
      out.push(tarifaFila(rotRevpar, tot, monthAvail, anual, totalAvail));
      return out;
    };

    const filas: FilaCuadro[] = [
      ...bloque(t("rackTitle"), r => r.rack, monthRack, grandRack,
                t("rackTotal"), t("adrRack"), t("revparRack"), false),
      { label: "", valores: Array(13).fill(null) },
      ...bloque(t("netTitle"), r => r.revenue, monthTotals, grand,
                t("netTotal"), t("adrLabel"), t("revparLabel"), true),
    ];
    try {
      await bajarCuadros("Total_Revenue", [{
        titulo: t("title"),
        subtitulo: `${esc} · ${t("xlsSubtitle")}`,
        hoja: "Total Revenue",
        columnas: [
          { label: "Room Type", ancho: 38, formato: "texto" },
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
        <>
          {/* ⚠️ El de RACK primero, que es lo que se le cobra al huésped, y el
              NETO debajo, que es lo que queda y lo que mueve el P&L. En ese
              orden se lee la comisión del canal sin tener que calcularla. */}
          <BloqueRevenue
            meses={MONTHS}
            filas={rows.map(r => ({ id: r.id, code: r.code, name: r.name, valores: r.rack }))}
            totales={monthRack} anual={grandRack}
            noches={monthNights} disponibles={monthAvail}
            totalNoches={totalNights} totalDisp={totalAvail}
            titulo={t("rackTitle")} nota={t("rackNote")}
            acento="var(--text-primary)" mostrarNoches={false}
            rotulos={{ anio: tc("year"), total: t("rackTotal"),
                       ocupadas: t("nightsOccupied"), disponibles: t("nightsAvailable"),
                       ocupacion: t("occupancyLabel"),
                       adr: t("adrRack"), revpar: t("revparRack") }} />

          {/* Lo que se lleva el canal, dicho una vez y no dejado a la resta. */}
          <div style={{ fontSize: 12.5, color: "var(--text-secondary)",
                        margin: "-14px 0 20px", paddingLeft: 2 }}>
            {t("commissionLine", {
              monto: fmtUsd(grandRack - grand),
              pct: grandRack ? ((1 - grand / grandRack) * 100).toFixed(1) : "0.0",
            })}
          </div>

          <BloqueRevenue
            meses={MONTHS}
            filas={rows.map(r => ({ id: r.id, code: r.code, name: r.name, valores: r.revenue }))}
            totales={monthTotals} anual={grand}
            noches={monthNights} disponibles={monthAvail}
            totalNoches={totalNights} totalDisp={totalAvail}
            titulo={t("netTitle")} nota={t("netNote")}
            acento="var(--brand)"
            rotulos={{ anio: tc("year"), total: t("netTotal"),
                       ocupadas: t("nightsOccupied"), disponibles: t("nightsAvailable"),
                       ocupacion: t("occupancyLabel"),
                       adr: t("adrLabel"), revpar: t("revparLabel") }} />
        </>
      )}
    </div>
  );
}
