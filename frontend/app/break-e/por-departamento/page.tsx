"use client";
/**
 * Break-E → Por Departamento. Spec `FINPLAN_TAB_BREAK-E.md` §3.2.
 *
 * Los que generan ingreso arriba con subtotal; los **no distribuidos** en un
 * bloque aparte y **sin columnas de ingreso ni % MC** — que es el punto de la
 * pantalla: un centro de costo no tiene margen de contribución, y mostrarle un
 * `0%` haría pensar que aporta cero margen en vez de que no aplica.
 *
 * La bandera sale de `be_department.generates_revenue`, no de una lista en el
 * código: hay 8 departamentos esperando activarse.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { getBeDeptos, getBeResultado, type BeDepto, type BeResultado } from "@/lib/api";
import { bajarCuadros } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import { BarraContexto, useContextoBE, useVigencia, usd, pct } from "../_contexto";

const TH: React.CSSProperties = {
  textAlign: "right", padding: "7px 8px", fontSize: 11, fontWeight: 700,
  textTransform: "uppercase", letterSpacing: ".04em",
};
const TD: React.CSSProperties = { padding: "6px 8px", fontSize: 13, textAlign: "right" };
const IZQ: React.CSSProperties = { ...TD, textAlign: "left" };

export default function PorDepartamento() {
  const t = useTranslations("breakEven");
  const tc = useTranslations("common");
  const [ctx, set, escenarios] = useContextoBE();
  const [d, setD] = useState<BeResultado | null>(null);
  const [deptos, setDeptos] = useState<BeDepto[]>([]);
  const [err, setErr] = useState("");

  const nuevaCarga = useVigencia();
  const cargar = useCallback(async () => {
    // `listo`, no `scenarioId`: sin el tipo del escenario el par es inventado.
    // `vigente()` descarta la respuesta que llegue tarde. Ver `_contexto`.
    if (!ctx.listo) return;
    const vigente = nuevaCarga();
    setErr("");
    try {
      const [res, cat] = await Promise.all([
        getBeResultado(ctx.scenarioId, ctx.dataVersion, ctx.month), getBeDeptos()]);
      if (vigente()) { setD(res); setDeptos(cat.departamentos); }
    } catch (e) { if (vigente()) setErr(String((e as Error).message || e)); }
  }, [ctx.listo, ctx.scenarioId, ctx.dataVersion, ctx.month, nuevaCarga]);
  useEffect(() => { void cargar(); }, [cargar]);

  const meta = Object.fromEntries(deptos.map(x => [x.slug, x]));
  const filas = d?.por_departamento ?? [];
  const operativos = filas.filter(f => meta[f.slug]?.generates_revenue);
  const noDistribuidos = filas.filter(f => !meta[f.slug]?.generates_revenue);
  const sum = (xs: typeof filas, k: "total_cost" | "variable_cost" | "fixed_cost" | "revenue") =>
    xs.reduce((a, x) => a + (x[k] || 0), 0);

  async function bajar() {
    if (!d) return;
    await bajarCuadros("break_even_por_departamento", [{
      titulo: t("porDeptoTitle"),
      subtitulo: `${d.data_version} · ${ctx.month ? t("mesN", { n: ctx.month }) : t("fullYear")}`,
      hoja: t("porDeptoSheet"),
      columnas: [
        { label: tc("department"), ancho: 26, formato: "texto" },
        { label: t("colRevenue"), formato: "usd" }, { label: t("colVariableCost"), formato: "usd" },
        { label: t("colContributionMargin"), formato: "usd" }, { label: t("colCmPct"), formato: "pct" },
        { label: t("colDirectFixedCost"), formato: "usd" }, { label: t("colTotalCost"), formato: "usd" },
      ],
      filas: filas.map(f => ({
        label: meta[f.slug]?.name || f.slug,
        valores: [f.revenue, f.variable_cost, f.contribution_margin,
                  f.cm_pct, f.fixed_cost, f.total_cost],
      })),
    }]);
  }

  return (
    <div className="pag pag-media" style={{ padding: "18px 22px" }}>
      <IrA esc={ctx.scenarioId} />
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>{t("porDeptoTitleScreen")}</h1>
      <BarraContexto ctx={ctx} set={set} escenarios={escenarios} />

      {err && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 13,
          background: "rgba(192,57,43,.12)", border: "1px solid #c0392b", color: "#e06c5f" }}>
          {err}
        </div>
      )}

      <button onClick={() => void bajar()} style={{
        padding: "8px 16px", borderRadius: 6, cursor: "pointer", marginBottom: 12,
        border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
        color: "var(--text-primary)", fontSize: 13.5, fontWeight: 600 }}>
        ⬇ Excel
      </button>

      {d && (
        <div className="fin-scroll-x">
          <table className="fin-table" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ ...TH, textAlign: "left" }}>{tc("department")}</th>
                <th style={TH}>{t("colRevenue")}</th><th style={TH}>{t("colVariableCost")}</th>
                <th style={TH}>{t("colContributionMarginShort")}</th><th style={TH}>{t("colCmPct")}</th>
                <th style={TH}>{t("colFixedCost")}</th><th style={TH}>{t("colTotalCost")}</th>
              </tr>
            </thead>
            <tbody>
              {operativos.map(f => (
                <tr key={f.slug}>
                  <td style={IZQ}>
                    <Link href={`/break-e/configuracion/${f.slug}`}
                      style={{ color: "var(--brand)" }}>
                      {meta[f.slug]?.name || f.slug}
                    </Link>
                  </td>
                  <td style={TD}>{usd(f.revenue)}</td>
                  <td style={TD}>{usd(f.variable_cost)}</td>
                  <td style={TD}>{usd(f.contribution_margin)}</td>
                  <td style={TD}>{pct(f.cm_pct)}</td>
                  <td style={TD}>{usd(f.fixed_cost)}</td>
                  <td style={TD}>{usd(f.total_cost)}</td>
                </tr>
              ))}
              <tr style={{ fontWeight: 700, borderTop: "1px solid var(--border-medium)" }}>
                <td style={IZQ}>{t("subtotalOperativos")}</td>
                <td style={TD}>{usd(sum(operativos, "revenue"))}</td>
                <td style={TD}>{usd(sum(operativos, "variable_cost"))}</td>
                <td style={TD}>—</td><td style={TD}>—</td>
                <td style={TD}>{usd(sum(operativos, "fixed_cost"))}</td>
                <td style={TD}>{usd(sum(operativos, "total_cost"))}</td>
              </tr>

              <tr>
                <td colSpan={7} style={{ ...IZQ, paddingTop: 16, fontSize: 12,
                  color: "var(--text-secondary)" }}>
                  {t.rich("noDistribuidosNote", { b: (c: React.ReactNode) => <b>{c}</b> })}
                </td>
              </tr>
              {noDistribuidos.map(f => (
                <tr key={f.slug}>
                  <td style={IZQ}>
                    <Link href={`/break-e/configuracion/${f.slug}`}
                      style={{ color: "var(--brand)" }}>
                      {meta[f.slug]?.name || f.slug}
                    </Link>
                  </td>
                  <td style={{ ...TD, color: "var(--text-secondary)" }}>—</td>
                  <td style={TD}>{usd(f.variable_cost)}</td>
                  <td style={{ ...TD, color: "var(--text-secondary)" }}>—</td>
                  <td style={{ ...TD, color: "var(--text-secondary)" }}>—</td>
                  <td style={TD}>{usd(f.fixed_cost)}</td>
                  <td style={TD}>{usd(f.total_cost)}</td>
                </tr>
              ))}
              <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border-medium)" }}>
                <td style={IZQ}>{tc("total")}</td>
                <td style={TD}>{usd(sum(filas, "revenue"))}</td>
                <td style={TD}>{usd(sum(filas, "variable_cost"))}</td>
                <td style={TD}>—</td><td style={TD}>—</td>
                <td style={TD}>{usd(sum(filas, "fixed_cost"))}</td>
                <td style={TD}>{usd(sum(filas, "total_cost"))}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 14,
        maxWidth: 900, lineHeight: 1.6 }}>
        {t.rich("ingresoSinDeptoNote", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>
    </div>
  );
}
