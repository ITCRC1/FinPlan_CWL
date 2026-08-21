"use client";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  getScenarios, getCashflowBudget, saveCashflowBudgetWcModel,
  type Scenario, type WcParams,
} from "@/lib/api";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

// Los meses salen de `months.short` del catálogo; esto queda de respaldo.
const MESES_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const GOLD = "#c8a24a";
const num = (s: string) => { const v = parseFloat(String(s).replace(/[$,%\s]/g, "")); return isNaN(v) ? 0 : v; };

/* `titleKey`, `labelKey` y `helpKey` son CLAVES del catálogo (`cfCriteria`), no
   texto: esta lista vive fuera del componente y no puede llamar a `t()` acá. */
type Field = { k: string; labelKey: string; helpKey: string; pct?: boolean; money?: boolean; bool?: boolean };
const GROUPS: { titleKey: string; fields: Field[] }[] = [
  { titleKey: "grpDeposits", fields: [
    { k: "retention", labelKey: "fRetention", helpKey: "fRetentionHelp", pct: true },
  ] },
  { titleKey: "grpCard", fields: [
    { k: "card_pct", labelKey: "fCardPct", helpKey: "fCardPctHelp", pct: true },
    { k: "card_iva_ret", labelKey: "fCardIva", helpKey: "fCardIvaHelp", pct: true },
    { k: "card_renta_ret", labelKey: "fCardRenta", helpKey: "fCardRentaHelp", pct: true },
  ] },
  { titleKey: "grpService", fields: [
    { k: "service_rate", labelKey: "fServiceRate", helpKey: "fServiceRateHelp", pct: true },
    { k: "service_lag", labelKey: "fServiceLag", helpKey: "fServiceLagHelp" },
  ] },
  { titleKey: "grpIvaApAgu", fields: [
    { k: "payroll_outsourced", labelKey: "fOutsourced", helpKey: "fOutsourcedHelp", bool: true },
    { k: "iva_rate", labelKey: "fIvaRate", helpKey: "fIvaRateHelp", pct: true },
    { k: "ap_same_pct", labelKey: "fApSame", helpKey: "fApSameHelp", pct: true },
    { k: "aguinaldo_monthly", labelKey: "fAguinaldo", helpKey: "fAguinaldoHelp", money: true },
    { k: "aguinaldo_pay_month", labelKey: "fAguinaldoMonth", helpKey: "fAguinaldoMonthHelp" },
  ] },
];

