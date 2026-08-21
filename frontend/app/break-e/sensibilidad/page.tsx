"use client";
/**
 * Break-E → Sensibilidad (Fase 2). Spec `FINPLAN_TAB_BREAK-E.md` §3.3.
 *
 * Matriz ocupación × factor de ADR; cada celda es el resultado antes de
 * impuestos. Semáforo rojo–amarillo–verde con **el cero anclado en amarillo** —
 * que es lo que hace legible la matriz: lo que importa no es si una celda es
 * grande, sino de qué lado del cero cae.
 *
 * ⚠️ **Una matriz de 153 celdas se lee como una predicción y no lo es.** Hereda
 * tres supuestos que el backend manda escritos y que esta pantalla muestra
 * siempre: mezcla de ingresos constante, % de margen constante y costos fijos
 * constantes. Los tres se rompen justo en los extremos de la matriz, que es
 * donde más tienta mirarla.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { getBeSensibilidad, type BeSensibilidad } from "@/lib/api";
import { bajarCuadros } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import { BarraContexto, useContextoBE, useVigencia, usd } from "../_contexto";

const TD: React.CSSProperties = {
  padding: "5px 7px", fontSize: 12, textAlign: "right", whiteSpace: "nowrap",
};

/** Rojo → amarillo → verde, con el CERO anclado en el amarillo.
 *
 * ⚠️ Los umbrales son **absolutos** (±$500.000), no relativos al máximo y mínimo
 * de la matriz — es como está en el modelo de referencia, y con razón: si la
 * escala se normalizara por los extremos de cada corrida, **el mismo resultado
 * pintaría de color distinto según los rangos que el usuario elija**, y el
 * semáforo dejaría de significar nada entre una pantalla y otra.
 *
 * Lo que importa acá no es si una celda es grande: es de qué lado del cero cae. */
const TOPE = 500000;

