"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import RecalcButton from "@/components/RecalcButton";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import {
  getScenarios, getPLMonthly, getPLManualInputs, savePLManualInput,
  type Scenario,
} from "@/lib/api";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

function fmtUsd(n: number) {
  if (!n) return "—";
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${s})` : s;
}

export default function ManagementFeesPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("mgmtFees");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [revByMonth, setRevByMonth] = useState<number[]>(Array(12).fill(0));
  const [pct3, setPct3] = useState<number[]>(Array(12).fill(0));   // % (0..100)
  const [pct5, setPct5] = useState<number[]>(Array(12).fill(0));
  const [pctReserve, setPctReserve] = useState<number[]>(Array(12).fill(0));
  const [taxRate, setTaxRate] = useState(30);   // impuesto de renta % (0..100)
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(null), 4000); };

  const load = useCallback(async (sid: string) => {
    const [pl, manual] = await Promise.all([getPLMonthly(sid), getPLManualInputs(sid)]);
    // Revenue base per month from the P&L
    const rev = Array(12).fill(0);
    for (const m of pl.months) {
      const r = m.lines.find(l => l.line_code === "TOTAL_REVENUES");
      rev[m.month - 1] = r ? r.amount_usd : 0;
    }
    setRevByMonth(rev);
    const p3 = Array(12).fill(0), p5 = Array(12).fill(0), pr = Array(12).fill(0);
    for (const mi of manual) {
      p3[mi.month - 1] = parseFloat(mi.mgmt_fee_pct_3 || "0") * 100;
      p5[mi.month - 1] = parseFloat(mi.mgmt_fee_pct_5 || "0") * 100;
      pr[mi.month - 1] = parseFloat(mi.capital_reserve_pct || "0") * 100;
    }
    setPct3(p3); setPct5(p5); setPctReserve(pr);
    // impuesto de renta: tasa única; tomar la primera fila o default 30%
    setTaxRate(manual.length ? parseFloat(manual[0].income_tax_rate || "0.30") * 100 : 30);
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
        const sc = elegir(all, "budget") ?? all[0];
        if (!sc) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarioId(sharedScenarioOr(sc.id));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Error");
      } finally { setLoading(false); }
    })();
  }, []);

  useEffect(() => {
    if (!scenarioId) return;
    setLoading(true);
    load(scenarioId).catch(e => setError(e instanceof Error ? e.message : tc("error"))).finally(() => setLoading(false));
  }, [scenarioId, load]);

  function applyAll(which: 3 | 5 | 0, value: number) {
    if (which === 3) setPct3(Array(12).fill(value));
    else if (which === 5) setPct5(Array(12).fill(value));
    else setPctReserve(Array(12).fill(value));
  }

  async function saveAll() {
    if (!scenarioId) return;
    setSaving(true);
    try {
      for (let m = 1; m <= 12; m++) {
        await savePLManualInput(scenarioId, m, {
          mgmt_fee_pct_3: String((pct3[m - 1] || 0) / 100),
          mgmt_fee_pct_5: String((pct5[m - 1] || 0) / 100),
          capital_reserve_pct: String((pctReserve[m - 1] || 0) / 100),
          income_tax_rate: String((taxRate || 0) / 100),
        });
      }
      await load(scenarioId);
      flash(t("saved"));
    } catch (e) {
      flash(e instanceof Error ? e.message : t("errorSaving"));
    } finally { setSaving(false); }
  }

  const fee3 = (i: number) => revByMonth[i] * (pct3[i] || 0) / 100;
  const fee5 = (i: number) => revByMonth[i] * (pct5[i] || 0) / 100;
  const feeRes = (i: number) => revByMonth[i] * (pctReserve[i] || 0) / 100;
  const totalRev = revByMonth.reduce((s, v) => s + v, 0);
  const totalFee3 = revByMonth.reduce((s, v, i) => s + fee3(i), 0);
  const totalFee5 = revByMonth.reduce((s, v, i) => s + fee5(i), 0);
  const totalRes = revByMonth.reduce((s, v, i) => s + feeRes(i), 0);

  async function bajarExcel() {
    setError(null);
    // Los % viajan como FRACCIÓN (0.03), no como 3: en pantalla se digita 3
    // porque es más cómodo, pero un Excel con "3" en una celda de porcentaje
    // multiplica por cien al primer cálculo que alguien le encime.
    const filas: FilaCuadro[] = [
      { label: t("totalRevenue"), valores: [...revByMonth, totalRev] },
      { label: "Mgmt Fee %", nivel: 1, formato: "pct",
        valores: [...pct3.map(v => (v || 0) / 100), null] },
      { label: "Mgmt Fee $", nivel: 1, valores: [...revByMonth.map((_v, i) => fee3(i)), totalFee3] },
      { label: "Royalties %", nivel: 1, formato: "pct",
        valores: [...pct5.map(v => (v || 0) / 100), null] },
      { label: "Royalties $", nivel: 1, valores: [...revByMonth.map((_v, i) => fee5(i)), totalFee5] },
      { label: "Total Management Fees", es_total: true,
        valores: [...revByMonth.map((_v, i) => fee3(i) + fee5(i)), totalFee3 + totalFee5] },
      { label: "Capital Reserve %", nivel: 1, formato: "pct",
        valores: [...pctReserve.map(v => (v || 0) / 100), null] },
      { label: "Capital Reserve $", nivel: 1,
        valores: [...revByMonth.map((_v, i) => feeRes(i)), totalRes] },
      // La tasa de renta es una sola para todo el año: va en la columna anual.
      { label: t("incomeTaxXls"), formato: "pct",
        valores: [...Array(12).fill(null), (taxRate || 0) / 100] },
    ];
    const sc = scenarios.find(s => s.id === scenarioId);
    try {
      await bajarCuadros("Management_Fees", [{
        titulo: "Management Fees",
        subtitulo: `${t("subtitleShort")} · ${sc ? `${sc.type} ${sc.version} ${sc.year}` : ""} · USD`,
        hoja: "Management Fees",
        columnas: [
          { label: "Concepto", ancho: 34, formato: "texto" },
          ...MONTHS.map(m => ({ label: m, ancho: 13, formato: "usd" as const })),
          { label: "Anual", ancho: 15, formato: "usd" as const },
        ],
        filas,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  const numInp: React.CSSProperties = {
    width: 56, textAlign: "right", background: "var(--bg-input)", color: "var(--brand)",
    border: "1px solid var(--border-medium)", borderRadius: 3, fontSize: 11, padding: "2px 4px",
  };

  return (
    <div className="pag pag-ancha">
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>
            Management Fees
          </h2>
          <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)" }}>
            {t("subtitle")}
          </p>
        </div>
        <select value={scenarioId ?? ""} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 200 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>)}
        </select>
        <RecalcButton scenarioId={scenarioId} />
        <button onClick={bajarExcel} disabled={loading || !scenarioId}
          title={t("excelHint")}
          style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer",
            background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
        <button onClick={saveAll} disabled={saving || !scenarioId}
          style={{ marginLeft: "auto", padding: "6px 16px", fontSize: 12, borderRadius: 4, fontWeight: 600,
            background: saving ? "var(--bg-elevated)" : "var(--brand)", color: "#fff", border: "none",
            cursor: saving ? "default" : "pointer" }}>
          {saving ? tc("saving") : tc("save")}
        </button>
      </div>

      {msg && (
        <div style={{ marginBottom: 12, padding: "8px 14px", borderRadius: 4, fontSize: 12,
          background: "rgba(38,166,154,0.12)", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          {msg}
        </div>
      )}
      {loading && <p style={{ color: "var(--text-secondary)" }}>{tc("loading")}</p>}
      {error && <div style={{ color: "var(--negative)" }}>⚠ {error}</div>}

      {!loading && !error && (
        <>
          {/* Quick "apply to all" */}
          <div style={{ display: "flex", gap: 20, marginBottom: 14, flexWrap: "wrap" }}>
            <ApplyAll label={t("applyMgmtFee")} onApply={v => applyAll(3, v)} />
            <ApplyAll label={t("applyRoyalties")} onApply={v => applyAll(5, v)} />
            <ApplyAll label={t("applyCapitalReserve")} onApply={v => applyAll(0, v)} />
          </div>

          {/* Impuesto de renta: tasa única sobre el EBT */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, padding: "8px 12px", borderRadius: 6, background: "var(--bg-elevated)", width: "fit-content" }}>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("incomeTaxPct")}</span>
            <input type="number" value={taxRate} onChange={e => setTaxRate(Number(e.target.value))}
              style={{ width: 64, textAlign: "right", background: "var(--bg-input)", color: "var(--brand)",
                border: "1px solid var(--border-medium)", borderRadius: 3, fontSize: 12, padding: "3px 6px" }} />
          </div>

          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 760 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", width: 140 }}>{tc("concept")}</th>
                  {MONTHS.map(m => <th key={m} style={{ textAlign: "right" }}>{m}</th>)}
                  <th style={{ textAlign: "right", color: "var(--brand)" }}>{tc("annual")}</th>
                </tr>
              </thead>
              <tbody>
                {/* Revenue base */}
                <tr style={{ background: "var(--bg-elevated)" }}>
                  <td style={{ color: "var(--text-secondary)", fontStyle: "italic", fontSize: 11 }}>{t("totalRevenue")}</td>
                  {revByMonth.map((v, i) => (
                    <td key={i} className="mono" style={{ textAlign: "right", fontSize: 11, color: "var(--text-secondary)" }}>{fmtUsd(v)}</td>
                  ))}
                  <td className="mono" style={{ textAlign: "right", fontSize: 11, color: "var(--text-secondary)" }}>{fmtUsd(totalRev)}</td>
                </tr>

                {/* Mgmt fee % row */}
                <tr>
                  <td style={{ color: "var(--text-primary)" }}>Mgmt Fee %</td>
                  {pct3.map((v, i) => (
                    <td key={i} style={{ textAlign: "right" }}>
                      <input type="number" value={v} style={numInp}
                        onChange={e => setPct3(p => p.map((x, j) => j === i ? Number(e.target.value) : x))} />
                    </td>
                  ))}
                  <td></td>
                </tr>
                {/* Mgmt fee $ */}
                <tr>
                  <td style={{ color: "var(--text-secondary)", paddingLeft: 16 }}>Mgmt Fee $</td>
                  {revByMonth.map((_, i) => (
                    <td key={i} className="mono" style={{ textAlign: "right", color: "var(--positive)" }}>{fmtUsd(fee3(i))}</td>
                  ))}
                  <td className="mono" style={{ textAlign: "right", fontWeight: 600, color: "var(--positive)" }}>{fmtUsd(totalFee3)}</td>
                </tr>

                {/* Royalty % row */}
                <tr>
                  <td style={{ color: "var(--text-primary)" }}>Royalties %</td>
                  {pct5.map((v, i) => (
                    <td key={i} style={{ textAlign: "right" }}>
                      <input type="number" value={v} style={numInp}
                        onChange={e => setPct5(p => p.map((x, j) => j === i ? Number(e.target.value) : x))} />
                    </td>
                  ))}
                  <td></td>
                </tr>
                {/* Royalty $ */}
                <tr>
                  <td style={{ color: "var(--text-secondary)", paddingLeft: 16 }}>Royalties $</td>
                  {revByMonth.map((_, i) => (
                    <td key={i} className="mono" style={{ textAlign: "right", color: "var(--positive)" }}>{fmtUsd(fee5(i))}</td>
                  ))}
                  <td className="mono" style={{ textAlign: "right", fontWeight: 600, color: "var(--positive)" }}>{fmtUsd(totalFee5)}</td>
                </tr>

                {/* Total management fees (Owners Fee 8005) */}
                <tr className="total">
                  <td style={{ fontWeight: 700, color: "var(--text-primary)" }}>Total Management Fees</td>
                  {revByMonth.map((_, i) => (
                    <td key={i} className="mono" style={{ textAlign: "right", fontWeight: 700 }}>{fmtUsd(fee3(i) + fee5(i))}</td>
                  ))}
                  <td className="mono" style={{ textAlign: "right", fontWeight: 700, color: "var(--positive)" }}>{fmtUsd(totalFee3 + totalFee5)}</td>
                </tr>

                {/* Capital Reserve (8020) — also % of revenue */}
                <tr>
                  <td style={{ color: "var(--text-primary)", paddingTop: 12 }}>Capital Reserve %</td>
                  {pctReserve.map((v, i) => (
                    <td key={i} style={{ textAlign: "right" }}>
                      <input type="number" value={v} style={numInp}
                        onChange={e => setPctReserve(p => p.map((x, j) => j === i ? Number(e.target.value) : x))} />
                    </td>
                  ))}
                  <td></td>
                </tr>
                <tr>
                  <td style={{ color: "var(--text-secondary)", paddingLeft: 16 }}>Capital Reserve $</td>
                  {revByMonth.map((_, i) => (
                    <td key={i} className="mono" style={{ textAlign: "right", color: "var(--positive)" }}>{fmtUsd(feeRes(i))}</td>
                  ))}
                  <td className="mono" style={{ textAlign: "right", fontWeight: 600, color: "var(--positive)" }}>{fmtUsd(totalRes)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function ApplyAll({ label, onApply }: { label: string; onApply: (v: number) => void }) {
  const t = useTranslations("mgmtFees");
  const [v, setV] = useState(3);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{label}:</span>
      <input type="number" value={v} onChange={e => setV(Number(e.target.value))}
        style={{ width: 56, textAlign: "right", background: "var(--bg-input)", color: "var(--text-primary)",
          border: "1px solid var(--border-medium)", borderRadius: 3, fontSize: 12, padding: "3px 6px" }} />
      <button onClick={() => onApply(v)}
        style={{ padding: "3px 10px", fontSize: 11, borderRadius: 3, cursor: "pointer",
          background: "var(--bg-surface)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
        {t("apply")}
      </button>
    </div>
  );
}
