"use client";
/**
 * Break-E → Resumen. Spec `FINPLAN_TAB_BREAK-E.md` §3.1.
 *
 * Tres bloques: el estado de resultados en costeo variable, el punto de
 * equilibrio, y el equilibrio expresado en métricas de habitación.
 *
 * ⚠️ **Dos rótulos de esta pantalla no son decoración y no se pueden quitar:**
 *
 * 1. El equilibrio mensual es un **prorrateo lineal**. En CWL la ocupación va de
 *    52% en febrero a **0,7% en septiembre**, así que un umbral plano de
 *    ~$333.000 al mes no describe **ningún** mes real. Se muestra porque el
 *    modelo de referencia lo trae, pero presentarlo como «el equilibrio del mes»
 *    sería falso. El cálculo mes a mes es Fase 2.
 * 2. Las métricas de habitación **suponen mezcla de ingresos constante** — el
 *    supuesto más fuerte del modelo.
 *
 * Y si el margen de contribución es ≤ 0 no se muestra un equilibrio en blanco ni
 * en cero: se muestra el motivo. Un cero ahí se lee como «no hay que vender
 * nada», que es exactamente lo contrario de lo que está pasando.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { getBeResultado, type BeResultado } from "@/lib/api";
import IrA from "@/components/IrA";
import { BarraContexto, useContextoBE, useVigencia, usd, pct } from "../_contexto";

const CARD: React.CSSProperties = {
  padding: 16, borderRadius: 10, background: "var(--bg-surface)",
  border: "1px solid var(--border-subtle)", minWidth: 260, flex: 1,
};
const FILA: React.CSSProperties = {
  display: "flex", justifyContent: "space-between", gap: 16,
  padding: "6px 0", fontSize: 14,
};
const NOTA: React.CSSProperties = {
  fontSize: 11.5, color: "var(--text-secondary)", lineHeight: 1.5, marginTop: 8,
};

export default function ResumenBE() {
  const t = useTranslations("breakEven");
  const RICH = { b: (c: React.ReactNode) => <b>{c}</b> };
  const [ctx, set, escenarios] = useContextoBE();
  const [d, setD] = useState<BeResultado | null>(null);
  const [err, setErr] = useState("");
  const [cargando, setCargando] = useState(false);

  const nuevaCarga = useVigencia();
  const cargar = useCallback(async () => {
    // `listo`, no `scenarioId`: con el tipo del escenario todavía sin saber, el
    // par que saldría es inventado y el backend lo rechaza. Ver `_contexto`.
    if (!ctx.listo) return;
    const vigente = nuevaCarga();
    setCargando(true); setErr("");
    try {
      const r = await getBeResultado(ctx.scenarioId, ctx.dataVersion, ctx.month);
      if (vigente()) setD(r);
    } catch (e) {
      if (vigente()) { setErr(String((e as Error).message || e)); setD(null); }
    } finally { if (vigente()) setCargando(false); }
  }, [ctx.listo, ctx.scenarioId, ctx.dataVersion, ctx.month, nuevaCarga]);
  useEffect(() => { void cargar(); }, [cargar]);

  const r = d?.resumen, eq = d?.equilibrio, hab = d?.habitaciones;
  const sinEquilibrio = d && eq?.be_revenue === null;

  return (
    <div className="pag pag-media" style={{ padding: "18px 22px" }}>
      <IrA esc={ctx.scenarioId} />
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>{t("resumenTitle")}</h1>
      <BarraContexto ctx={ctx} set={set} escenarios={escenarios} />

      {err && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 13,
          background: "rgba(192,57,43,.12)", border: "1px solid #c0392b", color: "#e06c5f" }}>
          {err}
        </div>
      )}
      {cargando && <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{t("calculando")}</div>}

      {d && (
        <>
          {/* ⚠️ El aviso es SOLO para lo que hay que decidir.
             *
             * Antes también anunciaba las «reglas sin movimiento» en el mismo
             * banner amarillo, y en el FORECAST April 2026 eso daba «376
             * regla(s) sin movimiento» — 376 de 612. Leído así parece que
             * faltara clasificar medio módulo, y no falta nada: una regla sin
             * movimiento es una cuenta que **este escenario no usa**, que es lo
             * normal cuando la semilla cubre los 22 departamentos y un
             * escenario mueve doce. Un aviso que salta siempre deja de ser un
             * aviso, y de paso le quita fuerza al que sí importa.
             *
             * El conteo sigue disponible, con el detalle cuenta por cuenta, en
             * `/break-e/sin-clasificar`, que es la pantalla que existe para eso. */}
          {d.sin_clasificar > 0 && (
            <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 13,
              background: "rgba(255,193,7,.10)", border: "1px solid #c9971b", color: "#d6a626" }}>
              {t.rich("defaultRuleWarn", { ...RICH, n: d.sin_clasificar })}{" "}
              <Link href="/break-e/sin-clasificar" style={{ color: "inherit" }}>
                {t("verYDecidir")}
              </Link>
            </div>
          )}

          <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
            <div style={CARD}>
              <h2 style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>
                {t("contributionStatement")}
              </h2>
              <div style={FILA}><span>{t("lineRevenue")}</span><b>{usd(r!.revenue)}</b></div>
              <div style={FILA}><span>{t("lineVariableCost")}</span><span>{usd(r!.variable_cost)}</span></div>
              <div style={{ ...FILA, borderTop: "1px solid var(--border-subtle)" }}>
                <span><b>{t("lineContributionMargin")}</b></span>
                <b>{usd(r!.contribution_margin)} · {pct(r!.cm_pct)}</b>
              </div>
              <div style={FILA}><span>{t("lineFixedCost")}</span><span>{usd(r!.fixed_cost)}</span></div>
              <div style={{ ...FILA, borderTop: "1px solid var(--border-subtle)" }}>
                <span><b>{t("lineEbt")}</b></span><b>{usd(r!.ebt)}</b>
              </div>
              <div style={FILA}>
                <span>{t("lineIncomeTax")}</span><span>{usd(r!.excluded_cost)}</span>
              </div>
              <div style={{ ...FILA, borderTop: "2px solid var(--border-medium)" }}>
                <span><b>{t("lineNet")}</b></span><b>{usd(r!.net)}</b>
              </div>
              <p style={NOTA}>
                {t.rich("taxOutOfFixedNote", RICH)}
              </p>
            </div>

            <div style={CARD}>
              <h2 style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>
                {t("breakEvenPoint")}
              </h2>
              {sinEquilibrio ? (
                <p style={{ fontSize: 13.5, color: "#e06c5f", lineHeight: 1.6 }}>
                  {d.motivo || t("sinEquilibrioCalculable")}
                </p>
              ) : (
                <>
                  <div style={FILA}>
                    <span>{t("beRevenueAnnual")}</span><b>{usd(eq!.be_revenue)}</b>
                  </div>
                  <div style={FILA}>
                    <span>{t("bePctOfBudget")}</span><span>{pct(eq!.be_pct_of_revenue)}</span>
                  </div>
                  <div style={FILA}>
                    <span>{t("marginOfSafety")}</span>
                    <span>{usd(eq!.margin_of_safety)} · {pct(eq!.margin_of_safety_pct)}</span>
                  </div>
                  <div style={FILA}>
                    <span>{t("operatingLeverage")}</span>
                    <b>{eq!.operating_leverage === null ? "—"
                        : `${eq!.operating_leverage.toFixed(1)}x`}</b>
                  </div>
                  {eq!.operating_leverage === null && eq!.operating_leverage_motivo && (
                    // Un guion sin explicación se lee como «falta el dato». Acá
                    // el dato no falta: no existe. Ver el motor.
                    <p style={{ ...NOTA, marginTop: 0 }}>
                      {eq!.operating_leverage_motivo}.
                    </p>
                  )}
                  <div style={{ ...FILA, opacity: .75 }}>
                    <span>{t("beMonthlyLinear")}</span>
                    <span>{usd(eq!.be_revenue_monthly_linear)}</span>
                  </div>
                  <p style={{ ...NOTA, color: "#d6a626" }}>
                    {t.rich("beMonthlyLinearWarn", RICH)}
                  </p>
                </>
              )}
            </div>

            <div style={CARD}>
              <h2 style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>
                {t("roomMetricsTitle")}
              </h2>
              {hab?.be_occupancy === null ? (
                <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                  {t("roomMetricsUnavailable")}
                </p>
              ) : (
                <>
                  <div style={FILA}>
                    <span>{t("beOccupancy")}</span><b>{pct(hab!.be_occupancy)}</b>
                  </div>
                  <div style={FILA}>
                    <span>{t("beRoomNights")}</span>
                    <span>{hab!.be_room_nights?.toLocaleString("en-US",
                      { maximumFractionDigits: 0 }) ?? "—"}</span>
                  </div>
                  <div style={FILA}>
                    <span>{t("beTrevpar")}</span><span>{usd(hab!.be_trevpar)}</span>
                  </div>
                  <div style={FILA}>
                    <span>{t("roomsMix")}</span><span>{pct(hab!.rooms_mix)}</span>
                  </div>
                </>
              )}
              <p style={NOTA}>
                {t.rich("constantMixNote", RICH)}
              </p>
            </div>
          </div>

          {/* ⚠️ Este pie decía, siempre, que ajustar «va a subir el equilibrio de
             * forma material». Medido contra los escenarios vivos, eso es falso
             * en general: con `BE = F·R/(R−V)`, pasar costo de variable a fijo
             * sube el equilibrio **solo si el resultado es positivo**. En el
             * `ACTUAL 2025`, que pierde plata, el mismo ajuste lo BAJA $925.541.
             * Por eso la frase ahora la decide el signo del EBT de la pantalla:
             * anunciar la dirección equivocada haría que un ajuste correcto se
             * leyera como una mejora. Ver `tests/test_break_even_direccion.py`. */}
          <p style={{ ...NOTA, marginTop: 16, maxWidth: 900 }}>
            {t.rich("seedNoteIntro", { ...RICH, i: (c: React.ReactNode) => <i>{c}</i> })}{" "}
            <Link href="/break-e/configuracion" style={{ color: "var(--brand)" }}>
              {t("configuracionLink")}
            </Link>{" "}
            {r!.ebt > 0 ? t.rich("seedNoteProfit", RICH) : t.rich("seedNoteLoss", RICH)}{" "}
            {t("seedNoteOutro")}
          </p>
        </>
      )}
    </div>
  );
}
