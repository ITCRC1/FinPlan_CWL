"use client";
import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { api, getBudgetScenario, getMonthlyRevenue, getComponentLabels, rtLabel, type MonthlyRevenue } from "@/lib/api";
import { bajarCuadros, num, type Cuadro, type ColumnaCuadro, type FilaCuadro } from "@/lib/exportCuadro";
import { HOTEL_ID } from "@/lib/hotel";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

// Los tipos de habitacion NO se escriben aca. Hasta el 2026-08-13 esta pantalla
// tenia los seis de Corcovado a mano y los apareaba con los UUID de la base
// POR POSICION, contra una lista de UUID ordenada como texto. Ese orden es el
// alfabetico de un numero aleatorio: no tiene ninguna relacion con sort_order,
// asi que el nombre del renglon no era el del tipo que se estaba editando. Y un
// tipo sin tarifa cargada no aparecia. Ahora salen de la base, en su orden, y lo
// que liga es el `id`; el rotulo es `code · nombre` como en el resto de la app.

const CHANNELS = ["TA", "OTA", "DIRECT"];
const CHANNEL_LABELS: Record<string, string> = {
  TA: "Travel Agency",
  OTA: "OTAs",
  DIRECT: "Direct",
};
const COMPONENTS = ["FOOD", "BEVERAGE", "ACTIVITIES", "TRANSPORT", "SUSTAINABILITY"];
// Los rótulos NO se escriben acá: los edita cada propiedad en Paquetes. El
// código (FOOD, ACTIVITIES…) es lo fijo; el nombre es lo que cambia de hotel a
// hotel — «Transportation» es la lancha desde Sierpe en Corcovado y puede ser
// otra cosa en el siguiente. Estos son solo el arranque, antes de que conteste
// el backend.
const COMPONENT_FALLBACK: Record<string, string> = {
  FOOD: "Food & Bev (base)",
  BEVERAGE: "Beverage ratio",
  ACTIVITIES: "Actividades",
  TRANSPORT: "Transporte/Transfer",
  SUSTAINABILITY: "Sustainability Fee",
};

interface RoomType { id: string; code: string; short_name: string; sort_order: number; }
interface RateCard { id: string; room_type_id: string; month: number; rack_rate: string; net_rate: string; pax_per_room: string; }
interface OccEntry { id: string; room_type_id: string; month: number; rooms_occupied: string; }
interface Channel  { id: string; channel: string; mix_pct: string; commission_pct: string; }
interface Package  { id: string; component: string; rate_per_pax_night: string; is_commissionable: boolean; bev_food_ratio: string | null; }

function NumInput({
  value, onSave, width = 72,
}: { value: string; onSave: (v: number) => Promise<void>; width?: number }) {
  const [local, setLocal] = useState(value);
  const [saving, setSaving] = useState(false);

  useEffect(() => setLocal(value), [value]);

  async function handleBlur() {
    const n = parseFloat(local);
    if (isNaN(n) || n.toString() === value) return;
    setSaving(true);
    try { await onSave(n); } finally { setSaving(false); }
  }

  return (
    <input
      className="fin-input mono"
      style={{ width, opacity: saving ? 0.5 : 1 }}
      value={local}
      onChange={e => setLocal(e.target.value)}
      onBlur={handleBlur}
      onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
    />
  );
}

function fmtUsd(v: string | number) {
  const n = Number(v);
  return isNaN(n) ? "—" : "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtPct(v: string | number) {
  const n = Number(v);
  return isNaN(n) ? "—" : (n * 100).toFixed(1) + "%";
}

