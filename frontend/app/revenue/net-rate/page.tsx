"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback, useMemo } from "react";
import PushRevenueButton from "@/components/PushRevenueButton";
import {
  getScenarios, getRackRates, getChannelsConfig, getRoomTypes,
  getNetRates, setNetRateManual,
  type Scenario, type RoomType, type NetRateRow,
} from "@/lib/api";
import { fmtUsd } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { useInfoSet } from "@/lib/roomSet";
import AvisoSet from "@/components/AvisoSet";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTH_KEYS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"] as const;

const excelBtn: React.CSSProperties = {
  padding: "7px 16px", fontSize: 13, fontWeight: 700, borderRadius: 5, cursor: "pointer",
  background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)",
};

interface NetRow {
  room_type_id: string;
  name: string;
  rack: number[];
  /** La neta GUARDADA por mes. Solo manda donde `manual` es true. */
  neto: number[];
  /** Qué meses tienen la neta puesta a mano (no derivada del rack). */
  manual: boolean[];
}

export default function NetRatePage() {
  const tc = useTranslations("common");
  const t = useTranslations("netRate");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [rows, setRows] = useState<NetRow[]>([]);
  const [tipos, setTipos] = useState<RoomType[]>([]);
  const info = useInfoSet(tipos);
  const vis = useMemo(() => {
    if (!info.activo) return rows;
    const ids = new Set(info.tipos.map(x => x.id));
    return rows.filter(r => ids.has(r.room_type_id));
  }, [rows, info]);
  const [netFactor, setNetFactor] = useState<number[]>(Array(12).fill(0));
  const [loading, setLoading] = useState(true);
  /** Lo que se está tecleando, por `${room_type_id}:${mes}`. Sin esto el input
   *  se repinta con el valor viejo en cada tecla y no se puede escribir. */
  const [borrador, setBorrador] = useState<Record<string, string>>({});
  const [guardando, setGuardando] = useState<string | null>(null);
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
      const [rack, ch, rt, net] = await Promise.all([
        getRackRates(sid), getChannelsConfig(sid),
        getRoomTypes(HOTEL_ID, sid).then(r => r.room_types).catch(() => [] as RoomType[]),
        // ⚠️ Con su propio `catch`: la neta guardada es un AUXILIAR de esta
        // pantalla —sirve para saber qué celdas son manuales— y si falla, lo
        // que corresponde es dibujar la fórmula como siempre, no dejar la
        // tabla en blanco. Iba dentro del `Promise.all` sin red, así que un
        // 500 del endpoint nuevo borraba las ocho categorías de golpe.
        getNetRates(sid).catch(() => ({ rooms: [] as NetRateRow[] })),
      ]);
      setTipos(rt);
      const netoPorTipo = new Map(net.rooms.map(n => [n.room_type_id, n]));
      setRows(rack.rooms.map(r => {
        const n = netoPorTipo.get(r.room_type_id);
        return {
          room_type_id: r.room_type_id, name: r.name,
          rack: MONTH_KEYS.map(mk => parseFloat(r[mk]) || 0),
          neto: MONTH_KEYS.map(mk => (n ? parseFloat(n.neto[mk]) || 0 : 0)),
          manual: MONTH_KEYS.map(mk => Boolean(n?.manual[mk])),
        };
      }));
      setBorrador({});
      setNetFactor(ch.net_factor.map(v => parseFloat(v) || 0));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const fmt = fmtUsd;
  const bloqueado = scenarios.find(x => x.id === scenarioId)?.is_locked ?? false;

  /** Lo que se MUESTRA en la celda neta: lo guardado si es manual, la fórmula
   *  si no. Para las celdas derivadas las dos cifras son la misma; mostrar la
   *  fórmula mantiene el comportamiento de siempre en las seis categorías. */
  const netoVisible = (r: NetRow, mi: number) =>
    r.manual[mi] ? r.neto[mi] : r.rack[mi] * (netFactor[mi] || 0);

  /** Guarda la celda, o la suelta si quedó vacía. */
  async function guardarNeto(r: NetRow, mi: number, texto: string) {
    const clave = `${r.room_type_id}:${mi}`;
    const limpio = texto.trim().replace(/[$,\s]/g, "");
    const valor = limpio === "" ? null : Number(limpio);
    if (valor !== null && !Number.isFinite(valor)) {
      setBorrador(b => { const n = { ...b }; delete n[clave]; return n; });
      return;
    }
    // Sin cambio real no se molesta al servidor.
    const antes = r.manual[mi] ? r.neto[mi] : null;
    if ((valor === null && antes === null) ||
        (valor !== null && antes !== null && Math.abs(valor - antes) < 0.005)) {
      setBorrador(b => { const n = { ...b }; delete n[clave]; return n; });
      return;
    }
    setGuardando(clave); setError(null);
    try {
      const res = await setNetRateManual(scenarioId, r.room_type_id, mi + 1, valor);
      const neto = parseFloat(res.net_rate) || 0;
      setRows(prev => prev.map(x => x.room_type_id !== r.room_type_id ? x : {
        ...x,
        neto: x.neto.map((v, i) => i === mi ? neto : v),
        manual: x.manual.map((v, i) => i === mi ? res.manual : v),
      }));
      setBorrador(b => { const n = { ...b }; delete n[clave]; return n; });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setGuardando(null); }
  }

  // ── Excel: la misma grilla, con las tarifas como número ───────────────────
  async function bajarExcel() {
    const sel = scenarios.find(s => s.id === scenarioId);
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    // El net factor es una fracción (0.75) → va como % para no perder decimales.
    const filas: FilaCuadro[] = [];
    filas.push({ label: t("blockRack"), es_total: true, valores: Array(12).fill(null) });
    for (const r of rows) {
      filas.push({ label: r.name, nivel: 1, valores: r.rack });
    }
    filas.push({ label: t("blockDiscount"), es_total: true, valores: Array(12).fill(null) });
    filas.push({ label: t("discountPct"), nivel: 1, formato: "pct",
                 valores: netFactor.map(nf => 1 - nf) });
    filas.push({ label: "Net Factor", nivel: 1, formato: "pct", valores: netFactor.map(nf => nf) });
    filas.push({ label: t("blockNet"), es_total: true, valores: Array(12).fill(null) });
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
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 6 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>
      <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginTop: 0, marginBottom: 12,
        borderLeft: "2px solid #c8a24a", paddingLeft: 10, lineHeight: 1.6 }}>
        {t.rich("editable", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>

      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      <AvisoSet set={info.set} unidades={info.unidades} vacio={info.vacio} />

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
              {/* Owner, 2026-10-06: *«pon acá la tarifa rack también para poder
                  comparar... primero tarifa rack, después el rate de descuento y
                  siguiente las tarifas net rate»*.
                  La página ya traía el rack — lo usaba para calcular y no lo
                  mostraba, así que para ver de dónde salía cada neta había que
                  abrir otra pantalla. */}
              <tr>
                <td colSpan={13} style={{ textAlign: "left", fontWeight: 700,
                  background: "var(--bg-surface)", padding: "6px 8px" }}>
                  {t("blockRack")}
                </td>
              </tr>
              {vis.map(r => (
                <tr key={`rack-${r.room_type_id}`}>
                  <td style={{ textAlign: "left", fontWeight: 500 }}>{r.name}</td>
                  {r.rack.map((rk, mi) => (
                    <td key={mi} className="mono" style={{ textAlign: "right",
                      color: rk ? "var(--text-primary)" : "var(--text-disabled)" }}>
                      {fmt(rk)}
                    </td>
                  ))}
                </tr>
              ))}

              <tr>
                <td colSpan={13} style={{ textAlign: "left", fontWeight: 700,
                  background: "var(--bg-surface)", padding: "6px 8px" }}>
                  {t("blockDiscount")}
                </td>
              </tr>
              <tr>
                <td style={{ textAlign: "left", fontWeight: 500 }}>{t("discountPct")}</td>
                {netFactor.map((nf, mi) => (
                  <td key={mi} className="mono" style={{ textAlign: "right" }}>
                    {((1 - nf) * 100).toFixed(2)}%
                  </td>
                ))}
              </tr>
              <tr style={{ color: "var(--brand)" }}>
                <td style={{ textAlign: "left", fontWeight: 600 }}>Net Factor</td>
                {netFactor.map((nf, mi) => (
                  <td key={mi} className="mono" style={{ textAlign: "right" }}>{nf.toFixed(4)}</td>
                ))}
              </tr>

              <tr>
                <td colSpan={13} style={{ textAlign: "left", fontWeight: 700,
                  background: "var(--bg-surface)", padding: "6px 8px" }}>
                  {t("blockNet")}
                </td>
              </tr>
              {vis.map(r => (
                <tr key={`net-${r.room_type_id}`}>
                  <td style={{ textAlign: "left", fontWeight: 500 }}>{r.name}</td>
                  {r.rack.map((rk, mi) => {
                    const clave = `${r.room_type_id}:${mi}`;
                    const manual = r.manual[mi];
                    const valor = netoVisible(r, mi);
                    return (
                      <td key={mi} style={{ padding: "1px 2px",
                        background: manual ? "rgba(200,162,74,0.10)" : undefined }}>
                        <input
                          className="fin-input mono"
                          value={borrador[clave] ?? (valor ? valor.toFixed(2) : "")}
                          disabled={bloqueado || guardando === clave}
                          onChange={e => setBorrador(b => ({ ...b, [clave]: e.target.value }))}
                          onBlur={e => guardarNeto(r, mi, e.target.value)}
                          onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }}
                          onFocus={e => e.target.select()}
                          title={manual ? t("manualCell") : t("formulaCell")}
                          style={{
                            width: "100%", minWidth: 0, textAlign: "right", padding: "3px 4px",
                            fontWeight: 600,
                            color: manual ? "#c8a24a"
                                 : (rk ? "var(--text-primary)" : "var(--text-disabled)"),
                          }}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
