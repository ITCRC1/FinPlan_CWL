"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import {
  getScenarios, getCashflowBudget, saveCashflowBudgetInputs, saveCashflowBudgetDrivers,
  anchorOpeningCash, checkOpeningAnchor, type AnchorCheck, getRecalcState,
  recalculateScenario, type RecalcState, getWcBreakdown, getPlBreakdown, getCashflowVersions, copyCashflowFromVersion, saveCashflowWcOverrides,
  type Scenario, type CashFlowBudget, type CashFlowBudgetRow, type CashFlowVersionMeta,
  type WcBreakdownParte,
} from "@/lib/api";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

// Desglose unificado para el modal (sirve para WC y para Operating Performance).
type ModalBd = { parts: WcBreakdownParte[]; total: number; source?: string; link?: string; link_label?: string };

const WC_MODEL_KEYS = ["WC_DEP_RECV", "WC_DEP_APPL", "WC_AR", "WC_AP", "WC_PROV", "WC_TAX", "WC_RENTTAX", "WC_SERVICE"];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const GOLD = "#c8a24a";
const num = (s: string) => { const v = parseFloat(String(s).replace(/[$,()%\s]/g, "")); return isNaN(v) ? 0 : (String(s).trim().startsWith("(") ? -Math.abs(v) : v); };
const m0 = (v: number) => { const s = "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); return v < 0 ? `(${s})` : s; };

type DMode = "manual" | "pct_sales" | "days" | "lead_lag";
type Driver = { mode: DMode; pct: number | null; lag: number };
const DAYS_BASE: Record<string, ["sales" | "costs", number]> = { WC_AR: ["sales", -1], WC_AP: ["costs", 1] };

export default function CashflowBudgetPage() {
  const tc = useTranslations("common");
  const t = useTranslations("cashflow");
  // El motor NOMBRA y la pantalla traduce: `app/engine/` no puede enterarse del
  // idioma, asi que manda `label_key` (rotulos fijos) y `label_key`+`label_params`
  // (componentes del drill-down). Sin clave se usa el `label` tal cual, que es el
  // caso de los rotulos que vienen de la BASE: eso es dato, no interfaz.
  const tFila = useTranslations("cfbFila");
  const tParte = useTranslations("cfbParte");
  const rotuloFila = (r: { label: string; label_key?: string }) => r.label_key ? tFila(r.label_key) : r.label;
  const rotuloParte = (pt: WcBreakdownParte) =>
    pt.label_key ? tParte(pt.label_key, pt.label_params ?? {}) : pt.label;
  const MODE_LABEL: Record<DMode, string> = { manual: t("cfbModeManual"), pct_sales: t("cfbModePctSales"), days: t("days"), lead_lag: "Lead/Lag" };
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // El selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se
  // eligio abre con el preferido del owner.
  const [scnId, setScnId] = useEscenarioDe("reports/cashflow-budget:budget", scenarios, "budget", undefined, true);
  const [data, setData] = useState<CashFlowBudget | null>(null);
  const [inputs, setInputs] = useState<Record<string, number[]>>({});
  const [overrides, setOverrides] = useState<Record<string, Record<string, number>>>({});  // reales copiados/fijados por celda {row_key:{mes:valor}}
  const [versions, setVersions] = useState<CashFlowVersionMeta[]>([]);
  const [srcVersion, setSrcVersion] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});   // texto crudo mientras se edita una celda (permite teclear "-")
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());  // secciones colapsadas (solo totales)
  const [bd, setBd] = useState<ModalBd | null>(null);                 // drill-down (WC o Operating Performance)
  const [bdAt, setBdAt] = useState<{ label: string; month: string } | null>(null);
  const [bdLoading, setBdLoading] = useState(false);
  const [drivers, setDrivers] = useState<Record<string, Driver>>({});
  const [wcEnabled, setWcEnabled] = useState(false);
  const [opening, setOpening] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // El ancla COPIA Y CONGELA a propósito. Esto no la descongela: solo avisa
  // cuando el cierre del escenario origen ya no es el que quedó guardado.
  const [anchorChk, setAnchorChk] = useState<AnchorCheck | null>(null);
  // Editar planilla, tipo de cambio o repartos NO se propaga solo al P&L.
  const [recalc, setRecalc] = useState<RecalcState | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
        try { setVersions(await getCashflowVersions(HOTEL_ID)); } catch { /* opcional */ }
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  const ingest = useCallback((res: CashFlowBudget) => {
    setData(res);
    const ins: Record<string, number[]> = {}, drv: Record<string, Driver> = {};
    res.rows.filter(r => r.editable).forEach(r => {
      ins[r.key] = [...r.values];
      drv[r.key] = { mode: (r.mode ?? "manual") as DMode, pct: r.pct ?? null, lag: r.lag ?? 0 };
    });
    // overrides editables (reales copiados/fijados): de override_months del backend
    const ovr: Record<string, Record<string, number>> = {};
    res.rows.forEach(r => {
      if (r.override_months?.length) {
        ovr[r.key] = {};
        r.override_months.forEach(m => { ovr[r.key][String(m)] = r.values[m - 1]; });
      }
    });
    setOverrides(ovr);
    setInputs(ins); setDrivers(drv); setOpening(res.opening_cash);
    setWcEnabled(res.wc_model?.enabled ?? false);
  }, []);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true); setError(null); setMsg(null);
    try { ingest(await getCashflowBudget(id)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, [ingest]);
  useEffect(() => { if (scnId) load(scnId); }, [scnId, load]);
  useEffect(() => {
    setRecalc(null);
    if (!scnId) return;
    let vivo = true;
    getRecalcState(scnId).then(r => { if (vivo) setRecalc(r); }).catch(() => {});
    return () => { vivo = false; };
  }, [scnId, data]);
  useEffect(() => {
    setAnchorChk(null);
    if (!scnId || !data?.opening_anchor) return;
    let vivo = true;
    checkOpeningAnchor(scnId).then(r => { if (vivo) setAnchorChk(r); }).catch(() => {});
    return () => { vivo = false; };
  }, [scnId, data?.opening_anchor?.scenario_id]);

  // valores auto del P&L + claves por sección
  const meta = useMemo(() => {
    const auto: Record<string, number[]> = {};
    const beVals: Record<string, number[]> = {};   // filas no-editables (modelo WC, ajuste) = valores del backend
    const capex: string[] = [], wc: string[] = [], other: string[] = [];
    (data?.rows ?? []).forEach(r => {
      if (r.kind === "auto") auto[r.key] = r.values;
      if (r.kind === "input") {                      // incluye editables Y computadas por el backend
        if (!r.editable) beVals[r.key] = r.values;
        if (r.section.includes("CapEx")) capex.push(r.key);
        else if (r.section.includes("Working Capital")) wc.push(r.key);
        else other.push(r.key);
      }
    });
    return { auto, capex, wc, other, beVals };
  }, [data]);

  const revenue = meta.auto["REVENUE"] ?? Array(12).fill(0);
  // costos operativos (magnitud positiva) = −(OpEx + Overhead + NonAlloc), base de DPO
  const costs = useMemo(() => {
    const op = meta.auto["OPEX"] ?? Array(12).fill(0), ov = meta.auto["OVERHEAD"] ?? Array(12).fill(0), na = meta.auto["NONALLOC"] ?? Array(12).fill(0);
    return op.map((_, i) => -(op[i] + ov[i] + na[i]));
  }, [meta]);
  // cuando el modelo de timing está activo, las 6+1 partidas vienen calculadas del backend
  const modelVals = useMemo(() => {
    const m: Record<string, number[]> = {};
    (data?.rows ?? []).forEach(r => { if (WC_MODEL_KEYS.includes(r.key)) m[r.key] = r.values; });
    return m;
  }, [data]);
  const resolveInput = useCallback((key: string): number[] => {
    const withOverride = (base: number[]): number[] => {
      const ov = overrides[key];
      if (!ov) return base;
      return base.map((v, i) => ov[String(i + 1)] !== undefined ? ov[String(i + 1)] : v);  // override pisa
    };
    if (wcEnabled && WC_MODEL_KEYS.includes(key)) return withOverride(modelVals[key] ?? Array(12).fill(0));
    if (meta.beVals[key]) return withOverride(meta.beVals[key]);   // no-editable (modelo WC en meses cerrados, ajuste a caja real)
    const d = drivers[key];
    if (!d || d.pct == null) return withOverride(inputs[key] ?? Array(12).fill(0));
    if (d.mode === "pct_sales") return withOverride(revenue.map(v => d.pct! * v));
    if (d.mode === "days") {
      const [base, sign] = DAYS_BASE[key] ?? ["sales", -1];
      const b = base === "costs" ? costs : revenue;
      const f = d.pct / 30;
      return withOverride(b.map((_, i) => i === 0 ? 0 : sign * (b[i] - b[i - 1]) * f));
    }
    if (d.mode === "lead_lag") return withOverride(revenue.map((_, i) => { const j = i - Math.round(d.lag); return d.pct! * (j >= 0 && j < 12 ? revenue[j] : 0); }));
    return withOverride(inputs[key] ?? Array(12).fill(0));
  }, [drivers, inputs, revenue, costs, wcEnabled, modelVals, meta, overrides]);

  // recálculo en vivo de filas derivadas
  const comp = useMemo<Record<string, number[]>>(() => {
    const z = () => Array(12).fill(0);
    const sumKeys = (keys: string[]) => { const a = z(); keys.forEach(k => resolveInput(k).forEach((v, i) => a[i] += v || 0)); return a; };
    const ovr = (key: string, arr: number[]) => { const o = overrides[key]; return o ? arr.map((v, i) => o[String(i + 1)] !== undefined ? o[String(i + 1)] : v) : arr; };  // override pisa la línea auto
    const rev = ovr("REVENUE", meta.auto["REVENUE"] ?? z()), op = ovr("OPEX", meta.auto["OPEX"] ?? z()), ov = ovr("OVERHEAD", meta.auto["OVERHEAD"] ?? z()), na = ovr("NONALLOC", meta.auto["NONALLOC"] ?? z());
    const totalExp = z().map((_, i) => op[i] + ov[i] + na[i]);
    const noi = z().map((_, i) => rev[i] + totalExp[i]);
    const capex = sumKeys(meta.capex), wc = sumKeys(meta.wc), other = sumKeys(meta.other);
    // CapEx/Projects es SALIDA de caja → se RESTA (gasto positivo rebaja el efectivo).
    const net = z().map((_, i) => noi[i] - capex[i] + wc[i] + other[i]);
    const beg = z(), end = z(); let bal = opening;
    for (let i = 0; i < 12; i++) { beg[i] = bal; end[i] = bal + net[i]; bal = end[i]; }
    return { TOTAL_EXPENSES: totalExp, NET_OPERATING_INCOME: noi, SUBTOTAL_CAPEX: capex, SUBTOTAL_WC: wc, NET_CHANGE: net, BEGINNING_CASH: beg, ENDING_CASH: end };
  }, [meta, resolveInput, opening, overrides]);

  const valuesFor = (r: CashFlowBudgetRow): number[] => r.editable ? resolveInput(r.key) : (comp[r.key] ?? r.values);
  const fyFor = (r: CashFlowBudgetRow, vals: number[]): number =>
    r.key === "BEGINNING_CASH" ? vals[0] : r.key === "ENDING_CASH" ? vals[11] : vals.reduce((a, b) => a + b, 0);

  function setCell(key: string, mi: number, v: string) {
    setInputs(prev => { const arr = [...(prev[key] ?? Array(12).fill(0))]; arr[mi] = num(v); return { ...prev, [key]: arr }; });
  }
  function setMode(key: string, mode: DMode) { setDrivers(p => ({ ...p, [key]: { mode, pct: p[key]?.pct ?? null, lag: p[key]?.lag ?? 0 } })); }
  function setPct(key: string, pctDisplay: string) {
    const v = pctDisplay.trim() === "" ? null : num(pctDisplay) / 100;
    setDrivers(p => ({ ...p, [key]: { mode: p[key]?.mode === "lead_lag" ? "lead_lag" : "pct_sales", pct: v, lag: p[key]?.lag ?? 0 } }));
  }
  function setDays(key: string, daysDisplay: string) {
    const v = daysDisplay.trim() === "" ? null : num(daysDisplay);
    setDrivers(p => ({ ...p, [key]: { mode: "days", pct: v, lag: p[key]?.lag ?? 0 } }));
  }
  function setLag(key: string, lagDisplay: string) {
    setDrivers(p => ({ ...p, [key]: { mode: "lead_lag", pct: p[key]?.pct ?? null, lag: Math.round(num(lagDisplay)) } }));
  }
  function paste(key: string, mi: number, e: React.ClipboardEvent) {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const cells = text.replace(/\r/g, "").split("\n").filter(l => l.length).map(l => l.split("\t"));
    const editKeys = (data?.rows ?? []).filter(r => r.editable && (drivers[r.key]?.mode ?? "manual") === "manual").map(r => r.key);
    const startRow = editKeys.indexOf(key);
    setInputs(prev => {
      const next = { ...prev };
      cells.forEach((rowc, dr) => {
        const rk = editKeys[startRow + dr]; if (!rk) return;
        const arr = [...(next[rk] ?? Array(12).fill(0))];
        rowc.forEach((c, dc) => { const m = mi + dc; if (m >= 0 && m < 12) arr[m] = num(c); });
        next[rk] = arr;
      });
      return next;
    });
  }

  async function openBreakdown(rowKey: string, rowLabel: string, monthIdx: number) {
    if (!scnId) return;
    setBd(null); setBdLoading(true); setBdAt({ label: rowLabel, month: MONTHS[monthIdx] });
    try { setBd(await getWcBreakdown(scnId, rowKey, monthIdx + 1)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); setBdAt(null); }
    finally { setBdLoading(false); }
  }

  // Operating Performance: REVENUE / OPEX / OVERHEAD / NONALLOC → fuente + cuentas + link
  const PL_BREAKDOWN_LINES: Record<string, string> = { REVENUE: "REVENUE", OPEX: "OPEX", OVERHEAD: "OVERHEAD", NONALLOC: "NONALLOC" };
  const COMP_KEYS = new Set(["TOTAL_EXPENSES", "NET_OPERATING_INCOME", "SUBTOTAL_CAPEX", "SUBTOTAL_WC", "NET_CHANGE", "ENDING_CASH"]);
  async function openPlBreakdown(lineKey: string, rowLabel: string, monthIdx: number) {
    if (!scnId) return;
    setBd(null); setBdLoading(true); setBdAt({ label: rowLabel, month: MONTHS[monthIdx] });
    try { setBd(await getPlBreakdown(scnId, lineKey, monthIdx + 1)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); setBdAt(null); }
    finally { setBdLoading(false); }
  }

  // Subtotales/totales del cash flow → qué líneas los suman (cálculo en vivo)
  function compParts(rowKey: string, mi: number): { label: string; amount: number }[] | null {
    const val = (k: string, sign = 1) => { const r = rows.find(x => x.key === k); return (r ? valuesFor(r)[mi] : 0) * sign; };
    const lbl = (k: string) => { const r = rows.find(x => x.key === k); return r ? rotuloFila(r) : k; };
    const keys = (ks: string[], sign = 1) => ks.map(k => ({ label: lbl(k), amount: val(k, sign) }));
    switch (rowKey) {
      case "TOTAL_EXPENSES": return keys(["OPEX", "OVERHEAD", "NONALLOC"]);
      case "NET_OPERATING_INCOME": return keys(["REVENUE", "OPEX", "OVERHEAD", "NONALLOC"]);
      case "SUBTOTAL_CAPEX": return keys(meta.capex);
      case "SUBTOTAL_WC": return keys(meta.wc);
      case "NET_CHANGE": return [
        { label: "Net Operating Income", amount: val("NET_OPERATING_INCOME") },
        { label: t("capexSalida"), amount: val("SUBTOTAL_CAPEX", -1) },
        { label: "Working Capital", amount: val("SUBTOTAL_WC") },
        ...keys(meta.other),
      ];
      case "ENDING_CASH": return [
        { label: "Beginning Cash", amount: val("BEGINNING_CASH") },
        { label: "Net Change in Cash", amount: val("NET_CHANGE") },
      ];
      default: return null;
    }
  }
  function openCompBreakdown(rowKey: string, rowLabel: string, monthIdx: number) {
    const parts = compParts(rowKey, monthIdx); if (!parts) return;
    const total = (() => { const r = rows.find(x => x.key === rowKey); return r ? valuesFor(r)[monthIdx] : parts.reduce((a, p) => a + p.amount, 0); })();
    setBdLoading(false); setBdAt({ label: rowLabel, month: MONTHS[monthIdx] });
    setBd({ parts, total, source: t("sumaLineas") });
  }

  function setOverride(key: string, mi: number, v: string) {
    setOverrides(prev => { const cells = { ...(prev[key] ?? {}) }; cells[String(mi + 1)] = num(v); return { ...prev, [key]: cells }; });
  }

  // Orden de las partidas WC tal como se muestran (para mapear un paste en bloque).
  const wcRowKeys = (data?.rows ?? []).filter(r => r.section.includes("Working Capital") && r.kind === "input").map(r => r.key);

  // Abre las celdas WC de Ene–May como overrides editables (inicia con el valor
  // actual) → quedan ámbar y podés teclear o pegar un bloque de Excel encima.
  function openEneMayForPaste() {
    const openKeys = [...wcRowKeys, "NONALLOC"];   // WC + Non Allocated Expenses (below-GOP)
    setOverrides(prev => {
      const next = { ...prev };
      openKeys.forEach(k => {
        const vals = (data?.rows ?? []).find(r => r.key === k)?.values ?? [];
        const cells = { ...(next[k] ?? {}) };
        for (let m = 1; m <= 5; m++) if (cells[String(m)] === undefined) cells[String(m)] = vals[m - 1] ?? 0;
        next[k] = cells;
      });
      return next;
    });
    setMsg(t("eneMayAbierto"));
  }

  // Abre Non Allocated Expenses (below-GOP) los 12 meses como override editable
  // → para cargar el real (Rent+Owner Fees+Insurance+Other) de todo el año.
  function openNonAllocFullYear() {
    setOverrides(prev => {
      const vals = (data?.rows ?? []).find(r => r.key === "NONALLOC")?.values ?? [];
      const cells = { ...(prev["NONALLOC"] ?? {}) };
      for (let m = 1; m <= 12; m++) if (cells[String(m)] === undefined) cells[String(m)] = vals[m - 1] ?? 0;
      return { ...prev, NONALLOC: cells };
    });
    setMsg(t("nonAllocAbierto"));
  }

  // El CapEx sale del P&L (reserva de capital sobre el revenue), pero el gasto
  // real no es lineal: esto abre los 12 meses para re-perfilarlo sin perder de
  // dónde salió el total. "Quitar reales fijados" lo devuelve al P&L.
  function openCapexFullYear() {
    setOverrides(prev => {
      const vals = (data?.rows ?? []).find(r => r.key === "CAPEX_LARGE")?.values ?? [];
      const cells = { ...(prev["CAPEX_LARGE"] ?? {}) };
      for (let m = 1; m <= 12; m++) if (cells[String(m)] === undefined) cells[String(m)] = vals[m - 1] ?? 0;
      return { ...prev, CAPEX_LARGE: cells };
    });
    setMsg(t("capexAbierto"));
  }

  // Pega un bloque (filas × meses) arrancando en la celda (key, mes) hacia abajo
  // por las partidas WC y a la derecha por los meses.
  function pasteOverride(startKey: string, startMi: number, e: React.ClipboardEvent) {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;   // celda única → comportamiento normal
    e.preventDefault();
    const grid = text.replace(/\r/g, "").split("\n").filter(l => l.length).map(l => l.split("\t"));
    const startRow = wcRowKeys.indexOf(startKey);
    if (startRow < 0) return;
    setOverrides(prev => {
      const next = { ...prev };
      grid.forEach((cells, dr) => {
        const k = wcRowKeys[startRow + dr]; if (!k) return;
        const cur = { ...(next[k] ?? {}) };
        cells.forEach((c, dc) => { const m = startMi + dc + 1; if (m >= 1 && m <= 12) cur[String(m)] = num(c); });
        next[k] = cur;
      });
      return next;
    });
  }

  async function copyReales() {
    if (!scnId || !srcVersion) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const res = await copyCashflowFromVersion(scnId, srcVersion, [1, 2, 3, 4, 5]);
      ingest(res);
      const cr = res.copy_result;
      setMsg(cr
        ? t("copiadosReales", { version: cr.version_name, n: cr.mapped.length, lineas: cr.mapped.join(", ") })
          + (cr.skipped.length ? t("copiadosNoCalzaron", { lineas: cr.skipped.join(", ") }) : "")
          + t("copiadosCola")
        : t("copiado"));
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setSaving(false); }
  }

  async function clearOverrides() {
    if (!scnId) return;
    setSaving(true); setMsg(null); setError(null);
    try { ingest(await saveCashflowWcOverrides(scnId, {})); setMsg(t("realesQuitados")); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setSaving(false); }
  }

  async function save(recalc = false) {
    if (!scnId) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const inRows = Object.entries(inputs).map(([row_key, values]) => ({ row_key, values }));
      await saveCashflowBudgetInputs(scnId, opening, inRows);
      const drvRows = Object.entries(drivers).map(([row_key, d]) => ({ row_key, mode: d.mode, pct: d.pct, lag: d.lag }));
      await saveCashflowBudgetDrivers(scnId, drvRows);
      ingest(await saveCashflowWcOverrides(scnId, overrides));   // el backend devuelve TODO recalculado
      if (!recalc) {
        setMsg(t("guardadoOk"));
        return;
      }
      // ⚠️ Acá vivía un falso positivo: el botón decía «Recalculado en el
      // servidor» pero solo guardaba los criterios del cash flow. Planilla,
      // repartos y costos seguían viejos, el aviso de «hay cambios sin
      // recalcular» no se iba, y el usuario se quedaba tranquilo con un número
      // desactualizado. Ahora recalcula el escenario de verdad.
      const r = await recalculateScenario(scnId);
      const avisos: string[] = r?.avisos ?? [];
      setRecalc(await getRecalcState(scnId).catch(() => null));
      setMsg(avisos.length
        ? t("recalcAvisos", { avisos: avisos.join(" · ") })
        : t("recalcOk"));
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setSaving(false); }
  }

  // Fuentes para la caja inicial: CUALQUIER escenario del año anterior, no solo
  // el Forecast. Antes se elegía sola la del Forecast del año previo, así que el
  // botón simplemente no aparecía en los años sin Forecast — o sea, en nueve de
  // los diez presupuestos. Con presupuestos encadenados (2028 abre donde cierra
  // 2027) el año anterior siempre tiene de dónde anclarse.
  const curScn = scenarios.find(s => s.id === scnId);
  const curYear = curScn?.year ?? 0;
  // Los encabezados decían "-26" fijo: en Budget 2027 las columnas mentían el año.
  const yy = String((data?.year ?? curYear ?? new Date().getFullYear()) % 100).padStart(2, "0");
  const anchorSources = useMemo(() => {
    const rango = (s: Scenario) => {
      if (s.type === "FORECAST" && s.is_current_forecast) return 0;  // el cierre vigente
      if (s.type === "FORECAST") return 1;
      if (s.type === "BUDGET" && s.version === curScn?.version) return 2;  // la cadena natural
      if (s.type === "BUDGET") return 3;
      return 4;                                                       // Actual al final
    };
    return scenarios.filter(s => s.year === curYear - 1 && s.id !== scnId)
                    .sort((a, b) => rango(a) - rango(b));
  }, [scenarios, curYear, scnId, curScn?.version]);

  // La sugerida queda arriba, pero el usuario manda.
  const [anchorSrc, setAnchorSrc] = useState("");
  useEffect(() => { setAnchorSrc(anchorSources[0]?.id ?? ""); }, [anchorSources]);

  async function anchorBase() {
    if (!scnId || !anchorSrc) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const res = await anchorOpeningCash(scnId, anchorSrc);
      ingest(res);
      const ef = res.anchored_from;
      const de = ef?.label ?? scenarios.find(s => s.id === anchorSrc)?.version ?? "";
      setMsg(t("anclada", { de, monto: ef ? `: $${ef.ending_cash.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "" }));
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setSaving(false); }
  }

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const th: React.CSSProperties = { padding: "8px 8px", fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.4, textAlign: "right", whiteSpace: "nowrap" };
  const numC = (v: number, strong = false): React.CSSProperties => ({ textAlign: "right", padding: "6px 8px", fontSize: 12.5, fontWeight: strong ? 800 : 600, color: v < 0 ? "var(--negative)" : (strong ? "var(--text-primary)" : "var(--text-secondary)"), whiteSpace: "nowrap" });
  const cal = data?.calibration ?? {};

  const rows = data?.rows ?? [];
  // Colapso: una sección es colapsable si tiene detalle Y una línea total/subtotal
  // (al colapsar se ocultan los detalles y queda la línea de total de la sección).
  const isTotalRow = (k: string) => k.startsWith("subtotal") || k.startsWith("total");
  const collapsible = (() => {
    const det = new Set<string>(), tot = new Set<string>();
    rows.forEach(r => { if (r.kind === "auto" || r.kind === "input") det.add(r.section); if (isTotalRow(r.kind)) tot.add(r.section); });
    return new Set([...det].filter(s => tot.has(s)));
  })();
  const visibleRows = rows.filter(r => !collapsed.has(r.section) || isTotalRow(r.kind));
  const toggleSection = (s: string) => setCollapsed(prev => { const n = new Set(prev); if (n.has(s)) n.delete(s); else n.add(s); return n; });
  const allCollapsed = collapsible.size > 0 && [...collapsible].every(s => collapsed.has(s));
  const toggleAll = () => setCollapsed(allCollapsed ? new Set() : new Set(collapsible));

  /* El Excel sale SIEMPRE con el detalle completo, aunque la pantalla esté en
     "Solo totales": el que baja el archivo lo baja para abrirlo, no para verlo
     colapsado. El criterio de cada fila (modelo / % ventas / días / lead-lag)
     viaja pegado a la etiqueta porque es texto; las cifras van como número. */
  function criterioDe(r: CashFlowBudgetRow): string {
    if (wcEnabled && WC_MODEL_KEYS.includes(r.key)) return t("critModelo");
    if (r.key === "CAPEX_LARGE") return t("critDelPl");
    if (!r.editable) return "";
    const d = drivers[r.key];
    const mode: DMode = d?.mode ?? "manual";
    const pctTxt = d?.pct != null ? `${+(d.pct * 100).toFixed(3)}%` : "—";
    if (mode === "pct_sales") return t("critPctVentas", { pct: pctTxt });
    if (mode === "days") return t("critDias", { n: d?.pct ?? "—" });
    if (mode === "lead_lag") return t("critLeadLag", { pct: pctTxt, lag: d?.lag ?? 0 });
    return "";
  }

  async function bajarExcel() {
    if (!rows.length) return;
    const VACIA: (number | null)[] = Array(13).fill(null);
    const filas: FilaCuadro[] = [];
    let secPrev = "";
    for (const r of rows) {                       // rows, NO visibleRows: detalle completo
      if (r.section !== secPrev) {
        filas.push({ label: r.section, nivel: 0, es_total: true, valores: VACIA });
        secPrev = r.section;
      }
      const vals = valuesFor(r);
      const esTotal = r.kind.startsWith("subtotal") || r.kind.startsWith("total");
      const crit = criterioDe(r);
      filas.push({
        label: crit ? `${rotuloFila(r)} · ${crit}` : rotuloFila(r),
        nivel: esTotal ? 0 : 1, es_total: esTotal,
        valores: [...vals, fyFor(r, vals)],
      });
    }
    const scn = scenarios.find(s => s.id === scnId);
    try {
      await bajarCuadros(`Cash_Flow_Budget_${data?.year ?? ""}`, [{
        titulo: `Full Year Cash Flow Budget ${data?.year ?? ""}`,
        subtitulo: t("cfbExcelSubtitulo", { scn: scn ? scnLabel(scn) : "", modelo: wcEnabled ? t("modeloActivo") : t("modeloApagado") }),
        hoja: "Cash Flow Budget",
        columnas: [
          { label: tc("concept"), ancho: 52, formato: "texto" },
          ...MONTHS.map(m => ({ label: `${m}-${yy}`, ancho: 14, formato: "usd2" as const })),
          { label: "Full Year", ancho: 16, formato: "usd2" },
        ],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : t("cfbExcelFallo")); }
  }

  let lastSection = "";

  return (
    <div className="print-dashboard pag pag-ancha" style={{ padding: "20px 20px 44px" }}>
      <IrA esc={scnId} />
      <div style={{ textAlign: "center", marginBottom: 6 }}>
        <h1 style={{ fontSize: 32, fontWeight: 800, margin: 0, letterSpacing: -0.5 }}>
          <span style={{ color: "var(--text-primary)" }}>Full Year </span><span style={{ color: "var(--brand)" }}>Cash Flow Budget</span>
        </h1>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginTop: 6 }}>
          <span style={{ height: 2, width: 60, background: "var(--border-medium)" }} />
          <span style={{ fontSize: 14, color: "var(--text-secondary)", fontWeight: 600 }}>{t("operatingFromPL")}<span style={{ color: GOLD, fontWeight: 800 }}>|</span> {t("wcPorCriterio")}</span>
          <span style={{ height: 2, width: 60, background: "var(--border-medium)" }} />
        </div>
      </div>

      <div className="no-print" style={{ display: "flex", gap: 10, justifyContent: "center", alignItems: "flex-end", margin: "16px 0 18px", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("scenario")}</span><select value={scnId} onChange={e => setScnId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("beginningCashEne")}</span><input className="mono" value={opening} onChange={e => setOpening(num(e.target.value))} style={{ ...sel, textAlign: "right", width: 130 }} /></div>
        {anchorSources.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("anchorTo")}</span>
            <div style={{ display: "flex", gap: 6 }}>
              <select value={anchorSrc} onChange={e => setAnchorSrc(e.target.value)} style={{ ...sel, fontSize: 12 }}>
                {anchorSources.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}
              </select>
              <button onClick={anchorBase} disabled={saving || !scnId || !anchorSrc}
                title={t("anchorHint")}
                style={{ padding: "7px 12px", fontSize: 11.5, fontWeight: 700, borderRadius: 6, cursor: saving ? "default" : "pointer", background: "var(--bg-elevated)", color: "var(--brand)", border: "1px solid var(--brand)", opacity: saving ? 0.6 : 1 }}>{t("anclarBtn")}</button>
            </div>
          </div>
        )}
        <Link href="/reports/cashflow-criteria" style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: wcEnabled ? "var(--brand)" : "var(--bg-input)", color: wcEnabled ? "#fff" : "var(--text-primary)", border: "1px solid var(--border-medium)", textDecoration: "none" }}>{t("criteriosBtn")} {wcEnabled ? t("modeloOn") : t("modeloOff")}</Link>
        <button onClick={() => save(false)} disabled={saving || !scnId} style={{ padding: "7px 16px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: saving ? "default" : "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", opacity: saving ? 0.6 : 1 }}>{saving ? tc("saving") : `💾 ${tc("save")}`}</button>
        <button onClick={() => save(true)} disabled={saving || !scnId} title={t("persistHint")} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: saving ? "default" : "pointer", background: "var(--bg-elevated)", color: "var(--brand)", border: "1px solid var(--brand)", opacity: saving ? 0.6 : 1 }}>{t("cfbRecalcularBtn")}</button>
        {collapsible.size > 0 && <button onClick={toggleAll} title={t("collapseHint")} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>{allCollapsed ? t("cfbVerDetalle") : t("cfbSoloTotales")}</button>}
        <button onClick={() => window.print()} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>{tc("print")}</button>
        <button onClick={bajarExcel} disabled={!rows.length} title={t("cfbExcelBtnTitle")}
          style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: rows.length ? "pointer" : "default", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)", opacity: rows.length ? 1 : 0.5 }}>⬇ Excel</button>
      </div>

      {versions.length > 0 && (
        <div className="no-print" style={{ display: "flex", gap: 8, justifyContent: "center", alignItems: "center", margin: "0 0 16px", flexWrap: "wrap" }}>
          <span style={{ fontSize: 11.5, fontWeight: 700, color: GOLD }}>{t("pullActuals")}</span>
          <select value={srcVersion} onChange={e => setSrcVersion(e.target.value)} style={{ ...sel, fontSize: 12, padding: "5px 8px" }}>
            <option value="" style={{ background: "var(--bg-input)" }}>{t("pickFrozen")}</option>
            {versions.map(v => <option key={v.id} value={v.id} style={{ background: "var(--bg-input)" }}>{v.name}{v.kind === "frozen" ? "" : t("versionWorking")}</option>)}
          </select>
          <button onClick={copyReales} disabled={saving || !scnId || !srcVersion}
            title={t("copyActualsHint")}
            style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: (saving || !srcVersion) ? "default" : "pointer", background: "var(--bg-elevated)", color: GOLD, border: `1px solid ${GOLD}`, opacity: (saving || !srcVersion) ? 0.5 : 1 }}>
            {t("copiarEneMay")}
          </button>
          <span style={{ color: "var(--text-disabled)", fontSize: 12 }}>{t("cfbO")}</span>
          <button onClick={openEneMayForPaste} disabled={saving || !scnId}
            title={t("openWcHint")}
            style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: saving ? "default" : "pointer", background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
            {t("abrirEneMay")}
          </button>
          <button onClick={openNonAllocFullYear} disabled={saving || !scnId}
            title={t("openNonAllocHint")}
            style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: saving ? "default" : "pointer", background: "var(--bg-elevated)", color: GOLD, border: `1px solid ${GOLD}` }}>
            {t("nonAlloc12")}
          </button>
          <button onClick={openCapexFullYear} disabled={saving || !scnId}
            title={t("capexBtnTitle")}
            style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: saving ? "default" : "pointer", background: "var(--bg-elevated)", color: GOLD, border: `1px solid ${GOLD}` }}>
            {t("capex12")}
          </button>
          {data?.has_overrides && (
            <button onClick={clearOverrides} disabled={saving} title={t("quitarRealesTitle")}
              style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--bg-input)", color: "var(--negative)", border: "1px solid var(--border-medium)" }}>
              {t("quitarRealesBtn")}
            </button>
          )}
        </div>
      )}

      {/* El P&L no se recalcula solo al editar planilla, tipo de cambio o repartos.
          Sin este aviso se puede estar mirando un reporte que no incluye lo que
          se editó hace media hora, y nada en pantalla lo delata. */}
      {recalc?.stale && (
        <div className="no-print" style={{ display: "flex", justifyContent: "center", marginBottom: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, background: "var(--bg-elevated)", border: "1px solid var(--negative)", borderRadius: 8, padding: "8px 16px", fontSize: 12.5, maxWidth: 1000 }}>
            <span style={{ color: "var(--negative)", fontWeight: 800 }}>⚠</span>
            <span style={{ color: "var(--text-secondary)", lineHeight: 1.5 }}>
              {t.rich("staleAviso", {
                que: recalc.changed.map(c => c.que).join(", "),
                boton: t("cfbRecalcularBtn"),
                neg: (c: React.ReactNode) => <b style={{ color: "var(--negative)" }}>{c}</b>,
                b: (c: React.ReactNode) => <b>{c}</b>,
              })}
            </span>
          </div>
        </div>
      )}

      {/* De dónde salió la caja inicial. Se muestra siempre, no solo al anclar: un
          monto sin origen no se puede auditar meses después. */}
      <div style={{ textAlign: "center", marginBottom: 10, fontSize: 11.5 }}>
        {data?.opening_anchor ? (
          <span style={{ color: "var(--text-secondary)" }}>
            {t("ancladaAl")} <b style={{ color: "var(--brand)" }}>{data.opening_anchor.label}</b>
            {data.opening_anchor.anchored_at ? ` · ${new Date(data.opening_anchor.anchored_at).toLocaleDateString("es-CR", { day: "numeric", month: "short", year: "numeric" })}` : ""}
            {anchorChk?.stale && (
              <b style={{ color: "var(--negative)", marginLeft: 8 }}>
                {t("anclaVieja", { actual: m0(anchorChk.current ?? 0), dif: m0(anchorChk.diff ?? 0) })}
              </b>
            )}
            {anchorChk?.source_missing && (
              <b style={{ color: "var(--negative)", marginLeft: 8 }}>{t("origenNoExiste")}</b>
            )}
          </span>
        ) : (
          <span style={{ color: GOLD }}>{t("handCash")}</span>
        )}
      </div>

      {wcEnabled && (
        <div className="no-print" style={{ textAlign: "center", marginBottom: 12, fontSize: 12, color: "var(--text-secondary)" }}>
          {t.rich("modeloActivoAviso", { b: (c: React.ReactNode) => <b style={{ color: "var(--brand)" }}>{c}</b> })} <Link href="/reports/cashflow-criteria" style={{ color: GOLD }}>{t("criteriaLink")}</Link>
          {data?.wc_integrated && (data.wc_integrated.prior || data.wc_integrated.next) && (
            <div style={{ marginTop: 4, fontSize: 11.5, color: "var(--brand)" }}>
              🔗 <b>{t("yearCross")}</b>{data.wc_integrated.prior ? t("yearCrossBase", { label: data.wc_integrated.prior.label }) : ""}{data.wc_integrated.next ? t("yearCrossNext", { label: data.wc_integrated.next.label }) : ""}{t("yearCrossNota")}
            </div>
          )}
        </div>
      )}

      {msg &&<div style={{ color: "var(--positive)", fontSize: 13, marginBottom: 8, textAlign: "center" }}>{msg}</div>}
      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8, textAlign: "center" }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13, textAlign: "center" }}>{tc("loading")}</div>}

      {!loading && rows.length > 0 && (
        <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, overflow: "auto" }}>
          <table style={{ borderCollapse: "collapse", minWidth: 1640, width: "100%" }}>
            <thead>
              <tr style={{ background: "var(--bg-header)" }}>
                <th style={{ ...th, textAlign: "left", position: "sticky", left: 0, background: "var(--bg-header)", minWidth: 180 }}>Section</th>
                <th style={{ ...th, textAlign: "left", minWidth: 210 }}>Description</th>
                <th style={{ ...th, textAlign: "center", minWidth: 150 }}>{t("cfbCriterio")}</th>
                {MONTHS.map(m => <th key={m} style={th}>{m}-{yy}</th>)}
                <th style={{ ...th, color: GOLD }}>Full Year</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map(r => {
                const vals = valuesFor(r);
                const fy = fyFor(r, vals);
                const isSub = r.kind.startsWith("subtotal");
                const isTot = r.kind.startsWith("total");
                const strong = r.kind.endsWith("_strong");
                const rowBg = strong ? "linear-gradient(90deg,#16234d,#244481)" : (isSub ? "rgba(200,162,74,0.10)" : (isTot ? "rgba(38,166,154,0.10)" : "transparent"));
                const fg = strong ? "#fff" : "var(--text-primary)";
                const showSection = r.section !== lastSection; lastSection = r.section;
                const labelBold = isSub || isTot;
                const drv = drivers[r.key];
                const mode = drv?.mode ?? "manual";
                const isModelRow = wcEnabled && WC_MODEL_KEYS.includes(r.key);
                const isComputed = isModelRow || (r.editable && mode !== "manual");
                const c = cal[r.key];
                const inp11: React.CSSProperties = { width: 48, textAlign: "right", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--brand)", borderRadius: 4, padding: "3px 5px", fontSize: 11 };
                return (
                  <tr key={r.key} style={{ borderTop: "1px solid var(--border-subtle)", background: rowBg }}>
                    <td style={{ padding: "6px 8px", fontSize: 11, fontWeight: 700, color: strong ? "#cdd6ea" : "var(--text-disabled)", position: "sticky", left: 0, background: showSection ? (strong ? "var(--accent-total)" : "var(--bg-elevated)") : "transparent", whiteSpace: "nowrap" }}>
                      {showSection && (collapsible.has(r.section)
                        ? <button onClick={() => toggleSection(r.section)} title={collapsed.has(r.section) ? t("cfbVerDetalleTitle") : t("cfbColapsarTitle")} style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", font: "inherit", fontWeight: 700, padding: 0 }}><span style={{ color: "var(--brand)", marginRight: 5 }}>{collapsed.has(r.section) ? "▸" : "▾"}</span>{r.section}</button>
                        : r.section)}
                    </td>
                    <td style={{ padding: "6px 10px", fontSize: 12.5, fontWeight: labelBold ? 800 : 600, color: fg, whiteSpace: "nowrap" }}>
                      {rotuloFila(r)}
                      {/* El Ajuste manual es un plug para cuadrar la caja. Que sea
                          manual está bien; lo que no está bien es que se confunda con
                          una partida real del flujo. Si tiene monto, se marca. */}
                      {r.key === "OTH_ADJUST" && resolveInput("OTH_ADJUST").some(v => Math.abs(v) > 0.005) && (
                        <span title={t("plugHint")}
                          style={{ marginLeft: 8, fontSize: 11, fontWeight: 800, color: "var(--negative)" }}>
                          {t("plugActivo")}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "3px 6px" }}>
                      {isModelRow ? (
                        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--brand)" }}>{t("critModelo")}</span>
                      ) : r.key === "CAPEX_LARGE" ? (
                        /* Cambió de fuente: dejó de ser una casilla tecleada y ahora
                           sale del P&L. Sin decirlo, la fila parece manual y en cero. */
                        <span title={t("capexHint")}
                          style={{ fontSize: 11, fontWeight: 700, color: GOLD, cursor: "help" }}>
                          {t("critDelPl")}
                        </span>
                      ) : r.editable ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
                          <select value={mode} onChange={e => setMode(r.key, e.target.value as DMode)} style={{ background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-subtle)", borderRadius: 4, fontSize: 11, padding: "3px 4px" }}>
                            {(["manual", "pct_sales", "days", "lead_lag"] as DMode[]).map(m => <option key={m} value={m}>{MODE_LABEL[m]}</option>)}
                          </select>
                          {(mode === "pct_sales" || mode === "lead_lag") && <>
                            <input className="mono" value={drv?.pct != null ? +(drv.pct * 100).toFixed(3) : ""} placeholder="%" onChange={e => setPct(r.key, e.target.value)} style={inp11} />
                            <span style={{ fontSize: 11, color: "var(--text-disabled)" }}>%</span>
                          </>}
                          {mode === "lead_lag" && <input className="mono" value={drv?.lag ?? 0} title={t("lagTitle")} onChange={e => setLag(r.key, e.target.value)} style={{ ...inp11, width: 38 }} />}
                          {mode === "days" && <>
                            <input className="mono" value={drv?.pct ?? ""} placeholder={t("diasPlaceholder")} onChange={e => setDays(r.key, e.target.value)} style={inp11} />
                            <span style={{ fontSize: 11, color: "var(--text-disabled)" }}>d</span>
                          </>}
                          {c?.implied_pct != null && (mode === "manual" || mode === "pct_sales") && (
                            <span title={t("realEneMayTitle")} style={{ fontSize: 10, color: GOLD, cursor: "pointer", whiteSpace: "nowrap" }}
                              onClick={() => setPct(r.key, String(+(c.implied_pct! * 100).toFixed(3)))}>
                              {t("realPct", { pct: (c.implied_pct * 100).toFixed(1) })}
                            </span>
                          )}
                        </div>
                      ) : null}
                    </td>
                    {vals.map((v, mi) => {
                      const ovv = overrides[r.key]?.[String(mi + 1)];           // valor en vivo del override (local)
                      const isOvr = ovv !== undefined || r.override_months?.includes(mi + 1);  // real fijado/abierto (editable)
                      if (isOvr) {
                        const dk = `o:${r.key}:${mi}`;
                        const cellV = ovv !== undefined ? ovv : v;
                        return (
                          <td key={mi} title={t("realFixed")} style={{ padding: "2px 3px" }}>
                            <input className="mono"
                              value={drafts[dk] !== undefined ? drafts[dk] : (cellV ? m0(cellV) : "")} placeholder="0"
                              onFocus={e => { setDrafts(d => ({ ...d, [dk]: ovv ? String(ovv) : "" })); e.target.select(); }}
                              onChange={e => { const raw = e.target.value; setDrafts(d => ({ ...d, [dk]: raw })); setOverride(r.key, mi, raw); }}
                              onBlur={() => setDrafts(d => { const n = { ...d }; delete n[dk]; return n; })}
                              onPaste={e => pasteOverride(r.key, mi, e)}
                              style={{ width: 92, textAlign: "right", background: "rgba(200,162,74,0.05)", color: cellV < 0 ? "var(--negative)" : "var(--text-primary)", border: "1px solid var(--border-subtle)", borderRadius: 4, padding: "5px 6px", fontSize: 12, fontWeight: 600 }} />
                          </td>
                        );
                      }
                      if (r.editable && !isComputed) {
                        return (
                          <td key={mi} style={{ padding: "2px 3px" }}>
                            <input className="mono"
                              value={drafts[`${r.key}:${mi}`] !== undefined ? drafts[`${r.key}:${mi}`] : (v ? m0(v) : "")} placeholder="0"
                              onFocus={e => { setDrafts(d => ({ ...d, [`${r.key}:${mi}`]: inputs[r.key]?.[mi] ? String(inputs[r.key][mi]) : "" })); e.target.select(); }}
                              onChange={e => { const raw = e.target.value; setDrafts(d => ({ ...d, [`${r.key}:${mi}`]: raw })); setCell(r.key, mi, raw); }}
                              onBlur={() => setDrafts(d => { const n = { ...d }; delete n[`${r.key}:${mi}`]; return n; })}
                              onPaste={e => paste(r.key, mi, e)}
                              style={{ width: 92, textAlign: "right", background: "var(--bg-input)", color: v < 0 ? "var(--negative)" : "var(--text-primary)", border: "1px solid var(--border-subtle)", borderRadius: 4, padding: "5px 6px", fontSize: 12 }} />
                          </td>
                        );
                      }
                      const isPlLine = r.kind === "auto" && PL_BREAKDOWN_LINES[r.key] !== undefined;  // Revenue/OpEx/Overhead/NonAlloc
                      const isComp = COMP_KEYS.has(r.key);                                              // subtotales/totales
                      const auditable = isModelRow || isPlLine || isComp;
                      const onAudit = isPlLine ? () => openPlBreakdown(r.key, rotuloFila(r), mi)
                        : isModelRow ? () => openBreakdown(r.key, rotuloFila(r), mi)
                        : isComp ? () => openCompBreakdown(r.key, rotuloFila(r), mi) : undefined;
                      return (
                        <td key={mi} className="mono"
                          onClick={isModelRow ? () => openBreakdown(r.key, rotuloFila(r), mi) : undefined}
                          onDoubleClick={onAudit}
                          title={auditable ? t("auditTitle") : undefined}
                          style={{ ...numC(v, labelBold || strong), fontStyle: isComputed ? "italic" : "normal", color: isComputed ? (v < 0 ? "var(--negative)" : "var(--text-secondary)") : numC(v, labelBold || strong).color, cursor: auditable ? "pointer" : "default", ...(auditable ? { textDecoration: "underline dotted var(--border-medium)", textUnderlineOffset: 3 } : {}) }}>{m0(v)}</td>
                      );
                    })}
                    <td className="mono" style={{ ...numC(fy, true), color: strong ? "#fff" : (fy < 0 ? "var(--negative)" : GOLD), background: strong ? "transparent" : "rgba(200,162,74,0.06)" }}>{m0(fy)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {bdAt && (
        <div onClick={() => setBdAt(null)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div onClick={e => e.stopPropagation()} style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, padding: "20px 22px", minWidth: 420, maxWidth: 620, maxHeight: "80vh", overflow: "auto", boxShadow: "0 16px 48px rgba(0,0,0,0.5)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 800, color: "var(--text-primary)" }}>{bdAt.label}</div>
                <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{bdAt.month}-{yy} · {bd?.source ? t("modalSubFuente") : t("modalSubMeses")}</div>
              </div>
              <button onClick={() => setBdAt(null)} style={{ background: "none", border: "none", color: "var(--text-secondary)", fontSize: 20, cursor: "pointer", lineHeight: 1 }}>×</button>
            </div>
            {bdLoading && <div style={{ color: "var(--text-secondary)", fontSize: 13, padding: "16px 0" }}>{t("cfbCalculando")}</div>}
            {!bdLoading && bd && (
              <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
                <tbody>
                  {bd.parts.length === 0 && <tr><td style={{ padding: 10, color: "var(--text-secondary)", fontSize: 13 }}>{t("noComponents")}</td></tr>}
                  {bd.parts.map((pt, i) => (
                    <tr key={i} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                      <td style={{ padding: "7px 8px", fontSize: 12.5, color: "var(--text-primary)" }}>{rotuloParte(pt)}</td>
                      <td className="mono" style={{ padding: "7px 8px", textAlign: "right", fontSize: 12.5, fontWeight: 600, color: pt.amount < 0 ? "var(--negative)" : "var(--text-primary)", whiteSpace: "nowrap" }}>{m0(pt.amount)}</td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: "2px solid var(--border-medium)", background: "linear-gradient(90deg,#16234d,#244481)" }}>
                    <td style={{ padding: "9px 8px", fontSize: 13, fontWeight: 800, color: "#fff" }}>{tc("total")} {bdAt.month}-{yy}</td>
                    <td className="mono" style={{ padding: "9px 8px", textAlign: "right", fontSize: 13.5, fontWeight: 800, color: bd.total < 0 ? "#ff8a80" : "#fff", whiteSpace: "nowrap" }}>{m0(bd.total)}</td>
                  </tr>
                </tbody>
              </table>
            )}
            {bd?.source && (
              <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--bg-input)", borderRadius: 8, border: "1px solid var(--border-subtle)" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.4 }}>{t("dataSource")}</div>
                <div style={{ fontSize: 12.5, color: "var(--text-primary)", margin: "3px 0 8px" }}>{bd.source}</div>
                {bd.link && (
                  <Link href={bd.link} style={{ display: "inline-block", padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, background: "var(--brand)", color: "#fff", textDecoration: "none" }}>
                    {t("irAConfirmar")}{bd.link_label ? ` ${bd.link_label}` : ""}
                  </Link>
                )}
              </div>
            )}
            <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-disabled)" }}>
              {bd?.link
                ? t("notaLink")
                : bd?.source
                ? t("notaSource")
                : t("notaSignos")}
            </div>
          </div>
        </div>
      )}

      {/* La leyenda va SIEMPRE: explica los criterios y no depende de que haya
          datos cargados. Y el texto va envuelto en un <span>: el contenedor es
          flex, así que sin envolverlo cada <b> y cada trozo suelto se vuelve una
          columna y el párrafo se dibuja picado en tiras verticales. */}
      <div className="no-print" style={{ marginTop: 16, display: "flex", justifyContent: "center" }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 10, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "11px 20px", fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 1000 }}>
          <span style={{ width: 22, height: 22, borderRadius: "50%", background: "var(--brand)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, flexShrink: 0, marginTop: 1 }}>i</span>
          <span style={{ lineHeight: 1.6 }}>
            {t.rich("operatingHelp", { b: (c: React.ReactNode) => <b>{c}</b>, gold: (c: React.ReactNode) => <b style={{ color: GOLD }}>{c}</b>, days: t("days") })}
          </span>
        </div>
      </div>
    </div>
  );
}
