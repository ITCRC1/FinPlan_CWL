"use client";
/**
 * El P&L de UNA versión, mes a mes, en el tab de Cierre de Mes.
 *
 * Owner, 2026-08-28: *«necesito meter en el tab Cierre de mes un sub tab que
 * tenga 12 meses, y una versión para escoger»*.
 *
 * **Por qué una sola versión y no las cuatro ranuras del resto de la pantalla.**
 * Los demás sub-tabs comparan versiones en UN período; éste hace lo contrario:
 * una versión a lo largo del año. Meterle las cuatro daría 48 columnas y
 * dejaría de leerse — que es justo lo que este cuadro sirve para evitar.
 *
 * **De dónde sale.** `/pl/{id}/doce-meses/`, que devuelve los doce SIN agregar.
 * No es `/pl/compare-range/` doce veces: ése agrega el rango en una columna, y
 * el ADR y el impuesto no son aditivos, así que sumar o restar columnas ya
 * armadas daría un número que no es de nadie.
 */
import { sembrarTres } from "@/lib/escenarioPreferido";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getPLDoceMeses, getPLManualInputs, savePLManualInput,
         type PLDoceMeses, type PLManualInput, type Scenario } from "@/lib/api";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

/** Las líneas del cuadro, en el orden del P&L. Es el mismo esqueleto que usa el
 *  resumen mensual: totales, no el detalle por departamento — para eso están
 *  los otros sub-tabs. */
const FILAS: { code: string; label: string; fuerte?: boolean; sangria?: boolean }[] = [
  { code: "K_ROOMS_AVAIL", label: "Total Rooms Available" },
  { code: "K_ROOMS_OCC", label: "Total Rooms Occupied" },
  { code: "K_OCC", label: "Occupancy %" },
  { code: "K_ADR", label: "ADR" },
  { code: "K_REVPAR", label: "RevPAR" },
  { code: "TOTAL_REVENUES", label: "Total Revenue", fuerte: true },
  { code: "TOTAL_OPEXP", label: "Total Operating Expenses", sangria: true },
  { code: "TOTAL_OP_PROFIT", label: "Operating Profit", fuerte: true },
  { code: "TOTAL_OVERHEAD", label: "Total Overhead", sangria: true },
  { code: "GOP", label: "GOP", fuerte: true },
  { code: "TOTAL_NON_OP", label: "Total Non-Op Expenses", sangria: true },
  { code: "EBITDA_BEFORE", label: "EBITDA before Capital", fuerte: true },
  { code: "CAPITAL_EXPENSE", label: "Capital Expense", sangria: true },
  { code: "EBITDA_AFTER", label: "EBITDA after Capital", fuerte: true },
  { code: "EBT", label: "Earnings before Taxes", fuerte: true },
  { code: "INCOME_TAXES", label: "Income Taxes", sangria: true },
  { code: "NET_PROFIT", label: "Net Profit", fuerte: true },
];

const KPI = new Set(["K_ROOMS_AVAIL", "K_ROOMS_OCC", "K_OCC", "K_ADR", "K_REVPAR"]);

