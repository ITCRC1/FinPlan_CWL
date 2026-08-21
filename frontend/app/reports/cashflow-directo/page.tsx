"use client";

import { useCallback, useEffect, useState, CSSProperties } from "react";
import { useTranslations } from "next-intl";
import {
  getScenarios, getCashflowDirecto, saveCashflowDirecto,
  getRetenciones, saveTramosRenta, type Retenciones, type TramoRenta, type RentaAnual,
  type EmpleadoRetencion,
  type Scenario, type CashFlowDirecto, type CfDirectoRow,
} from "@/lib/api";
import { bajarCuadros, type Cuadro, type FilaCuadro } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import IrA from "@/components/IrA";

// Los meses salen de `months.short` del catálogo; esto queda de respaldo.
const MESES_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const GOLD = "#c8a24a";

const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

function usd(n: number) {
  if (!n) return "—";
  const s = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Math.abs(n));
  return n < 0 ? `(${s})` : s;
}

type TabKey = "resumen" | "aux_ingresos" | "aux_nomina" | "aux_proveedores" | "aux_gastos_propiedad" | "impuestos";
/* `labelKey` es una CLAVE del catálogo (`cfDirect`), no texto: la lista vive
   fuera del componente y no puede llamar a `t()` acá. */
const TABS: { key: TabKey; labelKey: string }[] = [
  { key: "resumen", labelKey: "tabSummary" },
  { key: "aux_ingresos", labelKey: "tabRevenue" },
  { key: "aux_nomina", labelKey: "tabPayroll" },
  { key: "aux_proveedores", labelKey: "tabSuppliers" },
  { key: "aux_gastos_propiedad", labelKey: "tabProperty" },
  { key: "impuestos", labelKey: "tabTaxes" },
];

// Criterios que gobiernan este flujo. Ya NO se editan acá: viven en la hoja de
// Criterios del Cash Flow y valen igual para los dos métodos. Antes esta pantalla
// tenía su propia copia editable, y guardarla desconectaba el escenario de la
// hoja compartida sin avisar — desde ese momento cambiar un criterio movía un
// método y no el otro.
const CRITERIOS: { key: string; labelKey: string; kind: "pct" | "int" }[] = [
  { key: "iva_rate", labelKey: "crIva", kind: "pct" },
  { key: "card_pct", labelKey: "crCardPct", kind: "pct" },
  { key: "card_renta_ret", labelKey: "crCardRenta", kind: "pct" },
  { key: "card_iva_ret", labelKey: "crCardIva", kind: "pct" },
  { key: "ap_same_pct", labelKey: "crApSame", kind: "pct" },
  { key: "retention", labelKey: "crRetention", kind: "pct" },
  { key: "service_rate", labelKey: "crService", kind: "pct" },
  { key: "service_lag", labelKey: "crServiceLag", kind: "int" },
  { key: "aguinaldo_pay_month", labelKey: "crAguinaldoMonth", kind: "int" },
  { key: "ccss_rate", labelKey: "crCcssEmployer", kind: "pct" },
  { key: "ccss_obrera_rate", labelKey: "crCcssEmployee", kind: "pct" },
  { key: "retencion_rate", labelKey: "crEmployeeWithholding", kind: "pct" },
];

const thNum: CSSProperties = { color: "var(--text-secondary)", fontWeight: 500, fontSize: 11, textAlign: "right", padding: "8px 10px", borderBottom: "1px solid var(--border-medium)", whiteSpace: "nowrap" };
const td: CSSProperties = { padding: "4px 10px", textAlign: "right", borderBottom: "1px solid var(--border-subtle)", whiteSpace: "nowrap", fontSize: 12 };
const cardStyle: CSSProperties = { background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, padding: 14 };

type Params = Record<string, number | number[]>;

