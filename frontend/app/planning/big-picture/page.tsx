"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import {
  getScenarios, getPLMonthly, getBigPictureBreakdown,
  listBigPictureVersions, getBigPictureVersion, saveBigPictureVersion, deleteBigPictureVersion,
  applyBigPicture, getCuadre, type Scenario,
  type BigPictureBreakdown, type BPVersionMeta, type Cuadre,
} from "@/lib/api";

// Grupo (group_for_dept) → línea de ingreso oficial del Big Picture.
const REV_CODE_FOR_GROUP: Record<string, string> = {
  ROOMS: "REV_ROOMS", FB: "REV_FB", PRIVATE_BAR: "REV_PRIVATE_BAR", SPA: "REV_SPA", TOURS: "REV_TOURS", TIENDA: "REV_TIENDA", RETAIL: "REV_RETAIL",
  LAUNDRY_OPS: "REV_LAUNDRY", LAUNDRY: "REV_LAUNDRY", INNOCEANA: "REV_INNOCEANA", CLUB: "REV_CLUB",
  TRANSPORT: "REV_TRANSPORTATION", CROWTHER: "REV_CROWTHER_LAB", OTHER_OVERHEAD: "REV_MISC_OTHER",
  SUSTAINABILITY: "REV_MISC_OTHER",
};

type Col = Record<string, number>;
/** Ingresos por línea del P&L. Tienen que sumar EXACTO a `TOTAL_REVENUES`:
 *  lo que falte cae en `REV_OTHER`, que está pensado como residual de redondeo.
 *
 *  ⚠️ Faltaban 6 líneas desde que el ingreso se partió (2026-08-14):
 *  `REV_ROOMS_OTHER`, `REV_FB_BEV`, `REV_FB_MISC`, `REV_SUSTAINABILITY`,
 *  `REV_AREC` y `REV_CLARO_HUERTA`. El residual se las comía —el total seguía
 *  cuadrando— y, peor, **los drivers de crecimiento solo se aplican a las
 *  líneas de esta lista**: ese ingreso viajaba PLANO dentro del residual, sin
 *  responder a ningún supuesto del plan. */
const REV_LIST = [["REV_ROOMS", "Rooms"], ["REV_ROOMS_OTHER", "Other Rooms Revenue"], ["REV_FB", "F&B Food"], ["REV_FB_BEV", "F&B Beverage"], ["REV_FB_MISC", "F&B Miscellaneous"], ["REV_PRIVATE_BAR", "Private Bar"], ["REV_SPA", "Spa"], ["REV_TOURS", "Tours"], ["REV_TIENDA", "Tienda"], ["REV_RETAIL", "Gift Shop"], ["REV_LAUNDRY", "Laundry"], ["REV_INNOCEANA", "Innoceana"], ["REV_CLUB", "Club Madresal"], ["REV_AREC", "Área Recreativa"], ["REV_CLARO_HUERTA", "Claro del Bosque"], ["REV_TRANSPORTATION", "Transporte"], ["REV_CROWTHER_LAB", "Crowther Lab"], ["REV_SUSTAINABILITY", "Sustainability Fee"], ["REV_MISC_OTHER", "Otros"]] as [string, string][];
const NONOP = [["RENT", "Renta"], ["MGMT_FEE_3", "Management Fee · 3% de ingresos"], ["MGMT_FEE_5_ROYALTIES", "Royalties (5%)"], ["PROPERTY_INSURANCE", "Seguros"], ["NONOP_OTHER", "Otros no-operativos"]] as [string, string][];
const CAPITAL = [["CAP_RESERVE", "Reserva de Capital · 4% de ingresos"], ["CAP_LARGE", "CapEx Mayor · no existe en budget"]] as [string, string][];

const fmt = (v: number) => { const s = "$" + Math.abs(Math.round(v)).toLocaleString("en-US"); return v < 0 ? `(${s})` : s; };
const sumPrefix = (a: Col, p: string) => Object.keys(a).filter(k => k.startsWith(p)).reduce((s, k) => s + (a[k] || 0), 0);

function compute(leaf: Col): Col {
  const rev = sumPrefix(leaf, "REV_"), pay = sumPrefix(leaf, "PAY_"), opex = sumPrefix(leaf, "OPEX_"), cost = sumPrefix(leaf, "COST_");
  // ADJ = ajuste de neteo (allocations cafetería/lavandería que el P&L netea). Negativo = crédito.
  const gop = rev - pay - opex - cost - (leaf.ADJ || 0);
  const nonop = (leaf.RENT || 0) + (leaf.MGMT_FEE_3 || 0) + (leaf.MGMT_FEE_5_ROYALTIES || 0) + (leaf.PROPERTY_INSURANCE || 0) + (leaf.NONOP_OTHER || 0);
  const ebitda = gop - nonop;
  const capital = (leaf.CAP_RESERVE || 0) + (leaf.CAP_LARGE || 0);
  const ebitdaAfter = ebitda - capital;
  const ebt = ebitdaAfter - (leaf.DEPR_FIN || 0);          // utilidad antes de impuestos
  const tax = Math.max(0, 0.30 * ebt);                      // Renta = 30% del EBT (0 si pérdida)
  const net = ebt - tax;
  return { ...leaf, TOTAL_REV: rev, TOTAL_PAY: pay, TOTAL_OPEX: opex, TOTAL_COST: cost, GOP: gop, TOTAL_NONOP: nonop, EBITDA: ebitda, TOTAL_CAPITAL: capital, EBITDA_AFTER: ebitdaAfter, EBT: ebt, TAX: tax, NET: net };
}