function color(v: number | null): string {
  if (v === null) return "transparent";
  const t = Math.min(1, Math.abs(v) / TOPE);
  // Amarillo (#FFEB84) hacia rojo (#F8696B) o hacia verde (#63BE7B), igual que
  // la escala de tres colores del Excel.
  const [r2, g2, b2] = v >= 0 ? [99, 190, 123] : [248, 105, 107];
  const mez = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgba(${mez(255, r2)},${mez(235, g2)},${mez(132, b2)},0.55)`;
}

export default function SensibilidadBE() {
  const t = useTranslations("breakEven");
  const [ctx, set, escenarios] = useContextoBE();
  const [d, setD] = useState<BeSensibilidad | null>(null);
  const [err, setErr] = useState("");
  const [rangos, setRangos] = useState({
    occ_min: 0.20, occ_max: 0.60, occ_paso: 0.025,
    adr_min: 0.80, adr_max: 1.20, adr_paso: 0.05,
  });

  const nuevaCarga = useVigencia();
  const cargar = useCallback(async () => {
    // `listo`, no `scenarioId`: sin el tipo del escenario el par es inventado.
    // `vigente()` descarta la respuesta que llegue tarde. Ver `_contexto`.
    if (!ctx.listo) return;
    const vigente = nuevaCarga();
    setErr("");
    try {
      const r = await getBeSensibilidad(ctx.scenarioId, ctx.dataVersion, rangos);
      if (vigente()) setD(r);
    } catch (e) {
      if (vigente()) { setErr(String((e as Error).message || e)); setD(null); }
    }
  }, [ctx.listo, ctx.scenarioId, ctx.dataVersion, rangos, nuevaCarga]);
  useEffect(() => { void cargar(); }, [cargar]);

  async function bajar() {
    if (!d) return;
    await bajarCuadros("break_even_sensibilidad", [{
      titulo: t("sensXlsTitle"),
      subtitulo: `${ctx.dataVersion} · ${t("sensXlsSubtitle")}`,
      hoja: t("sensSheet"),
      columnas: [
        { label: t("occupancy"), ancho: 14, formato: "texto" },
        ...d.factores_adr.map(f => ({ label: `ADR ×${f.toFixed(2)}`,
                                      formato: "usd" as const })),
      ],
      filas: d.ocupaciones.map((o, i) => ({
        label: `${(o * 100).toFixed(1)}%`,
        valores: d.celdas[i],
      })),
    }]);
  }

  return (
    <div className="pag pag-ancha" style={{ padding: "18px 22px" }}>
      <IrA esc={ctx.scenarioId} />
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>{t("sensTitleScreen")}</h1>
      <BarraContexto ctx={ctx} set={set} escenarios={escenarios} />

      {err && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 13,
          background: "rgba(192,57,43,.12)", border: "1px solid #c0392b", color: "#e06c5f" }}>
          {err}
        </div>
      )}

      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
        marginBottom: 12, fontSize: 12 }}>
        {([["occ_min", "occMin"], ["occ_max", "occMax"], ["occ_paso", "occStep"],
           ["adr_min", "adrMin"], ["adr_max", "adrMax"], ["adr_paso", "adrStep"],
          ] as const).map(([k, lbl]) => (
          <label key={k} style={{ color: "var(--text-secondary)" }}>
            {t(lbl)}{" "}
            <input type="number" step={0.005} value={rangos[k]}
              onChange={e => setRangos(r => ({ ...r, [k]: Number(e.target.value) }))}
              style={{ width: 70, padding: "4px 6px", fontSize: 12.5, borderRadius: 5,
                border: "1px solid var(--border-subtle)", background: "var(--bg-input)",
                color: "var(--text-primary)" }} />
          </label>
        ))}
        <button onClick={() => void bajar()} style={{ padding: "7px 14px", borderRadius: 6,
          cursor: "pointer", fontSize: 13, border: "1px solid var(--border-medium)",
          background: "var(--bg-surface)", color: "var(--text-primary)" }}>⬇ Excel</button>
      </div>

      {d?.motivo && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 13,
          background: "rgba(255,193,7,.10)", border: "1px solid #c9971b", color: "#d6a626" }}>
          {d.motivo}
        </div>
      )}

      {d && !d.motivo && (
        <>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>
            {t.rich("sensIntro", {
              b: (c: React.ReactNode) => <b>{c}</b>,
              cm: `${(d.base.cm_pct * 100).toFixed(1)}%`,
              fijos: usd(d.base.fixed_cost),
              adr: usd(d.base.adr),
              mix: `${(d.base.rooms_mix * 100).toFixed(1)}%`,
              tope: usd(TOPE),
            })}
          </p>
          <div className="fin-scroll-x">
            <table className="fin-table" style={{ borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ ...TD, fontWeight: 700, textAlign: "left" }}>{t("occupancy")}</th>
                  {d.factores_adr.map(f => (
                    <th key={f} style={{ ...TD, fontWeight: 700 }}>
                      ADR ×{f.toFixed(2)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.ocupaciones.map((o, i) => (
                  <tr key={o}>
                    <td style={{ ...TD, fontWeight: 700, textAlign: "left" }}>
                      {(o * 100).toFixed(1)}%
                    </td>
                    {d.celdas[i].map((c, j) => {
                      const esPresup = d.celda_presupuesto?.[0] === i
                        && d.celda_presupuesto?.[1] === j;
                      return (
                        <td key={j} style={{
                          ...TD, background: color(c),
                          outline: esPresup ? "2px solid var(--brand)" : undefined,
                          fontWeight: esPresup ? 700 : 400,
                        }}
                          title={esPresup ? t("elPresupuesto") : undefined}>
                          {c === null ? "—"
                            : c.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: 16, padding: "12px 14px", borderRadius: 8, maxWidth: 900,
            background: "rgba(255,193,7,.07)", border: "1px solid rgba(201,151,27,.4)" }}>
            <b style={{ fontSize: 12.5, color: "#d6a626" }}>
              {t("sensPrediccionTitulo")}
            </b>
            <ul style={{ fontSize: 11.5, color: "var(--text-secondary)", lineHeight: 1.6,
              marginTop: 6, paddingLeft: 18 }}>
              {d.supuestos.map(s => <li key={s}>{s}</li>)}
            </ul>
            <p style={{ fontSize: 11.5, color: "var(--text-secondary)", lineHeight: 1.6,
              marginTop: 8, marginBottom: 0 }}>
              {t("sensPrediccionPie")}
            </p>
          </div>
        </>
      )}
    </div>
  );
}
