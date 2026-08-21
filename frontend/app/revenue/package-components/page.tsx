"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import PushRevenueButton from "@/components/PushRevenueButton";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import { bajarCuadros, type Cuadro, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import {
  getScenarios, getPackageComponents, savePackageComponents, getChannelsConfig,
  type Scenario, type PkgItem,
} from "@/lib/api";

interface ItemRow {
  inclusion: string; unit: string; unitPrice: string; enabled: boolean;
  notes: string; category: string; qms: string; qmd: string; info: string;
}
interface Exp {
  name: string; nights: string; days: string;
  /** Alimenta el tab «Package Component Rack and Net Rate». Exactamente una. */
  esBase: boolean;
  items: ItemRow[];
}

const num = (v: string) => { const n = parseFloat((v || "").replace(/[$, ]/g, "")); return isNaN(n) ? 0 : n; };
const fmtUsd = (n: number) => "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Referencia: cómo se compone el Full Board / Full Pension ($126 pre-SC). 10% service charge.
const FULL_BOARD_MEALS = [
  { meal: "Breakfast", base: 21 },
  { meal: "Lunch", base: 42 },
  { meal: "Dinner", base: 63 },
];
const SC_RATE = 0.10;
// Planes de comida (paquetes más sencillos) — combinaciones de las comidas del Full Board
const FULL_BOARD_PLANS = [
  { plan: "planBreakfastOnly", meals: ["Breakfast"] },
  { plan: "planLunchDinner", meals: ["Lunch", "Dinner"] },
  { plan: "planFullBoard", meals: ["Breakfast", "Lunch", "Dinner"] },
] as const;
const mealBase = (name: string) => FULL_BOARD_MEALS.find(m => m.meal === name)?.base ?? 0;

function emptyItem(): ItemRow {
  return { inclusion: "", unit: "per pax/night", unitPrice: "", enabled: true, notes: "", category: "Basic", qms: "1", qmd: "1", info: "" };
}