export default function CashflowDirectoPage() {
  const tc = useTranslations("common");
  const t = useTranslations("cfDirect");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // El selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se
  // eligio abre con el preferido del owner.
  const [scnId, setScnId] = useEscenarioDe("reports/cashflow-directo:budget", scenarios, "budget", undefined, true);
  const [data, setData] = useState<CashFlowDirecto | null>(null);
  const [params, setParams] = useState<Params>({});
  const [manual, setManual] = useState<Record<string, number[]>>({});
  const [tab, setTab] = useState<TabKey>("resumen");
  const [ret, setRet] = useState<Retenciones | null>(null);
  const [impTab, setImpTab] = useState<"iva" | "salario" | "renta">("iva");
  const [subTab, setSubTab] = useState<"tramos" | "empleados" | "mensual">("empleados");
  const [rentaTasa, setRentaTasa] = useState(0.30);
  const [rentaPago, setRentaPago] = useState(0);
  const [rentaMes, setRentaMes] = useState(3);
  const [tramos, setTramos] = useState<TramoRenta[]>([]);
  const [deduceCcss, setDeduceCcss] = useState(true);
  const [showDrivers, setShowDrivers] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [ayuda, setAyuda] = useState<{ label: string; clave: string } | null>(null);
  // La explicación de cada fila: el motor manda la clave, el texto vive acá.
  const tAy = useTranslations("cfdAyuda");
  // El rótulo de la fila: el motor manda `label_key` cuando es una etiqueta
  // fija de la pantalla. Las filas por DEPARTAMENTO no traen clave —su rótulo
  // es el nombre que viene de la base, o sea DATO— y caen al `label`.
  const tFi = useTranslations("cfdFila");
  const rotulo = (r: { label: string; label_key?: string; label_params?: Record<string, string | number> }) =>
    r.label_key ? r.label.replace(r.label.trim(), tFi(r.label_key, r.label_params ?? {})) : r.label;

  useEffect(() => {
    (async () => {
      try {
        // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    })();
  }, []);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true); setError(""); setMsg("");
    try {
      const d = await getCashflowDirecto(id);
      setData(d); setParams({ ...d.defaults, ...d.params }); setManual({ ...d.manual });
      const r = await getRetenciones(id);
      setRet(r); setTramos(r.tramos); setDeduceCcss(r.deduce_ccss);
      if (d.renta) { setRentaTasa(d.renta.tasa); setRentaPago(d.renta.pago_manual); setRentaMes(d.renta.mes_pago); }
    } catch (e) { setError(e instanceof Error ? t("loadFailed", { msg: e.message }) : "Error"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scnId) load(scnId); }, [scnId, load]);

  async function save() {
    setSaving(true); setMsg(""); setError("");
    try {
      await saveCashflowDirecto(scnId, params, manual);
      setMsg(t("saved")); load(scnId);
    } catch (e) { setError(e instanceof Error ? t("saveFailed", { msg: e.message }) : "Error"); }
    finally { setSaving(false); }
  }

  async function guardarTramos() {
    setSaving(true); setMsg(""); setError("");
    try {
      await saveTramosRenta(scnId, tramos, deduceCcss,
        { renta_tasa: rentaTasa, renta_pago_manual: rentaPago, renta_mes_pago: rentaMes });
      setMsg(t("bracketsSaved")); load(scnId);
    } catch (e) { setError(e instanceof Error ? t("saveFailed", { msg: e.message }) : "Error"); }
    finally { setSaving(false); }
  }

  function setTramo(i: number, campo: "desde" | "hasta" | "tasa", v: number | null) {
    setTramos(ts => ts.map((t, k) => (k === i ? { ...t, [campo]: v } : t)));
  }

  function setManualCell(key: string, i: number, v: number) {
    setManual(prev => { const arr = [...(prev[key] ?? Array(12).fill(0))]; arr[i] = v; return { ...prev, [key]: arr }; });
  }

  /* ── Bajar a Excel ─────────────────────────────────────────────────────────
     Un solo botón para TODOS los tabs: las cinco secciones del flujo, el IVA,
     las retenciones de salario (mensual, por empleado y tramos), la renta anual
     y los criterios efectivos. Cada uno su hoja, en el orden de la pantalla.
     Las filas editables van con lo que el usuario tiene digitado, esté guardado
     o no — el Excel refleja la pantalla, no la base. */
  function filasDeFlujo(rows: CfDirectoRow[]): FilaCuadro[] {
    const VACIA = Array<number | null>(13).fill(null);
    return rows.map(r => {
      // Las bandas de sección van con la fila vacía entera: si se manda 0, el
      // Excel pinta doce ceros que no significan nada.
      if (r.kind === "section")
        return { label: r.label.trim(), es_total: true, valores: [...VACIA] };
      const editable = r.editable && r.kind === "input" && r.key;
      const vals = editable ? (manual[r.key!] ?? r.values) : r.values;
      const annual = editable ? vals.reduce((s, v) => s + (v || 0), 0) : r.full_year;
      const total = isTotal(r.kind);
      return {
        label: r.label.trim(),
        nivel: total ? 0 : 1,
        es_total: total,
        valores: [...vals, annual],
      };
    });
  }

  async function bajarExcel() {
    if (!data) return;
    setExporting(true); setError(""); setMsg("");
    try {
      const scn = scenarios.find(s => s.id === scnId);
      const sub = scn ? scnLabel(scn) : "";
      const anio = scn?.year ?? new Date().getFullYear();
      const colsMes = [
        { label: tc("concept"), ancho: 46, formato: "texto" as const },
        ...MONTHS.map(m => ({ label: m, ancho: 13, formato: "usd" as const })),
        { label: tc("year"), ancho: 16, formato: "usd" as const },
      ];

      const cuadros: Cuadro[] = [
        { titulo: `Cash Flow — ${t("title")} · ${t("xlsSummary")}`, subtitulo: sub, hoja: t("xlsSummary"),
          columnas: colsMes, filas: filasDeFlujo(data.resumen) },
        { titulo: t("xlsAux", { que: t("tabRevenue") }), subtitulo: sub, hoja: t("tabRevenue"),
          columnas: colsMes, filas: filasDeFlujo(data.aux_ingresos) },
        { titulo: t("xlsAux", { que: t("tabPayroll") }), subtitulo: sub, hoja: t("tabPayroll"),
          columnas: colsMes, filas: filasDeFlujo(data.aux_nomina) },
        { titulo: t("xlsAux", { que: t("tabSuppliers") }), subtitulo: sub, hoja: t("tabSuppliers"),
          columnas: colsMes, filas: filasDeFlujo(data.aux_proveedores) },
        { titulo: t("xlsAux", { que: t("tabProperty") }), subtitulo: sub, hoja: t("tabProperty"),
          columnas: colsMes, filas: filasDeFlujo(data.aux_gastos_propiedad) },
        { titulo: `${t("tabTaxes")} — IVA`, subtitulo: sub, hoja: "IVA",
          columnas: colsMes, filas: filasDeFlujo(data.aux_iva) },
      ];

      if (ret) {
        cuadros.push({
          titulo: `${t("impSalary")} — ${t("subMonthly")}`,
          subtitulo: `${sub} · ${t("xlsEmployeesPayTax", { n: ret.empleados_afectos, total: ret.empleados_total })}`,
          hoja: t("xlsSheetRetMonthly"),
          columnas: colsMes,
          filas: [
            { label: t("taxableBase"), nivel: 1, valores: [...ret.base_mes, ret.base_anual] },
            { label: t("salaryWithholding"), es_total: true, valores: [...ret.total_mes, ret.total_anual] },
            // El tipo de cambio no es plata: no se suma en el año.
            { label: t("fxOfMonth"), nivel: 1, formato: "num1",
              valores: [...ret.tc_mes, null] },
          ],
        });

        const afectos = ret.empleados.filter(e => e.afecto);
        const exentos = ret.empleados.filter(e => !e.afecto);
        const filaEmp = (e: EmpleadoRetencion, pagaRenta: boolean): FilaCuadro => ({
          label: e.empleado, nivel: 1,
          valores: [e.puesto, e.dept_code, e.dept_name || e.dept_code, e.base_anual,
            // Sin tramo alcanzado la celda queda vacía, igual que el «—» de la pantalla.
            pagaRenta ? Math.max(...e.tramo) : null,
            pagaRenta ? e.impuesto_anual : 0],
        });
        cuadros.push({
          titulo: `${t("impSalary")} — ${t("subByEmployee")}`,
          subtitulo: `${sub} · ${t("xlsPerEmployeeSub")}`,
          hoja: t("xlsSheetRetEmployees"),
          columnas: [
            { label: tc("employee"), ancho: 32, formato: "texto" },
            { label: t("position"), ancho: 28, formato: "texto" },
            { label: tc("deptCode"), ancho: 11, formato: "texto" },
            { label: tc("department"), ancho: 28, formato: "texto" },
            { label: t("taxableBaseYear"), ancho: 18, formato: "usd" },
            { label: t("maxBracket"), ancho: 13, formato: "num" },
            { label: t("withholdingYear"), ancho: 17, formato: "usd" },
          ],
          filas: [
            { label: t("payIncomeTax", { n: afectos.length }), es_total: true, valores: [null, null, null, null, null, null] },
            ...afectos.map(e => filaEmp(e, true)),
            { label: t("exempt", { n: exentos.length }), es_total: true, valores: [null, null, null, null, null, null] },
            ...exentos.map(e => filaEmp(e, false)),
          ],
        });

        cuadros.push({
          titulo: t("bracketsTitle"),
          subtitulo: `${sub} · ${t("xlsBracketsSub", {
            pct: (ret.ccss_obrera_rate * 100).toFixed(2),
            resta: deduceCcss ? t("xlsIsDeducted") : t("xlsIsNotDeducted"),
          })}`,
          hoja: t("xlsSheetBrackets"),
          columnas: [
            { label: t("bracket"), ancho: 26, formato: "texto" },
            { label: t("fromCrc"), ancho: 16, formato: "num" },
            // `null` = sin techo. Un 0 diría que el tramo no llega a ningún lado.
            { label: t("toCrc"), ancho: 16, formato: "num" },
            { label: t("ratePct"), ancho: 10, formato: "pct" },
          ],
          filas: tramos.map((tr, i) => ({
            label: tr.etiqueta || `${t("bracket")} ${i + 1}`, nivel: 1,
            valores: [tr.desde, tr.hasta, tr.tasa],
          })),
        });
      }

      if (data.renta) {
        const r = data.renta;
        cuadros.push({
          titulo: `${t("xlsCompanyIncomeTax")} — ${t("settlementYear", { anio })}`,
          subtitulo: `${sub} · ${t("xlsPaidMarch", { anio: anio + 1 })}`,
          hoja: t("xlsSheetIncomeTax"),
          columnas: [
            { label: tc("concept"), ancho: 54, formato: "texto" },
            { label: t("xlsAmountUsd"), ancho: 18, formato: "usd" },
          ],
          filas: [
            { label: t("ebt"), nivel: 1, valores: [r.ebt] },
            { label: t("xlsIncomeTaxRate"), nivel: 1, formato: "pct", valores: [rentaTasa] },
            { label: t("incomeTax"), nivel: 1, valores: [r.impuesto_bruto] },
            { label: t("advCardWithholding"), nivel: 1, valores: [-r.creditos_tarjeta] },
            { label: r.neto > 0 ? t("toPayMarch", { anio: anio + 1 }) : t("creditBalance"),
              es_total: true, valores: [Math.abs(r.neto)] },
            { label: `${t("paymentThatLeaves", { anio })} ${t("xlsPriorSettlement", { prev: anio - 1 })}`, nivel: 1, valores: [rentaPago] },
            { label: t("xlsPaymentMonth112"), nivel: 1, formato: "num", valores: [rentaMes] },
            { label: t("xlsAmountToFlow"), es_total: true, valores: [r.pasa_al_flujo] },
          ],
        });
      }

      cuadros.push({
        titulo: t("effectiveCriteria"),
        subtitulo: `${sub} · ${t("criteriaEditedIn")} ${t("criteria")} ${t("criteriaShownOnly")}`,
        hoja: t("criteriaShort"),
        columnas: [
          { label: t("xlsCriterion"), ancho: 42, formato: "texto" },
          { label: t("xlsValue"), ancho: 14, formato: "num" },
        ],
        filas: CRITERIOS.map(f => ({
          label: t(f.labelKey), nivel: 1,
          // Los % viajan como FRACCIÓN: 0.13, no 13. El formato de Excel pone el signo.
          formato: f.kind === "pct" ? ("pct" as const) : ("num" as const),
          valores: [(params[f.key] as number) ?? null],
        })),
      });

      await bajarCuadros("Cash_Flow_Directo", cuadros);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    } finally {
      setExporting(false);
    }
  }

  // El tab de Retenciones no sale del payload del flujo: tiene su propio endpoint.
  const rows = (tab === "impuestos" ? [] : ((data?.[tab] as CfDirectoRow[] | undefined) ?? [])) as CfDirectoRow[];
  const filasIva = (data?.aux_iva ?? []) as CfDirectoRow[];
  const isTotal = (k: string) => k === "total" || k === "total_strong";

  return (
    <div className="pag pag-ancha" style={{ padding: "20px 20px 44px" }}>
      <IrA esc={scnId} />
      <div style={{ textAlign: "center", marginBottom: 10 }}>
        <h1 style={{ fontSize: 30, fontWeight: 800, margin: 0, letterSpacing: -0.5 }}>
          <span style={{ color: "var(--text-primary)" }}>Cash Flow </span><span style={{ color: "var(--brand)" }}>{t("title")}</span>
        </h1>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 600, marginTop: 4 }}>
          {t.rich("subtitle", { s: (c: React.ReactNode) => <span style={{ color: GOLD }}>{c}</span> })}
        </div>
      </div>

      {/* Escenario + acciones */}
      <div style={{ display: "flex", gap: 8, justifyContent: "center", alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
        <select value={scnId} onChange={e => setScnId(e.target.value)}
          style={{ padding: "6px 12px", fontSize: 12, fontWeight: 600, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
        </select>
        <button onClick={() => setShowDrivers(s => !s)} style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
          ⚙ {t("criteriaShort")} {showDrivers ? "▲" : "▼"}
        </button>
        <button onClick={save} disabled={saving || !scnId} style={{ padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", opacity: saving ? 0.6 : 1 }}>
          {saving ? tc("saving") : t("saveBtn")}
        </button>
        <button onClick={() => load(scnId)} style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--bg-elevated)", color: "var(--brand)", border: "1px solid var(--brand)" }}>{t("recalcBtn")}</button>
        <button onClick={bajarExcel} disabled={exporting || !data}
          title={t("excelTitle")}
          style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          {exporting ? t("generating") : "⬇ Excel"}
        </button>
        {msg && <span style={{ color: "var(--positive)", fontSize: 12, alignSelf: "center" }}>{msg}</span>}
        {error && <span style={{ color: "var(--negative)", fontSize: 12, alignSelf: "center" }}>{error}</span>}
      </div>

      {/* Criterios efectivos — solo lectura */}
      {showDrivers && (
        <div style={{ ...cardStyle, marginBottom: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: GOLD, marginBottom: 8, textTransform: "uppercase" }}>
            {t("effectiveCriteria")}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 10 }}>
            {CRITERIOS.map(f => (
              <div key={f.key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t(f.labelKey)}</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>
                  {f.kind === "pct"
                    ? `${(((params[f.key] as number) ?? 0) * 100).toFixed(2)}%`
                    : String((params[f.key] as number) ?? "—")}
                </span>
              </div>
            ))}
          </div>
          <p style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>
            {t("criteriaEditedIn")}{" "}
            <a href="/reports/cashflow-criteria" style={{ color: "var(--brand)", fontWeight: 700 }}>
              {t("criteria")}
            </a>{" "}
            {t("criteriaShownOnly")}
          </p>
        </div>
      )}

      {/* Sub-tabs */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "center", marginBottom: 14 }}>
        {TABS.map(tb => (
          <button key={tb.key} onClick={() => setTab(tb.key)} style={{
            padding: "5px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer",
            background: tab === tb.key ? "var(--brand)" : "var(--bg-input)", color: tab === tb.key ? "#fff" : "var(--text-primary)",
            border: `1px solid ${tab === tb.key ? "var(--brand)" : "var(--border-medium)"}`,
          }}>{t(tb.labelKey)}</button>
        ))}
      </div>

      {loading && <div style={{ color: "var(--text-secondary)", textAlign: "center", padding: 40 }}>{t("calculating")}</div>}

      {!loading && tab === "impuestos" && (
        <>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "center", marginBottom: 14 }}>
            {([["iva", "IVA"], ["salario", t("impSalary")], ["renta", t("impIncome")]] as const).map(([k, l]) => (
              <button key={k} onClick={() => setImpTab(k)} style={{
                padding: "6px 16px", borderRadius: 6, fontSize: 12.5, fontWeight: 700, cursor: "pointer",
                background: impTab === k ? GOLD : "var(--bg-input)",
                color: impTab === k ? "#1a1408" : "var(--text-primary)",
                border: "1px solid " + (impTab === k ? GOLD : "var(--border-medium)"),
              }}>{l}</button>
            ))}
          </div>

          {impTab === "iva" && <TablaFilas rows={filasIva} onAyuda={setAyuda} />}

          {impTab === "salario" && ret && (
            <RetencionesTab
              ret={ret} subTab={subTab} setSubTab={setSubTab}
              tramos={tramos} setTramo={setTramo}
              deduceCcss={deduceCcss} setDeduceCcss={setDeduceCcss}
              guardar={guardarTramos} saving={saving} />
          )}

          {impTab === "renta" && (
            <RentaAnualPanel
              renta={data?.renta ?? null}
              anio={scenarios.find(x => x.id === scnId)?.year ?? new Date().getFullYear()}
              tasa={rentaTasa} setTasa={setRentaTasa}
              pago={rentaPago} setPago={setRentaPago}
              mes={rentaMes} setMes={setRentaMes}
              guardar={guardarTramos} saving={saving} />
          )}
        </>
      )}

      {!loading && tab !== "impuestos" && data && (
        <>
          <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12 }}>
            <table style={{ borderCollapse: "collapse", minWidth: 1100, width: "100%", fontSize: 12 }}>
              <thead>
                <tr style={{ background: "var(--bg-header)" }}>
                  <th style={{ ...thNum, textAlign: "left", position: "sticky", left: 0, background: "var(--bg-header)", minWidth: 300 }}>{tc("concept")}</th>
                  {MONTHS.map(m => <th key={m} style={thNum}>{m}</th>)}
                  <th style={{ ...thNum, color: "var(--text-primary)", fontWeight: 700 }}>{tc("year")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, ri) => {
                  if (r.kind === "section") return (
                    <tr key={ri}>
                      <td colSpan={14} style={{ background: "var(--bg-header)", color: GOLD, fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", padding: "5px 10px", textTransform: "uppercase", position: "sticky", left: 0, zIndex: 1 }}>{rotulo(r)}</td>
                    </tr>
                  );
                  const total = isTotal(r.kind);
                  const strong = r.kind === "total_strong";
                  const editable = r.editable && r.kind === "input" && r.key;
                  const vals = editable ? (manual[r.key!] ?? r.values) : r.values;
                  const annual = editable ? (manual[r.key!] ?? r.values).reduce((s, v) => s + (v || 0), 0) : r.full_year;
                  const rowBg = total ? "var(--bg-elevated)" : r.kind === "sub" ? "rgba(200,162,74,0.08)" : "transparent";
                  const color = strong ? GOLD : "var(--text-primary)";
                  return (
                    <tr key={ri} style={{ background: rowBg }}>
                      <td onClick={() => r.ayuda && setAyuda({ label: r.label, ...r.ayuda })}
                        title={r.ayuda ? t("clickForSource") : undefined}
                        style={{ ...td, textAlign: "left", position: "sticky", left: 0, zIndex: 1, background: total ? "var(--bg-elevated)" : "var(--bg-base)", color: total ? color : "var(--text-secondary)", fontWeight: total ? 700 : 400, cursor: r.ayuda ? "help" : "default", textDecoration: r.ayuda ? "underline dotted var(--border-medium)" : "none", textUnderlineOffset: 3 }}>{rotulo(r)}</td>
                      {vals.map((v, i) => (
                        <td key={i} style={{ ...td, fontWeight: total ? 700 : 400 }}>
                          {editable
                            ? <input type="number" className="fin-input" style={{ width: 68 }} value={v || ""} onChange={e => setManualCell(r.key!, i, parseFloat(e.target.value) || 0)} />
                            : <span className="mono" style={{ color: v < 0 ? "var(--negative)" : total ? color : "var(--text-primary)" }}>{usd(v)}</span>}
                        </td>
                      ))}
                      <td style={{ ...td, fontWeight: 700, background: "var(--bg-surface)", color: annual < 0 ? "var(--negative)" : strong ? GOLD : "var(--text-primary)" }}>
                        <span className="mono">{usd(annual)}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 12, textAlign: "center" }}>
            {t.rich("editableNote", {
              b: (c: React.ReactNode) => <b>{c}</b>,
              a: (c: React.ReactNode) => <a href="/reports/cashflow-criteria" style={{ color: "var(--brand)", fontWeight: 700 }}>{c}</a>,
              criterios: t("criteria"),
            })}
          </p>
        </>
      )}

      {ayuda && (
        <div onClick={() => setAyuda(null)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50, padding: 20 }}>
          <div onClick={e => e.stopPropagation()}
            style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, padding: "20px 22px", maxWidth: 560, boxShadow: "0 16px 48px rgba(0,0,0,0.5)" }}>
            <div style={{ fontSize: 10.5, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-secondary)", fontWeight: 700 }}>{t("whereFrom")}</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: GOLD, margin: "4px 0 12px" }}>{ayuda.label.trim()}</div>
            <p style={{ fontSize: 13.5, lineHeight: 1.6, color: "var(--text-primary)", margin: 0 }}>{tAy(`${ayuda.clave}.deDonde`)}</p>
            {tAy.has(`${ayuda.clave}.formula`) && (
              <div style={{ marginTop: 14 }}>
                <div style={{ fontSize: 10.5, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-secondary)", fontWeight: 700, marginBottom: 4 }}>{t("calculation")}</div>
                <code className="mono" style={{ display: "block", fontSize: 12, color: "var(--text-primary)", background: "var(--bg-base)", border: "1px solid var(--border-subtle)", borderRadius: 6, padding: "8px 10px", whiteSpace: "pre-wrap" }}>{tAy(`${ayuda.clave}.formula`)}</code>
              </div>
            )}
            <button onClick={() => setAyuda(null)} style={{ marginTop: 16, padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)" }}>{tc("close")}</button>
          </div>
        </div>
      )}
    </div>
  );
}