function buildLeaves(bd: BigPictureBreakdown | null, annual: Record<string, number>): Col {
  const leaf: Col = {};
  let bdExp = 0;
  for (const b of bd?.operating ?? []) { leaf["PAY_" + b.group] = b.payroll; leaf["OPEX_" + b.group] = b.opex; leaf["COST_" + b.group] = b.cost; bdExp += b.payroll + b.opex + b.cost; }
  for (const b of bd?.overhead ?? []) { leaf["PAY_" + b.group] = (leaf["PAY_" + b.group] || 0) + b.payroll; leaf["OPEX_" + b.group] = (leaf["OPEX_" + b.group] || 0) + b.opex; if (Math.abs(b.cost) > 0.5) leaf["COST_" + b.group] = (leaf["COST_" + b.group] || 0) + b.cost; bdExp += b.payroll + b.opex + b.cost; }
  // Ingresos por línea del P&L oficial (reconcilian exacto → sin plug grande)
  for (const [code] of REV_LIST) leaf[code] = annual[code] || 0;
  // Residual: tiene que ser ~0. Si crece, es que nació una línea de ingreso que
  // esta lista no conoce — y ese ingreso no responde a ningún driver del plan.
  leaf.REV_OTHER = (annual.TOTAL_REVENUES || 0) - REV_LIST.reduce((s, [c]) => s + (annual[c] || 0), 0);
  // Gastos: el detalle bruto sobra lo que el P&L netea vía allocations (cafetería/lavandería)
  leaf.ADJ = ((annual.TOTAL_OPERATING_EXPENSES || 0) + (annual.TOTAL_OVERHEAD_EXPENSES || 0)) - bdExp;   // crédito de neteo (negativo)
  leaf.RENT = annual.RENT || 0; leaf.MGMT_FEE_3 = annual.MGMT_FEE_3 || 0; leaf.MGMT_FEE_5_ROYALTIES = annual.MGMT_FEE_5_ROYALTIES || 0; leaf.PROPERTY_INSURANCE = annual.PROPERTY_INSURANCE || 0;
  const nonopTotal = (annual.TOTAL_GOP || 0) - (annual.EBITDA_BEFORE_CAPITAL || 0);
  leaf.NONOP_OTHER = nonopTotal - (leaf.RENT + leaf.MGMT_FEE_3 + leaf.MGMT_FEE_5_ROYALTIES + leaf.PROPERTY_INSURANCE);
  leaf.CAP_RESERVE = annual.CAPITAL_RESERVE || 0; leaf.CAP_LARGE = annual.LARGE_CAPEX || 0;
  const ebitdaAfter = (annual.EBITDA_BEFORE_CAPITAL || 0) - (leaf.CAP_RESERVE + leaf.CAP_LARGE);
  leaf.DEPR_FIN = ebitdaAfter - (annual.EBT || 0);   // depreciación/financiero/otros bajo EBITDA, pre-impuesto
  return leaf;
}

const LS_KEY = "bigpicture_growth_v2";