export default function RatesPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("rates");
  const tch = useTranslations("channels");
  const tp = useTranslations("packages");
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [compLabels, setCompLabels] = useState<Record<string, string>>(COMPONENT_FALLBACK);
  const [rateCards, setRateCards] = useState<RateCard[]>([]);
  const [occupancy, setOccupancy] = useState<OccEntry[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [packages, setPackages] = useState<Package[]>([]);
  const [results, setResults] = useState<MonthlyRevenue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"rates" | "channels" | "packages">("rates");

  const loadAll = useCallback(async (scId: string) => {
    const [rt, et, rc, occ, ch, pkg, rev] = await Promise.all([
      api.get<{ room_types: RoomType[] }>(`/hotels/${HOTEL_ID}/room-types/`),
      getComponentLabels(HOTEL_ID),
      api.get<RateCard[]>(`/scenarios/${scId}/revenue/rate-cards/`),
      api.get<OccEntry[]>(`/scenarios/${scId}/revenue/occupancy/`),
      api.get<Channel[]>(`/scenarios/${scId}/revenue/channels/`),
      api.get<Package[]>(`/scenarios/${scId}/revenue/packages/`),
      getMonthlyRevenue(scId),
    ]);
    setRoomTypes(rt.room_types);
    setCompLabels(Object.fromEntries(et.labels.map(l => [l.code, l.label])));
    setRateCards(rc);
    setOccupancy(occ);
    setChannels(ch);
    setPackages(pkg);
    setResults(rev);
  }, []);

  useEffect(() => {
    async function init() {
      try {
        setLoading(true);
        const sc = await getBudgetScenario(HOTEL_ID, 2026);
        if (!sc) { setError(t("noBudgetScenario", { hotel: HOTEL_ID })); return; }
        setScenarioId(sc.id);
        await loadAll(sc.id);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : t("errorLoading"));
      } finally {
        setLoading(false);
      }
    }
    init();
  }, [loadAll]);

  async function updateRack(roomTypeId: string, month: number, v: number) {
    if (!scenarioId) return;
    await api.put(`/scenarios/${scenarioId}/revenue/rate-cards/${roomTypeId}/${month}/`, {
      rack_rate: v,
      net_rate: v * (1 - netFactor()),
      pax_per_room: 1.8,
    });
    await loadAll(scenarioId);
  }

  async function updateOcc(roomTypeId: string, month: number, v: number) {
    if (!scenarioId) return;
    await api.put(`/scenarios/${scenarioId}/revenue/occupancy/${roomTypeId}/${month}/`, { rooms_occupied: v });
    await loadAll(scenarioId);
  }

  function netFactor() {
    let nf = 0;
    for (const ch of channels) {
      nf += Number(ch.mix_pct) * Number(ch.commission_pct);
    }
    return nf;
  }

  function getRc(roomTypeId: string, month: number) {
    return rateCards.find(r => r.room_type_id === roomTypeId && r.month === month);
  }
  function getOcc(roomTypeId: string, month: number) {
    return occupancy.find(o => o.room_type_id === roomTypeId && o.month === month);
  }

  /**
   * Baja los cinco cuadros de la pantalla — los tres del tab de tarifas más
   * Canales y Paquete — sin importar qué tab esté abierto: quien baja el archivo
   * lo quiere completo, no la vista que dejó a medio mirar.
   *
   * Los que en pantalla son texto («Sí/No» de comisionable) van pegados al
   * rótulo: el exportador solo lleva números en las columnas de valores.
   */
  async function bajarExcel() {
    const colsMes: ColumnaCuadro[] = MONTHS.map(m => ({ label: m, ancho: 12, formato: "usd2" }));
    const tipos = roomTypes.map(rt => ({ label: rtLabel(rt.code, rt.short_name), rtId: rt.id }));
    const cuadros: Cuadro[] = [];

    cuadros.push({
      titulo: "Rack Rate (USD)",
      subtitulo: `Budget 2026 · Net Rate = Rack × (1 − ${(netFactor() * 100).toFixed(1)}%)`,
      hoja: "Rack Rates",
      columnas: [{ label: t("villaType"), ancho: 26, formato: "texto" }, ...colsMes],
      filas: [
        ...tipos.map(({ label, rtId }) => ({
          label,
          valores: MONTHS.map((_m, mi) => { const rc = getRc(rtId, mi + 1); return rc ? num(rc.rack_rate) : null; }),
        })),
        ...tipos.map(({ label, rtId }) => ({
          label: `Net ${label}`, nivel: 1,
          valores: MONTHS.map((_m, mi) => { const rc = getRc(rtId, mi + 1); return rc ? num(rc.net_rate) : null; }),
        })),
      ],
    });

    cuadros.push({
      titulo: "Rooms Occupied",
      subtitulo: "Budget 2026",
      hoja: "Rooms Occupied",
      columnas: [{ label: t("villaType"), ancho: 26, formato: "texto" },
        ...MONTHS.map(m => ({ label: m, ancho: 12, formato: "num" as const }))],
      filas: tipos.map(({ label, rtId }) => ({
        label,
        valores: MONTHS.map((_m, mi) => { const o = getOcc(rtId, mi + 1); return o ? num(o.rooms_occupied) : null; }),
      })),
    });

    if (results.length) {
      const suma = (k: keyof MonthlyRevenue) => results.reduce((s, r) => s + Number(r[k]), 0);
      const serie = (k: keyof MonthlyRevenue) => results.map(r => num(r[k] as string));
      cuadros.push({
        titulo: t("roomRevenueCalc"),
        subtitulo: "Budget 2026 · read-only",
        hoja: "Room Revenue",
        columnas: [
          { label: "KPI", ancho: 26, formato: "texto" },
          ...results.map(r => ({ label: MONTHS[r.month - 1] ?? String(r.month), ancho: 13, formato: "usd" as const })),
          { label: tc("annual"), ancho: 16, formato: "usd" as const },
        ],
        filas: [
          { label: "Room Revenue", valores: [...serie("rooms"), suma("rooms")] },
          { label: t("occupancyPct"), formato: "pct", valores: [...serie("occupancy_pct"), null] },
          { label: "ADR", formato: "usd2", valores: [...serie("adr"), null] },
          { label: "RevPAR", formato: "usd2", valores: [...serie("revpar"), null] },
          { label: "Total Revenue", es_total: true, valores: [...serie("total_revenue"), suma("total_revenue")] },
        ],
      });
    }

    const filasCh: FilaCuadro[] = CHANNELS.map(ch => {
      const c = channels.find(x => x.channel === ch);
      const label = CHANNEL_LABELS[ch] ?? ch;
      if (!c) return { label: t("noDataFor", { label }), valores: [null, null, null] };
      return {
        label,
        valores: [Number(c.mix_pct), Number(c.commission_pct), Number(c.mix_pct) * Number(c.commission_pct)],
      };
    });
    filasCh.push({ label: t("netFactorEffective"), es_total: true, valores: [null, null, 1 - netFactor()] });
    cuadros.push({
      titulo: tch("title"),
      subtitulo: "Net Rate = Rack Rate × Net Factor",
      hoja: tch("mixer.title"),
      columnas: [
        { label: tch("mixer.colChannel"), ancho: 26, formato: "texto" },
        { label: "Mix %", ancho: 12, formato: "pct" },
        { label: t("commission"), ancho: 12, formato: "pct" },
        { label: "Net contribution", ancho: 16, formato: "pct" },
      ],
      filas: filasCh,
    });

    cuadros.push({
      titulo: tp("title"),
      subtitulo: t("ratePerPaxNightUsd"),
      hoja: tp("title"),
      columnas: [
        { label: tp("component"), ancho: 30, formato: "texto" },
        { label: tp("ratePerPaxNight"), ancho: 16, formato: "usd2" },
        { label: t("bevFoodRatio"), ancho: 14, formato: "pct" },
      ],
      filas: COMPONENTS.map(comp => {
        const p = packages.find(x => x.component === comp);
        const label = compLabels[comp] ?? comp;
        if (!p) return { label: t("noDataFor", { label }), valores: [null, null] };
        return {
          label: `${label} · ${p.is_commissionable ? tp("isCommissionable") : tp("notCommissionable")}`,
          // Beverage no tiene tarifa propia: se deriva del ratio sobre Food.
          valores: [p.bev_food_ratio ? null : num(p.rate_per_pax_night),
            p.bev_food_ratio ? Number(p.bev_food_ratio) : null],
        };
      }),
    });

    try {
      await bajarCuadros("Rates_Tarifas", cuadros);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  const tabs = [
    { id: "rates",    label: t("tabRates") },
    { id: "channels", label: tch("title") },
    { id: "packages", label: tp("title") },
  ] as const;

  return (
    <div className="pag pag-ancha">
      {/* Header */}
      <div style={{ marginBottom: 16, display: "flex", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <h2 style={{ margin: 0, fontSize: 18, color: "var(--text-primary)", fontWeight: 600 }}>
            {t("title")}
          </h2>
          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: 12 }}>
            {t("subtitle")}
          </p>
        </div>
        <button onClick={bajarExcel} disabled={loading || !!error}
          title={t("excelHint")}
          style={{
            padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600,
            cursor: loading || error ? "not-allowed" : "pointer",
            background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)",
          }}>
          ⬇ Excel
        </button>
      </div>

      {loading && <p style={{ color: "var(--text-secondary)" }}>{tc("loading")}</p>}
      {error && (
        <div style={{ color: "var(--negative)", padding: "12px 16px", background: "var(--bg-surface)", borderRadius: 4, marginBottom: 16 }}>
          ⚠ {error}
        </div>
      )}

      {/* Tabs */}
      {!loading && !error && (
        <>
          <div style={{ display: "flex", gap: 0, borderBottom: "1px solid var(--border-medium)", marginBottom: 16 }}>
            {tabs.map(t => (
              <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
                padding: "8px 18px",
                fontSize: 13,
                background: "none",
                border: "none",
                borderBottom: activeTab === t.id ? "2px solid var(--brand)" : "2px solid transparent",
                color: activeTab === t.id ? "var(--text-primary)" : "var(--text-secondary)",
                cursor: "pointer",
              }}>{t.label}</button>
            ))}
          </div>

          {/* ── Tab: Rack Rates & Ocupación ── */}
          {activeTab === "rates" && (
            <div className="fin-sticky" style={{ overflowX: "auto" }}>
              {/* Rack Rates */}
              <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>
                {t.rich("rackHelp", { strong: (c: React.ReactNode) => <strong style={{ color: "var(--text-primary)" }}>{c}</strong>, pct: (netFactor() * 100).toFixed(1) })}
              </p>
              <table className="fin-table" style={{ marginBottom: 20 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>{t("villaType")}</th>
                    {MONTHS.map(m => <th key={m}>{m}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {roomTypes.map(rt => {
                    const rtId = rt.id;
                    return (
                      <tr key={rtId}>
                        <td style={{ color: "var(--text-primary)" }}>{rtLabel(rt.code, rt.short_name)}</td>
                        {MONTHS.map((_, mi) => {
                          const rc = getRc(rtId, mi + 1);
                          return (
                            <td key={mi}>
                              <NumInput
                                value={rc ? rc.rack_rate : "0"}
                                onSave={v => updateRack(rtId, mi + 1, v)}
                              />
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                  {/* Net Rate row (read-only) */}
                  {roomTypes.map(rt => {
                    const rtId = rt.id;
                    return (
                      <tr key={rtId + "_net"} style={{ opacity: 0.7 }}>
                        <td style={{ color: "var(--text-secondary)", fontSize: 11 }}>↳ Net {rtLabel(rt.code, rt.short_name)}</td>
                        {MONTHS.map((_, mi) => {
                          const rc = getRc(rtId, mi + 1);
                          return <td key={mi} className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>{rc ? fmtUsd(rc.net_rate) : "—"}</td>;
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {/* Ocupación */}
              <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>
                {t.rich("occHelp", { strong: (c: React.ReactNode) => <strong style={{ color: "var(--text-primary)" }}>{c}</strong> })}
              </p>
              <table className="fin-table" style={{ marginBottom: 20 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>{t("villaType")}</th>
                    {MONTHS.map(m => <th key={m}>{m}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {roomTypes.map(rt => {
                    const rtId = rt.id;
                    return (
                      <tr key={rtId}>
                        <td style={{ color: "var(--text-primary)" }}>{rtLabel(rt.code, rt.short_name)}</td>
                        {MONTHS.map((_, mi) => {
                          const occ = getOcc(rtId, mi + 1);
                          return (
                            <td key={mi}>
                              <NumInput
                                value={occ ? occ.rooms_occupied : "0"}
                                onSave={v => updateOcc(rtId, mi + 1, v)}
                                width={60}
                              />
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {/* Revenue summary */}
              {results.length > 0 && (
                <>
                  <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>
                    {t.rich("revHelp", { strong: (c: React.ReactNode) => <strong style={{ color: "var(--text-primary)" }}>{c}</strong> })}
                  </p>
                  <table className="fin-table">
                    <thead>
                      <tr>
                        <th style={{ textAlign: "left" }}>KPI</th>
                        {MONTHS.map(m => <th key={m}>{m}</th>)}
                        <th>{tc("annual")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        { label: "Room Revenue", key: "rooms" as keyof MonthlyRevenue, fmt: fmtUsd, esTotal: false },
                        { label: t("occupancyPct"),  key: "occupancy_pct" as keyof MonthlyRevenue, fmt: fmtPct, esTotal: false },
                        { label: "ADR",          key: "adr" as keyof MonthlyRevenue, fmt: fmtUsd, esTotal: false },
                        { label: "RevPAR",       key: "revpar" as keyof MonthlyRevenue, fmt: fmtUsd, esTotal: false },
                        { label: "Total Revenue",key: "total_revenue" as keyof MonthlyRevenue, fmt: fmtUsd, esTotal: true },
                      ].map(row => (
                        <tr key={row.label} className={row.esTotal ? "total" : ""}>
                          <td style={{ color: row.esTotal ? "var(--text-primary)" : undefined }}>{row.label}</td>
                          {results.map(r => (
                            <td key={r.month} className="mono">{row.fmt(r[row.key] as string)}</td>
                          ))}
                          <td className="mono" style={{ fontWeight: 600 }}>
                            {row.key === "rooms" || row.key === "total_revenue"
                              ? fmtUsd(results.reduce((s, r) => s + Number(r[row.key]), 0))
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>
          )}

          {/* ── Tab: Canales ── */}
          {activeTab === "channels" && (
            <div style={{ maxWidth: 500 }}>
              <table className="fin-table">
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>{tch("mixer.colChannel")}</th>
                    <th>Mix %</th>
                    <th>{t("commission")}</th>
                    <th>Net contribution</th>
                  </tr>
                </thead>
                <tbody>
                  {CHANNELS.map(ch => {
                    const c = channels.find(x => x.channel === ch);
                    if (!c) return <tr key={ch}><td colSpan={4} style={{ color: "var(--text-disabled)" }}>{t("noDataFor", { label: ch })}</td></tr>;
                    const contrib = Number(c.mix_pct) * Number(c.commission_pct);
                    return (
                      <tr key={ch}>
                        <td style={{ color: "var(--text-primary)" }}>{CHANNEL_LABELS[ch] ?? ch}</td>
                        <td className="mono">{fmtPct(c.mix_pct)}</td>
                        <td className="mono">{fmtPct(c.commission_pct)}</td>
                        <td className="mono" style={{ color: "var(--text-secondary)" }}>{(contrib * 100).toFixed(2)}%</td>
                      </tr>
                    );
                  })}
                  <tr className="total">
                    <td>{t("netFactorEffective")}</td>
                    <td></td>
                    <td></td>
                    <td className="mono" style={{ color: "var(--positive)" }}>
                      {(1 - netFactor()).toFixed(4)} ({((1 - netFactor()) * 100).toFixed(1)}%)
                    </td>
                  </tr>
                </tbody>
              </table>
              <p style={{ color: "var(--text-secondary)", fontSize: 11, marginTop: 8 }}>
                {t("channelsNote")}
              </p>
            </div>
          )}

          {/* ── Tab: Paquetes ── */}
          {activeTab === "packages" && (
            <div style={{ maxWidth: 500 }}>
              <table className="fin-table">
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>{tp("component")}</th>
                    <th>{tp("ratePerPaxNight")}</th>
                    <th>{t("commissionable")}</th>
                    <th>{t("bevFoodRatio")}</th>
                  </tr>
                </thead>
                <tbody>
                  {COMPONENTS.map(comp => {
                    const p = packages.find(x => x.component === comp);
                    if (!p) return <tr key={comp}><td colSpan={4} style={{ color: "var(--text-disabled)" }}>{t("noDataFor", { label: comp })}</td></tr>;
                    return (
                      <tr key={comp}>
                        <td style={{ color: "var(--text-primary)" }}>{compLabels[comp] ?? comp}</td>
                        <td className="mono">{p.bev_food_ratio ? t("derived") : fmtUsd(p.rate_per_pax_night)}</td>
                        <td style={{ color: p.is_commissionable ? "var(--positive)" : "var(--text-secondary)" }}>
                          {p.is_commissionable ? t("yes") : t("no")}
                        </td>
                        <td className="mono">{p.bev_food_ratio ? (Number(p.bev_food_ratio) * 100).toFixed(0) + "%" : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p style={{ color: "var(--text-secondary)", fontSize: 11, marginTop: 8 }}>
                {t("packagesNote")}
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