export default function CashflowCriteriaPage() {
  const tc = useTranslations("common");
  const t = useTranslations("cfCriteria");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // El selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se
  // eligio abre con el preferido del owner.
  const [scnId, setScnId] = useEscenarioDe("reports/cashflow-criteria:budget", scenarios, "budget", undefined, true);
  const [enabled, setEnabled] = useState(false);
  const [params, setParams] = useState<WcParams>({});
  const [offsets, setOffsets] = useState<number[]>([-4, -3, -2, -1, 0, 1]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true); setError(null); setMsg(null);
    try {
      const res = await getCashflowBudget(id);
      setEnabled(res.wc_model?.enabled ?? false);
      const tm = res.wc_model?.timing_matrix;
      const off = res.wc_model?.timing_offsets;
      if (Array.isArray(off) && off.length) setOffsets(off);
      const pr = res.wc_model?.params ?? {};
      setParams({ ...pr, timing_matrix: Array.isArray(tm) ? tm : [] });
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (scnId) load(scnId); }, [scnId, load]);

  const numv = (k: string) => (typeof params[k] === "number" ? params[k] as number : 0);
  const matrix = (Array.isArray(params.timing_matrix) ? params.timing_matrix : []) as number[][];
  function setField(k: string, display: string, pct?: boolean) {
    const raw = num(display);
    setParams(p => ({ ...p, [k]: pct ? raw / 100 : raw }));
  }
  /* Las 24 filas de la vista: los últimos 6 meses del año ANTERIOR, los 12 del
     año, y los primeros 6 del SIGUIENTE. Cada bloque guarda en su propia clave.

     Por qué 6 y 6: los offsets llegan a 4 meses antes y +1 mes, así que del año
     anterior solo diciembre alcanza a cobrar acá (por el +1) y del siguiente
     solo enero a abril (por los depósitos). Los demás se muestran igual, para
     ver el año corrido de una sola vez — pero no mueven la caja de este año, y
     por eso van marcados.  */
  const bloque = (k: string) => (Array.isArray(params[k]) ? params[k] : []) as number[][];
  /* Si el bloque vecino no está definido, se muestra la fila del MISMO mes del
     año en curso: es el default del motor, así que la pantalla dice la verdad
     de lo que se está calculando en vez de mostrar ceros. */
  const filaDe = (k: string, i: number): number[] =>
    bloque(k)[i] ?? matrix[k === "timing_matrix_prev" ? i + 6 : i] ?? [];

  function setCellEn(clave: string, largo: number, mi: number, ci: number, display: string) {
    setParams(p => {
      const base = (Array.isArray(p[clave]) ? p[clave] : []) as number[][];
      const m = Array.from({ length: largo }, (_, i) => [...(base[i] ?? [])]);
      while (m[mi].length < offsets.length) m[mi].push(0);
      m[mi][ci] = num(display) / 100;
      return { ...p, [clave]: m };
    });
  }
  function setCell(mi: number, ci: number, display: string) {
    setParams(p => {
      const m = ((Array.isArray(p.timing_matrix) ? p.timing_matrix : []) as number[][]).map(r => [...(r || [])]);
      while (m.length < 12) m.push(Array(offsets.length).fill(0));
      while (m[mi].length < offsets.length) m[mi].push(0);
      m[mi][ci] = num(display) / 100;
      return { ...p, timing_matrix: m };
    });
  }

  /* Año del escenario, para rotular cada bloque. Sin esto, «Ene» arriba y «Ene»
     abajo son indistinguibles y es justo lo que hay que poder distinguir. */
  const anio = scenarios.find(x => x.id === scnId)?.year ?? new Date().getFullYear();

  type FilaTiming = { etiqueta: string; clave: string; idx: number; largo: number; vecino: boolean; aporta: boolean };
  const FILAS: FilaTiming[] = [
    ...MONTHS.slice(6).map((m, k) => ({
      etiqueta: `${m} ${anio - 1}`, clave: "timing_matrix_prev", idx: k, largo: 6,
      vecino: true, aporta: k === 5,          // solo Dic del año anterior cobra acá
    })),
    ...MONTHS.map((m, i) => ({
      etiqueta: `${m} ${anio}`, clave: "timing_matrix", idx: i, largo: 12,
      vecino: false, aporta: true,
    })),
    ...MONTHS.slice(0, 6).map((m, k) => ({
      etiqueta: `${m} ${anio + 1}`, clave: "timing_matrix_next", idx: k, largo: 6,
      vecino: true, aporta: k <= 3,           // Ene-Abr del siguiente dejan depósito acá
    })),
  ];
  const offLabel = (o: number) => o < 0 ? t("mBefore", { n: -o }) : o === 0 ? t("sameMonth") : `+${o}m`;

  /* Dos hojas: los criterios sueltos y la matriz de timing completa (las 24 filas,
     incluidas las del año vecino). Los % viajan como fracción y el interruptor
     del modelo como 1/0 — la hoja es para revisar y recalcular, no para leerla. */
  async function bajarExcel() {
    const criterios: FilaCuadro[] = [
      { label: t("timingModelActiveXls"), nivel: 0, es_total: true, formato: "num", valores: [enabled ? 1 : 0] },
    ];
    for (const grp of GROUPS) {
      criterios.push({ label: t(grp.titleKey), nivel: 0, es_total: true, valores: [null] });
      for (const f of grp.fields) {
        criterios.push({
          label: t(f.labelKey), nivel: 1,
          formato: f.pct ? "pct" : f.money ? "usd2" : "num",
          valores: [f.bool ? (params[f.k] !== false ? 1 : 0) : numv(f.k)],
        });
      }
    }

    const timing: FilaCuadro[] = FILAS.map(f => {
      const row = f.clave === "timing_matrix" ? (matrix[f.idx] ?? []) : filaDe(f.clave, f.idx);
      const celdas = offsets.map((_o, ci) => row[ci] ?? 0);
      return {
        label: f.vecino && !f.aporta ? `${f.etiqueta} · ${t("notThisYear")}` : f.etiqueta,
        nivel: f.vecino ? 1 : 0,
        valores: [...celdas, celdas.reduce((a, b) => a + b, 0)],
      };
    });

    const scn = scenarios.find(s => s.id === scnId);
    try {
      await bajarCuadros("Criterios_Cash_Flow", [
        {
          titulo: `${t("titlePrefix")} Cash Flow`, subtitulo: scn ? scnLabel(scn) : "", hoja: t("xlsCriteria"),
          columnas: [{ label: t("xlsCriterion"), ancho: 46, formato: "texto" }, { label: t("xlsValue"), ancho: 14, formato: "num" }],
          filas: criterios,
        },
        {
          titulo: t("timingMatrix"), subtitulo: `${scn ? scnLabel(scn) : ""} · ${t("xlsTimingSub")}`,
          hoja: t("xlsSheetTiming"),
          columnas: [
            { label: t("stayMonth"), ancho: 26, formato: "texto" },
            ...offsets.map(o => ({ label: offLabel(o), ancho: 12, formato: "pct" as const })),
            { label: "Σ", ancho: 10, formato: "pct" as const },
          ],
          filas: timing,
        },
      ]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFailed")); }
  }

  async function save() {
    if (!scnId) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      await saveCashflowBudgetWcModel(scnId, enabled, params);
      setMsg(t("saved"));
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setSaving(false); }
  }

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const inp: React.CSSProperties = { width: 92, textAlign: "right", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-subtle)", borderRadius: 4, padding: "5px 7px", fontSize: 12.5 };
  const fInp: React.CSSProperties = { width: 56, textAlign: "right", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--brand)", borderRadius: 4, padding: "4px 5px", fontSize: 12 };

  return (
    <div className="pag pag-media" style={{ padding: "20px 20px 44px" }}>
      <IrA esc={scnId} />
      <div style={{ textAlign: "center", marginBottom: 6 }}>
        <h1 style={{ fontSize: 32, fontWeight: 800, margin: 0 }}><span style={{ color: "var(--text-primary)" }}>{t("titlePrefix")}{" "}</span><span style={{ color: "var(--brand)" }}>Cash Flow</span></h1>
        <div style={{ fontSize: 13.5, color: "var(--text-secondary)", fontWeight: 600, marginTop: 4 }}>{t("subtitle")}</div>
      </div>

      <div style={{ display: "flex", gap: 12, justifyContent: "center", alignItems: "center", margin: "16px 0 20px", flexWrap: "wrap" }}>
        <select value={scnId} onChange={e => setScnId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select>
        <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 13, fontWeight: 700, color: "var(--text-primary)", cursor: "pointer" }}>
          <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /> {t("timingModelActive")}
        </label>
        <button onClick={save} disabled={saving || !scnId} style={{ padding: "7px 16px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: saving ? "default" : "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", opacity: saving ? 0.6 : 1 }}>{saving ? tc("saving") : t("saveCriteria")}</button>
        <button onClick={bajarExcel} disabled={loading || !scnId} title={t("excelTitle")}
          style={{ padding: "7px 16px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: loading ? "default" : "pointer", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)", opacity: loading ? 0.6 : 1 }}>⬇ Excel</button>
      </div>

      {msg && <div style={{ color: "var(--positive)", fontSize: 13, marginBottom: 8, textAlign: "center" }}>{msg}</div>}
      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8, textAlign: "center" }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13, textAlign: "center" }}>{tc("loading")}</div>}

      {!loading && (
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "flex-start" }}>
          {GROUPS.map(grp => (
            <div key={grp.titleKey} style={{ flex: "1 1 360px", background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, padding: "14px 18px" }}>
              <div style={{ fontSize: 11, fontWeight: 800, color: GOLD, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10 }}>{t(grp.titleKey)}</div>
              {grp.fields.map(f => (
                <div key={f.k} style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 10 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-primary)" }}>{t(f.labelKey)}</div>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.4 }}>{t(f.helpKey)}</div>
                  </div>
                  {f.bool ? (
                    <input type="checkbox" checked={params[f.k] !== false}
                      onChange={e => setParams(p => ({ ...p, [f.k]: e.target.checked }))}
                      style={{ width: 18, height: 18, marginTop: 2, cursor: "pointer" }} />
                  ) : (
                    <input className="mono" value={f.money ? numv(f.k) : (f.pct ? +(numv(f.k) * 100).toFixed(3) : numv(f.k))}
                      onChange={e => setField(f.k, e.target.value, f.pct)} style={inp} />
                  )}
                </div>
              ))}
            </div>
          ))}

          {/* Matriz de timing de cobro por mes */}
          <div style={{ flex: "1 1 100%", background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: GOLD, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>{t("timingMatrix")}</div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 10, lineHeight: 1.4 }}>{t.rich("matrixHelp", { b: (c: React.ReactNode) => <b>{c}</b>, i: (c: React.ReactNode) => <i>{c}</i> })}</div>
            <div style={{ maxHeight: 460, overflowY: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr>
                <th style={{ textAlign: "left", fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", padding: "4px 6px", position: "sticky", top: 0, background: "var(--bg-elevated)", zIndex: 1 }}>{t("stayMonth")}</th>
                {offsets.map(o => <th key={o} style={{ textAlign: "right", fontSize: 10, fontWeight: 800, color: o < 0 ? "var(--brand)" : o === 0 ? "var(--text-primary)" : "var(--text-secondary)", padding: "4px 6px" }}>{offLabel(o)}</th>)}
                <th style={{ textAlign: "right", fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", padding: "4px 6px" }}>Σ</th>
              </tr></thead>
              <tbody>
                {FILAS.map((f) => {
                  const row = f.clave === "timing_matrix" ? (matrix[f.idx] ?? []) : filaDe(f.clave, f.idx);
                  const sum = offsets.reduce((a, _o, ci) => a + (row[ci] ?? 0), 0);
                  const ok = Math.abs(sum - 1) < 0.005;
                  return (
                    <tr key={f.etiqueta} style={{
                      borderTop: "1px solid var(--border-subtle)",
                      background: f.vecino ? "var(--bg-base)" : undefined,
                      opacity: f.vecino && !f.aporta ? 0.45 : 1,
                    }}>
                      <td style={{ fontSize: 12, color: f.vecino ? "var(--text-secondary)" : "var(--text-primary)", padding: "3px 6px", fontWeight: f.vecino ? 400 : 600, whiteSpace: "nowrap" }}>
                        {f.etiqueta}
                        {f.vecino && !f.aporta && <span style={{ fontSize: 9.5, marginLeft: 6, opacity: 0.8 }}>{t("notThisYear")}</span>}
                      </td>
                      {offsets.map((o, ci) => (
                        <td key={o} style={{ textAlign: "right", padding: "2px 6px" }}>
                          <input className="mono" value={+(((row[ci] ?? 0) * 100).toFixed(1))}
                            onChange={e => f.clave === "timing_matrix"
                              ? setCell(f.idx, ci, e.target.value)
                              : setCellEn(f.clave, f.largo, f.idx, ci, e.target.value)}
                            style={{ ...fInp, border: `1px solid ${o < 0 ? "var(--brand)" : "var(--border-subtle)"}` }} />
                        </td>
                      ))}
                      <td className="mono" style={{ textAlign: "right", fontSize: 12, fontWeight: 700, color: ok ? "var(--positive)" : "var(--negative)", padding: "3px 6px" }}>{(sum * 100).toFixed(0)}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          </div>
        </div>
      )}

      {!loading && (
        <div style={{ marginTop: 16, display: "flex", justifyContent: "center" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "11px 20px", fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 900 }}>
            <span style={{ width: 22, height: 22, borderRadius: "50%", background: "var(--brand)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, flexShrink: 0 }}>i</span>
            <span style={{ lineHeight: 1.6 }}>
            {t.rich("activeModelNote", { b: (c: React.ReactNode) => <b>{c}</b> })}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
