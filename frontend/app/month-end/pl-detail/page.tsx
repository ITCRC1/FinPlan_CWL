"use client";
/**
 * P&L Detail — Consolidado · Hotel · Club. **COPIA, bajo Cierre de Mes.**
 *
 * Owner, 2026-08-28: *«haceme una copia del reporte P&L Detail Full
 * (consolidado) y ponlo en Cierre de Mes»* · *«dale, termina, COPIA el
 * reporte»*.
 *
 * ⚠️ **Es una copia de verdad, pedida dos veces.** La primera vez se resolvió
 * con una segunda entrada de menú a `/reports/pl-detail`; el owner aclaró que
 * quería el reporte copiado. Vive acá y se toca acá.
 *
 * **Lo que eso cuesta, dicho para que no sorprenda:** son dos archivos con la
 * misma cascada. Un arreglo hecho en uno NO llega al otro, y a los tres meses
 * divergen sin que nada avise — es el mismo precio que paga este repo por ser
 * un clon de FinPlan CWL, y está documentado en `docs/CLONAR_PROPIEDAD.md`.
 * Lo que NO se duplicó es el motor: los dos leen
 * `/reports/pl-detail/{ambito}/`, así que los NÚMEROS no pueden divergir —
 * sólo la presentación.
 *
 *
 * Owner, 2026-08-27, entregando `BUDGET 2026-AMA formato.xlsx`: *«creálos en
 * Reporting con la información de presupuesto Budget 2026»*, y después *«mete
 * la estadística que estaba en el excel, y pon el botón para verlo por mes, YTD
 * o full year; y que se compare con otra versión»*.
 *
 * Son las tres primeras hojas de ese libro. La cuarta —`P&L Full Detail`— ya
 * existía en `/reports/pl-full-detail`.
 *
 * **Una pantalla y no tres.** Los tres son la misma cascada con un ámbito
 * distinto (el Hotel es el Consolidado menos el Club). Tres pantallas serían
 * tres verdades que sincronizar a mano. En el menú igual aparecen como tres
 * entradas, que es como el owner los pide.
 *
 * **Los cortes se arman acá, no se le piden al servidor.** La API manda los
 * doce meses de cada fila; Mes, YTD y Año son sumas de ese arreglo. Un viaje
 * por botón sería mandar tres veces el mismo dato.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { getScenarios, getPLDetail, type Scenario, type PLDetail } from "@/lib/api";
import { HOTEL_ID } from "@/lib/hotel";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";
import { bajarPLDetailExcel } from "@/lib/api";
import Cierre from "./Cierre";

const AMBITOS = [
  { id: "consolidado", rotulo: "Consolidado", ayuda: "Hotel + Club Madresal" },
  { id: "hotel", rotulo: "Hotel", ayuda: "Sin el Club Madresal" },
  { id: "club", rotulo: "Club Madresal", ayuda: "Sólo el departamento 260" },
] as const;

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

type Horizonte = "mes" | "ytd" | "full";

const usd = (n: number | null | undefined) =>
  n === null || n === undefined ? "—"
    : Math.abs(n) < 0.005 ? "—"
      : (n < 0 ? "(" : "") + "$" + Math.abs(n).toLocaleString("en-US",
        { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "");
const num = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });
const pct = (n: number) => (n * 100).toFixed(1) + "%";

const TD: React.CSSProperties = {
  padding: "3px 8px", textAlign: "right", fontSize: 12, whiteSpace: "nowrap",
};
const TDL: React.CSSProperties = { padding: "3px 10px", fontSize: 12.5 };

export default function PLDetailPage() {
  const sp = useSearchParams();
  const inicial = sp.get("ambito") || "consolidado";
  const [ambito, setAmbito] = useState<string>(
    AMBITOS.some(a => a.id === inicial) ? inicial : "consolidado");
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useEscenarioDe(
    "reports/pl-detail:budget", escenarios, "budget", undefined, true);
  /** Hasta tres versiones mas. Owner, 2026-08-27: «tiene que haber al menos 2
   *  versiones mas —actual, budget, forecast, actual del año pasado— pero
   *  escogibles». Su cuadro de Full Year lleva exactamente cuatro columnas. */
  const [comparar, setComparar] = useState<string[]>(["", "", ""]);
  const cmp = useMemo(() => comparar.filter(Boolean), [comparar]);
  const [horizonte, setHorizonte] = useState<Horizonte>("full");
  /** «Cascada» es el reporte completo del libro; «Cierre» es el cuadro compacto
   *  que el owner usa cada mes, con los tres cortes lado a lado. */
  const [vista, setVista] = useState<"cascada" | "cierre">("cascada");
  const [mes, setMes] = useState(12);
  const [datos, setDatos] = useState<PLDetail | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bajando, setBajando] = useState(false);

  useEffect(() => {
    const a = sp.get("ambito");
    if (a && AMBITOS.some(x => x.id === a)) setAmbito(a);
  }, [sp]);

  useEffect(() => {
    getScenarios(HOTEL_ID).then(setEscenarios).catch(() => setEscenarios([]));
  }, []);

  const cargar = useCallback(async () => {
    if (!scenarioId) return;
    setCargando(true); setError(null);
    try {
      setDatos(await getPLDetail(ambito, scenarioId, cmp));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el reporte");
      setDatos(null);
    } finally { setCargando(false); }
  }, [ambito, scenarioId, cmp]);

  useEffect(() => { cargar(); }, [cargar]);

  const act = AMBITOS.find(a => a.id === ambito)!;

  /** Qué meses entran en el corte elegido (índices 0..11). */
  const ventana = useMemo(() => {
    if (horizonte === "mes") return [mes - 1];
    if (horizonte === "ytd") return Array.from({ length: mes }, (_, i) => i);
    return Array.from({ length: 12 }, (_, i) => i);
  }, [horizonte, mes]);

  const rotuloCorte = horizonte === "full" ? "Full Year"
    : horizonte === "ytd" ? `YTD ${MESES[mes - 1]}` : MESES[mes - 1];

  const corte = useCallback(
    (serie: number[] | null | undefined) =>
      serie ? ventana.reduce((s, i) => s + (serie[i] ?? 0), 0) : null,
    [ventana]);

  /**
   * Las estadísticas del encabezado del Excel, rederivadas en el corte.
   *
   * ⚠️ **Ocupación, ADR y RevPAR NO se suman: son razones.** Se rearman con los
   * numeradores y denominadores del período. Promediar doce ADR le daría el
   * mismo peso a un mes lleno que a uno cerrado — y Amarena tiene cinco meses
   * en cero, así que el ADR del año habría salido 5/12 más bajo.
   */
  const stats = useCallback((k: PLDetail["versiones"][number]["kpis"] | undefined) => {
    if (!k) return null;
    const av = corte(k.rooms_available) ?? 0;
    const oc = corte(k.rooms_occupied) ?? 0;
    const gu = corte(k.guests) ?? 0;
    const rev = corte(k.rooms_revenue) ?? 0;
    return {
      "Total available Rooms": num(av),
      "Total Rooms Occupied": num(oc),
      "Total Guests": num(gu),
      "% Occupancy": av ? pct(oc / av) : "—",
      "Average Daily Room Only": oc ? usd(rev / oc) : "—",
      "Total RevPAR": av ? usd(rev / av) : "—",
    };
  }, [corte]);

  /** Una columna de estadisticas por version. */
  const statsPorVersion = useMemo(
    () => (datos?.versiones ?? []).map(v => stats(v.kpis)),
    [stats, datos]);

  /** Baja el Excel CON LA FORMA del cuadro. Antes usaba el exportador
   *  generico, que aplana los dos pisos de encabezado — el owner lo describio
   *  como «abre cualquier cosa», y tenia razon: doce columnas seguidas sin
   *  decir a que bloque pertenece cada una. */
  const bajar = useCallback(async () => {
    if (!datos) return;
    setBajando(true);
    try {
      const blob = await bajarPLDetailExcel(ambito, scenarioId, cmp, mes);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `PL_Detail_${act.rotulo}_${datos.year}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo bajar el Excel");
    } finally { setBajando(false); }
  }, [datos, ambito, scenarioId, cmp, mes, act]);

  const btn = (activo: boolean): React.CSSProperties => ({
    padding: "5px 12px", fontSize: 12, fontWeight: 600, border: "none",
    cursor: activo ? "default" : "pointer",
    background: activo ? "var(--brand)" : "var(--bg-surface)",
    color: activo ? "#fff" : "var(--text-primary)",
  });

  const hayVar = (datos?.versiones.length ?? 0) >= 2;
  const anchoCols = ventana.length + (datos?.versiones.length ?? 1) + (hayVar ? 2 : 0);

  return (
    <div style={{ padding: "18px 22px" }}>
      <IrA esc={scenarioId} />

      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
                    marginBottom: 12 }}>
        <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>
          P&amp;L Detail — {act.rotulo}
        </h1>

        <nav aria-label="Ámbito" style={{ display: "inline-flex", borderRadius: 6,
             overflow: "hidden", border: "1px solid var(--border-medium)" }}>
          {AMBITOS.map((a, i) => (
            <button key={a.id} onClick={() => setAmbito(a.id)} title={a.ayuda}
              style={{ ...btn(a.id === ambito),
                       borderLeft: i ? "1px solid var(--border-medium)" : "none" }}>
              {a.rotulo}
            </button>
          ))}
        </nav>

        <button onClick={bajar} disabled={!datos || bajando}
          style={{ padding: "5px 12px", fontSize: 12, borderRadius: 4, fontWeight: 600,
                   border: "none", cursor: datos ? "pointer" : "not-allowed",
                   background: "var(--accent-excel)", color: "#fff" }}>
          {bajando ? "Bajando…" : "⬇ Excel"}
        </button>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
                    marginBottom: 14 }}>
        <nav aria-label="Vista" style={{ display: "inline-flex", borderRadius: 6,
             overflow: "hidden", border: "1px solid var(--border-medium)" }}>
          {([["cascada", "Cascada"], ["cierre", "Cierre (mes · YTD · año)"]] as const)
            .map(([x, r], i) => (
              <button key={x} onClick={() => setVista(x)}
                style={{ ...btn(vista === x),
                         borderLeft: i ? "1px solid var(--border-medium)" : "none" }}>
                {r}
              </button>
            ))}
        </nav>

        <nav aria-label="Corte" style={{ display: "inline-flex", borderRadius: 6,
             overflow: "hidden", border: "1px solid var(--border-medium)" }}>
          {vista === "cierre" ? null : ([["mes", "Mes"], ["ytd", "YTD"], ["full", "Full Year"]] as const).map(
            ([h, r], i) => (
              <button key={h} onClick={() => setHorizonte(h)}
                style={{ ...btn(horizonte === h),
                         borderLeft: i ? "1px solid var(--border-medium)" : "none" }}>
                {r}
              </button>
            ))}
        </nav>

        {(horizonte !== "full" || vista === "cierre") && (
          <select value={mes} onChange={e => setMes(Number(e.target.value))}
            className="fin-input" style={{ fontSize: 12.5, padding: "5px 8px" }}>
            {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        )}

        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
          className="fin-input" style={{ fontSize: 12.5, padding: "5px 8px" }}>
          {escenarios.map(s => (
            <option key={s.id} value={s.id}>{s.year} · {s.type} {s.version}</option>
          ))}
        </select>

        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>vs</span>
        {comparar.map((c, i) => (
          <select key={i} value={c}
            onChange={e => setComparar(v => v.map((x, j) => j === i ? e.target.value : x))}
            className="fin-input" style={{ fontSize: 12.5, padding: "5px 8px" }}>
            <option value="">{i === 0 ? "— sin comparación —" : "— +versión —"}</option>
            {escenarios
              .filter(s => s.id !== scenarioId && !comparar.some((o, j) => o === s.id && j !== i))
              .map(s => (
                <option key={s.id} value={s.id}>{s.year} · {s.type} {s.version}</option>
              ))}
          </select>
        ))}
      </div>

      {error && (
        <div style={{ padding: 10, borderRadius: 5, fontSize: 12.5, marginBottom: 12,
                      background: "var(--bg-warning)" }}>{error}</div>
      )}
      {cargando && (
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>Cargando…</div>
      )}

      {!cargando && datos && (
        <>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>
            {datos.escenario} · {rotuloCorte}
            {datos.versiones.length > 1
              ? ` · vs ${datos.versiones.slice(1).map(v => v.escenario).join(" · ")}`
              : ""}
            {" · "}{act.ayuda} · USD
          </div>

          {/* Las estadísticas del Excel (filas 3–9 de sus hojas), una columna
              por versión. */}
          {statsPorVersion[0] && (
            <table className="fin-table" style={{ marginBottom: 16, minWidth: 520 }}>
              <thead>
                <tr>
                  <th style={{ ...TDL, textAlign: "left" }}>
                    ESTADÍSTICAS · {rotuloCorte}
                  </th>
                  {datos.versiones.map(v => (
                    <th key={v.scenario_id} style={TD}>{v.escenario}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.keys(statsPorVersion[0]!).map(k => (
                  <tr key={k}>
                    <td style={{ ...TDL, fontWeight: 500 }}>{k}</td>
                    {statsPorVersion.map((st, i) => (
                      <td key={i} className="mono"
                          style={{ ...TD, fontWeight: i === 0 ? 700 : 400,
                                   color: i ? "var(--text-secondary)" : undefined }}>
                        {st ? st[k as keyof typeof st] : "—"}
                      </td>
                    ))}
                  </tr>
                ))}
                {datos.club && (
                  <tr>
                    <td style={{ ...TDL, fontWeight: 500 }}>
                      Membresías (total · pagando)
                    </td>
                    <td className="mono" style={{ ...TD, fontWeight: 700 }}>
                      {datos.club.cierre.total} · {datos.club.cierre.pagando}
                    </td>
                    {datos.versiones.slice(1).map((v, i) => <td key={i} />)}
                  </tr>
                )}
              </tbody>
            </table>
          )}

          {vista === "cierre" ? <Cierre datos={datos} mes={mes} /> : (
          <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 300 + anchoCols * 95 }}>
              <thead>
                <tr>
                  <th style={{ ...TDL, textAlign: "left" }}>ACCOUNT DESCRIPTION</th>
                  {ventana.map(i => <th key={i} style={TD}>{MESES[i]}</th>)}
                  {datos.versiones.map((v, i) => (
                    <th key={v.scenario_id}
                        style={{ ...TD, fontWeight: i === 0 ? 800 : 600,
                                 borderLeft: i === 0
                                   ? "2px solid var(--border-medium)" : undefined }}>
                      {i === 0 ? `${rotuloCorte} · ${v.escenario}` : v.escenario}
                    </th>
                  ))}
                  {hayVar && (
                    <>
                      <th style={TD}>Var $</th>
                      <th style={TD}>Var %</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {datos.filas.map((f, i) => {
                  if (f.tipo === "esp") {
                    return (
                      <tr key={i}>
                        <td colSpan={anchoCols + 1} style={{ height: 7 }} />
                      </tr>
                    );
                  }
                  const fuerte = f.tipo === "tot";
                  const fondo = f.tipo === "sec" ? "var(--bg-elevated)"
                    : fuerte ? "var(--bg-subtle)" : undefined;
                  const tot = f.series.map(sr => corte(sr));
                  const a = tot[0] ?? null;
                  const b = hayVar ? (tot[1] ?? null) : null;
                  const d = a !== null && b !== null ? a - b : null;
                  // Sobre base cero no hay porcentaje: un 0% o un ∞ serían una
                  // lectura inventada. Con enero a mayo en cero pasa seguido.
                  const p = d !== null && b ? d / Math.abs(b) : null;
                  const principal = f.series[0];
                  return (
                    <tr key={i} style={{ background: fondo }}>
                      <td style={{ ...TDL,
                        fontWeight: f.tipo === "sec" || fuerte ? 700 : 400,
                        paddingLeft: f.tipo === "det" ? 24 : 10 }}>{f.rotulo}</td>
                      {principal === null || principal === undefined
                        ? <td colSpan={anchoCols} />
                        : (
                          <>
                            {ventana.map(j => (
                              <td key={j} className="mono" style={{ ...TD,
                                fontWeight: fuerte ? 700 : 400,
                                color: (principal[j] ?? 0) < 0
                                  ? "var(--negative)" : undefined,
                              }}>{usd(principal[j])}</td>
                            ))}
                            {tot.map((v, k) => (
                              <td key={k} className="mono" style={{ ...TD,
                                fontWeight: k === 0 ? 800 : 500,
                                color: (v ?? 0) < 0 ? "var(--negative)"
                                  : k ? "var(--text-secondary)" : undefined,
                                borderLeft: k === 0
                                  ? "2px solid var(--border-medium)" : undefined,
                              }}>{usd(v)}</td>
                            ))}
                            {hayVar && (
                              <>
                                <td className="mono" style={{ ...TD, fontWeight: 700,
                                  color: d === null ? undefined
                                    : d < 0 ? "var(--negative)" : "var(--positive)",
                                }}>{usd(d)}</td>
                                <td className="mono" style={{ ...TD,
                                  color: p === null ? undefined
                                    : p < 0 ? "var(--negative)" : "var(--positive)",
                                }}>{p === null ? "—" : (p * 100).toFixed(1) + "%"}</td>
                              </>
                            )}
                          </>
                        )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          )}

          {/* El cuadre del owner, con la diferencia CALCULADA. Va sobre el AÑO:
              es el que cierra contra la utilidad del motor. */}
          <div style={{ marginTop: 16, padding: "10px 14px", borderRadius: 6,
            fontSize: 12.5, border: "1px solid var(--border-medium)",
            background: "var(--bg-surface)", display: "flex", gap: 22,
            flexWrap: "wrap", alignItems: "center" }}>
            <strong>Control (año completo)</strong>
            <span>Ingresos {usd(datos.control.ingresos)}</span>
            <span>Gastos {usd(datos.control.gastos)}</span>
            <span>Utilidad {usd(datos.control.utilidad)}</span>
            <span style={{ fontWeight: 700,
              color: Math.abs(datos.control.diferencia) < 0.01
                ? "var(--positive)" : "var(--negative)" }}>
              Diferencia {datos.control.diferencia.toFixed(2)}
              {Math.abs(datos.control.diferencia) < 0.01 ? " ✓" : " ⚠"}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
