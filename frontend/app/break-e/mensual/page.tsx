"use client";
/**
 * Break-E → Equilibrio mensual (Fase 2). Spec §3.2 de `FINPLAN_BREAK_EVEN.md`.
 *
 * **Esto es lo que la Fase 2 vino a arreglar.** En la Fase 1 el equilibrio
 * mensual era `BE_anual / 12` — el MISMO umbral los doce meses, ~$333.036. En
 * CWL la ocupación va de 52% en febrero a **0,7% en septiembre** y el lodge
 * cierra en octubre: ese número plano no describía ningún mes real.
 *
 * ⚠️ **Dos cosas que la pantalla tiene que decir y no esconder:**
 *
 * 1. **Un mes puede no tener equilibrio.** En temporada baja el margen no cubre
 *    el costo fijo del mes a ningún volumen. Ese mes sale con su motivo, no con
 *    un cero — un cero diría «no hay que vender nada».
 * 2. **La suma de los doce NO es el equilibrio anual.** Un mes que no llega se
 *    compensa con otro que se pasa, y el anual reparte el costo fijo sobre el
 *    margen de todo el año.
 *
 * La estacionalidad sale del **P&L mensual de FinPlan**, no del Excel de
 * referencia: ese libro no tiene ni un dato mensual — se verificó buscando por
 * nombre de mes, por estructura (ningún bloque de 12 columnas) y por
 * encabezados (todo rotulado FY). Lo único que hay sobre estacionalidad ahí es
 * una frase suelta.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { getBeMensual, type BeMensual } from "@/lib/api";
import { bajarCuadros } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import { BarraContexto, useContextoBE, useVigencia, usd, pct } from "../_contexto";

const TD: React.CSSProperties = { padding: "6px 8px", fontSize: 13, textAlign: "right" };
const TH: React.CSSProperties = {
  textAlign: "right", padding: "7px 8px", fontSize: 11, fontWeight: 700,
  textTransform: "uppercase", letterSpacing: ".04em",
};

export default function MensualBE() {
  const t = useTranslations("breakEven");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MESES = tm.raw("short") as string[];
  const [ctx, set, escenarios] = useContextoBE();
  const [d, setD] = useState<BeMensual | null>(null);
  const [err, setErr] = useState("");
  const [cargando, setCargando] = useState(false);

  const nuevaCarga = useVigencia();
  const cargar = useCallback(async () => {
    // `listo`, no `scenarioId`: sin el tipo del escenario el par es inventado.
    // `vigente()` descarta la respuesta que llegue tarde. Ver `_contexto`.
    if (!ctx.listo) return;
    const vigente = nuevaCarga();
    setCargando(true); setErr("");
    try {
      const r = await getBeMensual(ctx.scenarioId, ctx.dataVersion);
      if (vigente()) setD(r);
    } catch (e) {
      if (vigente()) { setErr(String((e as Error).message || e)); setD(null); }
    } finally { if (vigente()) setCargando(false); }
  }, [ctx.listo, ctx.scenarioId, ctx.dataVersion, nuevaCarga]);
  useEffect(() => { void cargar(); }, [cargar]);

  async function bajar() {
    if (!d) return;
    await bajarCuadros("break_even_mensual", [{
      titulo: t("mensualTitle"),
      subtitulo: `${ctx.dataVersion} · ${t("conEstacionalidad")}`,
      hoja: t("mensualSheet"),
      columnas: [
        { label: tc("month"), ancho: 12, formato: "texto" },
        { label: t("colRevenue"), formato: "usd" }, { label: t("colVariableCost"), formato: "usd" },
        { label: t("colFixedCost"), formato: "usd" }, { label: t("colCmPct"), formato: "pct" },
        { label: t("colBeMes"), formato: "usd" }, { label: t("colHolgura"), formato: "usd" },
      ],
      filas: d.meses.map(m => ({
        label: MESES[m.month - 1],
        valores: [m.revenue, m.variable_cost, m.fixed_cost, m.cm_pct,
                  m.be_revenue, m.holgura],
      })),
    }]);
  }

  return (
    <div className="pag pag-media" style={{ padding: "18px 22px" }}>
      <IrA esc={ctx.scenarioId} />
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>{t("mensualTitleScreen")}</h1>
      <BarraContexto ctx={ctx} set={set} escenarios={escenarios} />

      {err && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 13,
          background: "rgba(192,57,43,.12)", border: "1px solid #c0392b", color: "#e06c5f" }}>
          {err}
        </div>
      )}
      {cargando && (
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {t("calculandoDoceMeses")}
        </div>
      )}

      {d && (
        <>
          <button onClick={() => void bajar()} style={{
            padding: "8px 16px", borderRadius: 6, cursor: "pointer", marginBottom: 12,
            fontSize: 13.5, fontWeight: 600, border: "1px solid var(--border-medium)",
            background: "var(--bg-surface)", color: "var(--text-primary)" }}>
            ⬇ Excel
          </button>

          <div className="fin-scroll-x">
            <table className="fin-table" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ ...TH, textAlign: "left" }}>{tc("month")}</th>
                  <th style={TH}>{t("colRevenue")}</th><th style={TH}>{t("colVariableCost")}</th>
                  <th style={TH}>{t("colFixedCost")}</th><th style={TH}>{t("colCmPct")}</th>
                  <th style={TH}>{t("colBeMes")}</th><th style={TH}>{t("colHolgura")}</th>
                </tr>
              </thead>
              <tbody>
                {d.meses.map(m => (
                  <tr key={m.month}>
                    <td style={{ ...TD, textAlign: "left", fontWeight: 600 }}>
                      {MESES[m.month - 1]}
                    </td>
                    <td style={TD}>{usd(m.revenue)}</td>
                    <td style={TD}>{usd(m.variable_cost)}</td>
                    <td style={TD}>{usd(m.fixed_cost)}</td>
                    <td style={TD}>{pct(m.cm_pct)}</td>
                    <td style={TD} title={m.motivo || undefined}>
                      {m.be_revenue === null
                        ? <span style={{ color: "#d6a626" }}>{t("sinEquilibrio")}</span>
                        : usd(m.be_revenue)}
                    </td>
                    <td style={{
                      ...TD, fontWeight: 600,
                      color: m.holgura === null ? "var(--text-secondary)"
                        : m.holgura >= 0 ? "#1fa363" : "#e06c5f",
                    }}>
                      {m.holgura === null ? "—" : usd(m.holgura)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: 16, padding: "12px 14px", borderRadius: 8, maxWidth: 900,
            background: "rgba(255,193,7,.07)", border: "1px solid rgba(201,151,27,.4)" }}>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6,
              margin: 0 }}>
              ⚠ {d.nota}
            </p>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6,
              marginTop: 8, marginBottom: 0 }}>
              {t.rich("sinEquilibrioNote", { b: (c: React.ReactNode) => <b>{c}</b> })}
            </p>
          </div>
        </>
      )}
    </div>
  );
}