export default function BigPicturePage() {
  const tc = useTranslations("common");
  const t = useTranslations("bigPicture");
  const [f, setF] = useState<{ leaf: Col; bd: BigPictureBreakdown | null } | null>(null);
  const [a, setA] = useState<Col | null>(null);
  const [b, setB] = useState<Col | null>(null);
  type Kpi = { avail: number; occ: number; pax: number };
  const [kpi, setKpi] = useState<{ a: Kpi; f: Kpi; b: Kpi }>({ a: { avail: 0, occ: 0, pax: 0 }, f: { avail: 0, occ: 0, pax: 0 }, b: { avail: 0, occ: 0, pax: 0 } });
  const [names, setNames] = useState({ a: "Actual 2025", f: "Forecast 2026", b: "Budget 2026" });
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Tres columnas, tres llaves distintas: cada selector se acuerda de lo ultimo
  // elegido EN ESTA pantalla y, si nunca se eligio, abre con el preferido del
  // owner. Compartir una sola llave haria que mover una referencia le cambiara
  // el escenario a las otras dos.
  const [baseId, setBaseId] = useEscenarioDe("planning/big-picture:forecast", scenarios, "forecast");   // base (crece sobre esta)
  const [colAId, setColAId] = useEscenarioDe("planning/big-picture:actual", scenarios, "actual");       // referencia izquierda
  const [colBId, setColBId] = useEscenarioDe("planning/big-picture:budget", scenarios, "budget");       // referencia media
  const [applying, setApplying] = useState(false);
  const [growth, setGrowth] = useState<Record<string, number>>({});
  const [globalPct, setGlobalPct] = useState(0);
  const [vert, setVert] = useState(true);   // análisis vertical (% de ingresos) bajo cada $
  const [collapsed, setCollapsed] = useState(false);   // Resumen: solo grandes totales
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  // versiones
  const [versions, setVersions] = useState<BPVersionMeta[]>([]);
  const [verId, setVerId] = useState<string>("");
  const [verName, setVerName] = useState<string>("Plan Big Picture 2027");
  const [msg, setMsg] = useState<string | null>(null);
  // A0.-2: si la base cuadra Resumen contra Detalle. Este tab construye el 2027
  // entero encima de `baseId` sin decirlo — armar sobre una base descuadrada
  // (p. ej. el ACTUAL 2024, con $43.698 que no llegan al P&L) no avisaba nada.
  const [cuadreBase, setCuadreBase] = useState<Cuadre | null>(null);

  useEffect(() => {
    try { const s = localStorage.getItem(LS_KEY); setGrowth({ MGMT_FEE_3: 3, CAP_RESERVE: 4, ...(s ? JSON.parse(s) : {}) }); } catch { /* */ }
    (async () => {
      try {
        // La eleccion de las tres columnas la hacen los `useEscenarioDe` cuando
        // llega la lista: aca solo se carga.
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        if (!all.length) setLoading(false);
        try { setVersions(await listBigPictureVersions(HOTEL_ID)); } catch { /* */ }
      } catch (e) { setErr(e instanceof Error ? e.message : tc("error")); setLoading(false); }
    })();
  }, []);

  /** Trae una columna. Da igual si el id vino del selector o de lo recordado. */
  const cargarCol = useCallback(async (which: "a" | "f" | "b", id: string) => {
    if (!id) { if (which === "a") setA(null); else if (which === "b") setB(null); else setF(null); return; }
    const sc = scenarios.find(s => s.id === id);
    const nm = sc ? `${sc.type} ${sc.version} ${sc.year}` : "—";
    try {
      const [pl, bd] = await Promise.all([getPLMonthly(id), getBigPictureBreakdown(id)]);
      const leaf = buildLeaves(bd, pl.annual);
      const k: Kpi = { avail: pl.annual_kpis?.rooms_available ?? 0, occ: pl.annual_kpis?.rooms_occupied ?? 0, pax: pl.annual_kpis?.guests ?? 0 };
      if (which === "a") { setA(leaf); setKpi(p => ({ ...p, a: k })); setNames(n => ({ ...n, a: nm })); }
      else if (which === "b") { setB(leaf); setKpi(p => ({ ...p, b: k })); setNames(n => ({ ...n, b: nm })); }
      else { setF({ leaf, bd }); setKpi(p => ({ ...p, f: k })); setNames(n => ({ ...n, f: nm })); }
    } catch (e) { setMsg(e instanceof Error ? e.message : tc("error")); }
  }, [scenarios, tc]);

  useEffect(() => { cargarCol("a", colAId); }, [colAId, cargarCol]);
  useEffect(() => { cargarCol("b", colBId); }, [colBId, cargarCol]);
  // La grilla no se muestra hasta que este la BASE: es contra ella que crece
  // todo el plan, y sin ella la pantalla saldria en blanco.
  useEffect(() => {
    if (!baseId) return;
    let vivo = true;
    (async () => { await cargarCol("f", baseId); if (vivo) setLoading(false); })();
    return () => { vivo = false; };
  }, [baseId, cargarCol]);

  // El veredicto de la base: si su Resumen y su Detalle cuadran. No bloquea
  // nada — solo lo muestra, que es todo lo que A0.-2 pedía.
  useEffect(() => {
    if (!baseId) { setCuadreBase(null); return; }
    let vivo = true;
    getCuadre(baseId).then(c => { if (vivo) setCuadreBase(c); })
      .catch(() => { if (vivo) setCuadreBase(null); });
    return () => { vivo = false; };
  }, [baseId]);

  function persistLocal(g: Record<string, number>) { try { localStorage.setItem(LS_KEY, JSON.stringify(g)); } catch { /* */ } }
  function setG(code: string, v: string) { const n = v === "" ? 0 : parseFloat(v); if (isNaN(n)) return; setGrowth(g => { const next = { ...g, [code]: n }; persistLocal(next); return next; }); }
  function applyGlobal() { if (!f) return; const next: Record<string, number> = {}; for (const k of Object.keys(f.leaf)) next[k] = globalPct; setGrowth(next); persistLocal(next); }
  function clearGrowth() { setGrowth({}); persistLocal({}); }

  async function loadVersion(id: string) {
    setVerId(id); if (!id) return;
    try { const v = await getBigPictureVersion(id); setGrowth(v.growth || {}); persistLocal(v.growth || {}); setVerName(v.name); setMsg(t("loadedVersion", { nombre: v.name })); } catch (e) { setMsg(e instanceof Error ? e.message : tc("error")); }
  }
  async function save() {
    try {
      const r = await saveBigPictureVersion({ id: verId || undefined, name: verName.trim() || "Budget 2027", base_scenario_id: baseId, target_year: 2027, growth });
      setVerId(r.id); setMsg(t("savedVersion", { nombre: r.name })); setVersions(await listBigPictureVersions(HOTEL_ID));
    } catch (e) { setMsg(e instanceof Error ? e.message : tc("error")); }
  }
  async function saveAsNew() { setVerId(""); await save(); }
  async function removeVersion() {
    if (!verId || !window.confirm(t("deleteConfirm", { nombre: verName }))) return;
    await deleteBigPictureVersion(verId); setVerId(""); setVersions(await listBigPictureVersions(HOTEL_ID)); setMsg(t("deleted"));
  }

  // Drivers 2027 (compartidos por el bloque de KPIs y las líneas de ingreso)
  const drivers = useMemo(() => {
    const availV = kpi.f.avail * (1 + (growth.ROOMS_AVAIL || 0) / 100);
    const occV = kpi.f.occ * (1 + (growth.ROOMS_OCC || 0) / 100);
    const ratioF = kpi.f.occ ? kpi.f.pax / kpi.f.occ : 0;
    const pnVal = growth.PAX_NIGHT !== undefined && growth.PAX_NIGHT > 0 ? growth.PAX_NIGHT : ratioF;
    const pax27 = occV * pnVal;
    // ADR libre (editable). Default = ADR del Forecast (rooms rev / noches ocup.). Rooms rev = ADR × noches.
    const adrF = kpi.f.occ ? (f?.leaf.REV_ROOMS ?? 0) / kpi.f.occ : 0;
    const adrVal = growth.ADR !== undefined && growth.ADR > 0 ? growth.ADR : adrF;
    const rooms27 = adrVal * occV;
    return { availV, occV, ratioF, pnVal, pax27, adrF, adrVal, rooms27, paxRatio: kpi.f.pax ? pax27 / kpi.f.pax : 1, nightsRatio: kpi.f.occ ? occV / kpi.f.occ : 1 };
  }, [kpi, growth, f]);

  // Líneas de ingreso manejadas por driver de volumen
  const DRIVEN: Record<string, "pax" | "nights"> = { REV_SPA: "pax", REV_FB: "pax", REV_TOURS: "pax", REV_MISC_OTHER: "pax" };

  const cols = useMemo(() => {
    const ca = a ? compute(a) : null, cf = f ? compute(f.leaf) : null, cb = b ? compute(b) : null;
    let c27: Col | null = null;
    if (f) {
      const fl = f.leaf; const l: Col = {};
      for (const k of Object.keys(fl)) {
        if (k === "REV_RETAIL") continue;          // retail = % de rooms (después)
        if (k === "REV_ROOMS") { l[k] = drivers.rooms27; continue; }   // automático = ADR × noches
        if (DRIVEN[k]) { const r = DRIVEN[k] === "pax" ? drivers.paxRatio : drivers.nightsRatio; l[k] = (fl[k] || 0) * r * (1 + (growth[k] || 0) / 100); }
        else l[k] = (fl[k] || 0) * (1 + (growth[k] || 0) / 100);
      }
      // Retail = % de los ingresos de Rooms. El % de la fila Retail es ese %
      // (poné 1.2). Si está en 0, usa el ratio del Forecast.
      const retailPct = growth.REV_RETAIL !== undefined && growth.REV_RETAIL > 0 ? growth.REV_RETAIL / 100 : (fl.REV_ROOMS ? (fl.REV_RETAIL || 0) / fl.REV_ROOMS : 0);
      l.REV_RETAIL = retailPct * (l.REV_ROOMS || 0);
      // Líneas calculadas como % de los INGRESOS totales 2027:
      const rev27 = sumPrefix(l, "REV_");
      const mgmtPct = growth.MGMT_FEE_3 !== undefined && growth.MGMT_FEE_3 > 0 ? growth.MGMT_FEE_3 / 100 : 0.03;   // Management Fee 3% ingresos
      const resPct = growth.CAP_RESERVE !== undefined && growth.CAP_RESERVE > 0 ? growth.CAP_RESERVE / 100 : 0.04;   // Reserva de Capital 4% ingresos
      l.MGMT_FEE_3 = mgmtPct * rev27;
      l.CAP_RESERVE = resPct * rev27;
      l.CAP_LARGE = 0;   // CapEx Mayor no existe en el budget
      c27 = compute(l);
    }
    return { ca, cf, cb, c27 };
  }, [a, f, b, growth, drivers]);

  // Destino del Big Picture: la versión Budget 2027 con "BIG" en el nombre (draft4-BIG).
  const bigTarget = useMemo(() => scenarios.find(s => s.type === "BUDGET" && s.year === 2027 && /big/i.test(s.version)), [scenarios]);

  async function applyToBig() {
    if (!bigTarget) { setMsg(t("noBigTarget")); return; }
    if (!f || !baseId || !cols.c27) { setMsg(t("missingBase")); return; }
    const c = cols.c27;
    const groups: Record<string, { revenue: number; payroll: number; opex: number; cost: number }> = {};
    for (const b of [...(f.bd?.operating ?? []), ...(f.bd?.overhead ?? [])]) {
      const revCode = REV_CODE_FOR_GROUP[b.group];
      groups[b.group] = {
        revenue: revCode ? (c[revCode] || 0) : 0,
        payroll: c["PAY_" + b.group] || 0, opex: c["OPEX_" + b.group] || 0, cost: c["COST_" + b.group] || 0,
      };
    }
    const payload = {
      base_scenario_id: baseId, groups, belowgop_total: (c.GOP || 0) - (c.NET || 0),
      stats: { rooms_available: drivers.availV, rooms_occupied: drivers.occV, guests: drivers.pax27 },
    };
    setApplying(true); setMsg(null);
    try {
      const dry = await applyBigPicture(bigTarget.id, payload, true);
      const p = dry.preview;
      const ok = window.confirm(t("applyConfirm", {
        destino: dry.target,
        ingresos: Math.round(p.revenue).toLocaleString(),
        gop: Math.round(p.gop).toLocaleString(),
        ebitda: Math.round(p.ebitda).toLocaleString(),
        net: Math.round(p.net).toLocaleString(),
      }));
      if (!ok) { setApplying(false); return; }
      await applyBigPicture(bigTarget.id, payload, false);
      setMsg(t("applied", { destino: dry.target }));
    } catch (e) { setMsg(e instanceof Error ? e.message : tc("error")); }
    finally { setApplying(false); }
  }

  if (loading) return <div style={{ padding: 30, color: "var(--text-secondary)" }}>{tc("loading")}</div>;
  if (err) return <div style={{ padding: 30, color: "var(--negative)" }}>⚠ {err}</div>;

  const cell: React.CSSProperties = { textAlign: "right", padding: "4px 12px", whiteSpace: "nowrap", fontFamily: "var(--font-mono, monospace)" };
  const stickyL: React.CSSProperties = { position: "sticky", left: 0, background: "var(--bg-elevated)", zIndex: 1 };
  const opGroups = f?.bd?.operating ?? [];
  const ohGroups = f?.bd?.overhead ?? [];

  // % vertical (sobre los ingresos de esa columna)
  const trA = cols.ca?.TOTAL_REV ?? 0, trB = cols.cb?.TOTAL_REV ?? 0, trF = cols.cf?.TOTAL_REV ?? 0, tr27 = cols.c27?.TOTAL_REV ?? 0;

  // celda de valor: muestra el $ y, si el análisis vertical está activo, el % de ingresos debajo
  function valTd(v: number, totalRev: number, key: string, opts?: { strong?: boolean; brand?: boolean }) {
    const pctv = totalRev ? (v / totalRev * 100).toFixed(1) + "%" : "—";
    return (
      <td key={key} className="mono" style={{ ...cell, fontWeight: opts?.strong ? 800 : undefined, color: opts?.brand ? "var(--brand)" : v < 0 ? "var(--negative)" : "var(--text-primary)" }}>
        {fmt(v)}
        {vert && <div style={{ fontSize: 9.5, fontWeight: 400, color: "var(--text-disabled)", marginTop: 1 }}>{pctv}</div>}
      </td>
    );
  }
  function varTds(vf: number, v27: number, strong = false) {
    const d = v27 - vf;
    const pct = Math.abs(vf) > 0.5 ? (d / Math.abs(vf) * 100) : null;
    const col = (x: number) => x > 0 ? "var(--positive)" : x < 0 ? "var(--negative)" : "var(--text-secondary)";
    return [
      <td key="vd" className="mono" style={{ ...cell, fontWeight: strong ? 800 : undefined, color: col(d) }}>{(d > 0 ? "+" : "") + fmt(d)}</td>,
      <td key="vp" className="mono" style={{ ...cell, fontStyle: "italic", color: pct === null ? "var(--text-secondary)" : col(pct) }}>{pct === null ? "—" : (pct > 0 ? "+" : "") + pct.toFixed(1) + "%"}</td>,
    ];
  }

  function Row({ code, label, indent = true, auto = false }: { code: string; label: string; indent?: boolean; auto?: boolean }) {
    const va = cols.ca?.[code] ?? 0, vf = cols.cf?.[code] ?? 0, vb = cols.cb?.[code] ?? 0, v27 = cols.c27?.[code] ?? 0;
    return (
      <tr key={code} style={{ borderTop: "1px solid var(--border-subtle)" }}>
        <td style={{ ...stickyL, textAlign: "left", padding: "4px 12px", paddingLeft: indent ? 28 : 12, color: "var(--text-secondary)" }}>{label}</td>
        {valTd(va, trA, "a")}
        {valTd(vb, trB, "b")}
        {valTd(vf, trF, "f")}
        <td style={{ textAlign: "center", padding: "2px 6px" }}>
          {auto ? <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>auto</span>
            : <input type="number" value={growth[code] ?? 0} onChange={e => setG(code, e.target.value)} onFocus={e => e.target.select()} onWheel={e => e.currentTarget.blur()} className="fin-input" style={{ width: 56, textAlign: "right", fontSize: 11 }} />}
        </td>
        {valTd(v27, tr27, "27", { brand: true, strong: true })}
        {varTds(vf, v27)}
      </tr>
    );
  }
  function Total({ code, label }: { code: string; label: string }) {
    const va = cols.ca?.[code] ?? 0, vf = cols.cf?.[code] ?? 0, vb = cols.cb?.[code] ?? 0, v27 = cols.c27?.[code] ?? 0;
    return (
      <tr key={code} style={{ borderTop: "2px solid var(--border-medium)", background: "rgba(200,162,74,0.08)", fontWeight: 800 }}>
        <td style={{ ...stickyL, textAlign: "left", padding: "6px 12px", background: "var(--bg-elevated)" }}>{label}</td>
        {valTd(va, trA, "a", { strong: true })}
        {valTd(vb, trB, "b", { strong: true })}
        {valTd(vf, trF, "f", { strong: true })}
        <td />
        {valTd(v27, tr27, "27", { strong: true, brand: true })}
        {varTds(vf, v27, true)}
      </tr>
    );
  }
  // ── Bajar a Excel ────────────────────────────────────────────────────────
  // Réplica del cuadro que está en pantalla, con las columnas que el usuario
  // eligió comparar y los % que tiene digitados. Va en DOS hojas: el bloque de
  // drivers mezcla unidades (noches, ocupación %, pax, dólares) que no caben en
  // el mismo formato de columna que el resto del cuadro.
  //
  // Sale el detalle completo aunque la pantalla esté en modo Resumen: colapsar
  // es para leer, no para recortar el archivo que uno se lleva.
  async function bajarExcel() {
    const VACIA = [null, null, null, null, null, null, null];
    const filas: FilaCuadro[] = [];
    const sec = (label: string) => filas.push({ label, nivel: 0, es_total: true, valores: VACIA });
    const fila = (code: string, label: string, opts?: { total?: boolean; auto?: boolean }) => {
      const va = cols.ca?.[code] ?? 0, vb = cols.cb?.[code] ?? 0;
      const vf = cols.cf?.[code] ?? 0, v27 = cols.c27?.[code] ?? 0;
      const d = v27 - vf;
      filas.push({
        label, nivel: opts?.total ? 0 : 1, es_total: !!opts?.total,
        valores: [va, vb, vf,
          opts?.total || opts?.auto ? null : (growth[code] ?? 0) / 100,
          v27, d,
          // Var % contra una base de cero no es infinito, es "no aplica".
          Math.abs(vf) > 0.5 ? d / Math.abs(vf) : null],
      });
    };

    sec(t("secRevenue"));
    for (const [c, l] of REV_LIST) fila(c, l, { auto: c === "REV_ROOMS" });
    fila("TOTAL_REV", t("totalRevenue"), { total: true });

    sec(t("secPayroll"));
    for (const g of opGroups) fila("PAY_" + g.group, g.name);
    for (const g of ohGroups) fila("PAY_" + g.group, g.name + " (OH)");
    fila("TOTAL_PAY", t("totalPayroll"), { total: true });

    sec(t("secOpex"));
    for (const g of opGroups) fila("OPEX_" + g.group, g.name);
    for (const g of ohGroups) fila("OPEX_" + g.group, g.name + " (OH)");
    fila("TOTAL_OPEX", t("totalOpex"), { total: true });

    sec(t("secCost"));
    for (const g of opGroups.filter(g => Math.abs(f?.leaf["COST_" + g.group] || 0) > 0.5)) fila("COST_" + g.group, g.name);
    fila("TOTAL_COST", t("totalCost"), { total: true });
    fila("ADJ", t("netAdjust"), { auto: true });

    fila("GOP", "GOP (Gross Operating Profit)", { total: true });

    sec(t("secNonop"));
    for (const [c, l] of NONOP) fila(c, l);
    fila("TOTAL_NONOP", t("totalNonop"), { total: true });
    fila("EBITDA", "EBITDA", { total: true });

    sec(t("secCapital"));
    for (const [c, l] of CAPITAL) fila(c, l, { auto: c === "CAP_LARGE" });
    fila("EBITDA_AFTER", t("ebitdaAfterCapital"), { total: true });
    fila("DEPR_FIN", t("deprFin"));
    fila("EBT", t("ebt"), { total: true });
    fila("TAX", t("incomeTax"), { auto: true });
    fila("NET", t("netProfit"), { total: true });

    const d4 = (va: number, vb: number, vf: number, v: number) => [va, vb, vf, v];
    const rt = (k: "a" | "b") => kpi[k].occ ? (cols[k === "a" ? "ca" : "cb"]?.REV_ROOMS ?? 0) / kpi[k].occ : 0;
    const dr: FilaCuadro[] = [
      { label: t("drvAvail"), formato: "num", valores: d4(kpi.a.avail, kpi.b.avail, kpi.f.avail, drivers.availV) },
      { label: t("drvOcc"), formato: "num", valores: d4(kpi.a.occ, kpi.b.occ, kpi.f.occ, drivers.occV) },
      { label: t("drvOccPct"), formato: "pct", valores: d4(
        kpi.a.avail ? kpi.a.occ / kpi.a.avail : 0, kpi.b.avail ? kpi.b.occ / kpi.b.avail : 0,
        kpi.f.avail ? kpi.f.occ / kpi.f.avail : 0, drivers.availV ? drivers.occV / drivers.availV : 0) },
      { label: t("drvPaxNight"), formato: "num1", valores: d4(
        kpi.a.occ ? kpi.a.pax / kpi.a.occ : 0, kpi.b.occ ? kpi.b.pax / kpi.b.occ : 0, drivers.ratioF, drivers.pnVal) },
      { label: t("drvTotalPax"), formato: "num", valores: d4(kpi.a.pax, kpi.b.pax, kpi.f.pax, drivers.pax27) },
      { label: t("drvAdrXls"), formato: "usd2", valores: d4(rt("a"), rt("b"), drivers.adrF, drivers.adrVal) },
      { label: t("drvRoomsXls"), es_total: true, formato: "usd", valores: d4(
        cols.ca?.REV_ROOMS ?? 0, cols.cb?.REV_ROOMS ?? 0, cols.cf?.REV_ROOMS ?? 0, drivers.rooms27) },
    ];

    const colsCuadro = [
      { label: tc("concept"), ancho: 48, formato: "texto" as const },
      { label: names.a, formato: "usd" as const },
      { label: names.b, formato: "usd" as const },
      { label: names.f + " (base)", formato: "usd" as const },
      { label: t("growthPct"), ancho: 10, formato: "pct" as const },
      { label: "Budget 2027", ancho: 16, formato: "usd" as const },
      { label: "Var $", formato: "usd" as const },
      { label: "Var %", ancho: 10, formato: "pct" as const },
    ];
    try {
      await bajarCuadros("Big_Picture_2027", [
        { titulo: "Budget Big Picture 2027", hoja: "Big Picture",
          subtitulo: t("xlsSubtitle", { base: names.f }),
          columnas: colsCuadro, filas },
        { titulo: t("xlsDriversTitle"), hoja: "Drivers",
          subtitulo: "USD",
          columnas: [colsCuadro[0], colsCuadro[1], colsCuadro[2], colsCuadro[3], colsCuadro[5]],
          filas: dr },
      ]);
    } catch (e) { setMsg(e instanceof Error ? e.message : t("xlsError")); }
  }

  const SecHead = ({ t }: { t: string }) => <tr key={t} style={{ background: "var(--bg-input)" }}><td colSpan={8} style={{ ...stickyL, background: "var(--bg-input)", padding: "6px 12px", color: "var(--brand)", fontSize: 11, fontWeight: 800, letterSpacing: 0.4 }}>{t}</td></tr>;
  const btn: React.CSSProperties = { padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer" };

  return (
    <div className="pag pag-ancha" style={{ padding: "18px 20px 44px" }}>
      <IrA esc={baseId} />
      <div style={{ textAlign: "center", marginBottom: 6 }}>
        <h1 style={{ fontSize: 30, fontWeight: 800, margin: 0 }}><span style={{ color: "var(--text-primary)" }}>Budget </span><span style={{ color: "var(--brand)" }}>Big Picture 2027</span></h1>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 600, marginTop: 4 }}>{t.rich("subtitle", { b: (c: React.ReactNode) => <b>{c}</b>, base: names.f })}</div>
      </div>

      {/* Versiones */}
      <div style={{ display: "flex", gap: 8, justifyContent: "center", alignItems: "center", flexWrap: "wrap", margin: "12px 0 8px", background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "10px 14px" }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--brand)" }} title={t("savedPlanTitle")}>📑 {t("savedPlan")}</span>
        <select value={verId} onChange={e => loadVersion(e.target.value)} style={{ background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "6px 10px", fontSize: 12 }}>
          <option value="">{t("newVersion")}</option>
          {versions.map(v => <option key={v.id} value={v.id} style={{ background: "var(--bg-input)" }}>{v.name}</option>)}
        </select>
        <input value={verName} onChange={e => setVerName(e.target.value)} placeholder={t("versionName")} style={{ background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "6px 10px", fontSize: 12, width: 200 }} />
        <button onClick={save} style={{ ...btn, background: "var(--positive)", color: "#fff", border: "1px solid var(--positive)" }}>💾 {tc("save")}</button>
        <button onClick={saveAsNew} style={{ ...btn, background: "transparent", color: "var(--brand)", border: "1px solid var(--brand)" }}>＋ {t("saveAsNew")}</button>
        {verId && <button onClick={removeVersion} style={{ ...btn, background: "transparent", color: "var(--negative)", border: "1px solid var(--negative)" }}>🗑</button>}
        <span style={{ color: "var(--border-medium)" }}>|</span>
        <button onClick={applyToBig} disabled={applying || !bigTarget} title={bigTarget ? t("applyTitle", { destino: `${bigTarget.type} ${bigTarget.version}` }) : t("applyTitleMissing")}
          style={{ ...btn, background: bigTarget && !applying ? "var(--accent-excel)" : "#555", color: "#fff", border: "none" }}>
          {applying ? t("applying") : bigTarget ? t("applyTo", { version: bigTarget.version }) : t("applyMissing")}
        </button>
      </div>

      {/* Comparar con — versiones elegibles por columna */}
      <div style={{ display: "flex", gap: 12, justifyContent: "center", alignItems: "flex-end", flexWrap: "wrap", margin: "0 0 10px" }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--brand)", alignSelf: "center" }}>🔀 {t("compareWith")}</span>
        {([["a", colAId, setColAId, t("ref1")], ["b", colBId, setColBId, t("ref2")], ["f", baseId, setBaseId, t("baseCol")]] as const).map(([w, val, elegirCol, lbl]) => (
          <label key={w} style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 10, color: w === "f" ? "var(--brand)" : "var(--text-secondary)" }}>
            <span style={{ fontWeight: w === "f" ? 700 : 400 }}>{lbl}</span>
            <select value={val} onChange={e => elegirCol(e.target.value)}
              style={{ background: "var(--bg-input)", color: "var(--text-primary)", border: `1px solid ${w === "f" ? "var(--brand)" : "var(--border-medium)"}`, borderRadius: 6, padding: "5px 8px", fontSize: 12 }}>
              {scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{s.type} · {s.version} · {s.year}</option>)}
            </select>
            {/* A0.-2: si la base cuadra Resumen contra Detalle. Solo se avisa —
                nada se bloquea: el owner decide si construye igual encima. */}
            {w === "f" && cuadreBase?.comparable && (
              <span
                title={cuadreBase.veredicto.motivo}
                style={{
                  fontSize: 9.5, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                  color: cuadreBase.manda === "detalle" ? "var(--accent-excel)" : "#a86b00",
                  background: cuadreBase.manda === "detalle" ? "rgba(26,107,60,.15)" : "rgba(168,107,0,.15)",
                  cursor: "help",
                }}>
                {cuadreBase.manda === "detalle" ? t("detailTies") : t("summaryRules", { n: cuadreBase.descuadres })}
              </span>
            )}
          </label>
        ))}
      </div>

      {/* Crecimiento global */}
      <div style={{ display: "flex", gap: 10, justifyContent: "center", alignItems: "center", flexWrap: "wrap", margin: "0 0 12px" }}>
        <label style={{ fontSize: 12, color: "var(--text-secondary)", fontWeight: 600 }}>{t("globalGrowth")}</label>
        <input type="number" value={globalPct} onChange={e => setGlobalPct(parseFloat(e.target.value) || 0)} onFocus={e => e.target.select()} onWheel={e => e.currentTarget.blur()} className="fin-input" style={{ width: 70, textAlign: "right" }} />
        <span style={{ color: "var(--text-secondary)", fontSize: 12 }}>%</span>
        <button onClick={applyGlobal} style={{ ...btn, background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)" }}>{t("applyToAll")}</button>
        <button onClick={clearGrowth} style={{ ...btn, background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>{t("clear")}</button>
        <span style={{ color: "var(--border-medium)" }}>|</span>
        <button onClick={() => setVert(v => !v)} title={t("verticalHint")} style={{ ...btn, background: vert ? "var(--brand)" : "transparent", color: vert ? "#fff" : "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>📊 Vertical % {vert ? "ON" : "OFF"}</button>
        <button onClick={() => setCollapsed(c => !c)} title={t("collapseTitle")} style={{ ...btn, background: collapsed ? "var(--brand)" : "transparent", color: collapsed ? "#fff" : "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>{collapsed ? `▸ ${t("summary")}` : `▾ ${t("detail")}`}</button>
        <button onClick={bajarExcel} title={t("xlsHint")} style={{ ...btn, background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>⬇ Excel</button>
        {msg && <span style={{ fontSize: 12, color: msg.startsWith("✓") ? "var(--positive)" : "var(--negative)" }}>{msg}</span>}
      </div>

      <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, minWidth: 1140 }}>
          <thead>
            <tr style={{ background: "var(--bg-header)" }}>
              <th style={{ ...stickyL, textAlign: "left", padding: "9px 12px", background: "var(--bg-header)", minWidth: 240 }}>{tc("concept")}{vert && <span style={{ fontSize: 9, color: "var(--text-disabled)" }}> {t("conceptPct")}</span>}</th>
              <th style={{ textAlign: "right", padding: "9px 12px", color: "var(--text-secondary)" }}>{names.a}</th>
              <th style={{ textAlign: "right", padding: "9px 12px", color: "var(--text-secondary)" }}>{names.b}</th>
              <th style={{ textAlign: "right", padding: "9px 12px", color: "var(--text-secondary)" }}>{names.f}</th>
              <th style={{ textAlign: "center", padding: "9px 12px", color: "var(--brand)" }}>{t("growthPct")}</th>
              <th style={{ textAlign: "right", padding: "9px 12px", color: "var(--brand)" }}>Budget 2027</th>
              <th style={{ textAlign: "right", padding: "9px 12px", color: "var(--text-secondary)" }} title="Budget 2027 − Forecast 2026">Var $</th>
              <th style={{ textAlign: "right", padding: "9px 12px", color: "var(--text-secondary)", fontStyle: "italic" }}>Var %</th>
            </tr>
          </thead>
          <tbody>
            {SecHead({ t: t("secDrivers") })}
            {(() => {
              const num = (v: number) => Math.round(v).toLocaleString("en-US");
              const usd = (v: number) => v ? "$" + Math.round(v).toLocaleString() : "—";
              const pn = (v: number) => v.toFixed(2);
              const pc = (v: number) => (v * 100).toFixed(1) + "%";
              // valores por columna
              const avail = { a: kpi.a.avail, b: kpi.b.avail, f: kpi.f.avail, v: drivers.availV };
              const occ = { a: kpi.a.occ, b: kpi.b.occ, f: kpi.f.occ, v: drivers.occV };
              const pnVal = drivers.pnVal;
              const paxN = { a: kpi.a.occ ? kpi.a.pax / kpi.a.occ : 0, b: kpi.b.occ ? kpi.b.pax / kpi.b.occ : 0, f: drivers.ratioF, v: pnVal };
              const pax = { a: kpi.a.pax, b: kpi.b.pax, f: kpi.f.pax, v: drivers.pax27 };
              const adr = { a: kpi.a.occ ? (cols.ca?.REV_ROOMS ?? 0) / kpi.a.occ : 0, b: kpi.b.occ ? (cols.cb?.REV_ROOMS ?? 0) / kpi.b.occ : 0, f: drivers.adrF, v: drivers.adrVal };
              const rooms = { a: cols.ca?.REV_ROOMS ?? 0, b: cols.cb?.REV_ROOMS ?? 0, f: cols.cf?.REV_ROOMS ?? 0, v: drivers.rooms27 };
              const td3 = (va: number, vb: number, vf: number, fm: (x: number) => string) => [
                <td key="a" className="mono" style={cell}>{fm(va)}</td>,
                <td key="b" className="mono" style={cell}>{fm(vb)}</td>,
                <td key="f" className="mono" style={cell}>{fm(vf)}</td>,
              ];
              const KRow = (label: string, d: { a: number; b: number; f: number; v: number }, fm: (x: number) => string, input: React.ReactNode, showVar = true) => (
                <tr style={{ borderTop: "1px solid var(--border-subtle)" }}>
                  <td style={{ ...stickyL, textAlign: "left", padding: "4px 12px", color: "var(--text-secondary)" }}>{label}</td>
                  {td3(d.a, d.b, d.f, fm)}
                  <td style={{ textAlign: "center", padding: "2px 6px" }}>{input}</td>
                  <td className="mono" style={{ ...cell, fontWeight: 700, color: "var(--brand)" }}>{fm(d.v)}</td>
                  {showVar ? varTds(d.f, d.v) : [<td key="vd" />, <td key="vp" />]}
                </tr>
              );
              const pctInput = (key: string) => <input type="number" value={growth[key] ?? 0} onChange={e => setG(key, e.target.value)} onFocus={e => e.target.select()} onWheel={e => e.currentTarget.blur()} className="fin-input" style={{ width: 56, textAlign: "right", fontSize: 11 }} title={t("growthPctTitle")} />;
              return (<>
                {KRow(t("drvAvail"), avail, num, pctInput("ROOMS_AVAIL"))}
                {KRow(t("drvOcc"), occ, num, pctInput("ROOMS_OCC"))}
                {KRow(t("drvOccPct"), { a: avail.a ? occ.a / avail.a : 0, b: avail.b ? occ.b / avail.b : 0, f: avail.f ? occ.f / avail.f : 0, v: avail.v ? occ.v / avail.v : 0 }, pc, <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>auto</span>, false)}
                {KRow(t("drvPaxNight"), paxN, pn, <input type="number" step="0.1" value={pnVal.toFixed(2)} onChange={e => setG("PAX_NIGHT", e.target.value)} onFocus={e => e.target.select()} onWheel={e => e.currentTarget.blur()} className="fin-input" style={{ width: 56, textAlign: "right", fontSize: 11 }} title={t("paxNightTitle")} />, false)}
                {KRow(t("drvTotalPax"), pax, num, <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>auto</span>)}
                {KRow(t("drvAdr"), adr, usd, <input type="number" value={Math.round(drivers.adrVal)} onChange={e => setG("ADR", e.target.value)} onFocus={e => e.target.select()} onWheel={e => e.currentTarget.blur()} className="fin-input" style={{ width: 56, textAlign: "right", fontSize: 11 }} title={t("adrTitle")} />)}
                {KRow(t("drvRooms"), rooms, usd, <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>auto</span>)}
              </>);
            })()}

            {!collapsed && SecHead({ t: t("secRevenue") })}
            {!collapsed && REV_LIST.map(([c, l]) => {
              const drv = c === "REV_ROOMS" ? t("drvAdrNights") : c === "REV_RETAIL" ? t("drvPctRooms") : DRIVEN[c] === "pax" ? t("drvPerPax") : DRIVEN[c] === "nights" ? t("drvPerNight") : t("drvFreePct");
              return Row({ code: c, label: `${l} · ${drv}`, auto: c === "REV_ROOMS" });
            })}
            {Total({ code: "TOTAL_REV", label: t("totalRevenue") })}

            {!collapsed && SecHead({ t: t("secPayroll") })}
            {!collapsed && opGroups.map(g => Row({ code: "PAY_" + g.group, label: g.name }))}
            {!collapsed && ohGroups.map(g => Row({ code: "PAY_" + g.group, label: g.name + " (OH)" }))}
            {Total({ code: "TOTAL_PAY", label: t("totalPayroll") })}

            {!collapsed && SecHead({ t: t("secOpex") })}
            {!collapsed && opGroups.map(g => Row({ code: "OPEX_" + g.group, label: g.name }))}
            {!collapsed && ohGroups.map(g => Row({ code: "OPEX_" + g.group, label: g.name + " (OH)" }))}
            {Total({ code: "TOTAL_OPEX", label: t("totalOpex") })}

            {!collapsed && SecHead({ t: t("secCost") })}
            {!collapsed && opGroups.filter(g => Math.abs((f?.leaf["COST_" + g.group]) || 0) > 0.5).map(g => Row({ code: "COST_" + g.group, label: g.name }))}
            {Total({ code: "TOTAL_COST", label: t("totalCost") })}
            {!collapsed && Row({ code: "ADJ", label: t("netAdjust"), indent: false })}

            {Total({ code: "GOP", label: "GOP (Gross Operating Profit)" })}

            {!collapsed && SecHead({ t: t("secNonop") })}
            {!collapsed && NONOP.map(([c, l]) => Row({ code: c, label: l }))}
            {Total({ code: "TOTAL_NONOP", label: t("totalNonop") })}
            {Total({ code: "EBITDA", label: "EBITDA" })}

            {!collapsed && SecHead({ t: t("secCapital") })}
            {!collapsed && CAPITAL.map(([c, l]) => Row({ code: c, label: l, auto: c === "CAP_LARGE" }))}
            {Total({ code: "EBITDA_AFTER", label: t("ebitdaAfterCapital") })}
            {!collapsed && Row({ code: "DEPR_FIN", label: t("deprFin") })}
            {Total({ code: "EBT", label: t("ebt") })}
            {!collapsed && Row({ code: "TAX", label: t("incomeTax"), auto: true })}
            {Total({ code: "NET", label: t("netProfit") })}
          </tbody>
        </table>
      </div>
      <p style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 12, textAlign: "center" }}>
        {t("footNote")}
      </p>
    </div>
  );
}
