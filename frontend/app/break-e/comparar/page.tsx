"use client";
/**
 * Break-E → Comparar. **Cuatro versiones a la vez, en NOCHES.**
 *
 * Owner, 2026-08-17, con una captura de su hoja: *«que se puedan comparar 4
 * versiones a la vez, mes, YTD o full year, que todo esté ahí, solo escoger la
 * mezcla… ahí mismo la validación de ese costo con todas las variables»*.
 *
 * ## Por qué esta pantalla es en noches y no en ingreso
 *
 *     noches_equilibrio = costo_fijo / (ingreso_por_noche − costo_var_por_noche)
 *
 * Es la fórmula de su hoja, verificada celda por celda contra la captura (junio
 * Actual 2025: $821,07 − $864,57 = −$43,50 → **−4.694,81 noches**, −521,65% de
 * ocupación, varianza 4.797). Y resulta ser **la mejor de las dos**: da la misma
 * identidad que `FC / CM%`, pero **no necesita el supuesto de mezcla constante**
 * que sí necesita derivar noches desde el ingreso de equilibrio vía el ADR.
 *
 * ## ⚠️ Las noches de equilibrio NEGATIVAS no son un error
 *
 * Cuando el costo variable por noche supera al ingreso por noche, **cada noche
 * vendida pierde plata**: no hay volumen que alcance, y por eso el número sale
 * negativo. En el junio real de CWL pasa. Esconderlo detrás de un guion sería
 * tapar el dato más importante de ese mes, así que se muestra con su aviso.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { getBeComparar, getScenarios, type BeComparar, type Scenario } from "@/lib/api";
import { bajarCuadros } from "@/lib/exportCuadro";
import { HOTEL_ID } from "@/lib/hotel";
import { elegir } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";
import { SEL, ROTULO, CAMPO, BARRA } from "../_contexto";

const TD: React.CSSProperties = { padding: "5px 10px", fontSize: 13, textAlign: "right" };
const IZQ: React.CSSProperties = { ...TD, textAlign: "left", whiteSpace: "nowrap" };
const BANDA: React.CSSProperties = {
  ...IZQ, fontWeight: 700, fontSize: 12, textTransform: "uppercase",
  letterSpacing: ".04em", paddingTop: 14,
};

const usd = (v: number | null | undefined, dec = 2) =>
  v === null || v === undefined ? "—"
    : v.toLocaleString("en-US", { style: "currency", currency: "USD",
                                  minimumFractionDigits: dec, maximumFractionDigits: dec });
const num = (v: number | null | undefined, dec = 2) =>
  v === null || v === undefined ? "—"
    : v.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
const pc = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(2)}%`;

export default function CompararBE() {
  const t = useTranslations("breakEven");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MESES = tm.raw("short") as string[];
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  const [sel, setSel] = useState<string[]>(["", "", "", ""]);
  const [modo, setModo] = useState<"mes" | "ytd" | "full">("full");
  const [month, setMonth] = useState(6);
  const [d, setD] = useState<BeComparar | null>(null);
  const [err, setErr] = useState("");
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    getScenarios(HOTEL_ID).then(xs => {
      setEscenarios(xs);
      // ⚠️ Las CUATRO casillas son exactamente los cuatro escenarios que pidió
      // el owner (2026-08-17): «dejame Budget 2027 Working, Forecast 2026
      // Working, Actual 2026 y Actual 2025».
      //
      // Antes esto ordenaba por año descendente y elegía «los más nuevos», así
      // que abría en **Working 2035 y 2034** — que están VACÍOS, y por eso el
      // aviso de «no tiene estadística de habitaciones cargada» salía siempre.
      // Es el mismo defecto del «año más nuevo» que la regla compartida vino a
      // matar; sobrevivió acá porque esta pantalla está exenta de
      // `useEscenarioDe` (elige cuatro a la vez, no uno) y nadie miró que su
      // criterio propio fuera el viejo.
      //
      // No usa `useEscenarioDe` pero sí `elegir()`, que es donde vive la regla.
      setSel([
        elegir(xs, "budget")?.id ?? "",
        elegir(xs, "forecast")?.id ?? "",
        elegir(xs, "actual")?.id ?? "",
        elegir(xs, "actualAnterior")?.id ?? "",
      ]);
    }).catch(() => { /* lo dice el fetch de datos */ });
  }, []);

  const cargar = useCallback(async () => {
    const ids = sel.filter(Boolean);
    if (!ids.length) return;
    setCargando(true); setErr("");
    try { setD(await getBeComparar(ids, modo, month)); }
    catch (e) { setErr(String((e as Error).message || e)); setD(null); }
    finally { setCargando(false); }
  }, [sel, modo, month]);
  useEffect(() => { void cargar(); }, [cargar]);

  const V = d?.versiones ?? [];

  /** Una fila del cuadro. `fmt` decide cómo se ve cada celda. */
  function Fila({ label, campo, fmt = usd, resalta = false, nota }: {
    label: string; campo: keyof BeComparar["versiones"][number];
    fmt?: (v: number | null | undefined) => string; resalta?: boolean; nota?: string;
  }) {
    return (
      <tr style={resalta ? { fontWeight: 700,
        borderTop: "1px solid var(--border-medium)",
        borderBottom: "1px solid var(--border-medium)" } : undefined}>
        <td style={IZQ} title={nota}>{label}{nota && " *"}</td>
        {V.map(v => {
          const x = v[campo] as number | null;
          const negativo = typeof x === "number" && x < 0;
          return (
            <td key={v.scenario_id} style={{
              ...TD, color: negativo ? "#e06c5f" : undefined,
            }}>{fmt(x)}</td>
          );
        })}
      </tr>
    );
  }

  async function bajar() {
    if (!d) return;
    const filas: { label: string; valores: (number | null)[] }[] = [
      ["Total available Rooms", "nights_available"],
      ["Total Rooms Occupied", "nights_occupied"],
      ["% Occupancy", "occupancy_pct"],
      ["Average Daily Rate", "adr"],
      ["Variable", "variable"],
      ["Fixed Cost", "fixed"],
      ["Total Cost", "total_cost"],
      ["Average Expense per month", "average_expense_per_month"],
      ["Total Revenue Hotel by Occ. Room", "revenue_per_night"],
      ["Variable Cost per Night", "variable_cost_per_night"],
      ["Contribution per Night", "contribution_per_night"],
      ["Break Even Point in Nights", "be_nights"],
      ["%%% Occ. Rooms", "be_occupancy_pct"],
      ["Variance in Nights", "variance_nights"],
    ].map(([label, campo]) => ({
      label: label as string,
      valores: d.versiones.map(v => v[campo as keyof typeof v] as number | null),
    }));
    await bajarCuadros("break_even_comparacion", [{
      titulo: "Break Even Point in Room Nights",
      subtitulo: `${d.modo === "full" ? t("fullYear")
        : d.modo === "ytd" ? `YTD ${MESES[d.month - 1]}` : MESES[d.month - 1]}`,
      hoja: t("compararSheet"),
      columnas: [
        { label: tc("concept"), ancho: 34, formato: "texto" },
        ...d.versiones.map(v => ({ label: v.nombre, formato: "usd" as const })),
      ],
      filas,
    }]);
  }

  return (
    <div className="pag pag-media" style={{ padding: "18px 22px" }}>
      <IrA />
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>Break Even Point in Room Nights</h1>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 950,
        margin: "4px 0 14px" }}>
        {t.rich("compararIntro", {
          b: (c: React.ReactNode) => <b>{c}</b>,
          code: (c: React.ReactNode) => <code>{c}</code>,
        })}
      </p>

      {/* Misma barra que el resto del tab (`BARRA`/`ROTULO`/`SEL` salen de
          `_contexto`). Acá no se puede usar `BarraContexto` porque se eligen
          CUATRO escenarios, pero tiene que verse idéntica: si cada pantalla
          arma su propia barra, el tab deja de sentirse como un tab. */}
      <div style={BARRA}>
        {sel.map((id, i) => (
          <div key={i} style={{ ...CAMPO, flex: "1 1 190px", maxWidth: 260 }}>
            <label htmlFor={`be-cmp-${i}`} style={ROTULO}>{t("versionN", { n: i + 1 })}</label>
            <select id={`be-cmp-${i}`} className="fin-input"
              style={{ ...SEL, width: "100%", fontWeight: id ? 600 : 400,
                       color: id ? "var(--text-primary)" : "var(--text-secondary)" }}
              value={id}
              onChange={e => setSel(s => s.map((x, j) => j === i ? e.target.value : x))}>
              <option value="">{t("vacio")}</option>
              {escenarios.map(s => (
                <option key={s.id} value={s.id}>{s.type} · {s.version} · {s.year}</option>
              ))}
            </select>
          </div>
        ))}

        <div style={CAMPO}>
          <label htmlFor="be-cmp-modo" style={ROTULO}>{t("period")}</label>
          <select id="be-cmp-modo" className="fin-input" style={{ ...SEL, minWidth: 150 }}
            value={modo} onChange={e => setModo(e.target.value as typeof modo)}>
            <option value="mes">{tc("month")}</option>
            <option value="ytd">YTD</option>
            <option value="full">{t("fullYear")}</option>
          </select>
        </div>

        {modo !== "full" && (
          <div style={CAMPO}>
            <label htmlFor="be-cmp-mes" style={ROTULO}>{tc("month")}</label>
            <select id="be-cmp-mes" className="fin-input" style={{ ...SEL, minWidth: 140 }}
              value={month} onChange={e => setMonth(Number(e.target.value))}>
              {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </div>
        )}

        <button onClick={() => void bajar()} style={{
          height: 38, padding: "0 16px", borderRadius: 8, cursor: "pointer",
          fontSize: 13, fontWeight: 600, border: "1px solid var(--border-medium)",
          background: "var(--bg-input)", color: "var(--text-primary)",
        }}>⬇ Excel</button>
      </div>

      {err && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 13,
          background: "rgba(192,57,43,.12)", border: "1px solid #c0392b", color: "#e06c5f" }}>
          {err}
        </div>
      )}
      {cargando && <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
        {t("calculandoVersiones")}</div>}

      {d && !!V.length && (
        <>
          {V.some(v => v.sin_noches) && (
            <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 13,
              background: "rgba(255,193,7,.10)", border: "1px solid #c9971b", color: "#d6a626" }}>
              {t.rich("sinNochesWarn", {
                b: (c: React.ReactNode) => <b>{c}</b>,
                i: (c: React.ReactNode) => <i>{c}</i>,
                versiones: V.filter(v => v.sin_noches).map(v => v.nombre).join(" · "),
              })}
            </div>
          )}

          {V.some(v => v.pierde_por_noche) && (
            <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 13,
              background: "rgba(192,57,43,.10)", border: "1px solid #c0392b", color: "#e06c5f" }}>
              {t.rich("pierdePorNocheWarn", {
                b: (c: React.ReactNode) => <b>{c}</b>,
                versiones: V.filter(v => v.pierde_por_noche).map(v => v.nombre).join(" · "),
              })}
            </div>
          )}

          <div className="fin-scroll-x">
            <table className="fin-table" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ ...IZQ, fontSize: 11, fontWeight: 700 }}>{tc("concept")}</th>
                  {V.map(v => (
                    <th key={v.scenario_id} style={{
                      ...TD, fontSize: 11.5, fontWeight: 700,
                      opacity: v.sin_noches ? .55 : 1,
                    }} title={v.sin_noches ? t("sinEstadisticaHab") : undefined}>
                      {v.nombre}{v.sin_noches && " ⚠"}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr><td style={BANDA} colSpan={V.length + 1}>Drivers</td></tr>
                <Fila label="Total available Rooms" campo="nights_available"
                  fmt={v => num(v, 0)} />
                <Fila label="Total Rooms Occupied" campo="nights_occupied"
                  fmt={v => num(v, 0)} />
                <Fila label="% Occupancy" campo="occupancy_pct" fmt={pc} />
                <Fila label="Average Revenue per Occ. Room" campo="adr" />

                <tr><td style={BANDA} colSpan={V.length + 1}>
                  Break Even Point in Room Nights</td></tr>
                <Fila label="Variable" campo="variable" />
                <Fila label="Fixed Cost" campo="fixed" />
                <Fila label="Total Cost" campo="total_cost" resalta />
                <Fila label="Average Expense per month" campo="average_expense_per_month"
                  nota={t("notaDivisor")} />
                <Fila label="Total Revenue Hotel by Occ. Room" campo="revenue_per_night" />
                <Fila label="Variable Cost per Night" campo="variable_cost_per_night" />
                <Fila label="Contribution per Night" campo="contribution_per_night"
                  nota={t("notaContribucionPorNoche")} />
                <Fila label="Break Even Point in Nights" campo="be_nights"
                  fmt={v => num(v, 0)} resalta />
                <Fila label="%%% Occ. Rooms" campo="be_occupancy_pct" fmt={pc} />
                <Fila label="Variance in Nights" campo="variance_nights"
                  fmt={v => num(v, 0)}
                  nota={t("notaVarianzaNoches")} />
              </tbody>
            </table>
          </div>

          {/* El bloque azul de la hoja: que el costo cierre contra sus partes. */}
          <div style={{ marginTop: 18, padding: 14, borderRadius: 8,
            background: "rgba(41,98,255,.06)", border: "1px solid rgba(41,98,255,.35)" }}>
            <b style={{ fontSize: 12.5 }}>{t("validacionDelCosto")}</b>
            <div className="fin-scroll-x" style={{ marginTop: 8 }}>
              <table className="fin-table" style={{ borderCollapse: "collapse" }}>
                <tbody>
                  {([["Variable Cost", "variable_cost"], ["Fix Amount", "fix_amount"],
                     ["Total Cost", "total_cost"], [t("costoTotalSegunPl"), "costo_del_pl"],
                     ["Incomes", "incomes"],
                     [t("impuestoExcluidoBe"), "excluded"]] as const).map(([l, k]) => (
                    <tr key={k}>
                      <td style={IZQ}>{l}</td>
                      {V.map(v => (
                        <td key={v.scenario_id} style={TD}>
                          {usd(v.validacion[k] as number)}
                        </td>
                      ))}
                    </tr>
                  ))}
                  <tr style={{ fontWeight: 700, borderTop: "1px solid var(--border-medium)" }}>
                    <td style={IZQ}>Validations</td>
                    {V.map(v => (
                      <td key={v.scenario_id} style={{
                        ...TD,
                        // `null` = SIN CONTROL, y no se pinta de verde: pintar de
                        // verde lo que nadie midió es exactamente como pasaron
                        // desapercibidos $1.577.905,52.
                        color: v.validacion.cuadra === null ? "var(--text-secondary)"
                          : v.validacion.cuadra ? "#1fa363" : "#e06c5f",
                      }}>
                        {v.validacion.cuadra === null
                          ? t("sinControl")
                          : `${usd(v.validacion.diferencia)} ${v.validacion.cuadra ? "✓" : "✗"}`}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
            <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 8,
              marginBottom: 0, lineHeight: 1.6 }}>
              {t.rich("validacionNota", { b: (c: React.ReactNode) => <b>{c}</b> })}
            </p>
          </div>
        </>
      )}
    </div>
  );
}