// ── Retenciones de renta al salario ─────────────────────────────────────────
// El impuesto es progresivo y MENSUAL, así que no sale de un % sobre la masa
// salarial: depende de cómo esté repartida. En Budget 2027, de 122 empleados
// solo 5 pagan. Por eso el cálculo recorre persona por persona.
function RetencionesTab({ ret, subTab, setSubTab, tramos, setTramo, deduceCcss, setDeduceCcss, guardar, saving }: {
  ret: Retenciones;
  subTab: "tramos" | "empleados" | "mensual";
  setSubTab: (s: "tramos" | "empleados" | "mensual") => void;
  tramos: TramoRenta[];
  setTramo: (i: number, campo: "desde" | "hasta" | "tasa", v: number | null) => void;
  deduceCcss: boolean;
  setDeduceCcss: (b: boolean) => void;
  guardar: () => void;
  saving: boolean;
}) {
  const tc = useTranslations("common");
  const t = useTranslations("cfDirect");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const SUBS: { k: "tramos" | "empleados" | "mensual"; label: string }[] = [
    { k: "empleados", label: t("subByEmployee") },
    { k: "mensual", label: t("subMonthly") },
    { k: "tramos", label: t("subBrackets") },
  ];
  const afectos = ret.empleados.filter(e => e.afecto);
  const exentos = ret.empleados.filter(e => !e.afecto);
  const tiles = [
    { k: t("tileEmployees"), v: String(ret.empleados_total) },
    { k: t("tilePayIncomeTax"), v: String(ret.empleados_afectos) },
    { k: t("withholdingYear"), v: usd(ret.total_anual) },
    { k: t("tileOnTaxableBase"), v: usd(ret.base_anual) },
  ];

  return (
    <>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", justifyContent: "center", marginBottom: 14 }}>
        {tiles.map(t => (
          <div key={t.k} style={{ ...cardStyle, minWidth: 170, textAlign: "center" }}>
            <div style={{ fontSize: 10.5, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>{t.k}</div>
            <div className="mono" style={{ fontSize: 19, fontWeight: 700, color: GOLD, marginTop: 3 }}>{t.v}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "center", marginBottom: 12 }}>
        {SUBS.map(t => (
          <button key={t.k} onClick={() => setSubTab(t.k)} style={{
            padding: "5px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer",
            background: subTab === t.k ? "var(--brand)" : "var(--bg-input)",
            color: subTab === t.k ? "#fff" : "var(--text-primary)",
            border: "1px solid " + (subTab === t.k ? "var(--brand)" : "var(--border-medium)"),
          }}>{t.label}</button>
        ))}
      </div>

      {subTab === "tramos" && (
        <div style={{ ...cardStyle, maxWidth: 900, margin: "0 auto" }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: GOLD, marginBottom: 4, textTransform: "uppercase" }}>
            {t("bracketsTitle")}
          </div>
          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 0 }}>
            {t.rich("bracketsHelp", { b: (c: React.ReactNode) => <b>{c}</b> })}
          </p>
          <div className="fin-scroll-x" style={{ overflowX: "auto", marginTop: 8 }}>
            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12.5 }}>
              <thead>
                <tr>
                  <th style={{ ...thNum, textAlign: "left" }}>{t("bracket")}</th>
                  <th style={thNum}>{t("fromCrc")}</th>
                  <th style={thNum}>{t("toCrc")}</th>
                  <th style={thNum}>{t("ratePct")}</th>
                </tr>
              </thead>
              <tbody>
                {tramos.map((tr, i) => (
                  <tr key={i}>
                    <td style={{ ...td, textAlign: "left" }}>{i + 1}</td>
                    <td style={td}><input type="number" className="fin-input" style={{ width: 110 }} value={tr.desde}
                      onChange={e => setTramo(i, "desde", parseFloat(e.target.value) || 0)} /></td>
                    <td style={td}><input type="number" className="fin-input" style={{ width: 110 }}
                      value={tr.hasta ?? ""} placeholder={t("noCeiling")}
                      onChange={e => setTramo(i, "hasta", e.target.value === "" ? null : parseFloat(e.target.value))} /></td>
                    <td style={td}><input type="number" step="0.01" className="fin-input" style={{ width: 80 }} value={tr.tasa * 100}
                      onChange={e => setTramo(i, "tasa", (parseFloat(e.target.value) || 0) / 100)} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, fontSize: 12.5 }}>
            <input type="checkbox" checked={deduceCcss} onChange={e => setDeduceCcss(e.target.checked)} />
            <span>{t("deductCcss", { pct: (ret.ccss_obrera_rate * 100).toFixed(2) })}</span>
          </label>
          <p style={{ fontSize: 11, color: "var(--text-secondary)" }}>
            {t("deductCcssHelp")}
          </p>
          <button onClick={guardar} disabled={saving} style={{ marginTop: 8, padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", opacity: saving ? 0.6 : 1 }}>
            {saving ? tc("saving") : t("saveBrackets")}
          </button>
        </div>
      )}

      {subTab === "mensual" && (
        <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12 }}>
          <table style={{ borderCollapse: "collapse", minWidth: 1100, width: "100%", fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ ...thNum, textAlign: "left", position: "sticky", left: 0, minWidth: 260 }}>{tc("concept")}</th>
                {MONTHS.map(m => <th key={m} style={thNum}>{m}</th>)}
                <th style={{ ...thNum, color: "var(--text-primary)", fontWeight: 700 }}>{tc("year")}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ ...td, textAlign: "left", position: "sticky", left: 0, zIndex: 1, background: "var(--bg-base)", color: "var(--text-secondary)" }}>{t("taxableBase")}</td>
                {ret.base_mes.map((v, k) => <td key={k} style={td}><span className="mono">{usd(v)}</span></td>)}
                <td style={{ ...td, fontWeight: 700, background: "var(--bg-surface)" }}><span className="mono">{usd(ret.base_anual)}</span></td>
              </tr>
              <tr>
                <td style={{ ...td, textAlign: "left", position: "sticky", left: 0, zIndex: 1, background: "var(--bg-base)", color: GOLD, fontWeight: 700 }}>{t("salaryWithholding")}</td>
                {ret.total_mes.map((v, k) => <td key={k} style={{ ...td, fontWeight: 700 }}><span className="mono" style={{ color: GOLD }}>{usd(v)}</span></td>)}
                <td style={{ ...td, fontWeight: 700, background: "var(--bg-surface)", color: GOLD }}><span className="mono">{usd(ret.total_anual)}</span></td>
              </tr>
              <tr>
                <td style={{ ...td, textAlign: "left", position: "sticky", left: 0, zIndex: 1, background: "var(--bg-base)", color: "var(--text-secondary)" }}>{t("fxOfMonth")}</td>
                {ret.tc_mes.map((v, k) => <td key={k} style={td}><span className="mono">{v.toLocaleString("en-US", { maximumFractionDigits: 2 })}</span></td>)}
                <td style={{ ...td, background: "var(--bg-surface)" }}><span className="mono">—</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {subTab === "empleados" && (
        <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12 }}>
          <table style={{ borderCollapse: "collapse", minWidth: 1000, width: "100%", fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ ...thNum, textAlign: "left", position: "sticky", left: 0, minWidth: 250 }}>{tc("employee")}</th>
                <th style={{ ...thNum, textAlign: "left" }}>{t("position")}</th>
                <th style={{ ...thNum, textAlign: "left" }}>{tc("department")}</th>
                <th style={thNum}>{t("taxableBaseYear")}</th>
                <th style={thNum}>{t("maxBracket")}</th>
                <th style={{ ...thNum, color: "var(--text-primary)", fontWeight: 700 }}>{t("withholdingYear")}</th>
              </tr>
            </thead>
            <tbody>
              <tr><td colSpan={6} style={{ background: "var(--bg-header)", color: GOLD, fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", padding: "5px 10px", textTransform: "uppercase", position: "sticky", left: 0, zIndex: 1 }}>
                {t("payIncomeTax", { n: afectos.length })}
              </td></tr>
              {afectos.map(e => (
                <tr key={e.position_id}>
                  <td style={{ ...td, textAlign: "left", position: "sticky", left: 0, zIndex: 1, background: "var(--bg-base)", color: "var(--text-primary)", fontWeight: 600 }}>{e.empleado}</td>
                  <td style={{ ...td, textAlign: "left", color: "var(--text-secondary)" }}>{e.puesto}</td>
                  <td style={{ ...td, textAlign: "left", color: "var(--text-secondary)" }}>{e.dept_name || e.dept_code}</td>
                  <td style={td}><span className="mono">{usd(e.base_anual)}</span></td>
                  <td style={td}><span className="mono">{Math.max(...e.tramo)}</span></td>
                  <td style={{ ...td, fontWeight: 700 }}><span className="mono" style={{ color: GOLD }}>{usd(e.impuesto_anual)}</span></td>
                </tr>
              ))}
              <tr><td colSpan={6} style={{ background: "var(--bg-header)", color: "var(--text-secondary)", fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", padding: "5px 10px", textTransform: "uppercase", position: "sticky", left: 0, zIndex: 1 }}>
                {t("exempt", { n: exentos.length })}
              </td></tr>
              {exentos.map(e => (
                <tr key={e.position_id}>
                  <td style={{ ...td, textAlign: "left", position: "sticky", left: 0, zIndex: 1, background: "var(--bg-base)", color: "var(--text-secondary)" }}>{e.empleado}</td>
                  <td style={{ ...td, textAlign: "left", color: "var(--text-secondary)" }}>{e.puesto}</td>
                  <td style={{ ...td, textAlign: "left", color: "var(--text-secondary)" }}>{e.dept_name || e.dept_code}</td>
                  <td style={td}><span className="mono">{usd(e.base_anual)}</span></td>
                  <td style={td}><span className="mono">—</span></td>
                  <td style={td}><span className="mono">{usd(0)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}


// Cuadro de filas mes × concepto, para los sub-tabs que no tienen celdas editables.
function TablaFilas({ rows, onAyuda }: {
  rows: CfDirectoRow[];
  onAyuda: (a: { label: string; clave: string }) => void;
}) {
  const tc = useTranslations("common");
  const t = useTranslations("cfDirect");
  const tm = useTranslations("months");
  // Su propia copia: los hooks no cruzan de un componente a otro.
  const tFi = useTranslations("cfdFila");
  const rotulo = (r: { label: string; label_key?: string; label_params?: Record<string, string | number> }) =>
    r.label_key ? r.label.replace(r.label.trim(), tFi(r.label_key, r.label_params ?? {})) : r.label;
  const MONTHS = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const isTotal = (k: string) => k === "total" || k === "total_strong";
  return (
    <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12 }}>
      <table style={{ borderCollapse: "collapse", minWidth: 1100, width: "100%", fontSize: 12 }}>
        <thead>
          <tr>
            <th style={{ ...thNum, textAlign: "left", position: "sticky", left: 0, minWidth: 300 }}>{tc("concept")}</th>
            {MONTHS.map(m => <th key={m} style={thNum}>{m}</th>)}
            <th style={{ ...thNum, color: "var(--text-primary)", fontWeight: 700 }}>{tc("year")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => {
            if (r.kind === "section") return (
              <tr key={ri}>
                <td colSpan={14} style={{ background: "var(--bg-header)", color: GOLD, fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", padding: "5px 10px", textTransform: "uppercase", position: "sticky", left: 0, zIndex: 1 }}>{rotulo(r)}</td>
              </tr>
            );
            const total = isTotal(r.kind);
            const strong = r.kind === "total_strong";
            const color = strong ? GOLD : "var(--text-primary)";
            return (
              <tr key={ri} style={{ background: total ? "var(--bg-elevated)" : r.kind === "sub" ? "rgba(200,162,74,0.08)" : "transparent" }}>
                <td onClick={() => r.ayuda && onAyuda({ label: r.label, ...r.ayuda })}
                  title={r.ayuda ? t("clickForSource") : undefined}
                  style={{ ...td, textAlign: "left", position: "sticky", left: 0, zIndex: 1, background: total ? "var(--bg-elevated)" : "var(--bg-base)", color: total ? color : "var(--text-secondary)", fontWeight: total ? 700 : 400, cursor: r.ayuda ? "help" : "default", textDecoration: r.ayuda ? "underline dotted var(--border-medium)" : "none", textUnderlineOffset: 3 }}>{rotulo(r)}</td>
                {r.values.map((v, i) => (
                  <td key={i} style={{ ...td, fontWeight: total ? 700 : 400 }}>
                    <span className="mono" style={{ color: v < 0 ? "var(--negative)" : total ? color : "var(--text-primary)" }}>{usd(v)}</span>
                  </td>
                ))}
                <td style={{ ...td, fontWeight: 700, background: "var(--bg-surface)", color: r.full_year < 0 ? "var(--negative)" : strong ? GOLD : "var(--text-primary)" }}>
                  <span className="mono">{usd(r.full_year)}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}


// ── Renta anual de la empresa (30% sobre la utilidad) ───────────────────────
// El impuesto que se calcula sobre la utilidad de ESTE año se paga en marzo del
// año SIGUIENTE, así que no es caja de este flujo. Lo que sale este año es la
// liquidación del año anterior — otro P&L, otro cálculo — y por eso ese monto
// se carga a mano.
function RentaAnualPanel({ renta, anio, tasa, setTasa, pago, setPago, mes, setMes, guardar, saving }: {
  renta: RentaAnual | null;
  anio: number;
  tasa: number; setTasa: (v: number) => void;
  pago: number; setPago: (v: number) => void;
  mes: number; setMes: (m: number) => void;
  guardar: () => void; saving: boolean;
}) {
  const t = useTranslations("cfDirect");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  if (!renta) return <div style={{ color: "var(--text-secondary)", textAlign: "center", padding: 30 }}>{t("noTaxData")}</div>;
  const aPagar = renta.neto > 0;
  return (
    <div style={{ display: "flex", gap: 16, flexWrap: "wrap", justifyContent: "center", alignItems: "flex-start" }}>

      <div style={{ ...cardStyle, maxWidth: 560, flex: "1 1 460px" }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: GOLD, marginBottom: 4, textTransform: "uppercase" }}>
          {t("settlementYear", { anio })}
        </div>
        <p style={{ fontSize: 11.5, color: "var(--text-secondary)", margin: "0 0 10px" }}>
          {t.rich("informativeMarch", { b: (c: React.ReactNode) => <b>{c}</b>, anio: anio + 1 })}
        </p>
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
          <tbody>
            <tr>
              <td style={{ ...td, textAlign: "left" }}>{t("ebt")}</td>
              <td style={td}><span className="mono">{usd(renta.ebt)}</span></td>
            </tr>
            <tr>
              <td style={{ ...td, textAlign: "left" }}>
                {t("incomeTax")}
                <input type="number" step="0.01" className="fin-input" style={{ width: 66, marginLeft: 8 }}
                  value={(tasa * 100).toFixed(2)}
                  onChange={e => setTasa((parseFloat(e.target.value) || 0) / 100)} />
                <span style={{ marginLeft: 4, color: "var(--text-secondary)" }}>%</span>
              </td>
              <td style={td}><span className="mono">{usd(renta.impuesto_bruto)}</span></td>
            </tr>
            <tr>
              <td style={{ ...td, textAlign: "left", color: "var(--text-secondary)" }}>
                {t("advCardWithholding")}
              </td>
              <td style={td}><span className="mono">{usd(-renta.creditos_tarjeta)}</span></td>
            </tr>
            <tr>
              <td style={{ ...td, textAlign: "left", fontWeight: 700, borderTop: "2px solid var(--border-medium)" }}>
                {aPagar ? t("toPayMarch", { anio: anio + 1 }) : t("creditBalance")}
              </td>
              <td style={{ ...td, fontWeight: 700, borderTop: "2px solid var(--border-medium)" }}>
                <span className="mono" style={{ color: aPagar ? GOLD : "var(--positive)", fontSize: 15 }}>
                  {usd(Math.abs(renta.neto))}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div style={{ ...cardStyle, maxWidth: 460, flex: "1 1 380px" }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: GOLD, marginBottom: 4, textTransform: "uppercase" }}>
          {t("paymentThatLeaves", { anio })}
        </div>
        <p style={{ fontSize: 11.5, color: "var(--text-secondary)", margin: "0 0 12px" }}>
          {t.rich("priorYearSettlement", { b: (c: React.ReactNode) => <b>{c}</b>, prev: anio - 1, anio })}
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
          <span style={{ color: "var(--text-secondary)", minWidth: 96 }}>{t("amountDue")}</span>
          <input type="number" className="fin-input" style={{ width: 130 }} value={pago || ""}
            placeholder="0" onChange={e => setPago(Math.max(0, parseFloat(e.target.value) || 0))} />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 12.5 }}>
          <span style={{ color: "var(--text-secondary)", minWidth: 96 }}>{t("paymentMonth")}</span>
          <select value={mes} onChange={e => setMes(parseInt(e.target.value))}
            style={{ padding: "4px 10px", fontSize: 12, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </div>
        <button onClick={guardar} disabled={saving} style={{ marginTop: 14, padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", opacity: saving ? 0.6 : 1 }}>
          {saving ? tc("saving") : t("saveApply")}
        </button>
        {renta.pasa_al_flujo > 0
          ? <p style={{ fontSize: 11.5, color: GOLD, marginTop: 10, fontWeight: 600 }}>
              {t("activeFlow", { monto: usd(renta.pasa_al_flujo), mes: MONTHS[renta.mes_pago - 1] })}
            </p>
          : <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 10 }}>
              {t("zeroFlow")}
            </p>}
      </div>
    </div>
  );
}