const usd = (n: number) =>
  Math.abs(n) < 0.005 ? "—"
    : (n < 0 ? "(" : "") + "$" + Math.abs(n).toLocaleString("en-US",
      { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "");
const num = (n: number) => (n ? n.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—");
const pct = (n: number) => (n ? (n * 100).toFixed(1) + "%" : "—");

const TD: React.CSSProperties = {
  padding: "3px 8px", textAlign: "right", fontSize: 11.5, whiteSpace: "nowrap",
};
const TDL: React.CSSProperties = { padding: "3px 10px", fontSize: 12 };

/** El primero de un tipo, para arrancar en lo obvio sin quitarle la opción de
 *  cambiar. Owner, 2026-08-28: «siempre aparece actual y el otro budget, pero
 *  con opción a cambiar». */
/** El escenario con el que abrir, para un papel.
 *
 *  ⚠️ Usa `sembrarTres` —la regla del owner— y NO `escenarios.find(...)`.
 *  Esa era la versión anterior, copiada en los cuatro sub-tabs: devolvía el
 *  PRIMERO de ese tipo, y `GET /scenarios/` ordena por año descendente, así
 *  que el primer BUDGET de la lista es el Working **2035**. Cada sub-tab abría
 *  en un presupuesto real, vacío y de otro año — sin que nada fallara. */
function primeroDe(escenarios: Scenario[], tipo: string): string {
  const tres = sembrarTres(escenarios);
  const id = tipo === "ACTUAL" ? tres.actual
    : tipo === "BUDGET" ? tres.budget
    : tipo === "FORECAST" ? tres.forecast : "";
  // El respaldo se queda: si NO hay ninguno de ese tipo, mejor mostrar algo
  // que un selector en blanco sin explicación.
  return id || escenarios.find(s => s.type === tipo)?.id || escenarios[0]?.id || "";
}

export default function DoceMeses({ escenarios, inicial, compacto = true }: {
  escenarios: Scenario[];
  /** El escenario que la pantalla ya tenía elegido, para no arrancar en blanco. */
  inicial?: string;
  /** Esconder las líneas que están en cero los doce meses. Lo manda la pantalla,
   *  así el interruptor es uno solo para todos los sub-tabs. */
  compacto?: boolean;
}) {
  /** Dos paneles, no dos pantallas: el de ACTUAL y el de BUDGET. Cada uno
   *  recuerda SU versión, así cambiar de panel no pierde lo que se eligió en el
   *  otro — que es lo que pasaría con un solo selector compartido. */
  const [panel, setPanel] = useState<"actual" | "budget">("actual");
  const [vActual, setVActual] = useState("");
  const [vBudget, setVBudget] = useState("");
  const scenarioId = panel === "actual" ? vActual : vBudget;
  const setScenarioId = panel === "actual" ? setVActual : setVBudget;
  const [datos, setDatos] = useState<PLDoceMeses | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!escenarios.length) return;
    // ⚠️ El panel de BUDGET arranca en un BUDGET, NO en `inicial`.
    //
    // Owner, 2026-09-02: «12 meses actual y budget working 2026 como estándar».
    // `inicial` es la ranura 1 de la pantalla, que casi siempre trae el ACTUAL:
    // el panel de Budget abria mostrando el Actual y habia que corregirlo a
    // mano cada vez. Se deja como respaldo, detras del BUDGET.
    setVActual(x => x || primeroDe(escenarios, "ACTUAL"));
    setVBudget(x => x || primeroDe(escenarios, "BUDGET") || inicial || "");
  }, [escenarios, inicial]);

  const cargar = useCallback(async () => {
    if (!scenarioId) return;
    setCargando(true); setError(null);
    try {
      setDatos(await getPLDoceMeses(scenarioId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el año");
      setDatos(null);
    } finally { setCargando(false); }
  }, [scenarioId]);

  useEffect(() => { cargar(); }, [cargar]);

  /** {code: [12 valores]} — los KPI salen de `kpis`, el resto de las líneas. */
  const serie = useMemo(() => {
    const out: Record<string, number[]> = {};
    for (const f of FILAS) out[f.code] = Array(12).fill(0);
    for (const m of datos?.meses ?? []) {
      const i = m.month - 1;
      out.K_ROOMS_AVAIL[i] = m.kpis.rooms_available;
      out.K_ROOMS_OCC[i] = m.kpis.rooms_occupied;
      out.K_OCC[i] = m.kpis.occupancy_pct;
      out.K_ADR[i] = m.kpis.adr;
      out.K_REVPAR[i] = m.kpis.revpar;
      for (const l of m.lines) {
        if (l.line_code in out && !KPI.has(l.line_code)) {
          out[l.line_code][i] = l.amount_usd;
        }
      }
    }
    return out;
  }, [datos]);

  /**
   * El total del año. ⚠️ **La ocupación, el ADR y el RevPAR NO se suman: son
   * razones.** Se rederivan con los doce meses de numerador y denominador —
   * promediarlos le daría el mismo peso a un mes lleno que a uno cerrado.
   */
  const anual = useCallback((code: string) => {
    const s = serie[code] ?? [];
    const av = (serie.K_ROOMS_AVAIL ?? []).reduce((a, b) => a + b, 0);
    const oc = (serie.K_ROOMS_OCC ?? []).reduce((a, b) => a + b, 0);
    if (code === "K_OCC") return av ? oc / av : 0;
    if (code === "K_ADR" || code === "K_REVPAR") {
      // El ingreso de habitaciones del año, reconstruido de ADR × noches.
      const rev = (serie.K_ADR ?? []).reduce(
        (t, adr, i) => t + adr * ((serie.K_ROOMS_OCC ?? [])[i] ?? 0), 0);
      return code === "K_ADR" ? (oc ? rev / oc : 0) : (av ? rev / av : 0);
    }
    return s.reduce((a, b) => a + b, 0);
  }, [serie]);

  // ── Lo editable del Budget ────────────────────────────────────────────────
  //
  // Owner, 2026-08-28: «12 meses budget pero que quede editable».
  //
  // ⚠️ **Sólo los PORCENTAJES.** Viven en `pl_manual_inputs` y ésa es su única
  // puerta. Los MONTOS de abajo del GOP —renta, seguro, capex, depreciación—
  // ya se digitan en el checkbook de Gastos de Propiedad, y meterlos también
  // acá sería una segunda puerta al mismo número: el día que difieran, nadie
  // sabría cuál mandó. La pantalla de Management Fees ya lo dice en su código.
  const EDITABLES: { campo: keyof PLManualInput; label: string }[] = [
    { campo: "mgmt_fee_pct_3", label: "Management Fee 3 %" },
    { campo: "mgmt_fee_pct_5", label: "Management Fee 5 %" },
    { campo: "capital_reserve_pct", label: "Capital Reserve %" },
    { campo: "income_tax_rate", label: "Income Tax %" },
  ];
  const [manual, setManual] = useState<PLManualInput[]>([]);
  const [guardando, setGuardando] = useState<string | null>(null);
  const editable = panel === "budget";

  useEffect(() => {
    if (!scenarioId || !editable) { setManual([]); return; }
    getPLManualInputs(scenarioId).then(setManual).catch(() => setManual([]));
  }, [scenarioId, editable]);

  const valorManual = (campo: keyof PLManualInput, mes: number) => {
    const f = manual.find(x => x.month === mes);
    // Se guarda como fracción y se muestra como porcentaje: 0.05 → 5.
    return f ? String(Number(f[campo] ?? 0) * 100) : "0";
  };

  /** Guarda UN mes y recarga el año: el P&L lee estos parámetros al calcular,
   *  así que el efecto se ve sin recalcular nada a mano. */
  const guardar = useCallback(async (campo: keyof PLManualInput, mes: number,
                                     texto: string) => {
    if (!scenarioId) return;
    const n = Number(texto.replace(",", "."));
    if (!isFinite(n)) return;
    setGuardando(`${campo}-${mes}`); setError(null);
    try {
      await savePLManualInput(scenarioId, mes, { [campo]: String(n / 100) });
      setManual(await getPLManualInputs(scenarioId));
      await cargar();
    } catch (e) {
      // El 409 del candado tiene que decirse, no tragarse: si no, el usuario
      // escribe, ve el número volver al viejo y no sabe por qué.
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    } finally { setGuardando(null); }
  }, [scenarioId, cargar]);

  const fmt = (code: string, v: number) =>
    code === "K_OCC" ? pct(v)
      : code === "K_ROOMS_AVAIL" || code === "K_ROOMS_OCC" ? num(v)
        : usd(v);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
                    marginBottom: 12 }}>
        <nav aria-label="Panel" style={{ display: "inline-flex", borderRadius: 6,
             overflow: "hidden", border: "1px solid var(--border-medium)" }}>
          {([["actual", "12 meses Actual"], ["budget", "12 meses Budget"]] as const)
            .map(([k, r], i) => (
              <button key={k} onClick={() => setPanel(k)} style={{
                padding: "5px 13px", fontSize: 12, fontWeight: 600, border: "none",
                borderLeft: i ? "1px solid var(--border-medium)" : "none",
                cursor: panel === k ? "default" : "pointer",
                background: panel === k ? "var(--brand)" : "var(--bg-surface)",
                color: panel === k ? "#fff" : "var(--text-primary)",
              }}>{r}</button>
            ))}
        </nav>

        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
          VERSIÓN
        </span>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
          className="fin-input" style={{ fontSize: 12.5, padding: "5px 8px" }}>
          {escenarios.map(s => (
            <option key={s.id} value={s.id}>{s.year} · {s.type} {s.version}</option>
          ))}
        </select>
        {datos && (
          <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            {datos.escenario} · los doce meses · USD
          </span>
        )}
      </div>

      {error && (
        <div style={{ padding: 10, borderRadius: 5, fontSize: 12.5, marginBottom: 12,
                      background: "var(--bg-warning)" }}>{error}</div>
      )}
      {cargando && (
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>Cargando…</div>
      )}

      {!cargando && datos && (
        <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1250 }}>
            <thead>
              <tr>
                <th style={{ ...TDL, textAlign: "left" }}>INDICADOR</th>
                {MESES.map(m => <th key={m} style={TD}>{m}</th>)}
                <th style={{ ...TD, fontWeight: 800,
                             borderLeft: "2px solid var(--border-medium)" }}>Año</th>
              </tr>
            </thead>
            <tbody>
              {FILAS.filter(f => !compacto
                  || (serie[f.code] ?? []).some(v => Math.abs(v) >= 0.005)
                ).map(f => {
                const s = serie[f.code] ?? [];
                const tot = anual(f.code);
                return (
                  <tr key={f.code} style={{
                    background: f.fuerte ? "var(--bg-subtle)" : undefined,
                  }}>
                    <td style={{ ...TDL, fontWeight: f.fuerte ? 700 : 500,
                                 paddingLeft: f.sangria ? 24 : 10 }}>{f.label}</td>
                    {s.map((v, i) => (
                      <td key={i} className="mono" style={{ ...TD,
                        fontWeight: f.fuerte ? 700 : 400,
                        color: v < 0 ? "var(--negative)" : undefined,
                      }}>{fmt(f.code, v)}</td>
                    ))}
                    <td className="mono" style={{ ...TD, fontWeight: 800,
                      borderLeft: "2px solid var(--border-medium)",
                      color: tot < 0 ? "var(--negative)" : undefined,
                    }}>{fmt(f.code, tot)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!cargando && datos && editable && (
        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>
            PARÁMETROS EDITABLES · {datos.escenario}
          </div>
          <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginBottom: 8 }}>
            Se guardan al salir de la celda y el cuadro de arriba se actualiza solo.
            Los montos de abajo del GOP —renta, seguro, capex, depreciación— se
            digitan en Gastos de Propiedad, que es su única puerta.
          </div>
          <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 1100 }}>
              <thead>
                <tr>
                  <th style={{ ...TDL, textAlign: "left" }}>PARÁMETRO</th>
                  {MESES.map(m => <th key={m} style={TD}>{m}</th>)}
                </tr>
              </thead>
              <tbody>
                {EDITABLES.map(({ campo, label }) => (
                  <tr key={String(campo)}>
                    <td style={{ ...TDL, fontWeight: 500 }}>{label}</td>
                    {MESES.map((_m, i) => (
                      <td key={i} style={{ ...TD, padding: "2px 4px" }}>
                        <input
                          className="fin-input mono"
                          defaultValue={valorManual(campo, i + 1)}
                          key={`${campo}-${i}-${scenarioId}-${manual.length}`}
                          inputMode="decimal"
                          onBlur={e => {
                            const v = e.target.value;
                            if (v !== valorManual(campo, i + 1)) guardar(campo, i + 1, v);
                          }}
                          onKeyDown={e => {
                            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                          }}
                          disabled={guardando !== null}
                          style={{ width: 62, textAlign: "right", padding: "3px 5px",
                                   fontSize: 11.5 }} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