export default function PackageComponentsPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("pkg");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [exps, setExps] = useState<Exp[]>([]);
  const [active, setActive] = useState(-1);   // -1 = sub-tab Rack & Net Rate (primero)
  const [netFactor, setNetFactor] = useState(0);
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
        const b = elegir(all, "budget") ?? all[0];
        if (!b) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarioId(sharedScenarioOr(b.id));
      } catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
      finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setMsg(null);
    try {
      const [res, ch] = await Promise.all([getPackageComponents(sid), getChannelsConfig(sid)]);
      setExps(res.experiences.map(e => ({
        name: e.name, nights: String(e.nights), days: String(e.days),
        esBase: !!e.es_base,
        items: e.items.map((it: PkgItem) => ({
          inclusion: it.inclusion, unit: it.unit,
          unitPrice: it.unit_price === null ? "" : String(parseFloat(it.unit_price)),
          enabled: it.enabled, notes: it.notes, category: it.category,
          qms: String(parseFloat(it.qty_mult_single)), qmd: String(parseFloat(it.qty_mult_double)),
          info: it.info,
        })),
      })));
      const nfs = ch.net_factor.map(v => parseFloat(v) || 0);
      setNetFactor(nfs.length ? nfs.reduce((a, b) => a + b, 0) / nfs.length : 0);
      setActive(-1); setSeeded(res.seeded); setDirty(false);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  function setItem(ri: number, k: keyof ItemRow, v: string | boolean) {
    setExps(prev => prev.map((e, i) => i === active
      ? { ...e, items: e.items.map((it, j) => j === ri ? { ...it, [k]: v } : it) } : e));
    setDirty(true);
  }
  // Editar el rack de un componente de la experiencia BASE (sub-tab Rack & Net).
  //
  // Antes se buscaba la que tuviera «classic» en el NOMBRE. Renombrarla —o
  // borrarla— hacía que este tab pasara a otra experiencia sin avisar, y lo que
  // se digitaba acá terminaba guardado contra la que quedara primera. Ahora la
  // base es una marca explícita y el nombre vuelve a ser solo una etiqueta.
  function setBaseRack(ri: number, v: string) {
    const ci = exps.findIndex(e => e.esBase);
    const idx = ci >= 0 ? ci : 0;
    setExps(prev => prev.map((e, i) => i === idx
      ? { ...e, items: e.items.map((it, j) => j === ri ? { ...it, unitPrice: v } : it) } : e));
    setDirty(true);
  }
  function addItem() {
    setExps(prev => prev.map((e, i) => i === active ? { ...e, items: [...e.items, emptyItem()] } : e));
    setDirty(true);
  }
  function removeItem(ri: number) {
    setExps(prev => prev.map((e, i) => i === active ? { ...e, items: e.items.filter((_, j) => j !== ri) } : e));
    setDirty(true);
  }
  function setExpField(k: "name" | "nights" | "days", v: string) {
    setExps(prev => prev.map((e, i) => i === active ? { ...e, [k]: v } : e)); setDirty(true);
  }
  /** Una sola base. Marcar otra desmarca la anterior. */
  function marcarBase(i: number) {
    setExps(prev => prev.map((e, idx) => ({ ...e, esBase: idx === i })));
    setDirty(true);
  }
  function addExp() {
    setExps(prev => [...prev, { name: t("newExperience"), nights: "0", days: "0", esBase: prev.length === 0, items: [] }]);
    setActive(exps.length); setDirty(true);
  }
  function removeExp(i: number) {
    const nombre = exps[i]?.name ?? "";
    if (!confirm(t("confirmDeleteExperience", { nombre }))) return;
    setExps(prev => {
      const quedan = prev.filter((_, idx) => idx !== i);
      // El Rack & Net no puede quedarse sin fuente: si se fue la base, la
      // primera que quede toma el relevo.
      if (quedan.length && !quedan.some(e => e.esBase)) quedan[0] = { ...quedan[0], esBase: true };
      return quedan;
    });
    setActive(a => Math.max(-1, a >= i ? a - 1 : a)); setDirty(true);
  }

  async function handleSave() {
    if (!scenarioId) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const payload = exps.map(e => ({
        name: e.name, nights: parseInt(e.nights) || 0, days: parseInt(e.days) || 0,
        es_base: e.esBase,
        items: e.items.map(it => ({
          inclusion: it.inclusion, unit: it.unit,
          unit_price: it.unitPrice.trim() === "" ? null : num(it.unitPrice),
          enabled: it.enabled, notes: it.notes, category: it.category,
          qty_mult_single: num(it.qms), qty_mult_double: num(it.qmd), info: it.info,
        })),
      }));
      const res = await savePackageComponents(scenarioId, payload);
      setSeeded(false); setDirty(false);
      setMsg(t("savedN", { exps: res.saved_experiences, items: res.saved_items }));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("errorSaving")); }
    finally { setSaving(false); }
  }

  const sel = scenarios.find(s => s.id === scenarioId);
  const exp = exps[active];
  const base = exps.find(e => e.esBase) ?? exps[0];

  // Monto por línea (single y double) = Unit Price × cantidad × qty mult.
  // `e` por parámetro (no el `exp` activo) para poder calcular cualquier
  // experiencia — el Excel las baja todas, no solo el sub-tab abierto.
  function montoOf(it: ItemRow, o: "single" | "double", e: Exp | undefined = exp): number {
    if (!it.enabled) return 0;
    const price = num(it.unitPrice);
    const nights = parseInt(e?.nights || "0") || 0;
    const days = parseInt(e?.days || "0") || 0;
    const pax = o === "double" ? 2 : 1;
    const u = it.unit.toLowerCase();
    let base: number;
    if (u.includes("pax/night")) base = pax * nights;
    else if (u.includes("pax/day")) base = pax * days;
    else if (u.includes("pax/stay") || u === "per pax") base = pax;
    else if (u.includes("room/night")) base = nights;
    else if (u.includes("flat")) base = 1;
    else base = pax;
    const mult = num(o === "double" ? it.qmd : it.qms);
    return price * base * mult;
  }
  const totalSingle = exp ? exp.items.reduce((s, it) => s + montoOf(it, "single"), 0) : 0;
  const totalDouble = exp ? exp.items.reduce((s, it) => s + montoOf(it, "double"), 0) : 0;

  /**
   * Baja los cuatro cuadros de la pantalla: Rack & Net del Classic, las
   * inclusiones de CADA experiencia (una hoja por sub-tab, no solo el abierto),
   * la referencia del Full Board y los planes de comida.
   *
   * Unit, Category, Notes e Info son texto y el exportador solo lleva números en
   * las columnas de valores: viajan pegados al rótulo de la fila para que no se
   * pierdan.
   */
  async function bajarExcel() {
    const escenario = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const cuadros: Cuadro[] = [];

    if (base) {
      const rackTotal = base.items.reduce((s, it) => s + (it.unitPrice.trim() === "" ? 0 : num(it.unitPrice)), 0);
      const filas: FilaCuadro[] = base.items.map(it => {
        const rack = it.unitPrice.trim() === "" ? null : num(it.unitPrice);
        return {
          label: it.unit ? `${it.inclusion} · ${it.unit}` : it.inclusion,
          valores: [rack, rack === null ? null : rack * netFactor],
        };
      });
      filas.push({ label: tc("total"), es_total: true, valores: [rackTotal, rackTotal * netFactor] });
      cuadros.push({
        titulo: "Package Component — Rack and Net Rate",
        subtitulo: [escenario, `Net Factor ${netFactor.toFixed(4)} (${(netFactor * 100).toFixed(1)}%) · Net = Rack × Factor`]
          .filter(Boolean).join(" · "),
        hoja: t("xlsRackNetSheet"),
        columnas: [
          { label: "Component", ancho: 46, formato: "texto" },
          { label: "Rack Rate", ancho: 14, formato: "usd2" },
          { label: "Net Rate", ancho: 14, formato: "usd2" },
        ],
        filas,
      });
    }

    for (const e of exps) {
      const filas: FilaCuadro[] = e.items.map(it => {
        const extras = [it.unit, it.category, it.notes, it.info].filter(x => (x || "").trim() !== "");
        const apagado = it.enabled ? "" : t("disabledSuffix");
        return {
          label: [it.inclusion, ...extras].join(" · ") + apagado,
          valores: [
            it.unitPrice.trim() === "" ? null : num(it.unitPrice),
            num(it.qms), num(it.qmd),
            // Deshabilitada: en pantalla el monto es «—», acá celda vacía.
            it.enabled ? montoOf(it, "single", e) : null,
            it.enabled ? montoOf(it, "double", e) : null,
          ],
        };
      });
      filas.push({
        label: t("totalExperience", { n: parseInt(e.nights) || 0 }), es_total: true,
        valores: [null, null, null,
          e.items.reduce((s, it) => s + montoOf(it, "single", e), 0),
          e.items.reduce((s, it) => s + montoOf(it, "double", e), 0)],
      });
      cuadros.push({
        titulo: `${e.name} — ${e.nights}N / ${e.days}D`,
        subtitulo: escenario || undefined,
        hoja: e.name,
        columnas: [
          { label: "Inclusion · Unit · Category · Notes · Info", ancho: 60, formato: "texto" },
          { label: "Unit Price", ancho: 13, formato: "usd2" },
          { label: "Qty Mult Single", ancho: 13, formato: "num1" },
          { label: "Qty Mult Double", ancho: 13, formato: "num1" },
          { label: t("amountSingle"), ancho: 14, formato: "usd2" },
          { label: t("amountDouble"), ancho: 14, formato: "usd2" },
        ],
        filas,
      });
    }

    const colsSc = [
      { label: "Description", ancho: 30, formato: "texto" as const },
      { label: "Total", ancho: 14, formato: "usd2" as const },
      { label: "10% SC", ancho: 14, formato: "usd2" as const },
      { label: "Total 10% Included", ancho: 18, formato: "usd2" as const },
    ];
    cuadros.push({
      titulo: t("fullBoardRef"),
      subtitulo: t("fullBoardXlsSubtitle"),
      hoja: "Full Board",
      columnas: colsSc,
      filas: [
        ...FULL_BOARD_MEALS.map(m => ({
          label: m.meal, valores: [m.base, m.base * SC_RATE, m.base * (1 + SC_RATE)],
        })),
        {
          label: "TOTAL", es_total: true,
          valores: [
            FULL_BOARD_MEALS.reduce((s, m) => s + m.base, 0),
            FULL_BOARD_MEALS.reduce((s, m) => s + m.base * SC_RATE, 0),
            FULL_BOARD_MEALS.reduce((s, m) => s + m.base * (1 + SC_RATE), 0),
          ],
        },
      ],
    });
    cuadros.push({
      titulo: t("mealPlans"),
      subtitulo: t("mealPlansXlsSubtitle"),
      hoja: t("mealPlans"),
      columnas: [{ ...colsSc[0], label: "Plan" }, ...colsSc.slice(1)],
      filas: FULL_BOARD_PLANS.map(p => {
        const base = p.meals.reduce((s, m) => s + mealBase(m), 0);
        return { label: t(p.plan), valores: [base, base * SC_RATE, base * (1 + SC_RATE)] };
      }),
    });

    try {
      await bajarCuadros("Package_Components", cuadros);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("excelFailed"));
    }
  }

  const btn = (en: boolean): React.CSSProperties => ({
    padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, border: "none",
    cursor: en ? "pointer" : "not-allowed", background: en ? "var(--brand)" : "var(--bg-surface)",
    color: en ? "#fff" : "var(--text-disabled)",
  });
  const inp = (w: number): React.CSSProperties => ({ width: w, padding: "3px 5px" });
  const cell: React.CSSProperties = { padding: "1px 3px" };

  return (
    <div className="pag pag-media" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>Package Components</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 200 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>)}
        </select>
        <PushRevenueButton scenarioId={scenarioId} />
        <div style={{ flex: 1 }} />
        <button onClick={bajarExcel} disabled={loading} title={t("excelHint")}
          style={{ ...btn(!loading), background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
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
        <>
          {/* sub-tabs */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12, borderBottom: "1px solid var(--border-medium)", paddingBottom: 8 }}>
            <button onClick={() => setActive(-1)} style={{
              padding: "6px 12px", fontSize: 12, borderRadius: 5, cursor: "pointer", border: "none",
              background: active === -1 ? "var(--brand)" : "var(--bg-surface)",
              color: active === -1 ? "#fff" : "var(--text-secondary)",
            }}>Package Component Rack and Net Rate</button>
            {exps.map((e, i) => (
              <button key={i} onClick={() => setActive(i)} style={{
                padding: "6px 12px", fontSize: 12, borderRadius: 5, cursor: "pointer", border: "none",
                background: i === active ? "var(--brand)" : "var(--bg-surface)",
                color: i === active ? "#fff" : "var(--text-secondary)",
              }}>
                {e.esBase && <span title={t("feedsRackNet")} style={{ marginRight: 5 }}>★</span>}
                {e.name} {e.nights}N/{e.days}D
              </button>
            ))}
            {!sel?.is_locked && <button onClick={addExp} style={{ padding: "6px 10px", fontSize: 12, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--text-secondary)", border: "1px dashed var(--border-medium)" }}>{t("addExperience")}</button>}
          </div>

          {active === -1 && base && (() => {
            const rackTotal = base.items.reduce((s, it) => s + (it.unitPrice.trim() === "" ? 0 : num(it.unitPrice)), 0);
            const renderTable = (mode: "rack" | "net") => (
              <table className="fin-table" style={{ width: "100%", maxWidth: 560 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", minWidth: 220 }}>Component</th>
                    <th style={{ textAlign: "left", minWidth: 110 }}>Unit</th>
                    <th style={{ textAlign: "right", minWidth: 110 }}>{mode === "rack" ? "Rack Rate" : "Net Rate"}</th>
                  </tr>
                </thead>
                <tbody>
                  {base.items.map((it, i) => {
                    const rack = it.unitPrice.trim() === "" ? null : num(it.unitPrice);
                    return (
                      <tr key={i}>
                        <td style={{ textAlign: "left", fontWeight: 500 }}>{it.inclusion}</td>
                        <td style={{ textAlign: "left", color: "var(--text-secondary)" }}>{it.unit}</td>
                        {mode === "rack" ? (
                          <td style={{ padding: "1px 3px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 1, justifyContent: "flex-end" }}>
                              <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>$</span>
                              <input className="fin-input mono" value={it.unitPrice} placeholder="—" disabled={sel?.is_locked}
                                onChange={e => setBaseRack(i, e.target.value)} onFocus={e => e.target.select()}
                                style={{ width: "100%", textAlign: "right", padding: "3px 4px" }} />
                            </div>
                          </td>
                        ) : (
                          <td className="mono" style={{ textAlign: "right", color: "var(--brand)" }}>{rack === null ? "—" : fmtUsd(rack * netFactor)}</td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                    <td style={{ textAlign: "left" }} colSpan={2}>{tc("total")}</td>
                    <td className="mono" style={{ textAlign: "right", color: mode === "net" ? "var(--brand)" : "var(--text-primary)" }}>{fmtUsd(mode === "rack" ? rackTotal : rackTotal * netFactor)}</td>
                  </tr>
                </tfoot>
              </table>
            );
            return (
              <div className="fin-sticky" style={{ overflowX: "auto" }}>
                {/* 1) Rack Rate */}
                <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: 8 }}>
                  {t.rich("step1Rack", { nombre: base.name, b: (c: React.ReactNode) => <span style={{ color: "var(--brand)" }}>{c}</span> })}
                </div>
                {renderTable("rack")}

                {/* 2) Factor de descuento */}
                <div style={{ margin: "16px 0", padding: "10px 14px", maxWidth: 560, background: "var(--bg-surface)", borderRadius: 8, border: "0.5px solid var(--border-medium)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{t("step2Factor")}</span>
                  <span className="mono" style={{ fontWeight: 700, color: "var(--brand)" }}>{netFactor.toFixed(4)} ({(netFactor * 100).toFixed(1)}%)</span>
                </div>

                {/* 3) Net Rate */}
                <div style={{ fontWeight: 600, color: "var(--text-primary)", margin: "8px 0" }}>{t("step3Net")}</div>
                {renderTable("net")}
              </div>
            );
          })()}

          {exp && (
            <>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
                <input className="fin-input" value={exp.name} disabled={sel?.is_locked}
                  onChange={e => setExpField("name", e.target.value)} style={{ minWidth: 240, padding: "5px 8px", fontWeight: 600, fontSize: 14 }} />
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("nights")}</span>
                <input className="fin-input mono" value={exp.nights} disabled={sel?.is_locked} onChange={e => setExpField("nights", e.target.value)} style={inp(46)} />
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("days")}</span>
                <input className="fin-input mono" value={exp.days} disabled={sel?.is_locked} onChange={e => setExpField("days", e.target.value)} style={inp(46)} />
                <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--text-secondary)", cursor: sel?.is_locked ? "default" : "pointer" }}
                  title={t("baseExperienceHint")}>
                  <input type="radio" checked={exp.esBase} disabled={sel?.is_locked}
                    onChange={() => marcarBase(active)} />
                  {t("feedsRackNetLabel")}
                </label>
                {!sel?.is_locked && <button onClick={() => removeExp(active)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-disabled)", fontSize: 15 }} aria-label={t("deleteExperience")} title={t("deleteExperienceHint")}>×</button>}
              </div>

              <div className="fin-sticky" style={{ overflowX: "auto" }}>
                <table className="fin-table" style={{ minWidth: 1250 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", minWidth: 190 }}>Inclusion</th>
                      <th style={{ textAlign: "left", minWidth: 110 }}>Unit</th>
                      <th style={{ textAlign: "right", minWidth: 90 }}>Unit Price</th>
                      <th style={{ textAlign: "center", minWidth: 70 }}>Enabled</th>
                      <th style={{ textAlign: "left", minWidth: 130 }}>Notes</th>
                      <th style={{ textAlign: "left", minWidth: 90 }}>Category</th>
                      <th style={{ textAlign: "right", minWidth: 80 }}>Qty Mult Single</th>
                      <th style={{ textAlign: "right", minWidth: 80 }}>Qty Mult Double</th>
                      <th style={{ textAlign: "left", minWidth: 150 }}>Info</th>
                      <th style={{ textAlign: "right", minWidth: 95, borderLeft: "1px solid var(--border)" }}>{t("amountSingle")}</th>
                      <th style={{ textAlign: "right", minWidth: 95 }}>{t("amountDouble")}</th>
                      <th style={{ width: 28 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {exp.items.map((it, ri) => (
                      <tr key={ri}>
                        <td style={cell}><input className="fin-input" value={it.inclusion} disabled={sel?.is_locked} onChange={e => setItem(ri, "inclusion", e.target.value)} style={{ width: "100%", padding: "3px 5px" }} /></td>
                        <td style={cell}><input className="fin-input" value={it.unit} disabled={sel?.is_locked} onChange={e => setItem(ri, "unit", e.target.value)} style={{ width: "100%", padding: "3px 5px" }} /></td>
                        <td style={cell}>
                          <div style={{ display: "flex", alignItems: "center", gap: 1, justifyContent: "flex-end" }}>
                            <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>$</span>
                            <input className="fin-input mono" value={it.unitPrice} placeholder="—" disabled={sel?.is_locked} onChange={e => setItem(ri, "unitPrice", e.target.value)} onFocus={e => e.target.select()} style={{ width: "100%", textAlign: "right", padding: "3px 4px" }} />
                          </div>
                        </td>
                        <td style={{ ...cell, textAlign: "center" }}><input type="checkbox" checked={it.enabled} disabled={sel?.is_locked} onChange={e => setItem(ri, "enabled", e.target.checked)} /></td>
                        <td style={cell}><input className="fin-input" value={it.notes} disabled={sel?.is_locked} onChange={e => setItem(ri, "notes", e.target.value)} style={{ width: "100%", padding: "3px 5px" }} /></td>
                        <td style={cell}>
                          <select className="fin-input" value={it.category} disabled={sel?.is_locked} onChange={e => setItem(ri, "category", e.target.value)} style={{ width: "100%", padding: "3px 4px" }}>
                            <option value="">—</option><option value="Basic">Basic</option><option value="Add-On">Add-On</option><option value="Optional">Optional</option>
                          </select>
                        </td>
                        <td style={cell}><input className="fin-input mono" value={it.qms} disabled={sel?.is_locked} onChange={e => setItem(ri, "qms", e.target.value)} onFocus={e => e.target.select()} style={{ width: "100%", textAlign: "right", padding: "3px 4px" }} /></td>
                        <td style={cell}><input className="fin-input mono" value={it.qmd} disabled={sel?.is_locked} onChange={e => setItem(ri, "qmd", e.target.value)} onFocus={e => e.target.select()} style={{ width: "100%", textAlign: "right", padding: "3px 4px" }} /></td>
                        <td style={cell}><input className="fin-input" value={it.info} disabled={sel?.is_locked} onChange={e => setItem(ri, "info", e.target.value)} style={{ width: "100%", padding: "3px 5px" }} /></td>
                        <td className="mono" style={{ textAlign: "right", paddingRight: 8, borderLeft: "1px solid var(--border)", color: it.enabled && montoOf(it, "single") ? "var(--text-primary)" : "var(--text-disabled)" }}>
                          {it.enabled ? fmtUsd(montoOf(it, "single")) : "—"}
                        </td>
                        <td className="mono" style={{ textAlign: "right", paddingRight: 8, color: it.enabled && montoOf(it, "double") ? "var(--text-primary)" : "var(--text-disabled)" }}>
                          {it.enabled ? fmtUsd(montoOf(it, "double")) : "—"}
                        </td>
                        <td style={{ textAlign: "center" }}>{!sel?.is_locked && <button onClick={() => removeItem(ri)} aria-label={t("deleteRow")} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-disabled)", fontSize: 15 }}>×</button>}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                      <td style={{ textAlign: "left", color: "var(--brand)" }} colSpan={9}>
                        {t("totalExperience", { n: parseInt(exp.nights) || 0 })}
                      </td>
                      <td className="mono" style={{ textAlign: "right", paddingRight: 8, borderLeft: "1px solid var(--border)", color: "var(--brand)" }}>{fmtUsd(totalSingle)}</td>
                      <td className="mono" style={{ textAlign: "right", paddingRight: 8, color: "var(--brand)" }}>{fmtUsd(totalDouble)}</td>
                      <td></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
              {!sel?.is_locked && <button onClick={addItem} style={{ marginTop: 10, padding: "6px 12px", fontSize: 12, borderRadius: 5, cursor: "pointer", background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>{t("addInclusion")}</button>}
            </>
          )}

          {/* Referencia: composición del Full Board / Full Pension */}
          <div style={{ marginTop: 28, maxWidth: 520, border: "0.5px solid var(--border-medium)", borderRadius: 8, padding: 16 }}>
            <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>{t("fullBoardRef")}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>
              {t("fullBoardHelp")}
            </div>
            <table className="fin-table" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Description</th>
                  <th style={{ textAlign: "right" }}>Total</th>
                  <th style={{ textAlign: "right" }}>10% SC</th>
                  <th style={{ textAlign: "right" }}>Total 10% Included</th>
                </tr>
              </thead>
              <tbody>
                {FULL_BOARD_MEALS.map(m => (
                  <tr key={m.meal}>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>{m.meal}</td>
                    <td className="mono" style={{ textAlign: "right" }}>{fmtUsd(m.base)}</td>
                    <td className="mono" style={{ textAlign: "right" }}>{fmtUsd(m.base * SC_RATE)}</td>
                    <td className="mono" style={{ textAlign: "right" }}>{fmtUsd(m.base * (1 + SC_RATE))}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                  <td style={{ textAlign: "left" }}>TOTAL</td>
                  <td className="mono" style={{ textAlign: "right" }}>{fmtUsd(FULL_BOARD_MEALS.reduce((s, m) => s + m.base, 0))}</td>
                  <td className="mono" style={{ textAlign: "right" }}>{fmtUsd(FULL_BOARD_MEALS.reduce((s, m) => s + m.base * SC_RATE, 0))}</td>
                  <td className="mono" style={{ textAlign: "right", color: "var(--brand)" }}>{fmtUsd(FULL_BOARD_MEALS.reduce((s, m) => s + m.base * (1 + SC_RATE), 0))}</td>
                </tr>
              </tfoot>
            </table>

            <div style={{ fontWeight: 600, color: "var(--text-primary)", margin: "16px 0 4px" }}>{t("mealPlans")}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>
              {t("mealPlansHelp")}
            </div>
            <table className="fin-table" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Plan</th>
                  <th style={{ textAlign: "right" }}>Total</th>
                  <th style={{ textAlign: "right" }}>10% SC</th>
                  <th style={{ textAlign: "right" }}>Total 10% Included</th>
                </tr>
              </thead>
              <tbody>
                {FULL_BOARD_PLANS.map(p => {
                  const base = p.meals.reduce((s, m) => s + mealBase(m), 0);
                  return (
                    <tr key={p.plan}>
                      <td style={{ textAlign: "left", fontWeight: 500 }}>{t(p.plan)}</td>
                      <td className="mono" style={{ textAlign: "right" }}>{fmtUsd(base)}</td>
                      <td className="mono" style={{ textAlign: "right" }}>{fmtUsd(base * SC_RATE)}</td>
                      <td className="mono" style={{ textAlign: "right", color: "var(--brand)" }}>{fmtUsd(base * (1 + SC_RATE))}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
